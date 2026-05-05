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

from dayu.engine.contracts.agent_policy import AgentPolicy
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
    TERMINAL_ENGINE_EVENT_TYPES,
    ContentCompleteData,
    ContentDeltaData,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventData,
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
from dayu.engine.contracts.runner import AsyncRunner
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
    "AgentMessage",
    "AgentMessageRole",
    "AgentPolicy",
    "AgentRunRequest",
    "AgentRunResult",
    "AnthropicThinkingExtension",
    "AssistantMessage",
    "AssistantToolCall",
    "AsyncRunner",
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
    "IterationStartedData",
    "MimoThinkingExtension",
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
    "ToolAwaitingData",
    "ToolCallRequestedData",
    "ToolMessage",
    "ToolResultAcceptedData",
    "UserMessage",
]
