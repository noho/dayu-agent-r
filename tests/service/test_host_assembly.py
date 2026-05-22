"""``dayu.service.host_assembly`` 组合 helper 测试。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from dayu.contracts import JsonValue
from dayu.engine import AgentFallbackMode
from dayu.host.api import (
    AuthorizationClaim,
    FollowupBehavior,
    HostCallContext,
    OperationContext,
)
from dayu.runtime.config_loader import ConfigLoader
from dayu.runtime.location import resolve_runtime_locations
from dayu.runtime.assembly import RuntimeAssemblySelectionError
from dayu.runtime.scene_prepare import (
    ScenePrepareRequest,
    SceneToolCatalog,
    prepare_scene,
)
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceOpenHostAssemblyRequest,
    _agent_fallback_mode_from_config,
    compose_open_host_options,
    compose_submit_followup_request,
    discover_service_tools,
)

_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_SCENE_ID = "smoke_host_public_multiturn"
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"


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
            available_tools=SceneToolCatalog.from_tool_bundle(
                discovered_tools.tool_bundle
            ),
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
    assert result.options.ordinary_run_baseline.runner_spec.headers[
        "Authorization"
    ] == f"Bearer {_API_KEY}"
    assert result.options.ordinary_run_baseline.runner_options.max_tokens is None
    compactor_baseline = result.options.compactor_runner_baseline
    assert compactor_baseline is not None
    assert compactor_baseline.compactor_runner_options.max_tokens is None
    assert result.options.ordinary_run_baseline.agent_policy.max_iterations == 20
    assert result.options.ordinary_run_baseline.agent_policy.continuation_max_attempts == 2
    assert result.diagnostics.model_source == "run_override"
    assert result.diagnostics.execution_profile_id == "standard-256k"
    assert result.diagnostics.ordinary_profile_compatibility.status == "conservative"
    assert (
        result.diagnostics.ordinary_profile_compatibility.profile_id
        == "standard-256k"
    )
    assert (
        result.diagnostics.ordinary_profile_compatibility.selected_model_id
        == _MODEL_ID
    )
    assert result.diagnostics.tool_selection == (
        "mode=select,tools=record_smoke_fact"
    )


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
            available_tools=SceneToolCatalog.from_tool_bundle(
                discovered_tools.tool_bundle
            ),
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


def test_agent_fallback_mode_from_config_uses_engine_enum_values() -> None:
    """fallback mode 映射复用 Engine enum 原生值校验。

    :returns: ``None``。
    :raises AssertionError: 合法值未映射到对应 Engine enum 时抛出。
    :raises ValueError: 非法值未保持 ``ValueError`` 语义时抛出。
    """

    assert (
        _agent_fallback_mode_from_config("force_answer")
        is AgentFallbackMode.FORCE_ANSWER
    )
    assert (
        _agent_fallback_mode_from_config("raise_error")
        is AgentFallbackMode.RAISE_ERROR
    )
    with pytest.raises(ValueError):
        _agent_fallback_mode_from_config("unsupported")


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
            available_tools=SceneToolCatalog.from_tool_bundle(
                discovered_tools.tool_bundle
            ),
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
            available_tools=SceneToolCatalog.from_tool_bundle(
                discovered_tools.tool_bundle
            ),
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
            available_tools=SceneToolCatalog.from_tool_bundle(
                discovered_tools.tool_bundle
            ),
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
    assert (
        result.diagnostics.compactor_profile_compatibility.selected_model_id
        == "deepseek-v4-flash"
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
                    "import_path": (
                        "utils.smoke_host_public_multiturn:discover_smoke_tools"
                    ),
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
    profile_id: str = "standard-256k",
    context_window_class: str = "256k",
    min_context_window_tokens: int = 262144,
    model_id: str = "deepseek-v4-flash",
) -> None:
    """写入覆盖截断策略开关的 workspace execution profile 配置。

    :param workspace_root: pytest 临时 workspace root。
    :param truncation_enabled: tool truncation policy 是否启用。
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
                        "runner_option_hint_id": "conversation_compaction",
                        "artifact_root": "workspace/.dayu/artifacts/compaction",
                    },
                    "context_budget_policy": {
                        "soft_threshold_context_ratio": 0.65,
                        "hard_threshold_context_ratio": 0.82,
                        "max_proactive_compactions_per_run": 2,
                        "max_reactive_compactions_per_run": 2,
                        "max_compaction_attempts_per_operation": 3,
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
                    "agent_policy": {
                        "max_iterations": 24,
                        "continuation_max_attempts": 2,
                        "allow_tool_calls": True,
                        "tool_execution_timeout_seconds": 120.0,
                        "fallback_mode": "force_answer",
                        "fallback_prompt": (
                            "请基于已获得的信息直接回答问题。"
                            "信息不足时必须说明不确定性，不得编造。"
                        ),
                        "continuation_prompt": (
                            "请从上一条回复被截断的位置继续输出，"
                            "保持原有语言、格式和结构，不要重复已经输出的内容。"
                        ),
                        "max_consecutive_failed_tool_batches": 2,
                    },
                }
            },
        },
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
        authorization_claims=(
            AuthorizationClaim(name="role", value="service-test"),
        ),
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
