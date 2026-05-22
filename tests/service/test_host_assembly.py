"""``dayu.service.host_assembly`` 组合 helper 测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dayu.contracts import JsonValue
from dayu.engine import AgentFallbackMode
from dayu.host import FollowupBehavior, HostCallContext, OperationContext
from dayu.host.api import AuthorizationClaim
from dayu.runtime.config_loader import ConfigLoader
from dayu.runtime.location import resolve_runtime_locations
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
                execution_profile_id="standard",
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
    assert result.options.ordinary_run_baseline.runner_spec.headers[
        "Authorization"
    ] == f"Bearer {_API_KEY}"
    assert result.diagnostics.model_source == "run_override"
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
                    "truncation_manager_enabled": True,
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
