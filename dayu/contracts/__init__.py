"""公共契约包 :mod:`dayu.contracts`。

本包收纳 Host 与 Engine 之间需要双方独立产生 / 解释 / 持久化的层间
协作协议（按 ``docs/engine/phase0-plan.md`` §0 / §1.1 范式落点）：

- :data:`JsonValue` 严格 JSON 联合。
- :class:`CancellationToken` 取消观察 Protocol（**不**导出取消异常）。
- :class:`ToolSchema` / :class:`ToolFunctionSchema` /
  :class:`ToolParametersSchema` / :class:`ToolTruncateSpec` 工具 schema
  与截断声明。
- :class:`ToolCallRequest` / :class:`ToolExecutionContext` /
  :class:`ToolExecutionRequest`。
- :class:`ToolResultSuccess` / :class:`ToolResultFailure` /
  :data:`ToolResultEnvelope` / :class:`ToolTruncationInfo` /
  :class:`ToolResultMeta`。
- :class:`ToolAwaitKind` / :class:`ToolAwaitSpec` /
  :class:`ToolAwaitSnapshot`。
- :class:`ToolCompletedOutcome` / :class:`ToolFailedOutcome` /
  :class:`ToolAwaitingOutcome` / :data:`ToolExecutionOutcome`。
- :class:`ToolExecutor` Protocol（仅 ``execute``）。
- :func:`tool` / :class:`ToolDisplayInfo` / :class:`ToolDefinition` /
  :class:`ToolBundle` 最小工具声明契约；definition / bundle 只能投影为
  ``ToolSchema`` 后进入 Engine。

本包内部模块允许相互 import；**禁止** import :mod:`dayu.engine` 或上层
任何包。
"""

from __future__ import annotations

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import (
    ToolAwaitKind,
    ToolAwaitSnapshot,
    ToolAwaitSpec,
)
from dayu.contracts.tool_call import (
    GeminiToolCallState,
    ToolCallProviderState,
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_declaration import (
    FunctionToolExecutor,
    ToolBundle,
    ToolDefinition,
    ToolDisplayInfo,
    ToolFunctionCallable,
    tool,
)
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultEnvelope,
    ToolResultFailure,
    ToolResultMeta,
    ToolResultSuccess,
    ToolTruncationInfo,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)

__all__ = [
    "CancellationToken",
    "GeminiToolCallState",
    "JsonValue",
    "ToolAwaitKind",
    "ToolAwaitSnapshot",
    "ToolAwaitSpec",
    "ToolAwaitingOutcome",
    "ToolCallProviderState",
    "ToolCallRequest",
    "ToolCompletedOutcome",
    "ToolExecutionContext",
    "ToolExecutionOutcome",
    "ToolExecutionRequest",
    "ToolExecutor",
    "FunctionToolExecutor",
    "ToolBundle",
    "ToolDefinition",
    "ToolDisplayInfo",
    "ToolFunctionCallable",
    "ToolFailedOutcome",
    "ToolFunctionSchema",
    "ToolParametersSchema",
    "ToolResultEnvelope",
    "ToolResultFailure",
    "ToolResultMeta",
    "ToolResultSuccess",
    "ToolSchema",
    "ToolTruncateSpec",
    "ToolTruncationInfo",
    "ToolTruncationStrategy",
    "tool",
]
