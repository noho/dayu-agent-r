"""工具执行能力声明契约。

本模块定义工具声明中的运行期执行形态。该能力只供 Host / ToolRuntime
选择治理边界使用，不进入 LLM-facing tool schema，也不得被解释为财报
事实、业务事实或模型可见结论。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import ToolCallRequest

PROCESS_TOOL_ENVELOPE_STATUS_FIELD = "status"
PROCESS_TOOL_ENVELOPE_COMPLETED_STATUS = "completed"
PROCESS_TOOL_ENVELOPE_FAILED_STATUS = "failed"
PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD = "value"
PROCESS_TOOL_ENVELOPE_FAILED_ERROR_TYPE_FIELD = "error_type"
PROCESS_TOOL_ENVELOPE_FAILED_MESSAGE_FIELD = "message"
PROCESS_TOOL_ENVELOPE_FAILED_HINT_FIELD = "hint"
PROCESS_TOOL_ENVELOPE_RESERVED_STATUSES = frozenset(
    ("awaiting", "cancelled", "timeout", "host_cancelled")
)
"""process-backed 工具子进程信封中由 Host 治理层保留的状态值。"""


@dataclass(frozen=True, slots=True)
class ProcessToolCompletedEnvelope:
    """已解析的 process-backed completed 信封。

    :param value: 工具子进程返回的 JSON 结果值。
    """

    value: JsonValue


@dataclass(frozen=True, slots=True)
class ProcessToolFailedEnvelope:
    """已解析的 process-backed failed 信封。

    :param error_type: 工具失败机器可读类型。
    :param message: 工具失败诊断消息。
    :param hint: 可选结构化提示；缺省、``null`` 或空白文本时为 ``None``。
    """

    error_type: str
    message: str
    hint: str | None


@dataclass(frozen=True, slots=True)
class ProcessToolMalformedEnvelope:
    """无法解析的 process-backed 信封。

    :param message: 面向诊断的格式错误说明。
    """

    message: str


@dataclass(frozen=True, slots=True)
class ProcessToolUnsupportedEnvelope:
    """语法有效但不允许由子进程表达的信封。

    :param status: 子进程返回的 status 文本。
    :param reserved: status 是否属于 Host 治理层保留值。
    """

    status: str
    reserved: bool


ProcessToolEnvelopeParseResult: TypeAlias = (
    ProcessToolCompletedEnvelope
    | ProcessToolFailedEnvelope
    | ProcessToolMalformedEnvelope
    | ProcessToolUnsupportedEnvelope
)
"""process-backed 工具子进程信封解析结果封闭联合。"""


def process_tool_completed_envelope(value: JsonValue) -> JsonValue:
    """构造 process-backed completed 信封。

    :param value: 工具子进程完成后的 JSON 结果值。
    :returns: 可序列化 JSON 信封。
    """

    return {
        PROCESS_TOOL_ENVELOPE_STATUS_FIELD: PROCESS_TOOL_ENVELOPE_COMPLETED_STATUS,
        PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD: value,
    }


def process_tool_failed_envelope(
    *, error_type: str, message: str, hint: str | None = None
) -> JsonValue:
    """构造 process-backed failed 信封。

    :param error_type: 非空机器可读失败类型。
    :param message: 非空失败诊断消息。
    :param hint: 可选结构化提示；``None`` 或空白文本时不写入信封。
    :returns: 可序列化 JSON 信封。
    :raises ValueError: ``error_type`` 或 ``message`` 为空时抛出。
    """

    if not error_type.strip():
        raise ValueError("process tool failed envelope error_type must be non-empty")
    if not message.strip():
        raise ValueError("process tool failed envelope message must be non-empty")
    envelope: dict[str, JsonValue] = {
        PROCESS_TOOL_ENVELOPE_STATUS_FIELD: PROCESS_TOOL_ENVELOPE_FAILED_STATUS,
        PROCESS_TOOL_ENVELOPE_FAILED_ERROR_TYPE_FIELD: error_type,
        PROCESS_TOOL_ENVELOPE_FAILED_MESSAGE_FIELD: message,
    }
    if hint is not None and hint.strip():
        envelope[PROCESS_TOOL_ENVELOPE_FAILED_HINT_FIELD] = hint
    return envelope


def parse_process_tool_envelope(
    envelope: JsonValue,
) -> ProcessToolEnvelopeParseResult:
    """解析 process-backed 工具子进程 stdout/result 信封。

    该解析器只允许子进程表达 ``completed`` 与 ``failed``。``awaiting``、
    ``cancelled``、``timeout`` 和 ``host_cancelled`` 属于 Host / Engine 治理
    状态，子进程返回时按 unsupported fail-closed 处理。

    :param envelope: 子进程返回的 JSON 值。
    :returns: 解析结果封闭联合。
    """

    if not isinstance(envelope, Mapping):
        return ProcessToolMalformedEnvelope(message="process envelope must be object")
    status = envelope.get(PROCESS_TOOL_ENVELOPE_STATUS_FIELD)
    if not isinstance(status, str):
        return ProcessToolMalformedEnvelope(
            message="process envelope status must be text"
        )
    if status == PROCESS_TOOL_ENVELOPE_COMPLETED_STATUS:
        return _parse_process_tool_completed_envelope(envelope)
    if status == PROCESS_TOOL_ENVELOPE_FAILED_STATUS:
        return _parse_process_tool_failed_envelope(envelope)
    return ProcessToolUnsupportedEnvelope(
        status=status,
        reserved=status in PROCESS_TOOL_ENVELOPE_RESERVED_STATUSES,
    )


def _parse_process_tool_completed_envelope(
    envelope: Mapping[str, JsonValue],
) -> ProcessToolCompletedEnvelope | ProcessToolMalformedEnvelope:
    """解析 completed 信封。

    :param envelope: 已确认 status 为 completed 的 JSON object。
    :returns: completed 解析结果或 malformed 结果。
    """

    if PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD not in envelope:
        return ProcessToolMalformedEnvelope(
            message="process completed envelope must contain value"
        )
    return ProcessToolCompletedEnvelope(
        value=envelope[PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD]
    )


def _parse_process_tool_failed_envelope(
    envelope: Mapping[str, JsonValue],
) -> ProcessToolFailedEnvelope | ProcessToolMalformedEnvelope:
    """解析 failed 信封。

    :param envelope: 已确认 status 为 failed 的 JSON object。
    :returns: failed 解析结果或 malformed 结果。
    """

    error_type = envelope.get(PROCESS_TOOL_ENVELOPE_FAILED_ERROR_TYPE_FIELD)
    message = envelope.get(PROCESS_TOOL_ENVELOPE_FAILED_MESSAGE_FIELD)
    if not isinstance(error_type, str) or error_type.strip() == "":
        return ProcessToolMalformedEnvelope(
            message="process failed envelope error_type must be non-empty text"
        )
    if not isinstance(message, str) or message.strip() == "":
        return ProcessToolMalformedEnvelope(
            message="process failed envelope message must be non-empty text"
        )
    hint = envelope.get(PROCESS_TOOL_ENVELOPE_FAILED_HINT_FIELD)
    if hint is not None and not isinstance(hint, str):
        return ProcessToolMalformedEnvelope(
            message="process failed envelope hint must be text when present"
        )
    return ProcessToolFailedEnvelope(
        error_type=error_type,
        message=message,
        hint=hint if isinstance(hint, str) and hint.strip() else None,
    )


@dataclass(frozen=True, slots=True)
class ProcessBackedToolContext:
    """子进程工具目标构造所需的可序列化上下文。

    本类型由 Host 从批式工具执行上下文投影而来，只包含
    multiprocessing spawn 可序列化的标量字段。它不包含
    cancellation_token、lock、runtime、repository、session 或 Host 内部
    对象。

    :param run_id: Agent run 唯一 id。
    :param session_id: 会话 id。
    :param iteration_id: 当前 LLM 迭代 id。
    :param timeout_seconds: 当前工具批次剩余超时预算；``None`` 表示调用方
        未提供。
    :param correlation_id: 批级中性关联标识；``None`` 表示调用方未提供。
    """

    run_id: str
    session_id: str
    iteration_id: str
    timeout_seconds: float | None
    correlation_id: str | None


class ToolExecutionMode(StrEnum):
    """工具运行时执行形态。

    枚举值进入稳定 digest 的 ``execution.mode`` 字段；它不进入
    LLM-facing tool schema，也不是业务事实。
    """

    ASYNC_DIRECT = "async_direct"
    THREAD_BACKED = "thread_backed"
    PROCESS_BACKED = "process_backed"


class ProcessBackedToolTarget(Protocol):
    """可在独立子进程内执行的工具目标。

    实现必须可被 multiprocessing spawn 序列化，不得捕获 repository、
    runtime、session、provider lock 或 Host 内部对象。
    """

    def __call__(self) -> JsonValue:
        """执行子进程工具目标并返回 JSON 信封。

        :returns: JSON 信封，合法形态仅为
            ``{"status": "completed", "value": JsonValue}`` 或
            ``{"status": "failed", "error_type": str, "message": str,
            "hint": str | null}``；failed 信封中的 ``hint`` 可缺省。
            子进程不得返回 awaiting、cancelled、timeout 或 host_cancelled
            语义；等待、取消和超时只能由 Host / Engine 治理层产生。
        :raises Exception: 未捕获异常由 process capsule 转为结构化工具失败。
        """

        ...


class ProcessBackedToolTargetFactory(Protocol):
    """根据工具调用构造 process-backed 目标。

    factory 本身与返回目标都必须可序列化，不得捕获 repository、runtime、
    session、provider lock 或 Host 内部对象。
    """

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> ProcessBackedToolTarget:
        """构造可序列化子进程目标。

        :param call: 单次工具调用请求。
        :param context: 已从批式执行上下文投影出的可序列化上下文；不包含
            cancellation_token、lock、runtime、repository、session 或 Host
            internals。
        :returns: 可被 multiprocessing spawn 序列化的目标。
        :raises Exception: 目标无法构造时抛出，ToolRuntime 转为工具失败。
        """

        ...


@dataclass(frozen=True, slots=True)
class AsyncDirectToolExecutionCapability:
    """直接 async 执行能力声明。

    :param request_abort_capable: 取消 async task 时，工具实现是否能关闭底层
        request / stream / client 等资源。该字段进入稳定 digest，不进入
        LLM-facing schema，也不得作为业务事实或财报事实使用。
    """

    request_abort_capable: bool = False


@dataclass(frozen=True, slots=True)
class ThreadBackedToolExecutionCapability:
    """线程托管执行能力声明。

    该模式只表示可取消 wrapper awaitable，不承诺停止 OS thread。

    :param production_safe_non_cooperative_cancel: 永远为 ``False`` 的显式
        guard 字段。该字段进入稳定 digest，不进入 LLM-facing schema；它
        用于证明 thread_backed 不能作为生产非协作 blocking cancel
        closeout 证据。
    """

    production_safe_non_cooperative_cancel: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ProcessBackedToolExecutionCapability:
    """子进程托管执行能力声明。

    :param target_factory: 根据工具调用构造可序列化 process target 的
        factory。该对象身份不进入稳定 digest，不进入 LLM-facing schema，
        也不是业务事实；digest 只记录 ``process_backed`` mode。
    """

    target_factory: ProcessBackedToolTargetFactory


ToolExecutionCapability: TypeAlias = (
    AsyncDirectToolExecutionCapability
    | ThreadBackedToolExecutionCapability
    | ProcessBackedToolExecutionCapability
)
"""工具运行时执行能力封闭联合。

联合成员只用于 ToolRuntime 选择执行边界；不进入 LLM-facing schema，也
不得投影为模型可见业务信息。
"""


__all__ = [
    "AsyncDirectToolExecutionCapability",
    "PROCESS_TOOL_ENVELOPE_COMPLETED_STATUS",
    "PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD",
    "PROCESS_TOOL_ENVELOPE_FAILED_ERROR_TYPE_FIELD",
    "PROCESS_TOOL_ENVELOPE_FAILED_HINT_FIELD",
    "PROCESS_TOOL_ENVELOPE_FAILED_MESSAGE_FIELD",
    "PROCESS_TOOL_ENVELOPE_FAILED_STATUS",
    "PROCESS_TOOL_ENVELOPE_RESERVED_STATUSES",
    "PROCESS_TOOL_ENVELOPE_STATUS_FIELD",
    "ProcessBackedToolContext",
    "ProcessBackedToolExecutionCapability",
    "ProcessBackedToolTarget",
    "ProcessBackedToolTargetFactory",
    "ProcessToolCompletedEnvelope",
    "ProcessToolEnvelopeParseResult",
    "ProcessToolFailedEnvelope",
    "ProcessToolMalformedEnvelope",
    "ProcessToolUnsupportedEnvelope",
    "ThreadBackedToolExecutionCapability",
    "ToolExecutionCapability",
    "ToolExecutionMode",
    "parse_process_tool_envelope",
    "process_tool_completed_envelope",
    "process_tool_failed_envelope",
]
