"""Host P1.5 最小 Run 契约。

本模块只定义当前 Run harness 与最小事件事实层所需的强类型结构。它不是
完整生产 Host 接口：创建幂等、持久 EventLog schema、Session governance
与多进程治理均由后续 Phase 落地。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

from dayu.engine import (
    AgentMessage,
    AgentPolicy,
    EngineEventData,
    EngineEventType,
    FinishReason,
    RunResumeHint,
    RunnerCallOptions,
    RunnerSpec,
    ToolSchema,
)


class RunState(StrEnum):
    """Host 当前最小 Run 状态。"""

    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"


class RunEventType(StrEnum):
    """Host RunEvent 类型。

    当前类型仍与 EngineEventType 保持一一映射，Host-owned failure 也复用
    ``RUN_FAILED``，通过 :class:`RunEventSource` 区分事实来源。
    """

    ITERATION_STARTED = EngineEventType.ITERATION_STARTED.value
    RUNNER_CONTENT_DELTA = EngineEventType.RUNNER_CONTENT_DELTA.value
    RUNNER_REASONING_DELTA = EngineEventType.RUNNER_REASONING_DELTA.value
    RUNNER_CONTENT_COMPLETED = EngineEventType.RUNNER_CONTENT_COMPLETED.value
    TOOL_CALL_REQUESTED = EngineEventType.TOOL_CALL_REQUESTED.value
    TOOL_RESULT_ACCEPTED = EngineEventType.TOOL_RESULT_ACCEPTED.value
    TOOL_AWAITING = EngineEventType.TOOL_AWAITING.value
    CONTEXT_COMPACTION_REQUESTED = (
        EngineEventType.CONTEXT_COMPACTION_REQUESTED.value
    )
    RUNNER_USAGE_RECORDED = EngineEventType.RUNNER_USAGE_RECORDED.value
    PROVIDER_PROTOCOL_ERROR = EngineEventType.PROVIDER_PROTOCOL_ERROR.value
    RUNNER_DONE = EngineEventType.RUNNER_DONE.value
    FINAL_ANSWER = EngineEventType.FINAL_ANSWER.value
    RUN_SUSPENDED = EngineEventType.RUN_SUSPENDED.value
    RUN_CANCELLED = EngineEventType.RUN_CANCELLED.value
    RUN_FAILED = EngineEventType.RUN_FAILED.value


class RunEventKind(StrEnum):
    """RunEvent 事实层级。"""

    CANONICAL = "canonical"
    PREVIEW = "preview"


class RunEventSource(StrEnum):
    """RunEvent 来源。"""

    ENGINE = "engine"
    HOST = "host"


@dataclass(frozen=True, slots=True)
class RunEventCursor:
    """Host 事件 cursor。

    P1.5 cursor 由 Host RunEventStore 在同一 run 内分配，不绑定 Engine
    sequence。

    :param sequence: 同一 run 内的事件序号。
    """

    sequence: int


@dataclass(frozen=True, slots=True)
class HostRunFailedData:
    """Host-owned run 失败事实。

    该 data 只用于 worker / proxy 异常导致 Host 无法获得 Engine 终态事件
    的路径，不代表完整 P7 生命周期治理。

    :param error_code: Host 侧中性错误码。
    :param message: 人类可读失败消息。
    :param recoverable: 是否可恢复。
    :param exception_type: 原始异常类型名。
    """

    error_code: str
    message: str
    recoverable: bool
    exception_type: str


RunEventData: TypeAlias = EngineEventData | HostRunFailedData
"""Host RunEvent data 封闭联合。"""


@dataclass(frozen=True, slots=True)
class RunInput:
    """Run 初始输入。

    当前只承载 Engine 可直接消费的消息序列，不包含 memory、timeline 或
    context builder 语义。

    :param messages: 进入 Engine 的 Agent 消息元组。
    """

    messages: tuple[AgentMessage, ...]


@dataclass(frozen=True, slots=True)
class RunOptions:
    """Run 执行选项。

    :param runner_spec: Runner 规约。
    :param runner_options: Runner 单次调用参数。
    :param agent_policy: Agent 运行策略。
    :param stream: 是否请求 Engine 流式运行。
    :param disable_tools: 是否禁用工具。
    :param tool_schemas: 暴露给 Engine / Runner 的工具 schema 元组。
    """

    runner_spec: RunnerSpec
    runner_options: RunnerCallOptions
    agent_policy: AgentPolicy
    stream: bool
    disable_tools: bool
    tool_schemas: tuple[ToolSchema, ...]


@dataclass(frozen=True, slots=True)
class StartRunRequest:
    """启动 Run 的当前最小请求。

    当前暂不包含 ``client_request_id``，因此不提供创建幂等。完整创建幂
    等与同 Session active Run 仲裁在 P7 落地。

    :param session_id: 会话 id。
    :param run_id: Run id，由调用方在测试 harness 中显式提供。
    :param input: Run 初始输入。
    :param options: Run 执行选项。
    """

    session_id: str
    run_id: str
    input: RunInput
    options: RunOptions


@dataclass(frozen=True, slots=True)
class RunHandle:
    """Run 句柄。

    :param session_id: 会话 id。
    :param run_id: Run id。
    :param state: 返回句柄时的 Run 状态快照。
    :param event_cursor: 订阅起点 cursor。
    """

    session_id: str
    run_id: str
    state: RunState
    event_cursor: RunEventCursor


@dataclass(frozen=True, slots=True)
class RunEvent:
    """Host Run 事件。

    ``RunEvent`` 只表示已经写入 Host RunEventStore 的事实，因此必须携带
    store 生成的 cursor。Engine sequence 可保留在来源事件中，但不是 Host
    cursor 真源。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param cursor: 事件 cursor。
    :param kind: 事件事实层级。
    :param source: 事件来源。
    :param type: Host RunEvent 类型。
    :param occurred_at: 事件发生时间。
    :param data: Host RunEvent data 联合。
    :param source_engine_event_id: 来源 EngineEvent id；Host-owned 事件为
        ``None``。
    """

    run_id: str
    session_id: str
    cursor: RunEventCursor
    kind: RunEventKind
    source: RunEventSource
    type: RunEventType
    occurred_at: datetime
    data: RunEventData
    source_engine_event_id: str | None


@dataclass(frozen=True, slots=True)
class RunEventDraft:
    """待写入 Host RunEventStore 的 Run 事件草稿。

    ``RunEventDraft`` 不携带 cursor，cursor 只能由 store append 时生成。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param kind: 事件事实层级。
    :param source: 事件来源。
    :param type: Host RunEvent 类型。
    :param occurred_at: 事件发生时间。
    :param data: Host RunEvent data 联合。
    :param source_engine_event_id: 来源 EngineEvent id；Host-owned 事件为
        ``None``。
    """

    run_id: str
    session_id: str
    kind: RunEventKind
    source: RunEventSource
    type: RunEventType
    occurred_at: datetime
    data: RunEventData
    source_engine_event_id: str | None


@dataclass(frozen=True, slots=True)
class RunSucceededResult:
    """Run 成功终态结果。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param content: 最终回答正文。
    :param filtered: 是否经过过滤。
    :param degraded: 是否为降级回答。
    :param finish_reason: 完成原因。
    :param terminal_event_cursor: 终态事件 cursor。
    """

    run_id: str
    session_id: str
    content: str
    filtered: bool
    degraded: bool
    finish_reason: FinishReason
    terminal_event_cursor: RunEventCursor


@dataclass(frozen=True, slots=True)
class RunFailedResult:
    """Run 失败终态结果。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param error_code: 失败错误码。
    :param message: 人类可读失败消息。
    :param recoverable: 是否可恢复。
    :param terminal_event_cursor: 终态事件 cursor。
    """

    run_id: str
    session_id: str
    error_code: str
    message: str
    recoverable: bool
    terminal_event_cursor: RunEventCursor


@dataclass(frozen=True, slots=True)
class RunCancelledResult:
    """Run 取消终态结果。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param reason: 取消原因。
    :param terminal_event_cursor: 终态事件 cursor。
    """

    run_id: str
    session_id: str
    reason: str
    terminal_event_cursor: RunEventCursor


@dataclass(frozen=True, slots=True)
class RunSuspendedResult:
    """Run 挂起终态结果。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param reason: 挂起原因。
    :param resume_hint: 可选恢复提示。
    :param terminal_event_cursor: 终态事件 cursor。
    """

    run_id: str
    session_id: str
    reason: str
    resume_hint: RunResumeHint | None
    terminal_event_cursor: RunEventCursor


RunResult: TypeAlias = (
    RunSucceededResult
    | RunFailedResult
    | RunCancelledResult
    | RunSuspendedResult
)
"""Run 终态结果封闭联合。"""

TERMINAL_RUN_EVENT_TYPES: frozenset[RunEventType] = frozenset(
    {
        RunEventType.FINAL_ANSWER,
        RunEventType.RUN_FAILED,
        RunEventType.RUN_CANCELLED,
        RunEventType.RUN_SUSPENDED,
    }
)
"""会导致 Host run 终止的 RunEvent 类型集合。"""


@dataclass(frozen=True, slots=True)
class RunStream:
    """Run 启动返回值。

    :param handle: Run 句柄。
    :param events: Host RunEvent 异步流。
    """

    handle: RunHandle
    events: AsyncIterator[RunEvent]


__all__ = [
    "HostRunFailedData",
    "RunCancelledResult",
    "RunEventData",
    "RunEvent",
    "RunEventCursor",
    "RunEventKind",
    "RunEventSource",
    "RunEventType",
    "RunFailedResult",
    "RunHandle",
    "RunInput",
    "RunOptions",
    "RunResult",
    "RunState",
    "RunStream",
    "RunSucceededResult",
    "RunSuspendedResult",
    "StartRunRequest",
]
