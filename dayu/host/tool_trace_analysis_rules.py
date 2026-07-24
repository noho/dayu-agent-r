"""Tool Trace Analyzer 的确定性聚合与 Host/Tool 诊断规则。

本模块只消费 Slice 1 已建立的可信 typed dataset。它拥有 run/tool 聚合、
confirmed finding、limitation、payload ranking、稳定排序与 finding id；
不读取文件、不修改 Host truth，也不实现 provider/vendor 规则。
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from dayu.contracts.json_value import JsonValue
from dayu.host.tool_trace_analysis_contracts import (
    ToolTraceAnalysisCapabilities,
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
    ToolTraceLimitation,
    ToolTracePayloadMeasurementSource,
    ToolTracePayloadMeasure,
    ToolTraceRunSummary,
    ToolTraceSignalCoverage,
    ToolTraceSignalStatus,
)
from dayu.host.tool_trace_analysis_input import (
    ToolTraceAnalysisDataset,
    ToolTraceColdRecord,
    ToolTraceInputDiagnostic,
    ToolTraceInputDiagnosticCode,
    ToolTraceInputLimitation,
    ToolTracePayloadCategory,
    ToolTraceResolvedPayloadMeasure,
)
from dayu.host.tool_trace import _tool_trace_cold_lock_path
from dayu.host.tooling import FrameworkToolName

_REPORT_SCHEMA_VERSION = 1
_EVENT_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_EVENT_TOOL_CALL_GOVERNED = "TOOL_CALL_GOVERNED"
_EVENT_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_EVENT_TOOL_AWAITING = "TOOL_AWAITING"
_EVENT_RUN_WAITING = "RUN_WAITING"
_EVENT_USAGE_REPORTED = "USAGE_REPORTED"
_EVENT_CONTEXT_COMPACTION_FAILED = "CONTEXT_COMPACTION_FAILED"
_EVENT_CONTEXT_COMPACTION_ATTEMPT_REJECTED = (
    "CONTEXT_COMPACTION_ATTEMPT_REJECTED"
)
_FETCH_MORE_TOOL_NAME = FrameworkToolName.FETCH_MORE.value
_FIELD_TRACE_SUMMARY = "trace_summary"
_FIELD_FAILURE_METADATA = "failure_metadata"
_FIELD_FAILURE_KIND = "failure_kind"
_FIELD_TOOL_TIMING = "tool_timing"
_FIELD_CONTEXT_PRESSURE = "context_pressure"
_FIELD_TRUNCATION = "truncation"
_FIELD_TOOL_REQUEST = "tool_request"
_FIELD_ARGUMENTS = "arguments"
_FIELD_CURSOR = "cursor"
_FIELD_CURSOR_HINT = "cursor_hint"
_FIELD_APPLIED = "applied"
_FIELD_DUPLICATE_KEY = "duplicate_key"
_FIELD_DUPLICATE_DECISION = "duplicate_decision"
_FIELD_DUPLICATE_SCOPE = "duplicate_scope"
_FIELD_REUSE_PRIOR_EVENT_REFS = "reuse_prior_event_refs"
_FIELD_DIAGNOSTIC_REFS = "diagnostic_refs"
_FIELD_CLIENT_CORRELATION_ID = "client_correlation_id"
_TIMING_AVAILABLE = "available"
_TIMING_MISSING = "missing_tool_result_meta"
_TIMING_SOURCE = "tool_result_meta"
_FAILURE_TOOL_FAILED = "tool_failed"
_FAILURE_TOOL_CANCELLED = "tool_cancelled"
_FAILURE_POLICY_BLOCKED = "policy_blocked"
_FAILURE_CONTEXT_COMPACTION_FAILED = "context_compaction_failed"
_FAILURE_CONTEXT_COMPACTION_ATTEMPT_REJECTED = (
    "context_compaction_attempt_rejected"
)
_INPUT_CHANGED_REASON = "input_changed_during_analysis"
_PAYLOAD_SIZE_UNVERIFIED_REASON = "payload_size_unverified"
_TOOL_TIMING_MISSING_REASON = "tool_timing_missing"
_TOOL_TIMING_INVALID_REASON = "tool_timing_invalid"
_CONTEXT_PRESSURE_INVALID_REASON = "context_pressure_invalid"
_TRUNCATION_CURSOR_UNAVAILABLE_REASON = "truncation_cursor_unavailable"
_FETCH_MORE_ARGUMENTS_UNAVAILABLE_REASON = (
    f"{FrameworkToolName.FETCH_MORE.value}_arguments_unavailable"
)
_TRUNCATION_FOLLOWUP_UNVERIFIED_REASON = "truncation_followup_unverified"
_LAYER_ORDER = {
    ToolTraceAnalysisLayer.HOST: 0,
    ToolTraceAnalysisLayer.ENGINE: 1,
    ToolTraceAnalysisLayer.TOOL: 2,
}
_SEVERITY_ORDER = {
    ToolTraceFindingSeverity.ERROR: 0,
    ToolTraceFindingSeverity.WARNING: 1,
    ToolTraceFindingSeverity.INFO: 2,
}
_PRIORITY_ORDER = {
    ToolTraceFindingPriority.HIGH: 0,
    ToolTraceFindingPriority.MEDIUM: 1,
    ToolTraceFindingPriority.LOW: 2,
}
_FINDING_PREFIX = {
    ToolTraceAnalysisLayer.HOST: "TT-HOST",
    ToolTraceAnalysisLayer.ENGINE: "TT-ENGINE",
    ToolTraceAnalysisLayer.TOOL: "TT-TOOL",
}


@dataclass(frozen=True, slots=True)
class _RuleRecord:
    """供规则消费的 cold/hot 同形直接证据。"""

    source_path: Path
    evidence_kind: ToolTraceEvidenceKind
    line_number: int | None
    event_id: str
    event_sequence: int
    event_type: str
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    tool_call_id: str | None
    tool_name: str | None
    provider_request_id: str | None
    client_correlation_id: str | None
    normalized_arguments_digest: str | None
    trace_ref: str | None
    payload_ref: str | None
    diagnostic_refs: tuple[str, ...]
    trace_summary: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class _TimingSample:
    """source-owned available tool timing sample。"""

    record: _RuleRecord
    duration_ms: int


@dataclass(frozen=True, slots=True)
class _FindingDraft:
    """规则内部尚未分配 public finding id 的严格中间类型。"""

    rule_id: str
    layer: ToolTraceAnalysisLayer
    severity: ToolTraceFindingSeverity
    priority: ToolTraceFindingPriority
    title: str
    summary: str
    recommendation: str
    evidence: tuple[ToolTraceEvidence, ...]


def build_tool_trace_analysis_report(
    dataset: ToolTraceAnalysisDataset,
    source: ToolTraceAnalysisSource,
    policy: ToolTraceAnalysisPolicy,
) -> ToolTraceAnalysisReport:
    """从可信 dataset 构造确定性 structured report。

    :param dataset: Slice 1 strict loader 产生的 immutable dataset。
    :param source: 与 dataset 同一显式输入来源。
    :param policy: 本次实际诊断阈值。
    :returns: schema version 1 structured report。
    :raises TypeError: 参数类型错误时抛出。
    :raises ValueError: dataset/source identity 不一致时抛出。
    """

    if not isinstance(dataset, ToolTraceAnalysisDataset):
        raise TypeError("dataset must be ToolTraceAnalysisDataset")
    if not isinstance(source, ToolTraceAnalysisSource):
        raise TypeError("source must be ToolTraceAnalysisSource")
    if not isinstance(policy, ToolTraceAnalysisPolicy):
        raise TypeError("policy must be ToolTraceAnalysisPolicy")
    if dataset.source != source:
        raise ValueError("dataset source must equal analysis source")

    records = _rule_records(dataset)
    findings: list[_FindingDraft] = []
    limitations = [_input_limitation(item) for item in dataset.limitations]
    findings.extend(_integrity_findings(dataset.input_diagnostics))
    limitations.extend(_dependent_integrity_limitations(dataset.input_diagnostics))
    findings.extend(_duplicate_governance_findings(records))
    findings.extend(_repeated_request_findings(records))
    findings.extend(_failure_findings(records))
    timing_findings, timing_limitations = _timing_results(records, policy)
    findings.extend(timing_findings)
    limitations.extend(timing_limitations)
    truncation_findings, truncation_limitations = _truncation_results(records)
    findings.extend(truncation_findings)
    limitations.extend(truncation_limitations)
    context_findings, context_limitations = _context_results(records)
    findings.extend(context_findings)
    limitations.extend(context_limitations)

    payload_rankings = _payload_rankings(dataset, policy)
    findings.extend(_large_payload_findings(payload_rankings, policy))
    ordered_findings = _order_and_assign_finding_ids(tuple(findings))
    ordered_limitations = _order_limitations(tuple(limitations))
    runs = _run_summaries(records)
    input_summary = _input_summary(dataset, source)
    summary = ToolTraceAnalysisSummary(
        valid_record_count=len(dataset.cold_records),
        invalid_record_count=_invalid_record_count(dataset.input_diagnostics),
        run_count=len(runs),
        tool_call_count=len(
            {
                record.tool_call_id
                for record in records
                if record.tool_call_id is not None
            }
        ),
        finding_count=len(ordered_findings),
        limitation_count=len(ordered_limitations),
    )
    return ToolTraceAnalysisReport(
        schema_version=_REPORT_SCHEMA_VERSION,
        input=input_summary,
        policy=policy,
        summary=summary,
        signal_coverage=_signal_coverage(
            records,
            payload_rankings,
            ordered_limitations,
        ),
        runs=runs,
        payload_rankings=payload_rankings,
        vendor_debugging=(),
        findings=ordered_findings,
        limitations=ordered_limitations,
    )


def _rule_records(dataset: ToolTraceAnalysisDataset) -> tuple[_RuleRecord, ...]:
    """构造 cold 优先、hot-only 补充的稳定规则输入。

    :param dataset: 可信输入 dataset。
    :returns: 按 event sequence/source 稳定排序的规则 records。
    :raises: 无。
    """

    records = [_rule_record_from_cold(record) for record in dataset.cold_records]
    cold_event_ids = {record.event_id for record in dataset.cold_records}
    hot_path = dataset.source.hot_db_path
    if hot_path is not None:
        for row in dataset.hot_rows:
            if row.event_id in cold_event_ids:
                continue
            summary = row.trace_summary
            records.append(
                _RuleRecord(
                    source_path=hot_path,
                    evidence_kind=ToolTraceEvidenceKind.HOT_ROW,
                    line_number=None,
                    event_id=row.event_id,
                    event_sequence=row.event_sequence,
                    event_type=row.event_type,
                    session_id=row.session_id,
                    run_id=row.run_id,
                    attempt_id=row.attempt_id,
                    execution_id=row.execution_id,
                    tool_call_id=row.tool_call_id,
                    tool_name=row.tool_name,
                    provider_request_id=row.provider_request_id,
                    client_correlation_id=_optional_text(
                        summary,
                        _FIELD_CLIENT_CORRELATION_ID,
                    ),
                    normalized_arguments_digest=row.normalized_arguments_digest,
                    trace_ref=row.cold_trace_ref,
                    payload_ref=row.payload_ref,
                    diagnostic_refs=_text_tuple(
                        summary,
                        _FIELD_DIAGNOSTIC_REFS,
                    ),
                    trace_summary=summary,
                )
            )
    return tuple(
        sorted(
            records,
            key=lambda item: (
                item.event_sequence,
                str(item.source_path),
                item.line_number or 0,
                item.event_id,
            ),
        )
    )


def _rule_record_from_cold(record: ToolTraceColdRecord) -> _RuleRecord:
    """把 strict cold record 投影为规则输入。

    :param record: strict current-schema cold record。
    :returns: 规则输入。
    :raises: 无。
    """

    fields = record.fields
    summary_value = fields[_FIELD_TRACE_SUMMARY]
    trace_summary = (
        summary_value if isinstance(summary_value, Mapping) else {}
    )
    return _RuleRecord(
        source_path=record.source_path,
        evidence_kind=ToolTraceEvidenceKind.COLD_LINE,
        line_number=record.line_number,
        event_id=record.event_id,
        event_sequence=record.event_sequence,
        event_type=record.event_type,
        session_id=record.session_id,
        run_id=record.run_id,
        attempt_id=_optional_text(fields, "attempt_id"),
        execution_id=_optional_text(fields, "execution_id"),
        tool_call_id=_optional_text(fields, "tool_call_id"),
        tool_name=_optional_text(fields, "tool_name"),
        provider_request_id=_optional_text(fields, "provider_request_id"),
        client_correlation_id=_optional_text(
            fields,
            _FIELD_CLIENT_CORRELATION_ID,
        ),
        normalized_arguments_digest=_optional_text(
            fields,
            "normalized_arguments_digest",
        ),
        trace_ref=record.cold_trace_ref,
        payload_ref=_optional_text(fields, "payload_ref"),
        diagnostic_refs=_text_tuple(fields, _FIELD_DIAGNOSTIC_REFS),
        trace_summary=trace_summary,
    )


def _integrity_findings(
    diagnostics: tuple[ToolTraceInputDiagnostic, ...],
) -> tuple[_FindingDraft, ...]:
    """把 S1 owner diagnostics 投影为 Host confirmed findings。

    :param diagnostics: S1 input diagnostics。
    :returns: 尚未分配最终 id 的 Host findings。
    :raises: 无。
    """

    findings: list[_FindingDraft] = []
    for diagnostic in diagnostics:
        severity, priority = _integrity_severity_priority(diagnostic.code)
        evidence = _diagnostic_evidence(diagnostic)
        findings.append(
            _finding(
                rule_id=diagnostic.code.value,
                layer=ToolTraceAnalysisLayer.HOST,
                severity=severity,
                priority=priority,
                title="Tool Trace 输入完整性异常",
                summary=diagnostic.summary,
                recommendation=(
                    "检查 Tool Trace projection、cold JSONL 或 payload resolver owner；"
                    "不要在 Analyzer 中修复输入。"
                ),
                evidence=(evidence,),
            )
        )
    return tuple(findings)


def _integrity_severity_priority(
    code: ToolTraceInputDiagnosticCode,
) -> tuple[ToolTraceFindingSeverity, ToolTraceFindingPriority]:
    """返回 input diagnostic 的稳定 severity/priority。

    :param code: S1 稳定 diagnostic code。
    :returns: severity 与 priority。
    :raises: 无。
    """

    if code is ToolTraceInputDiagnosticCode.DUPLICATE_COLD_LINE:
        return ToolTraceFindingSeverity.INFO, ToolTraceFindingPriority.LOW
    if code in (
        ToolTraceInputDiagnosticCode.MISSING_COLD_TRACE,
        ToolTraceInputDiagnosticCode.MISSING_HOT_TRACE,
    ):
        return ToolTraceFindingSeverity.WARNING, ToolTraceFindingPriority.MEDIUM
    if code in (
        ToolTraceInputDiagnosticCode.PAYLOAD_UNRESOLVABLE,
        ToolTraceInputDiagnosticCode.RUNNER_CALL_RECONSTRUCTION_LIMITED,
    ):
        return ToolTraceFindingSeverity.ERROR, ToolTraceFindingPriority.MEDIUM
    return ToolTraceFindingSeverity.ERROR, ToolTraceFindingPriority.HIGH


def _dependent_integrity_limitations(
    diagnostics: tuple[ToolTraceInputDiagnostic, ...],
) -> tuple[ToolTraceLimitation, ...]:
    """为 payload/resolver 失败记录依赖规则不可验证 limitation。

    :param diagnostics: S1 input diagnostics。
    :returns: payload size/reconstruction limitations。
    :raises: 无。
    """

    return tuple(
        ToolTraceLimitation(
            reason_code=_PAYLOAD_SIZE_UNVERIFIED_REASON,
            signal_status=ToolTraceSignalStatus.LIMITED_SIGNAL,
            summary="payload resolver 未通过，无法验证 exact payload bytes。",
            evidence=(_diagnostic_evidence(diagnostic),),
        )
        for diagnostic in diagnostics
        if diagnostic.code
        in (
            ToolTraceInputDiagnosticCode.PAYLOAD_UNRESOLVABLE,
            ToolTraceInputDiagnosticCode.RUNNER_CALL_RECONSTRUCTION_LIMITED,
        )
    )


def _duplicate_governance_findings(
    records: tuple[_RuleRecord, ...],
) -> tuple[_FindingDraft, ...]:
    """投影 Host 已做出的 duplicate governance 事实。

    :param records: 可信规则 records。
    :returns: Host governance findings。
    :raises: 无。
    """

    findings: list[_FindingDraft] = []
    for record in records:
        duplicate_key = _optional_text(record.trace_summary, _FIELD_DUPLICATE_KEY)
        duplicate_decision = _optional_text(
            record.trace_summary,
            _FIELD_DUPLICATE_DECISION,
        )
        if duplicate_key is None and duplicate_decision is None:
            continue
        observed: dict[str, JsonValue] = {
            _FIELD_DUPLICATE_KEY: duplicate_key,
            _FIELD_DUPLICATE_DECISION: duplicate_decision,
            _FIELD_DUPLICATE_SCOPE: record.trace_summary.get(
                _FIELD_DUPLICATE_SCOPE
            ),
            _FIELD_REUSE_PRIOR_EVENT_REFS: record.trace_summary.get(
                _FIELD_REUSE_PRIOR_EVENT_REFS
            ),
        }
        findings.append(
            _finding(
                rule_id="host.duplicate_governance",
                layer=ToolTraceAnalysisLayer.HOST,
                severity=ToolTraceFindingSeverity.INFO,
                priority=ToolTraceFindingPriority.LOW,
                title="Host duplicate governance decision",
                summary="当前 trace 直接记录了 Host duplicate governance decision。",
                recommendation="按现有 duplicate decision 与 prior refs 核对 Host policy。",
                evidence=(_record_evidence(record, observed),),
            )
        )
    return tuple(findings)


def _repeated_request_findings(
    records: tuple[_RuleRecord, ...],
) -> tuple[_FindingDraft, ...]:
    """识别同一 Run 内相同工具与 normalized arguments digest 的重复请求。

    :param records: 可信规则 records。
    :returns: Tool repeated-identical observations。
    :raises: 无。
    """

    groups: dict[tuple[str, str, str], list[_RuleRecord]] = defaultdict(list)
    for record in records:
        if (
            record.event_type != _EVENT_TOOL_CALL_REQUESTED
            or record.run_id is None
            or record.tool_name is None
            or record.normalized_arguments_digest is None
        ):
            continue
        groups[
            (
                record.run_id,
                record.tool_name,
                record.normalized_arguments_digest,
            )
        ].append(record)
    findings: list[_FindingDraft] = []
    for (run_id, tool_name, digest), grouped in sorted(groups.items()):
        if len(grouped) < 2:
            continue
        evidence = tuple(
            _record_evidence(
                record,
                {
                    "run_id": run_id,
                    "tool_name": tool_name,
                    "normalized_arguments_digest": digest,
                },
            )
            for record in grouped
        )
        findings.append(
            _finding(
                rule_id="tool.repeated_identical_request",
                layer=ToolTraceAnalysisLayer.TOOL,
                severity=ToolTraceFindingSeverity.INFO,
                priority=ToolTraceFindingPriority.LOW,
                title="相同工具请求重复出现",
                summary=(
                    "同一 Run 中直接观察到相同 tool_name 与 "
                    "normalized_arguments_digest 的多次请求。"
                ),
                recommendation="检查工具调用策略或 schema 是否导致无效重复请求。",
                evidence=evidence,
            )
        )
    return tuple(findings)


def _failure_findings(
    records: tuple[_RuleRecord, ...],
) -> tuple[_FindingDraft, ...]:
    """按 source-owned failure kind 归因 Host/Tool failure。

    :param records: 可信规则 records。
    :returns: failure findings。
    :raises: 无。
    """

    findings: list[_FindingDraft] = []
    for record in records:
        metadata = _mapping(record.trace_summary, _FIELD_FAILURE_METADATA)
        if metadata is None:
            continue
        failure_kind = _optional_text(metadata, _FIELD_FAILURE_KIND)
        if failure_kind == _FAILURE_TOOL_FAILED:
            findings.append(
                _failure_finding(
                    record,
                    metadata,
                    rule_id="tool.tool_failed",
                    layer=ToolTraceAnalysisLayer.TOOL,
                    summary="ToolRuntime accepted result 明确记录工具执行失败。",
                )
            )
        elif failure_kind == _FAILURE_TOOL_CANCELLED:
            findings.append(
                _failure_finding(
                    record,
                    metadata,
                    rule_id="tool.tool_cancelled",
                    layer=ToolTraceAnalysisLayer.TOOL,
                    summary="ToolRuntime accepted result 明确记录工具执行取消。",
                )
            )
        elif failure_kind == _FAILURE_POLICY_BLOCKED:
            findings.append(
                _failure_finding(
                    record,
                    metadata,
                    rule_id="host.policy_blocked",
                    layer=ToolTraceAnalysisLayer.HOST,
                    summary="Host policy 明确阻止了本次工具结果。",
                )
            )
    return tuple(findings)


def _failure_finding(
    record: _RuleRecord,
    metadata: Mapping[str, JsonValue],
    *,
    rule_id: str,
    layer: ToolTraceAnalysisLayer,
    summary: str,
) -> _FindingDraft:
    """构造单条 source-owned failure finding。

    :param record: owner record。
    :param metadata: source-owned failure metadata。
    :param rule_id: 稳定规则 id。
    :param layer: 归因层。
    :param summary: 中文摘要。
    :returns: 尚未分配最终 id 的 finding。
    :raises: 无。
    """

    return _finding(
        rule_id=rule_id,
        layer=layer,
        severity=ToolTraceFindingSeverity.WARNING,
        priority=ToolTraceFindingPriority.MEDIUM,
        title="工具执行或治理失败",
        summary=summary,
        recommendation=(
            "根据 failure metadata 中的 reason/code 定位对应 Host policy 或 Tool owner。"
        ),
        evidence=(_record_evidence(record, _bounded_observed(metadata)),),
    )


def _timing_results(
    records: tuple[_RuleRecord, ...],
    policy: ToolTraceAnalysisPolicy,
) -> tuple[tuple[_FindingDraft, ...], tuple[ToolTraceLimitation, ...]]:
    """分析 source-owned tool timing，不从 timestamp 推导耗时。

    :param records: 可信规则 records。
    :param policy: latency 阈值。
    :returns: latency findings 与 limitations。
    :raises: 无。
    """

    samples: dict[str, list[_TimingSample]] = defaultdict(list)
    limitations: list[ToolTraceLimitation] = []
    for record in records:
        if record.event_type != _EVENT_TOOL_RESULT_ACCEPTED:
            continue
        timing = _mapping(record.trace_summary, _FIELD_TOOL_TIMING)
        if timing is None:
            limitations.append(
                _record_limitation(
                    _TOOL_TIMING_MISSING_REASON,
                    "工具结果没有 source-owned tool_timing signal；未从 timestamp 推导。",
                    record,
                )
            )
            continue
        status = _optional_text(timing, "status")
        if status == _TIMING_MISSING:
            limitations.append(
                _record_limitation(
                    _TOOL_TIMING_MISSING_REASON,
                    "tool_timing 明确标记工具结果 metadata 缺失。",
                    record,
                )
            )
            continue
        duration_ms = timing.get("duration_ms")
        source = _optional_text(timing, "duration_source")
        if (
            status != _TIMING_AVAILABLE
            or isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or duration_ms < 0
            or source != _TIMING_SOURCE
            or record.tool_name is None
        ):
            limitations.append(
                _record_limitation(
                    _TOOL_TIMING_INVALID_REASON,
                    "tool_timing 不满足 available/tool_result_meta typed contract。",
                    record,
                )
            )
            continue
        samples[record.tool_name].append(
            _TimingSample(record=record, duration_ms=duration_ms)
        )

    findings: list[_FindingDraft] = []
    for tool_name, tool_samples in sorted(samples.items()):
        if len(tool_samples) < policy.latency_minimum_sample_count:
            continue
        median_duration = float(
            statistics.median(sample.duration_ms for sample in tool_samples)
        )
        for sample in tool_samples:
            if (
                sample.duration_ms
                < median_duration * policy.latency_outlier_multiplier
                or sample.duration_ms - median_duration
                < policy.latency_minimum_delta_ms
            ):
                continue
            findings.append(
                _finding(
                    rule_id="tool.latency_outlier",
                    layer=ToolTraceAnalysisLayer.TOOL,
                    severity=ToolTraceFindingSeverity.WARNING,
                    priority=ToolTraceFindingPriority.MEDIUM,
                    title="工具耗时异常",
                    summary="source-owned duration 同时超过 median 倍数与绝对差阈值。",
                    recommendation="检查对应 Tool implementation 与外部依赖耗时。",
                    evidence=(
                        _record_evidence(
                            sample.record,
                            {
                                "tool_name": tool_name,
                                "duration_ms": sample.duration_ms,
                                "median_duration_ms": median_duration,
                                "duration_source": _TIMING_SOURCE,
                            },
                        ),
                    ),
                )
            )
    return tuple(findings), tuple(limitations)


def _truncation_results(
    records: tuple[_RuleRecord, ...],
) -> tuple[tuple[_FindingDraft, ...], tuple[ToolTraceLimitation, ...]]:
    """分析 truncation 与 direct framework continuation cursor。

    :param records: 可信规则 records。
    :returns: truncation/continuation findings 与 limitations。
    :raises: 无。
    """

    findings: list[_FindingDraft] = []
    limitations: list[ToolTraceLimitation] = []
    by_run: dict[str, list[_RuleRecord]] = defaultdict(list)
    for record in records:
        if record.run_id is not None:
            by_run[record.run_id].append(record)
    for run_records in by_run.values():
        ordered = sorted(run_records, key=lambda item: item.event_sequence)
        for record in ordered:
            truncation = _mapping(record.trace_summary, _FIELD_TRUNCATION)
            if truncation is None or truncation.get(_FIELD_APPLIED) is not True:
                continue
            cursor_hint = _optional_text(truncation, _FIELD_CURSOR_HINT)
            if cursor_hint is None:
                limitations.append(
                    _record_limitation(
                        _TRUNCATION_CURSOR_UNAVAILABLE_REASON,
                        "truncation 已应用，但没有 typed cursor_hint。",
                        record,
                    )
                )
                continue
            later = [
                item
                for item in ordered
                if item.event_sequence > record.event_sequence
            ]
            continuation_records = [
                item
                for item in later
                if item.event_type == _EVENT_TOOL_CALL_REQUESTED
                and item.tool_name == _FETCH_MORE_TOOL_NAME
            ]
            matching = [
                item
                for item in continuation_records
                if _continuation_cursor(item) == cursor_hint
            ]
            if matching:
                continue
            unavailable = [
                item
                for item in continuation_records
                if _continuation_cursor(item) is None
            ]
            if unavailable:
                limitations.append(
                    ToolTraceLimitation(
                        reason_code=_FETCH_MORE_ARGUMENTS_UNAVAILABLE_REASON,
                        signal_status=ToolTraceSignalStatus.LIMITED_SIGNAL,
                        summary="framework 续读请求存在，但 typed arguments.cursor 不可用。",
                        evidence=(
                            _record_evidence(
                                record,
                                {"cursor_hint": cursor_hint},
                            ),
                            *(
                                _record_evidence(item, {})
                                for item in unavailable
                            ),
                        ),
                    )
                )
                continue
            if continuation_records:
                findings.append(
                    _finding(
                        rule_id=(
                            f"tool.{FrameworkToolName.FETCH_MORE.value}"
                            "_cursor_mismatch"
                        ),
                        layer=ToolTraceAnalysisLayer.TOOL,
                        severity=ToolTraceFindingSeverity.WARNING,
                        priority=ToolTraceFindingPriority.MEDIUM,
                        title="Framework 续读 cursor 不匹配",
                        summary="后续续读请求的 direct cursor 与 truncation cursor_hint 不同。",
                        recommendation="检查模型续读参数与 TruncationManager cursor 传递。",
                        evidence=(
                            _record_evidence(
                                record,
                                {"cursor_hint": cursor_hint},
                            ),
                            *(
                                _record_evidence(
                                    item,
                                    {"cursor": _continuation_cursor(item)},
                                )
                                for item in continuation_records
                            ),
                        ),
                    )
                )
            elif later:
                findings.append(
                    _finding(
                        rule_id="tool.truncation_not_followed",
                        layer=ToolTraceAnalysisLayer.TOOL,
                        severity=ToolTraceFindingSeverity.WARNING,
                        priority=ToolTraceFindingPriority.MEDIUM,
                        title="截断结果未观察到续读",
                        summary="同一 Run 后续已有事件，但未观察到匹配 cursor 的 framework 续读请求。",
                        recommendation="检查工具结果 contract 与模型续读策略。",
                        evidence=(
                            _record_evidence(
                                record,
                                {"cursor_hint": cursor_hint},
                            ),
                            _record_evidence(later[-1], {}),
                        ),
                    )
                )
            else:
                limitations.append(
                    _record_limitation(
                        _TRUNCATION_FOLLOWUP_UNVERIFIED_REASON,
                        "truncation 后没有更多 Run 事件，无法证明是否完成续读。",
                        record,
                    )
                )
    return tuple(findings), tuple(limitations)


def _continuation_cursor(record: _RuleRecord) -> str | None:
    """读取 source-owned tool_request.arguments.cursor。

    :param record: framework 续读请求 record。
    :returns: direct cursor；typed arguments 不完整时返回 ``None``。
    :raises: 无。
    """

    request = _mapping(record.trace_summary, _FIELD_TOOL_REQUEST)
    if request is None:
        return None
    arguments = _mapping(request, _FIELD_ARGUMENTS)
    if arguments is None:
        return None
    return _optional_text(arguments, _FIELD_CURSOR)


def _context_results(
    records: tuple[_RuleRecord, ...],
) -> tuple[tuple[_FindingDraft, ...], tuple[ToolTraceLimitation, ...]]:
    """分析 direct context pressure 与 compaction failure signal。

    :param records: 可信规则 records。
    :returns: Host context findings 与 limitations。
    :raises: 无。
    """

    findings: list[_FindingDraft] = []
    limitations: list[ToolTraceLimitation] = []
    for record in records:
        pressure = _mapping(record.trace_summary, _FIELD_CONTEXT_PRESSURE)
        if pressure is None:
            if record.event_type == _EVENT_USAGE_REPORTED:
                limitations.append(
                    _record_limitation(
                        _CONTEXT_PRESSURE_INVALID_REASON,
                        "USAGE_REPORTED 没有 typed context_pressure；不得解释为零压力。",
                        record,
                    )
                )
            continue
        hard = pressure.get("hard_threshold_exceeded")
        soft = pressure.get("soft_threshold_exceeded")
        status = _optional_text(pressure, "status")
        failure = _mapping(record.trace_summary, _FIELD_FAILURE_METADATA)
        failure_kind = (
            None if failure is None else _optional_text(failure, _FIELD_FAILURE_KIND)
        )
        if hard is True:
            findings.append(
                _context_finding(
                    record,
                    pressure,
                    rule_id="host.context_pressure_hard",
                    severity=ToolTraceFindingSeverity.ERROR,
                    priority=ToolTraceFindingPriority.HIGH,
                    summary="typed context pressure 明确超过 hard threshold。",
                )
            )
        elif soft is True:
            findings.append(
                _context_finding(
                    record,
                    pressure,
                    rule_id="host.context_pressure_soft",
                    severity=ToolTraceFindingSeverity.WARNING,
                    priority=ToolTraceFindingPriority.MEDIUM,
                    summary="typed context pressure 明确超过 soft threshold。",
                )
            )
        if (
            record.event_type == _EVENT_CONTEXT_COMPACTION_FAILED
            or status == "compaction_failed"
            or failure_kind == _FAILURE_CONTEXT_COMPACTION_FAILED
        ):
            findings.append(
                _context_finding(
                    record,
                    pressure,
                    rule_id="host.context_compaction_failed",
                    severity=ToolTraceFindingSeverity.ERROR,
                    priority=ToolTraceFindingPriority.HIGH,
                    summary="Host context compaction 明确失败。",
                )
            )
        elif (
            record.event_type == _EVENT_CONTEXT_COMPACTION_ATTEMPT_REJECTED
            or status == "compaction_attempt_rejected"
            or failure_kind == _FAILURE_CONTEXT_COMPACTION_ATTEMPT_REJECTED
        ):
            findings.append(
                _context_finding(
                    record,
                    pressure,
                    rule_id="host.context_compaction_attempt_rejected",
                    severity=ToolTraceFindingSeverity.WARNING,
                    priority=ToolTraceFindingPriority.MEDIUM,
                    summary="Host context compaction attempt 明确被拒绝。",
                )
            )
        if hard not in (None, True, False) or soft not in (None, True, False):
            limitations.append(
                _record_limitation(
                    _CONTEXT_PRESSURE_INVALID_REASON,
                    "context pressure threshold 字段不是 bool/null，未据此判断。",
                    record,
                )
            )
    return tuple(findings), tuple(limitations)


def _context_finding(
    record: _RuleRecord,
    pressure: Mapping[str, JsonValue],
    *,
    rule_id: str,
    severity: ToolTraceFindingSeverity,
    priority: ToolTraceFindingPriority,
    summary: str,
) -> _FindingDraft:
    """构造 Host context finding。

    :param record: source record。
    :param pressure: direct context pressure object。
    :param rule_id: 稳定规则 id。
    :param severity: finding severity。
    :param priority: finding priority。
    :param summary: 中文摘要。
    :returns: 尚未分配最终 id 的 finding。
    :raises: 无。
    """

    return _finding(
        rule_id=rule_id,
        layer=ToolTraceAnalysisLayer.HOST,
        severity=severity,
        priority=priority,
        title="Host context governance signal",
        summary=summary,
        recommendation="检查 Context Governance policy、compaction artifact 与失败元数据。",
        evidence=(_record_evidence(record, _bounded_observed(pressure)),),
    )


def _payload_rankings(
    dataset: ToolTraceAnalysisDataset,
    policy: ToolTraceAnalysisPolicy,
) -> tuple[ToolTracePayloadMeasure, ...]:
    """投影并稳定排序 verified byte measures。

    :param dataset: 可信 dataset。
    :param policy: ranking 上限。
    :returns: top-N public measures。
    :raises: 无。
    """

    measures = tuple(_public_payload_measure(dataset, item) for item in dataset.payload_measures)
    ordered = sorted(
        measures,
        key=lambda item: (
            -item.size_bytes,
            item.category,
            item.payload_ref,
            item.event_sequence,
        ),
    )
    return tuple(ordered[: policy.payload_ranking_limit])


def _public_payload_measure(
    dataset: ToolTraceAnalysisDataset,
    measure: ToolTraceResolvedPayloadMeasure,
) -> ToolTracePayloadMeasure:
    """把内部 verified measure 投影为不含 body 的 public measure。

    :param dataset: 可信 dataset。
    :param measure: S1 verified measure。
    :returns: public payload measure。
    :raises ValueError: measure 缺少其类别要求的 cold 或 hot owner fact 时抛出。
    """

    if measure.category is ToolTracePayloadCategory.COLD_LINE:
        cold = next(
            (
                record
                for record in dataset.cold_records
                if record.event_id == measure.event_id
                and record.event_sequence == measure.event_sequence
            ),
            None,
        )
        if cold is None:
            raise ValueError(
                "cold-line measure requires matching cold record owner"
            )
        evidence = _record_evidence(
            _rule_record_from_cold(cold),
            {
                "category": measure.category.value,
                "size_bytes": measure.payload_size_bytes,
            },
            payload_ref=measure.payload_ref,
        )
        measurement_source = (
            ToolTracePayloadMeasurementSource.COLD_JSONL_RECORD_BYTES
        )
    else:
        hot_db_path = dataset.source.hot_db_path
        if not dataset.hot_store_available or hot_db_path is None:
            raise ValueError(
                "resolved payload measure requires available hot store owner"
            )
        hot_owner = next(
            (
                row
                for row in dataset.hot_rows
                if row.event_id == measure.event_id
                and row.event_sequence == measure.event_sequence
            ),
            None,
        )
        if hot_owner is None:
            raise ValueError(
                "resolved payload measure requires matching hot row owner"
            )
        evidence = ToolTraceEvidence(
            kind=ToolTraceEvidenceKind.RESOLVED_PAYLOAD,
            source_path=hot_db_path,
            line_number=None,
            event_id=measure.event_id,
            event_sequence=measure.event_sequence,
            event_type=hot_owner.event_type,
            trace_ref=None,
            payload_ref=measure.payload_ref,
            observed={
                "category": measure.category.value,
                "size_bytes": measure.payload_size_bytes,
            },
        )
        measurement_source = (
            ToolTracePayloadMeasurementSource.RESOLVED_PAYLOAD_BYTES
        )
    return ToolTracePayloadMeasure(
        category=measure.category.value,
        measurement_source=measurement_source,
        size_bytes=measure.payload_size_bytes,
        event_sequence=measure.event_sequence,
        payload_ref=measure.payload_ref,
        evidence=(evidence,),
    )


def _large_payload_findings(
    measures: tuple[ToolTracePayloadMeasure, ...],
    policy: ToolTraceAnalysisPolicy,
) -> tuple[_FindingDraft, ...]:
    """为达到 absolute byte threshold 的 verified measures 生成 finding。

    :param measures: 已排序 public measures。
    :param policy: large payload threshold。
    :returns: large payload findings。
    :raises: 无。
    """

    return tuple(
        _finding(
            rule_id="payload.large_payload",
            layer=_payload_layer(measure.category),
            severity=ToolTraceFindingSeverity.WARNING,
            priority=ToolTraceFindingPriority.MEDIUM,
            title="Verified byte measure 达到 large threshold",
            summary=(
                "当前 measure 的 exact bytes 达到本次 policy 阈值；"
                "cold_line 仅表示 JSONL projection record bytes。"
            ),
            recommendation="检查对应 projection、Tool contract 或 runner input 的 payload 规模。",
            evidence=measure.evidence,
        )
        for measure in measures
        if measure.size_bytes >= policy.large_payload_threshold_bytes
    )


def _payload_layer(category: str) -> ToolTraceAnalysisLayer:
    """按 payload category 归因 large finding。

    :param category: public payload category。
    :returns: Host 或 Tool layer。
    :raises: 无。
    """

    if category in (
        ToolTracePayloadCategory.TOOL_ARGUMENTS.value,
        ToolTracePayloadCategory.TOOL_RESULT.value,
    ):
        return ToolTraceAnalysisLayer.TOOL
    return ToolTraceAnalysisLayer.HOST


def _run_summaries(
    records: tuple[_RuleRecord, ...],
) -> tuple[ToolTraceRunSummary, ...]:
    """按 direct run id 聚合稳定摘要。

    :param records: 可信规则 records。
    :returns: 按 run id lexical order 的摘要。
    :raises: 无。
    """

    grouped: dict[str, list[_RuleRecord]] = defaultdict(list)
    for record in records:
        if record.run_id is not None:
            grouped[record.run_id].append(record)
    summaries: list[ToolTraceRunSummary] = []
    for run_id, run_records in sorted(grouped.items()):
        summaries.append(
            ToolTraceRunSummary(
                run_id=run_id,
                session_ids=_sorted_values(item.session_id for item in run_records),
                attempt_ids=_sorted_values(item.attempt_id for item in run_records),
                execution_ids=_sorted_values(
                    item.execution_id for item in run_records
                ),
                tool_call_ids=_sorted_values(
                    item.tool_call_id for item in run_records
                ),
                tool_names=_sorted_values(item.tool_name for item in run_records),
                provider_request_ids=_sorted_values(
                    item.provider_request_id for item in run_records
                ),
                client_correlation_ids=_sorted_values(
                    item.client_correlation_id for item in run_records
                ),
                diagnostic_refs=_sorted_values(
                    ref
                    for item in run_records
                    for ref in item.diagnostic_refs
                ),
                event_count=len(run_records),
                tool_request_count=sum(
                    item.event_type == _EVENT_TOOL_CALL_REQUESTED
                    for item in run_records
                ),
                tool_result_count=sum(
                    item.event_type == _EVENT_TOOL_RESULT_ACCEPTED
                    for item in run_records
                ),
                tool_timing_sample_count=sum(
                    _has_available_timing(item) for item in run_records
                ),
                context_pressure_observation_count=sum(
                    _mapping(item.trace_summary, _FIELD_CONTEXT_PRESSURE)
                    is not None
                    for item in run_records
                ),
                tool_awaiting_count=sum(
                    item.event_type == _EVENT_TOOL_AWAITING
                    for item in run_records
                ),
                run_waiting_count=sum(
                    item.event_type == _EVENT_RUN_WAITING
                    for item in run_records
                ),
            )
        )
    return tuple(summaries)


def _has_available_timing(record: _RuleRecord) -> bool:
    """判断 record 是否有 source-owned available timing。

    :param record: 规则 record。
    :returns: status/source/duration 完整时为 ``True``。
    :raises: 无。
    """

    timing = _mapping(record.trace_summary, _FIELD_TOOL_TIMING)
    if timing is None:
        return False
    duration = timing.get("duration_ms")
    return (
        _optional_text(timing, "status") == _TIMING_AVAILABLE
        and _optional_text(timing, "duration_source") == _TIMING_SOURCE
        and not isinstance(duration, bool)
        and isinstance(duration, int)
        and duration >= 0
    )


def _input_summary(
    dataset: ToolTraceAnalysisDataset,
    source: ToolTraceAnalysisSource,
) -> ToolTraceAnalysisInputSummary:
    """投影本次实际输入能力与快照 watermark。

    :param dataset: 可信 dataset。
    :param source: 显式 source。
    :returns: structured input summary。
    :raises: 无。
    """

    cold_lock_path = (
        dataset.cold_snapshot.cold_lock_path
        if dataset.cold_snapshot is not None
        else _tool_trace_cold_lock_path(source.cold_jsonl_path)
    )
    return ToolTraceAnalysisInputSummary(
        requested_path=source.requested_path,
        mode=source.mode,
        cold_jsonl_path=source.cold_jsonl_path,
        cold_lock_path=cold_lock_path,
        hot_db_path=source.hot_db_path,
        artifact_root=source.artifact_root,
        capabilities=ToolTraceAnalysisCapabilities(
            cold=dataset.cold_snapshot is not None,
            hot=dataset.hot_store_available,
            payload_resolution=(
                dataset.hot_store_available and source.artifact_root is not None
            ),
        ),
        hot_event_sequence_watermark=dataset.hot_event_sequence_watermark,
    )


def _input_limitation(item: ToolTraceInputLimitation) -> ToolTraceLimitation:
    """把 S1 limitation 投影到 public report。

    :param item: S1 limitation。
    :returns: public limitation。
    :raises: 无。
    """

    observed: dict[str, JsonValue] = {}
    if item.hot_event_sequence_watermark is not None:
        observed["hot_event_sequence_watermark"] = (
            item.hot_event_sequence_watermark
        )
    evidence = ToolTraceEvidence(
        kind=ToolTraceEvidenceKind.INPUT_PATH,
        source_path=item.source_path,
        line_number=item.line_number,
        event_id=item.event_id,
        event_sequence=item.event_sequence,
        event_type=None,
        trace_ref=None,
        payload_ref=None,
        observed=observed,
    )
    return ToolTraceLimitation(
        reason_code=item.reason_code,
        signal_status=ToolTraceSignalStatus.LIMITED_SIGNAL,
        summary=item.summary,
        evidence=(evidence,),
    )


def _signal_coverage(
    records: tuple[_RuleRecord, ...],
    measures: tuple[ToolTracePayloadMeasure, ...],
    limitations: tuple[ToolTraceLimitation, ...],
) -> tuple[ToolTraceSignalCoverage, ...]:
    """从报告事实投影稳定 signal coverage。

    :param records: 可信规则 records。
    :param measures: verified payload measures。
    :param limitations: ordered limitations。
    :returns: 固定 signal name 顺序的 coverage。
    :raises: 无。
    """

    reasons = {item.reason_code for item in limitations}
    timing_present = any(
        _mapping(item.trace_summary, _FIELD_TOOL_TIMING) is not None
        for item in records
    )
    timing_trigger = any(
        item.event_type == _EVENT_TOOL_RESULT_ACCEPTED for item in records
    )
    context_present = any(
        _mapping(item.trace_summary, _FIELD_CONTEXT_PRESSURE) is not None
        for item in records
    )
    context_trigger = any(
        item.event_type
        in (
            _EVENT_USAGE_REPORTED,
            _EVENT_CONTEXT_COMPACTION_FAILED,
            _EVENT_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        )
        for item in records
    )
    return (
        ToolTraceSignalCoverage(
            signal_name="integrity",
            status=ToolTraceSignalStatus.AVAILABLE,
            reason_codes=(),
        ),
        ToolTraceSignalCoverage(
            signal_name="tool_timing",
            status=_coverage_status(
                present=timing_present,
                triggered=timing_trigger,
                limited=bool(
                    reasons
                    & {_TOOL_TIMING_MISSING_REASON, _TOOL_TIMING_INVALID_REASON}
                ),
            ),
            reason_codes=tuple(
                sorted(
                    reasons
                    & {_TOOL_TIMING_MISSING_REASON, _TOOL_TIMING_INVALID_REASON}
                )
            ),
        ),
        ToolTraceSignalCoverage(
            signal_name="context_pressure",
            status=_coverage_status(
                present=context_present,
                triggered=context_trigger,
                limited=_CONTEXT_PRESSURE_INVALID_REASON in reasons,
            ),
            reason_codes=tuple(
                sorted(reasons & {_CONTEXT_PRESSURE_INVALID_REASON})
            ),
        ),
        ToolTraceSignalCoverage(
            signal_name="payload_measurement",
            status=_coverage_status(
                present=bool(measures),
                triggered=bool(records),
                limited=_PAYLOAD_SIZE_UNVERIFIED_REASON in reasons,
            ),
            reason_codes=tuple(
                sorted(reasons & {_PAYLOAD_SIZE_UNVERIFIED_REASON})
            ),
        ),
        ToolTraceSignalCoverage(
            signal_name="vendor_debugging",
            status=ToolTraceSignalStatus.NOT_APPLICABLE,
            reason_codes=(),
        ),
    )


def _coverage_status(
    *,
    present: bool,
    triggered: bool,
    limited: bool,
) -> ToolTraceSignalStatus:
    """按 present/trigger/limited 计算 signal coverage。

    :param present: 是否存在 direct typed signal。
    :param triggered: 是否存在需要该 signal 的 trigger event。
    :param limited: 是否已有对应 limitation。
    :returns: 稳定 coverage status。
    :raises: 无。
    """

    if limited:
        return ToolTraceSignalStatus.LIMITED_SIGNAL
    if present:
        return ToolTraceSignalStatus.AVAILABLE
    if triggered:
        return ToolTraceSignalStatus.LIMITED_SIGNAL
    return ToolTraceSignalStatus.NOT_APPLICABLE


def _order_and_assign_finding_ids(
    findings: tuple[_FindingDraft, ...],
) -> tuple[ToolTraceFinding, ...]:
    """按冻结 ordering key 排序并分层递增分配 finding id。

    :param findings: 尚未分配最终 id 的 findings。
    :returns: deterministic findings。
    :raises: 无。
    """

    ordered = sorted(findings, key=_finding_sort_key)
    counters: dict[ToolTraceAnalysisLayer, int] = defaultdict(int)
    assigned: list[ToolTraceFinding] = []
    for finding in ordered:
        counters[finding.layer] += 1
        assigned.append(
            ToolTraceFinding(
                finding_id=(
                    f"{_FINDING_PREFIX[finding.layer]}-"
                    f"{counters[finding.layer]:04d}"
                ),
                rule_id=finding.rule_id,
                layer=finding.layer,
                severity=finding.severity,
                priority=finding.priority,
                title=finding.title,
                summary=finding.summary,
                recommendation=finding.recommendation,
                evidence=finding.evidence,
            )
        )
    return tuple(assigned)


def _finding_sort_key(
    finding: _FindingDraft,
) -> tuple[int, int, int, str, int, str, int]:
    """返回冻结 finding ordering key。

    :param finding: confirmed finding。
    :returns: layer/severity/priority/rule/evidence/source/line key。
    :raises: 无。
    """

    minimum_sequence = min(
        (
            evidence.event_sequence
            for evidence in finding.evidence
            if evidence.event_sequence is not None
        ),
        default=sys.maxsize,
    )
    first_evidence = min(
        finding.evidence,
        key=lambda evidence: (
            str(evidence.source_path),
            evidence.line_number or 0,
        ),
    )
    return (
        _LAYER_ORDER[finding.layer],
        _SEVERITY_ORDER[finding.severity],
        _PRIORITY_ORDER[finding.priority],
        finding.rule_id,
        minimum_sequence,
        str(first_evidence.source_path),
        first_evidence.line_number or 0,
    )


def _order_limitations(
    limitations: tuple[ToolTraceLimitation, ...],
) -> tuple[ToolTraceLimitation, ...]:
    """稳定排序并去除完全相同的 limitations。

    :param limitations: 未排序 limitations。
    :returns: deterministic limitations。
    :raises: 无。
    """

    by_key: dict[
        tuple[str, str, tuple[tuple[str, int | None, int | None], ...]],
        ToolTraceLimitation,
    ] = {}
    for limitation in limitations:
        key = (
            limitation.reason_code,
            limitation.summary,
            tuple(
                (
                    str(evidence.source_path),
                    evidence.line_number,
                    evidence.event_sequence,
                )
                for evidence in limitation.evidence
            ),
        )
        by_key[key] = limitation
    return tuple(by_key[key] for key in sorted(by_key))


def _finding(
    *,
    rule_id: str,
    layer: ToolTraceAnalysisLayer,
    severity: ToolTraceFindingSeverity,
    priority: ToolTraceFindingPriority,
    title: str,
    summary: str,
    recommendation: str,
    evidence: tuple[ToolTraceEvidence, ...],
) -> _FindingDraft:
    """构造尚未分配最终 id 的 finding。

    :param rule_id: 稳定规则 id。
    :param layer: 归因层。
    :param severity: 严重程度。
    :param priority: 处置优先级。
    :param title: 中文标题。
    :param summary: 中文摘要。
    :param recommendation: owner-facing 建议。
    :param evidence: 非空直接证据。
    :returns: finding draft。
    :raises ValueError: evidence 为空时抛出。
    """

    if not evidence:
        raise ValueError("finding evidence must not be empty")
    return _FindingDraft(
        rule_id=rule_id,
        layer=layer,
        severity=severity,
        priority=priority,
        title=title,
        summary=summary,
        recommendation=recommendation,
        evidence=evidence,
    )


def _record_evidence(
    record: _RuleRecord,
    observed: Mapping[str, JsonValue],
    *,
    payload_ref: str | None = None,
) -> ToolTraceEvidence:
    """从规则 record 构造白名单 evidence。

    :param record: direct rule record。
    :param observed: 规则选择的 bounded observation。
    :param payload_ref: 可选覆盖 payload ref。
    :returns: direct evidence。
    :raises: 无。
    """

    return ToolTraceEvidence(
        kind=record.evidence_kind,
        source_path=record.source_path,
        line_number=record.line_number,
        event_id=record.event_id,
        event_sequence=record.event_sequence,
        event_type=record.event_type,
        trace_ref=record.trace_ref,
        payload_ref=record.payload_ref if payload_ref is None else payload_ref,
        observed=observed,
    )


def _diagnostic_evidence(
    diagnostic: ToolTraceInputDiagnostic,
) -> ToolTraceEvidence:
    """从 S1 input diagnostic 构造 direct evidence。

    :param diagnostic: S1 diagnostic。
    :returns: input/cold evidence。
    :raises: 无。
    """

    observed: dict[str, JsonValue] = {"diagnostic_code": diagnostic.code.value}
    if diagnostic.cause_type is not None:
        observed["cause_type"] = diagnostic.cause_type
    return ToolTraceEvidence(
        kind=(
            ToolTraceEvidenceKind.COLD_LINE
            if diagnostic.line_number is not None
            else ToolTraceEvidenceKind.INPUT_PATH
        ),
        source_path=diagnostic.source_path,
        line_number=diagnostic.line_number,
        event_id=diagnostic.event_id,
        event_sequence=diagnostic.event_sequence,
        event_type=None,
        trace_ref=None,
        payload_ref=None,
        observed=observed,
    )


def _record_limitation(
    reason_code: str,
    summary: str,
    record: _RuleRecord,
) -> ToolTraceLimitation:
    """构造 record-scoped limitation。

    :param reason_code: 稳定原因码。
    :param summary: 中文说明。
    :param record: direct record。
    :returns: limitation。
    :raises: 无。
    """

    return ToolTraceLimitation(
        reason_code=reason_code,
        signal_status=ToolTraceSignalStatus.LIMITED_SIGNAL,
        summary=summary,
        evidence=(_record_evidence(record, {}),),
    )


def _mapping(
    source: Mapping[str, JsonValue],
    field_name: str,
) -> Mapping[str, JsonValue] | None:
    """读取 direct JSON object 字段，不做 loose parsing。

    :param source: source-owned JSON object。
    :param field_name: 字段名。
    :returns: object；字段缺失/null/类型错误时返回 ``None``。
    :raises: 无。
    """

    value = source.get(field_name)
    if isinstance(value, Mapping):
        return value
    return None


def _optional_text(
    source: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取非空 direct text 字段，不做 coercion。

    :param source: source-owned JSON object。
    :param field_name: 字段名。
    :returns: 非空文本；缺失/null/类型错误时返回 ``None``。
    :raises: 无。
    """

    value = source.get(field_name)
    if isinstance(value, str) and value != "":
        return value
    return None


def _text_tuple(
    source: Mapping[str, JsonValue],
    field_name: str,
) -> tuple[str, ...]:
    """读取 direct string array，不兼容 coercion。

    :param source: source-owned JSON object。
    :param field_name: 字段名。
    :returns: 去重稳定文本元组；字段不完整时返回空元组。
    :raises: 无。
    """

    value = source.get(field_name)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item != "" for item in value
    ):
        return ()
    return tuple(
        sorted(
            {
                item
                for item in value
                if isinstance(item, str) and item != ""
            }
        )
    )


def _sorted_values(values: Iterable[str | None]) -> tuple[str, ...]:
    """把可迭代的可选文本投影为去重稳定元组。

    :param values: 由调用方提供的 ``str | None`` iterable。
    :returns: 去重 lexical order 文本。
    :raises TypeError: values 不可迭代时抛出。
    """

    return tuple(sorted({value for value in values if value is not None}))


def _bounded_observed(
    source: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """白名单选择 rule 允许进入 evidence 的 bounded scalars/refs。

    :param source: source-owned structured signal。
    :returns: 不含 raw body 的 observation。
    :raises: 无。
    """

    allowed_fields = (
        "status",
        "signal_source",
        _FIELD_FAILURE_KIND,
        "error_code",
        "cancel_reason",
        "policy_decision_kind",
        "policy_block_reason",
        "failure_reason",
        "budget_decision",
        "soft_threshold_exceeded",
        "hard_threshold_exceeded",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "policy_ref",
        "estimator_digest",
    )
    return {
        field_name: source[field_name]
        for field_name in allowed_fields
        if field_name in source
    }


def _invalid_record_count(
    diagnostics: tuple[ToolTraceInputDiagnostic, ...],
) -> int:
    """统计被 strict parser 排除的 cold records。

    :param diagnostics: S1 diagnostics。
    :returns: 具有 line number 且属于 parser/digest/ref 类的数量。
    :raises: 无。
    """

    invalid_codes = {
        ToolTraceInputDiagnosticCode.INVALID_JSON_LINE,
        ToolTraceInputDiagnosticCode.NON_OBJECT_JSON_LINE,
        ToolTraceInputDiagnosticCode.UNSUPPORTED_SCHEMA_VERSION,
        ToolTraceInputDiagnosticCode.INVALID_RECORD_FIELD,
        ToolTraceInputDiagnosticCode.LINE_DIGEST_MISMATCH,
        ToolTraceInputDiagnosticCode.COLD_DIGEST_MISMATCH,
        ToolTraceInputDiagnosticCode.COLD_REF_MISMATCH,
    }
    return sum(
        diagnostic.line_number is not None and diagnostic.code in invalid_codes
        for diagnostic in diagnostics
    )
