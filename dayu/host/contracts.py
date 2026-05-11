"""Host 最小 Run 契约。

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

    USER_INPUT_ACCEPTED = "user_input_accepted"
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
    CONTEXT_OVERFLOW_OBSERVED = "context_overflow_observed"
    CONTEXT_COMPACT_REQUESTED = "context_compact_requested"
    CONTEXT_COMPACT_COMPLETED = "context_compact_completed"
    CONTEXT_COMPACT_FAILED = "context_compact_failed"
    CONTEXT_ATTEMPT_RETRYING = "context_attempt_retrying"
    RUN_INPUT_CONTEXT_SNAPSHOT_BUILT = "run_input_context_snapshot_built"


class RunEventKind(StrEnum):
    """RunEvent 事实层级。"""

    CANONICAL = "canonical"
    PREVIEW = "preview"


class RunEventSource(StrEnum):
    """RunEvent 来源。"""

    ENGINE = "engine"
    HOST = "host"


class UserInputScope(StrEnum):
    """用户输入接纳事件的 memory 可见范围。"""

    SESSION = "session"


class ContextCompactFailureReason(StrEnum):
    """Host context compact 失败原因。"""

    RETRY_LIMIT_EXCEEDED = "retry_limit_exceeded"
    NOT_REDUCED = "not_reduced"
    FIDELITY_FAILED = "fidelity_failed"
    CURRENT_USER_NOT_FOUND = "current_user_not_found"
    TRACE_MISSING = "trace_missing"
    INTERNAL_ERROR = "internal_error"


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


@dataclass(frozen=True, slots=True)
class UserInputAcceptedData:
    """Host 已接纳用户输入事实。

    该事件是 RunInputBuilder、memory projection、replay 与 display timeline
    读取本轮用户输入的唯一 canonical 真源。``StartRunRequest.input`` 只
    作为入口材料用于写入此事件，不作为后续投影旁路。

    :param turn_id: 同一 session 内调用方或 Host 分配的 turn id。P3 最小
        实现使用 run id 作为稳定 turn id。
    :param content: 规范化后的用户输入正文。
    :param scope: memory scope；P3 仅写入 ``SESSION``。
    """

    turn_id: str
    content: str
    scope: UserInputScope


@dataclass(frozen=True, slots=True)
class HostContextOverflowObservedData:
    """Host 已观察到 Engine context overflow 事实。

    :param attempt_index: 同一 Run 内 Engine attempt 序号，从 ``0`` 起。
    :param engine_event_type: 触发该事实的 Engine event type。
    :param engine_error_code: Engine 失败错误码；非 terminal trigger 为
        ``None``。
    :param recoverable: Engine 是否声明该失败可恢复。
    :param reason: 中性触发原因。
    """

    attempt_index: int
    engine_event_type: str
    engine_error_code: str | None
    recoverable: bool
    reason: str


@dataclass(frozen=True, slots=True)
class HostContextCompactRequestedData:
    """Host context compact 已请求事实。

    :param attempt_index: 触发 compact 的 attempt 序号。
    :param policy_id: Host compact policy 标识。
    :param before_token_estimate: compact 前 RunInput 估算 token。
    :param before_char_size: compact 前 RunInput 字符数。
    :param estimator_id: Host 估算器算法标识。
    """

    attempt_index: int
    policy_id: str
    before_token_estimate: int
    before_char_size: int
    estimator_id: str


@dataclass(frozen=True, slots=True)
class HostContextCompactCompletedData:
    """Host context compact 成功事实。

    :param attempt_index: 触发 compact 的 attempt 序号。
    :param policy_id: Host compact policy 标识。
    :param before_token_estimate: compact 前估算 token。
    :param after_token_estimate: compact 后估算 token。
    :param before_char_size: compact 前字符数。
    :param after_char_size: compact 后字符数。
    :param reduced: compact 后是否严格变短；成功事实必须为 ``True``。
    :param preserved_current_user: 当前用户问题是否保真。
    :param preserved_pinned_state: pinned state 是否保真。
    :param preserved_evidence_anchors: 证据锚点是否保真。
    :param preserved_source_cursors: 来源 cursor 是否保真。
    :param preserved_tool_facts: 必要工具事实是否保真。
    :param dropped_item_count: 被确定丢弃的历史 item 数。
    :param degraded_item_count: 本次 compact 中被保留但降级表达的历史
        item 数；当前 deterministic compact 不做额外摘要降级，因此为
        ``0``，被确定移除的 raw turns 只计入 ``dropped_item_count``。
    :param estimator_id: Host 估算器算法标识。
    """

    attempt_index: int
    policy_id: str
    before_token_estimate: int
    after_token_estimate: int
    before_char_size: int
    after_char_size: int
    reduced: bool
    preserved_current_user: bool
    preserved_pinned_state: bool
    preserved_evidence_anchors: bool
    preserved_source_cursors: bool
    preserved_tool_facts: bool
    dropped_item_count: int
    degraded_item_count: int
    estimator_id: str


@dataclass(frozen=True, slots=True)
class HostContextCompactFailedData:
    """Host context compact 失败事实。

    :param attempt_index: 触发 compact 的 attempt 序号。
    :param policy_id: Host compact policy 标识。
    :param reason: 强类型失败原因。
    :param message: 中性可读说明。
    :param before_token_estimate: compact 前估算 token。
    :param after_token_estimate: compact 后估算 token；未生成时为 ``None``。
    :param before_char_size: compact 前字符数。
    :param after_char_size: compact 后字符数；未生成时为 ``None``。
    :param estimator_id: Host 估算器算法标识。
    """

    attempt_index: int
    policy_id: str
    reason: ContextCompactFailureReason
    message: str
    before_token_estimate: int
    after_token_estimate: int | None
    before_char_size: int
    after_char_size: int | None
    estimator_id: str


@dataclass(frozen=True, slots=True)
class HostContextAttemptRetryData:
    """Host context compact 后即将重试 attempt 的事实。

    :param from_attempt_index: 触发 compact 的 attempt 序号。
    :param next_attempt_index: 下一次 internal Engine attempt 序号。
    :param policy_id: Host compact policy 标识。
    :param reason: 中性重试原因。
    """

    from_attempt_index: int
    next_attempt_index: int
    policy_id: str
    reason: str


HostContextCompactEventData: TypeAlias = (
    HostContextOverflowObservedData
    | HostContextCompactRequestedData
    | HostContextCompactCompletedData
    | HostContextCompactFailedData
    | HostContextAttemptRetryData
)
"""Host context compact canonical RunEvent data 封闭联合。"""


@dataclass(frozen=True, slots=True)
class ToolValueSizeSummary:
    """工具结果值大小摘要。

    :param unit: 摘要单位。
    :param size: 当前值大小。
    :param total_estimate: 原始总量估计。
    :param fingerprint: 当前值摘要指纹。
    """

    unit: str
    size: int
    total_estimate: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class RunInputMessageSummary:
    """RunInput 单条消息的热层摘要。

    :param role: Engine AgentMessage role 字面量。
    :param source_kind: 消息来源类别（current_user / memory_block / system /
        caller_system 等），用于 trace 诊断分组。
    :param excerpt: 已按 Host bounded 策略截断的文本预览。
    :param content_hash: 原文 sha256 16-byte 前缀十六进制摘要，用于跨 run /
        replay 比对一致性。
    :param char_size: 原文字符数。
    :param token_estimate: 估算 token 数。
    """

    role: str
    source_kind: str
    excerpt: str
    content_hash: str
    char_size: int
    token_estimate: int


@dataclass(frozen=True, slots=True)
class RunInputToolSchemaSummary:
    """RunInput 暴露给 Engine 的工具 schema 摘要。

    :param name: 工具名称。
    :param schema_hash: 工具 schema 序列化后 sha256 16-byte 前缀十六进制。
    """

    name: str
    schema_hash: str


@dataclass(frozen=True, slots=True)
class RunInputContextMeta:
    """RunInput 整体上下文摘要。

    :param message_count: 进入 RunInput 的消息总数。
    :param role_sequence: 按顺序的消息 role 元组（hot 层快速诊断）。
    :param total_char_size: 估算字符总数。
    :param total_token_estimate: 估算 token 总数。
    :param memory_item_count: 来自 conversation memory 的 item 数量。
    :param current_user_run_id: 当前 user 输入对应的 run id。
    """

    message_count: int
    role_sequence: tuple[str, ...]
    total_char_size: int
    total_token_estimate: int
    memory_item_count: int
    current_user_run_id: str


@dataclass(frozen=True, slots=True)
class RunInputContextSnapshotBuiltData:
    """RunInputBuilder 完成、Engine attempt 启动前的 Host-owned 事实。

    本 fact 在 Host RunInputBuilder 完成后、Engine attempt 启动前同事务追
    加到 EventLog；完整 model_input_messages 与 tool_schemas 的 raw JSON
    由 Host raw payload side-store 持久保存。EventLog hot fact 只保留
    摘要、blob id、sha256 与 byte size。

    :param iteration_id: 当前 Engine iteration id。
    :param iteration_index: Engine iteration index（attempt 内自增）。
    :param attempt_index: Host attempt index（retry / compact 后 +1）。
    :param current_user_excerpt: 当前 user 输入截断预览。
    :param current_user_content_hash: 当前 user 输入 sha256 摘要前缀。
    :param current_user_source_cursor: 当前 user 输入 RunEvent cursor.sequence；
        若来源事件未携带 cursor 则 ``None``。
    :param message_summaries: 每条 model_input message 的热层摘要。
    :param tool_schema_summaries: 暴露给 Engine 的工具 schema 摘要。
    :param context_meta: 整体上下文摘要。
    :param raw_input_messages_blob_id: ``input_messages`` raw payload blob id。
    :param raw_input_messages_sha256: ``input_messages`` raw payload sha256。
    :param raw_input_messages_byte_size: ``input_messages`` raw payload 字节数。
    :param raw_tool_schemas_blob_id: ``tool_schemas`` raw payload blob id。
    :param raw_tool_schemas_sha256: ``tool_schemas`` raw payload sha256。
    :param raw_tool_schemas_byte_size: ``tool_schemas`` raw payload 字节数。
    """

    iteration_id: str
    iteration_index: int
    attempt_index: int
    current_user_excerpt: str
    current_user_content_hash: str
    current_user_source_cursor: int | None
    message_summaries: tuple[RunInputMessageSummary, ...]
    tool_schema_summaries: tuple[RunInputToolSchemaSummary, ...]
    context_meta: RunInputContextMeta
    raw_input_messages_blob_id: str
    raw_input_messages_sha256: str
    raw_input_messages_byte_size: int
    raw_tool_schemas_blob_id: str
    raw_tool_schemas_sha256: str
    raw_tool_schemas_byte_size: int


RunEventData: TypeAlias = (
    EngineEventData
    | HostRunFailedData
    | UserInputAcceptedData
    | HostContextCompactEventData
    | RunInputContextSnapshotBuiltData
)
"""Host RunEvent data 封闭联合。"""


@dataclass(frozen=True, slots=True)
class RunInput:
    """Run 初始输入。

    当前只承载 Engine 可直接消费的消息序列，不包含 memory、timeline 或
    run input builder 语义。

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
    等与同 Session active Run 仲裁在 P9 落地。

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
    "ContextCompactFailureReason",
    "HostContextAttemptRetryData",
    "HostContextCompactCompletedData",
    "HostContextCompactEventData",
    "HostContextCompactFailedData",
    "HostContextCompactRequestedData",
    "HostContextOverflowObservedData",
    "HostRunFailedData",
    "UserInputAcceptedData",
    "UserInputScope",
    "ToolValueSizeSummary",
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
    "RunInputContextMeta",
    "RunInputContextSnapshotBuiltData",
    "RunInputMessageSummary",
    "RunInputToolSchemaSummary",
    "RunOptions",
    "RunResult",
    "RunState",
    "RunStream",
    "RunSucceededResult",
    "RunSuspendedResult",
    "StartRunRequest",
]
