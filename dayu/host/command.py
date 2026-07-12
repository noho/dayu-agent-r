"""Host public command handle 与 Session facade。

本模块是 Phase 4 public command path 的 Host composition root。它负责把
公共 handle options 映射到 durable store options，持有私有 durable store
和内部 service 依赖，并提供 Session / Run public facade；它不启动后台
supervisor，不实现 Engine dispatch、EventLog stream 或 purge。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection
from typing import NoReturn, Protocol
from uuid import uuid4

from dayu.contracts.json_value import JsonValue
from dayu.host.audit import (
    LogAuditSinkOptions,
    PurgeCompletedAuditRecordRequest,
    PurgeFailedAuditRecordRequest,
    PurgeStartedAuditRecordRequest,
    append_purge_completed_audit_record,
    append_purge_failed_audit_record,
    append_purge_started_audit_record,
    default_log_audit_sink_options,
)
from dayu.host.admission import (
    HostAdmissionService,
    PendingDispatchRecord,
    SubmitFollowupQueueAdmissionInput,
    create_host_admission_service,
)
from dayu.host.api import (
    AttemptStatus,
    AuthorizationClaim,
    CancelRunRequest,
    CancelSessionRunsRequest,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    FollowupSnapshot,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostCommandHandleOptions,
    HostInput,
    HostLocalExecutionOptions,
    OperationContext,
    PurgeSessionRequest,
    PurgeSessionResult,
    ReplayRunRequest,
    ResolveWaitRequest,
    RetryRunRequest,
    RunSnapshot,
    RunStatus,
    SessionSnapshot,
    StartRunRequest,
    SubmitFollowupRequest,
    _context_budget_policy_from_command_options,
)
from dayu.host._execution_config_projection import (
    optional_agent_policy_json as _optional_agent_policy_json,
    optional_runner_options_json as _optional_runner_options_json,
    optional_runner_spec_json as _optional_runner_spec_json,
)
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_json
from dayu.host.durable.connection import (
    HostDurableStore,
    open_host_durable_store,
)
from dayu.host.durable.errors import (
    HostDurableConfigError,
    HostDurableError,
    HostForeignKeyError,
    HostIdempotencyConflictError,
    HostTransactionBusyError,
    HostTransactionRetryExhaustedError,
    HostUniqueConstraintError,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.purge import (
    PurgeSessionAlreadyPurgedError,
    PurgeSessionDeleteRequest,
    PurgeSessionDeleteResult,
    PurgeSessionInvalidStateError,
    PurgeSessionNotFoundError,
    build_purge_tombstone_id,
    build_purge_semantic_digest,
    purge_session_durable,
)
from dayu.host.durable.session_lifecycle import (
    close_session as _close_session_in_durable,
    create_session as _create_session_in_durable,
    ensure_session as _ensure_session_in_durable,
)
from dayu.host.durable.state import (
    DispatchRecordRow,
    WaitRecordRow,
    WaitRecordStatus,
    read_run_by_id,
    read_wait_record_by_id,
    run_snapshot_from_row,
)
from dayu.host.durable.transaction import (
    HostReadTransactionOperation,
    HostTransaction,
    HostTransactionOperation,
    HostTransactionRunner,
    T,
)
from dayu.host.dispatch import (
    ActiveCancelMessage,
    ActiveWorkerCancelPort,
    ActiveWorkerRegistry,
)
from dayu.host.projection import catch_up_projection_best_effort
from dayu.host.wait_callback import (
    CallbackWaitResolveResult,
    CallbackWaitResolvePort,
    WaitCallbackStateReadPort,
    WaitCallbackStoredWaitState,
    WaitCallbackStoredWaitStatus,
)
from dayu.host.waiting import (
    DefaultHostResolveWaitService,
    ExpireWaitInput,
    ExpireWaitResult,
)
from dayu.runtime.filelock import RuntimeFileLockError
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_GENERATED_HANDLE_ID_PREFIX = "host-command"
_LOGGER = logging.getLogger(__name__)
_OPERATION_CREATE_SESSION = "create_session"
_OPERATION_CLOSE_SESSION = "close_session"
_OPERATION_START_RUN = "start_run"
_OPERATION_SUBMIT_FOLLOWUP = "submit_followup"
_OPERATION_CANCEL_RUN = "cancel_run"
_OPERATION_CANCEL_SESSION_RUNS = "cancel_session_runs"
_OPERATION_RETRY_RUN = "retry_run"
_OPERATION_REPLAY_RUN = "replay_run"
_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET = "host-public-followup-default"
_PURGE_FAILURE_STAGE_PRECONDITION_CHECK = "precondition_check"
_PURGE_FAILURE_STAGE_ALREADY_PURGED = "already_purged"
_PURGE_FAILURE_STAGE_NOT_FOUND = "not_found"
_PURGE_FAILURE_STAGE_IDEMPOTENCY_CONFLICT = "idempotency_conflict"
_PURGE_FAILURE_STAGE_SQLITE_TRANSACTION = "sqlite_purge_transaction"


class ActiveCancelWatchdogWakeupPort(Protocol):
    """active cancel watchdog commit 后唤醒端口。

    该端口只表达低延迟 wakeup，不拥有 durable cancel truth。
    """

    def wake_active_cancel_watchdog(self) -> None:
        """唤醒 active cancel watchdog。

        :returns: ``None``。
        """

        ...


class HostCommandHandle:
    """Host public command handle。

    :param host_handle_id: 稳定诊断 handle id。
    :param durable_store: 当前 handle 私有持有的 durable store。
    :param admission_service: 当前 handle 私有持有的内部 admission service。
    :param active_registry: 当前 handle 用于 active worker cancel 传播的 registry。
    :param active_cancel_watchdog_wakeup_port: active cancel commit 后的可选
        watchdog wakeup 端口；无后台 scheduler 的低层组装可为 ``None``。
    """

    __slots__ = (
        "_admission_service",
        "_active_registry",
        "_active_cancel_watchdog_wakeup_port",
        "_closed",
        "_durable_store",
        "_host_handle_id",
    )

    def __init__(
        self,
        *,
        host_handle_id: str,
        durable_store: HostDurableStore,
        admission_service: HostAdmissionService,
        active_registry: ActiveWorkerCancelPort,
        active_cancel_watchdog_wakeup_port: ActiveCancelWatchdogWakeupPort | None = None,
    ) -> None:
        """初始化 Host command handle。

        :param host_handle_id: 稳定诊断 handle id。
        :param durable_store: 已打开的 Host durable store。
        :param admission_service: 内部 admission service 依赖。
        :param active_registry: active worker cancel 传播 registry。
        :param active_cancel_watchdog_wakeup_port: active cancel watchdog wakeup
            端口；无后台 scheduler 时为 ``None``。
        :returns: 无返回值。
        :raises ValueError: ``host_handle_id`` 为空时抛出。
        """

        if host_handle_id.strip() == "":
            raise ValueError("host_handle_id must be non-empty")
        self._host_handle_id = host_handle_id
        self._durable_store = durable_store
        self._admission_service = admission_service
        self._active_registry = active_registry
        self._active_cancel_watchdog_wakeup_port = active_cancel_watchdog_wakeup_port
        self._closed = False

    @property
    def host_handle_id(self) -> str:
        """返回 Host command handle 的稳定诊断 id。

        :returns: command handle id。
        """

        return self._host_handle_id

    def close(self) -> None:
        """关闭 Host command handle 持有的 durable store。

        :returns: 无返回值。
        """

        if self._closed:
            return
        self._durable_store.close()
        self._closed = True

    def _transaction_runner(self) -> HostTransactionRunner:
        """返回私有 transaction runner。

        :returns: Host transaction runner。
        :raises HostApiError: handle 已关闭时抛出。
        """

        self._raise_if_closed()
        try:
            return self._durable_store.transaction_runner
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc

    def _audit_sink_options(self) -> LogAuditSinkOptions:
        """从当前 handle 持有的 durable store 派生 audit sink options。

        :returns: append-only audit JSONL sink options。
        :raises HostApiError: handle 已关闭或 durable store 配置不可读取时抛出。
        """

        self._raise_if_closed()
        try:
            options = self._durable_store.options
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc
        return default_log_audit_sink_options(
            options.payload_policy.artifact_root,
            create_parent_dirs=options.payload_policy.create_artifact_root,
        )

    def _db_path(self) -> Path:
        """返回当前 handle 持有的 Host durable SQLite DB 路径。

        :returns: durable SQLite DB 文件路径。
        :raises HostApiError: handle 已关闭或 durable store 配置不可读取时抛出。
        """

        self._raise_if_closed()
        try:
            return self._durable_store.options.db_path
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc

    def _artifact_root(self) -> Path:
        """返回当前 handle 持有的 Host artifact root 路径。

        :returns: artifact root 路径。
        :raises HostApiError: handle 已关闭或 durable store 配置不可读取时抛出。
        """

        self._raise_if_closed()
        try:
            return self._durable_store.options.payload_policy.artifact_root
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc

    def _open_durable_connection(self) -> Connection:
        """打开一条独立 Host durable SQLite connection。

        调用方负责关闭返回的 connection。该 accessor 只委托当前 handle 持有的
        durable store，不进入 command transaction，供 WAL checkpoint 等
        connection-level maintenance primitive 使用。

        :returns: 已配置并校验 schema 的独立 SQLite connection。
        :raises HostApiError: handle 已关闭或 durable connection 打开失败时抛出。
        """

        self._raise_if_closed()
        try:
            return self._durable_store.connect()
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc

    def _run_read(self, operation: HostReadTransactionOperation[T]) -> T:
        """在 handle 私有 store 上执行 read transaction。

        :param operation: read transaction body。
        :returns: operation 返回值。
        :raises HostApiError: handle 已关闭或 durable 读取失败时抛出。
        """

        try:
            return self._transaction_runner().run_read(operation)
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc

    def _run_write(self, operation: HostTransactionOperation[T]) -> T:
        """在 handle 私有 store 上执行 write transaction。

        :param operation: write transaction body。
        :returns: operation 返回值。
        :raises HostApiError: handle 已关闭或 durable 写入失败时抛出。
        """

        try:
            return self._transaction_runner().run_write(operation)
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc

    def _raise_if_closed(self) -> None:
        """检查 handle 是否已经关闭。

        :returns: 无返回值。
        :raises HostApiError: handle 已关闭时抛出。
        """

        if self._closed:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="Host command handle is closed",
                retryable=False,
            )


def create_host_command_handle(
    options: HostCommandHandleOptions,
    *,
    active_registry: ActiveWorkerCancelPort | None = None,
) -> HostCommandHandle:
    """创建 Host public command handle。

    :param options: Host command handle 公共构造选项。
    :param active_registry: active worker registry；不传时为当前 handle 创建新 registry。
    :returns: 已打开 durable store 并装配内部依赖的 ``HostCommandHandle``。
    :raises ValueError: ``local_execution`` 非空时抛出；scheduler 需显式异步装配。
    :raises HostApiError: durable store 配置、打开或 schema bootstrap 失败时抛出。
    """

    if options.local_execution is not None:
        raise ValueError(
            "HostCommandHandleOptions.local_execution is not supported by "
            "create_host_command_handle; open HostDispatchScheduler explicitly"
        )
    durable_options = _durable_options_from_public_options(options)
    try:
        durable_store = open_host_durable_store(durable_options)
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    try:
        admission_service = create_host_admission_service(durable_store.transaction_runner)
        return HostCommandHandle(
            host_handle_id=_host_handle_id_from_options(options),
            durable_store=durable_store,
            admission_service=admission_service,
            active_registry=(active_registry if active_registry is not None else ActiveWorkerRegistry()),
        )
    except HostDurableError as exc:
        durable_store.close()
        raise _host_api_error_from_durable_error(exc) from exc
    except Exception:
        durable_store.close()
        raise


def compose_host_local_execution_options(
    options: HostCommandHandleOptions,
) -> HostLocalExecutionOptions | None:
    """从 command handle options 归一化本地执行配置。

    本函数是 Host composition root 的 typed wiring 边界：Context Governance
    budget policy 只从 ``HostCommandHandleOptions`` 的显式字段构造，不读取
    Engine spec、per-run metadata、caller payload 或 provider overflow event。

    :param options: Host command handle options。
    :returns: 带 typed context budget policy 的本地执行配置；未配置本地执行时为
        ``None``。
    """

    if options.local_execution is None:
        return None
    context_budget_policy = (
        options.local_execution.context_budget_policy
        if options.local_execution.context_budget_policy is not None
        else _context_budget_policy_from_command_options(options)
    )
    return replace(
        options.local_execution,
        context_budget_policy=context_budget_policy,
        compact_artifact_root=options.artifact_root,
        compact_artifact_create_parent_dirs=options.create_parent_dirs,
    )


def ensure_session(host: HostCommandHandle, request: EnsureSessionRequest) -> SessionSnapshot:
    """确保 slot 绑定到一个 Session，并返回 Session snapshot。

    :param host: Host command handle。
    :param request: ensure session 请求。
    :returns: durable truth 生成的 Session snapshot。
    :raises HostApiError: handle 已关闭或 durable session 不一致时抛出。
    """

    try:
        result = _ensure_session_in_durable(host._transaction_runner(), request)
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    catch_up_projection_best_effort(host._admission_service.projection_catchup_port)
    return result.snapshot


def create_session(host: HostCommandHandle, request: CreateSessionRequest) -> SessionSnapshot:
    """显式创建 Session，并返回 Session snapshot。

    Phase 4 public facade 的幂等语义不把 ``metadata`` 作为 semantic
    digest 输入；当前实现也不会把 ``metadata`` 写入 durable Session
    row。metadata 持久化语义若需要对外承诺，必须先进入设计与 plan。

    :param host: Host command handle。
    :param request: create session 请求。
    :returns: durable truth 生成的 Session snapshot；幂等重放返回既有 Session。
    :raises HostApiError: handle 已关闭或幂等 digest 冲突时抛出。
    """

    caller_digest = _create_session_public_semantic_digest(request)
    durable_request = _request_without_create_metadata(request)
    try:
        result = _create_session_in_durable(
            host._transaction_runner(),
            durable_request,
            caller_semantic_digest=caller_digest,
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    catch_up_projection_best_effort(host._admission_service.projection_catchup_port)
    return result.snapshot


def close_session(
    host: HostCommandHandle,
    session_id: str,
    request: CloseSessionRequest,
) -> SessionSnapshot:
    """关闭 open Session，并返回 Session snapshot。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :param request: close session 请求。
    :returns: durable truth 生成的 Session snapshot；幂等重放返回既有 Session。
    :raises HostApiError: handle 已关闭、Session 缺失、状态非法或幂等冲突时抛出。
    """

    caller_digest = _close_session_public_semantic_digest(session_id=session_id, request=request)
    try:
        result = _close_session_in_durable(
            host._transaction_runner(),
            session_id,
            request,
            caller_semantic_digest=caller_digest,
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    catch_up_projection_best_effort(host._admission_service.projection_catchup_port)
    return result.snapshot


def start_run(host: HostCommandHandle, request: StartRunRequest) -> RunSnapshot:
    """启动独立 Run，并返回 Run snapshot。

    :param host: Host command handle。
    :param request: start run 请求。
    :returns: durable truth 生成的 Run snapshot。
    :raises HostApiError: handle 已关闭、Session 状态非法、active reject 或幂等冲突时抛出。
    """

    host._raise_if_closed()
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        "host.command.accepted operation=start_run session_id=%s",
        request.session_id,
    )
    try:
        result = host._admission_service.start_run(
            request,
            caller_semantic_digest=_start_run_public_semantic_digest(request),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        ("host.command.committed operation=start_run session_id=%s " "run_id=%s run_status=%s input_event_id=%s"),
        result.run.session_id,
        result.run.run_id,
        result.run.status.value,
        result.run.input_event_id,
    )
    return run_snapshot_from_row(result.run)


def submit_followup(
    host: HostCommandHandle,
    session_id: str,
    request: SubmitFollowupRequest,
) -> FollowupSnapshot:
    """提交同一 Session 的后续输入。

    :param host: Host command handle。
    :param session_id: 调用路径中的目标 Session id。
    :param request: follow-up 请求。
    :returns: follow-up 接受结果 snapshot。
    :raises HostApiError: session id 不一致、admission 失败或幂等冲突时抛出。
    """

    host._raise_if_closed()
    if session_id != request.session_id:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="submit_followup session_id does not match request",
            retryable=False,
        )
    if request.behavior == FollowupBehavior.STEER:
        return _submit_followup_steer(host, request)
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        "host.command.accepted operation=submit_followup session_id=%s",
        request.session_id,
    )
    try:
        result = host._admission_service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=request,
                resolved_execution_target=(_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET),
            ),
            caller_semantic_digest=_submit_followup_public_semantic_digest(request),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        ("host.command.committed operation=submit_followup session_id=%s " "run_id=%s run_status=%s input_event_id=%s"),
        result.run.session_id,
        result.run.run_id,
        result.run.status.value,
        result.run.input_event_id,
    )
    return FollowupSnapshot(
        accepted_input_ref=result.run.input_event_id,
        behavior=FollowupBehavior.QUEUE,
        accepted_run_id=result.run.run_id,
        accepted_run_status=result.run.status,
        command_watermark=run_snapshot_from_row(result.run).event_cursor,
        queued_run_id=(result.run.run_id if result.run.status == RunStatus.QUEUED else None),
        target_run_id=None,
    )


def _submit_followup_steer(host: HostCommandHandle, request: SubmitFollowupRequest) -> FollowupSnapshot:
    """提交 steer follow-up 并返回 public snapshot。

    :param host: Host command handle。
    :param request: steer follow-up 请求。
    :returns: follow-up 接受结果 snapshot。
    :raises HostApiError: admission 失败或 durable 写入失败时抛出。
    """

    try:
        result = host._admission_service.submit_followup_steer(
            request,
            caller_semantic_digest=_submit_followup_public_semantic_digest(request),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    if result.steered_cancel_target is not None:
        _propagate_active_cancel_targets(
            host,
            (
                ActiveCancelMessage(
                    run_id=result.steered_cancel_target.run_id,
                    attempt_id=result.steered_cancel_target.attempt_id,
                    execution_id=result.steered_cancel_target.execution_id,
                    reason=result.steered_cancel_target.reason,
                ),
            ),
        )
    return FollowupSnapshot(
        accepted_input_ref=result.input_event_id,
        behavior=FollowupBehavior.STEER,
        accepted_run_id=result.run.run_id,
        accepted_run_status=result.run.status,
        command_watermark=run_snapshot_from_row(result.run).event_cursor,
        queued_run_id=None,
        target_run_id=result.run.run_id,
    )


def cancel_run(host: HostCommandHandle, run_id: str, request: CancelRunRequest) -> RunSnapshot:
    """取消单个 Run，并返回最新 Run snapshot。

    当前覆盖 queued、pre-dispatch ``STARTING``、pre-accept dispatching、
    active worker、``WAITING`` 与 ``RECOVERING``。

    :param host: Host command handle。
    :param run_id: 目标 Run id。
    :param request: cancel run 请求。
    :returns: durable truth 生成的 Run snapshot。
    :raises HostApiError: Run 缺失、幂等冲突、真实非法前置或 deferred 状态未支持时抛出。
    """

    host._raise_if_closed()
    try:
        result = host._admission_service.cancel_run(
            run_id,
            request,
            caller_semantic_digest=_cancel_run_public_semantic_digest(
                run_id=run_id,
                request=request,
            ),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    _propagate_active_cancel_targets(
        host,
        (
            (
                ActiveCancelMessage(
                    run_id=result.active_cancel_target.run_id,
                    attempt_id=result.active_cancel_target.attempt_id,
                    execution_id=result.active_cancel_target.execution_id,
                    reason=result.active_cancel_target.reason,
                ),
            )
            if result.active_cancel_target is not None
            else ()
        ),
    )
    return run_snapshot_from_row(result.run)


def cancel_session_runs(
    host: HostCommandHandle,
    session_id: str,
    request: CancelSessionRunsRequest,
) -> SessionSnapshot:
    """取消指定 Session 下当前支持子集中的所有非终态 Run。

    当前覆盖 queued、pre-dispatch ``STARTING``、pre-accept dispatching、
    active worker、``WAITING`` 与 ``RECOVERING``。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :param request: cancel session runs 请求。
    :returns: cancel 后的 Session snapshot。
    :raises HostApiError: Session 缺失、幂等冲突或存在 unsupported non-terminal Run 时抛出。
    """

    host._raise_if_closed()
    try:
        result = host._admission_service.cancel_session_runs(
            session_id,
            request,
            caller_semantic_digest=_cancel_session_runs_public_semantic_digest(
                session_id=session_id,
                request=request,
            ),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    _propagate_active_cancel_targets(
        host,
        tuple(
            ActiveCancelMessage(
                run_id=target.run_id,
                attempt_id=target.attempt_id,
                execution_id=target.execution_id,
                reason=target.reason,
            )
            for target in result.active_cancel_targets
        ),
    )
    return result.snapshot


def retry_run(host: HostCommandHandle, run_id: str, request: RetryRunRequest) -> RunSnapshot:
    """重试普通本地 FAILED 源 Run，并返回关联新 Run snapshot。

    :param host: Host command handle。
    :param run_id: 源 Run id。
    :param request: retry run 请求。
    :returns: 关联新 Run snapshot。
    :raises HostApiError: handle 已关闭、源 Run 状态非法、幂等冲突或 policy limit
        命中时抛出。
    """

    host._raise_if_closed()
    try:
        result = host._admission_service.retry_run(
            run_id,
            request,
            caller_semantic_digest=_retry_run_public_semantic_digest(
                run_id=run_id,
                request=request,
            ),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    return run_snapshot_from_row(result.run)


def replay_run(host: HostCommandHandle, run_id: str, request: ReplayRunRequest) -> RunSnapshot:
    """对 SUCCEEDED 源 Run 创建 no-tool 结构修复 replay Run。

    :param host: Host command handle。
    :param run_id: 源 Run id。
    :param request: replay run 请求。
    :returns: 关联新 Run snapshot。
    :raises HostApiError: handle 已关闭、源 Run 状态非法或幂等冲突时抛出。
    """

    host._raise_if_closed()
    try:
        result = host._admission_service.replay_run(
            run_id,
            request,
            caller_semantic_digest=_replay_run_public_semantic_digest(
                run_id=run_id,
                request=request,
            ),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    return run_snapshot_from_row(result.run)


def resolve_wait(host: HostCommandHandle, wait_id: str, request: ResolveWaitRequest) -> RunSnapshot:
    """接收 wait result 并返回最新 Run snapshot。

    :param host: Host command handle。
    :param wait_id: 待接收结果的 wait id。
    :param request: resolve wait 请求。
    :returns: 最新 Run snapshot。
    :raises HostApiError: handle 已关闭、wait 缺失、状态非法或幂等冲突时抛出。
    """

    host._raise_if_closed()
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        "host.command.accepted operation=resolve_wait wait_id=%s",
        wait_id,
    )
    try:
        transaction_runner = host._transaction_runner()
        service = DefaultHostResolveWaitService(
            transaction_runner=transaction_runner,
            event_log_store=host._admission_service.event_log_store,
            idempotency_store=host._admission_service.idempotency_store,
            projection_catchup_port=(host._admission_service.projection_catchup_port),
            queue_promotion_wakeup_port=host._admission_service.wakeup_port,
        )
        result = service.resolve_wait(wait_id, request)
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    if result.dispatch_record is not None and not result.idempotent_replay:
        host._admission_service.wakeup_port.wake_dispatch(_pending_dispatch_from_row(result.dispatch_record))
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        (
            "host.command.committed operation=resolve_wait session_id=%s "
            "run_id=%s run_status=%s wait_id=%s dispatch_record_id=%s"
        ),
        result.run.session_id,
        result.run.run_id,
        result.run.status.value,
        wait_id,
        None if result.dispatch_record is None else result.dispatch_record.dispatch_record_id,
    )
    return run_snapshot_from_row(result.run)


def expire_wait(host: HostCommandHandle, request: ExpireWaitInput) -> ExpireWaitResult:
    """通过 command handle 执行 Host-internal wait expiry。

    :param host: poll round 私有 Host command handle。
    :param request: expiry owner 输入。
    :returns: expiry transition 结果。
    :raises HostApiError: handle 已关闭、wait 缺失或边界无效时抛出。
    :raises HostDurableError: durable transition 失败时转换或透传。
    """

    host._raise_if_closed()
    try:
        service = DefaultHostResolveWaitService(
            transaction_runner=host._transaction_runner(),
            event_log_store=host._admission_service.event_log_store,
            idempotency_store=host._admission_service.idempotency_store,
            projection_catchup_port=host._admission_service.projection_catchup_port,
            queue_promotion_wakeup_port=host._admission_service.wakeup_port,
        )
        return service.expire_wait(request)
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc


@dataclass(frozen=True, slots=True)
class HostCommandWaitCallbackPort(CallbackWaitResolvePort, WaitCallbackStateReadPort):
    """Host command handle 上的 wait callback port 实现。

    :param host: Host command handle。
    """

    host: HostCommandHandle

    def read_wait_state(self, wait_id: str) -> WaitCallbackStoredWaitState | None:
        """读取 wait record 的 callback 稳定状态投影。

        :param wait_id: wait record id。
        :returns: 找到时返回 callback wait state；不存在时返回 ``None``。
        :raises HostApiError: handle 已关闭或 durable 读取失败时抛出。
        """

        self.host._raise_if_closed()
        try:
            return self.host._transaction_runner().run_read(
                lambda transaction: _callback_wait_state_from_status(
                    read_wait_record_by_id(transaction, wait_id)
                )
            )
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc

    def resolve_callback_wait(
        self,
        wait_id: str,
        request: ResolveWaitRequest,
        context: HostCallContext,
    ) -> CallbackWaitResolveResult:
        """通过 command-layer 语义处理 callback wait resolve。

        :param wait_id: wait record id。
        :param request: callback 转换出的 resolve wait request。
        :param context: Host 调用上下文；必须与 request.context 同一对象。
        :returns: 最新 Run snapshot 与 replay 标志。
        :raises HostApiError: handle 已关闭、wait 缺失、状态非法或幂等冲突时抛出。
        """

        self.host._raise_if_closed()
        if context is not request.context:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="callback resolve context must match request context",
                retryable=False,
            )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.command.accepted operation=resolve_callback_wait wait_id=%s",
            wait_id,
        )
        try:
            transaction_runner = self.host._transaction_runner()
            service = DefaultHostResolveWaitService(
                transaction_runner=transaction_runner,
                event_log_store=self.host._admission_service.event_log_store,
                idempotency_store=self.host._admission_service.idempotency_store,
                projection_catchup_port=(
                    self.host._admission_service.projection_catchup_port
                ),
                queue_promotion_wakeup_port=(
                    self.host._admission_service.wakeup_port
                ),
            )
            result = service.resolve_wait(wait_id, request)
        except HostDurableError as exc:
            raise _host_api_error_from_durable_error(exc) from exc
        if result.dispatch_record is not None and not result.idempotent_replay:
            self.host._admission_service.wakeup_port.wake_dispatch(
                _pending_dispatch_from_row(result.dispatch_record)
            )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            (
                "host.command.committed operation=resolve_callback_wait "
                "session_id=%s run_id=%s run_status=%s wait_id=%s "
                "dispatch_record_id=%s idempotent_replay=%s"
            ),
            result.run.session_id,
            result.run.run_id,
            result.run.status.value,
            wait_id,
            None
            if result.dispatch_record is None
            else result.dispatch_record.dispatch_record_id,
            result.idempotent_replay,
        )
        return CallbackWaitResolveResult(
            run=run_snapshot_from_row(result.run),
            idempotent_replay=result.idempotent_replay,
        )


def _callback_wait_state_from_status(
    row: WaitRecordRow | None,
) -> WaitCallbackStoredWaitState | None:
    """把 durable wait record row 投影为 callback wait state。

    :param row: durable wait record row；不存在时为 ``None``。
    :returns: callback wait state；不存在时返回 ``None``。
    :raises ValueError: wait status 未被 callback contract 覆盖时抛出。
    """

    if row is None:
        return None
    return WaitCallbackStoredWaitState(
        status=_callback_wait_status(row.status),
        deadline_at=row.deadline_at,
        expires_at=row.expires_at,
    )


def _callback_wait_status(status: WaitRecordStatus) -> WaitCallbackStoredWaitStatus:
    """把 durable wait status 映射为 callback wait status。

    :param status: durable wait status。
    :returns: callback wait status。
    :raises ValueError: 未知 durable wait status 时抛出。
    """

    if status is WaitRecordStatus.WAITING:
        return WaitCallbackStoredWaitStatus.WAITING
    if status is WaitRecordStatus.RESOLVED:
        return WaitCallbackStoredWaitStatus.RESOLVED
    if status is WaitRecordStatus.FAILED:
        return WaitCallbackStoredWaitStatus.FAILED
    if status is WaitRecordStatus.CANCELLED:
        return WaitCallbackStoredWaitStatus.CANCELLED
    if status is WaitRecordStatus.LOST:
        return WaitCallbackStoredWaitStatus.LOST
    raise ValueError("unsupported wait record status")


@dataclass(frozen=True, slots=True)
class _PurgeAuditInputs:
    """purge command path 的 deterministic audit 输入。

    :param tombstone_id: deterministic purge tombstone id。
    :param session_id: 目标 Session id。
    :param client_request_id: purge 请求幂等 key。
    :param semantic_request_digest: purge semantic digest。
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
    operation_context_digest: str
    operation_context_refs: Mapping[str, JsonValue]
    reason: str
    request_context: Mapping[str, JsonValue]


def purge_session(
    host: HostCommandHandle,
    session_id: str,
    request: PurgeSessionRequest,
) -> PurgeSessionResult:
    """清理已关闭 Session 的 Host 本地可恢复事实。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :param request: purge session 请求。
    :returns: purge tombstone 与删除计数摘要组成的 public result。
    purge command path 直接写 JSONL 是 purge 专用例外：目标 EventLog facts
    会在 destructive transaction 内被删除，不能依赖普通 EventLog audit
    projection 事后生成 purge 流水。该例外不得扩散为通用 command audit 模式。

    :raises HostApiError: handle 已关闭、Session 缺失、前置条件非法、幂等冲突、
        已由不同请求 purge、durable 写入失败或 purge audit append 失败时抛出。
    """

    host._raise_if_closed()
    audit_sink_options = host._audit_sink_options()
    audit_inputs = _build_purge_audit_inputs(session_id=session_id, request=request)
    try:
        started_audit = append_purge_started_audit_record(
            audit_sink_options,
            PurgeStartedAuditRecordRequest(
                tombstone_id=audit_inputs.tombstone_id,
                session_id=audit_inputs.session_id,
                client_request_id=audit_inputs.client_request_id,
                semantic_request_digest=audit_inputs.semantic_request_digest,
                actor=audit_inputs.actor,
                source=audit_inputs.source,
                operation_context_digest=audit_inputs.operation_context_digest,
                operation_context_refs=audit_inputs.operation_context_refs,
                reason=audit_inputs.reason,
                request_context=audit_inputs.request_context,
            ),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    except (OSError, RuntimeFileLockError) as exc:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Host purge audit append failed",
            retryable=True,
        ) from exc

    try:
        operation = _PurgeSessionOperation(
            audit_inputs=audit_inputs,
            started_audit_record_ref=started_audit.audit_record_ref,
            started_audit_record_digest=started_audit.audit_record_digest,
        )
        result = host._transaction_runner().run_write(operation)
    except PurgeSessionInvalidStateError as exc:
        _append_purge_failed_best_effort(
            audit_sink_options,
            audit_inputs,
            failure_stage=_PURGE_FAILURE_STAGE_PRECONDITION_CHECK,
            error=exc,
        )
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="purge_session requires a closed Session with terminal Runs",
            retryable=False,
        ) from exc
    except PurgeSessionAlreadyPurgedError as exc:
        _append_purge_failed_best_effort(
            audit_sink_options,
            audit_inputs,
            failure_stage=_PURGE_FAILURE_STAGE_ALREADY_PURGED,
            error=exc,
        )
        raise HostApiError(
            code=HostApiErrorCode.CONFLICT,
            message="Session has already been purged",
            retryable=False,
        ) from exc
    except PurgeSessionNotFoundError as exc:
        _append_purge_failed_best_effort(
            audit_sink_options,
            audit_inputs,
            failure_stage=_PURGE_FAILURE_STAGE_NOT_FOUND,
            error=exc,
        )
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Session not found",
            retryable=False,
        ) from exc
    except HostIdempotencyConflictError as exc:
        _append_purge_failed_best_effort(
            audit_sink_options,
            audit_inputs,
            failure_stage=_PURGE_FAILURE_STAGE_IDEMPOTENCY_CONFLICT,
            error=exc,
        )
        raise _host_api_error_from_durable_error(exc) from exc
    except HostDurableError as exc:
        _append_purge_failed_best_effort(
            audit_sink_options,
            audit_inputs,
            failure_stage=_PURGE_FAILURE_STAGE_SQLITE_TRANSACTION,
            error=exc,
        )
        raise _host_api_error_from_durable_error(exc) from exc

    try:
        append_purge_completed_audit_record(
            audit_sink_options,
            PurgeCompletedAuditRecordRequest(
                tombstone=result.tombstone,
                semantic_request_digest=audit_inputs.semantic_request_digest,
            ),
        )
    except (OSError, RuntimeFileLockError) as exc:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Host purge completed audit append failed",
            retryable=True,
        ) from exc
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    return PurgeSessionResult(
        session_id=result.tombstone.session_id,
        purged=True,
        purge_tombstone_ref=result.tombstone.tombstone_id,
        deleted_counts_digest=result.tombstone.deleted_counts_digest,
    )


@dataclass(frozen=True, slots=True)
class _PurgeSessionOperation:
    """purge_session write transaction body。"""

    audit_inputs: _PurgeAuditInputs
    started_audit_record_ref: str
    started_audit_record_digest: str

    def __call__(self, transaction: HostTransaction) -> PurgeSessionDeleteResult:
        """执行 purge durable helper。

        :param transaction: 当前 Host write transaction。
        :returns: durable purge delete result。
        :raises HostDurableError: purge 前置条件、幂等或 durable 写入失败时抛出。
        """

        return purge_session_durable(
            transaction,
            PurgeSessionDeleteRequest(
                session_id=self.audit_inputs.session_id,
                client_request_id=self.audit_inputs.client_request_id,
                semantic_request_digest=self.audit_inputs.semantic_request_digest,
                actor=self.audit_inputs.actor,
                source=self.audit_inputs.source,
                operation_context_digest=self.audit_inputs.operation_context_digest,
                operation_context_refs=self.audit_inputs.operation_context_refs,
                reason=self.audit_inputs.reason,
                purged_at=format_utc_timestamp(datetime.now(UTC)),
                started_audit_record_ref=self.started_audit_record_ref,
                started_audit_record_digest=self.started_audit_record_digest,
                request_context=self.audit_inputs.request_context,
            ),
        )


def _build_purge_audit_inputs(
    *, session_id: str, request: PurgeSessionRequest
) -> _PurgeAuditInputs:
    """构造 purge command path 的 deterministic audit 输入。

    :param session_id: 目标 Session id。
    :param request: purge session 请求。
    :returns: purge audit 输入。
    :raises HostDurableError: semantic digest 或 tombstone id 输入非法时抛出。
    """

    operation_context_refs = _operation_context_json_value(
        request.context.operation_context
    )
    request_context = _call_context_json_value(request.context)
    operation_context_digest = sha256_digest_json(operation_context_refs)
    semantic_digest = build_purge_semantic_digest(
        session_id=session_id,
        reason=request.reason,
        operation_context_digest=operation_context_digest,
        operation_context_refs=operation_context_refs,
        request_context=request_context,
    )
    tombstone_id = build_purge_tombstone_id(
        session_id,
        request.client_request_id,
        semantic_digest,
    )
    return _PurgeAuditInputs(
        tombstone_id=tombstone_id,
        session_id=session_id,
        client_request_id=request.client_request_id,
        semantic_request_digest=semantic_digest,
        actor=request.context.actor,
        source=request.context.source,
        operation_context_digest=operation_context_digest,
        operation_context_refs=operation_context_refs,
        reason=request.reason,
        request_context=request_context,
    )


def _append_purge_failed_best_effort(
    options: LogAuditSinkOptions,
    audit_inputs: _PurgeAuditInputs,
    *,
    failure_stage: str,
    error: Exception,
) -> None:
    """best-effort 追加 purge_failed audit line。

    :param options: audit JSONL sink options。
    :param audit_inputs: deterministic purge audit 输入。
    :param failure_stage: 稳定失败阶段。
    :param error: 原始 transaction 错误。
    :returns: ``None``。
    :raises: 无；failed audit append 失败只记录 warning。
    """

    try:
        append_purge_failed_audit_record(
            options,
            PurgeFailedAuditRecordRequest(
                tombstone_id=audit_inputs.tombstone_id,
                session_id=audit_inputs.session_id,
                client_request_id=audit_inputs.client_request_id,
                semantic_request_digest=audit_inputs.semantic_request_digest,
                actor=audit_inputs.actor,
                source=audit_inputs.source,
                operation_context_digest=audit_inputs.operation_context_digest,
                operation_context_refs=audit_inputs.operation_context_refs,
                reason=audit_inputs.reason,
                request_context=audit_inputs.request_context,
                failure_stage=failure_stage,
                failure_message=str(error),
            ),
        )
    except Exception as audit_error:
        _LOGGER.warning(
            "purge_failed audit append failed for session_id=%s tombstone_id=%s: %s",
            audit_inputs.session_id,
            audit_inputs.tombstone_id,
            audit_error,
        )


def _host_api_error_from_durable_error(error: HostDurableError) -> HostApiError:
    """把 durable/internal 错误转换为 public Host API 错误。

    :param error: durable 层或内部运行期抛出的结构化错误。
    :returns: public Host API 错误。
    """

    if isinstance(error, HostIdempotencyConflictError):
        return HostApiError(
            code=HostApiErrorCode.IDEMPOTENCY_CONFLICT,
            message="Host command idempotency conflict",
            retryable=False,
        )
    if isinstance(error, HostForeignKeyError):
        return HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Host command referenced durable row was not found",
            retryable=False,
        )
    if isinstance(error, HostUniqueConstraintError):
        return HostApiError(
            code=HostApiErrorCode.CONFLICT,
            message="Host command durable identity conflict",
            retryable=False,
        )
    if isinstance(error, HostTransactionBusyError | HostTransactionRetryExhaustedError):
        return HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Host durable transaction is busy",
            retryable=True,
        )
    if isinstance(error, HostDurableConfigError):
        return HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="Host durable configuration is invalid",
            retryable=False,
        )
    return HostApiError(
        code=HostApiErrorCode.INTERNAL_ERROR,
        message="Host durable operation failed",
        retryable=False,
    )


def _durable_options_from_public_options(
    options: HostCommandHandleOptions,
) -> HostDurableStoreOptions:
    """把 public handle options 映射为 durable store options。

    :param options: Host command handle 公共构造选项。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(
            artifact_root=options.artifact_root,
            payload_inline_threshold_bytes=(options.payload_inline_threshold_bytes),
            create_artifact_root=options.create_parent_dirs,
        ),
        create_parent_dirs=options.create_parent_dirs,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=(options.sqlite_write_retry_initial_delay_seconds),
            write_retry_backoff_multiplier=(options.sqlite_write_retry_backoff_multiplier),
            write_retry_max_delay_seconds=(options.sqlite_write_retry_max_delay_seconds),
        ),
    )


def _raise_unsupported_operation(operation_name: str) -> NoReturn:
    """抛出 stable unsupported public facade 错误。

    :param operation_name: public operation 名称。
    :returns: 当前函数不会返回。
    :raises HostApiError: 始终以 ``UNSUPPORTED_OPERATION`` 抛出，且
        ``retryable=False``、``detail=None``。
    """

    raise HostApiError(
        code=HostApiErrorCode.UNSUPPORTED_OPERATION,
        message=f"{operation_name} is deferred beyond Phase 4",
        retryable=False,
        detail=None,
    )


def _host_handle_id_from_options(options: HostCommandHandleOptions) -> str:
    """返回 public handle id。

    :param options: Host command handle 公共构造选项。
    :returns: 调用方显式提供的 handle id，或本 factory 生成的生命周期稳定 id。
    """

    if options.host_handle_id is not None:
        return options.host_handle_id
    return f"{_GENERATED_HANDLE_ID_PREFIX}-{uuid4().hex}"


def _start_run_public_semantic_digest(request: StartRunRequest) -> str:
    """计算 public start_run facade semantic digest。

    :param request: start run 请求。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_START_RUN,
            "session_id": request.session_id,
            "input_digest": _input_digest(request.input),
            "execution_target": request.execution_target,
            "queue_policy": request.queue_policy,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _submit_followup_public_semantic_digest(
    request: SubmitFollowupRequest,
) -> str:
    """计算 public submit_followup facade semantic digest。

    :param request: submit follow-up 请求。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_SUBMIT_FOLLOWUP,
            "session_id": request.session_id,
            "prompt_digest": _submit_followup_prompt_digest(request),
            "tool_names": _tool_names_digest_value(request.tool_names),
            "runner_spec_digest": _optional_runner_spec_json(request.runner_spec),
            "runner_options_digest": _optional_runner_options_json(request.runner_options),
            "agent_policy_digest": _optional_agent_policy_json(request.agent_policy),
            "behavior": request.behavior.value,
            "target_run_id": request.target_run_id,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _cancel_run_public_semantic_digest(*, run_id: str, request: CancelRunRequest) -> str:
    """计算 public cancel_run facade semantic digest。

    :param run_id: 目标 Run id。
    :param request: cancel run 请求。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_CANCEL_RUN,
            "run_id": run_id,
            "reason": request.reason,
            "mode": request.mode.value,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _cancel_session_runs_public_semantic_digest(*, session_id: str, request: CancelSessionRunsRequest) -> str:
    """计算 public cancel_session_runs facade semantic digest。

    :param session_id: 目标 Session id。
    :param request: cancel session runs 请求。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_CANCEL_SESSION_RUNS,
            "session_id": session_id,
            "reason": request.reason,
            "mode": request.mode.value,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _retry_run_public_semantic_digest(*, run_id: str, request: RetryRunRequest) -> str:
    """计算 public retry_run facade semantic digest。

    :param run_id: 源 Run id。
    :param request: retry run 请求。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_RETRY_RUN,
            "source_run_id": run_id,
            "reason": request.reason,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _replay_run_public_semantic_digest(*, run_id: str, request: ReplayRunRequest) -> str:
    """计算 public replay_run facade semantic digest。

    :param run_id: 源 Run id。
    :param request: replay run 请求。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_REPLAY_RUN,
            "source_run_id": run_id,
            "reason": request.reason,
            "repair_instruction": request.repair_instruction,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


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


def _submit_followup_prompt_digest(request: SubmitFollowupRequest) -> str:
    """计算 follow-up prompt 字段摘要。

    :param request: submit follow-up 请求。
    :returns: ``sha256:<hex>`` digest。
    :raises: 无主动抛出。
    """

    return sha256_digest_json(
        {
            "system_prompt": request.system_prompt,
            "user_prompt": request.user_prompt,
        }
    )


def _tool_names_digest_value(tool_names: frozenset[str] | None) -> JsonValue:
    """把工具选择器投影为 semantic digest 输入。

    :param tool_names: 工具选择器。
    :returns: JSON digest 输入值。
    :raises: 无主动抛出。
    """

    if tool_names is None:
        return None
    values: list[JsonValue] = [tool_name for tool_name in sorted(tool_names)]
    return values


def _create_session_public_semantic_digest(
    request: CreateSessionRequest,
) -> str:
    """计算 public create_session facade semantic digest。

    digest 只包含显式 create_session 语义字段与 HostCallContext digest，不包含
    metadata bag、runtime-only object 或 durable 内部依赖。

    :param request: create session 请求。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_CREATE_SESSION,
            "bind_slot": request.bind_slot,
            "scope": request.scope,
            "slot_key": request.slot_key,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _close_session_public_semantic_digest(*, session_id: str, request: CloseSessionRequest) -> str:
    """计算 public close_session facade semantic digest。

    digest 只包含显式 close_session 语义字段与 HostCallContext digest，不包含
    runtime-only object 或 durable 内部依赖。

    :param session_id: 目标 Session id。
    :param request: close session 请求。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_CLOSE_SESSION,
            "session_id": session_id,
            "reason": request.reason,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _request_without_create_metadata(
    request: CreateSessionRequest,
) -> CreateSessionRequest:
    """构造不让 metadata 参与 durable idempotency digest 的 create 请求。

    :param request: public create session 请求。
    :returns: metadata 为空的 create session 请求；当前 public facade 不持久化
        create_session metadata。
    :raises ValueError: 复制后的请求不满足公共类型校验时抛出。
    """

    return CreateSessionRequest(
        context=request.context,
        client_request_id=request.client_request_id,
        bind_slot=request.bind_slot,
        scope=request.scope,
        slot_key=request.slot_key,
        metadata=(),
    )


def _call_context_digest(context: HostCallContext) -> str:
    """计算 HostCallContext semantic digest，排除 trace-only request_id。

    :param context: Host call context。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(_call_context_json_value(context))


def _call_context_json_value(context: HostCallContext) -> dict[str, JsonValue]:
    """把 HostCallContext 转为 canonical JSON 值。

    :param context: Host call context。
    :returns: JSON 对象值。
    """

    return {
        "actor": context.actor,
        "source": context.source,
        "authorization_claims": _authorization_claims_json_value(context.authorization_claims),
        "operation_context": _operation_context_json_value(context.operation_context),
    }


def _authorization_claims_json_value(claims: tuple[AuthorizationClaim, ...]) -> JsonValue:
    """把 authorization claims 转为 canonical JSON 值。

    :param claims: 授权声明元组。
    :returns: JSON 数组值。
    """

    values: list[JsonValue] = []
    for claim in claims:
        values.append({"name": claim.name, "value": claim.value})
    return values


def _operation_context_json_value(
    context: OperationContext,
) -> dict[str, JsonValue]:
    """把 OperationContext 转为 canonical JSON 值。

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


def _propagate_active_cancel_targets(
    host: HostCommandHandle,
    targets: tuple[ActiveCancelMessage, ...],
) -> None:
    """向 active worker registry 传播取消并唤醒 watchdog。

    :param host: Host command handle。
    :param targets: durable commit 后需要传播的 active cancel 目标集合。
    :returns: ``None``。
    """

    if targets:
        _wake_active_cancel_watchdog(host)
    for target in targets:
        host._active_registry.cancel(target)


def _wake_active_cancel_watchdog(host: HostCommandHandle) -> None:
    """唤醒 active cancel watchdog 并保留 bridge failure。

    :param host: Host command handle。
    :returns: ``None``。
    """

    wakeup_port = host._active_cancel_watchdog_wakeup_port
    if wakeup_port is None:
        return
    wakeup_port.wake_active_cancel_watchdog()


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


__all__ = [
    "HostCommandHandle",
    "HostCommandWaitCallbackPort",
    "cancel_run",
    "cancel_session_runs",
    "close_session",
    "compose_host_local_execution_options",
    "create_host_command_handle",
    "create_session",
    "ensure_session",
    "purge_session",
    "replay_run",
    "resolve_wait",
    "retry_run",
    "start_run",
    "submit_followup",
]
