"""EngineEvent 契约一致性测试。

- 验证 :class:`EngineEventType` 枚举值与 EngineEvent data dataclass 一一对应。
- 验证 :data:`TERMINAL_ENGINE_EVENT_TYPES` 集合内容固定。
- 验证 :class:`EngineEvent` 字段集合精确符合契约（无默认值、必填）。
"""

from __future__ import annotations

import dataclasses

import dayu.engine as engine
from dayu.engine.contracts.engine_events import (
    ContentCompleteData,
    ContentDeltaData,
    ContextCompactionRequestedData,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
    IterationStartedData,
    ProviderProtocolErrorData,
    ReasoningDeltaData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
    ToolAwaitingData,
    ToolCallBatchItemData,
    ToolCallDeltaData,
    ToolCallRequestedData,
    ToolCallsBatchDoneData,
    ToolCallsBatchReadyData,
    ToolResultAcceptedData,
    UsageReportedData,
)

EVENT_TYPE_TO_DATA: dict[EngineEventType, type] = {
    EngineEventType.ITERATION_STARTED: IterationStartedData,
    EngineEventType.CONTENT_DELTA: ContentDeltaData,
    EngineEventType.REASONING_DELTA: ReasoningDeltaData,
    EngineEventType.CONTENT_COMPLETED: ContentCompleteData,
    EngineEventType.TOOL_CALL_DELTA: ToolCallDeltaData,
    EngineEventType.TOOL_CALLS_BATCH_READY: ToolCallsBatchReadyData,
    EngineEventType.TOOL_CALL_REQUESTED: ToolCallRequestedData,
    EngineEventType.TOOL_RESULT_ACCEPTED: ToolResultAcceptedData,
    EngineEventType.TOOL_CALLS_BATCH_DONE: ToolCallsBatchDoneData,
    EngineEventType.TOOL_AWAITING: ToolAwaitingData,
    EngineEventType.CONTEXT_COMPACTION_REQUESTED: ContextCompactionRequestedData,
    EngineEventType.USAGE_REPORTED: UsageReportedData,
    EngineEventType.PROVIDER_PROTOCOL_ERROR: ProviderProtocolErrorData,
    EngineEventType.ITERATION_COMPLETED: IterationCompletedData,
    EngineEventType.FINAL_ANSWER: FinalAnswerData,
    EngineEventType.RUN_SUSPENDED: RunSuspendedData,
    EngineEventType.RUN_CANCELLED: RunCancelledData,
    EngineEventType.RUN_FAILED: RunFailedData,
}


def test_event_type_members_match_mapping_keys() -> None:
    """枚举成员集合与映射键集合必须严格相等。"""

    assert set(EngineEventType) == set(EVENT_TYPE_TO_DATA.keys())


def test_event_type_wire_values_are_locked() -> None:
    """EngineEventType 的 wire value 必须精确符合公共契约。"""

    assert {event_type.value for event_type in EngineEventType} == {
        "iteration_started",
        "content_delta",
        "reasoning_delta",
        "content_completed",
        "tool_call_delta",
        "tool_calls_batch_ready",
        "tool_call_requested",
        "tool_result_accepted",
        "tool_calls_batch_done",
        "tool_awaiting",
        "context_compaction_requested",
        "usage_reported",
        "provider_protocol_error",
        "iteration_completed",
        "final_answer",
        "run_suspended",
        "run_cancelled",
        "run_failed",
    }


def test_each_data_dataclass_is_distinct() -> None:
    """所有 EngineEvent data dataclass 必须互不相同。"""

    data_classes = list(EVENT_TYPE_TO_DATA.values())
    assert len(data_classes) == len(set(data_classes))


def test_iteration_completed_data_is_distinct_from_runner_done_data() -> None:
    """Engine 侧 ``IterationCompletedData`` 与 Runner 侧 ``RunnerDoneData``
    必须是不同 dataclass。"""

    assert engine.IterationCompletedData is not engine.RunnerDoneData


def test_terminal_event_types_are_locked() -> None:
    """:data:`TERMINAL_ENGINE_EVENT_TYPES` 内容必须严格等于锁定集合。"""

    assert engine.TERMINAL_ENGINE_EVENT_TYPES == frozenset(
        {
            EngineEventType.FINAL_ANSWER,
            EngineEventType.RUN_FAILED,
            EngineEventType.RUN_CANCELLED,
            EngineEventType.RUN_SUSPENDED,
        }
    )


def test_engine_event_field_set() -> None:
    """:class:`EngineEvent` 字段集合必须精确等于契约。"""

    fields = {f.name for f in dataclasses.fields(engine.EngineEvent)}
    assert fields == {
        "occurred_at",
        "session_id",
        "run_id",
        "type",
        "data",
        "metadata",
    }


def test_engine_event_required_fields_have_no_default() -> None:
    """:class:`EngineEvent` 字段必须全部是必填（无默认值）。"""

    for f in dataclasses.fields(engine.EngineEvent):
        assert f.default is dataclasses.MISSING, f"field {f.name} has default"
        assert f.default_factory is dataclasses.MISSING, (
            f"field {f.name} has default_factory"
        )


def test_tool_awaiting_and_suspended_data_fields_are_locked() -> None:
    """等待与挂起 data 必须携带恢复所需机器可读事实。"""

    awaiting_fields = {f.name for f in dataclasses.fields(ToolAwaitingData)}
    suspended_fields = {f.name for f in dataclasses.fields(RunSuspendedData)}

    assert awaiting_fields == {
        "iteration_id",
        "record",
    }
    assert suspended_fields == {
        "reason",
        "resume_hint",
        "accepted_records",
        "awaiting_records",
    }


def test_provider_request_id_fields_are_locked() -> None:
    """provider request id 字段必须是显式契约字段。"""

    assert {f.name for f in dataclasses.fields(IterationCompletedData)} == {
        "iteration_id",
        "finish_reason",
        "provider_request_id",
    }
    assert {f.name for f in dataclasses.fields(RunFailedData)} == {
        "error_code",
        "message",
        "provider_request_id",
        "recoverable",
    }
    assert {
        f.name for f in dataclasses.fields(ContextCompactionRequestedData)
    } == {
        "iteration_id",
        "budget_state",
        "reason",
        "provider_request_id",
    }


def test_tool_observation_data_fields_are_locked() -> None:
    """工具观测事件 data 字段必须保持强类型结构。"""

    assert {f.name for f in dataclasses.fields(ToolCallDeltaData)} == {
        "iteration_id",
        "tool_call_index",
        "tool_call_id",
        "name_delta",
        "arguments_delta",
    }
    assert {f.name for f in dataclasses.fields(ToolCallBatchItemData)} == {
        "tool_call_id",
        "name",
        "index_in_iteration",
        "provider_state",
    }
    assert {f.name for f in dataclasses.fields(ToolCallsBatchReadyData)} == {
        "iteration_id",
        "tool_calls",
    }
    assert {f.name for f in dataclasses.fields(ToolCallsBatchDoneData)} == {
        "iteration_id",
        "tool_call_ids",
        "completed_count",
        "failed_count",
        "cancelled_count",
    }
