"""Host durable state row codec。

本模块只负责 Phase 3 durable state tables 的 row dataclass、状态枚举编解码
与 ``HostRow`` 转换。它不追加 EventLog、不打开 transaction，也不实现
Session lifecycle、admission、promotion、cancel 或 command path 语义。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    TERMINAL_RUN_STATUSES as PUBLIC_TERMINAL_RUN_STATUSES,
    TerminalResultSummary,
    WaitAdapterKey,
    is_terminal_run_status as is_public_terminal_run_status,
)
from dayu.contracts.json_value import JsonValue
from dayu.host.durable._row_rules import (
    TERMINAL_ATTEMPT_STATUS_VALUES,
    WAIT_RECORD_CANCELLED_STATUS_VALUE,
    WAIT_RECORD_FAILED_STATUS_VALUE,
    WAIT_RECORD_LOST_STATUS_VALUE,
    WAIT_RECORD_RESOLVED_STATUS_VALUE,
    WAIT_RECORD_WAITING_STATUS_VALUE,
    terminal_event_refs_unset_where_sql,
    validate_terminal_event_refs_shape,
    validate_wait_terminal_at_shape,
    wait_terminal_at_unset_where_sql,
)
from dayu.host.durable.codec import format_utc_timestamp, parse_utc_timestamp
from dayu.host.queue_policy import RunQueuePolicy, parse_run_queue_policy
from dayu.host.durable._validation import (
    optional_int as _optional_int,
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_sha256_digest as _require_sha256_digest,
    require_text as _require_text,
)
from dayu.host.durable.errors import HostDurableError, HostRowDecodeError
from dayu.host.durable.schema import (
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_SESSION_SLOTS,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_WAIT_RECORDS,
)
from dayu.host.durable.transaction import HostRow, SQLiteScalar
from dayu.host.durable.transaction import HostTransaction

_StatusT = TypeVar("_StatusT", bound=StrEnum)
TERMINAL_RUN_STATUSES = PUBLIC_TERMINAL_RUN_STATUSES
"""Run 终态集合，作为 durable state / purge 等持久化逻辑的状态真源。"""

NON_TERMINAL_RUN_STATUSES = frozenset(status for status in RunStatus if status not in TERMINAL_RUN_STATUSES)
"""Run 非终态集合，由 :class:`RunStatus` 与终态集合派生。"""

START_BLOCKING_RUN_STATUSES = frozenset(
    status for status in NON_TERMINAL_RUN_STATUSES if status is not RunStatus.QUEUED
)
"""阻塞启动新 Run 的 Run 状态集合。

当前假设是所有非终态 Run 状态都会阻塞同一 Session 启动新 Run，唯一例外是
``QUEUED``。该集合用于 accepted / start-blocking admission 查询，不等同于
active slot。未来新增不应阻塞启动的非终态 ``RunStatus`` 时，必须显式审查
admission 语义并更新本集合与 owner test。
"""

TERMINAL_ATTEMPT_STATUSES = frozenset(AttemptStatus(value) for value in TERMINAL_ATTEMPT_STATUS_VALUES)
"""Attempt 终态集合，作为 durable state terminal shape 的状态真源。"""

_TERMINAL_REFS_UNSET_WHERE_SQL = terminal_event_refs_unset_where_sql(indent="          ")
"""CAS WHERE 中 Run / Attempt terminal refs 全空谓词。"""

_WAIT_TERMINAL_AT_UNSET_WHERE_SQL = wait_terminal_at_unset_where_sql(indent="          ")
"""CAS WHERE 中 WaitRecord terminal_at 为空谓词。"""
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
  poll_claim_id,
  poll_claim_owner_id,
  poll_claimed_at,
  poll_claim_expires_at,
  poll_next_observe_at,
  poll_backoff_attempt,
  poll_last_outcome,
  poll_last_error_code,
  poll_last_error_message,
  poll_abandoned_at,
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
    """Run 进入 running 并创建新 Attempt 的原因。"""

    INITIAL = "initial"
    QUEUE_PROMOTION = "queue_promotion"
    RESUME = "resume"
    STEER = "steer"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class RunStartedPayload:
    """``RUN_STARTED`` canonical fact payload 的 typed projection。

    :param start_reason: Run 进入 active Attempt lifecycle 的闭集原因。
    """

    start_reason: RunStartReason

    def __post_init__(self) -> None:
        """校验 ``RUN_STARTED`` payload typed projection。

        :returns: 无返回值。
        :raises HostDurableError: ``start_reason`` 不是 ``RunStartReason`` 时抛出。
        """

        if not isinstance(self.start_reason, RunStartReason):
            raise HostDurableError("RUN_STARTED.start_reason is invalid")


class WaitRecordStatus(StrEnum):
    """Host durable wait record 状态。"""

    WAITING = WAIT_RECORD_WAITING_STATUS_VALUE
    RESOLVED = WAIT_RECORD_RESOLVED_STATUS_VALUE
    FAILED = WAIT_RECORD_FAILED_STATUS_VALUE
    CANCELLED = WAIT_RECORD_CANCELLED_STATUS_VALUE
    LOST = WAIT_RECORD_LOST_STATUS_VALUE


class WaitResumePolicy(StrEnum):
    """等待恢复策略。"""

    POLL = "poll"
    CALLBACK = "callback"
    MANUAL = "manual"


class WaitPollLastOutcome(StrEnum):
    """wait poller 最近一次 retry / diagnostic outcome。"""

    NOT_READY = "not_ready"
    ADAPTER_ERROR = "adapter_error"
    MISSING_ADAPTER = "missing_adapter"
    RESOLVE_ERROR = "resolve_error"
    BOUNDARY_REJECTED = "boundary_rejected"
    ABANDON_ERROR = "abandon_error"
    SHUTDOWN_SKIPPED = "shutdown_skipped"
    ABANDONED = "abandoned"
    ABANDON_UNSUPPORTED = "abandon_unsupported"
    ABANDON_NOOP = "abandon_noop"


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
class SessionWithSlotRows:
    """Session row 及其当前 slot row 的只读组合。

    :param session: ``host_sessions`` durable row。
    :param slot: 当前绑定到该 Session 的 slot row；匿名 Session 为 ``None``。
    """

    session: SessionRow
    slot: SessionSlotRow | None


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
    cancel_request_event_id: str | None
    current_attempt_id: str | None
    source_run_id: str | None
    source_run_relation: SourceRunRelation | None
    execution_target: str
    queue_policy: RunQueuePolicy
    created_at: str
    updated_at: str
    terminal_at: str | None


@dataclass(frozen=True, slots=True)
class NonTerminalRunKeysetCursor:
    """non-terminal Run recovery keyset cursor。

    :param accepted_event_sequence: Run accepted canonical fact 的全局序号。
    :param run_id: 同 sequence 下的稳定 tie-break Run id。
    """

    accepted_event_sequence: int
    run_id: str


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
    :param snapshot_digest: 快照摘要，必须是 Host durable sha256 digest。
    """

    snapshot_id: str
    captured_at: datetime
    snapshot_digest: str

    def __post_init__(self) -> None:
        """校验快照引用字段。

        :returns: ``None``。
        :raises HostDurableError: 快照 id 为空、超长、digest 格式无效或时间格式非法时抛出。
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
        _require_sha256_digest(self.snapshot_digest, field_name="snapshot_digest")


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
    poll_claim_id: str | None = None
    poll_claim_owner_id: str | None = None
    poll_claimed_at: str | None = None
    poll_claim_expires_at: str | None = None
    poll_next_observe_at: str | None = None
    poll_backoff_attempt: int = 0
    poll_last_outcome: WaitPollLastOutcome | None = None
    poll_last_error_code: str | None = None
    poll_last_error_message: str | None = None
    poll_abandoned_at: str | None = None


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

    return _deserialize_str_enum(value, enum_type=SessionStatus, enum_name="SessionStatus")


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


def is_terminal_run_status(status: RunStatus) -> bool:
    """判断 Run 状态是否为 durable 终态。

    :param status: Run 状态。
    :returns: 属于 durable Run 终态集合时返回 ``True``。
    :raises TypeError: ``status`` 不是 ``RunStatus`` 时抛出。
    """

    return is_public_terminal_run_status(status)


def serialized_run_status_values(
    statuses: frozenset[RunStatus] | tuple[RunStatus, ...],
) -> tuple[str, ...]:
    """把 Run 状态集合转换为 durable schema 文本值。

    :param statuses: Run 状态集合。传入 tuple 时保留调用方顺序；传入
        frozenset 时按 ``RunStatus`` 定义顺序输出，保证 SQL 参数稳定。
    :returns: schema 中存储的 Run status 文本 tuple。
    :raises HostDurableError: 任一状态不是合法 ``RunStatus`` 时抛出。
    """

    if isinstance(statuses, frozenset):
        ordered_statuses = tuple(status for status in RunStatus if status in statuses)
    else:
        ordered_statuses = statuses
    return tuple(serialize_run_status(status) for status in ordered_statuses)


def run_status_in_clause(
    statuses: frozenset[RunStatus] | tuple[RunStatus, ...],
) -> tuple[str, tuple[str, ...]]:
    """生成 Run status ``IN`` 谓词片段与参数。

    :param statuses: Run 状态集合。传入 tuple 时保留调用方顺序；传入
        frozenset 时按 ``RunStatus`` 定义顺序输出。
    :returns: SQL ``IN`` 片段与对应参数，例如 ``("IN (?, ?)", (...))``。
    :raises HostDurableError: 状态集合为空或任一状态非法时抛出。
    """

    params = serialized_run_status_values(statuses)
    if not params:
        raise HostDurableError("Run status IN clause statuses must not be empty")
    placeholders = ", ".join("?" for _status in params)
    return f"IN ({placeholders})", params


def serialize_attempt_status(status: AttemptStatus) -> str:
    """序列化公共 Attempt 状态。

    :param status: 公共 Attempt status enum。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``status`` 不是合法 ``AttemptStatus`` 时抛出。
    """

    return _serialize_str_enum(status, enum_name="AttemptStatus")


def is_terminal_attempt_status(status: AttemptStatus) -> bool:
    """判断 Attempt 状态是否为 durable 终态。

    :param status: Attempt 状态。
    :returns: 属于 durable Attempt 终态集合时返回 ``True``。
    :raises: 无主动抛出。
    """

    return status in TERMINAL_ATTEMPT_STATUSES


def deserialize_attempt_status(value: str) -> AttemptStatus:
    """反序列化公共 Attempt 状态。

    :param value: SQLite row 中读取的状态文本。
    :returns: ``AttemptStatus``。
    :raises HostDurableError: 文本为空或不属于 ``AttemptStatus`` 时抛出。
    """

    return _deserialize_str_enum(value, enum_type=AttemptStatus, enum_name="AttemptStatus")


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


def is_dispatch_record_direct_cancelable(record: DispatchRecordRow) -> bool:
    """判断 dispatch record 是否仍可在 worker 接受前直接取消。

    ``PENDING``、``WAITING_FOR_LANE`` 与尚无 worker accepted facts 的
    ``DISPATCHING`` 都属于 pre-worker direct cancel 边界。其它状态或已经
    写入 worker accepted facts 的 ``DISPATCHING`` 必须交给 active worker
    cancel 路径处理。

    :param record: durable dispatch record row。
    :returns: 可直接取消时返回 ``True``，否则返回 ``False``。
    :raises: 无主动抛出。
    """

    if record.status in (
        DispatchRecordStatus.PENDING,
        DispatchRecordStatus.WAITING_FOR_LANE,
    ):
        return True
    return (
        record.status is DispatchRecordStatus.DISPATCHING
        and record.worker_accepted_at is None
        and record.worker_accept_event_id is None
        and record.worker_accept_event_sequence is None
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

    return _deserialize_str_enum(value, enum_type=RunStartReason, enum_name="RunStartReason")


def decode_run_started_payload(payload: Mapping[str, JsonValue]) -> RunStartedPayload:
    """解码 ``RUN_STARTED`` canonical fact payload。

    ``start_reason`` 是必填闭集字段。缺失、非文本、空字符串或未知枚举值都
    表示 durable canonical fact 不满足 Host lifecycle contract，必须 fail
    closed，不能投影为 initial / follow-up fallback。

    :param payload: ``RUN_STARTED`` inline payload 映射。
    :returns: ``RunStartedPayload`` typed projection。
    :raises HostDurableError: payload 字段缺失、类型非法或枚举值未知时抛出。
    """

    value = payload.get("start_reason")
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError("RUN_STARTED.start_reason is required")
    return RunStartedPayload(start_reason=deserialize_run_start_reason(value))


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

    return _deserialize_str_enum(value, enum_type=WaitRecordStatus, enum_name="WaitRecordStatus")


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

    return _deserialize_str_enum(value, enum_type=WaitResumePolicy, enum_name="WaitResumePolicy")


def serialize_wait_poll_last_outcome(outcome: WaitPollLastOutcome | None) -> str | None:
    """序列化 wait poller 最近一次 outcome。

    :param outcome: 最近一次 outcome；无 outcome 时为 ``None``。
    :returns: schema 中存储的文本值。
    :raises HostDurableError: ``outcome`` 不是合法 ``WaitPollLastOutcome`` 时抛出。
    """

    if outcome is None:
        return None
    return _serialize_str_enum(outcome, enum_name="WaitPollLastOutcome")


def deserialize_wait_poll_last_outcome(value: str) -> WaitPollLastOutcome:
    """反序列化 wait poller 最近一次 outcome。

    :param value: SQLite row 中读取的 outcome 文本。
    :returns: ``WaitPollLastOutcome``。
    :raises HostDurableError: 文本为空或不属于 ``WaitPollLastOutcome`` 时抛出。
    """

    return _deserialize_str_enum(
        value, enum_type=WaitPollLastOutcome, enum_name="WaitPollLastOutcome"
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
    if snapshot_id is None or captured_at is None or snapshot_digest is None:
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


def deserialize_external_job_ref(adapter_key: WaitAdapterKey, external_job_id: str | None) -> ExternalJobRef | None:
    """从 adapter key 与外部 job id 列反序列化外部 job 引用。

    :param adapter_key: wait record adapter key。
    :param external_job_id: SQLite external job id 列。
    :returns: ``ExternalJobRef`` 或 ``None``。
    :raises HostDurableError: external job id 非法时抛出。
    """

    if external_job_id is None:
        return None
    return ExternalJobRef(adapter_key=adapter_key, external_job_id=external_job_id)


def _decode_scalar(row: HostRow, *, row_name: str, column: str) -> SQLiteScalar:
    """从 HostRow 读取 SQLite scalar，并稳定缺列错误边界。

    :param row: ``HostTransaction`` 查询返回的 row。
    :param row_name: 发生 decode 的 durable row 名称。
    :param column: 需要读取的列名。
    :returns: SQLite scalar 值。
    :raises HostRowDecodeError: row 缺少指定列时抛出。
    """

    try:
        return row.get(column)
    except KeyError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name=column, detail="missing column"),
            row_name=row_name,
            field_name=column,
        ) from exc


def _decode_required_text(row: HostRow, *, row_name: str, column: str) -> str:
    """从 HostRow 读取必填文本列。

    :param row: ``HostTransaction`` 查询返回的 row。
    :param row_name: 发生 decode 的 durable row 名称。
    :param column: 需要读取的列名。
    :returns: 文本值。
    :raises HostRowDecodeError: 列缺失或值不是 SQLite text 时抛出。
    """

    try:
        return _require_text(_decode_scalar(row, row_name=row_name, column=column), field_name=column)
    except HostRowDecodeError:
        raise
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name=column, detail=str(exc)),
            row_name=row_name,
            field_name=column,
        ) from exc


def _decode_optional_text(row: HostRow, *, row_name: str, column: str) -> str | None:
    """从 HostRow 读取 optional 文本列。

    :param row: ``HostTransaction`` 查询返回的 row。
    :param row_name: 发生 decode 的 durable row 名称。
    :param column: 需要读取的列名。
    :returns: 文本值或 ``None``。
    :raises HostRowDecodeError: 列缺失或值不是 SQLite text / null 时抛出。
    """

    try:
        return _optional_text(_decode_scalar(row, row_name=row_name, column=column), field_name=column)
    except HostRowDecodeError:
        raise
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name=column, detail=str(exc)),
            row_name=row_name,
            field_name=column,
        ) from exc


def _decode_required_int(row: HostRow, *, row_name: str, column: str) -> int:
    """从 HostRow 读取必填整数列。

    :param row: ``HostTransaction`` 查询返回的 row。
    :param row_name: 发生 decode 的 durable row 名称。
    :param column: 需要读取的列名。
    :returns: 整数值。
    :raises HostRowDecodeError: 列缺失或值不是 SQLite integer 时抛出。
    """

    try:
        return _require_int(_decode_scalar(row, row_name=row_name, column=column), field_name=column)
    except HostRowDecodeError:
        raise
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name=column, detail=str(exc)),
            row_name=row_name,
            field_name=column,
        ) from exc


def _decode_optional_int(row: HostRow, *, row_name: str, column: str) -> int | None:
    """从 HostRow 读取 optional 整数列。

    :param row: ``HostTransaction`` 查询返回的 row。
    :param row_name: 发生 decode 的 durable row 名称。
    :param column: 需要读取的列名。
    :returns: 整数值或 ``None``。
    :raises HostRowDecodeError: 列缺失或值不是 SQLite integer / null 时抛出。
    """

    try:
        return _optional_int(_decode_scalar(row, row_name=row_name, column=column), field_name=column)
    except HostRowDecodeError:
        raise
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name=column, detail=str(exc)),
            row_name=row_name,
            field_name=column,
        ) from exc


def _decode_enum(
    row: HostRow,
    *,
    row_name: str,
    column: str,
    deserializer: Callable[[str], _StatusT],
) -> _StatusT:
    """从 HostRow 读取文本列并反序列化为 enum。

    :param row: ``HostTransaction`` 查询返回的 row。
    :param row_name: 发生 decode 的 durable row 名称。
    :param column: 需要读取的 enum 文本列名。
    :param deserializer: enum 反序列化函数。
    :returns: enum 值。
    :raises HostRowDecodeError: 列缺失、标量类型错误或 enum 文本非法时抛出。
    """

    value = _decode_required_text(row, row_name=row_name, column=column)
    try:
        return deserializer(value)
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name=column, detail=str(exc)),
            row_name=row_name,
            field_name=column,
        ) from exc


def _wrap_row_decode_shape_error(
    *,
    row_name: str,
    detail: str,
) -> HostRowDecodeError:
    """把 row 级形状校验错误转换为 HostRowDecodeError。

    :param row_name: 发生 decode 的 durable row 名称。
    :param detail: 形状错误诊断。
    :returns: 待抛出的 ``HostRowDecodeError``。
    :raises HostDurableError: 本函数不主动抛出。
    """

    return HostRowDecodeError(
        _format_row_decode_error(row_name=row_name, field_name=None, detail=detail),
        row_name=row_name,
        field_name=None,
    )


def _format_row_decode_error(*, row_name: str, field_name: str | None, detail: str) -> str:
    """格式化 durable row decode 错误消息。

    :param row_name: 发生 decode 的 durable row 名称。
    :param field_name: 发生 decode 失败的字段名；row 级形状错误时为 ``None``。
    :param detail: 具体错误诊断。
    :returns: 稳定 row decode 错误消息。
    :raises HostDurableError: 本函数不主动抛出。
    """

    if field_name is None:
        return f"Host durable row decode failed: row={row_name}: {detail}"
    return f"Host durable row decode failed: row={row_name} field={field_name}: {detail}"


def session_row_from_host_row(row: HostRow) -> SessionRow:
    """把通用 HostRow 转换为 SessionRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``SessionRow``。
    :raises HostRowDecodeError: row 缺列、字段类型或状态 enum 值无效时抛出。
    """

    row_name = TABLE_HOST_SESSIONS
    return SessionRow(
        session_id=_decode_required_text(row, row_name=row_name, column="session_id"),
        status=_decode_enum(
            row,
            row_name=row_name,
            column="status",
            deserializer=deserialize_session_status,
        ),
        metadata_json=_decode_required_text(row, row_name=row_name, column="metadata_json"),
        created_event_id=_decode_required_text(row, row_name=row_name, column="created_event_id"),
        created_event_sequence=_decode_required_int(row, row_name=row_name, column="created_event_sequence"),
        closed_event_id=_decode_optional_text(row, row_name=row_name, column="closed_event_id"),
        closed_event_sequence=_decode_optional_int(row, row_name=row_name, column="closed_event_sequence"),
        created_at=_decode_required_text(row, row_name=row_name, column="created_at"),
        closed_at=_decode_optional_text(row, row_name=row_name, column="closed_at"),
    )


def session_slot_row_from_host_row(row: HostRow) -> SessionSlotRow:
    """把通用 HostRow 转换为 SessionSlotRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``SessionSlotRow``。
    :raises HostRowDecodeError: row 缺列或字段类型无效时抛出。
    """

    row_name = TABLE_HOST_SESSION_SLOTS
    return SessionSlotRow(
        scope=_decode_required_text(row, row_name=row_name, column="scope"),
        slot_key=_decode_required_text(row, row_name=row_name, column="slot_key"),
        session_id=_decode_required_text(row, row_name=row_name, column="session_id"),
        bound_event_id=_decode_required_text(row, row_name=row_name, column="bound_event_id"),
        bound_event_sequence=_decode_required_int(row, row_name=row_name, column="bound_event_sequence"),
        metadata_json=_decode_required_text(row, row_name=row_name, column="metadata_json"),
        updated_at=_decode_required_text(row, row_name=row_name, column="updated_at"),
    )


def _session_with_slot_rows_from_host_row(row: HostRow) -> SessionWithSlotRows:
    """把 Session/slot left join row 转换为强类型组合。

    :param row: ``HostTransaction`` 查询返回的 joined row。
    :returns: ``SessionWithSlotRows``。
    :raises HostDurableError: join row 字段类型或 left join 形状无效时抛出。
    """

    return SessionWithSlotRows(
        session=session_row_from_host_row(row),
        slot=_slot_row_from_session_list_host_row(row),
    )


def _slot_row_from_session_list_host_row(row: HostRow) -> SessionSlotRow | None:
    """从 Session list left join row 中解码可空 slot row。

    :param row: ``HostTransaction`` 查询返回的 joined row。
    :returns: ``SessionSlotRow`` 或 ``None``。
    :raises HostRowDecodeError: slot alias 缺列或字段类型非法时抛出。
    :raises HostDurableError: slot 字段只有部分为空时抛出。
    """

    row_name = TABLE_HOST_SESSION_SLOTS
    scope = _decode_optional_text(row, row_name=row_name, column="slot_scope")
    slot_key = _decode_optional_text(row, row_name=row_name, column="slot_slot_key")
    session_id = _decode_optional_text(
        row, row_name=row_name, column="slot_session_id"
    )
    bound_event_id = _decode_optional_text(
        row, row_name=row_name, column="slot_bound_event_id"
    )
    bound_event_sequence = _decode_optional_int(
        row,
        row_name=row_name,
        column="slot_bound_event_sequence",
    )
    metadata_json = _decode_optional_text(
        row, row_name=row_name, column="slot_metadata_json"
    )
    updated_at = _decode_optional_text(
        row, row_name=row_name, column="slot_updated_at"
    )
    slot_values = (
        scope,
        slot_key,
        session_id,
        bound_event_id,
        bound_event_sequence,
        metadata_json,
        updated_at,
    )
    if all(value is None for value in slot_values):
        return None
    if any(value is None for value in slot_values):
        raise HostDurableError("session slot left join row is incomplete")
    assert scope is not None
    assert slot_key is not None
    assert session_id is not None
    assert bound_event_id is not None
    assert bound_event_sequence is not None
    assert metadata_json is not None
    assert updated_at is not None
    return SessionSlotRow(
        scope=scope,
        slot_key=slot_key,
        session_id=session_id,
        bound_event_id=bound_event_id,
        bound_event_sequence=bound_event_sequence,
        metadata_json=metadata_json,
        updated_at=updated_at,
    )


def _decode_run_queue_policy(row: HostRow, *, row_name: str) -> RunQueuePolicy:
    """从 HostRow 读取并解析 Run queue policy。

    :param row: ``HostTransaction`` 查询返回的 row。
    :param row_name: 发生 decode 的 durable row 名称。
    :returns: 已由 owner 校验的 Run queue policy。
    :raises HostRowDecodeError: 列缺失、非文本或不属于合法闭集时抛出。
    """

    raw_policy = _decode_required_text(row, row_name=row_name, column="queue_policy")
    try:
        return parse_run_queue_policy(raw_policy)
    except ValueError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(
                row_name=row_name,
                field_name="queue_policy",
                detail=str(exc),
            ),
            row_name=row_name,
            field_name="queue_policy",
        ) from exc


def run_row_from_host_row(row: HostRow) -> RunRow:
    """把通用 HostRow 转换为 RunRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``RunRow``。
    :raises HostRowDecodeError: row 缺列、字段类型、状态 enum 或终态形状无效时抛出。
    """

    row_name = TABLE_HOST_RUNS
    source_relation_text = _decode_optional_text(row, row_name=row_name, column="source_run_relation")
    try:
        source_run_relation = _optional_source_run_relation(source_relation_text)
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name="source_run_relation", detail=str(exc)),
            row_name=row_name,
            field_name="source_run_relation",
        ) from exc
    status = _decode_enum(row, row_name=row_name, column="status", deserializer=deserialize_run_status)
    terminal_event_id = _decode_optional_text(row, row_name=row_name, column="terminal_event_id")
    terminal_event_sequence = _decode_optional_int(row, row_name=row_name, column="terminal_event_sequence")
    terminal_at = _decode_optional_text(row, row_name=row_name, column="terminal_at")
    run_row = RunRow(
        run_id=_decode_required_text(row, row_name=row_name, column="run_id"),
        session_id=_decode_required_text(row, row_name=row_name, column="session_id"),
        status=status,
        client_request_id=_decode_required_text(row, row_name=row_name, column="client_request_id"),
        input_event_id=_decode_required_text(row, row_name=row_name, column="input_event_id"),
        input_event_sequence=_decode_required_int(row, row_name=row_name, column="input_event_sequence"),
        accepted_event_id=_decode_required_text(row, row_name=row_name, column="accepted_event_id"),
        accepted_event_sequence=_decode_required_int(row, row_name=row_name, column="accepted_event_sequence"),
        queued_event_id=_decode_optional_text(row, row_name=row_name, column="queued_event_id"),
        queued_event_sequence=_decode_optional_int(row, row_name=row_name, column="queued_event_sequence"),
        started_event_id=_decode_optional_text(row, row_name=row_name, column="started_event_id"),
        started_event_sequence=_decode_optional_int(row, row_name=row_name, column="started_event_sequence"),
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        cancel_request_event_id=_decode_optional_text(
            row, row_name=row_name, column="cancel_request_event_id"
        ),
        current_attempt_id=_decode_optional_text(row, row_name=row_name, column="current_attempt_id"),
        source_run_id=_decode_optional_text(row, row_name=row_name, column="source_run_id"),
        source_run_relation=source_run_relation,
        execution_target=_decode_required_text(row, row_name=row_name, column="execution_target"),
        queue_policy=_decode_run_queue_policy(row, row_name=row_name),
        created_at=_decode_required_text(row, row_name=row_name, column="created_at"),
        updated_at=_decode_required_text(row, row_name=row_name, column="updated_at"),
        terminal_at=terminal_at,
    )
    try:
        validate_terminal_event_refs_shape(
            terminal_event_id=run_row.terminal_event_id,
            terminal_event_sequence=run_row.terminal_event_sequence,
            terminal_at=run_row.terminal_at,
            is_terminal=is_terminal_run_status(run_row.status),
            owner_label="Run",
        )
    except HostDurableError as exc:
        raise _wrap_row_decode_shape_error(row_name=row_name, detail=str(exc)) from exc
    return run_row


def attempt_row_from_host_row(row: HostRow) -> AttemptRow:
    """把通用 HostRow 转换为 AttemptRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``AttemptRow``。
    :raises HostRowDecodeError: row 缺列、字段类型、状态 enum 或终态形状无效时抛出。
    """

    row_name = TABLE_HOST_ATTEMPTS
    status = _decode_enum(row, row_name=row_name, column="status", deserializer=deserialize_attempt_status)
    terminal_event_id = _decode_optional_text(row, row_name=row_name, column="terminal_event_id")
    terminal_event_sequence = _decode_optional_int(row, row_name=row_name, column="terminal_event_sequence")
    terminal_at = _decode_optional_text(row, row_name=row_name, column="terminal_at")
    attempt_row = AttemptRow(
        attempt_id=_decode_required_text(row, row_name=row_name, column="attempt_id"),
        run_id=_decode_required_text(row, row_name=row_name, column="run_id"),
        execution_id=_decode_required_text(row, row_name=row_name, column="execution_id"),
        status=status,
        started_event_id=_decode_required_text(row, row_name=row_name, column="started_event_id"),
        started_event_sequence=_decode_required_int(row, row_name=row_name, column="started_event_sequence"),
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        created_at=_decode_required_text(row, row_name=row_name, column="created_at"),
        updated_at=_decode_required_text(row, row_name=row_name, column="updated_at"),
        terminal_at=terminal_at,
    )
    try:
        validate_terminal_event_refs_shape(
            terminal_event_id=attempt_row.terminal_event_id,
            terminal_event_sequence=attempt_row.terminal_event_sequence,
            terminal_at=attempt_row.terminal_at,
            is_terminal=is_terminal_attempt_status(attempt_row.status),
            owner_label="Attempt",
        )
    except HostDurableError as exc:
        raise _wrap_row_decode_shape_error(row_name=row_name, detail=str(exc)) from exc
    return attempt_row


def dispatch_record_row_from_host_row(row: HostRow) -> DispatchRecordRow:
    """把通用 HostRow 转换为 DispatchRecordRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``DispatchRecordRow``。
    :raises HostRowDecodeError: row 缺列、字段类型或状态 enum 值无效时抛出。
    """

    row_name = TABLE_HOST_ATTEMPT_DISPATCH_RECORDS
    return DispatchRecordRow(
        dispatch_record_id=_decode_required_text(row, row_name=row_name, column="dispatch_record_id"),
        run_id=_decode_required_text(row, row_name=row_name, column="run_id"),
        attempt_id=_decode_required_text(row, row_name=row_name, column="attempt_id"),
        execution_id=_decode_required_text(row, row_name=row_name, column="execution_id"),
        status=_decode_enum(
            row,
            row_name=row_name,
            column="status",
            deserializer=deserialize_dispatch_record_status,
        ),
        worker_kind=_decode_enum(row, row_name=row_name, column="worker_kind", deserializer=deserialize_worker_kind),
        execution_target=_decode_required_text(row, row_name=row_name, column="execution_target"),
        owner_host_instance_id=_decode_optional_text(row, row_name=row_name, column="owner_host_instance_id"),
        created_event_id=_decode_required_text(row, row_name=row_name, column="created_event_id"),
        created_event_sequence=_decode_required_int(row, row_name=row_name, column="created_event_sequence"),
        waiting_for_lane_at=_decode_optional_text(row, row_name=row_name, column="waiting_for_lane_at"),
        lane_name=_decode_optional_text(row, row_name=row_name, column="lane_name"),
        lane_claim_id=_decode_optional_text(row, row_name=row_name, column="lane_claim_id"),
        lane_owner_id=_decode_optional_text(row, row_name=row_name, column="lane_owner_id"),
        lane_acquired_at=_decode_optional_text(row, row_name=row_name, column="lane_acquired_at"),
        dispatching_at=_decode_optional_text(row, row_name=row_name, column="dispatching_at"),
        worker_accepted_at=_decode_optional_text(row, row_name=row_name, column="worker_accepted_at"),
        worker_accept_event_id=_decode_optional_text(row, row_name=row_name, column="worker_accept_event_id"),
        worker_accept_event_sequence=_decode_optional_int(
            row,
            row_name=row_name,
            column="worker_accept_event_sequence",
        ),
        cancelled_event_id=_decode_optional_text(row, row_name=row_name, column="cancelled_event_id"),
        cancelled_event_sequence=_decode_optional_int(row, row_name=row_name, column="cancelled_event_sequence"),
        created_at=_decode_required_text(row, row_name=row_name, column="created_at"),
        updated_at=_decode_required_text(row, row_name=row_name, column="updated_at"),
        cancelled_at=_decode_optional_text(row, row_name=row_name, column="cancelled_at"),
    )


def wait_record_row_from_host_row(row: HostRow) -> WaitRecordRow:
    """把通用 HostRow 转换为 WaitRecordRow。

    :param row: ``HostTransaction`` 查询返回的 row。
    :returns: ``WaitRecordRow``。
    :raises HostRowDecodeError: row 缺列、字段类型、状态 enum、typed ref 或终态形状无效时抛出。
    """

    row_name = TABLE_HOST_WAIT_RECORDS
    adapter_key_text = _decode_required_text(row, row_name=row_name, column="adapter_key")
    try:
        adapter_key = _wait_adapter_key_from_text(adapter_key_text)
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name="adapter_key", detail=str(exc)),
            row_name=row_name,
            field_name="adapter_key",
        ) from exc
    snapshot_ref_id = _decode_optional_text(row, row_name=row_name, column="snapshot_ref")
    snapshot_captured_at = _decode_optional_text(row, row_name=row_name, column="snapshot_captured_at")
    snapshot_digest = _decode_optional_text(row, row_name=row_name, column="snapshot_digest")
    try:
        snapshot_ref = deserialize_wait_snapshot_ref(
            snapshot_ref_id,
            snapshot_captured_at,
            snapshot_digest,
        )
    except HostDurableError as exc:
        raise _wrap_row_decode_shape_error(row_name=row_name, detail=str(exc)) from exc
    external_job_id = _decode_optional_text(row, row_name=row_name, column="external_job_id")
    try:
        external_job_ref = deserialize_external_job_ref(adapter_key, external_job_id)
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(row_name=row_name, field_name="external_job_id", detail=str(exc)),
            row_name=row_name,
            field_name="external_job_id",
        ) from exc
    status = _decode_enum(row, row_name=row_name, column="status", deserializer=deserialize_wait_record_status)
    terminal_at = _decode_optional_text(row, row_name=row_name, column="terminal_at")
    poll_last_outcome_text = _decode_optional_text(
        row, row_name=row_name, column="poll_last_outcome"
    )
    try:
        poll_last_outcome = (
            None
            if poll_last_outcome_text is None
            else deserialize_wait_poll_last_outcome(poll_last_outcome_text)
        )
    except HostDurableError as exc:
        raise HostRowDecodeError(
            _format_row_decode_error(
                row_name=row_name,
                field_name="poll_last_outcome",
                detail=str(exc),
            ),
            row_name=row_name,
            field_name="poll_last_outcome",
        ) from exc
    wait_row = WaitRecordRow(
        wait_id=_decode_required_text(row, row_name=row_name, column="wait_id"),
        session_id=_decode_required_text(row, row_name=row_name, column="session_id"),
        run_id=_decode_required_text(row, row_name=row_name, column="run_id"),
        attempt_id=_decode_required_text(row, row_name=row_name, column="attempt_id"),
        execution_id=_decode_required_text(row, row_name=row_name, column="execution_id"),
        tool_call_id=_decode_required_text(row, row_name=row_name, column="tool_call_id"),
        tool_name=_decode_required_text(row, row_name=row_name, column="tool_name"),
        adapter_key=adapter_key,
        await_kind=_decode_required_text(row, row_name=row_name, column="await_kind"),
        resume_policy=_decode_enum(
            row,
            row_name=row_name,
            column="resume_policy",
            deserializer=deserialize_wait_resume_policy,
        ),
        resume_token=_decode_required_text(row, row_name=row_name, column="resume_token"),
        snapshot_ref=snapshot_ref,
        external_job_ref=external_job_ref,
        accept_idempotency_key=_decode_required_text(row, row_name=row_name, column="accept_idempotency_key"),
        resolve_idempotency_key=_decode_optional_text(row, row_name=row_name, column="resolve_idempotency_key"),
        resolve_semantic_digest=_decode_optional_text(row, row_name=row_name, column="resolve_semantic_digest"),
        deadline_at=_decode_optional_text(row, row_name=row_name, column="deadline_at"),
        expires_at=_decode_optional_text(row, row_name=row_name, column="expires_at"),
        poll_claim_id=_decode_optional_text(row, row_name=row_name, column="poll_claim_id"),
        poll_claim_owner_id=_decode_optional_text(
            row, row_name=row_name, column="poll_claim_owner_id"
        ),
        poll_claimed_at=_decode_optional_text(row, row_name=row_name, column="poll_claimed_at"),
        poll_claim_expires_at=_decode_optional_text(
            row, row_name=row_name, column="poll_claim_expires_at"
        ),
        poll_next_observe_at=_decode_optional_text(
            row, row_name=row_name, column="poll_next_observe_at"
        ),
        poll_backoff_attempt=_decode_required_int(
            row, row_name=row_name, column="poll_backoff_attempt"
        ),
        poll_last_outcome=poll_last_outcome,
        poll_last_error_code=_decode_optional_text(
            row, row_name=row_name, column="poll_last_error_code"
        ),
        poll_last_error_message=_decode_optional_text(
            row, row_name=row_name, column="poll_last_error_message"
        ),
        poll_abandoned_at=_decode_optional_text(row, row_name=row_name, column="poll_abandoned_at"),
        status=status,
        created_event_id=_decode_required_text(row, row_name=row_name, column="created_event_id"),
        created_event_sequence=_decode_required_int(row, row_name=row_name, column="created_event_sequence"),
        updated_event_id=_decode_required_text(row, row_name=row_name, column="updated_event_id"),
        updated_event_sequence=_decode_required_int(row, row_name=row_name, column="updated_event_sequence"),
        created_at=_decode_required_text(row, row_name=row_name, column="created_at"),
        updated_at=_decode_required_text(row, row_name=row_name, column="updated_at"),
        terminal_at=terminal_at,
    )
    try:
        validate_wait_terminal_at_shape(status_value=wait_row.status.value, terminal_at=wait_row.terminal_at)
        _validate_wait_poll_fields(wait_row)
    except HostDurableError as exc:
        raise _wrap_row_decode_shape_error(row_name=row_name, detail=str(exc)) from exc
    return wait_row


def read_session_by_id(transaction: HostTransaction, session_id: str) -> SessionRow | None:
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


def read_all_sessions_with_slots(
    transaction: HostTransaction,
) -> tuple[SessionWithSlotRows, ...]:
    """读取全部未 purge Session 及其当前 slot row。

    本函数只读取 durable state 表，不读取 projection，不追加 EventLog。已
    purge Session 已从 ``host_sessions`` 删除，因此不会出现在结果中。

    :param transaction: 调用方提供的 Host transaction。
    :returns: 按 ``created_at DESC, session_id ASC`` 排序的 Session/slot 组合。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    rows = transaction.fetchall(
        f"""
        SELECT
          session.session_id,
          session.status,
          session.metadata_json,
          session.created_event_id,
          session.created_event_sequence,
          session.closed_event_id,
          session.closed_event_sequence,
          session.created_at,
          session.closed_at,
          slot.scope AS slot_scope,
          slot.slot_key AS slot_slot_key,
          slot.session_id AS slot_session_id,
          slot.bound_event_id AS slot_bound_event_id,
          slot.bound_event_sequence AS slot_bound_event_sequence,
          slot.metadata_json AS slot_metadata_json,
          slot.updated_at AS slot_updated_at
        FROM {TABLE_HOST_SESSIONS} AS session
        LEFT JOIN {TABLE_HOST_SESSION_SLOTS} AS slot
          ON slot.rowid = (
            SELECT current_slot.rowid
            FROM {TABLE_HOST_SESSION_SLOTS} AS current_slot
            WHERE current_slot.session_id = session.session_id
            ORDER BY current_slot.updated_at DESC,
              current_slot.scope ASC,
              current_slot.slot_key ASC
            LIMIT 1
          )
        ORDER BY session.created_at DESC, session.session_id ASC
        """,
        (),
    )
    return tuple(_session_with_slot_rows_from_host_row(row) for row in rows)


def read_session_slot(transaction: HostTransaction, scope: str, slot_key: str) -> SessionSlotRow | None:
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


def read_session_slot_by_session_id(transaction: HostTransaction, session_id: str) -> SessionSlotRow | None:
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
          cancel_request_event_id,
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


def read_active_run_for_session(transaction: HostTransaction, session_id: str) -> RunRow | None:
    """读取 Session 当前 active Run。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 有 active Run 时返回 ``RunRow``，否则返回 ``None``。
    :raises HostDurableError: ``session_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    status_clause, status_params = run_status_in_clause(START_BLOCKING_RUN_STATUSES)
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
          cancel_request_event_id,
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
          AND status {status_clause}
        ORDER BY accepted_event_sequence ASC, run_id ASC
        LIMIT 1
        """,
        (session_id, *status_params),
    )
    if row is None:
        return None
    return run_row_from_host_row(row)


def read_accepted_run_for_session(transaction: HostTransaction, session_id: str) -> RunRow | None:
    """读取 Session 下 pre-start accepted Run。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 有 accepted Run 时返回 ``RunRow``，否则返回 ``None``。
    :raises HostDurableError: ``session_id`` 为空或 row 字段无效时抛出。
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
          cancel_request_event_id,
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
        (session_id, serialize_run_status(RunStatus.ACCEPTED)),
    )
    if row is None:
        return None
    return run_row_from_host_row(row)


def read_earliest_queued_run(transaction: HostTransaction, session_id: str) -> RunRow | None:
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
          cancel_request_event_id,
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


def read_non_terminal_runs_for_session(transaction: HostTransaction, session_id: str) -> tuple[RunRow, ...]:
    """读取指定 Session 下所有非终态 Run。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: 按 accepted event sequence 升序排列的非终态 Run row 元组。
    :raises HostDurableError: ``session_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    status_clause, status_params = run_status_in_clause(NON_TERMINAL_RUN_STATUSES)
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
          cancel_request_event_id,
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
          AND status {status_clause}
        ORDER BY accepted_event_sequence ASC, run_id ASC
        """,
        (session_id, *status_params),
    )
    return tuple(run_row_from_host_row(row) for row in rows)


def read_non_terminal_run_upper_watermark_for_session(
    transaction: HostTransaction,
    session_id: str,
) -> NonTerminalRunKeysetCursor | None:
    """读取目标 Session recovery scan 的固定 non-terminal Run upper watermark。

    watermark 只来自 durable Run governance rows，并以
    ``(accepted_event_sequence, run_id)`` 全序确定边界；projection/read model
    不参与。

    :param transaction: 调用方提供的 Host read transaction。
    :param session_id: recovery attachment 对应的目标 Session id。
    :returns: 当前最大 keyset；没有 non-terminal Run 时返回 ``None``。
    :raises HostDurableError: watermark row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    status_clause, status_params = run_status_in_clause(NON_TERMINAL_RUN_STATUSES)
    row = transaction.fetchone(
        f"""
        SELECT
          accepted_event_sequence,
          run_id
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ?
          AND status {status_clause}
        ORDER BY accepted_event_sequence DESC, run_id DESC
        LIMIT 1
        """,
        (session_id, *status_params),
    )
    if row is None:
        return None
    accepted_event_sequence = _decode_required_int(
        row,
        row_name="non_terminal_run_upper_watermark",
        column="accepted_event_sequence",
    )
    run_id = _decode_required_text(
        row,
        row_name="non_terminal_run_upper_watermark",
        column="run_id",
    )
    _require_positive_sequence(
        accepted_event_sequence,
        "accepted_event_sequence",
    )
    _require_non_empty_text(run_id, field_name="run_id")
    return NonTerminalRunKeysetCursor(
        accepted_event_sequence=accepted_event_sequence,
        run_id=run_id,
    )


def read_non_terminal_runs_for_session_keyset_page(
    transaction: HostTransaction,
    *,
    session_id: str,
    upper_watermark: NonTerminalRunKeysetCursor,
    cursor: NonTerminalRunKeysetCursor | None,
    batch_size: int,
) -> tuple[RunRow, ...]:
    """读取目标 Session upper watermark 内下一页 non-terminal Run。

    查询严格使用 keyset，不使用 OFFSET。``fetchall`` 只消费带 ``LIMIT`` 的
    单个 bounded page。

    :param transaction: 调用方提供的 Host write transaction。
    :param session_id: recovery attachment 对应的目标 Session id。
    :param upper_watermark: scan 开始时固定的最大 keyset。
    :param cursor: 上一批最后处理的 keyset；首批为 ``None``。
    :param batch_size: 本页最大 Run row 数。
    :returns: 按 ``(accepted_event_sequence, run_id)`` 严格升序的 Run rows。
    :raises ValueError: watermark/cursor/batch size 非法时抛出。
    :raises HostDurableError: Run row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _validate_non_terminal_run_keyset(
        upper_watermark,
        field_name="upper_watermark",
    )
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise TypeError("batch_size must be int")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if cursor is not None:
        _validate_non_terminal_run_keyset(cursor, field_name="cursor")
        if _non_terminal_run_keyset_order(cursor) >= _non_terminal_run_keyset_order(
            upper_watermark
        ):
            return ()

    status_clause, status_params = run_status_in_clause(NON_TERMINAL_RUN_STATUSES)
    cursor_clause = ""
    cursor_params: tuple[int | str, ...] = ()
    if cursor is not None:
        cursor_clause = """
          AND (
            accepted_event_sequence > ?
            OR (accepted_event_sequence = ? AND run_id > ?)
          )
        """
        cursor_params = (
            cursor.accepted_event_sequence,
            cursor.accepted_event_sequence,
            cursor.run_id,
        )
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
          cancel_request_event_id,
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
          AND status {status_clause}
          AND (
            accepted_event_sequence < ?
            OR (accepted_event_sequence = ? AND run_id <= ?)
          )
          {cursor_clause}
        ORDER BY accepted_event_sequence ASC, run_id ASC
        LIMIT ?
        """,
        (
            session_id,
            *status_params,
            upper_watermark.accepted_event_sequence,
            upper_watermark.accepted_event_sequence,
            upper_watermark.run_id,
            *cursor_params,
            batch_size,
        ),
    )
    return tuple(run_row_from_host_row(row) for row in rows)


def _validate_non_terminal_run_keyset(
    keyset: NonTerminalRunKeysetCursor,
    *,
    field_name: str,
) -> None:
    """校验 recovery keyset 输入。

    :param keyset: 待校验 keyset。
    :param field_name: 错误字段前缀。
    :returns: ``None``。
    :raises TypeError: keyset 字段类型非法时抛出。
    :raises ValueError: sequence 非正或 run id 为空时抛出。
    """

    if isinstance(keyset.accepted_event_sequence, bool) or not isinstance(
        keyset.accepted_event_sequence,
        int,
    ):
        raise TypeError(f"{field_name}.accepted_event_sequence must be int")
    if keyset.accepted_event_sequence <= 0:
        raise ValueError(
            f"{field_name}.accepted_event_sequence must be positive"
        )
    if not isinstance(keyset.run_id, str):
        raise TypeError(f"{field_name}.run_id must be str")
    if keyset.run_id.strip() == "":
        raise ValueError(f"{field_name}.run_id must be non-empty")


def _non_terminal_run_keyset_order(
    keyset: NonTerminalRunKeysetCursor,
) -> tuple[int, str]:
    """返回 recovery keyset 的 Python 全序比较值。

    :param keyset: 已校验的 recovery keyset。
    :returns: sequence/run id tuple。
    :raises Exception: 不主动抛出异常。
    """

    return keyset.accepted_event_sequence, keyset.run_id


def read_cancelling_runs(transaction: HostTransaction) -> tuple[RunRow, ...]:
    """读取全部 ``CANCELLING`` Run。

    :param transaction: 调用方提供的 Host transaction。
    :returns: 按 accepted event sequence 升序排列的 cancelling Run row 元组。
    :raises HostDurableError: row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

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
          cancel_request_event_id,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        FROM {TABLE_HOST_RUNS}
        WHERE status = ?
        ORDER BY accepted_event_sequence ASC, run_id ASC
        """,
        (serialize_run_status(RunStatus.CANCELLING),),
    )
    return tuple(run_row_from_host_row(row) for row in rows)


def read_cancelling_runs_for_session(
    transaction: HostTransaction,
    session_id: str,
) -> tuple[RunRow, ...]:
    """读取目标 Session 的全部 ``CANCELLING`` Run。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: 目标 Session id。
    :returns: 按 accepted event sequence 升序排列的 cancelling Run row 元组。
    :raises HostDurableError: Session id 或 row 字段无效时抛出。
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
          cancel_request_event_id,
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
        """,
        (session_id, serialize_run_status(RunStatus.CANCELLING)),
    )
    return tuple(run_row_from_host_row(row) for row in rows)


def count_runs_by_source_relation(
    transaction: HostTransaction,
    *,
    source_run_id: str,
    source_run_relation: SourceRunRelation,
) -> int:
    """统计指定源 Run 已创建的关联 Run 数。

    :param transaction: 调用方提供的 Host transaction。
    :param source_run_id: 源 Run id。
    :param source_run_relation: 源关系类型。
    :returns: 已存在的关联 Run 数。
    :raises HostDurableError: 输入字段或查询结果非法时抛出。
    """

    _require_non_empty_text(source_run_id, field_name="source_run_id")
    if not isinstance(source_run_relation, SourceRunRelation):
        raise HostDurableError("source_run_relation is invalid")
    row = transaction.fetchone(
        f"""
        SELECT COUNT(*) AS related_count
        FROM {TABLE_HOST_RUNS}
        WHERE source_run_id = ? AND source_run_relation = ?
        """,
        (
            source_run_id,
            _optional_source_run_relation_text(source_run_relation),
        ),
    )
    if row is None:
        return 0
    return _require_int(row.get("related_count"), field_name="related_count")


def read_attempt_by_id(transaction: HostTransaction, attempt_id: str) -> AttemptRow | None:
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


def read_dispatch_record_by_attempt_id(transaction: HostTransaction, attempt_id: str) -> DispatchRecordRow | None:
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


def read_dispatch_record_by_id(transaction: HostTransaction, dispatch_record_id: str) -> DispatchRecordRow | None:
    """按 dispatch record id 读取 dispatch record row。

    :param transaction: 调用方提供的 Host transaction。
    :param dispatch_record_id: dispatch record id。
    :returns: 找到时返回 ``DispatchRecordRow``，否则返回 ``None``。
    :raises HostDurableError: ``dispatch_record_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(dispatch_record_id, field_name="dispatch_record_id")
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


def read_wait_record_by_id(transaction: HostTransaction, wait_id: str) -> WaitRecordRow | None:
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


def read_active_wait_records_for_run(transaction: HostTransaction, run_id: str) -> tuple[WaitRecordRow, ...]:
    """读取 Run 下仍处于 waiting 的 wait records。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :returns: active wait record 元组，按创建事件序号升序排列。
    :raises HostDurableError: ``run_id`` 为空或 row 字段无效时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    rows = transaction.fetchall(
        _WAIT_RECORD_SELECT_SQL + """
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
        _WAIT_RECORD_SELECT_SQL + """
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


def read_next_wait_record_poll_due_at(
    transaction: HostTransaction,
    *,
    now: str,
) -> str | None:
    """读取当前 active poll wait 的下一次可观察时间。

    本 helper 只用于 poller 空轮询后的 scheduler sleep 计算。若存在已经
    due 的 wait record，claim path 应先处理它；本 helper 返回未来最早的
    ``poll_next_observe_at`` 或未过期 claim 的 ``poll_claim_expires_at``。

    :param transaction: 调用方提供的 Host transaction。
    :param now: 当前 UTC timestamp 文本。
    :returns: 下一次可观察 UTC timestamp；没有 active poll wait 时为 ``None``。
    :raises HostDurableError: ``now`` 为空或 SQLite row 字段非法时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(now, field_name="now")
    row = transaction.fetchone(
        f"""
        SELECT MIN(
          CASE
            WHEN poll_claim_id IS NOT NULL AND poll_claim_expires_at > ?
              THEN poll_claim_expires_at
            WHEN poll_next_observe_at IS NOT NULL AND poll_next_observe_at > ?
              THEN poll_next_observe_at
            ELSE NULL
          END
        ) AS next_due_at
        FROM {TABLE_HOST_WAIT_RECORDS}
        WHERE resume_policy = ?
          AND (
            status = ?
            OR (status = ? AND poll_abandoned_at IS NULL)
          )
          AND (
            (poll_claim_id IS NOT NULL AND poll_claim_expires_at > ?)
            OR (poll_next_observe_at IS NOT NULL AND poll_next_observe_at > ?)
          )
        """,
        (
            now,
            now,
            serialize_wait_resume_policy(WaitResumePolicy.POLL),
            serialize_wait_record_status(WaitRecordStatus.WAITING),
            serialize_wait_record_status(WaitRecordStatus.CANCELLED),
            now,
            now,
        ),
    )
    if row is None:
        return None
    return _optional_text(row.get("next_due_at"), field_name="next_due_at")


def claim_wait_record_for_poll(
    transaction: HostTransaction,
    *,
    claim_id: str,
    owner_id: str,
    now: str,
    claim_expires_at: str,
) -> WaitRecordMutationResult:
    """原子 claim 一条当前可 poll 的 wait record。

    本 helper 允许先读取候选 wait id，但只有同一 write transaction 内随后
    的 ``UPDATE ... WHERE`` 成功才表示 claim 已取得；调用方不得用候选读取
    结果触发 adapter 调用。

    :param transaction: 调用方提供的 Host transaction。
    :param claim_id: 本次 claim 唯一 id。
    :param owner_id: poller 实例 owner id。
    :param now: 当前 UTC timestamp 文本。
    :param claim_expires_at: claim 过期 UTC timestamp 文本。
    :returns: wait record mutation 结果；无候选为 ``NOT_FOUND``。
    :raises HostDurableError: 输入字段非法时抛出。
    """

    _validate_poll_claim_inputs(
        claim_id=claim_id,
        owner_id=owner_id,
        now=now,
        claim_expires_at=claim_expires_at,
    )
    candidate = transaction.fetchone(
        f"""
        SELECT wait_id
        FROM {TABLE_HOST_WAIT_RECORDS}
        WHERE resume_policy = ?
          AND (
            status = ?
            OR (status = ? AND poll_abandoned_at IS NULL)
          )
          AND (poll_next_observe_at IS NULL OR poll_next_observe_at <= ?)
          AND (poll_claim_id IS NULL OR poll_claim_expires_at <= ?)
        ORDER BY created_event_sequence ASC, wait_id ASC
        LIMIT 1
        """,
        (
            serialize_wait_resume_policy(WaitResumePolicy.POLL),
            serialize_wait_record_status(WaitRecordStatus.WAITING),
            serialize_wait_record_status(WaitRecordStatus.CANCELLED),
            now,
            now,
        ),
    )
    if candidate is None:
        return WaitRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    wait_id = _require_text(candidate.get("wait_id"), field_name="wait_id")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_WAIT_RECORDS}
        SET
          poll_claim_id = ?,
          poll_claim_owner_id = ?,
          poll_claimed_at = ?,
          poll_claim_expires_at = ?
        WHERE wait_id = ?
          AND resume_policy = ?
          AND (
            status = ?
            OR (status = ? AND poll_abandoned_at IS NULL)
          )
          AND (poll_next_observe_at IS NULL OR poll_next_observe_at <= ?)
          AND (poll_claim_id IS NULL OR poll_claim_expires_at <= ?)
        """,
        (
            claim_id,
            owner_id,
            now,
            claim_expires_at,
            wait_id,
            serialize_wait_resume_policy(WaitResumePolicy.POLL),
            serialize_wait_record_status(WaitRecordStatus.WAITING),
            serialize_wait_record_status(WaitRecordStatus.CANCELLED),
            now,
            now,
        ),
    )
    return _wait_record_poll_mutation_result(
        transaction, wait_id=wait_id, rowcount=result.rowcount
    )


def release_wait_record_poll_claim(
    transaction: HostTransaction,
    *,
    wait_id: str,
    claim_id: str,
    next_observe_at: str,
    backoff_attempt: int,
    last_outcome: WaitPollLastOutcome,
    last_error_code: str | None,
    last_error_message: str | None,
    updated_at: str,
) -> WaitRecordMutationResult:
    """释放匹配的 wait poll claim 并写入下一次观察时间。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param claim_id: 调用方已取得的 claim id，必须与 row 当前 claim 匹配。
    :param next_observe_at: 下次可观察 UTC timestamp 文本。
    :param backoff_attempt: 写入的 backoff attempt 计数。
    :param last_outcome: 最近一次 poller outcome。
    :param last_error_code: 最近一次错误码；无错误时为 ``None``。
    :param last_error_message: 最近一次错误消息；无错误时为 ``None``。
    :param updated_at: 更新时间文本。
    :returns: wait record mutation 结果。
    :raises HostDurableError: 输入字段非法时抛出。
    """

    _validate_poll_release_inputs(
        wait_id=wait_id,
        claim_id=claim_id,
        next_observe_at=next_observe_at,
        backoff_attempt=backoff_attempt,
        last_outcome=last_outcome,
        last_error_code=last_error_code,
        last_error_message=last_error_message,
        updated_at=updated_at,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_WAIT_RECORDS}
        SET
          poll_claim_id = NULL,
          poll_claim_owner_id = NULL,
          poll_claimed_at = NULL,
          poll_claim_expires_at = NULL,
          poll_next_observe_at = ?,
          poll_backoff_attempt = ?,
          poll_last_outcome = ?,
          poll_last_error_code = ?,
          poll_last_error_message = ?,
          updated_at = ?
        WHERE wait_id = ?
          AND poll_claim_id = ?
          AND status IN (?, ?)
        """,
        (
            next_observe_at,
            backoff_attempt,
            serialize_wait_poll_last_outcome(last_outcome),
            last_error_code,
            last_error_message,
            updated_at,
            wait_id,
            claim_id,
            serialize_wait_record_status(WaitRecordStatus.WAITING),
            serialize_wait_record_status(WaitRecordStatus.CANCELLED),
        ),
    )
    return _wait_record_poll_mutation_result(
        transaction, wait_id=wait_id, rowcount=result.rowcount
    )


def mark_wait_record_poll_abandoned(
    transaction: HostTransaction,
    *,
    wait_id: str,
    claim_id: str,
    abandoned_at: str,
    updated_at: str,
    last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED,
) -> WaitRecordMutationResult:
    """标记 cancelled wait 的外部 abandon 已完成并释放 claim。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param claim_id: 调用方已取得的 claim id，必须与 row 当前 claim 匹配。
    :param abandoned_at: abandon 完成 UTC timestamp 文本。
    :param updated_at: 更新时间文本。
    :param last_outcome: 写入的 terminal lifecycle diagnostic outcome。
    :returns: wait record mutation 结果。
    :raises HostDurableError: 输入字段非法时抛出。
    """

    _require_text_max_length(wait_id, field_name="wait_id", max_length=HOST_WAIT_ID_MAX_LENGTH)
    _require_text_max_length(
        claim_id,
        field_name="poll_claim_id",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_non_empty_text(abandoned_at, field_name="poll_abandoned_at")
    _require_non_empty_text(updated_at, field_name="updated_at")
    if not isinstance(last_outcome, WaitPollLastOutcome):
        raise HostDurableError("poll_last_outcome is invalid")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_WAIT_RECORDS}
        SET
          poll_claim_id = NULL,
          poll_claim_owner_id = NULL,
          poll_claimed_at = NULL,
          poll_claim_expires_at = NULL,
          poll_next_observe_at = NULL,
          poll_backoff_attempt = 0,
          poll_last_outcome = ?,
          poll_last_error_code = NULL,
          poll_last_error_message = NULL,
          poll_abandoned_at = ?,
          updated_at = ?
        WHERE wait_id = ?
          AND poll_claim_id = ?
          AND status = ?
          AND poll_abandoned_at IS NULL
        """,
        (
            serialize_wait_poll_last_outcome(last_outcome),
            abandoned_at,
            updated_at,
            wait_id,
            claim_id,
            serialize_wait_record_status(WaitRecordStatus.CANCELLED),
        ),
    )
    return _wait_record_poll_mutation_result(
        transaction, wait_id=wait_id, rowcount=result.rowcount
    )


def insert_session(transaction: HostTransaction, session: SessionRow) -> None:
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


def insert_session_slot(transaction: HostTransaction, slot: SessionSlotRow) -> None:
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


def upsert_session_slot(transaction: HostTransaction, slot: SessionSlotRow) -> None:
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
          cancel_request_event_id,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            run.cancel_request_event_id,
            run.current_attempt_id,
            run.source_run_id,
            _optional_source_run_relation_text(run.source_run_relation),
            run.execution_target,
            run.queue_policy.value,
            run.created_at,
            run.updated_at,
            run.terminal_at,
        ),
    )


def set_new_run_source_relation_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    expected_status: RunStatus,
    source_run_id: str,
    source_run_relation: SourceRunRelation,
    updated_at: str,
) -> RunMutationResult:
    """CAS 为新建 Run 写入 retry / replay 源 Run 关系。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 新建关联 Run id。
    :param expected_status: 新建 Run 当前期望状态，只允许 accepted 或 queued。
    :param source_run_id: 源 Run id。
    :param source_run_relation: 源关系类型。
    :param updated_at: 固定 UTC 更新时间文本。
    :returns: Run mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    if expected_status not in (RunStatus.ACCEPTED, RunStatus.QUEUED):
        raise HostDurableError("source relation target status is invalid")
    _require_non_empty_text(source_run_id, field_name="source_run_id")
    if not isinstance(source_run_relation, SourceRunRelation):
        raise HostDurableError("source_run_relation is invalid")
    _require_non_empty_text(updated_at, field_name="updated_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          source_run_id = ?,
          source_run_relation = ?,
          updated_at = ?
        WHERE run_id = ?
          AND status = ?
          AND source_run_id IS NULL
          AND source_run_relation IS NULL
          AND current_attempt_id IS NULL
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            source_run_id,
            _optional_source_run_relation_text(source_run_relation),
            updated_at,
            run_id,
            serialize_run_status(expected_status),
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=expected_status,
        cas_lost_when_expected=True,
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


def insert_dispatch_record(transaction: HostTransaction, dispatch_record: DispatchRecordRow) -> None:
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
          poll_claim_id,
          poll_claim_owner_id,
          poll_claimed_at,
          poll_claim_expires_at,
          poll_next_observe_at,
          poll_backoff_attempt,
          poll_last_outcome,
          poll_last_error_code,
          poll_last_error_message,
          poll_abandoned_at,
          status,
          created_event_id,
          created_event_sequence,
          updated_event_id,
          updated_event_sequence,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            row.poll_claim_id,
            row.poll_claim_owner_id,
            row.poll_claimed_at,
            row.poll_claim_expires_at,
            row.poll_next_observe_at,
            row.poll_backoff_attempt,
            serialize_wait_poll_last_outcome(row.poll_last_outcome),
            row.poll_last_error_code,
            row.poll_last_error_message,
            row.poll_abandoned_at,
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
        status = StateMutationStatus.INVALID_STATE if existing > 0 else StateMutationStatus.NOT_FOUND
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
{_WAIT_TERMINAL_AT_UNSET_WHERE_SQL}
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
        return WaitRecordsMutationResult(status=StateMutationStatus.UPDATED, rows=rows)
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
    status_clause, status_params = run_status_in_clause(START_BLOCKING_RUN_STATUSES)
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
              AND active_run.status {status_clause}
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
            *status_params,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.QUEUED,
        cas_lost_when_expected=True,
    )


def start_unstarted_run_row(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    expected_status: RunStatus,
    started_event_id: str,
    started_event_sequence: int,
    current_attempt_id: str,
    updated_at: str,
) -> RunMutationResult:
    """CAS 将 accepted 或 queued Run 推进到 running。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Run 所属 Session id。
    :param run_id: 目标 Run id。
    :param expected_status: 期望源状态，只允许 accepted 或 queued。
    :param started_event_id: ``RUN_STARTED`` 事件 id。
    :param started_event_sequence: ``RUN_STARTED`` 全局事件序号。
    :param current_attempt_id: 新建 current Attempt id。
    :param updated_at: 固定 UTC timestamp 文本。
    :returns: Run mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    if expected_status not in (RunStatus.ACCEPTED, RunStatus.QUEUED):
        raise HostDurableError("unstarted Run source status is invalid")
    _validate_run_start_update(
        session_id=session_id,
        run_id=run_id,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        current_attempt_id=current_attempt_id,
        updated_at=updated_at,
    )
    status_clause, status_params = run_status_in_clause(START_BLOCKING_RUN_STATUSES)
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
          AND started_event_id IS NULL
          AND started_event_sequence IS NULL
          AND current_attempt_id IS NULL
{_TERMINAL_REFS_UNSET_WHERE_SQL}
          AND NOT EXISTS (
            SELECT 1
            FROM {TABLE_HOST_RUNS} active_run
            WHERE active_run.session_id = ?
              AND active_run.run_id <> ?
              AND active_run.status {status_clause}
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
            serialize_run_status(expected_status),
            session_id,
            run_id,
            *status_params,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=expected_status,
        cas_lost_when_expected=True,
    )


def terminal_unstarted_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    expected_status: RunStatus,
    terminal_status: RunStatus,
    terminal_event_id: str,
    terminal_event_sequence: int,
    cancel_request_event_id: str | None,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 将未创建 Attempt 的 Run 收口到终态。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param expected_status: 期望源状态，只允许 accepted 或 queued。
    :param terminal_status: 目标终态，只允许 failed 或 cancelled。
    :param terminal_event_id: terminal 事件 id。
    :param terminal_event_sequence: terminal 事件全局序号。
    :param cancel_request_event_id: cancelled 终态对应的 ``CANCEL_REQUESTED`` event id；
        failed 终态必须为 ``None``。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    if expected_status not in (RunStatus.ACCEPTED, RunStatus.QUEUED):
        raise HostDurableError("unstarted Run source status is invalid")
    if terminal_status not in (RunStatus.FAILED, RunStatus.CANCELLED):
        raise HostDurableError("unstarted Run terminal status is invalid")
    _validate_run_terminal_update(
        run_id=run_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    _validate_terminal_cancel_request_link(
        terminal_status=terminal_status,
        cancel_request_event_id=cancel_request_event_id,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          cancel_request_event_id = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status = ?
          AND started_event_id IS NULL
          AND started_event_sequence IS NULL
          AND current_attempt_id IS NULL
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(terminal_status),
            terminal_event_id,
            terminal_event_sequence,
            cancel_request_event_id,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(expected_status),
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=expected_status,
        cas_lost_when_expected=True,
    )


def cancel_queued_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    cancel_request_event_id: str,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 取消 queued Run。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param terminal_event_id: ``RUN_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``RUN_CANCELLED`` 全局事件序号。
    :param cancel_request_event_id: 对应 ``CANCEL_REQUESTED`` event id。
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
    _require_non_empty_text(
        cancel_request_event_id, field_name="cancel_request_event_id"
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          cancel_request_event_id = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status = ?
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            cancel_request_event_id,
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
    cancel_request_event_id: str,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 取消 pre-dispatch running Run。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param terminal_event_id: ``RUN_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``RUN_CANCELLED`` 全局事件序号。
    :param cancel_request_event_id: 对应 ``CANCEL_REQUESTED`` event id。
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
    _require_non_empty_text(
        cancel_request_event_id, field_name="cancel_request_event_id"
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          cancel_request_event_id = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            cancel_request_event_id,
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

    ``cancel_request_event_id`` 在 Run 进入 ``CANCELLING`` 时已经固定；
    schema 保证 ``CANCELLING`` row 必须持有该 typed cancel link。本 mutator
    只写入 terminal refs 与 ``CANCELLED`` 状态，保留原有 cancel link。

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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
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
        terminal_status=RunStatus.CANCELLED,
        terminal_event_id=terminal_event_id,
    )


def mark_run_cancelling_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    cancel_request_event_id: str,
    updated_at: str,
) -> RunMutationResult:
    """CAS 将 active running Run 标记为 cancelling。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param cancel_request_event_id: 对应 ``CANCEL_REQUESTED`` event id。
    :param updated_at: 固定 UTC timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found/invalid_state。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    _require_non_empty_text(
        cancel_request_event_id, field_name="cancel_request_event_id"
    )
    _require_non_empty_text(updated_at, field_name="updated_at")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          cancel_request_event_id = ?,
          updated_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.CANCELLING),
            cancel_request_event_id,
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
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
    _require_non_empty_text(suspended_attempt_id, field_name="suspended_attempt_id")
    status_clause, status_params = run_status_in_clause(START_BLOCKING_RUN_STATUSES)
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
          AND NOT EXISTS (
            SELECT 1
            FROM {TABLE_HOST_RUNS} active_run
            WHERE active_run.session_id = ?
              AND active_run.run_id <> ?
              AND active_run.status {status_clause}
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
            *status_params,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.WAITING,
        cas_lost_when_expected=True,
    )


def steer_active_run_row(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    previous_attempt_id: str,
    next_attempt_id: str,
    input_event_id: str,
    input_event_sequence: int,
    started_event_id: str,
    started_event_sequence: int,
    updated_at: str,
) -> RunMutationResult:
    """CAS 将 active Run 切换到 steer 创建的新 Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Run 所属 Session id。
    :param run_id: 目标 Run id。
    :param previous_attempt_id: 期望的旧 current Attempt id。
    :param next_attempt_id: 新建 steer Attempt id。
    :param input_event_id: steer 输入事件 id。
    :param input_event_sequence: steer 输入事件序号。
    :param started_event_id: ``RUN_STARTED`` steer 事件 id。
    :param started_event_sequence: ``RUN_STARTED`` steer 事件序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :returns: Run mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _validate_run_start_update(
        session_id=session_id,
        run_id=run_id,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        current_attempt_id=next_attempt_id,
        updated_at=updated_at,
    )
    _require_non_empty_text(previous_attempt_id, field_name="previous_attempt_id")
    _require_non_empty_text(input_event_id, field_name="input_event_id")
    _require_positive_sequence(input_event_sequence, "input_event_sequence")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          input_event_id = ?,
          input_event_sequence = ?,
          started_event_id = ?,
          started_event_sequence = ?,
          current_attempt_id = ?,
          updated_at = ?
        WHERE run_id = ?
          AND session_id = ?
          AND status IN (?, ?)
          AND current_attempt_id = ?
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.RUNNING),
            input_event_id,
            input_event_sequence,
            started_event_id,
            started_event_sequence,
            next_attempt_id,
            updated_at,
            run_id,
            session_id,
            serialize_run_status(RunStatus.RUNNING),
            serialize_run_status(RunStatus.WAITING),
            previous_attempt_id,
        ),
    )
    return _run_mutation_result_for_active(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        terminal_status=None,
        terminal_event_id=None,
    )


def steer_running_attempt_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> AttemptMutationResult:
    """CAS 将 RUNNING Attempt 标记为 STEERED。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt_id: 目标 Attempt id。
    :param terminal_event_id: ``ATTEMPT_STEERED`` 事件 id。
    :param terminal_event_sequence: ``ATTEMPT_STEERED`` 事件序号。
    :param terminal_at: 固定 UTC 终态时间文本。
    :returns: Attempt mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
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
            serialize_attempt_status(AttemptStatus.STEERED),
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


def mark_running_run_recovering_row(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    current_attempt_id: str,
    recovering_event_id: str,
    recovering_event_sequence: int,
    updated_at: str,
) -> RunMutationResult:
    """CAS 将 running Run 标记为 recovering。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Run 所属 Session id。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param recovering_event_id: ``RUN_RECOVERING`` 事件 id。
    :param recovering_event_sequence: ``RUN_RECOVERING`` 全局事件序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :returns: Run mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _validate_run_start_update(
        session_id=session_id,
        run_id=run_id,
        started_event_id=recovering_event_id,
        started_event_sequence=recovering_event_sequence,
        current_attempt_id=current_attempt_id,
        updated_at=updated_at,
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          updated_at = ?
        WHERE run_id = ?
          AND session_id = ?
          AND status = ?
          AND current_attempt_id = ?
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.RECOVERING),
            updated_at,
            run_id,
            session_id,
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


def start_recovering_run_row(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    source_attempt_id: str,
    recovered_attempt_id: str,
    started_event_id: str,
    started_event_sequence: int,
    updated_at: str,
) -> RunMutationResult:
    """CAS 将 recovering Run 恢复为 running 并切换 current Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Run 所属 Session id。
    :param run_id: 目标 Run id。
    :param source_attempt_id: 期望的旧 Attempt id。
    :param recovered_attempt_id: 新建 recovery Attempt id。
    :param started_event_id: ``RUN_STARTED`` recovery 事件 id。
    :param started_event_sequence: ``RUN_STARTED`` recovery 事件序号。
    :param updated_at: 固定 UTC 更新时间文本。
    :returns: Run mutation 结果。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _validate_run_start_update(
        session_id=session_id,
        run_id=run_id,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        current_attempt_id=recovered_attempt_id,
        updated_at=updated_at,
    )
    _require_non_empty_text(source_attempt_id, field_name="source_attempt_id")
    status_clause, status_params = run_status_in_clause(START_BLOCKING_RUN_STATUSES)
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
          AND NOT EXISTS (
            SELECT 1
            FROM {TABLE_HOST_RUNS} active_run
            WHERE active_run.session_id = ?
              AND active_run.run_id <> ?
              AND active_run.status {status_clause}
          )
        """,
        (
            serialize_run_status(RunStatus.RUNNING),
            started_event_id,
            started_event_sequence,
            recovered_attempt_id,
            updated_at,
            run_id,
            session_id,
            serialize_run_status(RunStatus.RECOVERING),
            source_attempt_id,
            session_id,
            run_id,
            *status_params,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.RECOVERING,
        cas_lost_when_expected=True,
    )


def terminal_recovering_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 将 recovering Run 失败收口。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param terminal_event_id: ``RUN_FAILED`` 事件 id。
    :param terminal_event_sequence: ``RUN_FAILED`` 全局事件序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果。
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.FAILED),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(RunStatus.RECOVERING),
            current_attempt_id,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.RECOVERING,
        cas_lost_when_expected=True,
    )


def cancel_recovering_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    cancel_request_event_id: str,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 将 recovering Run 取消收口。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param terminal_event_id: ``RUN_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``RUN_CANCELLED`` 全局事件序号。
    :param cancel_request_event_id: 对应 ``CANCEL_REQUESTED`` event id。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果，区分 updated/cas_lost/not_found。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _validate_run_terminal_update(
        run_id=run_id,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )
    _require_non_empty_text(current_attempt_id, field_name="current_attempt_id")
    _require_non_empty_text(
        cancel_request_event_id, field_name="cancel_request_event_id"
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          cancel_request_event_id = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            cancel_request_event_id,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(RunStatus.RECOVERING),
            current_attempt_id,
        ),
    )
    row = read_run_by_id(transaction, run_id)
    if result.rowcount == 1:
        return RunMutationResult(status=StateMutationStatus.UPDATED, row=row)
    if row is None:
        return RunMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    return RunMutationResult(status=StateMutationStatus.CAS_LOST, row=row)


def cancel_waiting_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    cancel_request_event_id: str,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 取消 waiting Run。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 SUSPENDED Attempt id。
    :param terminal_event_id: ``RUN_CANCELLED`` 事件 id。
    :param terminal_event_sequence: ``RUN_CANCELLED`` 全局事件序号。
    :param cancel_request_event_id: 对应 ``CANCEL_REQUESTED`` event id。
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
    _require_non_empty_text(
        cancel_request_event_id, field_name="cancel_request_event_id"
    )
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_RUNS}
        SET
          status = ?,
          terminal_event_id = ?,
          terminal_event_sequence = ?,
          cancel_request_event_id = ?,
          updated_at = ?,
          terminal_at = ?
        WHERE run_id = ?
          AND status = ?
          AND current_attempt_id = ?
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.CANCELLED),
            terminal_event_id,
            terminal_event_sequence,
            cancel_request_event_id,
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
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
        terminal_status=terminal_status,
        terminal_event_id=terminal_event_id,
    )


def terminal_orphaned_run_lost_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    expected_status: RunStatus,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 将 startup orphan Run 收口为 lost。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param expected_status: 期望源状态，只允许 running 或 cancelling。
    :param terminal_event_id: ``RUN_LOST`` event id。
    :param terminal_event_sequence: ``RUN_LOST`` event sequence。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果。
    :raises HostDurableError: 输入字段或状态无效时抛出。
    """

    if expected_status not in (RunStatus.RUNNING, RunStatus.CANCELLING):
        raise HostDurableError("orphaned Run source status is invalid")
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.LOST),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(expected_status),
            current_attempt_id,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=expected_status,
        cas_lost_when_expected=True,
    )


def terminal_recovering_run_lost_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    current_attempt_id: str,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """CAS 将 recovering Run 收口为 lost。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: 目标 Run id。
    :param current_attempt_id: 期望的 current Attempt id。
    :param terminal_event_id: ``RUN_LOST`` event id。
    :param terminal_event_sequence: ``RUN_LOST`` event sequence。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果。
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
        """,
        (
            serialize_run_status(RunStatus.LOST),
            terminal_event_id,
            terminal_event_sequence,
            terminal_at,
            terminal_at,
            run_id,
            serialize_run_status(RunStatus.RECOVERING),
            current_attempt_id,
        ),
    )
    return _run_mutation_result(
        transaction,
        run_id=run_id,
        rowcount=result.rowcount,
        expected_status=RunStatus.RECOVERING,
        cas_lost_when_expected=True,
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
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
{_TERMINAL_REFS_UNSET_WHERE_SQL}
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
    _require_non_empty_text(owner_host_instance_id, field_name="owner_host_instance_id")
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
          AND cancelled_event_sequence IS NULL
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
    _require_non_empty_text(owner_host_instance_id, field_name="owner_host_instance_id")
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
    _require_non_empty_text(worker_accept_event_id, field_name="worker_accept_event_id")
    _require_positive_sequence(worker_accept_event_sequence, "worker_accept_event_sequence")
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
          AND cancelled_event_sequence IS NULL
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
        status=_public_session_status_from_durable(session.status),
        slot=_slot_ref_from_row(slot),
        active_run_id=_read_active_run_id(transaction, session.session_id),
        queued_run_ids=_read_queued_run_ids(transaction, session.session_id),
        timeline_cursor=HostStreamCursor(event_sequence=_session_timeline_cursor(session)),
    )


def run_snapshot_from_row(run: RunRow) -> RunSnapshot:
    """由 durable Run row 构造公共 RunSnapshot。

    Phase 4 尚无 typed terminal payload decoder；终态 Run 只能稳定返回
    status-only ``TerminalResultSummary``，不从 EventLog payload 字符串中做
    ad hoc JSON 解析。

    :param run: durable Run row。
    :returns: 公共 Run snapshot。
    :raises HostDurableError: Run status 不是当前公共状态 enum 时抛出。
    :raises ValueError: Run row 字段无法满足公共 snapshot 约束时抛出。
    """

    status = _public_run_status_from_durable(run.status)
    return RunSnapshot(
        run_id=run.run_id,
        session_id=run.session_id,
        status=status,
        current_attempt_id=run.current_attempt_id,
        terminal_result_summary=_terminal_result_summary_from_status(status),
        event_cursor=HostStreamCursor(event_sequence=_run_event_cursor(run)),
        source_run_id=run.source_run_id,
        source_run_relation=run.source_run_relation,
        outbox_summary=None,
    )


def _public_session_status_from_durable(status: SessionStatus) -> SessionStatus:
    """把 durable Session row 状态映射为 public SessionStatus。

    :param status: durable row 中的 Session 状态。
    :returns: public SessionStatus。
    :raises HostDurableError: 状态不是当前 public enum 成员时抛出。
    """

    if not isinstance(status, SessionStatus):
        raise HostDurableError("Session row status is invalid")
    return status


def _public_run_status_from_durable(status: RunStatus) -> RunStatus:
    """把 durable Run row 状态映射为 public RunStatus。

    :param status: durable row 中的 Run 状态。
    :returns: public RunStatus。
    :raises HostDurableError: 状态不是当前 public enum 成员时抛出。
    """

    if not isinstance(status, RunStatus):
        raise HostDurableError("Run row status is invalid")
    return status


def _terminal_result_summary_from_status(
    status: RunStatus,
) -> TerminalResultSummary | None:
    """按 Run 状态生成 public 终态摘要。

    :param status: durable Run 状态。
    :returns: 终态返回 status-only 摘要；非终态返回 ``None``。
    :raises ValueError: status-only 终态摘要无法满足公共类型约束时抛出。
    """

    if status not in TERMINAL_RUN_STATUSES:
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


def _deserialize_str_enum(value: str, *, enum_type: type[_StatusT], enum_name: str) -> _StatusT:
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
    _require_positive_sequence(run.accepted_event_sequence, "accepted_event_sequence")
    _require_optional_non_empty_text(run.queued_event_id, field_name="queued_event_id")
    _require_optional_positive_sequence(run.queued_event_sequence, "queued_event_sequence")
    _require_optional_non_empty_text(run.started_event_id, field_name="started_event_id")
    _require_optional_positive_sequence(run.started_event_sequence, "started_event_sequence")
    _require_optional_non_empty_text(run.terminal_event_id, field_name="terminal_event_id")
    _require_optional_positive_sequence(run.terminal_event_sequence, "terminal_event_sequence")
    _require_optional_non_empty_text(
        run.cancel_request_event_id, field_name="cancel_request_event_id"
    )
    _require_optional_non_empty_text(run.current_attempt_id, field_name="current_attempt_id")
    _require_optional_non_empty_text(run.source_run_id, field_name="source_run_id")
    _require_non_empty_text(run.execution_target, field_name="execution_target")
    if not isinstance(run.queue_policy, RunQueuePolicy):
        raise HostDurableError("Run queue_policy is invalid")
    _require_non_empty_text(run.created_at, field_name="created_at")
    _require_non_empty_text(run.updated_at, field_name="updated_at")
    _require_optional_non_empty_text(run.terminal_at, field_name="terminal_at")
    if run.status == RunStatus.QUEUED:
        if run.queued_event_id is None or run.queued_event_sequence is None:
            raise HostDurableError("queued Run requires queue event refs")
        if run.current_attempt_id is not None:
            raise HostDurableError("queued Run current_attempt_id must be unset")
    if run.status == RunStatus.ACCEPTED:
        if run.queued_event_id is not None or run.queued_event_sequence is not None:
            raise HostDurableError("accepted Run queue refs must be unset")
        if run.started_event_id is not None or run.started_event_sequence is not None:
            raise HostDurableError("accepted Run start refs must be unset")
        if run.current_attempt_id is not None:
            raise HostDurableError("accepted Run current_attempt_id must be unset")
    validate_terminal_event_refs_shape(
        terminal_event_id=run.terminal_event_id,
        terminal_event_sequence=run.terminal_event_sequence,
        terminal_at=run.terminal_at,
        is_terminal=is_terminal_run_status(run.status),
        owner_label="Run",
    )
    if (run.source_run_id is None) != (run.source_run_relation is None):
        raise HostDurableError("Run source relation fields must be paired")


def _validate_terminal_cancel_request_link(
    *, terminal_status: RunStatus, cancel_request_event_id: str | None
) -> None:
    """校验 Run terminal mutation 的取消链路形状。

    :param terminal_status: 目标 Run terminal status。
    :param cancel_request_event_id: 可选 ``CANCEL_REQUESTED`` event id。
    :returns: ``None``。
    :raises HostDurableError: cancelled 缺少 link 或非 cancelled 携带 link 时抛出。
    """

    if terminal_status == RunStatus.CANCELLED:
        if cancel_request_event_id is None:
            raise HostDurableError("cancelled Run terminal requires cancel link")
        _require_non_empty_text(
            cancel_request_event_id, field_name="cancel_request_event_id"
        )
        return
    if cancel_request_event_id is not None:
        raise HostDurableError("non-cancelled Run terminal cannot carry cancel link")


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
    _require_non_empty_text(attempt.started_event_id, field_name="started_event_id")
    _require_positive_sequence(attempt.started_event_sequence, "started_event_sequence")
    _require_optional_non_empty_text(attempt.terminal_event_id, field_name="terminal_event_id")
    _require_optional_positive_sequence(attempt.terminal_event_sequence, "terminal_event_sequence")
    _require_non_empty_text(attempt.created_at, field_name="created_at")
    _require_non_empty_text(attempt.updated_at, field_name="updated_at")
    _require_optional_non_empty_text(attempt.terminal_at, field_name="terminal_at")
    validate_terminal_event_refs_shape(
        terminal_event_id=attempt.terminal_event_id,
        terminal_event_sequence=attempt.terminal_event_sequence,
        terminal_at=attempt.terminal_at,
        is_terminal=is_terminal_attempt_status(attempt.status),
        owner_label="Attempt",
    )


def _validate_dispatch_record_for_insert(
    dispatch_record: DispatchRecordRow,
) -> None:
    """校验待插入 dispatch record row。

    :param dispatch_record: 待校验 dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: 任一字段违反 Phase 3 dispatch row 约束时抛出。
    """

    _require_non_empty_text(dispatch_record.dispatch_record_id, field_name="dispatch_record_id")
    _require_non_empty_text(dispatch_record.run_id, field_name="run_id")
    _require_non_empty_text(dispatch_record.attempt_id, field_name="attempt_id")
    _require_non_empty_text(dispatch_record.execution_id, field_name="execution_id")
    if not isinstance(dispatch_record.status, DispatchRecordStatus):
        raise HostDurableError("dispatch record status is invalid")
    if not isinstance(dispatch_record.worker_kind, WorkerKind):
        raise HostDurableError("worker kind is invalid")
    _require_non_empty_text(dispatch_record.execution_target, field_name="execution_target")
    _require_optional_non_empty_text(
        dispatch_record.owner_host_instance_id,
        field_name="owner_host_instance_id",
    )
    _require_non_empty_text(dispatch_record.created_event_id, field_name="created_event_id")
    _require_positive_sequence(dispatch_record.created_event_sequence, "created_event_sequence")
    _require_optional_non_empty_text(dispatch_record.waiting_for_lane_at, field_name="waiting_for_lane_at")
    _require_optional_non_empty_text(dispatch_record.lane_name, field_name="lane_name")
    _require_optional_non_empty_text(dispatch_record.lane_claim_id, field_name="lane_claim_id")
    _require_optional_non_empty_text(dispatch_record.lane_owner_id, field_name="lane_owner_id")
    _require_optional_non_empty_text(dispatch_record.lane_acquired_at, field_name="lane_acquired_at")
    _require_optional_non_empty_text(dispatch_record.dispatching_at, field_name="dispatching_at")
    _require_optional_non_empty_text(dispatch_record.worker_accepted_at, field_name="worker_accepted_at")
    _require_optional_non_empty_text(
        dispatch_record.worker_accept_event_id,
        field_name="worker_accept_event_id",
    )
    _require_optional_positive_sequence(
        dispatch_record.worker_accept_event_sequence,
        "worker_accept_event_sequence",
    )
    _require_optional_non_empty_text(dispatch_record.cancelled_event_id, field_name="cancelled_event_id")
    _require_optional_positive_sequence(dispatch_record.cancelled_event_sequence, "cancelled_event_sequence")
    _require_non_empty_text(dispatch_record.created_at, field_name="created_at")
    _require_non_empty_text(dispatch_record.updated_at, field_name="updated_at")
    _require_optional_non_empty_text(dispatch_record.cancelled_at, field_name="cancelled_at")
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
    _require_positive_sequence(terminal_event_sequence, "terminal_event_sequence")
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
    _require_positive_sequence(terminal_event_sequence, "terminal_event_sequence")
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
    transaction: HostTransaction,
    *,
    run_id: str,
    rowcount: int,
    terminal_status: RunStatus | None,
    terminal_event_id: str | None,
) -> RunMutationResult:
    """构造 active Run terminal mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param run_id: Run id。
    :param rowcount: UPDATE rowcount。
    :param terminal_status: 本次写入期望的终态；非终态 active mutation 传
        ``None``。
    :param terminal_event_id: 本次写入期望的 terminal event id；非终态
        active mutation 传 ``None``。
    :returns: Run mutation 结果。
    """

    latest = read_run_by_id(transaction, run_id)
    if rowcount == 1:
        return RunMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return RunMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if (
        terminal_status is not None
        and terminal_event_id is not None
        and latest.status == terminal_status
        and latest.terminal_event_id == terminal_event_id
    ):
        return RunMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest.status in (
        RunStatus.RUNNING,
        RunStatus.WAITING,
        RunStatus.CANCELLING,
        RunStatus.RECOVERING,
    ) or is_terminal_run_status(latest.status):
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
        return AttemptMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return AttemptMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if latest.status == expected_status and cas_lost_when_expected:
        return AttemptMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return AttemptMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


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
        return AttemptMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return AttemptMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if latest.status in (AttemptStatus.STARTING, AttemptStatus.RUNNING):
        return AttemptMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return AttemptMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


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
        return DispatchRecordMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return DispatchRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if latest.status in (
        DispatchRecordStatus.PENDING,
        DispatchRecordStatus.WAITING_FOR_LANE,
    ):
        return DispatchRecordMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return DispatchRecordMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


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
        return DispatchRecordMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return DispatchRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if (
        latest.status == DispatchRecordStatus.DISPATCHING
        and latest.worker_accept_event_id is None
        and latest.worker_accept_event_sequence is None
        and latest.worker_accepted_at is None
    ):
        return DispatchRecordMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return DispatchRecordMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


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
        return DispatchRecordMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return DispatchRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if latest.status == DispatchRecordStatus.WAITING_FOR_LANE:
        return DispatchRecordMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return DispatchRecordMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


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

    dispatch_record = read_dispatch_record_by_attempt_id(transaction, attempt_id)
    if dispatch_record is None:
        return DispatchRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    attempt = read_attempt_by_id(transaction, attempt_id)
    if attempt is None:
        return DispatchRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=dispatch_record)
    run = read_run_by_id(transaction, dispatch_record.run_id)
    if run is None:
        return DispatchRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=dispatch_record)
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
        return DispatchRecordMutationResult(status=StateMutationStatus.INVALID_STATE, row=dispatch_record)
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

    _require_text_max_length(row.wait_id, field_name="wait_id", max_length=HOST_WAIT_ID_MAX_LENGTH)
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
    if row.snapshot_ref is not None and not isinstance(row.snapshot_ref, WaitSnapshotRef):
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
    _validate_wait_poll_fields(row)
    _require_non_empty_text(row.created_event_id, field_name="created_event_id")
    _require_positive_sequence(row.created_event_sequence, "created_event_sequence")
    _require_non_empty_text(row.updated_event_id, field_name="updated_event_id")
    _require_positive_sequence(row.updated_event_sequence, "updated_event_sequence")
    _require_non_empty_text(row.created_at, field_name="created_at")
    _require_non_empty_text(row.updated_at, field_name="updated_at")
    _require_optional_non_empty_text(row.terminal_at, field_name="terminal_at")
    validate_wait_terminal_at_shape(status_value=row.status.value, terminal_at=row.terminal_at)


def _validate_wait_poll_fields(row: WaitRecordRow) -> None:
    """校验 wait record poll claim / backoff 字段形状。

    :param row: 待校验 wait record row。
    :returns: ``None``。
    :raises HostDurableError: poll 字段组合非法时抛出。
    """

    _require_optional_text_max_length(
        row.poll_claim_id,
        field_name="poll_claim_id",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_optional_text_max_length(
        row.poll_claim_owner_id,
        field_name="poll_claim_owner_id",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_optional_non_empty_text(row.poll_claimed_at, field_name="poll_claimed_at")
    _require_optional_non_empty_text(
        row.poll_claim_expires_at, field_name="poll_claim_expires_at"
    )
    _require_optional_non_empty_text(
        row.poll_next_observe_at, field_name="poll_next_observe_at"
    )
    if row.poll_backoff_attempt < 0:
        raise HostDurableError("poll_backoff_attempt must be non-negative")
    if row.poll_last_outcome is not None and not isinstance(
        row.poll_last_outcome, WaitPollLastOutcome
    ):
        raise HostDurableError("poll_last_outcome is invalid")
    _require_optional_non_empty_text(
        row.poll_last_error_code, field_name="poll_last_error_code"
    )
    _require_optional_non_empty_text(
        row.poll_last_error_message, field_name="poll_last_error_message"
    )
    _require_optional_non_empty_text(
        row.poll_abandoned_at, field_name="poll_abandoned_at"
    )
    claim_values = (
        row.poll_claim_id,
        row.poll_claim_owner_id,
        row.poll_claimed_at,
        row.poll_claim_expires_at,
    )
    if any(value is None for value in claim_values) and any(
        value is not None for value in claim_values
    ):
        raise HostDurableError("poll claim fields must be all set or all unset")
    if row.poll_abandoned_at is not None and row.status is not WaitRecordStatus.CANCELLED:
        raise HostDurableError("poll_abandoned_at requires cancelled wait")


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
    _require_optional_non_empty_text(row.resolve_semantic_digest, field_name="resolve_semantic_digest")
    if (row.resolve_idempotency_key is None) != (row.resolve_semantic_digest is None):
        raise HostDurableError("wait resolve fields must be paired")
    if (
        row.status
        in (
            WaitRecordStatus.RESOLVED,
            WaitRecordStatus.FAILED,
            WaitRecordStatus.LOST,
        )
        and row.resolve_idempotency_key is None
    ):
        raise HostDurableError("resolved, failed or lost wait requires resolve refs")
    if (
        row.status
        in (
            WaitRecordStatus.WAITING,
            WaitRecordStatus.CANCELLED,
        )
        and row.resolve_idempotency_key is not None
    ):
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
          terminal_at = ?,
          poll_claim_id = NULL,
          poll_claim_owner_id = NULL,
          poll_claimed_at = NULL,
          poll_claim_expires_at = NULL,
          poll_next_observe_at = NULL,
          poll_backoff_attempt = 0
        WHERE wait_id = ? AND status = ?
{_WAIT_TERMINAL_AT_UNSET_WHERE_SQL}
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
    return _wait_record_mutation_result(transaction, wait_id=wait_id, rowcount=result.rowcount)


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

    _require_text_max_length(wait_id, field_name="wait_id", max_length=HOST_WAIT_ID_MAX_LENGTH)
    _require_optional_text_max_length(
        resolve_idempotency_key,
        field_name="resolve_idempotency_key",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_optional_non_empty_text(resolve_semantic_digest, field_name="resolve_semantic_digest")
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
        return WaitRecordMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return WaitRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if latest.status == WaitRecordStatus.WAITING:
        return WaitRecordMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return WaitRecordMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


def _wait_record_poll_mutation_result(
    transaction: HostTransaction, *, wait_id: str, rowcount: int
) -> WaitRecordMutationResult:
    """构造 poll claim / release mutation 结果。

    :param transaction: 调用方提供的 Host transaction。
    :param wait_id: wait record id。
    :param rowcount: UPDATE rowcount。
    :returns: wait record mutation 结果。
    """

    latest = read_wait_record_by_id(transaction, wait_id)
    if rowcount == 1:
        return WaitRecordMutationResult(status=StateMutationStatus.UPDATED, row=latest)
    if latest is None:
        return WaitRecordMutationResult(status=StateMutationStatus.NOT_FOUND, row=None)
    if latest.status in (WaitRecordStatus.WAITING, WaitRecordStatus.CANCELLED):
        return WaitRecordMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
    return WaitRecordMutationResult(status=StateMutationStatus.INVALID_STATE, row=latest)


def _validate_poll_claim_inputs(
    *,
    claim_id: str,
    owner_id: str,
    now: str,
    claim_expires_at: str,
) -> None:
    """校验 poll claim 输入。

    :param claim_id: 本次 claim 唯一 id。
    :param owner_id: poller 实例 owner id。
    :param now: 当前 UTC timestamp 文本。
    :param claim_expires_at: claim 过期 UTC timestamp 文本。
    :returns: ``None``。
    :raises HostDurableError: 任一字段非法时抛出。
    """

    _require_text_max_length(
        claim_id,
        field_name="poll_claim_id",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_text_max_length(
        owner_id,
        field_name="poll_claim_owner_id",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_non_empty_text(now, field_name="now")
    _require_non_empty_text(claim_expires_at, field_name="poll_claim_expires_at")


def _validate_poll_release_inputs(
    *,
    wait_id: str,
    claim_id: str,
    next_observe_at: str,
    backoff_attempt: int,
    last_outcome: WaitPollLastOutcome,
    last_error_code: str | None,
    last_error_message: str | None,
    updated_at: str,
) -> None:
    """校验 poll claim release 输入。

    :param wait_id: wait record id。
    :param claim_id: claim id。
    :param next_observe_at: 下次可观察时间。
    :param backoff_attempt: backoff attempt 计数。
    :param last_outcome: 最近一次 outcome。
    :param last_error_code: 最近一次错误码。
    :param last_error_message: 最近一次错误消息。
    :param updated_at: 更新时间文本。
    :returns: ``None``。
    :raises HostDurableError: 任一字段非法时抛出。
    """

    _require_text_max_length(wait_id, field_name="wait_id", max_length=HOST_WAIT_ID_MAX_LENGTH)
    _require_text_max_length(
        claim_id,
        field_name="poll_claim_id",
        max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    )
    _require_non_empty_text(next_observe_at, field_name="poll_next_observe_at")
    if backoff_attempt < 0:
        raise HostDurableError("poll_backoff_attempt must be non-negative")
    if not isinstance(last_outcome, WaitPollLastOutcome):
        raise HostDurableError("poll_last_outcome is invalid")
    _require_optional_non_empty_text(
        last_error_code, field_name="poll_last_error_code"
    )
    _require_optional_non_empty_text(
        last_error_message, field_name="poll_last_error_message"
    )
    _require_non_empty_text(updated_at, field_name="updated_at")


def _read_wait_record_count_for_run(transaction: HostTransaction, run_id: str) -> int:
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
        _WAIT_RECORD_SELECT_SQL + """
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


def _require_optional_positive_sequence(value: int | None, field_name: str) -> None:
    """校验 optional 事件序号。

    :param value: 事件序号或 ``None``。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 序号存在且小于等于零时抛出。
    """

    if value is not None:
        _require_positive_sequence(value, field_name)


def _require_text_max_length(value: str, *, field_name: str, max_length: int) -> None:
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


def _require_optional_text_max_length(value: str | None, *, field_name: str, max_length: int) -> None:
    """校验 optional 文本存在时非空且不超过长度上限。

    :param value: 待校验文本或 ``None``。
    :param field_name: 字段名。
    :param max_length: 最大字符数。
    :returns: ``None``。
    :raises HostDurableError: 文本存在但为空或超长时抛出。
    """

    if value is not None:
        _require_text_max_length(value, field_name=field_name, max_length=max_length)


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


def _read_active_run_id(transaction: HostTransaction, session_id: str) -> str | None:
    """读取 Session 当前 active Run id。

    :param transaction: 调用方提供的 Host transaction。
    :param session_id: Session id。
    :returns: active Run id；不存在时为 ``None``。
    :raises HostDurableError: row 字段无效时抛出。
    """

    status_clause, status_params = run_status_in_clause(START_BLOCKING_RUN_STATUSES)
    row = transaction.fetchone(
        f"""
        SELECT run_id
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ?
          AND status {status_clause}
        ORDER BY accepted_event_sequence ASC, run_id ASC
        LIMIT 1
        """,
        (session_id, *status_params),
    )
    if row is None:
        return None
    return _require_text(row.get("run_id"), field_name="run_id")


def _read_queued_run_ids(transaction: HostTransaction, session_id: str) -> tuple[str, ...]:
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
