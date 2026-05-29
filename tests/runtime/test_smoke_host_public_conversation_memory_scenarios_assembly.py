"""Host public 财报对话记忆场景 smoke 的 assembly 与纯 helper 测试。"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from datetime import datetime
from typing import cast

import pytest

from dayu.contracts import JsonValue, ToolBundle, ToolBundleSourceKind, ToolBundleSourceRef
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.runtime.log import LogLevel
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscoveryProviderSpec,
)
from utils.smoke_host_public_conversation_memory_scenarios import (
    MockFinanceMemoryTool,
    PressureMode,
    SmokeArgs,
    SuiteMode,
    _build_byd_long_input,
    _compact_pressure_padding,
    _estimate_chars_as_tokens,
    _ensure_request,
    _mock_pressure_blob,
    _prepare_runtime_assembly,
    _runtime_user_pressure_text,
    _select_long_templates,
    _threshold_tokens,
    _tool_pressure_estimated_tokens,
    assert_answer_contains,
    calls_by_key_summary,
    discover_smoke_tools,
    normalize_answer,
    parse_args,
    select_round_specs,
)
from dayu.runtime.tools_discovery import ToolsDiscoveryProviderOutput

_SCENE_ID = "smoke_host_public_conversation_memory_scenarios"
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"
_TOOL_NAME = "get_mock_finance_memory_fact"
_TOOL_TAG = "manual-smoke"


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回取消状态。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


class _NonSmokeTool:
    """测试用同名非 smoke 工具。"""

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回固定成功结果。

        :param call: 工具调用请求。
        :param context: 工具执行上下文。
        :returns: 固定工具成功结果。
        """

        del call, context
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"known": False}, meta=None)
        )


def test_runtime_assembly_adds_builtin_mock_tool_and_selects_manual_smoke(
    tmp_path: pathlib.Path,
) -> None:
    """默认装配会追加内置 mock 工具，并由新 scene 只选中 manual-smoke 工具。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    assembly = _prepare_runtime_assembly(
        _args(tmp_path),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )

    assert assembly.scene_inputs.tool_selection.tool_names == frozenset({_TOOL_NAME})
    assert assembly.diagnostics.tool_provider_reports == (
        "provider=host-public-conversation-memory-scenarios-smoke,"
        f"spec=host-public-conversation-memory-scenarios-smoke,version=v1,tools={_TOOL_NAME}",
    )
    assert isinstance(assembly.smoke_tool, MockFinanceMemoryTool)
    assert assembly.effective_tool_bundle is not None
    definitions = assembly.effective_tool_bundle.definitions
    smoke_definitions = tuple(item for item in definitions if item.name == _TOOL_NAME)
    assert len(smoke_definitions) == 1
    assert smoke_definitions[0].tags == (_TOOL_TAG,)


def test_runtime_assembly_fails_closed_on_non_smoke_same_name_tool(
    tmp_path: pathlib.Path,
) -> None:
    """workspace overlay 已发现同名非 smoke 工具时，脚本必须 fail closed。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    _write_non_smoke_tool_discovery_overlay(tmp_path)

    with pytest.raises(ValueError, match="already contains non-smoke tool"):
        _prepare_runtime_assembly(
            _args(tmp_path),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )


def test_cli_bounds_for_suite_and_long_rounds(tmp_path: pathlib.Path) -> None:
    """CLI suite 与 long-rounds 边界按 20..25 fail closed。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    for suite in ("core", "long", "all"):
        args = parse_args(
            (
                "--workspace-root",
                str(tmp_path),
                "--suite",
                suite,
                "--long-rounds",
                "20",
            )
        )
        assert args.suite is SuiteMode(suite)
        assert args.long_rounds == 20

    for value in ("20", "25"):
        assert parse_args(("--workspace-root", str(tmp_path), "--long-rounds", value)).long_rounds == int(value)

    for value in ("19", "26", "0", "-1"):
        with pytest.raises(SystemExit):
            parse_args(("--workspace-root", str(tmp_path), "--long-rounds", value))


def test_pure_spec_selection_counts_and_long20_final_label(
    tmp_path: pathlib.Path,
) -> None:
    """纯规格选择保持 core/long/all 工具调用累计与 long20 最终 recap 轮。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    core_specs = select_round_specs(_args(tmp_path, suite=SuiteMode.CORE))
    long_specs = select_round_specs(_args(tmp_path, suite=SuiteMode.LONG))
    all_specs = select_round_specs(_args(tmp_path, suite=SuiteMode.ALL))
    long20_specs = select_round_specs(
        _args(tmp_path, suite=SuiteMode.LONG, long_rounds=20)
    )

    assert core_specs[-1].expected_tool_calls_after_round == 4
    assert long_specs[0].expected_tool_calls_after_round == 1
    assert all_specs[len(core_specs)].expected_tool_calls_after_round == 5
    assert long20_specs[-1].label == "long-l25-constraint-assert"
    assert _select_long_templates(20)[-1].label == "long-l25-constraint-assert"


def test_byd_long_input_is_deterministic_with_expected_anchors() -> None:
    """C2 长输入确定、长度受控，三个 anchor 各出现一次。

    :returns: ``None``。
    """

    first = _build_byd_long_input()
    second = _build_byd_long_input()

    assert first == second
    assert 8_000 <= len(first) <= 15_000
    assert first.count("DAYU_LONG_INPUT_FACTOR_1_EXPORT_MIX") == 1
    assert first.count("BATTERY_PRICE_PRESSURE_FACTOR_2") == 1
    assert first.count("DAYU_LONG_INPUT_FACTOR_3_SCALE_EFFECT") == 1


@pytest.mark.asyncio
async def test_mock_finance_memory_tool_tracks_session_and_calls_by_key() -> None:
    """MockFinanceMemoryTool 只统计 tracked session，并输出稳定 calls_by_key 摘要。

    :returns: ``None``。
    """

    tool = MockFinanceMemoryTool(pressure_mode=PressureMode.AUTO)
    untracked_context = _tool_context("other-session")
    tracked_context = _tool_context("tracked-session")

    await tool(_tool_call(_known_cmb_arguments()), untracked_context)
    assert tool.call_count == 0
    assert calls_by_key_summary(tool.calls_by_key) == "SMOKE TOOL_CALLS_BY_KEY none"

    tool.track_session("tracked-session")
    known_outcome = await tool(_tool_call(_known_cmb_arguments()), tracked_context)
    unknown_outcome = await tool(_tool_call(_unknown_arguments()), tracked_context)

    known_payload = _success_payload(known_outcome)
    unknown_payload = _success_payload(unknown_outcome)
    assert known_payload["known"] is True
    assert known_payload["marker"] == "DAYU_MEM_CMB_NIM_2024H1_V2"
    assert known_payload["pressure_blob"] != ""
    assert unknown_payload["known"] is False
    assert tool.call_count == 2
    assert calls_by_key_summary(tool.calls_by_key) == (
        "SMOKE TOOL_CALLS_BY_KEY _UNKNOWN_FACT_KEY=1 cmb_nim=1"
    )


def test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """pressure=off 返回空压力，auto padding 估算落在 soft 与 hard 之间。

    :param tmp_path: pytest 临时 workspace root。
    :param capsys: stdout 捕获 fixture。
    :returns: ``None``。
    """

    assembly = _prepare_runtime_assembly(
        _args(tmp_path),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )
    policy = assembly.options.context_budget_policy
    assert policy is not None

    assert _runtime_user_pressure_text(PressureMode.OFF, assembly.options) == ""
    assert _mock_pressure_blob(True, PressureMode.OFF) == ""
    print("SMOKE PRESSURE disabled")
    assert "SMOKE PRESSURE disabled" in capsys.readouterr().out

    prompt_tokens = _estimate_chars_as_tokens(
        len(_compact_pressure_padding(assembly.options))
    )
    pressure_tokens = prompt_tokens + _tool_pressure_estimated_tokens()
    soft_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.soft_threshold_context_ratio,
    )
    hard_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.hard_threshold_context_ratio,
    )
    assert pressure_tokens >= soft_threshold_tokens
    assert pressure_tokens < hard_threshold_tokens


def test_answer_normalization_contains_and_forbidden_behavior() -> None:
    """回答断言只做稳定文本归一化，缺失与 forbidden 都会硬失败。

    :returns: ``None``。
    """

    content = " Result \n DAYU_MEM_ASSERT value=17.56％ AbC "

    assert normalize_answer(content) == "resultdayu_mem_assertvalue=17.56%abc"
    assert_answer_contains(
        content,
        label="unit",
        required=("dayu_mem_assert value=17.56% abc",),
        forbidden=("missing-marker",),
    )
    with pytest.raises(AssertionError, match="missing"):
        assert_answer_contains(content, label="unit", required=("not-present",))
    with pytest.raises(AssertionError, match="forbidden"):
        assert_answer_contains(content, label="unit", required=(), forbidden=("AbC",))


def test_discover_smoke_tools_contract_exposes_single_manual_tool() -> None:
    """内置 provider 输出单个 manual-smoke mock 工具定义。

    :returns: ``None``。
    """

    output = discover_smoke_tools(
        ToolsDiscoveryProviderSpec(
            spec_id="financial-tools",
            location=PythonImportPathProvider(
                import_path=(
                    "utils.smoke_host_public_conversation_memory_scenarios:"
                    "discover_smoke_tools"
                )
            ),
        )
    )

    assert output.provider_id == "host-public-conversation-memory-scenarios-smoke"
    assert len(output.definitions) == 1
    definition = output.definitions[0]
    assert definition.name == _TOOL_NAME
    assert definition.tags == (_TOOL_TAG,)


def discover_non_smoke_same_name_tools(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderOutput:
    """返回同名非 smoke 工具，用于验证 assembly fail closed。

    :param spec: 工具发现 provider spec。
    :returns: 测试 provider 输出。
    """

    return ToolsDiscoveryProviderOutput(
        provider_id="non-smoke-same-name-provider",
        version_ref="v1",
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.CONFIG_BINDING,
                source_id=spec.spec_id,
            ),
        ),
        definitions=(_non_smoke_tool_definition(),),
    )


def _args(
    workspace_root: pathlib.Path,
    *,
    suite: SuiteMode = SuiteMode.CORE,
    long_rounds: int = 25,
    reuse_session: bool = False,
) -> SmokeArgs:
    """构造测试用 smoke 参数。

    :param workspace_root: pytest 临时 workspace root。
    :param suite: 场景套件模式。
    :param long_rounds: long suite 轮数。
    :param reuse_session: 是否复用稳定 session slot。
    :returns: smoke 参数。
    """

    return SmokeArgs(
        workspace_root=workspace_root,
        scene_id=_SCENE_ID,
        execution_profile_id="standard-256k",
        host_runtime_id="local",
        model_id=_MODEL_ID,
        runner_option_hint_id=_RUNNER_HINT_ID,
        log_level=LogLevel.CRITICAL,
        reuse_session=reuse_session,
        keep_workspace=False,
        suite=suite,
        long_rounds=long_rounds,
        pressure_mode=PressureMode.AUTO,
    )


def _tool_context(session_id: str) -> BatchToolExecutionContext:
    """构造测试工具执行上下文。

    :param session_id: session id。
    :returns: 工具执行上下文。
    """

    return BatchToolExecutionContext(
        run_id="run-1",
        session_id=session_id,
        iteration_id="iteration-1",
        timeout_seconds=None,
        cancellation_token=_OpenCancellationToken(),
        correlation_id=None,
    )


def _tool_call(arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造测试工具调用请求。

    :param arguments: 工具参数。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id="tool-call-1",
        name=_TOOL_NAME,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _known_cmb_arguments() -> Mapping[str, JsonValue]:
    """返回命中招商银行息差事实的工具参数。

    :returns: 工具参数映射。
    """

    return {
        "company": "招商银行",
        "ticker": "600036.SH",
        "period": "2024H1",
        "topic": "net_interest_margin",
        "metric": "cmb_nim",
        "include_pressure": True,
    }


def _unknown_arguments() -> Mapping[str, JsonValue]:
    """返回无法命中固定 facts 的工具参数。

    :returns: 工具参数映射。
    """

    return {
        "company": "未知公司",
        "ticker": "000000.SZ",
        "period": "2024H1",
        "topic": "net_interest_margin",
        "metric": "cmb_nim",
        "include_pressure": True,
    }


def _success_payload(outcome: ToolExecutionOutcome) -> Mapping[str, JsonValue]:
    """从工具成功 outcome 中取出 JSON object payload。

    :param outcome: 工具执行 outcome。
    :returns: 成功载荷映射。
    :raises AssertionError: outcome 不是成功 JSON object 时抛出。
    """

    assert isinstance(outcome, ToolCompletedOutcome)
    value = outcome.result.value
    assert isinstance(value, Mapping)
    return value


def _write_non_smoke_tool_discovery_overlay(workspace_root: pathlib.Path) -> None:
    """写入同名非 smoke provider overlay。

    :param workspace_root: pytest 临时 workspace root。
    :returns: ``None``。
    :raises OSError: 目录或文件写入失败时抛出。
    """

    config_dir = workspace_root / "workspace" / "config"
    config_dir.mkdir(parents=True)
    payload = {
        "providers": {
            "financial-tools": {
                "import_path": (
                    "tests.runtime.test_smoke_host_public_conversation_memory_scenarios_assembly:"
                    "discover_non_smoke_same_name_tools"
                ),
                "entry_point": None,
                "source_kind": "config_binding",
                "source_id": "tests.runtime.non_smoke_same_name",
                "enabled": True,
                "allow_empty": False,
            }
        }
    }
    (config_dir / "tool_discovery.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _non_smoke_tool_definition() -> ToolDefinition:
    """构造同名但 callable 类型不同的工具定义。

    :returns: 非 smoke 工具定义。
    """

    return ToolDefinition(
        name=_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=_TOOL_NAME,
                description="Non-smoke same-name test tool.",
                parameters=ToolParametersSchema(
                    type="object",
                    properties={},
                    required=(),
                    additional_properties=False,
                ),
            ),
        ),
        callable=_NonSmokeTool(),
        truncate=None,
        display=None,
        tags=(_TOOL_TAG,),
    )


def test_smoke_uses_fresh_session_slot_by_default(tmp_path: pathlib.Path) -> None:
    """默认 fresh slot 带 smoke run id，reuse 才使用稳定 slot。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    fresh = _ensure_request(_args(tmp_path), "runabc")
    reused = _ensure_request(_args(tmp_path, reuse_session=True), "runabc")

    assert fresh.slot_key.endswith("-runabc")
    assert reused.slot_key == "manual-smoke-conversation-memory-scenarios"


def test_find_mock_tool_uses_discovered_bundle_shape() -> None:
    """内置 provider 输出可放入 ToolBundle，避免 assembly 依赖历史状态。

    :returns: ``None``。
    """

    provider_output = discover_smoke_tools(
        ToolsDiscoveryProviderSpec(
            spec_id="financial-tools",
            location=PythonImportPathProvider(
                import_path=(
                    "utils.smoke_host_public_conversation_memory_scenarios:"
                    "discover_smoke_tools"
                )
            ),
        )
    )
    discovered_bundle = ToolBundle(definitions=provider_output.definitions)

    assert len(discovered_bundle.definitions) == 1
    assert isinstance(discovered_bundle.definitions[0].callable, MockFinanceMemoryTool)
