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
    RUNNER_HTTP_ERROR = "runner_http_error"
    RUNNER_DONE = "runner_done"


class RunnerHTTPErrorCode(StrEnum):
    """Runner HTTP / 网络 / 超时终态错误中性枚举。

    与 :class:`RunnerProtocolErrorData` 表达的协议解析错误正交分离：
    本枚举仅描述传输层失败的中性分类，使下游消费侧可用 ``match`` +
    ``assert_never`` 守护，避免以自由 ``str`` 比较。

    成员：

    - ``RATE_LIMIT_EXCEEDED``：HTTP 429 限流（含 Retry-After 路径与
      重试耗尽路径）。
    - ``SERVER_ERROR``：HTTP 5xx 服务端错误（重试耗尽时）。
    - ``CLIENT_ERROR``：HTTP 4xx 客户端错误（非 429，且不可重试）。
    - ``NETWORK_ERROR``：连接 / DNS / TLS 等网络层异常。
    - ``TIMEOUT``：请求或读流超时。
    - ``CONTEXT_LENGTH_EXCEEDED``：provider 明确报告上下文长度超限；
      Engine 会提升为 context compaction required 事实，是否 compact 由
      Host 决定。
    - ``UNKNOWN_HTTP_STATUS``:无法归类的 HTTP 状态码（如 1xx / 3xx
      未跟随重定向、自定义状态码）。
    """

    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"
    UNKNOWN_HTTP_STATUS = "unknown_http_status"


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
    :param content: 本轮 assistant 在请求工具前产生的完整正文；为 ``None``
        表示无正文。
    :param reasoning_content: 本轮 assistant 在请求工具前产生的完整推理链
        文本；为 ``None`` 表示无推理链。
    """

    tool_calls: tuple[ToolCallRequest, ...]
    content: str | None = None
    reasoning_content: str | None = None


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
class RunnerHTTPErrorData:
    """Runner HTTP / 网络 / 超时终态错误事件 data。

    :param error_code: 传输层错误中性枚举。
    :param http_status: HTTP 状态码；网络 / 超时无状态码时为 ``None``。
    :param message: 人类可读错误描述。
    :param provider_request_id: provider 侧请求 id；为 ``None`` 表示
        未提供。
    :param raw_payload: provider 原始报错 JSON 载荷；解析失败或非 JSON
        响应为 ``None``。
    :param attempt: 触发本错误事件时已经尝试的次数（首次为 1）。
    :param retried: 是否已经发生过至少一次重试。

    本事件**不**与 :class:`RunnerProtocolErrorData` 相互替代：解析层错误
    走协议错误事件，传输层错误走本事件；两者均以
    :class:`RunnerDoneData` ( ``finish_reason=ERROR`` ) 收口。
    """

    error_code: RunnerHTTPErrorCode
    http_status: int | None
    message: str
    provider_request_id: str | None
    raw_payload: JsonValue | None
    attempt: int
    retried: bool


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
    | RunnerHTTPErrorData
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
    "RunnerHTTPErrorCode",
    "RunnerContentDeltaData",
    "RunnerReasoningDeltaData",
    "RunnerToolCallDeltaData",
    "RunnerToolCallsCompletedData",
    "RunnerContentCompletedData",
    "RunnerUsageRecordedData",
    "RunnerProtocolErrorData",
    "RunnerHTTPErrorData",
    "RunnerDoneData",
    "RunnerEventData",
    "RunnerEvent",
]
