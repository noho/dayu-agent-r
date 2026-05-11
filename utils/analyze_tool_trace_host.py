"""Host P7 tool trace JSONL analyzer。

读取 :class:`ToolTraceJsonlSink` 写入的 JSONL trace（schema 字面量
``tool_trace_v2_host``），按 ``idempotency_key`` 去重并执行结构性诊断：

- 重复 tool_call（同 ``run_id`` + ``tool_name`` + ``arguments_json`` 多次出现）。
- ``truncation_has_more=True`` 之后同 run 没有 ordinary ``fetch_more`` 续读。
- ordinary ``tool_name=="fetch_more"`` 的 ``arguments_json`` 引用了未知 cursor、
  错误 scope、重复 cursor 或返回 failed outcome。
- ``provider_protocol_error`` 计数。
- ``final_response`` 是否存在。
- 同 ``run_id`` 内 ``source_event_position`` 是否单调不下降。
- 工具级统计聚合：每工具 call_count / success_count / success_rate /
  truncation_count / truncation_rate / median_result_bytes / p90_result_bytes /
  top_error_codes（对应 OLD ``_summarize_tool_stats``）。
- 失败模式聚合：按 ``(tool_name, failure_error)`` 计数（对应 OLD
  ``_build_failure_patterns``），并基于 ``failure_message`` 派生粗粒度
  ``error_signature``（对应 OLD ``_build_detailed_failure_patterns`` /
  ``_classify_error_signature`` 的可在 NEW record 上提取的子集）。
- 上下文压力 run 列表：基于 NEW record 字段（``final_response.degraded`` /
  ``final_response.filtered`` / ``provider_protocol_error`` 计数 /
  ``final_response`` 缺失）识别可能因为上下文压力降级或失败的 run（对应
  OLD ``_build_context_pressure_runs``，但 NEW record 不携带
  ``budget_snapshot.is_over_soft_limit`` / ``compaction_count`` /
  ``continuation_count``，因此这些维度不可用，详见 phase7-old-new-review
  Finding 4 / Finding 11）。

本分析器**严格拒绝** OLD ``tool_trace_v2`` 文件：遇到任何非
``tool_trace_v2_host`` 的 ``schema_version`` 字段都会抛
:class:`ValueError`，避免把不同生命周期、不同治理边界的两套 schema 混在
同一份诊断报告里。

CLI 用法::

    python utils/analyze_tool_trace_host.py <trace_root>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

_REPO_ROOT_PARENT_INDEX: int = 1


def _ensure_repo_root_on_path() -> None:
    """确保按文件路径运行脚本时也能导入仓库顶层包。

    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if __package__ not in (None, ""):
        return
    repo_root = Path(__file__).resolve().parents[_REPO_ROOT_PARENT_INDEX]
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


_ensure_repo_root_on_path()

from dayu.contracts import JsonValue  # noqa: E402

_TRACE_SCHEMA_VERSION_HOST: str = "tool_trace_v2_host"
_TRACE_TYPE_TOOL_CALL: str = "tool_call"
_TRACE_TYPE_FINAL_RESPONSE: str = "final_response"
_TRACE_TYPE_PROVIDER_PROTOCOL_ERROR: str = "provider_protocol_error"
_FETCH_MORE_TOOL_NAME: str = "fetch_more"
_FETCH_MORE_CURSOR_ARG: str = "cursor"
_FETCH_MORE_SCOPE_TOKEN_ARG: str = "scope_token"
_OUTCOME_FAILED: str = "failed"
_ISSUE_UNKNOWN_CONSUMED_CURSOR: str = "unknown_consumed_cursor"
_ISSUE_WRONG_SCOPE_TOKEN: str = "wrong_scope_token"
_ISSUE_DUPLICATE_CONSUMED_CURSOR: str = "duplicate_consumed_cursor"
_ISSUE_FETCH_MORE_FAILED_PREFIX: str = "fetch_more_failed"


JsonRecord: TypeAlias = Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class TraceLineEntry:
    """单条 JSONL record 解析结果。

    :param file_path: 来源文件绝对路径。
    :param line_number: 1-based 行号。
    :param record: 解析后的 JSON 对象。
    """

    file_path: Path
    line_number: int
    record: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RepeatedToolCall:
    """重复 tool_call 诊断条目。

    :param tool_name: 工具名。
    :param run_id: Run id。
    :param count: 重复次数。
    """

    tool_name: str
    run_id: str
    count: int


@dataclass(frozen=True, slots=True)
class TruncationGap:
    """truncation 后未续读 fetch_more 诊断条目。

    :param run_id: Run id。
    :param tool_call_id: 工具调用 id。
    :param scope_token: 截断 scope token。
    """

    run_id: str
    tool_call_id: str
    scope_token: str


@dataclass(frozen=True, slots=True)
class FetchMoreScopeIssue:
    """fetch_more cursor / scope_token 未知诊断条目。

    :param run_id: Run id。
    :param tool_call_id: 工具调用 id。
    :param scope_token_or_cursor: 触发问题的 cursor / scope_token 字符串。
    :param reason: 中性原因字符串。
    """

    run_id: str
    tool_call_id: str
    scope_token_or_cursor: str
    reason: str


@dataclass(frozen=True, slots=True)
class PositionGap:
    """同 run 内 ``source_event_position`` 出现降序时的 gap 条目。

    :param run_id: Run id。
    :param prev_position: 前一条记录的 position。
    :param next_position: 下一条记录的 position。
    """

    run_id: str
    prev_position: int
    next_position: int


@dataclass(frozen=True, slots=True)
class ToolStats:
    """单个工具的聚合统计。

    对应 OLD ``utils/analyze_tool_trace.py`` 中的 ``ToolStats``，但 NEW
    record 不携带 ``raw_result_ref.bytes`` 与 latency_ms，因此 byte 大小
    使用 ``result_value_json`` 的 UTF-8 字节长度估算（仅 outcome=completed
    时计入），latency 维度暂不提供。

    :param tool_name: 工具名。
    :param call_count: 总调用次数。
    :param success_count: 成功次数（``outcome_kind=='completed'``）。
    :param success_rate: 成功比例，区间 ``[0, 1]``。
    :param truncation_count: 触发截断的调用次数（``truncation_has_more=True``）。
    :param truncation_rate: 截断比例，区间 ``[0, 1]``。
    :param median_result_bytes: ``result_value_json`` UTF-8 字节长度中位数；
        无成功调用时为 ``0``。
    :param p90_result_bytes: 同上，P90；无成功调用时为 ``0``。
    :param top_error_codes: 失败错误码 top-3，``(error_code, count)`` 列表，
        若无失败为空 tuple。
    """

    tool_name: str
    call_count: int
    success_count: int
    success_rate: float
    truncation_count: int
    truncation_rate: float
    median_result_bytes: int
    p90_result_bytes: int
    top_error_codes: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class FailurePattern:
    """``(tool_name, error_code)`` 失败聚合。

    对应 OLD ``_build_failure_patterns`` 的语义。``error_code`` 取自 NEW
    record 的 ``failure_error`` 字段（中性错误码），缺失时记为
    ``"UNKNOWN"``。

    :param tool_name: 工具名。
    :param error_code: 失败错误码字面量。
    :param count: 命中次数。
    """

    tool_name: str
    error_code: str
    count: int


@dataclass(frozen=True, slots=True)
class DetailedFailurePattern:
    """``error_signature`` 维度的失败聚合。

    对应 OLD ``_build_detailed_failure_patterns`` 与
    ``_classify_error_signature``。NEW record 不携带 raw_result 冷存，
    因此只能基于 ``failure_message`` 文本与 ``failure_error`` 推断。

    :param tool_name: 工具名。
    :param error_signature: 粗粒度签名，例如 ``HTTP_403`` / ``TIMEOUT`` /
        ``DNS_ERROR``；无法识别时退化为 ``failure_error`` 原值。
    :param error_code: 原始 ``failure_error`` 字面量。
    :param count: 命中次数。
    """

    tool_name: str
    error_signature: str
    error_code: str
    count: int


@dataclass(frozen=True, slots=True)
class ContextPressureRun:
    """疑似上下文压力较高的 run。

    对应 OLD ``_build_context_pressure_runs`` 的可在 NEW record 上识别的
    子集。NEW record 不携带 ``budget_snapshot``，因此 ``is_over_soft_limit``
    / ``compaction_count`` / ``continuation_count`` 维度不可用；这些维度
    被设计上 deferred 到后续 phase（详见 phase7-old-new-review Finding
    4 / Finding 11）。

    :param run_id: Run id。
    :param degraded: ``final_response.degraded``；无 final_response 时为
        ``False``。
    :param filtered: ``final_response.filtered``；无 final_response 时为
        ``False``。
    :param has_final_response: 是否存在 final_response。
    :param provider_protocol_error_count: 该 run 的 provider_protocol_error
        计数。
    :param tool_call_count: 该 run 的 tool_call 数量。
    """

    run_id: str
    degraded: bool
    filtered: bool
    has_final_response: bool
    provider_protocol_error_count: int
    tool_call_count: int


@dataclass(frozen=True, slots=True)
class ProviderPartialToolCallDiagnostic:
    """provider_protocol_error 中的 partial tool call 诊断。

    :param run_id: Run id。
    :param iteration_id: iteration id。
    :param error_code: provider protocol error code。
    :param tool_call_index: provider tool call index。
    :param tool_call_id: provider 已给出的 tool call id。
    :param name_fragment: 已解析工具名片段。
    :param arguments_byte_size: 已收到 arguments delta 字节数。
    :param arguments_sha256: 已收到 arguments delta sha256。
    """

    run_id: str
    iteration_id: str
    error_code: str
    tool_call_index: int
    tool_call_id: str | None
    name_fragment: str | None
    arguments_byte_size: int
    arguments_sha256: str | None


@dataclass(frozen=True, slots=True)
class TraceAnalysisReport:
    """trace 诊断结果汇总。

    :param total_lines_read: 读取的 JSONL 行总数（含重复）。
    :param deduped_record_count: 按 ``idempotency_key`` 去重后的 record 数。
    :param duplicate_idempotency_keys: 出现 >1 次的 idempotency_key 列表。
    :param repeated_tool_calls: 重复 tool_call 列表。
    :param truncation_without_fetch_more: 截断未续读列表。
    :param fetch_more_with_unknown_scope_token: fetch_more 引用未知 cursor 列表。
    :param provider_protocol_error_count: provider_protocol_error 数量。
    :param final_response_present: 是否包含 final_response record。
    :param source_event_position_gaps: 单调下降异常列表。
    :param record_counts_by_type: 按 trace_type 分组的去重计数。
    """

    total_lines_read: int
    deduped_record_count: int
    duplicate_idempotency_keys: tuple[str, ...]
    repeated_tool_calls: tuple[RepeatedToolCall, ...]
    truncation_without_fetch_more: tuple[TruncationGap, ...]
    fetch_more_with_unknown_scope_token: tuple[FetchMoreScopeIssue, ...]
    provider_protocol_error_count: int
    final_response_present: bool
    source_event_position_gaps: tuple[PositionGap, ...]
    record_counts_by_type: Mapping[str, int]
    tool_stats: tuple[ToolStats, ...]
    failure_patterns: tuple[FailurePattern, ...]
    detailed_failure_patterns: tuple[DetailedFailurePattern, ...]
    context_pressure_runs: tuple[ContextPressureRun, ...]
    provider_partial_tool_calls: tuple[ProviderPartialToolCallDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class _TruncationCursor:
    """普通工具结果中签发的截断 cursor 摘要。

    :param run_id: Run id。
    :param tool_call_id: 签发 cursor 的工具调用 id。
    :param cursor: raw cursor。
    :param scope_token: raw scope token。
    :param source_event_position: 来源事件 position。
    """

    run_id: str
    tool_call_id: str
    cursor: str
    scope_token: str
    source_event_position: int


@dataclass(frozen=True, slots=True)
class _FetchMoreCall:
    """ordinary ``fetch_more`` 工具调用摘要。

    :param run_id: Run id。
    :param tool_call_id: fetch_more 工具调用 id。
    :param cursor: arguments_json.cursor。
    :param scope_token: arguments_json.scope_token。
    :param source_event_position: 来源事件 position。
    :param outcome_kind: 工具调用 outcome kind。
    :param failure_error: 失败错误码；成功时为空字符串。
    """

    run_id: str
    tool_call_id: str
    cursor: str
    scope_token: str
    source_event_position: int
    outcome_kind: str
    failure_error: str


def _iter_jsonl_files(*, trace_root: Path) -> list[Path]:
    """枚举 ``<trace_root>/sessions/**/tool_calls_*.jsonl``。

    :param trace_root: trace 根目录。
    :returns: 排序后的文件路径列表。
    :raises Exception: 不主动抛出异常。
    """

    sessions_dir = trace_root / "sessions"
    if not sessions_dir.exists():
        return []
    return sorted(sessions_dir.rglob("tool_calls_*.jsonl"))


def _validate_schema_version(*, value: JsonValue, file_path: Path) -> None:
    """校验 ``schema_version`` 字段。

    :param value: 字段值。
    :param file_path: 文件路径，仅用于错误提示。
    :returns: 无返回值。
    :raises ValueError: 字段缺失或非 ``tool_trace_v2_host``。
    """

    if not isinstance(value, str):
        raise ValueError(f"trace record missing string schema_version in {file_path}")
    if value == _TRACE_SCHEMA_VERSION_HOST:
        return
    raise ValueError(
        f"refusing OLD/unknown schema_version={value!r} in {file_path}; "
        f"NEW analyzer only accepts {_TRACE_SCHEMA_VERSION_HOST!r} "
        f"(OLD tool_trace_v2 has different governance and is not supported)"
    )


def _read_str(record: JsonRecord, key: str) -> str:
    """读取 ``str`` 字段。

    :param record: JSON 对象。
    :param key: 字段名。
    :returns: 字段字符串值；缺失或类型不匹配返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    value = record.get(key)
    if isinstance(value, str):
        return value
    return ""


def _read_int(record: JsonRecord, key: str) -> int | None:
    """读取 ``int`` 字段。

    :param record: JSON 对象。
    :param key: 字段名。
    :returns: 字段 int 值；缺失或类型不匹配返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    value = record.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _read_optional_str(record: JsonRecord, key: str) -> str | None:
    """读取可空 ``str`` 字段。

    :param record: JSON 对象。
    :param key: 字段名。
    :returns: 字段字符串值；缺失、``null`` 或类型不匹配返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    value = record.get(key)
    if isinstance(value, str):
        return value
    return None


def _read_bool(record: JsonRecord, key: str) -> bool | None:
    """读取 ``bool`` 字段。

    :param record: JSON 对象。
    :param key: 字段名。
    :returns: 字段 bool 值；缺失返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    value = record.get(key)
    if isinstance(value, bool):
        return value
    return None


def _read_arguments_json(record: JsonRecord) -> Mapping[str, JsonValue]:
    """解析 tool_call record 的 ``arguments_json``。

    :param record: trace JSON 对象。
    :returns: 参数 JSON 对象；缺失、非法或非对象时返回空映射。
    :raises Exception: 不主动抛出异常。
    """

    raw = _read_str(record, "arguments_json")
    if raw == "":
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return cast(Mapping[str, JsonValue], decoded)


def _collect_truncation_cursors(
    entries: list[TraceLineEntry],
) -> tuple[_TruncationCursor, ...]:
    """收集 ordinary tool result 中的截断 cursor。

    :param entries: 去重后的 record 列表。
    :returns: 截断 cursor 摘要元组。
    :raises Exception: 不主动抛出异常。
    """

    cursors: list[_TruncationCursor] = []
    for entry in entries:
        record = entry.record
        if _read_str(record, "trace_type") != _TRACE_TYPE_TOOL_CALL:
            continue
        if _read_bool(record, "truncation_has_more") is not True:
            continue
        cursor = _read_str(record, "truncation_cursor")
        scope_token = _read_str(record, "truncation_scope_token")
        cursors.append(
            _TruncationCursor(
                run_id=_read_str(record, "run_id"),
                tool_call_id=_read_str(record, "tool_call_id"),
                cursor=cursor,
                scope_token=scope_token,
                source_event_position=(_read_int(record, "source_event_position") or 0),
            )
        )
    return tuple(cursors)


def _collect_fetch_more_calls(
    entries: list[TraceLineEntry],
) -> tuple[_FetchMoreCall, ...]:
    """收集 ordinary ``fetch_more`` 工具调用。

    :param entries: 去重后的 record 列表。
    :returns: fetch_more 调用摘要元组。
    :raises Exception: 不主动抛出异常。
    """

    calls: list[_FetchMoreCall] = []
    for entry in entries:
        record = entry.record
        if _read_str(record, "trace_type") != _TRACE_TYPE_TOOL_CALL:
            continue
        if _read_str(record, "tool_name") != _FETCH_MORE_TOOL_NAME:
            continue
        arguments = _read_arguments_json(record)
        cursor_value = arguments.get(_FETCH_MORE_CURSOR_ARG)
        scope_token_value = arguments.get(_FETCH_MORE_SCOPE_TOKEN_ARG)
        cursor = cursor_value if isinstance(cursor_value, str) else ""
        scope_token = scope_token_value if isinstance(scope_token_value, str) else ""
        calls.append(
            _FetchMoreCall(
                run_id=_read_str(record, "run_id"),
                tool_call_id=_read_str(record, "tool_call_id"),
                cursor=cursor,
                scope_token=scope_token,
                source_event_position=(_read_int(record, "source_event_position") or 0),
                outcome_kind=_read_str(record, "outcome_kind"),
                failure_error=_read_str(record, "failure_error"),
            )
        )
    return tuple(calls)


def _detect_repeated_tool_calls(
    entries: list[TraceLineEntry],
) -> tuple[RepeatedToolCall, ...]:
    """按 ``(run_id, tool_name, arguments_json)`` 检测重复 tool_call。

    :param entries: 去重后的 record 列表。
    :returns: 重复 tool_call 列表。
    :raises Exception: 不主动抛出异常。
    """

    counter: dict[tuple[str, str, str], int] = {}
    for entry in entries:
        record = entry.record
        if _read_str(record, "trace_type") != _TRACE_TYPE_TOOL_CALL:
            continue
        run_id = _read_str(record, "run_id")
        tool_name = _read_str(record, "tool_name")
        arguments_json = _read_str(record, "arguments_json")
        key = (run_id, tool_name, arguments_json)
        counter[key] = counter.get(key, 0) + 1
    repeats: list[RepeatedToolCall] = []
    for (run_id, tool_name, _arguments_json), count in counter.items():
        if count > 1:
            repeats.append(
                RepeatedToolCall(
                    tool_name=tool_name,
                    run_id=run_id,
                    count=count,
                )
            )
    repeats.sort(key=lambda item: (item.run_id, item.tool_name))
    return tuple(repeats)


def _detect_truncation_gaps(
    entries: list[TraceLineEntry],
) -> tuple[TruncationGap, ...]:
    """检测 truncation 后没有 ordinary ``fetch_more`` 续读的 tool_call。

    :param entries: 去重后的 record 列表。
    :returns: TruncationGap 列表。
    :raises Exception: 不主动抛出异常。
    """

    truncations = _collect_truncation_cursors(entries)
    fetch_more_calls = _collect_fetch_more_calls(entries)
    consumed_positions: dict[tuple[str, str], list[int]] = {}
    for call in fetch_more_calls:
        if call.cursor == "":
            continue
        consumed_positions.setdefault((call.run_id, call.cursor), []).append(call.source_event_position)
    gaps: list[TruncationGap] = []
    for truncation in truncations:
        positions = consumed_positions.get(
            (truncation.run_id, truncation.cursor),
            [],
        )
        has_followup = any(position > truncation.source_event_position for position in positions)
        if not has_followup:
            gaps.append(
                TruncationGap(
                    run_id=truncation.run_id,
                    tool_call_id=truncation.tool_call_id,
                    scope_token=truncation.scope_token,
                )
            )
    return tuple(gaps)


def _detect_fetch_more_unknown_cursor(
    entries: list[TraceLineEntry],
) -> tuple[FetchMoreScopeIssue, ...]:
    """检测 ordinary ``fetch_more`` 的 cursor / scope / failed outcome 问题。

    :param entries: 去重后的 record 列表（按 source_event_position 排序）。
    :returns: FetchMoreScopeIssue 列表。
    :raises Exception: 不主动抛出异常。
    """

    sorted_entries = sorted(
        entries,
        key=lambda item: (
            _read_str(item.record, "run_id"),
            _read_int(item.record, "source_event_position") or 0,
        ),
    )
    issued_scope_by_cursor: dict[tuple[str, str], str] = {}
    consumed_cursors_by_run: dict[str, set[str]] = {}
    issues: list[FetchMoreScopeIssue] = []
    for entry in sorted_entries:
        record = entry.record
        if _read_str(record, "trace_type") != _TRACE_TYPE_TOOL_CALL:
            continue
        run_id = _read_str(record, "run_id")
        truncation_cursor = record.get("truncation_cursor")
        if isinstance(truncation_cursor, str) and truncation_cursor != "":
            issued_scope_by_cursor[(run_id, truncation_cursor)] = _read_str(
                record,
                "truncation_scope_token",
            )
        if _read_str(record, "tool_name") != _FETCH_MORE_TOOL_NAME:
            continue
        arguments = _read_arguments_json(record)
        cursor_value = arguments.get(_FETCH_MORE_CURSOR_ARG)
        scope_token_value = arguments.get(_FETCH_MORE_SCOPE_TOKEN_ARG)
        cursor = cursor_value if isinstance(cursor_value, str) else ""
        scope_token = scope_token_value if isinstance(scope_token_value, str) else ""
        consumed_set = consumed_cursors_by_run.setdefault(run_id, set())
        if cursor in consumed_set:
            issues.append(
                FetchMoreScopeIssue(
                    run_id=run_id,
                    tool_call_id=_read_str(record, "tool_call_id"),
                    scope_token_or_cursor=cursor,
                    reason=_ISSUE_DUPLICATE_CONSUMED_CURSOR,
                )
            )
        if cursor != "":
            consumed_set.add(cursor)
        expected_scope = issued_scope_by_cursor.get((run_id, cursor))
        if expected_scope is None:
            issues.append(
                FetchMoreScopeIssue(
                    run_id=run_id,
                    tool_call_id=_read_str(record, "tool_call_id"),
                    scope_token_or_cursor=cursor,
                    reason=_ISSUE_UNKNOWN_CONSUMED_CURSOR,
                )
            )
        elif expected_scope != "" and scope_token != expected_scope:
            issues.append(
                FetchMoreScopeIssue(
                    run_id=run_id,
                    tool_call_id=_read_str(record, "tool_call_id"),
                    scope_token_or_cursor=scope_token,
                    reason=_ISSUE_WRONG_SCOPE_TOKEN,
                )
            )
        if _read_str(record, "outcome_kind") == _OUTCOME_FAILED:
            failure_error = _read_str(record, "failure_error") or _UNKNOWN_ERROR_CODE
            issues.append(
                FetchMoreScopeIssue(
                    run_id=run_id,
                    tool_call_id=_read_str(record, "tool_call_id"),
                    scope_token_or_cursor=cursor,
                    reason=f"{_ISSUE_FETCH_MORE_FAILED_PREFIX}:{failure_error}",
                )
            )
    return tuple(issues)


def _detect_position_gaps(
    entries: list[TraceLineEntry],
) -> tuple[PositionGap, ...]:
    """检测同 run 内 ``source_event_position`` 出现降序的位置。

    同 position 重复（例如同一 source event 派生多 record）允许；只对
    严格降序报警。

    :param entries: 去重后的 record 列表。
    :returns: PositionGap 列表。
    :raises Exception: 不主动抛出异常。
    """

    by_run: dict[str, list[int]] = {}
    for entry in entries:
        record = entry.record
        run_id = _read_str(record, "run_id")
        position = _read_int(record, "source_event_position")
        if position is None:
            continue
        by_run.setdefault(run_id, []).append(position)
    gaps: list[PositionGap] = []
    for run_id, positions in by_run.items():
        # 保留 entries 顺序（反映 JSONL 写入顺序）。
        prev_position: int | None = None
        for position in positions:
            if prev_position is not None and position < prev_position:
                gaps.append(
                    PositionGap(
                        run_id=run_id,
                        prev_position=prev_position,
                        next_position=position,
                    )
                )
            prev_position = position
    return tuple(gaps)


_LARGE_PAYLOAD_PERCENTILE: float = 0.9
_TOP_ERROR_CODES_LIMIT: int = 3
_UNKNOWN_ERROR_CODE: str = "UNKNOWN"


def _percentile_int(values: list[int], percentile: float) -> int:
    """计算整数序列的指定百分位（线性插值近似）。

    :param values: 整数列表，可空。
    :param percentile: 百分位，区间 ``[0, 1]``。
    :returns: 百分位值；空列表返回 ``0``。
    :raises Exception: 不主动抛出异常。
    """

    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    bounded = min(max(percentile, 0.0), 1.0)
    last_index = len(ordered) - 1
    target_index = int(round(last_index * bounded))
    if target_index < 0:
        target_index = 0
    if target_index > last_index:
        target_index = last_index
    return ordered[target_index]


def _median_int(values: list[int]) -> int:
    """计算整数序列的中位数（向下取整）。

    :param values: 整数列表，可空。
    :returns: 中位数；空列表返回 ``0``。
    :raises Exception: 不主动抛出异常。
    """

    if not values:
        return 0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def _safe_ratio(numerator: int, denominator: int) -> float:
    """安全比例：分母 ``<= 0`` 返回 ``0.0``。

    :param numerator: 分子。
    :param denominator: 分母。
    :returns: 比例。
    :raises Exception: 不主动抛出异常。
    """

    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _classify_error_signature(*, error_code: str, message: str) -> str:
    """把粗粒度 ``failure_error`` + ``failure_message`` 映射成签名。

    NEW record 不携带 raw_result 冷存，无法读取 OLD ``error.detail`` /
    ``meta.repair_hint`` 等结构化字段；这里只能基于 ``failure_message``
    文本做粗判，覆盖 OLD ``_classify_error_signature`` 中可在 NEW record
    上提取的子集（HTTP 状态码、TIMEOUT、DNS_ERROR、SSL_ERROR、URL 拒绝）。

    :param error_code: NEW record 的 ``failure_error`` 字段。
    :param message: NEW record 的 ``failure_message`` 字段。
    :returns: 签名字符串。
    :raises Exception: 不主动抛出异常。
    """

    code = error_code or _UNKNOWN_ERROR_CODE
    msg_lower = message.lower()
    if "timeout" in msg_lower or "timed out" in msg_lower or "超时" in message:
        return "TIMEOUT"
    if "dns" in msg_lower or "name or service not known" in msg_lower:
        return "DNS_ERROR"
    if "ssl" in msg_lower or "certificate" in msg_lower:
        return "SSL_ERROR"
    if (
        "不允许访问的 url" in message
        or "not allowed url" in msg_lower
        or "blocked by fetch safety policy" in msg_lower
        or code == "permission_denied"
    ):
        return "URL_BLOCKED"
    for status_text, signature in (
        ("http 403", "HTTP_403"),
        ("http 404", "HTTP_404"),
        ("http 429", "HTTP_429"),
        ("status 403", "HTTP_403"),
        ("status 404", "HTTP_404"),
        ("status 429", "HTTP_429"),
        ("403 forbidden", "HTTP_403"),
        ("404 not found", "HTTP_404"),
        ("429 too many", "HTTP_429"),
    ):
        if status_text in msg_lower:
            return signature
    if "http 5" in msg_lower or " 5xx" in msg_lower:
        return "HTTP_5XX"
    return code


def _summarize_tool_stats(
    entries: list[TraceLineEntry],
) -> tuple[ToolStats, ...]:
    """聚合 tool_call record 为工具级统计。

    :param entries: 去重后的 record 列表。
    :returns: ``ToolStats`` tuple，按 ``call_count`` 降序、tool_name 升序。
    :raises Exception: 不主动抛出异常。
    """

    grouped_calls: dict[str, list[JsonRecord]] = {}
    for entry in entries:
        record = entry.record
        if _read_str(record, "trace_type") != _TRACE_TYPE_TOOL_CALL:
            continue
        tool_name = _read_str(record, "tool_name")
        grouped_calls.setdefault(tool_name, []).append(record)

    stats: list[ToolStats] = []
    for tool_name, calls in grouped_calls.items():
        call_count = len(calls)
        success_count = 0
        truncation_count = 0
        result_byte_sizes: list[int] = []
        error_counter: dict[str, int] = {}
        for record in calls:
            if _read_str(record, "outcome_kind") == "completed":
                success_count += 1
                result_value_json = record.get("result_value_json")
                if isinstance(result_value_json, str):
                    result_byte_sizes.append(len(result_value_json.encode("utf-8")))
            else:
                error_code = _read_str(record, "failure_error") or _UNKNOWN_ERROR_CODE
                error_counter[error_code] = error_counter.get(error_code, 0) + 1
            if _read_bool(record, "truncation_has_more") is True:
                truncation_count += 1
        top_errors = tuple(
            sorted(
                error_counter.items(),
                key=lambda item: (-item[1], item[0]),
            )[:_TOP_ERROR_CODES_LIMIT]
        )
        stats.append(
            ToolStats(
                tool_name=tool_name,
                call_count=call_count,
                success_count=success_count,
                success_rate=_safe_ratio(success_count, call_count),
                truncation_count=truncation_count,
                truncation_rate=_safe_ratio(truncation_count, call_count),
                median_result_bytes=_median_int(result_byte_sizes),
                p90_result_bytes=_percentile_int(result_byte_sizes, _LARGE_PAYLOAD_PERCENTILE),
                top_error_codes=top_errors,
            )
        )
    stats.sort(key=lambda item: (-item.call_count, item.tool_name))
    return tuple(stats)


def _build_failure_patterns(
    entries: list[TraceLineEntry],
) -> tuple[FailurePattern, ...]:
    """按 ``(tool_name, failure_error)`` 聚合失败次数。

    :param entries: 去重后的 record 列表。
    :returns: ``FailurePattern`` tuple，按 count 降序、tool_name / error_code
        升序。
    :raises Exception: 不主动抛出异常。
    """

    counter: dict[tuple[str, str], int] = {}
    for entry in entries:
        record = entry.record
        if _read_str(record, "trace_type") != _TRACE_TYPE_TOOL_CALL:
            continue
        if _read_str(record, "outcome_kind") == "completed":
            continue
        tool_name = _read_str(record, "tool_name")
        error_code = _read_str(record, "failure_error") or _UNKNOWN_ERROR_CODE
        key = (tool_name, error_code)
        counter[key] = counter.get(key, 0) + 1
    patterns = [
        FailurePattern(tool_name=tool_name, error_code=error_code, count=count)
        for (tool_name, error_code), count in counter.items()
    ]
    patterns.sort(key=lambda item: (-item.count, item.tool_name, item.error_code))
    return tuple(patterns)


def _build_detailed_failure_patterns(
    entries: list[TraceLineEntry],
) -> tuple[DetailedFailurePattern, ...]:
    """按 ``error_signature`` 维度聚合失败次数。

    :param entries: 去重后的 record 列表。
    :returns: ``DetailedFailurePattern`` tuple，按 count 降序排序。
    :raises Exception: 不主动抛出异常。
    """

    counter: dict[tuple[str, str, str], int] = {}
    for entry in entries:
        record = entry.record
        if _read_str(record, "trace_type") != _TRACE_TYPE_TOOL_CALL:
            continue
        if _read_str(record, "outcome_kind") == "completed":
            continue
        tool_name = _read_str(record, "tool_name")
        error_code = _read_str(record, "failure_error") or _UNKNOWN_ERROR_CODE
        message = _read_str(record, "failure_message")
        signature = _classify_error_signature(error_code=error_code, message=message)
        key = (tool_name, signature, error_code)
        counter[key] = counter.get(key, 0) + 1
    patterns = [
        DetailedFailurePattern(
            tool_name=tool_name,
            error_signature=signature,
            error_code=error_code,
            count=count,
        )
        for (tool_name, signature, error_code), count in counter.items()
    ]
    patterns.sort(
        key=lambda item: (
            -item.count,
            item.tool_name,
            item.error_signature,
            item.error_code,
        )
    )
    return tuple(patterns)


def _build_context_pressure_runs(
    entries: list[TraceLineEntry],
) -> tuple[ContextPressureRun, ...]:
    """识别 NEW record 视角下疑似上下文压力较高的 run。

    判定条件（任一命中即纳入）：

    - ``final_response.degraded == True``
    - ``final_response.filtered == True``
    - 没有 ``final_response`` 但有 ``provider_protocol_error``
    - 没有 ``final_response`` 也没有 ``provider_protocol_error``，但有
      ``tool_call`` record（即 run 没有正常收尾）

    NEW record 缺失 OLD ``budget_snapshot``（``is_over_soft_limit`` /
    ``compaction_count`` / ``continuation_count``）；这些维度在 phase7
    范围内不可得，留作后续 phase 的 followup（见
    phase7-old-new-review Finding 4 / Finding 11）。

    :param entries: 去重后的 record 列表。
    :returns: ``ContextPressureRun`` tuple，按 run_id 排序。
    :raises Exception: 不主动抛出异常。
    """

    by_run_tool_calls: dict[str, int] = {}
    by_run_provider_errors: dict[str, int] = {}
    by_run_final: dict[str, tuple[bool, bool]] = {}
    by_run_seen: set[str] = set()
    for entry in entries:
        record = entry.record
        run_id = _read_str(record, "run_id")
        if run_id == "":
            continue
        by_run_seen.add(run_id)
        trace_type = _read_str(record, "trace_type")
        if trace_type == _TRACE_TYPE_TOOL_CALL:
            by_run_tool_calls[run_id] = by_run_tool_calls.get(run_id, 0) + 1
        elif trace_type == _TRACE_TYPE_PROVIDER_PROTOCOL_ERROR:
            by_run_provider_errors[run_id] = by_run_provider_errors.get(run_id, 0) + 1
        elif trace_type == _TRACE_TYPE_FINAL_RESPONSE:
            degraded = _read_bool(record, "degraded") or False
            filtered = _read_bool(record, "filtered") or False
            by_run_final[run_id] = (degraded, filtered)
    findings: list[ContextPressureRun] = []
    for run_id in sorted(by_run_seen):
        tool_call_count = by_run_tool_calls.get(run_id, 0)
        provider_error_count = by_run_provider_errors.get(run_id, 0)
        final = by_run_final.get(run_id)
        has_final = final is not None
        degraded = final[0] if final is not None else False
        filtered = final[1] if final is not None else False
        if not (
            degraded
            or filtered
            or (not has_final and provider_error_count > 0)
            or (not has_final and tool_call_count > 0)
        ):
            continue
        findings.append(
            ContextPressureRun(
                run_id=run_id,
                degraded=degraded,
                filtered=filtered,
                has_final_response=has_final,
                provider_protocol_error_count=provider_error_count,
                tool_call_count=tool_call_count,
            )
        )
    return tuple(findings)


def _build_provider_partial_tool_calls(
    entries: list[TraceLineEntry],
) -> tuple[ProviderPartialToolCallDiagnostic, ...]:
    """从 provider_protocol_error record 提取 partial tool call 诊断。

    :param entries: 去重后的 record 列表。
    :returns: partial tool call 诊断元组。
    :raises ValueError: ``partial_tool_calls_json`` 非合法 JSON 时抛出。
    """

    diagnostics: list[ProviderPartialToolCallDiagnostic] = []
    for entry in entries:
        record = entry.record
        if _read_str(record, "trace_type") != _TRACE_TYPE_PROVIDER_PROTOCOL_ERROR:
            continue
        partials_raw = _read_str(record, "partial_tool_calls_json")
        if partials_raw == "":
            continue
        parsed = json.loads(partials_raw)
        if not isinstance(parsed, list):
            raise ValueError("partial_tool_calls_json must decode to list")
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("partial tool call summary must be object")
            diagnostics.append(
                ProviderPartialToolCallDiagnostic(
                    run_id=_read_str(record, "run_id"),
                    iteration_id=_read_str(record, "iteration_id"),
                    error_code=_read_str(record, "error_code"),
                    tool_call_index=_read_int(item, "tool_call_index") or 0,
                    tool_call_id=_read_optional_str(item, "tool_call_id"),
                    name_fragment=_read_optional_str(item, "name_fragment"),
                    arguments_byte_size=(
                        _read_int(item, "arguments_byte_size") or 0
                    ),
                    arguments_sha256=_read_optional_str(
                        item, "arguments_sha256"
                    ),
                )
            )
    return tuple(diagnostics)


def analyze_trace_root(*, trace_root: Path) -> TraceAnalysisReport:
    """读取并分析 ``<trace_root>/sessions/**/tool_calls_*.jsonl``。

    :param trace_root: trace 根目录。
    :returns: :class:`TraceAnalysisReport`。
    :raises ValueError: 命中 OLD/未知 ``schema_version`` 时抛出。
    :raises OSError: 文件读取失败时透传。
    """

    files = _iter_jsonl_files(trace_root=trace_root)
    total_lines_read = 0
    seen_keys: set[str] = set()
    duplicate_keys: list[str] = []
    deduped_entries: list[TraceLineEntry] = []
    for file_path in files:
        with file_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped = raw_line.strip()
                if stripped == "":
                    continue
                total_lines_read += 1
                record_obj = json.loads(stripped)
                if not isinstance(record_obj, dict):
                    raise ValueError(f"trace record at {file_path}:{line_number} is not a " f"JSON object")
                record: Mapping[str, JsonValue] = record_obj
                _validate_schema_version(
                    value=record.get("schema_version", ""),
                    file_path=file_path,
                )
                idempotency_key = _read_str(record, "idempotency_key")
                if idempotency_key in seen_keys:
                    duplicate_keys.append(idempotency_key)
                    continue
                seen_keys.add(idempotency_key)
                deduped_entries.append(
                    TraceLineEntry(
                        file_path=file_path,
                        line_number=line_number,
                        record=record,
                    )
                )

    counts_by_type: dict[str, int] = {}
    for entry in deduped_entries:
        trace_type = _read_str(entry.record, "trace_type")
        counts_by_type[trace_type] = counts_by_type.get(trace_type, 0) + 1

    repeated_tool_calls = _detect_repeated_tool_calls(deduped_entries)
    truncation_gaps = _detect_truncation_gaps(deduped_entries)
    fetch_more_issues = _detect_fetch_more_unknown_cursor(deduped_entries)
    position_gaps = _detect_position_gaps(deduped_entries)
    tool_stats = _summarize_tool_stats(deduped_entries)
    failure_patterns = _build_failure_patterns(deduped_entries)
    detailed_failure_patterns = _build_detailed_failure_patterns(deduped_entries)
    context_pressure_runs = _build_context_pressure_runs(deduped_entries)
    provider_partial_tool_calls = _build_provider_partial_tool_calls(
        deduped_entries
    )
    provider_error_count = counts_by_type.get(_TRACE_TYPE_PROVIDER_PROTOCOL_ERROR, 0)
    final_response_present = counts_by_type.get(_TRACE_TYPE_FINAL_RESPONSE, 0) > 0
    return TraceAnalysisReport(
        total_lines_read=total_lines_read,
        deduped_record_count=len(deduped_entries),
        duplicate_idempotency_keys=tuple(duplicate_keys),
        repeated_tool_calls=repeated_tool_calls,
        truncation_without_fetch_more=truncation_gaps,
        fetch_more_with_unknown_scope_token=fetch_more_issues,
        provider_protocol_error_count=provider_error_count,
        final_response_present=final_response_present,
        source_event_position_gaps=position_gaps,
        record_counts_by_type=counts_by_type,
        tool_stats=tool_stats,
        failure_patterns=failure_patterns,
        detailed_failure_patterns=detailed_failure_patterns,
        context_pressure_runs=context_pressure_runs,
        provider_partial_tool_calls=provider_partial_tool_calls,
    )


def _format_report(report: TraceAnalysisReport) -> str:
    """把报告渲染为人类可读字符串。

    :param report: 诊断报告。
    :returns: 多行文本。
    :raises Exception: 不主动抛出异常。
    """

    lines: list[str] = []
    lines.append(f"total_lines_read={report.total_lines_read}")
    lines.append(f"deduped_record_count={report.deduped_record_count}")
    lines.append("duplicate_idempotency_keys=" f"{len(report.duplicate_idempotency_keys)}")
    lines.append(f"provider_protocol_error_count={report.provider_protocol_error_count}")
    lines.append(f"final_response_present={report.final_response_present}")
    lines.append("record_counts_by_type:")
    for trace_type, count in sorted(report.record_counts_by_type.items()):
        lines.append(f"  {trace_type}: {count}")
    lines.append(f"repeated_tool_calls: {len(report.repeated_tool_calls)}")
    for repeat in report.repeated_tool_calls:
        lines.append(f"  run={repeat.run_id} tool={repeat.tool_name} " f"count={repeat.count}")
    lines.append("truncation_without_fetch_more: " f"{len(report.truncation_without_fetch_more)}")
    for gap in report.truncation_without_fetch_more:
        lines.append(f"  run={gap.run_id} tool_call={gap.tool_call_id} " f"scope_token={gap.scope_token!r}")
    lines.append("fetch_more_with_unknown_scope_token: " f"{len(report.fetch_more_with_unknown_scope_token)}")
    for issue in report.fetch_more_with_unknown_scope_token:
        lines.append(
            f"  run={issue.run_id} tool_call={issue.tool_call_id} "
            f"cursor={issue.scope_token_or_cursor!r} reason={issue.reason}"
        )
    lines.append(
        f"provider_partial_tool_calls: {len(report.provider_partial_tool_calls)}"
    )
    for partial in report.provider_partial_tool_calls:
        lines.append(
            f"  run={partial.run_id} iteration={partial.iteration_id} "
            f"error={partial.error_code} index={partial.tool_call_index} "
            f"id={partial.tool_call_id!r} name={partial.name_fragment!r} "
            f"arg_bytes={partial.arguments_byte_size} "
            f"arg_sha256={partial.arguments_sha256!r}"
        )
    lines.append(f"source_event_position_gaps: {len(report.source_event_position_gaps)}")
    for pos_gap in report.source_event_position_gaps:
        lines.append(f"  run={pos_gap.run_id} prev={pos_gap.prev_position} " f"next={pos_gap.next_position}")
    lines.append(f"tool_stats: {len(report.tool_stats)}")
    for stat in report.tool_stats:
        top_errors_text = ", ".join(f"{code}:{count}" for code, count in stat.top_error_codes)
        lines.append(
            f"  tool={stat.tool_name} call_count={stat.call_count} "
            f"success_rate={stat.success_rate:.2f} "
            f"truncation_rate={stat.truncation_rate:.2f} "
            f"median_result_bytes={stat.median_result_bytes} "
            f"p90_result_bytes={stat.p90_result_bytes} "
            f"top_errors=[{top_errors_text}]"
        )
    lines.append(f"failure_patterns: {len(report.failure_patterns)}")
    for pattern in report.failure_patterns:
        lines.append(f"  tool={pattern.tool_name} error={pattern.error_code} " f"count={pattern.count}")
    lines.append(f"detailed_failure_patterns: {len(report.detailed_failure_patterns)}")
    for detailed in report.detailed_failure_patterns:
        lines.append(
            f"  tool={detailed.tool_name} "
            f"signature={detailed.error_signature} "
            f"error={detailed.error_code} count={detailed.count}"
        )
    lines.append(f"context_pressure_runs: {len(report.context_pressure_runs)}")
    for pressure in report.context_pressure_runs:
        lines.append(
            f"  run={pressure.run_id} degraded={pressure.degraded} "
            f"filtered={pressure.filtered} "
            f"has_final_response={pressure.has_final_response} "
            f"provider_errors={pressure.provider_protocol_error_count} "
            f"tool_calls={pressure.tool_call_count}"
        )
    return "\n".join(lines)


def _parse_cli_args(argv: list[str]) -> Path:
    """解析 CLI 参数。

    :param argv: 不含程序名的参数列表。
    :returns: trace_root 路径。
    :raises SystemExit: 参数缺失时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser(description="Analyze Host P7 tool trace JSONL output.")
    parser.add_argument(
        "trace_root",
        type=Path,
        help="trace JSONL 根目录（含 sessions/<session_id>/tool_calls_*.jsonl）。",
    )
    namespace = parser.parse_args(argv)
    trace_root: Path = namespace.trace_root
    return trace_root


def main(argv: list[str] | None = None) -> None:
    """脚本入口。

    :param argv: 不含程序名的参数列表；为 ``None`` 时读取 ``sys.argv``。
    :returns: 无返回值。
    :raises Exception: 透传 :func:`analyze_trace_root` 抛出的异常。
    """

    actual_argv = list(sys.argv[1:]) if argv is None else list(argv)
    trace_root = _parse_cli_args(actual_argv)
    report = analyze_trace_root(trace_root=trace_root)
    print(_format_report(report))


if __name__ == "__main__":
    main()


__all__ = [
    "ContextPressureRun",
    "DetailedFailurePattern",
    "FailurePattern",
    "FetchMoreScopeIssue",
    "PositionGap",
    "RepeatedToolCall",
    "ToolStats",
    "TraceAnalysisReport",
    "TraceLineEntry",
    "TruncationGap",
    "analyze_trace_root",
    "main",
]
