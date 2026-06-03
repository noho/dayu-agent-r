"""Engine contracts 聚合导出。

该子包按 ``docs/engine/phase0-plan.md`` §1.2 范式收纳 Engine 单向 API
表面与内部协议（消息 / FinishReason / RunnerSpec / AgentPolicy /
AgentRunRequest 与终态 / RunnerEvent / EngineEvent / AsyncRunner），
并以平铺 ``__all__`` 暴露给上层 :mod:`dayu.engine`。

层间共享契约（``JsonValue`` / ``CancellationToken`` / 工具 schema /
工具 call / 工具 result / 工具 await / 工具 outcome / ``ToolExecutor``）
落在 :mod:`dayu.contracts`，不在本子包重复定义。
"""

from __future__ import annotations

from dayu.engine.contracts.agent_policy import AgentFallbackMode, AgentPolicy
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    ContextBudgetSnapshot,
    EngineRunOutcomeCancelled,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
    EngineRunOutcomeSuspended,
    RunResumeHint,
)
from dayu.engine.contracts.engine_events import (
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    TERMINAL_ENGINE_EVENT_TYPES,
    ContentCompleteData,
    ContentDeltaData,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventData,
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
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantMessage,
    AssistantToolCall,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.contracts.runner_identity import (
    RunnerRequestIdentity,
    build_runner_request_identity,
)
from dayu.engine.contracts.tool_records import (
    AcceptedToolExecutionRecord,
    AssistantToolCallBatchSnapshot,
    AwaitingToolExecutionRecord,
)
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
    RunnerProtocolErrorData,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.contracts.runner_spec import (
    AnthropicThinkingExtension,
    DeepSeekReasoningEffort,
    DeepSeekThinkingExtension,
    GeminiThinkingLevel,
    GeminiThinkingExtension,
    MimoThinkingExtension,
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
    RunnerCallOptions,
    RunnerSpec,
)

__all__ = [
    "AcceptedToolExecutionRecord",
    "AgentMessage",
    "AgentMessageRole",
    "AgentFallbackMode",
    "AgentPolicy",
    "AgentRunRequest",
    "AgentRunResult",
    "AnthropicThinkingExtension",
    "AssistantMessage",
    "AssistantToolCall",
    "AssistantToolCallBatchSnapshot",
    "AsyncRunner",
    "AwaitingToolExecutionRecord",
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
    "IterationCompletedData",
    "IterationStartedData",
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
    "RunnerRequestIdentity",
    "RunnerReasoningDeltaData",
    "RunnerSpec",
    "RunnerToolCallDeltaData",
    "RunnerToolCallsCompletedData",
    "RunnerUsageRecordedData",
    "SystemMessage",
    "TERMINAL_ENGINE_EVENT_TYPES",
    "ToolAwaitingData",
    "ToolCallBatchItemData",
    "ToolCallDeltaData",
    "ToolCallRequestedData",
    "ToolCallsBatchDoneData",
    "ToolCallsBatchReadyData",
    "ToolMessage",
    "ToolResultAcceptedData",
    "UsageReportedData",
    "UserMessage",
    "build_runner_request_identity",
]
