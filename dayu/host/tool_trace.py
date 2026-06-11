"""Host Tool Trace hot / cold projection sink。

本模块实现 ``ToolTraceProjectionConsumer``，只消费 committed EventLog 的命名
白名单事件，写入 hot SQLite projection 与 cold append-only JSONL。Tool Trace
只用于诊断查询，不参与 Host durable truth、恢复、resume、memory 或 Run 状态迁移。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    is_sha256_digest,
    sha256_digest_json,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, read_event_by_id
from dayu.host.durable.tool_trace import (
    RunnerCallReconstructionConsumerBoundary,
    RunnerCallReconstructionDiagnosticReason,
    RunnerCallReconstructionMissingAtomKind,
    RunnerCallReconstructionMissingRefKind,
    RunnerCallReconstructionStatus,
    ToolTraceHotRow,
    ToolTraceHotRowWriteStatus,
    insert_tool_trace_hot_row_if_absent,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.projection import (
    ProjectionApplyResult,
    ProjectionApplyStatus,
    ProjectionConsumerId,
    ProjectionEventClassFilter,
    ProjectionEventFilter,
    ProjectionEventView,
    ProjectionRunner,
)
from dayu.host.tool_trace_signals import (
    CONTEXT_PRESSURE_SCHEMA_VERSION as _CONTEXT_PRESSURE_SCHEMA_VERSION,
    FAILURE_KIND_CONTEXT_COMPACTION_ATTEMPT_REJECTED
    as _FAILURE_KIND_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    FAILURE_KIND_CONTEXT_COMPACTION_FAILED
    as _FAILURE_KIND_CONTEXT_COMPACTION_FAILED,
    FAILURE_KIND_POLICY_BLOCKED as _FAILURE_KIND_POLICY_BLOCKED,
    FAILURE_KIND_PROVIDER_PROTOCOL_ERROR as _FAILURE_KIND_PROVIDER_PROTOCOL_ERROR,
    FAILURE_KIND_TOOL_CANCELLED as _FAILURE_KIND_TOOL_CANCELLED,
    FAILURE_KIND_TOOL_FAILED as _FAILURE_KIND_TOOL_FAILED,
    FAILURE_METADATA_ALLOWED_KINDS as _FAILURE_METADATA_ALLOWED_KINDS,
    FAILURE_METADATA_SCHEMA_VERSION as _FAILURE_METADATA_SCHEMA_VERSION,
    PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION
    as _PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION,
    PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE as _PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE,
    PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT
    as _PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT,
    TOOL_TIMING_DURATION_SOURCE_META as _TOOL_TIMING_DURATION_SOURCE_META,
    TOOL_TIMING_SCHEMA_VERSION as _TOOL_TIMING_SCHEMA_VERSION,
    TOOL_TIMING_STATUS_AVAILABLE as _TOOL_TIMING_STATUS_AVAILABLE,
    TOOL_TIMING_STATUS_MISSING_META as _TOOL_TIMING_STATUS_MISSING_META,
    TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS as _TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS,
)
from dayu.runtime.filelock import file_lock

TOOL_TRACE_CONSUMER_ID = ProjectionConsumerId("host.tool-trace")
"""Tool Trace projection consumer id。"""

DEFAULT_TOOL_TRACE_CATCHUP_BATCH_SIZE = 128
"""默认 Tool Trace projection 单批 catch-up 扫描上限。"""

_TOOL_TRACE_LINE_SCHEMA_VERSION = 1
_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_EVENT_TYPE_TOOL_CALL_GOVERNED = "TOOL_CALL_GOVERNED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_EVENT_TYPE_TOOL_AWAITING = "TOOL_AWAITING"
_EVENT_TYPE_RUN_WAITING = "RUN_WAITING"
_EVENT_TYPE_WAIT_LATE_RESULT_REJECTED = "WAIT_LATE_RESULT_REJECTED"
_EVENT_TYPE_CONTEXT_COMPACTION_REQUESTED = "CONTEXT_COMPACTION_REQUESTED"
_EVENT_TYPE_CONTEXT_COMPACTED = "CONTEXT_COMPACTED"
_EVENT_TYPE_CONTEXT_COMPACTION_FAILED = "CONTEXT_COMPACTION_FAILED"
_EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED = (
    "CONTEXT_COMPACTION_ATTEMPT_REJECTED"
)
_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_EVENT_TYPE_RUN_LOST = "RUN_LOST"
_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC = "ENGINE_EVENT_DIAGNOSTIC"
_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR = "PROVIDER_PROTOCOL_ERROR"
_EVENT_TYPE_USAGE_REPORTED = "USAGE_REPORTED"
_FIELD_ATTEMPT_ID = "attempt_id"
_FIELD_EXECUTION_ID = "execution_id"
_FIELD_TOOL_CALL_ID = "tool_call_id"
_FIELD_TOOL_NAME = "tool_name"
_FIELD_TOOL_SCHEMA_DIGEST = "tool_schema_digest"
_FIELD_TOOL_IDENTITY_DIGEST = "tool_identity_digest"
_FIELD_NORMALIZED_ARGUMENTS_DIGEST = "normalized_arguments_digest"
_FIELD_SEMANTIC_INPUT_DIGEST = "semantic_input_digest"
_FIELD_DUPLICATE_KEY = "duplicate_key"
_FIELD_DUPLICATE_DECISION = "duplicate_decision"
_FIELD_DUPLICATE_SCOPE = "duplicate_scope"
_FIELD_REUSE_PRIOR_EVENT_REFS = "reuse_prior_event_refs"
_FIELD_OUTCOME_DIGEST = "outcome_digest"
_FIELD_PAYLOAD_REF = "payload_ref"
_FIELD_PAYLOAD_DIGEST = "payload_digest"
_FIELD_POLICY_DECISION = "policy_decision"
_FIELD_TRUNCATION = "truncation"
_FIELD_DIAGNOSTIC_REFS = "diagnostic_refs"
_FIELD_PROVIDER_REQUEST_ID = "provider_request_id"
_FIELD_CLIENT_CORRELATION_ID = "client_correlation_id"
_FIELD_ENGINE_EVENT_REF = "engine_event_ref"
_FIELD_PROVIDER_ERROR_REF = "provider_error_ref"
_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"
_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_FIELD_CONTEXT_PRESSURE = "context_pressure"
_FIELD_TOOL_TIMING = "tool_timing"
_FIELD_FAILURE_METADATA = "failure_metadata"
_FIELD_PARTIAL_TOOL_CALL_SIGNAL = "partial_tool_call_signal"
_FIELD_OPERATION_CONTEXT = "operation_context"
_FIELD_OPERATION_ID = "operation_id"
_FIELD_TRIGGER_SOURCE = "trigger_source"
_FIELD_BUDGET_REASON = "budget_reason"
_FIELD_POLICY_REF = "policy_ref"
_FIELD_ESTIMATOR_DIGEST = "estimator_digest"
_FIELD_BUDGET_AFTER_COMPACT = "budget_after_compact"
_FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT = "budget_after_attempted_compact"
_FIELD_FALLBACK_ACTION = "fallback_action"
_FIELD_FALLBACK_POLICY_DECISION = "fallback_policy_decision"
_FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED = "retry_repair_budget_exhausted"
_FIELD_NEXT_POLICY_DECISION = "next_policy_decision"
_FIELD_FAILURE_CATEGORY = "failure_category"
_FIELD_REPAIRABLE = "repairable"
_FIELD_COLD_TRACE_REF = "cold_trace_ref"
_FIELD_COLD_TRACE_DIGEST = "cold_trace_digest"
_FIELD_LINE_DIGEST = "line_digest"
_FIELD_SCHEMA_VERSION = "schema_version"
_FIELD_EVENT_SEQUENCE = "event_sequence"
_FIELD_EVENT_ID = "event_id"
_FIELD_EVENT_TYPE = "event_type"
_FIELD_EVENT_CLASS = "event_class"
_FIELD_OCCURRED_AT = "occurred_at"
_FIELD_SESSION_ID = "session_id"
_FIELD_RUN_ID = "run_id"
_FIELD_OPERATION_CONTEXT_REFS = "operation_context_refs"
_FIELD_OPERATION_CONTEXT_DIGEST = "operation_context_digest"
_FIELD_TRACE_SUMMARY = "trace_summary"
_FIELD_SOURCE_PAYLOAD_REF = "source_payload_ref"
_FIELD_SOURCE_PAYLOAD_DIGEST = "source_payload_digest"
_FIELD_RUNNER_CALL_INDEX = "runner_call_index"
_FIELD_RUNNER_CALL_KIND = "runner_call_kind"
_FIELD_RUNNER_CALL_TRIGGER_REASON = "runner_call_trigger_reason"
_FIELD_MANIFEST_PAYLOAD_REF = "manifest_payload_ref"
_FIELD_MANIFEST_DIGEST = "manifest_digest"
_FIELD_MESSAGE_COUNT = "message_count"
_FIELD_ROLE_SEQUENCE_DIGEST = "role_sequence_digest"
_FIELD_INPUT_PROJECTION_DIGEST = "input_projection_digest"
_FIELD_PROJECTOR_METADATA_SUMMARY = "projector_metadata_summary"
_FIELD_VALIDATION_STATUS = "validation_status"
_FIELD_DIAGNOSTIC = "diagnostic"
_FIELD_REASON = "reason"
_FIELD_MISSING_ATOM_KIND = "missing_atom_kind"
_FIELD_MISSING_REF_KIND = "missing_ref_kind"
_FIELD_MISSING_REF = "missing_ref"
_FIELD_OBSERVED_COUNT = "observed_count"
_FIELD_EXPECTED_COUNT = "expected_count"
_FIELD_OBSERVED_DIGEST = "observed_digest"
_FIELD_EXPECTED_DIGEST = "expected_digest"
_FIELD_CONSUMER_BOUNDARY = "consumer_boundary"
_FIELD_PROJECTOR_METADATA_ID = "projector_metadata_id"
_FIELD_PROJECTOR_ID = "projector_id"
_FIELD_PROJECTOR_SCHEMA_VERSION = "projector_schema_version"
_FIELD_PROJECTOR_DIGEST = "projector_digest"
_FIELD_PURPOSE = "purpose"
_CONTEXT_PRESSURE_STATUS_COMPACTION_FAILED = "compaction_failed"
_CONTEXT_PRESSURE_STATUS_COMPACTION_ATTEMPT_REJECTED = (
    "compaction_attempt_rejected"
)
_PARTIAL_ARGUMENTS_SHA256_HEX_LENGTH = 64
_LOWER_HEX_CHARS = frozenset("0123456789abcdef")
_PRODUCER_MISSING_REF_KIND_RUNNER_CALL_PROJECTION_ARTIFACT = (
    "runner_call_projection_artifact"
)
_OPERATION_CONTEXT_REF_FIELDS: tuple[str, ...] = (
    "operation_name",
    "operation_kind",
    "business_domain",
    "business_object_type",
    "business_object_id",
    "scenario",
    "correlation_id",
)
_CANONICAL_EVENT_TYPES: tuple[str, ...] = (
    _EVENT_TYPE_TOOL_CALL_REQUESTED,
    _EVENT_TYPE_TOOL_CALL_GOVERNED,
    _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    _EVENT_TYPE_TOOL_AWAITING,
    _EVENT_TYPE_RUN_WAITING,
    _EVENT_TYPE_WAIT_LATE_RESULT_REJECTED,
    _EVENT_TYPE_CONTEXT_COMPACTION_REQUESTED,
    _EVENT_TYPE_CONTEXT_COMPACTED,
    _EVENT_TYPE_CONTEXT_COMPACTION_FAILED,
    _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
    _EVENT_TYPE_RUN_SUCCEEDED,
    _EVENT_TYPE_RUN_FAILED,
    _EVENT_TYPE_RUN_CANCELLED,
    _EVENT_TYPE_RUN_LOST,
)
_DIAGNOSTIC_EVENT_TYPES: tuple[str, ...] = (
    _EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC,
    _EVENT_TYPE_PROVIDER_PROTOCOL_ERROR,
)
_PROJECTION_SIGNAL_EVENT_TYPES: tuple[str, ...] = (_EVENT_TYPE_USAGE_REPORTED,)
_JSONL_LINE_SEPARATOR = "\n"
_LOCK_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class ToolTraceSinkOptions:
    """Tool Trace cold JSONL 输出选项。

    :param cold_jsonl_path: append-only cold tool trace JSONL 文件路径。
    :param create_parent_dirs: 写入前是否创建 JSONL 与 lock parent directory。
    :param lock_path: 可选相邻文件锁路径；``None`` 表示不加文件锁。
    :raises TypeError: 路径字段类型非法时抛出。
    :raises ValueError: 路径为空时抛出。
    """

    cold_jsonl_path: Path
    create_parent_dirs: bool = True
    lock_path: Path | None = None

    def __post_init__(self) -> None:
        """校验 Tool Trace sink options。

        :returns: ``None``。
        :raises TypeError: 路径或布尔配置类型非法时抛出。
        :raises ValueError: 路径为空时抛出。
        """

        _require_path(self.cold_jsonl_path, field_name="cold_jsonl_path")
        if not isinstance(self.create_parent_dirs, bool):
            raise TypeError("create_parent_dirs must be bool")
        if self.lock_path is not None:
            _require_path(self.lock_path, field_name="lock_path")


@dataclass(frozen=True, slots=True)
class ToolTraceColdLine:
    """单条 Tool Trace cold JSONL 行。

    :param fields: 包含 ``line_digest`` 的 canonical JSON object 字段。
    :param line_digest: 与 ``fields`` 中同名字段一致的行 digest。
    """

    fields: Mapping[str, JsonValue]
    line_digest: str

    def to_jsonl_text(self) -> str:
        """序列化为单行 JSONL 文本。

        :returns: canonical JSON 行文本，末尾包含换行符。
        :raises TypeError: 字段包含非 JSON 值时抛出。
        :raises ValueError: 字段包含非有限浮点数时抛出。
        """

        return canonical_json_dumps(self.fields) + _JSONL_LINE_SEPARATOR


@dataclass(frozen=True, slots=True)
class ToolTraceCatchupResult:
    """Tool Trace catch-up 汇总结果。

    :param consumer_id: Tool Trace consumer id。
    :param started_cursor: 本次 catch-up 开始 cursor。
    :param finished_cursor: 本次 catch-up 结束 cursor。
    :param events_scanned: 扫描 EventLog row 数。
    :param events_applied: 新写 hot/cold trace 数。
    :param duplicates: hot row 判定重复的 event 数。
    :param failures: projection runner 记录 failure 数。
    """

    consumer_id: ProjectionConsumerId
    started_cursor: int
    finished_cursor: int
    events_scanned: int
    events_applied: int
    duplicates: int
    failures: int


@dataclass(frozen=True, slots=True)
class _TraceSummarySignals:
    """Tool Trace summary 的可选结构化 signal 集合。

    :param context_pressure: 可选上下文压力 signal JSON object。
    :param tool_timing: 可选工具耗时 signal JSON object。
    :param failure_metadata: 可选失败元数据 signal JSON object。
    :param partial_tool_call_signal: 可选 partial tool-call signal JSON object。
    """

    context_pressure: Mapping[str, JsonValue] | None = None
    tool_timing: Mapping[str, JsonValue] | None = None
    failure_metadata: Mapping[str, JsonValue] | None = None
    partial_tool_call_signal: Mapping[str, JsonValue] | None = None

    def present_items(self) -> tuple[tuple[str, Mapping[str, JsonValue]], ...]:
        """返回非空 signal 字段和值。

        :returns: 按稳定字段顺序排列的 ``(field_name, signal_object)`` 元组。
        :raises: 无。
        """

        items: list[tuple[str, Mapping[str, JsonValue]]] = []
        if self.context_pressure is not None:
            items.append((_FIELD_CONTEXT_PRESSURE, self.context_pressure))
        if self.tool_timing is not None:
            items.append((_FIELD_TOOL_TIMING, self.tool_timing))
        if self.failure_metadata is not None:
            items.append((_FIELD_FAILURE_METADATA, self.failure_metadata))
        if self.partial_tool_call_signal is not None:
            items.append(
                (_FIELD_PARTIAL_TOOL_CALL_SIGNAL, self.partial_tool_call_signal)
            )
        return tuple(items)


@dataclass(frozen=True, slots=True)
class _ToolTraceExtract:
    """从白名单 EventLog payload 抽出的 Tool Trace 字段。"""

    tool_call_id: str | None
    tool_name: str | None
    provider_request_id: str | None
    client_correlation_id: str | None
    diagnostic_ref: str | None
    diagnostic_refs: tuple[str, ...]
    normalized_arguments_digest: str | None
    semantic_input_digest: str | None
    result_digest: str | None
    payload_ref: str | None
    payload_digest: str | None
    trace_summary: Mapping[str, JsonValue]


class ToolTraceProjectionConsumer:
    """Tool Trace hot / cold projection consumer。

    :param options: Tool Trace cold JSONL sink options。
    """

    def __init__(self, options: ToolTraceSinkOptions) -> None:
        """初始化 Tool Trace projection consumer。

        :param options: Tool Trace cold JSONL sink options。
        :returns: ``None``。
        :raises TypeError: ``options`` 不是 ``ToolTraceSinkOptions`` 时抛出。
        """

        if not isinstance(options, ToolTraceSinkOptions):
            raise TypeError("ToolTraceProjectionConsumer options must be ToolTraceSinkOptions")
        self._options = options

    @property
    def consumer_id(self) -> ProjectionConsumerId:
        """返回稳定 consumer id。

        :returns: ``host.tool-trace`` consumer id。
        :raises: 无。
        """

        return TOOL_TRACE_CONSUMER_ID

    @property
    def event_filter(self) -> ProjectionEventFilter:
        """返回 Tool Trace 消费的 EventLog 白名单 filter。

        :returns: canonical / diagnostic / projection signal 命名事件 filter。
        :raises: 无。
        """

        return ProjectionEventFilter(
            (
                ProjectionEventClassFilter(
                    event_class=EventClass.CANONICAL_FACT,
                    event_types=_CANONICAL_EVENT_TYPES,
                ),
                ProjectionEventClassFilter(
                    event_class=EventClass.DIAGNOSTIC,
                    event_types=_DIAGNOSTIC_EVENT_TYPES,
                ),
                ProjectionEventClassFilter(
                    event_class=EventClass.PROJECTION_SIGNAL,
                    event_types=_PROJECTION_SIGNAL_EVENT_TYPES,
                ),
            )
        )

    def apply_event(
        self, transaction: HostTransaction, event: ProjectionEventView
    ) -> ProjectionApplyResult:
        """把单个白名单 EventLog row 投影为 Tool Trace hot row 与 cold line。

        :param transaction: 当前 Host durable transaction。
        :param event: typed projection event view。
        :returns: projection apply result。
        :raises HostDurableError: source EventLog row 缺失或 payload 字段类型非法时抛出。
        :raises OSError: cold JSONL 文件写入失败时抛出，由 ProjectionRunner 记录 failure。
        """

        row = read_event_by_id(transaction, event.event_id)
        if row is None:
            raise HostDurableError("tool trace source EventLog row is missing")
        extracted = _extract_tool_trace(transaction, event)
        if extracted is None:
            return ProjectionApplyResult(
                ProjectionApplyStatus.SKIPPED,
                idempotency_key=event.event_id,
                detail_code=event.event_type,
            )
        now = _utc_now_text()
        cold_line = _build_cold_line(event=event, event_row=row, extracted=extracted)
        cold_trace_ref = _cold_trace_ref(event.event_id)
        hot_row = _build_hot_row(
            event=event,
            event_row=row,
            extracted=extracted,
            cold_trace_ref=cold_trace_ref,
            cold_trace_digest=cold_line.line_digest,
            now=now,
        )
        write_result = insert_tool_trace_hot_row_if_absent(transaction, hot_row)
        if write_result.status is ToolTraceHotRowWriteStatus.DUPLICATE:
            return ProjectionApplyResult(
                ProjectionApplyStatus.DUPLICATE,
                idempotency_key=event.event_id,
                detail_code=event.event_type,
            )
        self._append_line(cold_line)
        return ProjectionApplyResult(
            ProjectionApplyStatus.APPLIED,
            idempotency_key=event.event_id,
            detail_code=event.event_type,
        )

    def _append_line(self, line: ToolTraceColdLine) -> None:
        """向 Tool Trace cold JSONL 文件幂等追加单行。

        :param line: 已构造的 cold line。
        :returns: ``None``。
        :raises OSError: 创建目录或写文件失败时抛出。
        :raises RuntimeFileLockError: lock 获取或释放失败时由底层抛出。
        """

        if self._options.create_parent_dirs:
            self._options.cold_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        source_keys = (
            (_FIELD_EVENT_ID, _required_line_text(line, _FIELD_EVENT_ID)),
            (_FIELD_COLD_TRACE_REF, _required_line_text(line, _FIELD_COLD_TRACE_REF)),
        )
        if self._options.lock_path is None:
            _append_text_if_absent(
                self._options.cold_jsonl_path,
                line.to_jsonl_text(),
                line_digest=line.line_digest,
                source_keys=source_keys,
            )
            return
        with file_lock(
            self._options.lock_path,
            timeout_seconds=_LOCK_TIMEOUT_SECONDS,
            create_parent_dirs=self._options.create_parent_dirs,
        ):
            _append_text_if_absent(
                self._options.cold_jsonl_path,
                line.to_jsonl_text(),
                line_digest=line.line_digest,
                source_keys=source_keys,
            )


def catch_up_tool_trace_projection(
    transaction_runner: HostTransactionRunner,
    *,
    options: ToolTraceSinkOptions,
    batch_size: int = DEFAULT_TOOL_TRACE_CATCHUP_BATCH_SIZE,
    max_event_sequence: int | None = None,
) -> ToolTraceCatchupResult:
    """追平 Tool Trace projection。

    :param transaction_runner: Host durable transaction runner。
    :param options: Tool Trace sink options。
    :param batch_size: 每批最多扫描 EventLog row 数，必须为正数。
    :param max_event_sequence: 可选最大 EventLog sequence。
    :returns: Tool Trace catch-up 汇总结果。
    :raises HostDurableError: batch size 非法或 projection runner 初始化失败时抛出。
    """

    if batch_size <= 0:
        raise HostDurableError("tool trace catch-up batch_size must be positive")
    consumer = ToolTraceProjectionConsumer(options)
    runner = ProjectionRunner(transaction_runner, (consumer,))
    started_cursor: int | None = None
    finished_cursor = 0
    events_scanned = 0
    events_applied = 0
    duplicates = 0
    failures = 0
    while True:
        batch_result = runner.run_once(
            consumer.consumer_id,
            limit=batch_size,
            max_event_sequence=max_event_sequence,
        )
        if started_cursor is None:
            started_cursor = batch_result.started_cursor
        finished_cursor = batch_result.finished_cursor
        events_scanned += batch_result.events_scanned
        events_applied += batch_result.events_applied
        duplicates += batch_result.duplicate_events
        failures += batch_result.failures
        if batch_result.failures > 0 or batch_result.events_scanned < batch_size:
            break
    if started_cursor is None:
        started_cursor = finished_cursor
    return ToolTraceCatchupResult(
        consumer_id=consumer.consumer_id,
        started_cursor=started_cursor,
        finished_cursor=finished_cursor,
        events_scanned=events_scanned,
        events_applied=events_applied,
        duplicates=duplicates,
        failures=failures,
    )


def _extract_tool_trace(
    transaction: HostTransaction, event: ProjectionEventView
) -> _ToolTraceExtract | None:
    """从白名单 EventLog payload 抽取 Tool Trace 字段。

    :param transaction: 当前 Host transaction。
    :param event: typed projection event view。
    :returns: 可投影字段；当前 EventLog 字段不足以形成 trace 时返回 ``None``。
    :raises HostDurableError: 已命名字段存在但类型非法时抛出。
    """

    if event.event_class is EventClass.DIAGNOSTIC:
        return _extract_diagnostic_trace(event)
    if event.event_class is EventClass.PROJECTION_SIGNAL:
        return _extract_usage_trace(event)
    if event.event_class is EventClass.CANONICAL_FACT:
        return _extract_canonical_trace(transaction, event)
    return None


def _extract_canonical_trace(
    transaction: HostTransaction, event: ProjectionEventView
) -> _ToolTraceExtract | None:
    """从 canonical fact payload 抽取 Tool Trace 字段。

    :param transaction: 当前 Host transaction。
    :param event: typed projection event view。
    :returns: 可投影字段。
    :raises HostDurableError: 已命名字段存在但类型非法时抛出。
    """

    if event.event_type == _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED:
        return _extract_runner_call_trace(event)
    payload = event.payload
    diagnostic_refs = _diagnostic_refs(payload)
    provider_request_id = _optional_text(payload, _FIELD_PROVIDER_REQUEST_ID)
    client_correlation_id = _optional_text(payload, _FIELD_CLIENT_CORRELATION_ID)
    provider_error_ref = _optional_text(payload, _FIELD_PROVIDER_ERROR_REF)
    engine_event_ref = _optional_text(payload, _FIELD_ENGINE_EVENT_REF)
    tool_call_id = _optional_text(payload, _FIELD_TOOL_CALL_ID)
    tool_name = _optional_text(payload, _FIELD_TOOL_NAME)
    result_digest = _first_text(
        _optional_text(payload, _FIELD_OUTCOME_DIGEST),
        _optional_text(payload, _FIELD_PAYLOAD_DIGEST),
        _optional_text(payload, _FIELD_TERMINAL_SUMMARY_DIGEST),
    )
    payload_ref = _payload_ref_from_payload(payload)
    payload_digest = _first_text(
        _payload_digest_from_payload(payload),
        _optional_text(payload, _FIELD_PAYLOAD_DIGEST),
        event.payload_digest,
    )
    signals = _canonical_trace_summary_signals(transaction, event, payload)
    refs = tuple(
        ref
        for ref in (
            provider_error_ref,
            engine_event_ref,
            *diagnostic_refs,
        )
        if ref is not None
    )
    summary = _trace_summary(
        event=event,
        tool_schema_digest=_optional_text(payload, _FIELD_TOOL_SCHEMA_DIGEST),
        tool_identity_digest=_optional_text(payload, _FIELD_TOOL_IDENTITY_DIGEST),
        duplicate_key=_optional_text(payload, _FIELD_DUPLICATE_KEY),
        duplicate_decision=_optional_text(payload, _FIELD_DUPLICATE_DECISION),
        duplicate_scope=_json_value_or_none(payload, _FIELD_DUPLICATE_SCOPE),
        reuse_prior_event_refs=_json_value_or_none(
            payload, _FIELD_REUSE_PRIOR_EVENT_REFS
        ),
        truncation=_json_value_or_none(payload, _FIELD_TRUNCATION),
        diagnostic_refs=refs,
        provider_error_ref=provider_error_ref,
        engine_event_ref=engine_event_ref,
        terminal_summary_ref=_optional_text(payload, _FIELD_TERMINAL_SUMMARY_REF),
        terminal_summary_digest=_optional_text(
            payload, _FIELD_TERMINAL_SUMMARY_DIGEST
        ),
        policy_decision=_json_value_or_none(payload, _FIELD_POLICY_DECISION),
        client_correlation_id=client_correlation_id,
        signals=signals,
    )
    return _ToolTraceExtract(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        provider_request_id=provider_request_id,
        client_correlation_id=client_correlation_id,
        diagnostic_ref=refs[0] if len(refs) > 0 else None,
        diagnostic_refs=refs,
        normalized_arguments_digest=_optional_text(
            payload, _FIELD_NORMALIZED_ARGUMENTS_DIGEST
        ),
        semantic_input_digest=_optional_text(payload, _FIELD_SEMANTIC_INPUT_DIGEST),
        result_digest=result_digest,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        trace_summary=summary,
    )


def _extract_runner_call_trace(event: ProjectionEventView) -> _ToolTraceExtract:
    """从 RUNNER_CALL_INPUT_ASSEMBLED payload 抽取 runner-call trace signal。

    :param event: typed projection event view。
    :returns: Tool Trace extract。
    :raises HostDurableError: runner-call signal 字段类型非法时抛出。
    """

    payload = event.payload
    manifest_ref = _optional_text(payload, _FIELD_MANIFEST_PAYLOAD_REF)
    manifest_digest = _optional_text(payload, _FIELD_MANIFEST_DIGEST)
    diagnostic_refs = tuple(
        ref for ref in (manifest_ref, manifest_digest) if ref is not None
    )
    summary = _runner_call_trace_summary(event)
    return _ToolTraceExtract(
        tool_call_id=None,
        tool_name=None,
        provider_request_id=None,
        client_correlation_id=None,
        diagnostic_ref=manifest_ref,
        diagnostic_refs=diagnostic_refs,
        normalized_arguments_digest=None,
        semantic_input_digest=None,
        result_digest=manifest_digest,
        payload_ref=manifest_ref,
        payload_digest=manifest_digest,
        trace_summary=summary,
    )


def _runner_call_trace_summary(event: ProjectionEventView) -> Mapping[str, JsonValue]:
    """构造 Tool Trace runner-call signal summary。

    :param event: typed projection event view。
    :returns: runner-call signal summary。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    payload = event.payload
    return {
        "event_type": event.event_type,
        _FIELD_RUNNER_CALL_INDEX: _optional_int(payload, _FIELD_RUNNER_CALL_INDEX),
        _FIELD_RUNNER_CALL_KIND: _optional_text(payload, _FIELD_RUNNER_CALL_KIND),
        _FIELD_RUNNER_CALL_TRIGGER_REASON: _optional_text(
            payload, _FIELD_RUNNER_CALL_TRIGGER_REASON
        ),
        "iteration_id": _optional_text(payload, "iteration_id"),
        "manifest_ref": _optional_text(payload, _FIELD_MANIFEST_PAYLOAD_REF),
        _FIELD_MANIFEST_DIGEST: _optional_text(payload, _FIELD_MANIFEST_DIGEST),
        _FIELD_MESSAGE_COUNT: _optional_int(payload, _FIELD_MESSAGE_COUNT),
        _FIELD_ROLE_SEQUENCE_DIGEST: _optional_text(
            payload, _FIELD_ROLE_SEQUENCE_DIGEST
        ),
        _FIELD_INPUT_PROJECTION_DIGEST: _optional_text(
            payload, _FIELD_INPUT_PROJECTION_DIGEST
        ),
        _FIELD_PROJECTOR_METADATA_SUMMARY: list(
            _runner_call_projector_metadata_summary(payload)
        ),
        _FIELD_DIAGNOSTIC: _runner_call_diagnostic(payload),
    }


def _runner_call_diagnostic(
    payload: Mapping[str, JsonValue]
) -> Mapping[str, JsonValue]:
    """从 runner-call canonical payload 读取 typed diagnostic。

    :param payload: RUNNER_CALL_INPUT_ASSEMBLED hot payload。
    :returns: Tool Trace consumer boundary 下的 diagnostic summary。
    :raises HostDurableError: 非 complete signal 缺少 typed diagnostic 时抛出。
    """

    status = _runner_call_status(
        _required_text(payload, _FIELD_VALIDATION_STATUS),
        field_name=_FIELD_VALIDATION_STATUS,
    )
    diagnostic = payload.get(_FIELD_DIAGNOSTIC)
    if status is RunnerCallReconstructionStatus.COMPLETE:
        return {
            "status": status.value,
            _FIELD_REASON: None,
            _FIELD_MISSING_ATOM_KIND: None,
            _FIELD_MISSING_REF_KIND: None,
            _FIELD_MISSING_REF: None,
            _FIELD_OBSERVED_COUNT: None,
            _FIELD_EXPECTED_COUNT: None,
            _FIELD_OBSERVED_DIGEST: None,
            _FIELD_EXPECTED_DIGEST: None,
            _FIELD_CONSUMER_BOUNDARY: (
                RunnerCallReconstructionConsumerBoundary.TOOL_TRACE_QUERY.value
            ),
        }
    if not isinstance(diagnostic, Mapping):
        raise HostDurableError("runner-call diagnostic must be object")
    diagnostic_mapping = cast(Mapping[str, JsonValue], diagnostic)
    diagnostic_status = _runner_call_status(
        _required_text(diagnostic_mapping, "status"),
        field_name="diagnostic.status",
    )
    if diagnostic_status is not status:
        raise HostDurableError("runner-call diagnostic status mismatch")
    reason = _runner_call_reason(
        _required_text(diagnostic_mapping, _FIELD_REASON),
        field_name="diagnostic.reason",
    )
    return {
        "status": diagnostic_status.value,
        _FIELD_REASON: reason.value,
        _FIELD_MISSING_ATOM_KIND: _optional_runner_call_missing_atom_kind(
            diagnostic_mapping, _FIELD_MISSING_ATOM_KIND
        ),
        _FIELD_MISSING_REF_KIND: _optional_runner_call_missing_ref_kind(
            diagnostic_mapping, _FIELD_MISSING_REF_KIND
        ),
        _FIELD_MISSING_REF: _optional_text(diagnostic_mapping, _FIELD_MISSING_REF),
        _FIELD_OBSERVED_COUNT: _optional_int(
            diagnostic_mapping, _FIELD_OBSERVED_COUNT
        ),
        _FIELD_EXPECTED_COUNT: _optional_int(
            diagnostic_mapping, _FIELD_EXPECTED_COUNT
        ),
        _FIELD_OBSERVED_DIGEST: _optional_text(
            diagnostic_mapping, _FIELD_OBSERVED_DIGEST
        ),
        _FIELD_EXPECTED_DIGEST: _optional_text(
            diagnostic_mapping, _FIELD_EXPECTED_DIGEST
        ),
        _FIELD_CONSUMER_BOUNDARY: (
            RunnerCallReconstructionConsumerBoundary.TOOL_TRACE_QUERY.value
        ),
    }


def _runner_call_projector_metadata_summary(
    payload: Mapping[str, JsonValue],
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取并裁剪 runner-call projector metadata summary。

    :param payload: RUNNER_CALL_INPUT_ASSEMBLED hot payload。
    :returns: 只含 projector metadata 摘要字段的 JSON object 元组。
    :raises HostDurableError: projector metadata summary 类型非法时抛出。
    """

    value = payload.get(_FIELD_PROJECTOR_METADATA_SUMMARY)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise HostDurableError(
            "runner-call projector_metadata_summary must be JSON array"
        )
    items: list[Mapping[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise HostDurableError("runner-call projector metadata item must be object")
        item_mapping = cast(Mapping[str, JsonValue], item)
        items.append(
            {
                _FIELD_PROJECTOR_METADATA_ID: _required_text(
                    item_mapping, _FIELD_PROJECTOR_METADATA_ID
                ),
                _FIELD_PROJECTOR_ID: _required_text(
                    item_mapping, _FIELD_PROJECTOR_ID
                ),
                _FIELD_PROJECTOR_SCHEMA_VERSION: _required_text(
                    item_mapping, _FIELD_PROJECTOR_SCHEMA_VERSION
                ),
                _FIELD_PROJECTOR_DIGEST: _required_text(
                    item_mapping, _FIELD_PROJECTOR_DIGEST
                ),
                _FIELD_PURPOSE: _required_text(item_mapping, _FIELD_PURPOSE),
            }
        )
    return tuple(items)


def _runner_call_status(
    value: str, *, field_name: str
) -> RunnerCallReconstructionStatus:
    """校验 runner-call reconstruction status。

    :param value: status 文本。
    :param field_name: 错误消息字段名。
    :returns: status enum。
    :raises HostDurableError: status 不在封闭枚举内时抛出。
    """

    try:
        return RunnerCallReconstructionStatus(value)
    except ValueError as exc:
        raise HostDurableError(f"runner-call {field_name} is unsupported") from exc


def _runner_call_reason(
    value: str, *, field_name: str
) -> RunnerCallReconstructionDiagnosticReason:
    """校验 runner-call reconstruction diagnostic reason。

    :param value: reason 文本。
    :param field_name: 错误消息字段名。
    :returns: reason enum。
    :raises HostDurableError: reason 不在封闭枚举内时抛出。
    """

    try:
        return RunnerCallReconstructionDiagnosticReason(value)
    except ValueError as exc:
        raise HostDurableError(f"runner-call {field_name} is unsupported") from exc


def _optional_runner_call_missing_atom_kind(
    diagnostic: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取并校验 optional runner-call missing atom kind。

    :param diagnostic: diagnostic JSON object。
    :param field_name: 字段名。
    :returns: missing atom kind 文本或 ``None``。
    :raises HostDurableError: 字段值不在封闭枚举内时抛出。
    """

    value = _optional_text(diagnostic, field_name)
    if value is None:
        return None
    try:
        return RunnerCallReconstructionMissingAtomKind(value).value
    except ValueError as exc:
        raise HostDurableError(f"runner-call diagnostic.{field_name} is unsupported") from exc


def _optional_runner_call_missing_ref_kind(
    diagnostic: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取并校验 optional runner-call missing ref kind。

    :param diagnostic: diagnostic JSON object。
    :param field_name: 字段名。
    :returns: missing ref kind 文本或 ``None``。
    :raises HostDurableError: 字段值不在封闭枚举内时抛出。
    """

    value = _optional_text(diagnostic, field_name)
    if value is None:
        return None
    # Engine ingest 的 projection artifact producer 标签在 Tool Trace 查询边界收敛为通用 artifact ref kind。
    if value == _PRODUCER_MISSING_REF_KIND_RUNNER_CALL_PROJECTION_ARTIFACT:
        return RunnerCallReconstructionMissingRefKind.ARTIFACT_REF.value
    try:
        return RunnerCallReconstructionMissingRefKind(value).value
    except ValueError as exc:
        raise HostDurableError(f"runner-call diagnostic.{field_name} is unsupported") from exc


def _extract_diagnostic_trace(event: ProjectionEventView) -> _ToolTraceExtract | None:
    """从 diagnostic payload 抽取 Tool Trace 字段。

    :param event: typed projection event view。
    :returns: 可投影字段；不满足 diagnostic 白名单细分条件时返回 ``None``。
    :raises HostDurableError: 已命名字段存在但类型非法时抛出。
    """

    payload = event.payload
    provider_request_id = _optional_text(payload, _FIELD_PROVIDER_REQUEST_ID)
    client_correlation_id = _optional_text(payload, _FIELD_CLIENT_CORRELATION_ID)
    if (
        event.event_type == _EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC
        and provider_request_id is None
    ):
        return None
    raw_payload_ref = _optional_text(payload, "raw_payload_ref")
    raw_payload_digest = _optional_text(payload, "raw_payload_digest")
    diagnostic_refs = tuple(
        ref for ref in (raw_payload_ref, provider_request_id) if ref is not None
    )
    return _ToolTraceExtract(
        tool_call_id=_optional_text(payload, _FIELD_TOOL_CALL_ID),
        tool_name=_optional_text(payload, _FIELD_TOOL_NAME),
        provider_request_id=provider_request_id,
        client_correlation_id=client_correlation_id,
        diagnostic_ref=diagnostic_refs[0] if len(diagnostic_refs) > 0 else None,
        diagnostic_refs=diagnostic_refs,
        normalized_arguments_digest=None,
        semantic_input_digest=None,
        result_digest=raw_payload_digest,
        payload_ref=raw_payload_ref,
        payload_digest=raw_payload_digest,
        trace_summary=_trace_summary(
            event=event,
            tool_schema_digest=None,
            tool_identity_digest=None,
            duplicate_key=None,
            duplicate_decision=None,
            duplicate_scope=None,
            reuse_prior_event_refs=None,
            truncation=None,
            diagnostic_refs=diagnostic_refs,
            provider_error_ref=raw_payload_ref,
            engine_event_ref=None,
            terminal_summary_ref=None,
            terminal_summary_digest=None,
            policy_decision=None,
            client_correlation_id=client_correlation_id,
            signals=_trace_summary_signals(payload),
        ),
    )


def _extract_usage_trace(event: ProjectionEventView) -> _ToolTraceExtract | None:
    """从 usage projection signal payload 抽取 provider / usage refs。

    :param event: typed projection event view。
    :returns: 可投影字段。
    :raises HostDurableError: 已命名字段存在但类型非法时抛出。
    """

    payload = event.payload
    provider_request_id = _optional_text(payload, _FIELD_PROVIDER_REQUEST_ID)
    client_correlation_id = _optional_text(payload, _FIELD_CLIENT_CORRELATION_ID)
    usage_digest = _optional_text(payload, "usage_observation_digest")
    estimator_digest = _optional_text(payload, "estimator_digest")
    diagnostic_refs = tuple(
        ref for ref in (usage_digest, estimator_digest) if ref is not None
    )
    if provider_request_id is None and len(diagnostic_refs) == 0:
        return None
    return _ToolTraceExtract(
        tool_call_id=None,
        tool_name=None,
        provider_request_id=provider_request_id,
        client_correlation_id=client_correlation_id,
        diagnostic_ref=diagnostic_refs[0] if len(diagnostic_refs) > 0 else None,
        diagnostic_refs=diagnostic_refs,
        normalized_arguments_digest=None,
        semantic_input_digest=None,
        result_digest=usage_digest,
        payload_ref=None,
        payload_digest=None,
        trace_summary=_trace_summary(
            event=event,
            tool_schema_digest=None,
            tool_identity_digest=None,
            duplicate_key=None,
            duplicate_decision=None,
            duplicate_scope=None,
            reuse_prior_event_refs=None,
            truncation=None,
            diagnostic_refs=diagnostic_refs,
            provider_error_ref=None,
            engine_event_ref=None,
            terminal_summary_ref=None,
            terminal_summary_digest=None,
            policy_decision=None,
            client_correlation_id=client_correlation_id,
            signals=_trace_summary_signals(payload),
        ),
    )


def _build_hot_row(
    *,
    event: ProjectionEventView,
    event_row: EventLogRow,
    extracted: _ToolTraceExtract,
    cold_trace_ref: str,
    cold_trace_digest: str,
    now: str,
) -> ToolTraceHotRow:
    """构造 Tool Trace hot row。

    :param event: typed projection event view。
    :param event_row: source EventLog row。
    :param extracted: typed payload 抽取结果。
    :param cold_trace_ref: cold JSONL line 稳定引用。
    :param cold_trace_digest: cold JSONL line digest。
    :param now: 投影时间。
    :returns: Tool Trace hot row。
    :raises HostDurableError: event 与 row identity 不一致时抛出。
    """

    _validate_event_row_identity(event, event_row)
    return ToolTraceHotRow(
        trace_id=event.event_id,
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        event_type=event.event_type,
        event_class=event.event_class.value,
        session_id=event.session_id,
        run_id=event.run_id,
        attempt_id=event.attempt_id,
        execution_id=event.execution_id,
        tool_call_id=extracted.tool_call_id,
        tool_name=extracted.tool_name,
        provider_request_id=extracted.provider_request_id,
        diagnostic_ref=extracted.diagnostic_ref,
        normalized_arguments_digest=extracted.normalized_arguments_digest,
        semantic_input_digest=extracted.semantic_input_digest,
        result_digest=extracted.result_digest,
        payload_ref=event_row.payload_ref,
        payload_digest=event_row.payload_digest,
        policy_decision_json=event_row.policy_decision_json,
        trace_summary=extracted.trace_summary,
        cold_trace_ref=cold_trace_ref,
        cold_trace_digest=cold_trace_digest,
        projected_at=now,
        updated_at=now,
    )


def _build_cold_line(
    *,
    event: ProjectionEventView,
    event_row: EventLogRow,
    extracted: _ToolTraceExtract,
) -> ToolTraceColdLine:
    """构造 Tool Trace cold JSONL line。

    :param event: typed projection event view。
    :param event_row: source EventLog row。
    :param extracted: typed payload 抽取结果。
    :returns: cold JSONL line。
    :raises HostDurableError: event 与 row identity 不一致时抛出。
    """

    _validate_event_row_identity(event, event_row)
    operation_context = _optional_mapping(
        event.payload.get(_FIELD_OPERATION_CONTEXT),
        field_name=_FIELD_OPERATION_CONTEXT,
    )
    operation_context_refs = _operation_context_refs(operation_context)
    operation_context_digest = (
        sha256_digest_json(operation_context)
        if operation_context is not None
        else None
    )
    fields_without_digest: dict[str, JsonValue] = {
        _FIELD_SCHEMA_VERSION: _TOOL_TRACE_LINE_SCHEMA_VERSION,
        _FIELD_EVENT_SEQUENCE: event.event_sequence,
        _FIELD_EVENT_ID: event.event_id,
        _FIELD_EVENT_TYPE: event.event_type,
        _FIELD_EVENT_CLASS: event.event_class.value,
        _FIELD_OCCURRED_AT: event.occurred_at,
        _FIELD_SESSION_ID: event.session_id,
        _FIELD_RUN_ID: event.run_id,
        _FIELD_ATTEMPT_ID: event.attempt_id,
        _FIELD_EXECUTION_ID: event.execution_id,
        _FIELD_TOOL_CALL_ID: extracted.tool_call_id,
        _FIELD_TOOL_NAME: extracted.tool_name,
        _FIELD_PROVIDER_REQUEST_ID: extracted.provider_request_id,
        _FIELD_CLIENT_CORRELATION_ID: extracted.client_correlation_id,
        _FIELD_DIAGNOSTIC_REFS: list(extracted.diagnostic_refs),
        _FIELD_OPERATION_CONTEXT_REFS: list(operation_context_refs),
        _FIELD_OPERATION_CONTEXT_DIGEST: operation_context_digest,
        _FIELD_NORMALIZED_ARGUMENTS_DIGEST: extracted.normalized_arguments_digest,
        _FIELD_SEMANTIC_INPUT_DIGEST: extracted.semantic_input_digest,
        _FIELD_OUTCOME_DIGEST: extracted.result_digest,
        _FIELD_PAYLOAD_REF: extracted.payload_ref,
        _FIELD_PAYLOAD_DIGEST: extracted.payload_digest,
        _FIELD_SOURCE_PAYLOAD_REF: event_row.payload_ref,
        _FIELD_SOURCE_PAYLOAD_DIGEST: event_row.payload_digest,
        _FIELD_POLICY_DECISION: event_row.policy_decision_json,
        _FIELD_TRACE_SUMMARY: extracted.trace_summary,
    }
    line_digest = sha256_digest_json(fields_without_digest)
    fields: dict[str, JsonValue] = dict(fields_without_digest)
    fields[_FIELD_LINE_DIGEST] = line_digest
    fields[_FIELD_COLD_TRACE_REF] = _cold_trace_ref(event.event_id)
    fields[_FIELD_COLD_TRACE_DIGEST] = line_digest
    return ToolTraceColdLine(fields=fields, line_digest=line_digest)


def _trace_summary(
    *,
    event: ProjectionEventView,
    tool_schema_digest: str | None,
    tool_identity_digest: str | None,
    duplicate_key: str | None,
    duplicate_decision: str | None,
    duplicate_scope: JsonValue | None,
    reuse_prior_event_refs: JsonValue | None,
    truncation: JsonValue | None,
    diagnostic_refs: tuple[str, ...],
    provider_error_ref: str | None,
    engine_event_ref: str | None,
    terminal_summary_ref: str | None,
    terminal_summary_digest: str | None,
    policy_decision: JsonValue | None,
    client_correlation_id: str | None,
    signals: _TraceSummarySignals,
) -> Mapping[str, JsonValue]:
    """构造 hot trace summary JSON object。

    :param event: typed projection event view。
    :param tool_schema_digest: 可选工具 schema digest。
    :param tool_identity_digest: 可选工具身份 digest。
    :param duplicate_key: 可选 duplicate key。
    :param duplicate_decision: 可选 duplicate 决策。
    :param duplicate_scope: 可选 duplicate scope JSON。
    :param reuse_prior_event_refs: 可选 prior refs JSON。
    :param truncation: 可选截断 JSON。
    :param diagnostic_refs: 诊断 refs。
    :param provider_error_ref: 可选 provider error ref。
    :param engine_event_ref: 可选 engine event ref。
    :param terminal_summary_ref: 可选 terminal summary ref。
    :param terminal_summary_digest: 可选 terminal summary digest。
    :param policy_decision: 可选 policy decision JSON。
    :param client_correlation_id: 可选本地客户端关联 id。
    :param signals: 可选结构化 signal 集合。
    :returns: trace summary JSON object。
    :raises HostDurableError: operation context 字段类型非法时抛出。
    """

    operation_context = _optional_mapping(
        event.payload.get(_FIELD_OPERATION_CONTEXT),
        field_name=_FIELD_OPERATION_CONTEXT,
    )
    operation_context_refs = _operation_context_refs(operation_context)
    operation_context_digest = (
        sha256_digest_json(operation_context)
        if operation_context is not None
        else None
    )
    summary: dict[str, JsonValue] = {
        "event_type": event.event_type,
        _FIELD_TOOL_SCHEMA_DIGEST: tool_schema_digest,
        _FIELD_TOOL_IDENTITY_DIGEST: tool_identity_digest,
        _FIELD_DUPLICATE_KEY: duplicate_key,
        _FIELD_DUPLICATE_DECISION: duplicate_decision,
        _FIELD_DUPLICATE_SCOPE: duplicate_scope,
        _FIELD_REUSE_PRIOR_EVENT_REFS: reuse_prior_event_refs,
        _FIELD_TRUNCATION: truncation,
        _FIELD_DIAGNOSTIC_REFS: list(diagnostic_refs),
        _FIELD_PROVIDER_ERROR_REF: provider_error_ref,
        _FIELD_CLIENT_CORRELATION_ID: client_correlation_id,
        _FIELD_ENGINE_EVENT_REF: engine_event_ref,
        _FIELD_TERMINAL_SUMMARY_REF: terminal_summary_ref,
        _FIELD_TERMINAL_SUMMARY_DIGEST: terminal_summary_digest,
        _FIELD_POLICY_DECISION: policy_decision,
        _FIELD_OPERATION_CONTEXT_REFS: list(operation_context_refs),
        _FIELD_OPERATION_CONTEXT_DIGEST: operation_context_digest,
    }
    for field_name, signal_object in signals.present_items():
        summary[field_name] = signal_object
    return summary


def _canonical_trace_summary_signals(
    transaction: HostTransaction,
    event: ProjectionEventView,
    payload: Mapping[str, JsonValue],
) -> _TraceSummarySignals:
    """从 canonical fact payload 构造 Tool Trace signal 集合。

    :param transaction: 当前 Host transaction。
    :param event: typed projection event view。
    :param payload: canonical fact payload。
    :returns: optional summary signal carrier。
    :raises HostDurableError: 已命名字段类型非法时抛出。
    """

    copied = _trace_summary_signals(payload)
    if event.event_type == _EVENT_TYPE_CONTEXT_COMPACTION_FAILED:
        return _TraceSummarySignals(
            context_pressure=_context_compaction_failed_pressure(
                transaction, payload
            ),
            tool_timing=copied.tool_timing,
            failure_metadata=_context_compaction_failed_failure_metadata(payload),
            partial_tool_call_signal=copied.partial_tool_call_signal,
        )
    if event.event_type == _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED:
        return _TraceSummarySignals(
            context_pressure=_context_compaction_attempt_rejected_pressure(payload),
            tool_timing=copied.tool_timing,
            failure_metadata=_context_compaction_attempt_rejected_failure_metadata(
                payload
            ),
            partial_tool_call_signal=copied.partial_tool_call_signal,
        )
    return copied


def _context_compaction_failed_pressure(
    transaction: HostTransaction, payload: Mapping[str, JsonValue]
) -> Mapping[str, JsonValue]:
    """从 ``CONTEXT_COMPACTION_FAILED`` 既有 payload 派生上下文压力 signal。

    :param transaction: 当前 Host transaction。
    :param payload: failed canonical payload。
    :returns: context pressure JSON object。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    request_payload = _context_compaction_request_payload(transaction, payload)
    return {
        _FIELD_SCHEMA_VERSION: _CONTEXT_PRESSURE_SCHEMA_VERSION,
        "signal_source": _EVENT_TYPE_CONTEXT_COMPACTION_FAILED,
        "status": _CONTEXT_PRESSURE_STATUS_COMPACTION_FAILED,
        _FIELD_POLICY_REF: _optional_text(request_payload, _FIELD_POLICY_REF)
        if request_payload is not None
        else None,
        _FIELD_ESTIMATOR_DIGEST: _optional_text(
            request_payload, _FIELD_ESTIMATOR_DIGEST
        )
        if request_payload is not None
        else None,
        _FIELD_OPERATION_ID: _required_text(payload, _FIELD_OPERATION_ID),
        _FIELD_TRIGGER_SOURCE: _optional_text(request_payload, _FIELD_TRIGGER_SOURCE)
        if request_payload is not None
        else None,
        _FIELD_BUDGET_REASON: _optional_text(request_payload, _FIELD_BUDGET_REASON)
        if request_payload is not None
        else None,
        _FIELD_BUDGET_AFTER_COMPACT: None,
        _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: _optional_int(
            payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT
        ),
        _FIELD_FALLBACK_ACTION: _optional_text(payload, _FIELD_FALLBACK_ACTION),
        _FIELD_FALLBACK_POLICY_DECISION: _optional_text(
            payload, _FIELD_FALLBACK_POLICY_DECISION
        ),
        _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED: _required_bool(
            payload, _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED
        ),
    }


def _context_compaction_attempt_rejected_pressure(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """从 ``CONTEXT_COMPACTION_ATTEMPT_REJECTED`` payload 派生压力 signal。

    :param payload: attempt rejected canonical payload。
    :returns: context pressure JSON object。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    return {
        _FIELD_SCHEMA_VERSION: _CONTEXT_PRESSURE_SCHEMA_VERSION,
        "signal_source": _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        "status": _CONTEXT_PRESSURE_STATUS_COMPACTION_ATTEMPT_REJECTED,
        _FIELD_OPERATION_ID: _required_text(payload, _FIELD_OPERATION_ID),
        _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: _optional_int(
            payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT
        ),
        _FIELD_NEXT_POLICY_DECISION: _required_text(
            payload, _FIELD_NEXT_POLICY_DECISION
        ),
        _FIELD_FAILURE_CATEGORY: _required_text(payload, _FIELD_FAILURE_CATEGORY),
        _FIELD_REPAIRABLE: _required_bool(payload, _FIELD_REPAIRABLE),
    }


def _context_compaction_attempt_rejected_failure_metadata(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """从 attempt rejected compact payload 派生失败元数据 signal。

    :param payload: attempt rejected canonical payload。
    :returns: failure metadata JSON object。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    return {
        _FIELD_SCHEMA_VERSION: _FAILURE_METADATA_SCHEMA_VERSION,
        "signal_source": _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        "failure_kind": _FAILURE_KIND_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        _FIELD_FAILURE_CATEGORY: _required_text(payload, _FIELD_FAILURE_CATEGORY),
        _FIELD_REPAIRABLE: _required_bool(payload, _FIELD_REPAIRABLE),
        _FIELD_NEXT_POLICY_DECISION: _required_text(
            payload, _FIELD_NEXT_POLICY_DECISION
        ),
        _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: _optional_int(
            payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT
        ),
        _FIELD_DIAGNOSTIC_REFS: list(_diagnostic_refs(payload)),
    }


def _context_compaction_failed_failure_metadata(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """从 failed compact payload 派生失败元数据 signal。

    :param payload: failed canonical payload。
    :returns: failure metadata JSON object。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    return {
        _FIELD_SCHEMA_VERSION: _FAILURE_METADATA_SCHEMA_VERSION,
        "signal_source": _EVENT_TYPE_CONTEXT_COMPACTION_FAILED,
        "failure_kind": _FAILURE_KIND_CONTEXT_COMPACTION_FAILED,
        "failure_reason": _required_text(payload, "failure_reason"),
        "policy_decision": _required_text(payload, _FIELD_POLICY_DECISION),
        "retryable": _required_bool(payload, "retryable"),
        "attempt_count": _required_int(payload, "attempt_count"),
        _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED: _required_bool(
            payload, _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED
        ),
        _FIELD_FALLBACK_ACTION: _optional_text(payload, _FIELD_FALLBACK_ACTION),
        _FIELD_FALLBACK_POLICY_DECISION: _optional_text(
            payload, _FIELD_FALLBACK_POLICY_DECISION
        ),
        _FIELD_DIAGNOSTIC_REFS: list(_diagnostic_refs(payload)),
    }


def _context_compaction_request_payload(
    transaction: HostTransaction, payload: Mapping[str, JsonValue]
) -> Mapping[str, JsonValue] | None:
    """读取 compaction result payload 引用的 request fact payload。

    :param transaction: 当前 Host transaction。
    :param payload: failed/rejected canonical payload。
    :returns: request payload；找不到 request fact 时返回 ``None``。
    :raises HostDurableError: request fact payload 不是 JSON object 时抛出。
    """

    operation_id = _required_text(payload, _FIELD_OPERATION_ID)
    row = read_event_by_id(transaction, operation_id)
    if row is None:
        return None
    request_payload = cast(JsonValue, json.loads(row.payload_json))
    if not isinstance(request_payload, Mapping):
        raise HostDurableError("context compaction request payload must be JSON object")
    return cast(Mapping[str, JsonValue], request_payload)


def _trace_summary_signals(payload: Mapping[str, JsonValue]) -> _TraceSummarySignals:
    """从 payload 复制可选 Tool Trace signal 对象。

    :param payload: projection event payload。
    :returns: 四类 optional summary signal 的 grouped carrier。
    :raises HostDurableError: signal 字段存在但不是 JSON object 或 ``null`` 时抛出。
    """

    return _TraceSummarySignals(
        context_pressure=_optional_signal_object(payload, _FIELD_CONTEXT_PRESSURE),
        tool_timing=_optional_tool_timing_signal(payload),
        failure_metadata=_optional_failure_metadata_signal(payload),
        partial_tool_call_signal=_optional_partial_tool_call_signal(payload),
    )


def _optional_tool_timing_signal(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue] | None:
    """读取并校验可选工具耗时 signal。

    :param payload: projection event payload。
    :returns: tool_timing JSON object；字段缺失或为 ``null`` 时返回 ``None``。
    :raises HostDurableError: 字段类型、状态或 duration 非法时抛出。
    """

    signal = _optional_signal_object(payload, _FIELD_TOOL_TIMING)
    if signal is None:
        return None
    schema_version = _required_int(signal, _FIELD_SCHEMA_VERSION)
    if schema_version != _TOOL_TIMING_SCHEMA_VERSION:
        raise HostDurableError("tool trace tool_timing schema_version is unsupported")
    status = _required_text(signal, "status")
    if status == _TOOL_TIMING_STATUS_AVAILABLE:
        _required_text(signal, "started_at")
        _required_text(signal, "finished_at")
        duration_ms = _required_int(signal, "duration_ms")
        if duration_ms < 0:
            raise HostDurableError(
                "tool trace tool_timing duration_ms must be non-negative integer"
            )
        if _required_text(signal, "duration_source") != (
            _TOOL_TIMING_DURATION_SOURCE_META
        ):
            raise HostDurableError(
                "tool trace tool_timing duration_source is unsupported"
            )
        return signal
    if status == _TOOL_TIMING_STATUS_MISSING_META:
        for field_name in ("started_at", "finished_at", "duration_ms"):
            if signal.get(field_name) is not None:
                raise HostDurableError(
                    f"tool trace tool_timing {field_name} must be null"
                )
        if signal.get("duration_source") is not None:
            raise HostDurableError(
                "tool trace tool_timing duration_source must be null"
            )
        return signal
    raise HostDurableError("tool trace tool_timing status is unsupported")


def _optional_failure_metadata_signal(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue] | None:
    """读取并校验可选失败元数据 signal。

    :param payload: projection event payload。
    :returns: failure metadata JSON object；字段缺失或为 ``null`` 时返回 ``None``。
    :raises HostDurableError: 字段类型、schema、source、kind 或变体字段非法时抛出。
    """

    signal = _optional_signal_object(payload, _FIELD_FAILURE_METADATA)
    if signal is None:
        return None
    schema_version = _required_int(signal, _FIELD_SCHEMA_VERSION)
    if schema_version != _FAILURE_METADATA_SCHEMA_VERSION:
        raise HostDurableError(
            "tool trace failure_metadata schema_version is unsupported"
        )
    signal_source = _required_text(signal, "signal_source")
    failure_kind = _required_text(signal, "failure_kind")
    if failure_kind not in _FAILURE_METADATA_ALLOWED_KINDS:
        raise HostDurableError("tool trace failure_metadata failure_kind is unsupported")
    _validate_failure_metadata_variant(
        signal=signal,
        signal_source=signal_source,
        failure_kind=failure_kind,
    )
    return signal


def _validate_failure_metadata_variant(
    *,
    signal: Mapping[str, JsonValue],
    signal_source: str,
    failure_kind: str,
) -> None:
    """按 failure_kind 校验失败元数据闭集变体。

    :param signal: failure metadata JSON object。
    :param signal_source: 已读取的 signal source。
    :param failure_kind: 已读取的 failure kind。
    :returns: ``None``。
    :raises HostDurableError: source 或变体字段非法时抛出。
    """

    if failure_kind == _FAILURE_KIND_TOOL_FAILED:
        _require_failure_source(signal_source, _EVENT_TYPE_TOOL_RESULT_ACCEPTED)
        _require_text_field(signal, "error_code")
        _validate_bounded_text_field(signal, "repair_hint")
        _validate_metadata_diagnostic_refs(signal)
        return
    if failure_kind == _FAILURE_KIND_TOOL_CANCELLED:
        _require_failure_source(signal_source, _EVENT_TYPE_TOOL_RESULT_ACCEPTED)
        _require_text_field(signal, "cancel_reason")
        _validate_bounded_text_field(signal, "cancel_message")
        _validate_bounded_text_field(signal, "cancel_hint")
        _validate_metadata_diagnostic_refs(signal)
        return
    if failure_kind == _FAILURE_KIND_POLICY_BLOCKED:
        _require_failure_source(signal_source, _EVENT_TYPE_TOOL_RESULT_ACCEPTED)
        _require_text_field(signal, "policy_decision_kind")
        _require_text_field(signal, "policy_block_reason")
        _validate_metadata_diagnostic_refs(signal)
        return
    if failure_kind == _FAILURE_KIND_PROVIDER_PROTOCOL_ERROR:
        _require_failure_source(signal_source, _EVENT_TYPE_PROVIDER_PROTOCOL_ERROR)
        _require_text_field(signal, "provider_error_code")
        _validate_metadata_diagnostic_refs(signal)
        return
    if failure_kind == _FAILURE_KIND_CONTEXT_COMPACTION_ATTEMPT_REJECTED:
        _require_failure_source(
            signal_source, _EVENT_TYPE_CONTEXT_COMPACTION_ATTEMPT_REJECTED
        )
        _require_text_field(signal, _FIELD_FAILURE_CATEGORY)
        _required_bool(signal, _FIELD_REPAIRABLE)
        _require_text_field(signal, _FIELD_NEXT_POLICY_DECISION)
        _optional_int(signal, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT)
        _validate_metadata_diagnostic_refs(signal)
        return
    if failure_kind == _FAILURE_KIND_CONTEXT_COMPACTION_FAILED:
        _require_failure_source(signal_source, _EVENT_TYPE_CONTEXT_COMPACTION_FAILED)
        _require_text_field(signal, "failure_reason")
        _require_text_field(signal, _FIELD_POLICY_DECISION)
        _required_bool(signal, "retryable")
        _required_int(signal, "attempt_count")
        _required_bool(signal, _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED)
        _optional_text(signal, _FIELD_FALLBACK_ACTION)
        _optional_text(signal, _FIELD_FALLBACK_POLICY_DECISION)
        _validate_metadata_diagnostic_refs(signal)
        return
    raise HostDurableError("tool trace failure_metadata failure_kind is unsupported")


def _optional_partial_tool_call_signal(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue] | None:
    """读取并校验可选 partial tool-call signal。

    :param payload: projection event payload。
    :returns: partial tool-call signal JSON object；字段缺失或为 ``null`` 时返回
        ``None``。
    :raises HostDurableError: 字段类型、schema、source、状态或 summary 字段非法时抛出。
    """

    signal = _optional_signal_object(payload, _FIELD_PARTIAL_TOOL_CALL_SIGNAL)
    if signal is None:
        return None
    schema_version = _required_int(signal, _FIELD_SCHEMA_VERSION)
    if schema_version != _PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION:
        raise HostDurableError(
            "tool trace partial_tool_call_signal schema_version is unsupported"
        )
    signal_source = _required_text(signal, "signal_source")
    if signal_source != _EVENT_TYPE_PROVIDER_PROTOCOL_ERROR:
        raise HostDurableError("tool trace partial_tool_call_signal source mismatch")
    partial_count = _required_int(signal, "partial_tool_call_count")
    if partial_count < 0:
        raise HostDurableError("tool trace partial_tool_call_signal count is invalid")
    summary_status = _required_text(signal, "summary_status")
    _required_bool(signal, "raw_payload_present")
    partial_tool_calls = _required_partial_tool_call_summary_list(signal)
    if partial_count != len(partial_tool_calls):
        raise HostDurableError("tool trace partial_tool_call_signal count mismatch")
    if summary_status == _PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE:
        if partial_count != 0:
            raise HostDurableError(
                "tool trace partial_tool_call_signal none status has summaries"
            )
    elif summary_status == _PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT:
        if partial_count == 0:
            raise HostDurableError(
                "tool trace partial_tool_call_signal present status is empty"
            )
    else:
        raise HostDurableError("tool trace partial_tool_call_signal status unsupported")
    for summary in partial_tool_calls:
        _validate_partial_tool_call_summary(summary)
    return signal


def _required_partial_tool_call_summary_list(
    signal: Mapping[str, JsonValue],
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取 partial tool-call summary 数组。

    :param signal: partial tool-call signal JSON object。
    :returns: summary JSON object 元组。
    :raises HostDurableError: 字段缺失、不是数组或数组成员不是 JSON object 时抛出。
    """

    value = signal.get("partial_tool_calls")
    if not isinstance(value, list):
        raise HostDurableError(
            "tool trace partial_tool_call_signal partial_tool_calls must be JSON array"
        )
    summaries: list[Mapping[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise HostDurableError(
                "tool trace partial_tool_call_signal summary must be JSON object"
            )
        summaries.append(cast(Mapping[str, JsonValue], item))
    return tuple(summaries)


def _validate_partial_tool_call_summary(
    summary: Mapping[str, JsonValue],
) -> None:
    """校验单个 partial tool-call 有界摘要。

    :param summary: partial tool-call summary JSON object。
    :returns: ``None``。
    :raises HostDurableError: index、bounded 字段、arguments 字节数或 digest 标志非法时抛出。
    """

    tool_call_index = _required_int(summary, "tool_call_index")
    if tool_call_index < 0:
        raise HostDurableError(
            "tool trace partial_tool_call_signal tool_call_index is invalid"
        )
    _optional_text(summary, "tool_call_id")
    _optional_text(summary, "name_fragment")
    arguments_byte_size = _required_int(summary, "arguments_byte_size")
    if arguments_byte_size < 0:
        raise HostDurableError(
            "tool trace partial_tool_call_signal arguments_byte_size is invalid"
        )
    arguments_sha256 = _optional_text(summary, "arguments_sha256")
    arguments_present = _required_bool(summary, "arguments_present")
    if arguments_sha256 is None:
        if arguments_present:
            raise HostDurableError(
                "tool trace partial_tool_call_signal arguments_present mismatch"
            )
        return
    if not _is_bare_sha256_hex(arguments_sha256):
        raise HostDurableError(
            "tool trace partial_tool_call_signal arguments_sha256 is invalid"
        )
    if not arguments_present:
        raise HostDurableError(
            "tool trace partial_tool_call_signal arguments_present mismatch"
        )


def _is_bare_sha256_hex(value: str) -> bool:
    """判断字符串是否为 Engine partial arguments 使用的裸 sha256 hex digest。

    :param value: 待检查字符串。
    :returns: 64 位小写十六进制字符串时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if len(value) != _PARTIAL_ARGUMENTS_SHA256_HEX_LENGTH:
        return False
    return all(character in _LOWER_HEX_CHARS for character in value)


def _require_failure_source(actual: str, expected: str) -> None:
    """校验 failure metadata 的 signal source。

    :param actual: payload 中的 signal source。
    :param expected: 当前变体要求的 signal source。
    :returns: ``None``。
    :raises HostDurableError: signal source 不匹配时抛出。
    """

    if actual != expected:
        raise HostDurableError("tool trace failure_metadata signal_source mismatch")


def _require_text_field(
    payload: Mapping[str, JsonValue], field_name: str
) -> str:
    """读取 failure metadata 变体必填文本字段。

    :param payload: failure metadata JSON object。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    return _required_text(payload, field_name)


def _validate_bounded_text_field(
    signal: Mapping[str, JsonValue], field_name: str
) -> None:
    """校验 failure metadata bounded text 字段组合。

    :param signal: failure metadata JSON object。
    :param field_name: bounded text 字段名前缀。
    :returns: ``None``。
    :raises HostDurableError: bounded 文本、digest 或 truncated 字段组合非法时抛出。
    """

    value = signal.get(field_name)
    digest = signal.get(f"{field_name}_sha256")
    truncated = signal.get(f"{field_name}_truncated")
    if not isinstance(truncated, bool):
        raise HostDurableError(
            f"tool trace failure_metadata {field_name}_truncated must be bool"
        )
    if value is None:
        if digest is not None or truncated:
            raise HostDurableError(
                f"tool trace failure_metadata {field_name} null fields are invalid"
            )
        return
    if not isinstance(value, str):
        raise HostDurableError(
            f"tool trace failure_metadata {field_name} must be text or null"
        )
    if len(value) > _TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS:
        raise HostDurableError(
            f"tool trace failure_metadata {field_name} exceeds bounded limit"
        )
    if not isinstance(digest, str) or not is_sha256_digest(digest):
        raise HostDurableError(
            f"tool trace failure_metadata {field_name}_sha256 must be sha256 digest"
        )


def _validate_metadata_diagnostic_refs(signal: Mapping[str, JsonValue]) -> None:
    """校验 failure metadata diagnostic refs。

    :param signal: failure metadata JSON object。
    :returns: ``None``。
    :raises HostDurableError: refs 字段不是文本数组时抛出。
    """

    refs = signal.get(_FIELD_DIAGNOSTIC_REFS)
    if not isinstance(refs, list):
        raise HostDurableError(
            "tool trace failure_metadata diagnostic_refs must be JSON array"
        )
    for ref in refs:
        if not isinstance(ref, str) or ref.strip() == "":
            raise HostDurableError(
                "tool trace failure_metadata diagnostic_refs must contain text"
            )


def _optional_signal_object(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue] | None:
    """读取可选 Tool Trace signal JSON object。

    :param payload: projection event payload。
    :param field_name: signal 字段名。
    :returns: JSON object；字段缺失或为 ``null`` 时返回 ``None``。
    :raises HostDurableError: 字段存在但不是 JSON object 或 ``null`` 时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise HostDurableError(f"tool trace {field_name} must be JSON object or null")
    return cast(Mapping[str, JsonValue], value)


def _diagnostic_refs(payload: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """从 typed payload 的 ``diagnostic_refs`` 字段抽取 ref id。

    :param payload: projection event payload。
    :returns: 诊断 ref id 元组。
    :raises HostDurableError: 字段存在但结构非法时抛出。
    """

    value = payload.get(_FIELD_DIAGNOSTIC_REFS)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise HostDurableError("tool trace diagnostic_refs must be JSON array")
    refs: list[str] = []
    for item in value:
        if isinstance(item, str):
            if item.strip() != "":
                refs.append(item)
            continue
        if not isinstance(item, Mapping):
            raise HostDurableError("tool trace diagnostic_ref must be JSON object")
        item_mapping = cast(Mapping[str, JsonValue], item)
        ref_id = item_mapping.get("ref_id")
        if not isinstance(ref_id, str):
            raise HostDurableError("tool trace diagnostic_ref.ref_id must be text")
        if ref_id.strip() != "":
            refs.append(ref_id)
    return tuple(refs)


def _payload_ref_from_payload(payload: Mapping[str, JsonValue]) -> str | None:
    """从 payload 中抽取可选 result payload ref。

    :param payload: projection event payload。
    :returns: payload ref 或 ``None``。
    :raises HostDurableError: 字段存在但结构非法时抛出。
    """

    payload_ref_value = payload.get(_FIELD_PAYLOAD_REF)
    if payload_ref_value is None:
        return _optional_text(payload, _FIELD_TERMINAL_SUMMARY_REF)
    if not isinstance(payload_ref_value, Mapping):
        raise HostDurableError("tool trace payload_ref must be JSON object")
    payload_ref_mapping = cast(Mapping[str, JsonValue], payload_ref_value)
    return _optional_text(payload_ref_mapping, _FIELD_PAYLOAD_REF)


def _payload_digest_from_payload(payload: Mapping[str, JsonValue]) -> str | None:
    """从 payload 中抽取可选 result payload digest。

    :param payload: projection event payload。
    :returns: payload digest 或 ``None``。
    :raises HostDurableError: 字段存在但结构非法时抛出。
    """

    payload_ref_value = payload.get(_FIELD_PAYLOAD_REF)
    if payload_ref_value is None:
        return _optional_text(payload, _FIELD_TERMINAL_SUMMARY_DIGEST)
    if not isinstance(payload_ref_value, Mapping):
        raise HostDurableError("tool trace payload_ref must be JSON object")
    payload_ref_mapping = cast(Mapping[str, JsonValue], payload_ref_value)
    return _optional_text(payload_ref_mapping, _FIELD_PAYLOAD_DIGEST)


def _operation_context_refs(
    operation_context: Mapping[str, JsonValue] | None,
) -> tuple[str, ...]:
    """从 operation context 中抽取稳定文本 refs。

    :param operation_context: 操作上下文 JSON object；缺失时为 ``None``。
    :returns: 按字段顺序排列的非空文本 refs。
    :raises HostDurableError: 指定字段存在但不是文本时抛出。
    """

    if operation_context is None:
        return ()
    refs: list[str] = []
    for field_name in _OPERATION_CONTEXT_REF_FIELDS:
        value = operation_context.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise HostDurableError("tool trace operation_context ref field must be text")
        if value.strip() != "":
            refs.append(value)
    return tuple(refs)


def _optional_mapping(
    value: JsonValue | None, *, field_name: str
) -> Mapping[str, JsonValue] | None:
    """读取可选 JSON object 字段。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON object 或 ``None``。
    :raises HostDurableError: 字段存在但不是 JSON object 时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise HostDurableError(f"tool trace {field_name} must be JSON object")
    return cast(Mapping[str, JsonValue], value)


def _optional_text(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取 payload 中的可选非空文本。

    :param payload: projection event payload。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"tool trace payload field {field_name} must be text")


def _required_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取 payload 中的必填非空文本。

    :param payload: projection event payload。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"tool trace payload field {field_name} must be text")


def _optional_int(payload: Mapping[str, JsonValue], field_name: str) -> int | None:
    """读取 payload 中的可选非负整数。

    :param payload: projection event payload。
    :param field_name: 字段名。
    :returns: 整数值或 ``None``。
    :raises HostDurableError: 字段存在但不是非负整数时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(
            f"tool trace payload field {field_name} must be non-negative integer"
        )
    return value


def _required_int(payload: Mapping[str, JsonValue], field_name: str) -> int:
    """读取 payload 中的必填整数。

    :param payload: projection event payload。
    :param field_name: 字段名。
    :returns: 整数值。
    :raises HostDurableError: 字段缺失或不是整数时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise HostDurableError(
            f"tool trace payload field {field_name} must be integer"
        )
    return value


def _required_bool(payload: Mapping[str, JsonValue], field_name: str) -> bool:
    """读取 payload 中的必填 bool。

    :param payload: projection event payload。
    :param field_name: 字段名。
    :returns: bool 值。
    :raises HostDurableError: 字段缺失或不是 bool 时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool):
        return value
    raise HostDurableError(f"tool trace payload field {field_name} must be bool")


def _json_value_or_none(payload: Mapping[str, JsonValue], field_name: str) -> JsonValue:
    """读取 payload 中的可选 JSON 值。

    :param payload: projection event payload。
    :param field_name: 字段名。
    :returns: JSON 值；缺失时为 ``None``。
    """

    return payload.get(field_name)


def _first_text(*values: str | None) -> str | None:
    """返回第一个非空文本。

    :param values: 候选文本。
    :returns: 第一个非空文本；均为空时返回 ``None``。
    """

    for value in values:
        if value is not None:
            return value
    return None


def _validate_event_row_identity(
    event: ProjectionEventView, event_row: EventLogRow
) -> None:
    """校验 projection event 与 EventLog row 身份一致。

    :param event: typed projection event view。
    :param event_row: source EventLog row。
    :returns: ``None``。
    :raises HostDurableError: 身份不一致时抛出。
    """

    if (
        event_row.event_id != event.event_id
        or event_row.event_sequence != event.event_sequence
    ):
        raise HostDurableError("tool trace EventLog row identity mismatch")


def _cold_trace_ref(event_id: str) -> str:
    """构造 cold JSONL line 稳定引用。

    :param event_id: source EventLog id。
    :returns: cold trace ref。
    """

    return f"tool-trace-cold:{event_id}"


def _append_text_if_absent(
    path: Path,
    text: str,
    *,
    line_digest: str,
    source_keys: tuple[tuple[str, str], ...],
) -> None:
    """目标 JSONL 不含同一 digest 或 source key 冲突时追加文本。

    :param path: 目标 JSONL 路径。
    :param text: 待追加文本。
    :param line_digest: 当前行 digest。
    :param source_keys: 当前行的稳定 source key 集合。
    :returns: ``None``。
    :raises HostDurableError: 已存在相同 source key 但 digest 不同时抛出。
    :raises OSError: 文件打开或写入失败时抛出。
    """

    if _jsonl_contains_line(path, line_digest=line_digest, source_keys=source_keys):
        return
    _append_text(path, text)


def _append_text(path: Path, text: str) -> None:
    """向文件追加 UTF-8 文本。

    :param path: 目标文件路径。
    :param text: 待追加文本。
    :returns: ``None``。
    :raises OSError: 文件打开或写入失败时抛出。
    """

    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()


def _jsonl_contains_line(
    path: Path,
    *,
    line_digest: str,
    source_keys: tuple[tuple[str, str], ...],
) -> bool:
    """检查 JSONL 中是否已有同一 line digest。

    :param path: JSONL 文件路径。
    :param line_digest: 当前行 digest。
    :param source_keys: 当前行的稳定 source key 集合。
    :returns: 已存在同一 line digest 时返回 ``True``。
    :raises HostDurableError: 已存在相同 source key 但 digest 不同时抛出。
    :raises OSError: 读取文件失败时抛出。
    """

    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            existing = _json_object_from_jsonl_line(raw_line)
            if existing is None:
                continue
            existing_digest = existing.get(_FIELD_LINE_DIGEST)
            if existing_digest == line_digest:
                return True
            for field_name, field_value in source_keys:
                if existing.get(field_name) == field_value:
                    raise HostDurableError(
                        "tool trace JSONL source key conflicts with line digest"
                    )
    return False


def _json_object_from_jsonl_line(raw_line: str) -> Mapping[str, JsonValue] | None:
    """把单行 JSONL 解析为 JSON object。

    :param raw_line: 原始 JSONL 行。
    :returns: JSON object；空行、非法 JSON 或非 object 行返回 ``None``。
    :raises: 无。
    """

    stripped = raw_line.strip()
    if stripped == "":
        return None
    try:
        value = cast(JsonValue, json.loads(stripped))
    except json.JSONDecodeError:
        return None
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, JsonValue], value)


def _required_line_text(line: ToolTraceColdLine, field_name: str) -> str:
    """读取 Tool Trace cold line 中的必填文本字段。

    :param line: Tool Trace cold JSONL 行。
    :param field_name: 字段名。
    :returns: 非空文本字段值。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = line.fields.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"tool trace cold line field {field_name} must be text")


def _require_path(path: Path, *, field_name: str) -> None:
    """校验路径字段。

    :param path: 待校验路径。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 路径类型非法时抛出。
    :raises ValueError: 路径为空或没有文件名时抛出。
    """

    if not isinstance(path, Path):
        raise TypeError(f"{field_name} must be Path")
    if str(path).strip() == "" or path.name.strip() == "":
        raise ValueError(f"{field_name} must include filename")


def _utc_now_text() -> str:
    """生成当前 UTC timestamp 文本。

    :returns: 固定格式 UTC timestamp 文本。
    """

    return format_utc_timestamp(datetime.now(UTC))


__all__ = [
    "DEFAULT_TOOL_TRACE_CATCHUP_BATCH_SIZE",
    "TOOL_TRACE_CONSUMER_ID",
    "ToolTraceCatchupResult",
    "ToolTraceColdLine",
    "ToolTraceProjectionConsumer",
    "ToolTraceSinkOptions",
    "catch_up_tool_trace_projection",
]
