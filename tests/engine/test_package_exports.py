"""包根导出白名单测试。

断言 :data:`dayu.engine.__all__` 与当前 Engine 公共表面严格相等，并
明确只导出真实函数式入口与契约类型，不导出实现类。
"""

from __future__ import annotations

import dayu.engine as engine

EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        "AgentMessage",
        "AgentMessageRole",
        "AgentFallbackMode",
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
        "DeepSeekReasoningEffort",
        "DeepSeekThinkingExtension",
        "EngineEvent",
        "EngineEventData",
        "EngineEventType",
        "EngineRunOutcomeCancelled",
        "EngineRunOutcomeFailed",
        "EngineRunOutcomeFinalAnswer",
        "EngineRunOutcomeSuspended",
        "FinalAnswerData",
        "FinishReason",
        "GeminiThinkingLevel",
        "GeminiThinkingExtension",
        "GeminiToolCallState",
        "IterationCompletedData",
        "IterationStartedData",
        "JsonValue",
        "MimoThinkingExtension",
        "OpenAIReasoningEffort",
        "OpenAIReasoningExtension",
        "PartialToolCallSummary",
        "ProviderProtocolErrorData",
        "ProviderRequestExtension",
        "QwenThinkingExtension",
        "ReasoningDeltaData",
        "RUN_SUSPENDED_REASON_TOOL_AWAITING",
        "RunCancelledData",
        "RunFailedData",
        "RunResumeHint",
        "RunSuspendedData",
        "run_agent_and_wait",
        "run_agent_messages",
        "RunnerCallOptions",
        "RunnerContentCompletedData",
        "RunnerContentDeltaData",
        "RunnerDoneData",
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
        "RunnerUsageRecordedData",
        "SystemMessage",
        "TERMINAL_ENGINE_EVENT_TYPES",
        "ToolAwaitKind",
        "ToolAwaitSnapshot",
        "ToolAwaitSpec",
        "ToolAwaitingData",
        "ToolAwaitingOutcome",
        "ToolCallBatchItemData",
        "ToolCallDeltaData",
        "ToolCallProviderState",
        "ToolCallRequest",
        "ToolCallRequestedData",
        "ToolCallsBatchDoneData",
        "ToolCallsBatchReadyData",
        "ToolCancelledOutcome",
        "ToolCompletedOutcome",
        "AcceptedToolExecutionRecord",
        "AssistantToolCallBatchSnapshot",
        "AwaitingToolExecutionRecord",
        "BatchToolExecutionContext",
        "BatchToolExecutionOutcome",
        "BatchToolExecutionRecord",
        "BatchToolExecutionRequest",
        "ToolExecutionOutcome",
        "ToolExecutor",
        "ToolFailedOutcome",
        "ToolFunctionSchema",
        "ToolMessage",
        "ToolParametersSchema",
        "ToolResultAcceptedData",
        "UsageReportedData",
        "ToolResultEnvelope",
        "ToolResultFailure",
        "ToolResultMeta",
        "ToolResultSuccess",
        "ToolSchema",
        "UserMessage",
    }
)


FORBIDDEN_EXPORTS: frozenset[str] = frozenset(
    {
        "AsyncAgent",
        "_AsyncAgent",
        "AsyncOpenAIRunner",
        "AsyncCliRunner",
        "ToolRegistry",
        "ToolRuntime",
        "ToolTraceRecorder",
        "JsonlToolTraceStore",
        "CancelledError",
        "ToolTruncationInfo",
    }
)


def test_engine_all_matches_expected_set() -> None:
    """``dayu.engine.__all__`` 必须与当前公共表面严格相等。"""

    actual = frozenset(engine.__all__)
    assert actual == EXPECTED_EXPORTS, (
        f"missing={EXPECTED_EXPORTS - actual}; extra={actual - EXPECTED_EXPORTS}"
    )


def test_forbidden_symbols_not_exported() -> None:
    """禁止导出的实现类必须不在 ``__all__`` 中。"""

    actual = frozenset(engine.__all__)
    assert actual.isdisjoint(FORBIDDEN_EXPORTS), (
        f"forbidden symbols leaked: {actual & FORBIDDEN_EXPORTS}"
    )


def test_forbidden_symbols_not_attribute_accessible() -> None:
    """禁止导出的符号也不得作为模块属性可访问。"""

    for name in FORBIDDEN_EXPORTS:
        assert not hasattr(engine, name), f"{name} unexpectedly accessible on dayu.engine"
