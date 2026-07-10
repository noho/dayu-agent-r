"""Service wait callback endpoint mapper 测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeAlias

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host import (
    HostStreamCursor,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    RunSnapshot,
    RunStatus,
    WaitCallbackAdapterResult,
    WaitCallbackAdapterStatus,
    WaitCallbackCompletionEnvelope,
)
from dayu.service.wait_callback_endpoint import (
    HeaderEntry,
    WaitCallbackHttpRequest,
    WaitCallbackHttpResponse,
    handle_wait_callback_completion,
)


JsonObject: TypeAlias = dict[str, JsonValue]

_VALID_DIGEST = "sha256:" + ("0" * 64)


@dataclass(slots=True)
class _FakeAdapter:
    """测试用 Host callback adapter。

    :param result: adapter 返回结果。
    :param envelopes: 已收到的 callback envelope。
    """

    result: WaitCallbackAdapterResult
    envelopes: list[WaitCallbackCompletionEnvelope]

    def resolve_callback(
        self, envelope: WaitCallbackCompletionEnvelope
    ) -> WaitCallbackAdapterResult:
        """记录 envelope 并返回预设结果。

        :param envelope: Host callback completion envelope。
        :returns: 预设 adapter result。
        """

        self.envelopes.append(envelope)
        return self.result


def test_valid_request_calls_adapter_with_typed_envelope_and_returns_accepted() -> None:
    """合法 HTTP-like 请求会构造 typed envelope 并把 accepted 映射为 202。"""

    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))
    response = handle_wait_callback_completion(_request(_completed_body()), adapter)

    assert response.status_code == 202
    assert response.body == {
        "status": "accepted",
        "diagnostic_code": "accepted",
        "message": "accepted",
        "retryable": False,
        "run_id": "run-1",
        "run_status": "waiting",
    }
    assert len(adapter.envelopes) == 1
    envelope = adapter.envelopes[0]
    assert envelope.wait_id == "wait-1"
    assert envelope.idempotency_key == "completion-1"
    assert envelope.payload_digest == _VALID_DIGEST
    assert envelope.observed_at == datetime(2026, 6, 21, 10, 0, 1, tzinfo=UTC)
    assert envelope.completed_at == datetime(2026, 6, 21, 10, 0, tzinfo=UTC)
    assert envelope.auth.auth_source == "bearer"
    assert envelope.auth.credential_ref == "token-1"
    assert envelope.request_id == "request-1"
    assert envelope.correlation_id == "correlation-1"
    assert isinstance(envelope.outcome, ResolveWaitCompletedOutcome)


def test_valid_replay_request_returns_200() -> None:
    """Host adapter replay 状态会映射为 HTTP 200。"""

    adapter = _adapter(
        _adapter_result(
            WaitCallbackAdapterStatus.REPLAYED,
            idempotent_replay=True,
        )
    )

    response = handle_wait_callback_completion(_request(_completed_body()), adapter)

    assert response.status_code == 200
    assert _body_string(response, "status") == "replayed"
    assert len(adapter.envelopes) == 1


def test_path_body_wait_mismatch_returns_transport_rejected_without_adapter_call() -> None:
    """path/body wait id 不一致时返回 transport_rejected 且不调用 adapter。"""

    body = _completed_body()
    body["wait_id"] = "other-wait"
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(_request(body), adapter)

    assert response.status_code == 400
    assert _body_string(response, "status") == "transport_rejected"
    assert _body_string(response, "diagnostic_code") == "path_body_wait_mismatch"
    assert adapter.envelopes == []


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH"])
def test_non_post_method_returns_transport_rejected_without_adapter_call(
    method: str,
) -> None:
    """非 POST method 会返回 transport_rejected 且不调用 adapter。"""

    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))
    request = WaitCallbackHttpRequest(
        method=method,
        path_wait_id="wait-1",
        headers=_default_headers(),
        body=_completed_body(),
    )

    response = handle_wait_callback_completion(request, adapter)

    assert response.status_code == 400
    assert _body_string(response, "status") == "transport_rejected"
    assert _body_string(response, "diagnostic_code") == "invalid_method"
    assert adapter.envelopes == []


@pytest.mark.parametrize(
    ("headers", "expected_status", "diagnostic_code"),
    [
        (
            (
                HeaderEntry("Authorization", "Bearer token-1"),
                HeaderEntry("X-Dayu-Callback-Auth-Source", "bearer"),
                HeaderEntry("X-Dayu-Callback-Request-Id", "request-1"),
            ),
            415,
            "missing_content_type",
        ),
        (
            (
                HeaderEntry("Content-Type", "text/plain"),
                HeaderEntry("Authorization", "Bearer token-1"),
                HeaderEntry("X-Dayu-Callback-Auth-Source", "bearer"),
                HeaderEntry("X-Dayu-Callback-Request-Id", "request-1"),
            ),
            415,
            "unsupported_content_type",
        ),
    ],
)
def test_missing_or_invalid_content_type_rejected_without_adapter_call(
    headers: tuple[HeaderEntry, ...], expected_status: int, diagnostic_code: str
) -> None:
    """缺失或非法 content-type 时拒绝 transport，不调用 adapter。"""

    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(
        WaitCallbackHttpRequest(
            method="POST",
            path_wait_id="wait-1",
            headers=headers,
            body=_completed_body(),
        ),
        adapter,
    )

    assert response.status_code == expected_status
    assert _body_string(response, "status") == "transport_rejected"
    assert _body_string(response, "diagnostic_code") == diagnostic_code
    assert adapter.envelopes == []


def test_missing_request_id_returns_diagnostic_without_adapter_call() -> None:
    """header/body 均缺失 request id 时返回确定诊断码且不调用 adapter。"""

    headers = (
        HeaderEntry("Content-Type", "application/json; charset=utf-8"),
        HeaderEntry("Authorization", "Bearer token-1"),
        HeaderEntry("X-Dayu-Callback-Auth-Source", "bearer"),
    )
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(
        WaitCallbackHttpRequest(
            method="POST",
            path_wait_id="wait-1",
            headers=headers,
            body=_completed_body(),
        ),
        adapter,
    )

    assert response.status_code == 400
    assert _body_string(response, "status") == "malformed_payload"
    assert _body_string(response, "diagnostic_code") == "missing_request_id"
    assert adapter.envelopes == []


def test_body_request_id_is_used_when_header_is_missing() -> None:
    """header 缺失 request id 时使用 body request_id 作为 fallback。"""

    headers = (
        HeaderEntry("Content-Type", "application/json; charset=utf-8"),
        HeaderEntry("Authorization", "Bearer token-1"),
        HeaderEntry("X-Dayu-Callback-Auth-Source", "bearer"),
    )
    body = _completed_body()
    body["request_id"] = "body-request-1"
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(
        WaitCallbackHttpRequest(
            method="POST",
            path_wait_id="wait-1",
            headers=headers,
            body=body,
        ),
        adapter,
    )

    assert response.status_code == 202
    assert len(adapter.envelopes) == 1
    assert adapter.envelopes[0].request_id == "body-request-1"


def test_header_request_id_has_priority_over_body_request_id() -> None:
    """header 与 body 均提供 request id 时优先使用 header 值。"""

    body = _completed_body()
    body["request_id"] = "body-request-1"
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(_request(body), adapter)

    assert response.status_code == 202
    assert len(adapter.envelopes) == 1
    assert adapter.envelopes[0].request_id == "request-1"


@pytest.mark.parametrize(
    "body",
    [
        [1, 2, 3],
        "body-text",
        123,
        True,
        None,
    ],
)
def test_non_object_body_returns_malformed_payload_without_adapter_call(
    body: JsonValue,
) -> None:
    """非 object JSON body 会返回 malformed_payload 且不调用 adapter。"""

    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(
        WaitCallbackHttpRequest(
            method="POST",
            path_wait_id="wait-1",
            headers=_default_headers(),
            body=body,
        ),
        adapter,
    )

    assert response.status_code == 400
    assert _body_string(response, "status") == "malformed_payload"
    assert adapter.envelopes == []


def test_malformed_outcome_shape_returns_malformed_payload_without_adapter_call() -> None:
    """outcome shape 错误时返回 malformed_payload 且不调用 adapter。"""

    body = _completed_body()
    body["outcome"] = {"kind": "completed", "result": {"ok": False}}
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(_request(body), adapter)

    assert response.status_code == 400
    assert _body_string(response, "status") == "malformed_payload"
    assert adapter.envelopes == []


def test_string_provider_status_ref_returns_malformed_payload_without_adapter_call() -> None:
    """裸字符串 provider_status_ref 会返回 malformed_payload 且不调用 adapter。"""

    body = _lost_body()
    outcome = body["outcome"]
    assert isinstance(outcome, dict)
    outcome["provider_status_ref"] = "jobs/provider-1/status"
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(_request(body), adapter)

    assert response.status_code == 400
    assert _body_string(response, "status") == "malformed_payload"
    assert adapter.envelopes == []


def test_unknown_outcome_kind_returns_malformed_payload_without_adapter_call() -> None:
    """未知 outcome kind 会返回 malformed_payload 且不调用 adapter。"""

    body = _completed_body()
    body["outcome"] = {"kind": "unknown"}
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(_request(body), adapter)

    assert response.status_code == 400
    assert _body_string(response, "status") == "malformed_payload"
    assert adapter.envelopes == []


@pytest.mark.parametrize(
    ("field_name", "timestamp"),
    [
        ("observed_at", "not-a-date"),
        ("completed_at", "2026-06-21T10:00:00"),
        ("completed_at", "2026-06-21T18:00:00+08:00"),
    ],
)
def test_invalid_timestamp_returns_malformed_payload_without_adapter_call(
    field_name: str, timestamp: str
) -> None:
    """非法或非 UTC timestamp 会返回 malformed_payload 且不调用 adapter。"""

    body = _completed_body()
    body[field_name] = timestamp
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(_request(body), adapter)

    assert response.status_code == 400
    assert _body_string(response, "status") == "malformed_payload"
    assert adapter.envelopes == []


def test_unsupported_cancelled_reason_returns_malformed_payload_without_adapter_call() -> None:
    """不可表达的 cancelled reason 会返回 malformed_payload 且不调用 adapter。"""

    body = _base_body(
        {
            "kind": "cancelled",
            "cancelled": {
                "reason_code": "provider_cancelled",
                "message": "provider cancelled",
                "hint": None,
                "meta": None,
            },
            "payload_ref": None,
        }
    )
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(_request(body), adapter)

    assert response.status_code == 400
    assert _body_string(response, "status") == "malformed_payload"
    assert adapter.envelopes == []


@pytest.mark.parametrize(
    ("kind", "expected_type"),
    [
        ("completed", ResolveWaitCompletedOutcome),
        ("failed", ResolveWaitFailedOutcome),
        ("cancelled", ResolveWaitCancelledOutcome),
        ("lost", ResolveWaitLostOutcome),
    ],
)
def test_supported_outcome_kinds_map_to_host_outcome_dataclasses(
    kind: str,
    expected_type: type[
        ResolveWaitCompletedOutcome
        | ResolveWaitFailedOutcome
        | ResolveWaitCancelledOutcome
        | ResolveWaitLostOutcome
    ],
) -> None:
    """completed/failed/cancelled/lost 都会转成对应 Host outcome dataclass。"""

    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))
    body = _body_for_kind(kind)

    response = handle_wait_callback_completion(_request(body), adapter)

    assert response.status_code == 202
    assert len(adapter.envelopes) == 1
    assert isinstance(adapter.envelopes[0].outcome, expected_type)


@pytest.mark.parametrize(
    ("diagnostic_code", "expected_status"),
    [
        ("missing_credential", 401),
        ("malformed_credential", 401),
        ("invalid_credential", 401),
        ("expired_credential", 401),
        ("forbidden_credential", 403),
    ],
)
def test_auth_failed_maps_to_401_or_403_by_reason_code(
    diagnostic_code: str, expected_status: int
) -> None:
    """AUTH_FAILED 按 reason code 决定 401 或 403。"""

    adapter = _adapter(
        _adapter_result(
            WaitCallbackAdapterStatus.AUTH_FAILED,
            diagnostic_code=diagnostic_code,
            retryable=True,
        )
    )

    response = handle_wait_callback_completion(_request(_completed_body()), adapter)

    assert response.status_code == expected_status
    assert _body_string(response, "status") == "auth_failed"
    assert _body_string(response, "diagnostic_code") == diagnostic_code
    assert len(adapter.envelopes) == 1


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (WaitCallbackAdapterStatus.ACCEPTED, 202),
        (WaitCallbackAdapterStatus.REPLAYED, 200),
        (WaitCallbackAdapterStatus.UNKNOWN_WAIT, 404),
        (WaitCallbackAdapterStatus.DIGEST_MISMATCH, 400),
        (WaitCallbackAdapterStatus.IDEMPOTENCY_CONFLICT, 409),
        (WaitCallbackAdapterStatus.INVALID_WAIT_STATE, 409),
        (WaitCallbackAdapterStatus.LATE_WAIT_CANCELLED, 410),
        (WaitCallbackAdapterStatus.LATE_WAIT_LOST, 410),
        (WaitCallbackAdapterStatus.STALE_CALLBACK, 410),
        (WaitCallbackAdapterStatus.INTERNAL_ERROR, 500),
    ],
)
def test_adapter_statuses_map_to_http_codes_and_typed_body(
    status: WaitCallbackAdapterStatus, expected_code: int
) -> None:
    """Host adapter status 会映射到 plan 指定 HTTP code 和 typed response body。"""

    adapter = _adapter(_adapter_result(status))

    response = handle_wait_callback_completion(_request(_completed_body()), adapter)

    assert response.status_code == expected_code
    assert _body_string(response, "status") == status.value
    assert _body_string(response, "diagnostic_code") == status.value
    assert _body_bool(response, "retryable") is False


def test_run_none_response_omits_run_fields() -> None:
    """adapter result 不含 run 时 response body 不输出 run_id/run_status。"""

    adapter = _adapter(
        _adapter_result(WaitCallbackAdapterStatus.ACCEPTED, include_run=False)
    )

    response = handle_wait_callback_completion(_request(_completed_body()), adapter)

    assert response.status_code == 202
    assert isinstance(response.body, dict)
    assert "run_id" not in response.body
    assert "run_status" not in response.body


def test_response_body_does_not_echo_outcome_result_payload() -> None:
    """响应体不得回显 callback outcome result payload。"""

    body = _completed_body()
    body["outcome"] = {
        "kind": "completed",
        "result": {
            "ok": True,
            "value": {"secret_result": "do-not-echo"},
            "meta": None,
        },
        "payload_ref": None,
    }
    adapter = _adapter(_adapter_result(WaitCallbackAdapterStatus.ACCEPTED))

    response = handle_wait_callback_completion(_request(body), adapter)

    assert "do-not-echo" not in str(response.body)
    assert "secret_result" not in str(response.body)


def test_missing_authorization_is_passed_to_adapter_for_auth_classification() -> None:
    """缺失认证字段交给 adapter/authenticator 分类，不在 Service 层误判 malformed。"""

    adapter = _adapter(
        _adapter_result(
            WaitCallbackAdapterStatus.AUTH_FAILED,
            diagnostic_code="missing_credential",
        )
    )
    request = WaitCallbackHttpRequest(
        method="POST",
        path_wait_id="wait-1",
        headers=(
            HeaderEntry("Content-Type", "application/json"),
            HeaderEntry("X-Dayu-Callback-Request-Id", "request-1"),
        ),
        body=_completed_body(),
    )

    response = handle_wait_callback_completion(request, adapter)

    assert response.status_code == 401
    assert len(adapter.envelopes) == 1
    assert adapter.envelopes[0].auth.auth_source == "missing"
    assert adapter.envelopes[0].auth.credential_ref == "missing"


def _request(body: JsonObject) -> WaitCallbackHttpRequest:
    """构造默认合法 HTTP-like request。

    :param body: JSON body。
    :returns: callback HTTP-like request。
    """

    return WaitCallbackHttpRequest(
        method="POST",
        path_wait_id="wait-1",
        headers=_default_headers(),
        body=body,
    )


def _default_headers() -> tuple[HeaderEntry, ...]:
    """构造默认合法 HTTP-like headers。

    :returns: callback headers。
    """

    return (
        HeaderEntry("Content-Type", "application/json; charset=utf-8"),
        HeaderEntry("Authorization", "Bearer token-1"),
        HeaderEntry("X-Dayu-Callback-Auth-Source", "bearer"),
        HeaderEntry("X-Dayu-Callback-Request-Id", "request-1"),
        HeaderEntry("X-Dayu-Callback-Correlation-Id", "correlation-1"),
    )


def _completed_body() -> JsonObject:
    """构造 completed callback JSON body。

    :returns: callback body。
    """

    return _base_body(
        {
            "kind": "completed",
            "result": {"ok": True, "value": {"answer": 42}, "meta": None},
            "payload_ref": None,
        }
    )


def _failed_body() -> JsonObject:
    """构造 failed callback JSON body。

    :returns: callback body。
    """

    return _base_body(
        {
            "kind": "failed",
            "failure": {
                "error_code": "provider_error",
                "message": "provider failed",
                "hint": "retry later",
                "meta": None,
            },
            "payload_ref": None,
        }
    )


def _cancelled_body() -> JsonObject:
    """构造 cancelled callback JSON body。

    :returns: callback body。
    """

    return _base_body(
        {
            "kind": "cancelled",
            "cancelled": {
                "reason_code": "host_cancelled",
                "message": "cancelled by host",
                "hint": "submit again",
                "meta": None,
            },
            "payload_ref": None,
        }
    )


def _lost_body() -> JsonObject:
    """构造 lost callback JSON body。

    :returns: callback body。
    """

    return _base_body(
        {
            "kind": "lost",
            "reason_code": "provider_lost",
            "message": "provider lost job",
            "provider_status_ref": {
                "adapter_key": "callback",
                "status_ref": "jobs/provider-1/status",
                "status_digest": None,
            },
        }
    )


def _body_for_kind(kind: str) -> JsonObject:
    """按 outcome kind 构造 callback body。

    :param kind: outcome kind。
    :returns: callback body。
    :raises AssertionError: kind 未被测试覆盖时抛出。
    """

    if kind == "completed":
        return _completed_body()
    if kind == "failed":
        return _failed_body()
    if kind == "cancelled":
        return _cancelled_body()
    if kind == "lost":
        return _lost_body()
    raise AssertionError(f"unsupported test outcome kind: {kind}")


def _base_body(outcome: JsonObject) -> JsonObject:
    """构造 callback body 基础字段。

    :param outcome: outcome JSON object。
    :returns: callback body。
    """

    return {
        "wait_id": "wait-1",
        "idempotency_key": "completion-1",
        "payload_digest": _VALID_DIGEST,
        "observed_at": "2026-06-21T10:00:01.000000Z",
        "completed_at": "2026-06-21T10:00:00.000000Z",
        "outcome": outcome,
    }


def _adapter(result: WaitCallbackAdapterResult) -> _FakeAdapter:
    """构造 fake adapter。

    :param result: adapter 返回结果。
    :returns: fake adapter。
    """

    return _FakeAdapter(result=result, envelopes=[])


def _adapter_result(
    status: WaitCallbackAdapterStatus,
    *,
    diagnostic_code: str | None = None,
    retryable: bool = False,
    idempotent_replay: bool = False,
    include_run: bool = True,
) -> WaitCallbackAdapterResult:
    """构造 Host callback adapter result。

    :param status: adapter status。
    :param diagnostic_code: 可选诊断码。
    :param retryable: 是否可重试。
    :param idempotent_replay: 是否 replay。
    :param include_run: 是否返回 Run snapshot。
    :returns: adapter result。
    """

    return WaitCallbackAdapterResult(
        status=status,
        run=_run_snapshot() if include_run else None,
        idempotent_replay=idempotent_replay,
        diagnostic_code=diagnostic_code if diagnostic_code is not None else status.value,
        message=status.value,
        retryable=retryable,
    )


def _run_snapshot() -> RunSnapshot:
    """构造测试用 Run snapshot。

    :returns: Run snapshot。
    """

    return RunSnapshot(
        run_id="run-1",
        session_id="session-1",
        status=RunStatus.WAITING,
        current_attempt_id=None,
        terminal_result_summary=None,
        event_cursor=HostStreamCursor(event_sequence=1),
        source_run_id=None,
        source_run_relation=None,
        outbox_summary=None,
    )


def _body_string(response: WaitCallbackHttpResponse, key: str) -> str:
    """从 response body 读取字符串字段。

    :param response: HTTP-like response。
    :param key: 字段名。
    :returns: 字符串字段。
    """

    assert isinstance(response.body, dict)
    value = response.body[key]
    assert isinstance(value, str)
    return value


def _body_bool(response: WaitCallbackHttpResponse, key: str) -> bool:
    """从 response body 读取布尔字段。

    :param response: HTTP-like response。
    :param key: 字段名。
    :returns: 布尔字段。
    """

    assert isinstance(response.body, dict)
    value = response.body[key]
    assert isinstance(value, bool)
    return value
