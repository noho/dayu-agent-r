"""Tool Trace Analyzer Host/Tool 行为规则的 owner-level 测试。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host.durable.tool_trace import (
    CompactorResponseDisposition,
    ResolvedCompactorEvidenceFact,
    ResolvedCompactorResponseIdentity,
    RunnerCallReconstructionConsumerBoundary,
    RunnerCallReconstructionDiagnostic,
    RunnerCallReconstructionSignal,
    RunnerCallReconstructionStatus,
    RunnerCallResolvedProjection,
    ToolTraceHotRow,
    ToolTraceResolvedJsonPayload,
    ToolTraceResolvedRowPayloads,
)
from dayu.host.tool_trace_analysis import (
    render_tool_trace_analysis_markdown,
    tool_trace_analysis_report_to_json,
)
from dayu.host.tool_trace_analysis_contracts import (
    ToolTraceAnalysisLayer,
    ToolTraceAnalysisPolicy,
    ToolTraceAnalysisSource,
    ToolTraceEvidenceKind,
    ToolTraceFindingPriority,
    ToolTraceFindingSeverity,
    ToolTraceInputMode,
    ToolTracePayloadMeasurementSource,
)
from dayu.host.tool_trace_analysis_input import (
    ToolTraceAnalysisDataset,
    ToolTraceColdFileIdentity,
    ToolTraceColdRecord,
    ToolTraceColdSnapshot,
    ToolTraceInputDiagnostic,
    ToolTraceInputDiagnosticCode,
    ToolTraceJoinedRecord,
    ToolTracePayloadCategory,
    ToolTraceResolvedPayloadMeasure,
)
from dayu.host.tool_trace_analysis_rules import build_tool_trace_analysis_report

_DIGEST = "sha256:" + "a" * 64


def _source(tmp_path: Path) -> ToolTraceAnalysisSource:
    """创建合法 cold-file source。

    :param tmp_path: pytest 临时目录。
    :returns: public source。
    :raises OSError: 创建 cold file 失败时抛出。
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


def _workspace_source(
    tmp_path: Path,
    *,
    cold_available: bool = True,
) -> ToolTraceAnalysisSource:
    """创建可表达 hot owner path 的合法 workspace source。

    :param tmp_path: pytest 临时目录。
    :param cold_available: 是否创建 expected cold JSONL。
    :returns: public workspace source。
    :raises OSError: 创建目录或文件失败时抛出。
    """

    workspace_path = (tmp_path / "workspace").absolute()
    cold_path = (
        workspace_path
        / ".dayu"
        / "artifacts"
        / "tool-trace"
        / "tool-trace-cold.jsonl"
    )
    hot_db_path = workspace_path / ".dayu" / "host" / "dayu_host.sqlite3"
    cold_path.parent.mkdir(parents=True)
    hot_db_path.parent.mkdir(parents=True)
    hot_db_path.touch()
    if cold_available:
        cold_path.write_text("", encoding="utf-8")
    return ToolTraceAnalysisSource(
        requested_path=workspace_path,
        mode=ToolTraceInputMode.WORKSPACE_DIRECTORY,
        cold_jsonl_path=cold_path,
        hot_db_path=hot_db_path,
        artifact_root=workspace_path / ".dayu" / "artifacts",
    )


def _record(
    source: ToolTraceAnalysisSource,
    *,
    sequence: int,
    event_type: str,
    run_id: str = "run-1",
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    normalized_arguments_digest: str | None = None,
    attempt_id: str | None = "attempt-1",
    execution_id: str | None = "execution-1",
    provider_request_id: str | None = None,
    client_correlation_id: str | None = None,
    diagnostic_refs: tuple[str, ...] = (),
    trace_summary: Mapping[str, JsonValue] | None = None,
) -> ToolTraceColdRecord:
    """构造规则层已接受的 typed cold record。

    :param source: public source。
    :param sequence: event sequence。
    :param event_type: event type。
    :param run_id: Run id。
    :param tool_call_id: 可选 tool-call id。
    :param tool_name: 可选工具名。
    :param normalized_arguments_digest: 可选 normalized digest。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param provider_request_id: 可选 provider-native request id。
    :param client_correlation_id: 可选 client correlation id。
    :param diagnostic_refs: source-owned diagnostic refs。
    :param trace_summary: source-owned structured summary。
    :returns: typed cold record。
    :raises: 无。
    """

    event_id = f"event-{sequence}"
    summary: Mapping[str, JsonValue] = (
        {"event_type": event_type} if trace_summary is None else trace_summary
    )
    fields: Mapping[str, JsonValue] = {
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "provider_request_id": provider_request_id,
        "client_correlation_id": client_correlation_id,
        "diagnostic_refs": list(diagnostic_refs),
        "normalized_arguments_digest": normalized_arguments_digest,
        "payload_ref": None,
        "trace_summary": summary,
    }
    return ToolTraceColdRecord(
        source_path=source.cold_jsonl_path,
        line_number=sequence,
        record_size_bytes=100 + sequence,
        event_id=event_id,
        event_sequence=sequence,
        event_type=event_type,
        event_class="canonical_fact",
        session_id="session-1",
        run_id=run_id,
        cold_trace_ref=f"tool-trace-cold:{event_id}",
        line_digest=_DIGEST,
        fields=fields,
    )


def _hot_row(record: ToolTraceColdRecord) -> ToolTraceHotRow:
    """从同一 owner event 构造 synthetic typed hot row。

    :param record: 同 event 的 cold record。
    :returns: typed hot row owner fact。
    :raises: 无。
    """

    provider_request_id = record.fields["provider_request_id"]
    diagnostic_refs = record.fields["diagnostic_refs"]
    trace_summary = record.fields["trace_summary"]
    assert provider_request_id is None or isinstance(provider_request_id, str)
    assert isinstance(diagnostic_refs, list)
    assert all(isinstance(item, str) for item in diagnostic_refs)
    assert isinstance(trace_summary, Mapping)
    typed_diagnostic_refs = tuple(
        item for item in diagnostic_refs if isinstance(item, str)
    )
    return ToolTraceHotRow(
        trace_id=record.event_id,
        event_id=record.event_id,
        event_sequence=record.event_sequence,
        event_type=record.event_type,
        event_class=record.event_class,
        session_id=record.session_id,
        run_id=record.run_id,
        attempt_id="attempt-1",
        execution_id="execution-1",
        tool_call_id=None,
        tool_name=None,
        provider_request_id=provider_request_id,
        diagnostic_ref=(
            typed_diagnostic_refs[0] if typed_diagnostic_refs else None
        ),
        normalized_arguments_digest=None,
        semantic_input_digest=None,
        result_digest=None,
        payload_ref=None,
        payload_digest=None,
        policy_decision_json=None,
        trace_summary=trace_summary,
        cold_trace_ref=record.cold_trace_ref,
        cold_trace_digest=record.line_digest,
        projected_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
    )


def _joined_record(
    record: ToolTraceColdRecord,
    *,
    source_event_payload: Mapping[str, JsonValue],
    runner_call_projection: RunnerCallResolvedProjection | None = None,
) -> ToolTraceJoinedRecord:
    """构造 resolver 已证明 source EventLog payload 的 joined record。

    :param record: strict cold record。
    :param source_event_payload: 模拟 resolver 校验通过的 source payload。
    :param runner_call_projection: 可选 typed runner-call resolver projection。
    :returns: hot/cold/resolver joined record。
    :raises: 无。
    """

    hot_row = _hot_row(record)
    return ToolTraceJoinedRecord(
        hot_row=hot_row,
        cold_record=record,
        resolved_payloads=ToolTraceResolvedRowPayloads(
            row=hot_row,
            source_event_payload=source_event_payload,
            descriptor_payload=None,
        ),
        runner_call_projection=runner_call_projection,
    )


def _compactor_projection(
    record: ToolTraceColdRecord,
) -> RunnerCallResolvedProjection:
    """构造 analysis rules 只读消费的 typed compactor projection。

    :param record: 对应 ``RUNNER_CALL_INPUT_ASSEMBLED`` cold record。
    :returns: 带 actual successful response identity 的 typed projection。
    :raises ValueError: synthetic Runner request identity 非 canonical 时抛出。
    """

    request_identity = build_runner_request_identity(
        run_id="compactor-engine-run-1",
        attempt_id=None,
        execution_id=None,
        iteration_id="compactor-iteration-1",
        iteration_index=0,
        runner_call_index=1,
    )
    signal = RunnerCallReconstructionSignal(
        event_id=record.event_id,
        event_sequence=record.event_sequence,
        session_id=record.session_id,
        run_id=record.run_id,
        attempt_id="attempt-1",
        execution_id="execution-1",
        runner_call_index=0,
        runner_call_kind="compactor_proposal",
        runner_call_trigger_reason="context_compaction_initial_proposal",
        iteration_id=None,
        manifest_ref="payload-manifest-1",
        manifest_digest=_DIGEST,
        message_count=0,
        role_sequence_digest=_DIGEST,
        input_projection_digest=_DIGEST,
        projector_metadata_summary=(),
        diagnostic=RunnerCallReconstructionDiagnostic(
            status=RunnerCallReconstructionStatus.COMPLETE,
            reason=None,
            missing_atom_kind=None,
            missing_ref_kind=None,
            missing_ref=None,
            observed_count=None,
            expected_count=None,
            observed_digest=None,
            expected_digest=None,
            consumer_boundary=(
                RunnerCallReconstructionConsumerBoundary.TOOL_TRACE_QUERY
            ),
        ),
    )
    resolved_payload = ToolTraceResolvedJsonPayload(
        payload_ref="payload-manifest-1",
        payload_digest=_DIGEST,
        payload_size_bytes=128,
        media_type="application/json",
        payload={},
    )
    return RunnerCallResolvedProjection(
        signal=signal,
        manifest=resolved_payload,
        runner_input_projection=resolved_payload,
        selected_tool_schema_snapshot=None,
        compactor_response_identity=ResolvedCompactorResponseIdentity(
            disposition=CompactorResponseDisposition.ACCEPTED,
            terminal_event_id="event-context-compacted-1",
            terminal_event_sequence=record.event_sequence + 10,
            compaction_operation_id="operation-1",
            compaction_attempt_number=1,
            proposal_manifest_ref="payload-manifest-1",
            proposal_manifest_digest=_DIGEST,
            successful_response_identity=SuccessfulRunnerResponseIdentity(
                effective_provider="provider-actual",
                effective_model="model-actual",
                runner_request_identity=request_identity,
                provider_request_id_availability=(
                    ProviderRequestIdAvailability.PRESENT
                ),
                provider_request_id="provider-request-actual",
            ),
            accepted_evidence_facts=(
                ResolvedCompactorEvidenceFact(
                    claim="Accepted evidence-backed claim.",
                    canonical_evidence_refs=("evidence:canonical-1",),
                ),
            ),
        ),
    )


def _dataset(
    source: ToolTraceAnalysisSource,
    records: tuple[ToolTraceColdRecord, ...],
    *,
    diagnostics: tuple[ToolTraceInputDiagnostic, ...] = (),
    measures: tuple[ToolTraceResolvedPayloadMeasure, ...] = (),
    hot_store_available: bool = False,
    hot_rows: tuple[ToolTraceHotRow, ...] = (),
    joined_records: tuple[ToolTraceJoinedRecord, ...] = (),
    cold_snapshot_available: bool = True,
) -> ToolTraceAnalysisDataset:
    """构造可信 normalized dataset。

    :param source: public source。
    :param records: valid cold records。
    :param diagnostics: S1 diagnostics。
    :param measures: verified byte measures。
    :param hot_store_available: 是否已取得 hot snapshot。
    :param hot_rows: hot snapshot owner rows。
    :param joined_records: resolver 校验通过的 hot/cold joins。
    :param cold_snapshot_available: 是否已取得 cold snapshot。
    :returns: immutable dataset。
    :raises: 无。
    """

    return ToolTraceAnalysisDataset(
        source=source,
        cold_snapshot=(
            ToolTraceColdSnapshot(
                cold_jsonl_path=source.cold_jsonl_path,
                cold_lock_path=source.cold_jsonl_path.with_name(
                    source.cold_jsonl_path.name + ".lock"
                ),
                prefix_byte_length=0,
                file_identity=ToolTraceColdFileIdentity(device=1, inode=2),
            )
            if cold_snapshot_available
            else None
        ),
        hot_store_available=hot_store_available,
        hot_event_sequence_watermark=(
            max((row.event_sequence for row in hot_rows), default=0)
            if hot_store_available
            else None
        ),
        hot_rows=hot_rows,
        cold_records=records,
        joined_records=joined_records,
        input_diagnostics=diagnostics,
        limitations=(),
        payload_measures=measures,
    )


def _rules(report_rule_ids: tuple[str, ...], expected: str) -> bool:
    """判断目标 rule 是否存在。

    :param report_rule_ids: report rule ids。
    :param expected: 目标 id。
    :returns: 存在时为 ``True``。
    :raises: 无。
    """

    return expected in report_rule_ids


def _partial_signal(status: str) -> Mapping[str, JsonValue]:
    """构造 producer contract 对齐的 partial signal。

    :param status: ``none`` 或 ``present``。
    :returns: typed partial signal JSON object。
    :raises ValueError: status 不受支持时抛出。
    """

    if status == "none":
        return {
            "schema_version": 1,
            "signal_source": "PROVIDER_PROTOCOL_ERROR",
            "partial_tool_call_count": 0,
            "summary_status": "none",
            "raw_payload_present": True,
            "partial_tool_calls": [],
        }
    if status == "present":
        return {
            "schema_version": 1,
            "signal_source": "PROVIDER_PROTOCOL_ERROR",
            "partial_tool_call_count": 1,
            "summary_status": "present",
            "raw_payload_present": True,
            "partial_tool_calls": [
                {
                    "tool_call_index": 0,
                    "tool_call_id": "call-partial",
                    "name_fragment": "lookup",
                    "arguments_byte_size": 4,
                    "arguments_sha256": "a" * 64,
                    "arguments_present": True,
                }
            ],
        }
    raise ValueError("unsupported partial signal status")


def test_engine_provider_rules_build_complete_group_from_direct_identities(
    tmp_path: Path,
) -> None:
    """Provider/protocol/terminal direct refs 形成一个 complete vendor block。"""

    source = _workspace_source(tmp_path)
    protocol = _record(
        source,
        sequence=1,
        event_type="PROVIDER_PROTOCOL_ERROR",
        provider_request_id="provider-1",
        client_correlation_id="client-1",
        diagnostic_refs=("raw-1", "provider-1"),
        trace_summary={
            "partial_tool_call_signal": _partial_signal("none"),
            "failure_metadata": {
                "failure_kind": "provider_protocol_error",
                "provider_error_code": "invalid_stream",
            },
        },
    )
    diagnostic = _record(
        source,
        sequence=2,
        event_type="PROVIDER_DIAGNOSTIC",
        provider_request_id="provider-1",
        client_correlation_id="client-1",
        diagnostic_refs=("diag-1", "provider-1"),
    )
    terminal = _record(
        source,
        sequence=3,
        event_type="RUN_FAILED",
        provider_request_id="provider-1",
        client_correlation_id="client-1",
        diagnostic_refs=("engine-terminal",),
        trace_summary={"engine_event_ref": "engine-terminal"},
    )
    records = (protocol, diagnostic, terminal)
    joined = tuple(
        _joined_record(
            record,
            source_event_payload={
                "iteration_id": "iteration-1",
                "error_code": (
                    "invalid_stream"
                    if record.event_type == "PROVIDER_PROTOCOL_ERROR"
                    else None
                ),
                "diagnostic_code": (
                    "usage_field_malformed"
                    if record.event_type == "PROVIDER_DIAGNOSTIC"
                    else None
                ),
            },
        )
        for record in records
    )

    report = build_tool_trace_analysis_report(
        _dataset(
            source,
            records,
            hot_store_available=True,
            hot_rows=tuple(_hot_row(record) for record in records),
            joined_records=joined,
        ),
        source,
        ToolTraceAnalysisPolicy(),
    )
    by_rule = {item.rule_id: item for item in report.findings}
    block = report.vendor_debugging[0]

    assert set(by_rule) >= {
        "engine.provider_diagnostic",
        "engine.provider_protocol_error",
    }
    assert block.status.value == "available"
    assert block.provider_request_id == "provider-1"
    assert block.client_correlation_id == "client-1"
    assert block.attempt_ids == ("attempt-1",)
    assert block.execution_ids == ("execution-1",)
    assert block.iteration_ids == ("iteration-1",)
    assert tuple(item.event_id for item in block.tool_trace_refs) == (
        "event-1",
        "event-2",
        "event-3",
    )
    assert block.partial_tool_call_signal.value == "available"
    assert block.limitations == ()


def test_vendor_grouping_uses_client_only_and_keeps_missing_ids_per_event(
    tmp_path: Path,
) -> None:
    """无 provider id 只按 client id 分组；两者皆缺时每 event 独立。"""

    source = _workspace_source(tmp_path)
    client_only_records = (
        _record(
            source,
            sequence=1,
            event_type="PROVIDER_DIAGNOSTIC",
            client_correlation_id="client-only",
        ),
        _record(
            source,
            sequence=2,
            event_type="RUN_FAILED",
            client_correlation_id="client-only",
            trace_summary={"engine_event_ref": "engine-2"},
        ),
    )
    no_id_records = (
        _record(
            source,
            sequence=3,
            event_type="PROVIDER_DIAGNOSTIC",
        ),
        _record(
            source,
            sequence=4,
            event_type="PROVIDER_PROTOCOL_ERROR",
            trace_summary={"partial_tool_call_signal": _partial_signal("none")},
        ),
    )
    records = client_only_records + no_id_records
    joined = tuple(
        _joined_record(
            record,
            source_event_payload={"iteration_id": f"iteration-{record.event_sequence}"},
        )
        for record in records
    )

    report = build_tool_trace_analysis_report(
        _dataset(
            source,
            records,
            hot_store_available=True,
            hot_rows=tuple(_hot_row(record) for record in records),
            joined_records=joined,
        ),
        source,
        ToolTraceAnalysisPolicy(),
    )
    client_blocks = [
        block
        for block in report.vendor_debugging
        if block.client_correlation_id == "client-only"
    ]
    no_id_blocks = [
        block
        for block in report.vendor_debugging
        if block.client_correlation_id is None
    ]

    assert len(client_blocks) == 1
    assert client_blocks[0].provider_request_id is None
    assert len(client_blocks[0].tool_trace_refs) == 2
    assert len(no_id_blocks) == 2
    assert all(len(block.tool_trace_refs) == 1 for block in no_id_blocks)
    issue_64 = [
        limitation.summary
        for block in report.vendor_debugging
        for limitation in block.limitations
        if limitation.reason_code == "provider_request_id_unavailable"
    ]
    assert issue_64
    assert all(
        "native Anthropic / Claude Code gateway-specific signal" in summary
        and "未推断 adapter/provider family" in summary
        for summary in issue_64
    )


def test_same_provider_id_conflicting_client_and_local_refs_is_finding(
    tmp_path: Path,
) -> None:
    """同 provider id 的 client/local refs 冲突必须显式 finding。"""

    source = _workspace_source(tmp_path)
    first = _record(
        source,
        sequence=1,
        event_type="PROVIDER_DIAGNOSTIC",
        attempt_id="attempt-1",
        execution_id="execution-1",
        provider_request_id="provider-conflict",
        client_correlation_id="client-a",
    )
    second = _record(
        source,
        sequence=2,
        event_type="PROVIDER_PROTOCOL_ERROR",
        attempt_id="attempt-2",
        execution_id="execution-2",
        provider_request_id="provider-conflict",
        client_correlation_id="client-b",
        trace_summary={"partial_tool_call_signal": _partial_signal("none")},
    )
    records = (first, second)
    joined = (
        _joined_record(
            first,
            source_event_payload={"iteration_id": "iteration-a"},
        ),
        _joined_record(
            second,
            source_event_payload={"iteration_id": "iteration-b"},
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(
            source,
            records,
            hot_store_available=True,
            hot_rows=(_hot_row(first), _hot_row(second)),
            joined_records=joined,
        ),
        source,
        ToolTraceAnalysisPolicy(),
    )
    conflict = next(
        item
        for item in report.findings
        if item.rule_id == "engine.vendor_correlation_conflict"
    )

    assert conflict.layer is ToolTraceAnalysisLayer.ENGINE
    assert conflict.severity is ToolTraceFindingSeverity.ERROR
    assert conflict.priority is ToolTraceFindingPriority.MEDIUM
    assert len(conflict.evidence) == 2
    conflict_fields = conflict.evidence[0].observed["conflict_fields"]
    assert isinstance(conflict_fields, list)
    assert all(isinstance(item, str) for item in conflict_fields)
    assert {
        "client_correlation_id",
        "attempt_id",
        "execution_id",
        "iteration_id",
    }.issubset(conflict_fields)
    assert report.vendor_debugging[0].status.value == "limited_signal"
    assert any(
        item.reason_code == "vendor_correlation_conflict"
        for item in report.vendor_debugging[0].limitations
    )


def test_partial_signal_absent_none_and_present_remain_distinct(
    tmp_path: Path,
) -> None:
    """Absent signal 是 limited；explicit none/present 都是 available signal。"""

    source = _source(tmp_path)
    records = (
        _record(
            source,
            sequence=1,
            event_type="PROVIDER_PROTOCOL_ERROR",
            provider_request_id="provider-absent",
            client_correlation_id="client-absent",
        ),
        _record(
            source,
            sequence=2,
            event_type="PROVIDER_PROTOCOL_ERROR",
            provider_request_id="provider-none",
            client_correlation_id="client-none",
            trace_summary={"partial_tool_call_signal": _partial_signal("none")},
        ),
        _record(
            source,
            sequence=3,
            event_type="PROVIDER_PROTOCOL_ERROR",
            provider_request_id="provider-present",
            client_correlation_id="client-present",
            trace_summary={
                "partial_tool_call_signal": _partial_signal("present")
            },
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, records),
        source,
        ToolTraceAnalysisPolicy(),
    )
    blocks = {
        block.provider_request_id: block for block in report.vendor_debugging
    }
    rule_ids = tuple(item.rule_id for item in report.findings)

    assert blocks["provider-absent"].partial_tool_call_signal.value == (
        "limited_signal"
    )
    assert blocks["provider-none"].partial_tool_call_signal.value == "available"
    assert blocks["provider-present"].partial_tool_call_signal.value == (
        "available"
    )
    assert rule_ids.count("engine.partial_tool_call_signal_missing") == 1
    assert rule_ids.count("engine.partial_tool_call_present") == 1
    assert any(
        item.reason_code == "partial_tool_call_signal_missing"
        for item in blocks["provider-absent"].limitations
    )


def test_file_only_provider_signal_is_limited_and_usage_never_joins(
    tmp_path: Path,
) -> None:
    """File-only 缺 payload/iteration 明确 limited；usage 零参与 vendor grouping。"""

    source = _source(tmp_path)
    protocol = _record(
        source,
        sequence=1,
        event_type="PROVIDER_PROTOCOL_ERROR",
        provider_request_id="provider-1",
        client_correlation_id="client-1",
        trace_summary={"partial_tool_call_signal": _partial_signal("none")},
    )
    usage = _record(
        source,
        sequence=2,
        event_type="USAGE_REPORTED",
        provider_request_id="provider-1",
        client_correlation_id="client-1",
        trace_summary={
            "iteration_id": "usage-iteration",
            "context_pressure": {"status": "observed"},
        },
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, (protocol, usage)),
        source,
        ToolTraceAnalysisPolicy(),
    )
    block = report.vendor_debugging[0]
    reason_codes = {item.reason_code for item in block.limitations}

    assert len(report.vendor_debugging) == 1
    assert tuple(item.event_id for item in block.tool_trace_refs) == ("event-1",)
    assert block.iteration_ids == ()
    assert {
        "vendor_iteration_id_unavailable",
        "vendor_source_payload_unavailable",
    }.issubset(reason_codes)
    assert block.status.value == "limited_signal"


def test_runner_observation_mismatch_is_engine_finding(
    tmp_path: Path,
) -> None:
    """Runner prepared/observed count/digest mismatch 归 Engine finding。"""

    source = _source(tmp_path)
    record = _record(
        source,
        sequence=1,
        event_type="RUNNER_CALL_INPUT_ASSEMBLED",
        trace_summary={
            "iteration_id": "iteration-1",
            "diagnostic": {
                "status": "mismatch",
                "reason": "role_sequence_digest_mismatch",
                "observed_count": 3,
                "expected_count": 2,
                "observed_digest": "sha256:" + "b" * 64,
                "expected_digest": "sha256:" + "c" * 64,
                "consumer_boundary": "tool_trace_query",
            },
        },
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, (record,)),
        source,
        ToolTraceAnalysisPolicy(),
    )
    finding = next(
        item
        for item in report.findings
        if item.rule_id == "engine.runner_observation_mismatch"
    )

    assert finding.layer is ToolTraceAnalysisLayer.ENGINE
    assert finding.evidence[0].observed["observed_count"] == 3
    assert finding.evidence[0].observed["expected_count"] == 2


def test_duplicate_governance_and_repeated_request_have_distinct_owners(
    tmp_path: Path,
) -> None:
    """Host duplicate fact 与 Tool repeated observation 不混为同一语义。"""

    source = _source(tmp_path)
    records = (
        _record(
            source,
            sequence=1,
            event_type="TOOL_CALL_REQUESTED",
            tool_call_id="call-1",
            tool_name="lookup",
            normalized_arguments_digest=_DIGEST,
        ),
        _record(
            source,
            sequence=2,
            event_type="TOOL_CALL_REQUESTED",
            tool_call_id="call-2",
            tool_name="lookup",
            normalized_arguments_digest=_DIGEST,
        ),
        _record(
            source,
            sequence=3,
            event_type="TOOL_CALL_GOVERNED",
            tool_call_id="call-2",
            tool_name="lookup",
            trace_summary={
                "duplicate_key": "duplicate-1",
                "duplicate_decision": "reuse",
                "duplicate_scope": {"kind": "attempt"},
                "reuse_prior_event_refs": [{"event_id": "event-1"}],
            },
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, records),
        source,
        ToolTraceAnalysisPolicy(),
    )
    by_rule = {item.rule_id: item for item in report.findings}

    assert by_rule["host.duplicate_governance"].layer is ToolTraceAnalysisLayer.HOST
    assert (
        by_rule["tool.repeated_identical_request"].layer
        is ToolTraceAnalysisLayer.TOOL
    )
    assert by_rule["host.duplicate_governance"].evidence[0].observed[
        "duplicate_decision"
    ] == "reuse"


def test_tool_failure_cancel_and_policy_block_keep_source_owner(
    tmp_path: Path,
) -> None:
    """Tool failure/cancel 与 Host policy block 分层归因。"""

    source = _source(tmp_path)
    records = (
        _record(
            source,
            sequence=1,
            event_type="TOOL_RESULT_ACCEPTED",
            tool_call_id="failed",
            tool_name="lookup",
            trace_summary={
                "failure_metadata": {
                    "failure_kind": "tool_failed",
                    "error_code": "lookup_failed",
                }
            },
        ),
        _record(
            source,
            sequence=2,
            event_type="TOOL_RESULT_ACCEPTED",
            tool_call_id="cancelled",
            tool_name="lookup",
            trace_summary={
                "failure_metadata": {
                    "failure_kind": "tool_cancelled",
                    "cancel_reason": "host_cancelled",
                }
            },
        ),
        _record(
            source,
            sequence=3,
            event_type="TOOL_RESULT_ACCEPTED",
            tool_call_id="blocked",
            tool_name="lookup",
            trace_summary={
                "failure_metadata": {
                    "failure_kind": "policy_blocked",
                    "policy_decision_kind": "governed_error",
                    "policy_block_reason": "approval_required",
                }
            },
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, records),
        source,
        ToolTraceAnalysisPolicy(),
    )
    by_rule = {item.rule_id: item for item in report.findings}

    assert by_rule["tool.tool_failed"].layer is ToolTraceAnalysisLayer.TOOL
    assert by_rule["tool.tool_cancelled"].layer is ToolTraceAnalysisLayer.TOOL
    assert by_rule["host.policy_blocked"].layer is ToolTraceAnalysisLayer.HOST


def test_timing_uses_direct_meta_and_requires_sample_and_dual_threshold(
    tmp_path: Path,
) -> None:
    """Latency 只用 direct meta，小样本不告警，缺失形成 limitation。"""

    source = _source(tmp_path)
    records = tuple(
        _record(
            source,
            sequence=index,
            event_type="TOOL_RESULT_ACCEPTED",
            tool_call_id=f"call-{index}",
            tool_name="lookup",
            trace_summary={
                "tool_timing": {
                    "status": "available",
                    "duration_ms": duration,
                    "duration_source": "tool_result_meta",
                }
            },
        )
        for index, duration in enumerate((100, 100, 100, 100, 2000), start=1)
    ) + (
        _record(
            source,
            sequence=6,
            event_type="TOOL_RESULT_ACCEPTED",
            tool_call_id="missing",
            tool_name="other",
            trace_summary={
                "tool_timing": {
                    "status": "missing_tool_result_meta",
                    "duration_ms": None,
                    "duration_source": None,
                }
            },
        ),
        _record(
            source,
            sequence=7,
            event_type="TOOL_RESULT_ACCEPTED",
            tool_call_id="small",
            tool_name="small-sample",
            trace_summary={
                "tool_timing": {
                    "status": "available",
                    "duration_ms": 9999,
                    "duration_source": "tool_result_meta",
                }
            },
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, records),
        source,
        ToolTraceAnalysisPolicy(),
    )
    outliers = [
        item for item in report.findings if item.rule_id == "tool.latency_outlier"
    ]

    assert len(outliers) == 1
    assert outliers[0].evidence[0].event_id == "event-5"
    assert outliers[0].evidence[0].observed["duration_source"] == (
        "tool_result_meta"
    )
    assert any(
        item.reason_code == "tool_timing_missing"
        for item in report.limitations
    )
    assert not any(
        item.evidence[0].event_id == "event-7" for item in outliers
    )


def test_truncation_matching_missing_and_wrong_cursor(
    tmp_path: Path,
) -> None:
    """Truncation 只按同 Run 后续 direct cursor 匹配 fetch_more。"""

    source = _source(tmp_path)
    records = (
        _record(
            source,
            sequence=1,
            event_type="TOOL_RESULT_ACCEPTED",
            run_id="run-match",
            tool_call_id="result-match",
            tool_name="lookup",
            trace_summary={
                "truncation": {"applied": True, "cursor_hint": "cursor-match"}
            },
        ),
        _record(
            source,
            sequence=2,
            event_type="TOOL_CALL_REQUESTED",
            run_id="run-match",
            tool_call_id="fetch-match",
            tool_name="fetch_more",
            trace_summary={"tool_request": {"arguments": {"cursor": "cursor-match"}}},
        ),
        _record(
            source,
            sequence=3,
            event_type="TOOL_RESULT_ACCEPTED",
            run_id="run-none",
            tool_call_id="result-none",
            tool_name="lookup",
            trace_summary={
                "truncation": {"applied": True, "cursor_hint": "cursor-none"}
            },
        ),
        _record(
            source,
            sequence=4,
            event_type="RUN_SUCCEEDED",
            run_id="run-none",
        ),
        _record(
            source,
            sequence=5,
            event_type="TOOL_RESULT_ACCEPTED",
            run_id="run-wrong",
            tool_call_id="result-wrong",
            tool_name="lookup",
            trace_summary={
                "truncation": {"applied": True, "cursor_hint": "cursor-right"}
            },
        ),
        _record(
            source,
            sequence=6,
            event_type="TOOL_CALL_REQUESTED",
            run_id="run-wrong",
            tool_call_id="fetch-wrong",
            tool_name="fetch_more",
            trace_summary={"tool_request": {"arguments": {"cursor": "cursor-wrong"}}},
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, records),
        source,
        ToolTraceAnalysisPolicy(),
    )
    no_follow = [
        item
        for item in report.findings
        if item.rule_id == "tool.truncation_not_followed"
    ]
    mismatch = [
        item
        for item in report.findings
        if item.rule_id == "tool.fetch_more_cursor_mismatch"
    ]

    assert len(no_follow) == 1
    assert no_follow[0].evidence[0].event_id == "event-3"
    assert len(mismatch) == 1
    assert mismatch[0].evidence[0].event_id == "event-5"
    assert not any(
        item.evidence[0].event_id == "event-1"
        for item in no_follow + mismatch
    )


def test_context_pressure_soft_hard_compaction_and_usage_are_direct(
    tmp_path: Path,
) -> None:
    """Context findings 消费 direct signal，usage 不进入 vendor grouping。"""

    source = _source(tmp_path)
    records = (
        _record(
            source,
            sequence=1,
            event_type="USAGE_REPORTED",
            run_id="run-context",
            trace_summary={
                "context_pressure": {
                    "status": "observed",
                    "soft_threshold_exceeded": True,
                    "hard_threshold_exceeded": False,
                    "prompt_tokens": 100,
                }
            },
        ),
        _record(
            source,
            sequence=2,
            event_type="USAGE_REPORTED",
            run_id="run-context",
            trace_summary={
                "context_pressure": {
                    "status": "observed",
                    "soft_threshold_exceeded": True,
                    "hard_threshold_exceeded": True,
                    "prompt_tokens": 200,
                }
            },
        ),
        _record(
            source,
            sequence=3,
            event_type="CONTEXT_COMPACTION_FAILED",
            run_id="run-context",
            trace_summary={
                "context_pressure": {"status": "compaction_failed"},
                "failure_metadata": {
                    "failure_kind": "context_compaction_failed",
                    "failure_reason": "quality_check_failed",
                },
            },
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, records),
        source,
        ToolTraceAnalysisPolicy(),
    )
    rule_ids = tuple(item.rule_id for item in report.findings)

    assert _rules(rule_ids, "host.context_pressure_soft")
    assert _rules(rule_ids, "host.context_pressure_hard")
    assert _rules(rule_ids, "host.context_compaction_failed")
    assert report.vendor_debugging == ()
    assert report.runs[0].context_pressure_observation_count == 3


def test_payload_categories_rank_threshold_and_keep_measurement_sources(
    tmp_path: Path,
) -> None:
    """所有 payload categories 参与 ranking，cold/resolved source 不混淆。"""

    source = _workspace_source(tmp_path)
    hot_db_path = source.hot_db_path
    assert hot_db_path is not None
    records = tuple(
        _record(
            source,
            sequence=index,
            event_type="RUN_SUCCEEDED",
            run_id="run-payload",
        )
        for index in range(1, 9)
    )
    categories = tuple(ToolTracePayloadCategory)
    measures = tuple(
        ToolTraceResolvedPayloadMeasure(
            category=category,
            payload_ref=f"payload-{category.value}",
            payload_digest=_DIGEST,
            payload_size_bytes=1000 + index,
            event_id=f"event-{index}",
            event_sequence=index,
        )
        for index, category in enumerate(categories, start=1)
    )
    diagnostic = ToolTraceInputDiagnostic(
        code=ToolTraceInputDiagnosticCode.PAYLOAD_UNRESOLVABLE,
        source_path=hot_db_path,
        summary="resolver failed",
        event_id="event-8",
        event_sequence=8,
        cause_type="HostDurableError",
    )

    report = build_tool_trace_analysis_report(
        _dataset(
            source,
            records,
            diagnostics=(diagnostic,),
            measures=measures,
            hot_store_available=True,
            hot_rows=tuple(_hot_row(record) for record in records),
        ),
        source,
        ToolTraceAnalysisPolicy(
            large_payload_threshold_bytes=1004,
            payload_ranking_limit=20,
        ),
    )

    assert {item.category for item in report.payload_rankings} == {
        item.value for item in categories
    }
    cold_measure = next(
        item
        for item in report.payload_rankings
        if item.category == ToolTracePayloadCategory.COLD_LINE.value
    )
    resolved_measure = next(
        item
        for item in report.payload_rankings
        if item.category == ToolTracePayloadCategory.TOOL_RESULT.value
    )
    assert (
        cold_measure.measurement_source
        is ToolTracePayloadMeasurementSource.COLD_JSONL_RECORD_BYTES
    )
    assert (
        resolved_measure.measurement_source
        is ToolTracePayloadMeasurementSource.RESOLVED_PAYLOAD_BYTES
    )
    assert cold_measure.evidence[0].kind is ToolTraceEvidenceKind.COLD_LINE
    assert cold_measure.evidence[0].source_path == source.cold_jsonl_path
    assert cold_measure.evidence[0].line_number is not None
    assert (
        resolved_measure.evidence[0].kind
        is ToolTraceEvidenceKind.RESOLVED_PAYLOAD
    )
    assert resolved_measure.evidence[0].source_path == source.hot_db_path
    assert resolved_measure.evidence[0].line_number is None
    assert all(
        item.size_bytes >= 1004
        for item in report.payload_rankings
        if any(
            finding.rule_id == "payload.large_payload"
            and finding.evidence == item.evidence
            for finding in report.findings
        )
    )
    assert any(
        item.reason_code == "payload_size_unverified"
        for item in report.limitations
    )


def test_same_event_cold_and_resolved_measures_keep_distinct_owner_evidence(
    tmp_path: Path,
) -> None:
    """同 event 的 cold record 与 resolved payload 仍使用各自 owner 证据。"""

    source = _workspace_source(tmp_path)
    record = _record(
        source,
        sequence=1,
        event_type="TOOL_RESULT_ACCEPTED",
        run_id="run-payload",
    )
    measures = (
        ToolTraceResolvedPayloadMeasure(
            category=ToolTracePayloadCategory.COLD_LINE,
            payload_ref=record.cold_trace_ref,
            payload_digest=_DIGEST,
            payload_size_bytes=101,
            event_id=record.event_id,
            event_sequence=record.event_sequence,
        ),
        ToolTraceResolvedPayloadMeasure(
            category=ToolTracePayloadCategory.TOOL_RESULT,
            payload_ref="payload-tool-result",
            payload_digest=_DIGEST,
            payload_size_bytes=202,
            event_id=record.event_id,
            event_sequence=record.event_sequence,
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(
            source,
            (record,),
            measures=measures,
            hot_store_available=True,
            hot_rows=(_hot_row(record),),
        ),
        source,
        ToolTraceAnalysisPolicy(),
    )
    by_category = {item.category: item for item in report.payload_rankings}
    cold_measure = by_category[ToolTracePayloadCategory.COLD_LINE.value]
    resolved_measure = by_category[ToolTracePayloadCategory.TOOL_RESULT.value]

    assert (
        cold_measure.measurement_source
        is ToolTracePayloadMeasurementSource.COLD_JSONL_RECORD_BYTES
    )
    assert cold_measure.evidence[0].kind is ToolTraceEvidenceKind.COLD_LINE
    assert cold_measure.evidence[0].source_path == source.cold_jsonl_path
    assert cold_measure.evidence[0].line_number == 1
    assert (
        resolved_measure.measurement_source
        is ToolTracePayloadMeasurementSource.RESOLVED_PAYLOAD_BYTES
    )
    assert (
        resolved_measure.evidence[0].kind
        is ToolTraceEvidenceKind.RESOLVED_PAYLOAD
    )
    assert resolved_measure.evidence[0].source_path == source.hot_db_path
    assert resolved_measure.evidence[0].line_number is None
    assert resolved_measure.evidence[0].event_id == record.event_id
    assert resolved_measure.evidence[0].event_sequence == record.event_sequence
    assert resolved_measure.evidence[0].payload_ref == "payload-tool-result"
    assert resolved_measure.evidence[0].observed == {
        "category": ToolTracePayloadCategory.TOOL_RESULT.value,
        "size_bytes": 202,
    }


def test_resolved_measure_without_hot_owner_facts_is_rejected(
    tmp_path: Path,
) -> None:
    """Synthetic resolved measure 缺少 hot owner facts 时严格拒绝。"""

    source = _source(tmp_path)
    record = _record(
        source,
        sequence=1,
        event_type="TOOL_RESULT_ACCEPTED",
    )
    resolved_measure = ToolTraceResolvedPayloadMeasure(
        category=ToolTracePayloadCategory.TOOL_RESULT,
        payload_ref="payload-tool-result",
        payload_digest=_DIGEST,
        payload_size_bytes=202,
        event_id=record.event_id,
        event_sequence=record.event_sequence,
    )

    with pytest.raises(
        ValueError,
        match="requires available hot store owner",
    ):
        build_tool_trace_analysis_report(
            _dataset(source, (record,), measures=(resolved_measure,)),
            source,
            ToolTraceAnalysisPolicy(),
        )


def test_hot_only_summary_keeps_expected_lock_path_without_claiming_lock_use(
    tmp_path: Path,
) -> None:
    """Hot-only 报告保留 expected path，且 capability 明确未读取 cold。"""

    source = _workspace_source(tmp_path, cold_available=False)
    report = build_tool_trace_analysis_report(
        _dataset(
            source,
            (),
            hot_store_available=True,
            cold_snapshot_available=False,
        ),
        source,
        ToolTraceAnalysisPolicy(),
    )
    markdown = render_tool_trace_analysis_markdown(report)

    assert report.input.cold_lock_path == source.cold_jsonl_path.with_name(
        source.cold_jsonl_path.name + ".lock"
    )
    assert report.input.capabilities.cold is False
    assert "expected cold lock path" in markdown
    assert "cold capability：`false`" in markdown
    assert "只有 `true` 表示本次实际获取上述 lock" in markdown


def test_waiting_and_unknown_events_only_affect_direct_summary(
    tmp_path: Path,
) -> None:
    """Awaiting/waiting/unknown 不制造 speculative finding。"""

    source = _source(tmp_path)
    records = (
        _record(
            source,
            sequence=1,
            event_type="TOOL_AWAITING",
            run_id="run-wait",
            tool_call_id="call-wait",
            tool_name="external_job",
        ),
        _record(
            source,
            sequence=2,
            event_type="RUN_WAITING",
            run_id="run-wait",
        ),
        _record(
            source,
            sequence=3,
            event_type="UNKNOWN_FUTURE_EVENT",
            run_id="run-wait",
        ),
    )

    report = build_tool_trace_analysis_report(
        _dataset(source, records),
        source,
        ToolTraceAnalysisPolicy(),
    )

    assert report.findings == ()
    assert report.runs[0].tool_awaiting_count == 1
    assert report.runs[0].run_waiting_count == 1
    assert report.runs[0].event_count == 3


def test_finding_order_and_ids_are_deterministic(
    tmp_path: Path,
) -> None:
    """相同 typed records 的输入顺序不改变 finding order/id。"""

    source = _source(tmp_path)
    records = (
        _record(
            source,
            sequence=2,
            event_type="TOOL_RESULT_ACCEPTED",
            tool_call_id="failed",
            tool_name="lookup",
            trace_summary={
                "failure_metadata": {
                    "failure_kind": "tool_failed",
                    "error_code": "failed",
                }
            },
        ),
        _record(
            source,
            sequence=1,
            event_type="TOOL_RESULT_ACCEPTED",
            tool_call_id="blocked",
            tool_name="lookup",
            trace_summary={
                "failure_metadata": {
                    "failure_kind": "policy_blocked",
                    "policy_decision_kind": "blocked",
                    "policy_block_reason": "policy",
                }
            },
        ),
    )
    policy = ToolTraceAnalysisPolicy()

    first = build_tool_trace_analysis_report(
        _dataset(source, records),
        source,
        policy,
    )
    second = build_tool_trace_analysis_report(
        _dataset(source, tuple(reversed(records))),
        source,
        policy,
    )

    assert tuple(
        (item.finding_id, item.rule_id) for item in first.findings
    ) == tuple((item.finding_id, item.rule_id) for item in second.findings)
    assert first.findings[0].finding_id == "TT-HOST-0001"
    assert first.findings[-1].finding_id == "TT-TOOL-0001"
    assert first.findings[0].severity is ToolTraceFindingSeverity.WARNING
    assert first.findings[0].priority is ToolTraceFindingPriority.MEDIUM


def test_compactor_response_summary_comes_only_from_typed_resolver_projection(
    tmp_path: Path,
) -> None:
    """schema v2 summary 从 typed resolver 投影 actual response 白名单字段。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: summary 脱离 typed projection 或字段错误时抛出。
    """

    source = _workspace_source(tmp_path)
    record = _record(
        source,
        sequence=1,
        event_type="RUNNER_CALL_INPUT_ASSEMBLED",
    )
    projection = _compactor_projection(record)
    joined = _joined_record(
        record,
        source_event_payload={
            "authorization": "credential-secret",
            "selection_label": "selection-label-secret",
            "raw_payload": "raw-payload-secret",
            "prompt": "prompt-secret",
        },
        runner_call_projection=projection,
    )

    report = build_tool_trace_analysis_report(
        _dataset(
            source,
            (record,),
            hot_store_available=True,
            hot_rows=(_hot_row(record),),
            joined_records=(joined,),
        ),
        source,
        ToolTraceAnalysisPolicy(),
    )

    assert report.schema_version == 2
    assert len(report.compactor_responses) == 1
    summary = report.compactor_responses[0]
    assert summary.parent_host_run_id == "run-1"
    assert summary.disposition is CompactorResponseDisposition.ACCEPTED
    assert summary.effective_provider == "provider-actual"
    assert summary.effective_model == "model-actual"
    assert summary.provider_request_id_availability is (
        ProviderRequestIdAvailability.PRESENT
    )
    assert summary.provider_request_id == "provider-request-actual"
    response = projection.compactor_response_identity
    assert response is not None
    successful = response.successful_response_identity
    assert successful is not None
    assert summary.runner_request_identity == successful.runner_request_identity
    assert summary.accepted_evidence_facts is response.accepted_evidence_facts
    serialized = json.loads(tool_trace_analysis_report_to_json(report))
    projected_facts = serialized["compactor_responses"][0][
        "accepted_evidence_facts"
    ]
    assert projected_facts == [
        {
            "claim": "Accepted evidence-backed claim.",
            "canonical_evidence_refs": ["evidence:canonical-1"],
        }
    ]
    assert set(projected_facts[0]) == {"claim", "canonical_evidence_refs"}
    rendered = tool_trace_analysis_report_to_json(report) + (
        render_tool_trace_analysis_markdown(report)
    )
    for forbidden in (
        "credential-secret",
        "selection-label-secret",
        "raw-payload-secret",
        "prompt-secret",
    ):
        assert forbidden not in rendered


def test_rejected_compactor_response_identity_projects_from_typed_owner_to_all_outputs(
    tmp_path: Path,
) -> None:
    """post-success rejection 的实际 identity 同源进入 typed/JSON/Markdown。

    邻近 event payload 刻意携带冲突的 config-like identity；analysis owner 只能
    消费 resolver 的 ``successful_response_identity``，不得从邻近事实推断。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: disposition、identity 同源或 renderer 投影漂移时抛出。
    """

    source = _workspace_source(tmp_path)
    record = _record(
        source,
        sequence=1,
        event_type="RUNNER_CALL_INPUT_ASSEMBLED",
    )
    accepted_projection = _compactor_projection(record)
    accepted_response = accepted_projection.compactor_response_identity
    assert accepted_response is not None
    successful = accepted_response.successful_response_identity
    assert successful is not None
    rejected_projection = replace(
        accepted_projection,
        compactor_response_identity=replace(
            accepted_response,
            disposition=CompactorResponseDisposition.ATTEMPT_REJECTED,
            terminal_event_id="event-context-compaction-attempt-rejected-1",
            accepted_evidence_facts=(),
        ),
    )
    joined = _joined_record(
        record,
        source_event_payload={
            "configured_provider": "provider-neighbor-poison",
            "configured_model": "model-neighbor-poison",
            "provider_request_id": "request-neighbor-poison",
        },
        runner_call_projection=rejected_projection,
    )

    report = build_tool_trace_analysis_report(
        _dataset(
            source,
            (record,),
            hot_store_available=True,
            hot_rows=(_hot_row(record),),
            joined_records=(joined,),
        ),
        source,
        ToolTraceAnalysisPolicy(),
    )

    assert len(report.compactor_responses) == 1
    summary = report.compactor_responses[0]
    assert summary.disposition is CompactorResponseDisposition.ATTEMPT_REJECTED
    assert summary.effective_provider == successful.effective_provider
    assert summary.effective_model == successful.effective_model
    assert summary.runner_request_identity == successful.runner_request_identity
    assert (
        summary.provider_request_id_availability
        is successful.provider_request_id_availability
    )
    assert summary.provider_request_id == successful.provider_request_id
    assert summary.accepted_evidence_facts == ()

    serialized = json.loads(tool_trace_analysis_report_to_json(report))
    projected = serialized["compactor_responses"][0]
    assert projected["disposition"] == "attempt_rejected"
    assert projected["effective_provider"] == successful.effective_provider
    assert projected["effective_model"] == successful.effective_model
    assert projected["runner_request_identity"] == {
        "run_id": successful.runner_request_identity.run_id,
        "attempt_id": successful.runner_request_identity.attempt_id,
        "execution_id": successful.runner_request_identity.execution_id,
        "iteration_id": successful.runner_request_identity.iteration_id,
        "iteration_index": successful.runner_request_identity.iteration_index,
        "runner_call_index": successful.runner_request_identity.runner_call_index,
        "client_correlation_id": (
            successful.runner_request_identity.client_correlation_id
        ),
    }
    assert projected["provider_request_id_availability"] == (
        successful.provider_request_id_availability.value
    )
    assert projected["provider_request_id"] == successful.provider_request_id
    assert projected["accepted_evidence_facts"] == []

    markdown = render_tool_trace_analysis_markdown(report)
    for actual_value in (
        successful.effective_provider,
        successful.effective_model,
        successful.runner_request_identity.run_id,
        successful.runner_request_identity.iteration_id,
        successful.provider_request_id_availability.value,
        successful.provider_request_id,
    ):
        assert actual_value is not None
        assert actual_value in markdown
    rendered = tool_trace_analysis_report_to_json(report) + markdown
    for poison in (
        "provider-neighbor-poison",
        "model-neighbor-poison",
        "request-neighbor-poison",
    ):
        assert poison not in rendered
