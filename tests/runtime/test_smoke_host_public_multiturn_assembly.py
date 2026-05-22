"""Host public multiturn smoke 的 runtime assembly focused tests。"""

from __future__ import annotations

import json
import pathlib

import pytest

from dayu.contracts import ToolBundle
from dayu.runtime.log import LogLevel
from dayu.runtime.scene_prepare import ScenePrepareError
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscoveryProviderSpec,
)
from utils.smoke_host_public_multiturn import (
    SmokeArgs,
    _find_smoke_tool,
    _print_assembly_diagnostics,
    _prepare_runtime_assembly,
    discover_smoke_tools,
)

_SCENE_ID = "smoke_host_public_multiturn"
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"


def test_runtime_assembly_fails_before_host_when_tools_not_discovered(
    tmp_path: pathlib.Path,
) -> None:
    """默认 disabled tool provider 不会被 smoke 用脚本内 ToolBundle 掩盖。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: 未在 Host 调用前暴露缺失工具时抛出。
    """

    with pytest.raises(ScenePrepareError, match="tool_tags_any matched no tools"):
        _prepare_runtime_assembly(_args(tmp_path), env={"DEEPSEEK_API_KEY": _API_KEY})


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
    assert assembly.diagnostics.tool_provider_reports == (
        "provider=host-public-multiturn-smoke,"
        "spec=financial-tools,version=v1,tools=record_smoke_fact",
    )
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
    assert tuple(
        definition.name
        for definition in options.tooling_options.business_tool_bundle.definitions
    ) == ("record_smoke_fact",)
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

    _print_assembly_diagnostics(assembly.diagnostics)

    output = capsys.readouterr().out
    assert "agent_policy_profile" not in output
    assert "SMOKE ASSEMBLY agent_policy_sources=" in output


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

    assert _find_smoke_tool(discovered_bundle) is not None
    assert _find_smoke_tool(ToolBundle(definitions=())) is None


def _args(workspace_root: pathlib.Path) -> SmokeArgs:
    """构造测试用 smoke 参数。

    :param workspace_root: pytest 临时 workspace root。
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
                "allow_empty": False,
            }
        }
    }
    (config_dir / "tool_discovery.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
