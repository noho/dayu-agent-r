"""``utils/analyze_tool_trace_host`` 单元测试。

每个用例临时构造一组 JSONL 文件（``<tmp>/sessions/<session>/tool_calls_*.jsonl``），
直接调用 :func:`analyze_trace_root` 验证分析逻辑；不依赖 Host runtime / Engine。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TypeAlias

import pytest

from dayu.contracts import JsonValue
from utils.analyze_tool_trace_host import (
    ContextPressureRun,
    DetailedFailurePattern,
    FailurePattern,
    FetchMoreScopeIssue,
    PositionGap,
    RepeatedToolCall,
    ToolStats,
    TraceAnalysisReport,
    TruncationGap,
    analyze_trace_root,
)

_SCHEMA_VERSION_HOST: str = "tool_trace_v2_host"
_SCHEMA_VERSION_OLD: str = "tool_trace_v2"
_SESSION_ID: str = "session_test"
_RUN_ID: str = "run_test"
_TOOL_NAME: str = "lookup_filing"


JsonRecord: TypeAlias = Mapping[str, JsonValue]


def _write_jsonl(
    *,
    trace_root: Path,
    session_id: str,
    records: list[Mapping[str, JsonValue]],
    file_index: int = 1,
) -> Path:
    """把 record 列表写入 ``<trace_root>/sessions/<session>/tool_calls_NNNNNN.jsonl``。

    :param trace_root: 临时根目录。
    :param session_id: 会话 id。
    :param records: 要写入的 record 列表。
    :param file_index: 文件序号。
    :returns: 写入的文件路径。
    :raises Exception: 不主动抛出异常。
    """

    target_dir = trace_root / "sessions" / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"tool_calls_{file_index:06d}.jsonl"
    with target_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False))
            handle.write("\n")
    return target_path


def _tool_call_record(
    *,
    idempotency_key: str,
    source_event_position: int,
    arguments_json: str = '{"q":"AAPL"}',
    truncation_has_more: bool | None = None,
    truncation_scope_token: str | None = None,
    truncation_cursor: str | None = None,
    fetch_more_consumed_cursor: str | None = None,
    fetch_more_next_cursor: str | None = None,
    tool_call_id: str = "tc-1",
    run_id: str = _RUN_ID,
    tool_name: str = _TOOL_NAME,
    outcome_kind: str = "completed",
    result_value_json: str | None = "{}",
    failure_error: str | None = None,
    failure_message: str | None = None,
) -> Mapping[str, JsonValue]:
    """构造最小 tool_call record。

    :returns: JSON record。
    :raises Exception: 不主动抛出异常。
    """

    record: dict[str, JsonValue] = {
        "schema_version": _SCHEMA_VERSION_HOST,
        "trace_type": "tool_call",
        "idempotency_key": idempotency_key,
        "recorded_at": "2026-05-08T00:00:00+00:00",
        "session_id": _SESSION_ID,
        "run_id": run_id,
        "source_event_position": source_event_position,
        "iteration_id": "iter-1",
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "index_in_iteration": 0,
        "arguments_json": arguments_json,
        "outcome_kind": outcome_kind,
        "result_value_json": result_value_json,
        "failure_error": failure_error,
        "failure_message": failure_message,
        "truncation_scope_token": truncation_scope_token,
        "truncation_cursor": truncation_cursor,
        "truncation_has_more": truncation_has_more,
        "truncation_limit": None,
        "fetch_more_consumed_cursor": fetch_more_consumed_cursor,
        "fetch_more_next_cursor": fetch_more_next_cursor,
        "fetch_more_chunk_size": None,
        "fetch_more_has_more": None,
        "cursor_denial_reason": None,
        "cursor_expired_at_monotonic": None,
    }
    return record


def _final_response_record(
    *,
    idempotency_key: str,
    source_event_position: int,
    run_id: str = _RUN_ID,
    degraded: bool = False,
    filtered: bool = False,
) -> Mapping[str, JsonValue]:
    """构造 final_response record。

    :returns: JSON record。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "schema_version": _SCHEMA_VERSION_HOST,
        "trace_type": "final_response",
        "idempotency_key": idempotency_key,
        "recorded_at": "2026-05-08T00:00:00+00:00",
        "session_id": _SESSION_ID,
        "run_id": run_id,
        "source_event_position": source_event_position,
        "iteration_id": "",
        "content": "答案",
        "filtered": filtered,
        "degraded": degraded,
        "finish_reason": "stop",
    }


def _provider_protocol_error_record(
    *,
    idempotency_key: str,
    source_event_position: int,
    run_id: str = _RUN_ID,
) -> Mapping[str, JsonValue]:
    """构造 provider_protocol_error record。

    :returns: JSON record。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "schema_version": _SCHEMA_VERSION_HOST,
        "trace_type": "provider_protocol_error",
        "idempotency_key": idempotency_key,
        "recorded_at": "2026-05-08T00:00:00+00:00",
        "session_id": _SESSION_ID,
        "run_id": run_id,
        "source_event_position": source_event_position,
        "iteration_id": "iter-1",
        "error_code": "rate_limited",
        "message": "429",
        "provider_request_id": "req-1",
        "raw_payload_json": "{}",
    }


def test_analyzer_dedupes_orphan_lines_by_idempotency_key(
    tmp_path: Path,
) -> None:
    """同 idempotency_key 多行只保留首条。"""

    record = _tool_call_record(
        idempotency_key="dup-key", source_event_position=1
    )
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=[record, record],
    )
    report: TraceAnalysisReport = analyze_trace_root(trace_root=tmp_path)
    assert report.total_lines_read == 2
    assert report.deduped_record_count == 1
    assert report.duplicate_idempotency_keys == ("dup-key",)


def test_analyzer_rejects_old_tool_trace_v2_files(tmp_path: Path) -> None:
    """schema_version=tool_trace_v2 必须被拒绝。"""

    record: Mapping[str, JsonValue] = {
        "schema_version": _SCHEMA_VERSION_OLD,
        "trace_type": "tool_call",
        "idempotency_key": "k",
        "recorded_at": "x",
        "session_id": _SESSION_ID,
        "run_id": _RUN_ID,
        "source_event_position": 1,
        "iteration_id": "iter-1",
        "tool_call_id": "tc-1",
    }
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=[record],
    )
    with pytest.raises(ValueError) as excinfo:
        analyze_trace_root(trace_root=tmp_path)
    assert _SCHEMA_VERSION_OLD in str(excinfo.value)


def test_analyzer_detects_repeated_tool_calls(tmp_path: Path) -> None:
    """同 (run_id, tool_name, arguments_json) 多次出现需被识别。"""

    records = [
        _tool_call_record(idempotency_key="k1", source_event_position=1),
        _tool_call_record(idempotency_key="k2", source_event_position=2),
    ]
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=records,
    )
    report = analyze_trace_root(trace_root=tmp_path)
    assert report.repeated_tool_calls == (
        RepeatedToolCall(tool_name=_TOOL_NAME, run_id=_RUN_ID, count=2),
    )


def test_analyzer_detects_truncation_without_fetch_more_followup(
    tmp_path: Path,
) -> None:
    """truncation_has_more=True 但同 run 无 fetch_more record 时报警。"""

    record = _tool_call_record(
        idempotency_key="trunc-1",
        source_event_position=1,
        truncation_has_more=True,
        truncation_scope_token="scope-A",
        truncation_cursor="cur-A",
    )
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=[record],
    )
    report = analyze_trace_root(trace_root=tmp_path)
    assert report.truncation_without_fetch_more == (
        TruncationGap(
            run_id=_RUN_ID,
            tool_call_id="tc-1",
            scope_token="scope-A",
        ),
    )


def test_analyzer_tracks_fetch_more_by_tool_call_not_run(
    tmp_path: Path,
) -> None:
    """同 run 其它 tool_call 的 fetch_more 不应掩盖当前 tool_call 的截断缺口。"""

    truncated_without_fetch_more = _tool_call_record(
        idempotency_key="trunc-a",
        source_event_position=1,
        tool_call_id="tc-a",
        truncation_has_more=True,
        truncation_scope_token="scope-A",
        truncation_cursor="cur-A",
    )
    unrelated_fetch_more = _tool_call_record(
        idempotency_key="fetch-b",
        source_event_position=2,
        tool_call_id="tc-b",
        fetch_more_consumed_cursor="cur-B",
    )
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=[truncated_without_fetch_more, unrelated_fetch_more],
    )
    report = analyze_trace_root(trace_root=tmp_path)
    assert report.truncation_without_fetch_more == (
        TruncationGap(
            run_id=_RUN_ID,
            tool_call_id="tc-a",
            scope_token="scope-A",
        ),
    )


def test_analyzer_detects_wrong_scope_token_in_fetch_more(
    tmp_path: Path,
) -> None:
    """fetch_more_consumed_cursor 引用从未出现过的 cursor 时报警。"""

    record = _tool_call_record(
        idempotency_key="fm-1",
        source_event_position=1,
        fetch_more_consumed_cursor="unknown-cursor",
    )
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=[record],
    )
    report = analyze_trace_root(trace_root=tmp_path)
    assert report.fetch_more_with_unknown_scope_token == (
        FetchMoreScopeIssue(
            run_id=_RUN_ID,
            tool_call_id="tc-1",
            scope_token_or_cursor="unknown-cursor",
            reason="unknown_consumed_cursor",
        ),
    )


def test_analyzer_counts_provider_protocol_errors(tmp_path: Path) -> None:
    """provider_protocol_error 数量统计。"""

    records = [
        _provider_protocol_error_record(
            idempotency_key="ppe-1", source_event_position=1
        ),
        _provider_protocol_error_record(
            idempotency_key="ppe-2", source_event_position=2
        ),
    ]
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=records,
    )
    report = analyze_trace_root(trace_root=tmp_path)
    assert report.provider_protocol_error_count == 2


def test_analyzer_reports_final_response_presence(tmp_path: Path) -> None:
    """final_response 存在与缺失两种 fixture。"""

    # 缺失。
    empty_root = tmp_path / "absent"
    record_only_tool_call = _tool_call_record(
        idempotency_key="t-1", source_event_position=1
    )
    _write_jsonl(
        trace_root=empty_root,
        session_id=_SESSION_ID,
        records=[record_only_tool_call],
    )
    report_absent = analyze_trace_root(trace_root=empty_root)
    assert report_absent.final_response_present is False

    # 存在。
    present_root = tmp_path / "present"
    final_record = _final_response_record(
        idempotency_key="f-1", source_event_position=2
    )
    _write_jsonl(
        trace_root=present_root,
        session_id=_SESSION_ID,
        records=[record_only_tool_call, final_record],
    )
    report_present = analyze_trace_root(trace_root=present_root)
    assert report_present.final_response_present is True


def test_analyzer_validates_trace_completeness_via_source_event_position(
    tmp_path: Path,
) -> None:
    """同 run 内 position 严格降序记 1 个 gap，单调升序无 gap。"""

    monotonic_root = tmp_path / "mono"
    monotonic_records = [
        _tool_call_record(
            idempotency_key="m-1",
            source_event_position=1,
            tool_call_id="tc-a",
        ),
        _tool_call_record(
            idempotency_key="m-2",
            source_event_position=2,
            tool_call_id="tc-b",
        ),
        _tool_call_record(
            idempotency_key="m-3",
            source_event_position=5,
            tool_call_id="tc-c",
        ),
    ]
    _write_jsonl(
        trace_root=monotonic_root,
        session_id=_SESSION_ID,
        records=monotonic_records,
    )
    monotonic_report = analyze_trace_root(trace_root=monotonic_root)
    assert monotonic_report.source_event_position_gaps == ()

    descending_root = tmp_path / "desc"
    descending_records = [
        _tool_call_record(
            idempotency_key="d-1",
            source_event_position=5,
            tool_call_id="tc-a",
        ),
        _tool_call_record(
            idempotency_key="d-2",
            source_event_position=2,
            tool_call_id="tc-b",
        ),
        _tool_call_record(
            idempotency_key="d-3",
            source_event_position=1,
            tool_call_id="tc-c",
        ),
    ]
    _write_jsonl(
        trace_root=descending_root,
        session_id=_SESSION_ID,
        records=descending_records,
    )
    descending_report = analyze_trace_root(trace_root=descending_root)
    assert PositionGap(run_id=_RUN_ID, prev_position=5, next_position=2) in (
        descending_report.source_event_position_gaps
    )
    # 至少 1 个 gap（按规则严格降序计 2 个）。
    assert len(descending_report.source_event_position_gaps) >= 1


def test_analyzer_summarizes_tool_stats(tmp_path: Path) -> None:
    """tool_stats 聚合 call_count / success_rate / truncation_rate /
    bytes / top_error_codes，覆盖 OLD `_summarize_tool_stats` 语义。"""

    records = [
        _tool_call_record(
            idempotency_key="ts-1",
            source_event_position=1,
            tool_call_id="tc-1",
            tool_name="search_web",
            outcome_kind="completed",
            result_value_json='{"text":"abc"}',
        ),
        _tool_call_record(
            idempotency_key="ts-2",
            source_event_position=2,
            tool_call_id="tc-2",
            tool_name="search_web",
            outcome_kind="completed",
            result_value_json='{"text":"abcd"}',
            truncation_has_more=True,
            truncation_scope_token="st",
        ),
        _tool_call_record(
            idempotency_key="ts-3",
            source_event_position=3,
            tool_call_id="tc-3",
            tool_name="search_web",
            outcome_kind="failed",
            result_value_json=None,
            failure_error="HTTP_429",
            failure_message="429",
        ),
        _tool_call_record(
            idempotency_key="ts-4",
            source_event_position=4,
            tool_call_id="tc-4",
            tool_name="lookup_filing",
            outcome_kind="completed",
            result_value_json='{"k":1}',
        ),
    ]
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=records,
    )
    report = analyze_trace_root(trace_root=tmp_path)
    by_tool = {item.tool_name: item for item in report.tool_stats}
    search = by_tool["search_web"]
    assert search.call_count == 3
    assert search.success_count == 2
    assert search.truncation_count == 1
    assert search.top_error_codes == (("HTTP_429", 1),)
    assert search.median_result_bytes > 0
    assert search.p90_result_bytes >= search.median_result_bytes
    lookup = by_tool["lookup_filing"]
    assert lookup.call_count == 1
    assert lookup.success_rate == 1.0
    # 排序：call_count 降序。
    assert report.tool_stats[0].tool_name == "search_web"


def test_analyzer_aggregates_failure_patterns(tmp_path: Path) -> None:
    """failure_patterns 按 (tool_name, failure_error) 聚合，对应 OLD
    `_build_failure_patterns`。"""

    records = [
        _tool_call_record(
            idempotency_key="fp-1",
            source_event_position=1,
            tool_call_id="tc-1",
            tool_name="fetch_web_page",
            outcome_kind="failed",
            result_value_json=None,
            failure_error="EXECUTION_ERROR",
            failure_message="404 Not Found",
        ),
        _tool_call_record(
            idempotency_key="fp-2",
            source_event_position=2,
            tool_call_id="tc-2",
            tool_name="fetch_web_page",
            outcome_kind="failed",
            result_value_json=None,
            failure_error="EXECUTION_ERROR",
            failure_message="HTTP 404 not found",
        ),
        _tool_call_record(
            idempotency_key="fp-3",
            source_event_position=3,
            tool_call_id="tc-3",
            tool_name="fetch_web_page",
            outcome_kind="failed",
            result_value_json=None,
            failure_error="permission_denied",
            failure_message="blocked by fetch safety policy",
        ),
        _tool_call_record(
            idempotency_key="fp-4",
            source_event_position=4,
            tool_call_id="tc-4",
            tool_name="fetch_web_page",
            outcome_kind="completed",
        ),
    ]
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=records,
    )
    report = analyze_trace_root(trace_root=tmp_path)
    assert FailurePattern(
        tool_name="fetch_web_page",
        error_code="EXECUTION_ERROR",
        count=2,
    ) in report.failure_patterns
    assert FailurePattern(
        tool_name="fetch_web_page",
        error_code="permission_denied",
        count=1,
    ) in report.failure_patterns
    # 详细签名：HTTP_404 与 URL_BLOCKED 至少各一个。
    signatures = {item.error_signature for item in report.detailed_failure_patterns}
    assert "HTTP_404" in signatures
    assert "URL_BLOCKED" in signatures
    assert all(
        isinstance(item, DetailedFailurePattern)
        for item in report.detailed_failure_patterns
    )


def test_analyzer_detects_context_pressure_runs(tmp_path: Path) -> None:
    """context_pressure_runs 识别 degraded / filtered / 缺失 final_response
    的 run；对应 OLD `_build_context_pressure_runs` 在 NEW record 上可识别
    的子集。"""

    records = [
        # run_a: degraded=True
        _tool_call_record(
            idempotency_key="cpr-a-1",
            source_event_position=1,
            tool_call_id="tc-a",
            run_id="run_a",
        ),
        _final_response_record(
            idempotency_key="cpr-a-2",
            source_event_position=2,
            run_id="run_a",
            degraded=True,
        ),
        # run_b: 没有 final_response，但有 provider_protocol_error
        _provider_protocol_error_record(
            idempotency_key="cpr-b-1",
            source_event_position=10,
            run_id="run_b",
        ),
        # run_c: filtered=True
        _tool_call_record(
            idempotency_key="cpr-c-1",
            source_event_position=20,
            tool_call_id="tc-c",
            run_id="run_c",
        ),
        _final_response_record(
            idempotency_key="cpr-c-2",
            source_event_position=21,
            run_id="run_c",
            filtered=True,
        ),
        # run_d: 正常 final_response，不应纳入。
        _tool_call_record(
            idempotency_key="cpr-d-1",
            source_event_position=30,
            tool_call_id="tc-d",
            run_id="run_d",
        ),
        _final_response_record(
            idempotency_key="cpr-d-2",
            source_event_position=31,
            run_id="run_d",
        ),
    ]
    _write_jsonl(
        trace_root=tmp_path,
        session_id=_SESSION_ID,
        records=records,
    )
    report = analyze_trace_root(trace_root=tmp_path)
    by_run = {item.run_id: item for item in report.context_pressure_runs}
    assert "run_a" in by_run
    assert by_run["run_a"].degraded is True
    assert "run_b" in by_run
    assert by_run["run_b"].has_final_response is False
    assert by_run["run_b"].provider_protocol_error_count == 1
    assert "run_c" in by_run
    assert by_run["run_c"].filtered is True
    assert "run_d" not in by_run


def test_tool_stats_dataclass_is_exported() -> None:
    """ToolStats / FailurePattern / DetailedFailurePattern /
    ContextPressureRun 需可被外部 import。"""

    assert ToolStats.__name__ == "ToolStats"
    assert FailurePattern.__name__ == "FailurePattern"
    assert DetailedFailurePattern.__name__ == "DetailedFailurePattern"
    assert ContextPressureRun.__name__ == "ContextPressureRun"
