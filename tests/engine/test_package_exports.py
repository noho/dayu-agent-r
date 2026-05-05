"""包根导出白名单测试。

断言 :data:`dayu.engine.__all__` 与 Phase 0 锁定白名单严格相等，并
明确禁止占位函数式入口与实现类出现在导出集合中。
"""

from __future__ import annotations

import dayu.engine as engine

EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        "AgentMessage",
        "AgentMessageRole",
        "AgentPolicy",
        "AgentRunRequest",
        "AgentRunResult",
        "AnthropicThinkingExtension",
        "AssistantMessage",
        "AssistantToolCall",
        "AsyncRunner",
        "CancellationToken",
        "ContentCompleteData",
        "ContentDeltaData",
        "ContextBudgetSnapshot",
        "ContextCompactionRequestedData",
        "EngineEvent",
        "EngineEventData",
        "EngineEventType",
        "EngineRunOutcomeCancelled",
        "EngineRunOutcomeFailed",
        "EngineRunOutcomeFinalAnswer",
        "EngineRunOutcomeSuspended",
        "FinalAnswerData",
        "FinishReason",
        "GeminiThinkingExtension",
        "GeminiToolCallState",
        "IterationStartedData",
        "JsonValue",
        "OpenAIReasoningEffort",
        "OpenAIReasoningExtension",
        "ProviderProtocolErrorData",
        "ProviderRequestExtension",
        "QwenThinkingExtension",
        "ReasoningDeltaData",
        "RunCancelledData",
        "RunFailedData",
        "RunResumeHint",
        "RunSuspendedData",
        "RunnerCallOptions",
        "RunnerContentCompletedData",
        "RunnerContentDeltaData",
        "RunnerDoneData",
        "RunnerDoneEngineData",
        "RunnerEvent",
        "RunnerEventData",
        "RunnerEventType",
        "RunnerHTTPErrorCode",
        "RunnerHTTPErrorData",
        "RunnerProtocolErrorData",
        "RunnerReasoningDeltaData",
        "RunnerSpec",
        "RunnerToolCallDeltaData",
        "RunnerToolCallsCompletedData",
        "RunnerUsageData",
        "RunnerUsageRecordedData",
        "SystemMessage",
        "TERMINAL_ENGINE_EVENT_TYPES",
        "ToolAwaitKind",
        "ToolAwaitSnapshot",
        "ToolAwaitSpec",
        "ToolAwaitingData",
        "ToolAwaitingOutcome",
        "ToolCallProviderState",
        "ToolCallRequest",
        "ToolCallRequestedData",
        "ToolCompletedOutcome",
        "ToolExecutionContext",
        "ToolExecutionOutcome",
        "ToolExecutionRequest",
        "ToolExecutor",
        "ToolFailedOutcome",
        "ToolFunctionSchema",
        "ToolMessage",
        "ToolParametersSchema",
        "ToolResultAcceptedData",
        "ToolResultEnvelope",
        "ToolResultFailure",
        "ToolResultMeta",
        "ToolResultSuccess",
        "ToolSchema",
        "ToolTruncationInfo",
        "UserMessage",
    }
)


FORBIDDEN_EXPORTS: frozenset[str] = frozenset(
    {
        "run_agent_messages",
        "run_agent_and_wait",
        "AsyncAgent",
        "AsyncOpenAIRunner",
        "AsyncCliRunner",
        "ToolRegistry",
        "ToolRuntime",
        "ToolTraceRecorder",
        "JsonlToolTraceStore",
        "CancelledError",
    }
)


def test_engine_all_matches_expected_set() -> None:
    """``dayu.engine.__all__`` 必须与 Phase 0 锁定白名单严格相等。"""

    actual = frozenset(engine.__all__)
    assert actual == EXPECTED_EXPORTS, (
        f"missing={EXPECTED_EXPORTS - actual}; extra={actual - EXPECTED_EXPORTS}"
    )


def test_forbidden_symbols_not_exported() -> None:
    """Phase 0 禁止导出的占位入口与实现类必须不在 ``__all__`` 中。"""

    actual = frozenset(engine.__all__)
    assert actual.isdisjoint(FORBIDDEN_EXPORTS), (
        f"forbidden symbols leaked: {actual & FORBIDDEN_EXPORTS}"
    )


def test_forbidden_symbols_not_attribute_accessible() -> None:
    """禁止导出的符号也不得作为模块属性可访问。"""

    for name in FORBIDDEN_EXPORTS:
        assert not hasattr(engine, name), f"{name} unexpectedly accessible on dayu.engine"
