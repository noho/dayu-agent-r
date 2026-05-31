"""Host append-only audit JSONL projection sink。

本模块实现 ``LogAuditSink``，只消费 committed EventLog canonical facts 并写入
append-only JSONL audit artifact。Audit 是 projection / sink，不是 Host
truth；失败只应通过 projection runner 的 failure path 暴露。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.audit import (
    AuditSinkMarkerWriteStatus,
    insert_audit_sink_marker_if_absent,
    read_audit_sink_marker,
)
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    sha256_digest_json,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, read_event_by_id
from dayu.host.durable.purge import (
    PurgeTombstoneRow,
    build_purge_attempt_ref,
    build_purge_tombstone_digest,
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

LOG_AUDIT_SINK_CONSUMER_ID = ProjectionConsumerId("host.audit-log-jsonl")
"""LogAuditSink projection consumer id。"""

DEFAULT_LOG_AUDIT_CATCHUP_BATCH_SIZE = 128
"""默认 audit projection 单批 catch-up 扫描上限。"""

_AUDIT_LINE_SCHEMA_VERSION = 1
_AUDIT_FIELD_SCHEMA_VERSION = "schema_version"
_AUDIT_FIELD_EVENT_SEQUENCE = "event_sequence"
_AUDIT_FIELD_EVENT_ID = "event_id"
_AUDIT_FIELD_EVENT_TYPE = "event_type"
_AUDIT_FIELD_EVENT_CLASS = "event_class"
_AUDIT_FIELD_OCCURRED_AT = "occurred_at"
_AUDIT_FIELD_SESSION_ID = "session_id"
_AUDIT_FIELD_RUN_ID = "run_id"
_AUDIT_FIELD_ATTEMPT_ID = "attempt_id"
_AUDIT_FIELD_EXECUTION_ID = "execution_id"
_AUDIT_FIELD_ACTOR = "actor"
_AUDIT_FIELD_PRINCIPAL = "principal"
_AUDIT_FIELD_SOURCE = "source"
_AUDIT_FIELD_CLIENT_REQUEST_ID = "client_request_id"
_AUDIT_FIELD_OPERATION_CONTEXT_REFS = "operation_context_refs"
_AUDIT_FIELD_OPERATION_CONTEXT_DIGEST = "operation_context_digest"
_AUDIT_FIELD_POLICY_DECISION_REF = "policy_decision_ref"
_AUDIT_FIELD_POLICY_DECISION_SUMMARY = "policy_decision_summary"
_AUDIT_FIELD_REASON = "reason"
_AUDIT_FIELD_PAYLOAD_REF = "payload_ref"
_AUDIT_FIELD_PAYLOAD_DIGEST = "payload_digest"
_AUDIT_FIELD_LINE_DIGEST = "line_digest"
_AUDIT_FIELD_LINE_KIND = "line_kind"
_AUDIT_FIELD_PURGE_ATTEMPT_REF = "purge_attempt_ref"
_AUDIT_FIELD_PLANNED_PURGE_TOMBSTONE_REF = "planned_purge_tombstone_ref"
_AUDIT_FIELD_PURGE_TOMBSTONE_REF = "purge_tombstone_ref"
_AUDIT_FIELD_PURGE_TOMBSTONE_DIGEST = "purge_tombstone_digest"
_AUDIT_FIELD_AUDIT_RECORD_REF = "audit_record_ref"
_AUDIT_FIELD_STARTED_AUDIT_RECORD_REF = "started_audit_record_ref"
_AUDIT_FIELD_STARTED_AUDIT_RECORD_DIGEST = "started_audit_record_digest"
_AUDIT_FIELD_SEMANTIC_REQUEST_DIGEST = "semantic_request_digest"
_AUDIT_FIELD_DELETED_COUNTS_DIGEST = "deleted_counts_digest"
_AUDIT_FIELD_PRECONDITION_DIGEST = "precondition_digest"
_AUDIT_FIELD_DELETED_REFS_DIGEST = "deleted_refs_digest"
_AUDIT_FIELD_REQUEST_CONTEXT = "request_context"
_AUDIT_FIELD_SOURCE_EVENTLOG_FACTS_PURGED = "source_eventlog_facts_purged"
_AUDIT_FIELD_DELETED_COUNTS = "deleted_counts"
_AUDIT_FIELD_FAILURE_STAGE = "failure_stage"
_AUDIT_FIELD_FAILURE_MESSAGE = "failure_message"
_AUDIT_LINE_KIND_PURGE_STARTED = "purge_started"
_AUDIT_LINE_KIND_PURGE_COMPLETED = "purge_completed"
_AUDIT_LINE_KIND_PURGE_FAILED = "purge_failed"
_AUDIT_RECORD_REF_PREFIX = "audit-jsonl:"
_AUDIT_ARTIFACT_DIRECTORY_NAME = "audit"
_AUDIT_JSONL_FILE_NAME = "host-audit.jsonl"
_AUDIT_LOCK_FILE_SUFFIX = ".lock"
_PAYLOAD_FIELD_OPERATION_CONTEXT = "operation_context"
_PAYLOAD_FIELD_AUTHORIZATION_CLAIMS = "authorization_claims"
_PAYLOAD_FIELD_POLICY_DECISION_REF = "policy_decision_ref"
_PAYLOAD_FIELD_POLICY_DECISION_SUMMARY = "policy_decision_summary"
_PAYLOAD_FIELD_REASON = "reason"
_OPERATION_CONTEXT_REF_FIELDS: tuple[str, ...] = (
    "operation_name",
    "operation_kind",
    "business_domain",
    "business_object_type",
    "business_object_id",
    "scenario",
    "correlation_id",
)
_PRINCIPAL_CLAIM_NAMES: frozenset[str] = frozenset(("principal", "subject", "user"))
_JSONL_LINE_SEPARATOR = "\n"
_LOCK_TIMEOUT_SECONDS = 5.0
_PURGE_FAILURE_MESSAGE_MAX_CHARS = 512


@dataclass(frozen=True, slots=True)
class LogAuditSinkOptions:
    """LogAuditSink JSONL 输出选项。

    :param audit_jsonl_path: append-only audit JSONL 文件路径。
    :param create_parent_dirs: 写入前是否创建 JSONL 与 lock parent directory。
    :param lock_path: 可选相邻文件锁路径；``None`` 表示不加文件锁。
    :raises TypeError: 路径字段类型非法时抛出。
    :raises ValueError: 路径为空时抛出。
    """

    audit_jsonl_path: Path
    create_parent_dirs: bool = True
    lock_path: Path | None = None

    def __post_init__(self) -> None:
        """校验 audit sink options。

        :returns: ``None``。
        :raises TypeError: 路径或布尔配置类型非法时抛出。
        :raises ValueError: 路径为空时抛出。
        """

        _require_path(self.audit_jsonl_path, field_name="audit_jsonl_path")
        if not isinstance(self.create_parent_dirs, bool):
            raise TypeError("create_parent_dirs must be bool")
        if self.lock_path is not None:
            _require_path(self.lock_path, field_name="lock_path")


@dataclass(frozen=True, slots=True)
class AuditJsonLine:
    """单条 audit JSONL 行。

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
class PurgeStartedAuditRecordRequest:
    """purge_started audit record 构造请求。

    :param tombstone_id: 本次 purge 的 deterministic tombstone id。
    :param session_id: 被 purge 的 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge 请求 semantic digest。
    :param actor: 发起方标识。
    :param source: 来源标识。
    :param operation_context_digest: 操作上下文 digest。
    :param operation_context_refs: 操作上下文 refs JSON object。
    :param reason: purge 原因。
    :param request_context: 请求上下文 refs JSON object。
    """

    tombstone_id: str
    session_id: str
    client_request_id: str
    semantic_request_digest: str
    actor: str | None
    source: str | None
    operation_context_digest: str | None
    operation_context_refs: Mapping[str, JsonValue]
    reason: str
    request_context: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class PurgeCompletedAuditRecordRequest:
    """purge_completed audit record 构造请求。

    :param tombstone: 已提交的 purge tombstone row。
    :param semantic_request_digest: purge 请求 semantic digest。
    """

    tombstone: PurgeTombstoneRow
    semantic_request_digest: str


@dataclass(frozen=True, slots=True)
class PurgeFailedAuditRecordRequest:
    """purge_failed audit record 构造请求。

    :param tombstone_id: 本次 purge 的 deterministic tombstone id。
    :param session_id: 被 purge 的 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge 请求 semantic digest。
    :param actor: 发起方标识。
    :param source: 来源标识。
    :param operation_context_digest: 操作上下文 digest。
    :param operation_context_refs: 操作上下文 refs JSON object。
    :param reason: purge 原因。
    :param request_context: 请求上下文 refs JSON object。
    :param failure_stage: 失败阶段稳定字符串。
    :param failure_message: 有界诊断文本。
    """

    tombstone_id: str
    session_id: str
    client_request_id: str
    semantic_request_digest: str
    actor: str | None
    source: str | None
    operation_context_digest: str | None
    operation_context_refs: Mapping[str, JsonValue]
    reason: str
    request_context: Mapping[str, JsonValue]
    failure_stage: str
    failure_message: str


@dataclass(frozen=True, slots=True)
class PurgeAuditRecordResult:
    """purge audit record 写入结果。

    :param audit_record_ref: append-only audit JSONL 中的稳定 record ref。
    :param audit_record_digest: 已追加 audit JSONL line digest。
    """

    audit_record_ref: str
    audit_record_digest: str


@dataclass(frozen=True, slots=True)
class LogAuditSinkCatchupResult:
    """LogAuditSink catch-up 汇总结果。

    :param consumer_id: audit sink consumer id。
    :param started_cursor: 本次 catch-up 开始 cursor。
    :param finished_cursor: 本次 catch-up 结束 cursor。
    :param events_scanned: 扫描 EventLog row 数。
    :param events_applied: 新写 audit line 数。
    :param duplicates: marker 判定重复的 event 数。
    :param failures: projection runner 记录 failure 数。
    """

    consumer_id: ProjectionConsumerId
    started_cursor: int
    finished_cursor: int
    events_scanned: int
    events_applied: int
    duplicates: int
    failures: int


def default_log_audit_sink_options(
    artifact_root: Path, *, create_parent_dirs: bool
) -> LogAuditSinkOptions:
    """从 artifact root 派生默认 audit JSONL sink options。

    :param artifact_root: Host artifact 根目录。
    :param create_parent_dirs: 写入 audit JSONL 前是否创建 parent directory。
    :returns: 默认 LogAuditSink options。
    :raises TypeError: 路径字段类型非法时抛出。
    :raises ValueError: 路径为空时抛出。
    """

    audit_jsonl_path = (
        artifact_root / _AUDIT_ARTIFACT_DIRECTORY_NAME / _AUDIT_JSONL_FILE_NAME
    )
    return LogAuditSinkOptions(
        audit_jsonl_path=audit_jsonl_path,
        create_parent_dirs=create_parent_dirs,
        lock_path=audit_jsonl_path.with_name(
            audit_jsonl_path.name + _AUDIT_LOCK_FILE_SUFFIX
        ),
    )


class LogAuditSink:
    """append-only audit JSONL projection consumer。

    :param options: audit JSONL sink options。
    """

    def __init__(self, options: LogAuditSinkOptions) -> None:
        """初始化 audit sink。

        :param options: audit JSONL sink options。
        :returns: ``None``。
        :raises TypeError: ``options`` 不是 ``LogAuditSinkOptions`` 时抛出。
        """

        if not isinstance(options, LogAuditSinkOptions):
            raise TypeError("LogAuditSink options must be LogAuditSinkOptions")
        self._options = options

    @property
    def consumer_id(self) -> ProjectionConsumerId:
        """返回稳定 consumer id。

        :returns: ``host.audit-log-jsonl`` consumer id。
        :raises: 无。
        """

        return LOG_AUDIT_SINK_CONSUMER_ID

    @property
    def event_filter(self) -> ProjectionEventFilter:
        """返回 audit sink 默认消费的 canonical facts。

        :returns: 只包含 ``canonical_fact`` 的 EventLog filter；不消费 preview。
        :raises: 无。
        """

        return ProjectionEventFilter(
            (
                ProjectionEventClassFilter(
                    event_class=EventClass.CANONICAL_FACT,
                    event_types=None,
                ),
            )
        )

    def apply_event(
        self, transaction: HostTransaction, event: ProjectionEventView
    ) -> ProjectionApplyResult:
        """把单个 committed EventLog canonical fact 写入 audit JSONL。

        :param transaction: 当前 Host durable transaction。
        :param event: typed projection event view。
        :returns: projection apply result。
        :raises HostDurableError: EventLog row 缺失或 marker 冲突时抛出。
        :raises OSError: JSONL 文件写入失败时抛出，由 ProjectionRunner 记录 failure。
        """

        existing = read_audit_sink_marker(transaction, event.event_id)
        if existing is not None:
            return ProjectionApplyResult(
                ProjectionApplyStatus.DUPLICATE,
                idempotency_key=event.event_id,
                detail_code=event.event_type,
            )
        row = read_event_by_id(transaction, event.event_id)
        if row is None:
            raise HostDurableError("audit sink source EventLog row is missing")
        line = build_audit_json_line(event=event, event_row=row)
        self._append_line(line)
        marker_result = insert_audit_sink_marker_if_absent(
            transaction,
            event_id=event.event_id,
            event_sequence=event.event_sequence,
            line_digest=line.line_digest,
            written_at=_utc_now_text(),
        )
        if marker_result.status is AuditSinkMarkerWriteStatus.DUPLICATE:
            return ProjectionApplyResult(
                ProjectionApplyStatus.DUPLICATE,
                idempotency_key=event.event_id,
                detail_code=event.event_type,
            )
        return ProjectionApplyResult(
            ProjectionApplyStatus.APPLIED,
            idempotency_key=event.event_id,
            detail_code=event.event_type,
        )

    def _append_line(self, line: AuditJsonLine) -> None:
        """向 audit JSONL 文件幂等追加单行。

        :param line: 已构造的 audit line。
        :returns: ``None``。
        :raises OSError: 创建目录或写文件失败时抛出。
        :raises RuntimeFileLockError: lock 获取或释放失败时由底层抛出。
        """

        _append_audit_json_line(
            self._options,
            line,
            source_keys=(
                (
                    _AUDIT_FIELD_EVENT_ID,
                    _required_line_text(line, _AUDIT_FIELD_EVENT_ID),
                ),
            ),
        )


def build_audit_json_line(
    *, event: ProjectionEventView, event_row: EventLogRow
) -> AuditJsonLine:
    """从 projection event 与 EventLog typed row 构造 audit JSONL line。

    :param event: typed projection event view。
    :param event_row: 与 ``event.event_id`` 对应的 EventLog row。
    :returns: 包含 ``line_digest`` 的 audit line。
    :raises HostDurableError: event 与 row identity 不一致时抛出。
    """

    if (
        event_row.event_id != event.event_id
        or event_row.event_sequence != event.event_sequence
    ):
        raise HostDurableError("audit sink EventLog row identity mismatch")
    operation_context = _optional_mapping(
        event.payload.get(_PAYLOAD_FIELD_OPERATION_CONTEXT),
        field_name=_PAYLOAD_FIELD_OPERATION_CONTEXT,
    )
    operation_context_refs = _operation_context_refs(operation_context)
    operation_context_digest = (
        sha256_digest_json(operation_context)
        if operation_context is not None
        else None
    )
    fields_without_digest: dict[str, JsonValue] = {
        _AUDIT_FIELD_SCHEMA_VERSION: _AUDIT_LINE_SCHEMA_VERSION,
        _AUDIT_FIELD_EVENT_SEQUENCE: event.event_sequence,
        _AUDIT_FIELD_EVENT_ID: event.event_id,
        _AUDIT_FIELD_EVENT_TYPE: event.event_type,
        _AUDIT_FIELD_EVENT_CLASS: event.event_class.value,
        _AUDIT_FIELD_OCCURRED_AT: event.occurred_at,
        _AUDIT_FIELD_SESSION_ID: event.session_id,
        _AUDIT_FIELD_RUN_ID: event.run_id,
        _AUDIT_FIELD_ATTEMPT_ID: event.attempt_id,
        _AUDIT_FIELD_EXECUTION_ID: event.execution_id,
        _AUDIT_FIELD_ACTOR: event_row.actor,
        _AUDIT_FIELD_PRINCIPAL: _principal_from_payload(event.payload),
        _AUDIT_FIELD_SOURCE: event_row.source,
        _AUDIT_FIELD_CLIENT_REQUEST_ID: event_row.client_request_id,
        _AUDIT_FIELD_OPERATION_CONTEXT_REFS: list(operation_context_refs),
        _AUDIT_FIELD_OPERATION_CONTEXT_DIGEST: operation_context_digest,
        _AUDIT_FIELD_POLICY_DECISION_REF: _optional_text_from_payload(
            event.payload, _PAYLOAD_FIELD_POLICY_DECISION_REF
        ),
        _AUDIT_FIELD_POLICY_DECISION_SUMMARY: _policy_decision_summary(
            event.payload, event_row.policy_decision_json
        ),
        _AUDIT_FIELD_REASON: _reason_value(event.payload, event_row.reason_json),
        _AUDIT_FIELD_PAYLOAD_REF: event_row.payload_ref,
        _AUDIT_FIELD_PAYLOAD_DIGEST: event_row.payload_digest,
    }
    line_digest = sha256_digest_json(fields_without_digest)
    fields: dict[str, JsonValue] = dict(fields_without_digest)
    fields[_AUDIT_FIELD_LINE_DIGEST] = line_digest
    return AuditJsonLine(fields=fields, line_digest=line_digest)


def build_purge_started_audit_json_line(
    request: PurgeStartedAuditRecordRequest,
) -> AuditJsonLine:
    """构造 purge_started audit JSONL line。

    ``schema_version``、``line_kind``、``audit_record_ref``、
    ``purge_attempt_ref`` 与 ``line_digest`` 均由 builder 派生；调用方只提供
    purge 业务输入。该 line 不包含 transaction 内才知道的删除矩阵信息。

    :param request: purge_started audit record 请求。
    :returns: 包含 ``line_digest`` 的 audit JSONL line。
    :raises HostDurableError: 请求字段无效时抛出。
    """

    _validate_purge_started_request(request)
    fields_without_digest: dict[str, JsonValue] = _base_purge_audit_fields(
        line_kind=_AUDIT_LINE_KIND_PURGE_STARTED,
        tombstone_id=request.tombstone_id,
        session_id=request.session_id,
        client_request_id=request.client_request_id,
        semantic_request_digest=request.semantic_request_digest,
        actor=request.actor,
        source=request.source,
        operation_context_digest=request.operation_context_digest,
        operation_context_refs=request.operation_context_refs,
        reason=request.reason,
        request_context=request.request_context,
    )
    fields_without_digest.update(
        {
            _AUDIT_FIELD_PLANNED_PURGE_TOMBSTONE_REF: request.tombstone_id,
            _AUDIT_FIELD_PURGE_TOMBSTONE_REF: None,
            _AUDIT_FIELD_PURGE_TOMBSTONE_DIGEST: None,
            _AUDIT_FIELD_SOURCE_EVENTLOG_FACTS_PURGED: False,
        }
    )
    return _line_with_digest(fields_without_digest)


def append_purge_started_audit_record(
    options: LogAuditSinkOptions,
    request: PurgeStartedAuditRecordRequest,
) -> PurgeAuditRecordResult:
    """append-only 写入 purge_started audit JSONL line。

    :param options: audit JSONL sink options。
    :param request: purge_started audit record 请求。
    :returns: audit record ref 与 line digest。
    :raises HostDurableError: 同 ``(line_kind, purge_attempt_ref)`` digest 冲突时抛出。
    :raises OSError: JSONL 文件创建或追加失败时抛出。
    :raises RuntimeFileLockError: 文件锁获取或释放失败时由底层抛出。
    """

    line = build_purge_started_audit_json_line(request)
    _append_purge_audit_json_line(options, line)
    return _purge_audit_record_result(line)


def build_purge_completed_audit_json_line(
    request: PurgeCompletedAuditRecordRequest,
) -> AuditJsonLine:
    """构造 purge_completed audit JSONL line。

    ``purge_tombstone_digest`` 来自 committed tombstone row 的稳定 digest，
    覆盖 tombstone 全部已持久字段，包括 started audit ref/digest；builder
    不接收 completed audit ref/digest，避免循环依赖。

    :param request: purge_completed audit record 请求。
    :returns: 包含 ``line_digest`` 的 audit JSONL line。
    :raises HostDurableError: 请求字段无效时抛出。
    """

    _validate_purge_completed_request(request)
    tombstone = request.tombstone
    fields_without_digest: dict[str, JsonValue] = _base_purge_audit_fields(
        line_kind=_AUDIT_LINE_KIND_PURGE_COMPLETED,
        tombstone_id=tombstone.tombstone_id,
        session_id=tombstone.session_id,
        client_request_id=tombstone.client_request_id,
        semantic_request_digest=request.semantic_request_digest,
        actor=tombstone.actor,
        source=tombstone.source,
        operation_context_digest=tombstone.operation_context_digest,
        operation_context_refs=tombstone.operation_context_refs,
        reason=tombstone.reason,
        request_context=tombstone.request_context,
    )
    fields_without_digest.update(
        {
            _AUDIT_FIELD_PURGE_TOMBSTONE_REF: tombstone.tombstone_id,
            _AUDIT_FIELD_PURGE_TOMBSTONE_DIGEST: build_purge_tombstone_digest(tombstone),
            _AUDIT_FIELD_STARTED_AUDIT_RECORD_REF: tombstone.audit_record_ref,
            _AUDIT_FIELD_STARTED_AUDIT_RECORD_DIGEST: tombstone.audit_record_digest,
            _AUDIT_FIELD_DELETED_COUNTS_DIGEST: tombstone.deleted_counts_digest,
            _AUDIT_FIELD_PRECONDITION_DIGEST: tombstone.precondition_digest,
            _AUDIT_FIELD_DELETED_REFS_DIGEST: tombstone.deleted_refs_digest,
            _AUDIT_FIELD_SOURCE_EVENTLOG_FACTS_PURGED: True,
        }
    )
    return _line_with_digest(fields_without_digest)


def append_purge_completed_audit_record(
    options: LogAuditSinkOptions,
    request: PurgeCompletedAuditRecordRequest,
) -> PurgeAuditRecordResult:
    """append-only 写入 purge_completed audit JSONL line。

    :param options: audit JSONL sink options。
    :param request: purge_completed audit record 请求。
    :returns: audit record ref 与 line digest。
    :raises HostDurableError: 同 ``(line_kind, purge_attempt_ref)`` digest 冲突时抛出。
    :raises OSError: JSONL 文件创建或追加失败时抛出。
    :raises RuntimeFileLockError: 文件锁获取或释放失败时由底层抛出。
    """

    line = build_purge_completed_audit_json_line(request)
    _append_purge_audit_json_line(options, line)
    return _purge_audit_record_result(line)


def build_purge_failed_audit_json_line(
    request: PurgeFailedAuditRecordRequest,
) -> AuditJsonLine:
    """构造 purge_failed audit JSONL line。

    ``purge_failed`` 只记录 best-effort 诊断，不表示 EventLog facts 已被
    purge，也不参与 durable truth、recovery 或 reconciliation 查询。

    :param request: purge_failed audit record 请求。
    :returns: 包含 ``line_digest`` 的 audit JSONL line。
    :raises HostDurableError: 请求字段无效时抛出。
    """

    _validate_purge_failed_request(request)
    fields_without_digest: dict[str, JsonValue] = _base_purge_audit_fields(
        line_kind=_AUDIT_LINE_KIND_PURGE_FAILED,
        tombstone_id=request.tombstone_id,
        session_id=request.session_id,
        client_request_id=request.client_request_id,
        semantic_request_digest=request.semantic_request_digest,
        actor=request.actor,
        source=request.source,
        operation_context_digest=request.operation_context_digest,
        operation_context_refs=request.operation_context_refs,
        reason=request.reason,
        request_context=request.request_context,
    )
    fields_without_digest.update(
        {
            _AUDIT_FIELD_PLANNED_PURGE_TOMBSTONE_REF: request.tombstone_id,
            _AUDIT_FIELD_FAILURE_STAGE: request.failure_stage,
            _AUDIT_FIELD_FAILURE_MESSAGE: _bounded_failure_message(
                request.failure_message
            ),
            _AUDIT_FIELD_SOURCE_EVENTLOG_FACTS_PURGED: False,
        }
    )
    return _line_with_digest(fields_without_digest)


def append_purge_failed_audit_record(
    options: LogAuditSinkOptions,
    request: PurgeFailedAuditRecordRequest,
) -> PurgeAuditRecordResult:
    """append-only 写入 purge_failed audit JSONL line。

    :param options: audit JSONL sink options。
    :param request: purge_failed audit record 请求。
    :returns: audit record ref 与 line digest。
    :raises HostDurableError: 同 ``(line_kind, purge_attempt_ref)`` digest 冲突时抛出。
    :raises OSError: JSONL 文件创建或追加失败时抛出。
    :raises RuntimeFileLockError: 文件锁获取或释放失败时由底层抛出。
    """

    line = build_purge_failed_audit_json_line(request)
    _append_purge_audit_json_line(options, line)
    return _purge_audit_record_result(line)


def audit_json_line_marks_purged_source_eventlog_facts(
    line: Mapping[str, JsonValue],
) -> bool:
    """判断 audit JSONL object 是否为 completed purge audit line。

    :param line: 已解析的 audit JSONL object。
    :returns: 该行明确表示源 EventLog facts 已 purge 时返回 ``True``。
    :raises: 无。
    """

    return (
        line.get(_AUDIT_FIELD_LINE_KIND) == _AUDIT_LINE_KIND_PURGE_COMPLETED
        and line.get(_AUDIT_FIELD_SOURCE_EVENTLOG_FACTS_PURGED) is True
    )


def _base_purge_audit_fields(
    *,
    line_kind: str,
    tombstone_id: str,
    session_id: str,
    client_request_id: str,
    semantic_request_digest: str,
    actor: str | None,
    source: str | None,
    operation_context_digest: str | None,
    operation_context_refs: Mapping[str, JsonValue],
    reason: str,
    request_context: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    """构造 purge audit line 公共字段。

    :param line_kind: purge audit line kind。
    :param tombstone_id: deterministic tombstone id。
    :param session_id: 被 purge 的 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge 请求 semantic digest。
    :param actor: 发起方标识。
    :param source: 来源标识。
    :param operation_context_digest: 操作上下文 digest。
    :param operation_context_refs: 操作上下文 refs JSON object。
    :param reason: purge 原因。
    :param request_context: 请求上下文 refs JSON object。
    :returns: 不含 ``line_digest`` 的 JSON object。
    :raises HostDurableError: line kind 或 tombstone id 无效时抛出。
    """

    attempt_ref = build_purge_attempt_ref(tombstone_id)
    return {
        _AUDIT_FIELD_SCHEMA_VERSION: _AUDIT_LINE_SCHEMA_VERSION,
        _AUDIT_FIELD_LINE_KIND: line_kind,
        _AUDIT_FIELD_AUDIT_RECORD_REF: _purge_audit_record_ref(
            line_kind=line_kind,
            attempt_ref=attempt_ref,
        ),
        _AUDIT_FIELD_PURGE_ATTEMPT_REF: attempt_ref,
        _AUDIT_FIELD_SESSION_ID: session_id,
        _AUDIT_FIELD_CLIENT_REQUEST_ID: client_request_id,
        _AUDIT_FIELD_ACTOR: actor,
        _AUDIT_FIELD_SOURCE: source,
        _AUDIT_FIELD_OPERATION_CONTEXT_REFS: operation_context_refs,
        _AUDIT_FIELD_OPERATION_CONTEXT_DIGEST: operation_context_digest,
        _AUDIT_FIELD_REASON: reason,
        _AUDIT_FIELD_REQUEST_CONTEXT: request_context,
        _AUDIT_FIELD_SEMANTIC_REQUEST_DIGEST: semantic_request_digest,
    }


def _line_with_digest(fields_without_digest: Mapping[str, JsonValue]) -> AuditJsonLine:
    """为 audit fields 补充 line digest。

    :param fields_without_digest: 不含 ``line_digest`` 的 JSON object。
    :returns: 包含 ``line_digest`` 的 audit JSONL line。
    :raises TypeError: 字段包含非 JSON 值时抛出。
    :raises ValueError: 字段包含非有限浮点数时抛出。
    """

    line_digest = sha256_digest_json(fields_without_digest)
    fields: dict[str, JsonValue] = dict(fields_without_digest)
    fields[_AUDIT_FIELD_LINE_DIGEST] = line_digest
    return AuditJsonLine(fields=fields, line_digest=line_digest)


def _append_purge_audit_json_line(
    options: LogAuditSinkOptions,
    line: AuditJsonLine,
) -> None:
    """按 purge audit source key 幂等追加 JSONL line。

    :param options: audit JSONL sink options。
    :param line: 待追加的 purge audit line。
    :returns: ``None``。
    :raises HostDurableError: 同 ``(line_kind, purge_attempt_ref)`` digest 冲突时抛出。
    :raises OSError: 创建目录或写文件失败时抛出。
    :raises RuntimeFileLockError: lock 获取或释放失败时由底层抛出。
    """

    _append_audit_json_line(
        options,
        line,
        source_keys=(
            (_AUDIT_FIELD_LINE_KIND, _required_line_text(line, _AUDIT_FIELD_LINE_KIND)),
            (
                _AUDIT_FIELD_PURGE_ATTEMPT_REF,
                _required_line_text(line, _AUDIT_FIELD_PURGE_ATTEMPT_REF),
            ),
        ),
    )


def _purge_audit_record_result(line: AuditJsonLine) -> PurgeAuditRecordResult:
    """从 audit line 构造 purge audit append result。

    :param line: 已构造的 purge audit line。
    :returns: purge audit record result。
    :raises HostDurableError: audit record ref 字段缺失时抛出。
    """

    return PurgeAuditRecordResult(
        audit_record_ref=_required_line_text(line, _AUDIT_FIELD_AUDIT_RECORD_REF),
        audit_record_digest=line.line_digest,
    )


def _purge_audit_record_ref(*, line_kind: str, attempt_ref: str) -> str:
    """构造 purge audit record ref。

    :param line_kind: purge audit line kind。
    :param attempt_ref: purge attempt ref。
    :returns: audit JSONL record ref。
    :raises HostDurableError: line kind 或 attempt ref 为空时抛出。
    """

    _require_non_empty_text(line_kind, field_name="line_kind")
    _require_non_empty_text(attempt_ref, field_name="purge_attempt_ref")
    return f"{_AUDIT_RECORD_REF_PREFIX}{line_kind}:{attempt_ref}"


def _validate_purge_started_request(request: PurgeStartedAuditRecordRequest) -> None:
    """校验 purge_started 请求。

    :param request: purge_started audit record 请求。
    :returns: ``None``。
    :raises HostDurableError: 任一字段不符合 audit contract 时抛出。
    """

    _validate_purge_common_request(
        tombstone_id=request.tombstone_id,
        session_id=request.session_id,
        client_request_id=request.client_request_id,
        semantic_request_digest=request.semantic_request_digest,
        actor=request.actor,
        source=request.source,
        operation_context_digest=request.operation_context_digest,
        reason=request.reason,
    )


def _validate_purge_completed_request(
    request: PurgeCompletedAuditRecordRequest,
) -> None:
    """校验 purge_completed 请求。

    :param request: purge_completed audit record 请求。
    :returns: ``None``。
    :raises HostDurableError: semantic digest 无效或 tombstone 无效时抛出。
    """

    _require_sha256_digest(
        request.semantic_request_digest,
        field_name="semantic_request_digest",
    )
    build_purge_tombstone_digest(request.tombstone)


def _validate_purge_failed_request(request: PurgeFailedAuditRecordRequest) -> None:
    """校验 purge_failed 请求。

    :param request: purge_failed audit record 请求。
    :returns: ``None``。
    :raises HostDurableError: 任一字段不符合 audit contract 时抛出。
    """

    _validate_purge_common_request(
        tombstone_id=request.tombstone_id,
        session_id=request.session_id,
        client_request_id=request.client_request_id,
        semantic_request_digest=request.semantic_request_digest,
        actor=request.actor,
        source=request.source,
        operation_context_digest=request.operation_context_digest,
        reason=request.reason,
    )
    _require_non_empty_text(request.failure_stage, field_name="failure_stage")
    _require_non_empty_text(request.failure_message, field_name="failure_message")


def _validate_purge_common_request(
    *,
    tombstone_id: str,
    session_id: str,
    client_request_id: str,
    semantic_request_digest: str,
    actor: str | None,
    source: str | None,
    operation_context_digest: str | None,
    reason: str,
) -> None:
    """校验 purge audit 公共请求字段。

    :param tombstone_id: purge tombstone id。
    :param session_id: 被 purge 的 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge 请求 semantic digest。
    :param actor: 发起方标识。
    :param source: 来源标识。
    :param operation_context_digest: 操作上下文 digest。
    :param reason: purge 原因。
    :returns: ``None``。
    :raises HostDurableError: 任一字段不符合 audit contract 时抛出。
    """

    _require_non_empty_text(tombstone_id, field_name="tombstone_id")
    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(client_request_id, field_name="client_request_id")
    _require_sha256_digest(
        semantic_request_digest,
        field_name="semantic_request_digest",
    )
    _require_optional_non_empty_text(actor, field_name="actor")
    _require_optional_non_empty_text(source, field_name="source")
    _require_optional_sha256_digest(
        operation_context_digest,
        field_name="operation_context_digest",
    )
    _require_non_empty_text(reason, field_name="reason")


def _bounded_failure_message(value: str) -> str:
    """返回有界 failure message。

    :param value: 原始 failure message。
    :returns: 最多 ``_PURGE_FAILURE_MESSAGE_MAX_CHARS`` 个字符的诊断文本。
    :raises HostDurableError: 文本为空时抛出。
    """

    _require_non_empty_text(value, field_name="failure_message")
    return value[:_PURGE_FAILURE_MESSAGE_MAX_CHARS]


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验必填非空文本。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 值为空时抛出。
    """

    if value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")


def _require_optional_non_empty_text(value: str | None, *, field_name: str) -> None:
    """校验可选非空文本。

    :param value: 待校验文本或 ``None``。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 值存在但为空时抛出。
    """

    if value is not None:
        _require_non_empty_text(value, field_name=field_name)


def _require_sha256_digest(value: str, *, field_name: str) -> None:
    """校验 sha256 digest 文本。

    :param value: 待校验 digest。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 值不是 ``sha256:`` digest 时抛出。
    """

    prefix = "sha256:"
    hex_part = value.removeprefix(prefix)
    if (
        not value.startswith(prefix)
        or len(hex_part) != 64
        or any(character not in "0123456789abcdef" for character in hex_part)
    ):
        raise HostDurableError(f"{field_name} must be sha256 digest")


def _require_optional_sha256_digest(value: str | None, *, field_name: str) -> None:
    """校验可选 sha256 digest 文本。

    :param value: 待校验 digest 或 ``None``。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 值存在但不是 ``sha256:`` digest 时抛出。
    """

    if value is not None:
        _require_sha256_digest(value, field_name=field_name)


def catch_up_log_audit_sink_projection(
    transaction_runner: HostTransactionRunner,
    *,
    options: LogAuditSinkOptions,
    batch_size: int = DEFAULT_LOG_AUDIT_CATCHUP_BATCH_SIZE,
    max_event_sequence: int | None = None,
) -> LogAuditSinkCatchupResult:
    """追平 LogAuditSink projection。

    :param transaction_runner: Host durable transaction runner。
    :param options: audit sink options。
    :param batch_size: 每批最多扫描 EventLog row 数，必须为正数。
    :param max_event_sequence: 可选最大 EventLog sequence。
    :returns: audit sink catch-up 汇总结果。
    :raises HostDurableError: batch size 非法或 projection runner 初始化失败时抛出。
    """

    if batch_size <= 0:
        raise HostDurableError("audit sink catch-up batch_size must be positive")
    consumer = LogAuditSink(options)
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
    return LogAuditSinkCatchupResult(
        consumer_id=consumer.consumer_id,
        started_cursor=started_cursor,
        finished_cursor=finished_cursor,
        events_scanned=events_scanned,
        events_applied=events_applied,
        duplicates=duplicates,
        failures=failures,
    )


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


def _append_audit_json_line(
    options: LogAuditSinkOptions,
    line: AuditJsonLine,
    *,
    source_keys: tuple[tuple[str, str], ...],
) -> None:
    """按 audit sink options 幂等追加 JSONL line。

    :param options: audit sink options。
    :param line: 待追加的 audit JSONL line。
    :param source_keys: 当前 line 的稳定 source key 集合。
    :returns: ``None``。
    :raises HostDurableError: source key 冲突时抛出。
    :raises OSError: 创建目录或写文件失败时抛出。
    :raises RuntimeFileLockError: lock 获取或释放失败时由底层抛出。
    """

    if options.create_parent_dirs:
        options.audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if options.lock_path is None:
        _append_text_if_absent(
            options.audit_jsonl_path,
            line.to_jsonl_text(),
            line_digest=line.line_digest,
            source_keys=source_keys,
        )
        return
    with file_lock(
        options.lock_path,
        timeout_seconds=_LOCK_TIMEOUT_SECONDS,
        create_parent_dirs=options.create_parent_dirs,
    ):
        _append_text_if_absent(
            options.audit_jsonl_path,
            line.to_jsonl_text(),
            line_digest=line.line_digest,
            source_keys=source_keys,
        )


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
    """检查 JSONL 中是否已有同一 line digest 或同一组合 source key。

    :param path: JSONL 文件路径。
    :param line_digest: 当前行 digest。
    :param source_keys: 当前行的稳定 source key 集合。
    :returns: 已存在同一 line digest 时返回 ``True``。
    :raises HostDurableError: 已存在相同组合 source key 但 digest 不同时抛出。
    :raises OSError: 读取文件失败时抛出。
    """

    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            existing = _json_object_from_jsonl_line(raw_line)
            if existing is None:
                continue
            existing_digest = existing.get(_AUDIT_FIELD_LINE_DIGEST)
            if existing_digest == line_digest:
                return True
            if all(
                existing.get(field_name) == field_value
                for field_name, field_value in source_keys
            ):
                raise HostDurableError(
                    "audit JSONL source key conflicts with line digest"
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


def _required_line_text(line: AuditJsonLine, field_name: str) -> str:
    """读取 audit line 中的必填文本字段。

    :param line: audit JSONL 行。
    :param field_name: 字段名。
    :returns: 非空文本字段值。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = line.fields.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"audit line field {field_name} must be text")


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
            raise HostDurableError(
                "audit operation_context ref field must be text"
            )
        if value.strip() != "":
            refs.append(value)
    return tuple(refs)


def _principal_from_payload(payload: Mapping[str, JsonValue]) -> str | None:
    """从 authorization claims 中抽取 principal 文本。

    :param payload: projection event payload。
    :returns: principal 文本；无法从 typed claims 明确取得时返回 ``None``。
    :raises HostDurableError: claims 结构存在但类型非法时抛出。
    """

    claims = payload.get(_PAYLOAD_FIELD_AUTHORIZATION_CLAIMS)
    if claims is None:
        return None
    if not isinstance(claims, list):
        raise HostDurableError("audit authorization_claims must be JSON array")
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise HostDurableError("audit authorization claim must be JSON object")
        name = claim.get("name")
        value = claim.get("value")
        if (
            isinstance(name, str)
            and name in _PRINCIPAL_CLAIM_NAMES
            and isinstance(value, str)
            and value.strip() != ""
        ):
            return value
    return None


def _policy_decision_summary(
    payload: Mapping[str, JsonValue], policy_decision_json: str | None
) -> JsonValue:
    """构造 audit line 的 policy decision summary。

    :param payload: projection event payload。
    :param policy_decision_json: EventLog row 的 canonical policy decision JSON 文本。
    :returns: summary JSON 值；缺失时为 ``None``。
    :raises HostDurableError: JSON 文本非法时抛出。
    """

    if policy_decision_json is not None:
        return _json_value_from_text(
            policy_decision_json, field_name="policy_decision_json"
        )
    return payload.get(_PAYLOAD_FIELD_POLICY_DECISION_SUMMARY)


def _reason_value(
    payload: Mapping[str, JsonValue], reason_json: str | None
) -> JsonValue:
    """构造 audit line 的 reason 字段。

    :param payload: projection event payload。
    :param reason_json: EventLog row 的 canonical reason JSON 文本。
    :returns: reason JSON 值；缺失时为 ``None``。
    :raises HostDurableError: JSON 文本非法时抛出。
    """

    if reason_json is not None:
        return _json_value_from_text(reason_json, field_name="reason_json")
    return payload.get(_PAYLOAD_FIELD_REASON)


def _json_value_from_text(value: str, *, field_name: str) -> JsonValue:
    """解析已持久化的 canonical JSON 文本。

    :param value: JSON 文本。
    :param field_name: 错误消息字段名。
    :returns: JSON 值。
    :raises HostDurableError: JSON 文本非法时抛出。
    """

    try:
        return cast(JsonValue, json.loads(value))
    except json.JSONDecodeError as exc:
        raise HostDurableError(f"audit {field_name} is invalid") from exc


def _optional_mapping(
    value: JsonValue | None, *, field_name: str
) -> Mapping[str, JsonValue] | None:
    """读取可选 JSON object 字段。

    :param value: JSON 值。
    :param field_name: 错误消息字段名。
    :returns: JSON object 或 ``None``。
    :raises HostDurableError: 字段存在但不是 JSON object 时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise HostDurableError(f"audit {field_name} must be JSON object")
    return cast(Mapping[str, JsonValue], value)


def _optional_text_from_payload(
    payload: Mapping[str, JsonValue], field_name: str
) -> str | None:
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
    raise HostDurableError(f"audit payload field {field_name} must be text")


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
    :raises: 无。
    """

    return format_utc_timestamp(datetime.now(UTC))


__all__ = [
    "DEFAULT_LOG_AUDIT_CATCHUP_BATCH_SIZE",
    "LOG_AUDIT_SINK_CONSUMER_ID",
    "AuditJsonLine",
    "LogAuditSink",
    "LogAuditSinkCatchupResult",
    "LogAuditSinkOptions",
    "PurgeAuditRecordResult",
    "PurgeCompletedAuditRecordRequest",
    "PurgeFailedAuditRecordRequest",
    "PurgeStartedAuditRecordRequest",
    "append_purge_completed_audit_record",
    "append_purge_failed_audit_record",
    "append_purge_started_audit_record",
    "audit_json_line_marks_purged_source_eventlog_facts",
    "build_audit_json_line",
    "build_purge_completed_audit_json_line",
    "build_purge_failed_audit_json_line",
    "build_purge_started_audit_json_line",
    "catch_up_log_audit_sink_projection",
    "default_log_audit_sink_options",
]
