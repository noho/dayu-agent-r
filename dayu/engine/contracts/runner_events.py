"""Runner 事件契约。

:class:`RunnerEvent` 是 :class:`AsyncRunner.call` 产出的最小事件单元。
Runner 只承担「LLM 协议归一」职责：把 OpenAI / Anthropic / Gemini /
Qwen 等具体协议归一为本事件流，**不**执行工具、**不**拆分迭代、**不**
为事件补 ``session_id`` / ``run_id`` / ``sequence`` / ``event_id``——这些
由 Agent 在 :class:`EngineEvent` 提升时补齐。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import ToolCallRequest


class RunnerEventType(StrEnum):
    """Runner 事件类型。"""

    RUNNER_CONTENT_DELTA = "runner_content_delta"
    RUNNER_REASONING_DELTA = "runner_reasoning_delta"
    RUNNER_TOOL_CALL_DELTA = "runner_tool_call_delta"
    RUNNER_TOOL_CALLS_COMPLETED = "runner_tool_calls_completed"
    RUNNER_CONTENT_COMPLETED = "runner_content_completed"
    RUNNER_USAGE_RECORDED = "runner_usage_recorded"
    PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"
    RUNNER_DONE = "runner_done"


@dataclass(frozen=True, slots=True)
class RunnerContentDeltaData:
    """正文增量事件 data。

    :param delta: 当前增量文本。
    """

    delta: str


@dataclass(frozen=True, slots=True)
class RunnerReasoningDeltaData:
    """推理链增量事件 data。

    :param delta: 当前推理链增量文本。
    """

    delta: str


@dataclass(frozen=True, slots=True)
class RunnerToolCallDeltaData:
    """工具调用增量事件 data。

    :param tool_call_index: 工具调用在本轮中的序号。
    :param tool_call_id: 工具调用 id；流式协议中可能在中后期才确定。
    :param name_delta: 工具名称增量；可能为 ``None``。
    :param arguments_delta: 工具参数增量字符串；可能为 ``None``。
    """

    tool_call_index: int
    tool_call_id: str | None
    name_delta: str | None
    arguments_delta: str | None


@dataclass(frozen=True, slots=True)
class RunnerToolCallsCompletedData:
    """工具调用完成事件 data。

    :param tool_calls: 解析完成的工具调用请求元组。
    """

    tool_calls: tuple[ToolCallRequest, ...]


@dataclass(frozen=True, slots=True)
class RunnerContentCompletedData:
    """正文完成事件 data。

    :param content: 完整正文；为 ``None`` 表示无正文。
    :param reasoning_content: 完整推理链文本；为 ``None`` 表示无推理链。
    :param finish_reason: 完成原因。
    """

    content: str | None
    reasoning_content: str | None
    finish_reason: FinishReason


@dataclass(frozen=True, slots=True)
class RunnerUsageRecordedData:
    """用量记录事件 data。

    :param prompt_tokens: 输入 token 数。
    :param completion_tokens: 输出 token 数。
    :param total_tokens: 总 token 数。
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class RunnerProtocolErrorData:
    """provider 协议错误事件 data。

    :param error_code: 中性错误码。
    :param message: 人类可读错误描述。
    :param provider_request_id: provider 侧请求 id；为 ``None`` 表示
        未提供。
    :param raw_payload: provider 原始报错载荷；为 ``None`` 表示无。
    """

    error_code: str
    message: str
    provider_request_id: str | None
    raw_payload: JsonValue | None


@dataclass(frozen=True, slots=True)
class RunnerDoneData:
    """Runner 事件流结束事件 data。

    :param finish_reason: 完成原因。
    """

    finish_reason: FinishReason


RunnerEventData: TypeAlias = (
    RunnerContentDeltaData
    | RunnerReasoningDeltaData
    | RunnerToolCallDeltaData
    | RunnerToolCallsCompletedData
    | RunnerContentCompletedData
    | RunnerUsageRecordedData
    | RunnerProtocolErrorData
    | RunnerDoneData
)
"""Runner 事件 data 封闭联合。"""


@dataclass(frozen=True, slots=True)
class RunnerEvent:
    """Runner 最小事件单元。

    :param type: 事件类型枚举。
    :param data: 事件 data 联合的某个具体成员。
    :param occurred_at: 事件发生时间。

    本事件**不**含 ``session_id`` / ``run_id`` / ``sequence`` / ``event_id``。
    Agent 在 :class:`EngineEvent` 提升阶段补齐这些字段。
    """

    type: RunnerEventType
    data: RunnerEventData
    occurred_at: datetime


__all__ = [
    "RunnerEventType",
    "RunnerContentDeltaData",
    "RunnerReasoningDeltaData",
    "RunnerToolCallDeltaData",
    "RunnerToolCallsCompletedData",
    "RunnerContentCompletedData",
    "RunnerUsageRecordedData",
    "RunnerProtocolErrorData",
    "RunnerDoneData",
    "RunnerEventData",
    "RunnerEvent",
]
