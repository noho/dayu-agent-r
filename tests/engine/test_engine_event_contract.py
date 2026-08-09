"""EngineEvent 契约一致性测试。

- 验证 :class:`EngineEventType` 枚举值与 EngineEvent data dataclass 一一对应。
- 验证 :data:`TERMINAL_ENGINE_EVENT_TYPES` 集合内容固定。
- 验证 :class:`EngineEvent` 字段集合精确符合契约（无默认值、必填）。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import cast

import dayu.engine as engine
import pytest
from dayu.engine.contracts.engine_events import (
    ENGINE_EVENT_TYPE_TO_DATA,
    ContentCompleteData,
    ContentDeltaData,
    ContextCompactionRequestedData,
    EngineEventData,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
    IterationStartedData,
    ProviderDiagnosticData,
    ProviderProtocolErrorData,
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
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
    engine_event_type_for_data,
    runner_role_sequence_digest,
    validate_engine_event_pairing,
)
from dayu.engine.contracts.runner_events import RunnerDiagnosticSeverity
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.engine.contracts.tool_records import (
    AcceptedToolExecutionRecord,
    AwaitingToolExecutionRecord,
)


def _successful_response_identity(
    *,
    case_label: str,
) -> SuccessfulRunnerResponseIdentity:
    """构造当前 contract case 唯一的安全成功身份。

    :param case_label: 当前无 run context contract case 的显式唯一标签。
    :returns: deterministic typed response identity。
    :raises ValueError: case label 为空时由 identity contract 抛出。
    """

    run_id = f"run-{case_label}"
    return SuccessfulRunnerResponseIdentity(
        effective_provider="provider-engine-event-contract",
        effective_model="model-engine-event-contract",
        runner_request_identity=build_runner_request_identity(
            run_id=run_id,
            attempt_id=None,
            execution_id=None,
            iteration_id=f"{run_id}-iteration-1",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=(
            ProviderRequestIdAvailability.UNAVAILABLE
        ),
        provider_request_id=None,
    )


def _engine_event_data_samples() -> tuple[EngineEventData, ...]:
    """构造覆盖 EngineEventData 封闭联合的最小外层实例。

    Pairing owner 只观察 data 的具体类型；各 data 字段不变量由各自契约
    测试负责，因此复杂 record 字段使用静态 cast 占位，不重复构造下游
    工具执行协议。

    :returns: 每种 EngineEventData 具体类型各一个实例。
    :raises Exception: 不主动抛出异常。
    """

    now = datetime.now(tz=timezone.utc)
    return (
        IterationStartedData(
            iteration_id="iteration-contract",
            iteration_index=0,
            message_count=1,
            role_sequence_digest="sha256:contract",
            runner_input_serializer_schema_version="contract.v1",
        ),
        ContentDeltaData(iteration_id="iteration-contract", delta="x"),
        ReasoningDeltaData(iteration_id="iteration-contract", delta="x"),
        ContentCompleteData(
            iteration_id="iteration-contract",
            content="x",
            reasoning_content=None,
        ),
        ToolCallDeltaData(
            iteration_id="iteration-contract",
            tool_call_index=0,
            tool_call_id="call-contract",
            name_delta="lookup",
            arguments_delta="{}",
        ),
        ToolCallsBatchReadyData(
            iteration_id="iteration-contract",
            tool_calls=(),
        ),
        ToolCallRequestedData(
            iteration_id="iteration-contract",
            tool_call_id="call-contract",
            name="lookup",
            arguments={},
            index_in_iteration=0,
            provider_state=None,
        ),
        ToolResultAcceptedData(
            iteration_id="iteration-contract",
            record=cast(AcceptedToolExecutionRecord, None),
        ),
        ToolCallsBatchDoneData(
            iteration_id="iteration-contract",
            tool_call_ids=(),
            completed_count=0,
            failed_count=0,
            cancelled_count=0,
        ),
        ToolAwaitingData(
            iteration_id="iteration-contract",
            record=cast(AwaitingToolExecutionRecord, None),
        ),
        ContextCompactionRequestedData(
            iteration_id="iteration-contract",
            budget_state=None,
            reason="context_compaction_required",
            provider_request_id=None,
        ),
        UsageReportedData(
            iteration_id="iteration-contract",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            provider_request_id=None,
        ),
        ProviderDiagnosticData(
            iteration_id="iteration-contract",
            diagnostic_code="contract-diagnostic",
            severity=RunnerDiagnosticSeverity.WARNING,
            message="diagnostic",
            provider_request_id=None,
            raw_payload=None,
        ),
        ProviderProtocolErrorData(
            iteration_id="iteration-contract",
            error_code=engine.EngineRunErrorCode.RUNNER_EXCEPTION,
            message="protocol error",
            provider_request_id=None,
            raw_payload=None,
        ),
        IterationCompletedData(
            iteration_id="iteration-contract",
            finish_reason=engine.FinishReason.STOP,
            provider_request_id=None,
        ),
        FinalAnswerData(
            content="answer",
            filtered=False,
            degraded=False,
            finish_reason=engine.FinishReason.STOP,
            response_identity=_successful_response_identity(
                case_label="sample-final-answer"
            ),
        ),
        RunSuspendedData(
            reason=RUN_SUSPENDED_REASON_TOOL_AWAITING,
            resume_hint=None,
            accepted_records=(),
            awaiting_records=(cast(AwaitingToolExecutionRecord, None),),
        ),
        RunCancelledData(
            reason="cancelled",
            requested_at=now,
            accepted_at=now,
            finished_at=now,
        ),
        RunFailedData(
            error_code=engine.EngineRunErrorCode.RUNNER_EXCEPTION,
            message="failed",
            provider_request_id=None,
            recoverable=False,
        ),
    )


def test_event_type_members_match_mapping_keys() -> None:
    """枚举成员集合与映射键集合必须严格相等。"""

    assert set(EngineEventType) == set(ENGINE_EVENT_TYPE_TO_DATA.keys())


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
        "provider_diagnostic",
        "provider_protocol_error",
        "iteration_completed",
        "final_answer",
        "run_suspended",
        "run_cancelled",
        "run_failed",
    }


def test_each_data_dataclass_is_distinct() -> None:
    """所有 EngineEvent data dataclass 必须互不相同。"""

    data_classes = list(ENGINE_EVENT_TYPE_TO_DATA.values())
    assert len(data_classes) == len(set(data_classes))


def test_each_legal_engine_event_pair_constructs() -> None:
    """production mapping 中每个合法 discriminator/data pair 都能构造。"""

    samples = _engine_event_data_samples()
    assert {type(data) for data in samples} == set(
        ENGINE_EVENT_TYPE_TO_DATA.values()
    )
    for data in samples:
        event_type = engine_event_type_for_data(data)

        validate_engine_event_pairing(event_type, data)
        event = engine.EngineEvent(
            occurred_at=datetime.now(tz=timezone.utc),
            session_id="session-contract",
            run_id="run-contract",
            type=event_type,
            data=data,
            metadata=None,
        )

        assert event.data is data
        assert engine_event_type_for_data(data) is event_type


def test_engine_event_rejects_mismatched_discriminator_and_data() -> None:
    """EngineEvent 构造边界拒绝合法成员间的错误 pairing。"""

    with pytest.raises(ValueError, match="type/data mismatch"):
        engine.EngineEvent(
            occurred_at=datetime.now(tz=timezone.utc),
            session_id="session-contract",
            run_id="run-contract",
            type=EngineEventType.FINAL_ANSWER,
            data=ToolCallRequestedData(
                iteration_id="iteration-contract",
                tool_call_id="call-contract",
                name="lookup",
                arguments={},
                index_in_iteration=0,
                provider_state=None,
            ),
            metadata=None,
        )


def test_engine_event_rejects_non_enum_discriminator() -> None:
    """EngineEvent 构造边界拒绝 raw string discriminator。"""

    with pytest.raises(TypeError, match="EngineEvent.type"):
        engine.EngineEvent(
            occurred_at=datetime.now(tz=timezone.utc),
            session_id="session-contract",
            run_id="run-contract",
            type=cast(EngineEventType, "final_answer"),
            data=FinalAnswerData(
                content="answer",
                filtered=False,
                degraded=False,
                finish_reason=engine.FinishReason.STOP,
                response_identity=_successful_response_identity(
                    case_label="invalid-discriminator-final-answer"
                ),
            ),
            metadata=None,
        )


def test_engine_event_rejects_data_outside_closed_union() -> None:
    """EngineEvent 构造边界拒绝 data 封闭联合之外的实例。"""

    with pytest.raises(TypeError, match="unsupported type"):
        engine.EngineEvent(
            occurred_at=datetime.now(tz=timezone.utc),
            session_id="session-contract",
            run_id="run-contract",
            type=EngineEventType.FINAL_ANSWER,
            data=cast(EngineEventData, "not-engine-event-data"),
            metadata=None,
        )


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
        assert (
            f.default_factory is dataclasses.MISSING
        ), f"field {f.name} has default_factory"


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

    assert {f.name for f in dataclasses.fields(UsageReportedData)} == {
        "iteration_id",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "provider_request_id",
    }
    assert {f.name for f in dataclasses.fields(IterationCompletedData)} == {
        "iteration_id",
        "finish_reason",
        "provider_request_id",
        "client_correlation_id",
    }
    assert {f.name for f in dataclasses.fields(RunFailedData)} == {
        "error_code",
        "message",
        "provider_request_id",
        "client_correlation_id",
        "recoverable",
    }
    assert {f.name for f in dataclasses.fields(ContextCompactionRequestedData)} == {
        "iteration_id",
        "budget_state",
        "reason",
        "provider_request_id",
        "client_correlation_id",
    }


def test_content_completed_fields_exclude_finish_reason() -> None:
    """正文完成事件不得重复承载 Runner 调用完成原因。"""

    assert {f.name for f in dataclasses.fields(ContentCompleteData)} == {
        "iteration_id",
        "content",
        "reasoning_content",
    }


def test_iteration_started_runner_input_signal_fields_are_locked() -> None:
    """iteration started 只携带 Engine 可观测 runner input signal。"""

    assert {f.name for f in dataclasses.fields(IterationStartedData)} == {
        "iteration_id",
        "iteration_index",
        "message_count",
        "role_sequence_digest",
        "runner_input_serializer_schema_version",
        "input_projection",
    }
    assert runner_role_sequence_digest(("system", "user")) == (
        "sha256:" "12217463eda5df10663547ab698e0aebc9e7d7620d3f2caea52f122a1abe8547"
    )
    assert RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION == "runner_input_roles.v1"


def test_context_compaction_budget_state_accepts_unknown_and_snapshot() -> None:
    """上下文压缩预算字段同时支持未知与真实快照。"""

    fields = {f.name: f for f in dataclasses.fields(ContextCompactionRequestedData)}
    assert fields["budget_state"].default is dataclasses.MISSING
    assert fields["budget_state"].default_factory is dataclasses.MISSING

    unknown_budget = ContextCompactionRequestedData(
        iteration_id="iter_unknown",
        budget_state=None,
        reason="context_compaction_required",
        provider_request_id="req_unknown",
    )
    real_budget = ContextCompactionRequestedData(
        iteration_id="iter_real",
        budget_state=engine.ContextBudgetSnapshot(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
        ),
        reason="context_compaction_required",
        provider_request_id="req_real",
    )

    assert unknown_budget.budget_state is None
    assert real_budget.budget_state == engine.ContextBudgetSnapshot(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
    )


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
