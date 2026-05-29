"""Host Tool Trace hot / cold projection sink。

本模块实现 ``ToolTraceProjectionConsumer``，只消费 committed EventLog 的命名
白名单事件，写入 hot SQLite projection 与 cold append-only JSONL。Tool Trace
只用于诊断查询，不参与 Host durable truth、恢复、resume、memory 或 Run 状态迁移。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    sha256_digest_json,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, read_event_by_id
from dayu.host.durable.tool_trace import (
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
_FIELD_REUSE_PRIOR_EVENT_REFS = "reuse_prior_event_refs"
_FIELD_OUTCOME_DIGEST = "outcome_digest"
_FIELD_PAYLOAD_REF = "payload_ref"
_FIELD_PAYLOAD_DIGEST = "payload_digest"
_FIELD_POLICY_DECISION = "policy_decision"
_FIELD_TRUNCATION = "truncation"
_FIELD_DIAGNOSTIC_REFS = "diagnostic_refs"
_FIELD_PROVIDER_REQUEST_ID = "provider_request_id"
_FIELD_ENGINE_EVENT_REF = "engine_event_ref"
_FIELD_PROVIDER_ERROR_REF = "provider_error_ref"
_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"
_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_FIELD_OPERATION_CONTEXT = "operation_context"
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
_FIELD_PAYLOAD = "payload"
_FIELD_SOURCE_PAYLOAD_REF = "source_payload_ref"
_FIELD_SOURCE_PAYLOAD_DIGEST = "source_payload_digest"
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
class _ToolTraceExtract:
    """从白名单 EventLog payload 抽出的 Tool Trace 字段。"""

    tool_call_id: str | None
    tool_name: str | None
    provider_request_id: str | None
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
        extracted = _extract_tool_trace(event)
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
        """向 Tool Trace cold JSONL 文件追加单行。

        :param line: 已构造的 cold line。
        :returns: ``None``。
        :raises OSError: 创建目录或写文件失败时抛出。
        :raises RuntimeFileLockError: lock 获取或释放失败时由底层抛出。
        """

        if self._options.create_parent_dirs:
            self._options.cold_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        if self._options.lock_path is None:
            _append_text(self._options.cold_jsonl_path, line.to_jsonl_text())
            return
        with file_lock(
            self._options.lock_path,
            timeout_seconds=_LOCK_TIMEOUT_SECONDS,
            create_parent_dirs=self._options.create_parent_dirs,
        ):
            _append_text(self._options.cold_jsonl_path, line.to_jsonl_text())


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


def _extract_tool_trace(event: ProjectionEventView) -> _ToolTraceExtract | None:
    """从白名单 EventLog payload 抽取 Tool Trace 字段。

    :param event: typed projection event view。
    :returns: 可投影字段；当前 EventLog 字段不足以形成 trace 时返回 ``None``。
    :raises HostDurableError: 已命名字段存在但类型非法时抛出。
    """

    if event.event_class is EventClass.DIAGNOSTIC:
        return _extract_diagnostic_trace(event)
    if event.event_class is EventClass.PROJECTION_SIGNAL:
        return _extract_usage_trace(event)
    if event.event_class is EventClass.CANONICAL_FACT:
        return _extract_canonical_trace(event)
    return None


def _extract_canonical_trace(event: ProjectionEventView) -> _ToolTraceExtract | None:
    """从 canonical fact payload 抽取 Tool Trace 字段。

    :param event: typed projection event view。
    :returns: 可投影字段。
    :raises HostDurableError: 已命名字段存在但类型非法时抛出。
    """

    payload = event.payload
    diagnostic_refs = _diagnostic_refs(payload)
    provider_request_id = _optional_text(payload, _FIELD_PROVIDER_REQUEST_ID)
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
    )
    return _ToolTraceExtract(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        provider_request_id=provider_request_id,
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


def _extract_diagnostic_trace(event: ProjectionEventView) -> _ToolTraceExtract | None:
    """从 diagnostic payload 抽取 Tool Trace 字段。

    :param event: typed projection event view。
    :returns: 可投影字段；不满足 diagnostic 白名单细分条件时返回 ``None``。
    :raises HostDurableError: 已命名字段存在但类型非法时抛出。
    """

    payload = event.payload
    provider_request_id = _optional_text(payload, _FIELD_PROVIDER_REQUEST_ID)
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
            reuse_prior_event_refs=None,
            truncation=None,
            diagnostic_refs=diagnostic_refs,
            provider_error_ref=raw_payload_ref,
            engine_event_ref=None,
            terminal_summary_ref=None,
            terminal_summary_digest=None,
            policy_decision=None,
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
            reuse_prior_event_refs=None,
            truncation=None,
            diagnostic_refs=diagnostic_refs,
            provider_error_ref=None,
            engine_event_ref=None,
            terminal_summary_ref=None,
            terminal_summary_digest=None,
            policy_decision=None,
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
        _FIELD_PAYLOAD: event.payload,
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
    reuse_prior_event_refs: JsonValue | None,
    truncation: JsonValue | None,
    diagnostic_refs: tuple[str, ...],
    provider_error_ref: str | None,
    engine_event_ref: str | None,
    terminal_summary_ref: str | None,
    terminal_summary_digest: str | None,
    policy_decision: JsonValue | None,
) -> Mapping[str, JsonValue]:
    """构造 hot trace summary JSON object。

    :param event: typed projection event view。
    :param tool_schema_digest: 可选工具 schema digest。
    :param tool_identity_digest: 可选工具身份 digest。
    :param duplicate_key: 可选 duplicate key。
    :param duplicate_decision: 可选 duplicate 决策。
    :param reuse_prior_event_refs: 可选 prior refs JSON。
    :param truncation: 可选截断 JSON。
    :param diagnostic_refs: 诊断 refs。
    :param provider_error_ref: 可选 provider error ref。
    :param engine_event_ref: 可选 engine event ref。
    :param terminal_summary_ref: 可选 terminal summary ref。
    :param terminal_summary_digest: 可选 terminal summary digest。
    :param policy_decision: 可选 policy decision JSON。
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
    return {
        "event_type": event.event_type,
        _FIELD_TOOL_SCHEMA_DIGEST: tool_schema_digest,
        _FIELD_TOOL_IDENTITY_DIGEST: tool_identity_digest,
        _FIELD_DUPLICATE_KEY: duplicate_key,
        _FIELD_DUPLICATE_DECISION: duplicate_decision,
        _FIELD_REUSE_PRIOR_EVENT_REFS: reuse_prior_event_refs,
        _FIELD_TRUNCATION: truncation,
        _FIELD_DIAGNOSTIC_REFS: list(diagnostic_refs),
        _FIELD_PROVIDER_ERROR_REF: provider_error_ref,
        _FIELD_ENGINE_EVENT_REF: engine_event_ref,
        _FIELD_TERMINAL_SUMMARY_REF: terminal_summary_ref,
        _FIELD_TERMINAL_SUMMARY_DIGEST: terminal_summary_digest,
        _FIELD_POLICY_DECISION: policy_decision,
        _FIELD_OPERATION_CONTEXT_REFS: list(operation_context_refs),
        _FIELD_OPERATION_CONTEXT_DIGEST: operation_context_digest,
    }


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
