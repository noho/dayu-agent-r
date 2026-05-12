"""Engine 工具批次 snapshot 与 record 共享契约。

本模块单独承载 batch-level snapshot 与 record dataclass，降低
``engine_events`` 与 ``agent_run`` 等模块对批式形状的耦合：

- :class:`AssistantToolCallBatchSnapshot`：把一轮 LLM 输出对应的工具调用
  批次与 assistant 文本 / reasoning / provider_request_id 一起冻结，
  供调用方在 suspended terminal 后重建 LLM 上下文。
- :class:`AcceptedToolExecutionRecord`：批内某次工具调用进入 LLM
  context 的 accepted 终态（completed / failed / cancelled 都属于
  accepted；awaiting 单独承载于 :class:`AwaitingToolExecutionRecord`）。
- :class:`AwaitingToolExecutionRecord`：批内进入长事务等待的工具调用
  终态。

Engine 不暴露重建 LLM message 的 helper，调用方按本模块的 shape 自行
重建。
"""

from __future__ import annotations

from dataclasses import dataclass

from dayu.contracts.tool_await import ToolAwaitSnapshot, ToolAwaitSpec
from dayu.contracts.tool_call import ToolCallRequest
from dayu.contracts.tool_outcome import (
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
)


@dataclass(frozen=True, slots=True)
class AssistantToolCallBatchSnapshot:
    """一轮 LLM tool_calls 输出的批次 snapshot。

    :param iteration_id: 当前迭代 id。
    :param tool_calls: 本批工具调用，按 LLM 输出顺序。
    :param content: 与本批同迭代的 assistant 正文；可能为 ``None``。
    :param reasoning_content: 与本批同迭代的 reasoning 文本；可能为
        ``None``。
    :param provider_request_id: 本轮 provider response request id；可能
        为 ``None``。
    """

    iteration_id: str
    tool_calls: tuple[ToolCallRequest, ...]
    content: str | None
    reasoning_content: str | None
    provider_request_id: str | None


@dataclass(frozen=True, slots=True)
class AcceptedToolExecutionRecord:
    """已进入 LLM context 的工具调用 accepted 终态记录。

    :param batch_snapshot: 当前批次 snapshot。
    :param call: 原始工具调用请求；保留 ``tool_call_id`` / ``name`` /
        ``index_in_iteration`` 等字段。
    :param outcome: completed / failed / cancelled 三种终态之一。
    """

    batch_snapshot: AssistantToolCallBatchSnapshot
    call: ToolCallRequest
    outcome: ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome


@dataclass(frozen=True, slots=True)
class AwaitingToolExecutionRecord:
    """工具进入长事务等待的批内记录。

    :param batch_snapshot: 当前批次 snapshot。
    :param call: 原始工具调用请求；保留 ``tool_call_id`` / ``name`` /
        ``index_in_iteration`` 等字段。
    :param await_spec: 等待规约（与 :class:`ToolAwaitingOutcome.await_spec`
        同源 alias，便于调用方直接拿到恢复信息）。
    :param snapshot: 可选等待快照。
    """

    batch_snapshot: AssistantToolCallBatchSnapshot
    call: ToolCallRequest
    await_spec: ToolAwaitSpec
    snapshot: ToolAwaitSnapshot | None


__all__ = [
    "AcceptedToolExecutionRecord",
    "AssistantToolCallBatchSnapshot",
    "AwaitingToolExecutionRecord",
]
