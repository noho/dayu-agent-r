"""Host durable Run / Attempt transition primitives。

本模块实现 Phase 3 P3-S3 的低层 Run / Attempt / dispatch record 状态迁移。
所有 helper 都接收调用方提供的 ``HostTransaction``，在同一 transaction 内
append canonical EventLog facts 并更新 durable state row；本模块不打开事务、
不注册 after-commit callback、不做 admission policy、queue scanning
orchestration、WorkerProxy、Engine dispatch 或 public facade。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host.api import AttemptStatus, CancelMode, RunStatus
from dayu.host.durable._validation import (
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_optional_sha256_digest as _require_optional_sha256_digest,
    require_sha256_digest as _require_sha256_digest,
)
from dayu.host.durable.codec import format_utc_timestamp, parse_utc_timestamp
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.liveness import HostInstanceStatus, read_host_instance
from dayu.host.durable.state import (
    AttemptMutationResult,
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordMutationResult,
    DispatchRecordStatus,
    RunRow,
    RunMutationResult,
    RunStartReason,
    StateMutationStatus,
    WaitRecordMutationResult,
    WaitRecordRow,
    WaitRecordStatus,
    WorkerKind,
    cancel_cancelling_run_row,
    cancel_active_wait_records_for_run,
    cancel_recovering_run_row,
    cancel_waiting_run_row,
    cancel_running_attempt_row,
    cancel_starting_dispatch_record_row,
    cancel_queued_run_row,
    cancel_running_run_row,
    cancel_starting_attempt_row,
    insert_attempt,
    insert_dispatch_record,
    insert_run,
    mark_wait_record_failed_row,
    mark_wait_record_lost_row,
    mark_wait_record_resolved_row,
    mark_attempt_running_row,
    mark_dispatch_worker_accepted_row,
    mark_running_run_recovering_row,
    mark_run_cancelling_row,
    promote_queued_run_row,
    read_active_run_for_session,
    read_active_wait_records_for_run,
    read_attempt_by_id,
    read_dispatch_record_by_id,
    read_dispatch_record_by_attempt_id,
    read_earliest_queued_run,
    read_run_by_id,
    read_wait_record_by_id,
    resume_waiting_run_row,
    start_recovering_run_row,
    start_unstarted_run_row,
    terminal_attempt_row,
    terminal_orphaned_run_lost_row,
    terminal_recovering_run_lost_row,
    terminal_recovering_run_row,
    terminal_unstarted_run_row,
    terminal_run_row,
)
from dayu.host.durable.transaction import HostTransaction

_EVENT_TYPE_RUN_ACCEPTED = "RUN_ACCEPTED"
_EVENT_TYPE_RUN_QUEUED = "RUN_QUEUED"
_EVENT_TYPE_RUN_STARTED = "RUN_STARTED"
_EVENT_TYPE_ATTEMPT_STARTED = "ATTEMPT_STARTED"
_EVENT_TYPE_RUN_RECOVERING = "RUN_RECOVERING"
_EVENT_TYPE_ATTEMPT_RUNNING = "ATTEMPT_RUNNING"
_EVENT_TYPE_CANCEL_REQUESTED = "CANCEL_REQUESTED"
_EVENT_TYPE_RUN_CANCELLING = "RUN_CANCELLING"
_EVENT_TYPE_ATTEMPT_CANCELLED = "ATTEMPT_CANCELLED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_EVENT_TYPE_ATTEMPT_SUCCEEDED = "ATTEMPT_SUCCEEDED"
_EVENT_TYPE_ATTEMPT_FAILED = "ATTEMPT_FAILED"
_EVENT_TYPE_ATTEMPT_LOST = "ATTEMPT_LOST"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
_EVENT_TYPE_RUN_LOST = "RUN_LOST"
_EVENT_TYPE_RESUME_REQUESTED = "RESUME_REQUESTED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_TERMINAL_STATUS_PAIRS: tuple[tuple[AttemptStatus, RunStatus], ...] = (
    (AttemptStatus.SUCCEEDED, RunStatus.SUCCEEDED),
    (AttemptStatus.FAILED, RunStatus.FAILED),
    (AttemptStatus.CANCELLED, RunStatus.CANCELLED),
    (AttemptStatus.LOST, RunStatus.LOST),
)


class PromotionSkipReason(StrEnum):
    """queue promotion 跳过原因文本常量。"""

    NO_QUEUED_RUN = "no_queued_run"
    ACTIVE_RUN_EXISTS = "active_run_exists"
    CAS_LOST_OR_NO_LONGER_ELIGIBLE = "cas_lost_or_no_longer_eligible"


@dataclass(frozen=True, slots=True)
class CreateQueuedRunInput:
    """创建 queued Run 的输入。

    :param session_id: 所属 Session id。
    :param run_id: 调用方生成的 Run id。
    :param client_request_id: 客户端幂等请求 id。
    :param input_event_id: 已存在 ``USER_INPUT_ACCEPTED`` event id。
    :param input_event_sequence: 已存在 ``USER_INPUT_ACCEPTED`` event sequence。
    :param run_accepted_event_id: 调用方生成的 ``RUN_ACCEPTED`` event id。
    :param run_queued_event_id: 调用方生成的 ``RUN_QUEUED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param idempotency_key: 幂等 key。
    :param execution_target: 已解析执行目标。
    :param queue_policy: Run queue policy。
    :param queue_reason: 排队原因。
    :param active_run_id: 接受时阻塞该 Run 的 active Run id。
    :param call_context_digest: 调用上下文 digest。
    """

    session_id: str
    run_id: str
    client_request_id: str
    input_event_id: str
    input_event_sequence: int
    run_accepted_event_id: str
    run_queued_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    idempotency_key: str
    execution_target: str
    queue_policy: str
    queue_reason: str
    active_run_id: str
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class CreateAcceptedRunInput:
    """创建 pre-start accepted Run 的输入。

    :param session_id: 所属 Session id。
    :param run_id: 调用方生成的 Run id。
    :param client_request_id: 客户端幂等请求 id。
    :param input_event_id: 已存在 ``USER_INPUT_ACCEPTED`` event id。
    :param input_event_sequence: 已存在 ``USER_INPUT_ACCEPTED`` event sequence。
    :param run_accepted_event_id: 调用方生成的 ``RUN_ACCEPTED`` event id。
    :param occurred_at: canonical fact 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param idempotency_key: 幂等 key。
    :param execution_target: 已解析执行目标。
    :param queue_policy: Run queue policy。
    :param call_context_digest: 调用上下文 digest。
    """

    session_id: str
    run_id: str
    client_request_id: str
    input_event_id: str
    input_event_sequence: int
    run_accepted_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    idempotency_key: str
    execution_target: str
    queue_policy: str
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class CreateRunningRunInput:
    """创建 running Run、STARTING Attempt 与 pending dispatch 的输入。

    :param session_id: 所属 Session id。
    :param run_id: 调用方生成的 Run id。
    :param client_request_id: 客户端幂等请求 id。
    :param input_event_id: 已存在 ``USER_INPUT_ACCEPTED`` event id。
    :param input_event_sequence: 已存在 ``USER_INPUT_ACCEPTED`` event sequence。
    :param run_accepted_event_id: 调用方生成的 ``RUN_ACCEPTED`` event id。
    :param run_started_event_id: 调用方生成的 ``RUN_STARTED`` event id。
    :param attempt_started_event_id: 调用方生成的 ``ATTEMPT_STARTED`` event id。
    :param attempt_id: 调用方生成的 Attempt id。
    :param execution_id: 调用方生成的 execution id。
    :param dispatch_record_id: 调用方生成的 dispatch record id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param idempotency_key: 幂等 key。
    :param execution_target: 已解析执行目标。
    :param queue_policy: Run queue policy。
    :param start_reason: Run start reason。
    :param worker_kind: worker 类型。
    :param owner_host_instance_id: owner Host instance id；Phase 3 可为 ``None``。
    :param call_context_digest: 调用上下文 digest。
    """

    session_id: str
    run_id: str
    client_request_id: str
    input_event_id: str
    input_event_sequence: int
    run_accepted_event_id: str
    run_started_event_id: str
    attempt_started_event_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    occurred_at: datetime
    actor: str
    source: str
    idempotency_key: str
    execution_target: str
    queue_policy: str
    start_reason: RunStartReason
    worker_kind: WorkerKind
    owner_host_instance_id: str | None
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class StartGovernedRunInput:
    """pre-start governance 通过后启动 accepted 或 queued Run 的输入。

    :param run_id: 目标 Run id。
    :param expected_status: 期望源状态，只允许 accepted 或 queued。
    :param run_started_event_id: 调用方生成的 ``RUN_STARTED`` event id。
    :param attempt_started_event_id: 调用方生成的 ``ATTEMPT_STARTED`` event id。
    :param attempt_id: 调用方生成的 Attempt id。
    :param execution_id: 调用方生成的 execution id。
    :param dispatch_record_id: 调用方生成的 dispatch record id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param start_reason: Run start reason。
    :param worker_kind: worker 类型。
    :param owner_host_instance_id: owner Host instance id；Phase 10 可为 ``None``。
    """

    run_id: str
    expected_status: RunStatus
    run_started_event_id: str
    attempt_started_event_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    occurred_at: datetime
    actor: str
    source: str
    start_reason: RunStartReason
    worker_kind: WorkerKind
    owner_host_instance_id: str | None


@dataclass(frozen=True, slots=True)
class FailUnstartedRunInput:
    """pre-start governance 失败后收口未创建 Attempt 的 Run。

    :param run_id: 目标 Run id。
    :param expected_status: 期望源状态，只允许 accepted 或 queued。
    :param run_failed_event_id: 调用方生成的 ``RUN_FAILED`` event id。
    :param occurred_at: canonical fact 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: 失败原因。
    :param error_code: 错误码。
    :param message: 失败消息。
    """

    run_id: str
    expected_status: RunStatus
    run_failed_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    error_code: str
    message: str


@dataclass(frozen=True, slots=True)
class PromoteQueuedRunInput:
    """promotion 最早 queued Run 的输入。

    :param session_id: 目标 Session id。
    :param run_started_event_id: 调用方生成的 ``RUN_STARTED`` event id。
    :param attempt_started_event_id: 调用方生成的 ``ATTEMPT_STARTED`` event id。
    :param attempt_id: 调用方生成的 Attempt id。
    :param execution_id: 调用方生成的 execution id。
    :param dispatch_record_id: 调用方生成的 dispatch record id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param worker_kind: worker 类型。
    :param owner_host_instance_id: owner Host instance id；Phase 3 可为 ``None``。
    """

    session_id: str
    run_started_event_id: str
    attempt_started_event_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    occurred_at: datetime
    actor: str
    source: str
    worker_kind: WorkerKind
    owner_host_instance_id: str | None


@dataclass(frozen=True, slots=True)
class TerminalCloseoutInput:
    """terminal closeout helper 输入。

    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id。
    :param attempt_terminal_event_id: 调用方生成的具体 Attempt terminal event id。
    :param run_terminal_event_id: 调用方生成的具体 Run terminal event id。
    :param attempt_terminal_status: 具体 Attempt 终态。
    :param run_terminal_status: 具体 Run 终态。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: terminal reason。
    :param terminal_summary_ref: terminal summary 引用；无摘要时为 ``None``。
    :param terminal_summary_digest: terminal summary digest；无摘要时为 ``None``。
    :param engine_event_ref: 触发收口的 EngineEvent Host event id；无对应事件时为 ``None``。
    :param finish_reason: Engine finish reason；仅成功路径使用。
    :param filtered: final answer 是否经过过滤器处理；仅成功路径使用。
    :param degraded: final answer 是否为降级回答；仅成功路径使用。
    :param error_code: 失败错误码；仅失败路径使用。
    :param message: 失败消息；仅失败路径使用。
    :param provider_request_id: provider request id；无时为 ``None``。
    :param recoverable: 失败是否可恢复；仅失败路径使用。
    :param unsupported_later_owner: unsupported 路径后续 owner；无时为 ``None``。
    :param worker_lifecycle_signal: worker lifecycle signal；仅 lost 路径使用。
    :param stream_error_code: stream error code；仅 lost 路径使用。
    :param last_observed_worker_event_index: 最后观察到的 worker event index；仅 lost 路径使用。
    :param last_accepted_event_id: 最后已接受 EventLog id；无时为 ``None``。
    """

    run_id: str
    attempt_id: str
    attempt_terminal_event_id: str
    run_terminal_event_id: str
    attempt_terminal_status: AttemptStatus
    run_terminal_status: RunStatus
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    terminal_summary_ref: str | None
    terminal_summary_digest: str | None
    engine_event_ref: str | None = None
    finish_reason: str | None = None
    filtered: bool | None = None
    degraded: bool | None = None
    error_code: str | None = None
    message: str | None = None
    provider_request_id: str | None = None
    recoverable: bool | None = None
    unsupported_later_owner: str | None = None
    worker_lifecycle_signal: str | None = None
    stream_error_code: str | None = None
    last_observed_worker_event_index: int | None = None
    last_accepted_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class ContextRecoveryCloseInput:
    """reactive context compact 前关闭旧 Attempt 并进入 recovering。

    :param run_id: 目标 Run id。
    :param attempt_id: 当前 Attempt id。
    :param attempt_failed_event_id: 调用方生成的 ``ATTEMPT_FAILED`` id。
    :param run_recovering_event_id: 调用方生成的 ``RUN_RECOVERING`` id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: recovery 原因。
    :param engine_event_ref: 触发 recovery 的 Engine event ref。
    :param provider_request_id: provider request id；无则为 ``None``。
    :param message: 诊断消息。
    """

    run_id: str
    attempt_id: str
    attempt_failed_event_id: str
    run_recovering_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    engine_event_ref: str
    provider_request_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class StartupOrphanCloseInput:
    """startup positive orphan proof 后关闭旧 Attempt 的输入。

    :param run_id: 目标 Run id。
    :param expected_run_status: CAS 期望 Run 状态，只允许 running 或 cancelling。
    :param attempt_id: 目标 Attempt id。
    :param expected_attempt_status: CAS 期望 Attempt 状态，只允许 starting 或 running。
    :param execution_id: 目标 execution id。
    :param dispatch_record_id: 目标 dispatch record id。
    :param expected_dispatch_status: CAS 期望 dispatch record 状态。
    :param owner_host_instance_id: positive proof 指向的 owner Host instance id。
    :param owner_heartbeat_at: classifier 使用的 owner heartbeat timestamp。
    :param stale_after: classifier 使用的 stale 阈值。
    :param recoverable: ``True`` 时写 ``RUN_RECOVERING``，否则写 ``RUN_LOST``。
    :param attempt_lost_event_id: 调用方生成的 ``ATTEMPT_LOST`` event id。
    :param run_close_event_id: 调用方生成的 ``RUN_RECOVERING`` 或 ``RUN_LOST`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: 结构化 closeout 原因。
    :param orphan_proof_reason: positive orphan proof 原因。
    :param observed_process_start_token: 探测到的进程启动指纹；不可用时为 ``None``。
    :param observed_boot_id: 探测到的 boot id；不可用时为 ``None``。
    """

    run_id: str
    expected_run_status: RunStatus
    attempt_id: str
    expected_attempt_status: AttemptStatus
    execution_id: str
    dispatch_record_id: str
    expected_dispatch_status: DispatchRecordStatus
    owner_host_instance_id: str
    owner_heartbeat_at: str
    stale_after: timedelta
    recoverable: bool
    attempt_lost_event_id: str
    run_close_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    orphan_proof_reason: str
    observed_process_start_token: str | None
    observed_boot_id: str | None


@dataclass(frozen=True, slots=True)
class StartupRecoveringLostInput:
    """startup scan 将 recovering Run 收口为 lost 的输入。

    :param run_id: 目标 Run id。
    :param source_attempt_id: 当前 source Attempt id。
    :param run_lost_event_id: 调用方生成的 ``RUN_LOST`` event id。
    :param occurred_at: canonical fact 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: 结构化 lost 原因。
    :param recovery_dispatch_count: 已提交 recovery dispatch 数量。
    :param recovery_dispatch_limit: startup 自动 recovery dispatch 上限。
    """

    run_id: str
    source_attempt_id: str
    run_lost_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    recovery_dispatch_count: int
    recovery_dispatch_limit: int


@dataclass(frozen=True, slots=True)
class StartRecoveryRunInput:
    """创建 recovery Attempt。

    :param run_id: 目标 Run id。
    :param source_attempt_id: 已关闭的旧 Attempt id。
    :param run_started_event_id: 调用方生成的 ``RUN_STARTED`` event id。
    :param attempt_started_event_id: 调用方生成的 ``ATTEMPT_STARTED`` event id。
    :param attempt_id: 新 recovery Attempt id。
    :param execution_id: 新 execution id。
    :param dispatch_record_id: 新 dispatch record id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param worker_kind: worker 类型。
    :param owner_host_instance_id: owner Host instance id；Phase 10 可为 ``None``。
    :param context_compacted_event_id: 已接受 compact event id；startup recovery
        未发生 compact 时为 ``None``。
    :param context_compacted_event_sequence: 已接受 compact event sequence；
        startup recovery 未发生 compact 时为 ``None``。
    """

    run_id: str
    source_attempt_id: str
    run_started_event_id: str
    attempt_started_event_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    occurred_at: datetime
    actor: str
    source: str
    worker_kind: WorkerKind
    owner_host_instance_id: str | None
    context_compacted_event_id: str | None
    context_compacted_event_sequence: int | None


@dataclass(frozen=True, slots=True)
class FailRecoveringRunInput:
    """reactive compact 失败后将 recovering Run 收口为 failed。

    :param run_id: 目标 Run id。
    :param source_attempt_id: 已关闭的旧 Attempt id。
    :param run_failed_event_id: 调用方生成的 ``RUN_FAILED`` event id。
    :param occurred_at: canonical fact 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: 失败原因。
    :param error_code: 错误码。
    :param message: 失败消息。
    :param context_compaction_failed_event_id: 对应 ``CONTEXT_COMPACTION_FAILED`` id。
    """

    run_id: str
    source_attempt_id: str
    run_failed_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    error_code: str
    message: str
    context_compaction_failed_event_id: str


@dataclass(frozen=True, slots=True)
class ResumeRunFromWaitingInput:
    """waiting Run 恢复为新 Attempt 的 transition 输入。

    :param wait_id: 被 resolve 的 wait record id。
    :param run_id: wait 所属 Run id。
    :param suspended_attempt_id: 产生等待并已 SUSPENDED 的 Attempt id。
    :param resume_attempt_id: 新建 resume Attempt id。
    :param resume_execution_id: 新建 execution id。
    :param resume_dispatch_record_id: 新建 dispatch record id。
    :param resume_requested_event_id: 调用方生成的 ``RESUME_REQUESTED`` id。
    :param tool_result_event_id: 调用方生成的 ``TOOL_RESULT_ACCEPTED`` id。
    :param run_started_event_id: 调用方生成的 resume ``RUN_STARTED`` id。
    :param attempt_started_event_id: 调用方生成的 ``ATTEMPT_STARTED`` id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param resolution_idempotency_key: resolve wait 幂等键。
    :param resolution_digest: resolve wait 语义 digest。
    :param resume_requested_payload: ``RESUME_REQUESTED`` payload。
    :param tool_result_payload: ``TOOL_RESULT_ACCEPTED`` payload。
    :param tool_result_payload_ref: EventLog payload descriptor 引用；无则为 ``None``。
    :param tool_result_payload_digest: EventLog payload digest；无则为 ``None``。
    :param worker_kind: resume Attempt 的 worker 类型。
    :param owner_host_instance_id: owner Host instance id；无则为 ``None``。
    """

    wait_id: str
    run_id: str
    suspended_attempt_id: str
    resume_attempt_id: str
    resume_execution_id: str
    resume_dispatch_record_id: str
    resume_requested_event_id: str
    tool_result_event_id: str
    run_started_event_id: str
    attempt_started_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    resolution_idempotency_key: str
    resolution_digest: str
    resume_requested_payload: JsonValue
    tool_result_payload: JsonValue
    tool_result_payload_ref: str | None
    tool_result_payload_digest: str | None
    worker_kind: WorkerKind
    owner_host_instance_id: str | None


@dataclass(frozen=True, slots=True)
class WaitingRunTerminalInput:
    """waiting Run 因等待结果失败或 lost 收口的 transition 输入。

    :param wait_id: 被 resolve 的 wait record id。
    :param run_id: wait 所属 Run id。
    :param suspended_attempt_id: 产生等待并已 SUSPENDED 的 Attempt id。
    :param tool_result_event_id: 调用方生成的 ``TOOL_RESULT_ACCEPTED`` id。
    :param run_terminal_event_id: 调用方生成的 ``RUN_FAILED`` 或 ``RUN_LOST`` id。
    :param run_terminal_status: 目标 Run 终态，只允许 failed 或 lost。
    :param wait_terminal_status: 目标 wait 终态，只允许 failed 或 lost。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: terminal reason。
    :param resolution_idempotency_key: resolve wait 幂等键。
    :param resolution_digest: resolve wait 语义 digest。
    :param tool_result_payload: ``TOOL_RESULT_ACCEPTED`` payload。
    :param tool_result_payload_ref: EventLog payload descriptor 引用；无则为 ``None``。
    :param tool_result_payload_digest: EventLog payload digest；无则为 ``None``。
    """

    wait_id: str
    run_id: str
    suspended_attempt_id: str
    tool_result_event_id: str
    run_terminal_event_id: str
    run_terminal_status: RunStatus
    wait_terminal_status: WaitRecordStatus
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    resolution_idempotency_key: str
    resolution_digest: str
    tool_result_payload: JsonValue
    tool_result_payload_ref: str | None
    tool_result_payload_digest: str | None


@dataclass(frozen=True, slots=True)
class AcceptWorkerRunningInput:
    """WorkerProxy accepted 后推进 Attempt RUNNING 的输入。

    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id。
    :param attempt_running_event_id: 调用方生成的 ``ATTEMPT_RUNNING`` event id。
    :param occurred_at: canonical fact 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param worker_accept_reason: worker accept 诊断原因。
    :param local_worker_id: 本地 worker id；测试或非本地 worker 路径可为 ``None``。
    """

    run_id: str
    attempt_id: str
    attempt_running_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    worker_accept_reason: str
    local_worker_id: str | None = None


@dataclass(frozen=True, slots=True)
class CancelQueuedRunInput:
    """取消 queued Run 的输入。

    :param run_id: 目标 Run id。
    :param cancel_request_event_id: 调用方生成的 ``CANCEL_REQUESTED`` event id。
    :param run_cancelled_event_id: 调用方生成的 ``RUN_CANCELLED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param client_request_id: 客户端幂等请求 id。
    :param idempotency_key: 幂等 key。
    :param reason: cancel reason。
    :param mode: cancel mode。
    :param call_context_digest: 调用上下文 digest。
    """

    run_id: str
    cancel_request_event_id: str
    run_cancelled_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    client_request_id: str
    idempotency_key: str
    reason: str
    mode: CancelMode
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class CancelPredispatchStartingInput:
    """取消 pre-dispatch STARTING Attempt 的输入。

    :param run_id: 目标 Run id。
    :param cancel_request_event_id: 调用方生成的 ``CANCEL_REQUESTED`` event id。
    :param attempt_cancelled_event_id: 调用方生成的 ``ATTEMPT_CANCELLED`` event id。
    :param run_cancelled_event_id: 调用方生成的 ``RUN_CANCELLED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param client_request_id: 客户端幂等请求 id。
    :param idempotency_key: 幂等 key。
    :param reason: cancel reason。
    :param mode: cancel mode。
    :param call_context_digest: 调用上下文 digest。
    """

    run_id: str
    cancel_request_event_id: str
    attempt_cancelled_event_id: str
    run_cancelled_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    client_request_id: str
    idempotency_key: str
    reason: str
    mode: CancelMode
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class CancelActiveAttemptInput:
    """请求取消 active RUNNING Attempt 的输入。

    :param run_id: 目标 Run id。
    :param cancel_request_event_id: 调用方生成的 ``CANCEL_REQUESTED`` event id。
    :param run_cancelling_event_id: 调用方生成的 ``RUN_CANCELLING`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param client_request_id: 客户端幂等请求 id。
    :param idempotency_key: 幂等 key。
    :param reason: cancel reason。
    :param mode: cancel mode。
    :param call_context_digest: 调用上下文 digest。
    """

    run_id: str
    cancel_request_event_id: str
    run_cancelling_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    client_request_id: str
    idempotency_key: str
    reason: str
    mode: CancelMode
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class CancelWaitingRunInput:
    """取消 waiting Run 的输入。

    :param run_id: 目标 Run id。
    :param cancel_request_event_id: 调用方生成的 ``CANCEL_REQUESTED`` event id。
    :param run_cancelled_event_id: 调用方生成的 ``RUN_CANCELLED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param client_request_id: 客户端幂等请求 id。
    :param idempotency_key: 幂等 key。
    :param reason: cancel reason。
    :param mode: cancel mode。
    :param call_context_digest: 调用上下文 digest。
    """

    run_id: str
    cancel_request_event_id: str
    run_cancelled_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    client_request_id: str
    idempotency_key: str
    reason: str
    mode: CancelMode
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class CancelRecoveringRunInput:
    """取消 RECOVERING Run 的输入。

    RECOVERING 表示旧 Attempt 已由 recovery 收口，新的 recovery dispatch
    尚未提交。取消该状态只提交用户取消意图和 Run terminal fact，不修改旧
    Attempt 或 dispatch record。

    :param run_id: 目标 Run id。
    :param cancel_request_event_id: 调用方生成的 ``CANCEL_REQUESTED`` event id。
    :param run_cancelled_event_id: 调用方生成的 ``RUN_CANCELLED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param client_request_id: 客户端幂等请求 id。
    :param idempotency_key: 幂等 key。
    :param reason: cancel reason。
    :param mode: cancel mode。
    :param call_context_digest: 调用上下文 digest。
    """

    run_id: str
    cancel_request_event_id: str
    run_cancelled_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    client_request_id: str
    idempotency_key: str
    reason: str
    mode: CancelMode
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class ActiveCancelCloseoutInput:
    """active worker 取消完成后的 terminal closeout 输入。

    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id。
    :param attempt_cancelled_event_id: 调用方生成的 ``ATTEMPT_CANCELLED`` event id。
    :param run_cancelled_event_id: 调用方生成的 ``RUN_CANCELLED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: 取消原因。
    :param cancel_request_event_id: 对应 ``CANCEL_REQUESTED`` event id。
    :param engine_event_ref: 触发收口的 EngineEvent Host event id。
    :param requested_at: Host/Engine 观察到的取消请求时间文本。
    :param accepted_at: Engine 接受取消时间文本。
    :param finished_at: Engine 完成取消时间文本。
    """

    run_id: str
    attempt_id: str
    attempt_cancelled_event_id: str
    run_cancelled_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    cancel_request_event_id: str
    engine_event_ref: str
    requested_at: str
    accepted_at: str
    finished_at: str


@dataclass(frozen=True, slots=True)
class RunTransitionResult:
    """Run transition helper 结果。

    :param status: transition 结果分类。
    :param run: 最新 Run row。
    :param attempt: 最新 Attempt row；无 Attempt 时为 ``None``。
    :param dispatch_record: 最新 dispatch record row；无 dispatch 时为 ``None``。
    """

    status: StateMutationStatus
    run: RunRow | None
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """queued Run promotion 结果。

    :param status: mutation 结果分类。
    :param promoted_run: 成功 promotion 的 Run row。
    :param attempt: 新建 Attempt row。
    :param dispatch_record: 新建 dispatch record row。
    :param skip_reason: 未 promotion 时的跳过原因。
    """

    status: StateMutationStatus
    promoted_run: RunRow | None
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None
    skip_reason: str | None


@dataclass(frozen=True, slots=True)
class WaitResolutionTransitionResult:
    """wait resolution transition helper 结果。

    :param status: transition 结果分类。
    :param run: 最新 Run row。
    :param attempt: resume Attempt；未创建时为 ``None``。
    :param dispatch_record: resume dispatch record；未创建时为 ``None``。
    :param wait_record: 最新 wait record row。
    :param resume_requested_event: ``RESUME_REQUESTED`` row；未创建时为 ``None``。
    :param tool_result_event: ``TOOL_RESULT_ACCEPTED`` row；未创建时为 ``None``。
    :param run_event: ``RUN_STARTED`` / ``RUN_FAILED`` / ``RUN_LOST`` row。
    :param attempt_started_event: ``ATTEMPT_STARTED`` row；未创建时为 ``None``。
    """

    status: StateMutationStatus
    run: RunRow | None
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None
    wait_record: WaitRecordRow | None
    resume_requested_event: EventLogRow | None
    tool_result_event: EventLogRow | None
    run_event: EventLogRow | None
    attempt_started_event: EventLogRow | None


def create_accepted_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CreateAcceptedRunInput,
) -> RunTransitionResult:
    """创建 pre-start accepted Run，不创建 Attempt 或 dispatch record。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: 创建 accepted Run 输入。
    :returns: transition 结果，成功时 ``status`` 为 ``updated``。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_create_accepted_input(request)
    accepted_event = event_log_store.append_event(
        transaction, _run_accepted_event_request(request)
    ).row
    created_at = format_utc_timestamp(request.occurred_at)
    run = RunRow(
        run_id=request.run_id,
        session_id=request.session_id,
        status=RunStatus.ACCEPTED,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        accepted_event_id=accepted_event.event_id,
        accepted_event_sequence=accepted_event.event_sequence,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=None,
        started_event_sequence=None,
        terminal_event_id=None,
        terminal_event_sequence=None,
        current_attempt_id=None,
        source_run_id=None,
        source_run_relation=None,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )
    insert_run(transaction, run)
    return RunTransitionResult(
        status=StateMutationStatus.UPDATED,
        run=read_run_by_id(transaction, request.run_id),
        attempt=None,
        dispatch_record=None,
    )


def create_queued_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CreateQueuedRunInput,
) -> RunTransitionResult:
    """创建 accepted queued Run。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: 创建 queued Run 输入。
    :returns: transition 结果，成功时 ``status`` 为 ``updated``。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_create_queued_input(request)
    accepted_event = event_log_store.append_event(
        transaction, _run_accepted_event_request(request)
    ).row
    queued_event = event_log_store.append_event(
        transaction,
        _run_queued_event_request(
            request=request,
            accepted_event_id=accepted_event.event_id,
            accepted_event_sequence=accepted_event.event_sequence,
        ),
    ).row
    created_at = format_utc_timestamp(request.occurred_at)
    run = RunRow(
        run_id=request.run_id,
        session_id=request.session_id,
        status=RunStatus.QUEUED,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        accepted_event_id=accepted_event.event_id,
        accepted_event_sequence=accepted_event.event_sequence,
        queued_event_id=queued_event.event_id,
        queued_event_sequence=queued_event.event_sequence,
        started_event_id=None,
        started_event_sequence=None,
        terminal_event_id=None,
        terminal_event_sequence=None,
        current_attempt_id=None,
        source_run_id=None,
        source_run_relation=None,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )
    insert_run(transaction, run)
    return RunTransitionResult(
        status=StateMutationStatus.UPDATED,
        run=read_run_by_id(transaction, request.run_id),
        attempt=None,
        dispatch_record=None,
    )


def create_running_run_with_starting_attempt_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CreateRunningRunInput,
) -> RunTransitionResult:
    """创建 running Run、STARTING Attempt 与 pending dispatch record。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: 创建 running Run 输入。
    :returns: transition 结果，成功时 ``status`` 为 ``updated``。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_create_running_input(request)
    accepted_event = event_log_store.append_event(
        transaction, _run_accepted_event_request(request)
    ).row
    started_event = event_log_store.append_event(
        transaction,
        _run_started_event_request(
            request=request,
            accepted_event_id=accepted_event.event_id,
            accepted_event_sequence=accepted_event.event_sequence,
        ),
    ).row
    attempt_started_event = event_log_store.append_event(
        transaction, _attempt_started_event_request(request)
    ).row
    created_at = format_utc_timestamp(request.occurred_at)
    run = RunRow(
        run_id=request.run_id,
        session_id=request.session_id,
        status=RunStatus.RUNNING,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        accepted_event_id=accepted_event.event_id,
        accepted_event_sequence=accepted_event.event_sequence,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=started_event.event_id,
        started_event_sequence=started_event.event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        current_attempt_id=request.attempt_id,
        source_run_id=None,
        source_run_relation=None,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )
    attempt = _starting_attempt_row(
        request=request,
        started_event_id=attempt_started_event.event_id,
        started_event_sequence=attempt_started_event.event_sequence,
        created_at=created_at,
    )
    dispatch_record = _pending_dispatch_record_row(
        request=request,
        created_event_id=attempt_started_event.event_id,
        created_event_sequence=attempt_started_event.event_sequence,
        created_at=created_at,
    )
    insert_run(transaction, run)
    insert_attempt(transaction, attempt)
    insert_dispatch_record(transaction, dispatch_record)
    return RunTransitionResult(
        status=StateMutationStatus.UPDATED,
        run=read_run_by_id(transaction, request.run_id),
        attempt=read_attempt_by_id(transaction, request.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.attempt_id
        ),
    )


def start_governed_run_with_starting_attempt_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: StartGovernedRunInput,
) -> RunTransitionResult:
    """将 accepted/queued Run 启动为 running 并创建 STARTING Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: governance 通过后的启动输入。
    :returns: transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_start_governed_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status != request.expected_status or run.current_attempt_id is not None:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    started_event = event_log_store.append_event(
        transaction, _governed_run_started_event_request(request, run)
    ).row
    updated_at = format_utc_timestamp(request.occurred_at)
    started = start_unstarted_run_row(
        transaction,
        session_id=run.session_id,
        run_id=run.run_id,
        expected_status=request.expected_status,
        started_event_id=started_event.event_id,
        started_event_sequence=started_event.event_sequence,
        current_attempt_id=request.attempt_id,
        updated_at=updated_at,
    )
    started = _require_run_mutation_updated(
        started, mutation_name="start governed Run"
    )
    attempt_started_event = event_log_store.append_event(
        transaction, _governed_attempt_started_event_request(request, run)
    ).row
    attempt = _governed_attempt_row(
        request=request,
        run_id=run.run_id,
        started_event_id=attempt_started_event.event_id,
        started_event_sequence=attempt_started_event.event_sequence,
        created_at=updated_at,
    )
    dispatch_record = _governed_dispatch_record_row(
        request=request,
        run=run,
        created_event_id=attempt_started_event.event_id,
        created_event_sequence=attempt_started_event.event_sequence,
        created_at=updated_at,
    )
    insert_attempt(transaction, attempt)
    insert_dispatch_record(transaction, dispatch_record)
    return RunTransitionResult(
        status=started.status,
        run=read_run_by_id(transaction, run.run_id),
        attempt=read_attempt_by_id(transaction, request.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.attempt_id
        ),
    )


def fail_unstarted_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: FailUnstartedRunInput,
) -> RunTransitionResult:
    """将 accepted/queued Run attempt-free 收口为 failed。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: failure 输入。
    :returns: transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_fail_unstarted_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status != request.expected_status or run.current_attempt_id is not None:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    failed_event = event_log_store.append_event(
        transaction, _unstarted_run_failed_event_request(request, run)
    ).row
    run_result = terminal_unstarted_run_row(
        transaction,
        run_id=run.run_id,
        expected_status=request.expected_status,
        terminal_status=RunStatus.FAILED,
        terminal_event_id=failed_event.event_id,
        terminal_event_sequence=failed_event.event_sequence,
        terminal_at=format_utc_timestamp(request.occurred_at),
    )
    run_result = _require_run_mutation_updated(
        run_result, mutation_name="fail unstarted Run"
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=None,
        dispatch_record=None,
    )


def close_attempt_for_context_recovery_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: ContextRecoveryCloseInput,
) -> RunTransitionResult:
    """关闭当前 Attempt 并将 Run 标记为 recovering。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: recovery close 输入。
    :returns: transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_context_recovery_close_input(request)
    run = read_run_by_id(transaction, request.run_id)
    attempt = read_attempt_by_id(transaction, request.attempt_id)
    invalid = _invalid_terminal_precondition(run, attempt, request.attempt_id)
    if invalid is not None:
        return invalid
    if run is None or attempt is None:
        raise HostDurableError("context recovery precondition narrowing failed")
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, request.attempt_id
    )
    attempt_event = event_log_store.append_event(
        transaction,
        _context_recovery_attempt_failed_event_request(
            request=request,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        ),
    ).row
    recovering_event = event_log_store.append_event(
        transaction,
        _run_recovering_event_request(
            request=request,
            run=run,
            attempt=attempt,
            attempt_failed_event_id=attempt_event.event_id,
        ),
    ).row
    recovered_at = format_utc_timestamp(request.occurred_at)
    attempt_result = terminal_attempt_row(
        transaction,
        attempt_id=request.attempt_id,
        terminal_status=AttemptStatus.FAILED,
        terminal_event_id=attempt_event.event_id,
        terminal_event_sequence=attempt_event.event_sequence,
        terminal_at=recovered_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="context recovery close Attempt",
    )
    run_result = mark_running_run_recovering_row(
        transaction,
        session_id=run.session_id,
        run_id=run.run_id,
        current_attempt_id=attempt.attempt_id,
        recovering_event_id=recovering_event.event_id,
        recovering_event_sequence=recovering_event.event_sequence,
        updated_at=recovered_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="mark Run recovering",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=attempt_result.row,
        dispatch_record=dispatch_record,
    )


def close_startup_orphan_attempt_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: StartupOrphanCloseInput,
) -> RunTransitionResult:
    """根据 startup positive orphan proof 关闭旧 Attempt。

    本 helper 在同一 write transaction 内重新读取 Run、Attempt、dispatch
    record 与 owner liveness row，确认它们仍与 classifier 输入一致后，按顺序
    append ``ATTEMPT_LOST`` 与 ``RUN_RECOVERING`` / ``RUN_LOST``，再更新
    Attempt 与 Run state index。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: startup orphan closeout 输入。
    :returns: transition 结果；前置不满足时返回 ``not_found`` 或
        ``invalid_state``。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_startup_orphan_close_input(request)
    run = read_run_by_id(transaction, request.run_id)
    attempt = read_attempt_by_id(transaction, request.attempt_id)
    dispatch_record = read_dispatch_record_by_id(
        transaction, request.dispatch_record_id
    )
    invalid = _invalid_startup_orphan_precondition(
        transaction=transaction,
        request=request,
        run=run,
        attempt=attempt,
        dispatch_record=dispatch_record,
    )
    if invalid is not None:
        return invalid
    if run is None or attempt is None or dispatch_record is None:
        raise HostDurableError("startup orphan precondition narrowing failed")

    attempt_event = event_log_store.append_event(
        transaction,
        _startup_orphan_attempt_lost_event_request(
            request=request,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        ),
    ).row
    run_event = event_log_store.append_event(
        transaction,
        _startup_orphan_run_close_event_request(
            request=request,
            run=run,
            attempt=attempt,
            attempt_lost_event_id=attempt_event.event_id,
        ),
    ).row
    close_at = format_utc_timestamp(request.occurred_at)
    attempt_result = terminal_attempt_row(
        transaction,
        attempt_id=attempt.attempt_id,
        terminal_status=AttemptStatus.LOST,
        terminal_event_id=attempt_event.event_id,
        terminal_event_sequence=attempt_event.event_sequence,
        terminal_at=close_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="startup orphan close Attempt",
    )
    if request.recoverable:
        run_result = mark_running_run_recovering_row(
            transaction,
            session_id=run.session_id,
            run_id=run.run_id,
            current_attempt_id=attempt.attempt_id,
            recovering_event_id=run_event.event_id,
            recovering_event_sequence=run_event.event_sequence,
            updated_at=close_at,
        )
    else:
        run_result = terminal_orphaned_run_lost_row(
            transaction,
            run_id=run.run_id,
            current_attempt_id=attempt.attempt_id,
            expected_status=request.expected_run_status,
            terminal_event_id=run_event.event_id,
            terminal_event_sequence=run_event.event_sequence,
            terminal_at=close_at,
        )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="startup orphan close Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=attempt_result.row,
        dispatch_record=dispatch_record,
    )


def lose_recovering_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: StartupRecoveringLostInput,
) -> RunTransitionResult:
    """将 startup scan 中不可继续 dispatch 的 recovering Run 收口为 lost。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: recovering lost 输入。
    :returns: transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_startup_recovering_lost_input(request)
    run = read_run_by_id(transaction, request.run_id)
    source_attempt = read_attempt_by_id(transaction, request.source_attempt_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=source_attempt,
            dispatch_record=None,
        )
    if (
        source_attempt is None
        or run.status != RunStatus.RECOVERING
        or run.current_attempt_id != request.source_attempt_id
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=source_attempt,
            dispatch_record=None,
        )
    run_lost_event = event_log_store.append_event(
        transaction, _startup_recovering_run_lost_event_request(request, run)
    ).row
    lost_at = format_utc_timestamp(request.occurred_at)
    run_result = terminal_recovering_run_lost_row(
        transaction,
        run_id=run.run_id,
        current_attempt_id=request.source_attempt_id,
        terminal_event_id=run_lost_event.event_id,
        terminal_event_sequence=run_lost_event.event_sequence,
        terminal_at=lost_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="lose recovering Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=source_attempt,
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.source_attempt_id
        ),
    )


def start_recovery_run_with_starting_attempt_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: StartRecoveryRunInput,
) -> RunTransitionResult:
    """从 recovering Run 创建新的 recovery Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: recovery start 输入。
    :returns: transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_start_recovery_input(request)
    run = read_run_by_id(transaction, request.run_id)
    source_attempt = read_attempt_by_id(transaction, request.source_attempt_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if (
        source_attempt is None
        or run.status != RunStatus.RECOVERING
        or run.current_attempt_id != request.source_attempt_id
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=source_attempt,
            dispatch_record=None,
        )
    started_event = event_log_store.append_event(
        transaction, _recovery_run_started_event_request(request, run)
    ).row
    updated_at = format_utc_timestamp(request.occurred_at)
    run_result = start_recovering_run_row(
        transaction,
        session_id=run.session_id,
        run_id=run.run_id,
        source_attempt_id=request.source_attempt_id,
        recovered_attempt_id=request.attempt_id,
        started_event_id=started_event.event_id,
        started_event_sequence=started_event.event_sequence,
        updated_at=updated_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="start recovery Run",
    )
    attempt_started_event = event_log_store.append_event(
        transaction, _recovery_attempt_started_event_request(request, run)
    ).row
    attempt = _recovery_attempt_row(
        request=request,
        run_id=run.run_id,
        started_event_id=attempt_started_event.event_id,
        started_event_sequence=attempt_started_event.event_sequence,
        created_at=updated_at,
    )
    dispatch_record = _recovery_dispatch_record_row(
        request=request,
        run=run,
        created_event_id=attempt_started_event.event_id,
        created_event_sequence=attempt_started_event.event_sequence,
        created_at=updated_at,
    )
    insert_attempt(transaction, attempt)
    insert_dispatch_record(transaction, dispatch_record)
    return RunTransitionResult(
        status=run_result.status,
        run=read_run_by_id(transaction, run.run_id),
        attempt=read_attempt_by_id(transaction, request.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.attempt_id
        ),
    )


def fail_recovering_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: FailRecoveringRunInput,
) -> RunTransitionResult:
    """将 recovering Run 失败收口，不修改已失败旧 Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: recovery failure 输入。
    :returns: transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_fail_recovering_input(request)
    run = read_run_by_id(transaction, request.run_id)
    source_attempt = read_attempt_by_id(transaction, request.source_attempt_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if (
        source_attempt is None
        or run.status != RunStatus.RECOVERING
        or run.current_attempt_id != request.source_attempt_id
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=source_attempt,
            dispatch_record=None,
        )
    failed_event = event_log_store.append_event(
        transaction, _recovering_run_failed_event_request(request, run)
    ).row
    failed_at = format_utc_timestamp(request.occurred_at)
    run_result = terminal_recovering_run_row(
        transaction,
        run_id=run.run_id,
        current_attempt_id=request.source_attempt_id,
        terminal_event_id=failed_event.event_id,
        terminal_event_sequence=failed_event.event_sequence,
        terminal_at=failed_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="fail recovering Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=source_attempt,
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.source_attempt_id
        ),
    )


def promote_queued_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: PromoteQueuedRunInput,
) -> PromotionResult:
    """将最早 queued Run promotion 为 running 并创建 STARTING Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: promotion 输入。
    :returns: promotion 结果，未满足前置条件时返回 skip reason。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_promote_input(request)
    if read_active_run_for_session(transaction, request.session_id) is not None:
        return PromotionResult(
            status=StateMutationStatus.INVALID_STATE,
            promoted_run=None,
            attempt=None,
            dispatch_record=None,
            skip_reason=PromotionSkipReason.ACTIVE_RUN_EXISTS,
        )
    queued = read_earliest_queued_run(transaction, request.session_id)
    if queued is None:
        return PromotionResult(
            status=StateMutationStatus.NOT_FOUND,
            promoted_run=None,
            attempt=None,
            dispatch_record=None,
            skip_reason=PromotionSkipReason.NO_QUEUED_RUN,
        )

    started_event = event_log_store.append_event(
        transaction, _promotion_run_started_event_request(request, queued)
    ).row
    promoted = promote_queued_run_row(
        transaction,
        session_id=request.session_id,
        run_id=queued.run_id,
        started_event_id=started_event.event_id,
        started_event_sequence=started_event.event_sequence,
        current_attempt_id=request.attempt_id,
        updated_at=format_utc_timestamp(request.occurred_at),
    )
    promoted = _require_run_mutation_updated(
        promoted,
        mutation_name="promote queued Run",
    )

    attempt_started_event = event_log_store.append_event(
        transaction, _promotion_attempt_started_event_request(request, queued)
    ).row
    created_at = format_utc_timestamp(request.occurred_at)
    attempt = _promotion_attempt_row(
        request=request,
        run_id=queued.run_id,
        started_event_id=attempt_started_event.event_id,
        started_event_sequence=attempt_started_event.event_sequence,
        created_at=created_at,
    )
    dispatch_record = _promotion_dispatch_record_row(
        request=request,
        run_id=queued.run_id,
        execution_target=queued.execution_target,
        created_event_id=attempt_started_event.event_id,
        created_event_sequence=attempt_started_event.event_sequence,
        created_at=created_at,
    )
    insert_attempt(transaction, attempt)
    insert_dispatch_record(transaction, dispatch_record)
    return PromotionResult(
        status=StateMutationStatus.UPDATED,
        promoted_run=read_run_by_id(transaction, queued.run_id),
        attempt=read_attempt_by_id(transaction, request.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.attempt_id
        ),
        skip_reason=None,
    )


def resume_run_from_waiting_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: ResumeRunFromWaitingInput,
) -> WaitResolutionTransitionResult:
    """resolve wait 成功后把 waiting Run 原子恢复为新 STARTING Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: waiting resume 输入。
    :returns: wait resolution transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_resume_waiting_input(request)
    run = read_run_by_id(transaction, request.run_id)
    source_attempt = read_attempt_by_id(transaction, request.suspended_attempt_id)
    wait_record = read_wait_record_by_id(transaction, request.wait_id)
    invalid = _invalid_waiting_resolution_precondition(
        transaction=transaction,
        run=run,
        source_attempt=source_attempt,
        wait_record=wait_record,
        run_id=request.run_id,
        suspended_attempt_id=request.suspended_attempt_id,
    )
    if invalid is not None:
        return invalid
    if run is None or source_attempt is None or wait_record is None:
        raise HostDurableError("resume waiting precondition narrowing failed")

    resume_requested = event_log_store.append_event(
        transaction, _resume_requested_event_request(request, run)
    ).row
    tool_result = event_log_store.append_event(
        transaction, _waiting_tool_result_event_request(request, run)
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    wait_result = mark_wait_record_resolved_row(
        transaction,
        wait_id=request.wait_id,
        resolve_idempotency_key=request.resolution_idempotency_key,
        resolve_semantic_digest=request.resolution_digest,
        updated_event_id=tool_result.event_id,
        updated_event_sequence=tool_result.event_sequence,
        updated_at=terminal_at,
        terminal_at=terminal_at,
    )
    wait_result = _require_wait_record_mutation_updated(
        wait_result, mutation_name="resolve wait record"
    )
    run_started = event_log_store.append_event(
        transaction,
        _resume_run_started_event_request(
            request=request,
            run=run,
            resume_requested=resume_requested,
            tool_result=tool_result,
        ),
    ).row
    attempt_started = event_log_store.append_event(
        transaction, _resume_attempt_started_event_request(request, run)
    ).row
    attempt = _resume_attempt_row(
        request=request,
        started_event_id=attempt_started.event_id,
        started_event_sequence=attempt_started.event_sequence,
        created_at=terminal_at,
    )
    dispatch_record = _resume_dispatch_record_row(
        request=request,
        run=run,
        created_event_id=attempt_started.event_id,
        created_event_sequence=attempt_started.event_sequence,
        created_at=terminal_at,
    )
    insert_attempt(transaction, attempt)
    run_result = resume_waiting_run_row(
        transaction,
        session_id=run.session_id,
        run_id=run.run_id,
        suspended_attempt_id=source_attempt.attempt_id,
        resumed_attempt_id=request.resume_attempt_id,
        started_event_id=run_started.event_id,
        started_event_sequence=run_started.event_sequence,
        updated_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result, mutation_name="resume waiting Run"
    )
    insert_dispatch_record(transaction, dispatch_record)
    return WaitResolutionTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=read_attempt_by_id(transaction, request.resume_attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.resume_attempt_id
        ),
        wait_record=wait_result.row,
        resume_requested_event=resume_requested,
        tool_result_event=tool_result,
        run_event=run_started,
        attempt_started_event=attempt_started,
    )


def fail_run_from_waiting_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: WaitingRunTerminalInput,
) -> WaitResolutionTransitionResult:
    """resolve wait 失败后把 waiting Run 原子收口为 FAILED。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: waiting terminal 输入。
    :returns: wait resolution transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    return _terminal_run_from_waiting_in_transaction(
        transaction=transaction,
        event_log_store=event_log_store,
        request=request,
        expected_run_status=RunStatus.FAILED,
        expected_wait_status=WaitRecordStatus.FAILED,
    )


def mark_run_lost_from_waiting_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: WaitingRunTerminalInput,
) -> WaitResolutionTransitionResult:
    """resolve wait lost 后把 waiting Run 原子收口为 LOST。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: waiting terminal 输入。
    :returns: wait resolution transition 结果。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    return _terminal_run_from_waiting_in_transaction(
        transaction=transaction,
        event_log_store=event_log_store,
        request=request,
        expected_run_status=RunStatus.LOST,
        expected_wait_status=WaitRecordStatus.LOST,
    )


def _terminal_run_from_waiting_in_transaction(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: WaitingRunTerminalInput,
    expected_run_status: RunStatus,
    expected_wait_status: WaitRecordStatus,
) -> WaitResolutionTransitionResult:
    """按显式终态收口 waiting Run。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: waiting terminal 输入。
    :param expected_run_status: 调用路径允许的 Run 终态。
    :param expected_wait_status: 调用路径允许的 wait 终态。
    :returns: wait resolution transition 结果。
    """

    _validate_waiting_terminal_input(
        request,
        expected_run_status=expected_run_status,
        expected_wait_status=expected_wait_status,
    )
    run = read_run_by_id(transaction, request.run_id)
    source_attempt = read_attempt_by_id(transaction, request.suspended_attempt_id)
    wait_record = read_wait_record_by_id(transaction, request.wait_id)
    invalid = _invalid_waiting_resolution_precondition(
        transaction=transaction,
        run=run,
        source_attempt=source_attempt,
        wait_record=wait_record,
        run_id=request.run_id,
        suspended_attempt_id=request.suspended_attempt_id,
    )
    if invalid is not None:
        return invalid
    if run is None or source_attempt is None or wait_record is None:
        raise HostDurableError("terminal waiting precondition narrowing failed")

    tool_result = event_log_store.append_event(
        transaction, _waiting_tool_result_event_request(request, run)
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    if expected_wait_status is WaitRecordStatus.FAILED:
        wait_result = mark_wait_record_failed_row(
            transaction,
            wait_id=request.wait_id,
            resolve_idempotency_key=request.resolution_idempotency_key,
            resolve_semantic_digest=request.resolution_digest,
            updated_event_id=tool_result.event_id,
            updated_event_sequence=tool_result.event_sequence,
            updated_at=terminal_at,
            terminal_at=terminal_at,
        )
    elif expected_wait_status is WaitRecordStatus.LOST:
        wait_result = mark_wait_record_lost_row(
            transaction,
            wait_id=request.wait_id,
            resolve_idempotency_key=request.resolution_idempotency_key,
            resolve_semantic_digest=request.resolution_digest,
            updated_event_id=tool_result.event_id,
            updated_event_sequence=tool_result.event_sequence,
            updated_at=terminal_at,
            terminal_at=terminal_at,
        )
    else:
        raise HostDurableError("waiting terminal wait status is invalid")
    wait_result = _require_wait_record_mutation_updated(
        wait_result, mutation_name="terminal wait record"
    )
    run_terminal = event_log_store.append_event(
        transaction,
        _waiting_run_terminal_event_request(
            request=request, run=run, tool_result=tool_result
        ),
    ).row
    run_result = terminal_run_row(
        transaction,
        run_id=run.run_id,
        current_attempt_id=source_attempt.attempt_id,
        terminal_status=request.run_terminal_status,
        terminal_event_id=run_terminal.event_id,
        terminal_event_sequence=run_terminal.event_sequence,
        terminal_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result, mutation_name="terminal waiting Run"
    )
    return WaitResolutionTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=None,
        dispatch_record=None,
        wait_record=wait_result.row,
        resume_requested_event=None,
        tool_result_event=tool_result,
        run_event=run_terminal,
        attempt_started_event=None,
    )


def terminal_closeout_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: TerminalCloseoutInput,
) -> RunTransitionResult:
    """关闭 active Run 与当前 Attempt 到具体终态。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: terminal closeout 输入。
    :returns: transition 结果，前置状态不满足时返回 not_found/invalid_state/cas_lost。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_terminal_input(request)
    run = read_run_by_id(transaction, request.run_id)
    attempt = read_attempt_by_id(transaction, request.attempt_id)
    invalid = _invalid_terminal_precondition(run, attempt, request.attempt_id)
    if invalid is not None:
        return invalid
    if run is None or attempt is None:
        raise HostDurableError("terminal precondition narrowing failed")
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, request.attempt_id
    )

    attempt_event = event_log_store.append_event(
        transaction,
        _attempt_terminal_event_request(
            request=request,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        ),
    ).row
    run_event = event_log_store.append_event(
        transaction,
        _run_terminal_event_request(
            request=request,
            run=run,
            attempt=attempt,
            attempt_terminal_event_id=attempt_event.event_id,
            dispatch_record=dispatch_record,
        ),
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    attempt_result = _terminal_attempt_row_for_closeout(
        transaction=transaction,
        request=request,
        terminal_event_id=attempt_event.event_id,
        terminal_event_sequence=attempt_event.event_sequence,
        terminal_at=terminal_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="terminal Attempt",
    )
    run_result = _terminal_run_row_for_closeout(
        transaction=transaction,
        request=request,
        terminal_event_id=run_event.event_id,
        terminal_event_sequence=run_event.event_sequence,
        terminal_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="terminal Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=attempt_result.row,
        dispatch_record=dispatch_record,
    )


def _terminal_attempt_row_for_closeout(
    *,
    transaction: HostTransaction,
    request: TerminalCloseoutInput,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> AttemptMutationResult:
    """按 terminal closeout 输入推进 Attempt 终态。

    :param transaction: 调用方提供的 Host transaction。
    :param request: terminal closeout 输入。
    :param terminal_event_id: 具体 Attempt terminal event id。
    :param terminal_event_sequence: 具体 Attempt terminal event 全局序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Attempt mutation 结果。
    :raises HostDurableError: 输入字段或当前状态无效时抛出。
    """

    if request.attempt_terminal_status is AttemptStatus.CANCELLED:
        return cancel_running_attempt_row(
            transaction,
            attempt_id=request.attempt_id,
            terminal_event_id=terminal_event_id,
            terminal_event_sequence=terminal_event_sequence,
            terminal_at=terminal_at,
        )
    return terminal_attempt_row(
        transaction,
        attempt_id=request.attempt_id,
        terminal_status=request.attempt_terminal_status,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )


def _terminal_run_row_for_closeout(
    *,
    transaction: HostTransaction,
    request: TerminalCloseoutInput,
    terminal_event_id: str,
    terminal_event_sequence: int,
    terminal_at: str,
) -> RunMutationResult:
    """按 terminal closeout 输入推进 Run 终态。

    :param transaction: 调用方提供的 Host transaction。
    :param request: terminal closeout 输入。
    :param terminal_event_id: 具体 Run terminal event id。
    :param terminal_event_sequence: 具体 Run terminal event 全局序号。
    :param terminal_at: 固定 UTC terminal timestamp 文本。
    :returns: Run mutation 结果。
    :raises HostDurableError: 输入字段或当前状态无效时抛出。
    """

    if request.run_terminal_status is RunStatus.CANCELLED:
        return cancel_running_run_row(
            transaction,
            run_id=request.run_id,
            current_attempt_id=request.attempt_id,
            terminal_event_id=terminal_event_id,
            terminal_event_sequence=terminal_event_sequence,
            terminal_at=terminal_at,
        )
    return terminal_run_row(
        transaction,
        run_id=request.run_id,
        current_attempt_id=request.attempt_id,
        terminal_status=request.run_terminal_status,
        terminal_event_id=terminal_event_id,
        terminal_event_sequence=terminal_event_sequence,
        terminal_at=terminal_at,
    )


def active_cancel_closeout_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: ActiveCancelCloseoutInput,
) -> RunTransitionResult:
    """Engine 确认 active cancel 后关闭 Attempt / Run 到 cancelled。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: active cancel closeout 输入。
    :returns: transition 结果，前置状态不满足时返回 not_found/invalid_state/cas_lost。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_active_cancel_closeout_input(request)
    run = read_run_by_id(transaction, request.run_id)
    attempt = read_attempt_by_id(transaction, request.attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, request.attempt_id
    )
    invalid = _invalid_active_cancel_closeout_precondition(
        run=run,
        attempt=attempt,
        dispatch_record=dispatch_record,
        attempt_id=request.attempt_id,
    )
    if invalid is not None:
        return invalid
    if run is None or attempt is None or dispatch_record is None:
        raise HostDurableError("active cancel closeout narrowing failed")

    attempt_event = event_log_store.append_event(
        transaction,
        _active_attempt_cancelled_event_request(
            request=request,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        ),
    ).row
    run_event = event_log_store.append_event(
        transaction,
        _active_run_cancelled_event_request(
            request=request,
            run=run,
            attempt=attempt,
            attempt_cancelled_event_id=attempt_event.event_id,
            dispatch_record=dispatch_record,
        ),
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    attempt_result = cancel_running_attempt_row(
        transaction,
        attempt_id=attempt.attempt_id,
        terminal_event_id=attempt_event.event_id,
        terminal_event_sequence=attempt_event.event_sequence,
        terminal_at=terminal_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="cancel active Attempt",
    )
    run_result = cancel_cancelling_run_row(
        transaction,
        run_id=run.run_id,
        current_attempt_id=attempt.attempt_id,
        terminal_event_id=run_event.event_id,
        terminal_event_sequence=run_event.event_sequence,
        terminal_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="cancel active Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=attempt_result.row,
        dispatch_record=dispatch_record,
    )


def accept_worker_running_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: AcceptWorkerRunningInput,
) -> RunTransitionResult:
    """WorkerProxy accepted 后追加 ``ATTEMPT_RUNNING`` 并推进 Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: worker accepted 输入。
    :returns: transition 结果，前置状态不满足时返回 not_found/invalid_state。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_accept_worker_running_input(request)
    run = read_run_by_id(transaction, request.run_id)
    attempt = read_attempt_by_id(transaction, request.attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, request.attempt_id
    )
    invalid = _invalid_accept_worker_precondition(
        run=run,
        attempt=attempt,
        dispatch_record=dispatch_record,
        attempt_id=request.attempt_id,
    )
    if invalid is not None:
        return invalid
    if run is None or attempt is None or dispatch_record is None:
        raise HostDurableError("worker accept precondition narrowing failed")

    attempt_running_event = event_log_store.append_event(
        transaction,
        _attempt_running_event_request(
            request=request,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        ),
    ).row
    accepted_at = format_utc_timestamp(request.occurred_at)
    attempt_result = mark_attempt_running_row(
        transaction,
        attempt_id=attempt.attempt_id,
        updated_at=accepted_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="mark Attempt running",
    )
    dispatch_result = mark_dispatch_worker_accepted_row(
        transaction,
        attempt_id=attempt.attempt_id,
        worker_accept_event_id=attempt_running_event.event_id,
        worker_accept_event_sequence=attempt_running_event.event_sequence,
        worker_accepted_at=accepted_at,
    )
    dispatch_result = _require_dispatch_record_mutation_updated(
        dispatch_result,
        mutation_name="record dispatch worker accept refs",
    )
    return RunTransitionResult(
        status=attempt_result.status,
        run=read_run_by_id(transaction, run.run_id),
        attempt=attempt_result.row,
        dispatch_record=dispatch_result.row,
    )


def cancel_waiting_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CancelWaitingRunInput,
) -> RunTransitionResult:
    """取消 WAITING Run 并标记 active wait records 为 cancelled。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: waiting cancel 输入。
    :returns: transition 结果；前置状态不满足时返回 not_found/invalid_state。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_cancel_waiting_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status != RunStatus.WAITING or run.current_attempt_id is None:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    active_waits = read_active_wait_records_for_run(transaction, run.run_id)
    if attempt is None or attempt.status != AttemptStatus.SUSPENDED or not active_waits:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=_read_dispatch_for_attempt(transaction, attempt),
        )

    cancel_request_event = event_log_store.append_event(
        transaction, _cancel_requested_event_request(request, run)
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    wait_result = cancel_active_wait_records_for_run(
        transaction,
        run_id=run.run_id,
        updated_event_id=cancel_request_event.event_id,
        updated_event_sequence=cancel_request_event.event_sequence,
        updated_at=terminal_at,
        terminal_at=terminal_at,
    )
    if wait_result.status != StateMutationStatus.UPDATED:
        _raise_after_event_append_mutation_failure(
            mutation_name="cancel active wait records",
            status=wait_result.status,
        )
    run_cancelled_event = event_log_store.append_event(
        transaction,
        _waiting_run_cancelled_event_request(
            request=request,
            run=run,
            attempt=attempt,
            cancel_request_event_id=cancel_request_event.event_id,
            wait_ids=tuple(row.wait_id for row in wait_result.rows),
        ),
    ).row
    run_result = cancel_waiting_run_row(
        transaction,
        run_id=run.run_id,
        current_attempt_id=attempt.attempt_id,
        terminal_event_id=run_cancelled_event.event_id,
        terminal_event_sequence=run_cancelled_event.event_sequence,
        terminal_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="cancel waiting Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=attempt,
        dispatch_record=_read_dispatch_for_attempt(transaction, attempt),
    )


def cancel_recovering_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CancelRecoveringRunInput,
) -> RunTransitionResult:
    """取消 RECOVERING Run，不修改旧 Attempt 或 dispatch record。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: recovering cancel 输入。
    :returns: transition 结果；前置状态不满足时返回 not_found/invalid_state。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_cancel_recovering_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status != RunStatus.RECOVERING:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=_read_current_attempt_if_present(transaction, run),
            dispatch_record=_read_current_dispatch_record_if_present(
                transaction, run
            ),
        )

    cancel_request_event = event_log_store.append_event(
        transaction, _cancel_requested_event_request(request, run)
    ).row
    run_cancelled_event = event_log_store.append_event(
        transaction,
        _run_cancelled_event_request(
            request=request,
            run=run,
            cancel_request_event_id=cancel_request_event.event_id,
            terminal_attempt_id=None,
            terminal_attempt_event_id=None,
        ),
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    run_result = cancel_recovering_run_row(
        transaction,
        run_id=run.run_id,
        terminal_event_id=run_cancelled_event.event_id,
        terminal_event_sequence=run_cancelled_event.event_sequence,
        terminal_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="cancel recovering Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=_read_current_attempt_if_present(transaction, run),
        dispatch_record=_read_current_dispatch_record_if_present(transaction, run),
    )


def cancel_queued_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CancelQueuedRunInput,
) -> RunTransitionResult:
    """取消 queued Run，不创建 Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: cancel queued 输入。
    :returns: transition 结果，前置状态不满足时返回 not_found/invalid_state。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_cancel_queued_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status not in (RunStatus.ACCEPTED, RunStatus.QUEUED):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    cancel_request_event = event_log_store.append_event(
        transaction, _cancel_requested_event_request(request, run)
    ).row
    run_cancelled_event = event_log_store.append_event(
        transaction,
        _run_cancelled_event_request(
            request=request,
            run=run,
            cancel_request_event_id=cancel_request_event.event_id,
            terminal_attempt_id=None,
            terminal_attempt_event_id=None,
        ),
    ).row
    run_result = terminal_unstarted_run_row(
        transaction,
        run_id=request.run_id,
        expected_status=run.status,
        terminal_status=RunStatus.CANCELLED,
        terminal_event_id=run_cancelled_event.event_id,
        terminal_event_sequence=run_cancelled_event.event_sequence,
        terminal_at=format_utc_timestamp(request.occurred_at),
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="cancel queued Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=None,
        dispatch_record=None,
    )


def cancel_predispatch_starting_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CancelPredispatchStartingInput,
) -> RunTransitionResult:
    """取消 RUNNING + STARTING + pending dispatch 的 pre-dispatch Run。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: cancel pre-dispatch starting 输入。
    :returns: transition 结果，前置状态不满足时返回 not_found/invalid_state。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_cancel_predispatch_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status != RunStatus.RUNNING or run.current_attempt_id is None:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, run.current_attempt_id
    )
    if (
        attempt is None
        or attempt.status != AttemptStatus.STARTING
        or dispatch_record is None
        or not _dispatch_record_is_direct_cancelable(dispatch_record)
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )

    cancel_request_event = event_log_store.append_event(
        transaction, _cancel_requested_event_request(request, run)
    ).row
    attempt_cancelled_event = event_log_store.append_event(
        transaction,
        _attempt_cancelled_event_request(
            request=request,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
            cancel_request_event_id=cancel_request_event.event_id,
        ),
    ).row
    run_cancelled_event = event_log_store.append_event(
        transaction,
        _run_cancelled_event_request(
            request=request,
            run=run,
            cancel_request_event_id=cancel_request_event.event_id,
            terminal_attempt_id=attempt.attempt_id,
            terminal_attempt_event_id=attempt_cancelled_event.event_id,
        ),
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    dispatch_result = cancel_starting_dispatch_record_row(
        transaction,
        attempt_id=attempt.attempt_id,
        cancelled_event_id=attempt_cancelled_event.event_id,
        cancelled_event_sequence=attempt_cancelled_event.event_sequence,
        cancelled_at=terminal_at,
    )
    dispatch_result = _require_dispatch_record_mutation_updated(
        dispatch_result,
        mutation_name="cancel starting dispatch record",
    )
    attempt_result = cancel_starting_attempt_row(
        transaction,
        attempt_id=attempt.attempt_id,
        terminal_event_id=attempt_cancelled_event.event_id,
        terminal_event_sequence=attempt_cancelled_event.event_sequence,
        terminal_at=terminal_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="cancel starting Attempt",
    )
    run_result = cancel_running_run_row(
        transaction,
        run_id=run.run_id,
        current_attempt_id=attempt.attempt_id,
        terminal_event_id=run_cancelled_event.event_id,
        terminal_event_sequence=run_cancelled_event.event_sequence,
        terminal_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="cancel running Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=attempt_result.row,
        dispatch_record=dispatch_result.row,
    )


def request_active_attempt_cancel_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CancelActiveAttemptInput,
) -> RunTransitionResult:
    """请求取消 active RUNNING Attempt，并只首次写 ``RUN_CANCELLING``。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: active cancel 输入。
    :returns: transition 结果；已处于 cancelling 时返回当前状态且不追加事件。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_cancel_active_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status == RunStatus.CANCELLING and run.current_attempt_id is not None:
        attempt = read_attempt_by_id(transaction, run.current_attempt_id)
        return RunTransitionResult(
            status=StateMutationStatus.UPDATED,
            run=run,
            attempt=attempt,
            dispatch_record=_read_dispatch_for_attempt(transaction, attempt),
        )
    if run.status != RunStatus.RUNNING or run.current_attempt_id is None:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    if attempt is None or attempt.status != AttemptStatus.RUNNING:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=_read_dispatch_for_attempt(transaction, attempt),
        )

    cancel_request_event = event_log_store.append_event(
        transaction, _cancel_requested_event_request(request, run)
    ).row
    event_log_store.append_event(
        transaction,
        _run_cancelling_event_request(
            request=request,
            run=run,
            attempt=attempt,
            cancel_request_event_id=cancel_request_event.event_id,
        ),
    )
    run_result = mark_run_cancelling_row(
        transaction,
        run_id=run.run_id,
        current_attempt_id=attempt.attempt_id,
        updated_at=format_utc_timestamp(request.occurred_at),
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="mark Run cancelling",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=read_attempt_by_id(transaction, attempt.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, attempt.attempt_id
        ),
    )


def _require_run_mutation_updated(
    result: RunMutationResult, *, mutation_name: str
) -> RunMutationResult:
    """断言 Run mutation 已完成。

    :param result: 低层 Run mutation 结果。
    :param mutation_name: mutation 语义名称，用于错误信息。
    :returns: ``UPDATED`` 的原始 mutation 结果。
    :raises HostDurableError: mutation 不是 ``UPDATED`` 时抛出以触发事务回滚。
    """

    if result.status != StateMutationStatus.UPDATED:
        _raise_after_event_append_mutation_failure(
            mutation_name=mutation_name,
            status=result.status,
        )
    return result


def _require_attempt_mutation_updated(
    result: AttemptMutationResult, *, mutation_name: str
) -> AttemptMutationResult:
    """断言 Attempt mutation 已完成。

    :param result: 低层 Attempt mutation 结果。
    :param mutation_name: mutation 语义名称，用于错误信息。
    :returns: ``UPDATED`` 的原始 mutation 结果。
    :raises HostDurableError: mutation 不是 ``UPDATED`` 时抛出以触发事务回滚。
    """

    if result.status != StateMutationStatus.UPDATED:
        _raise_after_event_append_mutation_failure(
            mutation_name=mutation_name,
            status=result.status,
        )
    return result


def _require_wait_record_mutation_updated(
    result: WaitRecordMutationResult, *, mutation_name: str
) -> WaitRecordMutationResult:
    """断言 wait record mutation 已完成。

    :param result: 低层 wait record mutation 结果。
    :param mutation_name: mutation 语义名称，用于错误信息。
    :returns: ``UPDATED`` 的原始 mutation 结果。
    :raises HostDurableError: mutation 不是 ``UPDATED`` 时抛出以触发事务回滚。
    """

    if result.status != StateMutationStatus.UPDATED:
        _raise_after_event_append_mutation_failure(
            mutation_name=mutation_name,
            status=result.status,
        )
    return result


def _require_dispatch_record_mutation_updated(
    result: DispatchRecordMutationResult, *, mutation_name: str
) -> DispatchRecordMutationResult:
    """断言 dispatch record mutation 已完成。

    :param result: 低层 dispatch record mutation 结果。
    :param mutation_name: mutation 语义名称，用于错误信息。
    :returns: ``UPDATED`` 的原始 mutation 结果。
    :raises HostDurableError: mutation 不是 ``UPDATED`` 时抛出以触发事务回滚。
    """

    if result.status != StateMutationStatus.UPDATED:
        _raise_after_event_append_mutation_failure(
            mutation_name=mutation_name,
            status=result.status,
        )
    return result


def _raise_after_event_append_mutation_failure(
    *, mutation_name: str, status: StateMutationStatus
) -> None:
    """在 append canonical EventLog 后的 state mutation 失败时中止事务。

    :param mutation_name: mutation 语义名称，用于错误信息。
    :param status: 非 ``UPDATED`` mutation 状态。
    :returns: ``None``。
    :raises HostDurableError: 总是抛出以阻止调用方正常 commit 孤立 EventLog。
    """

    raise HostDurableError(
        f"{mutation_name} returned {status.value} after EventLog append"
    )


def _run_accepted_event_request(
    request: CreateAcceptedRunInput | CreateQueuedRunInput | CreateRunningRunInput,
) -> EventLogAppendRequest:
    """构造 ``RUN_ACCEPTED`` EventLog append request。

    :param request: 创建 Run 输入。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_accepted_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=request.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_ACCEPTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason=None,
        payload_json={
            "run_id": request.run_id,
            "client_request_id": request.client_request_id,
            "input_event_id": request.input_event_id,
            "input_event_sequence": request.input_event_sequence,
            "execution_target": request.execution_target,
            "queue_policy": request.queue_policy,
            "source_run_id": None,
            "source_run_relation": None,
            "call_context_digest": request.call_context_digest,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_queued_event_request(
    *,
    request: CreateQueuedRunInput,
    accepted_event_id: str,
    accepted_event_sequence: int,
) -> EventLogAppendRequest:
    """构造 ``RUN_QUEUED`` EventLog append request。

    :param request: 创建 queued Run 输入。
    :param accepted_event_id: RUN_ACCEPTED event id。
    :param accepted_event_sequence: RUN_ACCEPTED event sequence。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_queued_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=request.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_QUEUED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"queue_reason": request.queue_reason},
        payload_json={
            "run_id": request.run_id,
            "accepted_event_id": accepted_event_id,
            "accepted_event_sequence": accepted_event_sequence,
            "queue_reason": request.queue_reason,
            "active_run_id": request.active_run_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_started_event_request(
    *,
    request: CreateRunningRunInput,
    accepted_event_id: str,
    accepted_event_sequence: int,
) -> EventLogAppendRequest:
    """构造 direct start ``RUN_STARTED`` EventLog append request。

    :param request: 创建 running Run 输入。
    :param accepted_event_id: RUN_ACCEPTED event id。
    :param accepted_event_sequence: RUN_ACCEPTED event sequence。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=request.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"start_reason": request.start_reason.value},
        payload_json={
            "run_id": request.run_id,
            "start_reason": request.start_reason.value,
            "accepted_event_id": accepted_event_id,
            "accepted_event_sequence": accepted_event_sequence,
            "attempt_id": request.attempt_id,
            "dispatch_record_id": request.dispatch_record_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _attempt_started_event_request(
    request: CreateRunningRunInput,
) -> EventLogAppendRequest:
    """构造 direct start ``ATTEMPT_STARTED`` EventLog append request。

    :param request: 创建 running Run 输入。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=request.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason=None,
        payload_json={
            "attempt_id": request.attempt_id,
            "execution_id": request.execution_id,
            "dispatch_record_id": request.dispatch_record_id,
            "worker_kind": request.worker_kind.value,
            "execution_target": request.execution_target,
            "owner_host_instance_id": request.owner_host_instance_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _promotion_run_started_event_request(
    request: PromoteQueuedRunInput, queued: RunRow
) -> EventLogAppendRequest:
    """构造 promotion ``RUN_STARTED`` EventLog append request。

    :param request: promotion 输入。
    :param queued: 被 promotion 的 queued Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=queued.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"start_reason": RunStartReason.QUEUE_PROMOTION.value},
        payload_json={
            "run_id": queued.run_id,
            "start_reason": RunStartReason.QUEUE_PROMOTION.value,
            "accepted_event_id": queued.accepted_event_id,
            "accepted_event_sequence": queued.accepted_event_sequence,
            "attempt_id": request.attempt_id,
            "dispatch_record_id": request.dispatch_record_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _promotion_attempt_started_event_request(
    request: PromoteQueuedRunInput, queued: RunRow
) -> EventLogAppendRequest:
    """构造 promotion ``ATTEMPT_STARTED`` EventLog append request。

    :param request: promotion 输入。
    :param queued: 被 promotion 的 queued Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=queued.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={
            "attempt_id": request.attempt_id,
            "execution_id": request.execution_id,
            "dispatch_record_id": request.dispatch_record_id,
            "worker_kind": request.worker_kind.value,
            "execution_target": queued.execution_target,
            "owner_host_instance_id": request.owner_host_instance_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _governed_run_started_event_request(
    request: StartGovernedRunInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 governance start ``RUN_STARTED`` EventLog append request。

    :param request: governance start 输入。
    :param run: 被启动的 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"start_reason": request.start_reason.value},
        payload_json={
            "run_id": run.run_id,
            "start_reason": request.start_reason.value,
            "accepted_event_id": run.accepted_event_id,
            "accepted_event_sequence": run.accepted_event_sequence,
            "attempt_id": request.attempt_id,
            "dispatch_record_id": request.dispatch_record_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _governed_attempt_started_event_request(
    request: StartGovernedRunInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 governance start ``ATTEMPT_STARTED`` EventLog append request。

    :param request: governance start 输入。
    :param run: 被启动的 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={
            "attempt_id": request.attempt_id,
            "execution_id": request.execution_id,
            "dispatch_record_id": request.dispatch_record_id,
            "worker_kind": request.worker_kind.value,
            "execution_target": run.execution_target,
            "owner_host_instance_id": request.owner_host_instance_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _context_recovery_attempt_failed_event_request(
    *,
    request: ContextRecoveryCloseInput,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow | None,
) -> EventLogAppendRequest:
    """构造 reactive recovery 的 ``ATTEMPT_FAILED`` EventLog 请求。

    :param request: recovery close 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param dispatch_record: dispatch row；缺失时为 ``None``。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_failed_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_FAILED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "reason": request.reason,
            "terminal_summary_ref": None,
            "terminal_summary_digest": None,
            "engine_event_ref": request.engine_event_ref,
            "error_code": request.reason,
            "message": request.message,
            "provider_request_id": request.provider_request_id,
            "recoverable": True,
            "unsupported_later_owner": None,
            "worker_kind": None
            if dispatch_record is None
            else dispatch_record.worker_kind.value,
            "dispatch_record_id": None
            if dispatch_record is None
            else dispatch_record.dispatch_record_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_recovering_event_request(
    *,
    request: ContextRecoveryCloseInput,
    run: RunRow,
    attempt: AttemptRow,
    attempt_failed_event_id: str,
) -> EventLogAppendRequest:
    """构造 ``RUN_RECOVERING`` EventLog 请求。

    :param request: recovery close 输入。
    :param run: 目标 Run row。
    :param attempt: 被关闭的 Attempt row。
    :param attempt_failed_event_id: 对应 ``ATTEMPT_FAILED`` event id。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_recovering_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_RUN_RECOVERING,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "reason": request.reason,
            "attempt_failed_event_id": attempt_failed_event_id,
            "engine_event_ref": request.engine_event_ref,
            "provider_request_id": request.provider_request_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _recovery_run_started_event_request(
    request: StartRecoveryRunInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 recovery ``RUN_STARTED`` EventLog 请求。

    :param request: recovery start 输入。
    :param run: recovering Run row。
    :returns: EventLog append request。
    """

    payload: dict[str, JsonValue] = {
        "run_id": run.run_id,
        "start_reason": RunStartReason.RECOVERY.value,
        "source_attempt_id": request.source_attempt_id,
        "attempt_id": request.attempt_id,
        "dispatch_record_id": request.dispatch_record_id,
    }
    if request.context_compacted_event_id is not None:
        payload["context_compacted_event_id"] = request.context_compacted_event_id
    if request.context_compacted_event_sequence is not None:
        payload["context_compacted_event_sequence"] = (
            request.context_compacted_event_sequence
        )
    return EventLogAppendRequest(
        event_id=request.run_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"start_reason": RunStartReason.RECOVERY.value},
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _startup_orphan_attempt_lost_event_request(
    *,
    request: StartupOrphanCloseInput,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow,
) -> EventLogAppendRequest:
    """构造 startup orphan ``ATTEMPT_LOST`` EventLog 请求。

    :param request: startup orphan closeout 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param dispatch_record: 目标 dispatch record row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_lost_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_LOST,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason, "orphan_proof": request.orphan_proof_reason},
        payload_json={
            "run_id": run.run_id,
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "dispatch_record_id": dispatch_record.dispatch_record_id,
            "owner_host_instance_id": request.owner_host_instance_id,
            "owner_heartbeat_at": request.owner_heartbeat_at,
            "orphan_proof_reason": request.orphan_proof_reason,
            "observed_process_start_token": request.observed_process_start_token,
            "observed_boot_id": request.observed_boot_id,
            "reason": request.reason,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _startup_orphan_run_close_event_request(
    *,
    request: StartupOrphanCloseInput,
    run: RunRow,
    attempt: AttemptRow,
    attempt_lost_event_id: str,
) -> EventLogAppendRequest:
    """构造 startup orphan Run close EventLog 请求。

    :param request: startup orphan closeout 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param attempt_lost_event_id: 已写入的 ``ATTEMPT_LOST`` event id。
    :returns: EventLog append request。
    """

    event_type = (
        _EVENT_TYPE_RUN_RECOVERING if request.recoverable else _EVENT_TYPE_RUN_LOST
    )
    return EventLogAppendRequest(
        event_id=request.run_close_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason, "orphan_proof": request.orphan_proof_reason},
        payload_json={
            "run_id": run.run_id,
            "attempt_id": attempt.attempt_id,
            "attempt_lost_event_id": attempt_lost_event_id,
            "recoverable": request.recoverable,
            "reason": request.reason,
            "orphan_proof_reason": request.orphan_proof_reason,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _startup_recovering_run_lost_event_request(
    request: StartupRecoveringLostInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 startup recovering ``RUN_LOST`` EventLog 请求。

    :param request: recovering lost 输入。
    :param run: 目标 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_lost_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_LOST,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "source_attempt_id": request.source_attempt_id,
            "reason": request.reason,
            "recovery_dispatch_count": request.recovery_dispatch_count,
            "recovery_dispatch_limit": request.recovery_dispatch_limit,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _recovery_attempt_started_event_request(
    request: StartRecoveryRunInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 recovery ``ATTEMPT_STARTED`` EventLog 请求。

    :param request: recovery start 输入。
    :param run: recovering Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={
            "attempt_id": request.attempt_id,
            "execution_id": request.execution_id,
            "dispatch_record_id": request.dispatch_record_id,
            "worker_kind": request.worker_kind.value,
            "execution_target": run.execution_target,
            "owner_host_instance_id": request.owner_host_instance_id,
            "source_attempt_id": request.source_attempt_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _recovering_run_failed_event_request(
    request: FailRecoveringRunInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 recovering ``RUN_FAILED`` EventLog 请求。

    :param request: recovery failure 输入。
    :param run: recovering Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_failed_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.source_attempt_id,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_FAILED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "attempt_id": request.source_attempt_id,
            "reason": request.reason,
            "error_code": request.error_code,
            "message": request.message,
            "context_compaction_failed_event_id": (
                request.context_compaction_failed_event_id
            ),
        },
        payload_ref=None,
        payload_digest=None,
    )


def _unstarted_run_failed_event_request(
    request: FailUnstartedRunInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 attempt-free ``RUN_FAILED`` EventLog append request。

    :param request: failure 输入。
    :param run: 被收口的 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_failed_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_FAILED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "attempt_id": None,
            "reason": request.reason,
            "error_code": request.error_code,
            "message": request.message,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _resume_requested_event_request(
    request: ResumeRunFromWaitingInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 ``RESUME_REQUESTED`` EventLog append request。

    :param request: resume waiting 输入。
    :param run: 目标 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.resume_requested_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.suspended_attempt_id,
        execution_id=None,
        event_type=_EVENT_TYPE_RESUME_REQUESTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=request.resolution_idempotency_key,
        policy_decision=None,
        reason={"reason": "wait_resolved"},
        payload_json=request.resume_requested_payload,
        payload_ref=None,
        payload_digest=None,
    )


def _waiting_tool_result_event_request(
    request: ResumeRunFromWaitingInput | WaitingRunTerminalInput,
    run: RunRow,
) -> EventLogAppendRequest:
    """构造 wait resolution ``TOOL_RESULT_ACCEPTED`` EventLog append request。

    :param request: resume 或 terminal waiting 输入。
    :param run: 目标 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.tool_result_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.suspended_attempt_id,
        execution_id=None,
        event_type=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=request.resolution_idempotency_key,
        policy_decision=None,
        reason={"reason": "wait_resolution"},
        payload_json=request.tool_result_payload,
        payload_ref=request.tool_result_payload_ref,
        payload_digest=request.tool_result_payload_digest,
    )


def _resume_run_started_event_request(
    *,
    request: ResumeRunFromWaitingInput,
    run: RunRow,
    resume_requested: EventLogRow,
    tool_result: EventLogRow,
) -> EventLogAppendRequest:
    """构造 resume ``RUN_STARTED`` EventLog append request。

    :param request: resume waiting 输入。
    :param run: 目标 Run row。
    :param resume_requested: 已追加的 ``RESUME_REQUESTED`` row。
    :param tool_result: 已追加的 ``TOOL_RESULT_ACCEPTED`` row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=run.client_request_id,
        idempotency_key=request.resolution_idempotency_key,
        policy_decision=None,
        reason={"start_reason": RunStartReason.RESUME.value},
        payload_json={
            "run_id": run.run_id,
            "start_reason": RunStartReason.RESUME.value,
            "accepted_event_id": run.accepted_event_id,
            "accepted_event_sequence": run.accepted_event_sequence,
            "attempt_id": request.resume_attempt_id,
            "dispatch_record_id": request.resume_dispatch_record_id,
            "wait_id": request.wait_id,
            "source_attempt_id": request.suspended_attempt_id,
            "resume_requested_event_ref": _event_ref_json_from_row(
                resume_requested
            ),
            "tool_result_event_ref": _event_ref_json_from_row(tool_result),
        },
        payload_ref=None,
        payload_digest=None,
    )


def _resume_attempt_started_event_request(
    request: ResumeRunFromWaitingInput, run: RunRow
) -> EventLogAppendRequest:
    """构造 resume ``ATTEMPT_STARTED`` EventLog append request。

    :param request: resume waiting 输入。
    :param run: 目标 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.resume_attempt_id,
        execution_id=request.resume_execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=request.resolution_idempotency_key,
        policy_decision=None,
        reason=None,
        payload_json={
            "attempt_id": request.resume_attempt_id,
            "execution_id": request.resume_execution_id,
            "dispatch_record_id": request.resume_dispatch_record_id,
            "worker_kind": request.worker_kind.value,
            "execution_target": run.execution_target,
            "owner_host_instance_id": request.owner_host_instance_id,
            "wait_id": request.wait_id,
            "source_attempt_id": request.suspended_attempt_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _waiting_run_terminal_event_request(
    *,
    request: WaitingRunTerminalInput,
    run: RunRow,
    tool_result: EventLogRow,
) -> EventLogAppendRequest:
    """构造 waiting resolve terminal Run event request。

    :param request: waiting terminal 输入。
    :param run: 目标 Run row。
    :param tool_result: 已追加的 ``TOOL_RESULT_ACCEPTED`` row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_terminal_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.suspended_attempt_id,
        execution_id=None,
        event_type=_run_terminal_event_type(request.run_terminal_status),
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=request.resolution_idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "attempt_id": request.suspended_attempt_id,
            "wait_id": request.wait_id,
            "terminal_status": request.run_terminal_status.value,
            "reason": request.reason,
            "tool_result_event_ref": _event_ref_json_from_row(tool_result),
        },
        payload_ref=None,
        payload_digest=None,
    )


def _attempt_running_event_request(
    *,
    request: AcceptWorkerRunningInput,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow,
) -> EventLogAppendRequest:
    """构造 ``ATTEMPT_RUNNING`` EventLog append request。

    :param request: worker accepted 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param dispatch_record: 目标 dispatch record row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_running_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_RUNNING,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.worker_accept_reason},
        payload_json={
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "dispatch_record_id": dispatch_record.dispatch_record_id,
            "worker_kind": dispatch_record.worker_kind.value,
            "execution_target": dispatch_record.execution_target,
            "local_worker_id": request.local_worker_id,
            "worker_accepted_at": format_utc_timestamp(request.occurred_at),
            "lane_name": dispatch_record.lane_name,
            "lane_claim_id": dispatch_record.lane_claim_id,
            "reason": request.worker_accept_reason,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _cancel_requested_event_request(
    request: (
        CancelQueuedRunInput
        | CancelPredispatchStartingInput
        | CancelActiveAttemptInput
        | CancelWaitingRunInput
        | CancelRecoveringRunInput
    ),
    run: RunRow,
) -> EventLogAppendRequest:
    """构造 ``CANCEL_REQUESTED`` EventLog append request。

    :param request: cancel 输入。
    :param run: 被取消的 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.cancel_request_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_CANCEL_REQUESTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason, "mode": request.mode.value},
        payload_json={
            "run_id": run.run_id,
            "client_request_id": request.client_request_id,
            "reason": request.reason,
            "mode": request.mode.value,
            "target_status_at_accept": run.status.value,
            "call_context_digest": request.call_context_digest,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_cancelling_event_request(
    *,
    request: CancelActiveAttemptInput,
    run: RunRow,
    attempt: AttemptRow,
    cancel_request_event_id: str,
) -> EventLogAppendRequest:
    """构造 ``RUN_CANCELLING`` EventLog append request。

    :param request: active cancel 输入。
    :param run: 被取消的 Run row。
    :param attempt: 被取消的 active Attempt row。
    :param cancel_request_event_id: CANCEL_REQUESTED event id。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_cancelling_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_RUN_CANCELLING,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason, "mode": request.mode.value},
        payload_json={
            "run_id": run.run_id,
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "reason": request.reason,
            "mode": request.mode.value,
            "cancel_request_event_id": cancel_request_event_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _attempt_cancelled_event_request(
    *,
    request: CancelPredispatchStartingInput,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow,
    cancel_request_event_id: str,
) -> EventLogAppendRequest:
    """构造 ``ATTEMPT_CANCELLED`` EventLog append request。

    :param request: cancel pre-dispatch 输入。
    :param run: 被取消的 Run row。
    :param attempt: 被取消的 Attempt row。
    :param dispatch_record: 被取消的 dispatch record row。
    :param cancel_request_event_id: CANCEL_REQUESTED event id。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_cancelled_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_CANCELLED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "reason": request.reason,
            "cancel_request_event_id": cancel_request_event_id,
            "dispatch_record_id": dispatch_record.dispatch_record_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_cancelled_event_request(
    *,
    request: (
        CancelQueuedRunInput
        | CancelPredispatchStartingInput
        | CancelRecoveringRunInput
    ),
    run: RunRow,
    cancel_request_event_id: str,
    terminal_attempt_id: str | None,
    terminal_attempt_event_id: str | None,
) -> EventLogAppendRequest:
    """构造 ``RUN_CANCELLED`` EventLog append request。

    :param request: cancel 输入。
    :param run: 被取消的 Run row。
    :param cancel_request_event_id: CANCEL_REQUESTED event id。
    :param terminal_attempt_id: terminal Attempt id；queued cancel 时为 ``None``。
    :param terminal_attempt_event_id: Attempt terminal event id；queued cancel 时为 ``None``。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_cancelled_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=terminal_attempt_id,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_CANCELLED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "reason": request.reason,
            "cancel_request_event_id": cancel_request_event_id,
            "terminal_attempt_id": terminal_attempt_id,
            "terminal_attempt_event_id": terminal_attempt_event_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _event_ref_json_from_row(row: EventLogRow) -> JsonValue:
    """把 EventLog row 投影成事件引用 JSON。

    :param row: EventLog row。
    :returns: JSON mapping。
    """

    return {
        "event_id": row.event_id,
        "event_sequence": row.event_sequence,
    }


def _attempt_terminal_event_request(
    *,
    request: TerminalCloseoutInput,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow | None,
) -> EventLogAppendRequest:
    """构造具体 Attempt terminal EventLog append request。

    :param request: terminal closeout 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param dispatch_record: 目标 dispatch record；缺失时为 ``None``。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_terminal_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_attempt_terminal_event_type(request.attempt_terminal_status),
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json=_attempt_terminal_payload(
            request=request,
            attempt=attempt,
            dispatch_record=dispatch_record,
        ),
        payload_ref=None,
        payload_digest=None,
    )


def _run_terminal_event_request(
    *,
    request: TerminalCloseoutInput,
    run: RunRow,
    attempt: AttemptRow,
    attempt_terminal_event_id: str,
    dispatch_record: DispatchRecordRow | None,
) -> EventLogAppendRequest:
    """构造具体 Run terminal EventLog append request。

    :param request: terminal closeout 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param attempt_terminal_event_id: Attempt terminal event id。
    :param dispatch_record: 目标 dispatch record；缺失时为 ``None``。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_terminal_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.attempt_id,
        execution_id=None,
        event_type=_run_terminal_event_type(request.run_terminal_status),
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json=_run_terminal_payload(
            request=request,
            run=run,
            attempt=attempt,
            attempt_terminal_event_id=attempt_terminal_event_id,
            dispatch_record=dispatch_record,
        ),
        payload_ref=None,
        payload_digest=None,
    )


def _waiting_run_cancelled_event_request(
    *,
    request: CancelWaitingRunInput,
    run: RunRow,
    attempt: AttemptRow,
    cancel_request_event_id: str,
    wait_ids: tuple[str, ...],
) -> EventLogAppendRequest:
    """构造 waiting Run ``RUN_CANCELLED`` EventLog append request。

    :param request: waiting cancel 输入。
    :param run: 目标 Run row。
    :param attempt: 已 SUSPENDED 的当前 Attempt row。
    :param cancel_request_event_id: ``CANCEL_REQUESTED`` event id。
    :param wait_ids: 本次取消的 wait record id 列表。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_cancelled_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_CANCELLED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason, "mode": request.mode.value},
        payload_json={
            "run_id": run.run_id,
            "cancel_request_event_id": cancel_request_event_id,
            "terminal_attempt_id": attempt.attempt_id,
            "terminal_attempt_event_id": attempt.terminal_event_id,
            "waiting_cancelled": True,
            "wait_ids": list(wait_ids),
            "reason": request.reason,
            "mode": request.mode.value,
            "call_context_digest": request.call_context_digest,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _active_attempt_cancelled_event_request(
    *,
    request: ActiveCancelCloseoutInput,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow,
) -> EventLogAppendRequest:
    """构造 active cancel ``ATTEMPT_CANCELLED`` 事件。

    :param request: active cancel closeout 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param dispatch_record: 目标 dispatch record。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_cancelled_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_CANCELLED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "dispatch_record_id": dispatch_record.dispatch_record_id,
            "cancel_request_event_id": request.cancel_request_event_id,
            "reason": request.reason,
            "engine_event_ref": request.engine_event_ref,
            "requested_at": request.requested_at,
            "accepted_at": request.accepted_at,
            "finished_at": request.finished_at,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _active_run_cancelled_event_request(
    *,
    request: ActiveCancelCloseoutInput,
    run: RunRow,
    attempt: AttemptRow,
    attempt_cancelled_event_id: str,
    dispatch_record: DispatchRecordRow,
) -> EventLogAppendRequest:
    """构造 active cancel ``RUN_CANCELLED`` 事件。

    :param request: active cancel closeout 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param attempt_cancelled_event_id: ``ATTEMPT_CANCELLED`` event id。
    :param dispatch_record: 目标 dispatch record。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_cancelled_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_CANCELLED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "terminal_attempt_id": attempt.attempt_id,
            "attempt_terminal_event_id": attempt_cancelled_event_id,
            "dispatch_record_id": dispatch_record.dispatch_record_id,
            "cancel_request_event_id": request.cancel_request_event_id,
            "reason": request.reason,
            "engine_event_ref": request.engine_event_ref,
            "requested_at": request.requested_at,
            "accepted_at": request.accepted_at,
            "finished_at": request.finished_at,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _attempt_terminal_payload(
    *,
    request: TerminalCloseoutInput,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow | None,
) -> Mapping[str, JsonValue]:
    """构造 Attempt terminal canonical payload。

    :param request: terminal closeout 输入。
    :param attempt: 目标 Attempt row。
    :param dispatch_record: 目标 dispatch record；缺失时为 ``None``。
    :returns: canonical payload JSON mapping。
    """

    payload: dict[str, JsonValue] = {
        "attempt_id": attempt.attempt_id,
        "execution_id": attempt.execution_id,
        "dispatch_record_id": _dispatch_record_id(dispatch_record),
        "reason": request.reason,
        "terminal_summary_ref": request.terminal_summary_ref,
        "terminal_summary_digest": request.terminal_summary_digest,
    }
    if request.engine_event_ref is not None:
        payload["engine_event_ref"] = request.engine_event_ref
    if request.attempt_terminal_status == AttemptStatus.SUCCEEDED:
        payload["finish_reason"] = request.finish_reason
        payload["filtered"] = request.filtered
        payload["degraded"] = request.degraded
        return payload
    if request.attempt_terminal_status == AttemptStatus.FAILED:
        payload["error_code"] = request.error_code
        payload["message"] = request.message
        payload["provider_request_id"] = request.provider_request_id
        payload["recoverable"] = request.recoverable
        if request.unsupported_later_owner is not None:
            payload["unsupported_later_owner"] = request.unsupported_later_owner
        return payload
    if request.attempt_terminal_status == AttemptStatus.LOST:
        payload["worker_lifecycle_signal"] = request.worker_lifecycle_signal
        payload["stream_error_code"] = request.stream_error_code
        payload["last_observed_worker_event_index"] = (
            request.last_observed_worker_event_index
        )
        payload["last_accepted_event_id"] = request.last_accepted_event_id
    return payload


def _run_terminal_payload(
    *,
    request: TerminalCloseoutInput,
    run: RunRow,
    attempt: AttemptRow,
    attempt_terminal_event_id: str,
    dispatch_record: DispatchRecordRow | None,
) -> Mapping[str, JsonValue]:
    """构造 Run terminal canonical payload。

    :param request: terminal closeout 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param attempt_terminal_event_id: Attempt terminal event id。
    :param dispatch_record: 目标 dispatch record；缺失时为 ``None``。
    :returns: canonical payload JSON mapping。
    """

    payload: dict[str, JsonValue] = {
        "run_id": run.run_id,
        "terminal_attempt_id": attempt.attempt_id,
        "attempt_terminal_event_id": attempt_terminal_event_id,
        "dispatch_record_id": _dispatch_record_id(dispatch_record),
        "terminal_summary_ref": request.terminal_summary_ref,
        "terminal_summary_digest": request.terminal_summary_digest,
        "reason": request.reason,
    }
    if request.engine_event_ref is not None:
        payload["engine_event_ref"] = request.engine_event_ref
    if request.run_terminal_status == RunStatus.SUCCEEDED:
        payload["finish_reason"] = request.finish_reason
        payload["filtered"] = request.filtered
        payload["degraded"] = request.degraded
        return payload
    if request.run_terminal_status == RunStatus.FAILED:
        payload["error_code"] = request.error_code
        payload["message"] = request.message
        payload["provider_request_id"] = request.provider_request_id
        payload["recoverable"] = request.recoverable
        if request.unsupported_later_owner is not None:
            payload["unsupported_later_owner"] = request.unsupported_later_owner
        return payload
    if request.run_terminal_status == RunStatus.LOST:
        payload["worker_lifecycle_signal"] = request.worker_lifecycle_signal
        payload["stream_error_code"] = request.stream_error_code
        payload["last_observed_worker_event_index"] = (
            request.last_observed_worker_event_index
        )
        payload["last_accepted_event_id"] = request.last_accepted_event_id
    return payload


def _dispatch_record_id(dispatch_record: DispatchRecordRow | None) -> str | None:
    """读取 dispatch record id。

    :param dispatch_record: dispatch record row；缺失时为 ``None``。
    :returns: dispatch record id 或 ``None``。
    """

    if dispatch_record is None:
        return None
    return dispatch_record.dispatch_record_id


def _starting_attempt_row(
    *,
    request: CreateRunningRunInput,
    started_event_id: str,
    started_event_sequence: int,
    created_at: str,
) -> AttemptRow:
    """构造 STARTING Attempt row。

    :param request: 创建 running Run 输入。
    :param started_event_id: ATTEMPT_STARTED event id。
    :param started_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: Attempt row。
    """

    return AttemptRow(
        attempt_id=request.attempt_id,
        run_id=request.run_id,
        execution_id=request.execution_id,
        status=AttemptStatus.STARTING,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )


def _pending_dispatch_record_row(
    *,
    request: CreateRunningRunInput,
    created_event_id: str,
    created_event_sequence: int,
    created_at: str,
) -> DispatchRecordRow:
    """构造 pending dispatch record row。

    :param request: 创建 running Run 输入。
    :param created_event_id: ATTEMPT_STARTED event id。
    :param created_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: dispatch record row。
    """

    return DispatchRecordRow(
        dispatch_record_id=request.dispatch_record_id,
        run_id=request.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=request.worker_kind,
        execution_target=request.execution_target,
        owner_host_instance_id=request.owner_host_instance_id,
        created_event_id=created_event_id,
        created_event_sequence=created_event_sequence,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        cancelled_at=None,
    )


def _promotion_attempt_row(
    *,
    request: PromoteQueuedRunInput,
    run_id: str,
    started_event_id: str,
    started_event_sequence: int,
    created_at: str,
) -> AttemptRow:
    """构造 promotion STARTING Attempt row。

    :param request: promotion 输入。
    :param run_id: 被 promotion 的 Run id。
    :param started_event_id: ATTEMPT_STARTED event id。
    :param started_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: Attempt row。
    """

    return AttemptRow(
        attempt_id=request.attempt_id,
        run_id=run_id,
        execution_id=request.execution_id,
        status=AttemptStatus.STARTING,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )


def _promotion_dispatch_record_row(
    *,
    request: PromoteQueuedRunInput,
    run_id: str,
    execution_target: str,
    created_event_id: str,
    created_event_sequence: int,
    created_at: str,
) -> DispatchRecordRow:
    """构造 promotion pending dispatch record row。

    :param request: promotion 输入。
    :param run_id: 被 promotion 的 Run id。
    :param execution_target: Run 持久化的 execution target。
    :param created_event_id: ATTEMPT_STARTED event id。
    :param created_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: dispatch record row。
    """

    return DispatchRecordRow(
        dispatch_record_id=request.dispatch_record_id,
        run_id=run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=request.worker_kind,
        execution_target=execution_target,
        owner_host_instance_id=request.owner_host_instance_id,
        created_event_id=created_event_id,
        created_event_sequence=created_event_sequence,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        cancelled_at=None,
    )


def _governed_attempt_row(
    *,
    request: StartGovernedRunInput,
    run_id: str,
    started_event_id: str,
    started_event_sequence: int,
    created_at: str,
) -> AttemptRow:
    """构造 governance start 的 STARTING Attempt row。

    :param request: governance start 输入。
    :param run_id: 被启动的 Run id。
    :param started_event_id: ATTEMPT_STARTED event id。
    :param started_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: Attempt row。
    """

    return AttemptRow(
        attempt_id=request.attempt_id,
        run_id=run_id,
        execution_id=request.execution_id,
        status=AttemptStatus.STARTING,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )


def _governed_dispatch_record_row(
    *,
    request: StartGovernedRunInput,
    run: RunRow,
    created_event_id: str,
    created_event_sequence: int,
    created_at: str,
) -> DispatchRecordRow:
    """构造 governance start 的 pending dispatch record row。

    :param request: governance start 输入。
    :param run: 被启动的 Run row。
    :param created_event_id: ATTEMPT_STARTED event id。
    :param created_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: dispatch record row。
    """

    return DispatchRecordRow(
        dispatch_record_id=request.dispatch_record_id,
        run_id=run.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=request.worker_kind,
        execution_target=run.execution_target,
        owner_host_instance_id=request.owner_host_instance_id,
        created_event_id=created_event_id,
        created_event_sequence=created_event_sequence,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        cancelled_at=None,
    )


def _recovery_attempt_row(
    *,
    request: StartRecoveryRunInput,
    run_id: str,
    started_event_id: str,
    started_event_sequence: int,
    created_at: str,
) -> AttemptRow:
    """构造 recovery STARTING Attempt row。

    :param request: recovery start 输入。
    :param run_id: Run id。
    :param started_event_id: ``ATTEMPT_STARTED`` event id。
    :param started_event_sequence: ``ATTEMPT_STARTED`` event sequence。
    :param created_at: 创建 timestamp。
    :returns: Attempt row。
    """

    return AttemptRow(
        attempt_id=request.attempt_id,
        run_id=run_id,
        execution_id=request.execution_id,
        status=AttemptStatus.STARTING,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )


def _recovery_dispatch_record_row(
    *,
    request: StartRecoveryRunInput,
    run: RunRow,
    created_event_id: str,
    created_event_sequence: int,
    created_at: str,
) -> DispatchRecordRow:
    """构造 recovery pending dispatch record row。

    :param request: recovery start 输入。
    :param run: Run row。
    :param created_event_id: ``ATTEMPT_STARTED`` event id。
    :param created_event_sequence: ``ATTEMPT_STARTED`` event sequence。
    :param created_at: 创建 timestamp。
    :returns: dispatch record row。
    """

    return DispatchRecordRow(
        dispatch_record_id=request.dispatch_record_id,
        run_id=run.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=request.worker_kind,
        execution_target=run.execution_target,
        owner_host_instance_id=request.owner_host_instance_id,
        created_event_id=created_event_id,
        created_event_sequence=created_event_sequence,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        cancelled_at=None,
    )


def _resume_attempt_row(
    *,
    request: ResumeRunFromWaitingInput,
    started_event_id: str,
    started_event_sequence: int,
    created_at: str,
) -> AttemptRow:
    """构造 resume STARTING Attempt row。

    :param request: resume waiting 输入。
    :param started_event_id: ATTEMPT_STARTED event id。
    :param started_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: Attempt row。
    """

    return AttemptRow(
        attempt_id=request.resume_attempt_id,
        run_id=request.run_id,
        execution_id=request.resume_execution_id,
        status=AttemptStatus.STARTING,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )


def _resume_dispatch_record_row(
    *,
    request: ResumeRunFromWaitingInput,
    run: RunRow,
    created_event_id: str,
    created_event_sequence: int,
    created_at: str,
) -> DispatchRecordRow:
    """构造 resume pending dispatch record row。

    :param request: resume waiting 输入。
    :param run: 目标 Run row。
    :param created_event_id: ATTEMPT_STARTED event id。
    :param created_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: dispatch record row。
    """

    return DispatchRecordRow(
        dispatch_record_id=request.resume_dispatch_record_id,
        run_id=run.run_id,
        attempt_id=request.resume_attempt_id,
        execution_id=request.resume_execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=request.worker_kind,
        execution_target=run.execution_target,
        owner_host_instance_id=request.owner_host_instance_id,
        created_event_id=created_event_id,
        created_event_sequence=created_event_sequence,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        cancelled_at=None,
    )


def _invalid_terminal_precondition(
    run: RunRow | None, attempt: AttemptRow | None, attempt_id: str
) -> RunTransitionResult | None:
    """检查 terminal closeout 前置状态。

    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param attempt_id: 请求中的 Attempt id。
    :returns: 前置失败时返回 transition 结果，否则返回 ``None``。
    """

    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=attempt,
            dispatch_record=None,
        )
    if attempt is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    if (
        run.status != RunStatus.RUNNING
        or run.current_attempt_id != attempt_id
        or attempt.run_id != run.run_id
        or attempt.status not in (AttemptStatus.STARTING, AttemptStatus.RUNNING)
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=None,
        )
    return None


def _invalid_startup_orphan_precondition(
    *,
    transaction: HostTransaction,
    request: StartupOrphanCloseInput,
    run: RunRow | None,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
) -> RunTransitionResult | None:
    """检查 startup orphan closeout 的完整 CAS 前置。

    :param transaction: 调用方提供的 Host transaction。
    :param request: startup orphan closeout 输入。
    :param run: 最新 Run row。
    :param attempt: 最新 Attempt row。
    :param dispatch_record: 最新 dispatch record row。
    :returns: 前置失败时返回 transition 结果，否则返回 ``None``。
    """

    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
    if attempt is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=None,
            dispatch_record=dispatch_record,
        )
    if dispatch_record is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=attempt,
            dispatch_record=None,
        )
    owner = read_host_instance(transaction, request.owner_host_instance_id)
    if owner is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
    try:
        heartbeat_at = parse_utc_timestamp(owner.heartbeat_at)
    except ValueError:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
    heartbeat_stale = request.occurred_at - heartbeat_at > request.stale_after
    owner_closed = owner.status is HostInstanceStatus.STOPPED
    if (
        run.status != request.expected_run_status
        or run.current_attempt_id != attempt.attempt_id
        or run.terminal_event_id is not None
        or run.terminal_event_sequence is not None
        or run.terminal_at is not None
        or attempt.run_id != run.run_id
        or attempt.status != request.expected_attempt_status
        or attempt.execution_id != request.execution_id
        or attempt.terminal_event_id is not None
        or attempt.terminal_event_sequence is not None
        or attempt.terminal_at is not None
        or dispatch_record.dispatch_record_id != request.dispatch_record_id
        or dispatch_record.run_id != run.run_id
        or dispatch_record.attempt_id != attempt.attempt_id
        or dispatch_record.execution_id != attempt.execution_id
        or dispatch_record.status != request.expected_dispatch_status
        or dispatch_record.owner_host_instance_id != request.owner_host_instance_id
        or dispatch_record.cancelled_event_id is not None
        or dispatch_record.cancelled_event_sequence is not None
        or owner.status not in (
            HostInstanceStatus.RUNNING,
            HostInstanceStatus.STOPPING,
            HostInstanceStatus.STOPPED,
        )
        or owner.heartbeat_at != request.owner_heartbeat_at
        or (not owner_closed and not heartbeat_stale)
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
    return None


def _invalid_waiting_resolution_precondition(
    *,
    transaction: HostTransaction,
    run: RunRow | None,
    source_attempt: AttemptRow | None,
    wait_record: WaitRecordRow | None,
    run_id: str,
    suspended_attempt_id: str,
) -> WaitResolutionTransitionResult | None:
    """检查 waiting resolve 前置状态。

    :param transaction: 当前 Host transaction。
    :param run: 目标 Run row。
    :param source_attempt: 源 Attempt row。
    :param wait_record: 目标 wait record row。
    :param run_id: 请求中的 Run id。
    :param suspended_attempt_id: 请求中的 SUSPENDED Attempt id。
    :returns: 前置失败时返回 transition 结果，否则为 ``None``。
    """

    if run is None:
        return WaitResolutionTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=source_attempt,
            dispatch_record=None,
            wait_record=wait_record,
            resume_requested_event=None,
            tool_result_event=None,
            run_event=None,
            attempt_started_event=None,
        )
    if source_attempt is None or wait_record is None:
        return WaitResolutionTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=source_attempt,
            dispatch_record=None,
            wait_record=wait_record,
            resume_requested_event=None,
            tool_result_event=None,
            run_event=None,
            attempt_started_event=None,
        )
    active_waits = read_active_wait_records_for_run(transaction, run_id)
    if (
        run.status != RunStatus.WAITING
        or run.current_attempt_id != suspended_attempt_id
        or source_attempt.run_id != run.run_id
        or source_attempt.status != AttemptStatus.SUSPENDED
        or wait_record.run_id != run.run_id
        or wait_record.attempt_id != source_attempt.attempt_id
        or wait_record.status != WaitRecordStatus.WAITING
        or len(active_waits) != 1
        or active_waits[0].wait_id != wait_record.wait_id
        or run.terminal_event_id is not None
        or run.terminal_event_sequence is not None
        or run.terminal_at is not None
    ):
        return WaitResolutionTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=source_attempt,
            dispatch_record=None,
            wait_record=wait_record,
            resume_requested_event=None,
            tool_result_event=None,
            run_event=None,
            attempt_started_event=None,
        )
    return None


def _invalid_active_cancel_closeout_precondition(
    *,
    run: RunRow | None,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
    attempt_id: str,
) -> RunTransitionResult | None:
    """检查 active cancel closeout 前置状态。

    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param dispatch_record: 目标 dispatch record。
    :param attempt_id: 请求中的 Attempt id。
    :returns: 前置失败时返回 transition 结果，否则返回 ``None``。
    """

    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
    if attempt is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=None,
            dispatch_record=dispatch_record,
        )
    if dispatch_record is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=attempt,
            dispatch_record=None,
        )
    if (
        run.status != RunStatus.CANCELLING
        or run.current_attempt_id != attempt_id
        or attempt.run_id != run.run_id
        or attempt.status != AttemptStatus.RUNNING
        or dispatch_record.worker_accept_event_id is None
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
    return None


def _invalid_accept_worker_precondition(
    *,
    run: RunRow | None,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
    attempt_id: str,
) -> RunTransitionResult | None:
    """检查 worker accept 前置状态。

    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param dispatch_record: 目标 dispatch record row。
    :param attempt_id: 请求中的 Attempt id。
    :returns: 前置失败时返回 transition 结果，否则返回 ``None``。
    """

    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
    if attempt is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=None,
            dispatch_record=dispatch_record,
        )
    if dispatch_record is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=attempt,
            dispatch_record=None,
        )
    if (
        run.status != RunStatus.RUNNING
        or run.current_attempt_id != attempt_id
        or attempt.run_id != run.run_id
        or attempt.status != AttemptStatus.STARTING
        or attempt.execution_id != dispatch_record.execution_id
        or dispatch_record.run_id != run.run_id
        or dispatch_record.attempt_id != attempt.attempt_id
        or dispatch_record.status != DispatchRecordStatus.DISPATCHING
        or dispatch_record.owner_host_instance_id is None
        or dispatch_record.waiting_for_lane_at is None
        or dispatch_record.lane_name is None
        or dispatch_record.lane_claim_id is None
        or dispatch_record.lane_owner_id is None
        or dispatch_record.lane_acquired_at is None
        or dispatch_record.dispatching_at is None
        or dispatch_record.worker_accepted_at is not None
        or dispatch_record.worker_accept_event_id is not None
        or dispatch_record.worker_accept_event_sequence is not None
        or dispatch_record.cancelled_event_id is not None
        or dispatch_record.cancelled_event_sequence is not None
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
    return None


def _dispatch_record_is_direct_cancelable(
    dispatch_record: DispatchRecordRow,
) -> bool:
    """判断 dispatch record 是否仍处于 worker accept 前 direct cancel 窗口。

    :param dispatch_record: dispatch record row。
    :returns: 可 direct cancel 时返回 ``True``。
    """

    if dispatch_record.status in (
        DispatchRecordStatus.PENDING,
        DispatchRecordStatus.WAITING_FOR_LANE,
    ):
        return True
    return (
        dispatch_record.status == DispatchRecordStatus.DISPATCHING
        and dispatch_record.worker_accepted_at is None
        and dispatch_record.worker_accept_event_id is None
        and dispatch_record.worker_accept_event_sequence is None
    )


def _read_dispatch_for_attempt(
    transaction: HostTransaction, attempt: AttemptRow | None
) -> DispatchRecordRow | None:
    """按 Attempt row 读取 dispatch record。

    :param transaction: 调用方提供的 Host transaction。
    :param attempt: Attempt row；缺失时返回 ``None``。
    :returns: dispatch record row 或 ``None``。
    """

    if attempt is None:
        return None
    return read_dispatch_record_by_attempt_id(transaction, attempt.attempt_id)


def _read_current_attempt_if_present(
    transaction: HostTransaction, run: RunRow
) -> AttemptRow | None:
    """读取 Run 当前 Attempt；Run 无当前 Attempt 时返回 ``None``。

    :param transaction: 调用方提供的 Host transaction。
    :param run: Run row。
    :returns: current Attempt row 或 ``None``。
    """

    if run.current_attempt_id is None:
        return None
    return read_attempt_by_id(transaction, run.current_attempt_id)


def _read_current_dispatch_record_if_present(
    transaction: HostTransaction, run: RunRow
) -> DispatchRecordRow | None:
    """读取 Run 当前 Attempt 对应 dispatch record；缺失时返回 ``None``。

    :param transaction: 调用方提供的 Host transaction。
    :param run: Run row。
    :returns: dispatch record row 或 ``None``。
    """

    if run.current_attempt_id is None:
        return None
    return read_dispatch_record_by_attempt_id(transaction, run.current_attempt_id)


def _attempt_terminal_event_type(status: AttemptStatus) -> str:
    """把 Attempt 终态映射到具体 canonical event type。

    :param status: Attempt 终态。
    :returns: event type。
    :raises ValueError: 状态不是 terminal closeout 支持的终态时抛出。
    """

    if status == AttemptStatus.SUCCEEDED:
        return _EVENT_TYPE_ATTEMPT_SUCCEEDED
    if status == AttemptStatus.FAILED:
        return _EVENT_TYPE_ATTEMPT_FAILED
    if status == AttemptStatus.CANCELLED:
        return _EVENT_TYPE_ATTEMPT_CANCELLED
    if status == AttemptStatus.LOST:
        return _EVENT_TYPE_ATTEMPT_LOST
    raise ValueError("unsupported Attempt terminal status")


def _run_terminal_event_type(status: RunStatus) -> str:
    """把 Run 终态映射到具体 canonical event type。

    :param status: Run 终态。
    :returns: event type。
    :raises ValueError: 状态不是 terminal closeout 支持的终态时抛出。
    """

    if status == RunStatus.SUCCEEDED:
        return _EVENT_TYPE_RUN_SUCCEEDED
    if status == RunStatus.FAILED:
        return _EVENT_TYPE_RUN_FAILED
    if status == RunStatus.CANCELLED:
        return _EVENT_TYPE_RUN_CANCELLED
    if status == RunStatus.LOST:
        return _EVENT_TYPE_RUN_LOST
    raise ValueError("unsupported Run terminal status")


def _terminal_status_pair_is_compatible(
    *, attempt_status: AttemptStatus, run_status: RunStatus
) -> bool:
    """判断 Attempt / Run terminal status 是否是合法配对。

    :param attempt_status: Attempt 终态。
    :param run_status: Run 终态。
    :returns: 配对合法返回 ``True``，否则返回 ``False``。
    """

    return (attempt_status, run_status) in _TERMINAL_STATUS_PAIRS


def _validate_create_queued_input(request: CreateQueuedRunInput) -> None:
    """校验 queued Run 创建输入。

    :param request: 创建 queued Run 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_create_input(
        session_id=request.session_id,
        run_id=request.run_id,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        run_accepted_event_id=request.run_accepted_event_id,
        actor=request.actor,
        source=request.source,
        idempotency_key=request.idempotency_key,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        call_context_digest=request.call_context_digest,
    )
    _require_non_empty_text(
        request.run_queued_event_id, field_name="run_queued_event_id"
    )
    _require_non_empty_text(request.queue_reason, field_name="queue_reason")
    _require_non_empty_text(request.active_run_id, field_name="active_run_id")


def _validate_create_accepted_input(request: CreateAcceptedRunInput) -> None:
    """校验 accepted Run 创建输入。

    :param request: 创建 accepted Run 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_create_input(
        session_id=request.session_id,
        run_id=request.run_id,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        run_accepted_event_id=request.run_accepted_event_id,
        actor=request.actor,
        source=request.source,
        idempotency_key=request.idempotency_key,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        call_context_digest=request.call_context_digest,
    )


def _validate_create_running_input(request: CreateRunningRunInput) -> None:
    """校验 running Run 创建输入。

    :param request: 创建 running Run 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_create_input(
        session_id=request.session_id,
        run_id=request.run_id,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        run_accepted_event_id=request.run_accepted_event_id,
        actor=request.actor,
        source=request.source,
        idempotency_key=request.idempotency_key,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        call_context_digest=request.call_context_digest,
    )
    _require_non_empty_text(
        request.run_started_event_id, field_name="run_started_event_id"
    )
    _require_non_empty_text(
        request.attempt_started_event_id, field_name="attempt_started_event_id"
    )
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(request.execution_id, field_name="execution_id")
    _require_non_empty_text(request.dispatch_record_id, field_name="dispatch_record_id")
    if not isinstance(request.start_reason, RunStartReason):
        raise ValueError("start_reason is invalid")
    if not isinstance(request.worker_kind, WorkerKind):
        raise ValueError("worker_kind is invalid")
    _require_optional_non_empty_text(
        request.owner_host_instance_id, field_name="owner_host_instance_id"
    )


def _validate_start_governed_input(request: StartGovernedRunInput) -> None:
    """校验 governance start 输入。

    :param request: governance start 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    if request.expected_status not in (RunStatus.ACCEPTED, RunStatus.QUEUED):
        raise HostDurableError("expected_status must be accepted or queued")
    _require_non_empty_text(
        request.run_started_event_id, field_name="run_started_event_id"
    )
    _require_non_empty_text(
        request.attempt_started_event_id, field_name="attempt_started_event_id"
    )
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(request.execution_id, field_name="execution_id")
    _require_non_empty_text(request.dispatch_record_id, field_name="dispatch_record_id")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    if not isinstance(request.start_reason, RunStartReason):
        raise HostDurableError("start_reason is invalid")
    if not isinstance(request.worker_kind, WorkerKind):
        raise HostDurableError("worker_kind is invalid")
    _require_optional_non_empty_text(
        request.owner_host_instance_id, field_name="owner_host_instance_id"
    )


def _validate_fail_unstarted_input(request: FailUnstartedRunInput) -> None:
    """校验 unstarted Run failure 输入。

    :param request: failure 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    if request.expected_status not in (RunStatus.ACCEPTED, RunStatus.QUEUED):
        raise HostDurableError("expected_status must be accepted or queued")
    _require_non_empty_text(request.run_failed_event_id, field_name="run_failed_event_id")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    _require_non_empty_text(request.error_code, field_name="error_code")
    _require_non_empty_text(request.message, field_name="message")


def _validate_context_recovery_close_input(
    request: ContextRecoveryCloseInput,
) -> None:
    """校验 context recovery close 输入。

    :param request: recovery close 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(
        request.attempt_failed_event_id, field_name="attempt_failed_event_id"
    )
    _require_non_empty_text(
        request.run_recovering_event_id, field_name="run_recovering_event_id"
    )
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    _require_non_empty_text(request.engine_event_ref, field_name="engine_event_ref")
    _require_optional_non_empty_text(
        request.provider_request_id, field_name="provider_request_id"
    )
    _require_non_empty_text(request.message, field_name="message")


def _validate_startup_orphan_close_input(request: StartupOrphanCloseInput) -> None:
    """校验 startup orphan close 输入。

    :param request: startup orphan close 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    if request.expected_run_status not in (RunStatus.RUNNING, RunStatus.CANCELLING):
        raise HostDurableError("expected_run_status is invalid")
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    if request.expected_attempt_status not in (
        AttemptStatus.STARTING,
        AttemptStatus.RUNNING,
    ):
        raise HostDurableError("expected_attempt_status is invalid")
    _require_non_empty_text(request.execution_id, field_name="execution_id")
    _require_non_empty_text(
        request.dispatch_record_id, field_name="dispatch_record_id"
    )
    if not isinstance(request.expected_dispatch_status, DispatchRecordStatus):
        raise HostDurableError("expected_dispatch_status is invalid")
    _require_non_empty_text(
        request.owner_host_instance_id, field_name="owner_host_instance_id"
    )
    _require_non_empty_text(request.owner_heartbeat_at, field_name="owner_heartbeat_at")
    if request.stale_after <= timedelta(0):
        raise HostDurableError("stale_after must be positive")
    _require_non_empty_text(
        request.attempt_lost_event_id, field_name="attempt_lost_event_id"
    )
    _require_non_empty_text(request.run_close_event_id, field_name="run_close_event_id")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    _require_non_empty_text(
        request.orphan_proof_reason, field_name="orphan_proof_reason"
    )
    _require_optional_non_empty_text(
        request.observed_process_start_token,
        field_name="observed_process_start_token",
    )
    _require_optional_non_empty_text(
        request.observed_boot_id,
        field_name="observed_boot_id",
    )
    if request.recoverable and request.expected_run_status != RunStatus.RUNNING:
        raise HostDurableError("only running orphan Run can become recovering")


def _validate_startup_recovering_lost_input(
    request: StartupRecoveringLostInput,
) -> None:
    """校验 startup recovering lost 输入。

    :param request: startup recovering lost 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(
        request.source_attempt_id, field_name="source_attempt_id"
    )
    _require_non_empty_text(request.run_lost_event_id, field_name="run_lost_event_id")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    if request.recovery_dispatch_count < 0:
        raise HostDurableError("recovery_dispatch_count must be non-negative")
    if request.recovery_dispatch_limit <= 0:
        raise HostDurableError("recovery_dispatch_limit must be positive")


def _validate_start_recovery_input(request: StartRecoveryRunInput) -> None:
    """校验 recovery start 输入。

    :param request: recovery start 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(request.source_attempt_id, field_name="source_attempt_id")
    _require_non_empty_text(
        request.run_started_event_id, field_name="run_started_event_id"
    )
    _require_non_empty_text(
        request.attempt_started_event_id, field_name="attempt_started_event_id"
    )
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(request.execution_id, field_name="execution_id")
    _require_non_empty_text(request.dispatch_record_id, field_name="dispatch_record_id")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    if not isinstance(request.worker_kind, WorkerKind):
        raise HostDurableError("worker_kind is invalid")
    _require_optional_non_empty_text(
        request.owner_host_instance_id, field_name="owner_host_instance_id"
    )
    _require_optional_non_empty_text(
        request.context_compacted_event_id, field_name="context_compacted_event_id"
    )
    if (
        request.context_compacted_event_id is None
        and request.context_compacted_event_sequence is not None
    ) or (
        request.context_compacted_event_id is not None
        and request.context_compacted_event_sequence is None
    ):
        raise HostDurableError("context compacted event ref must be complete")
    if request.context_compacted_event_sequence is not None:
        _require_positive_sequence(
            request.context_compacted_event_sequence,
            "context_compacted_event_sequence",
        )


def _validate_fail_recovering_input(request: FailRecoveringRunInput) -> None:
    """校验 recovering Run failure 输入。

    :param request: recovery failure 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(request.source_attempt_id, field_name="source_attempt_id")
    _require_non_empty_text(request.run_failed_event_id, field_name="run_failed_event_id")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    _require_non_empty_text(request.error_code, field_name="error_code")
    _require_non_empty_text(request.message, field_name="message")
    _require_non_empty_text(
        request.context_compaction_failed_event_id,
        field_name="context_compaction_failed_event_id",
    )


def _validate_common_create_input(
    *,
    session_id: str,
    run_id: str,
    client_request_id: str,
    input_event_id: str,
    input_event_sequence: int,
    run_accepted_event_id: str,
    actor: str,
    source: str,
    idempotency_key: str,
    execution_target: str,
    queue_policy: str,
    call_context_digest: str,
) -> None:
    """校验 Run 创建公共字段。

    :param session_id: Session id。
    :param run_id: Run id。
    :param client_request_id: client request id。
    :param input_event_id: input event id。
    :param input_event_sequence: input event sequence。
    :param run_accepted_event_id: RUN_ACCEPTED event id。
    :param actor: actor。
    :param source: source。
    :param idempotency_key: idempotency key。
    :param execution_target: execution target。
    :param queue_policy: queue policy。
    :param call_context_digest: call context digest。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(client_request_id, field_name="client_request_id")
    _require_non_empty_text(input_event_id, field_name="input_event_id")
    _require_positive_sequence(input_event_sequence, "input_event_sequence")
    _require_non_empty_text(run_accepted_event_id, field_name="run_accepted_event_id")
    _require_non_empty_text(actor, field_name="actor")
    _require_non_empty_text(source, field_name="source")
    _require_non_empty_text(idempotency_key, field_name="idempotency_key")
    _require_non_empty_text(execution_target, field_name="execution_target")
    _require_non_empty_text(queue_policy, field_name="queue_policy")
    _require_sha256_digest(call_context_digest, field_name="call_context_digest")


def _validate_promote_input(request: PromoteQueuedRunInput) -> None:
    """校验 promotion 输入。

    :param request: promotion 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.session_id, field_name="session_id")
    _require_non_empty_text(
        request.run_started_event_id, field_name="run_started_event_id"
    )
    _require_non_empty_text(
        request.attempt_started_event_id, field_name="attempt_started_event_id"
    )
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(request.execution_id, field_name="execution_id")
    _require_non_empty_text(request.dispatch_record_id, field_name="dispatch_record_id")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    if not isinstance(request.worker_kind, WorkerKind):
        raise ValueError("worker_kind is invalid")
    _require_optional_non_empty_text(
        request.owner_host_instance_id, field_name="owner_host_instance_id"
    )


def _validate_resume_waiting_input(request: ResumeRunFromWaitingInput) -> None:
    """校验 waiting resume 输入。

    :param request: waiting resume 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.wait_id, field_name="wait_id")
    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(
        request.suspended_attempt_id, field_name="suspended_attempt_id"
    )
    _require_non_empty_text(request.resume_attempt_id, field_name="resume_attempt_id")
    _require_non_empty_text(request.resume_execution_id, field_name="resume_execution_id")
    _require_non_empty_text(
        request.resume_dispatch_record_id, field_name="resume_dispatch_record_id"
    )
    _require_non_empty_text(
        request.resume_requested_event_id, field_name="resume_requested_event_id"
    )
    _require_non_empty_text(request.tool_result_event_id, field_name="tool_result_event_id")
    _require_non_empty_text(request.run_started_event_id, field_name="run_started_event_id")
    _require_non_empty_text(
        request.attempt_started_event_id, field_name="attempt_started_event_id"
    )
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(
        request.resolution_idempotency_key,
        field_name="resolution_idempotency_key",
    )
    _require_sha256_digest(request.resolution_digest, field_name="resolution_digest")
    _require_optional_non_empty_text(
        request.tool_result_payload_ref, field_name="tool_result_payload_ref"
    )
    _require_optional_sha256_digest(
        request.tool_result_payload_digest,
        field_name="tool_result_payload_digest",
    )
    if not isinstance(request.worker_kind, WorkerKind):
        raise HostDurableError("worker_kind is invalid")
    _require_optional_non_empty_text(
        request.owner_host_instance_id, field_name="owner_host_instance_id"
    )


def _validate_waiting_terminal_input(
    request: WaitingRunTerminalInput,
    *,
    expected_run_status: RunStatus,
    expected_wait_status: WaitRecordStatus,
) -> None:
    """校验 waiting terminal 输入。

    :param request: waiting terminal 输入。
    :param expected_run_status: 调用路径允许的 Run 终态。
    :param expected_wait_status: 调用路径允许的 wait 终态。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.wait_id, field_name="wait_id")
    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(
        request.suspended_attempt_id, field_name="suspended_attempt_id"
    )
    _require_non_empty_text(request.tool_result_event_id, field_name="tool_result_event_id")
    _require_non_empty_text(
        request.run_terminal_event_id, field_name="run_terminal_event_id"
    )
    if request.run_terminal_status is not expected_run_status:
        raise HostDurableError("waiting terminal Run status is invalid")
    if request.wait_terminal_status is not expected_wait_status:
        raise HostDurableError("waiting terminal wait status is invalid")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    _require_non_empty_text(
        request.resolution_idempotency_key,
        field_name="resolution_idempotency_key",
    )
    _require_sha256_digest(request.resolution_digest, field_name="resolution_digest")
    _require_optional_non_empty_text(
        request.tool_result_payload_ref, field_name="tool_result_payload_ref"
    )
    _require_optional_sha256_digest(
        request.tool_result_payload_digest,
        field_name="tool_result_payload_digest",
    )


def _validate_terminal_input(request: TerminalCloseoutInput) -> None:
    """校验 terminal closeout 输入。

    :param request: terminal closeout 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(
        request.attempt_terminal_event_id, field_name="attempt_terminal_event_id"
    )
    _require_non_empty_text(
        request.run_terminal_event_id, field_name="run_terminal_event_id"
    )
    try:
        _attempt_terminal_event_type(request.attempt_terminal_status)
        _run_terminal_event_type(request.run_terminal_status)
    except ValueError as exc:
        raise HostDurableError(str(exc)) from exc
    if not _terminal_status_pair_is_compatible(
        attempt_status=request.attempt_terminal_status,
        run_status=request.run_terminal_status,
    ):
        raise HostDurableError("terminal Attempt and Run status pair is invalid")
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    _require_optional_non_empty_text(
        request.terminal_summary_ref, field_name="terminal_summary_ref"
    )
    _require_optional_sha256_digest(
        request.terminal_summary_digest, field_name="terminal_summary_digest"
    )
    _require_optional_non_empty_text(
        request.engine_event_ref, field_name="engine_event_ref"
    )
    _require_optional_non_empty_text(request.finish_reason, field_name="finish_reason")
    _require_optional_non_empty_text(request.error_code, field_name="error_code")
    _require_optional_non_empty_text(request.message, field_name="message")
    _require_optional_non_empty_text(
        request.provider_request_id, field_name="provider_request_id"
    )
    _require_optional_non_empty_text(
        request.unsupported_later_owner, field_name="unsupported_later_owner"
    )
    _require_optional_non_empty_text(
        request.worker_lifecycle_signal, field_name="worker_lifecycle_signal"
    )
    _require_optional_non_empty_text(
        request.stream_error_code, field_name="stream_error_code"
    )
    _require_optional_non_empty_text(
        request.last_accepted_event_id, field_name="last_accepted_event_id"
    )
    if (
        request.last_observed_worker_event_index is not None
        and request.last_observed_worker_event_index < 0
    ):
        raise HostDurableError("last_observed_worker_event_index must be non-negative")


def _validate_accept_worker_running_input(
    request: AcceptWorkerRunningInput,
) -> None:
    """校验 worker accepted 输入。

    :param request: worker accepted 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(
        request.attempt_running_event_id,
        field_name="attempt_running_event_id",
    )
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(
        request.worker_accept_reason,
        field_name="worker_accept_reason",
    )
    _require_optional_non_empty_text(
        request.local_worker_id, field_name="local_worker_id"
    )


def _validate_cancel_queued_input(request: CancelQueuedRunInput) -> None:
    """校验 cancel queued 输入。

    :param request: cancel queued 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_cancel_input(
        run_id=request.run_id,
        cancel_request_event_id=request.cancel_request_event_id,
        run_cancelled_event_id=request.run_cancelled_event_id,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        reason=request.reason,
        mode=request.mode,
        call_context_digest=request.call_context_digest,
    )


def _validate_cancel_predispatch_input(
    request: CancelPredispatchStartingInput,
) -> None:
    """校验 cancel pre-dispatch 输入。

    :param request: cancel pre-dispatch 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_cancel_input(
        run_id=request.run_id,
        cancel_request_event_id=request.cancel_request_event_id,
        run_cancelled_event_id=request.run_cancelled_event_id,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        reason=request.reason,
        mode=request.mode,
        call_context_digest=request.call_context_digest,
    )
    _require_non_empty_text(
        request.attempt_cancelled_event_id,
        field_name="attempt_cancelled_event_id",
    )


def _validate_cancel_active_input(request: CancelActiveAttemptInput) -> None:
    """校验 active cancel 输入。

    :param request: active cancel 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_cancel_input(
        run_id=request.run_id,
        cancel_request_event_id=request.cancel_request_event_id,
        run_cancelled_event_id=request.run_cancelling_event_id,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        reason=request.reason,
        mode=request.mode,
        call_context_digest=request.call_context_digest,
    )


def _validate_cancel_waiting_input(request: CancelWaitingRunInput) -> None:
    """校验 waiting cancel 输入。

    :param request: waiting cancel 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_cancel_input(
        run_id=request.run_id,
        cancel_request_event_id=request.cancel_request_event_id,
        run_cancelled_event_id=request.run_cancelled_event_id,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        reason=request.reason,
        mode=request.mode,
        call_context_digest=request.call_context_digest,
    )
    _require_non_empty_text(
        request.run_cancelled_event_id, field_name="run_cancelled_event_id"
    )


def _validate_cancel_recovering_input(request: CancelRecoveringRunInput) -> None:
    """校验 recovering cancel 输入。

    :param request: recovering cancel 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_cancel_input(
        run_id=request.run_id,
        cancel_request_event_id=request.cancel_request_event_id,
        run_cancelled_event_id=request.run_cancelled_event_id,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        reason=request.reason,
        mode=request.mode,
        call_context_digest=request.call_context_digest,
    )


def _validate_active_cancel_closeout_input(
    request: ActiveCancelCloseoutInput,
) -> None:
    """校验 active cancel closeout 输入。

    :param request: active cancel closeout 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(
        request.attempt_cancelled_event_id,
        field_name="attempt_cancelled_event_id",
    )
    _require_non_empty_text(
        request.run_cancelled_event_id,
        field_name="run_cancelled_event_id",
    )
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    _require_non_empty_text(
        request.cancel_request_event_id,
        field_name="cancel_request_event_id",
    )
    _require_non_empty_text(
        request.engine_event_ref,
        field_name="engine_event_ref",
    )
    _require_non_empty_text(request.requested_at, field_name="requested_at")
    _require_non_empty_text(request.accepted_at, field_name="accepted_at")
    _require_non_empty_text(request.finished_at, field_name="finished_at")


def _validate_common_cancel_input(
    *,
    run_id: str,
    cancel_request_event_id: str,
    run_cancelled_event_id: str,
    actor: str,
    source: str,
    client_request_id: str,
    idempotency_key: str,
    reason: str,
    mode: CancelMode,
    call_context_digest: str,
) -> None:
    """校验 cancel 公共字段。

    :param run_id: Run id。
    :param cancel_request_event_id: CANCEL_REQUESTED event id。
    :param run_cancelled_event_id: RUN_CANCELLED event id。
    :param actor: actor。
    :param source: source。
    :param client_request_id: client request id。
    :param idempotency_key: idempotency key。
    :param reason: reason。
    :param mode: cancel mode。
    :param call_context_digest: call context digest。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(
        cancel_request_event_id, field_name="cancel_request_event_id"
    )
    _require_non_empty_text(run_cancelled_event_id, field_name="run_cancelled_event_id")
    _require_non_empty_text(actor, field_name="actor")
    _require_non_empty_text(source, field_name="source")
    _require_non_empty_text(client_request_id, field_name="client_request_id")
    _require_non_empty_text(idempotency_key, field_name="idempotency_key")
    _require_non_empty_text(reason, field_name="reason")
    if mode != CancelMode.GRACEFUL:
        raise ValueError("cancel mode must be graceful")
    _require_sha256_digest(call_context_digest, field_name="call_context_digest")


def _require_positive_sequence(value: int, field_name: str) -> None:
    """校验事件序号为正整数。

    :param value: 事件序号。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 序号小于等于零时抛出。
    """

    if value <= 0:
        raise HostDurableError(f"{field_name} must be positive")
