"""Host public command handle 与 Session facade。

本模块是 Phase 4 public command path 的 Host composition root。它负责把
公共 handle options 映射到 durable store options，持有私有 durable store
和内部 service 依赖，并提供 Session / Run public facade；它不启动后台
supervisor，不实现 Engine dispatch、EventLog stream 或 purge。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn
from uuid import uuid4

from dayu.contracts.json_value import JsonValue
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
)
from dayu.host.durable.codec import sha256_digest_json
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
from dayu.host.durable.session_lifecycle import (
    close_session as _close_session_in_durable,
    create_session as _create_session_in_durable,
    ensure_session as _ensure_session_in_durable,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
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
    ActiveWorkerRegistry,
)
from dayu.host.waiting import DefaultHostResolveWaitService

_GENERATED_HANDLE_ID_PREFIX = "host-command"
_OPERATION_CREATE_SESSION = "create_session"
_OPERATION_CLOSE_SESSION = "close_session"
_OPERATION_START_RUN = "start_run"
_OPERATION_SUBMIT_FOLLOWUP = "submit_followup"
_OPERATION_CANCEL_RUN = "cancel_run"
_OPERATION_CANCEL_SESSION_RUNS = "cancel_session_runs"
_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET = "host-public-followup-default"


class HostCommandHandle:
    """Host public command handle。

    :param host_handle_id: 稳定诊断 handle id。
    :param durable_store: 当前 handle 私有持有的 durable store。
    :param admission_service: 当前 handle 私有持有的内部 admission service。
    :param active_registry: 当前 handle 用于 active worker cancel 传播的 registry。
    """

    __slots__ = (
        "_admission_service",
        "_active_registry",
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
        active_registry: ActiveWorkerRegistry,
    ) -> None:
        """初始化 Host command handle。

        :param host_handle_id: 稳定诊断 handle id。
        :param durable_store: 已打开的 Host durable store。
        :param admission_service: 内部 admission service 依赖。
        :param active_registry: active worker cancel 传播 registry。
        :returns: 无返回值。
        :raises ValueError: ``host_handle_id`` 为空时抛出。
        """

        if host_handle_id.strip() == "":
            raise ValueError("host_handle_id must be non-empty")
        self._host_handle_id = host_handle_id
        self._durable_store = durable_store
        self._admission_service = admission_service
        self._active_registry = active_registry
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
    active_registry: ActiveWorkerRegistry | None = None,
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
        admission_service = create_host_admission_service(
            durable_store.transaction_runner
        )
        return HostCommandHandle(
            host_handle_id=_host_handle_id_from_options(options),
            durable_store=durable_store,
            admission_service=admission_service,
            active_registry=(
                active_registry
                if active_registry is not None
                else ActiveWorkerRegistry()
            ),
        )
    except HostDurableError as exc:
        durable_store.close()
        raise _host_api_error_from_durable_error(exc) from exc
    except Exception:
        durable_store.close()
        raise


def ensure_session(
    host: HostCommandHandle, request: EnsureSessionRequest
) -> SessionSnapshot:
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
    return result.snapshot


def create_session(
    host: HostCommandHandle, request: CreateSessionRequest
) -> SessionSnapshot:
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

    caller_digest = _close_session_public_semantic_digest(
        session_id=session_id, request=request
    )
    try:
        result = _close_session_in_durable(
            host._transaction_runner(),
            session_id,
            request,
            caller_semantic_digest=caller_digest,
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    return result.snapshot


def start_run(host: HostCommandHandle, request: StartRunRequest) -> RunSnapshot:
    """启动独立 Run，并返回 Run snapshot。

    :param host: Host command handle。
    :param request: start run 请求。
    :returns: durable truth 生成的 Run snapshot。
    :raises HostApiError: handle 已关闭、Session 状态非法、active reject 或幂等冲突时抛出。
    """

    host._raise_if_closed()
    try:
        result = host._admission_service.start_run(
            request,
            caller_semantic_digest=_start_run_public_semantic_digest(request),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    return run_snapshot_from_row(result.run)


def submit_followup(
    host: HostCommandHandle,
    session_id: str,
    request: SubmitFollowupRequest,
) -> FollowupSnapshot:
    """提交同一 Session 的后续输入。

    Phase 4 只实现 ``behavior=queue``；``behavior=steer`` 返回 stable
    unsupported，不追加 EventLog。

    :param host: Host command handle。
    :param session_id: 调用路径中的目标 Session id。
    :param request: follow-up 请求。
    :returns: follow-up 接受结果 snapshot。
    :raises HostApiError: session id 不一致、steer 未支持或 admission 失败时抛出。
    """

    host._raise_if_closed()
    if session_id != request.session_id:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="submit_followup session_id does not match request",
            retryable=False,
        )
    if request.behavior == FollowupBehavior.STEER:
        raise HostApiError(
            code=HostApiErrorCode.UNSUPPORTED_OPERATION,
            message="submit_followup steer is deferred beyond Phase 4",
            retryable=False,
        )
    try:
        result = host._admission_service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=request,
                resolved_execution_target=(
                    _PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET
                ),
            ),
            caller_semantic_digest=_submit_followup_public_semantic_digest(
                request
            ),
        )
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    return FollowupSnapshot(
        accepted_input_ref=result.run.input_event_id,
        behavior=FollowupBehavior.QUEUE,
        accepted_run_id=result.run.run_id,
        accepted_run_status=result.run.status,
        current_cursor=run_snapshot_from_row(result.run).event_cursor,
        queued_run_id=(
            result.run.run_id if result.run.status == RunStatus.QUEUED else None
        ),
        target_run_id=None,
    )


def cancel_run(
    host: HostCommandHandle, run_id: str, request: CancelRunRequest
) -> RunSnapshot:
    """取消单个 Run，并返回最新 Run snapshot。

    当前覆盖 queued、pre-dispatch ``STARTING``、pre-accept dispatching、
    active worker 与 ``WAITING``；``RECOVERING`` 取消由 Phase 11 负责。

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
    except HostApiError as exc:
        if exc.code == HostApiErrorCode.INVALID_STATE and _is_deferred_cancel_state(
            host, run_id
        ):
            raise HostApiError(
                code=HostApiErrorCode.UNSUPPORTED_OPERATION,
                message="Run cancel requires a later cancel owner phase",
                retryable=False,
            ) from exc
        raise
    _propagate_active_cancel_targets(
        host,
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
    )
    return run_snapshot_from_row(result.run)


def cancel_session_runs(
    host: HostCommandHandle,
    session_id: str,
    request: CancelSessionRunsRequest,
) -> SessionSnapshot:
    """取消指定 Session 下当前支持子集中的所有非终态 Run。

    当前覆盖 queued、pre-dispatch ``STARTING``、pre-accept dispatching、
    active worker 与 ``WAITING``；``RECOVERING`` 取消由 Phase 11 负责。

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
        )
    )
    return result.snapshot


def retry_run(
    host: HostCommandHandle, run_id: str, request: RetryRunRequest
) -> RunSnapshot:
    """稳定拒绝 Phase 4 尚未实现的 retry Run。

    本函数不打开 transaction、不追加 EventLog、不写 idempotency record。

    :param host: Host command handle；Phase 4 deferred 路径不读取该 handle。
    :param run_id: 源 Run id。
    :param request: retry run 请求。
    :returns: 当前阶段不会返回。
    :raises HostApiError: 始终以 ``UNSUPPORTED_OPERATION`` 抛出。
    """

    host._raise_if_closed()
    _raise_unsupported_operation("retry_run")


def replay_run(
    host: HostCommandHandle, run_id: str, request: ReplayRunRequest
) -> RunSnapshot:
    """稳定拒绝 Phase 4 尚未实现的 replay Run。

    本函数不打开 transaction、不追加 EventLog、不写 idempotency record。

    :param host: Host command handle；Phase 4 deferred 路径不读取该 handle。
    :param run_id: 源 Run id。
    :param request: replay run 请求。
    :returns: 当前阶段不会返回。
    :raises HostApiError: 始终以 ``UNSUPPORTED_OPERATION`` 抛出。
    """

    host._raise_if_closed()
    _raise_unsupported_operation("replay_run")


def resolve_wait(
    host: HostCommandHandle, wait_id: str, request: ResolveWaitRequest
) -> RunSnapshot:
    """接收 wait result 并返回最新 Run snapshot。

    :param host: Host command handle。
    :param wait_id: 待接收结果的 wait id。
    :param request: resolve wait 请求。
    :returns: 最新 Run snapshot。
    :raises HostApiError: handle 已关闭、wait 缺失、状态非法或幂等冲突时抛出。
    """

    try:
        transaction_runner = host._transaction_runner()
        service = DefaultHostResolveWaitService(
            transaction_runner=transaction_runner,
            event_log_store=host._admission_service.event_log_store,
            idempotency_store=host._admission_service.idempotency_store,
            projection_catchup_port=(
                host._admission_service.projection_catchup_port
            ),
        )
        result = service.resolve_wait(wait_id, request)
    except HostDurableError as exc:
        raise _host_api_error_from_durable_error(exc) from exc
    if result.dispatch_record is not None and not result.idempotent_replay:
        host._admission_service.wakeup_port.wake_dispatch(
            _pending_dispatch_from_row(result.dispatch_record)
        )
    return run_snapshot_from_row(result.run)


def purge_session(
    host: HostCommandHandle,
    session_id: str,
    request: PurgeSessionRequest,
) -> PurgeSessionResult:
    """稳定拒绝 Phase 4 尚未实现的 Session purge。

    本函数不打开 transaction、不追加 EventLog、不写 idempotency record。

    :param host: Host command handle；Phase 4 deferred 路径不读取该 handle。
    :param session_id: 目标 Session id。
    :param request: purge session 请求。
    :returns: 当前阶段不会返回。
    :raises HostApiError: 始终以 ``UNSUPPORTED_OPERATION`` 抛出。
    """

    host._raise_if_closed()
    _raise_unsupported_operation("purge_session")


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
    if isinstance(
        error, HostTransactionBusyError | HostTransactionRetryExhaustedError
    ):
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
            payload_inline_threshold_bytes=(
                options.payload_inline_threshold_bytes
            ),
            create_artifact_root=options.create_parent_dirs,
        ),
        create_parent_dirs=options.create_parent_dirs,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=(
                options.sqlite_write_retry_initial_delay_seconds
            ),
            write_retry_backoff_multiplier=(
                options.sqlite_write_retry_backoff_multiplier
            ),
            write_retry_max_delay_seconds=(
                options.sqlite_write_retry_max_delay_seconds
            ),
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
            "input_digest": _input_digest(request.input),
            "behavior": request.behavior.value,
            "target_run_id": request.target_run_id,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _cancel_run_public_semantic_digest(
    *, run_id: str, request: CancelRunRequest
) -> str:
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


def _cancel_session_runs_public_semantic_digest(
    *, session_id: str, request: CancelSessionRunsRequest
) -> str:
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


def _close_session_public_semantic_digest(
    *, session_id: str, request: CloseSessionRequest
) -> str:
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


def _call_context_json_value(context: HostCallContext) -> JsonValue:
    """把 HostCallContext 转为 canonical JSON 值。

    :param context: Host call context。
    :returns: JSON 对象值。
    """

    return {
        "actor": context.actor,
        "source": context.source,
        "authorization_claims": _authorization_claims_json_value(
            context.authorization_claims
        ),
        "operation_context": _operation_context_json_value(
            context.operation_context
        ),
    }


def _authorization_claims_json_value(
    claims: tuple[AuthorizationClaim, ...]
) -> JsonValue:
    """把 authorization claims 转为 canonical JSON 值。

    :param claims: 授权声明元组。
    :returns: JSON 数组值。
    """

    values: list[JsonValue] = []
    for claim in claims:
        values.append({"name": claim.name, "value": claim.value})
    return values


def _operation_context_json_value(context: OperationContext) -> JsonValue:
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
    """向 active worker registry best-effort 传播取消。

    :param host: Host command handle。
    :param targets: durable commit 后需要传播的 active cancel 目标集合。
    :returns: ``None``。
    """

    for target in targets:
        host._active_registry.cancel(target)


def _is_deferred_cancel_state(host: HostCommandHandle, run_id: str) -> bool:
    """判断当前 Run 状态是否属于后续 phase 的 cancel 能力。

    :param host: Host command handle。
    :param run_id: 目标 Run id。
    :returns: 属于 deferred cancel 能力时返回 ``True``。
    :raises HostApiError: handle 已关闭时由底层抛出。
    """

    return host._run_read(_IsDeferredCancelStateOperation(run_id=run_id))


@dataclass(frozen=True, slots=True)
class _IsDeferredCancelStateOperation:
    """deferred cancel 状态判断 read transaction body。"""

    run_id: str

    def __call__(self, transaction: HostTransaction) -> bool:
        """执行 deferred cancel 状态判断。

        :param transaction: 当前 Host transaction。
        :returns: 属于 deferred cancel 能力时返回 ``True``。
        """

        run = read_run_by_id(transaction, self.run_id)
        if run is None:
            return False
        if run.status in (
            RunStatus.WAITING,
            RunStatus.RECOVERING,
        ):
            return True
        if run.status not in (RunStatus.RUNNING, RunStatus.CANCELLING):
            return False
        return not (
            _is_predispatch_starting_run(transaction, run)
            or _is_active_worker_cancelable_run(transaction, run)
        )


def _is_predispatch_starting_run(
    transaction: HostTransaction, run: RunRow
) -> bool:
    """判断 Run 是否仍是可直接取消的 pre-dispatch STARTING。

    :param transaction: 当前 Host transaction。
    :param run: 目标 Run row。
    :returns: 满足 pre-dispatch STARTING 前置时返回 ``True``。
    """

    attempt, dispatch_record = _read_attempt_and_dispatch_for_run(transaction, run)
    return (
        attempt is not None
        and attempt.status == AttemptStatus.STARTING
        and dispatch_record is not None
        and _is_direct_cancelable_dispatch_record(dispatch_record)
    )


def _is_active_worker_cancelable_run(
    transaction: HostTransaction, run: RunRow
) -> bool:
    """判断 Run 是否处于 Phase 5 active worker cancel 子集。

    :param transaction: 当前 Host transaction。
    :param run: 目标 Run row。
    :returns: 可 active cancel 时返回 ``True``。
    """

    attempt, _dispatch_record = _read_attempt_and_dispatch_for_run(transaction, run)
    return attempt is not None and attempt.status == AttemptStatus.RUNNING


def _is_direct_cancelable_dispatch_record(
    dispatch_record: DispatchRecordRow,
) -> bool:
    """判断 dispatch record 是否仍可 pre-worker direct cancel。

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


def _read_attempt_and_dispatch_for_run(
    transaction: HostTransaction, run: RunRow
) -> tuple[AttemptRow | None, DispatchRecordRow | None]:
    """读取 Run 当前 Attempt 与 dispatch record。

    :param transaction: 当前 Host transaction。
    :param run: 目标 Run row。
    :returns: Attempt 与 dispatch record；缺失时对应位置为 ``None``。
    """

    if run.current_attempt_id is None:
        return None, None
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, run.current_attempt_id
    )
    return attempt, dispatch_record


__all__ = [
    "HostCommandHandle",
    "cancel_run",
    "cancel_session_runs",
    "close_session",
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
