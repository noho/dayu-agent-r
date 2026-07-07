"""``dayu.runtime.config_loader`` 配置加载测试。"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Final

import pytest

from dayu.contracts import JsonValue, ToolBundleSourceKind
from dayu.runtime.config_loader import (
    ConfigExtendsError,
    ConfigFieldError,
    ConfigLoader,
    ConfigShapeError,
    RunnerOptionHintConfig,
    RuntimeConfig,
    config_file_names,
    default_fallback_prompt,
    legacy_config_file_names,
    load_runtime_config,
)

_EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION: Final[int] = 5


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
            "top_p": 0.9,
            "stream": True,
        },
        "conversation_compaction": {
            "temperature": 0.0,
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
        "context_window_class": "256k",
        "min_context_window_tokens": 262144,
        "run_baseline": {
            "model_id": "base-model",
            "runner_option_hint_id": "interactive",
        },
        "compactor_baseline": {
            "model_id": "base-model",
            "scene_id": "conversation_compaction",
            "runner_option_hint_id": "conversation_compaction",
            "user_prompt_template_path": "scenes/conversation_compaction_user.md",
            "artifact_root": "artifacts/compact",
        },
        "context_budget_policy": {
            "soft_threshold_context_ratio": 0.6,
            "hard_threshold_context_ratio": 0.8,
            "max_proactive_compactions_per_run": 1,
            "max_reactive_compactions_per_run": 1,
            "max_compaction_attempts_per_operation": 2,
            "policy_ref": "test",
        },
        "memory_projection_policy": {
            "context_window_size": 262144,
            "selected_recent_window_item_cap": 8,
            "selected_recent_window_char_cap": 100,
            "selected_recent_window_turn_floor": 1,
            "fallback_selected_recent_window_item_cap": 4,
            "fallback_selected_recent_window_char_cap": 50,
            "evidence_fact_item_cap": 3,
            "evidence_fact_char_cap": 300,
            "evidence_fact_floor": 1,
            "session_summary_char_cap": 400,
            "answer_anchor_item_cap": 5,
            "answer_anchor_char_cap": 500,
            "forward_intent_item_cap": 6,
            "forward_intent_char_cap": 600,
            "reference_continuity_item_cap": 7,
            "reference_continuity_char_cap": 700,
            "reference_continuity_item_floor": 0,
            "max_lag_events_for_inline_delta": 5,
            "max_delta_repair_events": 6,
            "policy_ref": "test-memory",
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
        "tool_duplicate_governance_policy": _tool_duplicate_governance_policy_record(),
        "agent_policy": _agent_policy_record(),
    }


def _tool_duplicate_governance_policy_record() -> dict[str, JsonValue]:
    """构造完整工具重复调用治理 policy fixture。

    :returns: 工具重复调用治理 policy JSON object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "default_duplicate_decision": "hint",
        "decisions_by_tool_name": {},
        "justification_argument_names_by_tool_name": {},
        "messages": {
            "allow": "本次重复工具调用已允许执行。",
            "reuse": "请直接使用上一次工具结果继续推理，不要重复请求相同证据。",
            "hint": (
                "请优先使用上一次工具结果继续推理；只有当需要不同主体、期间、"
                "指标或证据范围时，才重新调用工具并修改参数。"
            ),
            "require_justification": (
                "重复调用同一工具前，必须在参数中说明为什么上一次工具结果不足，"
                "以及本次需要补充的不同证据范围。"
            ),
            "hard_stop": "本次重复工具调用已被拒绝。请使用上一次工具结果继续推理；如果信息不足，请说明不确定性，不要编造。",
            "attempt_scope_diagnostic": (
                "检测到当前推理步骤中重复请求相同工具证据。"
            ),
            "prior_accept_missing": "上一次相同工具请求没有产生可用结果。请说明信息不足，或在改变证据范围后再调用工具。",
        },
    }


def _agent_policy_record() -> dict[str, JsonValue]:
    """构造完整 Agent policy fixture。

    :returns: Agent policy JSON object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "max_iterations": 3,
        "continuation_max_attempts": 1,
        "allow_tool_calls": True,
        "tool_execution_timeout_seconds": 30.0,
        "fallback_mode": "force_answer",
        "fallback_prompt": default_fallback_prompt(),
        "continuation_prompt": "continue",
        "max_consecutive_failed_tool_batches": 2,
    }


def _host_runtime_config_record(
    *,
    include_process_capsule_interrupt_policy: bool = False,
    process_capsule_interrupt_policy: JsonValue = None,
) -> dict[str, JsonValue]:
    """构造完整 host_runtime.json fixture。

    :param include_process_capsule_interrupt_policy: 是否写入 process capsule
        cleanup interrupt policy block。
    :param process_capsule_interrupt_policy: 可选 process capsule cleanup
        interrupt policy JSON 值。
    :returns: host_runtime.json 顶层 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    runtime_record: dict[str, JsonValue] = {
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
    }
    if include_process_capsule_interrupt_policy:
        runtime_record["process_capsule_interrupt_policy"] = (
            process_capsule_interrupt_policy
        )
    return {
        "default_host_runtime_id": "local",
        "runtimes": {
            "local": runtime_record,
        },
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
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {
                "standard-256k": _execution_profile_record(),
            },
        },
    )
    _write_json(
        root / "host_runtime.json",
        _host_runtime_config_record(),
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
                    "config": {
                        "nested": {"keep": ["provider", "json"]},
                        "enabled_flag": True,
                    },
                }
            }
        },
    )


def test_default_runtime_config_files_load_as_typed_views() -> None:
    """五个包内默认新配置文件必须都能加载成 typed view。"""

    config = load_runtime_config()

    assert "runtime_lanes.json" in config_file_names()
    assert config.models.models["deepseek-v4-flash"].model_id == "deepseek-v4-flash"
    assert "max_tokens" not in {field.name for field in fields(RunnerOptionHintConfig)}
    assert config.execution_profiles.default_execution_profile_id == "standard-256k"
    profile_ids = set(config.execution_profiles.execution_profiles)
    assert {
        "standard-256k",
        "standard-1m",
        "wechat-256k",
        "wechat-1m",
    }.issubset(profile_ids)
    standard_256k = config.execution_profiles.execution_profiles["standard-256k"]
    assert standard_256k.context_window_class == "256k"
    assert standard_256k.min_context_window_tokens == 262144
    assert standard_256k.compactor_baseline.scene_id == "conversation_compaction"
    assert (
        standard_256k.context_budget_policy.max_compaction_attempts_per_operation
        == _EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION
    )
    assert standard_256k.compactor_baseline.user_prompt_template_path == (
        "scenes/conversation_compaction_user.md"
    )
    assert standard_256k.memory_projection_policy.evidence_fact_item_cap == 256
    assert (
        standard_256k.tool_duplicate_governance_policy.default_duplicate_decision
        == "hint"
    )
    assert (
        standard_256k.tool_duplicate_governance_policy.messages.hint
        == "请优先使用上一次工具结果继续推理；只有当需要不同主体、期间、指标或证据范围时，才重新调用工具并修改参数。"
    )
    assert standard_256k.agent_policy.max_iterations == 24
    assert standard_256k.agent_policy.fallback_prompt == default_fallback_prompt()
    assert (
        standard_256k.compactor_baseline.artifact_root
        == ".dayu/artifacts/compaction"
    )
    assert (
        config.execution_profiles.execution_profiles["standard-1m"]
        .min_context_window_tokens
        == 1000000
    )
    for profile in config.execution_profiles.execution_profiles.values():
        assert profile.agent_policy.continuation_prompt
        assert profile.agent_policy.max_consecutive_failed_tool_batches == 2
        assert (
            profile.context_budget_policy.max_compaction_attempts_per_operation
            == _EXPECTED_COMPACTION_ATTEMPTS_PER_OPERATION
        )
    assert config.host_runtime.default_host_runtime_id == "local"
    host_runtime = config.host_runtime.runtimes["local"]
    assert host_runtime.sqlite.write_busy_retry_count == 8
    assert host_runtime.sqlite.write_retry_initial_delay_seconds == 0.005
    assert host_runtime.store_root == ".dayu/host"
    assert host_runtime.artifact_root == ".dayu/artifacts"
    assert host_runtime.sqlite.path == ".dayu/host/dayu_host.sqlite3"
    assert host_runtime.payload_inline_threshold_bytes == 65535
    assert host_runtime.worker_startup_timeout_seconds == 10.0
    assert host_runtime.process_capsule_interrupt_policy is None
    assert (
        config.runtime_lanes.coordinator.db_path
        == ".dayu/runtime/runtime_lanes.sqlite3"
    )
    assert config.runtime_lanes.lanes["llm_api"].capacity == 4
    read_provider = config.tool_discovery.providers["financial-read-tools"]
    download_provider = config.tool_discovery.providers["financial-download-tools"]
    preprocess_provider = config.tool_discovery.providers["financial-preprocess-tools"]
    upload_provider = config.tool_discovery.providers["financial-upload-tools"]
    assert read_provider.source_kind == ToolBundleSourceKind.EXPLICIT_PROVIDER
    assert read_provider.import_path == "dayu.fins.tools.provider:discover_tools"
    assert read_provider.enabled is True
    assert "workspace_root" not in read_provider.config
    assert "include_ingestion_tools" not in read_provider.config
    assert read_provider.config["limits"] == {
        "processor_cache_max_entries": 128,
        "list_documents_max_items": 300,
        "get_document_sections_max_items": 1200,
        "search_document_max_items": 20,
        "list_tables_max_items": 50,
        "read_section_max_chars": 80000,
        "get_page_content_max_chars": 80000,
        "get_table_max_items": 800,
        "get_financial_statement_max_items": 1200,
        "query_xbrl_facts_max_items": 1200,
    }
    assert download_provider.import_path == (
        "dayu.fins.tools.download_provider:discover_tools"
    )
    assert download_provider.enabled is True
    assert "workspace_root" not in download_provider.config
    assert preprocess_provider.import_path == (
        "dayu.fins.tools.preprocess_provider:discover_tools"
    )
    assert preprocess_provider.enabled is True
    assert "workspace_root" not in preprocess_provider.config
    assert upload_provider.enabled is True
    assert "workspace_root" not in upload_provider.config
    assert "allowed_upload_roots" not in upload_provider.config
    doc_provider = config.tool_discovery.providers["doc-tools"]
    assert doc_provider.enabled is False
    assert doc_provider.config["limits"] == {
        "list_files_max": 200,
        "get_sections_max": 200,
        "search_files_max_results": 50,
        "read_file_max_chars": 80000,
        "read_file_section_max_chars": 50000,
    }
    web_provider = config.tool_discovery.providers["web-tools"]
    assert web_provider.enabled is True
    assert web_provider.config["provider"] == "auto"
    assert web_provider.config["request_timeout_seconds"] == 20.0
    assert web_provider.config["max_search_results"] == 8
    assert web_provider.config["fetch_truncate_chars"] == 80000
    assert web_provider.config["playwright_channel"] == "chrome"
    assert (
        web_provider.config["playwright_storage_state_dir"]
        == "workspace/.dayu/web_tools_storage_states"
    )
    assert web_provider.config["allow_private_network_url"] is False
    utils_provider = config.tool_discovery.providers["utils-tools"]
    assert utils_provider.enabled is True
    assert utils_provider.import_path == "dayu.tools.utils:discover_tools"
    assert utils_provider.source_kind == ToolBundleSourceKind.EXPLICIT_PROVIDER
    assert utils_provider.config == {}


def test_host_runtime_process_capsule_policy_missing_block_is_valid(
    tmp_path: Path,
) -> None:
    """host_runtime 缺省 process capsule policy block 时 typed config 为 None。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)

    config = ConfigLoader(package_config_dir=package_root).load_host_runtime()

    assert (
        config.runtimes["local"].process_capsule_interrupt_policy is None
    )


def test_host_runtime_process_capsule_policy_valid_block_parses(
    tmp_path: Path,
) -> None:
    """host_runtime process capsule cleanup policy 显式配置必须被解析。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "host_runtime.json",
        _host_runtime_config_record(
            include_process_capsule_interrupt_policy=True,
            process_capsule_interrupt_policy={
                "terminate_grace_seconds": 0.35,
                "kill_grace_seconds": 0.75,
            },
        ),
    )

    config = ConfigLoader(package_config_dir=package_root).load_host_runtime()
    policy = config.runtimes["local"].process_capsule_interrupt_policy

    assert policy is not None
    assert policy.terminate_grace_seconds == 0.35
    assert policy.kill_grace_seconds == 0.75


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("terminate_grace_seconds", True),
        ("terminate_grace_seconds", -0.1),
        ("terminate_grace_seconds", float("nan")),
        ("terminate_grace_seconds", float("inf")),
        ("terminate_grace_seconds", float("-inf")),
        ("kill_grace_seconds", True),
        ("kill_grace_seconds", -0.1),
        ("kill_grace_seconds", float("nan")),
        ("kill_grace_seconds", float("inf")),
        ("kill_grace_seconds", float("-inf")),
    ),
)
def test_host_runtime_process_capsule_policy_invalid_grace_fails_fast(
    tmp_path: Path,
    field_name: str,
    value: JsonValue,
) -> None:
    """host_runtime process capsule cleanup grace 拒绝 bool、负数、NaN 与无穷。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    policy: dict[str, JsonValue] = {
        "terminate_grace_seconds": 0.35,
        "kill_grace_seconds": 0.75,
    }
    policy[field_name] = value
    _write_json(
        package_root / "host_runtime.json",
        _host_runtime_config_record(
            include_process_capsule_interrupt_policy=True,
            process_capsule_interrupt_policy=policy,
        ),
    )

    with pytest.raises(ConfigFieldError, match=field_name):
        ConfigLoader(package_config_dir=package_root).load_host_runtime()


def test_host_runtime_process_capsule_policy_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    """host_runtime process capsule cleanup policy block 拒绝未知字段。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "host_runtime.json",
        _host_runtime_config_record(
            include_process_capsule_interrupt_policy=True,
            process_capsule_interrupt_policy={
                "terminate_grace_seconds": 0.35,
                "kill_grace_seconds": 0.75,
                "cleanup_deadline_seconds": 2.0,
            },
        ),
    )

    with pytest.raises(
        ConfigFieldError,
        match=(
            "host_runtime.runtimes.local.process_capsule_interrupt_policy "
            "has unknown fields"
        ),
    ):
        ConfigLoader(package_config_dir=package_root).load_host_runtime()


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
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {
                "standard-256k": _execution_profile_record(),
            },
            "runner_options_profiles": {},
            "runner_hints": {},
            "agent_hints": {},
        },
    )

    with pytest.raises(ConfigFieldError, match="unknown fields"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_old_memory_projection_policy_key_fails_fast(tmp_path: Path) -> None:
    """旧 memory projection policy key 必须作为未知字段失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    memory_projection = profile["memory_projection_policy"]
    assert isinstance(memory_projection, dict)
    memory_projection["max_evidence_backed_facts"] = 3
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="max_evidence_backed_facts"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_old_runner_hint_max_tokens_fails_fast(tmp_path: Path) -> None:
    """旧 runner option hint max_tokens 字段必须作为未知字段失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    model = _base_model_record(endpoint="https://package.example/chat")
    runtime_hints = model["runtime_hints"]
    assert isinstance(runtime_hints, dict)
    runner_option_hints = runtime_hints["runner_option_hints"]
    assert isinstance(runner_option_hints, dict)
    interactive = runner_option_hints["interactive"]
    assert isinstance(interactive, dict)
    interactive["max_tokens"] = 100
    _write_json(package_root / "models.json", {"models": {"base-model": model}})

    with pytest.raises(ConfigFieldError, match="unknown fields"):
        ConfigLoader(package_config_dir=package_root).load_models()


def test_old_agent_policy_profile_id_fails_fast(tmp_path: Path) -> None:
    """旧 execution profile agent_policy_profile_id 字段必须失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    profile["agent_policy_profile_id"] = "default-agent"
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="unknown fields"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_execution_profile_context_window_class_is_closed_enum(
    tmp_path: Path,
) -> None:
    """execution profile context_window_class 只允许 256k / 1m。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    profile["context_window_class"] = "512k"
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="unsupported value"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


@pytest.mark.parametrize("min_tokens", [0, -1])
def test_execution_profile_min_context_window_tokens_must_be_positive(
    tmp_path: Path,
    min_tokens: int,
) -> None:
    """execution profile min_context_window_tokens 必须是正整数。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    profile["min_context_window_tokens"] = min_tokens
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="must be > 0"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


@pytest.mark.parametrize(
    ("context_window_class", "min_tokens"),
    [("1m", 262144), ("256k", 1000000)],
)
def test_execution_profile_context_window_pair_must_be_consistent(
    tmp_path: Path,
    context_window_class: str,
    min_tokens: int,
) -> None:
    """上下文窗口分档与最小 token 数必须同源一致。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    profile["context_window_class"] = context_window_class
    profile["min_context_window_tokens"] = min_tokens
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="min_context_window_tokens must be"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_execution_profile_must_not_embed_context_window_size(
    tmp_path: Path,
) -> None:
    """execution profile 不得重复配置模型上下文窗口。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    context_budget = profile["context_budget_policy"]
    assert isinstance(context_budget, dict)
    context_budget["context_window_size"] = 1000
    memory_projection = profile["memory_projection_policy"]
    assert isinstance(memory_projection, dict)
    memory_projection["context_window_size"] = 1000
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {
                "standard-256k": profile,
            },
        },
    )

    with pytest.raises(ConfigFieldError, match="unknown fields"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_compactor_baseline_requires_scene_id(tmp_path: Path) -> None:
    """compactor_baseline 必须显式声明 compactor scene id。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 缺少 scene_id 未失败时抛出。
    """

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    compactor_baseline = profile["compactor_baseline"]
    assert isinstance(compactor_baseline, dict)
    compactor_baseline.pop("scene_id")
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="scene_id"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_compactor_baseline_requires_user_prompt_template_path(
    tmp_path: Path,
) -> None:
    """compactor_baseline 必须显式声明 user prompt template 路径。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 缺少 user_prompt_template_path 未失败时抛出。
    """

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    compactor_baseline = profile["compactor_baseline"]
    assert isinstance(compactor_baseline, dict)
    compactor_baseline.pop("user_prompt_template_path")
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="user_prompt_template_path"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_old_agent_policy_profiles_catalog_fails_fast(tmp_path: Path) -> None:
    """旧顶层 agent_policy_profiles catalog 必须 fail fast。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {
                "standard-256k": _execution_profile_record(),
            },
            "agent_policy_profiles": {
                "default-agent": _agent_policy_record(),
            },
        },
    )

    with pytest.raises(
        ConfigFieldError,
        match="unknown fields",
    ):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_agent_policy_missing_field_fails_fast(tmp_path: Path) -> None:
    """内嵌 agent_policy 缺少必填字段必须失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    agent_policy = profile["agent_policy"]
    assert isinstance(agent_policy, dict)
    agent_policy.pop("continuation_prompt")
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="missing required fields"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_tool_duplicate_governance_unknown_decision_fails_fast(tmp_path: Path) -> None:
    """工具重复治理 policy 不接受未知 duplicate decision。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 未在配置加载期 fail-fast 时抛出。
    """

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    duplicate_policy = profile["tool_duplicate_governance_policy"]
    assert isinstance(duplicate_policy, dict)
    duplicate_policy["default_duplicate_decision"] = "retry"
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="unsupported value"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_agent_policy_field_type_fails_fast(tmp_path: Path) -> None:
    """内嵌 agent_policy 字段类型非法必须失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    agent_policy = profile["agent_policy"]
    assert isinstance(agent_policy, dict)
    agent_policy["allow_tool_calls"] = "yes"
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
        },
    )

    with pytest.raises(ConfigFieldError, match="must be a boolean"):
        ConfigLoader(package_config_dir=package_root).load_execution_profiles()


def test_host_runtime_catalog_must_not_be_empty(tmp_path: Path) -> None:
    """host_runtime.runtimes 为空必须在配置加载期失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "host_runtime.json",
        {
            "default_host_runtime_id": "local",
            "runtimes": {},
        },
    )

    with pytest.raises(ConfigFieldError, match="runtimes must not be empty"):
        ConfigLoader(package_config_dir=package_root).load_host_runtime()


def test_runtime_lanes_catalog_must_not_be_empty(tmp_path: Path) -> None:
    """runtime_lanes.lanes 为空必须在配置加载期失败。"""

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
            "lanes": {},
        },
    )

    with pytest.raises(ConfigFieldError, match="lanes must not be empty"):
        ConfigLoader(package_config_dir=package_root).load_runtime_lanes()


def test_tool_discovery_providers_must_not_be_empty(tmp_path: Path) -> None:
    """tool_discovery.providers 为空必须在配置加载期失败。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "tool_discovery.json",
        {
            "providers": {},
        },
    )

    with pytest.raises(ConfigFieldError, match="providers must not be empty"):
        ConfigLoader(package_config_dir=package_root).load_tool_discovery()


def test_tool_discovery_provider_config_must_be_json_object(tmp_path: Path) -> None:
    """provider config 只能是层中立 JSON object。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 非 object config 未 fail fast 时抛出。
    """

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "tool_discovery.json",
        {
            "providers": {
                "bad": {
                    "import_path": "tests.fake_tools:provider",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "bad",
                    "enabled": True,
                    "config": ["not", "object"],
                }
            }
        },
    )

    with pytest.raises(ConfigShapeError, match="config must be a JSON object"):
        ConfigLoader(package_config_dir=package_root).load_tool_discovery()


def test_tool_discovery_provider_allow_empty_is_rejected(tmp_path: Path) -> None:
    """旧版 provider-level allow_empty 字段必须作为未知字段拒绝。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    _write_json(
        package_root / "tool_discovery.json",
        {
            "providers": {
                "old": {
                    "import_path": "tests.fake_tools:provider",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "old",
                    "enabled": True,
                    "allow_empty": False,
                    "config": {},
                }
            }
        },
    )

    with pytest.raises(ConfigFieldError, match="unknown fields"):
        ConfigLoader(package_config_dir=package_root).load_tool_discovery()


def test_agent_fallback_mode_is_closed_enum(tmp_path: Path) -> None:
    """fallback_mode 只允许 force_answer / raise_error。"""

    package_root = tmp_path / "package"
    _minimal_package_config(package_root)
    profile = _execution_profile_record()
    bad_agent = profile["agent_policy"]
    assert isinstance(bad_agent, dict)
    bad_agent["fallback_mode"] = "finalize"
    _write_json(
        package_root / "execution_profiles.json",
        {
            "default_execution_profile_id": "standard-256k",
            "execution_profiles": {"standard-256k": profile},
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
