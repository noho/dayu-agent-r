"""Tool Trace Analyzer 的公开编排与 deterministic report renderer。

本模块只接受显式 ``ToolTraceAnalysisSource`` 与 typed policy，委托 Slice 1
读取可信 dataset，再委托规则 owner 构造 immutable report。JSON/Markdown renderer
只消费 report，不重新读取输入或执行规则。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.options import HostSQLiteStoragePolicy
from dayu.host.tool_trace_analysis_contracts import (
    ToolTraceAnalysisInputSummary,
    ToolTraceAnalysisPolicy,
    ToolTraceAnalysisReport,
    ToolTraceAnalysisSource,
    ToolTraceAnalysisSummary,
    ToolTraceEvidence,
    ToolTraceFinding,
    ToolTraceLimitation,
    ToolTracePayloadMeasure,
    ToolTraceRunSummary,
    ToolTraceSignalCoverage,
    ToolTraceVendorDebuggingBlock,
)
from dayu.host.tool_trace_analysis_input import load_tool_trace_analysis_input
from dayu.host.tool_trace_analysis_rules import build_tool_trace_analysis_report

__all__ = (
    "analyze_tool_trace",
    "render_tool_trace_analysis_markdown",
    "tool_trace_analysis_report_to_json",
)

_MARKDOWN_SECTIONS = (
    "输入与 signal coverage",
    "Executive summary",
    "Host findings",
    "Engine findings",
    "Tool findings",
    "Vendor debugging",
    "Large payload ranking",
    "Run / attempt / tool-call chain",
    "Limitations",
    "Recommended next actions",
)


def analyze_tool_trace(
    source: ToolTraceAnalysisSource,
    policy: ToolTraceAnalysisPolicy,
) -> ToolTraceAnalysisReport:
    """读取显式可信输入并构造 structured Tool Trace report。

    :param source: 已由 public boundary 校验的显式输入来源。
    :param policy: 本次实际诊断阈值。
    :returns: immutable schema version 1 report。
    :raises TypeError: 参数类型错误时抛出。
    :raises ToolTraceAnalysisInputError: 输入读取、hot schema 或 cold snapshot
        无法建立可信边界时抛出。
    """

    if not isinstance(source, ToolTraceAnalysisSource):
        raise TypeError("source must be ToolTraceAnalysisSource")
    if not isinstance(policy, ToolTraceAnalysisPolicy):
        raise TypeError("policy must be ToolTraceAnalysisPolicy")
    dataset = load_tool_trace_analysis_input(
        source,
        policy,
        HostSQLiteStoragePolicy(),
    )
    return build_tool_trace_analysis_report(dataset, source, policy)


def tool_trace_analysis_report_to_json(
    report: ToolTraceAnalysisReport,
) -> str:
    """把 structured report 序列化为 deterministic UTF-8 JSON 文本。

    :param report: immutable Analyzer report。
    :returns: 带末尾换行的 deterministic JSON。
    :raises TypeError: report 类型错误时抛出。
    """

    if not isinstance(report, ToolTraceAnalysisReport):
        raise TypeError("report must be ToolTraceAnalysisReport")
    return (
        json.dumps(
            _report_json(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def render_tool_trace_analysis_markdown(
    report: ToolTraceAnalysisReport,
) -> str:
    """从同一个 structured report 渲染 bounded Markdown。

    :param report: immutable Analyzer report。
    :returns: 带末尾换行的 Markdown report。
    :raises TypeError: report 类型错误时抛出。
    """

    if not isinstance(report, ToolTraceAnalysisReport):
        raise TypeError("report must be ToolTraceAnalysisReport")
    sections = [
        "# Tool Trace Analysis",
        _render_input_and_coverage(report),
        _render_executive_summary(report.summary),
        _render_finding_section(report, layer="host", title=_MARKDOWN_SECTIONS[2]),
        _render_finding_section(
            report,
            layer="engine",
            title=_MARKDOWN_SECTIONS[3],
        ),
        _render_finding_section(report, layer="tool", title=_MARKDOWN_SECTIONS[4]),
        _render_vendor_debugging(report.vendor_debugging),
        _render_payload_rankings(report.payload_rankings),
        _render_runs(report.runs),
        _render_limitations(report.limitations),
        _render_recommended_actions(report.findings),
    ]
    return "\n\n".join(sections) + "\n"


def _report_json(report: ToolTraceAnalysisReport) -> Mapping[str, JsonValue]:
    """把 report 显式投影为固定顶层 schema。

    :param report: structured report。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "schema_version": report.schema_version,
        "input": _input_json(report.input),
        "policy": {
            "large_payload_threshold_bytes": (
                report.policy.large_payload_threshold_bytes
            ),
            "payload_ranking_limit": report.policy.payload_ranking_limit,
            "latency_minimum_sample_count": (
                report.policy.latency_minimum_sample_count
            ),
            "latency_outlier_multiplier": (
                report.policy.latency_outlier_multiplier
            ),
            "latency_minimum_delta_ms": (
                report.policy.latency_minimum_delta_ms
            ),
        },
        "summary": _summary_json(report.summary),
        "signal_coverage": [
            _signal_coverage_json(item) for item in report.signal_coverage
        ],
        "runs": [_run_json(item) for item in report.runs],
        "payload_rankings": [
            _payload_measure_json(item) for item in report.payload_rankings
        ],
        "vendor_debugging": [
            _vendor_block_json(item) for item in report.vendor_debugging
        ],
        "findings": [_finding_json(item) for item in report.findings],
        "limitations": [
            _limitation_json(item) for item in report.limitations
        ],
    }


def _input_json(item: ToolTraceAnalysisInputSummary) -> Mapping[str, JsonValue]:
    """投影 structured input summary。

    :param item: input summary。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "requested_path": str(item.requested_path),
        "mode": item.mode.value,
        "cold_jsonl_path": str(item.cold_jsonl_path),
        "cold_lock_path": str(item.cold_lock_path),
        "hot_db_path": _path_text(item.hot_db_path),
        "artifact_root": _path_text(item.artifact_root),
        "capabilities": {
            "cold": item.capabilities.cold,
            "hot": item.capabilities.hot,
            "payload_resolution": item.capabilities.payload_resolution,
        },
        "hot_event_sequence_watermark": item.hot_event_sequence_watermark,
    }


def _summary_json(item: ToolTraceAnalysisSummary) -> Mapping[str, JsonValue]:
    """投影顶层 report summary。

    :param item: report summary。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "valid_record_count": item.valid_record_count,
        "invalid_record_count": item.invalid_record_count,
        "run_count": item.run_count,
        "tool_call_count": item.tool_call_count,
        "finding_count": item.finding_count,
        "limitation_count": item.limitation_count,
    }


def _signal_coverage_json(
    item: ToolTraceSignalCoverage,
) -> Mapping[str, JsonValue]:
    """投影 signal coverage。

    :param item: signal coverage。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "signal_name": item.signal_name,
        "status": item.status.value,
        "reason_codes": list(item.reason_codes),
    }


def _run_json(item: ToolTraceRunSummary) -> Mapping[str, JsonValue]:
    """投影 Run summary。

    :param item: Run summary。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "run_id": item.run_id,
        "session_ids": list(item.session_ids),
        "attempt_ids": list(item.attempt_ids),
        "execution_ids": list(item.execution_ids),
        "tool_call_ids": list(item.tool_call_ids),
        "tool_names": list(item.tool_names),
        "provider_request_ids": list(item.provider_request_ids),
        "client_correlation_ids": list(item.client_correlation_ids),
        "diagnostic_refs": list(item.diagnostic_refs),
        "event_count": item.event_count,
        "tool_request_count": item.tool_request_count,
        "tool_result_count": item.tool_result_count,
        "tool_timing_sample_count": item.tool_timing_sample_count,
        "context_pressure_observation_count": (
            item.context_pressure_observation_count
        ),
        "tool_awaiting_count": item.tool_awaiting_count,
        "run_waiting_count": item.run_waiting_count,
    }


def _payload_measure_json(
    item: ToolTracePayloadMeasure,
) -> Mapping[str, JsonValue]:
    """投影 verified byte measure。

    :param item: payload measure。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "category": item.category,
        "measurement_source": item.measurement_source.value,
        "size_bytes": item.size_bytes,
        "event_sequence": item.event_sequence,
        "payload_ref": item.payload_ref,
        "evidence": [_evidence_json(value) for value in item.evidence],
    }


def _vendor_block_json(
    item: ToolTraceVendorDebuggingBlock,
) -> Mapping[str, JsonValue]:
    """投影冻结 vendor debugging block shape。

    :param item: vendor block。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "status": item.status.value,
        "provider_request_id": item.provider_request_id,
        "client_correlation_id": item.client_correlation_id,
        "session_id": item.session_id,
        "run_id": item.run_id,
        "attempt_ids": list(item.attempt_ids),
        "execution_ids": list(item.execution_ids),
        "iteration_ids": list(item.iteration_ids),
        "tool_trace_refs": [
            _evidence_json(value) for value in item.tool_trace_refs
        ],
        "diagnostic_refs": list(item.diagnostic_refs),
        "partial_tool_call_signal": item.partial_tool_call_signal.value,
        "limitations": [
            _limitation_json(value) for value in item.limitations
        ],
    }


def _finding_json(item: ToolTraceFinding) -> Mapping[str, JsonValue]:
    """投影 confirmed finding。

    :param item: finding。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "finding_id": item.finding_id,
        "rule_id": item.rule_id,
        "layer": item.layer.value,
        "severity": item.severity.value,
        "priority": item.priority.value,
        "title": item.title,
        "summary": item.summary,
        "recommendation": item.recommendation,
        "evidence": [_evidence_json(value) for value in item.evidence],
    }


def _limitation_json(item: ToolTraceLimitation) -> Mapping[str, JsonValue]:
    """投影 structured limitation。

    :param item: limitation。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "reason_code": item.reason_code,
        "signal_status": item.signal_status.value,
        "summary": item.summary,
        "evidence": [_evidence_json(value) for value in item.evidence],
    }


def _evidence_json(item: ToolTraceEvidence) -> Mapping[str, JsonValue]:
    """投影 direct evidence，不读取 raw payload。

    :param item: evidence。
    :returns: JSON object。
    :raises: 无。
    """

    return {
        "kind": item.kind.value,
        "source_path": str(item.source_path),
        "line_number": item.line_number,
        "event_id": item.event_id,
        "event_sequence": item.event_sequence,
        "event_type": item.event_type,
        "trace_ref": item.trace_ref,
        "payload_ref": item.payload_ref,
        "observed": dict(item.observed),
    }


def _path_text(path: Path | None) -> str | None:
    """把可选 Path 投影为文本。

    :param path: 可选路径。
    :returns: 路径文本或 ``None``。
    :raises: 无。
    """

    return None if path is None else str(path)


def _render_input_and_coverage(report: ToolTraceAnalysisReport) -> str:
    """渲染输入与 signal coverage 章节。

    :param report: structured report。
    :returns: Markdown section。
    :raises: 无。
    """

    lines = [
        f"## {_MARKDOWN_SECTIONS[0]}",
        "",
        f"- 输入：`{_markdown_escape(str(report.input.requested_path))}`",
        f"- 模式：`{report.input.mode.value}`",
        (
            "- cold JSONL record bytes 来源："
            f"`{_markdown_escape(str(report.input.cold_jsonl_path))}`"
        ),
        (
            "- expected cold lock path（由 Host owner 从 expected cold JSONL "
            "路径唯一派生）："
            f"`{_markdown_escape(str(report.input.cold_lock_path))}`"
        ),
        (
            f"- cold capability：`{str(report.input.capabilities.cold).lower()}`；"
            "只有 `true` 表示本次实际获取上述 lock 并读取 cold snapshot。"
        ),
    ]
    for item in report.signal_coverage:
        reason = (
            ""
            if not item.reason_codes
            else "；原因：" + ", ".join(item.reason_codes)
        )
        lines.append(f"- {item.signal_name}: `{item.status.value}`{reason}")
    return "\n".join(lines)


def _render_executive_summary(summary: ToolTraceAnalysisSummary) -> str:
    """渲染 executive summary。

    :param summary: report summary。
    :returns: Markdown section。
    :raises: 无。
    """

    return "\n".join(
        (
            f"## {_MARKDOWN_SECTIONS[1]}",
            "",
            (
                f"- valid records={summary.valid_record_count}, "
                f"invalid records={summary.invalid_record_count}, "
                f"runs={summary.run_count}, tool calls={summary.tool_call_count}"
            ),
            (
                f"- confirmed findings={summary.finding_count}, "
                f"limitations={summary.limitation_count}"
            ),
        )
    )


def _render_finding_section(
    report: ToolTraceAnalysisReport,
    *,
    layer: str,
    title: str,
) -> str:
    """渲染单个归因层的 findings。

    :param report: structured report。
    :param layer: ``host|engine|tool``。
    :param title: Markdown 标题。
    :returns: Markdown section。
    :raises: 无。
    """

    findings = [item for item in report.findings if item.layer.value == layer]
    lines = [f"## {title}", ""]
    if not findings:
        lines.append("- 无 confirmed finding。")
        return "\n".join(lines)
    for item in findings:
        lines.append(
            f"- **{item.finding_id}** `{item.priority.value}` "
            f"`{item.rule_id}`：{_markdown_escape(item.summary)}"
        )
        lines.append(f"  - 建议：{_markdown_escape(item.recommendation)}")
        for evidence in item.evidence:
            lines.append(f"  - 证据：{_evidence_markdown(evidence)}")
    return "\n".join(lines)


def _render_vendor_debugging(
    blocks: tuple[ToolTraceVendorDebuggingBlock, ...],
) -> str:
    """渲染 vendor debugging 章节。

    :param blocks: vendor blocks；S2 合法为空。
    :returns: Markdown section。
    :raises: 无。
    """

    lines = [f"## {_MARKDOWN_SECTIONS[5]}", ""]
    if not blocks:
        lines.append("- 当前 Slice 未产生 vendor debugging block。")
        return "\n".join(lines)
    for block in blocks:
        lines.append(
            "- "
            f"status=`{block.status.value}`, "
            f"provider_request_id=`{_markdown_escape(block.provider_request_id or 'null')}`, "
            f"client_correlation_id=`{_markdown_escape(block.client_correlation_id or 'null')}`"
        )
    return "\n".join(lines)


def _render_payload_rankings(
    measures: tuple[ToolTracePayloadMeasure, ...],
) -> str:
    """渲染 byte measure ranking，明确 cold record 的 projection 计量语义。

    :param measures: verified payload measures。
    :returns: Markdown section。
    :raises: 无。
    """

    lines = [
        f"## {_MARKDOWN_SECTIONS[6]}",
        "",
        (
            "以下为 verified byte measures；"
            "`cold_jsonl_record_bytes` 只计量 JSONL projection record bytes。"
        ),
    ]
    if not measures:
        lines.append("- 无 verified byte measure。")
        return "\n".join(lines)
    for item in measures:
        lines.append(
            f"- {item.size_bytes} bytes | `{item.category}` | "
            f"`{item.measurement_source.value}` | "
            f"`{_markdown_escape(item.payload_ref)}`"
        )
    return "\n".join(lines)


def _render_runs(runs: tuple[ToolTraceRunSummary, ...]) -> str:
    """渲染 Run/Attempt/Tool timeline 摘要。

    :param runs: run summaries。
    :returns: Markdown section。
    :raises: 无。
    """

    lines = [f"## {_MARKDOWN_SECTIONS[7]}", ""]
    if not runs:
        lines.append("- 无 direct run identity。")
        return "\n".join(lines)
    for item in runs:
        lines.append(
            f"- run=`{_markdown_escape(item.run_id)}` events={item.event_count}, "
            f"tool requests={item.tool_request_count}, "
            f"tool results={item.tool_result_count}, "
            f"tool awaiting={item.tool_awaiting_count}, "
            f"run waiting={item.run_waiting_count}"
        )
    return "\n".join(lines)


def _render_limitations(
    limitations: tuple[ToolTraceLimitation, ...],
) -> str:
    """渲染 limitations，并明确不能当成已发生故障。

    :param limitations: structured limitations。
    :returns: Markdown section。
    :raises: 无。
    """

    lines = [f"## {_MARKDOWN_SECTIONS[8]}", ""]
    if not limitations:
        lines.append("- 无 limitation。")
        return "\n".join(lines)
    for item in limitations:
        lines.append(
            f"- `{item.reason_code}` `{item.signal_status.value}`："
            f"无法证明。{_markdown_escape(item.summary)}"
        )
    return "\n".join(lines)


def _render_recommended_actions(
    findings: tuple[ToolTraceFinding, ...],
) -> str:
    """渲染按 finding 顺序去重的建议动作。

    :param findings: ordered findings。
    :returns: Markdown section。
    :raises: 无。
    """

    lines = [f"## {_MARKDOWN_SECTIONS[9]}", ""]
    recommendations = tuple(
        dict.fromkeys(item.recommendation for item in findings)
    )
    if not recommendations:
        lines.append("- 当前没有 confirmed finding 对应的处置动作。")
        return "\n".join(lines)
    lines.extend(
        f"- {_markdown_escape(recommendation)}"
        for recommendation in recommendations
    )
    return "\n".join(lines)


def _evidence_markdown(item: ToolTraceEvidence) -> str:
    """把 evidence 投影为单行 bounded Markdown。

    :param item: direct evidence。
    :returns: 单行 Markdown。
    :raises: 无。
    """

    observed = json.dumps(
        dict(item.observed),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        f"kind=`{item.kind.value}`, path=`{_markdown_escape(str(item.source_path))}`, "
        f"line={item.line_number}, event_sequence={item.event_sequence}, "
        f"event_id=`{_markdown_escape(item.event_id or 'null')}`, "
        f"observed=`{_markdown_escape(observed)}`"
    )


def _markdown_escape(value: str) -> str:
    """转义单行 Markdown 控制字符。

    :param value: 待渲染文本。
    :returns: 单行 escaped 文本。
    :raises: 无。
    """

    return (
        value.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )
