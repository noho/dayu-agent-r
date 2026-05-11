"""Host 内部 ToolRuntime 最小实现。

本模块只服务工具执行代理、schema-driven 截断与 Host 私有 framework
工具调度。ToolRuntime 不定义截断/cursor 专属 RunEvent；EventLog 只看到
Engine 普通工具调用请求与工具结果接受事件。
"""

from __future__ import annotations

import contextvars
import logging
import secrets
import time
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol

from dayu.contracts import ToolExecutor, ToolTruncateSpec
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine import ToolSchema
from dayu.host._attempt_lease import AttemptFencingError
from dayu.host._event_store import RunEventStore
from dayu.host._event_translation import terminal_result_from_event
from dayu.host._framework_tools import FRAMEWORK_FETCH_MORE_NAME, FrameworkToolSet
from dayu.host._runtime_truncate_manager import (
    RuntimeClock,
    RuntimeTokenGenerator,
    RuntimeTruncateManager,
)
from dayu.host.contracts import RunEvent, RunEventDraft
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_LOGGER: logging.Logger = logging.getLogger(__name__)
_ERROR_TOOL_RUNTIME_FAILED: str = "tool_runtime_failed"
_DEFAULT_TOKEN_BYTES: int = 32


class ToolRuntimeEventAppender(Protocol):
    """ToolRuntime attempt-scoped EventLog append port。

    P8 attempt owner scope 仍需要一个 Host 私有 append port 供 harness 绑定
    owner-aware appender。P8.5 Slice 1 后，ToolRuntime 不再通过该 port 写
    截断/cursor 专属事实；该 port 仍作为 attempt-scoped generic append
    能力被 harness 和既有 durable 边界复用。
    """

    async def verify_active_owner(self, *, run_id: str) -> None:
        """校验当前 appender 绑定的 owner 仍可写指定 run。

        :param run_id: 即将执行工具调用所属 Run id。
        :returns: 无返回值。
        :raises AttemptFencingError: durable attempt owner 已失效或 run 不匹配。
        :raises Exception: 实现自身错误透传。
        """
        ...

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """append 一条 Host RunEvent。

        :param draft: RunEvent 草稿。
        :returns: 已落库的 :class:`RunEvent`。
        :raises Exception: 实现自身错误透传；durable 实现可能抛
            ``AttemptFencingError``。
        """
        ...


@dataclass(frozen=True, slots=True)
class PlainRunEventAppender:
    """非 fencing 的 EventLog append 实现。

    :param event_store: 底层 :class:`RunEventStore`。
    """

    event_store: RunEventStore

    async def verify_active_owner(self, *, run_id: str) -> None:
        """非 durable appender 的 owner 校验 no-op。

        :param run_id: 即将执行工具调用所属 Run id；非 durable 路径不使用。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        _ = run_id

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """直接通过 :class:`RunEventStore.append` 落库。

        :param draft: RunEvent 草稿。
        :returns: 已落库的 :class:`RunEvent`。
        :raises Exception: 底层 EventStore 错误透传。
        """

        return await self.event_store.append(draft)


_ACTIVE_TOOL_RUNTIME_APPENDER: contextvars.ContextVar[
    ToolRuntimeEventAppender | None
] = contextvars.ContextVar("dayu_host_tool_runtime_appender", default=None)
"""当前 attempt 绑定的 fencing-aware appender。"""


@asynccontextmanager
async def ToolRuntimeOwnerScope(  # noqa: N802
    appender: ToolRuntimeEventAppender,
) -> AsyncGenerator[None, None]:
    """以 ContextVar 形式安装 attempt-scoped appender。

    :param appender: 当前 attempt 的 fencing-aware appender。
    :yields: 无 yield 值。
    :raises Exception: yield 内部异常透传；退出时无条件恢复旧 token。
    """

    token = _ACTIVE_TOOL_RUNTIME_APPENDER.set(appender)
    try:
        yield
    finally:
        _ACTIVE_TOOL_RUNTIME_APPENDER.reset(token)


def active_tool_runtime_appender() -> ToolRuntimeEventAppender | None:
    """返回当前 :class:`ToolRuntimeOwnerScope` 安装的 appender。

    :returns: 当前生效的 appender；无 scope 时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    return _ACTIVE_TOOL_RUNTIME_APPENDER.get()


@dataclass(frozen=True, slots=True)
class ToolRuntimeToolExecutor:
    """将 Host ToolRuntime 适配为 Engine 可消费的 ToolExecutor。

    :param runtime: Host 内部 ToolRuntime。
    """

    runtime: "HostToolRuntime"

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行工具调用并应用 Host ToolRuntime 治理。

        :param request: 工具执行请求。
        :returns: 工具执行 outcome。
        :raises AttemptFencingError: owner fencing 透传给 Host harness。
        :raises Exception: ToolRuntime 普通异常由 runtime 转为工具失败 outcome。
        """

        return await self.runtime.execute_tool_call(request)


@dataclass(frozen=True, slots=True)
class _RuntimeTerminalChecker:
    """基于 EventLog 的 run 终态检查器。

    :param event_store: Host RunEventStore。
    """

    event_store: RunEventStore

    async def is_terminal(self, run_id: str) -> bool:
        """判断 run 是否已经终态。

        :param run_id: Run id。
        :returns: 已终态返回 ``True``。
        :raises TypeError: 终态事件数据类型不一致时抛出。
        """

        events = await self.event_store.list_events(run_id=run_id, after=None)
        for event in reversed(events):
            if terminal_result_from_event(event) is not None:
                return True
        return False


@dataclass(slots=True, kw_only=True)
class HostToolRuntime:
    """Host-owned ToolRuntime。

    :param is_durable: durable 装配显式声明位；``True`` 时 owner scope
        缺失会 fail fast。
    :param executor: 底层业务 ToolExecutor。
    :param event_store: Host RunEventStore；仅用于终态检查与 non-durable
        fallback appender。
    :param truncate_specs: 按工具名注入的显式截断声明。
    :param manager: Host 私有截断管理器；未注入时由 runtime 自行构造。
    :param clock: 未注入 manager 时使用的 monotonic clock。
    :param token_generator: 未注入 manager 时使用的 cursor 原文生成器。
    """

    is_durable: bool
    executor: ToolExecutor
    event_store: RunEventStore
    truncate_specs: Mapping[str, ToolTruncateSpec] = field(default_factory=dict)
    manager: RuntimeTruncateManager | None = None
    clock: RuntimeClock | None = None
    token_generator: RuntimeTokenGenerator | None = None
    _default_manager: RuntimeTruncateManager = field(init=False)
    _framework_tools: FrameworkToolSet = field(init=False)

    def __post_init__(self) -> None:
        """初始化 Host 私有 manager 与 framework tool set。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        manager = self.manager
        if manager is None:
            terminal_checker = _RuntimeTerminalChecker(self.event_store)
            manager = RuntimeTruncateManager(
                terminal_checker=terminal_checker,
                clock=self.clock if self.clock is not None else time.monotonic,
                token_generator=(
                    self.token_generator
                    if self.token_generator is not None
                    else lambda: secrets.token_hex(_DEFAULT_TOKEN_BYTES)
                ),
            )
        self._default_manager = manager
        self._framework_tools = FrameworkToolSet(manager=manager)

    def _resolve_appender(self) -> ToolRuntimeEventAppender:
        """返回当前 attempt scope 内的 appender。

        :returns: 当前生效的 appender。
        :raises RuntimeError: ``is_durable=True`` 且没有 owner scope 时抛出。
        """

        active = _ACTIVE_TOOL_RUNTIME_APPENDER.get()
        if self.is_durable:
            if active is None:
                raise RuntimeError(
                    "durable runtime requires ToolRuntimeOwnerScope for "
                    "attempt-scoped execution"
                )
            return active
        if active is not None:
            return active
        return PlainRunEventAppender(event_store=self.event_store)

    def engine_visible_tool_schemas(
        self,
        user_tool_schemas: tuple[ToolSchema, ...],
    ) -> tuple[ToolSchema, ...]:
        """合成 Engine 可见工具 schema。

        :param user_tool_schemas: 调用方传入的业务工具 schema。
        :returns: 业务工具 schema 与 Host 私有 framework schema 的合成结果。
        :raises ValueError: 业务 schema 与 Host 私有工具名冲突时抛出。
        """

        user_names = {schema.function.name for schema in user_tool_schemas}
        framework_schemas = self._framework_tools.tool_schemas()
        framework_names = {
            schema.function.name for schema in framework_schemas
        }
        conflict = user_names & framework_names
        if conflict:
            framework_by_name = {
                schema.function.name: schema for schema in framework_schemas
            }
            if all(
                schema == framework_by_name.get(schema.function.name)
                for schema in user_tool_schemas
                if schema.function.name in conflict
            ):
                return user_tool_schemas
            names = ", ".join(sorted(conflict))
            raise ValueError(f"framework tool schema name conflict: {names}")
        return (*user_tool_schemas, *framework_schemas)

    async def execute_tool_call(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行工具调用并在成功结果上应用 Host 私有截断。

        :param request: 工具执行请求。
        :returns: 工具执行 outcome。
        :raises AttemptFencingError: owner fencing 必须透传给 Host harness。
        :raises Exception: ToolRuntime 自身普通异常转失败 outcome，不向外抛出。
        """

        appender = self._resolve_appender()
        await appender.verify_active_owner(run_id=request.context.run_id)
        is_framework_tool = request.call.name == FRAMEWORK_FETCH_MORE_NAME
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.tool_runtime.tool_call_start "
            "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
            "framework=%s",
            request.context.session_id,
            request.context.run_id,
            request.call.name,
            request.context.tool_call_id,
            is_framework_tool,
        )
        try:
            if is_framework_tool:
                outcome = await self._framework_tools.fetch_more_definition().executor.execute(
                    request
                )
                self._log_finished(
                    request=request,
                    outcome=outcome,
                    framework=True,
                    truncated=False,
                )
                return outcome
            outcome = await self.executor.execute(request)
            if not isinstance(outcome, ToolCompletedOutcome):
                self._log_finished(
                    request=request,
                    outcome=outcome,
                    framework=False,
                    truncated=False,
                )
                return outcome
            completed = self._default_manager.apply_truncation(
                request=request,
                outcome=outcome,
                spec=self.truncate_specs.get(request.call.name),
            )
            self._log_finished(
                request=request,
                outcome=completed,
                framework=False,
                truncated=completed is not outcome,
            )
            return completed
        except AttemptFencingError:
            raise
        except Exception as exc:
            _LOGGER.error(
                "host.tool_runtime.tool_call_finished "
                "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
                "framework=%s outcome=failed error=%s",
                request.context.session_id,
                request.context.run_id,
                request.call.name,
                request.context.tool_call_id,
                is_framework_tool,
                type(exc).__name__,
            )
            return ToolFailedOutcome(
                result=ToolResultFailure(
                    ok=False,
                    error=_ERROR_TOOL_RUNTIME_FAILED,
                    message=str(exc),
                    hint=None,
                    meta=None,
                )
            )

    def _log_finished(
        self,
        *,
        request: ToolExecutionRequest,
        outcome: ToolExecutionOutcome,
        framework: bool,
        truncated: bool,
    ) -> None:
        """记录工具调用完成日志。

        :param request: 工具执行请求。
        :param outcome: 工具执行 outcome。
        :param framework: 是否为 Host 私有 framework 工具。
        :param truncated: 是否发生截断。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.tool_runtime.tool_call_finished "
            "session_id=%s run_id=%s tool_name=%s tool_call_id=%s "
            "framework=%s outcome=%s truncated=%s",
            request.context.session_id,
            request.context.run_id,
            request.call.name,
            request.context.tool_call_id,
            framework,
            _tool_outcome_name(outcome),
            truncated,
        )


def _tool_outcome_name(outcome: ToolExecutionOutcome) -> str:
    """返回日志用工具执行 outcome 名称。

    :param outcome: 工具执行 outcome。
    :returns: ``completed``、``failed`` 或 ``awaiting``。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        return "completed"
    if isinstance(outcome, ToolFailedOutcome):
        return "failed"
    return "awaiting"


__all__: list[str] = []
