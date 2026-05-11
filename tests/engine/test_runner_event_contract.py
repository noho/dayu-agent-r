"""RunnerEvent 契约一致性测试。

- 验证 :class:`RunnerEventType` 枚举值与 RunnerEvent data dataclass 一一对应。
- 验证 :class:`RunnerEvent` 字段集合精确符合契约（不含 ``session_id`` /
  ``run_id``）。
"""

from __future__ import annotations

import dataclasses

from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventType,
    RunnerHTTPErrorData,
    RunnerProtocolErrorData,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)


RUNNER_EVENT_TYPE_TO_DATA: dict[RunnerEventType, type] = {
    RunnerEventType.RUNNER_CONTENT_DELTA: RunnerContentDeltaData,
    RunnerEventType.RUNNER_REASONING_DELTA: RunnerReasoningDeltaData,
    RunnerEventType.RUNNER_TOOL_CALL_DELTA: RunnerToolCallDeltaData,
    RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED: RunnerToolCallsCompletedData,
    RunnerEventType.RUNNER_CONTENT_COMPLETED: RunnerContentCompletedData,
    RunnerEventType.RUNNER_USAGE_RECORDED: RunnerUsageRecordedData,
    RunnerEventType.PROVIDER_PROTOCOL_ERROR: RunnerProtocolErrorData,
    RunnerEventType.RUNNER_HTTP_ERROR: RunnerHTTPErrorData,
    RunnerEventType.RUNNER_DONE: RunnerDoneData,
}


def test_runner_event_type_members_match_mapping_keys() -> None:
    """RunnerEventType 成员集合与映射键集合必须严格相等。"""

    assert set(RunnerEventType) == set(RUNNER_EVENT_TYPE_TO_DATA.keys())


def test_runner_event_data_dataclasses_distinct() -> None:
    """所有 Runner data dataclass 必须互不相同。"""

    classes = list(RUNNER_EVENT_TYPE_TO_DATA.values())
    assert len(classes) == len(set(classes))


def test_runner_event_field_set() -> None:
    """:class:`RunnerEvent` 字段集合必须精确等于契约。

    并且**不**包含 ``session_id`` / ``run_id``，这些字段必须由 Agent 在
    提升为 :class:`EngineEvent` 时补齐。
    """

    fields = {f.name for f in dataclasses.fields(RunnerEvent)}
    assert fields == {"type", "data", "occurred_at"}
    forbidden = {"session_id", "run_id"}
    assert fields.isdisjoint(forbidden)
