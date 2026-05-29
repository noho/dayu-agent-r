"""runtime-neutral assembly helper 测试。"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import fields
from typing import cast

import pytest

from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
from dayu.runtime.assembly import (
    AgentPolicyDefaults,
    AgentPolicyOverrideConfig,
    RuntimeAssemblyFieldError,
    RuntimeAssemblySelectionError,
    effective_tool_truncate_spec_from_policy,
    merge_agent_policy_config,
    parse_agent_policy_override_config,
    parse_model_runner_hint_override,
    select_runner_option_hint,
    tool_truncation_policy_defaults,
    validate_execution_profile_context_window,
)
from dayu.runtime.config_loader import ExecutionBaselineConfig, load_runtime_config
from dayu.runtime.scene_prepare import (
    SceneAgentFallbackMode,
    SceneAgentPolicyOverride,
    SceneModelHints,
)


def _agent_policy_defaults() -> AgentPolicyDefaults:
    """返回测试用完整代码默认 Agent policy。

    :returns: 代码默认 Agent policy 字段。
    """

    return AgentPolicyDefaults(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=True,
        tool_execution_timeout_seconds=30.0,
        fallback_mode="force_answer",
        fallback_prompt="default fallback",
        continuation_prompt="default continuation",
        max_consecutive_failed_tool_batches=1,
    )


def test_select_runner_option_hint_uses_field_level_precedence() -> None:
    """模型与 runner option hint selection 按字段应用四层优先级。"""

    config = load_runtime_config()
    baseline = (
        config.execution_profiles.execution_profiles["standard-256k"].run_baseline
    )
    override = parse_model_runner_hint_override(
        {"runner_option_hint_id": "audit"},
        source_name="run_override",
    )
    scene_hints = SceneModelHints(
        default_model_id="qwen-plus",
        runner_option_hint_id="write",
    )

    selection = select_runner_option_hint(
        models=config.models,
        execution_baseline=baseline,
        scene_model_hints=scene_hints,
        run_override=override,
        code_default=ExecutionBaselineConfig(
            model_id="deepseek-v4-flash",
            runner_option_hint_id="interactive",
        ),
    )

    assert selection.model_id == "qwen-plus"
    assert selection.runner_option_hint_id == "audit"
    assert selection.runner_option_hint.temperature == 0.2
    assert selection.diagnostic.selected_model_source == "scene_override"
    assert selection.diagnostic.selected_runner_option_hint_source == "run_override"


def test_select_runner_option_hint_fails_fast_for_missing_model_or_hint() -> None:
    """缺失模型或缺失 hint 必须结构化 fail fast。"""

    config = load_runtime_config()
    with pytest.raises(RuntimeAssemblySelectionError, match="model not found"):
        select_runner_option_hint(
            models=config.models,
            execution_baseline=None,
            scene_model_hints=None,
            run_override=parse_model_runner_hint_override(
                {"model_id": "missing", "runner_option_hint_id": "interactive"},
                source_name="run_override",
            ),
            code_default=None,
        )

    with pytest.raises(RuntimeAssemblySelectionError, match="runner option hint"):
        select_runner_option_hint(
            models=config.models,
            execution_baseline=None,
            scene_model_hints=None,
            run_override=parse_model_runner_hint_override(
                {
                    "model_id": "deepseek-v4-flash",
                    "runner_option_hint_id": "missing",
                },
                source_name="run_override",
            ),
            code_default=None,
        )


def test_parse_overrides_fail_fast_for_unknown_fields() -> None:
    """runtime helper 的 override parser 只接受白名单字段。"""

    with pytest.raises(RuntimeAssemblyFieldError, match="unknown fields"):
        parse_model_runner_hint_override(
            {"model_id": "deepseek-v4-flash", "provider": "deepseek"},
            source_name="run_override",
        )

    with pytest.raises(RuntimeAssemblyFieldError, match="unknown fields"):
        parse_agent_policy_override_config(
            {"allow_tool_calls": False, "runner_options": "bad"},
            source_name="run_override",
        )


def test_parse_agent_policy_override_accepts_scene_fallback_enum_values() -> None:
    """runtime fallback_mode 白名单必须与 scene typed enum 保持同源。"""

    for fallback_mode in SceneAgentFallbackMode:
        override = parse_agent_policy_override_config(
            {"fallback_mode": fallback_mode.value},
            source_name="run_override",
        )

        assert override.fallback_mode == fallback_mode.value


def test_merge_agent_policy_config_uses_typed_allowlist_precedence() -> None:
    """Agent policy 合并遵守 run > scene > profile > default 优先级。"""

    config = load_runtime_config()
    profile = (
        config.execution_profiles.execution_profiles["standard-256k"].agent_policy
    )
    run_override = parse_agent_policy_override_config(
        {
            "allow_tool_calls": False,
            "fallback_prompt": "run fallback",
        },
        source_name="run_override",
    )
    scene_override = SceneAgentPolicyOverride(
        max_iterations=7,
        fallback_mode=SceneAgentFallbackMode.RAISE_ERROR,
    )

    merged = merge_agent_policy_config(
        code_default=_agent_policy_defaults(),
        execution_profile=profile,
        scene_override=scene_override,
        run_override=run_override,
    )

    assert merged.max_iterations == 7
    assert merged.continuation_max_attempts == profile.continuation_max_attempts
    assert merged.allow_tool_calls is False
    assert merged.fallback_mode == "raise_error"
    assert merged.fallback_prompt == "run fallback"
    assert merged.continuation_prompt == profile.continuation_prompt
    assert merged.field_sources["max_iterations"] == "scene_override"
    assert merged.field_sources["allow_tool_calls"] == "run_override"
    assert merged.field_sources["continuation_prompt"] == "execution_profile"


def test_merge_agent_policy_config_revalidates_selected_fallback_mode() -> None:
    """直接构造 typed override 绕过解析器时，最终 fallback_mode 仍需校验。"""

    with pytest.raises(RuntimeAssemblyFieldError, match="unsupported value"):
        merge_agent_policy_config(
            code_default=_agent_policy_defaults(),
            execution_profile=None,
            scene_override=None,
            run_override=AgentPolicyOverrideConfig(fallback_mode="finalize"),
        )


def test_merge_agent_policy_config_field_sources_is_runtime_immutable() -> None:
    """合并诊断来源不得通过返回对象被调用方原地修改。"""

    config = load_runtime_config()
    profile = (
        config.execution_profiles.execution_profiles["standard-256k"].agent_policy
    )

    merged = merge_agent_policy_config(
        code_default=_agent_policy_defaults(),
        execution_profile=profile,
        scene_override=None,
        run_override=None,
    )

    with pytest.raises(TypeError):
        cast(MutableMapping[str, str], merged.field_sources)["max_iterations"] = (
            "mutated"
        )


def test_tool_truncation_policy_defaults_fill_declaration_without_target_drift() -> None:
    """截断 policy 默认值只补齐 limit / TTL，不改 declaration strategy / target。"""

    config = load_runtime_config()
    policy = (
        config.execution_profiles.execution_profiles["standard-256k"]
        .tool_truncation_policy
    )
    declaration = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={},
        target_field="content",
        field_path=None,
        ttl_seconds=None,
    )

    defaults = tool_truncation_policy_defaults(policy)
    effective = effective_tool_truncate_spec_from_policy(
        declaration,
        policy=policy,
    )

    assert defaults.enabled is True
    assert defaults.default_ttl_seconds == 3600
    assert effective.strategy is ToolTruncationStrategy.TEXT_CHARS
    assert effective.target_field == "content"
    assert effective.field_path is None
    assert effective.limits == {"max_chars": 12000}
    assert effective.ttl_seconds == 3600


def test_runtime_assembly_helpers_do_not_construct_host_or_engine_objects() -> None:
    """runtime assembly helper 返回值不得是 Host / Engine typed object。"""

    config = load_runtime_config()
    profile = (
        config.execution_profiles.execution_profiles["standard-256k"].agent_policy
    )
    selection = select_runner_option_hint(
        models=config.models,
        execution_baseline=config.execution_profiles.execution_profiles[
            "standard-256k"
        ].run_baseline,
        scene_model_hints=None,
        run_override=None,
        code_default=None,
    )
    merged = merge_agent_policy_config(
        code_default=_agent_policy_defaults(),
        execution_profile=profile,
        scene_override=None,
        run_override=None,
    )

    returned_modules = {
        selection.__class__.__module__,
        selection.model.__class__.__module__,
        selection.runner_option_hint.__class__.__module__,
        selection.diagnostic.__class__.__module__,
        merged.__class__.__module__,
    }

    assert not any(
        module.startswith("dayu.engine") or module.startswith("dayu.host")
        for module in returned_modules
    )


def test_execution_profile_256k_and_256k_model_is_compatible() -> None:
    """256k profile 搭配 256k 模型时诊断为 compatible。"""

    config = load_runtime_config()
    profile = config.execution_profiles.execution_profiles["standard-256k"]
    model = config.models.models["ollama"]

    diagnostic = validate_execution_profile_context_window(
        profile=profile,
        model=model,
    )

    assert diagnostic.profile_id == "standard-256k"
    assert diagnostic.selected_model_id == "ollama"
    assert diagnostic.status == "compatible"


def test_execution_profile_1m_and_256k_model_fails_fast() -> None:
    """1m profile 搭配 256k 模型必须 fail fast。"""

    config = load_runtime_config()
    profile = config.execution_profiles.execution_profiles["standard-1m"]
    model = config.models.models["ollama"]

    with pytest.raises(RuntimeAssemblySelectionError, match="larger context window"):
        validate_execution_profile_context_window(
            profile=profile,
            model=model,
        )


def test_execution_profile_256k_and_1m_model_is_conservative() -> None:
    """256k profile 搭配 1m 模型允许运行，但诊断为 conservative。"""

    config = load_runtime_config()
    profile = config.execution_profiles.execution_profiles["standard-256k"]
    model = config.models.models["deepseek-v4-flash"]

    diagnostic = validate_execution_profile_context_window(
        profile=profile,
        model=model,
    )

    assert diagnostic.profile_id == "standard-256k"
    assert diagnostic.selected_model_id == "deepseek-v4-flash"
    assert diagnostic.model_context_window_tokens >= 1000000
    assert diagnostic.status == "conservative"


def test_execution_profile_compatibility_helper_does_not_rewrite_selection() -> None:
    """compatibility helper 不改输入 profile，也不返回替代 profile id。"""

    config = load_runtime_config()
    profile = config.execution_profiles.execution_profiles["standard-256k"]
    model = config.models.models["deepseek-v4-flash"]

    diagnostic = validate_execution_profile_context_window(
        profile=profile,
        model=model,
    )

    assert profile.execution_profile_id == "standard-256k"
    assert diagnostic.profile_id == profile.execution_profile_id
    assert "alternative_profile_id" not in {
        field.name for field in fields(diagnostic)
    }
