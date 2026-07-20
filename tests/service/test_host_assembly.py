"""``dayu.service.host_assembly`` 组合 helper 测试。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts import (
    AgentFallbackMode,
    AsyncDirectToolExecutionCapability,
    BatchToolExecutionContext,
    JsonValue,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    ToolCallRequest,
    ToolCancelledOutcome,
    ToolDefinition,
    ToolAwaitingOutcome,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine import AgentPolicy
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy
from dayu.fins.direct_events import FinsOperationKind
from dayu.fins.ingestion.awaiting_resolution import AwaitingResolutionMode
from dayu.fins.ingestion.observation_handle import (
    FinsObservationHandle,
    FinsObservationSnapshot,
    FinsObservationStatus,
    parse_observation_handle_id_token,
)
from dayu.service.fins_wait_adapter import (
    FINS_INGESTION_WAIT_ADAPTER_KEY,
    FinsIngestionWaitActivationAdapter,
    FinsIngestionWaitPollAdapter,
)
from dayu.fins.ingestion_runtime import FinsIngestionRuntime
from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME, FinsDownloadToolCallable
from dayu.fins.tools.preprocess_tools import PREPROCESS_TOOL_NAME
from dayu.fins.tools.upload_tools import UPLOAD_TOOL_NAME
from dayu.contracts.tool_await import ToolAwaitKind
from dayu.host.api import (
    AuthorizationClaim,
    FollowupBehavior,
    HostCallContext,
    OperationContext,
)
from dayu.host.tool_duplicate_governance import (
    DuplicateDecisionKind,
)
from dayu.host.wait_adapter import WaitActivationRequest, WaitResumePolicy
from dayu.host.waiting import ToolAwaitingAcceptedAck, ToolAwaitingEventRef
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig
from dayu.runtime.config_loader import (
    ToolDuplicateGovernanceMessagesConfig,
    ToolDuplicateGovernancePolicyConfig,
    ToolDiscoveryEntryPointConfig,
    ToolDiscoveryProviderConfig,
)
from dayu.runtime.location import RuntimeLocations, resolve_runtime_locations
from dayu.runtime.assembly import RuntimeAssemblySelectionError
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    SceneAgentPolicyOverride,
    ScenePrepareRequest,
    SceneToolCatalog,
    SceneToolSelectionMode,
    SceneToolSelectionResult,
    prepare_scene,
)
from dayu.runtime.workspace_paths import resolve_workspace_path
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceDiscoveredTools,
    ServiceOpenHostAssemblyRequest,
    ServiceOpenHostAssemblyResult,
    ServiceRunOverrides,
    _agent_fallback_mode_from_config,
    _active_fins_awaiting_provider_metadata,
    _compactor_agent_policy_from_scene_inputs,
    _compactor_prompts_from_scene_inputs,
    _duplicate_decision_from_config,
    _fins_awaiting_provider_metadata_from_configs,
    _render_headers,
    _is_fins_workspace_bound_provider_config,
    _resolve_prompt_asset_path,
    _runner_spec_from_model,
    _tool_discovery_spec,
    _tooling_options_from_discovery,
    _wait_poller_policy_for_composition,
    assemble_effective_tool_provider_configs,
    compose_open_host_options,
    compose_submit_followup_request,
    compose_submit_followup_request_with_overrides,
    discover_service_tools,
)

_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_SCENE_ID = "smoke_host_public_multiturn"
_CUSTOM_COMPACTOR_SCENE_ID = "custom_compactor_scene"
_CURRENT_TIME_TEXT = (
    "# 当前时间\n"
    "现在是 2026年7月7日 17:20（Asia/Shanghai，星期二）。\n"
    "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
)
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"
_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION: Final[int] = 5
_DISCOVERY_REPLACEMENT_TOOL_NAME: Final[str] = "discovery_replacement_smoke"


def _scene_tool_catalog(discovered_tools: ServiceDiscoveredTools) -> SceneToolCatalog:
    """从测试发现结果构造 scene 工具目录。

    :param discovered_tools: Service 工具发现结果。
    :returns: SceneToolCatalog。
    :raises AssertionError: 测试配置未发现工具时抛出。
    """

    return SceneToolCatalog.from_tool_bundle(discovered_tools.tool_bundle)


def _discover_service_tools_for_workspace(
    config: RuntimeConfig,
    *,
    workspace_root: Path,
) -> ServiceDiscoveredTools:
    """按测试 workspace 装配 effective configs 后发现工具。

    :param config: ConfigLoader 输出的 runtime typed config。
    :param workspace_root: 测试 workspace root。
    :returns: Service 工具发现结果。
    :raises Exception: effective config 装配或工具发现失败时向上抛出。
    """

    effective_provider_configs = assemble_effective_tool_provider_configs(
        tuple(config.tool_discovery.providers.values()),
        workspace_root=workspace_root,
    )
    return discover_service_tools(effective_provider_configs)


def _complete_compactor_agent_policy_override() -> SceneAgentPolicyOverride:
    """构造完整 compactor scene AgentPolicy override。

    :returns: 完整的 scene agent policy override。
    :raises Exception: 不主动抛出异常。
    """

    return SceneAgentPolicyOverride(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=False,
        tool_execution_timeout_seconds=1.0,
        fallback_mode=AgentFallbackMode.RAISE_ERROR,
        fallback_prompt="Compactor is not allowed to fallback-answer.",
        continuation_prompt="Continue strict JSON.",
        max_consecutive_failed_tool_batches=1,
    )


def test_compose_open_host_options_uses_runtime_tuning_from_config(
    tmp_path: Path,
) -> None:
    """Service helper 使用 host_runtime schema 字段装配 Host opener tuning。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: helper 未按配置映射 Host opener 字段时抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    _write_host_runtime_overlay(tmp_path)
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    assert result.options.sqlite_write_busy_retry_count == 3
    assert result.options.sqlite_write_retry_initial_delay_seconds == 0.002
    assert result.options.sqlite_write_retry_backoff_multiplier == 1.25
    assert result.options.sqlite_write_retry_max_delay_seconds == 0.03
    assert result.options.payload_inline_threshold_bytes == 2048
    assert result.options.worker_startup_timeout_seconds == 4.5
    assert result.options.enable_truncation_manager is True
    policy = result.options.wait_poller_policy
    assert policy is not None
    assert policy.poll_interval_seconds == 0.4
    assert policy.claim_ttl_seconds == 41.0
    assert policy.claim_batch_size == 42
    assert policy.max_outstanding_adapter_calls == 5
    assert result.options.tooling_options is not None
    process_policy = result.options.tooling_options.process_capsule_interrupt_policy
    assert process_policy.terminate_grace_seconds == 0.35
    assert process_policy.kill_grace_seconds == 0.75
    assert result.options.memory_projection_policy.evidence_fact_item_cap == 256
    context_budget_policy = result.options.context_budget_policy
    assert context_budget_policy is not None
    assert context_budget_policy.max_compaction_attempts_per_operation == _EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION
    assert result.options.ordinary_run_baseline.runner_spec.headers["Authorization"] == f"Bearer {_API_KEY}"
    assert (
        result.options.ordinary_run_baseline.runner_spec.client_correlation_policy
        is ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID
    )
    assert result.options.ordinary_run_baseline.runner_options.max_tokens is None
    compactor_baseline = result.options.compactor_runner_baseline
    assert compactor_baseline is not None
    assert (
        compactor_baseline.compactor_runner_spec.client_correlation_policy
        is ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID
    )
    assert compactor_baseline.compactor_runner_options.temperature == 0.4
    assert compactor_baseline.compactor_runner_options.max_tokens is None
    assert compactor_baseline.compactor_runner_options.top_p == 1.0
    assert compactor_baseline.compactor_runner_options.stream is False
    assert compactor_baseline.compactor_agent_policy == AgentPolicy(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=False,
        tool_execution_timeout_seconds=1.0,
        fallback_mode=AgentFallbackMode.RAISE_ERROR,
        fallback_prompt="Compactor is not allowed to fallback-answer.",
        continuation_prompt=("Continue the strict JSON object without repeating content already emitted."),
        max_consecutive_failed_tool_batches=1,
    )
    assert "compaction_request" in compactor_baseline.compactor_system_prompt
    assert "严格 JSON" in compactor_baseline.compactor_system_prompt
    assert "<<compaction_request>>" in (compactor_baseline.compactor_user_prompt_template)
    assert result.options.ordinary_run_baseline.agent_policy.max_iterations == 20
    assert result.options.ordinary_run_baseline.agent_policy.continuation_max_attempts == 2
    assert result.diagnostics.model_source == "run_override"
    assert result.diagnostics.execution_profile_id == "standard-256k"
    assert result.diagnostics.ordinary_profile_compatibility.status == "conservative"
    assert result.diagnostics.ordinary_profile_compatibility.profile_id == "standard-256k"
    assert result.diagnostics.ordinary_profile_compatibility.selected_model_id == _MODEL_ID
    assert result.diagnostics.tool_selection == ("mode=select,tools=record_smoke_fact")


def test_compose_open_host_options_projects_complete_config_owned_wait_policy(
    tmp_path: Path,
) -> None:
    """Service 必须把完整 ConfigLoader snapshot 一对一投影给 Host。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 12 字段投影缺失或改值时抛出。
    """

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = _compactor_scene_inputs(agent_policy_override=None)

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    policy = result.options.wait_poller_policy
    assert policy is not None
    assert policy.enabled is True
    assert policy.poll_interval_seconds == 1.0
    assert policy.claim_ttl_seconds == 60.0
    assert policy.claim_batch_size == 100
    assert policy.backoff_initial_delay_seconds == 30.0
    assert policy.backoff_multiplier == 2.0
    assert policy.backoff_max_delay_seconds == 300.0
    assert policy.not_ready_observe_interval_seconds == 1.0
    assert policy.idle_poll_interval_seconds == 5.0
    assert policy.adapter_call_timeout_seconds == 30.0
    assert policy.close_drain_timeout_seconds == 5.0
    assert policy.max_outstanding_adapter_calls == 8
    runtime_snapshot = result.host_runtime.wait_poller_policy
    assert runtime_snapshot.adapter_call_timeout_seconds == 30.0
    assert runtime_snapshot.max_outstanding_adapter_calls == 8


def test_replacing_discovered_bundle_preserves_host_wait_composition(
    tmp_path: Path,
) -> None:
    """替换 discovery bundle 时必须保留 owner 产出的 Host wait composition。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 派生 discovery 丢失 binding、registry 或 policy 时抛出。
    """

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(
        config,
        workspace_root=tmp_path,
    )
    replaced_discovered_tools = replace(
        discovered_tools,
        tool_bundle=ToolBundle(
            definitions=(
                *discovered_tools.tool_bundle.definitions,
                _tool_definition(_DISCOVERY_REPLACEMENT_TOOL_NAME),
            )
        ),
    )
    request = ServiceOpenHostAssemblyRequest(
        workspace_root=tmp_path,
        config=config,
        locations=locations,
        scene_inputs=_compactor_scene_inputs(agent_policy_override=None),
        discovered_tools=discovered_tools,
        overrides=ServiceAssemblyOverrides(
            host_runtime_id="local",
            execution_profile_id="standard-256k",
            model_id=_MODEL_ID,
            runner_option_hint_id=_RUNNER_HINT_ID,
        ),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )

    original_result = compose_open_host_options(request)
    replaced_result = compose_open_host_options(replace(request, discovered_tools=replaced_discovered_tools))

    assert original_result.options.wait_poller_policy is not None
    assert replaced_result.options.wait_poller_policy == original_result.options.wait_poller_policy
    original_tooling = original_result.options.tooling_options
    replaced_tooling = replaced_result.options.tooling_options
    assert original_tooling is not None
    assert replaced_tooling is not None
    assert _DISCOVERY_REPLACEMENT_TOOL_NAME in {
        definition.name for definition in replaced_tooling.business_tool_bundle.definitions
    }
    original_bindings = original_tooling.wait_adapter_registry
    replaced_bindings = replaced_tooling.wait_adapter_registry
    assert original_bindings is not None
    assert replaced_bindings is not None
    for tool_name in (DOWNLOAD_TOOL_NAME, PREPROCESS_TOOL_NAME, UPLOAD_TOOL_NAME):
        assert replaced_bindings.resolve_binding(
            tool_name=tool_name,
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
        ) == original_bindings.resolve_binding(
            tool_name=tool_name,
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
        )
    original_activation = original_tooling.wait_activation_registry
    replaced_activation = replaced_tooling.wait_activation_registry
    assert original_activation is not None
    assert replaced_activation is not None
    assert replaced_activation.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY) == original_activation.resolve_adapter(
        FINS_INGESTION_WAIT_ADAPTER_KEY
    )
    original_poll = original_tooling.wait_poll_adapter_registry
    replaced_poll = replaced_tooling.wait_poll_adapter_registry
    assert original_poll is not None
    assert replaced_poll is not None
    assert replaced_poll.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY) == original_poll.resolve_adapter(
        FINS_INGESTION_WAIT_ADAPTER_KEY
    )


@pytest.mark.parametrize(
    "tool_selection",
    (
        SceneToolSelectionResult(
            mode=SceneToolSelectionMode.ALL,
            tool_names=None,
        ),
        SceneToolSelectionResult(
            mode=SceneToolSelectionMode.SELECT,
            tool_names=frozenset({DOWNLOAD_TOOL_NAME}),
        ),
        SceneToolSelectionResult(
            mode=SceneToolSelectionMode.NONE,
            tool_names=frozenset(),
        ),
    ),
)
def test_scene_tool_selection_does_not_own_wait_poller_composition(
    tmp_path: Path,
    tool_selection: SceneToolSelectionResult,
) -> None:
    """all/select/none 只改变工具暴露，不改变相同 owner inputs 的 policy。

    :param tmp_path: pytest 临时 workspace root。
    :param tool_selection: 本 case 的 scene 工具选择。
    :returns: ``None``。
    :raises AssertionError: scene selection 影响 Host opener policy 时抛出。
    """

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(
        config,
        workspace_root=tmp_path,
    )
    scene_inputs = replace(
        _compactor_scene_inputs(agent_policy_override=None),
        tool_selection=tool_selection,
    )
    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    policy = result.options.wait_poller_policy
    assert policy is not None
    assert policy.enabled is True
    assert policy.claim_batch_size == 100


def test_service_provider_boundary_builds_one_typed_mode_collection(
    tmp_path: Path,
) -> None:
    """Service 必须一次构造 poll/callback/manual typed metadata。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: typed mode 顺序或值与 provider owner 输入不一致时抛出。
    """

    workspace_root = tmp_path.resolve(strict=False)
    metadata = _fins_awaiting_provider_metadata_from_configs(
        (
            _provider_config_with_mode(
                provider_id="financial-download-tools",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="dayu.fins.tools.download_provider",
                workspace_root=workspace_root,
                mode="poll",
            ),
            _provider_config_with_mode(
                provider_id="financial-preprocess-tools",
                import_path="dayu.fins.tools.preprocess_provider:discover_tools",
                source_id="dayu.fins.tools.preprocess_provider",
                workspace_root=workspace_root,
                mode="callback",
            ),
            _provider_config_with_mode(
                provider_id="financial-upload-tools",
                import_path="dayu.fins.tools.upload_provider:discover_tools",
                source_id="dayu.fins.tools.upload_provider",
                workspace_root=workspace_root,
                mode="manual",
            ),
        )
    )

    assert tuple(item.mode for item in metadata) == (
        AwaitingResolutionMode.POLL,
        AwaitingResolutionMode.CALLBACK,
        AwaitingResolutionMode.MANUAL,
    )
    assert all(item.workspace_root == workspace_root for item in metadata)


@pytest.mark.parametrize("mode", ("poll", "callback", "manual"))
def test_disabled_fins_provider_parses_legal_mode_before_active_filter(
    tmp_path: Path,
    mode: str,
) -> None:
    """disabled Fins provider 的合法 mode 必须先校验、再排除 active 集合。

    :param tmp_path: pytest 临时 workspace。
    :param mode: 合法 raw mode。
    :returns: ``None``。
    :raises AssertionError: disabled provider 进入 active metadata 时抛出。
    """

    provider = _provider_config_with_mode(
        provider_id="financial-download-tools",
        import_path="dayu.fins.tools.download_provider:discover_tools",
        source_id="dayu.fins.tools.download_provider",
        workspace_root=tmp_path.resolve(strict=False),
        mode=mode,
        enabled=False,
    )

    assert _fins_awaiting_provider_metadata_from_configs((provider,)) == ()


def test_disabled_fins_provider_illegal_mode_fails_before_active_filter(
    tmp_path: Path,
) -> None:
    """disabled Fins provider 也不得绕过 owner mode parser。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: illegal mode 未 fail-fast 时抛出。
    """

    provider = _provider_config_with_mode(
        provider_id="financial-download-tools",
        import_path="dayu.fins.tools.download_provider:discover_tools",
        source_id="dayu.fins.tools.download_provider",
        workspace_root=tmp_path.resolve(strict=False),
        mode="POLL",
        enabled=False,
    )

    with pytest.raises(ValueError, match="awaiting_resolution_mode"):
        _fins_awaiting_provider_metadata_from_configs((provider,))


@pytest.mark.parametrize(
    ("provider_id", "import_path", "source_id"),
    (
        (
            "financial-read-tools",
            "dayu.fins.tools.provider:discover_tools",
            "dayu.fins.tools.provider",
        ),
        ("web-tools", "dayu.tools.web:discover_tools", "dayu.tools.web"),
    ),
)
def test_recognized_non_awaiting_provider_rejects_mode_field_presence_only(
    provider_id: str,
    import_path: str,
    source_id: str,
) -> None:
    """recognized non-awaiting provider 只按字段存在性拒绝误用。

    :param provider_id: provider id。
    :param import_path: provider import path。
    :param source_id: provider source id。
    :returns: ``None``。
    :raises AssertionError: raw object 被 loose parse 或误用未失败时抛出。
    """

    provider = _provider_config_with_config(
        provider_id=provider_id,
        import_path=import_path,
        source_id=source_id,
        config={"awaiting_resolution_mode": {"opaque": "do-not-parse"}},
    )

    with pytest.raises(ValueError, match="must not declare"):
        _fins_awaiting_provider_metadata_from_configs((provider,))


def test_unknown_third_party_provider_mode_field_remains_opaque() -> None:
    """未知第三方 provider 的同名字段不由 R04 发明新语义。

    :returns: ``None``。
    :raises AssertionError: Service 解析未知 provider raw value 时抛出。
    """

    provider = _provider_config_with_config(
        provider_id="third-party-tools",
        import_path="third_party.tools:discover",
        source_id="third_party.tools",
        config={"awaiting_resolution_mode": {"opaque": "provider-owned"}},
    )

    assert _fins_awaiting_provider_metadata_from_configs((provider,)) == ()


def test_manual_mode_composes_binding_without_background_poller(
    tmp_path: Path,
) -> None:
    """仅 manual provider 必须保留 activation/binding 且不传 poller policy。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: manual 被降级为 poll 或启动 poller 时抛出。
    """

    result = _compose_with_fins_provider_configs(
        tmp_path=tmp_path,
        provider_configs=(
            _provider_config_with_mode(
                provider_id="financial-download-tools",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="dayu.fins.tools.download_provider",
                workspace_root=tmp_path.resolve(strict=False),
                mode="manual",
            ),
        ),
    )

    assert result.options.wait_poller_policy is None
    tooling = result.options.tooling_options
    assert tooling is not None
    assert tooling.wait_activation_registry is not None
    assert tooling.wait_poll_adapter_registry is None
    assert tooling.wait_adapter_registry is not None
    binding = tooling.wait_adapter_registry.resolve_binding(
        tool_name=DOWNLOAD_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    assert binding is not None
    assert binding.resume_policy is WaitResumePolicy.MANUAL


def test_poll_and_manual_modes_partition_runtime_composition(
    tmp_path: Path,
) -> None:
    """poll+manual 必须启动 poller，但 manual binding 保持 MANUAL。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: typed modes 或 poll runtime 分区错误时抛出。
    """

    workspace_root = tmp_path.resolve(strict=False)
    result = _compose_with_fins_provider_configs(
        tmp_path=tmp_path,
        provider_configs=(
            _provider_config_with_mode(
                provider_id="financial-download-tools",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="dayu.fins.tools.download_provider",
                workspace_root=workspace_root,
                mode="poll",
            ),
            _provider_config_with_mode(
                provider_id="financial-preprocess-tools",
                import_path="dayu.fins.tools.preprocess_provider:discover_tools",
                source_id="dayu.fins.tools.preprocess_provider",
                workspace_root=workspace_root,
                mode="manual",
            ),
        ),
    )

    assert result.options.wait_poller_policy is not None
    tooling = result.options.tooling_options
    assert tooling is not None
    assert tooling.wait_poll_adapter_registry is not None
    assert tooling.wait_adapter_registry is not None
    manual_binding = tooling.wait_adapter_registry.resolve_binding(
        tool_name=PREPROCESS_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    assert manual_binding is not None
    assert manual_binding.resume_policy is WaitResumePolicy.MANUAL


def test_active_poll_with_disabled_runtime_policy_stays_disabled(
    tmp_path: Path,
) -> None:
    """active poll 必须把 disabled config snapshot 显式传给 Host。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: Service 丢弃 disabled snapshot 或代码默认重启时抛出。
    """

    result = _compose_with_fins_provider_configs(
        tmp_path=tmp_path,
        provider_configs=(
            _provider_config_with_mode(
                provider_id="financial-download-tools",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="dayu.fins.tools.download_provider",
                workspace_root=tmp_path.resolve(strict=False),
                mode="poll",
            ),
        ),
        policy_enabled=False,
    )

    policy = result.options.wait_poller_policy
    assert policy is not None
    assert policy.enabled is False


def test_callback_mode_fails_closed_before_open_host(tmp_path: Path) -> None:
    """callback transport 不存在时 composition 必须 fail-closed。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: callback 被降级为 poll/manual 时抛出。
    """

    with pytest.raises(ValueError, match="authenticated callback transport"):
        _compose_with_fins_provider_configs(
            tmp_path=tmp_path,
            provider_configs=(
                _provider_config_with_mode(
                    provider_id="financial-upload-tools",
                    import_path="dayu.fins.tools.upload_provider:discover_tools",
                    source_id="dayu.fins.tools.upload_provider",
                    workspace_root=tmp_path.resolve(strict=False),
                    mode="callback",
                ),
            ),
        )


def test_no_provider_and_disabled_provider_do_not_compose_poller(
    tmp_path: Path,
) -> None:
    """无 provider 与 disabled provider 都不得启动 poller。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: inactive provider 影响 poller 决策时抛出。
    """

    no_provider = _compose_with_fins_provider_configs(
        tmp_path=tmp_path,
        provider_configs=(),
    )
    disabled_provider = _compose_with_fins_provider_configs(
        tmp_path=tmp_path,
        provider_configs=(
            _provider_config_with_mode(
                provider_id="financial-download-tools",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="dayu.fins.tools.download_provider",
                workspace_root=tmp_path.resolve(strict=False),
                mode="poll",
                enabled=False,
            ),
        ),
    )

    assert no_provider.options.wait_poller_policy is None
    assert disabled_provider.options.wait_poller_policy is None


def test_enabled_poll_policy_with_missing_registry_fails_before_open_host(
    tmp_path: Path,
) -> None:
    """active poll + enabled policy 缺少 registry 必须在 Service fail-closed。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: 错误延迟到 public open_host 后才发生时抛出。
    """

    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load()
    metadata = _fins_awaiting_provider_metadata_from_configs(
        (
            _provider_config_with_mode(
                provider_id="financial-download-tools",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="dayu.fins.tools.download_provider",
                workspace_root=tmp_path.resolve(strict=False),
                mode="poll",
            ),
        )
    )

    with pytest.raises(ValueError, match="non-empty poll adapter registry"):
        _wait_poller_policy_for_composition(
            config=config.host_runtime.runtimes["local"].wait_poller_policy,
            fins_awaiting_providers=metadata,
            tooling_options=None,
        )


def test_compose_open_host_options_reads_compactor_scene_id_from_profile(
    tmp_path: Path,
) -> None:
    """Service helper 必须从 compactor_baseline 读取 compactor scene id。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: helper 仍使用硬编码 compactor scene 时抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )
    custom_locations = _custom_compactor_scene_locations(tmp_path)
    profile = config.execution_profiles.execution_profiles["standard-256k"]
    custom_profile = replace(
        profile,
        compactor_baseline=replace(
            profile.compactor_baseline,
            scene_id=_CUSTOM_COMPACTOR_SCENE_ID,
            user_prompt_template_path="scenes/custom_compactor_user.md",
        ),
    )
    custom_profiles = dict(config.execution_profiles.execution_profiles)
    custom_profiles["standard-256k"] = custom_profile
    custom_config = replace(
        config,
        execution_profiles=replace(
            config.execution_profiles,
            execution_profiles=custom_profiles,
        ),
    )

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=custom_config,
            locations=custom_locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    compactor_baseline = result.options.compactor_runner_baseline
    assert compactor_baseline is not None
    assert compactor_baseline.compactor_system_prompt == ("custom compactor system prompt")
    assert compactor_baseline.compactor_user_prompt_template == ("custom compactor user prompt <<compaction_request>>")
    assert compactor_baseline.compactor_agent_policy.max_iterations == 1
    assert compactor_baseline.compactor_agent_policy.allow_tool_calls is False


def test_compose_submit_followup_request_uses_prepared_system_prompt(
    tmp_path: Path,
) -> None:
    """per-run helper 直接使用 ``PreparedSceneInputs.system_prompt``。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: helper 重新拼接或丢失 system prompt 时抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )

    request = compose_submit_followup_request(
        context=_host_context("service-request-1"),
        session_id="session-1",
        client_request_id="service-request-1",
        scene_inputs=scene_inputs,
        user_prompt="请总结。",
        tool_names=scene_inputs.tool_selection.tool_names,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )

    assert request.system_prompt == scene_inputs.system_prompt
    assert request.tool_names == frozenset({"record_smoke_fact"})


def test_compose_submit_followup_request_with_overrides_sets_typed_fields(
    tmp_path: Path,
) -> None:
    """per-run override 必须进入 Host public typed fields。"""

    _write_tool_discovery_overlay(tmp_path)
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )
    host_assembly = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    request = compose_submit_followup_request_with_overrides(
        context=_host_context("service-request-override"),
        session_id="session-1",
        client_request_id="service-request-override",
        scene_inputs=scene_inputs,
        user_prompt="请总结。",
        tool_names=scene_inputs.tool_selection.tool_names,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
        host_assembly=host_assembly,
        run_overrides=ServiceRunOverrides(
            temperature=0.17,
            tool_execution_timeout_seconds=3.5,
            max_iterations=7,
            fallback_mode="raise_error",
            fallback_prompt="请停止工具调用并说明失败原因。",
            max_consecutive_failed_tool_batches=4,
        ),
    )

    assert request.runner_options is not None
    assert request.runner_options.temperature == 0.17
    assert request.runner_options.top_p == host_assembly.ordinary_selection.runner_option_hint.top_p
    assert request.agent_policy is not None
    assert request.agent_policy.max_iterations == 7
    assert request.agent_policy.tool_execution_timeout_seconds == 3.5
    assert request.agent_policy.fallback_mode is AgentFallbackMode.RAISE_ERROR
    assert request.agent_policy.fallback_prompt == "请停止工具调用并说明失败原因。"
    assert request.agent_policy.max_consecutive_failed_tool_batches == 4
    assert (
        request.agent_policy.continuation_max_attempts
        == host_assembly.options.ordinary_run_baseline.agent_policy.continuation_max_attempts
    )


def test_service_run_overrides_reject_invalid_values() -> None:
    """ServiceRunOverrides 必须在进入 Host request 前拒绝非法字段。"""

    with pytest.raises(ValueError, match="max_iterations"):
        ServiceRunOverrides(max_iterations=0)
    with pytest.raises(ValueError, match="fallback_mode"):
        ServiceRunOverrides(fallback_mode="unsupported")


def test_compactor_prompt_scene_requires_one_system_fragment() -> None:
    """Compactor scene prompt 必须只提供 system prompt fragment。

    :returns: ``None``。
    :raises AssertionError: helper 未 fail-fast 时抛出。
    """

    scene_inputs = PreparedSceneInputs(
        system_messages=("system", "extra"),
        system_prompt="system\n\nextra",
        tool_selection=SceneToolSelectionResult(
            mode=SceneToolSelectionMode.NONE,
            tool_names=frozenset(),
        ),
        model_hints=None,
        agent_policy_override=None,
        fragment_refs=(),
        source_refs=(),
        content_digest="sha256:test",
        capability_tags=(),
    )

    with pytest.raises(ValueError, match="one system prompt"):
        _compactor_prompts_from_scene_inputs(
            scene_inputs,
            user_prompt_template="user <<compaction_request>>",
        )


def test_compactor_prompt_scene_requires_agent_policy() -> None:
    """Compactor scene 必须声明完整 AgentPolicy。

    :returns: ``None``。
    :raises AssertionError: helper 未 fail-fast 时抛出。
    """

    scene_inputs = PreparedSceneInputs(
        system_messages=("system",),
        system_prompt="system",
        tool_selection=SceneToolSelectionResult(
            mode=SceneToolSelectionMode.NONE,
            tool_names=frozenset(),
        ),
        model_hints=None,
        agent_policy_override=None,
        fragment_refs=(),
        source_refs=(),
        content_digest="sha256:test",
        capability_tags=(),
    )

    with pytest.raises(ValueError, match="agent_policy"):
        _compactor_prompts_from_scene_inputs(
            scene_inputs,
            user_prompt_template="user <<compaction_request>>",
        )


@pytest.mark.parametrize(
    ("override", "message"),
    (
        (
            replace(_complete_compactor_agent_policy_override(), max_iterations=None),
            "max_iterations",
        ),
        (
            replace(
                _complete_compactor_agent_policy_override(),
                fallback_mode=None,
            ),
            "fallback_mode",
        ),
        (
            replace(
                _complete_compactor_agent_policy_override(),
                max_consecutive_failed_tool_batches=None,
            ),
            "max_consecutive_failed_tool_batches",
        ),
    ),
)
def test_compactor_agent_policy_requires_selected_fields(
    override: SceneAgentPolicyOverride,
    message: str,
) -> None:
    """Compactor scene AgentPolicy 缺必填字段时必须 fail-fast。

    :param override: 被测 scene agent policy override。
    :param message: 预期错误消息片段。
    :returns: ``None``。
    :raises AssertionError: helper 未拒绝缺失必填字段时抛出。
    """

    scene_inputs = _compactor_scene_inputs(agent_policy_override=override)

    with pytest.raises(ValueError, match=message):
        _compactor_agent_policy_from_scene_inputs(scene_inputs)


def test_agent_fallback_mode_from_config_uses_engine_enum_values() -> None:
    """fallback mode 映射复用共享枚举原生值校验。

    :returns: ``None``。
    :raises AssertionError: 合法值未映射到对应共享枚举时抛出。
    :raises ValueError: 非法值未保持 ``ValueError`` 语义时抛出。
    """

    assert _agent_fallback_mode_from_config("force_answer") is AgentFallbackMode.FORCE_ANSWER
    assert _agent_fallback_mode_from_config("raise_error") is AgentFallbackMode.RAISE_ERROR
    with pytest.raises(ValueError):
        _agent_fallback_mode_from_config("unsupported")


@pytest.mark.parametrize("env", ({}, {"DEEPSEEK_API_KEY": "   "}))
def test_render_headers_requires_api_key_env(env: dict[str, str]) -> None:
    """Header 渲染必须拒绝缺失或空白 API key。

    :param env: 测试用 env 映射。
    :returns: ``None``。
    :raises AssertionError: 缺失或空白 secret 未 fail-fast 时抛出。
    """

    with pytest.raises(ValueError, match="missing env DEEPSEEK_API_KEY"):
        _render_headers(
            {"Authorization": "Bearer {{DEEPSEEK_API_KEY}}"},
            api_key_ref="DEEPSEEK_API_KEY",
            env=env,
        )


def test_render_headers_rejects_unresolved_placeholder() -> None:
    """Header 渲染必须拒绝未解析 env 占位符。

    :returns: ``None``。
    :raises AssertionError: 未解析占位符未 fail-fast 时抛出。
    """

    with pytest.raises(ValueError, match="unresolved env placeholder"):
        _render_headers(
            {"Authorization": "Bearer {{DEEPSEEK_API_KEY}} {{OTHER_KEY}}"},
            api_key_ref="DEEPSEEK_API_KEY",
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )


def test_render_headers_allows_missing_api_key_ref_without_placeholders() -> None:
    """本地 provider 无 API key 引用时应原样保留非 secret header。"""

    assert _render_headers(
        {"Content-Type": "application/json"},
        api_key_ref=None,
        env={},
    ) == {"Content-Type": "application/json"}


def test_runner_spec_from_ollama_model_skips_api_key_header() -> None:
    """Ollama 这类本地模型 ``api_key_ref=None`` 时不要求 secret。"""

    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load()
    model = config.models.models["ollama"]

    spec = _runner_spec_from_model(model=model, env={})

    assert spec.api_key_ref is None
    assert spec.headers == {"Content-Type": "application/json"}
    assert spec.client_correlation_policy is ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID


def test_runner_spec_rejects_static_client_request_id_header() -> None:
    """Service 装配默认启用 policy 时必须拒绝静态客户端关联 header。"""

    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load()
    model = replace(
        config.models.models["ollama"],
        headers={"X-Client-Request-Id": "static-client-id"},
    )

    with pytest.raises(ValueError, match="X-Client-Request-Id"):
        _runner_spec_from_model(model=model, env={})


@pytest.mark.parametrize(
    ("configured_path", "message"),
    (
        ("", "must not be empty"),
        ("/tmp/dayu-prompt.md", "must be relative"),
        ("../outside.md", "escapes prompt asset root"),
    ),
)
def test_resolve_prompt_asset_path_rejects_invalid_paths(
    tmp_path: Path,
    configured_path: str,
    message: str,
) -> None:
    """Prompt asset path 必须是非空且不逃逸根目录的相对路径。

    :param tmp_path: pytest 临时目录。
    :param configured_path: 被测配置路径。
    :param message: 预期错误消息片段。
    :returns: ``None``。
    :raises AssertionError: 非法路径未 fail-fast 时抛出。
    """

    with pytest.raises(ValueError, match=message):
        _resolve_prompt_asset_path(
            tmp_path,
            configured_path,
            field_name="test.prompt_path",
        )


def test_tooling_options_from_discovery_requires_source_refs() -> None:
    """非空工具 bundle 必须携带 source refs。

    :returns: ``None``。
    :raises AssertionError: 缺少 source refs 未 fail-fast 时抛出。
    """

    with pytest.raises(ValueError, match="source refs"):
        _tooling_options_from_discovery(
            tool_bundle=ToolBundle(definitions=(_tool_definition("lookup_fact"),)),
            source_refs=(),
            fins_awaiting_providers=(),
            fins_awaiting_runtime=None,
            duplicate_governance_policy_config=_duplicate_governance_policy_config(),
        )


def test_tooling_options_without_fins_awaiting_providers_has_no_wait_adapter_registry(
    tmp_path: Path,
) -> None:
    """无 Fins awaiting provider config 时普通工具应正常装配且不绑定 wait adapter。"""

    tooling_options = _tooling_options_from_discovery(
        tool_bundle=ToolBundle(definitions=(_tool_definition("lookup_fact"),)),
        source_refs=(_source_ref("ordinary-provider"),),
        fins_awaiting_providers=(),
        fins_awaiting_runtime=None,
        duplicate_governance_policy_config=_duplicate_governance_policy_config(),
    )

    assert tooling_options is not None
    assert tooling_options.business_tool_bundle.definitions[0].name == "lookup_fact"
    assert tooling_options.wait_adapter_registry is None
    assert tooling_options.wait_activation_registry is None
    assert tooling_options.wait_poll_adapter_registry is None


def test_tooling_options_binds_fins_wait_adapter_registry_for_enabled_awaiting_providers(
    tmp_path: Path,
) -> None:
    """Service assembly 应为启用的 Fins awaiting providers 绑定 wait adapter。"""

    workspace_root = (tmp_path / "fins-workspace").resolve(strict=False)
    discovered_tools = discover_service_tools(
        (
            _provider_config(
                provider_id="custom-download-provider",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="custom-download-source",
                workspace_root=workspace_root,
            ),
            _provider_config(
                provider_id="custom-preprocess-provider",
                import_path="custom.package:discover_tools",
                source_id="dayu.fins.tools.preprocess_provider",
                workspace_root=workspace_root,
            ),
            _provider_config(
                provider_id="custom-upload-provider",
                import_path="custom.package:discover_tools",
                source_id="dayu.fins.tools.upload_provider",
                workspace_root=workspace_root,
            ),
        )
    )
    tooling_options = _tooling_options_from_discovery(
        tool_bundle=discovered_tools.tool_bundle,
        source_refs=discovered_tools.source_refs,
        fins_awaiting_providers=discovered_tools._fins_awaiting_providers,
        fins_awaiting_runtime=discovered_tools.fins_awaiting_runtime,
        duplicate_governance_policy_config=_duplicate_governance_policy_config(),
    )

    assert tooling_options is not None
    assert tooling_options.wait_adapter_registry is not None
    assert tooling_options.wait_activation_registry is not None
    assert tooling_options.wait_poll_adapter_registry is not None
    download_binding = tooling_options.wait_adapter_registry.resolve_binding(
        tool_name=DOWNLOAD_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    preprocess_binding = tooling_options.wait_adapter_registry.resolve_binding(
        tool_name=PREPROCESS_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    upload_binding = tooling_options.wait_adapter_registry.resolve_binding(
        tool_name=UPLOAD_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    assert download_binding is not None
    assert preprocess_binding is not None
    assert upload_binding is not None
    assert download_binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY
    assert preprocess_binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY
    assert upload_binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY
    activation_adapter = tooling_options.wait_activation_registry.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY)
    assert isinstance(activation_adapter, FinsIngestionWaitActivationAdapter)
    assert activation_adapter.runtime is discovered_tools.fins_awaiting_runtime
    poll_adapter = tooling_options.wait_poll_adapter_registry.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY)
    assert isinstance(poll_adapter, FinsIngestionWaitPollAdapter)
    assert poll_adapter.runtime is discovered_tools.fins_awaiting_runtime


@pytest.mark.asyncio
async def test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation(
    tmp_path: Path,
) -> None:
    """Service discovery、HostToolingOptions 与 activation 必须共享 Fins runtime。"""

    workspace_root = (tmp_path / "fins-workspace").resolve(strict=False)
    provider_configs = (
        _provider_config(
            provider_id="financial-download-tools",
            import_path="dayu.fins.tools.download_provider:discover_tools",
            source_id="dayu.fins.tools.download_provider",
            workspace_root=workspace_root,
        ),
    )
    discovered_tools = discover_service_tools(provider_configs)

    tooling_options = _tooling_options_from_discovery(
        tool_bundle=discovered_tools.tool_bundle,
        source_refs=discovered_tools.source_refs,
        fins_awaiting_providers=discovered_tools._fins_awaiting_providers,
        fins_awaiting_runtime=discovered_tools.fins_awaiting_runtime,
        duplicate_governance_policy_config=_duplicate_governance_policy_config(),
    )

    assert tooling_options is not None
    assert tooling_options.wait_adapter_registry is not None
    assert tooling_options.wait_activation_registry is not None
    assert tooling_options.wait_poll_adapter_registry is not None
    definition = tooling_options.business_tool_bundle.definitions[0]
    callable_ = definition.callable
    assert definition.name == DOWNLOAD_TOOL_NAME
    assert isinstance(callable_, FinsDownloadToolCallable)
    activation_adapter = tooling_options.wait_activation_registry.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY)
    assert isinstance(activation_adapter, FinsIngestionWaitActivationAdapter)
    assert activation_adapter.runtime is discovered_tools.fins_awaiting_runtime
    assert activation_adapter.runtime is callable_.runtime
    poll_adapter = tooling_options.wait_poll_adapter_registry.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY)
    assert isinstance(poll_adapter, FinsIngestionWaitPollAdapter)
    assert poll_adapter.runtime is discovered_tools.fins_awaiting_runtime
    assert poll_adapter.runtime is callable_.runtime

    outcome = await callable_(
        _service_tool_call(
            DOWNLOAD_TOOL_NAME,
            {
                "ticker": "AAPL",
                "source": "unknown",
            },
        ),
        _service_tool_context(),
    )

    assert isinstance(outcome, ToolAwaitingOutcome)
    runtime = callable_.runtime
    handle = _observation_handle_from_awaiting(outcome)
    before_activation = await runtime.poll_observation(handle)
    assert before_activation.status is FinsObservationStatus.PENDING

    activation_adapter.activate_accepted_wait(
        WaitActivationRequest(
            tool_name=DOWNLOAD_TOOL_NAME,
            await_spec=outcome.await_spec,
            accepted_ack=_accepted_awaiting_ack(),
        )
    )

    after_activation = await _wait_until_observation_leaves_pending(runtime, handle)
    assert after_activation.status is not FinsObservationStatus.PENDING


def test_tooling_options_skips_wait_adapter_for_missing_awaiting_tool_definition(
    tmp_path: Path,
) -> None:
    """Service assembly 只为实际进入 ToolBundle 的 awaiting 工具绑定 wait adapter。"""

    workspace_root = (tmp_path / "fins-workspace").resolve(strict=False)
    metadata = _fins_awaiting_provider_metadata_from_configs(
        (
            _provider_config(
                provider_id="custom-upload-provider",
                import_path="dayu.fins.tools.upload_provider:discover_tools",
                source_id="dayu.fins.tools.upload_provider",
                workspace_root=workspace_root,
            ),
        )
    )
    active_metadata = _active_fins_awaiting_provider_metadata(
        metadata,
        available_tool_names=frozenset({DOWNLOAD_TOOL_NAME}),
    )
    tooling_options = _tooling_options_from_discovery(
        tool_bundle=ToolBundle(definitions=(_tool_definition(DOWNLOAD_TOOL_NAME),)),
        source_refs=(_source_ref("fins-awaiting-test"),),
        fins_awaiting_providers=active_metadata,
        fins_awaiting_runtime=None,
        duplicate_governance_policy_config=_duplicate_governance_policy_config(),
    )

    assert tooling_options is not None
    assert tooling_options.wait_adapter_registry is None
    assert tooling_options.wait_activation_registry is None
    assert tooling_options.wait_poll_adapter_registry is None


def test_tooling_options_skips_wait_poll_adapter_for_disabled_awaiting_provider(
    tmp_path: Path,
) -> None:
    """禁用的 Fins awaiting provider 不应装配 wait poll adapter。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 禁用 provider 仍产生 poll registry 时抛出。
    """

    workspace_root = (tmp_path / "fins-workspace").resolve(strict=False)
    disabled_provider = replace(
        _provider_config(
            provider_id="financial-download-tools",
            import_path="dayu.fins.tools.download_provider:discover_tools",
            source_id="dayu.fins.tools.download_provider",
            workspace_root=workspace_root,
        ),
        enabled=False,
    )
    discovered_tools = discover_service_tools((disabled_provider,))

    assert discovered_tools._fins_awaiting_providers == ()
    assert discovered_tools.fins_awaiting_runtime is None
    assert discovered_tools.tool_bundle.definitions == ()


def test_fins_awaiting_provider_workspace_root_mismatch_fails_before_open_host(
    tmp_path: Path,
) -> None:
    """同一 Host assembly 中 Fins awaiting provider workspace 必须一致。"""

    with pytest.raises(ValueError, match="same absolute workspace_root"):
        discover_service_tools(
            (
                _provider_config(
                    provider_id="financial-download-tools",
                    import_path="custom.download:discover_tools",
                    source_id="custom.download",
                    workspace_root=(tmp_path / "one").resolve(strict=False),
                ),
                _provider_config(
                    provider_id="financial-preprocess-tools",
                    import_path="custom.preprocess:discover_tools",
                    source_id="custom.preprocess",
                    workspace_root=(tmp_path / "two").resolve(strict=False),
                ),
                _provider_config(
                    provider_id="financial-upload-tools",
                    import_path="custom.upload:discover_tools",
                    source_id="custom.upload",
                    workspace_root=(tmp_path / "one").resolve(strict=False),
                ),
            )
        )


def test_fins_awaiting_provider_missing_workspace_root_fails_before_open_host() -> None:
    """Fins awaiting provider 缺少 workspace_root 时必须在 open_host 前失败。"""

    with pytest.raises(ValueError, match="non-empty absolute path"):
        _fins_awaiting_provider_metadata_from_configs(
            (
                _provider_config_with_config(
                    provider_id="financial-download-tools",
                    import_path="custom.download:discover_tools",
                    source_id="custom.download",
                    config={"awaiting_resolution_mode": "poll"},
                ),
            )
        )


def test_fins_awaiting_provider_relative_workspace_root_fails_before_open_host() -> None:
    """Fins awaiting provider 使用相对 workspace_root 时必须在 open_host 前失败。"""

    with pytest.raises(ValueError, match="must be absolute"):
        _fins_awaiting_provider_metadata_from_configs(
            (
                _provider_config_with_config(
                    provider_id="financial-download-tools",
                    import_path="custom.download:discover_tools",
                    source_id="custom.download",
                    config={
                        "workspace_root": "relative/fins-workspace",
                        "awaiting_resolution_mode": "poll",
                    },
                ),
            )
        )


def test_fins_awaiting_provider_duplicate_binding_fails_before_open_host(
    tmp_path: Path,
) -> None:
    """重复 Fins awaiting binding 必须 fail fast，避免 registry 非确定合并。"""

    workspace_root = (tmp_path / "fins-workspace").resolve(strict=False)
    metadata = _fins_awaiting_provider_metadata_from_configs(
        (
            _provider_config(
                provider_id="financial-download-tools",
                import_path="custom.one:discover_tools",
                source_id="custom.one",
                workspace_root=workspace_root,
            ),
            _provider_config(
                provider_id="another-download-provider",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="custom.two",
                workspace_root=workspace_root,
            ),
        )
    )
    with pytest.raises(ValueError, match="duplicate Fins wait adapter binding"):
        _tooling_options_from_discovery(
            tool_bundle=ToolBundle(definitions=(_tool_definition(DOWNLOAD_TOOL_NAME),)),
            source_refs=(_source_ref("fins-awaiting-test"),),
            fins_awaiting_providers=metadata,
            fins_awaiting_runtime=None,
            duplicate_governance_policy_config=_duplicate_governance_policy_config(),
        )


def test_fins_upload_awaiting_provider_duplicate_binding_fails_before_open_host(
    tmp_path: Path,
) -> None:
    """重复 upload awaiting binding 必须 fail fast。"""

    workspace_root = (tmp_path / "fins-workspace").resolve(strict=False)
    metadata = _fins_awaiting_provider_metadata_from_configs(
        (
            _provider_config(
                provider_id="financial-upload-tools",
                import_path="custom.one:discover_tools",
                source_id="custom.one",
                workspace_root=workspace_root,
            ),
            _provider_config(
                provider_id="another-upload-provider",
                import_path="dayu.fins.tools.upload_provider:discover_tools",
                source_id="custom.two",
                workspace_root=workspace_root,
            ),
        )
    )
    with pytest.raises(ValueError, match="duplicate Fins wait adapter binding"):
        _tooling_options_from_discovery(
            tool_bundle=ToolBundle(definitions=(_tool_definition(UPLOAD_TOOL_NAME),)),
            source_refs=(_source_ref("fins-upload-awaiting-test"),),
            fins_awaiting_providers=metadata,
            fins_awaiting_runtime=None,
            duplicate_governance_policy_config=_duplicate_governance_policy_config(),
        )


def test_tool_discovery_spec_requires_provider_location() -> None:
    """工具发现 provider 必须声明 import_path 或 entry_point。

    :returns: ``None``。
    :raises AssertionError: 缺少 provider 解析位置未 fail-fast 时抛出。
    """

    provider = ToolDiscoveryProviderConfig(
        provider_id="missing-location",
        import_path=None,
        entry_point=None,
        source_kind=ToolBundleSourceKind.CONFIG_BINDING,
        source_id="missing-location",
        enabled=True,
        config={"path_policy": {"allowed_roots": ["workspace/docs"]}},
    )

    with pytest.raises(ValueError, match="import_path or entry_point"):
        _tool_discovery_spec(provider)


def test_tool_discovery_spec_uses_entry_point_location() -> None:
    """工具发现 provider 可以使用 entry point 位置。

    :returns: ``None``。
    :raises AssertionError: entry point 未映射为 discovery spec 时抛出。
    """

    provider = ToolDiscoveryProviderConfig(
        provider_id="entry-provider",
        import_path=None,
        entry_point=ToolDiscoveryEntryPointConfig(
            group="dayu.test_tools",
            name="provider",
        ),
        source_kind=ToolBundleSourceKind.PACKAGE_ENTRYPOINT,
        source_id="dayu.test_tools:provider",
        enabled=True,
        config={"provider_option": "entry"},
    )

    spec = _tool_discovery_spec(provider)

    assert spec.spec_id == "entry-provider"
    assert spec.enabled is True
    assert spec.config["provider_option"] == "entry"


def test_tool_discovery_provider_config_survives_loader_and_service_mapping(
    tmp_path: Path,
) -> None:
    """provider config 必须从 ConfigLoader 原样进入 ToolsDiscovery spec。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: provider config 被丢弃或解释时抛出。
    """

    package_root = tmp_path / "config"
    _write_json(
        package_root / "tool_discovery.json",
        {
            "providers": {
                "doc-tools": {
                    "import_path": "dayu.tools.doc_provider:discover_tools",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "dayu.tools.doc_provider",
                    "enabled": False,
                    "config": {
                        "allowed_paths": ["workspace/docs"],
                        "limits": {"read_file_max_chars": 2048},
                    },
                }
            }
        },
    )

    config = ConfigLoader(package_config_dir=package_root).load_tool_discovery()
    provider = config.providers["doc-tools"]
    spec = _tool_discovery_spec(provider)

    assert spec.config["allowed_paths"] == ["workspace/docs"]
    assert spec.config["limits"] == {"read_file_max_chars": 2048}


def test_web_tool_discovery_config_survives_service_mapping() -> None:
    """Web provider config 必须原样进入 ToolsDiscovery spec。

    :returns: ``None``。
    :raises AssertionError: Service assembly 解释或丢弃 Web config 时抛出。
    """

    web_config: dict[str, JsonValue] = {
        "provider": "serper",
        "request_timeout_seconds": 3.5,
        "max_search_results": 4,
        "fetch_truncate_chars": 4321,
        "allow_private_network_url": True,
        "playwright_channel": "msedge",
        "playwright_storage_state_dir": "storage-states",
    }
    provider = ToolDiscoveryProviderConfig(
        provider_id="web-tools",
        import_path="dayu.tools.web:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.tools.web",
        enabled=True,
        config=web_config,
    )

    spec = _tool_discovery_spec(provider)

    assert spec.spec_id == "web-tools"
    assert spec.config == web_config


def test_default_web_storage_state_dir_resolves_under_workspace_root(
    tmp_path: Path,
) -> None:
    """默认 Web storage state 目录不得解析到 nested workspace。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 默认 storage state 路径未按 workspace root 解析时抛出。
    """

    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load()

    effective_providers = assemble_effective_tool_provider_configs(
        tuple(config.tool_discovery.providers.values()),
        workspace_root=tmp_path,
    )
    web_provider = next(
        provider_config for provider_config in effective_providers if provider_config.provider_id == "web-tools"
    )

    assert web_provider.config["playwright_storage_state_dir"] == str(
        (tmp_path / ".dayu" / "web_tools_storage_states").resolve(strict=False)
    )
    assert not str(web_provider.config["playwright_storage_state_dir"]).startswith(
        str((tmp_path / "workspace").resolve(strict=False))
    )


def test_fins_tool_discovery_spec_injects_runtime_workspace_root(
    tmp_path: Path,
) -> None:
    """Fins provider effective spec 必须补齐运行时 workspace root。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: workspace root 未注入或污染 raw config 时抛出。
    """

    raw_config: dict[str, JsonValue] = {"limits": {}}
    provider = ToolDiscoveryProviderConfig(
        provider_id="financial-read-tools",
        import_path="dayu.fins.tools.provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.fins.tools.provider",
        enabled=True,
        config=raw_config,
    )

    effective_providers = assemble_effective_tool_provider_configs(
        (provider,),
        workspace_root=tmp_path,
    )
    spec = _tool_discovery_spec(effective_providers[0])

    assert spec.config["workspace_root"] == str(tmp_path.resolve(strict=False))
    assert "workspace_root" not in raw_config


def test_fins_tool_discovery_spec_preserves_explicit_workspace_root(
    tmp_path: Path,
) -> None:
    """Fins provider 显式 workspace root 不能被运行时默认值覆盖。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: 显式 workspace root 被覆盖时抛出。
    """

    configured_workspace = (tmp_path / "configured").resolve(strict=False)
    runtime_workspace = (tmp_path / "runtime").resolve(strict=False)
    provider = ToolDiscoveryProviderConfig(
        provider_id="financial-download-tools",
        import_path="dayu.fins.tools.download_provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.fins.tools.download_provider",
        enabled=True,
        config={"workspace_root": str(configured_workspace)},
    )

    effective_providers = assemble_effective_tool_provider_configs(
        (provider,),
        workspace_root=runtime_workspace,
    )
    spec = _tool_discovery_spec(effective_providers[0])

    assert spec.config["workspace_root"] == str(configured_workspace)


def test_fins_tool_discovery_spec_resolves_relative_workspace_root(
    tmp_path: Path,
) -> None:
    """Fins provider 相对 workspace root 必须由 Service 解析为绝对路径。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: 相对 workspace root 未按 runtime workspace 解析时抛出。
    """

    runtime_workspace = (tmp_path / "project").resolve(strict=False)
    provider = ToolDiscoveryProviderConfig(
        provider_id="financial-read-tools",
        import_path="dayu.fins.tools.provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.fins.tools.provider",
        enabled=True,
        config={"workspace_root": "fins-data/", "limits": {}},
    )

    effective_providers = assemble_effective_tool_provider_configs(
        (provider,),
        workspace_root=runtime_workspace,
    )
    spec = _tool_discovery_spec(effective_providers[0])

    assert spec.config["workspace_root"] == str((runtime_workspace / "fins-data").resolve(strict=False))
    assert provider.config["workspace_root"] == "fins-data/"


@pytest.mark.parametrize(
    "raw_workspace_root",
    (None, "/configured/fins", "relative/fins"),
)
@pytest.mark.parametrize(
    ("provider_id", "import_path", "source_id"),
    (
        (
            "financial-read-tools",
            "dayu.fins.tools.provider:discover_tools",
            "dayu.fins.tools.provider",
        ),
        (
            "financial-download-tools",
            "dayu.fins.tools.download_provider:discover_tools",
            "dayu.fins.tools.download_provider",
        ),
    ),
)
def test_fins_validation_override_dominates_all_legal_raw_path_cases(
    tmp_path: Path,
    raw_workspace_root: str | None,
    provider_id: str,
    import_path: str,
    source_id: str,
) -> None:
    """合法 raw 三态先过 grammar，再由 private absolute override 支配。

    :param tmp_path: pytest 临时目录。
    :param raw_workspace_root: 未配置、绝对或相对 raw Fins root。
    :param provider_id: read 或 awaiting Fins provider id。
    :param import_path: provider 当前 import path。
    :param source_id: provider 当前 source id。
    :returns: None。
    :raises AssertionError: effective precedence 或 raw mapping 被改写时抛出。
    """

    raw_config: dict[str, JsonValue] = {"limits": {}}
    if raw_workspace_root is not None:
        raw_config["workspace_root"] = raw_workspace_root
    original_raw_config = dict(raw_config)
    provider = ToolDiscoveryProviderConfig(
        provider_id=provider_id,
        import_path=import_path,
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=source_id,
        enabled=True,
        config=raw_config,
    )
    public_workspace = (tmp_path / "public").resolve(strict=False)
    private_workspace = (tmp_path / "private").resolve(strict=False)

    effective_provider = assemble_effective_tool_provider_configs(
        (provider,),
        workspace_root=public_workspace,
        fins_workspace_root_override=private_workspace,
    )[0]

    assert effective_provider.config["workspace_root"] == str(private_workspace)
    assert raw_config == original_raw_config
    assert provider.config == original_raw_config


@pytest.mark.parametrize("invalid_raw", (123, "", "   "))
def test_fins_validation_override_does_not_mask_invalid_raw_grammar(
    tmp_path: Path,
    invalid_raw: JsonValue,
) -> None:
    """Private override 不得跳过现行 raw type/non-empty grammar。

    :param tmp_path: pytest 临时目录。
    :param invalid_raw: 非字符串或空白 raw root。
    :returns: None。
    :raises AssertionError: 非法 raw 被 override 掩盖时抛出。
    """

    provider = ToolDiscoveryProviderConfig(
        provider_id="financial-read-tools",
        import_path="dayu.fins.tools.provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.fins.tools.provider",
        enabled=True,
        config={"workspace_root": invalid_raw, "limits": {}},
    )

    with pytest.raises(ValueError, match="workspace_root must"):
        assemble_effective_tool_provider_configs(
            (provider,),
            workspace_root=tmp_path / "public",
            fins_workspace_root_override=(tmp_path / "private").resolve(strict=False),
        )


def test_fins_validation_override_requires_absolute_path(
    tmp_path: Path,
) -> None:
    """Validation override 自身必须是 absolute path。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: relative override 未被拒绝时抛出。
    """

    provider = ToolDiscoveryProviderConfig(
        provider_id="financial-read-tools",
        import_path="dayu.fins.tools.provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.fins.tools.provider",
        enabled=True,
        config={"limits": {}},
    )

    with pytest.raises(ValueError, match="override must be absolute"):
        assemble_effective_tool_provider_configs(
            (provider,),
            workspace_root=tmp_path,
            fins_workspace_root_override=Path("relative-private"),
        )


def test_fins_validation_override_does_not_enter_non_fins_or_web_paths(
    tmp_path: Path,
) -> None:
    """Override 只由既有 Fins classifier 消费，Web 仍用 ordinary root。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: 非 Fins config 或 Web storage root 被污染时抛出。
    """

    ordinary_provider = ToolDiscoveryProviderConfig(
        provider_id="doc-tools",
        import_path="dayu.tools.doc_provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.tools.doc_provider",
        enabled=True,
        config={"root": "ordinary"},
    )
    web_provider = ToolDiscoveryProviderConfig(
        provider_id="web-tools",
        import_path="dayu.tools.web:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.tools.web",
        enabled=True,
        config={"playwright_storage_state_dir": "web-state"},
    )
    public_workspace = (tmp_path / "public").resolve(strict=False)
    private_workspace = (tmp_path / "private").resolve(strict=False)

    ordinary_effective, web_effective = assemble_effective_tool_provider_configs(
        (ordinary_provider, web_provider),
        workspace_root=public_workspace,
        fins_workspace_root_override=private_workspace,
    )

    assert ordinary_effective == ordinary_provider
    assert "workspace_root" not in ordinary_effective.config
    assert web_effective.config["playwright_storage_state_dir"] == str(
        (public_workspace / "web-state").resolve(strict=False)
    )
    assert str(private_workspace) not in json.dumps(web_effective.config)


def test_fins_tool_discovery_spec_rejects_non_string_workspace_root() -> None:
    """Fins provider workspace root 必须拒绝非字符串配置。

    :returns: ``None``。
    :raises AssertionError: 非字符串 workspace root 未被拒绝时抛出。
    """

    provider = ToolDiscoveryProviderConfig(
        provider_id="financial-read-tools",
        import_path="dayu.fins.tools.provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.fins.tools.provider",
        enabled=True,
        config={"workspace_root": 123, "limits": {}},
    )

    with pytest.raises(ValueError, match="financial-read-tools.*must be a string"):
        assemble_effective_tool_provider_configs((provider,), workspace_root=None)


@pytest.mark.parametrize("workspace_root_value", ("", "   "))
def test_fins_tool_discovery_spec_rejects_empty_workspace_root(
    workspace_root_value: str,
) -> None:
    """Fins provider workspace root 必须拒绝空字符串配置。

    :param workspace_root_value: 待验证的 workspace root 配置值。
    :returns: ``None``。
    :raises AssertionError: 空 workspace root 未被拒绝时抛出。
    """

    provider = ToolDiscoveryProviderConfig(
        provider_id="financial-read-tools",
        import_path="dayu.fins.tools.provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.fins.tools.provider",
        enabled=True,
        config={"workspace_root": workspace_root_value, "limits": {}},
    )

    with pytest.raises(ValueError, match="financial-read-tools.*must be non-empty"):
        assemble_effective_tool_provider_configs((provider,), workspace_root=None)


def test_fins_tool_discovery_spec_rejects_relative_workspace_root_without_runtime_root() -> None:
    """Fins provider 相对 workspace root 缺少运行时根目录时必须失败。

    :returns: ``None``。
    :raises AssertionError: 缺少运行时根目录仍完成解析时抛出。
    """

    provider = ToolDiscoveryProviderConfig(
        provider_id="financial-read-tools",
        import_path="dayu.fins.tools.provider:discover_tools",
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="dayu.fins.tools.provider",
        enabled=True,
        config={"workspace_root": "fins-data/", "limits": {}},
    )

    with pytest.raises(
        ValueError,
        match="financial-read-tools.*requires runtime workspace_root",
    ):
        assemble_effective_tool_provider_configs((provider,), workspace_root=None)


def test_fins_workspace_bound_provider_detection_boundaries() -> None:
    """Fins workspace-bound provider 识别必须覆盖关键边界。

    :returns: ``None``。
    :raises AssertionError: provider 识别结果与预期不符时抛出。
    """

    cases: tuple[tuple[str, ToolDiscoveryProviderConfig, bool], ...] = (
        (
            "ordinary-doc",
            ToolDiscoveryProviderConfig(
                provider_id="doc-tools",
                import_path="dayu.tools.doc_provider:discover_tools",
                entry_point=None,
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="dayu.tools.doc_provider",
                enabled=True,
                config={},
            ),
            False,
        ),
        (
            "read-entry-source",
            ToolDiscoveryProviderConfig(
                provider_id="custom-read",
                import_path=None,
                entry_point=ToolDiscoveryEntryPointConfig(
                    group="dayu.tools",
                    name="custom-read",
                ),
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="dayu.fins.tools.provider",
                enabled=True,
                config={},
            ),
            True,
        ),
        (
            "download-import",
            _provider_config_with_config(
                provider_id="custom-download",
                import_path="dayu.fins.tools.download_provider:discover_tools",
                source_id="custom.download",
                config={},
            ),
            True,
        ),
        (
            "preprocess-source",
            _provider_config_with_config(
                provider_id="custom-preprocess",
                import_path="custom.preprocess:discover_tools",
                source_id="dayu.fins.tools.preprocess_provider",
                config={},
            ),
            True,
        ),
        (
            "upload-id",
            _provider_config_with_config(
                provider_id="financial-upload-tools",
                import_path="custom.upload:discover_tools",
                source_id="custom.upload",
                config={},
            ),
            True,
        ),
    )

    for label, provider_config, expected in cases:
        assert _is_fins_workspace_bound_provider_config(provider_config) is expected, label


def test_discover_service_tools_carries_effective_fins_config_into_compose(
    tmp_path: Path,
) -> None:
    """compose_open_host_options 必须复用 discovery 阶段 effective provider config。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: compose 阶段重新解释 raw provider config 时抛出。
    """

    fins_workspace = (tmp_path / "fins-workspace").resolve(strict=False)
    overlay_dir = tmp_path / "config"
    _write_json(
        overlay_dir / "tool_discovery.json",
        {
            "providers": {
                "financial-download-tools": {
                    "import_path": "dayu.fins.tools.download_provider:discover_tools",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "dayu.fins.tools.download_provider",
                    "enabled": True,
                    "config": {"awaiting_resolution_mode": "poll"},
                }
            },
        },
    )
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(workspace_config_dir=overlay_dir)
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=fins_workspace)
    discovered_provider = next(
        provider_config
        for provider_config in discovered_tools.effective_provider_configs
        if provider_config.provider_id == "financial-download-tools"
    )
    assert discovered_provider.config["workspace_root"] == str(fins_workspace)

    raw_provider = config.tool_discovery.providers["financial-download-tools"]
    corrupted_config = replace(
        config,
        tool_discovery=replace(
            config.tool_discovery,
            providers={
                "financial-download-tools": replace(
                    raw_provider,
                    config={"workspace_root": "relative/fins-workspace"},
                )
            },
        ),
    )

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=corrupted_config,
            locations=locations,
            scene_inputs=_compactor_scene_inputs(agent_policy_override=None),
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    tooling_options = result.options.tooling_options
    assert tooling_options is not None
    registry = tooling_options.wait_adapter_registry
    assert registry is not None
    binding = registry.resolve_binding(
        tool_name=DOWNLOAD_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    assert binding is not None
    assert binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY


def test_config_loader_and_service_discover_web_tools_with_overlay_config(
    tmp_path: Path,
) -> None:
    """完整配置加载与 Service discovery 必须发现 Web tools。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: Web config 未进入生产式工具发现链路时抛出。
    """

    overlay_dir = tmp_path / "config"
    _write_json(
        overlay_dir / "tool_discovery.json",
        {
            "providers": {
                "web-tools": {
                    "import_path": "dayu.tools.web:discover_tools",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "dayu.tools.web",
                    "enabled": True,
                    "config": {
                        "provider": "duckduckgo",
                        "request_timeout_seconds": 4.0,
                        "max_search_results": 3,
                        "fetch_truncate_chars": 9876,
                        "allow_private_network_url": True,
                        "playwright_channel": "chrome",
                        "playwright_storage_state_dir": ".dayu/web-state",
                    },
                }
            }
        },
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(workspace_config_dir=overlay_dir)

    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    tool_names = tuple(definition.name for definition in discovered_tools.tool_bundle.definitions)

    assert "search_web" in tool_names
    assert "fetch_web_page" in tool_names
    assert (
        "provider=web-tools,spec=web-tools,version=web-tools-provider-v1,tools=search_web,fetch_web_page"
        in discovered_tools.provider_reports
    )
    discovered_provider = next(
        provider_config
        for provider_config in discovered_tools.effective_provider_configs
        if provider_config.provider_id == "web-tools"
    )
    assert discovered_provider.config["playwright_storage_state_dir"] == str(
        (tmp_path / ".dayu" / "web-state").resolve(strict=False)
    )


def test_truncation_manager_enabled_is_derived_from_execution_profile(
    tmp_path: Path,
) -> None:
    """截断 manager 开关必须由 execution profile 的 tool policy 派生。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: helper 仍从 host runtime 或其它来源读取开关时抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    _write_execution_profile_overlay(tmp_path, truncation_enabled=False)
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    assert result.options.enable_truncation_manager is False
    assert result.diagnostics.tool_truncation_policy.startswith("enabled=False")


def test_memory_projection_context_window_uses_effective_model_window(
    tmp_path: Path,
) -> None:
    """Memory projection context window 必须来自 effective model。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: helper 使用 profile policy 内的窗口字段时抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    _write_execution_profile_overlay(tmp_path, truncation_enabled=True)
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    assert config.models.models[_MODEL_ID].context_window_tokens == 1048576
    assert (
        config.execution_profiles.execution_profiles["standard-256k"].memory_projection_policy.context_window_size
        == 262144
    )
    assert result.options.memory_projection_policy.context_window_size == 1048576


def test_tool_duplicate_governance_policy_is_derived_from_execution_profile(
    tmp_path: Path,
) -> None:
    """重复工具调用治理策略必须由 execution profile 派生后传入 Host tooling。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: helper 未把配置映射进 HostToolingOptions 时抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    _write_execution_profile_overlay(
        tmp_path,
        truncation_enabled=True,
        duplicate_default_decision="hint",
    )
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    assert result.options.tooling_options is not None
    policy = result.options.tooling_options.duplicate_governance_policy
    assert policy.default_duplicate_decision is DuplicateDecisionKind.HINT
    assert policy.decisions_by_tool_name["lookup_fact"] is DuplicateDecisionKind.REUSE
    assert policy.decisions_by_tool_name["explain_fact"] is DuplicateDecisionKind.REQUIRE_JUSTIFICATION
    assert policy.justification_argument_names_by_tool_name["explain_fact"] == "duplicate_justification"
    assert policy.messages.reuse == "请直接使用上一次工具结果继续推理，不要重复请求相同证据。"


def test_duplicate_decision_from_config_reports_clear_error() -> None:
    """Service duplicate decision 映射失败时必须给出清晰上下文。

    :returns: ``None``。
    :raises AssertionError: 错误消息缺少治理决策上下文时抛出。
    """

    with pytest.raises(
        ValueError,
        match="unsupported duplicate governance decision: retry",
    ):
        _duplicate_decision_from_config("retry")


def test_explicit_1m_profile_with_256k_model_fails_fast(
    tmp_path: Path,
) -> None:
    """显式 1m profile 搭配 256k 模型必须在 Service assembly fail fast。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 未按 profile 最低窗口要求 fail fast 时抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    _write_execution_profile_overlay(
        tmp_path,
        truncation_enabled=True,
        profile_id="standard-1m",
        context_window_class="1m",
        min_context_window_tokens=1000000,
        model_id="ollama",
    )
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )
    scene_inputs = replace(scene_inputs, model_hints=None)

    with pytest.raises(RuntimeAssemblySelectionError, match="larger context window"):
        compose_open_host_options(
            ServiceOpenHostAssemblyRequest(
                workspace_root=tmp_path,
                config=config,
                locations=locations,
                scene_inputs=scene_inputs,
                discovered_tools=discovered_tools,
                overrides=ServiceAssemblyOverrides(
                    host_runtime_id="local",
                    execution_profile_id="standard-1m",
                    model_id=None,
                    runner_option_hint_id=None,
                ),
                env={"DEEPSEEK_API_KEY": _API_KEY},
            )
        )


def test_default_profile_does_not_auto_switch_for_1m_model(
    tmp_path: Path,
) -> None:
    """默认 profile 使用 default_execution_profile_id，不按模型窗口自动切换。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: helper 自动切换到 1m profile 时抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_service_tools_for_workspace(config, workspace_root=tmp_path)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "current_time": _CURRENT_TIME_TEXT,
                "fins_default_subject": "测试财报主体",
            },
            available_tools=_scene_tool_catalog(discovered_tools),
        )
    )

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id=None,
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    assert result.diagnostics.execution_profile_id == "standard-256k"
    assert result.execution_profile.execution_profile_id == "standard-256k"
    assert result.diagnostics.model_id == _MODEL_ID
    assert result.diagnostics.ordinary_profile_compatibility.status == "conservative"
    assert result.diagnostics.compactor_profile_compatibility.selected_model_id == "deepseek-v4-flash"


def test_resolve_workspace_path_rejects_relative_escape(tmp_path: Path) -> None:
    """公共 workspace path 相对配置不得逃逸 workspace root。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 未拒绝逃逸路径时抛出。
    """

    with pytest.raises(ValueError, match="escapes workspace root"):
        resolve_workspace_path(tmp_path, "../outside.sqlite3")


def test_resolve_workspace_path_keeps_absolute_path(tmp_path: Path) -> None:
    """公共 workspace path 绝对路径保持原有语义。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 绝对路径被错误改写时抛出。
    """

    absolute_path = tmp_path.parent / "outside.sqlite3"

    assert resolve_workspace_path(tmp_path, str(absolute_path)) == absolute_path


def _duplicate_governance_policy_config() -> ToolDuplicateGovernancePolicyConfig:
    """构造 Service 测试使用的 duplicate governance typed config。

    :returns: duplicate governance policy typed config。
    :raises Exception: 不主动抛出异常。
    """

    return ToolDuplicateGovernancePolicyConfig(
        default_duplicate_decision="hint",
        decisions_by_tool_name={},
        justification_argument_names_by_tool_name={},
        messages=ToolDuplicateGovernanceMessagesConfig(
            allow="本次重复工具调用已允许执行。",
            reuse="请直接使用上一次工具结果继续推理，不要重复请求相同证据。",
            hint=(
                "请优先使用上一次工具结果继续推理；只有当需要不同主体、期间、"
                "指标或证据范围时，才重新调用工具并修改参数。"
            ),
            require_justification=(
                "重复调用同一工具前，必须在参数中说明为什么上一次工具结果不足，以及本次需要补充的不同证据范围。"
            ),
            hard_stop=(
                "本次重复工具调用已被拒绝。请使用上一次工具结果继续推理；如果信息不足，请说明不确定性，不要编造。"
            ),
            attempt_scope_diagnostic="检测到当前推理步骤中重复请求相同工具证据。",
            prior_accept_missing=("上一次相同工具请求没有产生可用结果。请说明信息不足，或在改变证据范围后再调用工具。"),
        ),
    )


def _write_tool_discovery_overlay(workspace_root: Path) -> None:
    """写入启用 smoke provider 的 workspace tool discovery overlay。

    :param workspace_root: pytest 临时 workspace root。
    :returns: ``None``。
    :raises OSError: 目录或文件写入失败时抛出。
    """

    _write_json(
        workspace_root / "config" / "tool_discovery.json",
        {
            "providers": {
                "financial-tools": {
                    "import_path": ("utils.smoke_host_public_multiturn:discover_smoke_tools"),
                    "entry_point": None,
                    "source_kind": "config_binding",
                    "source_id": "utils.smoke_host_public_multiturn",
                    "enabled": True,
                    "config": {},
                }
            }
        },
    )


def _write_host_runtime_overlay(workspace_root: Path) -> None:
    """写入覆盖 Host construction tuning 的 workspace host runtime 配置。

    :param workspace_root: pytest 临时 workspace root。
    :returns: ``None``。
    :raises OSError: 目录或文件写入失败时抛出。
    """

    _write_json(
        workspace_root / "config" / "host_runtime.json",
        {
            "default_host_runtime_id": "local",
            "runtimes": {
                "local": {
                    "store_root": ".dayu/host",
                    "artifact_root": ".dayu/artifacts",
                    "sqlite": {
                        "path": ".dayu/host/dayu_host.sqlite3",
                        "busy_timeout_seconds": 5.0,
                        "write_busy_retry_count": 3,
                        "write_retry_initial_delay_seconds": 0.002,
                        "write_retry_backoff_multiplier": 1.25,
                        "write_retry_max_delay_seconds": 0.03,
                    },
                    "host_execution_lane_name": "llm_api",
                    "worker_backend": "local",
                    "dispatch_poll_interval_seconds": 0.2,
                    "payload_inline_threshold_bytes": 2048,
                    "worker_startup_timeout_seconds": 4.5,
                    "memory_projection_catch_up_batch_size": 100,
                    "wait_poller_policy": {
                        "enabled": True,
                        "poll_interval_seconds": 0.4,
                        "claim_ttl_seconds": 41,
                        "claim_batch_size": 42,
                        "backoff_initial_delay_seconds": 3,
                        "backoff_multiplier": 1.5,
                        "backoff_max_delay_seconds": 43,
                        "not_ready_observe_interval_seconds": 0.6,
                        "idle_poll_interval_seconds": 4,
                        "adapter_call_timeout_seconds": 7,
                        "close_drain_timeout_seconds": 2,
                        "max_outstanding_adapter_calls": 5,
                    },
                    "process_capsule_interrupt_policy": {
                        "terminate_grace_seconds": 0.35,
                        "kill_grace_seconds": 0.75,
                    },
                }
            },
        },
    )


def _write_execution_profile_overlay(
    workspace_root: Path,
    *,
    truncation_enabled: bool,
    duplicate_default_decision: str = "hint",
    profile_id: str = "standard-256k",
    context_window_class: str = "256k",
    min_context_window_tokens: int = 262144,
    model_id: str = "deepseek-v4-flash",
) -> None:
    """写入覆盖截断策略开关的 workspace execution profile 配置。

    :param workspace_root: pytest 临时 workspace root。
    :param truncation_enabled: tool truncation policy 是否启用。
    :param duplicate_default_decision: duplicate governance 默认决策。
    :param profile_id: 写入的 execution profile id。
    :param context_window_class: profile 上下文窗口分档。
    :param min_context_window_tokens: profile 最小上下文窗口 token 数。
    :param model_id: profile 默认 ordinary / compactor 模型 id。
    :returns: ``None``。
    :raises OSError: 目录或文件写入失败时抛出。
    """

    _write_json(
        workspace_root / "config" / "execution_profiles.json",
        {
            "default_execution_profile_id": profile_id,
            "execution_profiles": {
                profile_id: {
                    "context_window_class": context_window_class,
                    "min_context_window_tokens": min_context_window_tokens,
                    "run_baseline": {
                        "model_id": model_id,
                        "runner_option_hint_id": "interactive",
                    },
                    "compactor_baseline": {
                        "model_id": model_id,
                        "scene_id": "conversation_compaction",
                        "runner_option_hint_id": "conversation_compaction",
                        "user_prompt_template_path": ("scenes/conversation_compaction_user.md"),
                        "artifact_root": ".dayu/artifacts/compaction",
                    },
                    "context_budget_policy": {
                        "soft_threshold_context_ratio": 0.65,
                        "hard_threshold_context_ratio": 0.82,
                        "max_proactive_compactions_per_run": 2,
                        "max_reactive_compactions_per_run": 2,
                        "max_compaction_attempts_per_operation": 7,
                        "policy_ref": profile_id,
                    },
                    "memory_projection_policy": {
                        "context_window_size": 262144,
                        "selected_recent_window_item_cap": 32,
                        "selected_recent_window_char_cap": 131072,
                        "selected_recent_window_turn_floor": 4,
                        "fallback_selected_recent_window_item_cap": 8,
                        "fallback_selected_recent_window_char_cap": 32768,
                        "evidence_fact_item_cap": 256,
                        "evidence_fact_char_cap": 65536,
                        "evidence_fact_floor": 1,
                        "session_summary_char_cap": 4096,
                        "answer_anchor_item_cap": 32,
                        "answer_anchor_char_cap": 32768,
                        "forward_intent_item_cap": 32,
                        "forward_intent_char_cap": 32768,
                        "reference_continuity_item_cap": 32,
                        "reference_continuity_char_cap": 32768,
                        "reference_continuity_item_floor": 0,
                        "max_lag_events_for_inline_delta": 32,
                        "max_delta_repair_events": 128,
                        "policy_ref": profile_id,
                    },
                    "tool_truncation_policy": {
                        "enabled": truncation_enabled,
                        "default_cursor_ttl_seconds": 3600.0,
                        "default_limits": {
                            "text_chars": {"max_chars": 12000},
                            "text_lines": {"max_lines": 400},
                            "list_items": {"max_items": 200},
                            "binary_bytes": {"max_bytes": 1048576},
                        },
                    },
                    "tool_duplicate_governance_policy": {
                        "default_duplicate_decision": duplicate_default_decision,
                        "decisions_by_tool_name": {
                            "lookup_fact": "reuse",
                            "explain_fact": "require_justification",
                        },
                        "justification_argument_names_by_tool_name": {
                            "explain_fact": "duplicate_justification",
                        },
                        "messages": {
                            "allow": "本次重复工具调用已允许执行。",
                            "reuse": "请直接使用上一次工具结果继续推理，不要重复请求相同证据。",
                            "hint": (
                                "请优先使用上一次工具结果继续推理；只有当需要不同主体、"
                                "期间、指标或证据范围时，才重新调用工具并修改参数。"
                            ),
                            "require_justification": (
                                "重复调用同一工具前，必须在参数中说明为什么上一次"
                                "工具结果不足，以及本次需要补充的不同证据范围。"
                            ),
                            "hard_stop": (
                                "本次重复工具调用已被拒绝。请使用上一次工具结果继续"
                                "推理；如果信息不足，请说明不确定性，不要编造。"
                            ),
                            "attempt_scope_diagnostic": "检测到当前推理步骤中重复请求相同工具证据。",
                            "prior_accept_missing": (
                                "上一次相同工具请求没有产生可用结果。请说明信息不足，或在改变证据范围后再调用工具。"
                            ),
                        },
                    },
                    "agent_policy": {
                        "max_iterations": 24,
                        "continuation_max_attempts": 2,
                        "allow_tool_calls": True,
                        "tool_execution_timeout_seconds": 120.0,
                        "fallback_mode": "force_answer",
                        "fallback_prompt": ("请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。"),
                        "continuation_prompt": (
                            "请从上一条回复被截断的位置继续输出，保持原有语言、格式和结构，不要重复已经输出的内容。"
                        ),
                        "max_consecutive_failed_tool_batches": 2,
                    },
                }
            },
        },
    )


def _custom_compactor_scene_locations(workspace_root: Path) -> RuntimeLocations:
    """写入只包含自定义 compactor scene 的 prompt 根目录。

    :param workspace_root: pytest 临时 workspace root。
    :returns: 指向自定义 prompt 根目录的 RuntimeLocations。
    :raises OSError: 测试 prompt 文件写入失败时抛出。
    """

    prompt_root = workspace_root / "custom-prompts"
    manifest_root = prompt_root / "manifests"
    scene_root = prompt_root / "scenes"
    _write_json(
        manifest_root / f"{_CUSTOM_COMPACTOR_SCENE_ID}.json",
        {
            "schema_version": 1,
            "scene": _CUSTOM_COMPACTOR_SCENE_ID,
            "version": "v1",
            "description": "自定义 compactor scene",
            "capability_tags": ["conversation_compaction"],
            "extends": [],
            "model": {
                "default_model_id": _MODEL_ID,
                "runner_option_hint_id": "conversation_compaction",
            },
            "agent_policy": {
                "max_iterations": 1,
                "continuation_max_attempts": 0,
                "allow_tool_calls": False,
                "tool_execution_timeout_seconds": 1.0,
                "fallback_mode": "raise_error",
                "fallback_prompt": "Compactor is not allowed to fallback-answer.",
                "continuation_prompt": ("Continue the strict JSON object without repeating content already emitted."),
                "max_consecutive_failed_tool_batches": 1,
            },
            "tool_selection": {
                "mode": "none",
                "tool_names": [],
                "tool_tags_any": [],
                "allow_empty": False,
            },
            "defaults": {
                "missing_required_fragment": "fail_closed",
            },
            "fragments": [
                {
                    "id": "custom_compactor_system",
                    "path": "scenes/custom_compactor_system.md",
                    "order": 100,
                    "required": True,
                },
            ],
            "context_slots": [],
        },
    )
    scene_root.mkdir(parents=True, exist_ok=True)
    (scene_root / "custom_compactor_system.md").write_text(
        "custom compactor system prompt",
        encoding="utf-8",
    )
    (scene_root / "custom_compactor_user.md").write_text(
        "custom compactor user prompt <<compaction_request>>",
        encoding="utf-8",
    )
    return RuntimeLocations(
        config_overlay_dir=None,
        prompt_asset_root=prompt_root,
        scene_manifest_root=manifest_root,
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造测试用 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor="service-test",
        source="tests.service.test_host_assembly",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="service-test"),),
        operation_context=OperationContext(
            operation_name="service_host_assembly_test",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase12_2_service_assembly",
            correlation_id=None,
        ),
    )


def _compactor_scene_inputs(*, agent_policy_override: SceneAgentPolicyOverride | None) -> PreparedSceneInputs:
    """构造测试用 compactor scene inputs。

    :param agent_policy_override: compactor scene agent policy override。
    :returns: PreparedSceneInputs。
    :raises ValueError: 字段非法时由底层 dataclass 抛出。
    """

    return PreparedSceneInputs(
        system_messages=("system",),
        system_prompt="system",
        tool_selection=SceneToolSelectionResult(
            mode=SceneToolSelectionMode.NONE,
            tool_names=frozenset(),
        ),
        model_hints=None,
        agent_policy_override=agent_policy_override,
        fragment_refs=(),
        source_refs=(),
        content_digest="sha256:test",
        capability_tags=(),
    )


async def _noop_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用空工具 callable。

    :param call: 工具调用请求。
    :param context: 批式工具执行上下文。
    :returns: 取消 outcome。
    :raises Exception: 不主动抛出异常。
    """

    del call
    del context
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message="tool disabled in service assembly test",
        hint=None,
        meta=None,
    )


def _tool_definition(name: str) -> ToolDefinition:
    """构造测试用工具定义。

    :param name: 工具名。
    :returns: 工具定义。
    :raises ValueError: 工具声明名称与 schema 名称不一致时抛出。
    """

    properties: dict[str, JsonValue] = {}
    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=f"{name} test tool",
                parameters=ToolParametersSchema(
                    type="object",
                    properties=properties,
                    required=(),
                    additional_properties=False,
                ),
            ),
        ),
        callable=_noop_tool,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=(),
    )


def _source_ref(source_id: str) -> ToolBundleSourceRef:
    """构造测试用工具来源引用。

    :param source_id: 来源标识。
    :returns: 工具来源引用。
    :raises ValueError: 来源字段非法时由契约构造抛出。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=source_id,
        version_ref=None,
        content_digest=None,
    )


def _provider_config(
    *,
    provider_id: str,
    import_path: str,
    source_id: str,
    workspace_root: Path,
) -> ToolDiscoveryProviderConfig:
    """构造测试用工具发现 provider 配置。

    :param provider_id: provider spec id。
    :param import_path: 显式 provider import path。
    :param source_id: provider source id。
    :param workspace_root: Fins workspace root。
    :returns: ToolDiscoveryProviderConfig。
    :raises ValueError: 不主动抛出异常。
    """

    return ToolDiscoveryProviderConfig(
        provider_id=provider_id,
        import_path=import_path,
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=source_id,
        enabled=True,
        config={
            "workspace_root": str(workspace_root),
            "awaiting_resolution_mode": "poll",
        },
    )


def _provider_config_with_config(
    *,
    provider_id: str,
    import_path: str,
    source_id: str,
    config: dict[str, JsonValue],
) -> ToolDiscoveryProviderConfig:
    """使用原始 config 构造测试用 provider 配置。

    :param provider_id: provider spec id。
    :param import_path: 显式 provider import path。
    :param source_id: provider source id。
    :param config: provider 自有 JSON config。
    :returns: ToolDiscoveryProviderConfig。
    :raises ValueError: 不主动抛出异常。
    """

    return ToolDiscoveryProviderConfig(
        provider_id=provider_id,
        import_path=import_path,
        entry_point=None,
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=source_id,
        enabled=True,
        config=config,
    )


def _provider_config_with_mode(
    *,
    provider_id: str,
    import_path: str,
    source_id: str,
    workspace_root: Path,
    mode: str,
    enabled: bool = True,
) -> ToolDiscoveryProviderConfig:
    """构造显式声明 awaiting resolution mode 的测试 provider。

    :param provider_id: provider spec id。
    :param import_path: provider import path。
    :param source_id: provider source id。
    :param workspace_root: Fins workspace root。
    :param mode: 原始 provider-owned mode 字符串。
    :param enabled: provider 是否启用。
    :returns: 完整 provider config。
    :raises ValueError: 不主动抛出异常。
    """

    provider = _provider_config(
        provider_id=provider_id,
        import_path=import_path,
        source_id=source_id,
        workspace_root=workspace_root,
    )
    return replace(
        provider,
        enabled=enabled,
        config={
            "workspace_root": str(workspace_root),
            "awaiting_resolution_mode": mode,
        },
    )


def _compose_with_fins_provider_configs(
    *,
    tmp_path: Path,
    provider_configs: tuple[ToolDiscoveryProviderConfig, ...],
    policy_enabled: bool = True,
) -> ServiceOpenHostAssemblyResult:
    """用真实 ConfigLoader 与 Service discovery 组合 Fins provider matrix。

    :param tmp_path: pytest 临时 workspace。
    :param provider_configs: 当前 case 的 effective provider configs。
    :param policy_enabled: host runtime policy enabled 值。
    :returns: 完整 Service Host assembly 结果。
    :raises Exception: provider validation 或 composition fail-closed 时透出。
    """

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    local_runtime = config.host_runtime.runtimes["local"]
    configured_runtime = replace(
        local_runtime,
        wait_poller_policy=replace(
            local_runtime.wait_poller_policy,
            enabled=policy_enabled,
        ),
    )
    effective_config = replace(
        config,
        host_runtime=replace(
            config.host_runtime,
            runtimes={**config.host_runtime.runtimes, "local": configured_runtime},
        ),
    )
    discovered_tools = discover_service_tools(provider_configs)
    return compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=effective_config,
            locations=locations,
            scene_inputs=_compactor_scene_inputs(agent_policy_override=None),
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )


def _service_tool_call(
    tool_name: str,
    arguments: dict[str, JsonValue],
) -> ToolCallRequest:
    """构造 Service assembly focused 测试用工具调用请求。

    :param tool_name: 工具名。
    :param arguments: 工具参数。
    :returns: 工具调用请求。
    :raises ValueError: 请求字段非法时由契约构造抛出。
    """

    return ToolCallRequest(
        tool_call_id=f"call-{tool_name}",
        name=tool_name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _service_tool_context() -> BatchToolExecutionContext:
    """构造 Service assembly focused 测试用批执行上下文。

    :returns: 批执行上下文。
    :raises ValueError: 上下文字段非法时由契约构造抛出。
    """

    return BatchToolExecutionContext(
        run_id="run-service-fins-awaiting",
        session_id="session-service-fins-awaiting",
        iteration_id="iteration-service-fins-awaiting",
        timeout_seconds=30.0,
        cancellation_token=_OpenCancellationToken(),
        correlation_id="correlation-service-fins-awaiting",
    )


def _observation_handle_from_awaiting(
    outcome: ToolAwaitingOutcome,
) -> FinsObservationHandle:
    """从 awaiting outcome 恢复测试观察用 Fins handle。

    :param outcome: Fins awaiting 工具返回的 outcome。
    :returns: Fins observation handle。
    :raises ValueError: resume token 非法时抛出。
    """

    return FinsObservationHandle(
        handle_id=parse_observation_handle_id_token(outcome.await_spec.resume_token),
        operation_kind=FinsOperationKind.DOWNLOAD,
        created_at=datetime.now(timezone.utc),
    )


async def _wait_until_observation_leaves_pending(
    runtime: FinsIngestionRuntime,
    handle: FinsObservationHandle,
) -> FinsObservationSnapshot:
    """等待 observation 被 activation 提交并离开 prepared 状态。

    :param runtime: Fins ingestion runtime。
    :param handle: observation handle。
    :returns: observation snapshot。
    :raises AssertionError: observation 在限定时间内仍停留在 ``PENDING`` 时抛出。
    """

    last_snapshot = await runtime.poll_observation(handle)
    for _ in range(100):
        if last_snapshot.status is not FinsObservationStatus.PENDING:
            return last_snapshot
        await asyncio.sleep(0.01)
        last_snapshot = await runtime.poll_observation(handle)
    raise AssertionError("Fins observation did not leave PENDING after activation")


def _accepted_awaiting_ack() -> ToolAwaitingAcceptedAck:
    """构造测试用 Host awaiting accepted ack。

    :returns: accepted ack。
    :raises ValueError: ack 字段非法时由契约构造抛出。
    """

    tool_ref = ToolAwaitingEventRef(
        event_id="event-service-tool-awaiting",
        event_sequence=1,
    )
    run_ref = ToolAwaitingEventRef(
        event_id="event-service-run-waiting",
        event_sequence=2,
    )
    attempt_ref = ToolAwaitingEventRef(
        event_id="event-service-attempt-suspended",
        event_sequence=3,
    )
    return ToolAwaitingAcceptedAck(
        accepted_event_refs=(tool_ref, run_ref, attempt_ref),
        wait_id="wait-service-fins-awaiting",
        tool_awaiting_event_ref=tool_ref,
        run_waiting_event_ref=run_ref,
        attempt_suspended_event_ref=attempt_ref,
        result_digest="digest-service-fins-awaiting",
        idempotency_record_ref="idempotency-service-fins-awaiting",
    )


class _OpenCancellationToken(CancellationToken):
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间戳。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


def _write_json(path: Path, value: JsonValue) -> None:
    """写入 JSON fixture。

    :param path: 目标路径。
    :param value: JSON 值。
    :returns: ``None``。
    :raises OSError: 文件写入失败时抛出。
    :raises TypeError: JSON 序列化失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
