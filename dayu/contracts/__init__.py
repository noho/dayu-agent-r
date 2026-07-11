"""公共契约包 :mod:`dayu.contracts`。

本包收纳 Host 与 Engine 之间需要双方独立产生 / 解释 / 持久化的层间
协作协议：

- :data:`JsonValue` 严格 JSON 联合。
- :class:`CancellationToken` 取消观察 Protocol（**不**导出取消异常）。
- :class:`ToolSchema` / :class:`ToolFunctionSchema` /
  :class:`ToolParametersSchema` / :class:`ToolTruncateSpec` 工具 schema
  与截断声明，及 :func:`truncate_limit_key_for_strategy` 截断策略字段映射。
- :class:`ToolCallRequest` / :class:`BatchToolExecutionContext` /
  :class:`BatchToolExecutionRequest`：批式工具握手输入。
- :class:`ToolResultSuccess` / :class:`ToolResultFailure` /
  :data:`ToolResultEnvelope` / :class:`ToolResultMeta`。
- :class:`ToolAwaitKind` / :class:`ToolAwaitSpec` /
  :class:`ToolAwaitSnapshot`。
- :class:`ToolCompletedOutcome` / :class:`ToolFailedOutcome` /
  :class:`ToolAwaitingOutcome` / :class:`ToolCancelledOutcome` /
  :data:`ToolExecutionOutcome` /
  :class:`BatchToolExecutionRecord` / :class:`BatchToolExecutionOutcome`。
- :class:`ToolExecutor` Protocol（仅 ``execute``，批式签名）。
- :func:`tool` / :class:`ToolDisplayInfo` / :class:`ToolDefinition` /
  :class:`ToolBundle` 最小工具声明契约；definition / bundle 只能投影为
  ``ToolSchema`` 后进入 Engine。
- :class:`ToolExecutionMode` / :data:`ToolExecutionCapability` 及其具体
  capability 声明；只供 Host / ToolRuntime 选择执行边界，不进入
  LLM-facing schema。
- process-backed 工具子进程结果信封常量、构造 helper 与 parser；只供 Host
  parser 与具体工具实现共享，不进入 LLM-facing tool schema。
- :class:`ToolBundleSourceKind` / :class:`ToolBundleSourceRef` 工具 bundle
  来源引用契约。
- :class:`AgentFallbackMode` / :data:`AGENT_FALLBACK_MODES` Agent fallback
  mode 层中立契约。

本包内部模块允许相互 import；**禁止** import :mod:`dayu.engine` 或上层
任何包。
"""

from __future__ import annotations

from dayu.contracts.agent_policy import AGENT_FALLBACK_MODES, AgentFallbackMode
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import (
    ToolAwaitKind,
    ToolAwaitSnapshot,
    ToolAwaitSpec,
)
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    GeminiToolCallState,
    ToolCallProviderState,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import (
    ToolBundle,
    ToolCallable,
    ToolDefinition,
    ToolDisplayInfo,
    tool,
)
from dayu.contracts.tool_execution import (
    AsyncDirectToolExecutionCapability,
    PROCESS_TOOL_ENVELOPE_COMPLETED_STATUS,
    PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD,
    PROCESS_TOOL_ENVELOPE_FAILED_ERROR_TYPE_FIELD,
    PROCESS_TOOL_ENVELOPE_FAILED_HINT_FIELD,
    PROCESS_TOOL_ENVELOPE_FAILED_MESSAGE_FIELD,
    PROCESS_TOOL_ENVELOPE_FAILED_STATUS,
    PROCESS_TOOL_ENVELOPE_RESERVED_STATUSES,
    PROCESS_TOOL_ENVELOPE_STATUS_FIELD,
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    ProcessBackedToolTarget,
    ProcessBackedToolTargetFactory,
    ProcessToolCompletedEnvelope,
    ProcessToolEnvelopeParseResult,
    ProcessToolFailedEnvelope,
    ProcessToolMalformedEnvelope,
    ProcessToolUnsupportedEnvelope,
    ThreadBackedToolExecutionCapability,
    ToolExecutionCapability,
    ToolExecutionMode,
    parse_process_tool_envelope,
    process_tool_completed_envelope,
    process_tool_failed_envelope,
)
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    ALLOWED_TOOL_CANCELLED_REASONS,
    TOOL_CANCELLED_REASON_APPROVAL_DENIED,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    TOOL_CANCELLED_REASON_TIMEOUT,
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolAwaitingOutcome,
    ToolCancelledOutcome,
    ToolCancelledReason,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultEnvelope,
    ToolResultFailure,
    ToolResultMeta,
    ToolResultSuccess,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
    truncate_limit_key_for_strategy,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef

__all__ = [
    "ALLOWED_TOOL_CANCELLED_REASONS",
    "AGENT_FALLBACK_MODES",
    "AgentFallbackMode",
    "AsyncDirectToolExecutionCapability",
    "BatchToolExecutionContext",
    "BatchToolExecutionOutcome",
    "BatchToolExecutionRecord",
    "BatchToolExecutionRequest",
    "CancellationToken",
    "GeminiToolCallState",
    "JsonValue",
    "PROCESS_TOOL_ENVELOPE_COMPLETED_STATUS",
    "PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD",
    "PROCESS_TOOL_ENVELOPE_FAILED_ERROR_TYPE_FIELD",
    "PROCESS_TOOL_ENVELOPE_FAILED_HINT_FIELD",
    "PROCESS_TOOL_ENVELOPE_FAILED_MESSAGE_FIELD",
    "PROCESS_TOOL_ENVELOPE_FAILED_STATUS",
    "PROCESS_TOOL_ENVELOPE_RESERVED_STATUSES",
    "PROCESS_TOOL_ENVELOPE_STATUS_FIELD",
    "TOOL_CANCELLED_REASON_APPROVAL_DENIED",
    "TOOL_CANCELLED_REASON_HOST_CANCELLED",
    "TOOL_CANCELLED_REASON_TIMEOUT",
    "ToolAwaitKind",
    "ToolAwaitSnapshot",
    "ToolAwaitSpec",
    "ToolAwaitingOutcome",
    "ToolBundle",
    "ToolBundleSourceKind",
    "ToolBundleSourceRef",
    "ToolCallProviderState",
    "ToolCallRequest",
    "ToolCallable",
    "ToolCancelledOutcome",
    "ToolCancelledReason",
    "ToolCompletedOutcome",
    "ToolDefinition",
    "ToolDisplayInfo",
    "ToolExecutionCapability",
    "ToolExecutionMode",
    "ToolExecutionOutcome",
    "ToolExecutor",
    "ToolFailedOutcome",
    "ToolFunctionSchema",
    "ToolParametersSchema",
    "ProcessBackedToolContext",
    "ProcessBackedToolExecutionCapability",
    "ProcessBackedToolTarget",
    "ProcessBackedToolTargetFactory",
    "ProcessToolCompletedEnvelope",
    "ProcessToolEnvelopeParseResult",
    "ProcessToolFailedEnvelope",
    "ProcessToolMalformedEnvelope",
    "ProcessToolUnsupportedEnvelope",
    "ToolResultEnvelope",
    "ToolResultFailure",
    "ToolResultMeta",
    "ToolResultSuccess",
    "ToolSchema",
    "ToolTruncateSpec",
    "ToolTruncationStrategy",
    "ThreadBackedToolExecutionCapability",
    "parse_process_tool_envelope",
    "process_tool_completed_envelope",
    "process_tool_failed_envelope",
    "tool",
    "truncate_limit_key_for_strategy",
]
