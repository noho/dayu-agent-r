"""``dayu.service.host_assembly`` 组合 helper 测试。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Final

import pytest

from dayu.contracts import (
    BatchToolExecutionContext,
    JsonValue,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolBundle,
    ToolBundleSourceKind,
    ToolCallRequest,
    ToolCancelledOutcome,
    ToolDefinition,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine import AgentFallbackMode, AgentPolicy
from dayu.host.api import (
    AuthorizationClaim,
    FollowupBehavior,
    HostCallContext,
    OperationContext,
)
from dayu.host.tool_duplicate_governance import (
    DuplicateDecisionKind,
)
from dayu.runtime.config_loader import ConfigLoader
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
    SceneAgentFallbackMode,
    SceneAgentPolicyOverride,
    ScenePrepareRequest,
    SceneToolCatalog,
    SceneToolSelectionMode,
    SceneToolSelectionResult,
    prepare_scene,
)
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceDiscoveredTools,
    ServiceOpenHostAssemblyRequest,
    _agent_fallback_mode_from_config,
    _compactor_agent_policy_from_scene_inputs,
    _compactor_prompts_from_scene_inputs,
    _duplicate_decision_from_config,
    _render_headers,
    _resolve_prompt_asset_path,
    _resolve_project_path,
    _runner_spec_from_model,
    _tool_discovery_specs,
    _tooling_options_from_discovery,
    compose_open_host_options,
    compose_submit_followup_request,
    discover_service_tools,
)

_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_SCENE_ID = "smoke_host_public_multiturn"
_CUSTOM_COMPACTOR_SCENE_ID = "custom_compactor_scene"
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"
_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION: Final[int] = 5


def _scene_tool_catalog(discovered_tools: ServiceDiscoveredTools) -> SceneToolCatalog:
    """从测试发现结果构造 scene 工具目录。

    :param discovered_tools: Service 工具发现结果。
    :returns: SceneToolCatalog。
    :raises AssertionError: 测试配置未发现工具时抛出。
    """

    return SceneToolCatalog.from_tool_bundle(discovered_tools.tool_bundle)


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
        fallback_mode=SceneAgentFallbackMode.RAISE_ERROR,
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
        project_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = discover_service_tools(config)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "fins_default_subject": "测试财报主体",
                "base_user": "service-assembly-test",
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
    assert result.options.memory_projection_policy.max_evidence_backed_facts == 256
    context_budget_policy = result.options.context_budget_policy
    assert context_budget_policy is not None
    assert (
        context_budget_policy.max_compaction_attempts_per_operation
        == _EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION
    )
    assert result.options.ordinary_run_baseline.runner_spec.headers["Authorization"] == f"Bearer {_API_KEY}"
    assert result.options.ordinary_run_baseline.runner_options.max_tokens is None
    compactor_baseline = result.options.compactor_runner_baseline
    assert compactor_baseline is not None
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
        continuation_prompt=("Continue the strict JSON object without repeating content " "already emitted."),
        max_consecutive_failed_tool_batches=1,
    )
    assert "Host-owned context compaction" in (compactor_baseline.compactor_system_prompt)
    assert "<<compaction_request>>" in (compactor_baseline.compactor_user_prompt_template)
    assert result.options.ordinary_run_baseline.agent_policy.max_iterations == 20
    assert result.options.ordinary_run_baseline.agent_policy.continuation_max_attempts == 2
    assert result.diagnostics.model_source == "run_override"
    assert result.diagnostics.execution_profile_id == "standard-256k"
    assert result.diagnostics.ordinary_profile_compatibility.status == "conservative"
    assert result.diagnostics.ordinary_profile_compatibility.profile_id == "standard-256k"
    assert result.diagnostics.ordinary_profile_compatibility.selected_model_id == _MODEL_ID
    assert result.diagnostics.tool_selection == ("mode=select,tools=record_smoke_fact")


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
        project_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = discover_service_tools(config)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "fins_default_subject": "测试财报主体",
                "base_user": "service-assembly-test",
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
        project_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = discover_service_tools(config)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "fins_default_subject": "测试财报主体",
                "base_user": "service-assembly-test",
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
    """fallback mode 映射复用 Engine enum 原生值校验。

    :returns: ``None``。
    :raises AssertionError: 合法值未映射到对应 Engine enum 时抛出。
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
            duplicate_governance_policy_config=_duplicate_governance_policy_config(),
        )


def test_tool_discovery_specs_requires_provider_location() -> None:
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
        allow_empty=False,
    )

    with pytest.raises(ValueError, match="import_path or entry_point"):
        _tool_discovery_specs((provider,))


def test_tool_discovery_specs_uses_entry_point_location() -> None:
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
        allow_empty=False,
    )

    specs = _tool_discovery_specs((provider,))

    assert len(specs) == 1
    assert specs[0].spec_id == "entry-provider"
    assert specs[0].enabled is True


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
        project_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = discover_service_tools(config)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "fins_default_subject": "测试财报主体",
                "base_user": "service-assembly-test",
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
        project_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = discover_service_tools(config)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "fins_default_subject": "测试财报主体",
                "base_user": "service-assembly-test",
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
    assert (
        policy.decisions_by_tool_name["explain_fact"]
        is DuplicateDecisionKind.REQUIRE_JUSTIFICATION
    )
    assert (
        policy.justification_argument_names_by_tool_name["explain_fact"]
        == "duplicate_justification"
    )
    assert policy.messages.reuse == "reuse prior accepted tool result"


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
        project_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = discover_service_tools(config)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "fins_default_subject": "测试财报主体",
                "base_user": "service-assembly-test",
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
        project_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = discover_service_tools(config)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=_SCENE_ID,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "fins_default_subject": "测试财报主体",
                "base_user": "service-assembly-test",
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


def test_resolve_project_path_rejects_relative_escape(tmp_path: Path) -> None:
    """Service project path 相对配置不得逃逸 workspace root。"""

    with pytest.raises(ValueError, match="escapes workspace root"):
        _resolve_project_path(tmp_path, "../outside.sqlite3")


def test_resolve_project_path_keeps_absolute_path(tmp_path: Path) -> None:
    """Service project path 绝对路径保持原有语义。"""

    absolute_path = tmp_path.parent / "outside.sqlite3"

    assert _resolve_project_path(tmp_path, str(absolute_path)) == absolute_path


def _duplicate_governance_policy_config() -> ToolDuplicateGovernancePolicyConfig:
    """构造 Service 测试使用的 duplicate governance typed config。

    :returns: duplicate governance policy typed config。
    :raises Exception: 不主动抛出异常。
    """

    return ToolDuplicateGovernancePolicyConfig(
        default_duplicate_decision="allow",
        decisions_by_tool_name={},
        justification_argument_names_by_tool_name={},
        messages=ToolDuplicateGovernanceMessagesConfig(
            allow="duplicate tool call allowed",
            reuse="reuse prior accepted tool result",
            hint=(
                "duplicate tool call should use prior accepted result "
                "or change evidence scope"
            ),
            require_justification=(
                "duplicate tool call requires structured justification"
            ),
            hard_stop="duplicate tool call hard-stopped by Host governance",
            attempt_scope_diagnostic=(
                "duplicate tool call governed by attempt-local ToolRuntime index"
            ),
            prior_accept_missing=(
                "prior duplicate owner did not produce an accepted tool result"
            ),
        ),
    )


def _write_tool_discovery_overlay(workspace_root: Path) -> None:
    """写入启用 smoke provider 的 workspace tool discovery overlay。

    :param workspace_root: pytest 临时 workspace root。
    :returns: ``None``。
    :raises OSError: 目录或文件写入失败时抛出。
    """

    _write_json(
        workspace_root / "workspace" / "config" / "tool_discovery.json",
        {
            "providers": {
                "financial-tools": {
                    "import_path": ("utils.smoke_host_public_multiturn:discover_smoke_tools"),
                    "entry_point": None,
                    "source_kind": "config_binding",
                    "source_id": "utils.smoke_host_public_multiturn",
                    "enabled": True,
                    "allow_empty": False,
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
        workspace_root / "workspace" / "config" / "host_runtime.json",
        {
            "default_host_runtime_id": "local",
            "runtimes": {
                "local": {
                    "store_root": "workspace/.dayu/host",
                    "artifact_root": "workspace/.dayu/artifacts",
                    "sqlite": {
                        "path": "workspace/.dayu/host/dayu_host.sqlite3",
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
                }
            },
        },
    )


def _write_execution_profile_overlay(
    workspace_root: Path,
    *,
    truncation_enabled: bool,
    duplicate_default_decision: str = "allow",
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
        workspace_root / "workspace" / "config" / "execution_profiles.json",
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
                        "artifact_root": "workspace/.dayu/artifacts/compaction",
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
                        "max_pinned_items": 32,
                        "max_evidence_backed_facts": 256,
                        "max_working_assumptions": 128,
                        "recent_raw_turns_floor": 4,
                        "raw_turn_context_ratio": 0.02,
                        "raw_turn_size_floor": 1024,
                        "raw_turn_size_cap": 8192,
                        "history_pool_context_ratio": 0.18,
                        "history_pool_size_floor": 8192,
                        "history_pool_size_cap": 131072,
                        "stable_layer_context_ratio": 0.12,
                        "stable_layer_size_floor": 4096,
                        "stable_layer_size_cap": 65536,
                        "max_lag_events_for_inline_delta": 32,
                        "max_delta_repair_events": 128,
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
                            "allow": "duplicate tool call allowed",
                            "reuse": "reuse prior accepted tool result",
                            "hint": (
                                "duplicate tool call should use prior accepted result "
                                "or change evidence scope"
                            ),
                            "require_justification": (
                                "duplicate tool call requires structured justification"
                            ),
                            "hard_stop": (
                                "duplicate tool call hard-stopped by Host governance"
                            ),
                            "attempt_scope_diagnostic": (
                                "duplicate tool call governed by attempt-local "
                                "ToolRuntime index"
                            ),
                            "prior_accept_missing": (
                                "prior duplicate owner did not produce an accepted "
                                "tool result"
                            ),
                        },
                    },
                    "agent_policy": {
                        "max_iterations": 24,
                        "continuation_max_attempts": 2,
                        "allow_tool_calls": True,
                        "tool_execution_timeout_seconds": 120.0,
                        "fallback_mode": "force_answer",
                        "fallback_prompt": (
                            "请基于已获得的信息直接回答问题。" "信息不足时必须说明不确定性，不得编造。"
                        ),
                        "continuation_prompt": (
                            "请从上一条回复被截断的位置继续输出，" "保持原有语言、格式和结构，不要重复已经输出的内容。"
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
                "continuation_prompt": (
                    "Continue the strict JSON object without repeating content " "already emitted."
                ),
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
        truncate=None,
        display=None,
        tags=(),
    )


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
