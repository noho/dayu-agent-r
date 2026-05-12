"""Agent run 请求与终态结果契约。

本模块包含：

- :class:`ContextBudgetSnapshot`：上下文预算快照（仅快照，无运算）。
- :class:`RunResumeHint`：运行恢复提示。
- :class:`AgentRunRequest`：发起 Agent run 的强类型请求。
- 四种终态 outcome：
  :class:`EngineRunOutcomeFinalAnswer` / :class:`EngineRunOutcomeFailed` /
  :class:`EngineRunOutcomeCancelled` / :class:`EngineRunOutcomeSuspended`。
- :data:`AgentRunResult`：四种终态的封闭联合。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.contracts.cancellation import CancellationToken
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessage
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.engine.contracts.tool_records import (
    AcceptedToolExecutionRecord,
    AwaitingToolExecutionRecord,
)
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_schema import ToolSchema


@dataclass(frozen=True, slots=True)
class ContextBudgetSnapshot:
    """上下文预算快照。

    Phase 0 仅承载 token 数三元组，**不**含计算逻辑、不消费阈值。
    当 provider HTTP context overflow 在无 usage 数据的边界被识别时，
    Engine 会填入 ``0/0/0`` 作为占位快照；Host compact 诊断使用 Host
    自己的 estimator 记录 before / after，不依赖该占位值。

    :param prompt_tokens: 提示 token 数。
    :param completion_tokens: 完成 token 数。
    :param total_tokens: 总 token 数。
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class RunResumeHint:
    """运行恢复提示。

    :param message: 中性的人类可读恢复提示文本。
    """

    message: str


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    """Agent run 请求。

    :param run_id: 运行 id。
    :param session_id: 会话 id。
    :param messages: 进入本次 run 的消息元组。
    :param disable_tools: 是否禁用工具调用。
    :param runner_spec: Runner 规约。
    :param runner_options: Runner 调用参数。
    :param agent_policy: Agent 策略。
    :param tool_schemas: 暴露给 LLM 的工具 schema 元组。
    :param tool_executor: 工具执行器，由 Host 通过 EngineWorker capability
        提供；EngineWorker 替 Host 在选定执行环境中代持并提供该 protocol
        handle。
    :param cancellation_token: 取消观察 token（由 Host 注入）。
    """

    run_id: str
    session_id: str
    messages: tuple[AgentMessage, ...]
    disable_tools: bool
    runner_spec: RunnerSpec
    runner_options: RunnerCallOptions
    agent_policy: AgentPolicy
    tool_schemas: tuple[ToolSchema, ...]
    tool_executor: ToolExecutor
    cancellation_token: CancellationToken


@dataclass(frozen=True, slots=True)
class EngineRunOutcomeFinalAnswer:
    """Agent run 以最终回答结束。

    :param session_id: 会话 id。
    :param run_id: 运行 id。
    :param content: 最终回答。
    :param filtered: 是否经过过滤器处理。
    :param degraded: 是否为降级回答。
    :param finish_reason: 完成原因。
    """

    session_id: str
    run_id: str
    content: str
    filtered: bool
    degraded: bool
    finish_reason: FinishReason


@dataclass(frozen=True, slots=True)
class EngineRunOutcomeFailed:
    """Agent run 以失败结束。

    :param session_id: 会话 id。
    :param run_id: 运行 id。
    :param error_code: 中性错误码。
    :param message: 人类可读错误描述。
    :param recoverable: 是否可恢复。
    """

    session_id: str
    run_id: str
    error_code: str
    message: str
    recoverable: bool


@dataclass(frozen=True, slots=True)
class EngineRunOutcomeCancelled:
    """Agent run 以取消结束。

    :param session_id: 会话 id。
    :param run_id: 运行 id。
    :param reason: 取消原因。
    :param requested_at: 取消请求时间。
    :param accepted_at: Engine 接受取消的时间。
    :param finished_at: 实际收尾完成时间。
    """

    session_id: str
    run_id: str
    reason: str
    requested_at: datetime
    accepted_at: datetime
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class EngineRunOutcomeSuspended:
    """Agent run 因长事务挂起。

    :param session_id: 会话 id。
    :param run_id: 运行 id。
    :param reason: 挂起原因。
    :param resume_hint: 可选恢复提示。
    :param accepted_records: 本批已 accepted 的工具记录元组（按输入顺序）；
        与 ``awaiting_records`` 共同重建 LLM context 已知事实。
    :param awaiting_records: 本批进入长事务等待的工具记录元组（按输入
        顺序）；至少含一个，否则不应进入 SUSPENDED。
    """

    session_id: str
    run_id: str
    reason: str
    resume_hint: RunResumeHint | None
    accepted_records: tuple[AcceptedToolExecutionRecord, ...]
    awaiting_records: tuple[AwaitingToolExecutionRecord, ...]

    def __post_init__(self) -> None:
        """校验 ``awaiting_records`` 非空。

        :returns: 无返回值。
        :raises ValueError: ``awaiting_records`` 为空时抛出。
        """

        if not self.awaiting_records:
            raise ValueError(
                "EngineRunOutcomeSuspended.awaiting_records must be non-empty"
            )


AgentRunResult: TypeAlias = (
    EngineRunOutcomeFinalAnswer
    | EngineRunOutcomeFailed
    | EngineRunOutcomeCancelled
    | EngineRunOutcomeSuspended
)
"""Agent run 终态封闭联合。"""


__all__ = [
    "ContextBudgetSnapshot",
    "RunResumeHint",
    "AgentRunRequest",
    "EngineRunOutcomeFinalAnswer",
    "EngineRunOutcomeFailed",
    "EngineRunOutcomeCancelled",
    "EngineRunOutcomeSuspended",
    "AgentRunResult",
]
