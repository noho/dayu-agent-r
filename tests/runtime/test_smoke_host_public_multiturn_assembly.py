"""Host public multiturn smoke 的 runtime assembly focused tests。"""

from __future__ import annotations

import json
import pathlib

import pytest

from dayu.contracts import (
    BatchToolExecutionContext,
    ToolBundle,
    ToolCallRequest,
    ToolDefinition,
    ToolExecutionOutcome,
)
from dayu.runtime.log import LogLevel
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscoveryProviderSpec,
)
from utils.smoke_host_public_multiturn import (
    SmokeArgs,
    _compact_pressure_padding,
    _estimate_chars_as_tokens,
    _find_smoke_tool,
    _ensure_request,
    _print_assembly_diagnostics,
    _prepare_runtime_assembly,
    _safe_summary_text,
    _threshold_tokens,
    _tool_pressure_estimated_tokens,
    discover_smoke_tools,
)

_SCENE_ID = "smoke_host_public_multiturn"
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"


async def _not_smoke_tool(
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
) -> ToolExecutionOutcome:
    """测试用非 smoke callable。

    :param call: 工具调用请求。
    :param context: 执行上下文。
    :returns: 不返回；本测试只验证声明识别，不会调用该工具。
    :raises AssertionError: 被意外调用时抛出。
    """

    del call
    del context
    raise AssertionError("non-smoke tool should not be called")


def test_runtime_assembly_adds_builtin_smoke_tool_without_workspace_overlay(
    tmp_path: pathlib.Path,
) -> None:
    """默认直接运行 smoke 时会通过内置 provider 提供 mock tool。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 未发现内置 smoke tool 或仍依赖真实财报工具时抛出。
    """

    assembly = _prepare_runtime_assembly(
        _args(tmp_path),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )

    assert assembly.scene_inputs.tool_selection.tool_names == frozenset(
        {"record_smoke_fact"}
    )
    assert (
        "provider=host-public-multiturn-smoke,"
        "spec=host-public-multiturn-smoke,version=v1,tools=record_smoke_fact"
    ) in assembly.diagnostics.tool_provider_reports
    assert assembly.smoke_tool is not None


def test_runtime_assembly_uses_workspace_tool_discovery_and_typed_overrides(
    tmp_path: pathlib.Path,
) -> None:
    """workspace overlay 显式启用 provider 后，smoke 走完整 assembly 成功路径。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: assembly 输出未使用 typed override 或工具发现时抛出。
    """

    _write_smoke_tool_discovery_overlay(tmp_path)
    assembly = _prepare_runtime_assembly(
        _args(tmp_path),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )

    assert assembly.diagnostics.config_overlay_dir == tmp_path / "workspace" / "config"
    assert assembly.diagnostics.host_runtime_id == "local"
    assert assembly.diagnostics.execution_profile_id == "standard-256k"
    assert assembly.diagnostics.model_id == _MODEL_ID
    assert assembly.diagnostics.model_source == "run_override"
    assert assembly.diagnostics.runner_option_hint_id == _RUNNER_HINT_ID
    assert assembly.diagnostics.runner_option_hint_source == "run_override"
    assert assembly.scene_inputs.tool_selection.tool_names == frozenset(
        {"record_smoke_fact"}
    )
    assert (
        "provider=host-public-multiturn-smoke,"
        "spec=financial-tools,version=v1,tools=record_smoke_fact"
    ) in assembly.diagnostics.tool_provider_reports
    assert assembly.diagnostics.ordinary_provider_extension_status.endswith(
        "ok:DeepSeekThinkingExtension"
    )
    assert assembly.scene_inputs.system_prompt.strip() != ""
    options = assembly.options
    assert options.lane_name == "llm_api"
    assert options.sqlite_write_busy_retry_count == 8
    assert options.payload_inline_threshold_bytes == 65535
    assert options.worker_startup_timeout_seconds == 10.0
    assert options.tooling_options is not None
    assert "record_smoke_fact" in tuple(
        definition.name
        for definition in options.tooling_options.business_tool_bundle.definitions
    )
    assert options.ordinary_run_baseline.runner_spec.headers["Authorization"] == (
        f"Bearer {_API_KEY}"
    )


def test_assembly_diagnostics_output_uses_current_agent_policy_sources(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """assembly diagnostics 输出不再引用旧 agent policy profile 字段。

    :param tmp_path: pytest 临时 workspace root。
    :param capsys: pytest stdout 捕获 fixture。
    :returns: ``None``。
    :raises AssertionError: 输出仍包含旧 profile 标签或缺少当前来源摘要时抛出。
    """

    _write_smoke_tool_discovery_overlay(tmp_path)
    assembly = _prepare_runtime_assembly(
        _args(tmp_path),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )

    _print_assembly_diagnostics(assembly.diagnostics, assembly.options)

    output = capsys.readouterr().out
    assert "agent_policy_profile" not in output
    assert "SMOKE ASSEMBLY agent_policy_sources=" in output
    assert "SMOKE ASSEMBLY tool_duplicate_governance_default=hint" in output


def test_smoke_uses_fresh_session_slot_by_default(tmp_path: pathlib.Path) -> None:
    """默认 ensure session slot 带 smoke run id，避免多次手工运行互相污染。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 默认 slot key 没有 run id 或复用开关失效时抛出。
    """

    fresh = _ensure_request(_args(tmp_path), "runabc")
    reused = _ensure_request(_args(tmp_path, reuse_session=True), "runabc")

    assert fresh.slot_key.endswith("-runabc")
    assert reused.slot_key == "runtime-assembly-host-public-multiturn-smoke"


def test_compact_pressure_prompt_targets_soft_before_hard(
    tmp_path: pathlib.Path,
) -> None:
    """compact pressure prompt 根据装配出的 policy 落在 soft / hard 之间。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: pressure 过小不能触发 compact 或过大越过 hard 时抛出。
    """

    assembly = _prepare_runtime_assembly(
        _args(tmp_path),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )
    policy = assembly.options.context_budget_policy
    assert policy is not None
    prompt_tokens = _estimate_chars_as_tokens(
        len(_compact_pressure_padding(assembly.options))
    )
    expected_pressure_tokens = prompt_tokens + _tool_pressure_estimated_tokens()
    soft_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.soft_threshold_context_ratio,
    )
    hard_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.hard_threshold_context_ratio,
    )

    assert expected_pressure_tokens >= soft_threshold_tokens
    assert expected_pressure_tokens < hard_threshold_tokens


def test_find_smoke_tool_only_inspects_passed_tool_bundle() -> None:
    """smoke tool 查找只读取传入 bundle，不使用 provider 历史状态回退。

    :returns: ``None``。
    :raises AssertionError: 空 bundle 被历史 provider 调用结果污染时抛出。
    """

    provider_output = discover_smoke_tools(
        ToolsDiscoveryProviderSpec(
            spec_id="financial-tools",
            location=PythonImportPathProvider(
                import_path=(
                    "utils.smoke_host_public_multiturn:discover_smoke_tools"
                )
            ),
        )
    )
    discovered_bundle = ToolBundle(definitions=provider_output.definitions)
    non_smoke_bundle = ToolBundle(
        definitions=(
            ToolDefinition(
                name=provider_output.definitions[0].name,
                schema=provider_output.definitions[0].schema,
                callable=_not_smoke_tool,
                truncate=None,
                display=None,
                tags=(),
            ),
        )
    )

    assert _find_smoke_tool(discovered_bundle) is not None
    assert _find_smoke_tool(non_smoke_bundle) is None


def test_smoke_failure_summary_redacts_sensitive_message() -> None:
    """smoke 失败摘要不得打印 provider header 或 key 类敏感文本。"""

    assert _safe_summary_text("Authorization: Bearer sk-test") == "<redacted>"
    long_text = "x" * 260
    assert _safe_summary_text(long_text).endswith("...")


def _args(workspace_root: pathlib.Path, *, reuse_session: bool = False) -> SmokeArgs:
    """构造测试用 smoke 参数。

    :param workspace_root: pytest 临时 workspace root。
    :param reuse_session: 是否复用稳定 durable slot。
    :returns: smoke 参数。
    :raises Exception: 不主动抛出异常。
    """

    return SmokeArgs(
        workspace_root=workspace_root,
        scene_id=_SCENE_ID,
        execution_profile_id="standard-256k",
        host_runtime_id="local",
        model_id=_MODEL_ID,
        runner_option_hint_id=_RUNNER_HINT_ID,
        fins_default_subject="测试财报主体",
        base_user="runtime-assembly-test",
        log_level=LogLevel.CRITICAL,
        reuse_session=reuse_session,
        keep_workspace=False,
    )


def _write_smoke_tool_discovery_overlay(workspace_root: pathlib.Path) -> None:
    """写入启用 smoke provider 的 workspace tool discovery overlay。

    :param workspace_root: pytest 临时 workspace root。
    :returns: ``None``。
    :raises OSError: 目录或文件写入失败时抛出。
    :raises TypeError: JSON 序列化字段非法时抛出。
    """

    config_dir = workspace_root / "workspace" / "config"
    config_dir.mkdir(parents=True)
    payload = {
        "providers": {
            "financial-tools": {
                "import_path": (
                    "utils.smoke_host_public_multiturn:discover_smoke_tools"
                ),
                "entry_point": None,
                "source_kind": "config_binding",
                "source_id": "utils.smoke_host_public_multiturn",
                "enabled": True,
            }
        }
    }
    (config_dir / "tool_discovery.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
