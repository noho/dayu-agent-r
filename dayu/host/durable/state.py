"""Host durable state row codec。

本模块只负责 Phase 3 durable state tables 的 row dataclass、状态枚举编解码
与 ``HostRow`` 转换。它不追加 EventLog、不打开 transaction，也不实现
Session lifecycle、admission、promotion、cancel 或 command path 语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from dayu.host.api import (
    AttemptStatus,
    HOST_WAIT_EXTERNAL_JOB_ID_MAX_LENGTH,
    HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    HOST_WAIT_ID_MAX_LENGTH,
    HOST_WAIT_RESUME_TOKEN_MAX_LENGTH,
    HOST_WAIT_SNAPSHOT_ID_MAX_LENGTH,
    HOST_WAIT_TOOL_CALL_ID_MAX_LENGTH,
    HOST_WAIT_TOOL_NAME_MAX_LENGTH,
    HostStreamCursor,
    RunSnapshot,
    RunStatus,
    SessionSlotRef,
    SessionSnapshot,
    SessionStatus,
    SourceRunRelation,
    TerminalResultSummary,
    WaitAdapterKey,
)
from dayu.host.durable.codec import format_utc_timestamp, parse_utc_timestamp
from dayu.host.durable._validation import (
    optional_int as _optional_int,
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_text as _require_text,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.schema import (
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_SESSION_SLOTS,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_WAIT_RECORDS,
)
from dayu.host.durable.transaction import HostRow
from dayu.host.durable.transaction import HostTransaction

_StatusT = TypeVar("_StatusT", bound=StrEnum)
_TERMINAL_RUN_STATUSES = frozenset(
    (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.LOST)
)
_WAIT_RECORD_SELECT_SQL = f"""
SELECT
  wait_id,
  session_id,
  run_id,
  attempt_id,
  execution_id,
  tool_call_id,
  tool_name,
  adapter_key,
  await_kind,
  resume_policy,
  resume_token,
  snapshot_ref,
  snapshot_captured_at,
  snapshot_digest,
  external_job_id,
  accept_idempotency_key,
  resolve_idempotency_key,
  resolve_semantic_digest,
  deadline_at,
  expires_at,
  status,
  created_event_id,
  created_event_sequence,
  updated_event_id,
  updated_event_sequence,
  created_at,
  updated_at,
  terminal_at
FROM {TABLE_HOST_WAIT_RECORDS}
"""


class DispatchRecordStatus(StrEnum):
    """Attempt dispatch record 状态。

    ``PENDING`` 表示 Host 已创建 pre-dispatch durable truth；``WAITING_FOR_LANE``
    与 ``DISPATCHING`` 只表达本地 dispatch 诊断和重复派发抑制，不是 lease /
    fencing / owner truth；``CANCELLED`` 表示 worker accept 前的 direct cancel。
    """

    PENDING = "pending"
    WAITING_FOR_LANE = "waiting_for_lane"
    DISPATCHING = "dispatching"
    CANCELLED = "cancelled"


class WorkerKind(StrEnum):
    """dispatch record 指向的 worker 类型。"""

    LOCAL = "local"
    REMOTE = "remote"


class RunStartReason(StrEnum):
    """Run 从 queued 或 accepted 状态进入 running 的原因。"""

    INITIAL = "initial"
    QUEUE_PROMOTION = "queue_promotion"
    RESUME = "resume"


class WaitRecordStatus(StrEnum):
    """Host durable wait record 状态。"""

    WAITING = "waiting"
    RESOLVED = "resolved"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


class WaitResumePolicy(StrEnum):
    """等待恢复策略。"""

    POLL = "poll"
    CALLBACK = "callback"
    MANUAL = "manual"


class StateMutationStatus(StrEnum):
    """低层 CAS mutation 结果状态。"""

    UPDATED = "updated"
    CAS_LOST = "cas_lost"
    NOT_FOUND = "not_found"
    INVALID_STATE = "invalid_state"


@dataclass(frozen=True, slots=True)
class SessionRow:
    """``host_sessions`` durable row。

    字段保存 Session lifecycle 的 durable truth；事件字段引用 EventLog canonical
    facts，关闭字段只在 ``status`` 为 ``CLOSED`` 时存在。
    """

    session_id: str
    status: SessionStatus
    metadata_json: str
    created_event_id: str
    created_event_sequence: int
    closed_event_id: str | None
    closed_event_sequence: int | None
    created_at: str
    closed_at: str | None


@dataclass(frozen=True, slots=True)
class SessionSlotRow:
    """``host_session_slots`` durable row。

    字段保存 ``(scope, slot_key)`` 到当前 Session 的 durable binding。
    """

    scope: str
    slot_key: str
    session_id: str
    bound_event_id: str
    bound_event_sequence: int
    metadata_json: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class RunRow:
    """``host_runs`` durable row。

    字段保存 Run lifecycle、queue FIFO 游标、active attempt 指针与 terminal refs。
    Phase 3 不在此 dataclass 中承载 command 行为。
    """

    run_id: str
    session_id: str
    status: RunStatus
    client_request_id: str
    input_event_id: str
    input_event_sequence: int
    accepted_event_id: str
    accepted_event_sequence: int
    queued_event_id: str | None
    queued_event_sequence: int | None
    started_event_id: str | None
    started_event_sequence: int | None
    terminal_event_id: str | None
    terminal_event_sequence: int | None
    current_attempt_id: str | None
    source_run_id: str | None
    source_run_relation: SourceRunRelation | None
    execution_target: str
    queue_policy: str
    created_at: str
    updated_at: str
    terminal_at: str | None


@dataclass(frozen=True, slots=True)
class AttemptRow:
    """``host_attempts`` durable row。

    字段保存一次 execution attempt 的状态、execution id 和 terminal refs。
    """

    attempt_id: str
    run_id: str
    execution_id: str
    status: AttemptStatus
    started_event_id: str
    started_event_sequence: int
    terminal_event_id: str | None
    terminal_event_sequence: int | None
    created_at: str
    updated_at: str
    terminal_at: str | None


@dataclass(frozen=True, slots=True)
class DispatchRecordRow:
    """``host_attempt_dispatch_records`` durable row。

    字段保存 Attempt dispatch 诊断与重复派发抑制信息。active worker truth
    只能由 ``ATTEMPT_RUNNING`` 与 Attempt row ``RUNNING`` 表达。
    """

    dispatch_record_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    status: DispatchRecordStatus
    worker_kind: WorkerKind
    execution_target: str
    owner_host_instance_id: str | None
    created_event_id: str
    created_event_sequence: int
    waiting_for_lane_at: str | None
    lane_name: str | None
    lane_claim_id: str | None
    lane_owner_id: str | None
    lane_acquired_at: str | None
    dispatching_at: str | None
    worker_accepted_at: str | None
    worker_accept_event_id: str | None
    worker_accept_event_sequence: int | None
    cancelled_event_id: str | None
    cancelled_event_sequence: int | None
    created_at: str
    updated_at: str
    cancelled_at: str | None


@dataclass(frozen=True, slots=True)
class RunMutationResult:
    """Run CAS mutation 结果。

    :param status: mutation 结果分类。
    :param row: mutation 后读取到的最新 Run row；缺失时为 ``None``。
    """

    status: StateMutationStatus
    row: RunRow | None


@dataclass(frozen=True, slots=True)
class AttemptMutationResult:
    """Attempt CAS mutation 结果。

    :param status: mutation 结果分类。
    :param row: mutation 后读取到的最新 Attempt row；缺失时为 ``None``。
    """

    status: StateMutationStatus
    row: AttemptRow | None


@dataclass(frozen=True, slots=True)
class DispatchRecordMutationResult:
    """dispatch record CAS mutation 结果。

    :param status: mutation 结果分类。
    :param row: mutation 后读取到的最新 dispatch record row；缺失时为 ``None``。
    """

    status: StateMutationStatus
    row: DispatchRecordRow | None


@dataclass(frozen=True, slots=True)
class WaitSnapshotRef:
    """等待接受时捕获的快照引用。

    :param snapshot_id: 快照标识。
    :param captured_at: 快照采集时间，必须为 UTC aware ``datetime``。
    :param snapshot_digest: 快照摘要；无摘要时为 ``None``。
    """

    snapshot_id: str
    captured_at: datetime
    snapshot_digest: str | None

    def __post_init__(self) -> None:
        """校验快照引用字段。

        :returns: ``None``。
        :raises HostDurableError: 快照 id 为空、超长或时间格式非法时抛出。
        """

        _require_text_max_length(
            self.snapshot_id,
            field_name="snapshot_id",
            max_length=HOST_WAIT_SNAPSHOT_ID_MAX_LENGTH,
        )
        if not isinstance(self.captured_at, datetime):
            raise HostDurableError("snapshot_captured_at must be datetime")
        try:
            format_utc_timestamp(self.captured_at)
        except ValueError as exc:
            raise HostDurableError("snapshot_captured_at must be UTC aware") from exc
        _require_optional_non_empty_text(
            self.snapshot_digest, field_name="snapshot_digest"
        )


@dataclass(frozen=True, slots=True)
class ExternalJobRef:
    """等待适配器可重读的外部 job 引用。

    :param adapter_key: 产生外部 job 引用的 Host 等待适配器键。
    :param external_job_id: 外部 job 稳定 id。
    """

    adapter_key: WaitAdapterKey
    external_job_id: str

    def __post_init__(self) -> None:
        """校验外部 job 引用。

        :returns: ``None``。
        :raises HostDurableError: adapter key 类型或外部 id 非法时抛出。
        """

        if not isinstance(self.adapter_key, WaitAdapterKey):
            raise HostDurableError("external job adapter_key is invalid")
        _require_text_max_length(
            self.external_job_id,
            field_name="external_job_id",
            max_length=HOST_WAIT_EXTERNAL_JOB_ID_MAX_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class WaitRecordRow:
    """``host_wait_records`` durable row。

    字段保存 Host-owned wait record truth；只保存可重读引用，不保存外部
    adapter object、provider payload 或业务工具私有状态。
    """

    wait_id: str
    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    tool_call_id: str
    tool_name: str
    adapter_key: WaitAdapterKey
    await_kind: str
    resume_policy: WaitResumePolicy
    resume_token: str
    snapshot_ref: WaitSnapshotRef | None
    external_job_ref: ExternalJobRef | None
    accept_idempotency_key: str
    resolve_idempotency_key: str | None
    resolve_semantic_digest: str | None
    deadline_at: str | None
    expires_at: str | None
    status: WaitRecordStatus
    created_event_id: str
    created_event_sequence: int
    updated_event_id: str
    updated_event_sequence: int
    created_at: str
    updated_at: str
    terminal_at: str | None


@dataclass(frozen=True, slots=True)
class WaitRecordMutationResult:
    """单条 wait record CAS mutation 结果。

    :param status: mutation 结果分类。
    :param row: mutation 后读取到的最新 wait record row；缺失时为 ``None``。
    """

    status: StateMutationStatus
    row: WaitRecordRow | None


@dataclass(frozen=True, slots=True)
class WaitRecordsMutationResult:
    """多条 wait record CAS mutation 结果。

    :param status: mutation 结果分类。
    :param rows: mutation 后读取到的 wait record rows。
    """

    status: StateMutationStatus
    rows: tuple[WaitRecordRow, ...]


def serialize_session_status(status: SessionStatus) -> str:
    """序列化公共 Session 状态。

    :param status: 公共 Session status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``SessionStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="SessionStatus")


def deserialize_session_status(value: str) -> SessionStatus:
    """反序列化公共 Session 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``SessionStatus``。
    :raises HostDurableError: 文本为空或不属于 ``SessionStatus`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=SessionStatus, enum_name="SessionStatus"
    )


def serialize_run_status(status: RunStatus) -> str:
    """序列化公共 Run 状态。

    :param status: 公共 Run status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``RunStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="RunStatus")


def deserialize_run_status(value: str) -> RunStatus:
    """反序列化公共 Run 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``RunStatus``。
    :raises HostDurableError: 文本为空或不属于 ``RunStatus`` 时抛出。
    """

    return _deserialize_str_enum(value, enum_type=RunStatus, enum_name="RunStatus")


def serialize_attempt_status(status: AttemptStatus) -> str:
    """序列化公共 Attempt 状态。

    :param status: 公共 Attempt status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``AttemptStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="AttemptStatus")


def deserialize_attempt_status(value: str) -> AttemptStatus:
    """反序列化公共 Attempt 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``AttemptStatus``。
    :raises HostDurableError: 文本为空或不属于 ``AttemptStatus`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=AttemptStatus, enum_name="AttemptStatus"
    )


def serialize_dispatch_record_status(status: DispatchRecordStatus) -> str:
    """序列化 dispatch record 状态。

    :param status: dispatch record status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``DispatchRecordStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="DispatchRecordStatus")


def deserialize_dispatch_record_status(value: str) -> DispatchRecordStatus:
    """反序列化 dispatch record 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``DispatchRecordStatus``。
    :raises HostDurableError: 文本为空或不属于 ``DispatchRecordStatus`` 时抛出。
    """

    return _deserialize_str_enum(
        value,
        enum_type=DispatchRecordStatus,
        enum_name="DispatchRecordStatus",
    )


def serialize_worker_kind(worker_kind: WorkerKind) -> str:
    """序列化 worker kind。

    :param worker_kind: worker kind enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``worker_kind`` 不是合法 ``WorkerKind`` 时抛出。
    """

    return _serialize_str_enum(worker_kind, enum_name="WorkerKind")


def deserialize_worker_kind(value: str) -> WorkerKind:
    """反序列化 worker kind。

    :param value: SQLite row 中读取的 worker kind 文本。
    :returns: ``WorkerKind``。
    :raises HostDurableError: 文本为空或不属于 ``WorkerKind`` 时抛出。
    """

    return _deserialize_str_enum(value, enum_type=WorkerKind, enum_name="WorkerKind")


def serialize_run_start_reason(reason: RunStartReason) -> str:
    """序列化 Run start reason。

    :param reason: Run start reason enum。
    :returns: canonical event payload 中使用的文本值。
    :raises HostDurableError: ``reason`` 不是合法 ``RunStartReason`` 时抛出。
    """

    return _serialize_str_enum(reason, enum_name="RunStartReason")


def deserialize_run_start_reason(value: str) -> RunStartReason:
    """反序列化 Run start reason。

    :param value: canonical event payload 中读取的 reason 文本。
    :returns: ``RunStartReason``。
    :raises HostDurableError: 文本为空或不属于 ``RunStartReason`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=RunStartReason, enum_name="RunStartReason"
    )


def serialize_wait_record_status(status: WaitRecordStatus) -> str:
    """序列化 wait record 状态。

    :param status: wait record status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``WaitRecordStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="WaitRecordStatus")


def deserialize_wait_record_status(value: str) -> WaitRecordStatus:
    """反序列化 wait record 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``WaitRecordStatus``。
    :raises HostDurableError: 文本为空或不属于 ``WaitRecordStatus`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=WaitRecordStatus, enum_name="WaitRecordStatus"
    )


def serialize_wait_resume_policy(policy: WaitResumePolicy) -> str:
    """序列化等待恢复策略。

    :param policy: wait resume policy enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``policy`` 不是合法 ``WaitResumePolicy`` 时抛出。
    """

    return _serialize_str_enum(policy, enum_name="WaitResumePolicy")


def deserialize_wait_resume_policy(value: str) -> WaitResumePolicy:
    """反序列化等待恢复策略。

    :param value: SQLite row 中读取的恢复策略文本。
    :returns: ``WaitResumePolicy``。
    :raises HostDurableError: 文本为空或不属于 ``WaitResumePolicy`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=WaitResumePolicy, enum_name="WaitResumePolicy"
    )


def serialize_wait_snapshot_ref(ref: WaitSnapshotRef | None) -> str | None:
    """序列化 wait snapshot ref 的 id 列。

    :param ref: wait snapshot ref 或 ``None``。
    :returns: snapshot id 或 ``None``。
    """

    if ref is None:
        return None
    return ref.snapshot_id


def serialize_wait_snapshot_captured_at(ref: WaitSnapshotRef | None) -> str | None:
    """序列化 wait snapshot ref 的采集时间列。

    :param ref: wait snapshot ref 或 ``None``。
    :returns: 固定 UTC timestamp 文本或 ``None``。
    """

    if ref is None:
        return None
    return format_utc_timestamp(ref.captured_at)


def serialize_wait_snapshot_digest(ref: WaitSnapshotRef | None) -> str | None:
    """序列化 wait snapshot ref 的摘要列。

    :param ref: wait snapshot ref 或 ``None``。
    :returns: snapshot digest 或 ``None``。
    """

    if ref is None:
        return None
    return ref.snapshot_digest


def deserialize_wait_snapshot_ref(
    snapshot_id: str | None,
    captured_at: str | None,
    snapshot_digest: str | None,
) -> WaitSnapshotRef | None:
    """从 SQLite 三列反序列化 wait snapshot ref。

    :param snapshot_id: snapshot id 列。
    :param captured_at: snapshot 采集时间列。
    :param snapshot_digest: snapshot digest 列。
    :returns: ``WaitSnapshotRef`` 或 ``None``。
    :raises HostDurableError: nullable 字段组合或 timestamp 格式非法时抛出。
    """

    if snapshot_id is None and captured_at is None and snapshot_digest is None:
        return None
    if snapshot_id is None or captured_at is None:
        raise HostDurableError("snapshot ref columns must be paired")
    try:
        parsed = parse_utc_timestamp(captured_at)
    except ValueError as exc:
        raise HostDurableError("snapshot_captured_at is invalid") from exc
    return WaitSnapshotRef(
        snapshot_id=snapshot_id,
        captured_at=parsed,
        snapshot_digest=snapshot_digest,
    )


def serialize_external_job_id(ref: ExternalJobRef | None) -> str | None:
    """序列化外部 job 引用的 id 列。

    :param ref: 外部 job 引用或 ``None``。
    :returns: external job id 或 ``None``。
    """

    if ref is None:
        return None
    return ref.external_job_id


def deserialize_external_job_ref(
    adapter_key: WaitAdapterKey, external_job_id: str | None
) -> ExternalJobRef | None:
    """从 adapter key 与外部 job id 列反序列化外部 job 引用。

    :param adapter_key: wait record adapter key。
    :param external_job_id: SQLite external job id 列。
    :returns: ``ExternalJobRef`` 或 ``None``。
    :raises HostDurableError: external job id 非法时抛出。
    """

    if external_job_id is None:
        return None
    return ExternalJobRef(adapter_key=adapter_key, external_job_id=external_job_id)


def session_row_from_host_row(row: HostRow) -> SessionRow:
    """把通用 HostRow 转换为 SessionRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``SessionRow``。
    :raises HostDurableError: row 字段类型或状态 enum 值无效时抛出。
    """

    return SessionRow(
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        status=deserialize_session_status(
            _require_text(row.get("status"), field_name="status")
        ),
        metadata_json=_require_text(row.get("metadata_json"), field_name="metadata_json"),
        created_event_id=_require_text(
            row.get("created_event_id"), field_name="created_event_id"
        ),
        created_event_sequence=_require_int(
            row.get("created_event_sequence"), field_name="created_event_sequence"
        ),
        closed_event_id=_optional_text(
            row.get("closed_event_id"), field_name="closed_event_id"
        ),
        closed_event_sequence=_optional_int(
            row.get("closed_event_sequence"), field_name="closed_event_sequence"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        closed_at=_optional_text(row.get("closed_at"), field_name="closed_at"),
    )


def session_slot_row_from_host_row(row: HostRow) -> SessionSlotRow:
    """把通用 HostRow 转换为 SessionSlotRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``SessionSlotRow``。
    :raises HostDurableError: row 字段类型无效时抛出。
    """

    return SessionSlotRow(
        scope=_require_text(row.get("scope"), field_name="scope"),
        slot_key=_require_text(row.get("slot_key"), field_name="slot_key"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        bound_event_id=_require_text(
            row.get("bound_event_id"), field_name="bound_event_id"
        ),
        bound_event_sequence=_require_int(
            row.get("bound_event_sequence"), field_name="bound_event_sequence"
        ),
        metadata_json=_require_text(row.get("metadata_json"), field_name="metadata_json"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
    )


def run_row_from_host_row(row: HostRow) -> RunRow:
    """把通用 HostRow 转换为 RunRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``RunRow``。
    :raises HostDurableError: row 字段类型或状态 enum 值无效时抛出。
    """

    source_relation_text = _optional_text(
        row.get("source_run_relation"), field_name="source_run_relation"
    )
    return RunRow(
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        status=deserialize_run_status(
            _require_text(row.get("status"), field_name="status")
        ),
        client_request_id=_require_text(
            row.get("client_request_id"), field_name="client_request_id"
        ),
        input_event_id=_require_text(
            row.get("input_event_id"), field_name="input_event_id"
        ),
        input_event_sequence=_require_int(
            row.get("input_event_sequence"), field_name="input_event_sequence"
        ),
        accepted_event_id=_require_text(
            row.get("accepted_event_id"), field_name="accepted_event_id"
        ),
        accepted_event_sequence=_require_int(
            row.get("accepted_event_sequence"), field_name="accepted_event_sequence"
        ),
        queued_event_id=_optional_text(
            row.get("queued_event_id"), field_name="queued_event_id"
        ),
        queued_event_sequence=_optional_int(
            row.get("queued_event_sequence"), field_name="queued_event_sequence"
        ),
        started_event_id=_optional_text(
            row.get("started_event_id"), field_name="started_event_id"
        ),
        started_event_sequence=_optional_int(
            row.get("started_event_sequence"), field_name="started_event_sequence"
        ),
        terminal_event_id=_optional_text(
            row.get("terminal_event_id"), field_name="terminal_event_id"
        ),
        terminal_event_sequence=_optional_int(
            row.get("terminal_event_sequence"), field_name="terminal_event_sequence"
        ),
        current_attempt_id=_optional_text(
            row.get("current_attempt_id"), field_name="current_attempt_id"
        ),
        source_run_id=_optional_text(
            row.get("source_run_id"), field_name="source_run_id"
        ),
        source_run_relation=_optional_source_run_relation(source_relation_text),
        execution_target=_require_text(
            row.get("execution_target"), field_name="execution_target"
        ),
        queue_policy=_require_text(row.get("queue_policy"), field_name="queue_policy"),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
        terminal_at=_optional_text(row.get("terminal_at"), field_name="terminal_at"),
    )


def attempt_row_from_host_row(row: HostRow) -> AttemptRow:
    """把通用 HostRow 转换为 AttemptRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``AttemptRow``。
    :raises HostDurableError: row 字段类型或状态 enum 值无效时抛出。
    """

    return AttemptRow(
        attempt_id=_require_text(row.get("attempt_id"), field_name="attempt_id"),
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        execution_id=_require_text(row.get("execution_id"), field_name="execution_id"),
        status=deserialize_attempt_status(
            _require_text(row.get("status"), field_name="status")
        ),
        started_event_id=_require_text(
            row.get("started_event_id"), field_name="started_event_id"
        ),
        started_event_sequence=_require_int(
            row.get("started_event_sequence"), field_name="started_event_sequence"
        ),
        terminal_event_id=_optional_text(
            row.get("terminal_event_id"), field_name="terminal_event_id"
        ),
        terminal_event_sequence=_optional_int(
            row.get("terminal_event_sequence"), field_name="terminal_event_sequence"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
        terminal_at=_optional_text(row.get("terminal_at"), field_name="terminal_at"),
    )


def dispatch_record_row_from_host_row(row: HostRow) -> DispatchRecordRow:
    """把通用 HostRow 转换为 DispatchRecordRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``DispatchRecordRow``。
    :raises HostDurableError: row 字段类型或状态 enum 值无效时抛出。
    """

    return DispatchRecordRow(
        dispatch_record_id=_require_text(
            row.get("dispatch_record_id"), field_name="dispatch_record_id"
        ),
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        attempt_id=_require_text(row.get("attempt_id"), field_name="attempt_id"),
        execution_id=_require_text(row.get("execution_id"), field_name="execution_id"),
        status=deserialize_dispatch_record_status(
            _require_text(row.get("status"), field_name="status")
        ),
        worker_kind=deserialize_worker_kind(
            _require_text(row.get("worker_kind"), field_name="worker_kind")
        ),
        execution_target=_require_text(
            row.get("execution_target"), field_name="execution_target"
        ),
        owner_host_instance_id=_optional_text(
            row.get("owner_host_instance_id"), field_name="owner_host_instance_id"
        ),
        created_event_id=_require_text(
            row.get("created_event_id"), field_name="created_event_id"
        ),
        created_event_sequence=_require_int(
            row.get("created_event_sequence"), field_name="created_event_sequence"
        ),
        waiting_for_lane_at=_optional_text(
            row.get("waiting_for_lane_at"), field_name="waiting_for_lane_at"
        ),
        lane_name=_optional_text(row.get("lane_name"), field_name="lane_name"),
        lane_claim_id=_optional_text(
            row.get("lane_claim_id"), field_name="lane_claim_id"
        ),
        lane_owner_id=_optional_text(
            row.get("lane_owner_id"), field_name="lane_owner_id"
        ),
        lane_acquired_at=_optional_text(
            row.get("lane_acquired_at"), field_name="lane_acquired_at"
        ),
        dispatching_at=_optional_text(
            row.get("dispatching_at"), field_name="dispatching_at"
        ),
        worker_accepted_at=_optional_text(
            row.get("worker_accepted_at"), field_name="worker_accepted_at"
        ),
        worker_accept_event_id=_optional_text(
            row.get("worker_accept_event_id"), field_name="worker_accept_event_id"
        ),
        worker_accept_event_sequence=_optional_int(
            row.get("worker_accept_event_sequence"),
            field_name="worker_accept_event_sequence",
        ),
        cancelled_event_id=_optional_text(
            row.get("cancelled_event_id"), field_name="cancelled_event_id"
        ),
        cancelled_event_sequence=_optional_int(
            row.get("cancelled_event_sequence"), field_name="cancelled_event_sequence"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
        cancelled_at=_optional_text(row.get("cancelled_at"), field_name="cancelled_at"),
    )


def wait_record_row_from_host_row(row: HostRow) -> WaitRecordRow:
    """把通用 HostRow 转换为 WaitRecordRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``WaitRecordRow``。
    :raises HostDurableError: row 字段类型、状态 enum 或 typed ref 无效时抛出。
    """

    adapter_key = _wait_adapter_key_from_text(
        _require_text(row.get("adapter_key"), field_name="adapter_key")
    )
    snapshot_ref = deserialize_wait_snapshot_ref(
        _optional_text(row.get("snapshot_ref"), field_name="snapshot_ref"),
        _optional_text(
            row.get("snapshot_captured_at"), field_name="snapshot_captured_at"
        ),
        _optional_text(row.get("snapshot_digest"), field_name="snapshot_digest"),
    )
    external_job_ref = deserialize_external_job_ref(
        adapter_key,
        _optional_text(row.get("external_job_id"), field_name="external_job_id"),
    )
    return WaitRecordRow(
        wait_id=_require_text(row.get("wait_id"), field_name="wait_id"),
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        run_id=_require_text(row.get("run_id"), field_name="run_id"),
        attempt_id=_require_text(row.get("attempt_id"), field_name="attempt_id"),
        execution_id=_require_text(row.get("execution_id"), field_name="execution_id"),
        tool_call_id=_require_text(row.get("tool_call_id"), field_name="tool_call_id"),
        tool_name=_require_text(row.get("tool_name"), field_name="tool_name"),
        adapter_key=adapter_key,
        await_kind=_require_text(row.get("await_kind"), field_name="await_kind"),
        resume_policy=deserialize_wait_resume_policy(
            _require_text(row.get("resume_policy"), field_name="resume_policy")
        ),
        resume_token=_require_text(row.get("resume_token"), field_name="resume_token"),
        snapshot_ref=snapshot_ref,
        external_job_ref=external_job_ref,
        accept_idempotency_key=_require_text(
            row.get("accept_idempotency_key"), field_name="accept_idempotency_key"
        ),
        resolve_idempotency_key=_optional_text(
            row.get("resolve_idempotency_key"),
            field_name="resolve_idempotency_key",
        ),
        resolve_semantic_digest=_optional_text(
            row.get("resolve_semantic_digest"),
            field_name="resolve_semantic_digest",
        ),
        deadline_at=_optional_text(row.get("deadline_at"), field_name="deadline_at"),
        expires_at=_optional_text(row.get("expires_at"), field_name="expires_at"),
        status=deserialize_wait_record_status(
            _require_text(row.get("status"), field_name="status")
        ),
        created_event_id=_require_text(
            row.get("created_event_id"), field_name="created_event_id"
        ),
        created_event_sequence=_require_int(
            row.get("created_event_sequence"), field_name="created_event_sequence"
        ),
        updated_event_id=_require_text(
            row.get("updated_event_id"), field_name="updated_event_id"
        ),
        updated_event_sequence=_require_int(
            row.get("updated_event_sequence"), field_name="updated_event_sequence"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
        terminal_at=_optional_text(row.get("terminal_at"), field_name="terminal_at"),
    )


def read_session_by_id(
    transaction: HostTransaction, session_id: str
) -> SessionRow | None:
    """按 Session id 读取 Session row。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 找到时返回 ``SessionRow``，否则返回 ``None``。
    :raises HostDurableError: ``session_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    row = transaction.fetchone(
        f"""
        SELECT
          session_id,
          status,
          metadata_json,
          created_event_id,
          created_event_sequence,
          closed_event_id,
          closed_event_sequence,
          created_at,
          closed_at
        FROM {TABLE_HOST_SESSIONS}
        WHERE session_id = ?
        """,
        (session_id,),
    )
    if row is None:
        return None
    return session_row_from_host_row(row)


def read_session_slot(
    transaction: HostTransaction, scope: str, slot_key: str
) -> SessionSlotRow | None:
    """按 ``(scope, slot_key)`` 读取 Session slot row。

    :param transaction: 调用方提供的 Host transaction。
    :param scope: slot 命名空间。
    :param slot_key: slot 稳定键。
    :returns: 找到时返回 ``SessionSlotRow``，否则返回 ``None``。
    :raises HostDurableError: ``scope`` 或 ``slot_key`` 为空时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(scope, field_name="scope")
    _require_non_empty_text(slot_key, field_name="slot_key")
    row = transaction.fetchone(
        f"""
        SELECT
          scope,
          slot_key,
          session_id,
          bound_event_id,
          bound_event_sequence,
          metadata_json,
          updated_at
        FROM {TABLE_HOST_SESSION_SLOTS}
        WHERE scope = ? AND slot_key = ?
        """,
        (scope, slot_key),
    )
    if row is None:
        return None
    return session_slot_row_from_host_row(row)


def read_session_slot_by_session_id(
    transaction: HostTransaction, session_id: str
) -> SessionSlotRow | None:
    """读取当前绑定到指定 Session 的 slot row。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 找到时返回 ``SessionSlotRow``，否则返回 ``None``。
    :raises HostDurableError: ``session_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    row = transaction.fetchone(
        f"""
        SELECT
          scope,
          slot_key,
          session_id,
          bound_event_id,
          bound_event_sequence,
          metadata_json,
          updated_at
        FROM {TABLE_HOST_SESSION_SLOTS}
        WHERE session_id = ?
        ORDER BY updated_at DESC, scope ASC, slot_key ASC
        LIMIT 1
        """,
        (session_id,),
    )
    if row is None:
        return None
    return session_slot_row_from_host_row(row)


def read_run_by_id(transaction: HostTransaction, run_id: str) -> RunRow | None:
    """按 Run id 读取 Run row。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :returns: 找到时返回 ``RunRow``，否则返回 ``None``。
    :raises HostDurableError: ``run_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    row = transaction.fetchone(
        f"""
        SELECT
          run_id,
          session_id,
          status,
          client_request_id,
          input_event_id,
          input_event_sequence,
          accepted_event_id,
          accepted_event_sequence,
          queued_event_id,
          queued_event_sequence,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        FROM {TABLE_HOST_RUNS}
        WHERE run_id = ?
        """,
        (run_id,),
    )
    if row is None:
        return None
    return run_row_from_host_row(row)


def read_active_run_for_session(
    transaction: HostTransaction, session_id: str
) -> RunRow | None:
    """读取 Session 当前 active Run。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 有 active Run 时返回 ``RunRow``，否则返回 ``None``。
    :raises HostDurableError: ``session_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    row = transaction.fetchone(
        f"""
        SELECT
          run_id,
          session_id,
          status,
          client_request_id,
          input_event_id,
          input_event_sequence,
          accepted_event_id,
          accepted_event_sequence,
          queued_event_id,
          queued_event_sequence,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ?
          AND status IN (?, ?, ?, ?)
        ORDER BY accepted_event_sequence ASC, run_id ASC
        LIMIT 1
        """,
        (
            session_id,
            serialize_run_status(RunStatus.RUNNING),
            serialize_run_status(RunStatus.WAITING),
            serialize_run_status(RunStatus.CANCELLING),
            serialize_run_status(RunStatus.RECOVERING),
        ),
    )
    if row is None:
        return None
    return run_row_from_host_row(row)


def read_earliest_queued_run(
    transaction: HostTransaction, session_id: str
) -> RunRow | None:
    """读取 Session 下最早 accepted 的 queued Run。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 有 queued Run 时返回最早 row，否则返回 ``None``。
    :raises HostDurableError: ``session_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    row = transaction.fetchone(
        f"""
        SELECT
          run_id,
          session_id,
          status,
          client_request_id,
          input_event_id,
          input_event_sequence,
          accepted_event_id,
          accepted_event_sequence,
          queued_event_id,
          queued_event_sequence,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ? AND status = ?
        ORDER BY accepted_event_sequence ASC, run_id ASC
        LIMIT 1
        """,
        (session_id, serialize_run_status(RunStatus.QUEUED)),
    )
    if row is None:
        return None
    return run_row_from_host_row(row)


def read_non_terminal_runs_for_session(
    transaction: HostTransaction, session_id: str
) -> tuple[RunRow, ...]:
    """读取指定 Session 下所有非终态 Run。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 按 accepted event sequence 升序排列的非终态 Run row 元组。
    :raises HostDurableError: ``session_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    rows = transaction.fetchall(
        f"""
        SELECT
          run_id,
          session_id,
          status,
          client_request_id,
          input_event_id,
          input_event_sequence,
          accepted_event_id,
          accepted_event_sequence,
          queued_event_id,
          queued_event_sequence,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ?
          AND status IN (?, ?, ?, ?, ?)
        ORDER BY accepted_event_sequence ASC, run_id ASC
        """,
        (
            session_id,
            serialize_run_status(RunStatus.QUEUED),
            serialize_run_status(RunStatus.RUNNING),
            serialize_run_status(RunStatus.WAITING),
            serialize_run_status(RunStatus.CANCELLING),
            serialize_run_status(RunStatus.RECOVERING),
        ),
    )
    return tuple(run_row_from_host_row(row) for row in rows)


def read_attempt_by_id(
    transaction: HostTransaction, attempt_id: str
) -> AttemptRow | None:
    """按 Attempt id 读取 Attempt row。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: Attempt id。
    :returns: 找到时返回 ``AttemptRow``，否则返回 ``None``。
    :raises HostDurableError: ``attempt_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(attempt_id, field_name="attempt_id")
    row = transaction.fetchone(
        f"""
        SELECT
          attempt_id,
          run_id,
          execution_id,
          status,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          created_at,
          updated_at,
          terminal_at
        FROM {TABLE_HOST_ATTEMPTS}
        WHERE attempt_id = ?
        """,
        (attempt_id,),
    )
    if row is None:
        return None
    return attempt_row_from_host_row(row)


def read_dispatch_record_by_attempt_id(
    transaction: HostTransaction, attempt_id: str
) -> DispatchRecordRow | None:
    """按 Attempt id 读取 dispatch record row。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: Attempt id。
    :returns: 找到时返回 ``DispatchRecordRow``，否则返回 ``None``。
    :raises HostDurableError: ``attempt_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(attempt_id, field_name="attempt_id")
    row = transaction.fetchone(
        f"""
        SELECT
          dispatch_record_id,
          run_id,
          attempt_id,
          execution_id,
          status,
          worker_kind,
          execution_target,
          owner_host_instance_id,
          created_event_id,
          created_event_sequence,
          waiting_for_lane_at,
          lane_name,
          lane_claim_id,
          lane_owner_id,
          lane_acquired_at,
          dispatching_at,
          worker_accepted_at,
          worker_accept_event_id,
          worker_accept_event_sequence,
          cancelled_event_id,
          cancelled_event_sequence,
          created_at,
          updated_at,
          cancelled_at
        FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
        WHERE attempt_id = ?
        """,
        (attempt_id,),
    )
    if row is None:
        return None
    return dispatch_record_row_from_host_row(row)


def read_dispatch_record_by_id(
    transaction: HostTransaction, dispatch_record_id: str
) -> DispatchRecordRow | None:
    """按 dispatch record id 读取 dispatch record row。

    :param transaction: 调用方提供的 Host transaction。
    :param dispatch_record_id: dispatch record id。
    :returns: 找到时返回 ``DispatchRecordRow``，否则返回 ``None``。
    :raises HostDurableError: ``dispatch_record_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(
        dispatch_record_id, field_name="dispatch_record_id"
    )
    row = transaction.fetchone(
        f"""
        SELECT
          dispatch_record_id,
          run_id,
          attempt_id,
          execution_id,
          status,
          worker_kind,
          execution_target,
          owner_host_instance_id,
          created_event_id,
          created_event_sequence,
          waiting_for_lane_at,
          lane_name,
          lane_claim_id,
          lane_owner_id,
          lane_acquired_at,
          dispatching_at,
          worker_accepted_at,
          worker_accept_event_id,
          worker_accept_event_sequence,
          cancelled_event_id,
          cancelled_event_sequence,
          created_at,
          updated_at,
          cancelled_at
        FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
        WHERE dispatch_record_id = ?
        """,
        (dispatch_record_id,),
    )
    if row is None:
        return None
    return dispatch_record_row_from_host_row(row)


def read_wait_record_by_id(
    transaction: HostTransaction, wait_id: str
) -> WaitRecordRow | None:
    """按 wait id 读取 wait record row。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :returns: 找到时返回 ``WaitRecordRow``，否则返回 ``None``。
    :raises HostDurableError: ``wait_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(wait_id, field_name="wait_id")
    row = transaction.fetchone(
        _WAIT_RECORD_SELECT_SQL + " WHERE wait_id = ?",
        (wait_id,),
    )
    if row is None:
        return None
    return wait_record_row_from_host_row(row)


def read_active_wait_records_for_run(
    transaction: HostTransaction, run_id: str
) -> tuple[WaitRecordRow, ...]:
    """读取 Run 下仍处于 waiting 的 wait records。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :returns: active wait record 元组，按创建事件序号升序排列。
    :raises HostDurableError: ``run_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    rows = transaction.fetchall(
        _WAIT_RECORD_SELECT_SQL
        + """
        WHERE run_id = ? AND status = ?
        ORDER BY created_event_sequence ASC, wait_id ASC
        """,
        (run_id, serialize_wait_record_status(WaitRecordStatus.WAITING)),
    )
    return tuple(wait_record_row_from_host_row(row) for row in rows)


def read_wait_records_for_poll_observation(
    transaction: HostTransaction,
) -> tuple[WaitRecordRow, ...]:
    """读取 poller 本轮可观察的 wait records。

    本 helper 只返回 ``resume_policy=poll`` 且状态仍需 poller 处理的 row。
    ``cancelled`` row 用于让 adapter 放弃外部 job；调用方不得把它交给
    ``resolve_wait``。

    :param transaction: 调用方提供的 Host transaction。
    :returns: poller 可观察 wait record 元组。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    rows = transaction.fetchall(
        _WAIT_RECORD_SELECT_SQL
        + """
        WHERE resume_policy = ?
          AND status IN (?, ?)
        ORDER BY created_event_sequence ASC, wait_id ASC
        """,
        (
            serialize_wait_resume_policy(WaitResumePolicy.POLL),
            serialize_wait_record_status(WaitRecordStatus.WAITING),
            serialize_wait_record_status(WaitRecordStatus.CANCELLED),
        ),
    )
    return tuple(wait_record_row_from_host_row(row) for row in rows)


def insert_session(
    transaction: HostTransaction, session: SessionRow
) -> None:
    """插入 Session row。

    :param transaction: 调用方提供的 Host transaction。
    :param session: 待插入的 Session row。
    :returns: ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_session_for_insert(session)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSIONS} (
          session_id,
          status,
          metadata_json,
          created_event_id,
          created_event_sequence,
          closed_event_id,
          closed_event_sequence,
          created_at,
          closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session.session_id,
            serialize_session_status(session.status),
            session.metadata_json,
            session.created_event_id,
            session.created_event_sequence,
            session.closed_event_id,
            session.closed_event_sequence,
            session.created_at,
            session.closed_at,
        ),
    )


def insert_session_slot(
    transaction: HostTransaction, slot: SessionSlotRow
) -> None:
    """插入 Session slot row。

    :param transaction: 调用方提供的 Host transaction。
    :param slot: 待插入的 slot row。
    :returns: ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_session_slot(slot)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSION_SLOTS} (
          scope,
          slot_key,
          session_id,
          bound_event_id,
          bound_event_sequence,
          metadata_json,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slot.scope,
            slot.slot_key,
            slot.session_id,
            slot.bound_event_id,
            slot.bound_event_sequence,
            slot.metadata_json,
            slot.updated_at,
        ),
    )


def upsert_session_slot(
    transaction: HostTransaction, slot: SessionSlotRow
) -> None:
    """插入或重绑定 Session slot row。

    :param transaction: 调用方提供的 Host transaction。
    :param slot: 新的 slot binding row。
    :returns: ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_session_slot(slot)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSION_SLOTS} (
          scope,
          slot_key,
          session_id,
          bound_event_id,
          bound_event_sequence,
          metadata_json,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scope, slot_key) DO UPDATE SET
          session_id = excluded.session_id,
          bound_event_id = excluded.bound_event_id,
          bound_event_sequence = excluded.bound_event_sequence,
          metadata_json = excluded.metadata_json,
          updated_at = excluded.updated_at
        """,
        (
            slot.scope,
            slot.slot_key,
            slot.session_id,
            slot.bound_event_id,
            slot.bound_event_sequence,
            slot.metadata_json,
            slot.updated_at,
        ),
    )


def close_open_session_row(
    transaction: HostTransaction,
    *,
    session_id: str,
    closed_event_id: str,
    closed_event_sequence: int,
    closed_at: str,
) -> bool:
    """CAS 关闭 open Session row。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: 目标 Session id。
    :param closed_event_id: ``SESSION_CLOSED`` 事件 id。
    :param closed_event_sequence: ``SESSION_CLOSED`` 全局事件序号。
    :param closed_at: 固定 UTC timestamp 文本。
    :returns: 更新到一行时返回 ``True``，CAS loser 或非 open 状态返回 ``False``。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(closed_event_id, field_name="closed_event_id")
    if closed_event_sequence <= 0:
        raise HostDurableError("closed_event_sequence must be positive")
    _require_non_empty_text(closed_at, field_name="closed_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_SESSIONS}
        SET
          status = ?,
          closed_event_id = ?,
          closed_event_sequence = ?,
          closed_at = ?
        WHERE session_id = ? AND status = ?
        """,
        (
            serialize_session_status(SessionStatus.CLOSED),
            closed_event_id,
            closed_event_sequence,
            closed_at,
            session_id,
            serialize_session_status(SessionStatus.OPEN),
        ),
    )
    return result.rowcount == 1


def insert_run(transaction: HostTransaction, run: RunRow) -> None:
    """插入 Run row。

    :param transaction: 调用方提供的 Host transaction。
    :param run: 待插入的 Run row。
    :returns: ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_run_for_insert(run)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_RUNS} (
          run_id,
          session_id,
          status,
          client_request_id,
          input_event_id,
          input_event_sequence,
          accepted_event_id,
          accepted_event_sequence,
          queued_event_id,
          queued_event_sequence,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.run_id,
            run.session_id,
            serialize_run_status(run.status),
            run.client_request_id,
            run.input_event_id,
            run.input_event_sequence,
            run.accepted_event_id,
            run.accepted_event_sequence,
            run.queued_event_id,
            run.queued_event_sequence,
            run.started_event_id,
            run.started_event_sequence,
            run.terminal_event_id,
            run.terminal_event_sequence,
            run.current_attempt_id,
            run.source_run_id,
            _optional_source_run_relation_text(run.source_run_relation),
            run.execution_target,
            run.queue_policy,
            run.created_at,
            run.updated_at,
            run.terminal_at,
        ),
    )


def insert_attempt(transaction: HostTransaction, attempt: AttemptRow) -> None:
    """插入 Attempt row。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt: 待插入的 Attempt row。
    :returns: ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_attempt_for_insert(attempt)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_ATTEMPTS} (
          attempt_id,
          run_id,
          execution_id,
          status,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt.attempt_id,
            attempt.run_id,
            attempt.execution_id,
            serialize_attempt_status(attempt.status),
            attempt.started_event_id,
            attempt.started_event_sequence,
            attempt.terminal_event_id,
            attempt.terminal_event_sequence,
            attempt.created_at,
            attempt.updated_at,
            attempt.terminal_at,
        ),
    )


def insert_dispatch_record(
    transaction: HostTransaction, dispatch_record: DispatchRecordRow
) -> None:
    """插入 Attempt dispatch record row。

    :param transaction: 调用方提供的 Host transaction。
    :param dispatch_record: 待插入的 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_dispatch_record_for_insert(dispatch_record)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} (
          dispatch_record_id,
          run_id,
          attempt_id,
          execution_id,
          status,
          worker_kind,
          execution_target,
          owner_host_instance_id,
          created_event_id,
          created_event_sequence,
          waiting_for_lane_at,
          lane_name,
          lane_claim_id,
          lane_owner_id,
          lane_acquired_at,
          dispatching_at,
          worker_accepted_at,
          worker_accept_event_id,
          worker_accept_event_sequence,
          cancelled_event_id,
          cancelled_event_sequence,
          created_at,
          updated_at,
          cancelled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dispatch_record.dispatch_record_id,
            dispatch_record.run_id,
            dispatch_record.attempt_id,
            dispatch_record.execution_id,
            serialize_dispatch_record_status(dispatch_record.status),
            serialize_worker_kind(dispatch_record.worker_kind),
            dispatch_record.execution_target,
            dispatch_record.owner_host_instance_id,
            dispatch_record.created_event_id,
            dispatch_record.created_event_sequence,
            dispatch_record.waiting_for_lane_at,
            dispatch_record.lane_name,
            dispatch_record.lane_claim_id,
            dispatch_record.lane_owner_id,
            dispatch_record.lane_acquired_at,
            dispatch_record.dispatching_at,
            dispatch_record.worker_accepted_at,
            dispatch_record.worker_accept_event_id,
            dispatch_record.worker_accept_event_sequence,
            dispatch_record.cancelled_event_id,
            dispatch_record.cancelled_event_sequence,
            dispatch_record.created_at,
            dispatch_record.updated_at,
            dispatch_record.cancelled_at,
        ),
    )


def insert_wait_record(transaction: HostTransaction, row: WaitRecordRow) -> None:
    """插入 wait record row。

    :param transaction: 调用方提供的 Host transaction。
    :param row: 待插入的 wait record row。
    :returns: ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_wait_record_for_insert(row)
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_WAIT_RECORDS} (
          wait_id,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          adapter_key,
          await_kind,
          resume_policy,
          resume_token,
          snapshot_ref,
          snapshot_captured_at,
          snapshot_digest,
          external_job_id,
          accept_idempotency_key,
          resolve_idempotency_key,
          resolve_semantic_digest,
          deadline_at,
          expires_at,
          status,
          created_event_id,
          created_event_sequence,
          updated_event_id,
          updated_event_sequence,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.wait_id,
            row.session_id,
            row.run_id,
            row.attempt_id,
            row.execution_id,
            row.tool_call_id,
            row.tool_name,
            row.adapter_key.value,
            row.await_kind,
            serialize_wait_resume_policy(row.resume_policy),
            row.resume_token,
            serialize_wait_snapshot_ref(row.snapshot_ref),
            serialize_wait_snapshot_captured_at(row.snapshot_ref),
            serialize_wait_snapshot_digest(row.snapshot_ref),
            serialize_external_job_id(row.external_job_ref),
            row.accept_idempotency_key,
            row.resolve_idempotency_key,
            row.resolve_semantic_digest,
            row.deadline_at,
            row.expires_at,
            serialize_wait_record_status(row.status),
            row.created_event_id,
            row.created_event_sequence,
            row.updated_event_id,
            row.updated_event_sequence,
            row.created_at,
            row.updated_at,
            row.terminal_at,
        ),
    )


def mark_wait_record_resolved_row(
    transaction: HostTransaction,
    *,
    wait_id: str,
    resolve_idempotency_key: str,
    resolve_semantic_digest: str,
    updated_event_id: str,
    updated_event_sequence: int,
    updated_at: str,
    terminal_at: str,
) -> WaitRecordMutationResult:
    """CAS 标记 waiting wait record 为 resolved。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param resolve_idempotency_key: resolve wait 幂等键。
    :param resolve_semantic_digest: resolve wait 语义 digest。
    :param updated_event_id: 更新该 wait record 的事件 id。
    :param updated_event_sequence: 更新事件全局序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :param terminal_at: 固定 UTC 终态时间文本。
    :returns: wait record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    return _mark_wait_record_terminal_row(
        transaction,
        wait_id=wait_id,
        status=WaitRecordStatus.RESOLVED,
        resolve_idempotency_key=resolve_idempotency_key,
        resolve_semantic_digest=resolve_semantic_digest,
        updated_event_id=updated_event_id,
        updated_event_sequence=updated_event_sequence,
        updated_at=updated_at,
        terminal_at=terminal_at,
    )


def mark_wait_record_failed_row(
    transaction: HostTransaction,
    *,
    wait_id: str,
    resolve_idempotency_key: str,
    resolve_semantic_digest: str,
    updated_event_id: str,
    updated_event_sequence: int,
    updated_at: str,
    terminal_at: str,
) -> WaitRecordMutationResult:
    """CAS 标记 waiting wait record 为 failed。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param resolve_idempotency_key: resolve wait 幂等键。
    :param resolve_semantic_digest: resolve wait 语义 digest。
    :param updated_event_id: 更新该 wait record 的事件 id。
    :param updated_event_sequence: 更新事件全局序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :param terminal_at: 固定 UTC 终态时间文本。
    :returns: wait record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    return _mark_wait_record_terminal_row(
        transaction,
        wait_id=wait_id,
        status=WaitRecordStatus.FAILED,
        resolve_idempotency_key=resolve_idempotency_key,
        resolve_semantic_digest=resolve_semantic_digest,
        updated_event_id=updated_event_id,
        updated_event_sequence=updated_event_sequence,
        updated_at=updated_at,
        terminal_at=terminal_at,
    )


def mark_wait_record_cancelled_row(
    transaction: HostTransaction,
    *,
    wait_id: str,
    updated_event_id: str,
    updated_event_sequence: int,
    updated_at: str,
    terminal_at: str,
) -> WaitRecordMutationResult:
    """CAS 标记 waiting wait record 为 cancelled。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param updated_event_id: 更新该 wait record 的事件 id。
    :param updated_event_sequence: 更新事件全局序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :param terminal_at: 固定 UTC 终态时间文本。
    :returns: wait record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    return _mark_wait_record_terminal_row(
        transaction,
        wait_id=wait_id,
        status=WaitRecordStatus.CANCELLED,
        resolve_idempotency_key=None,
        resolve_semantic_digest=None,
        updated_event_id=updated_event_id,
        updated_event_sequence=updated_event_sequence,
        updated_at=updated_at,
        terminal_at=terminal_at,
    )


def mark_wait_record_lost_row(
    transaction: HostTransaction,
    *,
    wait_id: str,
    resolve_idempotency_key: str,
    resolve_semantic_digest: str,
    updated_event_id: str,
    updated_event_sequence: int,
    updated_at: str,
    terminal_at: str,
) -> WaitRecordMutationResult:
    """CAS 标记 waiting wait record 为 lost。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param resolve_idempotency_key: resolve wait 幂等键。
    :param resolve_semantic_digest: resolve wait 语义 digest。
    :param updated_event_id: 更新该 wait record 的事件 id。
    :param updated_event_sequence: 更新事件全局序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :param terminal_at: 固定 UTC 终态时间文本。
    :returns: wait record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    return _mark_wait_record_terminal_row(
        transaction,
        wait_id=wait_id,
        status=WaitRecordStatus.LOST,
        resolve_idempotency_key=resolve_idempotency_key,
        resolve_semantic_digest=resolve_semantic_digest,
        updated_event_id=updated_event_id,
        updated_event_sequence=updated_event_sequence,
        updated_at=updated_at,
        terminal_at=terminal_at,
    )


def cancel_active_wait_records_for_run(
    transaction: HostTransaction,
    *,
    run_id: str,
    updated_event_id: str,
    updated_event_sequence: int,
    updated_at: str,
    terminal_at: str,
) -> WaitRecordsMutationResult:
    """CAS 取消 Run 下全部 active wait records。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :param updated_event_id: 更新 wait records 的事件 id。
    :param updated_event_sequence: 更新事件全局序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :param terminal_at: 固定 UTC 终态时间文本。
    :returns: 多条 wait record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _validate_wait_batch_terminal_update(
        updated_event_id=updated_event_id,
        updated_event_sequence=updated_event_sequence,
        updated_at=updated_at,
        terminal_at=terminal_at,
    )
    before_rows = read_active_wait_records_for_run(transaction, run_id)
    if not before_rows:
        existing = _read_wait_record_count_for_run(transaction, run_id)
        status = (
            StateMutationStatus.INVALID_STATE
            if existing > 0
            else StateMutationStatus.NOT_FOUND
        )
        return WaitRecordsMutationResult(status=status, rows=())
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_WAIT_RECORDS}
        SET
          status = ?,
          updated_event_id = ?,
          updated_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ? AND status = ?
        """,
        (
            serialize_wait_record_status(WaitRecordStatus.CANCELLED),
            updated_event_id,
            updated_event_sequence,
            updated_at,
            terminal_at,
            run_id,
            serialize_wait_record_status(WaitRecordStatus.WAITING),
        ),
    )
    rows = _read_terminal_wait_records_for_run(
        transaction,
        run_id=run_id,
        updated_event_id=updated_event_id,
        updated_event_sequence=updated_event_sequence,
    )
    if result.rowcount == len(before_rows):
        return WaitRecordsMutationResult(
            status=StateMutationStatus.UPDATED, rows=rows
        )
    return WaitRecordsMutationResult(
        status=StateMutationStatus.CAS_LOST,
        rows=read_active_wait_records_for_run(transaction, run_id),
    )


def promote_queued_run_row(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    started_event_id: str,
    started_event_sequence: int,
    current_attempt_id: str,
    updated_at: str,
) -> RunMutationResult:
    """CAS 推进 queued Run 到 running。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Run 所属 Session id。
    :param run_id: 目标 Run id。
    :param started_event_id: ``RUN_STARTED`` 事件 id。
    :param started_event_sequence: ``RUN_STARTED`` 全局事件序号。
    :param current_attempt_id: 新建 current Attempt id。
    :param updated_at: 固定 UTC timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_run_start_update(
        session_id=session_id,
        run_id=run_id,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        current_attempt_id=current_attempt_id,
        updated_at=updated_at,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          started_event_id = ?,
          started_event_sequence = ?,
          current_attempt_id = ?,
          updated_at = ?
        WHERE run_id = ?
          AND session_id = ?
          AND status = ?
          AND NOT EXISTS (
            SELECT 1
            FROM {TABLE_HOST_RUNS} active_run
            WHERE active_run.session_id = ?
              AND active_run.run_id <> ?
              AND active_run.status IN (?, ?, ?, ?)
          )
        """,
        (
            serialize_run_status(RunStatus.RUNNING),
            started_event_id,
            started_event_sequence,
            current_attempt_id,
            updated_at,
            run_id,
            session_id,
            serialize_run_status(RunStatus.QUEUED),
            session_id,
            run_id,
            serialize_run_status(RunStatus.RUNNING),
            serialize_run_status(RunStatus.WAITING),
            serialize_run_status(RunStatus.CANCELLING),
            serialize_run_status(RunStatus.RECOVERING),
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.QUEUED,
        cas_lost_when_expected=True,
    )


def cancel_queued_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 取消 queued Run。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param terminal_event_id: ``RUN_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``RUN_CANCELLED`` 全局事件序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_run_terminal_update(
        run_id=run_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ? AND status = ?
        """,
        (
            serialize_run_status(RunStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(RunStatus.QUEUED),
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.QUEUED,
        cas_lost_when_expected=False,
    )


def cancel_running_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 取消 pre-dispatch running Run。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param terminal_event_id: ``RUN_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``RUN_CANCELLED`` 全局事件序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_run_terminal_update(
        run_id=run_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
        """,
        (
            serialize_run_status(RunStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(RunStatus.RUNNING),
            current_attempt_id,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.RUNNING,
        cas_lost_when_expected=True,
    )


def cancel_cancelling_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 将 active cancelling Run 收口为 cancelled。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param terminal_event_id: ``RUN_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``RUN_CANCELLED`` 全局事件序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_run_terminal_update(
        run_id=run_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
          AND terminal_event_id IS NULL
          AND terminal_event_sequence IS NULL
          AND terminal_at IS NULL
        """,
        (
            serialize_run_status(RunStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(RunStatus.CANCELLING),
            current_attempt_id,
        ),
    )
    return _run_mutation_result_for_active(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
    )


def mark_run_cancelling_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    updated_at: str,
) -> RunMutationResult:
    """CAS 将 active running Run 标记为 cancelling。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param updated_at: 固定 UTC timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    _require_non_empty_text(updated_at, field_name="updated_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          updated_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
          AND terminal_event_id IS NULL
          AND terminal_event_sequence IS NULL
          AND terminal_at IS NULL
        """,
        (
            serialize_run_status(RunStatus.CANCELLING),
            updated_at,
            run_id,
            serialize_run_status(RunStatus.RUNNING),
            current_attempt_id,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.RUNNING,
        cas_lost_when_expected=True,
    )


def mark_run_waiting_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    updated_at: str,
) -> RunMutationResult:
    """CAS 将 active running Run 标记为 waiting。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param updated_at: 固定 UTC timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    _require_non_empty_text(updated_at, field_name="updated_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          updated_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
          AND terminal_event_id IS NULL
          AND terminal_event_sequence IS NULL
          AND terminal_at IS NULL
        """,
        (
            serialize_run_status(RunStatus.WAITING),
            updated_at,
            run_id,
            serialize_run_status(RunStatus.RUNNING),
            current_attempt_id,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.RUNNING,
        cas_lost_when_expected=True,
    )


def resume_waiting_run_row(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    suspended_attempt_id: str,
    resumed_attempt_id: str,
    started_event_id: str,
    started_event_sequence: int,
    updated_at: str,
) -> RunMutationResult:
    """CAS 将 waiting Run 恢复为 running 并切换 current Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Run 所属 Session id。
    :param run_id: 目标 Run id。
    :param suspended_attempt_id: 期望的原 SUSPENDED Attempt id。
    :param resumed_attempt_id: 新建 resume Attempt id。
    :param started_event_id: ``RUN_STARTED`` resume 事件 id。
    :param started_event_sequence: ``RUN_STARTED`` resume 事件序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _validate_run_start_update(
        session_id=session_id,
        run_id=run_id,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        current_attempt_id=resumed_attempt_id,
        updated_at=updated_at,
    )
    _require_non_empty_text(
        suspended_attempt_id, field_name="suspended_attempt_id"
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          started_event_id = ?,
          started_event_sequence = ?,
          current_attempt_id = ?,
          updated_at = ?
        WHERE run_id = ?
          AND session_id = ?
          AND status = ?
          AND current_attempt_id = ?
          AND terminal_event_id IS NULL
          AND terminal_event_sequence IS NULL
          AND terminal_at IS NULL
          AND NOT EXISTS (
            SELECT 1
            FROM {TABLE_HOST_RUNS} active_run
            WHERE active_run.session_id = ?
              AND active_run.run_id <> ?
              AND active_run.status IN (?, ?, ?, ?)
          )
        """,
        (
            serialize_run_status(RunStatus.RUNNING),
            started_event_id,
            started_event_sequence,
            resumed_attempt_id,
            updated_at,
            run_id,
            session_id,
            serialize_run_status(RunStatus.WAITING),
            suspended_attempt_id,
            session_id,
            run_id,
            serialize_run_status(RunStatus.RUNNING),
            serialize_run_status(RunStatus.WAITING),
            serialize_run_status(RunStatus.CANCELLING),
            serialize_run_status(RunStatus.RECOVERING),
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.WAITING,
        cas_lost_when_expected=True,
    )


def cancel_waiting_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 取消 waiting Run。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 SUSPENDED Attempt id。
    :param terminal_event_id: ``RUN_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``RUN_CANCELLED`` 全局事件序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _validate_run_terminal_update(
        run_id=run_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
          AND terminal_event_id IS NULL
          AND terminal_event_sequence IS NULL
          AND terminal_at IS NULL
        """,
        (
            serialize_run_status(RunStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(RunStatus.WAITING),
            current_attempt_id,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.WAITING,
        cas_lost_when_expected=True,
    )


def terminal_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    terminal_status: RunStatus,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 将 active Run 推进到具体终态。

    ``WAITING`` 源状态是为后续 phase 的 wait resolve 路径预留；Phase 3
    调用方通过前置检查保证只会传入 ``RUNNING`` Run。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param terminal_status: 目标 Run 终态，只允许 succeeded/failed/lost。
    :param terminal_event_id: 具体 Run terminal event id。
    :param terminal_event_sequence: 具体 Run terminal event 全局序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段或 terminal status 无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    if terminal_status not in (
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.LOST,
    ):
        raise HostDurableError("terminal Run status is invalid")
    _validate_run_terminal_update(
        run_id=run_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status IN (?, ?)
          AND current_attempt_id = ?
        """,
        (
            serialize_run_status(terminal_status),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(RunStatus.RUNNING),
            serialize_run_status(RunStatus.WAITING),
            current_attempt_id,
        ),
    )
    return _run_mutation_result_for_active(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
    )


def terminal_attempt_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    terminal_status: AttemptStatus,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> AttemptMutationResult:
    """CAS 将 Attempt 推进到具体终态。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param terminal_status: 目标 Attempt 终态，只允许 succeeded/failed/lost。
    :param terminal_event_id: 具体 Attempt terminal event id。
    :param terminal_event_sequence: 具体 Attempt terminal event 全局序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Attempt mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段或 terminal status 无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    if terminal_status not in (
        AttemptStatus.SUCCEEDED,
        AttemptStatus.FAILED,
        AttemptStatus.LOST,
    ):
        raise HostDurableError("terminal Attempt status is invalid")
    _validate_attempt_terminal_update(
        attempt_id=attempt_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPTS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE attempt_id = ?
          AND status IN (?, ?)
        """,
        (
            serialize_attempt_status(terminal_status),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            attempt_id,
            serialize_attempt_status(AttemptStatus.STARTING),
            serialize_attempt_status(AttemptStatus.RUNNING),
        ),
    )
    return _attempt_mutation_result_for_active(
        transaction,
        attempt_id=attempt_id,
        rowcount=result.rowcount,
    )


def cancel_starting_attempt_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> AttemptMutationResult:
    """CAS 取消 STARTING Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param terminal_event_id: ``ATTEMPT_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``ATTEMPT_CANCELLED`` 全局事件序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Attempt mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_attempt_terminal_update(
        attempt_id=attempt_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPTS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE attempt_id = ? AND status = ?
        """,
        (
            serialize_attempt_status(AttemptStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            attempt_id,
            serialize_attempt_status(AttemptStatus.STARTING),
        ),
    )
    return _attempt_mutation_result(
        transaction,
        attempt_id=attempt_id,
        rowcount=result.rowcount,
        expected_status=AttemptStatus.STARTING,
        cas_lost_when_expected=False,
    )


def cancel_running_attempt_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> AttemptMutationResult:
    """CAS 取消 RUNNING Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param terminal_event_id: ``ATTEMPT_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``ATTEMPT_CANCELLED`` 全局事件序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Attempt mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_attempt_terminal_update(
        attempt_id=attempt_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPTS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE attempt_id = ?
          AND status = ?
          AND terminal_event_id IS NULL
          AND terminal_event_sequence IS NULL
          AND terminal_at IS NULL
        """,
        (
            serialize_attempt_status(AttemptStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            attempt_id,
            serialize_attempt_status(AttemptStatus.RUNNING),
        ),
    )
    return _attempt_mutation_result_for_active(
        transaction,
        attempt_id=attempt_id,
        rowcount=result.rowcount,
    )


def mark_attempt_running_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    updated_at: str,
) -> AttemptMutationResult:
    """CAS 将 STARTING Attempt 标记为 RUNNING。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param updated_at: 固定 UTC timestamp 文本。
    :returns: Attempt mutation 结果，只有 STARTING 源状态可成功。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(attempt_id, field_name="attempt_id")
    _require_non_empty_text(updated_at, field_name="updated_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPTS}
        SET
          status = ?,
          updated_at = ?
        WHERE attempt_id = ?
          AND status = ?
          AND terminal_event_id IS NULL
          AND terminal_event_sequence IS NULL
          AND terminal_at IS NULL
        """,
        (
            serialize_attempt_status(AttemptStatus.RUNNING),
            updated_at,
            attempt_id,
            serialize_attempt_status(AttemptStatus.STARTING),
        ),
    )
    return _attempt_mutation_result(
        transaction,
        attempt_id=attempt_id,
        rowcount=result.rowcount,
        expected_status=AttemptStatus.STARTING,
        cas_lost_when_expected=False,
    )


def mark_attempt_suspended_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> AttemptMutationResult:
    """CAS 将 RUNNING Attempt 标记为 SUSPENDED。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param terminal_event_id: ``ATTEMPT_SUSPENDED`` 事件 id。
    :param terminal_event_sequence: ``ATTEMPT_SUSPENDED`` 全局事件序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Attempt mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_attempt_terminal_update(
        attempt_id=attempt_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPTS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE attempt_id = ?
          AND status = ?
          AND terminal_event_id IS NULL
          AND terminal_event_sequence IS NULL
          AND terminal_at IS NULL
        """,
        (
            serialize_attempt_status(AttemptStatus.SUSPENDED),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            attempt_id,
            serialize_attempt_status(AttemptStatus.RUNNING),
        ),
    )
    return _attempt_mutation_result_for_active(
        transaction,
        attempt_id=attempt_id,
        rowcount=result.rowcount,
    )


def mark_dispatch_waiting_for_lane_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    owner_host_instance_id: str,
    lane_name: str,
    waiting_for_lane_at: str,
) -> DispatchRecordMutationResult:
    """CAS 将 pending dispatch record 标记为 waiting_for_lane。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param owner_host_instance_id: 记录本次调度诊断的 Host instance id。
    :param lane_name: 等待的 lane 名称。
    :param waiting_for_lane_at: 固定 UTC timestamp 文本。
    :returns: dispatch record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(attempt_id, field_name="attempt_id")
    _require_non_empty_text(
        owner_host_instance_id, field_name="owner_host_instance_id"
    )
    _require_non_empty_text(lane_name, field_name="lane_name")
    _require_non_empty_text(waiting_for_lane_at, field_name="waiting_for_lane_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
        SET
          status = ?,
          owner_host_instance_id = ?,
          waiting_for_lane_at = ?,
          lane_name = ?,
          updated_at = ?
        WHERE attempt_id = ?
          AND status = ?
          AND waiting_for_lane_at IS NULL
          AND lane_name IS NULL
          AND lane_claim_id IS NULL
          AND lane_owner_id IS NULL
          AND lane_acquired_at IS NULL
          AND dispatching_at IS NULL
          AND worker_accept_event_id IS NULL
          AND cancelled_event_id IS NULL
        """,
        (
            serialize_dispatch_record_status(DispatchRecordStatus.WAITING_FOR_LANE),
            owner_host_instance_id,
            waiting_for_lane_at,
            lane_name,
            waiting_for_lane_at,
            attempt_id,
            serialize_dispatch_record_status(DispatchRecordStatus.PENDING),
        ),
    )
    return _dispatch_record_mutation_result_for_dispatch_start(
        transaction, attempt_id=attempt_id, rowcount=result.rowcount
    )


def mark_dispatching_after_lane_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    owner_host_instance_id: str,
    lane_name: str,
    lane_claim_id: str,
    lane_owner_id: str,
    lane_acquired_at: str,
    dispatching_at: str,
) -> DispatchRecordMutationResult:
    """CAS 将 lane recheck 通过的 dispatch record 标记为 dispatching。

    该 helper 只接受 production scheduler 已完成 durable recheck 后的
    ``WAITING_FOR_LANE`` row，保留已写入的 waiting timestamp 与 lane name，
    只补齐 lane claim / owner / dispatching 诊断字段。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param owner_host_instance_id: 记录本次调度诊断的 Host instance id。
    :param lane_name: 已获得的 lane 名称。
    :param lane_claim_id: lane acquire claim id。
    :param lane_owner_id: lane token owner id。
    :param lane_acquired_at: lane acquire timestamp。
    :param dispatching_at: dispatching timestamp。
    :returns: dispatch record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(attempt_id, field_name="attempt_id")
    _require_non_empty_text(
        owner_host_instance_id, field_name="owner_host_instance_id"
    )
    _require_non_empty_text(lane_name, field_name="lane_name")
    _require_non_empty_text(lane_claim_id, field_name="lane_claim_id")
    _require_non_empty_text(lane_owner_id, field_name="lane_owner_id")
    _require_non_empty_text(lane_acquired_at, field_name="lane_acquired_at")
    _require_non_empty_text(dispatching_at, field_name="dispatching_at")
    invalid = _invalid_dispatching_after_lane_precondition(
        transaction,
        attempt_id=attempt_id,
        owner_host_instance_id=owner_host_instance_id,
        lane_name=lane_name,
    )
    if invalid is not None:
        return invalid
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
        SET
          status = ?,
          owner_host_instance_id = ?,
          lane_name = ?,
          lane_claim_id = ?,
          lane_owner_id = ?,
          lane_acquired_at = ?,
          dispatching_at = ?,
          updated_at = ?
        WHERE attempt_id = ?
          AND status = ?
          AND owner_host_instance_id = ?
          AND waiting_for_lane_at IS NOT NULL
          AND lane_name = ?
          AND lane_claim_id IS NULL
          AND lane_owner_id IS NULL
          AND lane_acquired_at IS NULL
          AND dispatching_at IS NULL
          AND worker_accepted_at IS NULL
          AND worker_accept_event_id IS NULL
          AND worker_accept_event_sequence IS NULL
          AND cancelled_event_id IS NULL
          AND cancelled_event_sequence IS NULL
        """,
        (
            serialize_dispatch_record_status(DispatchRecordStatus.DISPATCHING),
            owner_host_instance_id,
            lane_name,
            lane_claim_id,
            lane_owner_id,
            lane_acquired_at,
            dispatching_at,
            dispatching_at,
            attempt_id,
            serialize_dispatch_record_status(DispatchRecordStatus.WAITING_FOR_LANE),
            owner_host_instance_id,
            lane_name,
        ),
    )
    return _dispatch_record_mutation_result_for_lane_dispatching(
        transaction, attempt_id=attempt_id, rowcount=result.rowcount
    )


def mark_dispatch_worker_accepted_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    worker_accept_event_id: str,
    worker_accept_event_sequence: int,
    worker_accepted_at: str,
) -> DispatchRecordMutationResult:
    """CAS 记录 WorkerProxy accept refs，dispatch 状态保持 dispatching。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param worker_accept_event_id: ``ATTEMPT_RUNNING`` event id。
    :param worker_accept_event_sequence: ``ATTEMPT_RUNNING`` event sequence。
    :param worker_accepted_at: worker accept timestamp。
    :returns: dispatch record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(attempt_id, field_name="attempt_id")
    _require_non_empty_text(
        worker_accept_event_id, field_name="worker_accept_event_id"
    )
    _require_positive_sequence(
        worker_accept_event_sequence, "worker_accept_event_sequence"
    )
    _require_non_empty_text(worker_accepted_at, field_name="worker_accepted_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
        SET
          worker_accepted_at = ?,
          worker_accept_event_id = ?,
          worker_accept_event_sequence = ?,
          updated_at = ?
        WHERE attempt_id = ?
          AND status = ?
          AND worker_accepted_at IS NULL
          AND worker_accept_event_id IS NULL
          AND worker_accept_event_sequence IS NULL
          AND cancelled_event_id IS NULL
        """,
        (
            worker_accepted_at,
            worker_accept_event_id,
            worker_accept_event_sequence,
            worker_accepted_at,
            attempt_id,
            serialize_dispatch_record_status(DispatchRecordStatus.DISPATCHING),
        ),
    )
    return _dispatch_record_mutation_result_for_dispatching(
        transaction, attempt_id=attempt_id, rowcount=result.rowcount
    )


def cancel_starting_dispatch_record_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    cancelled_event_id: str,
    cancelled_event_sequence: int,
    cancelled_at: str,
) -> DispatchRecordMutationResult:
    """CAS 取消 worker accept 前的 STARTING dispatch record。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param cancelled_event_id: ``ATTEMPT_CANCELLED`` 事件 id。
    :param cancelled_event_sequence: ``ATTEMPT_CANCELLED`` 全局事件序号。
    :param cancelled_at: 固定 UTC cancel timestamp 文本。
    :returns: dispatch record mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(attempt_id, field_name="attempt_id")
    _require_non_empty_text(cancelled_event_id, field_name="cancelled_event_id")
    if cancelled_event_sequence <= 0:
        raise HostDurableError("cancelled_event_sequence must be positive")
    _require_non_empty_text(cancelled_at, field_name="cancelled_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
        SET
          status = ?,
          cancelled_event_id = ?,
          cancelled_event_sequence = ?,
          updated_at = ?,
          cancelled_at = ?
        WHERE attempt_id = ?
          AND status IN (?, ?, ?)
          AND worker_accepted_at IS NULL
          AND worker_accept_event_id IS NULL
          AND worker_accept_event_sequence IS NULL
        """,
        (
            serialize_dispatch_record_status(DispatchRecordStatus.CANCELLED),
            cancelled_event_id,
            cancelled_event_sequence,
            cancelled_at,
            cancelled_at,
            attempt_id,
            serialize_dispatch_record_status(DispatchRecordStatus.PENDING),
            serialize_dispatch_record_status(DispatchRecordStatus.WAITING_FOR_LANE),
            serialize_dispatch_record_status(DispatchRecordStatus.DISPATCHING),
        ),
    )
    if result.rowcount == 1:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.UPDATED,
            row=read_dispatch_record_by_attempt_id(transaction, attempt_id),
        )
    latest = read_dispatch_record_by_attempt_id(transaction, attempt_id)
    if latest is None:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.NOT_FOUND,
            row=None,
        )
    if latest.status in (
        DispatchRecordStatus.PENDING,
        DispatchRecordStatus.WAITING_FOR_LANE,
        DispatchRecordStatus.CANCELLED,
    ):
        return DispatchRecordMutationResult(
            status=StateMutationStatus.CAS_LOST,
            row=latest,
        )
    if (
        latest.status == DispatchRecordStatus.DISPATCHING
        and latest.worker_accept_event_id is None
        and latest.worker_accept_event_sequence is None
        and latest.worker_accepted_at is None
    ):
        return DispatchRecordMutationResult(
            status=StateMutationStatus.CAS_LOST,
            row=latest,
        )
    return DispatchRecordMutationResult(
        status=StateMutationStatus.INVALID_STATE,
        row=latest,
    )


def session_snapshot_from_rows(
    transaction: HostTransaction,
    session: SessionRow,
    slot: SessionSlotRow | None,
) -> SessionSnapshot:
    """由 durable row 转换为公共 SessionSnapshot。

    :param transaction: 调用方提供的 Host transaction，用于读取 Run 索引摘要。
    :param session: Session row。
    :param slot: 当前绑定 slot；未绑定时为 ``None``。
    :returns: 公共 ``SessionSnapshot``。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    return SessionSnapshot(
        session_id=session.session_id,
        status=session.status,
        slot=_slot_ref_from_row(slot),
        active_run_id=_read_active_run_id(transaction, session.session_id),
        queued_run_ids=_read_queued_run_ids(transaction, session.session_id),
        timeline_cursor=HostStreamCursor(
            event_sequence=_session_timeline_cursor(session)
        ),
    )


def run_snapshot_from_row(run: RunRow) -> RunSnapshot:
    """由 durable Run row 构造公共 RunSnapshot。

    Phase 4 尚无 typed terminal payload decoder；终态 Run 只能稳定返回
    status-only ``TerminalResultSummary``，不从 EventLog payload 字符串中做
    ad hoc JSON 解析。

    :param run: durable Run row。
    :returns: 公共 Run snapshot。
    :raises ValueError: Run row 字段无法满足公共 snapshot 约束时抛出。
    """

    return RunSnapshot(
        run_id=run.run_id,
        session_id=run.session_id,
        status=run.status,
        current_attempt_id=run.current_attempt_id,
        terminal_result_summary=_terminal_result_summary_from_status(
            run.status
        ),
        event_cursor=HostStreamCursor(event_sequence=_run_event_cursor(run)),
        source_run_id=run.source_run_id,
        source_run_relation=run.source_run_relation,
        outbox_summary=None,
    )


def _terminal_result_summary_from_status(
    status: RunStatus,
) -> TerminalResultSummary | None:
    """按 Run 状态生成 public 终态摘要。

    :param status: durable Run 状态。
    :returns: 终态返回 status-only 摘要；非终态返回 ``None``。
    :raises ValueError: status-only 终态摘要无法满足公共类型约束时抛出。
    """

    if status not in _TERMINAL_RUN_STATUSES:
        return None
    return TerminalResultSummary(
        status=status,
        summary_ref=None,
        summary_digest=None,
    )


def _serialize_str_enum(value: StrEnum, *, enum_name: str) -> str:
    """序列化 StrEnum。

    :param value: 待序列化 enum。
    :param enum_name: 错误消息中使用的 enum 名称。
    :returns: enum 的 schema 文本值。
    :raises HostDurableError: enum 值为空或类型无效时抛出。
    """

    if not isinstance(value, StrEnum):
        raise HostDurableError(f"{enum_name} is invalid")
    _require_non_empty_text(value.value, field_name=enum_name)
    return value.value


def _deserialize_str_enum(
    value: str, *, enum_type: type[_StatusT], enum_name: str
) -> _StatusT:
    """反序列化 StrEnum。

    :param value: SQLite 或 payload 中的文本值。
    :param enum_type: 目标 enum 类型。
    :param enum_name: 错误消息中使用的 enum 名称。
    :returns: enum 值。
    :raises HostDurableError: 文本为空或不属于目标 enum 时抛出。
    """

    _require_non_empty_text(value, field_name=enum_name)
    try:
        return enum_type(value)
    except ValueError as exc:
        raise HostDurableError(f"{enum_name} is invalid") from exc


def _validate_session_for_insert(session: SessionRow) -> None:
    """校验待插入 Session row。

    :param session: 待校验 Session row。
    :returns: ``None``。
    :raises HostDurableError: 任一字段不满足 open Session 插入约束时抛出。
    """

    _require_non_empty_text(session.session_id, field_name="session_id")
    if session.status != SessionStatus.OPEN:
        raise HostDurableError("insert_session only accepts open Session row")
    _require_non_empty_text(session.metadata_json, field_name="metadata_json")
    _require_non_empty_text(session.created_event_id, field_name="created_event_id")
    if session.created_event_sequence <= 0:
        raise HostDurableError("created_event_sequence must be positive")
    if session.closed_event_id is not None:
        raise HostDurableError("open Session closed_event_id must be unset")
    if session.closed_event_sequence is not None:
        raise HostDurableError("open Session closed_event_sequence must be unset")
    _require_non_empty_text(session.created_at, field_name="created_at")
    if session.closed_at is not None:
        raise HostDurableError("open Session closed_at must be unset")


def _validate_session_slot(slot: SessionSlotRow) -> None:
    """校验 Session slot row。

    :param slot: 待校验 slot row。
    :returns: ``None``。
    :raises HostDurableError: 任一必填字段为空或事件序号无效时抛出。
    """

    _require_non_empty_text(slot.scope, field_name="scope")
    _require_non_empty_text(slot.slot_key, field_name="slot_key")
    _require_non_empty_text(slot.session_id, field_name="session_id")
    _require_non_empty_text(slot.bound_event_id, field_name="bound_event_id")
    if slot.bound_event_sequence <= 0:
        raise HostDurableError("bound_event_sequence must be positive")
    _require_non_empty_text(slot.metadata_json, field_name="metadata_json")
    _require_non_empty_text(slot.updated_at, field_name="updated_at")


def _validate_run_for_insert(run: RunRow) -> None:
    """校验待插入 Run row。

    :param run: 待校验 Run row。
    :returns: ``None``。
    :raises HostDurableError: 任一字段违反 Phase 3 Run row 约束时抛出。
    """

    _require_non_empty_text(run.run_id, field_name="run_id")
    _require_non_empty_text(run.session_id, field_name="session_id")
    if not isinstance(run.status, RunStatus):
        raise HostDurableError("Run status is invalid")
    _require_non_empty_text(run.client_request_id, field_name="client_request_id")
    _require_non_empty_text(run.input_event_id, field_name="input_event_id")
    _require_positive_sequence(run.input_event_sequence, "input_event_sequence")
    _require_non_empty_text(run.accepted_event_id, field_name="accepted_event_id")
    _require_positive_sequence(
        run.accepted_event_sequence, "accepted_event_sequence"
    )
    _require_optional_non_empty_text(
        run.queued_event_id, field_name="queued_event_id"
    )
    _require_optional_positive_sequence(
        run.queued_event_sequence, "queued_event_sequence"
    )
    _require_optional_non_empty_text(
        run.started_event_id, field_name="started_event_id"
    )
    _require_optional_positive_sequence(
        run.started_event_sequence, "started_event_sequence"
    )
    _require_optional_non_empty_text(
        run.terminal_event_id, field_name="terminal_event_id"
    )
    _require_optional_positive_sequence(
        run.terminal_event_sequence, "terminal_event_sequence"
    )
    _require_optional_non_empty_text(
        run.current_attempt_id, field_name="current_attempt_id"
    )
    _require_optional_non_empty_text(run.source_run_id, field_name="source_run_id")
    _require_non_empty_text(run.execution_target, field_name="execution_target")
    _require_non_empty_text(run.queue_policy, field_name="queue_policy")
    _require_non_empty_text(run.created_at, field_name="created_at")
    _require_non_empty_text(run.updated_at, field_name="updated_at")
    _require_optional_non_empty_text(run.terminal_at, field_name="terminal_at")
    if run.status == RunStatus.QUEUED:
        if run.queued_event_id is None or run.queued_event_sequence is None:
            raise HostDurableError("queued Run requires queue event refs")
        if run.current_attempt_id is not None:
            raise HostDurableError("queued Run current_attempt_id must be unset")
    if _is_terminal_run_status(run.status):
        if (
            run.terminal_event_id is None
            or run.terminal_event_sequence is None
            or run.terminal_at is None
        ):
            raise HostDurableError("terminal Run requires terminal refs")
    elif (
        run.terminal_event_id is not None
        or run.terminal_event_sequence is not None
        or run.terminal_at is not None
    ):
        raise HostDurableError("non-terminal Run terminal refs must be unset")
    if (run.source_run_id is None) != (run.source_run_relation is None):
        raise HostDurableError("Run source relation fields must be paired")


def _validate_attempt_for_insert(attempt: AttemptRow) -> None:
    """校验待插入 Attempt row。

    :param attempt: 待校验 Attempt row。
    :returns: ``None``。
    :raises HostDurableError: 任一字段违反 Phase 3 Attempt row 约束时抛出。
    """

    _require_non_empty_text(attempt.attempt_id, field_name="attempt_id")
    _require_non_empty_text(attempt.run_id, field_name="run_id")
    _require_non_empty_text(attempt.execution_id, field_name="execution_id")
    if attempt.status != AttemptStatus.STARTING:
        raise HostDurableError("insert_attempt only accepts STARTING Attempt")
    _require_non_empty_text(
        attempt.started_event_id, field_name="started_event_id"
    )
    _require_positive_sequence(
        attempt.started_event_sequence, "started_event_sequence"
    )
    if attempt.terminal_event_id is not None:
        raise HostDurableError("STARTING Attempt terminal_event_id must be unset")
    if attempt.terminal_event_sequence is not None:
        raise HostDurableError(
            "STARTING Attempt terminal_event_sequence must be unset"
        )
    _require_non_empty_text(attempt.created_at, field_name="created_at")
    _require_non_empty_text(attempt.updated_at, field_name="updated_at")
    if attempt.terminal_at is not None:
        raise HostDurableError("STARTING Attempt terminal_at must be unset")


def _validate_dispatch_record_for_insert(
    dispatch_record: DispatchRecordRow,
) -> None:
    """校验待插入 dispatch record row。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: 任一字段违反 Phase 3 dispatch row 约束时抛出。
    """

    _require_non_empty_text(
        dispatch_record.dispatch_record_id, field_name="dispatch_record_id"
    )
    _require_non_empty_text(dispatch_record.run_id, field_name="run_id")
    _require_non_empty_text(dispatch_record.attempt_id, field_name="attempt_id")
    _require_non_empty_text(dispatch_record.execution_id, field_name="execution_id")
    if not isinstance(dispatch_record.status, DispatchRecordStatus):
        raise HostDurableError("dispatch record status is invalid")
    if not isinstance(dispatch_record.worker_kind, WorkerKind):
        raise HostDurableError("worker kind is invalid")
    _require_non_empty_text(
        dispatch_record.execution_target, field_name="execution_target"
    )
    _require_optional_non_empty_text(
        dispatch_record.owner_host_instance_id,
        field_name="owner_host_instance_id",
    )
    _require_non_empty_text(
        dispatch_record.created_event_id, field_name="created_event_id"
    )
    _require_positive_sequence(
        dispatch_record.created_event_sequence, "created_event_sequence"
    )
    _require_optional_non_empty_text(
        dispatch_record.waiting_for_lane_at, field_name="waiting_for_lane_at"
    )
    _require_optional_non_empty_text(
        dispatch_record.lane_name, field_name="lane_name"
    )
    _require_optional_non_empty_text(
        dispatch_record.lane_claim_id, field_name="lane_claim_id"
    )
    _require_optional_non_empty_text(
        dispatch_record.lane_owner_id, field_name="lane_owner_id"
    )
    _require_optional_non_empty_text(
        dispatch_record.lane_acquired_at, field_name="lane_acquired_at"
    )
    _require_optional_non_empty_text(
        dispatch_record.dispatching_at, field_name="dispatching_at"
    )
    _require_optional_non_empty_text(
        dispatch_record.worker_accepted_at, field_name="worker_accepted_at"
    )
    _require_optional_non_empty_text(
        dispatch_record.worker_accept_event_id,
        field_name="worker_accept_event_id",
    )
    _require_optional_positive_sequence(
        dispatch_record.worker_accept_event_sequence,
        "worker_accept_event_sequence",
    )
    _require_optional_non_empty_text(
        dispatch_record.cancelled_event_id, field_name="cancelled_event_id"
    )
    _require_optional_positive_sequence(
        dispatch_record.cancelled_event_sequence, "cancelled_event_sequence"
    )
    _require_non_empty_text(dispatch_record.created_at, field_name="created_at")
    _require_non_empty_text(dispatch_record.updated_at, field_name="updated_at")
    _require_optional_non_empty_text(
        dispatch_record.cancelled_at, field_name="cancelled_at"
    )
    _validate_dispatch_record_status_shape(dispatch_record)


def _validate_dispatch_record_status_shape(
    dispatch_record: DispatchRecordRow,
) -> None:
    """校验 dispatch record 各状态的字段组合。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: 状态字段组合不满足 fresh schema 约束时抛出。
    """

    if dispatch_record.status == DispatchRecordStatus.PENDING:
        _require_dispatch_diagnostics_unset(dispatch_record)
        _require_dispatch_cancel_refs_unset(dispatch_record)
    elif dispatch_record.status == DispatchRecordStatus.WAITING_FOR_LANE:
        _require_waiting_for_lane_diagnostics(dispatch_record)
        _require_dispatch_pre_lane_diagnostics_unset(dispatch_record)
        _require_dispatch_worker_accept_refs_unset(dispatch_record)
        _require_dispatch_cancel_refs_unset(dispatch_record)
    elif dispatch_record.status == DispatchRecordStatus.DISPATCHING:
        _require_dispatching_diagnostics(dispatch_record)
        _require_dispatch_worker_accept_refs_paired(dispatch_record)
        _require_dispatch_cancel_refs_unset(dispatch_record)
    elif dispatch_record.status == DispatchRecordStatus.CANCELLED:
        _require_dispatch_cancel_refs(dispatch_record)
        _require_dispatch_worker_accept_refs_unset(dispatch_record)


def _require_dispatch_diagnostics_unset(
    dispatch_record: DispatchRecordRow,
) -> None:
    """要求 pending dispatch 诊断字段均为空。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: 任何诊断字段非空时抛出。
    """

    if (
        dispatch_record.waiting_for_lane_at is not None
        or dispatch_record.lane_name is not None
        or dispatch_record.lane_claim_id is not None
        or dispatch_record.lane_owner_id is not None
        or dispatch_record.lane_acquired_at is not None
        or dispatch_record.dispatching_at is not None
        or dispatch_record.worker_accepted_at is not None
        or dispatch_record.worker_accept_event_id is not None
        or dispatch_record.worker_accept_event_sequence is not None
    ):
        raise HostDurableError("pending dispatch diagnostics must be unset")


def _require_waiting_for_lane_diagnostics(
    dispatch_record: DispatchRecordRow,
) -> None:
    """要求 waiting_for_lane 必填诊断字段非空。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: 必填诊断字段缺失时抛出。
    """

    if (
        dispatch_record.waiting_for_lane_at is None
        or dispatch_record.lane_name is None
        or dispatch_record.owner_host_instance_id is None
    ):
        raise HostDurableError("waiting dispatch requires lane wait diagnostics")


def _require_dispatch_pre_lane_diagnostics_unset(
    dispatch_record: DispatchRecordRow,
) -> None:
    """要求 waiting_for_lane 尚未持有 lane 或进入 dispatching。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: lane acquire 或 dispatching 字段非空时抛出。
    """

    if (
        dispatch_record.lane_claim_id is not None
        or dispatch_record.lane_owner_id is not None
        or dispatch_record.lane_acquired_at is not None
        or dispatch_record.dispatching_at is not None
    ):
        raise HostDurableError("waiting dispatch lane acquire diagnostics must be unset")


def _require_dispatching_diagnostics(
    dispatch_record: DispatchRecordRow,
) -> None:
    """要求 dispatching 必填诊断字段非空。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: 必填诊断字段缺失时抛出。
    """

    if (
        dispatch_record.waiting_for_lane_at is None
        or dispatch_record.lane_name is None
        or dispatch_record.owner_host_instance_id is None
        or dispatch_record.lane_claim_id is None
        or dispatch_record.lane_owner_id is None
        or dispatch_record.lane_acquired_at is None
        or dispatch_record.dispatching_at is None
    ):
        raise HostDurableError("dispatching requires lane diagnostics")


def _require_dispatch_worker_accept_refs_paired(
    dispatch_record: DispatchRecordRow,
) -> None:
    """要求 worker accept refs 要么全空要么全有。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: worker accept refs 部分缺失时抛出。
    """

    refs = (
        dispatch_record.worker_accepted_at,
        dispatch_record.worker_accept_event_id,
        dispatch_record.worker_accept_event_sequence,
    )
    if any(ref is None for ref in refs) and any(ref is not None for ref in refs):
        raise HostDurableError("worker accept refs must be paired")


def _require_dispatch_worker_accept_refs_unset(
    dispatch_record: DispatchRecordRow,
) -> None:
    """要求 worker accept refs 全空。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: worker accept refs 非空时抛出。
    """

    if (
        dispatch_record.worker_accepted_at is not None
        or dispatch_record.worker_accept_event_id is not None
        or dispatch_record.worker_accept_event_sequence is not None
    ):
        raise HostDurableError("worker accept refs must be unset")


def _require_dispatch_cancel_refs(
    dispatch_record: DispatchRecordRow,
) -> None:
    """要求 cancel refs 全部存在。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: cancel refs 缺失时抛出。
    """

    if (
        dispatch_record.cancelled_event_id is None
        or dispatch_record.cancelled_event_sequence is None
        or dispatch_record.cancelled_at is None
    ):
        raise HostDurableError("cancelled dispatch requires cancel refs")


def _require_dispatch_cancel_refs_unset(
    dispatch_record: DispatchRecordRow,
) -> None:
    """要求 cancel refs 全空。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: cancel refs 非空时抛出。
    """

    if (
        dispatch_record.cancelled_event_id is not None
        or dispatch_record.cancelled_event_sequence is not None
        or dispatch_record.cancelled_at is not None
    ):
        raise HostDurableError("non-cancelled dispatch cancel refs must be unset")


def _validate_run_start_update(
    *,
    session_id: str,
    run_id: str,
    started_event_id: str,
    started_event_sequence: int,
    current_attempt_id: str,
    updated_at: str,
) -> None:
    """校验 Run start update 输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param started_event_id: RUN_STARTED event id。
    :param started_event_sequence: RUN_STARTED event sequence。
    :param current_attempt_id: current Attempt id。
    :param updated_at: 更新时间。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(started_event_id, field_name="started_event_id")
    _require_positive_sequence(started_event_sequence, "started_event_sequence")
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    _require_non_empty_text(updated_at, field_name="updated_at")


def _validate_run_terminal_update(
    *,
    run_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> None:
    """校验 Run terminal update 输入。

    :param run_id: Run id。
    :param terminal_event_id: terminal event id。
    :param terminal_event_sequence: terminal event sequence。
    :param terminal_at: terminal timestamp。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(terminal_event_id, field_name="terminal_event_id")
    _require_positive_sequence(
        terminal_event_sequence, "terminal_event_sequence"
    )
    _require_non_empty_text(terminal_at, field_name="terminal_at")


def _validate_attempt_terminal_update(
    *,
    attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> None:
    """校验 Attempt terminal update 输入。

    :param attempt_id: Attempt id。
    :param terminal_event_id: terminal event id。
    :param terminal_event_sequence: terminal event sequence。
    :param terminal_at: terminal timestamp。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(attempt_id, field_name="attempt_id")
    _require_non_empty_text(terminal_event_id, field_name="terminal_event_id")
    _require_positive_sequence(
        terminal_event_sequence, "terminal_event_sequence"
    )
    _require_non_empty_text(terminal_at, field_name="terminal_at")


def _run_mutation_result(
    transaction: HostTransaction,
    *,
    run_id: str,
    rowcount: int,
    expected_status: RunStatus,
    cas_lost_when_expected: bool,
) -> RunMutationResult:
    """构造 Run mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :param rowcount: UPDATE rowcount。
    :param expected_status: CAS 期望源状态。
    :param cas_lost_when_expected: 仍处于期望源状态时是否归为 CAS lost。
    :returns: Run mutation 结果。
    """

    latest = read_run_by_id(transaction, run_id)
    if rowcount == 1:
        return RunMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return RunMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if latest.status == expected_status and cas_lost_when_expected:
        return RunMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return RunMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


def _run_mutation_result_for_active(
    transaction: HostTransaction, *, run_id: str, rowcount: int
) -> RunMutationResult:
    """构造 active Run terminal mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :param rowcount: UPDATE rowcount。
    :returns: Run mutation 结果。
    """

    latest = read_run_by_id(transaction, run_id)
    if rowcount == 1:
        return RunMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return RunMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if latest.status in (
        RunStatus.RUNNING,
        RunStatus.WAITING,
        RunStatus.CANCELLING,
        RunStatus.RECOVERING,
    ) or _is_terminal_run_status(latest.status):
        return RunMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return RunMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


def _attempt_mutation_result(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    rowcount: int,
    expected_status: AttemptStatus,
    cas_lost_when_expected: bool,
) -> AttemptMutationResult:
    """构造 Attempt mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: Attempt id。
    :param rowcount: UPDATE rowcount。
    :param expected_status: CAS 期望源状态。
    :param cas_lost_when_expected: 仍处于期望源状态时是否归为 CAS lost。
    :returns: Attempt mutation 结果。
    """

    latest = read_attempt_by_id(transaction, attempt_id)
    if rowcount == 1:
        return AttemptMutationResult(
            status=StateMutationStatus.UPDATED, row=latest
        )
    if latest is None:
        return AttemptMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=None
        )
    if latest.status == expected_status and cas_lost_when_expected:
        return AttemptMutationResult(
            status=StateMutationStatus.CAS_LOST, row=latest
        )
    return AttemptMutationResult(
        status=StateMutationStatus.INVALID_STATE, row=latest
    )


def _attempt_mutation_result_for_active(
    transaction: HostTransaction, *, attempt_id: str, rowcount: int
) -> AttemptMutationResult:
    """构造 active Attempt terminal mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: Attempt id。
    :param rowcount: UPDATE rowcount。
    :returns: Attempt mutation 结果。
    """

    latest = read_attempt_by_id(transaction, attempt_id)
    if rowcount == 1:
        return AttemptMutationResult(
            status=StateMutationStatus.UPDATED, row=latest
        )
    if latest is None:
        return AttemptMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=None
        )
    if latest.status in (AttemptStatus.STARTING, AttemptStatus.RUNNING):
        return AttemptMutationResult(
            status=StateMutationStatus.CAS_LOST, row=latest
        )
    return AttemptMutationResult(
        status=StateMutationStatus.INVALID_STATE, row=latest
    )


def _dispatch_record_mutation_result_for_dispatch_start(
    transaction: HostTransaction, *, attempt_id: str, rowcount: int
) -> DispatchRecordMutationResult:
    """构造 dispatch start 诊断状态 mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: Attempt id。
    :param rowcount: UPDATE rowcount。
    :returns: dispatch record mutation 结果。
    """

    latest = read_dispatch_record_by_attempt_id(transaction, attempt_id)
    if rowcount == 1:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.UPDATED, row=latest
        )
    if latest is None:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=None
        )
    if latest.status in (
        DispatchRecordStatus.PENDING,
        DispatchRecordStatus.WAITING_FOR_LANE,
    ):
        return DispatchRecordMutationResult(
            status=StateMutationStatus.CAS_LOST, row=latest
        )
    return DispatchRecordMutationResult(
        status=StateMutationStatus.INVALID_STATE, row=latest
    )


def _dispatch_record_mutation_result_for_dispatching(
    transaction: HostTransaction, *, attempt_id: str, rowcount: int
) -> DispatchRecordMutationResult:
    """构造 dispatching source 状态 mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: Attempt id。
    :param rowcount: UPDATE rowcount。
    :returns: dispatch record mutation 结果。
    """

    latest = read_dispatch_record_by_attempt_id(transaction, attempt_id)
    if rowcount == 1:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.UPDATED, row=latest
        )
    if latest is None:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=None
        )
    if (
        latest.status == DispatchRecordStatus.DISPATCHING
        and latest.worker_accept_event_id is None
        and latest.worker_accept_event_sequence is None
        and latest.worker_accepted_at is None
    ):
        return DispatchRecordMutationResult(
            status=StateMutationStatus.CAS_LOST, row=latest
        )
    return DispatchRecordMutationResult(
        status=StateMutationStatus.INVALID_STATE, row=latest
    )


def _dispatch_record_mutation_result_for_lane_dispatching(
    transaction: HostTransaction, *, attempt_id: str, rowcount: int
) -> DispatchRecordMutationResult:
    """构造 lane acquired 后 dispatching mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: Attempt id。
    :param rowcount: UPDATE rowcount。
    :returns: dispatch record mutation 结果。
    """

    latest = read_dispatch_record_by_attempt_id(transaction, attempt_id)
    if rowcount == 1:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.UPDATED, row=latest
        )
    if latest is None:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=None
        )
    if latest.status == DispatchRecordStatus.WAITING_FOR_LANE:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.CAS_LOST, row=latest
        )
    return DispatchRecordMutationResult(
        status=StateMutationStatus.INVALID_STATE, row=latest
    )


def _invalid_dispatching_after_lane_precondition(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    owner_host_instance_id: str,
    lane_name: str,
) -> DispatchRecordMutationResult | None:
    """检查 lane acquired 后 dispatching mutation 的完整前置。

    本函数提供结构化 ``NOT_FOUND`` / ``INVALID_STATE`` 诊断；随后
    ``mark_dispatching_after_lane_row`` 的 SQL ``WHERE`` 仍保留最终 CAS 防线，
    用来防止同事务后续维护或未来调用路径绕过原子条件。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: Attempt id。
    :param owner_host_instance_id: scheduler owner Host instance id。
    :param lane_name: runtime lane 名称。
    :returns: 前置失败时返回 mutation 结果，否则返回 ``None``。
    """

    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, attempt_id
    )
    if dispatch_record is None:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=None
        )
    attempt = read_attempt_by_id(transaction, attempt_id)
    if attempt is None:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=dispatch_record
        )
    run = read_run_by_id(transaction, dispatch_record.run_id)
    if run is None:
        return DispatchRecordMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=dispatch_record
        )
    if (
        dispatch_record.status != DispatchRecordStatus.WAITING_FOR_LANE
        or dispatch_record.owner_host_instance_id != owner_host_instance_id
        or dispatch_record.waiting_for_lane_at is None
        or dispatch_record.lane_name != lane_name
        or dispatch_record.run_id != run.run_id
        or dispatch_record.attempt_id != attempt.attempt_id
        or dispatch_record.execution_id != attempt.execution_id
        or run.status != RunStatus.RUNNING
        or run.current_attempt_id != attempt_id
        or attempt.run_id != run.run_id
        or attempt.status != AttemptStatus.STARTING
        or dispatch_record.lane_claim_id is not None
        or dispatch_record.lane_owner_id is not None
        or dispatch_record.lane_acquired_at is not None
        or dispatch_record.dispatching_at is not None
        or dispatch_record.worker_accepted_at is not None
        or dispatch_record.worker_accept_event_id is not None
        or dispatch_record.worker_accept_event_sequence is not None
        or dispatch_record.cancelled_event_id is not None
        or dispatch_record.cancelled_event_sequence is not None
    ):
        return DispatchRecordMutationResult(
            status=StateMutationStatus.INVALID_STATE, row=dispatch_record
        )
    return None


def _optional_source_run_relation_text(
    relation: SourceRunRelation | None,
) -> str | None:
    """序列化 optional SourceRunRelation。

    :param relation: source relation 或 ``None``。
    :returns: SQLite 文本值或 ``None``。
    :raises HostDurableError: relation 类型非法时抛出。
    """

    if relation is None:
        return None
    if not isinstance(relation, SourceRunRelation):
        raise HostDurableError("SourceRunRelation is invalid")
    return relation.value


def _wait_adapter_key_from_text(value: str) -> WaitAdapterKey:
    """从 durable 文本构造 ``WaitAdapterKey``。

    :param value: SQLite 中保存的 adapter key 文本。
    :returns: ``WaitAdapterKey``。
    :raises HostDurableError: adapter key 文本非法时抛出。
    """

    try:
        return WaitAdapterKey(value)
    except ValueError as exc:
        raise HostDurableError("wait adapter_key is invalid") from exc


def _validate_wait_record_for_insert(row: WaitRecordRow) -> None:
    """校验待插入 wait record row。

    :param row: 待校验 wait record row。
    :returns: ``None``。
    :raises HostDurableError: 任一字段违反 wait record 约束时抛出。
    """

    _require_text_max_length(
        row.wait_id, field_name="wait_id", max_length=HOST_WAIT_ID_MAX_LENGTH
    )
    _require_non_empty_text(row.session_id, field_name="session_id")
    _require_non_empty_text(row.run_id, field_name="run_id")
    _require_non_empty_text(row.attempt_id, field_name="attempt_id")
    _require_non_empty_text(row.execution_id, field_name="execution_id")
    _require_text_max_length(
        row.tool_call_id,
        field_name="tool_call_id",
        max_length=HOST_WAIT_TOOL_CALL_ID_MAX_LENGTH,
    )
    _require_text_max_length(
        row.tool_name,
        field_name="tool_name",
        max_length=HOST_WAIT_TOOL_NAME_MAX_LENGTH,
    )
    if not isinstance(row.adapter_key, WaitAdapterKey):
        raise HostDurableError("wait adapter_key is invalid")
    _require_non_empty_text(row.await_kind, field_name="await_kind")
    if not isinstance(row.resume_policy, WaitResumePolicy):
        raise HostDurableError("wait resume_policy is invalid")
    _require_text_max_length(
        row.resume_token,
        field_name="resume_token",
        max_length=HOST_WAIT_RESUME_TOKEN_MAX_LENGTH,
    )
    if row.snapshot_ref is not None and not isinstance(
        row.snapshot_ref, WaitSnapshotRef
    ):
        raise HostDurableError("wait snapshot_ref is invalid")
    _validate_wait_external_job_ref(row)
    _require_text_max_length(
        row.accept_idempotency_key,
        field_name="accept_idempotency_key",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _validate_wait_resolution_refs(row)
    _require_optional_non_empty_text(row.deadline_at, field_name="deadline_at")
    _require_optional_non_empty_text(row.expires_at, field_name="expires_at")
    if not isinstance(row.status, WaitRecordStatus):
        raise HostDurableError("wait status is invalid")
    _require_non_empty_text(row.created_event_id, field_name="created_event_id")
    _require_positive_sequence(
        row.created_event_sequence, "created_event_sequence"
    )
    _require_non_empty_text(row.updated_event_id, field_name="updated_event_id")
    _require_positive_sequence(
        row.updated_event_sequence, "updated_event_sequence"
    )
    _require_non_empty_text(row.created_at, field_name="created_at")
    _require_non_empty_text(row.updated_at, field_name="updated_at")
    _require_optional_non_empty_text(row.terminal_at, field_name="terminal_at")
    if row.status == WaitRecordStatus.WAITING and row.terminal_at is not None:
        raise HostDurableError("waiting wait record terminal_at must be unset")
    if row.status != WaitRecordStatus.WAITING and row.terminal_at is None:
        raise HostDurableError("terminal wait record requires terminal_at")


def _validate_wait_external_job_ref(row: WaitRecordRow) -> None:
    """校验 wait record 外部 job ref 与 adapter key 一致。

    :param row: 待校验 wait record row。
    :returns: ``None``。
    :raises HostDurableError: 外部 job 引用类型或 adapter key 不一致时抛出。
    """

    if row.external_job_ref is None:
        return
    if not isinstance(row.external_job_ref, ExternalJobRef):
        raise HostDurableError("wait external_job_ref is invalid")
    if row.external_job_ref.adapter_key != row.adapter_key:
        raise HostDurableError("external_job_ref adapter_key must match wait row")


def _validate_wait_resolution_refs(row: WaitRecordRow) -> None:
    """校验 wait record resolve 幂等字段组合。

    :param row: 待校验 wait record row。
    :returns: ``None``。
    :raises HostDurableError: resolve 字段未成对或状态组合非法时抛出。
    """

    _require_optional_text_max_length(
        row.resolve_idempotency_key,
        field_name="resolve_idempotency_key",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_optional_non_empty_text(
        row.resolve_semantic_digest, field_name="resolve_semantic_digest"
    )
    if (row.resolve_idempotency_key is None) != (
        row.resolve_semantic_digest is None
    ):
        raise HostDurableError("wait resolve fields must be paired")
    if row.status in (
        WaitRecordStatus.RESOLVED,
        WaitRecordStatus.FAILED,
        WaitRecordStatus.LOST,
    ) and row.resolve_idempotency_key is None:
        raise HostDurableError("resolved, failed or lost wait requires resolve refs")
    if row.status in (
        WaitRecordStatus.WAITING,
        WaitRecordStatus.CANCELLED,
    ) and row.resolve_idempotency_key is not None:
        raise HostDurableError("waiting or cancelled wait must not carry resolve refs")


def _mark_wait_record_terminal_row(
    transaction: HostTransaction,
    *,
    wait_id: str,
    status: WaitRecordStatus,
    resolve_idempotency_key: str | None,
    resolve_semantic_digest: str | None,
    updated_event_id: str,
    updated_event_sequence: int,
    updated_at: str,
    terminal_at: str,
) -> WaitRecordMutationResult:
    """CAS 标记单条 wait record 为终态。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param status: 目标终态。
    :param resolve_idempotency_key: resolve 幂等键；取消路径为 ``None``。
    :param resolve_semantic_digest: resolve 语义 digest；取消路径为 ``None``。
    :param updated_event_id: 更新事件 id。
    :param updated_event_sequence: 更新事件序号。
    :param updated_at: 更新时间文本。
    :param terminal_at: 终态时间文本。
    :returns: wait record mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _validate_wait_terminal_update(
        wait_id=wait_id,
        updated_event_id=updated_event_id,
        updated_event_sequence=updated_event_sequence,
        updated_at=updated_at,
        terminal_at=terminal_at,
        resolve_idempotency_key=resolve_idempotency_key,
        resolve_semantic_digest=resolve_semantic_digest,
    )
    if not isinstance(status, WaitRecordStatus) or status == WaitRecordStatus.WAITING:
        raise HostDurableError("wait terminal status is invalid")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_WAIT_RECORDS}
        SET
          status = ?,
          resolve_idempotency_key = ?,
          resolve_semantic_digest = ?,
          updated_event_id = ?,
          updated_event_sequence = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE wait_id = ? AND status = ?
        """,
        (
            serialize_wait_record_status(status),
            resolve_idempotency_key,
            resolve_semantic_digest,
            updated_event_id,
            updated_event_sequence,
            updated_at,
            terminal_at,
            wait_id,
            serialize_wait_record_status(WaitRecordStatus.WAITING),
        ),
    )
    return _wait_record_mutation_result(
        transaction, wait_id=wait_id, rowcount=result.rowcount
    )


def _validate_wait_terminal_update(
    *,
    wait_id: str,
    updated_event_id: str,
    updated_event_sequence: int,
    updated_at: str,
    terminal_at: str,
    resolve_idempotency_key: str | None,
    resolve_semantic_digest: str | None,
) -> None:
    """校验 wait record 终态更新字段。

    :param wait_id: wait record id。
    :param updated_event_id: 更新事件 id。
    :param updated_event_sequence: 更新事件序号。
    :param updated_at: 更新时间文本。
    :param terminal_at: 终态时间文本。
    :param resolve_idempotency_key: resolve 幂等键或 ``None``。
    :param resolve_semantic_digest: resolve 语义 digest 或 ``None``。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_text_max_length(
        wait_id, field_name="wait_id", max_length=HOST_WAIT_ID_MAX_LENGTH
    )
    _require_optional_text_max_length(
        resolve_idempotency_key,
        field_name="resolve_idempotency_key",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_optional_non_empty_text(
        resolve_semantic_digest, field_name="resolve_semantic_digest"
    )
    if (resolve_idempotency_key is None) != (resolve_semantic_digest is None):
        raise HostDurableError("wait resolve fields must be paired")
    _require_non_empty_text(updated_event_id, field_name="updated_event_id")
    _require_positive_sequence(updated_event_sequence, "updated_event_sequence")
    _require_non_empty_text(updated_at, field_name="updated_at")
    _require_non_empty_text(terminal_at, field_name="terminal_at")


def _validate_wait_batch_terminal_update(
    *,
    updated_event_id: str,
    updated_event_sequence: int,
    updated_at: str,
    terminal_at: str,
) -> None:
    """校验批量 wait record 终态更新字段。

    :param updated_event_id: 更新事件 id。
    :param updated_event_sequence: 更新事件序号。
    :param updated_at: 更新时间文本。
    :param terminal_at: 终态时间文本。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(updated_event_id, field_name="updated_event_id")
    _require_positive_sequence(updated_event_sequence, "updated_event_sequence")
    _require_non_empty_text(updated_at, field_name="updated_at")
    _require_non_empty_text(terminal_at, field_name="terminal_at")


def _wait_record_mutation_result(
    transaction: HostTransaction, *, wait_id: str, rowcount: int
) -> WaitRecordMutationResult:
    """构造单条 wait record mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param rowcount: UPDATE rowcount。
    :returns: wait record mutation 结果。
    """

    latest = read_wait_record_by_id(transaction, wait_id)
    if rowcount == 1:
        return WaitRecordMutationResult(
            status=StateMutationStatus.UPDATED, row=latest
        )
    if latest is None:
        return WaitRecordMutationResult(
            status=StateMutationStatus.NOT_FOUND, row=None
        )
    if latest.status == WaitRecordStatus.WAITING:
        return WaitRecordMutationResult(
            status=StateMutationStatus.CAS_LOST, row=latest
        )
    return WaitRecordMutationResult(
        status=StateMutationStatus.INVALID_STATE, row=latest
    )


def _read_wait_record_count_for_run(
    transaction: HostTransaction, run_id: str
) -> int:
    """读取 Run 下 wait record 总数。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :returns: wait record 数量。
    :raises HostDurableError: row 字段无效时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT COUNT(*) AS count
        FROM {TABLE_HOST_WAIT_RECORDS}
        WHERE run_id = ?
        """,
        (run_id,),
    )
    if row is None:
        raise HostDurableError("wait record count is unreadable")
    return _require_int(row.get("count"), field_name="count")


def _read_terminal_wait_records_for_run(
    transaction: HostTransaction,
    *,
    run_id: str,
    updated_event_id: str,
    updated_event_sequence: int,
) -> tuple[WaitRecordRow, ...]:
    """读取本次批量终态更新写入的 wait records。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :param updated_event_id: 更新事件 id。
    :param updated_event_sequence: 更新事件序号。
    :returns: wait record row 元组。
    """

    rows = transaction.fetchall(
        _WAIT_RECORD_SELECT_SQL
        + """
        WHERE run_id = ?
          AND updated_event_id = ?
          AND updated_event_sequence = ?
        ORDER BY created_event_sequence ASC, wait_id ASC
        """,
        (run_id, updated_event_id, updated_event_sequence),
    )
    return tuple(wait_record_row_from_host_row(row) for row in rows)


def _require_positive_sequence(value: int, field_name: str) -> None:
    """校验事件序号为正整数。

    :param value: 事件序号。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 序号小于等于零时抛出。
    """

    if value <= 0:
        raise HostDurableError(f"{field_name} must be positive")


def _require_optional_positive_sequence(
    value: int | None, field_name: str
) -> None:
    """校验 optional 事件序号。

    :param value: 事件序号或 ``None``。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 序号存在且小于等于零时抛出。
    """

    if value is not None:
        _require_positive_sequence(value, field_name)


def _require_text_max_length(
    value: str, *, field_name: str, max_length: int
) -> None:
    """校验必填文本非空且不超过长度上限。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :param max_length: 最大字符数。
    :returns: ``None``。
    :raises HostDurableError: 文本为空或超长时抛出。
    """

    _require_non_empty_text(value, field_name=field_name)
    if len(value) > max_length:
        raise HostDurableError(f"{field_name} length must be <= {max_length}")


def _require_optional_text_max_length(
    value: str | None, *, field_name: str, max_length: int
) -> None:
    """校验 optional 文本存在时非空且不超过长度上限。

    :param value: 待校验文本或 ``None``。
    :param field_name: 字段名。
    :param max_length: 最大字符数。
    :returns: ``None``。
    :raises HostDurableError: 文本存在但为空或超长时抛出。
    """

    if value is not None:
        _require_text_max_length(
            value, field_name=field_name, max_length=max_length
        )


def _is_terminal_run_status(status: RunStatus) -> bool:
    """判断 Run 状态是否为终态。

    :param status: Run 状态。
    :returns: 是终态时返回 ``True``。
    """

    return status in (
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.LOST,
    )


def _slot_ref_from_row(slot: SessionSlotRow | None) -> SessionSlotRef | None:
    """把 slot row 转换为公共 slot 引用。

    :param slot: slot row 或 ``None``。
    :returns: ``SessionSlotRef`` 或 ``None``。
    """

    if slot is None:
        return None
    return SessionSlotRef(scope=slot.scope, slot_key=slot.slot_key)


def _session_timeline_cursor(session: SessionRow) -> int:
    """读取 Session 自身 lifecycle 的最新事件游标。

    :param session: Session row。
    :returns: ``closed_event_sequence`` 或 ``created_event_sequence``。
    """

    if session.closed_event_sequence is not None:
        return session.closed_event_sequence
    return session.created_event_sequence


def _run_event_cursor(run: RunRow) -> int:
    """计算 Run snapshot 的当前事件游标。

    :param run: durable Run row。
    :returns: Run 已知事件引用中的最大全局 event sequence。
    """

    event_sequences = (
        run.input_event_sequence,
        run.accepted_event_sequence,
        run.queued_event_sequence,
        run.started_event_sequence,
        run.terminal_event_sequence,
    )
    return max(sequence for sequence in event_sequences if sequence is not None)


def _read_active_run_id(
    transaction: HostTransaction, session_id: str
) -> str | None:
    """读取 Session 当前 active Run id。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: active Run id；不存在时为 ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT run_id
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ?
          AND status IN (?, ?, ?, ?)
        ORDER BY accepted_event_sequence ASC, run_id ASC
        LIMIT 1
        """,
        (
            session_id,
            serialize_run_status(RunStatus.RUNNING),
            serialize_run_status(RunStatus.WAITING),
            serialize_run_status(RunStatus.CANCELLING),
            serialize_run_status(RunStatus.RECOVERING),
        ),
    )
    if row is None:
        return None
    return _require_text(row.get("run_id"), field_name="run_id")


def _read_queued_run_ids(
    transaction: HostTransaction, session_id: str
) -> tuple[str, ...]:
    """读取 Session queued Run id 列表。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 按 accepted event sequence 排序的 Run id 元组。
    :raises HostDurableError: row 字段无效时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT run_id
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ? AND status = ?
        ORDER BY accepted_event_sequence ASC, run_id ASC
        """,
        (session_id, serialize_run_status(RunStatus.QUEUED)),
    )
    return tuple(_require_text(row.get("run_id"), field_name="run_id") for row in rows)


def _optional_source_run_relation(value: str | None) -> SourceRunRelation | None:
    """反序列化 optional SourceRunRelation。

    :param value: SQLite row 中读取的 source relation 文本。
    :returns: ``SourceRunRelation`` 或 ``None``。
    :raises HostDurableError: 文本不属于 ``SourceRunRelation`` 时抛出。
    """

    if value is None:
        return None
    try:
        return SourceRunRelation(value)
    except ValueError as exc:
        raise HostDurableError("SourceRunRelation is invalid") from exc
