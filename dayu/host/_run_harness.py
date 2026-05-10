"""Host P4 最小 Run harness。

本模块定义 Host 内部 :class:`LocalRunHarness`，不再提供 package-level
``start_run`` / ``stream_run_events`` / ``get_run_result`` 便利入口。上层
（service / smoke / 测试）一律通过 :func:`build_durable_harness` 装配
durable harness 后调用其实例方法；test-only 场景显式构造
``LocalRunHarness(is_durable=False, ...)``。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from functools import partial
from typing import Protocol, TypeVar, runtime_checkable

from dayu.contracts import ToolExecutor
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolExecutionOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine import (
    AgentMessage,
    AssistantMessage,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventType,
    RunFailedData,
    SystemMessage,
    UserMessage,
)
from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptOwnerContext,
)
from dayu.host._attempt_state_mapping import (
    attempt_state_from_terminal_event_type,
)
from dayu.host._attempt_supervisor import (
    AttemptOwnerLossReason,
    AttemptSupervisor,
)
from dayu.host._context_compaction import (
    ContextCompactCoordinator,
    ContextCompactDecisionStatus,
)
from dayu.host._conversation_memory import (
    ConversationMemoryStore,
    snapshot_with_transient_tool_facts,
)
from dayu.host._durable_event_store import DurableRunEventStore
from dayu.host._event_observer import ProjectionCoordinator
from dayu.host._event_store import InMemoryRunEventStore, RunEventStore
from dayu.host._event_translation import (
    context_attempt_retrying_draft,
    context_compact_completed_draft,
    context_compact_failed_draft,
    context_compact_requested_draft,
    context_overflow_observed_draft,
    host_context_compact_failure_terminal_draft,
    host_failure_draft,
    terminal_result_from_event,
    translate_engine_event,
    user_input_accepted_draft,
)
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import (
    AttemptState,
    GlobalEventPosition,
)
from dayu.host._proxy import LocalProxy, WorkerProxy
from dayu.host._run_input_builder import (
    DefaultRunInputBuilder,
    RunInputBuildTrace,
    RunInputBuilder,
)
from dayu.host._run_input_context_fact import RunInputContextFactBuilder
from dayu.host._run_state_store import AttemptStateStore
from dayu.host._tool_runtime import (
    InMemoryToolRuntime,
    PlainRunEventAppender,
    ToolRuntimeEventAppender,
    ToolRuntimeOwnerScope,
    ToolRuntimeToolExecutor,
    active_tool_runtime_appender,
)
from dayu.host._worker import EngineWorker
from dayu.host.contracts import (
    TERMINAL_RUN_EVENT_TYPES,
    ContextCompactFailureReason,
    HostContextAttemptRetryData,
    HostContextOverflowObservedData,
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunHandle,
    RunInput,
    RunResult,
    RunState,
    RunStream,
    StartRunRequest,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_INITIAL_CURSOR_SEQUENCE: int = -1
_ERROR_TOOL_EXECUTOR_NOT_CONFIGURED: str = "tool_executor_not_configured"
_ERROR_CURRENT_USER_INPUT_REQUIRED: str = "current_user_input_required"
_ERROR_CURRENT_USER_INPUT_SHAPE_EMPTY: str = (
    "start_run_input_requires_trailing_non_empty_user_message"
)
_ERROR_CURRENT_USER_INPUT_SHAPE_TRAILING_USER: str = (
    "start_run_input_must_end_with_single_current_user_message"
)
_ERROR_CURRENT_USER_INPUT_SHAPE_MULTIPLE_USER: str = (
    "start_run_input_allows_only_one_trailing_current_user_message"
)
_ERROR_CURRENT_USER_INPUT_SHAPE_UNSUPPORTED_HISTORY: str = (
    "start_run_input_allows_only_leading_system_messages_before_current_user"
)
_ERROR_RUN_INPUT_TRACE_CACHE_LIMIT_INVALID: str = (
    "run_input_trace_cache_limit_must_be_positive"
)
_ERROR_RUN_INPUT_MESSAGE_CACHE_LIMIT_INVALID: str = (
    "run_input_message_cache_limit_must_be_positive"
)
_ERROR_CONTEXT_COMPACT_RETRY_LIMIT_INVALID: str = (
    "context_compact_retry_limit_must_be_non_negative"
)
_ERROR_ENGINE_STREAM_ENDED_WITHOUT_TERMINAL: str = (
    "engine_stream_ended_without_terminal"
)
_ERROR_ATTEMPT_LEASE_LOST: str = "attempt_lease_lost"
_ERROR_CONTEXT_OVERFLOW_RETRY_ACQUIRE_FAILED: str = (
    "context_overflow_retry_acquire_failed"
)
_RUN_INPUT_TRACE_CACHE_LIMIT: int = 32
_RUN_INPUT_MESSAGE_CACHE_LIMIT: int = 3
_CONTEXT_COMPACT_RETRY_LIMIT: int = 1
_ERROR_CONTEXT_COMPACTION_REQUIRED: str = "context_compaction_required"
_COMPACT_TRACE_MISSING_MESSAGE: str = "run input build trace is missing"
_UNEXPECTED_COMPACTION_TERMINAL_MESSAGE: str = (
    "engine produced terminal event after context compaction request"
)
_LOGGER: logging.Logger = logging.getLogger(__name__)
_RunCacheValue = TypeVar("_RunCacheValue")


class _OwnerLostDuringEngineWait(Exception):
    """harness 等待 Engine event 期间 owner-lost 命中的内部信号。

    本异常仅在 :meth:`LocalRunHarness._next_engine_event_or_lose_owner`
    的 race 命中 owner-lost 时构造, 用于把控制权交回 ``_run_to_store``
    主循环, 让其按 owner-lost 路径关闭 engine iterator、停止后续
    EventLog append 并执行 owner-aware diagnostic close。

    本异常不进入 Engine、不进入 EventLog payload、不暴露 owner secret
    token; 只携带 typed :class:`AttemptOwnerLossReason` 用于日志与诊断
    分支判断。
    """

    def __init__(self, *, loss_reason: AttemptOwnerLossReason) -> None:
        """构造 owner-lost 信号。

        :param loss_reason: typed owner-lost 原因。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(f"attempt owner lost: {loss_reason.value}")
        self.loss_reason: AttemptOwnerLossReason = loss_reason


_RUN_INPUT_CONTEXT_FACT_BUILDER_REQUIRED: str = (
    "run_input_context_fact_builder must be provided when "
    "tool_trace_context_fact_enabled is True"
)


def _iteration_id_for_attempt(*, run_id: str, attempt_index: int) -> str:
    """派生 attempt 启动前的占位 iteration_id。

    Engine attempt 的 iteration id 在首个 ``ITERATION_STARTED`` 事件前不
    可见，但 P7 trace observer 需要把 RunInput context snapshot 与
    iteration 0 关联用于 raw payload 拆文件路径。本函数派生稳定占位
    ``f"{run_id}-attempt-{attempt_index:02d}"``，跨 replay 一致。

    :param run_id: Run id。
    :param attempt_index: Host attempt 序号。
    :returns: 占位 iteration_id。
    :raises Exception: 不主动抛出异常。
    """

    return f"{run_id}-attempt-{attempt_index:02d}"


@asynccontextmanager
async def _null_attempt_owner_scope() -> AsyncGenerator[None, None]:
    """no-op attempt owner scope, 用于 legacy / 无 supervisor 路径。

    与 :class:`ToolRuntimeOwnerScope` 等价的 async context manager 接口,
    但不修改 ToolRuntime active appender, 也不引入任何 owner CAS。这样
    ``LocalRunHarness._run_to_store`` 可以无条件用同一形态的
    ``async with`` 包裹 attempt 体, 不必 if/else 分支。

    :yields: 无 yield 值。
    :raises Exception: 不主动抛出异常。
    """

    yield


def _synthesize_compact_trace(
    *,
    request: StartRunRequest,
    compacted_input: RunInput,
    after_token_estimate: int,
) -> RunInputBuildTrace:
    """compact 路径下合成 :class:`RunInputBuildTrace`。

    compact 不再经过 :class:`RunInputBuilder`，所以没有原生 trace。本函数
    合成一个最小 trace：``items`` 留空，``total_token_estimate`` 取
    ``completed_data.after_token_estimate``，``total_char_size`` 由 compact
    后消息文本累加而成。该 trace 仅用于 P7 Host-owned context snapshot
    fact 的元信息字段，不参与 RunInputBuilder 自身行为。

    :param request: compact 前的 attempt 请求；提供 session_id / run_id。
    :param compacted_input: compact 后的 :class:`RunInput`。
    :param after_token_estimate: compact 完成后估算 token 总数。
    :returns: 合成的 :class:`RunInputBuildTrace`。
    :raises Exception: 不主动抛出异常。
    """

    total_char_size = sum(
        len(_message_text_for_trace(message))
        for message in compacted_input.messages
    )
    return RunInputBuildTrace(
        session_id=request.session_id,
        run_id=request.run_id,
        items=(),
        total_char_size=total_char_size,
        total_token_estimate=after_token_estimate,
    )


def _message_text_for_trace(message: AgentMessage) -> str:
    """读取 AgentMessage 正文用于字符数累加。

    :param message: AgentMessage。
    :returns: 文本正文；AssistantMessage.content 为 ``None`` 时返回空串。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(message, AssistantMessage):
        return "" if message.content is None else message.content
    return message.content


@runtime_checkable
class _ClosableAsyncIterator(Protocol):
    """支持显式关闭的异步迭代器协议。"""

    async def aclose(self) -> None:
        """关闭异步迭代器。

        :returns: 无返回值。
        :raises Exception: 关闭失败时透传底层异常。
        """
        ...


@dataclass(frozen=True, slots=True)
class _NeverCancelledToken:
    """当前默认未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


@dataclass(frozen=True, slots=True)
class _NoopToolExecutor:
    """public ``start_run`` 默认工具执行器。"""

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """返回失败 outcome，避免 public 入口隐式拥有工具能力。

        :param request: 工具执行请求。
        :returns: 失败 outcome。
        :raises Exception: 不主动抛出异常。
        """

        return ToolFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error=_ERROR_TOOL_EXECUTOR_NOT_CONFIGURED,
                message=request.call.name,
                hint=None,
                meta=None,
            )
        )


@dataclass(frozen=True, slots=True)
class _ActiveAttempt:
    """Host attempt 运行期句柄。

    durable 路径下, ``_begin_attempt_if_durable`` 在 attempt 启动边界返回
    本句柄, ``_run_to_store`` 与 ``_finish_attempt_if_durable`` 通过它在
    attempt 内串联状态:

    - ``attempt_id``: attempt 标识, 由 supervisor (P8-S3) 或 legacy
      ``attempt_state_store.create`` (P6) 分配。
    - ``owner_context``: supervisor 路径下当前 owner 句柄;
      legacy attempt_state_store 路径为 ``None``。
    - ``lease_exit_stack``: 持有 :meth:`AttemptSupervisor.lease_context`
      的 :class:`AsyncExitStack`; finish 时 ``aclose`` 触发 supervisor
      退出 / 取消 renew loop。legacy 路径为 ``None``。

    :param attempt_id: attempt 标识。
    :param owner_context: supervisor 路径下的 owner 句柄。
    :param lease_exit_stack: lease_context 的 ``AsyncExitStack``。
    """

    attempt_id: str
    owner_context: AttemptOwnerContext | None
    lease_exit_stack: AsyncExitStack | None


@dataclass(frozen=True, slots=True)
class _AcceptedStartInput:
    """Host ingress 接纳后的消息结构。

    :param current_user_text: 当前用户输入正文。
    :param caller_system_messages: 调用方提供的 leading system prompt。
    """

    current_user_text: str
    caller_system_messages: tuple[SystemMessage, ...]


def _require_memory_store() -> ConversationMemoryStore:
    """legacy default factory: 拒绝默认装配 memory store。

    P8-S8 起 production ``InMemoryConversationMemoryStore`` 已删除；调用
    方必须显式传入 :class:`ConversationMemoryStore`。Durable harness 通过
    :func:`build_durable_harness` 注入 :class:`DurableConversationMemoryStore`，
    legacy 内存测试路径必须传入 ``tests/host/_memory_store_fake`` 中的
    fake store。

    :returns: 不返回；总是 raise。
    :raises RuntimeError: 始终抛出，以提示调用方未注入 memory store。
    """

    raise RuntimeError(
        "LocalRunHarness 必须显式传入 memory_store: "
        "production InMemoryConversationMemoryStore 已在 P8-S8 删除"
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class LocalRunHarness:
    """Host 内部本地 Run harness。

    :param is_durable: P8-S1 装配显式声明位:``True`` 表示 production /
        durable 装配 (必须注入 :class:`AttemptSupervisor` +
        :class:`DurableRunEventStore` + :class:`HostStorage`,
        ``attempt_state_store`` 必须为 ``None``);``False`` 表示 test-only
        non-durable 装配 (禁止注入 ``attempt_supervisor``)。本字段是
        keyword-only 必填参数, 所有 ``LocalRunHarness(...)`` 构造点必须显
        式传值,否则触发 ``TypeError``。
    :param proxy: Host 内部 worker proxy。
    :param event_store: Host 内部 RunEventStore。
    :param tool_runtime: Host 内部 ToolRuntime。
    :param memory_store: Host 内部 ConversationMemoryStore。
    :param run_input_builder: Host 内部 RunInputBuilder。
    :param compact_coordinator: Host 内部 context compact coordinator。
    :param coordinator: 可选 :class:`ProjectionCoordinator`；durable 路径下
        必须注入,terminal 后由 harness 调用 ``coordinator.drain()`` 推进
        observer checkpoint / required projection；为 ``None`` 时退化为
        legacy 内存路径,直接调用 ``memory_store.project_run_events``。
    :param attempt_state_store: 可选 :class:`AttemptStateStore`；仅 P6
        legacy 非 durable 兼容路径使用。durable (``is_durable=True``)
        装配禁止注入本字段。
    :param attempt_supervisor: 可选 :class:`AttemptSupervisor`；P8-S3 起,
        durable 装配层通过装配 :class:`AttemptLeaseConfig` 注入 supervisor,
        harness 只在 attempt 边界薄委托 ``lease_context``, 自身不写 lease
        SQL、不计算 TTL、不实现 renew loop, 也不处理 fencing 逻辑。
        ``is_durable=True`` 时必填; ``is_durable=False`` 时禁止注入。
    :param storage: 可选 :class:`HostStorage`；attempt_state_store 写入需要
        共享事务,因此 harness 持有 storage handle 以开启短事务。
        ``is_durable=True`` 时必填。
    :param tool_trace_context_fact_enabled: P7 开关，启用后 harness 在每个
        attempt 启动前同事务追加 ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT``
        canonical fact。仅 durable 路径生效（要求
        ``event_store`` 是 :class:`DurableRunEventStore` 且 ``storage`` 非
        ``None``）。
    :param run_input_context_fact_builder: P7 RunInput context fact 构造器；
        ``tool_trace_context_fact_enabled`` 启用后必须注入。
    :param context_compact_retry_limit: context overflow compact retry 上限。
    :param run_input_trace_cache_limit: RunInput 构造 trace 保留上限。
    :param run_input_message_cache_limit: RunInput 消息诊断缓存保留上限。
    """

    is_durable: bool
    proxy: WorkerProxy
    event_store: RunEventStore = field(default_factory=InMemoryRunEventStore)
    tool_runtime: InMemoryToolRuntime | None = None
    memory_store: ConversationMemoryStore = field(
        default_factory=lambda: _require_memory_store()
    )
    run_input_builder: RunInputBuilder = field(
        default_factory=DefaultRunInputBuilder
    )
    compact_coordinator: ContextCompactCoordinator = field(
        default_factory=ContextCompactCoordinator
    )
    coordinator: ProjectionCoordinator | None = None
    attempt_state_store: AttemptStateStore | None = None
    attempt_supervisor: AttemptSupervisor | None = None
    storage: HostStorage | None = None
    tool_trace_context_fact_enabled: bool = False
    run_input_context_fact_builder: RunInputContextFactBuilder | None = None
    context_compact_retry_limit: int = _CONTEXT_COMPACT_RETRY_LIMIT
    run_input_trace_cache_limit: int = _RUN_INPUT_TRACE_CACHE_LIMIT
    run_input_message_cache_limit: int = _RUN_INPUT_MESSAGE_CACHE_LIMIT
    last_run_input_build_trace_by_run: OrderedDict[
        str, RunInputBuildTrace
    ] = field(
        default_factory=OrderedDict,
        init=False,
    )
    last_run_input_messages_by_run: OrderedDict[
        str, tuple[AgentMessage, ...]
    ] = field(
        default_factory=OrderedDict,
        init=False,
    )

    def __post_init__(self) -> None:
        """校验 harness 内部 compact retry / 调试缓存配置 + durable invariant。

        :returns: 无返回值。
        :raises ValueError: compact retry 上限为负数，或调试缓存容量
            不是正数时抛出。
        :raises RuntimeError: ``is_durable`` 与注入字段组合违反 P8-S1
            装配契约时抛出。
        """

        if self.context_compact_retry_limit < 0:
            raise ValueError(_ERROR_CONTEXT_COMPACT_RETRY_LIMIT_INVALID)
        if self.run_input_trace_cache_limit <= 0:
            raise ValueError(_ERROR_RUN_INPUT_TRACE_CACHE_LIMIT_INVALID)
        if self.run_input_message_cache_limit <= 0:
            raise ValueError(_ERROR_RUN_INPUT_MESSAGE_CACHE_LIMIT_INVALID)
        if self.is_durable:
            if self.attempt_supervisor is None:
                raise RuntimeError(
                    "durable harness invariant violated: "
                    "attempt_supervisor is required when is_durable=True"
                )
            # invariant 校验:isinstance 用于装配契约校验,非类型分支判断;
            # 与 CLAUDE.md 禁止 isinstance 当类型逃避不冲突。
            if not isinstance(self.event_store, DurableRunEventStore):
                raise RuntimeError(
                    "durable harness invariant violated: "
                    "event_store must be DurableRunEventStore when "
                    f"is_durable=True (got {type(self.event_store).__name__})"
                )
            if self.attempt_state_store is not None:
                raise RuntimeError(
                    "durable harness invariant violated: "
                    "attempt_state_store must be None when is_durable=True "
                    "(P6 legacy store is forbidden in durable path)"
                )
            if self.storage is None:
                raise RuntimeError(
                    "durable harness invariant violated: "
                    "storage is required when is_durable=True"
                )
            if self.tool_runtime is None:
                raise RuntimeError(
                    "durable harness invariant violated: "
                    "tool_runtime is required when is_durable=True"
                )
            if not self.tool_runtime.is_durable:
                raise RuntimeError(
                    "durable harness invariant violated: "
                    "tool_runtime.is_durable must be True when "
                    "harness.is_durable=True"
                )
            return
        if self.attempt_supervisor is not None:
            raise RuntimeError(
                "non-durable harness invariant violated: "
                "attempt_supervisor must be None when is_durable=False "
                "(test-only path forbids supervisor)"
            )
        if self.tool_runtime is not None and self.tool_runtime.is_durable:
            raise RuntimeError(
                "non-durable harness invariant violated: "
                "tool_runtime.is_durable must be False when "
                "harness.is_durable=False"
            )

    def _resolve_attempt_appender(
        self,
        active_attempt: "_ActiveAttempt | None",
    ) -> ToolRuntimeEventAppender:
        """返回当前 attempt 的 fencing-aware fact appender。

        - ``is_durable=True``: 必须能解析 :class:`AttemptOwnerContext`
          (来自 ``active_attempt`` 或 ToolRuntime ContextVar);
          解析失败立即 ``RuntimeError`` fail fast,
          **永不**返回 :class:`PlainRunEventAppender`。
        - ``is_durable=False`` (test-only): 沿用旧 fallback 语义,
          返回 :class:`PlainRunEventAppender`, 直接透传
          :class:`RunEventStore.append`。

        :param active_attempt: 当前 active attempt 句柄; 为 ``None`` 表
            示 run-level 或 lease-lost 之后的非 attempt-scoped 写入。
        :returns: 当前生效的 :class:`ToolRuntimeEventAppender`。
        :raises RuntimeError: ``is_durable=True`` 且无法解析 owner_context
            时抛出。
        """

        if self.is_durable:
            if (
                self.attempt_supervisor is not None
                and active_attempt is not None
                and active_attempt.owner_context is not None
            ):
                return self.attempt_supervisor.scoped_appender(
                    active_attempt.owner_context
                )
            active = active_tool_runtime_appender()
            if active is not None:
                return active
            raise RuntimeError(
                "durable harness requires AttemptOwnerContext for "
                "attempt-scoped append"
            )
        if (
            self.attempt_supervisor is not None
            and active_attempt is not None
            and active_attempt.owner_context is not None
        ):
            return self.attempt_supervisor.scoped_appender(
                active_attempt.owner_context
            )
        return PlainRunEventAppender(event_store=self.event_store)

    def _scope_appender(self) -> ToolRuntimeEventAppender:
        """从 ToolRuntime active scope 解析当前 attempt 的 fact appender。

        本 helper 与 :meth:`_resolve_attempt_appender` 互补: 后者要求显
        式持有 :class:`_ActiveAttempt`, 前者读取由
        :class:`ToolRuntimeOwnerScope` 安装的 ContextVar, 让
        ``_compact_or_fail`` 等不直接持有 ``active_attempt`` 的 helper
        也能命中 attempt-scoped append, 不必把 ``active_attempt`` 显式
        穿透到所有签名。

        :returns: 当前生效的 :class:`ToolRuntimeEventAppender`; 没有
            scope 时退化为 :class:`PlainRunEventAppender`。
        :raises Exception: 不主动抛出异常。
        """

        active = active_tool_runtime_appender()
        if active is not None:
            return active
        return PlainRunEventAppender(event_store=self.event_store)

    def _attempt_owner_scope(
        self,
        active_attempt: "_ActiveAttempt | None",
    ) -> AbstractAsyncContextManager[None]:
        """构造当前 attempt 的 ``ToolRuntimeOwnerScope`` 包装。

        durable + supervisor 路径返回真正的
        :class:`ToolRuntimeOwnerScope`, 在 attempt 生命周期内把绑定
        owner 的 :class:`AttemptScopedRunEventAppender` 注入到
        :class:`InMemoryToolRuntime` 的 active appender ContextVar,
        使 ToolRuntime canonical fact append (``TOOL_RESULT_TRUNCATED``
        / ``TOOL_CURSOR_*`` / ``TOOL_FETCH_MORE_*``) 与 Engine 翻译事件
        统一走 fencing-aware 同事务路径; legacy / 无 supervisor / 无
        ``owner_context`` 路径返回 :func:`_null_attempt_owner_scope`,
        退化为 P6/P7 行为, 不修改 ToolRuntime active appender。

        :param active_attempt: 当前 attempt 句柄。
        :returns: async context manager。
        :raises Exception: 不主动抛出异常。
        """

        if (
            self.attempt_supervisor is not None
            and active_attempt is not None
            and active_attempt.owner_context is not None
        ):
            return ToolRuntimeOwnerScope(
                self.attempt_supervisor.scoped_appender(
                    active_attempt.owner_context
                )
            )
        return _null_attempt_owner_scope()

    async def start_run(self, request: StartRunRequest) -> RunStream:
        """启动 P1.5 内存态 Run。

        后台 task 将 EngineEvent 翻译为 RunEventDraft 并先 append 到
        RunEventStore；返回的事件流只是 store 的订阅视图。P3 起，本方法
        会先追加 Host-owned ``USER_INPUT_ACCEPTED`` 事件，并从 EventLog
        与 memory snapshot 构造真正交给 Engine 的 RunInput；若追加失败，
        不会启动 Engine。P4 起，context overflow 后可在同一 Run 下启动
        compacted internal attempt，但不会再次追加 ``USER_INPUT_ACCEPTED``。

        :param request: start_run 请求。
        :returns: RunStream，包含句柄与事件流。
        :raises Exception: 构造后台任务失败时透传底层异常。
        """

        accepted_input = _extract_accepted_start_input(request=request)
        current_user_event = await self.event_store.append(
            user_input_accepted_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                turn_id=request.run_id,
                content=accepted_input.current_user_text,
            )
        )
        snapshot = await self.memory_store.get_snapshot(request.session_id)
        build_result = self.run_input_builder.build(
            snapshot=snapshot,
            current_user_event=current_user_event,
            caller_system_messages=accepted_input.caller_system_messages,
        )
        self._remember_run_input_build_trace(
            run_id=request.run_id,
            trace=build_result.trace,
        )
        self._remember_run_input_messages(
            run_id=request.run_id,
            messages=build_result.run_input.messages,
        )
        engine_request = replace(request, input=build_result.run_input)
        await self._append_run_input_context_snapshot_fact(
            request=engine_request,
            build_trace=build_result.trace,
            current_user_event=current_user_event,
            attempt_index=0,
            iteration_index=0,
            iteration_id=_iteration_id_for_attempt(
                run_id=engine_request.run_id, attempt_index=0
            ),
        )
        task = asyncio.create_task(
            self._run_to_store(
                request=engine_request,
                current_user_event=current_user_event,
            )
        )
        task.add_done_callback(
            partial(_log_background_task_failure, engine_request)
        )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.start_accepted session_id=%s run_id=%s "
            "caller_system_count=%s run_input_message_count=%s "
            "current_user_cursor=%s",
            engine_request.session_id,
            engine_request.run_id,
            len(accepted_input.caller_system_messages),
            len(build_result.run_input.messages),
            current_user_event.cursor.sequence,
        )
        handle = RunHandle(
            session_id=engine_request.session_id,
            run_id=engine_request.run_id,
            state=RunState.RUNNING,
            event_cursor=RunEventCursor(sequence=_INITIAL_CURSOR_SEQUENCE),
        )
        return RunStream(
            handle=handle,
            events=self.event_store.subscribe(
                run_id=engine_request.run_id,
                after=handle.event_cursor,
            ),
        )

    async def _run_to_store(
        self,
        request: StartRunRequest,
        current_user_event: RunEvent | None = None,
    ) -> None:
        """立即执行 Engine 事件流并写入 RunEventStore。

        :param request: start_run 请求。
        :param current_user_event: 本 Run 原始 USER_INPUT_ACCEPTED 事件；仅
            context compact retry 路径必需。
        :returns: 无返回值。
        :raises Exception: 翻译、append 或终态结果推导失败时暴露底层错误；
            worker / proxy 取事件异常会转为 Host-owned failure RunEvent。
        """

        token = _NeverCancelledToken()
        attempt_request = request
        attempt_index = 0
        event_count = 0
        terminal_seen = False
        current_active_attempt: _ActiveAttempt | None = (
            await self._begin_attempt_if_durable(
                request=request,
                attempt_index=attempt_index,
            )
        )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.background_start session_id=%s run_id=%s",
            request.session_id,
            request.run_id,
        )
        try:
            while True:
                overflow_trigger_seen = False
                overflow_observed_seen = False
                overflow_trigger_event: EngineEvent | None = None
                _LOGGER.log(
                    VERBOSE_LOG_LEVEL,
                    "host.run.attempt_start session_id=%s run_id=%s "
                    "attempt_index=%s message_count=%s",
                    attempt_request.session_id,
                    attempt_request.run_id,
                    attempt_index,
                    len(attempt_request.input.messages),
                )
                try:
                    engine_events = self.proxy.stream_engine_events(
                        request=attempt_request,
                        cancellation_token=token,
                    )
                except Exception as exc:
                    terminal_seen = await self._append_worker_failure_if_needed(
                        request=attempt_request,
                        error=exc,
                        event_count=event_count,
                        terminal_seen=terminal_seen,
                    )
                    return
                try:
                    async with self._attempt_owner_scope(current_active_attempt):
                        while True:
                            try:
                                event = await self._next_engine_event_or_lose_owner(
                                    engine_events=engine_events,
                                    active_attempt=current_active_attempt,
                                )
                            except StopAsyncIteration:
                                break
                            except _OwnerLostDuringEngineWait as lost:
                                terminal_seen = (
                                    await self._handle_owner_lost(
                                        request=attempt_request,
                                        active_attempt=current_active_attempt,
                                        loss_reason=lost.loss_reason,
                                        event_count=event_count,
                                        terminal_seen=terminal_seen,
                                    )
                                )
                                current_active_attempt = None
                                return
                            except Exception as exc:
                                terminal_seen = (
                                    await self._append_worker_failure_if_needed(
                                        request=attempt_request,
                                        error=exc,
                                        event_count=event_count,
                                        terminal_seen=terminal_seen,
                                    )
                                )
                                return
                            event_count += 1
                            if _is_context_compaction_requested(event):
                                overflow_trigger_seen = True
                                overflow_trigger_event = event
                                _LOGGER.log(
                                    VERBOSE_LOG_LEVEL,
                                    "host.run.context_overflow_triggered "
                                    "session_id=%s run_id=%s attempt_index=%s "
                                    "engine_event_type=%s",
                                    attempt_request.session_id,
                                    attempt_request.run_id,
                                    attempt_index,
                                    event.type.value,
                                )
                                await self._resolve_attempt_appender(
                                    current_active_attempt
                                ).append(translate_engine_event(event))
                                continue
                            if _is_context_compaction_required_terminal(event):
                                overflow_trigger_seen = True
                                await self._append_overflow_observed(
                                    request=attempt_request,
                                    event=event,
                                    attempt_index=attempt_index,
                                )
                                overflow_observed_seen = True
                                break
                            if overflow_trigger_seen and _is_terminal_engine_event(
                                event
                            ):
                                await self._append_unexpected_compaction_terminal_closure(
                                    request=attempt_request,
                                    event=event,
                                    attempt_index=attempt_index,
                                )
                            draft = translate_engine_event(event)
                            atomic_attempt = (
                                current_active_attempt
                                if (
                                    draft.type in TERMINAL_RUN_EVENT_TYPES
                                    and current_active_attempt is not None
                                    and self._can_atomic_terminal_close(
                                        current_active_attempt
                                    )
                                )
                                else None
                            )
                            if atomic_attempt is not None:
                                stored_event = (
                                    await self._append_terminal_and_close(
                                        active_attempt=atomic_attempt,
                                        draft=draft,
                                    )
                                )
                            else:
                                stored_event = await self._resolve_attempt_appender(
                                    current_active_attempt
                                ).append(draft)
                            if terminal_result_from_event(stored_event) is not None:
                                _LOGGER.log(
                                    VERBOSE_LOG_LEVEL,
                                    "host.run.terminal_appended session_id=%s "
                                    "run_id=%s attempt_index=%s "
                                    "engine_event_type=%s event_count=%s "
                                    "event_cursor=%s",
                                    attempt_request.session_id,
                                    attempt_request.run_id,
                                    attempt_index,
                                    event.type.value,
                                    event_count,
                                    stored_event.cursor.sequence,
                                )
                                terminal_seen = True
                                if atomic_attempt is None:
                                    # legacy / 非 supervisor 路径仍走旧 close。
                                    await self._finish_attempt_if_durable(
                                        active_attempt=current_active_attempt,
                                        terminal_event=stored_event,
                                    )
                                current_active_attempt = None
                                return
                        if overflow_trigger_seen:
                            if (
                                not overflow_observed_seen
                                and overflow_trigger_event is not None
                            ):
                                await self._append_overflow_observed(
                                    request=attempt_request,
                                    event=overflow_trigger_event,
                                    attempt_index=attempt_index,
                                )
                            if current_user_event is None:
                                raise RuntimeError(
                                    "context compact requires current_user_event"
                                )
                            try:
                                next_request_with_trace = await self._compact_or_fail(
                                    request=attempt_request,
                                    current_user_event=current_user_event,
                                    attempt_index=attempt_index,
                                )
                            except Exception as exc:
                                terminal_seen = (
                                    await self._append_compact_exception_failure(
                                        request=attempt_request,
                                        attempt_index=attempt_index,
                                        error=exc,
                                    )
                                )
                                return
                            if next_request_with_trace is None:
                                terminal_seen = True
                                await self._finish_attempt_if_durable(
                                    active_attempt=current_active_attempt,
                                    terminal_event=None,
                                    state=AttemptState.FAILED,
                                    failure_summary="context_compact_failed",
                                )
                                current_active_attempt = None
                                return
                            next_request, compact_trace = next_request_with_trace
                            # F5 root cause: 必须 (1) 先 acquire 新 attempt,
                            # 成功后再把旧 attempt 收口到 STALE; (2) acquire
                            # 失败时旧 attempt 仍持有有效 owner, 必须沿旧
                            # owner-scoped 路径写入 Host-owned ``RUN_FAILED``
                            # terminal RunEvent (走 :meth:`_append_terminal_and_close`
                            # 同事务原子路径), 不能裸 ``event_store.append``,
                            # 否则 RunStream 永远收不到 terminal, RunResult
                            # 也无法推导, Run 残留无 terminal 的 STALE 收口。
                            new_attempt_index = attempt_index + 1
                            try:
                                new_active_attempt = (
                                    await self._begin_attempt_if_durable(
                                        request=next_request,
                                        attempt_index=new_attempt_index,
                                    )
                                )
                            except Exception as acquire_exc:
                                terminal_seen = (
                                    await self._append_overflow_acquire_failure_terminal(
                                        request=attempt_request,
                                        active_attempt=current_active_attempt,
                                        attempt_index=attempt_index,
                                        new_attempt_index=new_attempt_index,
                                        error=acquire_exc,
                                    )
                                )
                                # _append_terminal_and_close 已经把旧
                                # attempt 推进到终态并 close lease_exit_stack;
                                # 把 current_active_attempt 置 None 防止
                                # 上层 finally 二次 close。非 supervisor 路径
                                # 下旧 attempt 由上层 finally 走
                                # _finish_attempt_if_durable(state=FAILED)
                                # 推进 host_attempts。
                                if (
                                    current_active_attempt is not None
                                    and self._can_atomic_terminal_close(
                                        current_active_attempt
                                    )
                                ):
                                    current_active_attempt = None
                                return
                            # 新 attempt 成功 acquire 后再关闭旧 attempt; 此时
                            # 切换 owner 视角不再可逆。
                            await self._finish_attempt_if_durable(
                                active_attempt=current_active_attempt,
                                terminal_event=None,
                                state=AttemptState.STALE,
                                failure_summary="context_overflow_compacted",
                            )
                            attempt_request = next_request
                            attempt_index = new_attempt_index
                            current_active_attempt = new_active_attempt
                            await self._append_run_input_context_snapshot_fact(
                                request=attempt_request,
                                build_trace=compact_trace,
                                current_user_event=current_user_event,
                                attempt_index=attempt_index,
                                iteration_index=0,
                                iteration_id=_iteration_id_for_attempt(
                                    run_id=attempt_request.run_id,
                                    attempt_index=attempt_index,
                                ),
                                active_attempt=current_active_attempt,
                            )
                            continue
                        terminal_seen = (
                            await self._append_missing_terminal_failure_if_needed(
                                request=attempt_request,
                                event_count=event_count,
                                terminal_seen=terminal_seen,
                            )
                        )
                        return
                finally:
                    await _close_engine_events_if_supported(
                        engine_events=engine_events,
                        request=attempt_request,
                    )
        finally:
            if current_active_attempt is not None:
                await self._finish_attempt_if_durable(
                    active_attempt=current_active_attempt,
                    terminal_event=None,
                    state=(
                        AttemptState.FAILED
                        if terminal_seen
                        else AttemptState.STALE
                    ),
                    failure_summary=(
                        "attempt_closed_by_terminal_event"
                        if terminal_seen
                        else "run_terminated_without_terminal_event"
                    ),
                )
                current_active_attempt = None
            if terminal_seen:
                await self._project_terminal_run(request.run_id)
            _LOGGER.info(
                "host.run.background_finished session_id=%s run_id=%s "
                "event_count=%s terminal_seen=%s",
                request.session_id,
                request.run_id,
                event_count,
                terminal_seen,
            )

    async def _next_engine_event_or_lose_owner(
        self,
        *,
        engine_events: AsyncIterator[EngineEvent],
        active_attempt: "_ActiveAttempt | None",
    ) -> EngineEvent:
        """等待下一个 Engine event, 与 owner-lost signal race。

        无 supervisor / 无 owner_context (legacy 内存路径或 P6 兼容路径)
        时, 直接 ``anext(engine_events)``, 与本 slice 之前行为一致。

        supervisor 路径下, harness 与 supervisor 的 owner-lost signal
        做 race:

        - Engine event 先到: 正常返回, 调用方继续翻译并 append。
        - owner-lost 先到: 抛 :class:`_OwnerLostDuringEngineWait`,
          调用方负责取消 engine iterator、停止后续 append 并走 owner-
          aware diagnostic close 路径。
        - 两者都已就绪时, owner-lost 优先, 防止旧 owner 把已经 fenced
          后到达的 stale Engine event 写进 EventLog。

        :param engine_events: worker 返回的 EngineEvent 异步流。
        :param active_attempt: 当前 active attempt 句柄。
        :returns: 下一个 EngineEvent。
        :raises StopAsyncIteration: Engine stream 正常耗尽时透传。
        :raises _OwnerLostDuringEngineWait: owner-lost 命中时抛出。
        :raises Exception: 透传 Engine iterator 自身异常。
        """

        if (
            self.attempt_supervisor is None
            or active_attempt is None
            or active_attempt.owner_context is None
        ):
            return await anext(engine_events)
        owner_context = active_attempt.owner_context
        # 进入 race 前先做无锁快照检查: 已失活直接抛, 不再尝试拉取
        # Engine event。
        if not self.attempt_supervisor.is_owner_active(owner_context):
            loss_reason = await self.attempt_supervisor.wait_owner_lost(
                owner_context
            )
            raise _OwnerLostDuringEngineWait(loss_reason=loss_reason)
        next_event_task: asyncio.Task[EngineEvent] = asyncio.ensure_future(
            anext(engine_events)
        )
        owner_lost_task: asyncio.Task[AttemptOwnerLossReason] = (
            asyncio.ensure_future(
                self.attempt_supervisor.wait_owner_lost(owner_context)
            )
        )
        try:
            done, _ = await asyncio.wait(
                {next_event_task, owner_lost_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if owner_lost_task in done:
                loss_reason = owner_lost_task.result()
                raise _OwnerLostDuringEngineWait(loss_reason=loss_reason)
            return next_event_task.result()
        finally:
            if not owner_lost_task.done():
                owner_lost_task.cancel()
                try:
                    await owner_lost_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            if not next_event_task.done():
                next_event_task.cancel()
                try:
                    await next_event_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    async def _handle_owner_lost(
        self,
        *,
        request: StartRunRequest,
        active_attempt: "_ActiveAttempt | None",
        loss_reason: AttemptOwnerLossReason,
        event_count: int,
        terminal_seen: bool,
    ) -> bool:
        """attempt owner-lost 后通过原子接口收口或安全放弃。

        本 helper 是 P8-S3 owner-lost 路径的统一收口入口:

        - 若已经写入终态 (``terminal_seen``), 不再追加 Host-owned failure,
          交给上层 finally 块的 :meth:`_finish_attempt_if_durable` 完成
          attempt 状态推进;
        - 否则通过 :meth:`AttemptSupervisor.append_terminal_and_close`
          在单一 ``BEGIN IMMEDIATE`` 事务内尝试: ``verify_owner`` CAS +
          terminal RunEvent append + ``host_attempts`` 终态 close。
          - CAS hit: terminal ``RUN_FAILED(error_code=attempt_lease_lost)``
            落库, 上层 ``_run_to_store`` 经由现有 ``terminal_seen`` 路径
            自然退出, RunStream 订阅方收到 terminal event 后 generator
            自然结束;
          - CAS miss (``AttemptFencingError``): 整事务回滚, EventLog 不
            残留 stale terminal RunEvent; 仅记 typed log 供诊断, 上层
            generator 通过现有 ``_run_to_store`` cleanup 自然退出。

        本 helper 不再执行裸 ``event_store.append``; legacy 非 supervisor
        路径在 ``is_durable=False`` 装配下仅记诊断日志后返回, 不写终态。

        :param request: 当前 attempt 请求。
        :param active_attempt: 当前 active attempt 句柄, 仅用于诊断字段。
        :param loss_reason: typed owner-lost 原因。
        :param event_count: 已成功取得的 EngineEvent 数量。
        :param terminal_seen: 是否已经从已 append 事件推导出终态。
        :returns: 已存在或新写入终态时返回 ``True``; CAS miss 或非
            durable 路径返回 ``False``。
        :raises Exception: ``append_terminal_and_close`` 抛出非
            :class:`AttemptFencingError` 异常时透传。
        """

        attempt_id = (
            "<none>" if active_attempt is None else active_attempt.attempt_id
        )
        _LOGGER.error(
            "host.run.attempt_lease_lost session_id=%s run_id=%s "
            "attempt_id=%s loss_reason=%s event_count=%s",
            request.session_id,
            request.run_id,
            attempt_id,
            loss_reason.value,
            event_count,
        )
        if terminal_seen:
            return True
        # 非 supervisor 路径: 仅在 ``is_durable=False`` test-only 装配下
        # 命中; 此时无 owner CAS 真源, 不写任何终态, 由上层 generator
        # cleanup 自然结束。
        if (
            self.attempt_supervisor is None
            or active_attempt is None
            or active_attempt.owner_context is None
            or active_attempt.lease_exit_stack is None
        ):
            return False
        supervisor = self.attempt_supervisor
        owner_context = active_attempt.owner_context
        failure_summary = (
            f"{_ERROR_ATTEMPT_LEASE_LOST}:{loss_reason.value}"
        )
        draft = host_failure_draft(
            run_id=request.run_id,
            session_id=request.session_id,
            occurred_at=datetime.now(tz=timezone.utc),
            error=RuntimeError(_ERROR_ATTEMPT_LEASE_LOST),
            error_code=_ERROR_ATTEMPT_LEASE_LOST,
        )
        try:
            link = await supervisor.append_terminal_and_close(
                owner_context=owner_context,
                draft=draft,
                failure_summary=failure_summary,
                terminal_state_override=AttemptState.LOST,
            )
        except AttemptFencingError as fence_exc:
            # CAS miss: owner 已被 recovery / 其它进程替换或 attempt 已
            # 推到终态。本路径**绝不**写 RunEvent: 任何额外 append 都会
            # 与 recovery 真源竞争, 形成 stale terminal。
            _LOGGER.warning(
                "host.run.attempt_lease_lost_cas_miss session_id=%s "
                "run_id=%s attempt_id=%s loss_reason=%s "
                "fence_reason=%s event_count=%s",
                request.session_id,
                request.run_id,
                attempt_id,
                loss_reason.value,
                fence_exc.reason.value,
                event_count,
            )
            # 仍需关闭 lease_exit_stack 让 renew loop / supervisor
            # session 干净退出; CAS miss 不影响后续 cleanup 顺序。
            await active_attempt.lease_exit_stack.aclose()
            return False
        # CAS hit: supervisor 已在同事务内推进 attempt 终态并写入
        # terminal_event_position; 这里关闭 lease_exit_stack 让 renew
        # loop / supervisor session 退出, 避免与上层 finally 块的
        # ``_finish_attempt_if_durable`` 二次 close 重复。
        await active_attempt.lease_exit_stack.aclose()
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.attempt_lease_lost_terminal_appended attempt_id=%s "
            "state=%s terminal_event_position=%s",
            link.attempt_id,
            link.terminal_state.value,
            link.event_position.value,
        )
        return True

    async def _compact_or_fail(
        self,
        *,
        request: StartRunRequest,
        current_user_event: RunEvent,
        attempt_index: int,
    ) -> tuple[StartRunRequest, RunInputBuildTrace] | None:
        """执行 Host-owned compact 并返回下一次 attempt 请求与合成 trace。

        :param request: 当前 attempt 请求。
        :param current_user_event: 本 Run 原始用户输入事件。
        :param attempt_index: 当前 attempt 序号。
        :returns: 成功返回 ``(compact 后请求, 合成 RunInputBuildTrace)``；失败
            返回 ``None``。合成 trace 的 ``items`` 为空（compact 路径不再来自
            RunInputBuilder），``total_token_estimate`` 取
            ``completed_data.after_token_estimate``，``total_char_size`` 由
            compact 后消息正文重新累加。
        :raises Exception: append 事件或 compact 失败时透传。
        """

        if attempt_index >= self.context_compact_retry_limit:
            _LOGGER.error(
                "host.run.context_compact_retry_limit_exceeded "
                "session_id=%s run_id=%s attempt_index=%s retry_limit=%s",
                request.session_id,
                request.run_id,
                attempt_index,
                self.context_compact_retry_limit,
            )
            failed_data = self.compact_coordinator.retry_limit_failed(
                request=request,
                attempt_index=attempt_index,
            )
            await self._scope_appender().append(
                context_compact_failed_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    data=failed_data,
                )
            )
            await self._scope_appender().append(
                host_context_compact_failure_terminal_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    reason=failed_data.reason,
                    message=failed_data.message,
                )
            )
            return None
        snapshot = await self.memory_store.get_snapshot(request.session_id)
        current_run_events = await self.event_store.list_events(
            run_id=request.run_id,
            after=None,
        )
        snapshot = snapshot_with_transient_tool_facts(
            snapshot=snapshot,
            events=current_run_events,
        )
        if request.run_id not in self.last_run_input_build_trace_by_run:
            _LOGGER.error(
                "host.run.context_compact_trace_missing session_id=%s "
                "run_id=%s attempt_index=%s",
                request.session_id,
                request.run_id,
                attempt_index,
            )
            failed_data = self.compact_coordinator.exception_failed(
                request=request,
                attempt_index=attempt_index,
                reason=ContextCompactFailureReason.TRACE_MISSING,
                message=_COMPACT_TRACE_MISSING_MESSAGE,
            )
            await self._scope_appender().append(
                context_compact_failed_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    data=failed_data,
                )
            )
            await self._scope_appender().append(
                host_context_compact_failure_terminal_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    reason=failed_data.reason,
                    message=failed_data.message,
                )
            )
            return None
        decision = self.compact_coordinator.compact(
            request=request,
            snapshot=snapshot,
            current_user_event=current_user_event,
            attempt_index=attempt_index,
        )
        await self._scope_appender().append(
            context_compact_requested_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=decision.requested_data,
            )
        )
        if decision.status is ContextCompactDecisionStatus.FAILED:
            failed_data = decision.failed_data
            if failed_data is None:
                raise RuntimeError("context compact failed without failed_data")
            _LOGGER.error(
                "host.run.context_compact_decision_failed session_id=%s "
                "run_id=%s attempt_index=%s reason=%s before_tokens=%s "
                "after_tokens=%s",
                request.session_id,
                request.run_id,
                attempt_index,
                failed_data.reason.value,
                failed_data.before_token_estimate,
                failed_data.after_token_estimate,
            )
            await self._scope_appender().append(
                context_compact_failed_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    data=failed_data,
                )
            )
            await self._scope_appender().append(
                host_context_compact_failure_terminal_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    reason=failed_data.reason,
                    message=failed_data.message,
                )
            )
            return None
        completed_data = decision.completed_data
        compacted_input = decision.run_input
        if completed_data is None or compacted_input is None:
            raise RuntimeError("context compact completed without run_input")
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.context_compact_completed session_id=%s run_id=%s "
            "attempt_index=%s before_tokens=%s after_tokens=%s "
            "dropped_item_count=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            completed_data.before_token_estimate,
            completed_data.after_token_estimate,
            completed_data.dropped_item_count,
        )
        await self._scope_appender().append(
            context_compact_completed_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=completed_data,
            )
        )
        next_attempt_index = attempt_index + 1
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.attempt_retrying session_id=%s run_id=%s "
            "from_attempt_index=%s next_attempt_index=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            next_attempt_index,
        )
        await self._scope_appender().append(
            context_attempt_retrying_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=HostContextAttemptRetryData(
                    from_attempt_index=attempt_index,
                    next_attempt_index=next_attempt_index,
                    policy_id=completed_data.policy_id,
                    reason="context_overflow_compacted",
                ),
            )
        )
        return replace(request, input=compacted_input), _synthesize_compact_trace(
            request=request,
            compacted_input=compacted_input,
            after_token_estimate=completed_data.after_token_estimate,
        )

    async def _append_overflow_acquire_failure_terminal(
        self,
        *,
        request: StartRunRequest,
        active_attempt: "_ActiveAttempt | None",
        attempt_index: int,
        new_attempt_index: int,
        error: Exception,
    ) -> bool:
        """context overflow retry 路径下, 新 attempt acquire 失败时的 terminal 收口。

        语义: compact 已成功产出新 ``RunInputBuildTrace``, 但取得新
        attempt owner CAS 失败 (:class:`AttemptFencingError` / SQLite
        IntegrityError 等)。此时 *旧* attempt 的 owner 仍然有效, 必须沿
        旧 attempt 的 owner-scoped 路径写入 Host-owned ``RUN_FAILED``
        terminal RunEvent, 让 RunStream 正常收口、RunResult 可推导;
        本方法**绝不**走裸 ``event_store.append``, 也不引入 unscoped
        Host failure append。

        - ``_can_atomic_terminal_close=True`` (durable + supervisor):
          调用 :meth:`_append_terminal_and_close`, 在单一事务内完成
          ``verify_owner`` + terminal RunEvent append + 旧 attempt 终态
          ``close`` (含 ``terminal_event_position``); ``lease_exit_stack``
          也会在事务成功后关闭, 上层 finally 不再重复 close。
        - 非 supervisor 路径 (legacy + ``is_durable=False``): 通过
          :meth:`_resolve_attempt_appender` 取出当前 attempt 的 fencing-
          aware appender (legacy non-durable 退化为
          :class:`PlainRunEventAppender`) 写入 terminal RunEvent, 再由
          上层 finally 经 :meth:`_finish_attempt_if_durable` 推进
          ``host_attempts`` 终态。

        :param request: 旧 attempt 请求 (acquire 失败时新 attempt 已经无
            owner, 必须用旧 attempt 的 session/run 标识)。
        :param active_attempt: 旧 attempt 句柄, 必须仍持有有效 owner。
        :param attempt_index: 旧 attempt 序号 (诊断字段)。
        :param new_attempt_index: 计划中的新 attempt 序号 (诊断字段)。
        :param error: acquire 失败的根因异常。
        :returns: 已写入 terminal 时返回 ``True``。
        :raises Exception: terminal 写入或 supervisor close 失败时透传。
        """

        _LOGGER.error(
            "host.run.context_overflow_retry_acquire_failed "
            "session_id=%s run_id=%s old_attempt_index=%s "
            "new_attempt_index=%s exc_type=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            new_attempt_index,
            type(error).__name__,
            exc_info=(type(error), error, error.__traceback__),
        )
        draft = host_failure_draft(
            run_id=request.run_id,
            session_id=request.session_id,
            occurred_at=datetime.now(tz=timezone.utc),
            error=RuntimeError(_ERROR_CONTEXT_OVERFLOW_RETRY_ACQUIRE_FAILED),
            error_code=_ERROR_CONTEXT_OVERFLOW_RETRY_ACQUIRE_FAILED,
        )
        if active_attempt is not None and self._can_atomic_terminal_close(
            active_attempt
        ):
            stored_event = await self._append_terminal_and_close(
                active_attempt=active_attempt,
                draft=draft,
            )
            return terminal_result_from_event(stored_event) is not None
        appender = self._resolve_attempt_appender(active_attempt)
        stored_event = await appender.append(draft)
        return terminal_result_from_event(stored_event) is not None

    async def _append_compact_exception_failure(
        self,
        *,
        request: StartRunRequest,
        attempt_index: int,
        error: Exception,
    ) -> bool:
        """将 compact 分支异常收口为 Host-owned 失败终态。

        :param request: 当前 attempt 请求。
        :param attempt_index: 当前 attempt 序号。
        :param error: compact 分支抛出的异常。
        :returns: 已追加终态时返回 ``True``。
        :raises Exception: append 失败时透传。
        """

        _LOGGER.error(
            "host.run.context_compact_failed session_id=%s run_id=%s "
            "attempt_index=%s exc_type=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            type(error).__name__,
            exc_info=(type(error), error, error.__traceback__),
        )
        failed_data = self.compact_coordinator.exception_failed(
            request=request,
            attempt_index=attempt_index,
            reason=ContextCompactFailureReason.INTERNAL_ERROR,
            message=str(error),
        )
        await self._scope_appender().append(
            context_compact_failed_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=failed_data,
            )
        )
        stored_event = await self._scope_appender().append(
            host_context_compact_failure_terminal_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                reason=failed_data.reason,
                message=failed_data.message,
            )
        )
        return terminal_result_from_event(stored_event) is not None

    async def _append_overflow_observed(
        self,
        *,
        request: StartRunRequest,
        event: EngineEvent,
        attempt_index: int,
    ) -> None:
        """追加 Host-owned overflow observed 事实。

        :param request: 当前 attempt 请求。
        :param event: Engine overflow 触发事件；可以是 terminal
            ``RUN_FAILED(context_compaction_required)``，也可以是非 terminal
            ``CONTEXT_COMPACTION_REQUESTED``。
        :param attempt_index: 当前 attempt 序号。
        :returns: 无返回值。
        :raises Exception: append 失败时透传。
        """

        data = event.data
        engine_error_code: str | None = None
        recoverable = False
        reason = "engine_context_compaction_required"
        if isinstance(data, RunFailedData):
            engine_error_code = data.error_code
            recoverable = data.recoverable
            reason = data.message
        if isinstance(data, ContextCompactionRequestedData):
            recoverable = True
            reason = data.reason
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.context_overflow_observed session_id=%s run_id=%s "
            "attempt_index=%s engine_event_type=%s engine_error_code=%s "
            "recoverable=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            event.type.value,
            engine_error_code,
            recoverable,
        )
        await self._scope_appender().append(
            context_overflow_observed_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=HostContextOverflowObservedData(
                    attempt_index=attempt_index,
                    engine_event_type=event.type.value,
                    engine_error_code=engine_error_code,
                    recoverable=recoverable,
                    reason=reason,
                ),
            )
        )

    async def _append_unexpected_compaction_terminal_closure(
        self,
        *,
        request: StartRunRequest,
        event: EngineEvent,
        attempt_index: int,
    ) -> None:
        """闭合 Engine context compaction requested 后的意外终态序列。

        Engine 契约要求 ``CONTEXT_COMPACTION_REQUESTED`` 后跟
        recoverable ``RUN_FAILED(context_compaction_required)``。若 Engine
        产出其它终态，Host 先追加 Host-owned ``CONTEXT_COMPACT_FAILED``
        事实闭合 compact 序列，再保留 Engine 原终态作为本 Run 终态。

        :param request: 当前 attempt 请求。
        :param event: Engine 意外终态事件。
        :param attempt_index: 当前 attempt 序号。
        :returns: 无返回值。
        :raises Exception: append 失败时透传。
        """

        _LOGGER.warning(
            "host.run.context_compact_unexpected_terminal "
            "session_id=%s run_id=%s attempt_index=%s engine_event_type=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            event.type.value,
        )
        failed_data = self.compact_coordinator.exception_failed(
            request=request,
            attempt_index=attempt_index,
            reason=ContextCompactFailureReason.INTERNAL_ERROR,
            message=_UNEXPECTED_COMPACTION_TERMINAL_MESSAGE,
        )
        await self._scope_appender().append(
            context_compact_failed_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=failed_data,
            )
        )

    async def _append_worker_failure_if_needed(
        self,
        *,
        request: StartRunRequest,
        error: Exception,
        event_count: int,
        terminal_seen: bool,
    ) -> bool:
        """按 worker / proxy 异常追加 Host-owned failure。

        本 helper 只应从 worker / proxy 取事件边界调用；Host 自身翻译、
        append 或终态推导错误不得进入该路径。

        :param request: start_run 请求。
        :param error: worker / proxy 抛出的异常。
        :param event_count: 已成功取得的 EngineEvent 数量。
        :param terminal_seen: 是否已经从已 append 事件推导出终态。
        :returns: 已存在或新追加终态时返回 ``True``。
        :raises Exception: append Host-owned failure 失败时透传。
        """

        _LOGGER.error(
            "host.run.background_failed session_id=%s run_id=%s "
            "event_count=%s exc_type=%s",
            request.session_id,
            request.run_id,
            event_count,
            type(error).__name__,
        )
        if terminal_seen:
            return True
        stored_event = await self._scope_appender().append(
            host_failure_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                error=error,
            )
        )
        return terminal_result_from_event(stored_event) is not None

    async def _append_missing_terminal_failure_if_needed(
        self,
        *,
        request: StartRunRequest,
        event_count: int,
        terminal_seen: bool,
    ) -> bool:
        """Engine stream 正常结束但无终态时追加 Host-owned failure。

        这是 Host 对 Engine 协议缺口的治理收口：正常耗尽事件流却没有
        terminal 时，不能把本轮投影为成功，也不能丢弃已接纳用户输入。

        :param request: start_run 请求。
        :param event_count: 已成功取得的 EngineEvent 数量。
        :param terminal_seen: 是否已经从已 append 事件推导出终态。
        :returns: 已存在或新追加终态时返回 ``True``。
        :raises Exception: append Host-owned failure 失败时透传。
        """

        if terminal_seen:
            return True
        _LOGGER.critical(
            "host.run.engine_stream_ended_without_terminal "
            "session_id=%s run_id=%s event_count=%s",
            request.session_id,
            request.run_id,
            event_count,
        )
        stored_event = await self._scope_appender().append(
            host_failure_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                error=RuntimeError(_ERROR_ENGINE_STREAM_ENDED_WITHOUT_TERMINAL),
                error_code=_ERROR_ENGINE_STREAM_ENDED_WITHOUT_TERMINAL,
            )
        )
        return terminal_result_from_event(stored_event) is not None

    async def _project_terminal_run(self, run_id: str) -> None:
        """terminal 后驱动 read model 投影。

        durable 路径下调用 ``ProjectionCoordinator.drain`` 推进 observer
        checkpoint / required projection（含 memory / timeline / audit）。
        legacy 内存路径（``coordinator is None``）退化为直接读取已落库事件
        并调用 ``memory_store.project_run_events``,以保持 P3-P5
        ``InMemoryRunEventStore`` 测试入口的兼容。

        :param run_id: Run id。
        :returns: 无返回值。
        :raises Exception: 投影失败时透传。
        """

        if self.coordinator is not None:
            await self.coordinator.drain()
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.run.coordinator_drained run_id=%s",
                run_id,
            )
            return
        await self._project_run_events(run_id)

    async def _project_run_events(self, run_id: str) -> None:
        """legacy 内存路径下的 memory 投影 fallback。

        仅在 ``coordinator is None``(P3-P5 ``InMemoryRunEventStore`` 路径)
        被使用。durable 路径已统一走 ``coordinator.drain``,该方法不会被调
        用,保留是为了保证非 durable 装配的 harness 仍能完成最小 read
        model 投影。

        :param run_id: Run id。
        :returns: 无返回值。
        :raises Exception: 读取事件或投影失败时透传。
        """

        events = await self.event_store.list_events(
            run_id=run_id,
            after=None,
        )
        await self.memory_store.project_run_events(events)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.memory_projected run_id=%s event_count=%s",
            run_id,
            len(events),
        )

    async def _begin_attempt_if_durable(
        self,
        *,
        request: StartRunRequest,
        attempt_index: int,
    ) -> "_ActiveAttempt | None":
        """durable 路径下创建 attempt 最小记录并返回 active attempt 句柄。

        当 :class:`AttemptSupervisor` 已注入时, harness 不再直接写
        ``host_attempts``, 而是薄委托 :meth:`AttemptSupervisor.lease_context`:
        supervisor 在事务内 acquire owner、分配全局单调 fencing token、写入
        ``host_attempts`` ``state='running'``、启动 renew heartbeat。本方
        法只持有 :class:`AsyncExitStack` 来跟踪 lease context 的退出, 不
        计算 TTL、不写 lease SQL、不感知 owner secret token。

        legacy 路径(P6 兼容): 仅有 ``attempt_state_store`` 而无 supervisor
        时, 保持原 ``CREATED -> RUNNING`` 行为, 等待后续 slice 收口。

        legacy 内存路径(无 ``attempt_state_store``)直接返回 ``None``。

        :param request: 当前 attempt 的 start 请求。
        :param attempt_index: 同一 run 内 attempt 序号。
        :returns: :class:`_ActiveAttempt` 句柄; 非 durable 路径返回
            ``None``。
        :raises AttemptFencingError: supervisor acquire 命中非 ACQUIRED
            决策时透传(P8-S3 主路径首个 attempt 不应出现, 由 P8-S6
            recovery 路径处理)。
        :raises Exception: 其它写入失败时透传。
        """

        if self.attempt_supervisor is not None:
            stack = AsyncExitStack()
            owner_context = await stack.enter_async_context(
                self.attempt_supervisor.lease_context(
                    run_id=request.run_id,
                    attempt_index=attempt_index,
                    recovered_from_attempt_id=None,
                )
            )
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.run.attempt_lease_acquired run_id=%s attempt_id=%s "
                "attempt_index=%s owner_id=%s owner_token=%s "
                "fencing_token=%s",
                request.run_id,
                owner_context.attempt_id,
                attempt_index,
                owner_context.owner_id,
                owner_context.owner_token.masked(),
                owner_context.fencing_token.value,
            )
            return _ActiveAttempt(
                attempt_id=owner_context.attempt_id,
                owner_context=owner_context,
                lease_exit_stack=stack,
            )
        if self.attempt_state_store is None or self.storage is None:
            return None
        attempt_id = (
            f"attempt-{request.run_id}-{attempt_index}-{uuid.uuid4().hex[:8]}"
        )
        async with self.storage.transaction() as tx:
            self.attempt_state_store.create(
                tx=tx,
                attempt_id=attempt_id,
                run_id=request.run_id,
                attempt_index=attempt_index,
            )
            self.attempt_state_store.update_state(
                tx=tx,
                attempt_id=attempt_id,
                state=AttemptState.RUNNING,
            )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.attempt_created run_id=%s attempt_id=%s "
            "attempt_index=%s",
            request.run_id,
            attempt_id,
            attempt_index,
        )
        return _ActiveAttempt(
            attempt_id=attempt_id,
            owner_context=None,
            lease_exit_stack=None,
        )

    def _can_atomic_terminal_close(
        self,
        active_attempt: "_ActiveAttempt | None",
    ) -> bool:
        """判断是否走 P8-S4 supervisor 同事务原子 terminal append + close。

        条件: 当前 attempt 由 supervisor 接管 (持有 owner_context 与
        lease_exit_stack), 且 supervisor 已注入。否则回退到 P6 legacy
        路径: 先 ``event_store.append()`` 再 ``_finish_attempt_if_durable``。

        :param active_attempt: 当前 attempt 句柄;为 ``None`` 表示无
            durable attempt。
        :returns: 走原子路径返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            active_attempt is not None
            and active_attempt.owner_context is not None
            and active_attempt.lease_exit_stack is not None
            and self.attempt_supervisor is not None
        )

    async def _append_terminal_and_close(
        self,
        *,
        active_attempt: "_ActiveAttempt",
        draft: RunEventDraft,
    ) -> RunEvent:
        """走 P8-S4 supervisor API: 单事务 terminal append + attempt close。

        通过 :meth:`AttemptSupervisor.append_terminal_and_close` 在同一
        ``BEGIN IMMEDIATE`` 事务内完成 ``verify_owner`` ->
        terminal RunEvent append -> attempt 终态 close (含
        ``terminal_event_position`` 写入)。任意 owner CAS 命中失败抛
        :class:`AttemptFencingError`, 整事务回滚, EventLog 不残留 stale
        terminal RunEvent。

        本方法在原子写入成功后立即关闭 ``lease_exit_stack``, 避免与
        ``_finish_attempt_if_durable`` 二次 close 重复; supervisor 内部
        ``_sessions`` 也在 lease_context 退出时被清理。

        :param active_attempt: 当前 attempt 句柄, 必须持有 owner_context
            与 lease_exit_stack。
        :param draft: terminal RunEvent 草稿; type 必须是 terminal。
        :returns: 已落库的 terminal :class:`RunEvent`。
        :raises AttemptFencingError: owner CAS 命中失败时由 supervisor 抛
            出, 整事务回滚。
        :raises Exception: 其它写入失败透传。
        """

        supervisor = self.attempt_supervisor
        owner_context = active_attempt.owner_context
        lease_exit_stack = active_attempt.lease_exit_stack
        if (
            supervisor is None
            or owner_context is None
            or lease_exit_stack is None
        ):
            # _can_atomic_terminal_close 已经守住, 此分支只是 type narrowing
            # 兜底。
            raise RuntimeError(
                "atomic terminal close requires supervisor + owner_context + "
                "lease_exit_stack"
            )
        terminal_state = attempt_state_from_terminal_event_type(draft.type)
        failure_summary = (
            draft.type.value
            if terminal_state in (
                AttemptState.FAILED,
                AttemptState.CANCELLED,
                AttemptState.SUSPENDED,
            )
            else None
        )
        link = await supervisor.append_terminal_and_close(
            owner_context=owner_context,
            draft=draft,
            failure_summary=failure_summary,
        )
        await lease_exit_stack.aclose()
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.attempt_finished attempt_id=%s state=%s "
            "terminal_event_position=%s",
            active_attempt.attempt_id,
            link.terminal_state.value,
            link.event_position.value,
        )
        # supervisor 在同一 ``BEGIN IMMEDIATE`` 事务内已经 append 了
        # terminal RunEvent, 并通过 ``AttemptTerminalLink.event`` 把构造
        # 出的 :class:`RunEvent` 直接交给 caller; 这里直接复用, 不再做
        # 事务提交后的 ``list_events`` round-trip, 也不依赖 "append 后立
        # 即可查" 的隐含不变量。
        return link.event

    async def _finish_attempt_if_durable(
        self,
        *,
        active_attempt: "_ActiveAttempt | None",
        terminal_event: RunEvent | None,
        state: AttemptState | None = None,
        failure_summary: str | None = None,
    ) -> None:
        """durable 路径下推进 attempt 终态 / 诊断态。

        supervisor 路径(``is_durable=True`` 必经):

        - 通过 :meth:`AttemptSupervisor.close_attempt_with_diagnostic_state`
          在同事务内对 ``host_attempts`` 做 owner_token + fencing_token CAS
          更新; CAS 命中失败说明 owner 已被 recovery 替换, harness 直接放弃
          覆盖未来状态。
        - 然后才调用 :meth:`AsyncExitStack.aclose` 让
          :meth:`AttemptSupervisor.lease_context` 退出 (取消 renew loop /
          清理 supervisor 内部 session)。这样可以保证 CAS 在 supervisor
          仍持有 session 时执行, 避免 "先丢弃 session 再写库" 的窗口。

        ``is_durable=False`` 路径下 attempt 概念不存在, 函数 noop。
        ``is_durable=True`` 但 supervisor / owner_context / lease_exit_stack
        缺失视为装配 invariant 被破坏, 直接 raise 而不是退化到非 owner-aware
        update; 避免与 recovery 真源在 ``host_attempts`` 上竞争产生 stale
        state(P8 D5)。

        :param active_attempt: 当前 active attempt 句柄；``None`` 表示无
            durable attempt 可推进, 直接返回。
        :param terminal_event: 关联的 terminal RunEvent；提供时由事件类型
            推导默认 attempt state。
        :param state: 显式 attempt state；与 ``terminal_event`` 二选一。
        :param failure_summary: 失败摘要;成功终态可为 ``None``。
        :returns: 无返回值。
        :raises ValueError: 同时显式提供 ``terminal_event`` 与 ``state`` 时
            抛出；二者语义互斥，调用方必须明确意图，禁止隐式优先级。
        :raises RuntimeError: ``is_durable=True`` 但 supervisor / owner_context
            / lease_exit_stack 缺失。
        :raises Exception: 写入失败时透传。
        """

        if terminal_event is not None and state is not None:
            raise ValueError(
                "_finish_attempt_if_durable 不允许同时传入 terminal_event "
                "与 state；二者互斥，调用方需明确终态来源。"
            )
        if active_attempt is None:
            return
        resolved_state = state
        resolved_failure = failure_summary
        if terminal_event is not None:
            resolved_state = attempt_state_from_terminal_event_type(
                terminal_event.type
            )
            if resolved_state in (
                AttemptState.FAILED,
                AttemptState.CANCELLED,
                AttemptState.SUSPENDED,
            ) and resolved_failure is None:
                resolved_failure = terminal_event.type.value
        if resolved_state is None:
            resolved_state = AttemptState.FAILED
        if (
            self.attempt_supervisor is not None
            and active_attempt.owner_context is not None
            and active_attempt.lease_exit_stack is not None
        ):
            # owner-aware diagnostic close: 必须在 lease_context 退出前
            # 完成 CAS 写入, 否则 session 被移除后 verify_owner / 后续
            # owner-lost signal 都会立即视为已失活。terminal event
            # position 的同事务原子写入归 P8-S4。
            await self.attempt_supervisor.close_attempt_with_diagnostic_state(
                owner_context=active_attempt.owner_context,
                state=resolved_state,
                failure_summary=resolved_failure,
                terminal_event_position=None,
            )
            await active_attempt.lease_exit_stack.aclose()
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.run.attempt_finished attempt_id=%s state=%s",
                active_attempt.attempt_id,
                resolved_state.value,
            )
            return
        if not self.is_durable:
            # 非 durable 路径下 attempt 概念不存在, noop。
            return
        # is_durable=True 必须始终携带 supervisor + owner_context;
        # 进入此分支说明上游装配或 attempt 生命周期出错, 立即 fail-fast,
        # 避免退化到非 owner-aware update 制造 stale state。
        raise RuntimeError(
            "_finish_attempt_if_durable invariant violated: "
            "is_durable=True 但 attempt_supervisor / owner_context / "
            f"lease_exit_stack 缺失 attempt_id={active_attempt.attempt_id}"
        )

    def _remember_run_input_build_trace(
        self,
        *,
        run_id: str,
        trace: RunInputBuildTrace,
    ) -> None:
        """记录最近 RunInput 构造 trace，并按 FIFO 淘汰旧 run。

        :param run_id: Run id。
        :param trace: RunInput 构造 trace。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        _remember_lru_run_cache_item(
            cache=self.last_run_input_build_trace_by_run,
            run_id=run_id,
            value=trace,
            limit=self.run_input_trace_cache_limit,
        )

    def _remember_run_input_messages(
        self,
        *,
        run_id: str,
        messages: tuple[AgentMessage, ...],
    ) -> None:
        """记录最近 RunInput 消息，用于 P5 内部 smoke 观察。

        该缓存是 Host internal-only 诊断材料，不进入 public API，不作为
        memory 真源；事实真源仍是 EventLog 与 memory projection。

        :param run_id: Run id。
        :param messages: 已交给 Engine 的 RunInput 消息。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        _remember_lru_run_cache_item(
            cache=self.last_run_input_messages_by_run,
            run_id=run_id,
            value=messages,
            limit=self.run_input_message_cache_limit,
        )

    async def _append_run_input_context_snapshot_fact(
        self,
        *,
        request: StartRunRequest,
        build_trace: RunInputBuildTrace,
        current_user_event: RunEvent,
        attempt_index: int,
        iteration_index: int,
        iteration_id: str,
        active_attempt: "_ActiveAttempt | None" = None,
    ) -> None:
        """同事务追加 ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` canonical fact。

        非 durable 路径（``event_store`` 不是 :class:`DurableRunEventStore`
        或 ``storage is None``）以及 ``tool_trace_context_fact_enabled`` 未开
        启时直接 no-op，保持 P6 行为不变。

        当 ``active_attempt`` 非 ``None`` 且 supervisor 路径生效时, 改走
        :class:`AttemptScopedRunEventAppender.append_in_transaction`,
        在同 ``BEGIN IMMEDIATE`` 内执行 ``verify_owner`` + EventLog
        append; 其它路径退化为 :meth:`DurableRunEventStore.append_in_transaction`,
        与 P6 行为一致 (start_run 阶段尚未开 attempt, 不参与 fencing)。

        :param request: 当前 attempt 的 start 请求；其 ``input.messages`` 为
            实际交给 Engine 的消息序列。
        :param build_trace: RunInputBuilder 产出的 trace；compact 路径下由
            调用方合成。
        :param current_user_event: 本 Run 原始用户输入事件。
        :param attempt_index: 当前 attempt 序号。
        :param iteration_index: 即将启动的 iteration 序号；attempt 启动前固
            定为 0。
        :param iteration_id: 占位 iteration_id（见
            :func:`_iteration_id_for_attempt`）。
        :param active_attempt: 当前 active attempt; 非 ``None`` 时启用 owner
            fencing。
        :returns: 无返回值。
        :raises ValueError: 启用 fact 但未注入 builder 时抛出。
        :raises AttemptFencingError: scoped 路径下 owner CAS 失败。
        :raises Exception: 同事务 append 失败时透传。
        """

        if not self.tool_trace_context_fact_enabled:
            return
        if not isinstance(self.event_store, DurableRunEventStore):
            return
        if self.storage is None:
            return
        if self.run_input_context_fact_builder is None:
            raise ValueError(_RUN_INPUT_CONTEXT_FACT_BUILDER_REQUIRED)
        data = self.run_input_context_fact_builder.build(
            run_input=request.input,
            build_trace=build_trace,
            current_user_event=current_user_event,
            tool_schemas=request.options.tool_schemas,
            attempt_index=attempt_index,
            iteration_index=iteration_index,
            iteration_id=iteration_id,
        )
        draft = RunEventDraft(
            run_id=request.run_id,
            session_id=request.session_id,
            kind=RunEventKind.CANONICAL,
            source=RunEventSource.HOST,
            type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
            occurred_at=datetime.now(tz=timezone.utc),
            data=data,
            source_engine_event_id=None,
        )
        scoped = (
            self.attempt_supervisor.scoped_appender(active_attempt.owner_context)
            if (
                self.attempt_supervisor is not None
                and active_attempt is not None
                and active_attempt.owner_context is not None
            )
            else None
        )
        async with self.storage.transaction() as tx:
            if scoped is not None:
                scoped.append_in_transaction(tx=tx, draft=draft)
            else:
                self.event_store.append_in_transaction(tx=tx, draft=draft)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.run.run_input_context_snapshot_built run_id=%s "
            "attempt_index=%s iteration_id=%s message_count=%s",
            request.run_id,
            attempt_index,
            iteration_id,
            len(request.input.messages),
        )

    def stream_run_events(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncIterator[RunEvent]:
        """订阅某个 run 的 RunEvent 流。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时从头订阅。
        :returns: RunEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        return self.event_store.subscribe(run_id=run_id, after=after)

    async def get_run_result(self, run_id: str) -> RunResult | None:
        """从已 append 的 terminal RunEvent 推导 RunResult 快照。

        :param run_id: Run id。
        :returns: 已终态时返回 RunResult，否则返回 ``None``。
        :raises TypeError: 终态事件类型与 data 类型不一致时抛出。
        """

        events = await self.event_store.list_events(run_id=run_id, after=None)
        for event in reversed(events):
            result = terminal_result_from_event(event)
            if result is not None:
                return result
        return None


def _remember_lru_run_cache_item(
    *,
    cache: OrderedDict[str, _RunCacheValue],
    run_id: str,
    value: _RunCacheValue,
    limit: int,
) -> None:
    """记录 Run 级调试缓存项，并按插入顺序淘汰最旧项。

    :param cache: Run id 到缓存值的有序字典。
    :param run_id: Run id。
    :param value: 需要缓存的值。
    :param limit: 最大缓存条数。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if run_id in cache:
        del cache[run_id]
    cache[run_id] = value
    while len(cache) > limit:
        cache.popitem(last=False)


async def _close_engine_events_if_supported(
    *,
    engine_events: AsyncIterator[EngineEvent],
    request: StartRunRequest,
) -> None:
    """在提前停止消费时关闭 worker stream。

    ``WorkerProxy`` 的稳定契约只承诺返回 ``AsyncIterator``；本 helper 通过
    运行时协议识别 async generator 等支持 ``aclose`` 的实现，避免 harness
    在首个终态后停止消费时泄漏底层 runner close 流程。关闭失败只记录诊断
    日志，不覆盖原始异常，也不生成 Host-owned failure 事实事件。

    :param engine_events: worker 返回的 EngineEvent 异步流。
    :param request: start_run 请求，用于输出诊断上下文。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(engine_events, _ClosableAsyncIterator):
        try:
            await engine_events.aclose()
        except Exception as exc:
            _LOGGER.warning(
                "host.run.stream_close_failed session_id=%s run_id=%s "
                "exc_type=%s",
                request.session_id,
                request.run_id,
                type(exc).__name__,
                exc_info=(type(exc), exc, exc.__traceback__),
            )


def _log_background_task_failure(
    request: StartRunRequest,
    task: asyncio.Future[None],
) -> None:
    """取回后台 task 异常并记录 ERROR 日志。

    该回调只负责诊断可观测性，不把 Host 内部错误转换为 Host-owned
    failure，也不引入完整 Run supervisor / governance。

    :param request: start_run 请求。
    :param task: 已完成的后台 Future。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    try:
        error = task.exception()
    except asyncio.CancelledError:
        return
    if error is None:
        return
    _LOGGER.error(
        "host.run.background_task_failed session_id=%s run_id=%s "
        "exc_type=%s",
        request.session_id,
        request.run_id,
        type(error).__name__,
        exc_info=(type(error), error, error.__traceback__),
    )


def _extract_accepted_start_input(*, request: StartRunRequest) -> _AcceptedStartInput:
    """从入口 RunInput 中提取 caller system prompt 与当前用户输入。

    该函数只位于 ingress 边界，用于在 Engine 启动前写入 Host-owned
    ``USER_INPUT_ACCEPTED``。后续 memory projection、RunInputBuilder 与
    replay 均不得继续从 ``StartRunRequest.input`` 读取用户输入。

    :param request: start_run 请求。
    :returns: 接纳后的当前用户输入和 caller system prompt。
    :raises ValueError: 请求不是若干 leading SystemMessage 加一条非空
        UserMessage 时抛出。
    """

    messages = request.input.messages
    if not messages:
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SHAPE_EMPTY)
    trailing_message = messages[-1]
    if not isinstance(trailing_message, UserMessage):
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SHAPE_TRAILING_USER)
    caller_system_messages: list[SystemMessage] = []
    for message in messages[:-1]:
        if isinstance(message, SystemMessage):
            caller_system_messages.append(message)
            continue
        if isinstance(message, UserMessage):
            raise ValueError(_ERROR_CURRENT_USER_INPUT_SHAPE_MULTIPLE_USER)
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SHAPE_UNSUPPORTED_HISTORY)
    content = trailing_message.content.strip()
    if content == "":
        raise ValueError(_ERROR_CURRENT_USER_INPUT_REQUIRED)
    return _AcceptedStartInput(
        current_user_text=content,
        caller_system_messages=tuple(caller_system_messages),
    )


def _is_terminal_engine_event(event: EngineEvent) -> bool:
    """判断 EngineEvent 是否为 Engine 终态事件。

    :param event: EngineEvent。
    :returns: 是 final / failed / cancelled / suspended 终态时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return event.type in {
        EngineEventType.FINAL_ANSWER,
        EngineEventType.RUN_FAILED,
        EngineEventType.RUN_CANCELLED,
        EngineEventType.RUN_SUSPENDED,
    }


def _is_context_compaction_requested(event: EngineEvent) -> bool:
    """判断 Engine 事件是否为强类型 context compaction requested。

    :param event: EngineEvent。
    :returns: 是 context compaction requested 返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return event.type is EngineEventType.CONTEXT_COMPACTION_REQUESTED and isinstance(
        event.data,
        ContextCompactionRequestedData,
    )


def _is_context_compaction_required_terminal(event: EngineEvent) -> bool:
    """判断 Engine terminal 是否为可 compact 的 context overflow。

    :param event: EngineEvent。
    :returns: 可由 Host compact 接管返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    data = event.data
    return (
        event.type is EngineEventType.RUN_FAILED
        and isinstance(data, RunFailedData)
        and data.recoverable
        and data.error_code == _ERROR_CONTEXT_COMPACTION_REQUIRED
    )


__all__ = [
    "LocalRunHarness",
]
