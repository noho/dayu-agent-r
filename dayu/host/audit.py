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

        if self._options.create_parent_dirs:
            self._options.audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        source_keys = (
            (_AUDIT_FIELD_EVENT_ID, _required_line_text(line, _AUDIT_FIELD_EVENT_ID)),
        )
        if self._options.lock_path is None:
            _append_text_if_absent(
                self._options.audit_jsonl_path,
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
                self._options.audit_jsonl_path,
                line.to_jsonl_text(),
                line_digest=line.line_digest,
                source_keys=source_keys,
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
            existing_digest = existing.get(_AUDIT_FIELD_LINE_DIGEST)
            if existing_digest == line_digest:
                return True
            for field_name, field_value in source_keys:
                if existing.get(field_name) == field_value:
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
    "build_audit_json_line",
    "catch_up_log_audit_sink_projection",
]
