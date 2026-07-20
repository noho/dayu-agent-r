"""RunnerEvent 契约一致性测试。

- 验证 :class:`RunnerEventType` 枚举值与 RunnerEvent data dataclass 一一对应。
- 验证 :class:`RunnerEvent` 字段集合精确符合契约（不含 ``session_id`` /
  ``run_id``）。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from dayu.contracts.tool_call import ToolCallRequest
from dayu.engine.contracts.error_codes import runner_protocol_error_code
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RUNNER_EVENT_TYPE_TO_DATA,
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
    RunnerDiagnosticSeverity,
    RunnerProviderDiagnosticData,
    RunnerProtocolErrorData,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
    runner_event_type_for_data,
)


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _tool_call() -> ToolCallRequest:
    """构造测试用工具调用请求。

    :returns: ToolCallRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id="tc_1",
        name="lookup",
        arguments={},
        index_in_iteration=0,
        provider_state=None,
    )


def _valid_data_by_type() -> dict[RunnerEventType, RunnerEventData]:
    """构造每个 RunnerEventType 对应的合法 data。

    :returns: RunnerEventType 到合法 data 的映射。
    :raises Exception: 不主动抛出异常。
    """

    return {
        RunnerEventType.RUNNER_CONTENT_DELTA: RunnerContentDeltaData(delta="a"),
        RunnerEventType.RUNNER_REASONING_DELTA: RunnerReasoningDeltaData(delta="r"),
        RunnerEventType.RUNNER_TOOL_CALL_DELTA: RunnerToolCallDeltaData(
            tool_call_index=0,
            tool_call_id="tc_1",
            name_delta="lookup",
            arguments_delta="{}",
        ),
        RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED: RunnerToolCallsCompletedData(
            tool_calls=(_tool_call(),),
            content=None,
            reasoning_content=None,
        ),
        RunnerEventType.RUNNER_CONTENT_COMPLETED: RunnerContentCompletedData(
            content="done",
            reasoning_content=None,
        ),
        RunnerEventType.RUNNER_USAGE_RECORDED: RunnerUsageRecordedData(
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            provider_request_id="req_usage",
        ),
        RunnerEventType.PROVIDER_DIAGNOSTIC: RunnerProviderDiagnosticData(
            diagnostic_code="diag",
            severity=RunnerDiagnosticSeverity.WARNING,
            message="diagnostic",
            provider_request_id=None,
            raw_payload=None,
        ),
        RunnerEventType.PROVIDER_PROTOCOL_ERROR: RunnerProtocolErrorData(
            error_code=runner_protocol_error_code("bad_payload"),
            message="bad payload",
            provider_request_id=None,
            raw_payload=None,
        ),
        RunnerEventType.RUNNER_HTTP_ERROR: RunnerHTTPErrorData(
            error_code=RunnerHTTPErrorCode.NETWORK_ERROR,
            http_status=None,
            message="network error",
            provider_request_id=None,
            raw_payload=None,
            attempt=1,
            retried=False,
        ),
        RunnerEventType.RUNNER_DONE: RunnerDoneData(
            finish_reason=FinishReason.STOP,
            provider_request_id=None,
        ),
    }


def test_runner_event_type_members_match_mapping_keys() -> None:
    """RunnerEventType 成员集合与映射键集合必须严格相等。

    :returns: ``None``。
    :raises AssertionError: 枚举成员与映射键不一致时抛出。
    """

    assert set(RunnerEventType) == set(RUNNER_EVENT_TYPE_TO_DATA.keys())


def test_runner_event_data_dataclasses_distinct() -> None:
    """所有 Runner data dataclass 必须互不相同。

    :returns: ``None``。
    :raises AssertionError: data dataclass 出现重复时抛出。
    """

    classes = list(RUNNER_EVENT_TYPE_TO_DATA.values())
    assert len(classes) == len(set(classes))


def test_runner_event_constructs_all_valid_pairings() -> None:
    """RunnerEvent 构造边界接受全部合法 type/data 配对。

    :returns: ``None``。
    :raises AssertionError: 任一合法配对被拒绝或派生类型不一致时抛出。
    """

    data_by_type = _valid_data_by_type()
    assert set(data_by_type) == set(RunnerEventType)
    for event_type, data in data_by_type.items():
        event = RunnerEvent(
            type=event_type,
            data=data,
            occurred_at=_utc_now(),
        )

        assert event.type is event_type
        assert event.data is data
        assert runner_event_type_for_data(data) is event_type


@pytest.mark.parametrize(
    ("event_type", "data"),
    (
        (
            RunnerEventType.RUNNER_CONTENT_DELTA,
            RunnerDoneData(
                finish_reason=FinishReason.STOP,
                provider_request_id=None,
            ),
        ),
        (
            RunnerEventType.RUNNER_DONE,
            RunnerProtocolErrorData(
                error_code=runner_protocol_error_code("bad_payload"),
                message="bad payload",
                provider_request_id=None,
                raw_payload=None,
            ),
        ),
    ),
)
def test_runner_event_rejects_invalid_pairing(
    event_type: RunnerEventType, data: RunnerEventData
) -> None:
    """RunnerEvent 构造边界必须拒绝 type/data 矛盾事件。

    :param event_type: 测试用事件类型。
    :param data: 与事件类型不匹配的 data。
    :returns: ``None``。
    :raises AssertionError: malformed pairing 未被拒绝时抛出。
    """

    with pytest.raises(ValueError, match="type/data mismatch"):
        RunnerEvent(type=event_type, data=data, occurred_at=_utc_now())


def test_runner_event_field_set() -> None:
    """:class:`RunnerEvent` 字段集合必须精确等于契约。

    并且**不**包含 ``session_id`` / ``run_id``，这些字段必须由 Agent 在
    提升为 :class:`EngineEvent` 时补齐。
    """

    fields = {f.name for f in dataclasses.fields(RunnerEvent)}
    assert fields == {"type", "data", "occurred_at"}
    forbidden = {"session_id", "run_id"}
    assert fields.isdisjoint(forbidden)
