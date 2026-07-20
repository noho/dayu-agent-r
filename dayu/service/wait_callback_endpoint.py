"""Service 层 wait callback HTTP-like endpoint mapper。

本模块只实现 framework-neutral transport 映射：真实 Web router 负责把
path 中的 wait id、headers 与已解析 JSON body 传入这里；本模块负责
校验 transport 形态、构造 Host callback envelope，并把 Host adapter
结果映射为 HTTP-like response。它不注册路由、不写 durable state，也不
依赖具体 Web framework。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import (
    ALLOWED_TOOL_CANCELLED_REASONS,
    ToolCancelledOutcome,
    ToolCancelledReason,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultMeta,
    ToolResultSuccess,
)
from dayu.host import (
    AuthorizationClaim,
    HostPayloadRef,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    RunSnapshot,
    WaitAdapterKey,
    WaitCallbackAdapterResult,
    WaitCallbackAdapterStatus,
    WaitCallbackAuthInput,
    WaitCallbackCompletionEnvelope,
    WaitProviderStatusRef,
)


JsonObject: TypeAlias = Mapping[str, JsonValue]
"""JSON object 类型别名。"""

_MISSING_REQUEST_ID_DIAGNOSTIC_CODE = "missing_request_id"
"""callback request id 缺失诊断码。"""


class WaitCallbackEndpointStatus(StrEnum):
    """Service mapper 自有 transport 诊断状态。"""

    TRANSPORT_REJECTED = "transport_rejected"
    MALFORMED_PAYLOAD = "malformed_payload"


class WaitCallbackOutcomeKind(StrEnum):
    """Service mapper 支持的 callback outcome kind。"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


@dataclass(frozen=True, slots=True)
class HeaderEntry:
    """HTTP-like header 条目。

    :param name: header 名称。
    :param value: header 值。
    """

    name: str
    value: str

    def __post_init__(self) -> None:
        """校验 header 条目字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: header 名称为空时抛出。
        """

        _require_non_empty(self.name, "HeaderEntry.name")
        if not isinstance(self.value, str):
            raise TypeError("HeaderEntry.value must be str")


@dataclass(frozen=True, slots=True)
class WaitCallbackHttpRequest:
    """framework-neutral callback completion 请求。

    :param method: HTTP method 文本。
    :param path_wait_id: 真实 router 从 path 提取出的 wait id。
    :param headers: HTTP-like header 条目集合。
    :param body: 已由真实 framework 解析出的 JSON body。
    """

    method: str
    path_wait_id: str
    headers: tuple[HeaderEntry, ...]
    body: JsonValue

    def __post_init__(self) -> None:
        """校验请求字段的 transport 基础形态。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: method、path wait id 为空或 headers 元素非法时抛出。
        """

        _require_non_empty(self.method, "WaitCallbackHttpRequest.method")
        _require_non_empty(
            self.path_wait_id, "WaitCallbackHttpRequest.path_wait_id"
        )
        if not isinstance(self.headers, tuple):
            raise TypeError("WaitCallbackHttpRequest.headers must be tuple")
        for header in self.headers:
            if not isinstance(header, HeaderEntry):
                raise TypeError(
                    "WaitCallbackHttpRequest.headers must contain HeaderEntry"
                )


@dataclass(frozen=True, slots=True)
class WaitCallbackHttpResponse:
    """framework-neutral callback completion 响应。

    :param status_code: HTTP status code。
    :param body: JSON response body；不包含 callback outcome payload。
    """

    status_code: int
    body: JsonValue

    def __post_init__(self) -> None:
        """校验响应字段。

        :returns: ``None``。
        :raises TypeError: status code 类型非法时抛出。
        :raises ValueError: status code 不在 HTTP 三位状态码范围时抛出。
        """

        if not isinstance(self.status_code, int):
            raise TypeError("WaitCallbackHttpResponse.status_code must be int")
        if self.status_code < 100 or self.status_code > 599:
            raise ValueError("WaitCallbackHttpResponse.status_code must be HTTP code")


class WaitCallbackEndpointAdapter(Protocol):
    """Service mapper 调用的 Host callback adapter 协议。"""

    def resolve_callback(
        self, envelope: WaitCallbackCompletionEnvelope
    ) -> WaitCallbackAdapterResult:
        """处理已解析 callback completion envelope。

        :param envelope: Host callback completion envelope。
        :returns: Host callback adapter typed result。
        """

        ...


def handle_wait_callback_completion(
    request: WaitCallbackHttpRequest, adapter: WaitCallbackEndpointAdapter
) -> WaitCallbackHttpResponse:
    """处理 framework-neutral wait callback completion 请求。

    :param request: HTTP-like callback 请求。
    :param adapter: Host callback adapter。
    :returns: HTTP-like callback 响应。
    :raises TypeError: ``request`` 类型非法时抛出。
    """

    if not isinstance(request, WaitCallbackHttpRequest):
        raise TypeError("request must be WaitCallbackHttpRequest")
    headers = _headers_by_lower_name(request.headers)
    transport_response = _transport_rejection_or_none(request, headers)
    if transport_response is not None:
        return transport_response
    missing_request_id_response = _missing_request_id_response_or_none(
        request, headers
    )
    if missing_request_id_response is not None:
        return missing_request_id_response
    try:
        envelope = _completion_envelope_from_request(request, headers)
    except (TypeError, ValueError):
        return _service_response(
            status_code=400,
            status=WaitCallbackEndpointStatus.MALFORMED_PAYLOAD.value,
            diagnostic_code=WaitCallbackEndpointStatus.MALFORMED_PAYLOAD.value,
            message="callback payload is malformed",
            retryable=False,
            run=None,
        )
    adapter_result = adapter.resolve_callback(envelope)
    return _adapter_response(adapter_result)


def _headers_by_lower_name(
    headers: tuple[HeaderEntry, ...]
) -> Mapping[str, str]:
    """把 header tuple 归一为大小写不敏感 mapping。

    :param headers: header 条目集合。
    :returns: 小写 header name 到原始值的 mapping。
    """

    normalized: dict[str, str] = {}
    for header in headers:
        normalized[header.name.lower()] = header.value
    return normalized


def _transport_rejection_or_none(
    request: WaitCallbackHttpRequest, headers: Mapping[str, str]
) -> WaitCallbackHttpResponse | None:
    """校验 method、content-type 与 path/body wait id。

    :param request: HTTP-like callback 请求。
    :param headers: 小写 header mapping。
    :returns: 需要拒绝时返回 response，否则返回 ``None``。
    """

    if request.method.upper() != "POST":
        return _transport_rejected_response(400, "invalid_method")
    content_type = headers.get("content-type")
    if content_type is None or content_type.strip() == "":
        return _transport_rejected_response(415, "missing_content_type")
    if not _is_json_content_type(content_type):
        return _transport_rejected_response(415, "unsupported_content_type")
    body = _json_object_or_none(request.body)
    if body is None:
        return None
    body_wait_id = body.get("wait_id")
    if isinstance(body_wait_id, str) and body_wait_id != request.path_wait_id:
        return _transport_rejected_response(400, "path_body_wait_mismatch")
    return None


def _missing_request_id_response_or_none(
    request: WaitCallbackHttpRequest, headers: Mapping[str, str]
) -> WaitCallbackHttpResponse | None:
    """在构造 Host envelope 前检查 request id 是否缺失。

    :param request: HTTP-like callback 请求。
    :param headers: 小写 header mapping。
    :returns: request id 缺失时返回 response，否则返回 ``None``。
    """

    if headers.get("x-dayu-callback-request-id") is not None:
        return None
    body = _json_object_or_none(request.body)
    if body is None:
        return None
    if body.get("request_id") is not None:
        return None
    return _service_response(
        status_code=400,
        status=WaitCallbackEndpointStatus.MALFORMED_PAYLOAD.value,
        diagnostic_code=_MISSING_REQUEST_ID_DIAGNOSTIC_CODE,
        message="callback request id is missing",
        retryable=False,
        run=None,
    )


def _completion_envelope_from_request(
    request: WaitCallbackHttpRequest, headers: Mapping[str, str]
) -> WaitCallbackCompletionEnvelope:
    """把 HTTP-like request 转为 Host callback envelope。

    :param request: HTTP-like callback 请求。
    :param headers: 小写 header mapping。
    :returns: Host callback completion envelope。
    :raises TypeError: body JSON shape 非对象时抛出。
    :raises ValueError: 必填字段缺失、类型非法或 Host dataclass 校验失败时抛出。
    """

    body = _require_json_object(request.body, "body")
    wait_id = _required_string(body, "wait_id")
    if wait_id != request.path_wait_id:
        raise ValueError("body.wait_id must match path wait id")
    outcome = _outcome_from_json(_required_object(body, "outcome"))
    return WaitCallbackCompletionEnvelope(
        wait_id=wait_id,
        idempotency_key=_required_string(body, "idempotency_key"),
        payload_digest=_required_string(body, "payload_digest"),
        observed_at=_required_utc_datetime(body, "observed_at"),
        completed_at=_required_utc_datetime(body, "completed_at"),
        outcome=outcome,
        auth=_auth_input_from_transport(headers, body),
        request_id=_request_id_from_transport(headers, body),
        correlation_id=_optional_string_from_transport(
            headers,
            body,
            header_name="x-dayu-callback-correlation-id",
            body_name="correlation_id",
        ),
    )


def _auth_input_from_transport(
    headers: Mapping[str, str], body: JsonObject
) -> WaitCallbackAuthInput:
    """从 headers/body 提取 callback 认证输入。

    :param headers: 小写 header mapping。
    :param body: JSON body object。
    :returns: Host callback auth input。
    """

    auth_source = _optional_string_from_transport(
        headers,
        body,
        header_name="x-dayu-callback-auth-source",
        body_name="auth_source",
    )
    credential_ref = _optional_string_from_transport(
        headers,
        body,
        header_name="x-dayu-callback-credential-ref",
        body_name="credential_ref",
    )
    if credential_ref is None:
        credential_ref = _credential_ref_from_authorization(headers)
    return WaitCallbackAuthInput(
        auth_source=auth_source if auth_source is not None else "missing",
        credential_ref=credential_ref if credential_ref is not None else "missing",
        presented_claims=_authorization_claims_from_body(body),
    )


def _credential_ref_from_authorization(headers: Mapping[str, str]) -> str | None:
    """从 Authorization header 提取凭据引用。

    :param headers: 小写 header mapping。
    :returns: bearer token 文本或 ``None``。
    """

    authorization = headers.get("authorization")
    if authorization is None:
        return None
    stripped = authorization.strip()
    if stripped == "":
        return None
    bearer_prefix = "Bearer "
    if stripped.startswith(bearer_prefix):
        token = stripped[len(bearer_prefix) :].strip()
        return token if token != "" else None
    return stripped


def _authorization_claims_from_body(body: JsonObject) -> tuple[AuthorizationClaim, ...]:
    """从 body 中读取可选 presented claims。

    :param body: JSON body object。
    :returns: 授权声明 tuple。
    :raises TypeError: claims shape 非数组或元素非对象时抛出。
    :raises ValueError: claim 字段缺失或为空时抛出。
    """

    raw_claims = body.get("authorization_claims")
    if raw_claims is None:
        return ()
    if not isinstance(raw_claims, list):
        raise TypeError("authorization_claims must be list")
    claims: list[AuthorizationClaim] = []
    for raw_claim in raw_claims:
        claim = _require_json_object(raw_claim, "authorization_claims[]")
        claims.append(
            AuthorizationClaim(
                name=_required_string(claim, "name"),
                value=_required_string(claim, "value"),
            )
        )
    return tuple(claims)


def _request_id_from_transport(headers: Mapping[str, str], body: JsonObject) -> str:
    """从 headers/body 提取 request id。

    :param headers: 小写 header mapping。
    :param body: JSON body object。
    :returns: request id。
    """

    request_id = _optional_string_from_transport(
        headers,
        body,
        header_name="x-dayu-callback-request-id",
        body_name="request_id",
    )
    if request_id is None:
        raise ValueError("request_id is required")
    return request_id


def _optional_string_from_transport(
    headers: Mapping[str, str],
    body: JsonObject,
    *,
    header_name: str,
    body_name: str,
) -> str | None:
    """按 header 优先级读取可选字符串字段。

    :param headers: 小写 header mapping。
    :param body: JSON body object。
    :param header_name: 小写 header 名称。
    :param body_name: body 字段名。
    :returns: 字段值或 ``None``。
    :raises TypeError: 字段存在但不是字符串时抛出。
    :raises ValueError: 字段存在但为空时抛出。
    """

    header_value = headers.get(header_name)
    if header_value is not None:
        return _validated_optional_string(header_value, header_name)
    body_value = body.get(body_name)
    if body_value is None:
        return None
    if not isinstance(body_value, str):
        raise TypeError(f"{body_name} must be str")
    return _validated_optional_string(body_value, body_name)


def _outcome_from_json(raw: JsonObject) -> (
    ResolveWaitCompletedOutcome
    | ResolveWaitFailedOutcome
    | ResolveWaitCancelledOutcome
    | ResolveWaitLostOutcome
):
    """把 callback outcome JSON 转为 Host resolve wait outcome。

    :param raw: outcome JSON object。
    :returns: Host resolve wait outcome dataclass。
    :raises TypeError: outcome shape 非法时抛出。
    :raises ValueError: outcome kind 或字段值非法时抛出。
    """

    kind = WaitCallbackOutcomeKind(_required_string(raw, "kind"))
    if kind is WaitCallbackOutcomeKind.COMPLETED:
        return ResolveWaitCompletedOutcome(
            result=_tool_result_success_from_json(_required_object(raw, "result")),
            payload_ref=_payload_ref_from_json(raw.get("payload_ref")),
        )
    if kind is WaitCallbackOutcomeKind.FAILED:
        failure = _required_object(raw, "failure")
        return ResolveWaitFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error=_required_string(failure, "error_code"),
                message=_required_string(failure, "message"),
                hint=_optional_string(failure, "hint"),
                meta=_tool_result_meta_from_json(failure.get("meta")),
            ),
            payload_ref=_payload_ref_from_json(raw.get("payload_ref")),
        )
    if kind is WaitCallbackOutcomeKind.CANCELLED:
        cancelled = _required_object(raw, "cancelled")
        reason = _tool_cancelled_reason(_required_string(cancelled, "reason_code"))
        return ResolveWaitCancelledOutcome(
            result=ToolCancelledOutcome(
                reason=reason,
                message=_required_string(cancelled, "message"),
                hint=_optional_string(cancelled, "hint"),
                meta=_tool_result_meta_from_json(cancelled.get("meta")),
            ),
            payload_ref=_payload_ref_from_json(raw.get("payload_ref")),
        )
    return ResolveWaitLostOutcome(
        reason_code=_required_string(raw, "reason_code"),
        message=_required_string(raw, "message"),
        provider_status_ref=_provider_status_ref_from_json(
            raw.get("provider_status_ref")
        ),
    )


def _tool_result_success_from_json(raw: JsonObject) -> ToolResultSuccess:
    """把 completed result JSON 转为工具成功结果。

    :param raw: result JSON object。
    :returns: 工具成功结果。
    :raises ValueError: ``ok`` 不是 ``True`` 时抛出。
    """

    ok_value = raw.get("ok")
    if ok_value is not True:
        raise ValueError("completed result.ok must be true")
    return ToolResultSuccess(
        ok=True,
        value=raw.get("value"),
        meta=_tool_result_meta_from_json(raw.get("meta")),
    )


def _tool_result_meta_from_json(raw: JsonValue) -> ToolResultMeta | None:
    """把可选工具结果 meta JSON 转为 typed meta。

    :param raw: meta JSON 值。
    :returns: 工具结果 meta 或 ``None``。
    :raises TypeError: meta 不是对象时抛出。
    :raises ValueError: 必填字段缺失或 timestamp 非 UTC 时抛出。
    """

    if raw is None:
        return None
    meta = _require_json_object(raw, "meta")
    return ToolResultMeta(
        tool_name=_required_string(meta, "tool_name"),
        started_at=_required_utc_datetime(meta, "started_at"),
        finished_at=_required_utc_datetime(meta, "finished_at"),
    )


def _payload_ref_from_json(raw: JsonValue) -> HostPayloadRef | None:
    """把可选 payload ref JSON 转为 Host payload ref。

    :param raw: payload ref JSON 值。
    :returns: Host payload ref 或 ``None``。
    :raises TypeError: payload ref 不是对象时抛出。
    :raises ValueError: 字段缺失或 digest 非法时抛出。
    """

    if raw is None:
        return None
    payload_ref = _require_json_object(raw, "payload_ref")
    return HostPayloadRef(
        payload_ref=_required_string(payload_ref, "payload_ref"),
        payload_digest=_required_string(payload_ref, "payload_digest"),
    )


def _provider_status_ref_from_json(raw: JsonValue) -> WaitProviderStatusRef | None:
    """把可选 provider status ref JSON 转为 Host typed ref。

    :param raw: provider status ref JSON 值。
    :returns: Host provider status ref 或 ``None``。
    :raises TypeError: ref shape 非对象时抛出。
    :raises ValueError: 字段缺失或 digest 非法时抛出。
    """

    if raw is None:
        return None
    status_ref = _require_json_object(raw, "provider_status_ref")
    return WaitProviderStatusRef(
        adapter_key=WaitAdapterKey(_required_string(status_ref, "adapter_key")),
        status_ref=_required_string(status_ref, "status_ref"),
        status_digest=_optional_string(status_ref, "status_digest"),
    )


def _tool_cancelled_reason(value: str) -> ToolCancelledReason:
    """校验并收窄工具取消 reason。

    :param value: reason 文本。
    :returns: 工具取消 reason。
    :raises ValueError: reason 不属于 Host 现有取消 reason 集合时抛出。
    """

    if value not in ALLOWED_TOOL_CANCELLED_REASONS:
        raise ValueError("cancelled.reason_code is not supported")
    return value


def _required_utc_datetime(raw: JsonObject, name: str) -> datetime:
    """读取并解析 UTC datetime 字段。

    :param raw: JSON object。
    :param name: 字段名。
    :returns: timezone-aware UTC datetime。
    :raises ValueError: 字段不是合法 UTC timestamp 时抛出。
    """

    text = _required_string(raw, name)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"{name} must be UTC timestamp")
    return parsed.astimezone(UTC)


def _required_object(raw: JsonObject, name: str) -> JsonObject:
    """从 JSON object 中读取必填 object 字段。

    :param raw: JSON object。
    :param name: 字段名。
    :returns: 字段 JSON object。
    :raises TypeError: 字段不是对象时抛出。
    :raises ValueError: 字段缺失时抛出。
    """

    value = raw.get(name)
    if value is None:
        raise ValueError(f"{name} is required")
    return _require_json_object(value, name)


def _required_string(raw: JsonObject, name: str) -> str:
    """从 JSON object 中读取必填非空字符串字段。

    :param raw: JSON object。
    :param name: 字段名。
    :returns: 非空字符串。
    :raises TypeError: 字段不是字符串时抛出。
    :raises ValueError: 字段缺失或为空时抛出。
    """

    value = raw.get(name)
    if value is None:
        raise ValueError(f"{name} is required")
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    return _validated_optional_string(value, name)


def _optional_string(raw: JsonObject, name: str) -> str | None:
    """从 JSON object 中读取可选非空字符串字段。

    :param raw: JSON object。
    :param name: 字段名。
    :returns: 字符串或 ``None``。
    :raises TypeError: 字段存在但不是字符串时抛出。
    :raises ValueError: 字段存在但为空时抛出。
    """

    value = raw.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    return _validated_optional_string(value, name)


def _require_json_object(value: JsonValue, field_name: str) -> JsonObject:
    """校验 JSON 值为 object。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON object。
    :raises TypeError: ``value`` 不是 mapping 或 key 不是字符串时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be object")
    for key in value:
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be str")
    return value


def _json_object_or_none(value: JsonValue) -> JsonObject | None:
    """尝试把 JSON 值收窄为 object。

    :param value: JSON 值。
    :returns: 是 object 时返回 mapping，否则返回 ``None``。
    """

    if not isinstance(value, Mapping):
        return None
    for key in value:
        if not isinstance(key, str):
            return None
    return value


def _validated_optional_string(value: str, field_name: str) -> str:
    """校验字符串字段非空。

    :param value: 字符串值。
    :param field_name: 字段名。
    :returns: 原字符串。
    :raises ValueError: 字符串为空或纯空白时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")
    return value


def _transport_rejected_response(
    status_code: int, diagnostic_code: str
) -> WaitCallbackHttpResponse:
    """构造 transport rejected response。

    :param status_code: HTTP status code。
    :param diagnostic_code: 机器可读诊断码。
    :returns: HTTP-like response。
    """

    return _service_response(
        status_code=status_code,
        status=WaitCallbackEndpointStatus.TRANSPORT_REJECTED.value,
        diagnostic_code=diagnostic_code,
        message="callback request rejected by transport mapper",
        retryable=False,
        run=None,
    )


def _adapter_response(result: WaitCallbackAdapterResult) -> WaitCallbackHttpResponse:
    """把 Host callback adapter result 映射为 HTTP-like response。

    :param result: Host callback adapter result。
    :returns: HTTP-like response。
    """

    return _service_response(
        status_code=_http_status_code_for_adapter_result(result),
        status=result.status.value,
        diagnostic_code=result.diagnostic_code,
        message=result.message,
        retryable=result.retryable,
        run=result.run,
    )


def _http_status_code_for_adapter_result(result: WaitCallbackAdapterResult) -> int:
    """把 Host callback adapter status 映射为 HTTP status code。

    :param result: Host callback adapter result。
    :returns: HTTP status code。
    """

    if result.status is WaitCallbackAdapterStatus.ACCEPTED:
        return 202
    if result.status is WaitCallbackAdapterStatus.REPLAYED:
        return 200
    if result.status is WaitCallbackAdapterStatus.UNKNOWN_WAIT:
        return 404
    if result.status is WaitCallbackAdapterStatus.AUTH_FAILED:
        return _auth_failed_status_code(result.diagnostic_code)
    if result.status is WaitCallbackAdapterStatus.DIGEST_MISMATCH:
        return 400
    if result.status in {
        WaitCallbackAdapterStatus.IDEMPOTENCY_CONFLICT,
        WaitCallbackAdapterStatus.INVALID_WAIT_STATE,
    }:
        return 409
    if result.status in {
        WaitCallbackAdapterStatus.LATE_WAIT_CANCELLED,
        WaitCallbackAdapterStatus.LATE_WAIT_LOST,
    }:
        return 410
    return 500


def _auth_failed_status_code(diagnostic_code: str) -> int:
    """按认证拒绝 reason code 映射 401/403。

    :param diagnostic_code: Host authenticator 给出的 reason code。
    :returns: 认证失败 HTTP status code。
    """

    forbidden_codes = frozenset(
        {
            "forbidden",
            "forbidden_credential",
            "credential_forbidden",
            "insufficient_permission",
            "permission_denied",
        }
    )
    if diagnostic_code in forbidden_codes:
        return 403
    return 401


def _service_response(
    *,
    status_code: int,
    status: str,
    diagnostic_code: str,
    message: str,
    retryable: bool,
    run: RunSnapshot | None,
) -> WaitCallbackHttpResponse:
    """构造统一 JSON response body。

    :param status_code: HTTP status code。
    :param status: typed 状态。
    :param diagnostic_code: 机器可读诊断码。
    :param message: 人类可读说明。
    :param retryable: 是否可重试。
    :param run: 可选 Run snapshot。
    :returns: HTTP-like response。
    """

    body: dict[str, JsonValue] = {
        "status": status,
        "diagnostic_code": diagnostic_code,
        "message": message,
        "retryable": retryable,
    }
    if run is not None:
        body["run_id"] = run.run_id
        body["run_status"] = run.status.value
    return WaitCallbackHttpResponse(status_code=status_code, body=body)


def _is_json_content_type(content_type: str) -> bool:
    """判断 content type 是否为 JSON。

    :param content_type: Content-Type header 值。
    :returns: 是 JSON content type 时返回 ``True``。
    """

    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == "application/json"


def _require_non_empty(value: str, field_name: str) -> None:
    """校验字符串非空。

    :param value: 待校验字符串。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: ``value`` 不是字符串时抛出。
    :raises ValueError: ``value`` 为空或纯空白时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


__all__ = [
    "HeaderEntry",
    "WaitCallbackEndpointAdapter",
    "WaitCallbackEndpointStatus",
    "WaitCallbackHttpRequest",
    "WaitCallbackHttpResponse",
    "handle_wait_callback_completion",
]
