"""Host wait callback typed contract 与适配器。

本模块只定义 framework-independent callback completion 入口。真实 HTTP
路由、header/body 解析和 HTTP status 映射属于 Service/Web；本模块把已经
解析成强类型 envelope 的 callback completion 接入 Host-owned
``resolve_wait`` 语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, TypeAlias

from dayu.host.api import (
    AuthorizationClaim,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    OperationContext,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    ResolveWaitOutcome,
    ResolveWaitRequest,
    RunSnapshot,
    WaitResolutionSource,
)
from dayu.host.durable.codec import is_sha256_digest
from dayu.host.durable.wait_resolution_digest import wait_resolution_digest


class WaitCallbackAdapterStatus(StrEnum):
    """Host callback adapter 的领域状态。

    这些状态只表达 Host callback contract 的处理结果，不包含 HTTP
    method、content-type、path/body mismatch 或 JSON malformed 等 Service
    transport 诊断。
    """

    ACCEPTED = "accepted"
    REPLAYED = "replayed"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    UNKNOWN_WAIT = "unknown_wait"
    LATE_WAIT_CANCELLED = "late_wait_cancelled"
    LATE_WAIT_LOST = "late_wait_lost"
    DIGEST_MISMATCH = "digest_mismatch"
    AUTH_FAILED = "auth_failed"
    INVALID_WAIT_STATE = "invalid_wait_state"
    INTERNAL_ERROR = "internal_error"


class WaitCallbackStoredWaitStatus(StrEnum):
    """callback adapter 预读 wait record 时使用的稳定状态投影。"""

    WAITING = "waiting"
    RESOLVED = "resolved"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


@dataclass(frozen=True, slots=True)
class WaitCallbackStoredWaitState:
    """callback adapter 预读到的 wait record 稳定状态。

    :param status: wait record 当前状态。
    :param deadline_at: wait deadline UTC 文本；没有 deadline 时为 ``None``。
    :param expires_at: 预留 expires UTC 文本；当前 schema 通常为 ``None``。
    """

    status: WaitCallbackStoredWaitStatus
    deadline_at: str | None
    expires_at: str | None

    def __post_init__(self) -> None:
        """校验 wait state 投影字段。

        :returns: ``None``。
        :raises TypeError: ``status`` 类型非法时抛出。
        :raises ValueError: 时间文本为空字符串时抛出。
        """

        if not isinstance(self.status, WaitCallbackStoredWaitStatus):
            raise TypeError(
                "WaitCallbackStoredWaitState.status must be "
                "WaitCallbackStoredWaitStatus"
            )
        _require_optional_non_empty(
            self.deadline_at, "WaitCallbackStoredWaitState.deadline_at"
        )
        _require_optional_non_empty(
            self.expires_at, "WaitCallbackStoredWaitState.expires_at"
        )


@dataclass(frozen=True, slots=True)
class WaitCallbackAuthInput:
    """callback 认证输入。

    :param auth_source: transport 层识别出的认证来源，例如 bearer 或 hmac。
    :param credential_ref: 凭据引用或脱敏凭据标识，不承载明文 secret。
    :param presented_claims: transport 层已提取但尚未由 authenticator 采信的声明。
    """

    auth_source: str
    credential_ref: str
    presented_claims: tuple[AuthorizationClaim, ...]

    def __post_init__(self) -> None:
        """校验认证输入字段。

        :returns: ``None``。
        :raises TypeError: claims 字段类型非法时抛出。
        :raises ValueError: 来源或凭据引用为空时抛出。
        """

        _require_non_empty(self.auth_source, "WaitCallbackAuthInput.auth_source")
        _require_non_empty(
            self.credential_ref, "WaitCallbackAuthInput.credential_ref"
        )
        _require_authorization_claim_tuple(
            self.presented_claims, "WaitCallbackAuthInput.presented_claims"
        )


@dataclass(frozen=True, slots=True)
class WaitCallbackAuthAccepted:
    """callback 认证通过结果。

    :param actor: HostCallContext 中使用的调用主体。
    :param authorization_claims: 已由 authenticator 采信的授权声明。
    """

    actor: str
    authorization_claims: tuple[AuthorizationClaim, ...]

    def __post_init__(self) -> None:
        """校验认证通过结果字段。

        :returns: ``None``。
        :raises TypeError: claims 字段类型非法时抛出。
        :raises ValueError: ``actor`` 为空时抛出。
        """

        _require_non_empty(self.actor, "WaitCallbackAuthAccepted.actor")
        _require_authorization_claim_tuple(
            self.authorization_claims,
            "WaitCallbackAuthAccepted.authorization_claims",
        )


@dataclass(frozen=True, slots=True)
class WaitCallbackAuthRejected:
    """callback 认证拒绝结果。

    :param reason_code: 机器可读拒绝原因。
    :param message: 人类可读诊断，不应包含凭据明文。
    :param retryable: 调用方是否可用同一语义请求重试。
    """

    reason_code: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        """校验认证拒绝结果字段。

        :returns: ``None``。
        :raises TypeError: ``retryable`` 类型非法时抛出。
        :raises ValueError: 原因或说明为空时抛出。
        """

        _require_non_empty(self.reason_code, "WaitCallbackAuthRejected.reason_code")
        _require_non_empty(self.message, "WaitCallbackAuthRejected.message")
        if not isinstance(self.retryable, bool):
            raise TypeError("WaitCallbackAuthRejected.retryable must be bool")


WaitCallbackAuthResult: TypeAlias = WaitCallbackAuthAccepted | WaitCallbackAuthRejected
"""callback 认证结果封闭联合。"""


class WaitCallbackAuthenticator(Protocol):
    """callback 认证协议。

    实现方通常位于 Service/Web composition root，负责把 deployment-specific
    bearer/HMAC/secret store 判断转换为 Host 可消费的强类型认证结果。
    """

    def authenticate_callback(
        self, request: WaitCallbackAuthInput
    ) -> WaitCallbackAuthResult:
        """认证 callback 请求。

        :param request: callback 认证输入。
        :returns: 认证通过或拒绝结果。
        :raises Exception: 实现方异常会被 adapter 映射为 internal error。
        """

        ...


@dataclass(frozen=True, slots=True)
class WaitCallbackCompletionEnvelope:
    """已解析的 callback completion envelope。

    :param wait_id: Host wait record id。
    :param idempotency_key: callback completion 幂等键。
    :param payload_digest: sender 声明的 canonical outcome material digest。
    :param observed_at: Host 观察到 callback 的 UTC 时间。
    :param completed_at: 外部系统完成该 wait 的 UTC 时间，仅用于 audit/stale 输入。
    :param outcome: 强类型 wait resolution outcome。
    :param auth: 认证输入。
    :param request_id: 本次 callback 调用追踪 id。
    :param correlation_id: 跨系统关联 id；没有时为 ``None``。
    """

    wait_id: str
    idempotency_key: str
    payload_digest: str
    observed_at: datetime
    completed_at: datetime
    outcome: ResolveWaitOutcome
    auth: WaitCallbackAuthInput
    request_id: str
    correlation_id: str | None

    def __post_init__(self) -> None:
        """校验 callback envelope 字段。

        :returns: ``None``。
        :raises TypeError: 时间、outcome 或 auth 类型非法时抛出。
        :raises ValueError: id、digest 或 UTC 时间字段非法时抛出。
        """

        _require_non_empty(
            self.wait_id, "WaitCallbackCompletionEnvelope.wait_id"
        )
        _require_non_empty(
            self.idempotency_key,
            "WaitCallbackCompletionEnvelope.idempotency_key",
        )
        if not is_sha256_digest(self.payload_digest):
            raise ValueError(
                "WaitCallbackCompletionEnvelope.payload_digest must be sha256 digest"
            )
        _require_utc_datetime(
            self.observed_at, "WaitCallbackCompletionEnvelope.observed_at"
        )
        _require_utc_datetime(
            self.completed_at, "WaitCallbackCompletionEnvelope.completed_at"
        )
        _require_resolve_wait_outcome(
            self.outcome, "WaitCallbackCompletionEnvelope.outcome"
        )
        if not isinstance(self.auth, WaitCallbackAuthInput):
            raise TypeError(
                "WaitCallbackCompletionEnvelope.auth must be WaitCallbackAuthInput"
            )
        _require_non_empty(
            self.request_id, "WaitCallbackCompletionEnvelope.request_id"
        )
        _require_optional_non_empty(
            self.correlation_id,
            "WaitCallbackCompletionEnvelope.correlation_id",
        )


@dataclass(frozen=True, slots=True)
class CallbackWaitResolveResult:
    """callback resolve port 返回结果。

    :param run: resolve 后最新 Run snapshot。
    :param idempotent_replay: 本次 resolve 是否为已有相同语义结果的 replay。
    """

    run: RunSnapshot
    idempotent_replay: bool

    def __post_init__(self) -> None:
        """校验 resolve port 返回字段。

        :returns: ``None``。
        :raises TypeError: ``run`` 或 ``idempotent_replay`` 类型非法时抛出。
        """

        if not isinstance(self.run, RunSnapshot):
            raise TypeError("CallbackWaitResolveResult.run must be RunSnapshot")
        if not isinstance(self.idempotent_replay, bool):
            raise TypeError(
                "CallbackWaitResolveResult.idempotent_replay must be bool"
            )


class CallbackWaitResolvePort(Protocol):
    """callback adapter 进入 Host command-layer resolve_wait 的端口。"""

    def resolve_callback_wait(
        self,
        wait_id: str,
        request: ResolveWaitRequest,
        context: HostCallContext,
    ) -> CallbackWaitResolveResult:
        """通过 command-layer 语义 resolve wait。

        :param wait_id: wait record id。
        :param request: callback 转换出的 resolve wait request。
        :param context: 与 request.context 同源的 Host 调用上下文。
        :returns: resolve 后 Run snapshot 与 replay 标志。
        :raises HostApiError: wait 缺失、状态非法或幂等冲突时抛出。
        """

        ...


class WaitCallbackStateReadPort(Protocol):
    """callback adapter 预读 wait state 的端口。"""

    def read_wait_state(self, wait_id: str) -> WaitCallbackStoredWaitState | None:
        """读取 wait record 稳定状态投影。

        :param wait_id: wait record id。
        :returns: 找到时返回 wait state；不存在时返回 ``None``。
        :raises HostApiError: durable 读取失败时抛出。
        """

        ...


@dataclass(frozen=True, slots=True)
class WaitCallbackAdapterResult:
    """callback adapter 返回结果。

    :param status: callback 处理状态。
    :param run: 已进入 resolve pipeline 时的最新 Run snapshot；无 snapshot 时为 ``None``。
    :param idempotent_replay: 本次请求是否是 idempotent replay。
    :param diagnostic_code: 机器可读诊断码。
    :param message: 人类可读诊断，不回显 callback result payload。
    :param retryable: 调用方是否可按同一语义重试。
    """

    status: WaitCallbackAdapterStatus
    run: RunSnapshot | None
    idempotent_replay: bool
    diagnostic_code: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        """校验 adapter 返回字段。

        :returns: ``None``。
        :raises TypeError: status、run 或布尔字段类型非法时抛出。
        :raises ValueError: 诊断码或消息为空时抛出。
        """

        if not isinstance(self.status, WaitCallbackAdapterStatus):
            raise TypeError(
                "WaitCallbackAdapterResult.status must be "
                "WaitCallbackAdapterStatus"
            )
        if self.run is not None and not isinstance(self.run, RunSnapshot):
            raise TypeError("WaitCallbackAdapterResult.run must be RunSnapshot")
        if not isinstance(self.idempotent_replay, bool):
            raise TypeError(
                "WaitCallbackAdapterResult.idempotent_replay must be bool"
            )
        _require_non_empty(
            self.diagnostic_code, "WaitCallbackAdapterResult.diagnostic_code"
        )
        _require_non_empty(self.message, "WaitCallbackAdapterResult.message")
        if not isinstance(self.retryable, bool):
            raise TypeError("WaitCallbackAdapterResult.retryable must be bool")


@dataclass(frozen=True, slots=True)
class DefaultWaitCallbackAdapter:
    """默认 Host wait callback adapter。

    :param authenticator: callback 认证协议实现。
    :param state_reader: wait state 预读端口。
    :param resolver: command-layer resolve port。
    """

    authenticator: WaitCallbackAuthenticator
    state_reader: WaitCallbackStateReadPort
    resolver: CallbackWaitResolvePort

    def resolve_callback(
        self, envelope: WaitCallbackCompletionEnvelope
    ) -> WaitCallbackAdapterResult:
        """处理 callback completion 并进入 Host resolve_wait 语义。

        :param envelope: 已解析并构造的 callback completion envelope。
        :returns: callback adapter typed 结果。
        :raises TypeError: ``envelope`` 类型非法时抛出。
        """

        if not isinstance(envelope, WaitCallbackCompletionEnvelope):
            raise TypeError("envelope must be WaitCallbackCompletionEnvelope")
        wait_state: WaitCallbackStoredWaitState | None = None
        try:
            accepted_auth = self._authenticate(envelope.auth)
            if isinstance(accepted_auth, WaitCallbackAuthRejected):
                return _result(
                    status=WaitCallbackAdapterStatus.AUTH_FAILED,
                    diagnostic_code=accepted_auth.reason_code,
                    message=accepted_auth.message,
                    retryable=accepted_auth.retryable,
                )
            wait_state = self.state_reader.read_wait_state(envelope.wait_id)
            if wait_state is None:
                return _result(
                    status=WaitCallbackAdapterStatus.UNKNOWN_WAIT,
                    diagnostic_code="unknown_wait",
                    message="wait record not found",
                    retryable=False,
                )
            if _callback_payload_digest(envelope) != envelope.payload_digest:
                return _result(
                    status=WaitCallbackAdapterStatus.DIGEST_MISMATCH,
                    diagnostic_code="digest_mismatch",
                    message="callback payload digest does not match outcome",
                    retryable=False,
                )
            context = _host_call_context(envelope, accepted_auth)
            request = ResolveWaitRequest(
                context=context,
                idempotency_key=envelope.idempotency_key,
                outcome=envelope.outcome,
                source=WaitResolutionSource.CALLBACK,
                observed_at=envelope.observed_at,
            )
            resolved = self.resolver.resolve_callback_wait(
                envelope.wait_id,
                request,
                context,
            )
        except HostApiError as exc:
            return _result_from_host_api_error(exc, wait_state)
        except (TypeError, ValueError):
            raise
        except Exception:
            return _result(
                status=WaitCallbackAdapterStatus.INTERNAL_ERROR,
                diagnostic_code="internal_error",
                message="callback resolve failed unexpectedly",
                retryable=True,
            )
        status = (
            WaitCallbackAdapterStatus.REPLAYED
            if resolved.idempotent_replay
            else WaitCallbackAdapterStatus.ACCEPTED
        )
        return _result(
            status=status,
            run=resolved.run,
            idempotent_replay=resolved.idempotent_replay,
            diagnostic_code=status.value,
            message=(
                "callback replayed"
                if resolved.idempotent_replay
                else "callback accepted"
            ),
            retryable=False,
        )

    def _authenticate(
        self, auth: WaitCallbackAuthInput
    ) -> WaitCallbackAuthResult:
        """执行 callback 认证。

        :param auth: 认证输入。
        :returns: 认证结果。
        :raises TypeError: authenticator 返回非封闭联合成员时抛出。
        """

        result = self.authenticator.authenticate_callback(auth)
        if not isinstance(result, (WaitCallbackAuthAccepted, WaitCallbackAuthRejected)):
            raise TypeError(
                "WaitCallbackAuthenticator.authenticate_callback must return "
                "WaitCallbackAuthResult"
            )
        return result


def callback_payload_digest(envelope: WaitCallbackCompletionEnvelope) -> str:
    """计算 callback payload digest。

    该 digest 与现有 wait resolution semantic digest 使用同一业务材料：
    ``wait_id + idempotency_key + outcome``。``observed_at`` 与
    ``completed_at`` 不参与计算。

    :param envelope: callback completion envelope。
    :returns: Host canonical sha256 digest。
    :raises TypeError: ``envelope`` 类型非法时抛出。
    """

    if not isinstance(envelope, WaitCallbackCompletionEnvelope):
        raise TypeError("envelope must be WaitCallbackCompletionEnvelope")
    return _callback_payload_digest(envelope)


def _callback_payload_digest(envelope: WaitCallbackCompletionEnvelope) -> str:
    """计算 callback payload digest 内部实现。

    :param envelope: callback completion envelope。
    :returns: Host canonical sha256 digest。
    """

    return wait_resolution_digest(
        envelope.wait_id,
        envelope.idempotency_key,
        envelope.outcome,
    )


def _result_from_host_api_error(
    error: HostApiError, wait_state: WaitCallbackStoredWaitState | None
) -> WaitCallbackAdapterResult:
    """把 HostApiError 映射为 callback adapter 状态。

    :param error: command-layer 抛出的 HostApiError。
    :param wait_state: resolve 前稳定预读的 wait state；没有则为 ``None``。
    :returns: adapter typed 结果。
    """

    if error.code is HostApiErrorCode.NOT_FOUND:
        return _result(
            status=WaitCallbackAdapterStatus.UNKNOWN_WAIT,
            diagnostic_code="unknown_wait",
            message="wait record not found",
            retryable=False,
        )
    if error.code is HostApiErrorCode.IDEMPOTENCY_CONFLICT:
        return _result(
            status=WaitCallbackAdapterStatus.IDEMPOTENCY_CONFLICT,
            diagnostic_code="idempotency_conflict",
            message="callback idempotency key conflicts with existing outcome",
            retryable=False,
        )
    if error.code is HostApiErrorCode.INVALID_STATE:
        late_status = _stable_late_status_or_none(wait_state)
        if late_status is not None:
            return late_status
        return _result(
            status=WaitCallbackAdapterStatus.INVALID_WAIT_STATE,
            diagnostic_code="invalid_wait_state",
            message="wait record is not resolvable",
            retryable=error.retryable,
        )
    return _result(
        status=WaitCallbackAdapterStatus.INTERNAL_ERROR,
        diagnostic_code="host_api_error",
        message="callback resolve failed",
        retryable=error.retryable,
    )


def _stable_late_status_or_none(
    wait_state: WaitCallbackStoredWaitState | None,
) -> WaitCallbackAdapterResult | None:
    """根据预读 stable wait state 映射 late callback 分类。

    :param wait_state: resolve 前预读 wait state。
    :returns: late 状态；不能稳定分类时返回 ``None``。
    """

    if wait_state is None:
        return None
    if wait_state.status is WaitCallbackStoredWaitStatus.CANCELLED:
        return _result(
            status=WaitCallbackAdapterStatus.LATE_WAIT_CANCELLED,
            diagnostic_code="late_wait_cancelled",
            message="wait was already cancelled",
            retryable=False,
        )
    if wait_state.status is WaitCallbackStoredWaitStatus.LOST:
        return _result(
            status=WaitCallbackAdapterStatus.LATE_WAIT_LOST,
            diagnostic_code="late_wait_lost",
            message="wait was already lost",
            retryable=False,
        )
    return None


def _host_call_context(
    envelope: WaitCallbackCompletionEnvelope, auth: WaitCallbackAuthAccepted
) -> HostCallContext:
    """构造 callback resolve 使用的 HostCallContext。

    :param envelope: callback completion envelope。
    :param auth: 认证通过结果。
    :returns: Host 调用上下文。
    """

    return HostCallContext(
        actor=auth.actor,
        source=envelope.auth.auth_source,
        request_id=envelope.request_id,
        authorization_claims=auth.authorization_claims,
        operation_context=OperationContext(
            operation_name="resolve_wait_callback",
            operation_kind="callback",
            business_domain="host",
            business_object_type="wait",
            business_object_id=envelope.wait_id,
            scenario="wait_callback",
            correlation_id=envelope.correlation_id,
        ),
    )


def _result(
    *,
    status: WaitCallbackAdapterStatus,
    diagnostic_code: str,
    message: str,
    retryable: bool,
    run: RunSnapshot | None = None,
    idempotent_replay: bool = False,
) -> WaitCallbackAdapterResult:
    """构造 callback adapter result。

    :param status: adapter 状态。
    :param diagnostic_code: 机器可读诊断码。
    :param message: 人类可读诊断。
    :param retryable: 是否可重试。
    :param run: 可选 Run snapshot。
    :param idempotent_replay: 是否为幂等 replay。
    :returns: adapter result。
    """

    return WaitCallbackAdapterResult(
        status=status,
        run=run,
        idempotent_replay=idempotent_replay,
        diagnostic_code=diagnostic_code,
        message=message,
        retryable=retryable,
    )


def _require_resolve_wait_outcome(
    outcome: ResolveWaitOutcome, field_name: str
) -> None:
    """校验 resolve wait outcome 封闭联合成员。

    :param outcome: 待校验 outcome。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: outcome 类型非法时抛出。
    """

    if not isinstance(
        outcome,
        (
            ResolveWaitCompletedOutcome,
            ResolveWaitFailedOutcome,
            ResolveWaitCancelledOutcome,
            ResolveWaitLostOutcome,
        ),
    ):
        raise TypeError(f"{field_name} must be ResolveWaitOutcome")


def _require_utc_datetime(value: datetime, field_name: str) -> None:
    """校验 datetime 为 timezone-aware UTC。

    :param value: 待校验 datetime。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: ``value`` 不是 datetime 时抛出。
    :raises ValueError: ``value`` 不是 UTC aware datetime 时抛出。
    """

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"{field_name} must be UTC aware datetime")


def _require_authorization_claim_tuple(
    claims: tuple[AuthorizationClaim, ...], field_name: str
) -> None:
    """校验授权声明 tuple。

    :param claims: 待校验 claims。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: claims 不是 tuple 或元素类型非法时抛出。
    """

    if not isinstance(claims, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for claim in claims:
        if not isinstance(claim, AuthorizationClaim):
            raise TypeError(f"{field_name} must contain AuthorizationClaim")


def _require_non_empty(value: str, field_name: str) -> None:
    """校验字符串非空。

    :param value: 待校验字符串。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: ``value`` 不是字符串时抛出。
    :raises ValueError: ``value`` 为空或纯空白时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    """校验可选字符串存在时非空。

    :param value: 待校验可选字符串。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: ``value`` 不是字符串或 ``None`` 时抛出。
    :raises ValueError: 字符串为空或纯空白时抛出。
    """

    if value is None:
        return
    _require_non_empty(value, field_name)


__all__ = [
    "CallbackWaitResolvePort",
    "CallbackWaitResolveResult",
    "DefaultWaitCallbackAdapter",
    "WaitCallbackAdapterResult",
    "WaitCallbackAdapterStatus",
    "WaitCallbackAuthAccepted",
    "WaitCallbackAuthInput",
    "WaitCallbackAuthRejected",
    "WaitCallbackAuthResult",
    "WaitCallbackAuthenticator",
    "WaitCallbackCompletionEnvelope",
    "WaitCallbackStateReadPort",
    "WaitCallbackStoredWaitState",
    "WaitCallbackStoredWaitStatus",
    "callback_payload_digest",
]
