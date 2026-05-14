"""Host public command handle 与 Session facade。

本模块是 Phase 4 public command path 的 Host composition root。它负责把
公共 handle options 映射到 durable store options，持有私有 durable store
和内部 service 依赖，并提供 Session public facade；它不启动后台 supervisor、
不实现 Engine dispatch、Run admission facade、EventLog stream 或 purge。
"""

from __future__ import annotations

from uuid import uuid4

from dayu.contracts.json_value import JsonValue
from dayu.host.admission import HostAdmissionService, create_host_admission_service
from dayu.host.api import (
    AuthorizationClaim,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostCommandHandleOptions,
    OperationContext,
    SessionSnapshot,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import (
    HostDurableStore,
    open_host_durable_store,
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
from dayu.host.durable.transaction import (
    HostReadTransactionOperation,
    HostTransactionOperation,
    HostTransactionRunner,
    T,
)

_GENERATED_HANDLE_ID_PREFIX = "host-command"
_OPERATION_CREATE_SESSION = "create_session"
_OPERATION_CLOSE_SESSION = "close_session"


class HostCommandHandle:
    """Host public command handle。

    :param host_handle_id: 稳定诊断 handle id。
    :param durable_store: 当前 handle 私有持有的 durable store。
    :param admission_service: 当前 handle 私有持有的内部 admission service。
    """

    __slots__ = (
        "_admission_service",
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
    ) -> None:
        """初始化 Host command handle。

        :param host_handle_id: 稳定诊断 handle id。
        :param durable_store: 已打开的 Host durable store。
        :param admission_service: 内部 admission service 依赖。
        :returns: 无返回值。
        :raises ValueError: ``host_handle_id`` 为空时抛出。
        """

        if host_handle_id.strip() == "":
            raise ValueError("host_handle_id must be non-empty")
        self._host_handle_id = host_handle_id
        self._durable_store = durable_store
        self._admission_service = admission_service
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
        return self._durable_store.transaction_runner

    def _run_read(self, operation: HostReadTransactionOperation[T]) -> T:
        """在 handle 私有 store 上执行 read transaction。

        :param operation: read transaction body。
        :returns: operation 返回值。
        :raises HostApiError: handle 已关闭时抛出。
        """

        return self._transaction_runner().run_read(operation)

    def _run_write(self, operation: HostTransactionOperation[T]) -> T:
        """在 handle 私有 store 上执行 write transaction。

        :param operation: write transaction body。
        :returns: operation 返回值。
        :raises HostApiError: handle 已关闭时抛出。
        """

        return self._transaction_runner().run_write(operation)

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
) -> HostCommandHandle:
    """创建 Host public command handle。

    :param options: Host command handle 公共构造选项。
    :returns: 已打开 durable store 并装配内部依赖的 ``HostCommandHandle``。
    :raises HostDurableConfigError: durable store 配置非法时由底层抛出。
    :raises HostDurableError: durable store 打开或 schema bootstrap 失败时由底层抛出。
    """

    durable_options = _durable_options_from_public_options(options)
    durable_store = open_host_durable_store(durable_options)
    try:
        admission_service = create_host_admission_service(
            durable_store.transaction_runner
        )
        return HostCommandHandle(
            host_handle_id=_host_handle_id_from_options(options),
            durable_store=durable_store,
            admission_service=admission_service,
        )
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

    result = _ensure_session_in_durable(host._transaction_runner(), request)
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
    result = _create_session_in_durable(
        host._transaction_runner(),
        durable_request,
        caller_semantic_digest=caller_digest,
    )
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
    result = _close_session_in_durable(
        host._transaction_runner(),
        session_id,
        request,
        caller_semantic_digest=caller_digest,
    )
    return result.snapshot


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


def _host_handle_id_from_options(options: HostCommandHandleOptions) -> str:
    """返回 public handle id。

    :param options: Host command handle 公共构造选项。
    :returns: 调用方显式提供的 handle id，或本 factory 生成的生命周期稳定 id。
    """

    if options.host_handle_id is not None:
        return options.host_handle_id
    return f"{_GENERATED_HANDLE_ID_PREFIX}-{uuid4().hex}"


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


__all__ = [
    "HostCommandHandle",
    "close_session",
    "create_host_command_handle",
    "create_session",
    "ensure_session",
]
