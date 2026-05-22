"""``dayu.runtime.config_loader`` 配置加载测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dayu.contracts import JsonValue, ToolBundleSourceKind
from dayu.runtime.config_loader import (
    ConfigExtendsError,
    ConfigFieldError,
    ConfigLoader,
    ConfigShapeError,
    RuntimeConfig,
    config_file_names,
    default_fallback_prompt,
    legacy_config_file_names,
    load_runtime_config,
)


def _write_json(path: Path, value: JsonValue) -> None:
    """写入测试 JSON 文件。

    :param path: 目标文件路径。
    :param value: 可被 ``json.dumps`` 序列化的测试值。
    :returns: ``None``。
    :raises OSError: 文件或目录写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _runner_option_hints() -> dict[str, JsonValue]:
    """构造完整 runner option hints fixture。

    :returns: runner option hints JSON object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "interactive": {
            "temperature": 0.2,
            "max_tokens": 100,
            "top_p": 0.9,
            "stream": True,
        },
        "conversation_compaction": {
            "temperature": 0.0,
            "max_tokens": 50,
            "top_p": 1.0,
            "stream": False,
        },
    }


def _base_model_record(*, endpoint: str) -> dict[str, JsonValue]:
    """构造完整模型配置记录。

    :param endpoint: endpoint URL。
    :returns: 模型配置 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "extends": None,
        "runner_kind": "openai_compatible",
        "provider": "test-provider",
        "model": "base-model",
        "endpoint": endpoint,
        "api_key_ref": "RAW_API_KEY_REF",
        "headers": {
            "Authorization": "Bearer ${RAW_API_KEY_REF}",
            "X-Raw": "{{NOT_EXPANDED}}",
        },
        "supports_tool_calling": True,
        "supports_stream": True,
        "supports_stream_usage": False,
        "default_timeout_seconds": 10.0,
        "max_retries": 1,
        "sse_idle_timeout_seconds": 20.0,
        "sse_heartbeat_seconds": 5.0,
        "provider_request_extension": {
            "type": "custom",
            "nested": {"keep": ["as", "json"]},
        },
        "context_window_tokens": 1000,
        "runtime_hints": {
            "runner_option_hints": _runner_option_hints(),
        },
    }


def _execution_profile_record() -> dict[str, JsonValue]:
    """构造完整 execution profile fixture。

    :returns: execution profile JSON object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "extends": None,
        "run_baseline": {
            "model_id": "base-model",
            "runner_option_hint_id": "interactive",
        },
        "compactor_baseline": {
            "model_id": "base-model",
            "runner_option_hint_id": "conversation_compaction",
            "artifact_root": "artifacts/compact",
        },
        "context_budget_policy": {
            "context_window_size": 1000,
            "soft_threshold_context_ratio": 0.6,
            "hard_threshold_context_ratio": 0.8,
            "max_proactive_compactions_per_run": 1,
            "max_reactive_compactions_per_run": 1,
            "max_compaction_attempts_per_operation": 2,
            "policy_ref": "test",
        },
        "memory_projection_policy": {
            "context_window_size": 1000,
            "max_pinned_items": 2,
            "max_verified_facts": 3,
            "max_working_assumptions": 4,
            "recent_raw_turns_floor": 1,
            "raw_turn_context_ratio": 0.1,
            "raw_turn_size_floor": 10,
            "raw_turn_size_cap": 100,
            "history_pool_context_ratio": 0.2,
            "history_pool_size_floor": 20,
            "history_pool_size_cap": 200,
            "stable_layer_context_ratio": 0.3,
            "stable_layer_size_floor": 30,
            "stable_layer_size_cap": 300,
            "max_lag_events_for_inline_delta": 5,
            "max_delta_repair_events": 6,
        },
        "tool_truncation_policy": {
            "enabled": True,
            "default_cursor_ttl_seconds": 60.0,
            "default_limits": {
                "text_chars": {"max_chars": 100},
                "text_lines": {"max_lines": 10},
                "list_items": {"max_items": 8},
                "binary_bytes": {"max_bytes": 1024},
            },
        },
        "agent_policy_profile_id": "default-agent",
    }


def _agent_policy_profile_record() -> dict[str, JsonValue]:
    """构造完整 agent policy profile fixture。

    :returns: agent policy profile JSON object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "extends": None,
        "max_iterations": 3,
        "continuation_max_attempts": 1,
        "allow_tool_calls": True,
        "tool_execution_timeout_seconds": 30.0,
        "fallback_mode": "force_answer",
        "fallback_prompt": default_fallback_prompt(),
        "continuation_prompt": "continue",
        "max_consecutive_failed_tool_batches": 2,
    }


def _minimal_package_config(root: Path) -> None:
    """写入一套最小完整包内配置 fixture。

    :param root: package config fixture 根目录。
    :returns: ``None``。
    :raises OSError: 文件写入失败时抛出。
    """

    _write_json(
        root / "models.json",
        {
            "models": {
                "base-model": _base_model_record(
                    endpoint="https://package.example/chat"
                ),
                "derived-model": {
                    "extends": "base-model",
                    "model": "derived-model",
                    "endpoint": "https://derived.example/chat",
                },
                "final-model": {
                    "extends": "derived-model",
                    "endpoint": "https://final.example/chat",
                },
            }
        },
    )
    _write_json(
        root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard",
            "execution_profiles": {
                "standard": _execution_profile_record(),
            },
            "agent_policy_profiles": {
                "default-agent": _agent_policy_profile_record(),
            },
        },
    )
    _write_json(
        root / "host_runtime.json",
        {
            "default_host_runtime_id": "local",
            "runtimes": {
                "local": {
                    "extends": None,
                    "store_root": "workspace/.dayu/host",
                    "artifact_root": "workspace/.dayu/artifacts",
                    "sqlite": {
                        "path": "workspace/.dayu/host/dayu.sqlite3",
                        "busy_timeout_seconds": 5.0,
                        "write_busy_retry_count": 8,
                        "write_retry_initial_delay_seconds": 0.005,
                        "write_retry_backoff_multiplier": 1.5,
                        "write_retry_max_delay_seconds": 0.05,
                    },
                    "host_execution_lane_name": "llm_api",
                    "worker_backend": "local",
                    "dispatch_poll_interval_seconds": 0.1,
                    "payload_inline_threshold_bytes": 4096,
                    "worker_startup_timeout_seconds": 10.0,
                    "memory_projection_catch_up_batch_size": 10,
                    "truncation_manager_enabled": True,
                }
            },
        },
    )
    _write_json(
        root / "runtime_lanes.json",
        {
            "coordinator": {
                "db_path": "workspace/.dayu/runtime/lane.sqlite3",
                "busy_timeout_seconds": 5.0,
                "poll_interval_seconds": 0.05,
            },
            "lanes": {
                "llm_api": {
                    "extends": None,
                    "capacity": 1,
                    "default_timeout_seconds": None,
                    "claim_ttl_seconds": 10.0,
                    "heartbeat_interval_seconds": 2.0,
                }
            },
        },
    )
    _write_json(
        root / "tool_discovery.json",
        {
            "providers": {
                "tools": {
                    "extends": None,
                    "import_path": "tests.fake_tools:provider",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "tests.fake_tools",
                    "enabled": False,
                    "allow_empty": True,
                }
            }
        },
    )


def test_default_runtime_config_files_load_as_typed_views() -> None:
    """五个包内默认新配置文件必须都能加载成 typed view。"""

    config = load_runtime_config()

    assert "runtime_lanes.json" in config_file_names()
    assert config.models.models["deepseek-v4-flash"].model_id == "deepseek-v4-flash"
    assert (
        config.models.models["deepseek-v4-flash"]
        .runtime_hints.runner_option_hints["interactive"]
        .max_tokens
        == 4096
    )
    assert config.execution_profiles.default_execution_profile_id == "standard"
    assert config.host_runtime.default_host_runtime_id == "local"
    host_runtime = config.host_runtime.runtimes["local"]
    assert host_runtime.sqlite.write_busy_retry_count == 8
    assert host_runtime.sqlite.write_retry_initial_delay_seconds == 0.005
    assert host_runtime.payload_inline_threshold_bytes == 4096
    assert host_runtime.worker_startup_timeout_seconds == 10.0
    assert config.runtime_lanes.lanes["llm_api"].capacity == 4
    provider = config.tool_discovery.providers["financial-tools"]
    assert provider.source_kind == ToolBundleSourceKind.EXPLICIT_PROVIDER
    assert provider.import_path == "dayu.fins.tools:discover_tools"


def test_workspace_record_replaces_package_record_without_deep_merge(
    tmp_path: Path,
) -> None:
    """workspace 同 id 记录必须整条替换包内默认记录。"""

    package_root = tmp_path / "package"
    workspace_root = tmp_path / "workspace"
    _minimal_package_config(package_root)
    replacement = _base_model_record(endpoint="https://workspace.example/chat")
    replacement["headers"] = {"Authorization": "Bearer workspace"}
    _write_json(workspace_root / "models.json", {"models": {"base-model": replacement}})

    config = ConfigLoader(package_config_dir=package_root).load(
        workspace_config_dir=workspace_root
    )

    assert config.models.models["base-model"].endpoint == "https://workspace.example/chat"
    assert config.models.models["base-model"].headers == {
        "Authorization": "Bearer workspace"
    }
    assert config.models.models["derived-model"].endpoint == "https://derived.example/chat"


def test_single_extends_chain_resolves_to_complete_typed_record(tmp_path: Path) -> None:
    """合法 A -> B -> C 单继承链必须解析为完整 typed record。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)

    config = ConfigLoader(package_config_dir=package_root).load()

    final = config.models.models["final-model"]
    assert final.provider == "test-provider"
    assert final.model == "derived-model"
    assert final.endpoint == "https://final.example/chat"
    compact = final.runtime_hints.runner_option_hints["conversation_compaction"]
    assert compact.stream is False


def test_extends_cycle_fails_fast(tmp_path: Path) -> None:
    """循环继承必须在 ConfigLoader 层 fail fast。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "models.json",
        {"models": {"a": {"extends": "b"}, "b": {"extends": "a"}}},
    )

    with pytest.raises(ConfigExtendsError, match="cycle"):
        ConfigLoader(package_config_dir=package_root).load_models()


def test_self_extends_fails_fast(tmp_path: Path) -> None:
    """自引用继承必须 fail fast。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(package_root / "models.json", {"models": {"a": {"extends": "a"}}})

    with pytest.raises(ConfigExtendsError, match="extends self"):
        ConfigLoader(package_config_dir=package_root).load_models()


def test_multiple_extends_fails_fast(tmp_path: Path) -> None:
    """多继承声明必须失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "models.json",
        {
            "models": {
                "base-model": _base_model_record(
                    endpoint="https://package.example/chat"
                ),
                "derived-model": {
                    "extends": ["base-model", "other-model"],
                },
            }
        },
    )

    with pytest.raises(ConfigExtendsError, match="multiple parents"):
        ConfigLoader(package_config_dir=package_root).load_models()


def test_missing_extends_parent_fails_fast(tmp_path: Path) -> None:
    """继承父项不存在时必须抛出结构化继承错误。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "models.json",
        {"models": {"derived-model": {"extends": "missing-model"}}},
    )

    with pytest.raises(ConfigExtendsError, match="missing parent"):
        ConfigLoader(package_config_dir=package_root).load_models()


@pytest.mark.parametrize("extends_value", [123, True, {"parent": "base-model"}])
def test_invalid_extends_type_fails_fast(
    tmp_path: Path,
    extends_value: JsonValue,
) -> None:
    """extends 为非 string、非 null、非 list 类型时必须失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "models.json",
        {
            "models": {
                "base-model": _base_model_record(
                    endpoint="https://package.example/chat"
                ),
                "derived-model": {
                    "extends": extends_value,
                },
            }
        },
    )

    with pytest.raises(ConfigExtendsError, match="string or null"):
        ConfigLoader(package_config_dir=package_root).load_models()


def test_workspace_non_map_top_level_field_overrides_package_default(
    tmp_path: Path,
) -> None:
    """workspace 必须能覆盖 default_execution_profile_id 这类非 map 顶层字段。"""

    package_root = tmp_path / "package"
    workspace_root = tmp_path / "workspace"
    _minimal_package_config(package_root)
    workspace_profile = _execution_profile_record()
    workspace_profile["run_baseline"] = {
        "model_id": "derived-model",
        "runner_option_hint_id": "interactive",
    }
    _write_json(
        workspace_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "workspace-profile",
            "execution_profiles": {
                "workspace-profile": workspace_profile,
            },
        },
    )

    config = ConfigLoader(package_config_dir=package_root).load_execution_profiles(
        workspace_config_dir=workspace_root
    )

    assert config.default_execution_profile_id == "workspace-profile"
    assert (
        config.execution_profiles["workspace-profile"].run_baseline.model_id
        == "derived-model"
    )


def test_workspace_partial_record_does_not_deep_merge_and_fails(
    tmp_path: Path,
) -> None:
    """workspace partial record 不能与包内默认做 deep merge。"""

    package_root = tmp_path / "package"
    workspace_root = tmp_path / "workspace"
    _minimal_package_config(package_root)
    _write_json(
        workspace_root / "models.json",
        {
            "models": {
                "base-model": {
                    "headers": {"Authorization": "Bearer partial"},
                }
            }
        },
    )

    with pytest.raises(ConfigFieldError, match="missing required fields"):
        ConfigLoader(package_config_dir=package_root).load(
            workspace_config_dir=workspace_root
        )


def test_secret_and_provider_extension_values_are_preserved_raw(
    tmp_path: Path,
) -> None:
    """api_key_ref、headers 与 provider_request_extension 必须原样保留。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)

    config = ConfigLoader(package_config_dir=package_root).load()
    model = config.models.models["base-model"]

    assert model.api_key_ref == "RAW_API_KEY_REF"
    assert model.headers["Authorization"] == "Bearer ${RAW_API_KEY_REF}"
    assert model.headers["X-Raw"] == "{{NOT_EXPANDED}}"
    assert model.provider_request_extension == {
        "type": "custom",
        "nested": {"keep": ["as", "json"]},
    }


def test_legacy_files_do_not_exist_and_are_not_read(tmp_path: Path) -> None:
    """旧配置文件已删除，workspace 中存在旧文件也不得被读取。"""

    workspace_root = tmp_path / "workspace"
    _write_json(workspace_root / "llm_models.json", {"bad": ["legacy"]})
    (workspace_root / "run.json").write_text("{not valid json", encoding="utf-8")

    config = load_runtime_config(workspace_config_dir=workspace_root)

    assert isinstance(config, RuntimeConfig)
    for file_name in legacy_config_file_names():
        assert not (Path("dayu/config") / file_name).exists()


def test_embedded_catalog_id_fields_fail_fast(tmp_path: Path) -> None:
    """catalog record 内重复 id 字段必须 fail fast。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    bad_model = _base_model_record(endpoint="https://package.example/chat")
    bad_model["model_id"] = "base-model"
    _write_json(package_root / "models.json", {"models": {"base-model": bad_model}})

    with pytest.raises(ConfigFieldError, match="embedded id fields"):
        ConfigLoader(package_config_dir=package_root).load_models()


def test_old_execution_profile_fields_fail_fast(tmp_path: Path) -> None:
    """旧 runner_options_profiles / runner_hints / agent_hints schema 必须失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard",
            "execution_profiles": {
                "standard": _execution_profile_record(),
            },
            "agent_policy_profiles": {
                "default-agent": _agent_policy_profile_record(),
            },
            "runner_options_profiles": {},
            "runner_hints": {},
            "agent_hints": {},
        },
    )

    with pytest.raises(ConfigFieldError, match="unknown fields"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_agent_fallback_mode_is_closed_enum(tmp_path: Path) -> None:
    """fallback_mode 只允许 force_answer / raise_error。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    bad_agent = _agent_policy_profile_record()
    bad_agent["fallback_mode"] = "finalize"
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard",
            "execution_profiles": {"standard": _execution_profile_record()},
            "agent_policy_profiles": {"default-agent": bad_agent},
        },
    )

    with pytest.raises(ConfigFieldError, match="unsupported value"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_host_runtime_lane_reference_must_exist(tmp_path: Path) -> None:
    """host_runtime.host_execution_lane_name 必须引用 runtime_lanes 已有 lane。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "host_runtime.json",
        {
            "default_host_runtime_id": "local",
            "runtimes": {
                "local": {
                    "store_root": "workspace/.dayu/host",
                    "artifact_root": "workspace/.dayu/artifacts",
                    "sqlite": {
                        "path": "workspace/.dayu/host/dayu.sqlite3",
                        "busy_timeout_seconds": 5.0,
                        "write_busy_retry_count": 8,
                        "write_retry_initial_delay_seconds": 0.005,
                        "write_retry_backoff_multiplier": 1.5,
                        "write_retry_max_delay_seconds": 0.05,
                    },
                    "host_execution_lane_name": "missing_lane",
                    "worker_backend": "local",
                    "dispatch_poll_interval_seconds": 0.1,
                    "payload_inline_threshold_bytes": 4096,
                    "worker_startup_timeout_seconds": 10.0,
                    "memory_projection_catch_up_batch_size": 10,
                    "truncation_manager_enabled": True,
                }
            },
        },
    )

    with pytest.raises(ConfigFieldError, match="unknown id"):
        ConfigLoader(package_config_dir=package_root).load()


def test_runtime_lane_capacity_claim_ttl_must_exceed_heartbeat(
    tmp_path: Path,
) -> None:
    """lane claim_ttl_seconds 必须大于 heartbeat_interval_seconds。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "runtime_lanes.json",
        {
            "coordinator": {
                "db_path": "workspace/.dayu/runtime/lane.sqlite3",
                "busy_timeout_seconds": 5.0,
                "poll_interval_seconds": 0.05,
            },
            "lanes": {
                "llm_api": {
                    "capacity": 1,
                    "default_timeout_seconds": None,
                    "claim_ttl_seconds": 2.0,
                    "heartbeat_interval_seconds": 2.0,
                }
            },
        },
    )

    with pytest.raises(ConfigFieldError, match="greater than heartbeat"):
        ConfigLoader(package_config_dir=package_root).load_runtime_lanes()


def test_tool_discovery_entry_point_requires_import_path_xor_entry_point(
    tmp_path: Path,
) -> None:
    """工具发现 provider 必须 import_path 与 entry_point 二选一。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "tool_discovery.json",
        {
            "providers": {
                "bad": {
                    "import_path": "tests.fake_tools:provider",
                    "entry_point": {"group": "dayu.tools", "name": "bad"},
                    "source_kind": "explicit_provider",
                    "source_id": "bad",
                    "enabled": True,
                    "allow_empty": False,
                }
            }
        },
    )

    with pytest.raises(ConfigFieldError, match="exactly one"):
        ConfigLoader(package_config_dir=package_root).load_tool_discovery()


def test_json_shape_error_is_structured(tmp_path: Path) -> None:
    """JSON shape 错误必须暴露为结构化配置错误。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(package_root / "models.json", [])

    with pytest.raises(ConfigShapeError, match="JSON object"):
        ConfigLoader(package_config_dir=package_root).load_models()
