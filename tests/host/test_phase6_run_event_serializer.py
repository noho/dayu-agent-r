"""Host P6 RunEventData 序列化注册表行为测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.engine import (
    ContentDeltaData,
    FinalAnswerData,
    FinishReason,
    ProviderProtocolErrorData,
    RunCancelledData,
    RunFailedData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
)
from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host._run_event_serializer import (
    CURRENT_SCHEMA_VERSION,
    deserialize_run_event_data,
    is_known_run_event_type,
    serialize_run_event_data,
)
from dayu.host.contracts import (
    HostRunFailedData,
    RunEventType,
    UserInputAcceptedData,
    UserInputScope,
)


def _utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def test_round_trip_content_delta() -> None:
    """ContentDeltaData JSON round trip。"""

    original = ContentDeltaData(iteration_id="iter-1", delta="hello")
    raw = serialize_run_event_data(event_type=RunEventType.RUNNER_CONTENT_DELTA, data=original)
    decoded = deserialize_run_event_data(event_type=RunEventType.RUNNER_CONTENT_DELTA, raw=raw)
    assert decoded == original


def test_round_trip_final_answer() -> None:
    """FinalAnswerData round trip 保持 finish_reason 枚举。"""

    original = FinalAnswerData(
        content="ok",
        filtered=False,
        degraded=False,
        finish_reason=FinishReason.STOP,
    )
    raw = serialize_run_event_data(event_type=RunEventType.FINAL_ANSWER, data=original)
    decoded = deserialize_run_event_data(event_type=RunEventType.FINAL_ANSWER, raw=raw)
    assert decoded == original


def test_run_failed_engine_vs_host_variants_distinguished() -> None:
    """RUN_FAILED 同时支持 Engine 和 Host 变体，靠 exception_type 区分。"""

    engine = RunFailedData(error_code="model_unavailable", message="m", recoverable=False)
    raw_engine = serialize_run_event_data(event_type=RunEventType.RUN_FAILED, data=engine)
    decoded_engine = deserialize_run_event_data(event_type=RunEventType.RUN_FAILED, raw=raw_engine)
    assert isinstance(decoded_engine, RunFailedData)
    assert decoded_engine == engine

    host = HostRunFailedData(
        error_code="worker_internal_error",
        message="boom",
        recoverable=False,
        exception_type="RuntimeError",
    )
    raw_host = serialize_run_event_data(event_type=RunEventType.RUN_FAILED, data=host)
    decoded_host = deserialize_run_event_data(event_type=RunEventType.RUN_FAILED, raw=raw_host)
    assert isinstance(decoded_host, HostRunFailedData)
    assert decoded_host == host


def test_run_failed_message_scrubs_explicit_credentials() -> None:
    """Engine RUN_FAILED message 写入 EventLog 前必须清洗显式凭证。"""

    raw = serialize_run_event_data(
        event_type=RunEventType.RUN_FAILED,
        data=RunFailedData(
            error_code="http_401",
            message="provider rejected api_key=sk-secret",
            recoverable=False,
        ),
    )
    decoded = deserialize_run_event_data(
        event_type=RunEventType.RUN_FAILED,
        raw=raw,
    )
    assert isinstance(decoded, RunFailedData)
    assert decoded.message == "provider rejected api_key=***"
    assert "sk-secret" not in raw


def test_provider_protocol_error_scrubs_message_and_raw_payload() -> None:
    """PROVIDER_PROTOCOL_ERROR 的 message / raw_payload 都要清洗显式凭证。"""

    raw = serialize_run_event_data(
        event_type=RunEventType.PROVIDER_PROTOCOL_ERROR,
        data=ProviderProtocolErrorData(
            iteration_id="iter-1",
            error_code="bad_sse",
            message="Authorization: Bearer sk-secret",
            provider_request_id="req-1",
            raw_payload={
                "api_key": "sk-payload",
                "cursor": "ordinary-cursor",
            },
            partial_tool_calls=(
                PartialToolCallSummary(
                    tool_call_index=0,
                    tool_call_id="call-1",
                    name_fragment="lookup",
                    arguments_byte_size=5,
                    arguments_sha256="abc",
                ),
            ),
        ),
    )
    decoded = deserialize_run_event_data(
        event_type=RunEventType.PROVIDER_PROTOCOL_ERROR,
        raw=raw,
    )
    assert isinstance(decoded, ProviderProtocolErrorData)
    assert decoded.message == "Authorization: ***"
    assert decoded.raw_payload == {
        "api_key": "***",
        "cursor": "ordinary-cursor",
    }
    assert decoded.partial_tool_calls[0].tool_call_id == "call-1"
    assert "sk-secret" not in raw
    assert "sk-payload" not in raw


def test_provider_protocol_error_requires_partial_tool_calls_field() -> None:
    """缺失 partial_tool_calls 字段必须 fail-fast；显式空列表才表示无 partial。"""

    raw_missing = f"""
    {{
        "schema_version": {CURRENT_SCHEMA_VERSION},
        "type_name": "{RunEventType.PROVIDER_PROTOCOL_ERROR.value}::ProviderProtocolErrorData",
        "fields": {{
            "iteration_id": "iter-1",
            "error_code": "bad_sse",
            "message": "m",
            "provider_request_id": null,
            "raw_payload": null
        }}
    }}
    """
    with pytest.raises(ValueError):
        deserialize_run_event_data(
            event_type=RunEventType.PROVIDER_PROTOCOL_ERROR,
            raw=raw_missing,
        )

    raw_empty = f"""
    {{
        "schema_version": {CURRENT_SCHEMA_VERSION},
        "type_name": "{RunEventType.PROVIDER_PROTOCOL_ERROR.value}::ProviderProtocolErrorData",
        "fields": {{
            "iteration_id": "iter-1",
            "error_code": "bad_sse",
            "message": "m",
            "provider_request_id": null,
            "raw_payload": null,
            "partial_tool_calls": []
        }}
    }}
    """
    decoded = deserialize_run_event_data(
        event_type=RunEventType.PROVIDER_PROTOCOL_ERROR,
        raw=raw_empty,
    )
    assert isinstance(decoded, ProviderProtocolErrorData)
    assert decoded.partial_tool_calls == ()


def test_run_cancelled_round_trip_preserves_timestamps() -> None:
    """RunCancelledData ISO 时间戳 round trip。"""

    now = _utc()
    original = RunCancelledData(
        reason="user_cancel",
        requested_at=now,
        accepted_at=now,
        finished_at=now,
    )
    raw = serialize_run_event_data(event_type=RunEventType.RUN_CANCELLED, data=original)
    decoded = deserialize_run_event_data(event_type=RunEventType.RUN_CANCELLED, raw=raw)
    assert isinstance(decoded, RunCancelledData)
    assert decoded.requested_at == now


def test_user_input_accepted_round_trip() -> None:
    """UserInputAcceptedData scope 枚举 round trip。"""

    original = UserInputAcceptedData(turn_id="t1", content="hi", scope=UserInputScope.SESSION)
    raw = serialize_run_event_data(event_type=RunEventType.USER_INPUT_ACCEPTED, data=original)
    decoded = deserialize_run_event_data(event_type=RunEventType.USER_INPUT_ACCEPTED, raw=raw)
    assert decoded == original


def test_tool_payload_serializer_scrubs_credentials_and_retains_capabilities() -> None:
    """普通工具 payload 只清洗显式凭证，保留 cursor / scope_token。"""

    requested = ToolCallRequestedData(
        iteration_id="iter-1",
        tool_call_id="tc-1",
        name="fetch_more",
        arguments={
            "API_KEY": "sk-secret",
            "debug_text": "Authorization: Bearer sk-debug",
            "cursor": "cursor-raw",
            "scope_token": "scope-raw",
            "token": "ordinary-token",
        },
        index_in_iteration=0,
        provider_state=None,
    )
    raw_requested = serialize_run_event_data(
        event_type=RunEventType.TOOL_CALL_REQUESTED,
        data=requested,
    )
    decoded_requested = deserialize_run_event_data(
        event_type=RunEventType.TOOL_CALL_REQUESTED,
        raw=raw_requested,
    )
    assert isinstance(decoded_requested, ToolCallRequestedData)
    assert decoded_requested.arguments["API_KEY"] == "***"
    assert decoded_requested.arguments["debug_text"] == "Authorization: ***"
    assert decoded_requested.arguments["cursor"] == "cursor-raw"
    assert decoded_requested.arguments["scope_token"] == "scope-raw"
    assert decoded_requested.arguments["token"] == "ordinary-token"

    accepted = ToolResultAcceptedData(
        iteration_id="iter-1",
        tool_call_id="tc-1",
        name="demo",
        index_in_iteration=0,
        outcome=ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "api_key": "sk-result",
                    "debug_text": "x-api-key: sk-result-text",
                    "cursor": "cursor-result",
                    "scope_token": "scope-result",
                    "token": "ordinary-result-token",
                    "truncation": {
                        "fetch_more_args": {
                            "cursor": "cursor-truncation",
                            "limit": 10,
                            "scope_token": "scope-truncation",
                        },
                        "has_more": True,
                        "next_action": "fetch_more",
                        "ttl_seconds": 60,
                    },
                },
                meta=None,
            )
        ),
    )
    raw_accepted = serialize_run_event_data(
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        data=accepted,
    )
    decoded_accepted = deserialize_run_event_data(
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        raw=raw_accepted,
    )
    assert isinstance(decoded_accepted, ToolResultAcceptedData)
    assert isinstance(decoded_accepted.outcome, ToolCompletedOutcome)
    value = decoded_accepted.outcome.result.value
    assert isinstance(value, dict)
    assert value["api_key"] == "***"
    assert value["debug_text"] == "x-api-key: ***"
    assert value["cursor"] == "cursor-result"
    assert value["scope_token"] == "scope-result"
    assert value["token"] == "ordinary-result-token"
    truncation = value["truncation"]
    assert isinstance(truncation, dict)
    fetch_more_args = truncation["fetch_more_args"]
    assert isinstance(fetch_more_args, dict)
    assert fetch_more_args["cursor"] == "cursor-truncation"
    assert fetch_more_args["scope_token"] == "scope-truncation"


def test_deserialize_rejects_legacy_top_level_tool_result_truncation() -> None:
    """旧 success result 顶层 truncation schema 必须 fail-fast。"""

    raw = f"""
    {{
        "schema_version": {CURRENT_SCHEMA_VERSION},
        "type_name": "{RunEventType.TOOL_RESULT_ACCEPTED.value}::ToolResultAcceptedData",
        "fields": {{
            "iteration_id": "iter-1",
            "tool_call_id": "tc-1",
            "name": "demo",
            "index_in_iteration": 0,
            "outcome": {{
                "kind": "completed",
                "result": {{
                    "ok": true,
                    "value": {{"content": "short"}},
                    "truncation": {{
                        "cursor": "legacy-cursor",
                        "scope_token": "legacy-scope",
                        "scope_hash": "legacy-scope-hash",
                        "has_more": true
                    }},
                    "meta": null
                }}
            }}
        }}
    }}
    """

    with pytest.raises(ValueError, match="legacy top-level truncation"):
        deserialize_run_event_data(
            event_type=RunEventType.TOOL_RESULT_ACCEPTED,
            raw=raw,
        )


def test_deserialize_tool_result_success_requires_value_key() -> None:
    """success result 缺少必填 value 字段必须 fail-fast。"""

    raw = f"""
    {{
        "schema_version": {CURRENT_SCHEMA_VERSION},
        "type_name": "{RunEventType.TOOL_RESULT_ACCEPTED.value}::ToolResultAcceptedData",
        "fields": {{
            "iteration_id": "iter-1",
            "tool_call_id": "tc-1",
            "name": "demo",
            "index_in_iteration": 0,
            "outcome": {{
                "kind": "completed",
                "result": {{
                    "ok": true,
                    "meta": null
                }}
            }}
        }}
    }}
    """

    with pytest.raises(ValueError, match="missing value"):
        deserialize_run_event_data(
            event_type=RunEventType.TOOL_RESULT_ACCEPTED,
            raw=raw,
        )


def test_deserialize_tool_result_success_allows_explicit_null_value() -> None:
    """success result 显式 ``value: null`` 是合法 JSON null。"""

    raw = f"""
    {{
        "schema_version": {CURRENT_SCHEMA_VERSION},
        "type_name": "{RunEventType.TOOL_RESULT_ACCEPTED.value}::ToolResultAcceptedData",
        "fields": {{
            "iteration_id": "iter-1",
            "tool_call_id": "tc-1",
            "name": "demo",
            "index_in_iteration": 0,
            "outcome": {{
                "kind": "completed",
                "result": {{
                    "ok": true,
                    "value": null,
                    "meta": null
                }}
            }}
        }}
    }}
    """

    decoded = deserialize_run_event_data(
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        raw=raw,
    )
    assert isinstance(decoded, ToolResultAcceptedData)
    assert isinstance(decoded.outcome, ToolCompletedOutcome)
    assert decoded.outcome.result.value is None


def test_serialize_rejects_type_data_mismatch() -> None:
    """event_type 与 data 不匹配必须 fail-fast。"""

    with pytest.raises(ValueError):
        serialize_run_event_data(
            event_type=RunEventType.FINAL_ANSWER,
            data=ContentDeltaData(iteration_id="x", delta="y"),
        )


def test_deserialize_rejects_unsupported_schema_version() -> None:
    """schema_version 不匹配必须 fail-fast。"""

    raw = '{"schema_version": 999, "type_name": "final_answer::FinalAnswerData",' ' "fields": {}}'
    with pytest.raises(ValueError):
        deserialize_run_event_data(event_type=RunEventType.FINAL_ANSWER, raw=raw)


def test_deserialize_rejects_type_name_mismatch() -> None:
    """type_name 与 event_type 不匹配必须 fail-fast。"""

    raw = '{"schema_version": 1, "type_name": "wrong::FinalAnswerData",' ' "fields": {}}'
    with pytest.raises(ValueError):
        deserialize_run_event_data(event_type=RunEventType.FINAL_ANSWER, raw=raw)


def test_schema_version_is_current() -> None:
    """schema_version 注册表常量与序列化输出一致。"""

    raw = serialize_run_event_data(
        event_type=RunEventType.RUNNER_CONTENT_DELTA,
        data=ContentDeltaData(iteration_id="i", delta="d"),
    )
    assert f'"schema_version": {CURRENT_SCHEMA_VERSION}' in raw


def test_is_known_run_event_type_covers_canonical_types() -> None:
    """常见 canonical 类型在注册表内。"""

    assert is_known_run_event_type(RunEventType.FINAL_ANSWER)
    assert is_known_run_event_type(RunEventType.RUNNER_CONTENT_DELTA)
    assert is_known_run_event_type(RunEventType.USER_INPUT_ACCEPTED)
