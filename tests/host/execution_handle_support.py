"""低层 Host command 测试的显式 execution admission 装配。

本模块仅供仍需分别打开 command handle 与 scheduler 的 Host 测试使用。它把测试
明确提供的 execution construction truth 装入 admission service，不为生产代码提供
默认值、兼容入口或配置 fallback。
"""

from __future__ import annotations

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.runner_spec import RunnerCallOptions
from dayu.host.admission import create_host_admission_service
from dayu.host.api import (
    HostCommandHandleOptions,
    OrdinaryRunExecutionBaseline,
)
from dayu.host.command import HostCommandHandle, create_host_command_handle
from dayu.host.context_policy import ContextBudgetPolicy
from dayu.host.dispatch import ActiveWorkerCancelPort
from dayu.host.durable.payload import PayloadStore
from dayu.host.memory import MemoryProjectionPolicy
from dayu.host.tooling import HostToolingOptions
from tests.host.public_smoke_support import deterministic_runner_spec


def create_execution_command_handle(
    options: HostCommandHandleOptions,
    *,
    ordinary_run_baseline: OrdinaryRunExecutionBaseline,
    memory_projection_policy: MemoryProjectionPolicy,
    tooling_options: HostToolingOptions | None = None,
    context_budget_policy: ContextBudgetPolicy | None = None,
    enable_truncation_manager: bool = False,
    active_registry: ActiveWorkerCancelPort | None = None,
) -> HostCommandHandle:
    """创建显式携带 execution construction truth 的低层测试 handle。

    :param options: command handle durable options。
    :param ordinary_run_baseline: ordinary Run execution baseline。
    :param memory_projection_policy: candidate memory projection policy。
    :param tooling_options: 可选业务工具 construction truth。
    :param context_budget_policy: 可选 context budget policy。
    :param enable_truncation_manager: 是否允许 truncation manager。
    :param active_registry: 可选 active worker cancel port。
    :returns: 已装配 execution admission service 的 command handle。
    :raises HostApiError: durable store 打开或 admission 装配失败时抛出。
    """

    handle = create_host_command_handle(options, active_registry=active_registry)
    handle._admission_service = create_host_admission_service(
        handle._transaction_runner(),
        terminal_post_commit_port=handle._terminal_post_commit_port,
        payload_store=PayloadStore(),
        event_log_store=None,
        idempotency_store=None,
        clock=None,
        id_factory=None,
        wakeup_port=None,
        projection_catchup_port=None,
        ordinary_run_baseline=ordinary_run_baseline,
        tooling_options=tooling_options,
        context_budget_policy=context_budget_policy,
        memory_projection_policy=memory_projection_policy,
        enable_truncation_manager=enable_truncation_manager,
        owner_host_instance_id=handle.host_handle_id,
    )
    return handle


def deterministic_ordinary_run_baseline(
    label: str,
) -> OrdinaryRunExecutionBaseline:
    """构造由调用测试显式命名的 deterministic ordinary Run baseline。

    本 helper 只消除测试模块间重复的 typed contract 字面量；调用方仍需明确传入
    baseline label、memory policy 及其它 construction truth。

    :param label: 用于隔离 Runner policy identity 的非空测试标签。
    :returns: deterministic ordinary Run baseline。
    :raises ValueError: 标签为空或 typed contract 字段非法时抛出。
    :raises TypeError: typed contract 类型非法时抛出。
    """

    if label.strip() == "":
        raise ValueError("label must be non-empty")
    return OrdinaryRunExecutionBaseline(
        runner_spec=deterministic_runner_spec(label),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
    )
