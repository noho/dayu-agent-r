"""Tool Trace Analyzer 的可信输入读取与完整性边界。

本模块按显式来源先读取单个 SQLite 只读快照，再通过 Tool Trace producer
同源文件锁捕获 cold JSONL 精确前缀。它拥有 strict current-schema parser、
hot/cold join、resolver orchestration 与输入诊断；不拥有行为规则或报告。
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import is_sha256_digest, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_read_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.options import HostSQLiteStoragePolicy
from dayu.host.durable.tool_trace import (
    TOOL_TRACE_QUERY_MAX_LIMIT,
    RunnerCallReconstructionSignal,
    RunnerCallResolvedProjection,
    ToolTraceHotRow,
    ToolTraceResolvedJsonPayload,
    ToolTraceResolvedRowPayloads,
    read_runner_call_reconstruction_signals_by_run,
    read_tool_trace_page,
    resolve_runner_call_projection_from_signal,
    resolve_tool_trace_hot_row_payloads,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.tool_trace import (
    _LOCK_TIMEOUT_SECONDS,
    _tool_trace_cold_lock_path,
)
from dayu.host.tool_trace_analysis_contracts import (
    ToolTraceAnalysisPolicy,
    ToolTraceAnalysisSource,
    ToolTraceInputMode,
)
from dayu.runtime.filelock import (
    RuntimeFileLockError,
    RuntimeFileLockTimeoutError,
    file_lock,
)

_COLD_SCHEMA_VERSION = 1
_RUNNER_CALL_EVENT_TYPE = "RUNNER_CALL_INPUT_ASSEMBLED"
_COLD_REF_PREFIX = "tool-trace-cold:"
_INPUT_CHANGED_REASON = "input_changed_during_analysis"
_HOT_UNAVAILABLE_REASON = "hot_store_unavailable"
_PAYLOAD_UNAVAILABLE_REASON = "payload_resolution_unavailable"

_REQUIRED_COLD_FIELDS = frozenset(
    {
        "schema_version",
        "event_sequence",
        "event_id",
        "event_type",
        "event_class",
        "occurred_at",
        "session_id",
        "run_id",
        "attempt_id",
        "execution_id",
        "tool_call_id",
        "tool_name",
        "provider_request_id",
        "client_correlation_id",
        "diagnostic_refs",
        "operation_context_refs",
        "operation_context_digest",
        "normalized_arguments_digest",
        "semantic_input_digest",
        "outcome_digest",
        "payload_ref",
        "payload_digest",
        "source_payload_ref",
        "source_payload_digest",
        "policy_decision",
        "trace_summary",
        "line_digest",
        "cold_trace_ref",
        "cold_trace_digest",
    }
)
_OPTIONAL_TEXT_FIELDS = (
    "run_id",
    "attempt_id",
    "execution_id",
    "tool_call_id",
    "tool_name",
    "provider_request_id",
    "client_correlation_id",
    "payload_ref",
    "source_payload_ref",
    "policy_decision",
)
_OPTIONAL_DIGEST_FIELDS = (
    "operation_context_digest",
    "normalized_arguments_digest",
    "semantic_input_digest",
    "outcome_digest",
    "payload_digest",
    "source_payload_digest",
)
_REQUIRED_TEXT_FIELDS = (
    "event_id",
    "event_type",
    "event_class",
    "occurred_at",
    "session_id",
    "line_digest",
    "cold_trace_ref",
    "cold_trace_digest",
)


class ToolTraceAnalysisInputFailureReason(StrEnum):
    """阻止本次分析完成的输入读取失败原因。"""

    SOURCE_INVALID = "source_invalid"
    HOT_STORE_READ_FAILED = "hot_store_read_failed"
    COLD_SNAPSHOT_LOCK_TIMEOUT = "cold_snapshot_lock_timeout"
    COLD_SNAPSHOT_LOCK_FAILED = "cold_snapshot_lock_failed"
    COLD_SNAPSHOT_READ_FAILED = "cold_snapshot_read_failed"


class ToolTraceInputDiagnosticCode(StrEnum):
    """可信输入阶段产生的稳定完整性诊断代码。"""

    INVALID_JSON_LINE = "input.invalid_json_line"
    NON_OBJECT_JSON_LINE = "input.non_object_json_line"
    UNSUPPORTED_SCHEMA_VERSION = "input.unsupported_schema_version"
    INVALID_RECORD_FIELD = "input.invalid_record_field"
    LINE_DIGEST_MISMATCH = "integrity.line_digest_mismatch"
    COLD_DIGEST_MISMATCH = "integrity.cold_digest_mismatch"
    COLD_REF_MISMATCH = "integrity.cold_ref_mismatch"
    DUPLICATE_COLD_LINE = "integrity.duplicate_cold_line"
    COLD_SOURCE_CONFLICT = "integrity.cold_source_conflict"
    MISSING_COLD_TRACE = "integrity.missing_cold_trace"
    MISSING_HOT_TRACE = "integrity.missing_hot_trace"
    HOT_COLD_SOURCE_MISMATCH = "integrity.hot_cold_source_mismatch"
    PAYLOAD_UNRESOLVABLE = "integrity.payload_unresolvable"
    RUNNER_CALL_RECONSTRUCTION_LIMITED = "integrity.runner_call_reconstruction_limited"


class ToolTracePayloadCategory(StrEnum):
    """S1 verified payload measure 的内部类别。"""

    COLD_LINE = "cold_line"
    SOURCE_EVENT_PAYLOAD = "source_event_payload"
    TOOL_ARGUMENTS = "tool_arguments"
    TOOL_RESULT = "tool_result"
    PROVIDER_DIAGNOSTIC = "provider_diagnostic"
    RUNNER_CALL_MANIFEST = "runner_call_manifest"
    RUNNER_INPUT_PROJECTION = "runner_input_projection"
    SELECTED_TOOL_SCHEMA_SNAPSHOT = "selected_tool_schema_snapshot"


class ToolTraceAnalysisInputError(Exception):
    """Tool Trace 分析输入 fatal error。

    :param reason: 稳定失败原因。
    :param source_path: 失败对应的输入路径。
    :param summary: 有界诊断摘要。
    :param cause_type: 可选底层异常类型名。
    """

    reason: ToolTraceAnalysisInputFailureReason
    source_path: Path
    summary: str
    cause_type: str | None

    def __init__(
        self,
        *,
        reason: ToolTraceAnalysisInputFailureReason,
        source_path: Path,
        summary: str,
        cause_type: str | None = None,
    ) -> None:
        """初始化输入 fatal error。

        :param reason: 稳定失败原因。
        :param source_path: 失败对应的输入路径。
        :param summary: 有界诊断摘要。
        :param cause_type: 可选底层异常类型名。
        :returns: ``None``。
        :raises TypeError: 父类异常初始化失败时抛出。
        """

        self.reason = reason
        self.source_path = source_path
        self.summary = summary
        self.cause_type = cause_type
        super().__init__(f"{reason.value}: {summary}")


@dataclass(frozen=True, slots=True)
class ToolTraceColdFileIdentity:
    """cold snapshot 打开 handle 的平台文件身份。

    :param device: ``fstat.st_dev``。
    :param inode: ``fstat.st_ino``。
    """

    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class ToolTraceColdSnapshot:
    """单次 cold JSONL 精确前缀快照。

    :param cold_jsonl_path: 实际读取路径。
    :param cold_lock_path: Host owner 派生的实际锁路径。
    :param prefix_byte_length: 锁内捕获的精确前缀字节数。
    :param file_identity: 同一打开 handle 的平台身份。
    """

    cold_jsonl_path: Path
    cold_lock_path: Path
    prefix_byte_length: int
    file_identity: ToolTraceColdFileIdentity


@dataclass(frozen=True, slots=True)
class ToolTraceColdRecord:
    """strict parser 接受的 current-schema cold record。

    :param source_path: cold JSONL 路径。
    :param line_number: 1-based 行号。
    :param record_size_bytes: 不含行终止符的 record bytes。
    :param event_id: source EventLog id。
    :param event_sequence: source EventLog sequence。
    :param event_type: source EventLog event type。
    :param event_class: source EventLog event class。
    :param session_id: source Session id。
    :param run_id: 可选 Run id。
    :param cold_trace_ref: cold source ref。
    :param line_digest: producer canonical preimage digest。
    :param fields: 已校验 current-schema JSON object。
    """

    source_path: Path
    line_number: int
    record_size_bytes: int
    event_id: str
    event_sequence: int
    event_type: str
    event_class: str
    session_id: str
    run_id: str | None
    cold_trace_ref: str
    line_digest: str
    fields: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ToolTraceInputDiagnostic:
    """输入语法或完整性诊断。

    :param code: 稳定诊断代码。
    :param source_path: 直接证据路径。
    :param summary: operator-readable 中文摘要。
    :param line_number: 可选 cold 行号。
    :param event_id: 可选 event id。
    :param event_sequence: 可选 event sequence。
    :param cause_type: resolver 等 owner error 的类型名。
    """

    code: ToolTraceInputDiagnosticCode
    source_path: Path
    summary: str
    line_number: int | None = None
    event_id: str | None = None
    event_sequence: int | None = None
    cause_type: str | None = None


@dataclass(frozen=True, slots=True)
class ToolTraceInputLimitation:
    """输入观察窗口或 capability limitation。

    :param reason_code: 稳定 limitation reason。
    :param summary: operator-readable 中文摘要。
    :param source_path: 直接相关输入路径。
    :param line_number: 可选 cold 行号。
    :param event_id: 可选 event id。
    :param event_sequence: 可选 event sequence。
    :param hot_event_sequence_watermark: 可选 hot snapshot watermark。
    """

    reason_code: str
    summary: str
    source_path: Path
    line_number: int | None = None
    event_id: str | None = None
    event_sequence: int | None = None
    hot_event_sequence_watermark: int | None = None


@dataclass(frozen=True, slots=True)
class ToolTraceResolvedPayloadMeasure:
    """resolver 校验通过的内部 payload byte measure。

    :param category: payload 业务类别。
    :param payload_ref: descriptor ref。
    :param payload_digest: 已校验 digest。
    :param payload_size_bytes: 已校验实际字节数。
    :param event_id: owner event id。
    :param event_sequence: owner event sequence。
    """

    category: ToolTracePayloadCategory
    payload_ref: str
    payload_digest: str
    payload_size_bytes: int
    event_id: str
    event_sequence: int


@dataclass(frozen=True, slots=True)
class ToolTraceJoinedRecord:
    """通过 strict identity/digest 校验的 hot/cold join。

    :param hot_row: durable hot projection row。
    :param cold_record: strict cold record。
    :param resolved_payloads: 可选 source/descriptor resolver 结果。
    :param runner_call_projection: 可选完整 runner-call reconstruction 结果。
    """

    hot_row: ToolTraceHotRow
    cold_record: ToolTraceColdRecord
    resolved_payloads: ToolTraceResolvedRowPayloads | None
    runner_call_projection: RunnerCallResolvedProjection | None


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisDataset:
    """S1 可信输入阶段的 immutable normalized dataset。

    :param source: 已复核显式来源。
    :param cold_snapshot: 实际取得的 cold prefix；hot-only 时为 ``None``。
    :param hot_store_available: 本次是否成功取得 hot snapshot。
    :param hot_event_sequence_watermark: hot 可用时为最大 sequence 或 ``0``。
    :param hot_rows: hot snapshot 全部 rows。
    :param cold_records: 去除 exact duplicate/conflict 后的 valid cold records。
    :param joined_records: identity/digest 完整匹配的 rows。
    :param input_diagnostics: 语法、完整性和 resolver 诊断。
    :param limitations: capability / observation-window limitations。
    :param payload_measures: verified descriptor byte measures。
    """

    source: ToolTraceAnalysisSource
    cold_snapshot: ToolTraceColdSnapshot | None
    hot_store_available: bool
    hot_event_sequence_watermark: int | None
    hot_rows: tuple[ToolTraceHotRow, ...]
    cold_records: tuple[ToolTraceColdRecord, ...]
    joined_records: tuple[ToolTraceJoinedRecord, ...]
    input_diagnostics: tuple[ToolTraceInputDiagnostic, ...]
    limitations: tuple[ToolTraceInputLimitation, ...]
    payload_measures: tuple[ToolTraceResolvedPayloadMeasure, ...]


@dataclass(frozen=True, slots=True)
class _HotSnapshot:
    """单个 SQLite read transaction 产生的完整 hot snapshot。"""

    rows: tuple[ToolTraceHotRow, ...]
    watermark: int
    resolved_rows: Mapping[str, ToolTraceResolvedRowPayloads]
    runner_projections: Mapping[str, RunnerCallResolvedProjection]
    diagnostics: tuple[ToolTraceInputDiagnostic, ...]
    payload_measures: tuple[ToolTraceResolvedPayloadMeasure, ...]


@dataclass(frozen=True, slots=True)
class _CapturedColdPrefix:
    """锁内捕获并在锁外读完的 cold prefix。"""

    snapshot: ToolTraceColdSnapshot
    content: bytes


def load_tool_trace_analysis_input(
    source: ToolTraceAnalysisSource,
    policy: ToolTraceAnalysisPolicy,
    sqlite_policy: HostSQLiteStoragePolicy,
) -> ToolTraceAnalysisDataset:
    """读取并标准化 Tool Trace Analyzer 输入。

    :param source: 五字段显式来源。
    :param policy: 已校验 Analyzer 诊断 policy。
    :param sqlite_policy: durable SQLite policy；只读 opener 只使用 busy timeout。
    :returns: immutable normalized dataset。
    :raises ToolTraceAnalysisInputError: source、hot store 或 cold snapshot fatal
        failure 时抛出。
    :raises TypeError: policy 类型错误时抛出。
    """

    _revalidate_source(source)
    if not isinstance(policy, ToolTraceAnalysisPolicy):
        raise TypeError("policy must be ToolTraceAnalysisPolicy")
    if not isinstance(sqlite_policy, HostSQLiteStoragePolicy):
        raise TypeError("sqlite_policy must be HostSQLiteStoragePolicy")

    hot_snapshot, initial_limitations = _load_hot_snapshot(
        source,
        sqlite_policy,
    )
    captured_prefix = _load_cold_snapshot(source, hot_snapshot is not None)
    cold_records: tuple[ToolTraceColdRecord, ...] = ()
    cold_diagnostics: tuple[ToolTraceInputDiagnostic, ...] = ()
    cold_snapshot: ToolTraceColdSnapshot | None = None
    if captured_prefix is not None:
        cold_snapshot = captured_prefix.snapshot
        parsed_records, parser_diagnostics = _parse_cold_prefix(
            source.cold_jsonl_path,
            captured_prefix.content,
        )
        cold_records, source_diagnostics = _deduplicate_cold_records(parsed_records)
        cold_diagnostics = parser_diagnostics + source_diagnostics

    hot_rows = () if hot_snapshot is None else hot_snapshot.rows
    watermark = None if hot_snapshot is None else hot_snapshot.watermark
    joined_records, join_diagnostics, window_limitations = _join_hot_and_cold(
        source=source,
        hot_snapshot=hot_snapshot,
        cold_records=cold_records,
    )
    hot_diagnostics = () if hot_snapshot is None else hot_snapshot.diagnostics
    payload_measures = () if hot_snapshot is None else hot_snapshot.payload_measures
    cold_measures = tuple(
        ToolTraceResolvedPayloadMeasure(
            category=ToolTracePayloadCategory.COLD_LINE,
            payload_ref=record.cold_trace_ref,
            payload_digest=record.line_digest,
            payload_size_bytes=record.record_size_bytes,
            event_id=record.event_id,
            event_sequence=record.event_sequence,
        )
        for record in cold_records
    )
    limitations = list(initial_limitations + window_limitations)
    if source.artifact_root is None and hot_snapshot is None:
        limitations.append(
            ToolTraceInputLimitation(
                reason_code=_PAYLOAD_UNAVAILABLE_REASON,
                summary="当前输入没有 hot store 与 artifact root，无法校验 payload。",
                source_path=source.requested_path,
            )
        )
    return ToolTraceAnalysisDataset(
        source=source,
        cold_snapshot=cold_snapshot,
        hot_store_available=hot_snapshot is not None,
        hot_event_sequence_watermark=watermark,
        hot_rows=hot_rows,
        cold_records=cold_records,
        joined_records=joined_records,
        input_diagnostics=(cold_diagnostics + join_diagnostics + hot_diagnostics),
        limitations=tuple(limitations),
        payload_measures=cold_measures + payload_measures,
    )


def _revalidate_source(source: ToolTraceAnalysisSource) -> None:
    """在实际 load 前再次执行 public Source boundary。

    :param source: 待复核来源。
    :returns: ``None``。
    :raises ToolTraceAnalysisInputError: 当前路径状态已违反 Source contract 时抛出。
    """

    if not isinstance(source, ToolTraceAnalysisSource):
        raise TypeError("source must be ToolTraceAnalysisSource")
    try:
        ToolTraceAnalysisSource(
            requested_path=source.requested_path,
            mode=source.mode,
            cold_jsonl_path=source.cold_jsonl_path,
            hot_db_path=source.hot_db_path,
            artifact_root=source.artifact_root,
        )
    except (TypeError, ValueError, OSError) as exc:
        raise ToolTraceAnalysisInputError(
            reason=ToolTraceAnalysisInputFailureReason.SOURCE_INVALID,
            source_path=source.requested_path,
            summary="输入来源在实际读取前已不满足显式布局契约。",
            cause_type=type(exc).__name__,
        ) from exc


def _load_hot_snapshot(
    source: ToolTraceAnalysisSource,
    sqlite_policy: HostSQLiteStoragePolicy,
) -> tuple[_HotSnapshot | None, tuple[ToolTraceInputLimitation, ...]]:
    """先于 cold snapshot 读取完整 hot snapshot。

    :param source: 已复核来源。
    :param sqlite_policy: durable SQLite policy。
    :returns: hot snapshot 与 capability limitations。
    :raises ToolTraceAnalysisInputError: 已存在 hot DB 无法打开或校验时抛出。
    """

    hot_db_path = source.hot_db_path
    if hot_db_path is None:
        return None, (
            ToolTraceInputLimitation(
                reason_code=_HOT_UNAVAILABLE_REASON,
                summary="当前显式输入模式不包含 hot store。",
                source_path=source.requested_path,
            ),
        )
    try:
        hot_db_path.stat()
    except FileNotFoundError:
        return None, (
            ToolTraceInputLimitation(
                reason_code=_HOT_UNAVAILABLE_REASON,
                summary="预期 hot store 当前不存在，仅能执行 cold-only 分析。",
                source_path=hot_db_path,
            ),
        )
    except OSError as exc:
        raise ToolTraceAnalysisInputError(
            reason=ToolTraceAnalysisInputFailureReason.HOT_STORE_READ_FAILED,
            source_path=hot_db_path,
            summary="预期 hot store metadata 无法读取。",
            cause_type=type(exc).__name__,
        ) from exc
    artifact_root = source.artifact_root
    if artifact_root is None:
        raise ToolTraceAnalysisInputError(
            reason=ToolTraceAnalysisInputFailureReason.SOURCE_INVALID,
            source_path=source.requested_path,
            summary="directory input 缺少显式 artifact root。",
        )
    snapshot: _HotSnapshot | None = None
    try:
        with open_host_durable_read_store(
            db_path=hot_db_path,
            artifact_root=artifact_root,
            sqlite_policy=sqlite_policy,
        ) as store:
            snapshot = store.run_read(
                lambda transaction: _read_hot_snapshot_in_transaction(
                    transaction,
                    hot_db_path,
                )
            )
    except (HostDurableError, OSError) as exc:
        raise ToolTraceAnalysisInputError(
            reason=ToolTraceAnalysisInputFailureReason.HOT_STORE_READ_FAILED,
            source_path=hot_db_path,
            summary="已存在的 hot store 无法以当前 schema 完成只读分析。",
            cause_type=type(exc).__name__,
        ) from exc
    if snapshot is None:
        raise ToolTraceAnalysisInputError(
            reason=ToolTraceAnalysisInputFailureReason.HOT_STORE_READ_FAILED,
            source_path=hot_db_path,
            summary="hot store 只读 transaction 未返回 snapshot。",
        )
    return snapshot, ()


def _read_hot_snapshot_in_transaction(
    transaction: HostTransaction,
    hot_db_path: Path,
) -> _HotSnapshot:
    """在单个 read transaction 中分页读取并解析全部 hot rows。

    :param transaction: 当前 read-only Host transaction。
    :param hot_db_path: 本次 hot snapshot 的真实 DB 路径。
    :returns: 完整 hot snapshot。
    :raises HostDurableError: hot row decode 或分页查询失败时抛出。
    """

    rows: list[ToolTraceHotRow] = []
    cursor = 0
    while True:
        page = read_tool_trace_page(
            transaction,
            cursor,
            TOOL_TRACE_QUERY_MAX_LIMIT,
        )
        rows.extend(page.rows)
        cursor = page.next_event_sequence
        if not page.has_more:
            break

    runner_signals = _read_runner_signals(transaction, tuple(rows))
    resolved_rows: dict[str, ToolTraceResolvedRowPayloads] = {}
    runner_projections: dict[str, RunnerCallResolvedProjection] = {}
    diagnostics: list[ToolTraceInputDiagnostic] = []
    measures: list[ToolTraceResolvedPayloadMeasure] = []
    for row in rows:
        try:
            resolved = resolve_tool_trace_hot_row_payloads(transaction, row)
        except HostDurableError as exc:
            diagnostics.append(_resolver_diagnostic(hot_db_path, row, exc))
        else:
            resolved_rows[row.event_id] = resolved
            if resolved.descriptor_payload is not None and row.event_type != _RUNNER_CALL_EVENT_TYPE:
                measures.append(
                    _payload_measure_from_resolved(
                        row,
                        resolved.descriptor_payload,
                        _payload_category_for_hot_row(row),
                    )
                )
        if row.event_type != _RUNNER_CALL_EVENT_TYPE:
            continue
        signal = runner_signals.get(row.event_id)
        if signal is None:
            diagnostics.append(
                ToolTraceInputDiagnostic(
                    code=(ToolTraceInputDiagnosticCode.RUNNER_CALL_RECONSTRUCTION_LIMITED),
                    source_path=hot_db_path,
                    summary="runner-call hot row 没有唯一 typed reconstruction signal。",
                    event_id=row.event_id,
                    event_sequence=row.event_sequence,
                )
            )
            continue
        try:
            projection = resolve_runner_call_projection_from_signal(
                transaction,
                signal,
            )
        except HostDurableError as exc:
            diagnostics.append(_runner_resolver_diagnostic(hot_db_path, row, exc))
            continue
        runner_projections[row.event_id] = projection
        measures.extend(_runner_projection_measures(row, projection))
    watermark = rows[-1].event_sequence if rows else 0
    return _HotSnapshot(
        rows=tuple(rows),
        watermark=watermark,
        resolved_rows=resolved_rows,
        runner_projections=runner_projections,
        diagnostics=tuple(diagnostics),
        payload_measures=tuple(measures),
    )


def _read_runner_signals(
    transaction: HostTransaction,
    rows: tuple[ToolTraceHotRow, ...],
) -> Mapping[str, RunnerCallReconstructionSignal]:
    """按 typed query contract 读取 snapshot 内全部 runner-call signals。

    :param transaction: 当前 read-only transaction。
    :param rows: 已读取 hot rows。
    :returns: 以 owner event id 索引的 typed signals。
    :raises HostDurableError: signal query 或 decode 失败时抛出。
    """

    run_ids = sorted(
        {row.run_id for row in rows if row.event_type == _RUNNER_CALL_EVENT_TYPE and row.run_id is not None}
    )
    signals: dict[str, RunnerCallReconstructionSignal] = {}
    for run_id in run_ids:
        cursor = 0
        while True:
            page = read_runner_call_reconstruction_signals_by_run(
                transaction,
                run_id,
                cursor,
                TOOL_TRACE_QUERY_MAX_LIMIT,
            )
            for signal in page.signals:
                signals[signal.event_id] = signal
            cursor = page.next_event_sequence
            if not page.has_more:
                break
    return signals


def _load_cold_snapshot(
    source: ToolTraceAnalysisSource,
    hot_available: bool,
) -> _CapturedColdPrefix | None:
    """在 hot transaction 关闭后读取 cold 精确前缀。

    :param source: 已复核来源。
    :param hot_available: 本次是否已有可用 hot snapshot。
    :returns: cold prefix；合法 hot-only 输入返回 ``None``。
    :raises ToolTraceAnalysisInputError: cold-only 缺失或 snapshot 失败时抛出。
    """

    cold_path = source.cold_jsonl_path
    try:
        cold_path.stat()
    except FileNotFoundError:
        if (
            source.mode
            in (
                ToolTraceInputMode.WORKSPACE_DIRECTORY,
                ToolTraceInputMode.DAYU_DIRECTORY,
            )
            and hot_available
        ):
            return None
        raise ToolTraceAnalysisInputError(
            reason=ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_READ_FAILED,
            source_path=cold_path,
            summary="当前输入要求的 cold JSONL 不存在。",
        )
    except OSError as exc:
        raise ToolTraceAnalysisInputError(
            reason=(ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_READ_FAILED),
            source_path=cold_path,
            summary="预期 cold JSONL metadata 无法读取。",
            cause_type=type(exc).__name__,
        ) from exc
    return _capture_cold_prefix(cold_path)


def _capture_cold_prefix(cold_path: Path) -> _CapturedColdPrefix:
    """锁内 open/fstat，锁外从同一 handle 精确读取 prefix。

    :param cold_path: 已存在的 cold JSONL regular file。
    :returns: 精确 prefix 与 snapshot metadata。
    :raises ToolTraceAnalysisInputError: lock、open、fstat、read、close 或
        identity invariant 失败时抛出。
    """

    lock_path = _tool_trace_cold_lock_path(cold_path)
    handle: BinaryIO | None = None
    initial_stat: os.stat_result | None = None
    try:
        with file_lock(
            lock_path,
            timeout_seconds=_LOCK_TIMEOUT_SECONDS,
            create_parent_dirs=False,
        ):
            handle = _open_cold_binary_file(cold_path)
            initial_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(initial_stat.st_mode):
                raise OSError("cold JSONL handle is not regular file")
    except RuntimeFileLockTimeoutError as exc:
        _close_cold_handle_best_effort(handle)
        raise ToolTraceAnalysisInputError(
            reason=(ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_LOCK_TIMEOUT),
            source_path=lock_path,
            summary="获取 Tool Trace cold snapshot 文件锁超时。",
            cause_type=type(exc).__name__,
        ) from exc
    except RuntimeFileLockError as exc:
        _close_cold_handle_best_effort(handle)
        raise ToolTraceAnalysisInputError(
            reason=(ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_LOCK_FAILED),
            source_path=lock_path,
            summary="获取或释放 Tool Trace cold snapshot 文件锁失败。",
            cause_type=type(exc).__name__,
        ) from exc
    except OSError as exc:
        _close_cold_handle_best_effort(handle)
        raise ToolTraceAnalysisInputError(
            reason=(ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_READ_FAILED),
            source_path=cold_path,
            summary="锁内 open/fstat 无法捕获 cold snapshot prefix。",
            cause_type=type(exc).__name__,
        ) from exc

    if handle is None or initial_stat is None:
        raise ToolTraceAnalysisInputError(
            reason=ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_READ_FAILED,
            source_path=cold_path,
            summary="cold snapshot 未取得有效 handle 与 file identity。",
        )
    identity = ToolTraceColdFileIdentity(
        device=initial_stat.st_dev,
        inode=initial_stat.st_ino,
    )
    snapshot = ToolTraceColdSnapshot(
        cold_jsonl_path=cold_path,
        cold_lock_path=lock_path,
        prefix_byte_length=initial_stat.st_size,
        file_identity=identity,
    )
    try:
        content = _read_exact_prefix(handle, snapshot.prefix_byte_length)
        final_stat = os.fstat(handle.fileno())
        if (
            final_stat.st_dev != identity.device
            or final_stat.st_ino != identity.inode
            or final_stat.st_size < snapshot.prefix_byte_length
        ):
            raise OSError("cold snapshot handle identity or size changed")
    except OSError as exc:
        raise ToolTraceAnalysisInputError(
            reason=(ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_READ_FAILED),
            source_path=cold_path,
            summary="无法从同一 handle 读取完整 cold snapshot prefix。",
            cause_type=type(exc).__name__,
        ) from exc
    finally:
        try:
            handle.close()
        except OSError as exc:
            raise ToolTraceAnalysisInputError(
                reason=(ToolTraceAnalysisInputFailureReason.COLD_SNAPSHOT_READ_FAILED),
                source_path=cold_path,
                summary="关闭 cold snapshot handle 失败。",
                cause_type=type(exc).__name__,
            ) from exc
    return _CapturedColdPrefix(snapshot=snapshot, content=content)


def _open_cold_binary_file(path: Path) -> BinaryIO:
    """以 binary read-only 模式打开 cold JSONL。

    :param path: cold JSONL 路径。
    :returns: binary file handle。
    :raises OSError: 文件无法打开时抛出。
    """

    return path.open("rb")


def _read_exact_prefix(handle: BinaryIO, prefix_byte_length: int) -> bytes:
    """从当前 handle 位置循环读取精确字节数，不读取动态 EOF。

    :param handle: 锁内打开的同一 binary handle。
    :param prefix_byte_length: 锁内 ``fstat`` 捕获的字节数。
    :returns: 精确 prefix bytes。
    :raises OSError: short read 或读取失败时抛出。
    """

    remaining = prefix_byte_length
    chunks: list[bytes] = []
    while remaining > 0:
        chunk = handle.read(remaining)
        if chunk == b"":
            raise OSError("cold snapshot short read")
        if len(chunk) > remaining:
            raise OSError("cold snapshot read exceeded captured prefix")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _close_cold_handle_best_effort(handle: BinaryIO | None) -> None:
    """尽力关闭尚未交给锁外读取的 cold handle。

    :param handle: 可选 binary handle。
    :returns: ``None``。
    :raises: 无。
    """

    if handle is None:
        return
    try:
        handle.close()
    except OSError:
        return


def _parse_cold_prefix(
    source_path: Path,
    content: bytes,
) -> tuple[
    tuple[ToolTraceColdRecord, ...],
    tuple[ToolTraceInputDiagnostic, ...],
]:
    """逐行 strict 解析 cold prefix。

    :param source_path: cold JSONL 路径。
    :param content: 精确 prefix bytes。
    :returns: valid records 与 malformed/integrity diagnostics。
    :raises: 无；单行错误进入 diagnostic 并继续后续行。
    """

    records: list[ToolTraceColdRecord] = []
    diagnostics: list[ToolTraceInputDiagnostic] = []
    for line_number, record_bytes in _jsonl_record_bytes(content):
        record, diagnostic = _parse_cold_record(
            source_path,
            line_number,
            record_bytes,
        )
        if record is not None:
            records.append(record)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return tuple(records), tuple(diagnostics)


def _jsonl_record_bytes(content: bytes) -> tuple[tuple[int, bytes], ...]:
    """按 ``LF``/``CRLF`` 边界切分 JSONL record bytes。

    :param content: cold prefix bytes。
    :returns: ``(1-based line, record bytes)`` 元组；record 不含终止符。
    :raises: 无。
    """

    if content == b"":
        return ()
    parts = content.split(b"\n")
    if content.endswith(b"\n"):
        parts = parts[:-1]
    records: list[tuple[int, bytes]] = []
    for index, part in enumerate(parts, start=1):
        record = part[:-1] if part.endswith(b"\r") else part
        records.append((index, record))
    return tuple(records)


def _parse_cold_record(
    source_path: Path,
    line_number: int,
    record_bytes: bytes,
) -> tuple[ToolTraceColdRecord | None, ToolTraceInputDiagnostic | None]:
    """解析并校验单个 current-schema cold record。

    :param source_path: cold JSONL 路径。
    :param line_number: 1-based 行号。
    :param record_bytes: 不含行终止符的 bytes。
    :returns: valid record 或单个稳定 diagnostic。
    :raises: 无；所有单行错误均结构化返回。
    """

    try:
        text = record_bytes.decode("utf-8", errors="strict")
        parsed = cast(JsonValue, json.loads(text))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.INVALID_JSON_LINE,
            source_path,
            line_number,
            "cold JSONL 行不是 strict UTF-8 JSON。",
        )
    if not isinstance(parsed, Mapping):
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.NON_OBJECT_JSON_LINE,
            source_path,
            line_number,
            "cold JSONL 行必须是 JSON object。",
        )
    fields = cast(Mapping[str, JsonValue], parsed)
    schema_version = fields.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != _COLD_SCHEMA_VERSION
    ):
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.UNSUPPORTED_SCHEMA_VERSION,
            source_path,
            line_number,
            "cold JSONL schema_version 不是当前版本 1。",
        )
    if frozenset(fields) != _REQUIRED_COLD_FIELDS:
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.INVALID_RECORD_FIELD,
            source_path,
            line_number,
            "cold JSONL 字段集合不符合 current schema。",
        )
    try:
        event_sequence = _required_positive_int(fields, "event_sequence")
        required_text = {name: _required_text(fields, name) for name in _REQUIRED_TEXT_FIELDS}
        optional_text = {name: _optional_text(fields, name) for name in _OPTIONAL_TEXT_FIELDS}
        for name in _OPTIONAL_DIGEST_FIELDS:
            _optional_digest(fields, name)
        _required_text_list(fields, "diagnostic_refs")
        _required_text_list(fields, "operation_context_refs")
        trace_summary = fields["trace_summary"]
        if not isinstance(trace_summary, Mapping):
            raise ValueError("trace_summary must be object")
    except (KeyError, TypeError, ValueError):
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.INVALID_RECORD_FIELD,
            source_path,
            line_number,
            "cold JSONL required/optional 字段类型或 digest 形状非法。",
        )

    event_id = required_text["event_id"]
    line_digest = required_text["line_digest"]
    cold_digest = required_text["cold_trace_digest"]
    cold_ref = required_text["cold_trace_ref"]
    if not is_sha256_digest(line_digest) or not is_sha256_digest(cold_digest):
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.INVALID_RECORD_FIELD,
            source_path,
            line_number,
            "cold JSONL line/cold digest 形状非法。",
            event_id=event_id,
            event_sequence=event_sequence,
        )
    preimage = dict(fields)
    del preimage["line_digest"]
    del preimage["cold_trace_ref"]
    del preimage["cold_trace_digest"]
    if sha256_digest_json(preimage) != line_digest:
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.LINE_DIGEST_MISMATCH,
            source_path,
            line_number,
            "cold JSONL canonical preimage 与 line_digest 不一致。",
            event_id=event_id,
            event_sequence=event_sequence,
        )
    if cold_digest != line_digest:
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.COLD_DIGEST_MISMATCH,
            source_path,
            line_number,
            "cold_trace_digest 与 line_digest 不一致。",
            event_id=event_id,
            event_sequence=event_sequence,
        )
    if cold_ref != _COLD_REF_PREFIX + event_id:
        return None, _line_diagnostic(
            ToolTraceInputDiagnosticCode.COLD_REF_MISMATCH,
            source_path,
            line_number,
            "cold_trace_ref 与 event_id 不一致。",
            event_id=event_id,
            event_sequence=event_sequence,
        )
    return (
        ToolTraceColdRecord(
            source_path=source_path,
            line_number=line_number,
            record_size_bytes=len(record_bytes),
            event_id=event_id,
            event_sequence=event_sequence,
            event_type=required_text["event_type"],
            event_class=required_text["event_class"],
            session_id=required_text["session_id"],
            run_id=optional_text["run_id"],
            cold_trace_ref=cold_ref,
            line_digest=line_digest,
            fields=fields,
        ),
        None,
    )


def _deduplicate_cold_records(
    records: tuple[ToolTraceColdRecord, ...],
) -> tuple[
    tuple[ToolTraceColdRecord, ...],
    tuple[ToolTraceInputDiagnostic, ...],
]:
    """按 event id/cold ref 去重并拒绝 source conflict。

    :param records: strict parser 接受的 records。
    :returns: 唯一 records 与 duplicate/conflict diagnostics。
    :raises: 无。
    """

    by_event_id: dict[str, ToolTraceColdRecord] = {}
    by_cold_ref: dict[str, ToolTraceColdRecord] = {}
    diagnostics: list[ToolTraceInputDiagnostic] = []
    for record in records:
        prior = by_event_id.get(record.event_id)
        prior_by_ref = by_cold_ref.get(record.cold_trace_ref)
        source_prior = prior if prior is not None else prior_by_ref
        if source_prior is None:
            by_event_id[record.event_id] = record
            by_cold_ref[record.cold_trace_ref] = record
            continue
        if (
            source_prior.event_id == record.event_id
            and source_prior.cold_trace_ref == record.cold_trace_ref
            and source_prior.line_digest == record.line_digest
        ):
            diagnostics.append(
                _record_diagnostic(
                    ToolTraceInputDiagnosticCode.DUPLICATE_COLD_LINE,
                    record,
                    "cold JSONL 包含 exact duplicate source line。",
                )
            )
            continue
        diagnostics.append(
            _record_diagnostic(
                ToolTraceInputDiagnosticCode.COLD_SOURCE_CONFLICT,
                record,
                "同一 cold source key 对应冲突 identity 或 digest。",
            )
        )
    unique_records = tuple(sorted(by_event_id.values(), key=lambda item: item.event_sequence))
    return unique_records, tuple(diagnostics)


def _join_hot_and_cold(
    *,
    source: ToolTraceAnalysisSource,
    hot_snapshot: _HotSnapshot | None,
    cold_records: tuple[ToolTraceColdRecord, ...],
) -> tuple[
    tuple[ToolTraceJoinedRecord, ...],
    tuple[ToolTraceInputDiagnostic, ...],
    tuple[ToolTraceInputLimitation, ...],
]:
    """按 event id 主键与 ref/digest/sequence 二次校验 join。

    :param source: 显式输入来源。
    :param hot_snapshot: 可选 hot snapshot。
    :param cold_records: 唯一 valid cold records。
    :returns: joined records、integrity diagnostics 与 limitations。
    :raises: 无。
    """

    diagnostics: list[ToolTraceInputDiagnostic] = []
    limitations: list[ToolTraceInputLimitation] = []
    joined: list[ToolTraceJoinedRecord] = []
    cold_by_event = {record.event_id: record for record in cold_records}
    hot_by_event = {} if hot_snapshot is None else {row.event_id: row for row in hot_snapshot.rows}
    if hot_snapshot is not None:
        for hot_row in hot_snapshot.rows:
            cold_record = cold_by_event.get(hot_row.event_id)
            if cold_record is None:
                diagnostics.append(
                    ToolTraceInputDiagnostic(
                        code=ToolTraceInputDiagnosticCode.MISSING_COLD_TRACE,
                        source_path=source.cold_jsonl_path,
                        summary="hot row 没有对应 cold JSONL line。",
                        event_id=hot_row.event_id,
                        event_sequence=hot_row.event_sequence,
                    )
                )
                continue
            if not _hot_cold_identity_matches(hot_row, cold_record):
                diagnostics.append(
                    _record_diagnostic(
                        ToolTraceInputDiagnosticCode.HOT_COLD_SOURCE_MISMATCH,
                        cold_record,
                        "hot/cold event sequence、ref、digest 或 identity 不一致。",
                    )
                )
                continue
            joined.append(
                ToolTraceJoinedRecord(
                    hot_row=hot_row,
                    cold_record=cold_record,
                    resolved_payloads=hot_snapshot.resolved_rows.get(hot_row.event_id),
                    runner_call_projection=(hot_snapshot.runner_projections.get(hot_row.event_id)),
                )
            )
    if hot_snapshot is not None:
        for cold_record in cold_records:
            if cold_record.event_id in hot_by_event:
                continue
            if cold_record.event_sequence > hot_snapshot.watermark:
                limitations.append(
                    ToolTraceInputLimitation(
                        reason_code=_INPUT_CHANGED_REASON,
                        summary=("cold row 在 hot snapshot watermark 之后提交，" "本次不判定 missing hot。"),
                        source_path=cold_record.source_path,
                        line_number=cold_record.line_number,
                        event_id=cold_record.event_id,
                        event_sequence=cold_record.event_sequence,
                        hot_event_sequence_watermark=hot_snapshot.watermark,
                    )
                )
            else:
                diagnostics.append(
                    _record_diagnostic(
                        ToolTraceInputDiagnosticCode.MISSING_HOT_TRACE,
                        cold_record,
                        "cold JSONL line 不高于 watermark，但没有对应 hot row。",
                    )
                )
    return tuple(joined), tuple(diagnostics), tuple(limitations)


def _hot_cold_identity_matches(
    hot_row: ToolTraceHotRow,
    cold_record: ToolTraceColdRecord,
) -> bool:
    """校验 hot/cold secondary identity。

    :param hot_row: hot projection row。
    :param cold_record: strict cold record。
    :returns: sequence/ref/digest 与基础 identity 全部一致时返回 ``True``。
    :raises: 无。
    """

    return (
        hot_row.event_sequence == cold_record.event_sequence
        and hot_row.event_type == cold_record.event_type
        and hot_row.event_class == cold_record.event_class
        and hot_row.session_id == cold_record.session_id
        and hot_row.run_id == cold_record.run_id
        and hot_row.cold_trace_ref == cold_record.cold_trace_ref
        and hot_row.cold_trace_digest == cold_record.line_digest
    )


def _payload_measure_from_resolved(
    row: ToolTraceHotRow,
    payload: ToolTraceResolvedJsonPayload,
    category: ToolTracePayloadCategory,
) -> ToolTraceResolvedPayloadMeasure:
    """把 resolver 结果投影为 bounded byte measure。

    :param row: owner hot row。
    :param payload: 已校验 descriptor payload。
    :param category: payload 类别。
    :returns: 不含 payload body 的 byte measure。
    :raises: 无。
    """

    return ToolTraceResolvedPayloadMeasure(
        category=category,
        payload_ref=payload.payload_ref,
        payload_digest=payload.payload_digest,
        payload_size_bytes=payload.payload_size_bytes,
        event_id=row.event_id,
        event_sequence=row.event_sequence,
    )


def _runner_projection_measures(
    row: ToolTraceHotRow,
    projection: RunnerCallResolvedProjection,
) -> tuple[ToolTraceResolvedPayloadMeasure, ...]:
    """投影 runner-call manifest/projection/schema verified measures。

    :param row: owner hot row。
    :param projection: 完整 runner-call resolver 结果。
    :returns: 不含 payload body 的 measures。
    :raises: 无。
    """

    measures = [
        _payload_measure_from_resolved(
            row,
            projection.manifest,
            ToolTracePayloadCategory.RUNNER_CALL_MANIFEST,
        ),
        _payload_measure_from_resolved(
            row,
            projection.runner_input_projection,
            ToolTracePayloadCategory.RUNNER_INPUT_PROJECTION,
        ),
    ]
    if projection.selected_tool_schema_snapshot is not None:
        measures.append(
            _payload_measure_from_resolved(
                row,
                projection.selected_tool_schema_snapshot,
                ToolTracePayloadCategory.SELECTED_TOOL_SCHEMA_SNAPSHOT,
            )
        )
    return tuple(measures)


def _payload_category_for_hot_row(
    row: ToolTraceHotRow,
) -> ToolTracePayloadCategory:
    """按 source-owned event type 分类 descriptor measure。

    :param row: hot projection row。
    :returns: 稳定内部 payload category。
    :raises: 无。
    """

    if row.event_type == _RUNNER_CALL_EVENT_TYPE:
        return ToolTracePayloadCategory.RUNNER_CALL_MANIFEST
    if row.event_type == "TOOL_CALL_REQUESTED":
        return ToolTracePayloadCategory.TOOL_ARGUMENTS
    if row.event_type == "TOOL_RESULT_ACCEPTED":
        return ToolTracePayloadCategory.TOOL_RESULT
    if row.event_type in ("PROVIDER_DIAGNOSTIC", "PROVIDER_PROTOCOL_ERROR"):
        return ToolTracePayloadCategory.PROVIDER_DIAGNOSTIC
    return ToolTracePayloadCategory.SOURCE_EVENT_PAYLOAD


def _resolver_diagnostic(
    hot_db_path: Path,
    row: ToolTraceHotRow,
    error: HostDurableError,
) -> ToolTraceInputDiagnostic:
    """保留 hot-row resolver typed cause。

    :param hot_db_path: hot store 路径。
    :param row: resolver owner hot row。
    :param error: durable resolver error。
    :returns: bounded input diagnostic。
    :raises: 无。
    """

    return ToolTraceInputDiagnostic(
        code=ToolTraceInputDiagnosticCode.PAYLOAD_UNRESOLVABLE,
        source_path=hot_db_path,
        summary="source EventLog payload 或 descriptor graph 无法通过 owner 校验。",
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        cause_type=type(error).__name__,
    )


def _runner_resolver_diagnostic(
    hot_db_path: Path,
    row: ToolTraceHotRow,
    error: HostDurableError,
) -> ToolTraceInputDiagnostic:
    """保留 runner reconstruction resolver typed cause。

    :param hot_db_path: hot store 路径。
    :param row: runner-call hot row。
    :param error: reconstruction owner error。
    :returns: bounded input diagnostic。
    :raises: 无。
    """

    return ToolTraceInputDiagnostic(
        code=(ToolTraceInputDiagnosticCode.RUNNER_CALL_RECONSTRUCTION_LIMITED),
        source_path=hot_db_path,
        summary="runner-call manifest/projection/schema graph 无法完整重建。",
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        cause_type=type(error).__name__,
    )


def _line_diagnostic(
    code: ToolTraceInputDiagnosticCode,
    source_path: Path,
    line_number: int,
    summary: str,
    *,
    event_id: str | None = None,
    event_sequence: int | None = None,
) -> ToolTraceInputDiagnostic:
    """构造 cold 行诊断。

    :param code: 稳定诊断代码。
    :param source_path: cold JSONL 路径。
    :param line_number: 1-based 行号。
    :param summary: 中文摘要。
    :param event_id: 可选 event id。
    :param event_sequence: 可选 event sequence。
    :returns: immutable diagnostic。
    :raises: 无。
    """

    return ToolTraceInputDiagnostic(
        code=code,
        source_path=source_path,
        summary=summary,
        line_number=line_number,
        event_id=event_id,
        event_sequence=event_sequence,
    )


def _record_diagnostic(
    code: ToolTraceInputDiagnosticCode,
    record: ToolTraceColdRecord,
    summary: str,
) -> ToolTraceInputDiagnostic:
    """从 strict cold record 构造完整性诊断。

    :param code: 稳定诊断代码。
    :param record: 直接证据 record。
    :param summary: 中文摘要。
    :returns: immutable diagnostic。
    :raises: 无。
    """

    return _line_diagnostic(
        code,
        record.source_path,
        record.line_number,
        summary,
        event_id=record.event_id,
        event_sequence=record.event_sequence,
    )


def _required_positive_int(
    fields: Mapping[str, JsonValue],
    field_name: str,
) -> int:
    """读取 required positive integer。

    :param fields: current-schema record。
    :param field_name: 字段名。
    :returns: 正整数值。
    :raises KeyError: 字段缺失时抛出。
    :raises ValueError: 值不是正整数时抛出。
    """

    value = fields[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be positive int")
    return value


def _required_text(
    fields: Mapping[str, JsonValue],
    field_name: str,
) -> str:
    """读取 required non-empty text。

    :param fields: current-schema record。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises KeyError: 字段缺失时抛出。
    :raises ValueError: 值不是非空文本时抛出。
    """

    value = fields[field_name]
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _optional_text(
    fields: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取 nullable non-empty text。

    :param fields: current-schema record。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises KeyError: 字段缺失时抛出。
    :raises ValueError: 非空值不是非空文本时抛出。
    """

    value = fields[field_name]
    if value is None:
        return None
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field_name} must be non-empty text or null")
    return value


def _optional_digest(
    fields: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取 nullable Host sha256 digest。

    :param fields: current-schema record。
    :param field_name: 字段名。
    :returns: digest 或 ``None``。
    :raises KeyError: 字段缺失时抛出。
    :raises ValueError: digest 类型或形状非法时抛出。
    """

    value = _optional_text(fields, field_name)
    if value is not None and not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be Host sha256 digest")
    return value


def _required_text_list(
    fields: Mapping[str, JsonValue],
    field_name: str,
) -> tuple[str, ...]:
    """读取 required text array。

    :param fields: current-schema record。
    :param field_name: 字段名。
    :returns: 文本元组。
    :raises KeyError: 字段缺失时抛出。
    :raises ValueError: 值不是纯文本 array 时抛出。
    """

    value = fields[field_name]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be array")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or item == "":
            raise ValueError(f"{field_name} items must be non-empty text")
        items.append(item)
    return tuple(items)
