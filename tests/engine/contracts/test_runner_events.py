"""``RunnerHTTPErrorCode`` / ``RunnerHTTPErrorData`` 与联合穷尽测试。

覆盖 Phase 1 contract 补丁（``docs/engine/phase1-plan.md`` §0.1）：

- ``RunnerHTTPErrorCode`` 枚举成员与 StrEnum 值。
- ``RunnerHTTPErrorData`` 字段集合与构造。
- ``RunnerEventType.RUNNER_HTTP_ERROR`` 枚举成员。
- ``RunnerEventData`` 联合包含 :class:`RunnerHTTPErrorData`。
- ``match RunnerEvent.data`` 守护 ``RunnerHTTPErrorData`` 分支。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import cast

import pytest

from dayu.engine.contracts.error_codes import (
    EngineRunErrorCode,
    RunnerSpecificErrorCode,
    RunnerSpecificErrorSource,
    runner_protocol_error_code,
    serialize_engine_error_code,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    ContextOverflowDetection,
    ContextOverflowDetectionKind,
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDiagnosticSeverity,
    RunnerDiagnosticSource,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
    RunnerProtocolErrorData,
    RunnerProviderDiagnosticData,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)


def test_runner_http_error_code_members_and_values() -> None:
    """成员、StrEnum 值与契约一致。"""

    assert {m.value for m in RunnerHTTPErrorCode} == {
        "rate_limit_exceeded",
        "server_error",
        "client_error",
        "network_error",
        "timeout",
        "context_length_exceeded",
        "unknown_http_status",
    }


def test_runner_http_error_data_field_set() -> None:
    """字段集合必须严格符合契约。"""

    fields = {f.name for f in dataclasses.fields(RunnerHTTPErrorData)}
    assert fields == {
        "error_code",
        "http_status",
        "message",
        "provider_request_id",
        "raw_payload",
        "attempt",
        "retried",
        "context_overflow_detection",
    }


def test_runner_provider_diagnostic_contract_fields() -> None:
    """非致命 provider diagnostic 字段集合必须符合契约。"""

    fields = {f.name for f in dataclasses.fields(RunnerProviderDiagnosticData)}
    assert fields == {
        "diagnostic_code",
        "severity",
        "message",
        "provider_request_id",
        "raw_payload",
        "partial_tool_calls",
        "diagnostic_source",
    }


def test_runner_provider_diagnostic_enums_are_closed() -> None:
    """diagnostic severity/source 枚举值必须锁定。"""

    assert {item.value for item in RunnerDiagnosticSeverity} == {
        "info",
        "warning",
    }
    assert {item.value for item in RunnerDiagnosticSource} == {
        "http_adapter",
        "sse_parser",
        "non_stream_parser",
        "tool_call_aggregator",
        "context_overflow_classifier",
    }
    assert {item.value for item in ContextOverflowDetectionKind} == {
        "structured_code",
        "message_marker_fallback",
        "not_overflow",
    }


def test_runner_http_error_data_construction() -> None:
    """枚举值 + 全字段构造合法。"""

    data = RunnerHTTPErrorData(
        error_code=RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
        http_status=429,
        message="rate limit",
        provider_request_id="req-1",
        raw_payload={"error": "throttle"},
        attempt=3,
        retried=True,
        context_overflow_detection=ContextOverflowDetection(
            kind=ContextOverflowDetectionKind.STRUCTURED_CODE
        ),
    )
    assert data.error_code is RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED
    assert data.http_status == 429


def test_runner_done_data_field_set() -> None:
    """RunnerDoneData 必须携带 provider request id 字段。"""

    fields = {f.name for f in dataclasses.fields(RunnerDoneData)}
    assert fields == {"finish_reason", "provider_request_id"}


def test_runner_content_completed_data_field_set() -> None:
    """正文完成事件只承载正文与推理内容。"""

    fields = {f.name for f in dataclasses.fields(RunnerContentCompletedData)}
    assert fields == {"content", "reasoning_content"}


def test_runner_usage_recorded_data_field_set() -> None:
    """Runner usage 事件必须携带 provider request id。"""

    fields = {f.name for f in dataclasses.fields(RunnerUsageRecordedData)}
    assert fields == {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "provider_request_id",
    }


def test_runner_event_type_includes_runner_http_error() -> None:
    """枚举包含 ``RUNNER_HTTP_ERROR`` 成员。"""

    assert RunnerEventType.RUNNER_HTTP_ERROR.value == "runner_http_error"
    assert RunnerEventType.PROVIDER_DIAGNOSTIC.value == "provider_diagnostic"


def _classify_event_data(data: RunnerEventData) -> str:
    """穷尽守护 :data:`RunnerEventData` 联合。"""

    match data:
        case RunnerContentDeltaData():
            return "content_delta"
        case RunnerReasoningDeltaData():
            return "reasoning_delta"
        case RunnerToolCallDeltaData():
            return "tool_call_delta"
        case RunnerToolCallsCompletedData():
            return "tool_calls_completed"
        case RunnerContentCompletedData():
            return "content_completed"
        case RunnerUsageRecordedData():
            return "usage_recorded"
        case RunnerProviderDiagnosticData():
            return "provider_diagnostic"
        case RunnerProtocolErrorData():
            return "protocol_error"
        case RunnerHTTPErrorData():
            return "http_error"
        case RunnerDoneData():
            return "done"


def test_runner_event_data_union_match_covers_http_error() -> None:
    """``match`` 必须覆盖 ``RunnerHTTPErrorData`` 分支。"""

    http_error = RunnerHTTPErrorData(
        error_code=RunnerHTTPErrorCode.SERVER_ERROR,
        http_status=503,
        message="server error",
        provider_request_id=None,
        raw_payload=None,
        attempt=1,
        retried=False,
    )
    assert _classify_event_data(http_error) == "http_error"


def test_runner_event_data_union_match_covers_provider_diagnostic() -> None:
    """``match`` 必须覆盖非致命 provider diagnostic 分支。"""

    diagnostic = RunnerProviderDiagnosticData(
        diagnostic_code="usage_field_malformed",
        severity=RunnerDiagnosticSeverity.WARNING,
        message="usage ignored",
        provider_request_id="req-diagnostic",
        raw_payload=None,
        diagnostic_source=RunnerDiagnosticSource.SSE_PARSER,
    )
    assert _classify_event_data(diagnostic) == "provider_diagnostic"


def test_runner_event_with_http_error_data_construction() -> None:
    """``RunnerEvent`` 可承载 ``RunnerHTTPErrorData``。"""

    event = RunnerEvent(
        type=RunnerEventType.RUNNER_HTTP_ERROR,
        data=RunnerHTTPErrorData(
            error_code=RunnerHTTPErrorCode.TIMEOUT,
            http_status=None,
            message="read timeout",
            provider_request_id=None,
            raw_payload=None,
            attempt=2,
            retried=True,
        ),
        occurred_at=datetime.now(tz=timezone.utc),
    )
    assert event.type is RunnerEventType.RUNNER_HTTP_ERROR


def test_runner_done_finish_reason_error_is_legal() -> None:
    """HTTP 错误最终以 ``RunnerDoneData(FinishReason.ERROR)`` 收口。"""

    done = RunnerDoneData(
        finish_reason=FinishReason.ERROR,
        provider_request_id="req-final",
    )
    assert done.finish_reason is FinishReason.ERROR
    assert done.provider_request_id == "req-final"


def test_runner_specific_error_code_trims_and_serializes() -> None:
    """provider / runner 专有错误码必须 trim 后经统一 helper 序列化。"""

    code = RunnerSpecificErrorCode(
        "  sse_invalid_json  ",
        RunnerSpecificErrorSource.RUNNER_PROTOCOL,
    )

    assert code.value == "sse_invalid_json"
    assert code.source is RunnerSpecificErrorSource.RUNNER_PROTOCOL
    assert serialize_engine_error_code(code) == "sse_invalid_json"


def test_runner_specific_error_code_rejects_empty_and_too_long() -> None:
    """专有错误码必须拒绝空白和超长文本。"""

    with pytest.raises(ValueError):
        RunnerSpecificErrorCode(
            "   ",
            RunnerSpecificErrorSource.RUNNER_PROTOCOL,
        )
    with pytest.raises(ValueError):
        RunnerSpecificErrorCode(
            "x" * 129,
            RunnerSpecificErrorSource.RUNNER_PROTOCOL,
        )


def test_runner_protocol_error_data_rejects_bare_string_error_code() -> None:
    """RunnerProtocolErrorData 不再接受裸字符串错误码。"""

    with pytest.raises(TypeError):
        RunnerProtocolErrorData(
            error_code=cast(RunnerSpecificErrorCode, "bad_protocol"),
            message="bad",
            provider_request_id=None,
            raw_payload=None,
        )


def test_missing_provider_detail_uses_engine_fallback_enum() -> None:
    """缺失 provider 明细时使用 Engine-owned fallback enum。"""

    assert serialize_engine_error_code(
        EngineRunErrorCode.RUNNER_ERROR_DONE_WITHOUT_DETAIL
    ) == "runner_error_done_without_detail"


def test_runner_protocol_error_data_accepts_wrapper() -> None:
    """RunnerProtocolErrorData 使用 wrapper 承载专有协议码。"""

    data = RunnerProtocolErrorData(
        error_code=runner_protocol_error_code("bad_protocol"),
        message="bad",
        provider_request_id=None,
        raw_payload=None,
    )

    assert serialize_engine_error_code(data.error_code) == "bad_protocol"
