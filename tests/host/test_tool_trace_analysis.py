"""Tool Trace Analyzer public orchestration 与 renderer 测试。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import dayu.host as host_public
import dayu.host.tool_trace_analysis as analysis_module
import dayu.host.tool_trace_analysis_contracts as analysis_contracts
from dayu.host.tool_trace_analysis import (
    analyze_tool_trace,
    render_tool_trace_analysis_markdown,
    tool_trace_analysis_report_to_json,
)
from dayu.host.tool_trace_analysis_contracts import (
    ToolTraceAnalysisCapabilities,
    ToolTraceCompactorResponseSummary,
    ToolTraceAnalysisInputSummary,
    ToolTraceAnalysisLayer,
    ToolTraceAnalysisPolicy,
    ToolTraceAnalysisReport,
    ToolTraceAnalysisSource,
    ToolTraceAnalysisSummary,
    ToolTraceEvidence,
    ToolTraceEvidenceKind,
    ToolTraceFinding,
    ToolTraceFindingPriority,
    ToolTraceFindingSeverity,
    ToolTraceInputMode,
    ToolTraceLimitation,
    ToolTracePayloadMeasurementSource,
    ToolTracePayloadMeasure,
    ToolTraceRunSummary,
    ToolTraceSignalStatus,
    ToolTraceVendorDebuggingBlock,
)
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    build_runner_request_identity,
)
from dayu.host.durable.tool_trace import (
    CompactorResponseDisposition,
    ResolvedCompactorEvidenceFact,
)


def _source(tmp_path: Path) -> ToolTraceAnalysisSource:
    """创建合法空 cold-file source。

    :param tmp_path: pytest 临时目录。
    :returns: public source。
    :raises OSError: 创建文件失败时抛出。
    """

    cold_path = (tmp_path / "tool-trace-cold.jsonl").absolute()
    cold_path.write_text("", encoding="utf-8")
    return ToolTraceAnalysisSource(
        requested_path=cold_path,
        mode=ToolTraceInputMode.COLD_FILE,
        cold_jsonl_path=cold_path,
        hot_db_path=None,
        artifact_root=None,
    )


def _valid_finding(source_path: Path) -> ToolTraceFinding:
    """创建具有 direct evidence 的合法 public finding。

    :param source_path: finding evidence 来源路径。
    :returns: 已分配非空 id 的 public finding。
    :raises: 无。
    """

    evidence = ToolTraceEvidence(
        kind=ToolTraceEvidenceKind.COLD_LINE,
        source_path=source_path,
        line_number=1,
        event_id="event-1",
        event_sequence=1,
        event_type="TOOL_RESULT_ACCEPTED",
        trace_ref="tool-trace-cold:event-1",
        payload_ref=None,
        observed={"status": "failed"},
    )
    return ToolTraceFinding(
        finding_id="TT-HOST-0001",
        rule_id="host.example",
        layer=ToolTraceAnalysisLayer.HOST,
        severity=ToolTraceFindingSeverity.WARNING,
        priority=ToolTraceFindingPriority.MEDIUM,
        title="Host example",
        summary="Host direct evidence example。",
        recommendation="检查 Host owner。",
        evidence=(evidence,),
    )


def test_contract_owner_exports_complete_public_report_surface() -> None:
    """Contracts owner 的 ``__all__`` 精确覆盖冻结 public surface。"""

    assert set(analysis_contracts.__all__) == {
        "DEFAULT_TOOL_TRACE_LARGE_PAYLOAD_THRESHOLD_BYTES",
        "DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_DELTA_MS",
        "DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_SAMPLE_COUNT",
        "DEFAULT_TOOL_TRACE_LATENCY_OUTLIER_MULTIPLIER",
        "DEFAULT_TOOL_TRACE_PAYLOAD_RANKING_LIMIT",
        "ToolTraceAnalysisCapabilities",
        "ToolTraceCompactorResponseSummary",
        "ToolTraceAnalysisInputSummary",
        "ToolTraceAnalysisLayer",
        "ToolTraceAnalysisPolicy",
        "ToolTraceAnalysisReport",
        "ToolTraceAnalysisSource",
        "ToolTraceAnalysisSummary",
        "ToolTraceEvidence",
        "ToolTraceEvidenceKind",
        "ToolTraceFinding",
        "ToolTraceFindingPriority",
        "ToolTraceFindingSeverity",
        "ToolTraceInputMode",
        "ToolTraceLimitation",
        "ToolTracePayloadMeasurementSource",
        "ToolTracePayloadMeasure",
        "ToolTraceRunSummary",
        "ToolTraceSignalCoverage",
        "ToolTraceSignalStatus",
        "ToolTraceVendorDebuggingBlock",
    }


def test_analysis_module_owner_exports_only_three_public_functions() -> None:
    """Analysis module owner 只声明三个 public functions。"""

    assert set(analysis_module.__all__) == {
        "analyze_tool_trace",
        "render_tool_trace_analysis_markdown",
        "tool_trace_analysis_report_to_json",
    }
    assert {
        "build_tool_trace_analysis_report",
        "load_tool_trace_analysis_input",
    }.isdisjoint(analysis_module.__all__)


def test_input_summary_validates_typed_facts_and_capability_relations(
    tmp_path: Path,
) -> None:
    """InputSummary 只接受 typed paths 与可自证的 capability/watermark 关系。"""

    report = analyze_tool_trace(_source(tmp_path), ToolTraceAnalysisPolicy())
    input_summary = report.input
    hot_capabilities = ToolTraceAnalysisCapabilities(
        cold=input_summary.capabilities.cold,
        hot=True,
        payload_resolution=False,
    )
    payload_capabilities = ToolTraceAnalysisCapabilities(
        cold=input_summary.capabilities.cold,
        hot=False,
        payload_resolution=True,
    )

    with pytest.raises(TypeError, match="requested_path"):
        replace(
            input_summary,
            requested_path=cast(Path, "not-path"),
        )
    with pytest.raises(TypeError, match="mode"):
        replace(
            input_summary,
            mode=cast(ToolTraceInputMode, "not-mode"),
        )
    with pytest.raises(TypeError, match="capabilities"):
        replace(
            input_summary,
            capabilities=cast(
                ToolTraceAnalysisCapabilities,
                "not-capabilities",
            ),
        )
    with pytest.raises(ValueError, match="non-negative"):
        replace(input_summary, hot_event_sequence_watermark=-1)
    with pytest.raises(ValueError, match="watermark requires hot"):
        replace(input_summary, hot_event_sequence_watermark=0)
    with pytest.raises(ValueError, match="requires hot_db_path"):
        replace(
            input_summary,
            capabilities=hot_capabilities,
            hot_event_sequence_watermark=0,
        )
    with pytest.raises(ValueError, match="requires hot watermark"):
        replace(
            input_summary,
            capabilities=hot_capabilities,
            hot_db_path=tmp_path / "dayu_host.sqlite3",
        )
    with pytest.raises(ValueError, match="payload resolution requires"):
        replace(
            input_summary,
            capabilities=payload_capabilities,
            artifact_root=tmp_path / "artifacts",
        )

    valid_hot = replace(
        input_summary,
        capabilities=hot_capabilities,
        hot_db_path=tmp_path / "dayu_host.sqlite3",
        hot_event_sequence_watermark=0,
    )
    assert isinstance(valid_hot, ToolTraceAnalysisInputSummary)


def test_finding_and_report_reject_invalid_final_finding_ids(
    tmp_path: Path,
) -> None:
    """Public finding 拒绝空 id，report 边界拒绝缺失或重复 id。"""

    report = analyze_tool_trace(_source(tmp_path), ToolTraceAnalysisPolicy())
    finding = _valid_finding(report.input.cold_jsonl_path)

    with pytest.raises(ValueError, match="finding_id"):
        replace(finding, finding_id="")

    duplicated_summary = replace(report.summary, finding_count=2)
    with pytest.raises(ValueError, match="must be unique"):
        replace(
            report,
            summary=duplicated_summary,
            findings=(finding, finding),
        )

    # 模拟越过 nested dataclass constructor 的损坏对象，验证 report 自身仍守边界。
    missing_id_finding = replace(finding)
    object.__setattr__(missing_id_finding, "finding_id", "")
    missing_summary = replace(report.summary, finding_count=1)
    with pytest.raises(ValueError, match="must be non-empty"):
        replace(
            report,
            summary=missing_summary,
            findings=(missing_id_finding,),
        )


def test_report_rejects_run_count_mismatch(tmp_path: Path) -> None:
    """Report 只接受与 runs 数量一致的 summary run_count。"""

    report = analyze_tool_trace(_source(tmp_path), ToolTraceAnalysisPolicy())

    with pytest.raises(ValueError, match="run_count must match runs"):
        replace(
            report,
            summary=replace(report.summary, run_count=1),
        )


def test_public_analyzer_builds_deterministic_final_report_shape(
    tmp_path: Path,
) -> None:
    """Public analyzer 对显式 source 返回冻结顶层 schema。"""

    source = _source(tmp_path)
    policy = ToolTraceAnalysisPolicy()

    first = analyze_tool_trace(source, policy)
    second = analyze_tool_trace(source, policy)
    first_json = tool_trace_analysis_report_to_json(first)
    second_json = tool_trace_analysis_report_to_json(second)
    parsed = json.loads(first_json)

    assert first_json == second_json
    assert list(parsed) == sorted(parsed)
    assert set(parsed) == {
        "schema_version",
        "compactor_responses",
        "input",
        "policy",
        "summary",
        "signal_coverage",
        "runs",
        "payload_rankings",
        "vendor_debugging",
        "findings",
        "limitations",
    }
    assert parsed["schema_version"] == 2
    assert parsed["compactor_responses"] == []
    assert parsed["vendor_debugging"] == []
    assert parsed["input"]["cold_jsonl_path"] == str(source.cold_jsonl_path)
    assert parsed["input"]["cold_lock_path"] == (
        str(source.cold_jsonl_path) + ".lock"
    )
    assert parsed["summary"]["finding_count"] == 0
    assert {
        item["reason_code"] for item in parsed["limitations"]
    } >= {"hot_store_unavailable", "payload_resolution_unavailable"}


def test_compactor_response_summary_json_markdown_share_safe_typed_source(
    tmp_path: Path,
) -> None:
    """JSON/Markdown 只从同一 v2 typed summary 公开实际 response identity。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 两种 renderer 不同源或泄漏非白名单字段时抛出。
    """

    report = analyze_tool_trace(_source(tmp_path), ToolTraceAnalysisPolicy())
    request_identity = build_runner_request_identity(
        run_id="compactor-engine-run-1",
        attempt_id=None,
        execution_id=None,
        iteration_id="iteration-final",
        iteration_index=1,
        runner_call_index=2,
    )
    response = ToolTraceCompactorResponseSummary(
        parent_host_run_id="parent-run-1",
        disposition=CompactorResponseDisposition.ACCEPTED,
        terminal_event_id="event-compacted-1",
        terminal_event_sequence=11,
        compaction_operation_id="operation-1",
        compaction_attempt_number=1,
        proposal_manifest_ref="payload-manifest-1",
        proposal_manifest_digest="sha256:" + "a" * 64,
        effective_provider="provider-actual",
        effective_model="model-actual",
        runner_request_identity=request_identity,
        provider_request_id_availability=ProviderRequestIdAvailability.PRESENT,
        provider_request_id="provider-request-actual",
        accepted_evidence_facts=(
            ResolvedCompactorEvidenceFact(
                claim="Revenue increased by 21.7%.",
                canonical_evidence_refs=(
                    "evidence:canonical-1",
                    "evidence:canonical-2",
                ),
            ),
        ),
    )
    with_response = replace(report, compactor_responses=(response,))

    serialized = json.loads(tool_trace_analysis_report_to_json(with_response))
    markdown = render_tool_trace_analysis_markdown(with_response)
    projected = serialized["compactor_responses"][0]

    assert projected["effective_provider"] == "provider-actual"
    assert projected["effective_model"] == "model-actual"
    assert projected["provider_request_id_availability"] == "present"
    assert projected["provider_request_id"] == "provider-request-actual"
    assert projected["runner_request_identity"]["client_correlation_id"] == (
        request_identity.client_correlation_id
    )
    assert projected["accepted_evidence_facts"] == [
        {
            "claim": "Revenue increased by 21.7%.",
            "canonical_evidence_refs": [
                "evidence:canonical-1",
                "evidence:canonical-2",
            ],
        }
    ]
    assert set(projected["accepted_evidence_facts"][0]) == {
        "claim",
        "canonical_evidence_refs",
    }
    for expected in (
        "provider-actual",
        "model-actual",
        "provider-request-actual",
        request_identity.client_correlation_id,
        "Revenue increased by 21.7%.",
        "evidence:canonical-1",
        "evidence:canonical-2",
    ):
        assert expected in markdown
    rendered_text = tool_trace_analysis_report_to_json(with_response) + markdown
    for forbidden in (
        "Authorization",
        "credential",
        "api_key",
        "raw_request",
        "raw_response",
        "selection-label-secret",
        "raw-payload-secret",
        "credential-secret",
        "prompt-secret",
    ):
        assert forbidden not in rendered_text


def test_no_success_compactor_response_requires_typed_null_identity(
    tmp_path: Path,
) -> None:
    """no-success rejection 的 provider/model/request identity 必须整体为 null。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: typed null 未被 JSON renderer 保留时抛出。
    """

    report = analyze_tool_trace(_source(tmp_path), ToolTraceAnalysisPolicy())
    response = ToolTraceCompactorResponseSummary(
        parent_host_run_id="parent-run-1",
        disposition=CompactorResponseDisposition.ATTEMPT_REJECTED,
        terminal_event_id="event-rejected-1",
        terminal_event_sequence=12,
        compaction_operation_id="operation-1",
        compaction_attempt_number=2,
        proposal_manifest_ref="payload-manifest-2",
        proposal_manifest_digest="sha256:" + "b" * 64,
        effective_provider=None,
        effective_model=None,
        runner_request_identity=None,
        provider_request_id_availability=None,
        provider_request_id=None,
        accepted_evidence_facts=(),
    )
    payload = json.loads(
        tool_trace_analysis_report_to_json(
            replace(report, compactor_responses=(response,))
        )
    )["compactor_responses"][0]

    assert payload["effective_provider"] is None
    assert payload["effective_model"] is None
    assert payload["runner_request_identity"] is None
    assert payload["provider_request_id_availability"] is None
    assert payload["provider_request_id"] is None
    with pytest.raises(ValueError, match="all be null"):
        replace(response, effective_provider="inferred-provider")
    with pytest.raises(ValueError, match="accepted.*requires successful identity"):
        replace(response, disposition=CompactorResponseDisposition.ACCEPTED)


def test_vendor_block_final_contract_serializes_without_schema_change(
    tmp_path: Path,
) -> None:
    """S2 冻结的 vendor block 即使本 Slice 不生成也可完整序列化。"""

    report = analyze_tool_trace(_source(tmp_path), ToolTraceAnalysisPolicy())
    evidence = ToolTraceEvidence(
        kind=ToolTraceEvidenceKind.COLD_LINE,
        source_path=report.input.cold_jsonl_path,
        line_number=1,
        event_id="event-provider",
        event_sequence=1,
        event_type="PROVIDER_PROTOCOL_ERROR",
        trace_ref="tool-trace-cold:event-provider",
        payload_ref=None,
        observed={"provider_request_id": "provider-1"},
    )
    limitation = ToolTraceLimitation(
        reason_code="iteration_id_unavailable",
        signal_status=ToolTraceSignalStatus.LIMITED_SIGNAL,
        summary="iteration id 不可验证。",
        evidence=(evidence,),
    )
    block = ToolTraceVendorDebuggingBlock(
        status=ToolTraceSignalStatus.LIMITED_SIGNAL,
        provider_request_id="provider-1",
        client_correlation_id=None,
        session_id="session-1",
        run_id="run-1",
        attempt_ids=("attempt-1",),
        execution_ids=("execution-1",),
        iteration_ids=(),
        tool_trace_refs=(evidence,),
        diagnostic_refs=("diagnostic-1",),
        partial_tool_call_signal=ToolTraceSignalStatus.NOT_APPLICABLE,
        limitations=(limitation,),
    )
    with_vendor = replace(report, vendor_debugging=(block,))

    payload = json.loads(tool_trace_analysis_report_to_json(with_vendor))
    serialized = payload["vendor_debugging"][0]

    assert set(serialized) == {
        "status",
        "provider_request_id",
        "client_correlation_id",
        "session_id",
        "run_id",
        "attempt_ids",
        "execution_ids",
        "iteration_ids",
        "tool_trace_refs",
        "diagnostic_refs",
        "partial_tool_call_signal",
        "limitations",
    }
    assert serialized["provider_request_id"] == "provider-1"
    assert serialized["client_correlation_id"] is None
    assert serialized["iteration_ids"] == []


def test_nonempty_report_json_and_markdown_render_all_structured_sections(
    tmp_path: Path,
) -> None:
    """Renderer 对非空 finding/run/payload/vendor 只消费同一 report。"""

    report = analyze_tool_trace(_source(tmp_path), ToolTraceAnalysisPolicy())
    evidence = ToolTraceEvidence(
        kind=ToolTraceEvidenceKind.COLD_LINE,
        source_path=report.input.cold_jsonl_path,
        line_number=1,
        event_id="event-1",
        event_sequence=1,
        event_type="TOOL_RESULT_ACCEPTED",
        trace_ref="tool-trace-cold:event-1",
        payload_ref="payload-1",
        observed={"status": "failed|bounded\ntext"},
    )
    finding = ToolTraceFinding(
        finding_id="TT-HOST-0001",
        rule_id="host.policy_blocked",
        layer=ToolTraceAnalysisLayer.HOST,
        severity=ToolTraceFindingSeverity.WARNING,
        priority=ToolTraceFindingPriority.MEDIUM,
        title="Policy blocked",
        summary="Host `policy` blocked",
        recommendation="检查 Host policy。",
        evidence=(evidence,),
    )
    payload_measure = ToolTracePayloadMeasure(
        category="cold_line",
        measurement_source=(
            ToolTracePayloadMeasurementSource.COLD_JSONL_RECORD_BYTES
        ),
        size_bytes=123,
        event_sequence=1,
        payload_ref="tool-trace-cold:event-1",
        evidence=(evidence,),
    )
    run = ToolTraceRunSummary(
        run_id="run-1",
        session_ids=("session-1",),
        attempt_ids=("attempt-1",),
        execution_ids=("execution-1",),
        tool_call_ids=("call-1",),
        tool_names=("lookup",),
        provider_request_ids=(),
        client_correlation_ids=(),
        diagnostic_refs=(),
        event_count=1,
        tool_request_count=0,
        tool_result_count=1,
        tool_timing_sample_count=0,
        context_pressure_observation_count=0,
        tool_awaiting_count=0,
        run_waiting_count=0,
    )
    vendor_limitation = ToolTraceLimitation(
        reason_code="provider_request_id_unavailable",
        signal_status=ToolTraceSignalStatus.LIMITED_SIGNAL,
        summary="provider-native request id 无法验证。",
        evidence=(evidence,),
    )
    vendor = ToolTraceVendorDebuggingBlock(
        status=ToolTraceSignalStatus.LIMITED_SIGNAL,
        provider_request_id=None,
        client_correlation_id="client-1",
        session_id="session-1",
        run_id="run-1",
        attempt_ids=("attempt-1",),
        execution_ids=("execution-1",),
        iteration_ids=(),
        tool_trace_refs=(evidence,),
        diagnostic_refs=(),
        partial_tool_call_signal=ToolTraceSignalStatus.NOT_APPLICABLE,
        limitations=(vendor_limitation,),
    )
    nonempty = replace(
        report,
        input=replace(
            report.input,
            hot_db_path=tmp_path / "host.sqlite3",
            artifact_root=tmp_path / "artifacts",
        ),
        summary=ToolTraceAnalysisSummary(
            valid_record_count=1,
            invalid_record_count=0,
            run_count=1,
            tool_call_count=1,
            finding_count=1,
            limitation_count=len(report.limitations),
        ),
        runs=(run,),
        payload_rankings=(payload_measure,),
        vendor_debugging=(vendor,),
        findings=(finding,),
    )

    serialized = json.loads(tool_trace_analysis_report_to_json(nonempty))
    markdown = render_tool_trace_analysis_markdown(nonempty)

    assert serialized["runs"][0]["run_id"] == "run-1"
    assert serialized["payload_rankings"][0]["measurement_source"] == (
        "cold_jsonl_record_bytes"
    )
    assert serialized["findings"][0]["rule_id"] == "host.policy_blocked"
    assert serialized["input"]["hot_db_path"].endswith("host.sqlite3")
    assert "TT-HOST-0001" in markdown
    assert "client_correlation_id=`client-1`" in markdown
    assert "attempts=`attempt-1`" in markdown
    assert "partial_tool_call_signal=`not_applicable`" in markdown
    assert "provider_request_id_unavailable" in markdown
    assert "run=`run-1`" in markdown
    assert "123 bytes" in markdown
    assert "检查 Host policy。" in markdown
    assert "failed\\|bounded" in markdown
    assert "\nbounded" not in markdown


def test_markdown_uses_structured_report_and_distinguishes_record_bytes(
    tmp_path: Path,
) -> None:
    """Markdown 固定章节齐全且不把 cold line 称为 raw payload。"""

    report = analyze_tool_trace(_source(tmp_path), ToolTraceAnalysisPolicy())

    markdown = render_tool_trace_analysis_markdown(report)

    assert "## 输入与 signal coverage" in markdown
    assert "## Host findings" in markdown
    assert "## Engine findings" in markdown
    assert "## Tool findings" in markdown
    assert "## Vendor debugging" in markdown
    assert "## Large payload ranking" in markdown
    assert "## Run / attempt / tool-call chain" in markdown
    assert "## Limitations" in markdown
    assert "## Recommended next actions" in markdown
    assert "JSONL record bytes" in markdown
    assert "无法证明" in markdown
    assert "原始 payload" not in markdown


def test_public_package_exports_final_contract_and_functions() -> None:
    """Host package root 公开 S2 最终 report contract 与 renderer。"""

    expected_names = (
        "ToolTraceAnalysisReport",
        "ToolTraceFinding",
        "ToolTraceLimitation",
        "ToolTracePayloadMeasure",
        "ToolTraceRunSummary",
        "ToolTraceVendorDebuggingBlock",
        "analyze_tool_trace",
        "tool_trace_analysis_report_to_json",
        "render_tool_trace_analysis_markdown",
    )

    assert all(name in host_public.__all__ for name in expected_names)
    assert host_public.analyze_tool_trace is analyze_tool_trace


def test_public_functions_reject_untyped_arguments(tmp_path: Path) -> None:
    """Public analyzer/renderers 不接受 untyped fallback 输入。"""

    source = _source(tmp_path)
    report = analyze_tool_trace(source, ToolTraceAnalysisPolicy())

    with pytest.raises(TypeError, match="source"):
        analyze_tool_trace(
            cast(ToolTraceAnalysisSource, "not-source"),
            ToolTraceAnalysisPolicy(),
        )
    with pytest.raises(TypeError, match="policy"):
        analyze_tool_trace(
            source,
            cast(ToolTraceAnalysisPolicy, "not-policy"),
        )
    with pytest.raises(TypeError, match="report"):
        tool_trace_analysis_report_to_json(
            cast(ToolTraceAnalysisReport, "not-report")
        )
    with pytest.raises(TypeError, match="report"):
        render_tool_trace_analysis_markdown(
            cast(ToolTraceAnalysisReport, "not-report")
        )
    assert report.schema_version == 2
    with pytest.raises(ValueError, match="schema_version must be 2"):
        replace(report, schema_version=1)
