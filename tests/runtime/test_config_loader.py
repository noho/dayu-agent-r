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


def _base_model_record(model_id: str, *, endpoint: str) -> dict[str, JsonValue]:
    """构造完整模型配置记录。

    :param model_id: 模型 id。
    :param endpoint: endpoint URL。
    :returns: 模型配置 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "extends": None,
        "model_id": model_id,
        "runner_kind": "openai_compatible",
        "provider": "test-provider",
        "model": model_id,
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
                    "base-model",
                    endpoint="https://package.example/chat",
                ),
                "derived-model": {
                    "extends": "base-model",
                    "model_id": "derived-model",
                    "model": "derived-model",
                    "endpoint": "https://derived.example/chat",
                },
            }
        },
    )
    _write_json(
        root / "execution_profiles.json",
        {
            "default_profile_id": "ordinary",
            "profiles": {
                "ordinary": {
                    "extends": None,
                    "profile_id": "ordinary",
                    "ordinary": {
                        "model_id": "base-model",
                        "runner_options_profile_id": "analytical",
                        "agent_policy_profile_id": "default-agent",
                    },
                    "compactor": {
                        "model_id": "base-model",
                        "runner_options_profile_id": "compact",
                        "artifact_root": "artifacts/compact",
                    },
                    "context_budget": {
                        "max_context_tokens": 1000,
                        "reserved_response_tokens": 100,
                        "compaction_trigger_tokens": 800,
                    },
                    "memory_projection": {
                        "enabled": True,
                        "stable_layer_max_items": 10,
                        "history_pool_max_items": 20,
                    },
                    "truncation": {
                        "enabled": True,
                        "default_max_chars": 100,
                        "fetch_more_tool_name": "fetch_more",
                    },
                }
            },
            "runner_options_profiles": {
                "analytical": {
                    "extends": None,
                    "temperature": 0.2,
                    "max_tokens": 100,
                    "top_p": 0.9,
                    "stream": True,
                },
                "compact": {
                    "extends": "analytical",
                    "temperature": 0.0,
                    "stream": False,
                },
            },
            "agent_policy_profiles": {
                "default-agent": {
                    "extends": None,
                    "max_iterations": 3,
                    "continuation_attempts": 1,
                    "tool_execution_timeout_seconds": 30.0,
                    "fallback_mode": "finalize",
                    "fallback_prompt": "fallback",
                    "continuation_prompt": "continue",
                    "consecutive_failed_tool_batches": 2,
                }
            },
            "runner_hints": {
                "fast": {
                    "extends": None,
                    "model_id": "derived-model",
                    "max_tokens": 50,
                }
            },
            "agent_hints": {
                "strict": {
                    "extends": None,
                    "agent_policy_profile_id": "default-agent",
                    "max_iterations": 2,
                }
            },
        },
    )
    _write_json(
        root / "host_runtime.json",
        {
            "default_runtime_id": "local",
            "runtimes": {
                "local": {
                    "extends": None,
                    "runtime_id": "local",
                    "store_root": "workspace/.dayu/host",
                    "artifact_root": "workspace/.dayu/artifacts",
                    "sqlite": {
                        "path": "workspace/.dayu/host/dayu.sqlite3",
                        "busy_timeout_seconds": 5.0,
                    },
                    "lane": {
                        "db_path": "workspace/.dayu/runtime/lane.sqlite3",
                        "default_lane_name": "llm_api",
                        "lanes": {
                            "llm_api": {
                                "capacity": 1,
                                "claim_ttl_seconds": 10.0,
                                "heartbeat_interval_seconds": 2.0,
                            }
                        },
                    },
                    "worker_factory_kind": "local",
                    "dispatch_poll_interval_seconds": 0.1,
                    "memory_projection_catch_up_batch_size": 10,
                    "truncation_manager_enabled": True,
                    "prompt_asset_root": "workspace/config/prompts",
                    "scene_manifest_root": "workspace/config/prompts/manifests",
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
                    "provider_id": "tools",
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
    """四个包内默认新配置文件必须都能加载成 typed view。"""

    config = load_runtime_config()

    assert config.models.models["deepseek-chat"].model_id == "deepseek-chat"
    assert config.execution_profiles.default_profile_id == "ordinary"
    assert config.host_runtime.default_runtime_id == "local"
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
    replacement = _base_model_record(
        "base-model",
        endpoint="https://workspace.example/chat",
    )
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


def test_single_extends_resolves_to_complete_typed_record(tmp_path: Path) -> None:
    """单继承记录必须解析为完整 typed record。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)

    config = ConfigLoader(package_config_dir=package_root).load()

    derived = config.models.models["derived-model"]
    assert derived.provider == "test-provider"
    assert derived.endpoint == "https://derived.example/chat"
    compact = config.execution_profiles.runner_options_profiles["compact"]
    assert compact.max_tokens == 100
    assert compact.stream is False


def test_extends_cycle_fails_fast(tmp_path: Path) -> None:
    """循环继承必须在 ConfigLoader 层 fail fast。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "models.json",
        {
            "models": {
                "a": {"extends": "b", "model_id": "a"},
                "b": {"extends": "a", "model_id": "b"},
            }
        },
    )

    with pytest.raises(ConfigExtendsError, match="cycle"):
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
                    "base-model",
                    endpoint="https://package.example/chat",
                ),
                "derived-model": {
                    "extends": ["base-model", "other-model"],
                    "model_id": "derived-model",
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
        {
            "models": {
                "derived-model": {
                    "extends": "missing-model",
                    "model_id": "derived-model",
                },
            }
        },
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
                    "base-model",
                    endpoint="https://package.example/chat",
                ),
                "derived-model": {
                    "extends": extends_value,
                    "model_id": "derived-model",
                },
            }
        },
    )

    with pytest.raises(ConfigExtendsError, match="string or null"):
        ConfigLoader(package_config_dir=package_root).load_models()


def test_workspace_non_map_top_level_field_overrides_package_default(
    tmp_path: Path,
) -> None:
    """workspace 必须能覆盖 default_profile_id 这类非 map 顶层字段。"""

    package_root = tmp_path / "package"
    workspace_root = tmp_path / "workspace"
    _minimal_package_config(package_root)
    _write_json(
        workspace_root / "execution_profiles.json",
        {
            "default_profile_id": "workspace-profile",
            "profiles": {
                "workspace-profile": {
                    "extends": "ordinary",
                    "profile_id": "workspace-profile",
                }
            },
        },
    )

    config = ConfigLoader(package_config_dir=package_root).load_execution_profiles(
        workspace_config_dir=workspace_root
    )

    assert config.default_profile_id == "workspace-profile"
    assert config.profiles["workspace-profile"].ordinary.model_id == "base-model"


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
                    "model_id": "base-model",
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
                    "extends": None,
                    "provider_id": "bad",
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


def test_lane_capacity_claim_ttl_must_exceed_heartbeat(tmp_path: Path) -> None:
    """lane claim_ttl_seconds 必须大于 heartbeat_interval_seconds。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "host_runtime.json",
        {
            "default_runtime_id": "local",
            "runtimes": {
                "local": {
                    "extends": None,
                    "runtime_id": "local",
                    "store_root": "workspace/.dayu/host",
                    "artifact_root": "workspace/.dayu/artifacts",
                    "sqlite": {
                        "path": "workspace/.dayu/host/dayu.sqlite3",
                        "busy_timeout_seconds": 5.0,
                    },
                    "lane": {
                        "db_path": "workspace/.dayu/runtime/lane.sqlite3",
                        "default_lane_name": "llm_api",
                        "lanes": {
                            "llm_api": {
                                "capacity": 1,
                                "claim_ttl_seconds": 2.0,
                                "heartbeat_interval_seconds": 2.0,
                            }
                        },
                    },
                    "worker_factory_kind": "local",
                    "dispatch_poll_interval_seconds": 0.1,
                    "memory_projection_catch_up_batch_size": 10,
                    "truncation_manager_enabled": True,
                    "prompt_asset_root": "workspace/config/prompts",
                    "scene_manifest_root": "workspace/config/prompts/manifests",
                }
            },
        },
    )

    with pytest.raises(ConfigFieldError, match="greater than heartbeat"):
        ConfigLoader(package_config_dir=package_root).load_host_runtime()


def test_json_shape_error_is_structured(tmp_path: Path) -> None:
    """JSON shape 错误必须暴露为结构化配置错误。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(package_root / "models.json", [])

    with pytest.raises(ConfigShapeError, match="JSON object"):
        ConfigLoader(package_config_dir=package_root).load_models()
