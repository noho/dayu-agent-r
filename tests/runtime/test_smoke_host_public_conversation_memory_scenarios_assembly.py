"""Host public 财报对话记忆场景 smoke 的 assembly 与纯 helper 测试。"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from datetime import datetime

import pytest

from dayu.contracts import (
    AsyncDirectToolExecutionCapability,
    JsonValue,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
)
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
)
from dayu.host.durable.event_log import EventClass, EventLogRow
from dayu.runtime.log import LogLevel
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscoveryProviderSpec,
)
from utils.smoke_host_public_conversation_memory_scenarios import (
    CompactAuditSummary,
    CompactAuditReport,
    MockFinanceMemoryTool,
    PressureMode,
    SmokeArgs,
    SuiteMode,
    _ASSERT_B_CFO,
    _assert_compact_acceptance,
    _assert_fallback_dispatch_acceptance,
    _assert_memory_compact_pressure_bounds,
    _assert_reactive_compact_acceptance,
    _FACT_KEY_CATL_CASHFLOW,
    _FACT_KEY_CMB_NIM,
    _FACT_KEY_MAOTAI_REVENUE,
    _FACT_KEY_MIDEA_LONG_SESSION,
    _FACT_KEY_WULIANGYE_REVENUE,
    _LABEL_CORE_B1,
    _MARKER_CATL_CASHFLOW,
    _COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS,
    _COMPACT_PRESSURE_RESERVE_TOKENS,
    _SMOKE_REACTIVE_CURRENT_MARKER,
    _SMOKE_REACTIVE_OLD_MARKER,
    _SMOKE_REACTIVE_RECENT_MARKER,
    _SMOKE_REACTIVE_SELECTED_RECENT_ITEMS_PER_TURN,
    _VALUE_CATL_LARGEST_GAP,
    _VALUE_CATL_NET_PROFIT,
    _VALUE_CATL_OPERATING_CF,
    _build_byd_long_input,
    _compact_audit_report_from_rows,
    _compact_audit_summary_from_rows,
    _compact_pressure_padding,
    _deterministic_dropped_old_marker,
    _estimate_chars_as_tokens,
    _fake_compaction_proposal_from_material_json,
    _fallback_compact_pressure_padding,
    _print_compact_audit_report,
    DeterministicDispatchCapture,
    DeterministicSmokeObservation,
    _ensure_request,
    _mock_pressure_blob,
    _prepare_runtime_assembly,
    _print_compact_pressure_plan,
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
        return ToolCompletedOutcome(result=ToolResultSuccess(ok=True, value={"known": False}, meta=None))


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
    assert (
        "provider=host-public-conversation-memory-scenarios-smoke,"
        f"spec=host-public-conversation-memory-scenarios-smoke,version=v1,tools={_TOOL_NAME}"
    ) in assembly.diagnostics.tool_provider_reports
    assert isinstance(assembly.smoke_tool, MockFinanceMemoryTool)
    assert assembly.effective_tool_bundle is not None
    definitions = assembly.effective_tool_bundle.definitions
    smoke_definitions = tuple(item for item in definitions if item.name == _TOOL_NAME)
    assert len(smoke_definitions) == 1
    assert smoke_definitions[0].tags == (_TOOL_TAG,)


def test_reactive_runtime_assembly_bounds_selected_recent_window(
    tmp_path: pathlib.Path,
) -> None:
    """reactive smoke 本地收紧 selected recent，避免旧 marker 仍进 recovery。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    assembly = _prepare_runtime_assembly(
        _args(tmp_path, suite=SuiteMode.MEMORY_REACTIVE_COMPACT),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )
    policy = assembly.options.memory_projection_policy

    assert policy.selected_recent_window_item_cap == (
        policy.selected_recent_window_turn_floor
        * _SMOKE_REACTIVE_SELECTED_RECENT_ITEMS_PER_TURN
    )
    assert policy.fallback_selected_recent_window_item_cap <= policy.selected_recent_window_item_cap


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
    """CLI suite、pressure 与 long-rounds 边界按新语义 fail closed。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    default_args = parse_args(("--workspace-root", str(tmp_path)))
    assert default_args.suite is SuiteMode.MEMORY_CORE
    assert default_args.pressure_mode is PressureMode.OFF

    for suite in ("memory-core", "memory-reactive-compact"):
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

    compact_args = parse_args(
        (
            "--workspace-root",
            str(tmp_path),
            "--suite",
            "memory-compact",
            "--pressure-mode",
            "auto",
        )
    )
    assert compact_args.suite is SuiteMode.MEMORY_COMPACT
    assert compact_args.pressure_mode is PressureMode.AUTO

    fallback_args = parse_args(
        (
            "--workspace-root",
            str(tmp_path),
            "--suite",
            "memory-compact-fallback",
            "--pressure-mode",
            "auto",
        )
    )
    assert fallback_args.suite is SuiteMode.MEMORY_COMPACT_FALLBACK
    assert fallback_args.pressure_mode is PressureMode.AUTO

    with pytest.raises(SystemExit):
        parse_args(("--workspace-root", str(tmp_path), "--suite", "memory-compact"))
    with pytest.raises(SystemExit):
        parse_args(("--workspace-root", str(tmp_path), "--suite", "memory-compact-fallback"))

    for value in ("20", "25"):
        assert parse_args(("--workspace-root", str(tmp_path), "--long-rounds", value)).long_rounds == int(value)

    for value in ("19", "26", "0", "-1"):
        with pytest.raises(SystemExit):
            parse_args(("--workspace-root", str(tmp_path), "--long-rounds", value))


def test_pure_spec_selection_tool_fact_requirements_and_long20_final_label(
    tmp_path: pathlib.Path,
) -> None:
    """纯规格选择保持工具事实要求与 long20 最终 recap 轮。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    core_specs = select_round_specs(_args(tmp_path, suite=SuiteMode.MEMORY_CORE))
    compact_specs = select_round_specs(_args(tmp_path, suite=SuiteMode.MEMORY_COMPACT, pressure_mode=PressureMode.AUTO))
    reactive_specs = select_round_specs(_args(tmp_path, suite=SuiteMode.MEMORY_REACTIVE_COMPACT))
    fallback_specs = select_round_specs(
        _args(tmp_path, suite=SuiteMode.MEMORY_COMPACT_FALLBACK, pressure_mode=PressureMode.AUTO)
    )
    compact20_specs = select_round_specs(
        _args(
            tmp_path,
            suite=SuiteMode.MEMORY_COMPACT,
            long_rounds=20,
            pressure_mode=PressureMode.AUTO,
        )
    )

    assert tuple(spec.expected_tool_fact_key for spec in core_specs if spec.tool_names) == (
        _FACT_KEY_MAOTAI_REVENUE,
        _FACT_KEY_WULIANGYE_REVENUE,
        _FACT_KEY_CATL_CASHFLOW,
        _FACT_KEY_CMB_NIM,
    )
    first_long_index = len(core_specs)
    assert compact_specs[first_long_index].expected_tool_fact_key == _FACT_KEY_MIDEA_LONG_SESSION
    assert compact_specs[first_long_index + 4].tool_names
    assert compact_specs[first_long_index + 4].expected_tool_fact_key is None
    assert tuple(spec.label for spec in compact_specs[:first_long_index]) == tuple(spec.label for spec in core_specs)
    assert compact20_specs[-1].label == "long-l25-constraint-assert"
    assert _select_long_templates(20)[-1].label == "long-l25-constraint-assert"
    assert tuple(spec.label for spec in reactive_specs) == (
        "reactive-r1-old-seed",
        "reactive-r2-history-gap",
        "reactive-r3-history-gap",
        "reactive-r4-history-gap",
        "reactive-r5-protected-recent",
        "reactive-r6-overflow-target",
    )
    reactive_spec_by_label = {spec.label: spec for spec in reactive_specs}
    assert _SMOKE_REACTIVE_OLD_MARKER in reactive_spec_by_label["reactive-r1-old-seed"].prompt
    assert tuple(spec.label for spec in fallback_specs) == (
        "fallback-f1-old-dropped",
        "fallback-f2-old-dropped",
        "fallback-f3-old-dropped",
        "fallback-f4-old-dropped",
        "fallback-f5-old-dropped",
        "fallback-f6-selected-recent",
        "fallback-f7-pressure-target",
    )


def test_core_b1_tool_round_prompt_does_not_leak_cashflow_answer_values(
    tmp_path: pathlib.Path,
) -> None:
    """core-b1 强制工具轮的 prompt 不泄露工具结果值。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    specs = select_round_specs(_args(tmp_path, suite=SuiteMode.MEMORY_CORE))
    core_b1 = next(spec for spec in specs if spec.label == _LABEL_CORE_B1)

    assert "get_mock_finance_memory_fact" in core_b1.prompt
    assert _ASSERT_B_CFO not in core_b1.prompt
    assert _MARKER_CATL_CASHFLOW not in core_b1.prompt
    assert _VALUE_CATL_OPERATING_CF not in core_b1.prompt
    assert _VALUE_CATL_NET_PROFIT not in core_b1.prompt
    assert _VALUE_CATL_LARGEST_GAP not in core_b1.prompt
    assert _MARKER_CATL_CASHFLOW in core_b1.hard_answer_contains
    assert _VALUE_CATL_OPERATING_CF in core_b1.hard_answer_contains
    assert _VALUE_CATL_LARGEST_GAP in core_b1.hard_answer_contains


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
    assert calls_by_key_summary(tool.calls_by_key) == ("SMOKE TOOL_CALLS_BY_KEY _UNKNOWN_FACT_KEY=1 cmb_nim=1")


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

    prompt_tokens = _estimate_chars_as_tokens(len(_compact_pressure_padding(assembly.options)))
    pressure_tokens = (
        prompt_tokens
        + _tool_pressure_estimated_tokens()
        + _COMPACT_PRESSURE_RESERVE_TOKENS
    )
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
    _assert_memory_compact_pressure_bounds(
        assembly.options,
        PressureMode.AUTO,
        SuiteMode.MEMORY_COMPACT,
    )
    _print_compact_pressure_plan(
        assembly.options,
        PressureMode.AUTO,
        suite=SuiteMode.MEMORY_COMPACT,
    )
    compact_output = capsys.readouterr().out
    assert f"reserve_tokens={_COMPACT_PRESSURE_RESERVE_TOKENS}" in compact_output
    assert f"estimated_effective_pressure_tokens={pressure_tokens}" in compact_output
    assert f"estimated_total_pressure_tokens={pressure_tokens}" in compact_output

    fallback_prompt_tokens = _estimate_chars_as_tokens(
        len(_fallback_compact_pressure_padding(assembly.options))
    )
    fallback_effective_tokens = (
        fallback_prompt_tokens
        + _tool_pressure_estimated_tokens()
        + _COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS
    )
    _print_compact_pressure_plan(
        assembly.options,
        PressureMode.AUTO,
        suite=SuiteMode.MEMORY_COMPACT_FALLBACK,
    )
    fallback_output = capsys.readouterr().out
    assert (
        f"reserve_tokens={_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS}"
        in fallback_output
    )
    assert (
        f"estimated_effective_pressure_tokens={fallback_effective_tokens}"
        in fallback_output
    )


def test_compact_acceptance_requires_event_log_audit_summary(tmp_path: pathlib.Path) -> None:
    """compact suite 基于 EventLog audit 摘要验收，不把最终回答当 compact PASS。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    """

    assembly = _prepare_runtime_assembly(
        _args(tmp_path),
        env={"DEEPSEEK_API_KEY": _API_KEY},
    )
    assert assembly.options.compactor_runner_baseline is not None
    compact_root = assembly.options.compactor_runner_baseline.compact_artifact_root
    compact_root.mkdir(parents=True, exist_ok=True)
    (compact_root / "compact-smoke.json").write_text("{}", encoding="utf-8")

    accepted = CompactAuditSummary(
        requested_proactive=1,
        requested_reactive=0,
        compacted_proactive=1,
        compacted_reactive=0,
        failed_proactive=0,
        failed_reactive=0,
        rejected_proactive=0,
        rejected_reactive=0,
    )
    _assert_compact_acceptance(
        suite=SuiteMode.MEMORY_COMPACT,
        audit=accepted,
        options=assembly.options,
    )
    _assert_compact_acceptance(
        suite=SuiteMode.MEMORY_CORE,
        audit=CompactAuditSummary(
            requested_proactive=0,
            requested_reactive=0,
            compacted_proactive=0,
            compacted_reactive=0,
            failed_proactive=0,
            failed_reactive=0,
            rejected_proactive=0,
            rejected_reactive=0,
        ),
        options=assembly.options,
    )

    missing_accepted = CompactAuditSummary(
        requested_proactive=1,
        requested_reactive=0,
        compacted_proactive=0,
        compacted_reactive=0,
        failed_proactive=0,
        failed_reactive=0,
        rejected_proactive=0,
        rejected_reactive=0,
    )
    with pytest.raises(RuntimeError, match="did not observe proactive CONTEXT_COMPACTED"):
        _assert_compact_acceptance(
            suite=SuiteMode.MEMORY_COMPACT,
            audit=missing_accepted,
            options=assembly.options,
        )

    failed = CompactAuditSummary(
        requested_proactive=1,
        requested_reactive=0,
        compacted_proactive=1,
        compacted_reactive=0,
        failed_proactive=1,
        failed_reactive=0,
        rejected_proactive=0,
        rejected_reactive=0,
    )
    with pytest.raises(RuntimeError, match="CONTEXT_COMPACTION_FAILED"):
        _assert_compact_acceptance(
            suite=SuiteMode.MEMORY_COMPACT,
            audit=failed,
            options=assembly.options,
        )


def test_reactive_compact_acceptance_helper_requires_reactive_recovery_signals() -> None:
    """reactive helper 只在 compact 成功、recovery 与旧 marker 排除都存在时通过。

    :returns: ``None``。
    """

    base_rows = (
        _event_row(
            sequence=1,
            event_id="event-reactive-request",
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload={"trigger_source": "reactive"},
            run_id="run-reactive-target",
        ),
        _event_row(
            sequence=2,
            event_id="event-reactive-compacted",
            event_type=CONTEXT_COMPACTED,
            payload={"operation_id": "event-reactive-request"},
            run_id="run-reactive-target",
        ),
    )
    report = _compact_audit_report_from_rows(base_rows)
    assert _deterministic_dropped_old_marker(SuiteMode.MEMORY_REACTIVE_COMPACT) == _SMOKE_REACTIVE_OLD_MARKER
    observation = DeterministicSmokeObservation(
        dispatches=(
            _dispatch_capture(
                run_id="run-reactive-target",
                attempt_id="attempt-original",
                execution_id="execution-original",
                text=_SMOKE_REACTIVE_CURRENT_MARKER,
            ),
            _dispatch_capture(
                run_id="run-reactive-target",
                attempt_id="attempt-recovery",
                execution_id="execution-recovery",
                text=(
                    f"{_SMOKE_REACTIVE_CURRENT_MARKER} "
                    f"{_SMOKE_REACTIVE_RECENT_MARKER}"
                ),
            ),
        ),
        target_run_id="run-reactive-target",
        current_input_marker=_SMOKE_REACTIVE_CURRENT_MARKER,
        protected_recent_marker=_SMOKE_REACTIVE_RECENT_MARKER,
        dropped_old_marker=_deterministic_dropped_old_marker(SuiteMode.MEMORY_REACTIVE_COMPACT),
        pressure_tokens=None,
        soft_threshold_tokens=None,
        hard_threshold_tokens=None,
    )

    _assert_reactive_compact_acceptance(report, observation)

    for polluted_rows in (
        (
            _event_row(
                sequence=3,
                event_id="event-proactive-request",
                event_type=CONTEXT_COMPACTION_REQUESTED,
                payload={"trigger_source": "proactive"},
                run_id="run-reactive-target",
            ),
        ),
        (
            _event_row(
                sequence=3,
                event_id="event-proactive-request",
                event_type=CONTEXT_COMPACTION_REQUESTED,
                payload={"trigger_source": "proactive"},
                run_id="run-reactive-target",
            ),
            _event_row(
                sequence=4,
                event_id="event-proactive-compacted",
                event_type=CONTEXT_COMPACTED,
                payload={"operation_id": "event-proactive-request"},
                run_id="run-reactive-target",
            ),
        ),
        (
            _event_row(
                sequence=3,
                event_id="event-proactive-request",
                event_type=CONTEXT_COMPACTION_REQUESTED,
                payload={"trigger_source": "proactive"},
                run_id="run-reactive-target",
            ),
            _event_row(
                sequence=4,
                event_id="event-proactive-failed",
                event_type=CONTEXT_COMPACTION_FAILED,
                payload={"operation_id": "event-proactive-request"},
                run_id="run-reactive-target",
            ),
        ),
    ):
        proactive_polluted = _compact_audit_report_from_rows(
            (
                *base_rows,
                *polluted_rows,
            )
        )
        with pytest.raises(RuntimeError, match="unexpected proactive compact activity"):
            _assert_reactive_compact_acceptance(proactive_polluted, observation)

    missing_reactive = _compact_audit_report_from_rows(())
    with pytest.raises(RuntimeError, match="reactive CONTEXT_COMPACTION_REQUESTED"):
        _assert_reactive_compact_acceptance(missing_reactive, observation)

    missing_dropped_marker = DeterministicSmokeObservation(
        dispatches=observation.dispatches,
        target_run_id=observation.target_run_id,
        current_input_marker=observation.current_input_marker,
        protected_recent_marker=observation.protected_recent_marker,
        dropped_old_marker=None,
        pressure_tokens=None,
        soft_threshold_tokens=None,
        hard_threshold_tokens=None,
    )
    with pytest.raises(RuntimeError, match="missing dropped old marker expectation"):
        _assert_reactive_compact_acceptance(report, missing_dropped_marker)

    old_marker_leaked = DeterministicSmokeObservation(
        dispatches=(
            observation.dispatches[0],
            _dispatch_capture(
                run_id="run-reactive-target",
                attempt_id="attempt-recovery",
                execution_id="execution-recovery",
                text=(
                    f"{_SMOKE_REACTIVE_CURRENT_MARKER} "
                    f"{_SMOKE_REACTIVE_RECENT_MARKER} "
                    f"{_SMOKE_REACTIVE_OLD_MARKER}"
                ),
            ),
        ),
        target_run_id=observation.target_run_id,
        current_input_marker=observation.current_input_marker,
        protected_recent_marker=observation.protected_recent_marker,
        dropped_old_marker=observation.dropped_old_marker,
        pressure_tokens=None,
        soft_threshold_tokens=None,
        hard_threshold_tokens=None,
    )
    with pytest.raises(RuntimeError, match="reactive recovery dropped old unexpectedly contains marker"):
        _assert_reactive_compact_acceptance(report, old_marker_leaked)


def test_fake_compactor_proposal_does_not_echo_material_markers() -> None:
    """deterministic compact proposal 引用 material label 但不回写 material marker。

    :returns: ``None``。
    """

    proposal = _fake_compaction_proposal_from_material_json(
        {
            "trace_material": [{"label": "T1"}],
            "evidence_material": [
                {
                    "label": "E1",
                    "response_text": _SMOKE_REACTIVE_OLD_MARKER,
                }
            ],
            "answer_material": [
                {
                    "label": "A1",
                    "answer_text": _SMOKE_REACTIVE_OLD_MARKER,
                }
            ],
        }
    )
    parsed = json.loads(proposal)

    assert _SMOKE_REACTIVE_OLD_MARKER not in proposal
    assert parsed["session_summary"]["source_labels"] == ["T1", "E1", "A1"]
    assert parsed["evidence_backed_facts"][0]["evidence_labels"] == ["E1"]
    assert parsed["answer_anchors"][0]["answer_source_labels"] == ["A1"]


def test_fallback_acceptance_helper_requires_proactive_request_and_window() -> None:
    """fallback helper 要求 proactive request、dispatch fallback window 和 selected-only 输入。

    :returns: ``None``。
    """

    report = _fallback_report(include_request=True)
    observation = DeterministicSmokeObservation(
        dispatches=(
            _dispatch_capture(
                run_id="run-fallback-target",
                attempt_id="attempt-fallback",
                execution_id="execution-fallback",
                text=(
                    "DAYU_SMOKE_FALLBACK_SELECTED_RECENT_V1 "
                    "DAYU_SMOKE_FALLBACK_CURRENT_INPUT_V1"
                ),
            ),
        ),
        target_run_id="run-fallback-target",
        current_input_marker="DAYU_SMOKE_FALLBACK_CURRENT_INPUT_V1",
        protected_recent_marker="DAYU_SMOKE_FALLBACK_SELECTED_RECENT_V1",
        dropped_old_marker="DAYU_SMOKE_FALLBACK_DROPPED_OLD_V1",
        pressure_tokens=120,
        soft_threshold_tokens=100,
        hard_threshold_tokens=200,
    )

    _assert_fallback_dispatch_acceptance(report, observation)

    with pytest.raises(RuntimeError, match="proactive CONTEXT_COMPACTION_REQUESTED"):
        _assert_fallback_dispatch_acceptance(_fallback_report(include_request=False), observation)

    bad_pressure = DeterministicSmokeObservation(
        dispatches=observation.dispatches,
        target_run_id=observation.target_run_id,
        current_input_marker=observation.current_input_marker,
        protected_recent_marker=observation.protected_recent_marker,
        dropped_old_marker=observation.dropped_old_marker,
        pressure_tokens=90,
        soft_threshold_tokens=100,
        hard_threshold_tokens=200,
    )
    with pytest.raises(RuntimeError, match="below soft threshold"):
        _assert_fallback_dispatch_acceptance(report, bad_pressure)


def test_compact_audit_summary_maps_operation_id_to_request_trigger_source() -> None:
    """compact accepted / rejected row 通过 operation_id 归属到 request trigger。

    :returns: ``None``。
    """

    rows = (
        _event_row(
            sequence=1,
            event_id="event-context-compact-requested-1",
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload={"trigger_source": "proactive"},
        ),
        _event_row(
            sequence=2,
            event_id="event-context-compacted-1",
            event_type=CONTEXT_COMPACTED,
            payload={"operation_id": "event-context-compact-requested-1"},
        ),
        _event_row(
            sequence=3,
            event_id="event-context-compaction-attempt-rejected-1",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload={"operation_id": "event-context-compact-requested-1"},
        ),
    )

    summary = _compact_audit_summary_from_rows(rows)

    assert summary.requested_proactive == 1
    assert summary.compacted_proactive == 1
    assert summary.rejected_proactive == 1
    assert summary.compacted_reactive == 0


def test_compact_audit_report_prints_operation_histograms_and_manifest_stage(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """compact report 输出 operation timeline、histogram 与 manifest 缺失阶段。

    :param tmp_path: pytest 临时 workspace root。
    :param capsys: pytest stdout 捕获 fixture。
    :returns: ``None``。
    """

    rows = (
        _event_row(
            sequence=100,
            event_id="event-context-compact-requested-100",
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload={"trigger_source": "proactive"},
            run_id="run-request-100",
        ),
        _event_row(
            sequence=101,
            event_id="event-context-compaction-attempt-rejected-101",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload={
                "operation_id": "event-context-compact-requested-100",
                "attempt_number": 1,
                "failure_category": "invalid_candidate",
                "repairable": True,
                "next_policy_decision": "repair",
                "diagnostic_refs": [
                    "compact:operation:attempt:ValueError:previous reference continuity text is invalid",
                ],
                "budget_after_attempted_compact": 8192,
            },
            run_id="run-request-100",
        ),
        _event_row(
            sequence=102,
            event_id="event-context-compaction-attempt-rejected-102",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload={
                "operation_id": "event-context-compact-requested-100",
                "attempt_number": 2,
                "failure_category": "source_boundary",
                "repairable": True,
                "next_policy_decision": "repair",
                "diagnostic_refs": ["ValueError:short diagnostic"],
                "proposal_manifest_ref": "manifest-ref-102",
                "proposal_manifest_digest": "sha256:manifest",
            },
            run_id="run-request-100",
        ),
        _event_row(
            sequence=103,
            event_id="event-context-compacted-103",
            event_type=CONTEXT_COMPACTED,
            payload={"operation_id": "event-context-compact-requested-100"},
            run_id="run-request-100",
        ),
        _event_row(
            sequence=104,
            event_id="event-context-compaction-failed-104",
            event_type=CONTEXT_COMPACTION_FAILED,
            payload={
                "operation_id": "event-context-compact-requested-100",
                "failure_reason": "repair budget exhausted",
                "policy_decision": "fallback",
                "fallback_policy_decision": "deterministic_recent_window",
                "fallback_action": "dispatch",
                "fallback_tier": "tier4",
                "attempt_count": 2,
                "retry_repair_budget_exhausted": True,
                "budget_after_attempted_compact": 4096,
            },
            run_id="run-request-100",
        ),
    )

    report = _compact_audit_report_from_rows(rows)

    assert report.summary.requested_proactive == 1
    assert report.summary.rejected_proactive == 2
    assert report.summary.compacted_proactive == 1
    assert report.summary.failed_proactive == 1
    assert report.rejected_failure_histogram == (
        ("invalid_candidate", 1),
        ("source_boundary", 1),
    )
    assert report.rejected_diagnostic_histogram == (
        ("ValueError:short diagnostic", 1),
        ("previous reference continuity text is invalid", 1),
    )
    assert report.rejected_manifest_presence_histogram == (("missing", 1), ("present", 1))
    operation = report.operations[0]
    assert operation.operation_id == "event-context-compact-requested-100"
    assert operation.request_event_sequence == 100
    assert operation.run_id == "run-request-100"
    assert operation.compacted_event_sequences == (103,)
    assert operation.failed_events[0].fallback_action == "dispatch"

    with pytest.raises(RuntimeError, match="CONTEXT_COMPACTION_FAILED"):
        _assert_compact_acceptance(
            suite=SuiteMode.MEMORY_COMPACT,
            audit=report.summary,
            options=_prepare_runtime_assembly(_args(tmp_path), env={"DEEPSEEK_API_KEY": _API_KEY}).options,
        )

    _print_compact_audit_report(report, debug_smoke_output=True)
    output = capsys.readouterr().out

    assert "SMOKE COMPACT_OPERATION operation_id=event-context-compact-requested-100" in output
    assert "request_seq=100" in output
    assert "run_id=run-request-100" in output
    assert "fallback_action=dispatch" in output
    assert "kind=proposal_manifest_ref value='missing' count=1" in output
    assert "kind=proposal_manifest_ref value='present' count=1" in output
    assert "failure_stage=prepare_or_material_projection" in output
    assert "log_insufficient=offending_material_block_unavailable" in output
    for line in output.splitlines():
        assert line.startswith("SMOKE ")


def test_compact_audit_report_handles_empty_missing_and_malformed_payloads() -> None:
    """compact report 覆盖空 rows、缺失 operation id 与 malformed payload 边界。

    :returns: ``None``。
    """

    empty_report = _compact_audit_report_from_rows(())
    assert empty_report.operations == ()
    assert empty_report.rejected_failure_histogram == ()
    assert empty_report.rejected_diagnostic_histogram == ()
    assert empty_report.rejected_manifest_presence_histogram == ()

    missing_operation_report = _compact_audit_report_from_rows(
        (
            _event_row(
                sequence=1,
                event_id="event-context-compaction-attempt-rejected-missing-operation",
                event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                payload={
                    "attempt_number": "1",
                    "repairable": "true",
                    "diagnostic_refs": [],
                },
            ),
        )
    )
    operation = missing_operation_report.operations[0]
    attempt = operation.rejected_attempts[0]
    assert operation.operation_id == "<missing-operation-id>"
    assert attempt.attempt_number is None
    assert attempt.repairable is None
    assert attempt.diagnostic_refs == ()
    assert operation.diagnostic_histogram == ()
    assert missing_operation_report.rejected_manifest_presence_histogram == (("missing", 1),)

    with pytest.raises(ValueError, match="compact event payload must be object"):
        _compact_audit_report_from_rows(
            (
                _raw_payload_event_row(
                    sequence=2,
                    event_id="event-context-compaction-attempt-rejected-bad-payload",
                    event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                    payload="not-an-object",
                ),
            )
        )


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
                import_path=("utils.smoke_host_public_conversation_memory_scenarios:" "discover_smoke_tools")
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


def _dispatch_capture(
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    text: str,
) -> DeterministicDispatchCapture:
    """构造 deterministic dispatch capture。

    :param run_id: Host Run id。
    :param attempt_id: Host Attempt id。
    :param execution_id: execution id。
    :param text: joined message 文本。
    :returns: dispatch capture。
    """

    return DeterministicDispatchCapture(
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        joined_messages=text,
        system_message_count=1,
        system_message_at_start=True,
    )


def _fallback_report(*, include_request: bool) -> CompactAuditReport:
    """构造 fallback acceptance helper 测试用 report。

    :param include_request: 是否包含 proactive request row。
    :returns: compact audit report。
    """

    operation_id = "event-fallback-request" if include_request else "event-missing-request"
    request_rows = (
        (
            _event_row(
                sequence=1,
                event_id=operation_id,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                payload={"trigger_source": "proactive"},
                run_id="run-fallback-target",
            ),
        )
        if include_request
        else ()
    )
    return _compact_audit_report_from_rows(
        (
            *request_rows,
            _event_row(
                sequence=2,
                event_id="event-fallback-failed",
                event_type=CONTEXT_COMPACTION_FAILED,
                payload={
                    "operation_id": operation_id,
                    "failure_reason": "repair budget exhausted",
                    "policy_decision": "fallback",
                    "fallback_policy_decision": "deterministic_recent_window",
                    "fallback_action": "dispatch",
                    "fallback_tier": "tier4",
                    "attempt_count": 2,
                    "retry_repair_budget_exhausted": True,
                    "fallback_input_window": {
                        "selected_block_ids": ["history:recent", "current:event-current"],
                        "dropped_block_ids": ["history:old"],
                        "current_input_ref": "event-current",
                    },
                },
                run_id="run-fallback-target",
            ),
        )
    )


def _event_row(
    *,
    sequence: int,
    event_id: str,
    event_type: str,
    payload: Mapping[str, JsonValue],
    run_id: str | None = "run-compact-test",
) -> EventLogRow:
    """构造 compact audit helper 测试用 EventLog row。

    :param sequence: EventLog sequence。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: payload JSON object。
    :param run_id: Host run id。
    :returns: EventLogRow。
    """

    return EventLogRow(
        event_sequence=sequence,
        event_id=event_id,
        event_body_digest=f"sha256:{'0' * 64}",
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-compact-test",
        run_id=run_id,
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at="2026-06-19T00:00:00.000000Z",
        actor=None,
        source=None,
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        payload_ref=None,
        payload_digest=None,
        appended_at="2026-06-19T00:00:00.000000Z",
    )


def _raw_payload_event_row(
    *,
    sequence: int,
    event_id: str,
    event_type: str,
    payload: JsonValue,
) -> EventLogRow:
    """构造任意 JSON payload 的 EventLog row。

    :param sequence: EventLog sequence。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: 任意 JSON payload。
    :returns: EventLogRow。
    """

    return EventLogRow(
        event_sequence=sequence,
        event_id=event_id,
        event_body_digest=f"sha256:{'0' * 64}",
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-compact-test",
        run_id="run-compact-test",
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at="2026-06-19T00:00:00.000000Z",
        actor=None,
        source=None,
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        payload_ref=None,
        payload_digest=None,
        appended_at="2026-06-19T00:00:00.000000Z",
    )


def _args(
    workspace_root: pathlib.Path,
    *,
    suite: SuiteMode = SuiteMode.MEMORY_CORE,
    long_rounds: int = 25,
    reuse_session: bool = False,
    pressure_mode: PressureMode = PressureMode.OFF,
) -> SmokeArgs:
    """构造测试用 smoke 参数。

    :param workspace_root: pytest 临时 workspace root。
    :param suite: 场景套件模式。
    :param long_rounds: long suite 轮数。
    :param reuse_session: 是否复用稳定 session slot。
    :param pressure_mode: 压力注入方式。
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
        pressure_mode=pressure_mode,
        debug_smoke_output=False,
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

    config_dir = workspace_root / "config"
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
        execution=AsyncDirectToolExecutionCapability(),
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
                import_path=("utils.smoke_host_public_conversation_memory_scenarios:" "discover_smoke_tools")
            ),
        )
    )
    discovered_bundle = ToolBundle(definitions=provider_output.definitions)

    assert len(discovered_bundle.definitions) == 1
    assert isinstance(discovered_bundle.definitions[0].callable, MockFinanceMemoryTool)
