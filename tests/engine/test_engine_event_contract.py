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
    IterationStartedData,
    ProviderProtocolErrorData,
    ReasoningDeltaData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
    RunnerDoneEngineData,
    RunnerUsageData,
    ToolAwaitingData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
)

EVENT_TYPE_TO_DATA: dict[EngineEventType, type] = {
    EngineEventType.ITERATION_STARTED: IterationStartedData,
    EngineEventType.RUNNER_CONTENT_DELTA: ContentDeltaData,
    EngineEventType.RUNNER_REASONING_DELTA: ReasoningDeltaData,
    EngineEventType.RUNNER_CONTENT_COMPLETED: ContentCompleteData,
    EngineEventType.TOOL_CALL_REQUESTED: ToolCallRequestedData,
    EngineEventType.TOOL_RESULT_ACCEPTED: ToolResultAcceptedData,
    EngineEventType.TOOL_AWAITING: ToolAwaitingData,
    EngineEventType.CONTEXT_COMPACTION_REQUESTED: ContextCompactionRequestedData,
    EngineEventType.RUNNER_USAGE_RECORDED: RunnerUsageData,
    EngineEventType.PROVIDER_PROTOCOL_ERROR: ProviderProtocolErrorData,
    EngineEventType.RUNNER_DONE: RunnerDoneEngineData,
    EngineEventType.FINAL_ANSWER: FinalAnswerData,
    EngineEventType.RUN_SUSPENDED: RunSuspendedData,
    EngineEventType.RUN_CANCELLED: RunCancelledData,
    EngineEventType.RUN_FAILED: RunFailedData,
}


def test_event_type_members_match_mapping_keys() -> None:
    """枚举成员集合与映射键集合必须严格相等。"""

    assert set(EngineEventType) == set(EVENT_TYPE_TO_DATA.keys())


def test_each_data_dataclass_is_distinct() -> None:
    """所有 EngineEvent data dataclass 必须互不相同。"""

    data_classes = list(EVENT_TYPE_TO_DATA.values())
    assert len(data_classes) == len(set(data_classes))


def test_runner_done_engine_data_is_distinct_from_runner_done_data() -> None:
    """Engine 侧 ``RunnerDoneEngineData`` 与 Runner 侧 ``RunnerDoneData``
    必须是不同 dataclass。"""

    assert engine.RunnerDoneEngineData is not engine.RunnerDoneData


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
        "event_id",
        "sequence",
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
