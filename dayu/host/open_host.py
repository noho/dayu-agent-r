"""Host public opener 与 production composition root。

本模块实现普通 Service 使用的 ``open_host(options)`` 入口，负责在 Host
内部装配 durable store、command handle、dispatch scheduler、active
worker registry、memory catch-up 与 compactor baseline。调用方只持有异步
public handle，不接触 scheduler、wakeup port 或 durable internals。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Future
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, TypeVar
from uuid import uuid4

from dayu.host.audit import (
    DEFAULT_LOG_AUDIT_CATCHUP_BATCH_SIZE,
    LogAuditSinkOptions,
    catch_up_log_audit_sink_projection,
    default_log_audit_sink_options,
)
from dayu.host.admission import create_host_admission_service
from dayu.host._durable_actor import DurableActor, open_durable_actor
from dayu.host.api import (
    CancelRunRequest,
    CancelSessionRunsRequest,
    CloseSessionRequest,
    CreateSessionRequest,
    DrainOutboxTerminalItemsRequest,
    EnsureSessionRequest,
    FollowupSnapshot,
    Host,
    HostAdmin,
    HostApiError,
    HostApiErrorCode,
    HostClosedError,
    HostCommandHandleOptions,
    HostEvent,
    HostLocalExecutionOptions,
    HostCallContext,
    ListSessionsResult,
    OperationContext,
    OutboxTerminalItemsBatch,
    OpenHostOptions,
    OpenHostAdminOptions,
    PurgeSessionRequest,
    PurgeSessionResult,
    ReadOutboxTerminalItemsRequest,
    ReplayRunRequest,
    ResolveWaitRequest,
    RetryRunRequest,
    RunSnapshot,
    SessionSnapshot,
    SubmitFollowupRequest,
)
from dayu.host.command import (
    HostCommandHandle,
    cancel_run as _cancel_run,
    cancel_session_runs as _cancel_session_runs,
    close_session as _close_session,
    create_session as _create_session,
    ensure_session as _ensure_session,
    purge_session as _purge_session,
    resolve_wait as _resolve_wait,
    retry_run as _retry_run,
    replay_run as _replay_run,
    submit_followup as _submit_followup,
)
from dayu.host.command import (
    _durable_options_from_public_options as _durable_options_from_command_options,
)
from dayu.host.dispatch import (
    ActiveCancelMessage,
    ActiveWorkerCancelPort,
    ActiveWorkerRegistry,
    HostDispatchScheduler,
    NoActiveWorkerCancelPort,
)
from dayu.host.durable.connection import (
    HostDurableStore,
    open_host_durable_store,
)
from dayu.host.durable.event_log import EventLogStore
from dayu.host.llm_compaction import LLMContextCompactor
from dayu.host.outbox import (
    DEFAULT_OUTBOX_TERMINAL_CATCHUP_BATCH_SIZE,
    catch_up_outbox_terminal_projection,
)
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.read_api import get_run as _get_run
from dayu.host.read_api import get_session as _get_session
from dayu.host.read_api import list_sessions as _list_sessions
from dayu.host.read_api import (
    drain_outbox_terminal_items as _drain_outbox_terminal_items,
)
from dayu.host.read_api import (
    read_outbox_terminal_items as _read_outbox_terminal_items,
)
from dayu.host.read_api import (
    read_session_host_events_after as _read_session_host_events_after,
)
from dayu.host.read_api import (
    session_live_event_start_cursor as _session_live_event_start_cursor,
)
from dayu.host.recovery import StartupRecoveryScanner
from dayu.host.storage_maintenance import (
    HostStorageMaintenanceRequest,
    HostStorageMaintenanceResult,
    HostStorageUsageReport,
    report_storage_usage as _report_storage_usage,
    run_storage_maintenance as _run_storage_maintenance,
)
from dayu.host.tool_trace import (
    DEFAULT_TOOL_TRACE_CATCHUP_BATCH_SIZE,
    ToolTraceSinkOptions,
    catch_up_tool_trace_projection,
)
from dayu.host.wait_adapter import (
    WaitPollAdapterRegistry,
    WaitPollLifecycleGate,
    WaitPollOnceResult,
    WaitPoller,
    WaitPollerFactory,
    WaitPollerRuntimePolicy,
    WaitPollerSupervisor,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

if TYPE_CHECKING:
    from dayu.host.admission import PendingDispatchRecord

T = TypeVar("T")

_GENERATED_OPEN_HOST_ID_PREFIX = "open-host"
_GENERATED_OPEN_HOST_ADMIN_ID_PREFIX = "open-host-admin"
_LOGGER = logging.getLogger(__name__)
_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE = 8192
"""``context_budget_policy=None`` 时内部 command options 使用的兜底窗口。"""

_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS = 1024
"""``context_budget_policy=None`` 时内部 command options 使用的兜底输出预留。"""

_SESSION_WATCH_POLL_INTERVAL_SECONDS = 0.02
"""session live watch 未读取到新事件时的轻量轮询间隔。"""

_TOOL_TRACE_ARTIFACT_DIRECTORY_NAME = "tool-trace"
"""artifact_root 下 Tool Trace artifact 目录名。"""

_TOOL_TRACE_COLD_JSONL_FILE_NAME = "tool-trace-cold.jsonl"
"""默认 Tool Trace cold JSONL 文件名。"""

_TOOL_TRACE_LOCK_FILE_SUFFIX = ".lock"
"""默认 Tool Trace cold JSONL lock 文件名后缀。"""

_WAIT_POLLER_COMMAND_HANDLE_ID_SUFFIX = "wait-poller"
"""open_host wait poller 每轮 command handle id 后缀。"""

_DURABLE_ACTOR_THREAD_NAME_SUFFIX = "durable-actor"
"""public durable actor worker thread 名称后缀。"""

@dataclass(frozen=True, slots=True)
class _CommandContextBudgetFields:
    """内部 command handle context budget 字段组。

    :param context_window_size: command handle 必填 context window token 数。
    :param reserved_output_tokens: command handle 必填输出预留 token 数。
    """

    context_window_size: int
    reserved_output_tokens: int


@dataclass(frozen=True, slots=True)
class _LogAuditProjectionCatchupPort(ProjectionCatchupPort):
    """LogAuditSink projection catch-up 端口。

    :param durable_store: 当前 opener 持有的 durable store。
    :param options: audit sink options。
    :raises: 无。
    """

    durable_store: HostDurableStore
    options: LogAuditSinkOptions

    def catch_up_projection(self) -> None:
        """追平 audit JSONL projection。

        :returns: ``None``。
        :raises HostDurableError: durable projection catch-up 失败时抛出。
        """

        catch_up_log_audit_sink_projection(
            self.durable_store.transaction_runner,
            options=self.options,
            batch_size=DEFAULT_LOG_AUDIT_CATCHUP_BATCH_SIZE,
        )


@dataclass(frozen=True, slots=True)
class _ToolTraceProjectionCatchupPort(ProjectionCatchupPort):
    """Tool Trace projection catch-up 端口。

    :param durable_store: 当前 opener 持有的 durable store。
    :param options: Tool Trace sink options。
    :raises: 无。
    """

    durable_store: HostDurableStore
    options: ToolTraceSinkOptions

    def catch_up_projection(self) -> None:
        """追平 Tool Trace hot / cold projection。

        :returns: ``None``。
        :raises HostDurableError: durable projection catch-up 失败时抛出。
        """

        catch_up_tool_trace_projection(
            self.durable_store.transaction_runner,
            options=self.options,
            batch_size=DEFAULT_TOOL_TRACE_CATCHUP_BATCH_SIZE,
        )


@dataclass(frozen=True, slots=True)
class _OutboxTerminalProjectionCatchupPort(ProjectionCatchupPort):
    """Outbox terminal projection catch-up 端口。

    :param durable_store: 当前 opener 持有的 durable store。
    :raises: 无。
    """

    durable_store: HostDurableStore

    def catch_up_projection(self) -> None:
        """追平 Outbox terminal delivery queue projection。

        :returns: ``None``。
        :raises HostDurableError: durable projection catch-up 失败时抛出。
        """

        catch_up_outbox_terminal_projection(
            self.durable_store.transaction_runner,
            batch_size=DEFAULT_OUTBOX_TERMINAL_CATCHUP_BATCH_SIZE,
        )


@dataclass(frozen=True, slots=True)
class _CompositeProjectionCatchupPort(ProjectionCatchupPort):
    """顺序执行多个 projection catch-up port。

    :param ports: 按顺序执行的 projection catch-up ports。
    :raises: 无。
    """

    ports: tuple[ProjectionCatchupPort, ...]

    def catch_up_projection(self) -> None:
        """顺序追平所有子 projection。

        :returns: ``None``。
        :raises Exception: 任一子 port 发生未处理错误时透传。
        """

        for port in self.ports:
            port.catch_up_projection()


@dataclass(frozen=True, slots=True)
class _ThreadsafeSchedulerWakeupPort:
    """允许 poller thread 同步唤醒 asyncio scheduler 的端口。

    :param loop: ``open_host`` 所属 asyncio event loop。
    :param scheduler: 当前 Host dispatch scheduler。
    """

    loop: asyncio.AbstractEventLoop
    scheduler: HostDispatchScheduler

    def wake_dispatch(self, record: "PendingDispatchRecord") -> None:
        """在线程安全边界唤醒 dispatch。

        :param record: 已持久化的 pending dispatch 摘要。
        :returns: ``None``。
        :raises Exception: scheduler wakeup 失败时透传。
        """

        if _is_current_event_loop(self.loop):
            self.scheduler.wake_dispatch(record)
            return
        self._run_on_loop(lambda: self.scheduler.wake_dispatch(record))

    def wake_queue_promotion(self, session_id: str) -> None:
        """在线程安全边界唤醒 queue promotion。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises Exception: scheduler wakeup 失败时透传。
        """

        if _is_current_event_loop(self.loop):
            self.scheduler.wake_queue_promotion(session_id)
            return
        self._run_on_loop(lambda: self.scheduler.wake_queue_promotion(session_id))

    def wake_active_cancel_watchdog(self) -> None:
        """在线程安全边界唤醒 active cancel watchdog。

        :returns: ``None``。
        :raises Exception: scheduler wakeup 失败时透传。
        """

        if _is_current_event_loop(self.loop):
            self.scheduler.wake_active_cancel_watchdog()
            return
        self._run_on_loop(self.scheduler.wake_active_cancel_watchdog)

    def _run_on_loop(self, callback: Callable[[], None]) -> None:
        """在 opener event loop 上同步执行 callback。

        :param callback: 要在 event loop thread 执行的回调。
        :returns: ``None``。
        :raises Exception: callback 抛出的异常。
        """

        _run_callback_on_event_loop(self.loop, callback)


@dataclass(frozen=True, slots=True)
class _ThreadsafeActiveWorkerCancelPort(ActiveWorkerCancelPort):
    """把 actor thread 的 active worker cancel 桥接回 opener loop。

    :param loop: ``open_host`` 所属 asyncio event loop。
    :param active_registry: opener loop 拥有的 active worker registry。
    """

    loop: asyncio.AbstractEventLoop
    active_registry: ActiveWorkerRegistry

    def cancel(self, message: ActiveCancelMessage) -> bool:
        """在 opener loop 上传播 active worker cancel。

        :param message: durable commit 后的 active cancel 消息。
        :returns: 找到匹配 active worker 时返回 ``True``。
        :raises Exception: bridge 或 registry callback 失败时透传。
        """

        if _is_current_event_loop(self.loop):
            return self.active_registry.cancel(message)
        return _run_callback_on_event_loop(
            self.loop,
            lambda: self.active_registry.cancel(message),
        )


def _run_callback_on_event_loop(
    loop: asyncio.AbstractEventLoop,
    callback: Callable[[], T],
) -> T:
    """从非 loop thread 同步执行 opener-loop callback。

    :param loop: opener event loop。
    :param callback: 只允许在该 loop thread 执行的 typed callback。
    :returns: callback 返回值。
    :raises Exception: callback 异常原样返回发起线程。
    """

    future: Future[T] = Future()
    loop.call_soon_threadsafe(_complete_event_loop_callback, callback, future)
    return future.result()


def _complete_event_loop_callback(
    callback: Callable[[], T],
    future: Future[T],
) -> None:
    """在 opener loop 执行 callback 并完成跨线程 future。

    :param callback: 待执行 typed callback。
    :param future: 向 actor thread 回传结果的 future。
    :returns: ``None``。
    :raises Exception: callback 异常写入 future，不向 event loop 泄漏。
    """

    try:
        result = callback()
    except Exception as exc:
        future.set_exception(exc)
    else:
        future.set_result(result)


class _CommandHandleWaitResolver:
    """通过 Host command handle 调用 ``resolve_wait`` 的 poller resolver。"""

    def __init__(self, command_handle: HostCommandHandle) -> None:
        """初始化 resolver。

        :param command_handle: 当前 poll round 私有 command handle。
        :returns: ``None``。
        """

        self._command_handle = command_handle

    def resolve_wait(self, wait_id: str, request: ResolveWaitRequest) -> RunSnapshot:
        """转发 wait result 到 command path。

        :param wait_id: wait id。
        :param request: resolve wait request。
        :returns: 最新 Run snapshot。
        """

        return _resolve_wait(self._command_handle, wait_id, request)


class _ClosingWaitPoller(WaitPoller):
    """poll_once 后关闭当前 poll round 私有 command handle。"""

    def __init__(self, *, command_handle: HostCommandHandle, poller: WaitPoller) -> None:
        """初始化 wrapper。

        :param command_handle: 当前 poll round 私有 command handle。
        :param poller: 实际 wait poller。
        :returns: ``None``。
        """

        self._command_handle = command_handle
        self._poller = poller

    def poll_once(self) -> WaitPollOnceResult:
        """执行单轮 poll 并释放当前 poll round durable connection。

        :returns: 单轮 poll result。
        """

        try:
            return self._poller.poll_once()
        finally:
            self._command_handle.close()


@dataclass(frozen=True, slots=True)
class _OpenHostWaitPollerFactory(WaitPollerFactory):
    """为 open_host supervisor 创建线程内可用 wait poller 的 factory。

    :param command_options: 派生自 opener options 的 command handle options。
    :param adapter_registry: production poll adapter registry。
    :param active_cancel_port: 当前 open_host active worker cancel bridge。
    :param wakeup_port: 线程安全 scheduler wakeup port。
    :param policy: wait poller runtime policy。
    :param owner_id: poller owner id。
    """

    command_options: HostCommandHandleOptions
    adapter_registry: WaitPollAdapterRegistry
    active_cancel_port: ActiveWorkerCancelPort
    wakeup_port: _ThreadsafeSchedulerWakeupPort
    policy: WaitPollerRuntimePolicy
    owner_id: str

    def create_wait_poller(self, lifecycle_gate: WaitPollLifecycleGate) -> WaitPoller:
        """在调用线程内打开独立 durable store 并创建 wait poller。

        :param lifecycle_gate: supervisor close gate。
        :returns: 单轮 poller wrapper。
        :raises Exception: durable store 或 poller 构造失败时透传。
        """

        durable_store = open_host_durable_store(
            _durable_options_from_command_options(self.command_options)
        )
        try:
            admission_service = create_host_admission_service(
                durable_store.transaction_runner,
                wakeup_port=self.wakeup_port,
            )
            command_handle = HostCommandHandle(
                host_handle_id=self.owner_id,
                durable_store=durable_store,
                admission_service=admission_service,
                active_registry=self.active_cancel_port,
            )
            poller = WaitPoller(
                transaction_runner=command_handle._transaction_runner(),
                adapter_registry=self.adapter_registry,
                resolver=_CommandHandleWaitResolver(command_handle),
                context=_wait_poller_call_context(self.owner_id),
                policy=self.policy,
                lifecycle_gate=lifecycle_gate,
                owner_id=self.owner_id,
            )
            return _ClosingWaitPoller(command_handle=command_handle, poller=poller)
        except Exception:
            durable_store.close()
            raise


@dataclass(frozen=True, slots=True)
class _EnabledWaitPollerConfiguration:
    """已启用 wait poller 的 construction 配置。

    :param policy: wait poller runtime policy。
    :param adapter_registry: production poll adapter registry。
    """

    policy: WaitPollerRuntimePolicy
    adapter_registry: WaitPollAdapterRegistry


@dataclass(frozen=True, slots=True)
class _ExecutionCommandHandleFactory:
    """在 actor thread 打开 execution command handle 的 factory。

    :param command_options: durable store typed options 来源。
    :param host_handle_id: execution Host 诊断 id。
    :param wakeup_port: scheduler event-loop wake bridge。
    :param active_cancel_port: active worker event-loop cancel bridge。
    :param open_options: execution opener options，用于 admission baseline/tooling。
    """

    command_options: HostCommandHandleOptions
    host_handle_id: str
    wakeup_port: _ThreadsafeSchedulerWakeupPort
    active_cancel_port: _ThreadsafeActiveWorkerCancelPort
    open_options: OpenHostOptions

    def __call__(self) -> HostCommandHandle:
        """在当前 actor thread 创建 store、admission 与 command handle。

        :returns: actor 独占 command handle。
        :raises Exception: durable store 或 admission 构造失败时透传。
        """

        durable_store = open_host_durable_store(
            _durable_options_from_command_options(self.command_options)
        )
        try:
            admission_service = create_host_admission_service(
                durable_store.transaction_runner,
                wakeup_port=self.wakeup_port,
                projection_catchup_port=None,
                ordinary_run_baseline=self.open_options.ordinary_run_baseline,
                tooling_options=self.open_options.tooling_options,
            )
            return HostCommandHandle(
                host_handle_id=self.host_handle_id,
                durable_store=durable_store,
                admission_service=admission_service,
                active_registry=self.active_cancel_port,
                active_cancel_watchdog_wakeup_port=self.wakeup_port,
            )
        except Exception:
            durable_store.close()
            raise


@dataclass(frozen=True, slots=True)
class _AdminCommandHandleFactory:
    """在 actor thread 打开纯 durable admin command handle 的 factory。

    :param command_options: admin durable store typed options 来源。
    :param host_handle_id: admin handle 诊断 id。
    """

    command_options: HostCommandHandleOptions
    host_handle_id: str

    def __call__(self) -> HostCommandHandle:
        """创建不含 scheduler、recovery、lane 或 worker 的 command handle。

        :returns: actor 独占 command handle。
        :raises Exception: durable store 或只读 admission primitive 构造失败时透传。
        """

        durable_store = open_host_durable_store(
            _durable_options_from_command_options(self.command_options)
        )
        try:
            admission_service = create_host_admission_service(
                durable_store.transaction_runner
            )
            return HostCommandHandle(
                host_handle_id=self.host_handle_id,
                durable_store=durable_store,
                admission_service=admission_service,
                active_registry=NoActiveWorkerCancelPort(),
            )
        except Exception:
            durable_store.close()
            raise


class _PublicHostHandle:
    """``open_host`` 返回的 public async Host handle。

    :param durable_actor: public durable command 单线程 actor。
    :param scheduler: 内部 dispatch scheduler。
    :param projection_catchup_port: close 阶段使用的 projection flush 端口。
    :param scheduler_store: scheduler 独占的 durable store。
    """

    __slots__ = (
        "_closed",
        "_durable_actor",
        "_host_handle_id",
        "_projection_catchup_port",
        "_scheduler",
        "_scheduler_store",
        "_wait_poller",
    )

    def __init__(
        self,
        *,
        durable_actor: DurableActor,
        host_handle_id: str,
        scheduler: HostDispatchScheduler,
        projection_catchup_port: ProjectionCatchupPort,
        scheduler_store: HostDurableStore,
        wait_poller: WaitPollerSupervisor | None,
    ) -> None:
        """初始化 public Host handle。

        :param durable_actor: public durable command 单线程 actor。
        :param host_handle_id: 当前 Host handle 诊断 id。
        :param scheduler: 内部 dispatch scheduler。
        :param projection_catchup_port: close 阶段使用的 projection flush 端口。
        :param scheduler_store: scheduler 独占的 durable store。
        :param wait_poller: 可选 production wait poller supervisor。
        :returns: ``None``。
        """

        self._durable_actor = durable_actor
        self._host_handle_id = host_handle_id
        self._scheduler = scheduler
        self._projection_catchup_port = projection_catchup_port
        self._scheduler_store = scheduler_store
        self._wait_poller = wait_poller
        self._closed: bool = False

    async def ensure_session(self, request: EnsureSessionRequest) -> SessionSnapshot:
        """确保 slot 绑定到 Session。

        :param request: ensure session 请求。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _ensure_session(handle, request)
        )

    async def create_session(self, request: CreateSessionRequest) -> SessionSnapshot:
        """显式创建 Session。

        :param request: create session 请求。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _create_session(handle, request)
        )

    async def get_session(self, session_id: str) -> SessionSnapshot:
        """读取 Session snapshot。

        :param session_id: 目标 Session id。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _get_session(handle, session_id)
        )

    async def get_run(self, run_id: str) -> RunSnapshot:
        """读取 Run snapshot。

        :param run_id: 目标 Run id。
        :returns: Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _get_run(handle, run_id)
        )

    async def read_outbox_terminal_items(
        self,
        session_id: str,
        request: ReadOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """读取 Session 的 Outbox terminal items。

        :param session_id: 目标 Session id。
        :param request: Outbox terminal read 请求。
        :returns: Outbox terminal item 批次。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _read_outbox_terminal_items(
                handle,
                session_id,
                request,
            )
        )

    async def drain_outbox_terminal_items(
        self,
        session_id: str,
        request: DrainOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """幂等 drain Session 的 Outbox terminal items。

        :param session_id: 目标 Session id。
        :param request: Outbox terminal drain 请求。
        :returns: Outbox terminal item 批次。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _drain_outbox_terminal_items(
                handle,
                session_id,
                request,
            )
        )

    async def submit_followup(self, session_id: str, request: SubmitFollowupRequest) -> FollowupSnapshot:
        """提交普通 queue / steer follow-up。

        :param session_id: 目标 Session id。
        :param request: follow-up 请求。
        :returns: follow-up 接受结果 snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _submit_followup(handle, session_id, request)
        )

    async def retry_run(self, run_id: str, request: RetryRunRequest) -> RunSnapshot:
        """重试源 Run。

        :param run_id: 源 Run id。
        :param request: retry 请求。
        :returns: 新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _retry_run(handle, run_id, request)
        )

    async def replay_run(self, run_id: str, request: ReplayRunRequest) -> RunSnapshot:
        """基于源 Run 创建结构化 replay Run。

        :param run_id: 源 Run id。
        :param request: replay 请求。
        :returns: 新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _replay_run(handle, run_id, request)
        )

    async def resolve_wait(self, wait_id: str, request: ResolveWaitRequest) -> RunSnapshot:
        """接收已取得的 wait result 并恢复治理路径。

        :param wait_id: 待 resolve 的 wait id。
        :param request: resolve wait 请求。
        :returns: 最新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _resolve_wait(handle, wait_id, request)
        )

    async def cancel_run(self, run_id: str, request: CancelRunRequest) -> RunSnapshot:
        """取消单个 Run。

        :param run_id: 目标 Run id。
        :param request: cancel run 请求。
        :returns: 最新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _cancel_run(handle, run_id, request)
        )

    async def cancel_session_runs(self, session_id: str, request: CancelSessionRunsRequest) -> SessionSnapshot:
        """取消 Session 下全部未终态 Run。

        :param session_id: 目标 Session id。
        :param request: cancel session runs 请求。
        :returns: 最新 Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _cancel_session_runs(handle, session_id, request)
        )

    async def close_session(self, session_id: str, request: CloseSessionRequest) -> SessionSnapshot:
        """关闭 Session 的新输入入口。

        :param session_id: 目标 Session id。
        :param request: close session 请求。
        :returns: 最新 Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _close_session(handle, session_id, request)
        )

    def watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]:
        """创建 Session live HostEvent 订阅。

        :param session_id: 目标 Session id。
        :returns: Host-owned typed event async iterator。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Session 不存在或不可 watch 时抛出。
        """

        self._raise_if_closed()
        cursor_future = self._durable_actor.submit(
            lambda handle: _session_live_event_start_cursor(handle, session_id)
        )
        cursor_future.add_done_callback(_observe_watch_cursor_future)
        return self._watch_session_events(session_id, cursor_future)

    async def _watch_session_events(
        self,
        session_id: str,
        cursor_future: asyncio.Future[int],
    ) -> AsyncIterator[HostEvent]:
        """在 actor 中 attach cursor 后持续产出 Session live event。

        :param session_id: 目标 Session id。
        :param cursor_future: watch 调用时已同步排队的 actor cursor attach future。
        :returns: Host-owned typed event async iterator。
        :raises HostApiError: Session 不存在或 durable 读取失败时抛出。
        """

        cursor = await asyncio.shield(cursor_future)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.public_handle.watch_attached host_handle_id=%s "
            "session_id=%s cursor=%s",
            self._host_handle_id,
            session_id,
            cursor,
        )
        async for event in self._watch_session_events_after(session_id, cursor):
            yield event

    async def _watch_session_events_after(self, session_id: str, cursor: int) -> AsyncIterator[HostEvent]:
        """从指定 cursor 后持续产出 Session live HostEvent。

        :param session_id: 目标 Session id。
        :param cursor: live watch attach 时的 EventLog 全局序号。
        :returns: Host-owned typed event async iterator。
        :raises HostApiError: Session 在 watch 期间消失时抛出。
        :raises HostDurableError: EventLog 或 payload 投影失败时抛出。
        """

        next_cursor = cursor
        while not self._closed:
            batch = await self._durable_actor.call(
                lambda handle: _read_session_host_events_after(
                    handle,
                    session_id,
                    next_cursor,
                )
            )
            next_cursor = batch.next_cursor
            if len(batch.events) == 0:
                await asyncio.sleep(_SESSION_WATCH_POLL_INTERVAL_SECONDS)
                continue
            for event in batch.events:
                yield event

    async def close(self) -> None:
        """关闭当前 Host handle lifecycle。

        关闭顺序为 public gate、wait poller、actor drain、scheduler、projection
        flush、actor handle、actor executor、scheduler store。actor drain 保证
        after-commit wake 已在 scheduler 仍存活时收口；本方法幂等，不写
        cancel / failed terminal facts。

        :returns: ``None``。
        """

        if self._closed:
            return
        self._closed = True
        _LOGGER.info(
            "host.public_handle.close_start host_handle_id=%s",
            self._host_handle_id,
        )
        close_error: BaseException | None = None
        try:
            if self._wait_poller is not None:
                await asyncio.to_thread(self._wait_poller.close)
        except Exception as exc:
            close_error = exc
            _LOGGER.error(
                "host.public_handle.close_wait_poller_failed "
                "host_handle_id=%s error_type=%s",
                self._host_handle_id,
                exc.__class__.__name__,
                exc_info=True,
            )
        try:
            await self._durable_actor.stop_and_drain()
        except Exception as exc:
            if close_error is None:
                close_error = exc
            else:
                _LOGGER.error(
                    "host.public_handle.close_actor_drain_failed "
                    "host_handle_id=%s error_type=%s",
                    self._host_handle_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
        try:
            await self._scheduler.close()
        except Exception as exc:
            if close_error is None:
                close_error = exc
            else:
                _LOGGER.error(
                    "host.public_handle.close_scheduler_failed "
                    "host_handle_id=%s error_type=%s",
                    self._host_handle_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
        try:
            self._projection_catchup_port.catch_up_projection()
        except Exception as exc:
            if close_error is None:
                close_error = exc
            else:
                _LOGGER.error(
                    "host.public_handle.close_projection_failed "
                    "host_handle_id=%s error_type=%s",
                    self._host_handle_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
        try:
            await self._durable_actor.close_handle()
        except Exception as exc:
            if close_error is None:
                close_error = exc
            else:
                _LOGGER.error(
                    "host.public_handle.close_actor_handle_failed "
                    "host_handle_id=%s error_type=%s",
                    self._host_handle_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
        try:
            self._durable_actor.shutdown_executor()
        except Exception as exc:
            if close_error is None:
                close_error = exc
            else:
                _LOGGER.error(
                    "host.public_handle.close_actor_executor_failed "
                    "host_handle_id=%s error_type=%s",
                    self._host_handle_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
        try:
            self._scheduler_store.close()
        except Exception as exc:
            if close_error is None:
                close_error = exc
            else:
                _LOGGER.error(
                    "host.public_handle.close_scheduler_store_failed "
                    "host_handle_id=%s error_type=%s",
                    self._host_handle_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
        _LOGGER.info(
            "host.public_handle.close_done host_handle_id=%s",
            self._host_handle_id,
        )
        if close_error is not None:
            raise close_error

    def _raise_if_closed(self) -> None:
        """校验 public handle 仍处于打开状态。

        :returns: ``None``。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        if self._closed:
            raise HostClosedError()


def _observe_watch_cursor_future(future: asyncio.Future[int]) -> None:
    """消费未开始迭代的 watch cursor future 异常，避免后台告警。

    调用 ``future.exception()`` 只标记异常已被观察；后续 async iterator await
    同一 future 时仍会得到原异常，不改变 fail-closed 语义。

    :param future: watch 调用时同步排队的 cursor future。
    :returns: ``None``。
    :raises Exception: 不向 event loop 抛出 future 中的业务异常。
    """

    if future.cancelled():
        return
    future.exception()


class _PublicHostAdminHandle:
    """``open_host_admin`` 返回的纯 durable async handle。

    :param durable_actor: admin command 的单线程 durable actor。
    :param host_handle_id: admin handle 诊断 id。
    """

    __slots__ = ("_closed", "_durable_actor", "_host_handle_id")

    def __init__(
        self,
        *,
        durable_actor: DurableActor,
        host_handle_id: str,
    ) -> None:
        """初始化 public HostAdmin handle。

        :param durable_actor: admin command 的单线程 durable actor。
        :param host_handle_id: admin handle 诊断 id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._durable_actor = durable_actor
        self._host_handle_id = host_handle_id
        self._closed = False

    async def list_sessions(self) -> ListSessionsResult:
        """读取全部未 purge Session 列表。

        :returns: durable truth 生成的 Session 列表结果。
        :raises HostClosedError: admin handle 已关闭时抛出。
        :raises HostApiError: durable 读取失败时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(_list_sessions)

    async def get_session(self, session_id: str) -> SessionSnapshot:
        """读取单个 Session snapshot。

        :param session_id: 目标 Session id。
        :returns: durable truth 生成的 Session snapshot。
        :raises HostClosedError: admin handle 已关闭时抛出。
        :raises HostApiError: Session 不存在或 durable 读取失败时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _get_session(handle, session_id)
        )

    async def purge_session(
        self,
        session_id: str,
        request: PurgeSessionRequest,
    ) -> PurgeSessionResult:
        """清理满足前置条件的 Session durable facts。

        :param session_id: 目标 Session id。
        :param request: purge session 请求。
        :returns: purge tombstone 与删除计数摘要。
        :raises HostClosedError: admin handle 已关闭时抛出。
        :raises HostApiError: purge 前置条件或 durable command 失败时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _purge_session(handle, session_id, request)
        )

    async def report_storage_usage(self) -> HostStorageUsageReport:
        """读取 Host durable storage usage report。

        :returns: storage usage report。
        :raises HostClosedError: admin handle 已关闭时抛出。
        :raises HostApiError: durable 读取失败时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(_report_storage_usage)

    async def run_storage_maintenance(
        self,
        request: HostStorageMaintenanceRequest,
    ) -> HostStorageMaintenanceResult:
        """执行 Host storage maintenance。

        :param request: maintenance 请求。
        :returns: maintenance 结果。
        :raises HostClosedError: admin handle 已关闭时抛出。
        :raises HostApiError: maintenance 失败时抛出。
        """

        self._raise_if_closed()
        return await self._durable_actor.call(
            lambda handle: _run_storage_maintenance(handle, request)
        )

    async def close(self) -> None:
        """幂等关闭 admin actor、handle、store 与 executor。

        :returns: ``None``。
        :raises Exception: actor chain 关闭失败时透传。
        """

        if self._closed:
            return
        self._closed = True
        await self._durable_actor.close()
        _LOGGER.info(
            "host.admin_handle.close_done host_handle_id=%s",
            self._host_handle_id,
        )

    def _raise_if_closed(self) -> None:
        """校验 admin handle 仍处于打开状态。

        :returns: ``None``。
        :raises HostClosedError: admin handle 已关闭时抛出。
        """

        if self._closed:
            raise HostClosedError("Host admin handle is closed")


class _OpenHostContextManager(AbstractAsyncContextManager[Host]):
    """``open_host`` public async context manager。

    :param options: Host public opener 构造期选项。
    """

    _host: _PublicHostHandle | None
    _options: OpenHostOptions

    def __init__(self, options: OpenHostOptions) -> None:
        """保存已校验的 opener options。

        :param options: Host public opener 构造期选项。
        :returns: 无返回值。
        :raises TypeError: ``options`` 不是 ``OpenHostOptions`` 时抛出。
        """

        if not isinstance(options, OpenHostOptions):
            raise TypeError("open_host options must be OpenHostOptions")
        self._options = options
        self._host = None

    async def __aenter__(self) -> Host:
        """进入 Host opener runtime。

        :returns: public async Host handle。
        :raises HostDurableError: durable store 打开失败时由底层抛出。
        """

        host_handle_id = _new_open_host_handle_id()
        command_options = _command_options_from_open_host_options(
            self._options,
            host_handle_id=host_handle_id,
        )
        local_execution = _local_execution_options_from_open_host_options(self._options)
        _validate_wait_poller_configuration(self._options)
        _LOGGER.info(
            "host.open.start host_handle_id=%s",
            host_handle_id,
        )
        scheduler_store = open_host_durable_store(
            _durable_options_from_command_options(command_options)
        )
        scheduler: HostDispatchScheduler | None = None
        close_projection_catchup_port: ProjectionCatchupPort | None = None
        wait_poller: WaitPollerSupervisor | None = None
        durable_actor: DurableActor | None = None
        try:
            loop = asyncio.get_running_loop()
            active_registry = ActiveWorkerRegistry()
            audit_projection_catchup_port = _LogAuditProjectionCatchupPort(
                durable_store=scheduler_store,
                options=default_log_audit_sink_options(
                    self._options.artifact_root,
                    create_parent_dirs=self._options.create_parent_dirs,
                ),
            )
            tool_trace_projection_catchup_port = _ToolTraceProjectionCatchupPort(
                durable_store=scheduler_store,
                options=_tool_trace_sink_options_from_open_host_options(self._options),
            )
            outbox_projection_catchup_port = _OutboxTerminalProjectionCatchupPort(
                durable_store=scheduler_store,
            )
            close_projection_catchup_port = _CompositeProjectionCatchupPort(
                ports=(
                    audit_projection_catchup_port,
                    tool_trace_projection_catchup_port,
                    outbox_projection_catchup_port,
                )
            )
            scheduler = await HostDispatchScheduler.open(
                transaction_runner=scheduler_store.transaction_runner,
                local_execution=local_execution,
                host_handle_id=host_handle_id,
                active_registry=active_registry,
                projection_catchup_port=None,
            )
            scheduler.tick_active_cancel_watchdog(datetime.now(UTC))
            StartupRecoveryScanner(
                transaction_runner=scheduler_store.transaction_runner,
                event_log_store=EventLogStore(),
                dispatch_wakeup_port=scheduler,
                recovery_owner_host_instance_id=scheduler.host_instance_id,
                defer_accepted_cancel_to_watchdog=True,
            ).scan()
            wakeup_port = _ThreadsafeSchedulerWakeupPort(
                loop=loop,
                scheduler=scheduler,
            )
            active_cancel_port = _ThreadsafeActiveWorkerCancelPort(
                loop=loop,
                active_registry=active_registry,
            )
            durable_actor = await open_durable_actor(
                _ExecutionCommandHandleFactory(
                    command_options=command_options,
                    host_handle_id=host_handle_id,
                    wakeup_port=wakeup_port,
                    active_cancel_port=active_cancel_port,
                    open_options=self._options,
                ),
                thread_name_prefix=(
                    f"{host_handle_id}-{_DURABLE_ACTOR_THREAD_NAME_SUFFIX}"
                ),
            )
            wait_poller = _wait_poller_supervisor_from_open_host_options(
                self._options,
                command_options=command_options,
                active_registry=active_registry,
                scheduler=scheduler,
                loop=loop,
                host_handle_id=host_handle_id,
            )
            if wait_poller is not None:
                wait_poller.open()
            self._host = _PublicHostHandle(
                durable_actor=durable_actor,
                host_handle_id=host_handle_id,
                scheduler=scheduler,
                projection_catchup_port=close_projection_catchup_port,
                scheduler_store=scheduler_store,
                wait_poller=wait_poller,
            )
            _LOGGER.info(
                "host.open.ready host_handle_id=%s",
                host_handle_id,
            )
            return self._host
        except Exception:
            _LOGGER.error(
                "host.open.failed host_handle_id=%s",
                host_handle_id,
                exc_info=True,
            )
            if wait_poller is not None:
                try:
                    await asyncio.to_thread(wait_poller.close)
                except Exception as cleanup_exc:
                    _LOGGER.error(
                        "host.open.cleanup_wait_poller_failed "
                        "host_handle_id=%s error_type=%s",
                        host_handle_id,
                        cleanup_exc.__class__.__name__,
                        exc_info=True,
                    )
            if durable_actor is not None:
                try:
                    await durable_actor.stop_and_drain()
                except Exception as cleanup_exc:
                    _LOGGER.error(
                        "host.open.cleanup_durable_actor_drain_failed "
                        "host_handle_id=%s error_type=%s",
                        host_handle_id,
                        cleanup_exc.__class__.__name__,
                        exc_info=True,
                    )
            if scheduler is not None:
                try:
                    await scheduler.close()
                except Exception as cleanup_exc:
                    _LOGGER.error(
                        "host.open.cleanup_scheduler_failed host_handle_id=%s " "error_type=%s",
                        host_handle_id,
                        cleanup_exc.__class__.__name__,
                        exc_info=True,
                    )
            _best_effort_catch_up_projection_on_open_failure(
                close_projection_catchup_port,
                host_handle_id=host_handle_id,
            )
            if durable_actor is not None:
                try:
                    await durable_actor.close_handle()
                    durable_actor.shutdown_executor()
                except Exception as cleanup_exc:
                    _LOGGER.error(
                        "host.open.cleanup_durable_actor_failed "
                        "host_handle_id=%s error_type=%s",
                        host_handle_id,
                        cleanup_exc.__class__.__name__,
                        exc_info=True,
                    )
            try:
                scheduler_store.close()
            except Exception as cleanup_exc:
                _LOGGER.error(
                    "host.open.cleanup_durable_store_failed host_handle_id=%s " "error_type=%s",
                    host_handle_id,
                    cleanup_exc.__class__.__name__,
                    exc_info=True,
                )
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """退出 Host opener runtime。

        :param exc_type: context body 抛出的异常类型；无异常时为 ``None``。
        :param exc_value: context body 抛出的异常；无异常时为 ``None``。
        :param traceback: context body 异常 traceback；无异常时为 ``None``。
        :returns: ``None`` 表示不吞掉异常。
        """

        if self._host is not None:
            await self._host.close()
        return None


def open_host(options: OpenHostOptions) -> AbstractAsyncContextManager[Host]:
    """打开普通本地多轮 Host public handle。

    :param options: Host public opener 构造期选项。
    :returns: public async Host handle context manager。
    :raises TypeError: ``options`` 不是 ``OpenHostOptions`` 时抛出。
    """

    return _OpenHostContextManager(options)


class _OpenHostAdminContextManager(AbstractAsyncContextManager[HostAdmin]):
    """``open_host_admin`` 的纯 durable async context manager。

    :param options: HostAdmin public opener 构造选项。
    """

    _host: _PublicHostAdminHandle | None
    _options: OpenHostAdminOptions

    def __init__(self, options: OpenHostAdminOptions) -> None:
        """保存并校验 admin opener options。

        :param options: HostAdmin public opener 构造选项。
        :returns: ``None``。
        :raises TypeError: options 类型错误时抛出。
        """

        if not isinstance(options, OpenHostAdminOptions):
            raise TypeError("open_host_admin options must be OpenHostAdminOptions")
        self._options = options
        self._host = None

    async def __aenter__(self) -> HostAdmin:
        """打开不含 execution side effect 的 admin durable actor。

        :returns: public async HostAdmin handle。
        :raises Exception: durable store 或 actor 打开失败时透传。
        """

        host_handle_id = _new_open_host_admin_handle_id()
        command_options = _command_options_from_open_host_admin_options(
            self._options,
            host_handle_id=host_handle_id,
        )
        durable_actor = await open_durable_actor(
            _AdminCommandHandleFactory(
                command_options=command_options,
                host_handle_id=host_handle_id,
            ),
            thread_name_prefix=(
                f"{host_handle_id}-{_DURABLE_ACTOR_THREAD_NAME_SUFFIX}"
            ),
        )
        self._host = _PublicHostAdminHandle(
            durable_actor=durable_actor,
            host_handle_id=host_handle_id,
        )
        _LOGGER.info(
            "host.admin.open.ready host_handle_id=%s",
            host_handle_id,
        )
        return self._host

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """退出 admin opener 并关闭 actor chain。

        :param exc_type: context body 异常类型；无异常时为 ``None``。
        :param exc_value: context body 异常；无异常时为 ``None``。
        :param traceback: context body traceback；无异常时为 ``None``。
        :returns: ``None`` 表示不吞掉异常。
        """

        if self._host is not None:
            await self._host.close()
        return None


def open_host_admin(
    options: OpenHostAdminOptions,
) -> AbstractAsyncContextManager[HostAdmin]:
    """打开纯 durable Host 管理 handle。

    :param options: 不含 execution 配置或 secret 的 admin opener options。
    :returns: public async HostAdmin context manager。
    :raises TypeError: options 类型错误时抛出。
    """

    return _OpenHostAdminContextManager(options)


def _best_effort_catch_up_projection_on_open_failure(
    projection_catchup_port: ProjectionCatchupPort | None,
    *,
    host_handle_id: str,
) -> None:
    """启动失败清理路径中尽力追平 projection。

    :param projection_catchup_port: 已构造的 projection catch-up 端口；若启动
        尚未完成端口构造则为 ``None``。
    :param host_handle_id: 当前 open_host handle id。
    :returns: ``None``。
    """

    if projection_catchup_port is None:
        return
    try:
        projection_catchup_port.catch_up_projection()
    except Exception as cleanup_exc:
        _LOGGER.warning(
            "host.open.cleanup_projection_catchup_failed host_handle_id=%s "
            "error_type=%s",
            host_handle_id,
            cleanup_exc.__class__.__name__,
            exc_info=True,
        )


def _validate_wait_poller_configuration(options: OpenHostOptions) -> None:
    """校验 wait poller opener 配置。

    :param options: public opener options。
    :returns: ``None``。
    :raises TypeError: policy 或 poll adapter registry 类型非法时抛出。
    :raises HostApiError: 启用 poller 但缺少 poll adapter registry 时抛出。
    """

    _enabled_wait_poller_configuration(options)


def _enabled_wait_poller_configuration(
    options: OpenHostOptions,
) -> _EnabledWaitPollerConfiguration | None:
    """读取已启用 wait poller 配置。

    :param options: public opener options。
    :returns: 已启用配置；未配置或 disabled policy 时返回 ``None``。
    :raises TypeError: policy 或 poll adapter registry 类型非法时抛出。
    :raises HostApiError: 启用 poller 但缺少 poll adapter registry 时抛出。
    """

    policy = options.wait_poller_policy
    if policy is None:
        return None
    if not policy.enabled:
        return None
    tooling_options = options.tooling_options
    if tooling_options is None or tooling_options.wait_poll_adapter_registry is None:
        raise HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message=(
                "OpenHostOptions.wait_poller_policy requires "
                "HostToolingOptions.wait_poll_adapter_registry"
            ),
            retryable=False,
        )
    adapter_registry = tooling_options.wait_poll_adapter_registry
    return _EnabledWaitPollerConfiguration(
        policy=policy,
        adapter_registry=adapter_registry,
    )


def _wait_poller_supervisor_from_open_host_options(
    options: OpenHostOptions,
    *,
    command_options: HostCommandHandleOptions,
    active_registry: ActiveWorkerRegistry,
    scheduler: HostDispatchScheduler,
    loop: asyncio.AbstractEventLoop,
    host_handle_id: str,
) -> WaitPollerSupervisor | None:
    """从 opener options 构造 wait poller supervisor。

    :param options: public opener options。
    :param command_options: opener 派生 command options。
    :param active_registry: 当前 Host active worker registry。
    :param scheduler: 当前 dispatch scheduler。
    :param loop: 当前 opener event loop。
    :param host_handle_id: 当前 public Host handle id。
    :returns: wait poller supervisor；未启用时返回 ``None``。
    """

    configuration = _enabled_wait_poller_configuration(options)
    if configuration is None:
        return None
    owner_id = f"{host_handle_id}-{_WAIT_POLLER_COMMAND_HANDLE_ID_SUFFIX}"
    poller_command_options = replace(
        command_options,
        host_handle_id=owner_id,
        local_execution=None,
    )
    return WaitPollerSupervisor(
        poller_factory=_OpenHostWaitPollerFactory(
            command_options=poller_command_options,
            adapter_registry=configuration.adapter_registry,
            active_cancel_port=_ThreadsafeActiveWorkerCancelPort(
                loop=loop,
                active_registry=active_registry,
            ),
            wakeup_port=_ThreadsafeSchedulerWakeupPort(
                loop=loop,
                scheduler=scheduler,
            ),
            policy=configuration.policy,
            owner_id=owner_id,
        ),
        policy=configuration.policy,
        owner_id=owner_id,
    )


def _wait_poller_call_context(owner_id: str) -> HostCallContext:
    """构造 wait poller 内部 resolve_wait 调用上下文。

    :param owner_id: poller owner id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor="host",
        source="wait_poller",
        request_id=owner_id,
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name="wait_poller",
            operation_kind="host_runtime",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="production_wait_poll",
            correlation_id=owner_id,
        ),
    )


def _is_current_event_loop(loop: asyncio.AbstractEventLoop) -> bool:
    """判断当前线程是否正在运行指定 event loop。

    :param loop: 目标 event loop。
    :returns: 当前线程运行目标 loop 时返回 ``True``。
    """

    try:
        return asyncio.get_running_loop() is loop
    except RuntimeError:
        return False


def _command_options_from_open_host_options(
    options: OpenHostOptions,
    *,
    host_handle_id: str,
) -> HostCommandHandleOptions:
    """从 public opener options 构造内部 command handle options。

    :param options: public opener options。
    :param host_handle_id: opener 内部生成的 Host runtime 诊断 id。
    :returns: 内部 ``HostCommandHandleOptions``。
    """

    local_execution = _local_execution_options_from_open_host_options(options)
    context_budget_fields = _command_context_budget_fields_from_open_host_options(options)
    return HostCommandHandleOptions(
        host_handle_id=host_handle_id,
        db_path=options.db_path,
        artifact_root=options.artifact_root,
        create_parent_dirs=options.create_parent_dirs,
        sqlite_busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
        sqlite_write_busy_retry_count=options.sqlite_write_busy_retry_count,
        sqlite_write_retry_initial_delay_seconds=(options.sqlite_write_retry_initial_delay_seconds),
        sqlite_write_retry_backoff_multiplier=(options.sqlite_write_retry_backoff_multiplier),
        sqlite_write_retry_max_delay_seconds=(options.sqlite_write_retry_max_delay_seconds),
        payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
        context_window_size=context_budget_fields.context_window_size,
        reserved_output_tokens=context_budget_fields.reserved_output_tokens,
        context_budget_hard_threshold_tokens=None,
        context_budget_minimum_protection_tokens=None,
        local_execution=local_execution,
    )


def _command_options_from_open_host_admin_options(
    options: OpenHostAdminOptions,
    *,
    host_handle_id: str,
) -> HostCommandHandleOptions:
    """从 admin opener options 构造纯 durable command options。

    context budget 字段仅满足既有内部 command handle 的必填 typed contract；
    admin public capability 不调用 admission 或 execution command。

    :param options: admin public opener options。
    :param host_handle_id: admin opener 诊断 id。
    :returns: ``local_execution=None`` 的内部 command options。
    :raises Exception: 不主动抛出异常。
    """

    return HostCommandHandleOptions(
        host_handle_id=host_handle_id,
        db_path=options.db_path,
        artifact_root=options.artifact_root,
        create_parent_dirs=options.create_parent_dirs,
        sqlite_busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
        sqlite_write_busy_retry_count=options.sqlite_write_busy_retry_count,
        sqlite_write_retry_initial_delay_seconds=(
            options.sqlite_write_retry_initial_delay_seconds
        ),
        sqlite_write_retry_backoff_multiplier=(
            options.sqlite_write_retry_backoff_multiplier
        ),
        sqlite_write_retry_max_delay_seconds=(
            options.sqlite_write_retry_max_delay_seconds
        ),
        payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
        context_window_size=_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE,
        reserved_output_tokens=_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS,
        local_execution=None,
    )


def _command_context_budget_fields_from_open_host_options(
    options: OpenHostOptions,
) -> _CommandContextBudgetFields:
    """从 public opener options 提取内部 command budget 字段。

    ``OpenHostOptions.context_budget_policy`` 为 ``None`` 时，本 helper 只为
    满足内部 ``HostCommandHandleOptions`` 必填字段构造 fallback；这不是生产
    context budget 默认值。生产调用方需要显式预算治理时必须传入
    ``ContextBudgetPolicy``，本路径不会从 Engine、extra payload 或 profile
    lookup 推导预算。

    :param options: public opener options。
    :returns: 内部 command handle context budget 字段组。
    """

    context_policy = options.context_budget_policy
    if context_policy is None:
        return _CommandContextBudgetFields(
            context_window_size=_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE,
            reserved_output_tokens=(_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS),
        )
    return _CommandContextBudgetFields(
        context_window_size=context_policy.context_window_size,
        reserved_output_tokens=_internal_reserved_output_tokens_for_policy(context_policy.context_window_size),
    )


def _internal_reserved_output_tokens_for_policy(context_window_size: int) -> int:
    """为内部 command options 派生合法输出预留占位值。

    显式 ``OpenHostOptions.context_budget_policy`` 已作为
    ``HostLocalExecutionOptions.context_budget_policy`` 传入 scheduler；这里的
    reserved output 只满足内部 command options 的既有必填 validation，不作为
    ratio-first policy 真源。

    :param context_window_size: 显式 policy 的 context window token 数。
    :returns: 小于 context window 的正整数输出预留。
    """

    return min(
        _INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS,
        context_window_size - 1,
    )


def _local_execution_options_from_open_host_options(
    options: OpenHostOptions,
) -> HostLocalExecutionOptions:
    """从 public opener options 构造内部本地执行配置。

    :param options: public opener options。
    :returns: 内部 ``HostLocalExecutionOptions``。
    """

    compactor_runner_baseline = options.compactor_runner_baseline
    context_compactor = (
        LLMContextCompactor(
            runner_spec=compactor_runner_baseline.compactor_runner_spec,
            runner_options=compactor_runner_baseline.compactor_runner_options,
            agent_policy=compactor_runner_baseline.compactor_agent_policy,
            system_prompt=compactor_runner_baseline.compactor_system_prompt,
            user_prompt_template=(compactor_runner_baseline.compactor_user_prompt_template),
        )
        if compactor_runner_baseline is not None
        else None
    )
    return HostLocalExecutionOptions(
        lane_db_path=options.lane_db_path,
        lane_name=options.lane_name,
        lane_capacity=options.lane_capacity,
        lane_default_timeout_seconds=options.lane_default_timeout_seconds,
        lane_claim_ttl_seconds=options.lane_claim_ttl_seconds,
        lane_heartbeat_interval_seconds=options.lane_heartbeat_interval_seconds,
        worker_startup_timeout_seconds=options.worker_startup_timeout_seconds,
        dispatch_poll_interval_seconds=options.dispatch_poll_interval_seconds,
        runner_spec=options.ordinary_run_baseline.runner_spec,
        runner_options=options.ordinary_run_baseline.runner_options,
        agent_policy=options.ordinary_run_baseline.agent_policy,
        worker_factory=options.worker_factory,
        context_budget_policy=options.context_budget_policy,
        context_compactor=context_compactor,
        compactor_runner_spec=(
            compactor_runner_baseline.compactor_runner_spec if compactor_runner_baseline is not None else None
        ),
        compactor_runner_options=(
            compactor_runner_baseline.compactor_runner_options if compactor_runner_baseline is not None else None
        ),
        compactor_policy_ref=None,
        compact_artifact_root=(
            compactor_runner_baseline.compact_artifact_root if compactor_runner_baseline is not None else None
        ),
        compact_artifact_create_parent_dirs=(
            compactor_runner_baseline.compact_artifact_create_parent_dirs
            if compactor_runner_baseline is not None
            else options.create_parent_dirs
        ),
        memory_projection_policy=options.memory_projection_policy,
        memory_projection_catchup_batch_size=(options.memory_projection_catchup_batch_size),
        tooling_options=options.tooling_options,
        enable_truncation_manager=options.enable_truncation_manager,
    )


def _tool_trace_sink_options_from_open_host_options(
    options: OpenHostOptions,
) -> ToolTraceSinkOptions:
    """从 public opener options 派生内部 Tool Trace sink options。

    :param options: public opener options。
    :returns: ToolTraceSink options；不新增 public ``OpenHostOptions`` 字段。
    :raises TypeError: 派生出的路径配置类型非法时抛出。
    :raises ValueError: 派生出的路径为空时抛出。
    """

    cold_jsonl_path = _default_tool_trace_cold_jsonl_path(options.artifact_root)
    return ToolTraceSinkOptions(
        cold_jsonl_path=cold_jsonl_path,
        create_parent_dirs=options.create_parent_dirs,
        lock_path=_default_tool_trace_lock_path(cold_jsonl_path),
    )


def _default_tool_trace_cold_jsonl_path(artifact_root: Path) -> Path:
    """从 artifact_root 派生默认 Tool Trace cold JSONL 路径。

    :param artifact_root: Host artifact root。
    :returns: 默认 Tool Trace cold JSONL 路径。
    :raises: 无。
    """

    return artifact_root / _TOOL_TRACE_ARTIFACT_DIRECTORY_NAME / _TOOL_TRACE_COLD_JSONL_FILE_NAME


def _default_tool_trace_lock_path(cold_jsonl_path: Path) -> Path:
    """从 Tool Trace cold JSONL 路径派生相邻 lock 文件路径。

    :param cold_jsonl_path: Tool Trace cold JSONL 路径。
    :returns: 相邻 lock 文件路径。
    :raises: 无。
    """

    return cold_jsonl_path.with_name(cold_jsonl_path.name + _TOOL_TRACE_LOCK_FILE_SUFFIX)


def _new_open_host_handle_id() -> str:
    """生成 opener runtime 使用的 Host handle id。

    :returns: 本 opener 生命周期唯一的 Host runtime 诊断 id。
    """

    return f"{_GENERATED_OPEN_HOST_ID_PREFIX}-{uuid4().hex}"


def _new_open_host_admin_handle_id() -> str:
    """生成 admin opener 使用的 Host handle id。

    :returns: 本 admin opener 生命周期唯一诊断 id。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_GENERATED_OPEN_HOST_ADMIN_ID_PREFIX}-{uuid4().hex}"


__all__ = ["open_host", "open_host_admin"]
