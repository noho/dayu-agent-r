"""Runner 事件契约。

:class:`RunnerEvent` 是 :class:`AsyncRunner.call` 产出的最小事件单元。
Runner 只承担「LLM 协议归一」职责：把 OpenAI / Anthropic / Gemini /
Qwen 等具体协议归一为本事件流，**不**执行工具、**不**拆分迭代、**不**
为事件补 ``session_id`` / ``run_id`` 等调用方关联字段。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TypeAlias

from dayu.engine.contracts.error_codes import (
    RunnerSpecificErrorCode,
    validate_runner_specific_error_code,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary
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
    PROVIDER_DIAGNOSTIC = "provider_diagnostic"
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


class RunnerDiagnosticSeverity(StrEnum):
    """Runner 非致命诊断严重级别闭集。"""

    INFO = "info"
    WARNING = "warning"


class RunnerDiagnosticSource(StrEnum):
    """Runner 非致命诊断来源闭集。"""

    HTTP_ADAPTER = "http_adapter"
    SSE_PARSER = "sse_parser"
    NON_STREAM_PARSER = "non_stream_parser"
    TOOL_CALL_AGGREGATOR = "tool_call_aggregator"
    CONTEXT_OVERFLOW_CLASSIFIER = "context_overflow_classifier"


class ContextOverflowDetectionKind(StrEnum):
    """provider context overflow 检测来源闭集。"""

    STRUCTURED_CODE = "structured_code"
    MESSAGE_MARKER_FALLBACK = "message_marker_fallback"
    NOT_OVERFLOW = "not_overflow"


@dataclass(frozen=True, slots=True)
class ContextOverflowDetection:
    """provider context overflow 检测结果。

    :param kind: 检测来源分类。只有 ``STRUCTURED_CODE`` 可作为业务真源；
        ``MESSAGE_MARKER_FALLBACK`` 只提供诊断 provenance。
    :param diagnostic_code: 需要对外持久化诊断时使用的诊断码。
    :param message: 需要对外持久化诊断时使用的人类可读摘要。
    :param raw_payload: 有界诊断载荷；无诊断或无结构化载荷时为 ``None``。
    """

    kind: ContextOverflowDetectionKind
    diagnostic_code: str | None = None
    message: str | None = None
    raw_payload: JsonValue | None = None


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
    """

    content: str | None
    reasoning_content: str | None


@dataclass(frozen=True, slots=True)
class RunnerUsageRecordedData:
    """用量记录事件 data。

    :param prompt_tokens: 输入 token 数。
    :param completion_tokens: 输出 token 数。
    :param total_tokens: 总 token 数。
    :param provider_request_id: provider 侧请求 id；为 ``None`` 表示未提供。
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider_request_id: str | None


@dataclass(frozen=True, slots=True)
class RunnerProtocolErrorData:
    """provider 协议错误事件 data。

    :param error_code: 中性错误码。
    :param message: 人类可读错误描述。
    :param provider_request_id: provider 侧请求 id；为 ``None`` 表示
        未提供。
    :param raw_payload: 有界诊断载荷；为 ``None`` 表示无。不承诺保留
        provider 原始报错载荷。
    :param partial_tool_calls: SSE 失败前已解析但未完成的 tool call 有界
        摘要；不包含 raw argument payload。
    """

    error_code: RunnerSpecificErrorCode
    message: str
    provider_request_id: str | None
    raw_payload: JsonValue | None
    partial_tool_calls: tuple[PartialToolCallSummary, ...] = ()

    def __post_init__(self) -> None:
        """校验 provider 协议错误码类型。

        :returns: ``None``。
        :raises TypeError: ``error_code`` 不是专有错误码 wrapper 时抛出。
        """

        validate_runner_specific_error_code(
            self.error_code,
            field_name="RunnerProtocolErrorData.error_code",
        )


@dataclass(frozen=True, slots=True)
class RunnerProviderDiagnosticData:
    """provider 非致命诊断事件 data。

    :param diagnostic_code: 中性诊断码。
    :param severity: 诊断严重级别闭集。
    :param message: 人类可读诊断摘要。
    :param provider_request_id: provider 侧请求 id；为 ``None`` 表示未提供。
    :param raw_payload: 有界诊断载荷；为 ``None`` 表示无。不承诺保留
        provider 原始报错载荷。
    :param partial_tool_calls: 诊断发生时已解析但未完成的 tool call 有界
        摘要；不包含 raw argument payload。
    :param diagnostic_source: 产生诊断的 Runner 内部来源闭集。
    """

    diagnostic_code: str
    severity: RunnerDiagnosticSeverity
    message: str
    provider_request_id: str | None
    raw_payload: JsonValue | None
    partial_tool_calls: tuple[PartialToolCallSummary, ...] = ()
    diagnostic_source: RunnerDiagnosticSource = (
        RunnerDiagnosticSource.HTTP_ADAPTER
    )


@dataclass(frozen=True, slots=True)
class RunnerHTTPErrorData:
    """Runner HTTP / 网络 / 超时终态错误事件 data。

    :param error_code: 传输层错误中性枚举。
    :param http_status: HTTP 状态码；网络 / 超时无状态码时为 ``None``。
    :param message: 人类可读错误描述。
    :param provider_request_id: provider 侧请求 id；为 ``None`` 表示
        未提供。
    :param raw_payload: 从有界 HTTP body 派生的有界诊断载荷；解析失败或
        非 JSON object 响应为 ``None``。不承诺保留 provider 原始报错
        载荷。
    :param attempt: 触发本错误事件时已经尝试的次数（首次为 1）。
    :param retried: 是否已经发生过至少一次重试。
    :param context_overflow_detection: HTTP 错误被识别为 context overflow 时
        的检测 provenance；非 context overflow 时为 ``None``。

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
    context_overflow_detection: ContextOverflowDetection | None = None


@dataclass(frozen=True, slots=True)
class RunnerDoneData:
    """Runner 事件流结束事件 data。

    :param finish_reason: 完成原因。
    :param provider_request_id: 本次 Runner 调用最终采用的 provider
        response request id；网络层在收到 response 前失败时为 ``None``。
    """

    finish_reason: FinishReason
    provider_request_id: str | None


RunnerEventData: TypeAlias = (
    RunnerContentDeltaData
    | RunnerReasoningDeltaData
    | RunnerToolCallDeltaData
    | RunnerToolCallsCompletedData
    | RunnerContentCompletedData
    | RunnerUsageRecordedData
    | RunnerProviderDiagnosticData
    | RunnerProtocolErrorData
    | RunnerHTTPErrorData
    | RunnerDoneData
)
"""Runner 事件 data 封闭联合。"""

RUNNER_EVENT_TYPE_TO_DATA: Mapping[RunnerEventType, type[RunnerEventData]] = (
    MappingProxyType(
        {
            RunnerEventType.RUNNER_CONTENT_DELTA: RunnerContentDeltaData,
            RunnerEventType.RUNNER_REASONING_DELTA: RunnerReasoningDeltaData,
            RunnerEventType.RUNNER_TOOL_CALL_DELTA: RunnerToolCallDeltaData,
            RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED: RunnerToolCallsCompletedData,
            RunnerEventType.RUNNER_CONTENT_COMPLETED: RunnerContentCompletedData,
            RunnerEventType.RUNNER_USAGE_RECORDED: RunnerUsageRecordedData,
            RunnerEventType.PROVIDER_DIAGNOSTIC: RunnerProviderDiagnosticData,
            RunnerEventType.PROVIDER_PROTOCOL_ERROR: RunnerProtocolErrorData,
            RunnerEventType.RUNNER_HTTP_ERROR: RunnerHTTPErrorData,
            RunnerEventType.RUNNER_DONE: RunnerDoneData,
        }
    )
)
"""RunnerEvent type/data 配对真源。"""


def runner_event_type_for_data(data: RunnerEventData) -> RunnerEventType:
    """根据 RunnerEvent data 类型返回对应事件类型。

    :param data: RunnerEvent data 联合成员。
    :returns: 与 data 类型唯一对应的 RunnerEventType。
    :raises TypeError: ``data`` 不是 RunnerEventData 闭集成员时抛出。
    """

    for event_type, data_type in RUNNER_EVENT_TYPE_TO_DATA.items():
        if isinstance(data, data_type):
            return event_type
    raise TypeError("RunnerEvent.data has unsupported type")


def validate_runner_event_pairing(
    event_type: RunnerEventType, data: RunnerEventData
) -> None:
    """校验 RunnerEvent type/data 判别关系。

    :param event_type: RunnerEventType。
    :param data: RunnerEvent data 联合成员。
    :returns: ``None``。
    :raises TypeError: ``event_type`` 不是 RunnerEventType，或 ``data`` 不是
        RunnerEventData 闭集成员时抛出。
    :raises ValueError: type 与 data 类型不匹配时抛出。
    """

    if not isinstance(event_type, RunnerEventType):
        raise TypeError("RunnerEvent.type must be RunnerEventType")
    actual_type = runner_event_type_for_data(data)
    if actual_type is not event_type:
        raise ValueError(
            "RunnerEvent.type/data mismatch: "
            f"type={event_type.value} data_type={type(data).__name__}"
        )


@dataclass(frozen=True, slots=True)
class RunnerEvent:
    """Runner 最小事件单元。

    :param type: 事件类型枚举。
    :param data: 事件 data 联合的某个具体成员。
    :param occurred_at: 事件发生时间。

    本事件**不**含 ``session_id`` / ``run_id``，Agent 在
    :class:`EngineEvent` 提升阶段补齐这些字段。
    """

    type: RunnerEventType
    data: RunnerEventData
    occurred_at: datetime

    def __post_init__(self) -> None:
        """校验 RunnerEvent 公共判别契约。

        :returns: ``None``。
        :raises TypeError: ``type`` 或 ``data`` 类型非法时抛出。
        :raises ValueError: ``type`` 与 ``data`` 不匹配时抛出。
        """

        validate_runner_event_pairing(self.type, self.data)


__all__ = [
    "RunnerEventType",
    "RunnerHTTPErrorCode",
    "RunnerDiagnosticSeverity",
    "RunnerDiagnosticSource",
    "ContextOverflowDetectionKind",
    "ContextOverflowDetection",
    "PartialToolCallSummary",
    "RunnerContentDeltaData",
    "RunnerReasoningDeltaData",
    "RunnerToolCallDeltaData",
    "RunnerToolCallsCompletedData",
    "RunnerContentCompletedData",
    "RunnerUsageRecordedData",
    "RunnerProviderDiagnosticData",
    "RunnerProtocolErrorData",
    "RunnerHTTPErrorData",
    "RunnerDoneData",
    "RunnerEventData",
    "RUNNER_EVENT_TYPE_TO_DATA",
    "RunnerEvent",
    "runner_event_type_for_data",
    "validate_runner_event_pairing",
]
