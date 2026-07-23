"""Host 内部 admission 服务。

本模块实现 Phase 3 P3-S5 的内部 command 编排：``start_run``、
``submit_followup(queue)``、``cancel_run``与 terminal closeout。它只依赖 Host durable
foundation、Session/Run/Attempt state helper 与调用方提供的 transaction
runner；不实现 public facade、scheduler、lane、WorkerProxy、Engine dispatch、
steer、retry、replay、wait 或 recovery。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast
from uuid import uuid4

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_schema import ToolSchema
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.host.api import (
    AttemptStatus,
    AuthorizationClaim,
    CancelRunRequest,
    CancelSessionRunsRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostInput,
    OrdinaryRunExecutionBaseline,
    OperationContext,
    ReplayRunRequest,
    RetryRunRequest,
    RunStatus,
    SessionSnapshot,
    SessionStatus,
    SourceRunRelation,
    StartRunRequest,
    SteerConflictDetail,
    SubmitFollowupRequest,
)
from dayu.host.durable._validation import (
    require_non_empty_text as _require_non_empty_text,
    require_sha256_digest as _require_sha256_digest,
)
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    sha256_digest_json,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.idempotency import (
    IdempotencyRecord,
    IdempotencyResultRef,
    IdempotencyResultKind,
    IdempotencyScope,
    IdempotencyScopeKind,
    IdempotencyStore,
)
from dayu.host.durable.payload import (
    PayloadDescriptor,
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host._runner_call_manifest import (
    RunnerCallSizingUnavailableReason,
    complete_runner_call_sizing_snapshot,
    unavailable_runner_call_sizing_snapshot,
)
from dayu.host.context_budget import (
    ContextBudgetPolicy,
    ContextSizingResult,
    ContextSizingStage,
    build_conservative_context_sizing_result,
    build_conservative_context_sizing_result_from_atoms,
)
from dayu.host.context_events import (
    append_context_budget_evaluated_in_transaction,
)
from dayu.host.durable.run_transition import (
    CancelActiveAttemptInput,
    CancelPredispatchStartingInput,
    CancelQueuedRunInput,
    CancelRecoveringRunInput,
    CancelWaitingRunInput,
    CreateAcceptedRunInput,
    CreateQueuedRunInput,
    RunTransitionResult as DurableRunTransitionResult,
    TerminalCloseoutInput,
    cancel_predispatch_starting_in_transaction,
    cancel_queued_in_transaction,
    cancel_recovering_run_in_transaction,
    cancel_waiting_run_in_transaction,
    confirm_terminal_run_in_transaction,
    create_accepted_run_in_transaction,
    create_queued_run_in_transaction,
    project_terminal_notice_from_exact_run_event,
    request_active_attempt_cancel_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    RunStartReason,
    SessionRow,
    StateMutationStatus,
    WorkerKind,
    cancel_active_wait_records_for_run,
    count_runs_by_source_relation,
    insert_attempt,
    insert_dispatch_record,
    is_terminal_run_status,
    read_active_run_for_session,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_non_terminal_runs_for_session,
    read_run_by_id,
    read_session_by_id,
    read_session_slot_by_session_id,
    session_snapshot_from_rows,
    set_new_run_source_relation_row,
    steer_active_run_row,
    steer_running_attempt_row,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host._execution_config_projection import (
    effective_execution_config_json as _effective_execution_config_json,
    effective_execution_snapshot_from_json as _effective_execution_snapshot_from_json,
    optional_agent_policy_json as _optional_agent_policy_json,
    optional_runner_options_json as _optional_runner_options_json,
    optional_runner_spec_json as _optional_runner_spec_json,
)
from dayu.host.projection import (
    NoopProjectionCatchupPort,
    ProjectionCatchupPort,
    catch_up_projection_best_effort,
)
from dayu.host.memory import (
    MemoryProjectionPolicy,
)
from dayu.host.memory_repair import (
    catch_up_conversation_memory_projection,
)
from dayu.host.run_input import (
    PolicySnapshot,
    SessionContinuityView,
    ToolExecutionMode,
    estimate_prepared_runner_call_candidate,
    load_prepared_runner_call_source_in_transaction,
    prepare_runner_call_candidate_in_transaction,
    record_prepared_runner_call_candidate_in_transaction,
)
from dayu.host.tool_runtime import (
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
)
from dayu.host.queue_policy import (
    RunQueuePolicy,
    parse_run_queue_policy,
    serialize_run_queue_policy,
)
from dayu.host.payload_resolution import event_payload_object
from dayu.host.tool_runtime_schema_projection import (
    tool_definitions_digest as _tool_definitions_digest,
    tool_schemas_digest as _tool_schemas_digest,
)
from dayu.host.tooling import HostToolingOptions
from dayu.host.terminal_post_commit import (
    TerminalPostCommitNotice,
    TerminalPostCommitPort,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_LOGGER = logging.getLogger(__name__)
_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_STEER_REQUESTED = "STEER_REQUESTED"
_EVENT_TYPE_ATTEMPT_STEERED = "ATTEMPT_STEERED"
_EVENT_TYPE_RUN_STARTED = "RUN_STARTED"
_EVENT_TYPE_ATTEMPT_STARTED = "ATTEMPT_STARTED"
_EVENT_TYPE_RETRY_REQUESTED = "RETRY_REQUESTED"
_EVENT_TYPE_REPLAY_REQUESTED = "REPLAY_REQUESTED"
_EVENT_SOURCE = "host.admission"
_INTERNAL_ACTOR = "host"
_EVENT_ID_PREFIX = "event"
_RUN_ID_PREFIX = "run"
_ATTEMPT_ID_PREFIX = "attempt"
_EXECUTION_ID_PREFIX = "execution"
_DISPATCH_RECORD_ID_PREFIX = "dispatch"
_OPERATION_START_RUN = IdempotencyScopeKind.START_RUN
_OPERATION_SUBMIT_FOLLOWUP_QUEUE = IdempotencyScopeKind.SUBMIT_FOLLOWUP_QUEUE
_OPERATION_SUBMIT_FOLLOWUP_STEER = IdempotencyScopeKind.SUBMIT_FOLLOWUP_STEER
_OPERATION_RETRY_RUN = IdempotencyScopeKind.RETRY_RUN
_OPERATION_REPLAY_RUN = IdempotencyScopeKind.REPLAY_RUN
_OPERATION_CANCEL_RUN = IdempotencyScopeKind.CANCEL_RUN
_OPERATION_CANCEL_SESSION_RUNS = IdempotencyScopeKind.CANCEL_SESSION_RUNS
_IDEMPOTENCY_RESULT_KIND_RUN = IdempotencyResultKind.RUN
_IDEMPOTENCY_RESULT_KIND_SESSION = IdempotencyResultKind.SESSION
_QUEUE_REASON_ACTIVE_RUN_EXISTS = "active_run_exists"
_TERMINAL_CLOSEOUT_REASON = "phase3_internal_closeout"
_TOOL_SNAPSHOT_REF_PREFIX = "tools:"
_TOOL_SELECTION_ALL = "all"
_TOOL_SELECTION_NONE = "none"
_TOOL_SELECTION_SUBSET = "subset"
_MAX_ORDINARY_RETRY_RUNS_PER_SOURCE = 1
_EFFECTIVE_TOOL_FACT_FIELDS = frozenset(
    {
        "tool_snapshot_ref",
        "selector",
        "requested_business_tool_names",
        "effective_business_tool_names",
        "business_bundle_digest",
        "effective_schema_digest",
        "effective_tool_display_names",
        "source_refs",
    }
)
_TOOL_SOURCE_REF_FIELDS = frozenset(
    {"source_kind", "source_id", "version_ref", "content_digest"}
)


class EffectiveBusinessToolSelector(StrEnum):
    """admission 冻结的业务工具选择意图。"""

    ALL = _TOOL_SELECTION_ALL
    SUBSET = _TOOL_SELECTION_SUBSET
    NONE = _TOOL_SELECTION_NONE


@dataclass(frozen=True, slots=True)
class EffectiveToolFacts:
    """admission 与 dispatch 共用的严格 effective tool facts。

    :param tool_snapshot_ref: exact effective schema snapshot 引用。
    :param selector: 调用方选择意图。
    :param requested_business_tool_names: 原始选择；``all`` 时为 ``None``。
    :param effective_business_tool_names: admission 时冻结的 exact 工具名集合。
    :param business_bundle_digest: admission 时完整业务 bundle 摘要。
    :param effective_schema_digest: exact selected schema 摘要。
    :param effective_tool_display_names: exact selected display name 快照。
    :param source_refs: admission 时完整业务工具来源引用。
    """

    tool_snapshot_ref: str
    selector: EffectiveBusinessToolSelector
    requested_business_tool_names: frozenset[str] | None
    effective_business_tool_names: frozenset[str]
    business_bundle_digest: str
    effective_schema_digest: str
    effective_tool_display_names: tuple[tuple[str, str], ...]
    source_refs: tuple[ToolBundleSourceRef, ...]


class AdmissionClock(Protocol):
    """admission 服务使用的时钟端口。"""

    def now(self) -> datetime:
        """返回当前时间。

        :returns: timezone-aware ``datetime``。
        :raises RuntimeError: 具体实现可在时钟不可用时抛出。
        """

        ...


class AdmissionIdFactory(Protocol):
    """admission 服务使用的 id 生成端口。"""

    def new_id(self, prefix: str) -> str:
        """生成带指定前缀的稳定文本 id。

        :param prefix: id 前缀。
        :returns: 新生成的非空 id。
        :raises RuntimeError: 具体实现可在熵源不可用时抛出。
        """

        ...


class AdmissionWakeupPort(Protocol):
    """admission commit 后的轻量 wakeup 端口。

    该端口只负责 commit 后的轻量唤醒；具体实现可以连接 scheduler，但不得在
    admission transaction 内启动 Engine、lane acquire 或 WorkerProxy。
    """

    def wake_dispatch(self, record: "PendingDispatchRecord") -> None:
        """唤醒后续 dispatch 检查。

        :param record: 已持久化的 pending dispatch 摘要。
        :returns: ``None``。
        :raises RuntimeError: 具体测试或上层实现可抛出自身错误。
        """

        ...

    def wake_queue_promotion(self, session_id: str) -> None:
        """唤醒同 Session queue promotion 检查。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises RuntimeError: 具体测试或上层实现可抛出自身错误。
        """

        ...


@dataclass(frozen=True, slots=True)
class SubmitFollowupQueueAdmissionInput:
    """follow-up queue admission 的内部输入。

    :param request: 公共 follow-up request，必须为 ``behavior=queue``。
    :param resolved_execution_target: 调用方已归一化的执行目标，必须非空。
    """

    request: SubmitFollowupRequest
    resolved_execution_target: str


@dataclass(frozen=True, slots=True)
class _ResolvedFollowupEffectiveFacts:
    """admission 前解析出的 per-run effective 冻结事实。

    :param effective_execution_config: effective runner / agent 配置 JSON。
    :param effective_tool_set: effective business tool 集合 JSON。
    """

    effective_execution_config: JsonValue
    effective_tool_set: JsonValue


@dataclass(frozen=True, slots=True)
class PendingDispatchRecord:
    """commit 后 dispatch wakeup 使用的 pending dispatch 摘要。

    :param dispatch_record_id: dispatch record id。
    :param run_id: 所属 Run id。
    :param attempt_id: 所属 Attempt id。
    :param execution_id: execution id。
    :param execution_target: 已持久化执行目标。
    :param worker_kind: worker 类型。
    """

    dispatch_record_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    execution_target: str
    worker_kind: WorkerKind


@dataclass(frozen=True, slots=True)
class RunAdmissionResult:
    """start/follow-up admission 结果。

    :param run: 命令返回的 Run row。
    :param attempt: 本次或幂等首次创建的 current Attempt；无 Attempt 时为 ``None``。
    :param dispatch_record: 本次或幂等首次创建的 dispatch record；无 dispatch 时为 ``None``。
    :param pending_dispatch: commit 后需要唤醒 dispatch 检查的摘要。
    :param created: 本次调用是否新建 Run。
    :param queued: 返回的 Run 是否处于 queued 状态。
    :param attached_active: 是否通过 ``attach_active`` 返回既有 active Run。
    :param idempotent_replay: 是否命中既有幂等记录。
    """

    run: RunRow
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None
    pending_dispatch: PendingDispatchRecord | None
    created: bool
    queued: bool
    attached_active: bool
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class SteerAdmissionResult:
    """submit_followup(steer) admission 结果。

    :param run: steer 后的目标 Run row。
    :param attempt: 新建 current Attempt；幂等重放时为当前 Attempt。
    :param dispatch_record: 新建 dispatch record；幂等重放时为当前 dispatch record。
    :param pending_dispatch: commit 后需要唤醒 dispatch 的摘要。
    :param steered_cancel_target: commit 后需要 best-effort 取消的旧 active worker。
    :param input_event_id: 本次 steer 接受的输入事件 id。
    :param idempotent_replay: 是否命中既有幂等记录。
    """

    run: RunRow
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None
    pending_dispatch: PendingDispatchRecord | None
    steered_cancel_target: ActiveCancelTarget | None
    input_event_id: str
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class ActiveCancelTarget:
    """commit 后需要传播到 active worker 的取消目标。

    :param run_id: 目标 Run id。
    :param attempt_id: 当前 active Attempt id。
    :param execution_id: 当前 active execution id。
    :param reason: 调用方取消原因。
    """

    run_id: str
    attempt_id: str
    execution_id: str
    reason: str


class _CancelRunClassification(StrEnum):
    """单 Run cancel 在唯一 write snapshot 下的闭集分类。"""

    SUPPORTED = "supported"
    DEFERRED = "deferred"
    TERMINAL = "terminal"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class _CancelRunOperationResult:
    """``_CancelRunOperation`` 的 transaction-local 分类结果。

    :param classification: 当前 write snapshot 的闭集分类。
    :param result: supported/terminal 路径的 cancel result；其它分类为 ``None``。
    """

    classification: _CancelRunClassification
    result: CancelRunResult | None


@dataclass(frozen=True, slots=True)
class CloseoutAttemptTerminalInput:
    """admission 层 internal terminal closeout 输入。

    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id，必须是 Run 当前 Attempt。
    :param attempt_terminal_status: Attempt 具体终态，只支持 succeeded/failed/lost。
    :param run_terminal_status: Run 具体终态，只支持 succeeded/failed/lost。
    :param terminal_summary_ref: terminal summary 引用；无摘要时为 ``None``。
    :param terminal_summary_digest: terminal summary digest；无摘要时为 ``None``。
    """

    run_id: str
    attempt_id: str
    attempt_terminal_status: AttemptStatus
    run_terminal_status: RunStatus
    terminal_summary_ref: str | None
    terminal_summary_digest: str | None


@dataclass(frozen=True, slots=True)
class CancelRunResult:
    """admission 层 cancel_run 结果。

    :param run: cancel 后或幂等重放读取到的 Run。
    :param attempt: Run 当前 Attempt；queued cancel 时为 ``None``。
    :param dispatch_record: 当前 Attempt 对应 dispatch record；无 Attempt 时为 ``None``。
    :param terminal_notice: transaction commit 后消费的精确 terminal notice；
        nonterminal active cancel request 时为 ``None``。
    :param active_cancel_target: commit 后需要 best-effort 传播的 active worker
        cancel 目标；无 active worker 时为 ``None``。
    :param idempotent_replay: 是否命中既有 cancel 幂等记录。
    """

    run: RunRow
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None
    terminal_notice: TerminalPostCommitNotice | None
    active_cancel_target: ActiveCancelTarget | None
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class SessionCancelResult:
    """admission 层 cancel_session_runs 结果。

    :param snapshot: cancel 后或幂等重放读取到的 Session snapshot。
    :param active_cancel_targets: commit 后需要 best-effort 传播的 active worker
        cancel 目标集合。
    :param idempotent_replay: 是否命中既有 session-scope cancel 幂等记录。
    :param cancelled_run_count: 本次新取消的 Run 数；幂等重放时为 0。
    :param terminal_notices: 按 terminal EventLog sequence 排序的精确 notices。
    """

    snapshot: SessionSnapshot
    active_cancel_targets: tuple[ActiveCancelTarget, ...]
    idempotent_replay: bool
    cancelled_run_count: int
    terminal_notices: tuple[TerminalPostCommitNotice, ...]


@dataclass(frozen=True, slots=True)
class TerminalCloseoutResult:
    """admission 层 terminal closeout 结果。

    :param run: terminal closeout 后的 Run。
    :param attempt: terminal closeout 后的 Attempt。
    :param dispatch_record: Attempt 对应 dispatch record；缺失时为 ``None``。
    :param terminal_notice: transaction commit 后消费的精确 terminal notice。
    """

    run: RunRow
    attempt: AttemptRow
    dispatch_record: DispatchRecordRow | None
    terminal_notice: TerminalPostCommitNotice


class NoopAdmissionWakeupPort:
    """默认 no-op wakeup port。

    该实现只满足 admission 服务依赖注入，不启动任何后台任务或外部副作用。
    """

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """忽略 dispatch wakeup。

        :param record: 已持久化的 pending dispatch 摘要。
        :returns: ``None``。
        """

        del record

    def wake_queue_promotion(self, session_id: str) -> None:
        """忽略 queue promotion wakeup。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        """

        del session_id


class UtcAdmissionClock:
    """使用系统 UTC 时间的 admission clock。"""

    def now(self) -> datetime:
        """返回当前 UTC 时间。

        :returns: timezone-aware UTC ``datetime``。
        """

        return datetime.now(UTC)


class UuidAdmissionIdFactory:
    """使用 UUID4 生成 admission id 的默认工厂。"""

    def new_id(self, prefix: str) -> str:
        """生成 ``prefix-uuid`` 格式 id。

        :param prefix: id 前缀。
        :returns: 新生成的文本 id。
        :raises ValueError: ``prefix`` 为空时抛出。
        """

        if prefix.strip() == "":
            raise ValueError("prefix must be non-empty")
        return f"{prefix}-{uuid4().hex}"


@dataclass(frozen=True, slots=True)
class HostAdmissionService:
    """Host 内部 admission 服务。

    :param transaction_runner: Host durable write transaction runner。
    :param event_log_store: EventLog primitive。
    :param idempotency_store: idempotency primitive。
    :param payload_store: durable payload primitive。
    :param clock: admission 事件时间来源。
    :param id_factory: admission id 生成端口。
    :param wakeup_port: commit 后 no-op/测试 wakeup 端口。
    :param terminal_post_commit_port: commit 后消费精确 terminal notice 的本地端口。
    :param projection_catchup_port: commit 后 best-effort projection catch-up 端口。
    :param ordinary_run_baseline: ordinary Run 的显式 execution baseline；管理句柄为
        ``None``。
    :param tooling_options: ordinary Run 的显式 tool truth；管理句柄为 ``None``。
    :param context_budget_policy: continuation context budget policy；管理句柄为
        ``None``。
    :param memory_projection_policy: continuation memory projection policy；管理句柄为
        ``None``。
    :param enable_truncation_manager: 是否启用受 Host 治理的 truncation manager。
    :param owner_host_instance_id: 当前 Host owner id；不声明 owner 时为 ``None``。
    """

    transaction_runner: HostTransactionRunner
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    payload_store: PayloadStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory
    wakeup_port: AdmissionWakeupPort
    terminal_post_commit_port: TerminalPostCommitPort
    projection_catchup_port: ProjectionCatchupPort
    ordinary_run_baseline: OrdinaryRunExecutionBaseline | None
    tooling_options: HostToolingOptions | None
    context_budget_policy: ContextBudgetPolicy | None
    memory_projection_policy: MemoryProjectionPolicy | None
    enable_truncation_manager: bool
    owner_host_instance_id: str | None

    def start_run(
        self, request: StartRunRequest, *, caller_semantic_digest: str
    ) -> RunAdmissionResult:
        """接受显式 start_run 请求。

        :param request: start_run 请求。
        :param caller_semantic_digest: 调用方语义输入摘要。
        :returns: Run admission 结果。
        :raises ValueError: queue policy 未知或 digest 非法时抛出。
        :raises HostApiError: Session 缺失、closed、active reject 或幂等冲突时抛出。
        :raises HostDurableError: durable 写入失败时由底层抛出。
        """

        policy = parse_run_queue_policy(request.queue_policy)
        _require_sha256_digest(
            caller_semantic_digest, field_name="caller_semantic_digest"
        )
        result = self.transaction_runner.run_write(
            _StartRunOperation(
                request=request,
                policy=policy,
                caller_semantic_digest=caller_semantic_digest,
                ordinary_run_baseline=self.ordinary_run_baseline,
                tooling_options=self.tooling_options,
                event_log_store=self.event_log_store,
                idempotency_store=self.idempotency_store,
                clock=self.clock,
                id_factory=self.id_factory,
            )
        )
        _log_run_admission_result(_OPERATION_START_RUN, result)
        catch_up_projection_best_effort(self.projection_catchup_port)
        _wake_dispatch_if_needed(self.wakeup_port, result.pending_dispatch)
        _wake_start_governance_if_needed(self.wakeup_port, result.run)
        return result

    def submit_followup_queue(
        self,
        admission_input: SubmitFollowupQueueAdmissionInput,
        *,
        caller_semantic_digest: str,
    ) -> RunAdmissionResult:
        """接受 ``submit_followup(queue)`` 请求。

        :param admission_input: follow-up queue admission 输入。
        :param caller_semantic_digest: 调用方语义输入摘要。
        :returns: Run admission 结果。
        :raises ValueError: behavior 非 queue、resolved target 为空或 digest 非法时抛出。
        :raises HostApiError: Session 缺失、closed 或幂等冲突时抛出。
        :raises HostDurableError: durable 写入失败时由底层抛出。
        """

        _validate_followup_queue_input(admission_input)
        _require_sha256_digest(
            caller_semantic_digest, field_name="caller_semantic_digest"
        )
        result = self.transaction_runner.run_write(
            _SubmitFollowupQueueOperation(
                admission_input=admission_input,
                caller_semantic_digest=caller_semantic_digest,
                ordinary_run_baseline=self.ordinary_run_baseline,
                tooling_options=self.tooling_options,
                event_log_store=self.event_log_store,
                idempotency_store=self.idempotency_store,
                clock=self.clock,
                id_factory=self.id_factory,
            )
        )
        _log_run_admission_result(_OPERATION_SUBMIT_FOLLOWUP_QUEUE, result)
        catch_up_projection_best_effort(self.projection_catchup_port)
        _wake_dispatch_if_needed(self.wakeup_port, result.pending_dispatch)
        _wake_start_governance_if_needed(self.wakeup_port, result.run)
        return result

    def submit_followup_steer(
        self,
        request: SubmitFollowupRequest,
        *,
        caller_semantic_digest: str,
    ) -> SteerAdmissionResult:
        """接受 ``submit_followup(steer)`` 请求。

        :param request: follow-up steer 请求。
        :param caller_semantic_digest: 调用方语义输入摘要。
        :returns: steer admission 结果。
        :raises ValueError: behavior 非 steer 或 digest 非法时抛出。
        :raises HostApiError: 目标 Run 非 active RUNNING / WAITING 或幂等冲突时抛出。
        :raises HostDurableError: durable 写入失败时由底层抛出。
        """

        if request.behavior != FollowupBehavior.STEER:
            raise ValueError("SubmitFollowupRequest.behavior must be steer")
        _require_sha256_digest(
            caller_semantic_digest, field_name="caller_semantic_digest"
        )
        if self.memory_projection_policy is None:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="submit_followup steer requires memory policy",
                retryable=False,
            )
        catch_up = catch_up_conversation_memory_projection(
            self.transaction_runner,
            policy=self.memory_projection_policy,
            batch_size=self.memory_projection_policy.max_delta_repair_events,
        )
        if catch_up.failures != 0:
            raise HostDurableError(
                "steer memory projection catch-up failed"
            )
        result = self.transaction_runner.run_write(
            _SubmitFollowupSteerOperation(
                request=request,
                caller_semantic_digest=caller_semantic_digest,
                event_log_store=self.event_log_store,
                idempotency_store=self.idempotency_store,
                clock=self.clock,
                id_factory=self.id_factory,
                ordinary_run_baseline=self.ordinary_run_baseline,
                tooling_options=self.tooling_options,
                payload_store=self.payload_store,
                context_budget_policy=self.context_budget_policy,
                memory_projection_policy=self.memory_projection_policy,
                enable_truncation_manager=self.enable_truncation_manager,
                owner_host_instance_id=self.owner_host_instance_id,
            )
        )
        catch_up_projection_best_effort(self.projection_catchup_port)
        _wake_dispatch_if_needed(self.wakeup_port, result.pending_dispatch)
        return result

    def retry_run(
        self,
        run_id: str,
        request: RetryRunRequest,
        *,
        caller_semantic_digest: str,
    ) -> RunAdmissionResult:
        """接受普通本地 FAILED Run retry 请求。

        :param run_id: 源 Run id。
        :param request: retry run 请求。
        :param caller_semantic_digest: 调用方语义输入摘要。
        :returns: 关联新 Run admission 结果。
        :raises HostApiError: 源 Run 缺失、非 FAILED、Session closed、幂等冲突或
            retry policy limit 命中时抛出。
        :raises HostDurableError: durable 写入失败时由底层抛出。
        """

        _require_non_empty_text(run_id, field_name="run_id")
        _require_sha256_digest(
            caller_semantic_digest, field_name="caller_semantic_digest"
        )
        result = self.transaction_runner.run_write(
            _RetryRunOperation(
                run_id=run_id,
                request=request,
                caller_semantic_digest=caller_semantic_digest,
                event_log_store=self.event_log_store,
                idempotency_store=self.idempotency_store,
                clock=self.clock,
                id_factory=self.id_factory,
            )
        )
        _log_run_admission_result(_OPERATION_RETRY_RUN, result)
        catch_up_projection_best_effort(self.projection_catchup_port)
        _wake_dispatch_if_needed(self.wakeup_port, result.pending_dispatch)
        _wake_start_governance_if_needed(self.wakeup_port, result.run)
        return result

    def replay_run(
        self,
        run_id: str,
        request: ReplayRunRequest,
        *,
        caller_semantic_digest: str,
    ) -> RunAdmissionResult:
        """接受 SUCCEEDED Run 的 no-tool 结构修复 replay 请求。

        :param run_id: 源 Run id。
        :param request: replay run 请求。
        :param caller_semantic_digest: 调用方语义输入摘要。
        :returns: 关联新 Run admission 结果。
        :raises HostApiError: 源 Run 缺失、非 SUCCEEDED、Session closed 或幂等冲突时抛出。
        :raises HostDurableError: durable 写入失败时由底层抛出。
        """

        _require_non_empty_text(run_id, field_name="run_id")
        _require_sha256_digest(
            caller_semantic_digest, field_name="caller_semantic_digest"
        )
        result = self.transaction_runner.run_write(
            _ReplayRunOperation(
                run_id=run_id,
                request=request,
                caller_semantic_digest=caller_semantic_digest,
                event_log_store=self.event_log_store,
                idempotency_store=self.idempotency_store,
                clock=self.clock,
                id_factory=self.id_factory,
                ordinary_run_baseline=self.ordinary_run_baseline,
            )
        )
        _log_run_admission_result(_OPERATION_REPLAY_RUN, result)
        catch_up_projection_best_effort(self.projection_catchup_port)
        _wake_dispatch_if_needed(self.wakeup_port, result.pending_dispatch)
        _wake_start_governance_if_needed(self.wakeup_port, result.run)
        return result

    def cancel_run(
        self,
        run_id: str,
        request: CancelRunRequest,
        *,
        caller_semantic_digest: str,
    ) -> CancelRunResult:
        """接受单 Run cancel 请求。

        :param run_id: 被取消的 Run id。
        :param request: cancel run 请求。
        :param caller_semantic_digest: 调用方语义输入摘要。
        :returns: cancel 结果；pre-dispatch active cancel 会包含 promotion 结果。
        :raises ValueError: run id 或 digest 非法时抛出。
        :raises HostApiError: Run 缺失、幂等冲突或 Phase 3 不支持状态时抛出。
        :raises HostDurableError: durable 写入失败时由底层抛出。
        """

        _require_non_empty_text(run_id, field_name="run_id")
        _require_sha256_digest(
            caller_semantic_digest, field_name="caller_semantic_digest"
        )
        operation_result = self.transaction_runner.run_write(
            _CancelRunOperation(
                run_id=run_id,
                request=request,
                caller_semantic_digest=caller_semantic_digest,
                event_log_store=self.event_log_store,
                idempotency_store=self.idempotency_store,
                clock=self.clock,
                id_factory=self.id_factory,
            )
        )
        if operation_result.classification is _CancelRunClassification.DEFERRED:
            raise HostApiError(
                code=HostApiErrorCode.UNSUPPORTED_OPERATION,
                message="Run cancel requires a later cancel owner phase",
                retryable=False,
            )
        if operation_result.classification is _CancelRunClassification.CONFLICT:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="Run state is not cancellable in Phase 5 admission",
                retryable=False,
            )
        result = operation_result.result
        if result is None:
            raise HostApiError(
                code=HostApiErrorCode.INTERNAL_ERROR,
                message="Cancel transaction classification is missing its result",
                retryable=False,
            )
        if result.terminal_notice is not None:
            self.terminal_post_commit_port.notify_terminal_post_commit(
                result.terminal_notice
            )
        return result

    def cancel_session_runs(
        self,
        session_id: str,
        request: CancelSessionRunsRequest,
        *,
        caller_semantic_digest: str,
    ) -> SessionCancelResult:
        """接受 session-scope cancel 请求。

        本方法取消 queued、pre-dispatch ``STARTING``、active worker、
        ``WAITING`` 与 ``RECOVERING`` Run；存在其它非终态状态时 fail closed。

        :param session_id: 目标 Session id。
        :param request: cancel session runs 请求。
        :param caller_semantic_digest: 调用方语义输入摘要。
        :returns: cancel 后的 Session snapshot。
        :raises ValueError: session id 或 digest 非法时抛出。
        :raises HostApiError: Session 缺失、幂等冲突或存在未支持非终态 Run 时抛出。
        :raises HostDurableError: durable 写入失败时由底层抛出。
        """

        _require_non_empty_text(session_id, field_name="session_id")
        _require_sha256_digest(
            caller_semantic_digest, field_name="caller_semantic_digest"
        )
        result = self.transaction_runner.run_write(
            _CancelSessionRunsOperation(
                session_id=session_id,
                request=request,
                caller_semantic_digest=caller_semantic_digest,
                event_log_store=self.event_log_store,
                idempotency_store=self.idempotency_store,
                clock=self.clock,
                id_factory=self.id_factory,
            )
        )
        for notice in result.terminal_notices:
            self.terminal_post_commit_port.notify_terminal_post_commit(notice)
        return result

    def closeout_attempt_terminal(
        self, closeout_input: CloseoutAttemptTerminalInput
    ) -> TerminalCloseoutResult:
        """关闭 active Attempt / Run 到 succeeded、failed 或 lost 终态。

        :param closeout_input: internal terminal closeout 输入。
        :returns: terminal closeout 结果，包含 commit 后 exact notice。
        :raises ValueError: 输入为空、终态不匹配或使用 cancellation terminal 时抛出。
        :raises HostApiError: Run/Attempt 缺失或 Phase 3 不支持状态时抛出。
        :raises HostDurableError: durable 写入失败时由底层抛出。
        """

        _validate_closeout_attempt_terminal_input(closeout_input)
        result = self.transaction_runner.run_write(
            _CloseoutAttemptTerminalOperation(
                closeout_input=closeout_input,
                event_log_store=self.event_log_store,
                clock=self.clock,
                id_factory=self.id_factory,
            )
        )
        self.terminal_post_commit_port.notify_terminal_post_commit(
            result.terminal_notice
        )
        catch_up_projection_best_effort(self.projection_catchup_port)
        return TerminalCloseoutResult(
            run=result.run,
            attempt=result.attempt,
            dispatch_record=result.dispatch_record,
            terminal_notice=result.terminal_notice,
        )

def create_host_admission_service(
    transaction_runner: HostTransactionRunner,
    *,
    terminal_post_commit_port: TerminalPostCommitPort,
    payload_store: PayloadStore,
    ordinary_run_baseline: OrdinaryRunExecutionBaseline | None,
    tooling_options: HostToolingOptions | None,
    context_budget_policy: ContextBudgetPolicy | None,
    memory_projection_policy: MemoryProjectionPolicy | None,
    enable_truncation_manager: bool,
    owner_host_instance_id: str | None,
    event_log_store: EventLogStore | None = None,
    idempotency_store: IdempotencyStore | None = None,
    clock: AdmissionClock | None = None,
    id_factory: AdmissionIdFactory | None = None,
    wakeup_port: AdmissionWakeupPort | None = None,
    projection_catchup_port: ProjectionCatchupPort | None = None,
) -> HostAdmissionService:
    """创建默认依赖装配的内部 admission service。

    :param transaction_runner: Host durable write transaction runner。
    :param terminal_post_commit_port: terminal commit 后本地 notice 的显式最终端点。
    :param payload_store: durable payload primitive。
    :param ordinary_run_baseline: ordinary Run 的显式 execution baseline；管理句柄为
        ``None``。
    :param tooling_options: ordinary Run 的显式 tool truth；管理句柄为 ``None``。
    :param context_budget_policy: continuation context budget policy；管理句柄为
        ``None``。
    :param memory_projection_policy: continuation memory projection policy；管理句柄为
        ``None``。
    :param enable_truncation_manager: 是否启用受 Host 治理的 truncation manager。
    :param owner_host_instance_id: 当前 Host owner id；不声明 owner 时为 ``None``。
    :param event_log_store: 可选 EventLog primitive。
    :param idempotency_store: 可选 idempotency primitive。
    :param clock: 可选 clock 端口。
    :param id_factory: 可选 id factory 端口。
    :param wakeup_port: 可选 wakeup 端口。
    :param projection_catchup_port: 可选 projection catch-up 端口。
    :returns: Host admission service。
    """

    return HostAdmissionService(
        transaction_runner=transaction_runner,
        event_log_store=(
            event_log_store if event_log_store is not None else EventLogStore()
        ),
        idempotency_store=(
            idempotency_store if idempotency_store is not None else IdempotencyStore()
        ),
        payload_store=payload_store,
        clock=clock if clock is not None else UtcAdmissionClock(),
        id_factory=id_factory if id_factory is not None else UuidAdmissionIdFactory(),
        wakeup_port=(
            wakeup_port if wakeup_port is not None else NoopAdmissionWakeupPort()
        ),
        terminal_post_commit_port=terminal_post_commit_port,
        projection_catchup_port=(
            projection_catchup_port
            if projection_catchup_port is not None
            else NoopProjectionCatchupPort()
        ),
        ordinary_run_baseline=ordinary_run_baseline,
        tooling_options=tooling_options,
        context_budget_policy=context_budget_policy,
        memory_projection_policy=memory_projection_policy,
        enable_truncation_manager=enable_truncation_manager,
        owner_host_instance_id=owner_host_instance_id,
    )


def _log_run_admission_result(operation: str, result: RunAdmissionResult) -> None:
    """记录 admission 已提交 Run 结果的骨架日志。

    :param operation: admission operation 名称。
    :param result: durable transaction 已提交后的 admission 结果。
    :returns: ``None``。
    """

    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        (
            "host.admission.run_committed operation=%s session_id=%s "
            "run_id=%s run_status=%s attempt_id=%s dispatch_record_id=%s "
            "created=%s queued=%s idempotent_replay=%s pending_dispatch=%s"
        ),
        operation,
        result.run.session_id,
        result.run.run_id,
        result.run.status.value,
        None if result.attempt is None else result.attempt.attempt_id,
        (
            None
            if result.dispatch_record is None
            else result.dispatch_record.dispatch_record_id
        ),
        result.created,
        result.queued,
        result.idempotent_replay,
        result.pending_dispatch is not None,
    )


@dataclass(frozen=True, slots=True)
class _StartRunOperation:
    """start_run transaction body。"""

    request: StartRunRequest
    policy: RunQueuePolicy
    caller_semantic_digest: str
    ordinary_run_baseline: OrdinaryRunExecutionBaseline | None
    tooling_options: HostToolingOptions | None
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory

    def __call__(self, transaction: HostTransaction) -> RunAdmissionResult:
        """执行 start_run admission transaction。

        :param transaction: 当前 Host transaction。
        :returns: Run admission 结果。
        :raises HostApiError: durable precondition 或幂等冲突失败时抛出。
        """

        semantic_digest = _start_run_semantic_digest(
            self.request, caller_semantic_digest=self.caller_semantic_digest
        )
        scope = _idempotency_scope(
            operation=_OPERATION_START_RUN,
            scope_id=self.request.session_id,
            idempotency_key=self.request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            return _idempotent_run_result(transaction, existing)

        _require_open_session(transaction, self.request.session_id)
        active = read_active_run_for_session(transaction, self.request.session_id)
        if active is not None:
            return self._handle_active_run(
                transaction=transaction,
                semantic_digest=semantic_digest,
                scope=scope,
                active=active,
            )
        return _create_accepted_admission_result(
            transaction=transaction,
            event_log_store=self.event_log_store,
            idempotency_store=self.idempotency_store,
            clock=self.clock,
            id_factory=self.id_factory,
            request=self._create_request(),
            semantic_digest=semantic_digest,
            scope=scope,
            queue_policy=self.policy,
        )

    def _handle_active_run(
        self,
        *,
        transaction: HostTransaction,
        semantic_digest: str,
        scope: IdempotencyScope,
        active: RunRow,
    ) -> RunAdmissionResult:
        """处理 start_run 遇到 active Run 的 policy 分支。

        :param transaction: 当前 Host transaction。
        :param semantic_digest: 本次操作 semantic digest。
        :param scope: 幂等 scope。
        :param active: 当前 active Run。
        :returns: admission 结果。
        :raises HostApiError: reject policy 命中 active Run 时抛出 conflict。
        """

        if self.policy == RunQueuePolicy.REJECT:
            raise HostApiError(
                code=HostApiErrorCode.CONFLICT,
                message="Session already has an active Run",
                retryable=False,
            )
        if self.policy == RunQueuePolicy.ATTACH_ACTIVE:
            if active.status == RunStatus.ACCEPTED:
                self.idempotency_store.record_idempotent_result(
                    transaction,
                    scope,
                    semantic_digest,
                    IdempotencyResultRef(
                        result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
                        result_ref=active.run_id,
                        created_event_id=None,
                        created_event_sequence=None,
                    ),
                )
                return RunAdmissionResult(
                    run=active,
                    attempt=None,
                    dispatch_record=None,
                    pending_dispatch=None,
                    created=False,
                    queued=False,
                    attached_active=True,
                    idempotent_replay=False,
                )
            self.idempotency_store.record_idempotent_result(
                transaction,
                scope,
                semantic_digest,
                IdempotencyResultRef(
                    result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
                    result_ref=active.run_id,
                    created_event_id=None,
                    created_event_sequence=None,
                ),
            )
            return RunAdmissionResult(
                run=active,
                attempt=_read_current_attempt(transaction, active),
                dispatch_record=_read_current_dispatch_record(transaction, active),
                pending_dispatch=None,
                created=False,
                queued=False,
                attached_active=True,
                idempotent_replay=False,
            )
        return _create_queued_admission_result(
            transaction=transaction,
            event_log_store=self.event_log_store,
            idempotency_store=self.idempotency_store,
            clock=self.clock,
            id_factory=self.id_factory,
            request=self._create_request(),
            semantic_digest=semantic_digest,
            scope=scope,
            queue_policy=self.policy,
            active_run_id=active.run_id,
        )

    def _create_request(self) -> "_CreateAdmissionRequest":
        """构造带有 admission-time effective facts 的初始 Run 输入。

        :returns: 已冻结 execution/tool facts 的创建输入。
        :raises HostApiError: 当前 handle 不具备 execution baseline 时抛出。
        :raises TypeError: execution baseline 含非法 provider extension 时抛出。
        """

        return _CreateAdmissionRequest.from_start_request(
            self.request,
            effective_facts=_resolve_start_effective_facts(
                baseline=self.ordinary_run_baseline,
                tooling_options=self.tooling_options,
            ),
        )


@dataclass(frozen=True, slots=True)
class _SubmitFollowupQueueOperation:
    """submit_followup(queue) transaction body。"""

    admission_input: SubmitFollowupQueueAdmissionInput
    caller_semantic_digest: str
    ordinary_run_baseline: OrdinaryRunExecutionBaseline | None
    tooling_options: HostToolingOptions | None
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory

    def __call__(self, transaction: HostTransaction) -> RunAdmissionResult:
        """执行 follow-up queue admission transaction。

        :param transaction: 当前 Host transaction。
        :returns: Run admission 结果。
        :raises HostApiError: durable precondition 或幂等冲突失败时抛出。
        """

        request = self.admission_input.request
        semantic_digest = _followup_queue_semantic_digest(
            request, caller_semantic_digest=self.caller_semantic_digest
        )
        scope = _idempotency_scope(
            operation=_OPERATION_SUBMIT_FOLLOWUP_QUEUE,
            scope_id=request.session_id,
            idempotency_key=request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            return _idempotent_run_result(transaction, existing)

        _require_open_session(transaction, request.session_id)
        effective_facts = _resolve_followup_effective_facts(
            request,
            baseline=self.ordinary_run_baseline,
            tooling_options=self.tooling_options,
        )
        active = read_active_run_for_session(transaction, request.session_id)
        create_request = _CreateAdmissionRequest.from_followup_queue_input(
            self.admission_input,
            effective_facts=effective_facts,
        )
        if active is not None:
            return _create_queued_admission_result(
                transaction=transaction,
                event_log_store=self.event_log_store,
                idempotency_store=self.idempotency_store,
                clock=self.clock,
                id_factory=self.id_factory,
                request=create_request,
                semantic_digest=semantic_digest,
                scope=scope,
                queue_policy=RunQueuePolicy.QUEUE,
                active_run_id=active.run_id,
            )
        return _create_accepted_admission_result(
            transaction=transaction,
            event_log_store=self.event_log_store,
            idempotency_store=self.idempotency_store,
            clock=self.clock,
            id_factory=self.id_factory,
            request=create_request,
            semantic_digest=semantic_digest,
            scope=scope,
            queue_policy=RunQueuePolicy.QUEUE,
        )


@dataclass(frozen=True, slots=True)
class _SubmitFollowupSteerOperation:
    """submit_followup(steer) transaction body。"""

    request: SubmitFollowupRequest
    caller_semantic_digest: str
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory
    ordinary_run_baseline: OrdinaryRunExecutionBaseline | None
    tooling_options: HostToolingOptions | None
    payload_store: PayloadStore
    context_budget_policy: ContextBudgetPolicy | None
    memory_projection_policy: MemoryProjectionPolicy | None
    enable_truncation_manager: bool
    owner_host_instance_id: str | None

    def __call__(self, transaction: HostTransaction) -> SteerAdmissionResult:
        """执行 follow-up steer admission transaction。

        :param transaction: 当前 Host transaction。
        :returns: steer admission 结果。
        :raises HostApiError: 目标 Run 前置条件或幂等失败时抛出。
        """

        semantic_digest = _followup_steer_semantic_digest(
            self.request, caller_semantic_digest=self.caller_semantic_digest
        )
        scope = _idempotency_scope(
            operation=_OPERATION_SUBMIT_FOLLOWUP_STEER,
            scope_id=self.request.session_id,
            idempotency_key=self.request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            return _idempotent_steer_result(transaction, existing)
        target_run = _require_steer_target_run(transaction, self.request)
        current_attempt = _require_current_attempt_for_steer(transaction, target_run)
        now = self.clock.now()
        effective_facts = _resolve_followup_effective_facts(
            self.request,
            baseline=self.ordinary_run_baseline,
            tooling_options=self.tooling_options,
        )
        create_request = _CreateAdmissionRequest.from_followup_steer(
            self.request,
            execution_target=target_run.execution_target,
            effective_facts=effective_facts,
        )
        input_event = _append_user_input_event(
            transaction=transaction,
            event_log_store=self.event_log_store,
            request=create_request,
            run_id=target_run.run_id,
            event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
            occurred_at=now,
        )
        steer_event = _append_steer_requested_event(
            transaction=transaction,
            event_log_store=self.event_log_store,
            request=self.request,
            target_run=target_run,
            current_attempt=current_attempt,
            event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
            occurred_at=now,
        )
        if target_run.status == RunStatus.RUNNING:
            steered_event = _append_attempt_steered_event(
                transaction=transaction,
                event_log_store=self.event_log_store,
                request=self.request,
                target_run=target_run,
                current_attempt=current_attempt,
                event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                steer_event=steer_event,
            )
            attempt_result = steer_running_attempt_row(
                transaction,
                attempt_id=current_attempt.attempt_id,
                terminal_event_id=steered_event.event_id,
                terminal_event_sequence=steered_event.event_sequence,
                terminal_at=format_utc_timestamp(now),
            )
            if attempt_result.status != StateMutationStatus.UPDATED:
                raise HostApiError(
                    code=HostApiErrorCode.INVALID_STATE,
                    message="Run terminal race won before steer",
                    retryable=False,
                )
        else:
            wait_result = cancel_active_wait_records_for_run(
                transaction,
                run_id=target_run.run_id,
                updated_event_id=steer_event.event_id,
                updated_event_sequence=steer_event.event_sequence,
                updated_at=format_utc_timestamp(now),
                terminal_at=format_utc_timestamp(now),
            )
            if wait_result.status != StateMutationStatus.UPDATED:
                raise HostApiError(
                    code=HostApiErrorCode.INVALID_STATE,
                    message="WAITING Run has no active wait to steer",
                    retryable=False,
                )
        return _create_steer_attempt_result(
            transaction=transaction,
            event_log_store=self.event_log_store,
            idempotency_store=self.idempotency_store,
            id_factory=self.id_factory,
            request=self.request,
            semantic_digest=semantic_digest,
            scope=scope,
            target_run=target_run,
            previous_attempt=current_attempt,
            input_event=input_event,
            steer_event=steer_event,
            occurred_at=now,
            tooling_options=self.tooling_options,
            payload_store=self.payload_store,
            context_budget_policy=self.context_budget_policy,
            memory_projection_policy=self.memory_projection_policy,
            enable_truncation_manager=self.enable_truncation_manager,
            owner_host_instance_id=self.owner_host_instance_id,
        )


@dataclass(frozen=True, slots=True)
class _RetryRunOperation:
    """retry_run transaction body。"""

    run_id: str
    request: RetryRunRequest
    caller_semantic_digest: str
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory

    def __call__(self, transaction: HostTransaction) -> RunAdmissionResult:
        """执行 retry_run admission transaction。

        :param transaction: 当前 Host transaction。
        :returns: 关联新 Run admission 结果。
        :raises HostApiError: 源 Run 前置条件、幂等或 policy limit 失败时抛出。
        """

        semantic_digest = _retry_run_semantic_digest(
            self.run_id,
            self.request,
            caller_semantic_digest=self.caller_semantic_digest,
        )
        scope = _idempotency_scope(
            operation=_OPERATION_RETRY_RUN,
            scope_id=self.run_id,
            idempotency_key=self.request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            return _idempotent_run_result(transaction, existing)
        source_run = _require_source_run_for_relation(
            transaction,
            run_id=self.run_id,
            expected_status=RunStatus.FAILED,
            operation_name=_OPERATION_RETRY_RUN,
        )
        if (
            count_runs_by_source_relation(
                transaction,
                source_run_id=source_run.run_id,
                source_run_relation=SourceRunRelation.RETRY,
            )
            >= _MAX_ORDINARY_RETRY_RUNS_PER_SOURCE
        ):
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="retry_run policy limit reached for source Run",
                retryable=False,
            )
        source_input_payload = _source_input_payload(
            transaction, self.event_log_store, source_run
        )
        control_event = _append_source_relation_requested_event(
            transaction=transaction,
            event_log_store=self.event_log_store,
            source_run=source_run,
            event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
            event_type=_EVENT_TYPE_RETRY_REQUESTED,
            occurred_at=self.clock.now(),
            actor=self.request.context.actor,
            source=self.request.context.source,
            client_request_id=self.request.client_request_id,
            reason=self.request.reason,
            repair_instruction=None,
        )
        return _create_source_related_admission_result(
            transaction=transaction,
            event_log_store=self.event_log_store,
            idempotency_store=self.idempotency_store,
            clock=self.clock,
            id_factory=self.id_factory,
            request=_CreateAdmissionRequest.from_source_run_retry(
                source_run=source_run,
                request=self.request,
                source_input_payload=source_input_payload,
            ),
            semantic_digest=semantic_digest,
            scope=scope,
            source_run=source_run,
            source_relation=SourceRunRelation.RETRY,
            control_event=control_event,
        )


@dataclass(frozen=True, slots=True)
class _ReplayRunOperation:
    """replay_run transaction body。"""

    run_id: str
    request: ReplayRunRequest
    caller_semantic_digest: str
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory
    ordinary_run_baseline: OrdinaryRunExecutionBaseline | None

    def __call__(self, transaction: HostTransaction) -> RunAdmissionResult:
        """执行 replay_run admission transaction。

        :param transaction: 当前 Host transaction。
        :returns: 关联新 Run admission 结果。
        :raises HostApiError: 源 Run 前置条件或幂等失败时抛出。
        """

        semantic_digest = _replay_run_semantic_digest(
            self.run_id,
            self.request,
            caller_semantic_digest=self.caller_semantic_digest,
        )
        scope = _idempotency_scope(
            operation=_OPERATION_REPLAY_RUN,
            scope_id=self.run_id,
            idempotency_key=self.request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            return _idempotent_run_result(transaction, existing)
        source_run = _require_source_run_for_relation(
            transaction,
            run_id=self.run_id,
            expected_status=RunStatus.SUCCEEDED,
            operation_name=_OPERATION_REPLAY_RUN,
        )
        source_input_payload = _source_input_payload(
            transaction, self.event_log_store, source_run
        )
        control_event = _append_source_relation_requested_event(
            transaction=transaction,
            event_log_store=self.event_log_store,
            source_run=source_run,
            event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
            event_type=_EVENT_TYPE_REPLAY_REQUESTED,
            occurred_at=self.clock.now(),
            actor=self.request.context.actor,
            source=self.request.context.source,
            client_request_id=self.request.client_request_id,
            reason=self.request.reason,
            repair_instruction=self.request.repair_instruction,
        )
        return _create_source_related_admission_result(
            transaction=transaction,
            event_log_store=self.event_log_store,
            idempotency_store=self.idempotency_store,
            clock=self.clock,
            id_factory=self.id_factory,
            request=_CreateAdmissionRequest.from_source_run_replay(
                source_run=source_run,
                request=self.request,
                source_input_payload=source_input_payload,
                baseline=self.ordinary_run_baseline,
            ),
            semantic_digest=semantic_digest,
            scope=scope,
            source_run=source_run,
            source_relation=SourceRunRelation.REPLAY,
            control_event=control_event,
        )


@dataclass(frozen=True, slots=True)
class _CancelRunOperation:
    """cancel_run transaction body。"""

    run_id: str
    request: CancelRunRequest
    caller_semantic_digest: str
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory

    def __call__(self, transaction: HostTransaction) -> _CancelRunOperationResult:
        """执行 cancel_run transaction。

        :param transaction: 当前 Host transaction。
        :returns: 同一 write snapshot 下的 cancel 闭集分类与可选结果；本
            transaction 不执行 promotion。
        :raises HostApiError: Run 缺失、幂等冲突或状态不支持时抛出。
        """

        semantic_digest = _cancel_run_semantic_digest(
            self.request, caller_semantic_digest=self.caller_semantic_digest
        )
        scope = _idempotency_scope(
            operation=_OPERATION_CANCEL_RUN,
            scope_id=self.run_id,
            idempotency_key=self.request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            result = _idempotent_cancel_result(
                transaction,
                existing,
                event_log_store=self.event_log_store,
            )
            return _classified_cancel_result(
                _CancelRunClassification.TERMINAL
                if is_terminal_run_status(result.run.status)
                else _CancelRunClassification.SUPPORTED,
                result,
            )

        run = read_run_by_id(transaction, self.run_id)
        if run is None:
            raise HostApiError(
                code=HostApiErrorCode.NOT_FOUND,
                message="Run not found",
                retryable=False,
            )
        if run.status in (RunStatus.ACCEPTED, RunStatus.QUEUED):
            return _classified_cancel_result(
                _CancelRunClassification.SUPPORTED,
                self._cancel_queued(
                    transaction=transaction,
                    semantic_digest=semantic_digest,
                    scope=scope,
                ),
            )
        if run.status == RunStatus.RUNNING:
            predispatch = self._cancel_predispatch_starting_or_none(
                transaction=transaction,
                semantic_digest=semantic_digest,
                scope=scope,
            )
            if predispatch is not None:
                return _classified_cancel_result(
                    _CancelRunClassification.SUPPORTED,
                    predispatch,
                )
            return self._cancel_active_attempt(
                transaction=transaction,
                semantic_digest=semantic_digest,
                scope=scope,
            )
        if run.status == RunStatus.CANCELLING:
            return self._cancel_active_attempt(
                transaction=transaction,
                semantic_digest=semantic_digest,
                scope=scope,
            )
        if run.status == RunStatus.WAITING:
            return _classified_cancel_result(
                _CancelRunClassification.SUPPORTED,
                self._cancel_waiting(
                    transaction=transaction,
                    semantic_digest=semantic_digest,
                    scope=scope,
                ),
            )
        if run.status == RunStatus.RECOVERING:
            return _classified_cancel_result(
                _CancelRunClassification.SUPPORTED,
                self._cancel_recovering(
                    transaction=transaction,
                    semantic_digest=semantic_digest,
                    scope=scope,
                ),
            )
        if is_terminal_run_status(run.status):
            return _classified_cancel_result(
                _CancelRunClassification.TERMINAL,
                self._record_terminal_cancel_ack(
                    transaction=transaction,
                    run=run,
                    semantic_digest=semantic_digest,
                    scope=scope,
                ),
            )
        return _CancelRunOperationResult(
            classification=_CancelRunClassification.CONFLICT,
            result=None,
        )

    def _cancel_queued(
        self,
        *,
        transaction: HostTransaction,
        semantic_digest: str,
        scope: IdempotencyScope,
    ) -> CancelRunResult:
        """取消 queued Run 并记录幂等结果。

        :param transaction: 当前 Host transaction。
        :param semantic_digest: cancel semantic digest。
        :param scope: 幂等 scope。
        :returns: cancel 结果。
        :raises HostApiError: 状态变化竞争导致不满足 queued 前置条件时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        transition_result = cancel_queued_in_transaction(
            transaction,
            self.event_log_store,
            CancelQueuedRunInput(
                run_id=self.run_id,
                cancel_request_event_id=cancel_request_event_id,
                run_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        _raise_for_cancel_transition_status(transition_result)
        run = _require_transition_run(transition_result.run)
        cancel_request_sequence = _require_event_sequence(
            transaction,
            self.event_log_store,
            cancel_request_event_id,
        )
        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
                result_ref=run.run_id,
                created_event_id=cancel_request_event_id,
                created_event_sequence=cancel_request_sequence,
            ),
        )
        return CancelRunResult(
            run=run,
            attempt=None,
            dispatch_record=None,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                transition_result.run,
                transition_result.run_event,
                wake_queue_promotion=False,
            ),
            active_cancel_target=None,
            idempotent_replay=False,
        )

    def _cancel_predispatch_starting_or_none(
        self,
        *,
        transaction: HostTransaction,
        semantic_digest: str,
        scope: IdempotencyScope,
    ) -> CancelRunResult | None:
        """尝试取消 pre-worker STARTING Attempt 并记录幂等结果。

        :param transaction: 当前 Host transaction。
        :param semantic_digest: cancel semantic digest。
        :param scope: 幂等 scope。
        :returns: direct cancel 结果；当前 Run 不是 pre-worker 时返回 ``None``。
        :raises HostApiError: direct cancel transition 竞争失败时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        transition_result = cancel_predispatch_starting_in_transaction(
            transaction,
            self.event_log_store,
            CancelPredispatchStartingInput(
                run_id=self.run_id,
                cancel_request_event_id=cancel_request_event_id,
                attempt_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                run_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        if transition_result.status == StateMutationStatus.INVALID_STATE:
            return None
        _raise_for_cancel_transition_status(transition_result)
        run = _require_transition_run(transition_result.run)
        cancel_request_sequence = _require_event_sequence(
            transaction,
            self.event_log_store,
            cancel_request_event_id,
        )
        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
                result_ref=run.run_id,
                created_event_id=cancel_request_event_id,
                created_event_sequence=cancel_request_sequence,
            ),
        )
        return CancelRunResult(
            run=run,
            attempt=transition_result.attempt,
            dispatch_record=transition_result.dispatch_record,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                transition_result.run,
                transition_result.run_event,
                wake_queue_promotion=True,
            ),
            active_cancel_target=None,
            idempotent_replay=False,
        )

    def _cancel_recovering(
        self,
        *,
        transaction: HostTransaction,
        semantic_digest: str,
        scope: IdempotencyScope,
    ) -> CancelRunResult:
        """取消 RECOVERING Run 并记录幂等结果。

        :param transaction: 当前 Host transaction。
        :param semantic_digest: cancel semantic digest。
        :param scope: 幂等 scope。
        :returns: cancel 结果；不产生 active worker 传播目标。
        :raises HostApiError: 状态变化竞争导致不满足 recovering 前置条件时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        transition_result = cancel_recovering_run_in_transaction(
            transaction,
            self.event_log_store,
            CancelRecoveringRunInput(
                run_id=self.run_id,
                cancel_request_event_id=cancel_request_event_id,
                run_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        _raise_for_cancel_transition_status(transition_result)
        run = _require_transition_run(transition_result.run)
        cancel_request_sequence = _require_event_sequence(
            transaction,
            self.event_log_store,
            cancel_request_event_id,
        )
        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
                result_ref=run.run_id,
                created_event_id=cancel_request_event_id,
                created_event_sequence=cancel_request_sequence,
            ),
        )
        return CancelRunResult(
            run=run,
            attempt=transition_result.attempt,
            dispatch_record=transition_result.dispatch_record,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                transition_result.run,
                transition_result.run_event,
                wake_queue_promotion=True,
            ),
            active_cancel_target=None,
            idempotent_replay=False,
        )

    def _cancel_active_attempt(
        self,
        *,
        transaction: HostTransaction,
        semantic_digest: str,
        scope: IdempotencyScope,
    ) -> _CancelRunOperationResult:
        """请求取消 active RUNNING Attempt 并记录幂等结果。

        :param transaction: 当前 Host transaction。
        :param semantic_digest: cancel semantic digest。
        :param scope: 幂等 scope。
        :returns: supported 结果，或由当前 transaction snapshot 派生的
            deferred/conflict 分类。
        :raises HostApiError: transition 返回不可恢复的 not-found 时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        transition_result = request_active_attempt_cancel_in_transaction(
            transaction,
            self.event_log_store,
            CancelActiveAttemptInput(
                run_id=self.run_id,
                cancel_request_event_id=cancel_request_event_id,
                run_cancelling_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        if transition_result.status != StateMutationStatus.UPDATED:
            if transition_result.status == StateMutationStatus.NOT_FOUND:
                _raise_for_cancel_transition_status(transition_result)
            return _CancelRunOperationResult(
                classification=(
                    _CancelRunClassification.DEFERRED
                    if transition_result.status == StateMutationStatus.INVALID_STATE
                    and transition_result.run is not None
                    and transition_result.run.status
                    in (RunStatus.RUNNING, RunStatus.CANCELLING)
                    else _CancelRunClassification.CONFLICT
                ),
                result=None,
            )
        run = _require_transition_run(transition_result.run)
        cancel_request_sequence = _require_event_sequence_if_present(
            transaction,
            self.event_log_store,
            cancel_request_event_id,
        )
        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
                result_ref=run.run_id,
                created_event_id=(
                    cancel_request_event_id
                    if cancel_request_sequence is not None
                    else None
                ),
                created_event_sequence=cancel_request_sequence,
            ),
        )
        return _classified_cancel_result(
            _CancelRunClassification.SUPPORTED,
            CancelRunResult(
                run=run,
                attempt=transition_result.attempt,
                dispatch_record=transition_result.dispatch_record,
                terminal_notice=None,
                active_cancel_target=_active_cancel_target_from_transition(
                    run=run,
                    attempt=transition_result.attempt,
                    reason=self.request.reason,
                ),
                idempotent_replay=False,
            ),
        )

    def _cancel_waiting(
        self,
        *,
        transaction: HostTransaction,
        semantic_digest: str,
        scope: IdempotencyScope,
    ) -> CancelRunResult:
        """取消 WAITING Run 并记录幂等结果。

        :param transaction: 当前 Host transaction。
        :param semantic_digest: cancel semantic digest。
        :param scope: 幂等 scope。
        :returns: cancel 结果。
        :raises HostApiError: 当前状态不满足 waiting cancel 前置条件时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        transition_result = cancel_waiting_run_in_transaction(
            transaction,
            self.event_log_store,
            CancelWaitingRunInput(
                run_id=self.run_id,
                cancel_request_event_id=cancel_request_event_id,
                run_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        _raise_for_cancel_transition_status(transition_result)
        run = _require_transition_run(transition_result.run)
        cancel_request_sequence = _require_event_sequence(
            transaction,
            self.event_log_store,
            cancel_request_event_id,
        )
        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
                result_ref=run.run_id,
                created_event_id=cancel_request_event_id,
                created_event_sequence=cancel_request_sequence,
            ),
        )
        return CancelRunResult(
            run=run,
            attempt=transition_result.attempt,
            dispatch_record=transition_result.dispatch_record,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                transition_result.run,
                transition_result.run_event,
                wake_queue_promotion=True,
            ),
            active_cancel_target=None,
            idempotent_replay=False,
        )

    def _record_terminal_cancel_ack(
        self,
        *,
        transaction: HostTransaction,
        run: RunRow,
        semantic_digest: str,
        scope: IdempotencyScope,
    ) -> CancelRunResult:
        """为已终态 Run 记录 cancel 幂等结果并返回当前终态。

        :param transaction: 当前 Host transaction。
        :param run: 已终态 Run row。
        :param semantic_digest: cancel semantic digest。
        :param scope: 幂等 scope。
        :returns: 当前 terminal Run 对应的 cancel 结果。
        """

        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
                result_ref=run.run_id,
                created_event_id=None,
                created_event_sequence=None,
            ),
        )
        confirmation = confirm_terminal_run_in_transaction(
            transaction,
            self.event_log_store,
            run,
        )
        return CancelRunResult(
            run=run,
            attempt=_read_current_attempt(transaction, run),
            dispatch_record=_read_current_dispatch_record(transaction, run),
            terminal_notice=project_terminal_notice_from_exact_run_event(
                confirmation.run,
                confirmation.run_event,
                wake_queue_promotion=False,
            ),
            active_cancel_target=None,
            idempotent_replay=False,
        )


@dataclass(frozen=True, slots=True)
class _SupportedSessionCancelTarget:
    """session-scope cancel 支持子集中的单个目标。"""

    run: RunRow
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None
    active_worker: bool
    waiting: bool
    recovering: bool


@dataclass(frozen=True, slots=True)
class _SessionCancelTargetResult:
    """单个 session-scope cancel target 的 transaction-local 结果。

    :param cancel_request_event_id: 本目标首次 cancel request event id。
    :param terminal_notice: terminal target 的 exact notice；active request 为 ``None``。
    """

    cancel_request_event_id: str
    terminal_notice: TerminalPostCommitNotice | None


@dataclass(frozen=True, slots=True)
class _CancelSessionRunsOperation:
    """cancel_session_runs transaction body。"""

    session_id: str
    request: CancelSessionRunsRequest
    caller_semantic_digest: str
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory

    def __call__(self, transaction: HostTransaction) -> SessionCancelResult:
        """执行 session-scope cancel transaction。

        :param transaction: 当前 Host transaction。
        :returns: session-scope cancel 结果。
        :raises HostApiError: Session 缺失、幂等冲突或存在 unsupported non-terminal Run 时抛出。
        """

        semantic_digest = _cancel_session_runs_semantic_digest(
            self.session_id,
            self.request,
            caller_semantic_digest=self.caller_semantic_digest,
        )
        scope = _idempotency_scope(
            operation=_OPERATION_CANCEL_SESSION_RUNS,
            scope_id=self.session_id,
            idempotency_key=self.request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            return _idempotent_session_cancel_result(
                transaction,
                existing,
                event_log_store=self.event_log_store,
                reason=self.request.reason,
            )

        session = _require_existing_session(transaction, self.session_id)
        targets = self._read_supported_targets_or_raise(transaction)
        first_cancel_event_id: str | None = None
        first_cancel_event_sequence: int | None = None
        first_active_cancel_event_id: str | None = None
        first_active_cancel_event_sequence: int | None = None
        active_cancel_targets: list[ActiveCancelTarget] = []
        terminal_notices: list[TerminalPostCommitNotice] = []
        for target in targets:
            target_result = self._cancel_target(transaction, target)
            cancel_event_id = target_result.cancel_request_event_id
            cancel_event_sequence = _require_event_sequence_if_present(
                transaction,
                self.event_log_store,
                cancel_event_id,
            )
            if first_cancel_event_id is None and cancel_event_sequence is not None:
                first_cancel_event_id = cancel_event_id
                first_cancel_event_sequence = cancel_event_sequence
            if (
                target.active_worker
                and first_active_cancel_event_id is None
                and cancel_event_sequence is not None
            ):
                first_active_cancel_event_id = cancel_event_id
                first_active_cancel_event_sequence = cancel_event_sequence
            active_cancel_target = _active_cancel_target_for_session_target(
                target=target,
                reason=self.request.reason,
            )
            if active_cancel_target is not None:
                active_cancel_targets.append(active_cancel_target)
            if target_result.terminal_notice is not None:
                terminal_notices.append(target_result.terminal_notice)
        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_SESSION,
                result_ref=self.session_id,
                created_event_id=(
                    first_active_cancel_event_id
                    if first_active_cancel_event_id is not None
                    else first_cancel_event_id
                ),
                created_event_sequence=(
                    first_active_cancel_event_sequence
                    if first_active_cancel_event_sequence is not None
                    else first_cancel_event_sequence
                ),
            ),
        )
        return SessionCancelResult(
            snapshot=session_snapshot_from_rows(
                transaction,
                session,
                read_session_slot_by_session_id(transaction, self.session_id),
            ),
            active_cancel_targets=tuple(active_cancel_targets),
            idempotent_replay=False,
            cancelled_run_count=len(targets),
            terminal_notices=tuple(
                sorted(
                    terminal_notices,
                    key=lambda notice: notice.terminal_event_sequence,
                )
            ),
        )

    def _read_supported_targets_or_raise(
        self, transaction: HostTransaction
    ) -> tuple[_SupportedSessionCancelTarget, ...]:
        """读取并校验本次 session-scope cancel 的全部支持目标。

        :param transaction: 当前 Host transaction。
        :returns: 支持取消的目标元组。
        :raises HostApiError: 存在当前不支持的非终态 Run 时抛出。
        """

        targets: list[_SupportedSessionCancelTarget] = []
        for run in read_non_terminal_runs_for_session(transaction, self.session_id):
            target = _session_cancel_target_for_run(transaction, run)
            if target is None:
                raise HostApiError(
                    code=HostApiErrorCode.UNSUPPORTED_OPERATION,
                    message=(
                        "cancel_session_runs supports only queued, pre-dispatch "
                        "STARTING, active worker, WAITING, and RECOVERING Runs in the "
                        "current Host cancel scope"
                    ),
                    retryable=False,
                )
            targets.append(target)
        return tuple(targets)

    def _cancel_target(
        self, transaction: HostTransaction, target: _SupportedSessionCancelTarget
    ) -> _SessionCancelTargetResult:
        """取消一个已校验支持的 session-scope cancel 目标。

        :param transaction: 当前 Host transaction。
        :param target: 已校验的取消目标。
        :returns: 本目标 cancel request id 与可选 exact terminal notice。
        :raises HostApiError: 低层 transition 失败时抛出。
        """

        if target.run.status in (RunStatus.ACCEPTED, RunStatus.QUEUED):
            return self._cancel_queued_target(transaction, target.run)
        if target.waiting:
            return self._cancel_waiting_target(transaction, target.run)
        if target.recovering:
            return self._cancel_recovering_target(transaction, target.run)
        if target.active_worker:
            return self._cancel_active_target(transaction, target.run)
        return self._cancel_predispatch_target(transaction, target.run)

    def _cancel_queued_target(
        self,
        transaction: HostTransaction,
        run: RunRow,
    ) -> _SessionCancelTargetResult:
        """取消一个 queued Run。

        :param transaction: 当前 Host transaction。
        :param run: 已校验为 queued 的 Run。
        :returns: cancel request id 与 flag=false terminal notice。
        :raises HostApiError: transition 失败时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        result = cancel_queued_in_transaction(
            transaction,
            self.event_log_store,
            CancelQueuedRunInput(
                run_id=run.run_id,
                cancel_request_event_id=cancel_request_event_id,
                run_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        _raise_for_session_cancel_transition_status(result)
        return _SessionCancelTargetResult(
            cancel_request_event_id=cancel_request_event_id,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=False,
            ),
        )

    def _cancel_predispatch_target(
        self, transaction: HostTransaction, run: RunRow
    ) -> _SessionCancelTargetResult:
        """取消一个 pre-dispatch STARTING Run。

        :param transaction: 当前 Host transaction。
        :param run: 已校验为 pre-dispatch STARTING 的 Run。
        :returns: cancel request id 与 flag=false terminal notice。
        :raises HostApiError: transition 失败时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        result = cancel_predispatch_starting_in_transaction(
            transaction,
            self.event_log_store,
            CancelPredispatchStartingInput(
                run_id=run.run_id,
                cancel_request_event_id=cancel_request_event_id,
                attempt_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                run_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        _raise_for_session_cancel_transition_status(result)
        return _SessionCancelTargetResult(
            cancel_request_event_id=cancel_request_event_id,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=False,
            ),
        )

    def _cancel_active_target(
        self,
        transaction: HostTransaction,
        run: RunRow,
    ) -> _SessionCancelTargetResult:
        """请求取消一个 active worker Run。

        :param transaction: 当前 Host transaction。
        :param run: 已校验为 active worker 的 Run。
        :returns: cancel request id；active request 不产生 terminal notice。
        :raises HostApiError: transition 失败时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        result = request_active_attempt_cancel_in_transaction(
            transaction,
            self.event_log_store,
            CancelActiveAttemptInput(
                run_id=run.run_id,
                cancel_request_event_id=cancel_request_event_id,
                run_cancelling_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        _raise_for_session_cancel_transition_status(result)
        return _SessionCancelTargetResult(
            cancel_request_event_id=cancel_request_event_id,
            terminal_notice=None,
        )

    def _cancel_waiting_target(
        self,
        transaction: HostTransaction,
        run: RunRow,
    ) -> _SessionCancelTargetResult:
        """取消一个 WAITING Run。

        :param transaction: 当前 Host transaction。
        :param run: 已校验为 WAITING 的 Run。
        :returns: cancel request id 与 flag=false terminal notice。
        :raises HostApiError: transition 失败时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        result = cancel_waiting_run_in_transaction(
            transaction,
            self.event_log_store,
            CancelWaitingRunInput(
                run_id=run.run_id,
                cancel_request_event_id=cancel_request_event_id,
                run_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        _raise_for_session_cancel_transition_status(result)
        return _SessionCancelTargetResult(
            cancel_request_event_id=cancel_request_event_id,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=False,
            ),
        )

    def _cancel_recovering_target(
        self, transaction: HostTransaction, run: RunRow
    ) -> _SessionCancelTargetResult:
        """取消一个 RECOVERING Run。

        :param transaction: 当前 Host transaction。
        :param run: 已校验为 RECOVERING 的 Run。
        :returns: cancel request id 与 flag=false terminal notice。
        :raises HostApiError: transition 失败时抛出。
        """

        now = self.clock.now()
        cancel_request_event_id = self.id_factory.new_id(_EVENT_ID_PREFIX)
        result = cancel_recovering_run_in_transaction(
            transaction,
            self.event_log_store,
            CancelRecoveringRunInput(
                run_id=run.run_id,
                cancel_request_event_id=cancel_request_event_id,
                run_cancelled_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                mode=self.request.mode,
                call_context_digest=_call_context_digest(self.request.context),
            ),
        )
        _raise_for_session_cancel_transition_status(result)
        return _SessionCancelTargetResult(
            cancel_request_event_id=cancel_request_event_id,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=False,
            ),
        )


@dataclass(frozen=True, slots=True)
class _TerminalCloseoutTransactionResult:
    """terminal closeout transaction 内部结果。

    :param run: 已提交终态 Run row。
    :param attempt: 已提交终态 Attempt row。
    :param dispatch_record: 当前 Attempt dispatch row。
    :param terminal_notice: exact terminal row 派生的 commit 后 notice。
    """

    run: RunRow
    attempt: AttemptRow
    dispatch_record: DispatchRecordRow | None
    terminal_notice: TerminalPostCommitNotice


@dataclass(frozen=True, slots=True)
class _CloseoutAttemptTerminalOperation:
    """closeout_attempt_terminal transaction body。"""

    closeout_input: CloseoutAttemptTerminalInput
    event_log_store: EventLogStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory

    def __call__(
        self, transaction: HostTransaction
    ) -> _TerminalCloseoutTransactionResult:
        """执行 terminal closeout transaction。

        :param transaction: 当前 Host transaction。
        :returns: transaction 内部 closeout 结果；promotion 由 commit 后外层执行。
        :raises HostApiError: Run/Attempt 缺失或状态不支持时抛出。
        """

        transition_result = terminal_closeout_in_transaction(
            transaction,
            self.event_log_store,
            TerminalCloseoutInput(
                run_id=self.closeout_input.run_id,
                attempt_id=self.closeout_input.attempt_id,
                attempt_terminal_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                run_terminal_event_id=self.id_factory.new_id(_EVENT_ID_PREFIX),
                attempt_terminal_status=self.closeout_input.attempt_terminal_status,
                run_terminal_status=self.closeout_input.run_terminal_status,
                occurred_at=self.clock.now(),
                actor=_INTERNAL_ACTOR,
                source=_EVENT_SOURCE,
                reason=_TERMINAL_CLOSEOUT_REASON,
                terminal_summary_ref=self.closeout_input.terminal_summary_ref,
                terminal_summary_digest=self.closeout_input.terminal_summary_digest,
            ),
        )
        _raise_for_terminal_transition_status(transition_result)
        run = _require_transition_run(transition_result.run)
        if transition_result.attempt is None:
            raise HostApiError(
                code=HostApiErrorCode.INTERNAL_ERROR,
                message="Terminal closeout returned no Attempt",
                retryable=False,
            )
        return _TerminalCloseoutTransactionResult(
            run=run,
            attempt=transition_result.attempt,
            dispatch_record=transition_result.dispatch_record,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                transition_result.run,
                transition_result.run_event,
                wake_queue_promotion=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class _CreateAdmissionRequest:
    """创建 Run admission state 所需的归一化输入。"""

    session_id: str
    client_request_id: str
    input: HostInput
    system_prompt: str | None
    execution_target: str
    actor: str
    source: str
    call_context_digest: str
    operation_kind: str
    effective_execution_config: JsonValue | None
    effective_tool_set: JsonValue | None

    @classmethod
    def from_start_request(
        cls,
        request: StartRunRequest,
        *,
        effective_facts: _ResolvedFollowupEffectiveFacts,
    ) -> "_CreateAdmissionRequest":
        """从 start_run request 构造归一化创建输入。

        :param request: start_run request。
        :param effective_facts: admission-time 冻结的 execution/tool facts。
        :returns: 归一化创建输入。
        """

        return cls(
            session_id=request.session_id,
            client_request_id=request.client_request_id,
            input=request.input,
            system_prompt=None,
            execution_target=request.execution_target,
            actor=request.context.actor,
            source=request.context.source,
            call_context_digest=_call_context_digest(request.context),
            operation_kind=_OPERATION_START_RUN,
            effective_execution_config=effective_facts.effective_execution_config,
            effective_tool_set=effective_facts.effective_tool_set,
        )

    @classmethod
    def from_followup_queue_input(
        cls,
        admission_input: SubmitFollowupQueueAdmissionInput,
        *,
        effective_facts: _ResolvedFollowupEffectiveFacts,
    ) -> "_CreateAdmissionRequest":
        """从 follow-up queue input 构造归一化创建输入。

        :param admission_input: follow-up queue admission 输入。
        :returns: 归一化创建输入。
        """

        request = admission_input.request
        return cls(
            session_id=request.session_id,
            client_request_id=request.client_request_id,
            input=HostInput(
                display_text=request.user_prompt,
                payload_ref=None,
                payload_digest=None,
            ),
            system_prompt=request.system_prompt,
            execution_target=admission_input.resolved_execution_target,
            actor=request.context.actor,
            source=request.context.source,
            call_context_digest=_call_context_digest(request.context),
            operation_kind=_OPERATION_SUBMIT_FOLLOWUP_QUEUE,
            effective_execution_config=effective_facts.effective_execution_config,
            effective_tool_set=effective_facts.effective_tool_set,
        )

    @classmethod
    def from_followup_steer(
        cls,
        request: SubmitFollowupRequest,
        *,
        execution_target: str,
        effective_facts: _ResolvedFollowupEffectiveFacts,
    ) -> "_CreateAdmissionRequest":
        """从 follow-up steer request 构造归一化输入。

        :param request: follow-up steer request。
        :param execution_target: 目标 Run 已冻结执行目标。
        :param effective_facts: 已解析的 execution / tool 冻结事实。
        :returns: 归一化创建输入。
        """

        return cls(
            session_id=request.session_id,
            client_request_id=request.client_request_id,
            input=HostInput(
                display_text=request.user_prompt,
                payload_ref=None,
                payload_digest=None,
            ),
            system_prompt=request.system_prompt,
            execution_target=execution_target,
            actor=request.context.actor,
            source=request.context.source,
            call_context_digest=_call_context_digest(request.context),
            operation_kind=_OPERATION_SUBMIT_FOLLOWUP_STEER,
            effective_execution_config=effective_facts.effective_execution_config,
            effective_tool_set=effective_facts.effective_tool_set,
        )

    @classmethod
    def from_source_run_retry(
        cls,
        *,
        source_run: RunRow,
        request: RetryRunRequest,
        source_input_payload: JsonValue,
    ) -> "_CreateAdmissionRequest":
        """从源 Run 与 retry 请求构造关联新 Run 创建输入。

        :param source_run: 已校验的 FAILED 源 Run。
        :param request: retry run 请求。
        :param source_input_payload: 源 Run ``USER_INPUT_ACCEPTED`` payload。
        :returns: 归一化创建输入。
        """

        payload = _require_payload_mapping(source_input_payload)
        return cls(
            session_id=source_run.session_id,
            client_request_id=request.client_request_id,
            input=HostInput(
                display_text=_required_payload_text(payload, "display_text"),
                payload_ref=None,
                payload_digest=None,
            ),
            system_prompt=_optional_payload_text(payload, "system_prompt"),
            execution_target=source_run.execution_target,
            actor=request.context.actor,
            source=request.context.source,
            call_context_digest=_call_context_digest(request.context),
            operation_kind=_OPERATION_RETRY_RUN,
            effective_execution_config=payload.get("effective_execution_config"),
            effective_tool_set=payload.get("effective_tool_set"),
        )

    @classmethod
    def from_source_run_replay(
        cls,
        *,
        source_run: RunRow,
        request: ReplayRunRequest,
        source_input_payload: JsonValue,
        baseline: OrdinaryRunExecutionBaseline | None,
    ) -> "_CreateAdmissionRequest":
        """从源 Run 与 replay 请求构造 no-tool 结构修复创建输入。

        :param source_run: 已校验的 SUCCEEDED 源 Run。
        :param request: replay run 请求。
        :param source_input_payload: 源 Run ``USER_INPUT_ACCEPTED`` payload。
        :param baseline: opener ordinary Run baseline；源 Run 缺少冻结配置时使用。
        :returns: 归一化创建输入。
        :raises HostApiError: 无法取得 replay execution baseline 时抛出。
        """

        payload = _require_payload_mapping(source_input_payload)
        return cls(
            session_id=source_run.session_id,
            client_request_id=request.client_request_id,
            input=HostInput(
                display_text=request.repair_instruction,
                payload_ref=None,
                payload_digest=None,
            ),
            system_prompt=_optional_payload_text(payload, "system_prompt"),
            execution_target=source_run.execution_target,
            actor=request.context.actor,
            source=request.context.source,
            call_context_digest=_call_context_digest(request.context),
            operation_kind=_OPERATION_REPLAY_RUN,
            effective_execution_config=_replay_effective_execution_config(
                payload.get("effective_execution_config"),
                baseline=baseline,
            ),
            effective_tool_set=effective_tool_facts_json(
                frozenset(),
                tooling_options=None,
            ),
        )


def _create_accepted_admission_result(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    idempotency_store: IdempotencyStore,
    clock: AdmissionClock,
    id_factory: AdmissionIdFactory,
    request: _CreateAdmissionRequest,
    semantic_digest: str,
    scope: IdempotencyScope,
    queue_policy: RunQueuePolicy,
) -> RunAdmissionResult:
    """创建 pre-start accepted Run admission 结果。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param idempotency_store: idempotency primitive。
    :param clock: admission clock。
    :param id_factory: admission id factory。
    :param request: 归一化创建输入。
    :param semantic_digest: semantic input digest。
    :param scope: 幂等 scope。
    :param queue_policy: 持久化 queue policy。
    :returns: admission 结果。
    """

    now = clock.now()
    run_id = id_factory.new_id(_RUN_ID_PREFIX)
    input_event = _append_user_input_event(
        transaction=transaction,
        event_log_store=event_log_store,
        request=request,
        run_id=run_id,
        event_id=id_factory.new_id(_EVENT_ID_PREFIX),
        occurred_at=now,
    )
    transition_result = create_accepted_run_in_transaction(
        transaction,
        event_log_store,
        CreateAcceptedRunInput(
            session_id=request.session_id,
            run_id=run_id,
            client_request_id=request.client_request_id,
            input_event_id=input_event.event_id,
            input_event_sequence=input_event.event_sequence,
            run_accepted_event_id=id_factory.new_id(_EVENT_ID_PREFIX),
            occurred_at=now,
            actor=request.actor,
            source=request.source,
            idempotency_key=request.client_request_id,
            execution_target=request.execution_target,
            queue_policy=queue_policy,
            call_context_digest=request.call_context_digest,
        ),
    )
    run = _require_transition_run(transition_result.run)
    idempotency_store.record_idempotent_result(
        transaction,
        scope,
        semantic_digest,
        IdempotencyResultRef(
            result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
            result_ref=run.run_id,
            created_event_id=input_event.event_id,
            created_event_sequence=input_event.event_sequence,
        ),
    )
    return RunAdmissionResult(
        run=run,
        attempt=None,
        dispatch_record=None,
        pending_dispatch=None,
        created=True,
        queued=False,
        attached_active=False,
        idempotent_replay=False,
    )


def _create_queued_admission_result(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    idempotency_store: IdempotencyStore,
    clock: AdmissionClock,
    id_factory: AdmissionIdFactory,
    request: _CreateAdmissionRequest,
    semantic_digest: str,
    scope: IdempotencyScope,
    queue_policy: RunQueuePolicy,
    active_run_id: str,
) -> RunAdmissionResult:
    """创建 queued Run admission 结果。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param idempotency_store: idempotency primitive。
    :param clock: admission clock。
    :param id_factory: admission id factory。
    :param request: 归一化创建输入。
    :param semantic_digest: semantic input digest。
    :param scope: 幂等 scope。
    :param queue_policy: 持久化 queue policy。
    :param active_run_id: admission 时存在的 active Run id。
    :returns: admission 结果。
    """

    now = clock.now()
    run_id = id_factory.new_id(_RUN_ID_PREFIX)
    input_event = _append_user_input_event(
        transaction=transaction,
        event_log_store=event_log_store,
        request=request,
        run_id=run_id,
        event_id=id_factory.new_id(_EVENT_ID_PREFIX),
        occurred_at=now,
    )
    transition_result = create_queued_run_in_transaction(
        transaction,
        event_log_store,
        CreateQueuedRunInput(
            session_id=request.session_id,
            run_id=run_id,
            client_request_id=request.client_request_id,
            input_event_id=input_event.event_id,
            input_event_sequence=input_event.event_sequence,
            run_accepted_event_id=id_factory.new_id(_EVENT_ID_PREFIX),
            run_queued_event_id=id_factory.new_id(_EVENT_ID_PREFIX),
            occurred_at=now,
            actor=request.actor,
            source=request.source,
            idempotency_key=request.client_request_id,
            execution_target=request.execution_target,
            queue_policy=queue_policy,
            queue_reason=_QUEUE_REASON_ACTIVE_RUN_EXISTS,
            active_run_id=active_run_id,
            call_context_digest=request.call_context_digest,
        ),
    )
    run = _require_transition_run(transition_result.run)
    idempotency_store.record_idempotent_result(
        transaction,
        scope,
        semantic_digest,
        IdempotencyResultRef(
            result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
            result_ref=run.run_id,
            created_event_id=input_event.event_id,
            created_event_sequence=input_event.event_sequence,
        ),
    )
    return RunAdmissionResult(
        run=run,
        attempt=None,
        dispatch_record=None,
        pending_dispatch=None,
        created=True,
        queued=True,
        attached_active=False,
        idempotent_replay=False,
    )


def _create_source_related_admission_result(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    idempotency_store: IdempotencyStore,
    clock: AdmissionClock,
    id_factory: AdmissionIdFactory,
    request: _CreateAdmissionRequest,
    semantic_digest: str,
    scope: IdempotencyScope,
    source_run: RunRow,
    source_relation: SourceRunRelation,
    control_event: EventLogRow,
) -> RunAdmissionResult:
    """创建 retry / replay 关联新 Run 并写入源关系。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param idempotency_store: idempotency primitive。
    :param clock: admission clock。
    :param id_factory: admission id factory。
    :param request: 归一化创建输入。
    :param semantic_digest: semantic input digest。
    :param scope: 幂等 scope。
    :param source_run: 源 Run row。
    :param source_relation: retry 或 replay 源关系。
    :param control_event: 已追加的控制请求事件。
    :returns: admission 结果。
    :raises HostApiError: 源关系写入 CAS 失败时抛出。
    """

    active = read_active_run_for_session(transaction, request.session_id)
    result = (
        _create_queued_admission_result(
            transaction=transaction,
            event_log_store=event_log_store,
            idempotency_store=idempotency_store,
            clock=clock,
            id_factory=id_factory,
            request=request,
            semantic_digest=semantic_digest,
            scope=scope,
            queue_policy=RunQueuePolicy.QUEUE,
            active_run_id=active.run_id,
        )
        if active is not None
        else _create_accepted_admission_result(
            transaction=transaction,
            event_log_store=event_log_store,
            idempotency_store=idempotency_store,
            clock=clock,
            id_factory=id_factory,
            request=request,
            semantic_digest=semantic_digest,
            scope=scope,
            queue_policy=RunQueuePolicy.QUEUE,
        )
    )
    relation_result = set_new_run_source_relation_row(
        transaction,
        run_id=result.run.run_id,
        expected_status=result.run.status,
        source_run_id=source_run.run_id,
        source_run_relation=source_relation,
        updated_at=format_utc_timestamp(clock.now()),
    )
    if relation_result.status != StateMutationStatus.UPDATED:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="related Run source relation was not recorded",
            retryable=False,
        )
    updated_run = _require_transition_run(relation_result.row)
    return RunAdmissionResult(
        run=updated_run,
        attempt=result.attempt,
        dispatch_record=result.dispatch_record,
        pending_dispatch=result.pending_dispatch,
        created=result.created,
        queued=result.queued,
        attached_active=result.attached_active,
        idempotent_replay=result.idempotent_replay,
    )


def _create_steer_attempt_result(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    idempotency_store: IdempotencyStore,
    id_factory: AdmissionIdFactory,
    request: SubmitFollowupRequest,
    semantic_digest: str,
    scope: IdempotencyScope,
    target_run: RunRow,
    previous_attempt: AttemptRow,
    input_event: EventLogRow,
    steer_event: EventLogRow,
    occurred_at: datetime,
    tooling_options: HostToolingOptions | None,
    payload_store: PayloadStore,
    context_budget_policy: ContextBudgetPolicy | None,
    memory_projection_policy: MemoryProjectionPolicy | None,
    enable_truncation_manager: bool,
    owner_host_instance_id: str | None,
) -> SteerAdmissionResult:
    """创建 steer 新 Attempt、切换 Run 并记录幂等结果。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param idempotency_store: idempotency primitive。
    :param id_factory: admission id factory。
    :param request: steer 请求。
    :param semantic_digest: semantic input digest。
    :param scope: 幂等 scope。
    :param target_run: steer 目标 Run。
    :param previous_attempt: 旧 current Attempt。
    :param input_event: 新 steer 输入事件。
    :param steer_event: ``STEER_REQUESTED`` 事件。
    :param occurred_at: 事件发生时间。
    :param tooling_options: construction-time tool truth。
    :param payload_store: manifest payload primitive。
    :param context_budget_policy: 当前 Host context policy；不可用时为 ``None``。
    :param memory_projection_policy: candidate memory policy。
    :param enable_truncation_manager: framework truncation tool 是否启用。
    :param owner_host_instance_id: 新 dispatch owner Host instance id。
    :returns: steer admission 结果。
    :raises HostApiError: Run 切换 CAS 失败时抛出。
    """

    attempt_id = id_factory.new_id(_ATTEMPT_ID_PREFIX)
    execution_id = id_factory.new_id(_EXECUTION_ID_PREFIX)
    dispatch_record_id = id_factory.new_id(_DISPATCH_RECORD_ID_PREFIX)
    if memory_projection_policy is None:
        raise HostDurableError(
            "steer memory projection policy is unavailable"
        )
    policy_snapshot, tool_schemas, disable_tools, execution_mode = (
        _strict_steer_candidate_inputs(
            transaction=transaction,
            input_event=input_event,
            tooling_options=tooling_options,
            enable_truncation_manager=enable_truncation_manager,
            replay=target_run.source_run_relation is SourceRunRelation.REPLAY,
        )
    )
    load_prepared_runner_call_source_in_transaction(
        transaction,
        event_log_store,
        run_id=target_run.run_id,
        attempt_id=previous_attempt.attempt_id,
        execution_id=previous_attempt.execution_id,
    )
    candidate = prepare_runner_call_candidate_in_transaction(
        transaction,
        event_log_store,
        run=target_run,
        current_input_event=input_event,
        continuity=SessionContinuityView(
            messages=(),
            source_refs=(),
        ),
        policy_snapshot=policy_snapshot,
        tool_schemas=tool_schemas,
        disable_tools=disable_tools,
        tool_execution_mode=execution_mode,
        memory_projection_policy=memory_projection_policy,
    )
    sizing: ContextSizingResult | None = None
    if context_budget_policy is None:
        sizing_snapshot = unavailable_runner_call_sizing_snapshot(
            RunnerCallSizingUnavailableReason.CONTEXT_POLICY_UNAVAILABLE,
            sizing_stage=ContextSizingStage.CONTINUATION,
        )
    else:
        estimate = estimate_prepared_runner_call_candidate(
            candidate,
            context_budget_policy,
        )
        sizing = build_conservative_context_sizing_result(
            stage=ContextSizingStage.CONTINUATION,
            candidate_input_cursor=candidate.candidate_input_cursor,
            candidate_input_projection_ref=(
                candidate.candidate_input_projection_ref
            ),
            candidate_input_digest=candidate.input_snapshot_digest,
            policy=context_budget_policy,
            estimate=estimate,
        )
        sizing_snapshot = complete_runner_call_sizing_snapshot(
            sizing_stage=sizing.stage,
            estimator_id=sizing.estimator_contract.estimator_id,
            estimator_version=sizing.estimator_contract.estimator_version,
            estimator_digest=sizing.estimator_digest,
            conservative_input_tokens=sizing.conservative_input_tokens,
            context_window_size=sizing.context_window_size,
            provider=candidate.policy_snapshot.runner_spec.provider,
            model=candidate.policy_snapshot.runner_spec.model,
            request_semantics_digest=candidate.request_semantics_digest,
            input_snapshot_digest=candidate.input_snapshot_digest,
            policy_ref=sizing.policy_ref,
            policy_snapshot_digest=sizing.policy_snapshot_digest,
        )
    manifest_event = record_prepared_runner_call_candidate_in_transaction(
        transaction,
        event_log_store,
        payload_store,
        run=target_run,
        attempt_id=attempt_id,
        execution_id=execution_id,
        occurred_at=occurred_at,
        candidate=candidate,
        sizing_snapshot=sizing_snapshot,
    )
    if sizing is not None:
        sizing = build_conservative_context_sizing_result_from_atoms(
            stage=ContextSizingStage.CONTINUATION,
            candidate_input_cursor=manifest_event.event_sequence,
            candidate_input_projection_ref=(
                sizing.candidate_input_projection_ref
            ),
            candidate_input_digest=sizing.candidate_input_digest,
            estimator_contract=sizing.estimator_contract,
            estimator_digest=sizing.estimator_digest,
            conservative_input_tokens=sizing.conservative_input_tokens,
            context_window_size=sizing.context_window_size,
            soft_threshold_tokens=sizing.soft_threshold_tokens,
            hard_threshold_tokens=sizing.hard_threshold_tokens,
            policy_ref=sizing.policy_ref,
            policy_snapshot_digest=sizing.policy_snapshot_digest,
            fallback_reason=sizing.fallback_reason,
        )
        append_context_budget_evaluated_in_transaction(
            transaction,
            event_log_store,
            session_id=target_run.session_id,
            run_id=target_run.run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            occurred_at=occurred_at,
            result=sizing,
        )
    run_started_event = _append_steer_run_started_event(
        transaction=transaction,
        event_log_store=event_log_store,
        request=request,
        target_run=target_run,
        attempt_id=attempt_id,
        dispatch_record_id=dispatch_record_id,
        event_id=id_factory.new_id(_EVENT_ID_PREFIX),
        occurred_at=occurred_at,
        steer_event=steer_event,
    )
    attempt_started_event = _append_steer_attempt_started_event(
        transaction=transaction,
        event_log_store=event_log_store,
        request=request,
        target_run=target_run,
        attempt_id=attempt_id,
        execution_id=execution_id,
        event_id=id_factory.new_id(_EVENT_ID_PREFIX),
        occurred_at=occurred_at,
        steer_event=steer_event,
    )
    timestamp = format_utc_timestamp(occurred_at)
    attempt = AttemptRow(
        attempt_id=attempt_id,
        run_id=target_run.run_id,
        execution_id=execution_id,
        status=AttemptStatus.STARTING,
        started_event_id=attempt_started_event.event_id,
        started_event_sequence=attempt_started_event.event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=timestamp,
        updated_at=timestamp,
        terminal_at=None,
    )
    dispatch_record = DispatchRecordRow(
        dispatch_record_id=dispatch_record_id,
        run_id=target_run.run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=WorkerKind.LOCAL,
        execution_target=target_run.execution_target,
        owner_host_instance_id=owner_host_instance_id,
        created_event_id=attempt_started_event.event_id,
        created_event_sequence=attempt_started_event.event_sequence,
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
        created_at=timestamp,
        updated_at=timestamp,
        cancelled_at=None,
    )
    insert_attempt(transaction, attempt)
    run_result = steer_active_run_row(
        transaction,
        session_id=target_run.session_id,
        run_id=target_run.run_id,
        previous_attempt_id=previous_attempt.attempt_id,
        next_attempt_id=attempt_id,
        input_event_id=input_event.event_id,
        input_event_sequence=input_event.event_sequence,
        started_event_id=run_started_event.event_id,
        started_event_sequence=run_started_event.event_sequence,
        updated_at=timestamp,
    )
    if run_result.status != StateMutationStatus.UPDATED:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="Run terminal race won before steer",
            retryable=False,
        )
    insert_dispatch_record(transaction, dispatch_record)
    idempotency_store.record_idempotent_result(
        transaction,
        scope,
        semantic_digest,
        IdempotencyResultRef(
            result_kind=_IDEMPOTENCY_RESULT_KIND_RUN,
            result_ref=target_run.run_id,
            created_event_id=input_event.event_id,
            created_event_sequence=input_event.event_sequence,
        ),
    )
    updated_run = _require_transition_run(run_result.row)
    stored_dispatch = _read_current_dispatch_record(transaction, updated_run)
    if stored_dispatch is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Steer Run current dispatch record is missing",
            retryable=False,
        )
    return SteerAdmissionResult(
        run=updated_run,
        attempt=_read_current_attempt(transaction, updated_run),
        dispatch_record=stored_dispatch,
        pending_dispatch=_pending_dispatch_from_row(stored_dispatch),
        steered_cancel_target=(
            ActiveCancelTarget(
                run_id=target_run.run_id,
                attempt_id=previous_attempt.attempt_id,
                execution_id=previous_attempt.execution_id,
                reason="steered",
            )
            if previous_attempt.status == AttemptStatus.RUNNING
            else None
        ),
        input_event_id=input_event.event_id,
        idempotent_replay=False,
    )


def _strict_steer_candidate_inputs(
    *,
    transaction: HostTransaction,
    input_event: EventLogRow,
    tooling_options: HostToolingOptions | None,
    enable_truncation_manager: bool,
    replay: bool,
) -> tuple[
    PolicySnapshot,
    tuple[ToolSchema, ...],
    bool,
    ToolExecutionMode,
]:
    """从刚追加的 steer input payload strict 重建candidate执行输入。

    :param transaction: 当前 admission write transaction。
    :param input_event: 本次刚追加的 ``USER_INPUT_ACCEPTED``。
    :param tooling_options: construction-time tool truth。
    :param enable_truncation_manager: framework truncation tool 是否启用。
    :param replay: 当前 Run 是否为 replay lineage。
    :returns: typed policy、selected schemas、disable flag与tool mode。
    :raises HostDurableError: durable effective facts缺失或损坏时抛出。
    """

    if input_event.event_type != _EVENT_TYPE_USER_INPUT_ACCEPTED:
        raise HostDurableError("steer input event type mismatch")
    payload = event_payload_object(
        transaction,
        input_event,
        payload_label=_EVENT_TYPE_USER_INPUT_ACCEPTED,
    )
    execution_value = payload.get("effective_execution_config")
    tool_value = payload.get("effective_tool_set")
    if execution_value is None or tool_value is None:
        raise HostDurableError("steer durable effective facts are missing")
    execution = _effective_execution_snapshot_from_json(execution_value)
    policy_snapshot = PolicySnapshot(
        runner_spec=execution.runner_spec,
        runner_options=execution.runner_options,
        agent_policy=execution.agent_policy,
        policy_snapshot_ref=execution.policy_snapshot_ref,
    )
    effective_tool_facts = parse_effective_tool_facts(tool_value)
    runtime_tooling_options = None if replay else tooling_options
    selected_names = validate_effective_tool_facts_runtime(
        effective_tool_facts,
        tooling_options=runtime_tooling_options,
    )
    if (
        runtime_tooling_options is None
        or not policy_snapshot.agent_policy.allow_tool_calls
    ):
        if (
            not replay
            and effective_tool_facts.selector
            is EffectiveBusinessToolSelector.SUBSET
            and selected_names
        ):
            raise HostDurableError(
                "steer explicit subset tools are unavailable under frozen policy"
            )
        return (
            policy_snapshot,
            (),
            True,
            ToolExecutionMode.NO_TOOL_REPLAY
            if replay
            else ToolExecutionMode.NO_TOOL_DISABLED,
        )
    tooling_options = runtime_tooling_options
    effective_bundle = EffectiveToolBundleBuilder().build(
        EffectiveToolBundleBuildRequest(
            business_tool_bundle=tooling_options.business_tool_bundle,
            source_refs=tooling_options.source_refs,
            framework_tool_policy=tooling_options.framework_tool_policy,
            policy_snapshot_digest=_steer_policy_snapshot_digest(
                policy_snapshot
            ),
            selected_business_tool_names=selected_names,
            enable_truncation_manager=enable_truncation_manager,
        )
    )
    return (
        policy_snapshot,
        effective_bundle.tool_schemas,
        False,
        ToolExecutionMode.TOOL_ENABLED,
    )


def _steer_policy_snapshot_digest(
    policy_snapshot: PolicySnapshot,
) -> str:
    """计算 shared tool builder 使用的 frozen policy诊断digest。

    :param policy_snapshot: steer input strict typed policy。
    :returns: canonical sha256 digest。
    """

    return sha256_digest_json(
        {
            "policy_snapshot_ref": policy_snapshot.policy_snapshot_ref,
            "allow_tool_calls": policy_snapshot.agent_policy.allow_tool_calls,
            "max_iterations": policy_snapshot.agent_policy.max_iterations,
            "continuation_max_attempts": (
                policy_snapshot.agent_policy.continuation_max_attempts
            ),
            "tool_execution_timeout_seconds": (
                policy_snapshot.agent_policy.tool_execution_timeout_seconds
            ),
        }
    )


def _append_user_input_event(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: _CreateAdmissionRequest,
    run_id: str,
    event_id: str,
    occurred_at: datetime,
) -> EventLogRow:
    """追加 ``USER_INPUT_ACCEPTED`` canonical fact。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param request: 归一化创建输入。
    :param run_id: 本次 admission 生成的 Run id。
    :param event_id: 本次 input event id。
    :param occurred_at: 事件发生时间。
    :returns: 已持久化 EventLog row。
    """

    payload = _user_input_payload(request)
    descriptor = _write_user_input_payload_if_needed(
        transaction=transaction,
        payload=payload,
        event_id=event_id,
    )
    event_payload = (
        payload if descriptor is None else _referenced_user_input_event_payload(request)
    )
    return event_log_store.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=request.session_id,
            run_id=run_id,
            attempt_id=None,
            execution_id=None,
            event_type=_EVENT_TYPE_USER_INPUT_ACCEPTED,
            occurred_at=occurred_at,
            actor=request.actor,
            source=request.source,
            client_request_id=request.client_request_id,
            idempotency_key=request.client_request_id,
            policy_decision=None,
            reason=None,
            payload_json=event_payload,
            payload_ref=None if descriptor is None else descriptor.payload_ref,
            payload_digest=None if descriptor is None else descriptor.payload_digest,
        ),
    ).row


def _user_input_payload(request: _CreateAdmissionRequest) -> Mapping[str, JsonValue]:
    """构造完整 ``USER_INPUT_ACCEPTED`` payload。

    :param request: 归一化创建输入。
    :returns: 完整 payload object。
    """

    return {
        "input_ref": request.input.payload_ref,
        "input_digest": _input_digest(request.input),
        "display_text": request.input.display_text,
        "system_prompt": request.system_prompt,
        "user_prompt": request.input.display_text,
        "payload_ref": request.input.payload_ref,
        "payload_digest": request.input.payload_digest,
        "operation_kind": request.operation_kind,
        "call_context_digest": request.call_context_digest,
        "effective_execution_config": request.effective_execution_config,
        "effective_tool_set": request.effective_tool_set,
    }


def _write_user_input_payload_if_needed(
    *,
    transaction: HostTransaction,
    payload: Mapping[str, JsonValue],
    event_id: str,
) -> PayloadDescriptor | None:
    """超出 inline 阈值时把用户输入 payload 写入 SQLite payload 表。

    :param transaction: 当前 Host transaction。
    :param payload: 完整用户输入 payload。
    :param event_id: 对应 EventLog event id。
    :returns: payload descriptor；未超阈值时为 ``None``。
    :raises HostDurableError: payload 编码或写入失败时抛出。
    """

    encoded = canonical_json_dumps(payload)
    if len(encoded.encode("utf-8")) <= transaction.payload_inline_threshold_bytes:
        return None
    return PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=f"payload-user-input-{event_id}",
            payload_id=f"sqlite-payload-user-input-{event_id}",
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=payload,
            payload_bytes=None,
            media_type="application/json",
            metadata={"kind": "user_input_accepted"},
            expected_digest=None,
        ),
    )


def _referenced_user_input_event_payload(
    request: _CreateAdmissionRequest,
) -> Mapping[str, JsonValue]:
    """构造引用大 payload 的轻量 EventLog inline payload。

    :param request: 归一化创建输入。
    :returns: 可内联保存的轻量 payload object。
    """

    return {
        "input_ref": request.input.payload_ref,
        "input_digest": _input_digest(request.input),
        "payload_ref": request.input.payload_ref,
        "payload_digest": request.input.payload_digest,
        "operation_kind": request.operation_kind,
        "call_context_digest": request.call_context_digest,
    }


def _append_source_relation_requested_event(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    source_run: RunRow,
    event_id: str,
    event_type: str,
    occurred_at: datetime,
    actor: str,
    source: str,
    client_request_id: str,
    reason: str,
    repair_instruction: str | None,
) -> EventLogRow:
    """追加 retry / replay 控制请求 canonical fact。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param source_run: 源 Run row。
    :param event_id: 本次控制事件 id。
    :param event_type: ``RETRY_REQUESTED`` 或 ``REPLAY_REQUESTED``。
    :param occurred_at: 事件发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param client_request_id: 控制命令幂等 id。
    :param reason: 控制原因。
    :param repair_instruction: replay 修复指令；retry 时为 ``None``。
    :returns: 已持久化 EventLog row。
    """

    return event_log_store.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=source_run.session_id,
            run_id=source_run.run_id,
            attempt_id=source_run.current_attempt_id,
            execution_id=None,
            event_type=event_type,
            occurred_at=occurred_at,
            actor=actor,
            source=source,
            client_request_id=client_request_id,
            idempotency_key=client_request_id,
            policy_decision=None,
            reason={"reason": reason},
            payload_json={
                "source_run_id": source_run.run_id,
                "source_status": source_run.status.value,
                "reason": reason,
                "repair_instruction": repair_instruction,
            },
            payload_ref=None,
            payload_digest=None,
        ),
    ).row


def _append_steer_requested_event(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: SubmitFollowupRequest,
    target_run: RunRow,
    current_attempt: AttemptRow,
    event_id: str,
    occurred_at: datetime,
) -> EventLogRow:
    """追加 ``STEER_REQUESTED`` canonical fact。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param request: steer 请求。
    :param target_run: 目标 Run。
    :param current_attempt: 旧 current Attempt。
    :param event_id: 事件 id。
    :param occurred_at: 事件时间。
    :returns: 已持久化 EventLog row。
    """

    return event_log_store.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=target_run.session_id,
            run_id=target_run.run_id,
            attempt_id=current_attempt.attempt_id,
            execution_id=current_attempt.execution_id,
            event_type=_EVENT_TYPE_STEER_REQUESTED,
            occurred_at=occurred_at,
            actor=request.context.actor,
            source=request.context.source,
            client_request_id=request.client_request_id,
            idempotency_key=request.client_request_id,
            policy_decision=None,
            reason={"reason": "user_steer"},
            payload_json={
                "target_run_id": target_run.run_id,
                "previous_attempt_id": current_attempt.attempt_id,
                "user_prompt": request.user_prompt,
            },
            payload_ref=None,
            payload_digest=None,
        ),
    ).row


def _append_attempt_steered_event(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: SubmitFollowupRequest,
    target_run: RunRow,
    current_attempt: AttemptRow,
    event_id: str,
    occurred_at: datetime,
    steer_event: EventLogRow,
) -> EventLogRow:
    """追加 ``ATTEMPT_STEERED`` canonical fact。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param request: steer 请求。
    :param target_run: 目标 Run。
    :param current_attempt: 被 steer 的 Attempt。
    :param event_id: 事件 id。
    :param occurred_at: 事件时间。
    :param steer_event: ``STEER_REQUESTED`` 事件。
    :returns: 已持久化 EventLog row。
    """

    return event_log_store.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=target_run.session_id,
            run_id=target_run.run_id,
            attempt_id=current_attempt.attempt_id,
            execution_id=current_attempt.execution_id,
            event_type=_EVENT_TYPE_ATTEMPT_STEERED,
            occurred_at=occurred_at,
            actor=request.context.actor,
            source=request.context.source,
            client_request_id=request.client_request_id,
            idempotency_key=request.client_request_id,
            policy_decision=None,
            reason={"reason": "user_steer"},
            payload_json={
                "run_id": target_run.run_id,
                "attempt_id": current_attempt.attempt_id,
                "steer_requested_event_ref": _event_ref_json(steer_event),
            },
            payload_ref=None,
            payload_digest=None,
        ),
    ).row


def _append_steer_run_started_event(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: SubmitFollowupRequest,
    target_run: RunRow,
    attempt_id: str,
    dispatch_record_id: str,
    event_id: str,
    occurred_at: datetime,
    steer_event: EventLogRow,
) -> EventLogRow:
    """追加 steer 新 Attempt 的 ``RUN_STARTED`` canonical fact。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param request: steer 请求。
    :param target_run: 目标 Run。
    :param attempt_id: 新 Attempt id。
    :param dispatch_record_id: 新 dispatch record id。
    :param event_id: 事件 id。
    :param occurred_at: 事件时间。
    :param steer_event: ``STEER_REQUESTED`` 事件。
    :returns: 已持久化 EventLog row。
    """

    return event_log_store.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=target_run.session_id,
            run_id=target_run.run_id,
            attempt_id=None,
            execution_id=None,
            event_type=_EVENT_TYPE_RUN_STARTED,
            occurred_at=occurred_at,
            actor=request.context.actor,
            source=request.context.source,
            client_request_id=request.client_request_id,
            idempotency_key=request.client_request_id,
            policy_decision=None,
            reason={"start_reason": RunStartReason.STEER.value},
            payload_json={
                "run_id": target_run.run_id,
                "start_reason": RunStartReason.STEER.value,
                "accepted_event_id": target_run.accepted_event_id,
                "accepted_event_sequence": target_run.accepted_event_sequence,
                "attempt_id": attempt_id,
                "dispatch_record_id": dispatch_record_id,
                "steer_requested_event_ref": _event_ref_json(steer_event),
            },
            payload_ref=None,
            payload_digest=None,
        ),
    ).row


def _append_steer_attempt_started_event(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: SubmitFollowupRequest,
    target_run: RunRow,
    attempt_id: str,
    execution_id: str,
    event_id: str,
    occurred_at: datetime,
    steer_event: EventLogRow,
) -> EventLogRow:
    """追加 steer 新 Attempt 的 ``ATTEMPT_STARTED`` canonical fact。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param request: steer 请求。
    :param target_run: 目标 Run。
    :param attempt_id: 新 Attempt id。
    :param execution_id: 新 execution id。
    :param event_id: 事件 id。
    :param occurred_at: 事件时间。
    :param steer_event: ``STEER_REQUESTED`` 事件。
    :returns: 已持久化 EventLog row。
    """

    return event_log_store.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=target_run.session_id,
            run_id=target_run.run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            event_type=_EVENT_TYPE_ATTEMPT_STARTED,
            occurred_at=occurred_at,
            actor=request.context.actor,
            source=request.context.source,
            client_request_id=request.client_request_id,
            idempotency_key=request.client_request_id,
            policy_decision=None,
            reason={"start_reason": RunStartReason.STEER.value},
            payload_json={
                "run_id": target_run.run_id,
                "attempt_id": attempt_id,
                "execution_id": execution_id,
                "start_reason": RunStartReason.STEER.value,
                "steer_requested_event_ref": _event_ref_json(steer_event),
            },
            payload_ref=None,
            payload_digest=None,
        ),
    ).row


def _event_ref_json(event: EventLogRow) -> JsonValue:
    """构造 EventLog ref JSON。

    :param event: EventLog row。
    :returns: 事件引用 JSON。
    """

    return {"event_id": event.event_id, "event_sequence": event.event_sequence}


def _validate_followup_queue_input(
    admission_input: SubmitFollowupQueueAdmissionInput,
) -> None:
    """校验 follow-up queue admission 输入。

    :param admission_input: 待校验 admission 输入。
    :returns: ``None``。
    :raises ValueError: behavior 非 queue 或 resolved target 为空时抛出。
    """

    if admission_input.request.behavior != FollowupBehavior.QUEUE:
        raise ValueError("SubmitFollowupRequest.behavior must be queue")
    if admission_input.resolved_execution_target.strip() == "":
        raise ValueError("resolved_execution_target must be non-empty")


def _resolve_followup_effective_facts(
    request: SubmitFollowupRequest,
    *,
    baseline: OrdinaryRunExecutionBaseline | None,
    tooling_options: HostToolingOptions | None,
) -> _ResolvedFollowupEffectiveFacts:
    """解析并冻结 follow-up 的 effective execution config 与业务工具集合。

    :param request: submit follow-up 请求。
    :param baseline: opener ordinary Run baseline；低层 legacy handle 可能为 ``None``。
    :param tooling_options: opener construction-time 工具选项。
    :returns: 已解析的 effective facts。
    :raises HostApiError: 缺少 opener baseline 或工具名未知时抛出。
    :raises TypeError: RunnerSpec 中包含未知 provider request extension 时抛出。
    """

    if baseline is None:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="submit_followup requires an opener ordinary Run baseline",
            retryable=False,
        )
    runner_spec = (
        request.runner_spec if request.runner_spec is not None else baseline.runner_spec
    )
    runner_options = (
        request.runner_options
        if request.runner_options is not None
        else baseline.runner_options
    )
    agent_policy = (
        request.agent_policy
        if request.agent_policy is not None
        else baseline.agent_policy
    )
    execution_config = _effective_execution_config_json(
        runner_spec=runner_spec,
        runner_options=runner_options,
        agent_policy=agent_policy,
        runner_spec_source=_field_source(request.runner_spec is not None),
        runner_options_source=_field_source(request.runner_options is not None),
        agent_policy_source=_field_source(request.agent_policy is not None),
    )
    tool_set = effective_tool_facts_json(
        request.tool_names,
        tooling_options=tooling_options,
    )
    return _ResolvedFollowupEffectiveFacts(
        effective_execution_config=execution_config,
        effective_tool_set=tool_set,
    )


def _resolve_start_effective_facts(
    *,
    baseline: OrdinaryRunExecutionBaseline | None,
    tooling_options: HostToolingOptions | None,
) -> _ResolvedFollowupEffectiveFacts:
    """解析并冻结初始 Run 的 effective execution config 与业务工具集合。

    初始 ``StartRunRequest`` 没有 per-request execution/tool override，因此两个
    canonical facts 必须完全来自当前 execution Host 的构造期输入。admin-only
    handle 没有 baseline 时在 admission owner 边界 fail closed。

    :param baseline: execution Host ordinary Run baseline。
    :param tooling_options: execution Host 构造期工具选项。
    :returns: 已解析的 effective facts。
    :raises HostApiError: 当前 handle 没有 ordinary Run baseline 时抛出。
    :raises TypeError: RunnerSpec 中包含未知 provider request extension 时抛出。
    """

    if baseline is None:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="start_run requires an opener ordinary Run baseline",
            retryable=False,
        )
    return _ResolvedFollowupEffectiveFacts(
        effective_execution_config=_effective_execution_config_json(
            runner_spec=baseline.runner_spec,
            runner_options=baseline.runner_options,
            agent_policy=baseline.agent_policy,
            runner_spec_source="opener_baseline",
            runner_options_source="opener_baseline",
            agent_policy_source="opener_baseline",
        ),
        effective_tool_set=effective_tool_facts_json(
            None,
            tooling_options=tooling_options,
        ),
    )


def _field_source(override_present: bool) -> str:
    """返回 effective 字段的来源标识。

    :param override_present: 请求是否显式提供 override。
    :returns: ``request`` 或 ``opener_baseline``。
    :raises: 无主动抛出。
    """

    if override_present:
        return "request"
    return "opener_baseline"


def effective_tool_facts_json(
    requested_tool_names: frozenset[str] | None,
    *,
    tooling_options: HostToolingOptions | None,
) -> JsonValue:
    """构造 effective business tool set 冻结 JSON。

    :param requested_tool_names: 请求选择器。
    :param tooling_options: construction-time 工具选项。
    :returns: 可写入 EventLog 的 JSON mapping。
    :raises HostApiError: 请求未知工具名时抛出。
    :raises ValueError: 工具 bundle schema 字段非法时由底层转换抛出。
    """

    business_definitions = (
        ()
        if tooling_options is None
        else tooling_options.business_tool_bundle.definitions
    )
    known_names = frozenset(definition.name for definition in business_definitions)
    if requested_tool_names is None:
        effective_names = known_names
        selector = _TOOL_SELECTION_ALL
    else:
        unknown = requested_tool_names.difference(known_names)
        if unknown:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message=(
                    "submit_followup tool_names contains unknown business tools: "
                    + ",".join(sorted(unknown))
                ),
                retryable=False,
            )
        effective_names = requested_tool_names
        selector = (
            _TOOL_SELECTION_NONE if not requested_tool_names else _TOOL_SELECTION_SUBSET
        )
    selected_schemas = tuple(
        definition.to_tool_schema()
        for definition in business_definitions
        if definition.name in effective_names
    )
    schema_digest = _tool_schemas_digest(selected_schemas)
    source_refs_json: list[JsonValue] = []
    if tooling_options is not None:
        source_refs_json = [
            {
                "source_kind": source_ref.source_kind.value,
                "source_id": source_ref.source_id,
                "version_ref": source_ref.version_ref,
                "content_digest": source_ref.content_digest,
            }
            for source_ref in tooling_options.source_refs
        ]
    tool_set: JsonValue = {
        "tool_snapshot_ref": _TOOL_SNAPSHOT_REF_PREFIX + schema_digest,
        "selector": selector,
        "requested_business_tool_names": (
            None
            if requested_tool_names is None
            else _sorted_text_json_array(requested_tool_names)
        ),
        "effective_business_tool_names": _sorted_text_json_array(effective_names),
        "business_bundle_digest": _tool_definitions_digest(business_definitions),
        "effective_schema_digest": schema_digest,
        "effective_tool_display_names": _effective_tool_display_names_json(
            business_definitions, effective_names
        ),
        "source_refs": source_refs_json,
    }
    return tool_set


def parse_effective_tool_facts(value: JsonValue) -> EffectiveToolFacts:
    """严格解析 admission 冻结的 effective tool facts。

    :param value: ``USER_INPUT_ACCEPTED.effective_tool_set`` JSON。
    :returns: 完整 typed effective tool facts。
    :raises HostDurableError: 字段缺失、多余、类型、选择闭集或摘要非法时抛出。
    """

    if not isinstance(value, Mapping):
        raise HostDurableError("effective_tool_set must be object")
    if frozenset(value) != _EFFECTIVE_TOOL_FACT_FIELDS:
        raise HostDurableError("effective_tool_set fields mismatch")
    selector_value = value.get("selector")
    if not isinstance(selector_value, str):
        raise HostDurableError("effective tool selector must be text")
    try:
        selector = EffectiveBusinessToolSelector(selector_value)
    except ValueError as exc:
        raise HostDurableError("effective tool selector is invalid") from exc
    effective_names = _strict_tool_name_set(
        value.get("effective_business_tool_names"),
        field_name="effective_business_tool_names",
    )
    requested_value = value.get("requested_business_tool_names")
    requested_names = (
        None
        if requested_value is None
        else _strict_tool_name_set(
            requested_value,
            field_name="requested_business_tool_names",
        )
    )
    if selector is EffectiveBusinessToolSelector.ALL:
        if requested_names is not None:
            raise HostDurableError("all tool selector must have null requested names")
    elif selector is EffectiveBusinessToolSelector.SUBSET:
        if not requested_names or requested_names != effective_names:
            raise HostDurableError(
                "subset tool selector must preserve exact requested names"
            )
    elif requested_names != frozenset() or effective_names:
        raise HostDurableError("none tool selector must preserve exact empty names")
    business_bundle_digest = _strict_effective_tool_digest(
        value.get("business_bundle_digest"),
        field_name="business_bundle_digest",
    )
    effective_schema_digest = _strict_effective_tool_digest(
        value.get("effective_schema_digest"),
        field_name="effective_schema_digest",
    )
    tool_snapshot_ref = value.get("tool_snapshot_ref")
    if (
        not isinstance(tool_snapshot_ref, str)
        or tool_snapshot_ref
        != _TOOL_SNAPSHOT_REF_PREFIX + effective_schema_digest
    ):
        raise HostDurableError("effective tool snapshot ref does not match schema digest")
    display_names = _strict_effective_tool_display_names(
        value.get("effective_tool_display_names"),
        effective_names=effective_names,
    )
    source_refs = _strict_tool_source_refs(value.get("source_refs"))
    return EffectiveToolFacts(
        tool_snapshot_ref=tool_snapshot_ref,
        selector=selector,
        requested_business_tool_names=requested_names,
        effective_business_tool_names=effective_names,
        business_bundle_digest=business_bundle_digest,
        effective_schema_digest=effective_schema_digest,
        effective_tool_display_names=display_names,
        source_refs=source_refs,
    )


def validate_effective_tool_facts_runtime(
    facts: EffectiveToolFacts,
    *,
    tooling_options: HostToolingOptions | None,
) -> frozenset[str]:
    """校验当前 runtime 能精确实现 admission 冻结的工具事实。

    :param facts: strict typed admission tool facts。
    :param tooling_options: 当前 Host construction-time 工具真源。
    :returns: admission 冻结的 exact effective 业务工具名集合。
    :raises HostDurableError: bundle、selected schema、source refs 或 display
        snapshot 发生漂移时抛出。
    """

    definitions = (
        ()
        if tooling_options is None
        else tooling_options.business_tool_bundle.definitions
    )
    source_refs = () if tooling_options is None else tooling_options.source_refs
    if _tool_definitions_digest(definitions) != facts.business_bundle_digest:
        raise HostDurableError("current business tool bundle does not match admission")
    if source_refs != facts.source_refs:
        raise HostDurableError("current business tool source refs do not match admission")
    known_names = frozenset(definition.name for definition in definitions)
    if not facts.effective_business_tool_names.issubset(known_names):
        raise HostDurableError("admission effective tool names are unavailable")
    selected_schemas = tuple(
        definition.to_tool_schema()
        for definition in definitions
        if definition.name in facts.effective_business_tool_names
    )
    if _tool_schemas_digest(selected_schemas) != facts.effective_schema_digest:
        raise HostDurableError("current selected tool schemas do not match admission")
    if (
        _TOOL_SNAPSHOT_REF_PREFIX + facts.effective_schema_digest
        != facts.tool_snapshot_ref
    ):
        raise HostDurableError("admission tool snapshot ref is inconsistent")
    expected_display_names = _effective_tool_display_names(
        definitions,
        facts.effective_business_tool_names,
    )
    if expected_display_names != facts.effective_tool_display_names:
        raise HostDurableError("current selected tool display names do not match admission")
    return facts.effective_business_tool_names


def _strict_tool_name_set(
    value: JsonValue | None,
    *,
    field_name: str,
) -> frozenset[str]:
    """严格解析无重复工具名数组。

    :param value: 待解析 JSON 值。
    :param field_name: 错误消息字段名。
    :returns: exact 工具名集合。
    :raises HostDurableError: 值不是数组、元素为空或重复时抛出。
    """

    if not isinstance(value, list):
        raise HostDurableError(f"{field_name} must be array")
    names: set[str] = set()
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise HostDurableError(f"{field_name} entries must be non-empty text")
        if item in names:
            raise HostDurableError(f"{field_name} contains duplicate")
        names.add(item)
    return frozenset(names)


def _strict_effective_tool_digest(
    value: JsonValue | None,
    *,
    field_name: str,
) -> str:
    """严格读取 effective tool digest。

    :param value: 待解析 JSON 值。
    :param field_name: 错误消息字段名。
    :returns: 合法 ``sha256:`` 摘要。
    :raises HostDurableError: 值不是合法摘要时抛出。
    """

    if not isinstance(value, str):
        raise HostDurableError(f"{field_name} must be sha256 digest")
    try:
        _require_sha256_digest(value, field_name=field_name)
    except ValueError as exc:
        raise HostDurableError(f"{field_name} must be sha256 digest") from exc
    return value


def _strict_effective_tool_display_names(
    value: JsonValue | None,
    *,
    effective_names: frozenset[str],
) -> tuple[tuple[str, str], ...]:
    """严格读取 selected tool display name 快照。

    :param value: display name JSON mapping。
    :param effective_names: admission exact selected names。
    :returns: 按工具名排序的 immutable 键值对。
    :raises HostDurableError: key/value 非法或包含未选中工具时抛出。
    """

    if not isinstance(value, Mapping):
        raise HostDurableError("effective_tool_display_names must be object")
    display_names: list[tuple[str, str]] = []
    for name, display_name in value.items():
        if (
            name not in effective_names
            or name.strip() == ""
            or not isinstance(display_name, str)
            or display_name.strip() == ""
        ):
            raise HostDurableError("effective tool display name is invalid")
        display_names.append((name, display_name))
    return tuple(sorted(display_names))


def _strict_tool_source_refs(
    value: JsonValue | None,
) -> tuple[ToolBundleSourceRef, ...]:
    """严格读取完整业务工具来源引用。

    :param value: ``source_refs`` JSON 数组。
    :returns: 保留冻结顺序的 typed source refs。
    :raises HostDurableError: shape、枚举或字段语义非法时抛出。
    """

    if not isinstance(value, list):
        raise HostDurableError("effective tool source_refs must be array")
    refs: list[ToolBundleSourceRef] = []
    for item in value:
        if not isinstance(item, Mapping) or frozenset(item) != _TOOL_SOURCE_REF_FIELDS:
            raise HostDurableError("effective tool source ref fields mismatch")
        source_kind_value = item.get("source_kind")
        source_id = item.get("source_id")
        version_ref = item.get("version_ref")
        content_digest = item.get("content_digest")
        if (
            not isinstance(source_kind_value, str)
            or not isinstance(source_id, str)
            or (version_ref is not None and not isinstance(version_ref, str))
            or (content_digest is not None and not isinstance(content_digest, str))
        ):
            raise HostDurableError("effective tool source ref values are invalid")
        try:
            source_ref = ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind(source_kind_value),
                source_id=source_id,
                version_ref=version_ref,
                content_digest=content_digest,
            )
        except (TypeError, ValueError) as exc:
            raise HostDurableError("effective tool source ref is invalid") from exc
        if source_ref in refs:
            raise HostDurableError("effective tool source refs contain duplicate")
        refs.append(source_ref)
    return tuple(refs)


def _effective_tool_display_names_json(
    definitions: tuple[ToolDefinition, ...], effective_names: frozenset[str]
) -> JsonValue:
    """构造 selected tools 的 Host-owned display name snapshot。

    :param definitions: construction-time business tool definitions。
    :param effective_names: 本次 Run 选中的稳定工具名集合。
    :returns: 工具名到展示名的 JSON mapping；缺少 display metadata 的工具不写入。
    :raises: 无主动抛出。
    """

    return dict(_effective_tool_display_names(definitions, effective_names))


def _effective_tool_display_names(
    definitions: tuple[ToolDefinition, ...],
    effective_names: frozenset[str],
) -> tuple[tuple[str, str], ...]:
    """构造 selected tools 的 immutable display name 快照。

    :param definitions: construction-time business tool definitions。
    :param effective_names: 本次 Run 选中的稳定工具名集合。
    :returns: 按工具名排序的 display name 键值对。
    :raises: 无主动抛出。
    """

    display_names: list[tuple[str, str]] = []
    for definition in definitions:
        if definition.name not in effective_names or definition.display is None:
            continue
        display_names.append((definition.name, definition.display.name))
    return tuple(sorted(display_names))


def _replay_effective_execution_config(
    source_execution_config: JsonValue | None,
    *,
    baseline: OrdinaryRunExecutionBaseline | None,
) -> JsonValue:
    """构造 replay 使用的 no-tool execution config。

    :param source_execution_config: 源 Run 冻结 execution config。
    :param baseline: opener ordinary Run baseline；源配置缺失时使用。
    :returns: replay Run 写入 USER_INPUT_ACCEPTED 的 execution config JSON。
    :raises HostApiError: 源配置缺失且无 opener baseline 时抛出。
    """

    if source_execution_config is None:
        if baseline is None:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="replay_run requires source execution config",
                retryable=False,
            )
        runner_spec = baseline.runner_spec
        runner_options = baseline.runner_options
        agent_policy = baseline.agent_policy
    else:
        snapshot = _effective_execution_snapshot_from_json(source_execution_config)
        runner_spec = snapshot.runner_spec
        runner_options = snapshot.runner_options
        agent_policy = snapshot.agent_policy
    return _effective_execution_config_json(
        runner_spec=runner_spec,
        runner_options=runner_options,
        agent_policy=replace(agent_policy, allow_tool_calls=False),
        runner_spec_source="source_run",
        runner_options_source="source_run",
        agent_policy_source="replay_no_tool",
    )


def _require_payload_mapping(payload: JsonValue) -> dict[str, JsonValue]:
    """校验 payload 是 JSON object 并复制为 dict。

    :param payload: payload JSON 值。
    :returns: 字段映射副本。
    :raises HostDurableError: payload 不是 object 时抛出。
    """

    if not isinstance(payload, dict):
        raise HostDurableError("EventLog payload_json must be object")
    return payload


def _required_payload_text(payload: dict[str, JsonValue], field_name: str) -> str:
    """读取必填文本 payload 字段。

    :param payload: payload 字段映射。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"payload field {field_name} must be text")
    return value


def _optional_payload_text(
    payload: dict[str, JsonValue], field_name: str
) -> str | None:
    """读取可选文本 payload 字段。

    :param payload: payload 字段映射。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"payload field {field_name} must be text")
    return value


def _sorted_text_json_array(values: frozenset[str]) -> list[JsonValue]:
    """把文本集合稳定投影为 JSON 数组。

    :param values: 文本集合。
    :returns: 排序后的 JSON 数组。
    :raises: 无主动抛出。
    """

    return [value for value in sorted(values)]


def _require_open_session(transaction: HostTransaction, session_id: str) -> None:
    """读取并校验 Session 为 open。

    :param transaction: 当前 Host transaction。
    :param session_id: Session id。
    :returns: ``None``。
    :raises HostApiError: Session 缺失或非 open 时抛出。
    """

    session = _require_existing_session(transaction, session_id)
    if session.status != SessionStatus.OPEN:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="Session is not open",
            retryable=False,
        )


def _require_source_run_for_relation(
    transaction: HostTransaction,
    *,
    run_id: str,
    expected_status: RunStatus,
    operation_name: str,
) -> RunRow:
    """读取并校验 retry / replay 源 Run。

    :param transaction: 当前 Host transaction。
    :param run_id: 源 Run id。
    :param expected_status: 操作要求的源 Run 状态。
    :param operation_name: public operation 名称，用于错误消息。
    :returns: 已校验源 Run row。
    :raises HostApiError: 源 Run 缺失、状态不符或所属 Session closed 时抛出。
    """

    run = read_run_by_id(transaction, run_id)
    if run is None:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Source Run not found",
            retryable=False,
        )
    _require_open_session(transaction, run.session_id)
    if run.status != expected_status:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message=f"{operation_name} source Run state is invalid",
            retryable=False,
        )
    return run


def _require_steer_target_run(
    transaction: HostTransaction, request: SubmitFollowupRequest
) -> RunRow:
    """读取并校验 steer 目标 Run。

    :param transaction: 当前 Host transaction。
    :param request: steer 请求。
    :returns: 已校验目标 Run。
    :raises HostApiError: 目标 Run 缺失、非当前 active 或状态非法时抛出。
    """

    target_run_id = request.target_run_id
    if target_run_id is None:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="submit_followup steer requires target Run",
            retryable=False,
        )
    _require_open_session(transaction, request.session_id)
    target = read_run_by_id(transaction, target_run_id)
    active = read_active_run_for_session(transaction, request.session_id)
    if target is None or active is None or active.run_id != target_run_id:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="submit_followup steer target is not active",
            retryable=False,
            detail=_steer_conflict_detail(
                target_run_id=target_run_id,
                target=target,
                active=active,
            ),
        )
    if target.session_id != request.session_id:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="submit_followup steer target session mismatch",
            retryable=False,
            detail=_steer_conflict_detail(
                target_run_id=target_run_id,
                target=target,
                active=active,
            ),
        )
    if target.status not in (RunStatus.RUNNING, RunStatus.WAITING):
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="submit_followup steer target state is invalid",
            retryable=False,
            detail=_steer_conflict_detail(
                target_run_id=target_run_id,
                target=target,
                active=active,
            ),
        )
    return target


def _steer_conflict_detail(
    *, target_run_id: str, target: RunRow | None, active: RunRow | None
) -> SteerConflictDetail:
    """构造 steer 前置条件冲突详情。

    :param target_run_id: 调用方请求 steer 的目标 Run id。
    :param target: durable 中读到的目标 Run；缺失时为 ``None``。
    :param active: 同 Session 当前 active Run；缺失时为 ``None``。
    :returns: typed steer 冲突详情。
    """

    return SteerConflictDetail(
        target_run_id=target_run_id,
        target_run_status=None if target is None else target.status,
        current_active_run_id=None if active is None else active.run_id,
        current_active_run_status=None if active is None else active.status,
    )


def _require_current_attempt_for_steer(
    transaction: HostTransaction, run: RunRow
) -> AttemptRow:
    """读取并校验 steer 目标 Run 当前 Attempt。

    :param transaction: 当前 Host transaction。
    :param run: steer 目标 Run。
    :returns: 当前 Attempt。
    :raises HostApiError: Attempt 缺失或状态不符合 Run 状态时抛出。
    """

    attempt = _read_current_attempt(transaction, run)
    if attempt is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Steer target Run has no current Attempt",
            retryable=False,
        )
    if run.status == RunStatus.RUNNING and attempt.status != AttemptStatus.RUNNING:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="RUNNING steer target Attempt is not running",
            retryable=False,
        )
    if run.status == RunStatus.WAITING and attempt.status != AttemptStatus.SUSPENDED:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="WAITING steer target Attempt is not suspended",
            retryable=False,
        )
    return attempt


def _source_input_payload(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    source_run: RunRow,
) -> JsonValue:
    """读取源 Run 的 USER_INPUT_ACCEPTED payload。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param source_run: 源 Run row。
    :returns: 源输入 payload JSON。
    :raises HostApiError: 源输入事件缺失或类型不匹配时抛出。
    :raises HostDurableError: payload JSON 解析失败时抛出。
    """

    event = event_log_store.read_event_by_id(transaction, source_run.input_event_id)
    if event is None or event.event_type != _EVENT_TYPE_USER_INPUT_ACCEPTED:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Source Run input event is missing",
            retryable=False,
        )
    return event_payload_object(transaction, event, payload_label="USER_INPUT_ACCEPTED")


def _require_existing_session(
    transaction: HostTransaction, session_id: str
) -> SessionRow:
    """读取存在的 Session row。

    :param transaction: 当前 Host transaction。
    :param session_id: Session id。
    :returns: Session row。
    :raises HostApiError: Session 缺失时抛出。
    """

    session = read_session_by_id(transaction, session_id)
    if session is None:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Session not found",
            retryable=False,
        )
    return session


def _idempotency_scope(
    *,
    operation: IdempotencyScopeKind,
    scope_id: str,
    idempotency_key: str,
) -> IdempotencyScope:
    """构造 admission 幂等 scope。

    :param operation: 操作名。
    :param scope_id: scope id。
    :param idempotency_key: 幂等 key。
    :returns: idempotency scope。
    """

    return IdempotencyScope(
        scope_kind=operation,
        scope_id=scope_id,
        idempotency_key=idempotency_key,
    )


def _raise_if_digest_conflict(record: IdempotencyRecord, semantic_digest: str) -> None:
    """校验既有幂等记录 digest 是否一致。

    :param record: 既有幂等记录。
    :param semantic_digest: 本次 semantic digest。
    :returns: ``None``。
    :raises HostApiError: digest 不一致时抛出 idempotency conflict。
    """

    if record.semantic_input_digest != semantic_digest:
        raise HostApiError(
            code=HostApiErrorCode.IDEMPOTENCY_CONFLICT,
            message="Idempotency key already exists with different semantic digest",
            retryable=False,
        )


def _idempotent_run_result(
    transaction: HostTransaction, record: IdempotencyRecord
) -> RunAdmissionResult:
    """从幂等记录恢复 Run admission 结果。

    :param transaction: 当前 Host transaction。
    :param record: 已持久化幂等记录。
    :returns: admission 结果。
    :raises HostApiError: 结果类型错误或 Run 缺失时抛出。
    """

    if record.result_kind != _IDEMPOTENCY_RESULT_KIND_RUN:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Idempotency record result kind is not run",
            retryable=False,
        )
    run = read_run_by_id(transaction, record.result_ref)
    if run is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Idempotency record points to missing Run",
            retryable=False,
        )
    attempt = _read_current_attempt(transaction, run)
    dispatch_record = _read_current_dispatch_record(transaction, run)
    pending_dispatch = _idempotent_replay_pending_dispatch(
        run=run,
        attempt=attempt,
        dispatch_record=dispatch_record,
    )
    return RunAdmissionResult(
        run=run,
        attempt=attempt,
        dispatch_record=dispatch_record,
        pending_dispatch=pending_dispatch,
        created=False,
        queued=run.status == RunStatus.QUEUED,
        attached_active=record.created_event_id is None,
        idempotent_replay=True,
    )


def _idempotent_replay_pending_dispatch(
    *,
    run: RunRow,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
) -> PendingDispatchRecord | None:
    """从 durable snapshot 派生幂等 replay 的 matching dispatch wake。

    只有仍处于 ``RUNNING / STARTING / PENDING`` 的同源 current Attempt 才需要
    重投递 dispatch。ACCEPTED Run 的 pre-start governance wake 由同一 admission
    service 的 ``_wake_start_governance_if_needed`` 派生；terminal、queued、已
    取消或已进入 lane/worker 流程的记录不重投递。

    :param run: idempotency record 指向的最新 Run row。
    :param attempt: Run current Attempt row；无 current Attempt 时为 ``None``。
    :param dispatch_record: current Attempt dispatch row；无时为 ``None``。
    :returns: 需要重投递时返回 matching pending dispatch，否则返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if (
        run.status is not RunStatus.RUNNING
        or attempt is None
        or attempt.status is not AttemptStatus.STARTING
        or dispatch_record is None
        or dispatch_record.status is not DispatchRecordStatus.PENDING
        or run.current_attempt_id != attempt.attempt_id
        or dispatch_record.run_id != run.run_id
        or dispatch_record.attempt_id != attempt.attempt_id
        or dispatch_record.execution_id != attempt.execution_id
        or dispatch_record.cancelled_event_id is not None
        or dispatch_record.worker_accept_event_id is not None
    ):
        return None
    return _pending_dispatch_from_row(dispatch_record)


def _idempotent_steer_result(
    transaction: HostTransaction, record: IdempotencyRecord
) -> SteerAdmissionResult:
    """从幂等记录恢复 steer 结果。

    :param transaction: 当前 Host transaction。
    :param record: 已持久化幂等记录。
    :returns: steer 结果；不会再次传播旧 Attempt cancel。
    :raises HostApiError: 结果类型错误或 Run 缺失时抛出。
    """

    run_result = _idempotent_run_result(transaction, record)
    return SteerAdmissionResult(
        run=run_result.run,
        attempt=run_result.attempt,
        dispatch_record=run_result.dispatch_record,
        pending_dispatch=None,
        steered_cancel_target=None,
        input_event_id=(
            record.created_event_id
            if record.created_event_id is not None
            else run_result.run.input_event_id
        ),
        idempotent_replay=True,
    )


def _classified_cancel_result(
    classification: _CancelRunClassification,
    result: CancelRunResult,
) -> _CancelRunOperationResult:
    """构造带有效 cancel result 的 transaction-local 分类。

    :param classification: 只允许 supported 或 terminal 分类。
    :param result: 同一 transaction 产生或恢复的 cancel result。
    :returns: immutable operation result。
    :raises ValueError: classification 不携带成功 result 时抛出。
    """

    if classification not in (
        _CancelRunClassification.SUPPORTED,
        _CancelRunClassification.TERMINAL,
    ):
        raise ValueError("cancel result requires supported or terminal classification")
    return _CancelRunOperationResult(
        classification=classification,
        result=result,
    )


def _idempotent_cancel_result(
    transaction: HostTransaction,
    record: IdempotencyRecord,
    *,
    event_log_store: EventLogStore,
) -> CancelRunResult:
    """从幂等记录恢复 cancel_run 结果。

    :param transaction: 当前 Host transaction。
    :param record: 已持久化 cancel 幂等记录。
    :param event_log_store: EventLog 读取 primitive。
    :returns: cancel 结果；幂等重放不再次触发 promotion。
    :raises HostApiError: 结果类型错误或 Run 缺失时抛出。
    """

    if record.result_kind != _IDEMPOTENCY_RESULT_KIND_RUN:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Cancel idempotency record result kind is not run",
            retryable=False,
        )
    run = read_run_by_id(transaction, record.result_ref)
    if run is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Cancel idempotency record points to missing Run",
            retryable=False,
        )
    terminal_notice = None
    if is_terminal_run_status(run.status):
        confirmation = confirm_terminal_run_in_transaction(
            transaction,
            event_log_store,
            run,
        )
        terminal_notice = project_terminal_notice_from_exact_run_event(
            confirmation.run,
            confirmation.run_event,
            wake_queue_promotion=False,
        )
    return CancelRunResult(
        run=run,
        attempt=_read_current_attempt(transaction, run),
        dispatch_record=_read_current_dispatch_record(transaction, run),
        terminal_notice=terminal_notice,
        active_cancel_target=None,
        idempotent_replay=True,
    )


def _idempotent_session_cancel_result(
    transaction: HostTransaction,
    record: IdempotencyRecord,
    *,
    event_log_store: EventLogStore,
    reason: str,
) -> SessionCancelResult:
    """从幂等记录恢复 cancel_session_runs 结果。

    :param transaction: 当前 Host transaction。
    :param record: 已持久化幂等记录。
    :param event_log_store: 注入的 EventLog primitive。
    :param reason: 本次 replay 的取消原因，用于 best-effort 重新传播。
    :returns: 当前 Session snapshot；不会取消首次操作后新增的 Run。
    :raises HostApiError: 结果类型错误或 Session 缺失时抛出。
    """

    if record.result_kind != _IDEMPOTENCY_RESULT_KIND_SESSION:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Session cancel idempotency record result kind is not session",
            retryable=False,
        )
    session = read_session_by_id(transaction, record.result_ref)
    if session is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Session cancel idempotency record points to missing Session",
            retryable=False,
        )
    return SessionCancelResult(
        snapshot=session_snapshot_from_rows(
            transaction,
            session,
            read_session_slot_by_session_id(transaction, session.session_id),
        ),
        active_cancel_targets=_active_cancelling_targets_for_session_replay(
            transaction,
            event_log_store,
            session.session_id,
            record=record,
            reason=reason,
        ),
        idempotent_replay=True,
        cancelled_run_count=0,
        terminal_notices=(),
    )


def _read_current_attempt(
    transaction: HostTransaction, run: RunRow
) -> AttemptRow | None:
    """读取 Run 当前 Attempt。

    :param transaction: 当前 Host transaction。
    :param run: Run row。
    :returns: 有 current Attempt 时返回 Attempt row，否则返回 ``None``。
    :raises HostApiError: current_attempt_id 指向缺失 row 时抛出。
    """

    if run.current_attempt_id is None:
        return None
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    if attempt is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Run current Attempt is missing",
            retryable=False,
        )
    return attempt


def _read_current_dispatch_record(
    transaction: HostTransaction, run: RunRow
) -> DispatchRecordRow | None:
    """读取 Run 当前 Attempt 对应的 dispatch record。

    :param transaction: 当前 Host transaction。
    :param run: Run row。
    :returns: 有 current Attempt 时返回 dispatch row，否则返回 ``None``。
    :raises HostApiError: current Attempt 缺 dispatch record 时抛出。
    """

    if run.current_attempt_id is None:
        return None
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, run.current_attempt_id
    )
    if dispatch_record is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Run current dispatch record is missing",
            retryable=False,
        )
    return dispatch_record


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


def _active_cancel_target_from_transition(
    *, run: RunRow, attempt: AttemptRow | None, reason: str
) -> ActiveCancelTarget | None:
    """从 active cancel transition 结果提取 post-commit 传播目标。

    :param run: transition 返回的 Run row。
    :param attempt: transition 返回的 Attempt row。
    :param reason: cancel reason。
    :returns: active worker 目标；当前状态不需要传播时返回 ``None``。
    """

    if (
        run.status != RunStatus.CANCELLING
        or attempt is None
        or attempt.status != AttemptStatus.RUNNING
    ):
        return None
    return ActiveCancelTarget(
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        reason=reason,
    )


def _active_cancel_target_for_session_target(
    *, target: _SupportedSessionCancelTarget, reason: str
) -> ActiveCancelTarget | None:
    """从 session-scope cancel target 提取 post-commit active cancel 目标。

    :param target: 已校验并执行取消的 session target。
    :param reason: cancel reason。
    :returns: active worker 目标；非 active worker 时返回 ``None``。
    """

    if not target.active_worker or target.attempt is None:
        return None
    return ActiveCancelTarget(
        run_id=target.run.run_id,
        attempt_id=target.attempt.attempt_id,
        execution_id=target.attempt.execution_id,
        reason=reason,
    )


def _active_cancelling_targets_for_session_replay(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    session_id: str,
    *,
    record: IdempotencyRecord,
    reason: str,
) -> tuple[ActiveCancelTarget, ...]:
    """读取 session cancel replay 可重新传播的同源 active CANCELLING 目标。

    :param transaction: 当前 Host transaction。
    :param event_log_store: 注入的 EventLog primitive。
    :param session_id: Session id。
    :param record: 首次 session cancel 的幂等记录。
    :param reason: replay 请求中的 cancel reason。
    :returns: 仍处于 active cancelling 的 worker 目标集合。
    """

    if record.created_event_id is None:
        return ()
    event = event_log_store.read_event_by_id(transaction, record.created_event_id)
    if event is None or event.session_id != session_id or event.run_id is None:
        return ()
    run = read_run_by_id(transaction, event.run_id)
    if (
        run is None
        or run.session_id != session_id
        or run.status != RunStatus.CANCELLING
        or run.current_attempt_id is None
    ):
        return ()
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    if attempt is None or attempt.status != AttemptStatus.RUNNING:
        return ()
    return (
        ActiveCancelTarget(
            run_id=run.run_id,
            attempt_id=attempt.attempt_id,
            execution_id=attempt.execution_id,
            reason=reason,
        ),
    )


def _session_cancel_target_for_run(
    transaction: HostTransaction, run: RunRow
) -> _SupportedSessionCancelTarget | None:
    """判断 Run 是否属于当前 session-scope cancel 支持子集。

    :param transaction: 当前 Host transaction。
    :param run: 待判断的非终态 Run。
    :returns: 支持时返回取消目标，否则返回 ``None``。
    :raises HostApiError: durable row 指针缺失表示内部状态损坏时抛出。
    """

    if run.status in (RunStatus.ACCEPTED, RunStatus.QUEUED):
        return _SupportedSessionCancelTarget(
            run=run,
            attempt=None,
            dispatch_record=None,
            active_worker=False,
            waiting=False,
            recovering=False,
        )
    if run.status == RunStatus.WAITING:
        if run.current_attempt_id is None:
            raise HostApiError(
                code=HostApiErrorCode.INTERNAL_ERROR,
                message="WAITING Run has no current Attempt",
                retryable=False,
            )
        attempt = read_attempt_by_id(transaction, run.current_attempt_id)
        dispatch_record = read_dispatch_record_by_attempt_id(
            transaction, run.current_attempt_id
        )
        if attempt is None:
            raise HostApiError(
                code=HostApiErrorCode.INTERNAL_ERROR,
                message="WAITING Run current Attempt is missing",
                retryable=False,
            )
        if attempt.status != AttemptStatus.SUSPENDED:
            return None
        return _SupportedSessionCancelTarget(
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
            active_worker=False,
            waiting=True,
            recovering=False,
        )
    if run.status == RunStatus.RECOVERING:
        attempt = (
            read_attempt_by_id(transaction, run.current_attempt_id)
            if run.current_attempt_id is not None
            else None
        )
        dispatch_record = (
            read_dispatch_record_by_attempt_id(transaction, run.current_attempt_id)
            if run.current_attempt_id is not None
            else None
        )
        return _SupportedSessionCancelTarget(
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
            active_worker=False,
            waiting=False,
            recovering=True,
        )
    if run.status not in (RunStatus.RUNNING, RunStatus.CANCELLING):
        return None
    if run.current_attempt_id is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Active Run has no current Attempt",
            retryable=False,
        )
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, run.current_attempt_id
    )
    if attempt is None or dispatch_record is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Active Run current Attempt or dispatch record is missing",
            retryable=False,
        )
    if (
        run.status == RunStatus.RUNNING
        and attempt.status == AttemptStatus.STARTING
        and _dispatch_record_is_direct_cancelable(dispatch_record)
    ):
        return _SupportedSessionCancelTarget(
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
            active_worker=False,
            waiting=False,
            recovering=False,
        )
    if (
        run.status in (RunStatus.RUNNING, RunStatus.CANCELLING)
        and attempt.status == AttemptStatus.RUNNING
    ):
        return _SupportedSessionCancelTarget(
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
            active_worker=True,
            waiting=False,
            recovering=False,
        )
    return None


def _pending_dispatch_from_row(
    dispatch_record: DispatchRecordRow,
) -> PendingDispatchRecord:
    """把 durable dispatch row 转为 wakeup 摘要。

    :param dispatch_record: durable dispatch record row。
    :returns: pending dispatch 摘要。
    """

    return PendingDispatchRecord(
        dispatch_record_id=dispatch_record.dispatch_record_id,
        run_id=dispatch_record.run_id,
        attempt_id=dispatch_record.attempt_id,
        execution_id=dispatch_record.execution_id,
        execution_target=dispatch_record.execution_target,
        worker_kind=dispatch_record.worker_kind,
    )


def _wake_dispatch_if_needed(
    wakeup_port: AdmissionWakeupPort,
    pending_dispatch: PendingDispatchRecord | None,
    *,
    suppress_runtime_error: bool = False,
) -> None:
    """在 commit 后按需调用 dispatch wakeup。

    :param wakeup_port: wakeup 端口。
    :param pending_dispatch: pending dispatch 摘要。
    :param suppress_runtime_error: 是否把 wakeup ``RuntimeError`` 视为 best-effort。
    :returns: ``None``。
    """

    if pending_dispatch is not None:
        try:
            wakeup_port.wake_dispatch(pending_dispatch)
        except RuntimeError:
            if not suppress_runtime_error:
                raise


def _wake_start_governance_if_needed(
    wakeup_port: AdmissionWakeupPort, run: RunRow
) -> None:
    """accepted Run commit 后唤醒 pre-start governance。

    :param wakeup_port: wakeup 端口。
    :param run: 本次 admission 返回的 Run。
    :returns: ``None``。
    """

    if run.status == RunStatus.ACCEPTED:
        wakeup_port.wake_queue_promotion(run.session_id)


def _require_transition_run(run: RunRow | None) -> RunRow:
    """断言 transition 返回 Run row。

    :param run: transition 返回的 Run row。
    :returns: 非空 Run row。
    :raises HostApiError: Run 缺失时抛出。
    """

    if run is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Run transition returned no Run",
            retryable=False,
        )
    return run


def _require_transition_dispatch_record(
    dispatch_record: DispatchRecordRow | None,
) -> DispatchRecordRow:
    """断言 transition 返回 dispatch record。

    :param dispatch_record: transition 返回的 dispatch record。
    :returns: 非空 dispatch record。
    :raises HostApiError: dispatch record 缺失时抛出。
    """

    if dispatch_record is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Run transition returned no dispatch record",
            retryable=False,
        )
    return dispatch_record


def _require_event_sequence(
    transaction: HostTransaction, event_log_store: EventLogStore, event_id: str
) -> int:
    """按 event id 读取已追加 EventLog sequence。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param event_id: EventLog event id。
    :returns: event sequence。
    :raises HostApiError: event id 缺失或 sequence 类型异常时抛出。
    """

    event = event_log_store.read_event_by_id(transaction, event_id)
    if event is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="EventLog row is missing after append",
            retryable=False,
        )
    value = event.event_sequence
    if not isinstance(value, int):
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="EventLog sequence is invalid",
            retryable=False,
        )
    return value


def _require_event_sequence_if_present(
    transaction: HostTransaction, event_log_store: EventLogStore, event_id: str
) -> int | None:
    """按 event id 读取可选 EventLog sequence。

    active cancel 对已处于 ``CANCELLING`` 的 Run 不重复追加
    ``CANCEL_REQUESTED``，因此调用方生成的候选 event id 可能不存在。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param event_id: EventLog event id。
    :returns: event sequence；事件未写入时返回 ``None``。
    :raises HostApiError: sequence 类型异常时抛出。
    """

    event = event_log_store.read_event_by_id(transaction, event_id)
    if event is None:
        return None
    value = event.event_sequence
    if not isinstance(value, int):
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="EventLog sequence is invalid",
            retryable=False,
        )
    return value


def _raise_for_cancel_transition_status(
    result: DurableRunTransitionResult,
) -> None:
    """把 cancel transition status 映射为 API 错误。

    :param result: cancel transition 结果。
    :returns: ``None``。
    :raises HostApiError: status 为 not_found/invalid_state/cas_lost 时抛出。
    """

    if result.status == StateMutationStatus.UPDATED:
        return
    if result.status == StateMutationStatus.NOT_FOUND:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Run not found",
            retryable=False,
        )
    raise HostApiError(
        code=HostApiErrorCode.INVALID_STATE,
        message="Run state is not cancellable in Phase 5 admission",
        retryable=False,
    )


def _raise_for_session_cancel_transition_status(
    result: DurableRunTransitionResult,
) -> None:
    """把 session-scope cancel transition status 映射为 API 错误。

    :param result: cancel transition 结果。
    :returns: ``None``。
    :raises HostApiError: status 为 not_found/invalid_state/cas_lost 时抛出。
    """

    if result.status == StateMutationStatus.UPDATED:
        return
    if result.status == StateMutationStatus.NOT_FOUND:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Run not found during session cancel",
            retryable=False,
        )
    raise HostApiError(
        code=HostApiErrorCode.UNSUPPORTED_OPERATION,
        message="Run state is not supported by Phase 5 session cancel",
        retryable=False,
    )


def _raise_for_terminal_transition_status(
    result: DurableRunTransitionResult,
) -> None:
    """把 terminal transition status 映射为 API 错误。

    :param result: terminal transition 结果。
    :returns: ``None``。
    :raises HostApiError: status 为 not_found/invalid_state/cas_lost 时抛出。
    """

    if result.status == StateMutationStatus.UPDATED:
        return
    if result.status == StateMutationStatus.NOT_FOUND:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Run or Attempt not found",
            retryable=False,
        )
    raise HostApiError(
        code=HostApiErrorCode.INVALID_STATE,
        message="Run or Attempt state is not terminal-closeout eligible in Phase 3",
        retryable=False,
    )


def _start_run_semantic_digest(
    request: StartRunRequest, *, caller_semantic_digest: str
) -> str:
    """计算 start_run semantic digest。

    :param request: start_run request。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_START_RUN,
            "input_digest": _input_digest(request.input),
            "execution_target": request.execution_target,
            "queue_policy": serialize_run_queue_policy(
                parse_run_queue_policy(request.queue_policy)
            ),
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _followup_queue_semantic_digest(
    request: SubmitFollowupRequest, *, caller_semantic_digest: str
) -> str:
    """计算 submit_followup_queue semantic digest。

    :param request: follow-up request。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    :raises TypeError: RunnerSpec 中包含未知 provider request extension 时抛出。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_SUBMIT_FOLLOWUP_QUEUE,
            "prompt_digest": sha256_digest_json(
                {
                    "system_prompt": request.system_prompt,
                    "user_prompt": request.user_prompt,
                }
            ),
            "tool_names": (
                None
                if request.tool_names is None
                else _sorted_text_json_array(request.tool_names)
            ),
            "runner_spec": _optional_runner_spec_json(request.runner_spec),
            "runner_options": _optional_runner_options_json(request.runner_options),
            "agent_policy": _optional_agent_policy_json(request.agent_policy),
            "behavior": FollowupBehavior.QUEUE.value,
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _followup_steer_semantic_digest(
    request: SubmitFollowupRequest, *, caller_semantic_digest: str
) -> str:
    """计算 submit_followup_steer semantic digest。

    :param request: follow-up steer request。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_SUBMIT_FOLLOWUP_STEER,
            "prompt_digest": sha256_digest_json(
                {
                    "system_prompt": request.system_prompt,
                    "user_prompt": request.user_prompt,
                }
            ),
            "tool_names": (
                None
                if request.tool_names is None
                else _sorted_text_json_array(request.tool_names)
            ),
            "runner_spec": _optional_runner_spec_json(request.runner_spec),
            "runner_options": _optional_runner_options_json(request.runner_options),
            "agent_policy": _optional_agent_policy_json(request.agent_policy),
            "behavior": FollowupBehavior.STEER.value,
            "target_run_id": request.target_run_id,
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _retry_run_semantic_digest(
    run_id: str,
    request: RetryRunRequest,
    *,
    caller_semantic_digest: str,
) -> str:
    """计算 retry_run semantic digest。

    :param run_id: 源 Run id。
    :param request: retry 请求。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_RETRY_RUN,
            "source_run_id": run_id,
            "reason": request.reason,
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _replay_run_semantic_digest(
    run_id: str,
    request: ReplayRunRequest,
    *,
    caller_semantic_digest: str,
) -> str:
    """计算 replay_run semantic digest。

    :param run_id: 源 Run id。
    :param request: replay 请求。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_REPLAY_RUN,
            "source_run_id": run_id,
            "reason": request.reason,
            "repair_instruction": request.repair_instruction,
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _cancel_run_semantic_digest(
    request: CancelRunRequest, *, caller_semantic_digest: str
) -> str:
    """计算 cancel_run semantic digest。

    :param request: cancel run 请求。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_CANCEL_RUN,
            "reason": request.reason,
            "mode": request.mode.value,
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _cancel_session_runs_semantic_digest(
    session_id: str,
    request: CancelSessionRunsRequest,
    *,
    caller_semantic_digest: str,
) -> str:
    """计算 cancel_session_runs semantic digest。

    digest 不包含当前 Run 列表，避免幂等重放取消首次操作后新增的 Run。

    :param session_id: 目标 Session id。
    :param request: cancel session runs 请求。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_CANCEL_SESSION_RUNS,
            "session_id": session_id,
            "reason": request.reason,
            "mode": request.mode.value,
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _validate_closeout_attempt_terminal_input(
    closeout_input: CloseoutAttemptTerminalInput,
) -> None:
    """校验 admission terminal closeout 输入。

    :param closeout_input: 待校验 closeout 输入。
    :returns: ``None``。
    :raises ValueError: 字段为空、终态不是 Phase 3 支持集合或 Run/Attempt 不匹配时抛出。
    """

    _require_non_empty_text(closeout_input.run_id, field_name="run_id")
    _require_non_empty_text(closeout_input.attempt_id, field_name="attempt_id")
    allowed_pairs = (
        (AttemptStatus.SUCCEEDED, RunStatus.SUCCEEDED),
        (AttemptStatus.FAILED, RunStatus.FAILED),
        (AttemptStatus.LOST, RunStatus.LOST),
    )
    pair = (
        closeout_input.attempt_terminal_status,
        closeout_input.run_terminal_status,
    )
    if pair not in allowed_pairs:
        raise ValueError(
            "terminal closeout supports only succeeded, failed or lost matched statuses"
        )
    if closeout_input.terminal_summary_digest is not None:
        _require_sha256_digest(
            closeout_input.terminal_summary_digest,
            field_name="terminal_summary_digest",
        )
    if (
        closeout_input.terminal_summary_ref is not None
        and closeout_input.terminal_summary_ref.strip() == ""
    ):
        raise ValueError("terminal_summary_ref must be non-empty")


def _input_digest(input_value: HostInput) -> str:
    """计算 HostInput envelope digest。

    :param input_value: Host 输入 envelope。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "display_text": input_value.display_text,
            "payload_ref": input_value.payload_ref,
            "payload_digest": input_value.payload_digest,
        }
    )


def _call_context_digest(context: HostCallContext) -> str:
    """计算调用上下文 digest，排除 tracing request_id。

    :param context: Host call context。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(_call_context_json_value(context))


def _call_context_json_value(context: HostCallContext) -> JsonValue:
    """把调用上下文转为 JSON 值。

    :param context: Host call context。
    :returns: JSON 对象值。
    """

    return {
        "actor": context.actor,
        "source": context.source,
        "authorization_claims": _authorization_claims_json_value(
            context.authorization_claims
        ),
        "operation_context": _operation_context_json_value(context.operation_context),
    }


def _authorization_claims_json_value(
    claims: tuple[AuthorizationClaim, ...],
) -> JsonValue:
    """把授权声明转为 JSON 值。

    :param claims: 授权声明元组。
    :returns: JSON 数组值。
    """

    values: list[JsonValue] = []
    for claim in claims:
        values.append({"name": claim.name, "value": claim.value})
    return values


def _operation_context_json_value(context: OperationContext) -> JsonValue:
    """把操作上下文转为 JSON 值。

    :param context: 操作上下文。
    :returns: JSON 对象值。
    """

    return {
        "operation_name": context.operation_name,
        "operation_kind": context.operation_kind,
        "business_domain": context.business_domain,
        "business_object_type": context.business_object_type,
        "business_object_id": context.business_object_id,
        "scenario": context.scenario,
        "correlation_id": context.correlation_id,
    }
