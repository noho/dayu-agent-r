"""Engine 事件契约。

:class:`EngineEvent` 是 Engine 对 Host / Service 暴露的**唯一**事件流。
Agent 在内部把 :class:`RunnerEvent` 提升为 :class:`EngineEvent`，并补齐
``session_id`` / ``run_id`` / ``sequence`` / ``event_id`` 等治理性字段。

本模块同时提供 :data:`TERMINAL_ENGINE_EVENT_TYPES` 常量集合，列出会
导致 Engine run 终止的事件类型，供 Host 治理层使用。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

from dayu.engine.contracts.agent_run import ContextBudgetSnapshot, RunResumeHint
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitSpec
from dayu.contracts.tool_call import ToolCallProviderState
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolFailedOutcome,
)


class EngineEventType(StrEnum):
    """Engine 事件类型枚举。"""

    ITERATION_STARTED = "iteration_started"
    RUNNER_CONTENT_DELTA = "runner_content_delta"
    RUNNER_REASONING_DELTA = "runner_reasoning_delta"
    RUNNER_CONTENT_COMPLETED = "runner_content_completed"
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_RESULT_ACCEPTED = "tool_result_accepted"
    TOOL_AWAITING = "tool_awaiting"
    CONTEXT_COMPACTION_REQUESTED = "context_compaction_requested"
    RUNNER_USAGE_RECORDED = "runner_usage_recorded"
    PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"
    RUNNER_DONE = "runner_done"
    FINAL_ANSWER = "final_answer"
    RUN_SUSPENDED = "run_suspended"
    RUN_CANCELLED = "run_cancelled"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True, slots=True)
class IterationStartedData:
    """LLM 迭代开始事件 data。

    :param iteration_id: 当前迭代 id。
    :param iteration_index: 迭代序号（从 0 起）。
    :param message_count: 进入本轮 LLM 调用的消息数量。
    """

    iteration_id: str
    iteration_index: int
    message_count: int


@dataclass(frozen=True, slots=True)
class ContentDeltaData:
    """正文增量事件 data。

    :param iteration_id: 当前迭代 id。
    :param delta: 增量文本。
    """

    iteration_id: str
    delta: str


@dataclass(frozen=True, slots=True)
class ReasoningDeltaData:
    """推理链增量事件 data。

    :param iteration_id: 当前迭代 id。
    :param delta: 推理链增量文本。
    """

    iteration_id: str
    delta: str


@dataclass(frozen=True, slots=True)
class ContentCompleteData:
    """正文完成事件 data。

    :param iteration_id: 当前迭代 id。
    :param content: 完整正文；为 ``None`` 表示无正文。
    :param reasoning_content: 完整推理链文本；为 ``None`` 表示无推理链。
    :param finish_reason: 完成原因。
    """

    iteration_id: str
    content: str | None
    reasoning_content: str | None
    finish_reason: FinishReason


@dataclass(frozen=True, slots=True)
class ToolCallRequestedData:
    """工具调用请求事件 data。

    :param iteration_id: 当前迭代 id。
    :param tool_call_id: 工具调用 id。
    :param name: 工具名称。
    :param arguments: 工具参数。
    :param index_in_iteration: 工具调用在迭代内的序号。
    :param provider_state: provider 私有续航状态。
    """

    iteration_id: str
    tool_call_id: str
    name: str
    arguments: Mapping[str, JsonValue]
    index_in_iteration: int
    provider_state: ToolCallProviderState | None


@dataclass(frozen=True, slots=True)
class ToolResultAcceptedData:
    """工具结果被 Engine 接受事件 data。

    :param iteration_id: 当前迭代 id。
    :param tool_call_id: 工具调用 id。
    :param name: 工具名称。
    :param index_in_iteration: 工具调用在迭代内的序号。
    :param outcome: 终态 outcome（仅 completed / failed；awaiting 走
        :class:`ToolAwaitingData`）。
    """

    iteration_id: str
    tool_call_id: str
    name: str
    index_in_iteration: int
    outcome: ToolCompletedOutcome | ToolFailedOutcome


@dataclass(frozen=True, slots=True)
class ToolAwaitingData:
    """工具进入长事务等待事件 data。

    :param iteration_id: 当前迭代 id。
    :param tool_call_id: 工具调用 id。
    :param await_spec: 等待规约。
    """

    iteration_id: str
    tool_call_id: str
    await_spec: ToolAwaitSpec


@dataclass(frozen=True, slots=True)
class ContextCompactionRequestedData:
    """上下文压缩请求事件 data。

    :param iteration_id: 当前迭代 id。
    :param budget_state: 触发压缩时的预算快照。
    :param reason: 压缩触发原因（中性字符串）。
    """

    iteration_id: str
    budget_state: ContextBudgetSnapshot
    reason: str


@dataclass(frozen=True, slots=True)
class RunnerUsageData:
    """Runner 用量提升事件 data。

    :param iteration_id: 当前迭代 id。
    :param prompt_tokens: 提示 token 数。
    :param completion_tokens: 完成 token 数。
    :param total_tokens: 总 token 数。
    """

    iteration_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ProviderProtocolErrorData:
    """provider 协议错误提升事件 data。

    :param iteration_id: 当前迭代 id。
    :param error_code: 中性错误码。
    :param message: 人类可读错误描述。
    :param provider_request_id: provider 侧请求 id；为 ``None`` 表示
        未提供。
    :param raw_payload: provider 原始报错载荷；为 ``None`` 表示无。
    """

    iteration_id: str
    error_code: str
    message: str
    provider_request_id: str | None
    raw_payload: JsonValue | None


@dataclass(frozen=True, slots=True)
class RunnerDoneEngineData:
    """Runner 事件流结束在 Engine 侧的提升 data。

    与 :class:`dayu.engine.contracts.runner_events.RunnerDoneData` 是
    **不同**的 dataclass，命名上故意区分以避免包根白名单冲突。

    :param iteration_id: 当前迭代 id。
    :param finish_reason: 完成原因。
    """

    iteration_id: str
    finish_reason: FinishReason


@dataclass(frozen=True, slots=True)
class FinalAnswerData:
    """最终回答事件 data。

    :param content: 最终回答正文。
    :param filtered: 是否经过过滤器处理。
    :param degraded: 是否为降级回答。
    :param finish_reason: 完成原因。
    """

    content: str
    filtered: bool
    degraded: bool
    finish_reason: FinishReason


@dataclass(frozen=True, slots=True)
class RunSuspendedData:
    """运行挂起事件 data。

    :param reason: 挂起原因（中性字符串）。
    :param resume_hint: 可选的恢复提示；无为 ``None``。
    """

    reason: str
    resume_hint: RunResumeHint | None


@dataclass(frozen=True, slots=True)
class RunCancelledData:
    """运行被取消事件 data。

    :param reason: 取消原因。
    :param requested_at: 取消请求时间。
    :param accepted_at: Engine 接受取消的时间。
    :param finished_at: 实际收尾完成时间。
    """

    reason: str
    requested_at: datetime
    accepted_at: datetime
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class RunFailedData:
    """运行失败事件 data。

    :param error_code: 中性错误码。
    :param message: 人类可读错误描述。
    :param recoverable: 是否可恢复。
    """

    error_code: str
    message: str
    recoverable: bool


EngineEventData: TypeAlias = (
    IterationStartedData
    | ContentDeltaData
    | ReasoningDeltaData
    | ContentCompleteData
    | ToolCallRequestedData
    | ToolResultAcceptedData
    | ToolAwaitingData
    | ContextCompactionRequestedData
    | RunnerUsageData
    | ProviderProtocolErrorData
    | RunnerDoneEngineData
    | FinalAnswerData
    | RunSuspendedData
    | RunCancelledData
    | RunFailedData
)
"""Engine 事件 data 封闭联合。"""


@dataclass(frozen=True, slots=True)
class EngineEvent:
    """Engine 公共事件。

    :param event_id: 事件唯一 id（由 Agent 生成）。
    :param sequence: 事件序号（在同一 run 内单调递增）。
    :param occurred_at: 事件发生时间。
    :param session_id: 会话 id。
    :param run_id: 运行 id。
    :param type: 事件类型。
    :param data: 事件 data 联合的某个具体成员。
    :param metadata: 中性 observer / debug hint；只允许
        ``Mapping[str, JsonValue]``，不得承载契约事实；为 ``None`` 表示
        无元数据。
    """

    event_id: str
    sequence: int
    occurred_at: datetime
    session_id: str
    run_id: str
    type: EngineEventType
    data: EngineEventData
    metadata: Mapping[str, JsonValue] | None


TERMINAL_ENGINE_EVENT_TYPES: frozenset[EngineEventType] = frozenset(
    {
        EngineEventType.FINAL_ANSWER,
        EngineEventType.RUN_FAILED,
        EngineEventType.RUN_CANCELLED,
        EngineEventType.RUN_SUSPENDED,
    }
)
"""会导致 Engine run 终止的事件类型集合。"""


__all__ = [
    "EngineEventType",
    "IterationStartedData",
    "ContentDeltaData",
    "ReasoningDeltaData",
    "ContentCompleteData",
    "ToolCallRequestedData",
    "ToolResultAcceptedData",
    "ToolAwaitingData",
    "ContextCompactionRequestedData",
    "RunnerUsageData",
    "ProviderProtocolErrorData",
    "RunnerDoneEngineData",
    "FinalAnswerData",
    "RunSuspendedData",
    "RunCancelledData",
    "RunFailedData",
    "EngineEventData",
    "EngineEvent",
    "TERMINAL_ENGINE_EVENT_TYPES",
]
