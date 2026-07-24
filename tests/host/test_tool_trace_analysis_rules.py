"""Tool Trace Analyzer Host/Tool 行为规则的 owner-level 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.tool_trace import ToolTraceHotRow
from dayu.host.tool_trace_analysis import render_tool_trace_analysis_markdown
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
        "provider_request_id": None,
        "client_correlation_id": None,
        "diagnostic_refs": [],
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
        provider_request_id=None,
        diagnostic_ref=None,
        normalized_arguments_digest=None,
        semantic_input_digest=None,
        result_digest=None,
        payload_ref=None,
        payload_digest=None,
        policy_decision_json=None,
        trace_summary={},
        cold_trace_ref=record.cold_trace_ref,
        cold_trace_digest=record.line_digest,
        projected_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
    )


def _dataset(
    source: ToolTraceAnalysisSource,
    records: tuple[ToolTraceColdRecord, ...],
    *,
    diagnostics: tuple[ToolTraceInputDiagnostic, ...] = (),
    measures: tuple[ToolTraceResolvedPayloadMeasure, ...] = (),
    hot_store_available: bool = False,
    hot_rows: tuple[ToolTraceHotRow, ...] = (),
    cold_snapshot_available: bool = True,
) -> ToolTraceAnalysisDataset:
    """构造可信 normalized dataset。

    :param source: public source。
    :param records: valid cold records。
    :param diagnostics: S1 diagnostics。
    :param measures: verified byte measures。
    :param hot_store_available: 是否已取得 hot snapshot。
    :param hot_rows: hot snapshot owner rows。
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
        joined_records=(),
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
