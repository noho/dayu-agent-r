"""Host public opener 与 production composition root。

本模块实现普通 Service 使用的 ``open_host(options)`` 入口，负责在 Host
内部装配 durable store、command handle、dispatch scheduler、active
worker registry、memory catch-up 与 compactor baseline。调用方只持有异步
public handle，不接触 scheduler、wakeup port 或 durable internals。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from types import TracebackType
from uuid import uuid4

from dayu.host.admission import create_host_admission_service
from dayu.host.api import (
    CancelRunRequest,
    CancelSessionRunsRequest,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    FollowupSnapshot,
    Host,
    HostClosedError,
    HostCommandHandleOptions,
    HostEvent,
    HostLocalExecutionOptions,
    OpenHostOptions,
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
    resolve_wait as _resolve_wait,
    retry_run as _retry_run,
    replay_run as _replay_run,
    submit_followup as _submit_followup,
)
from dayu.host.command import (
    _durable_options_from_public_options as _durable_options_from_command_options,
)
from dayu.host.dispatch import ActiveWorkerRegistry, HostDispatchScheduler
from dayu.host.durable.connection import (
    HostDurableStore,
    open_host_durable_store,
)
from dayu.host.durable.event_log import EventLogStore
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.llm_compaction import LLMContextCompactor
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.read_api import get_run as _get_run
from dayu.host.read_api import get_session as _get_session
from dayu.host.read_api import (
    read_session_host_events_after as _read_session_host_events_after,
)
from dayu.host.read_api import (
    session_live_event_start_cursor as _session_live_event_start_cursor,
)
from dayu.host.recovery import StartupRecoveryScanner
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_GENERATED_OPEN_HOST_ID_PREFIX = "open-host"
_LOGGER = logging.getLogger(__name__)
_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE = 8192
"""``context_budget_policy=None`` 时内部 command options 使用的兜底窗口。"""

_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS = 1024
"""``context_budget_policy=None`` 时内部 command options 使用的兜底输出预留。"""

_SESSION_WATCH_POLL_INTERVAL_SECONDS = 0.02
"""session live watch 未读取到新事件时的轻量轮询间隔。"""


@dataclass(frozen=True, slots=True)
class _CommandContextBudgetFields:
    """内部 command handle context budget 字段组。

    :param context_window_size: command handle 必填 context window token 数。
    :param reserved_output_tokens: command handle 必填输出预留 token 数。
    """

    context_window_size: int
    reserved_output_tokens: int


@dataclass(slots=True)
class _MemoryProjectionCatchupPort(ProjectionCatchupPort):
    """conversation memory projection catch-up 端口。

    :param durable_store: 当前 opener 持有的 durable store。
    :param options: 当前 opener 的 public construction options。
    """

    durable_store: HostDurableStore
    options: OpenHostOptions

    def catch_up_projection(self) -> None:
        """追平 conversation memory projection。

        :returns: ``None``。
        :raises HostDurableError: durable projection catch-up 失败时抛出。
        """

        catch_up_conversation_memory_projection(
            self.durable_store.transaction_runner,
            policy=self.options.memory_projection_policy,
            batch_size=self.options.memory_projection_catchup_batch_size,
        )


class _PublicHostHandle:
    """``open_host`` 返回的 public async Host handle。

    :param command_handle: 内部同步 command handle。
    :param scheduler: 内部 dispatch scheduler。
    :param projection_catchup_port: close 阶段使用的 projection flush 端口。
    """

    __slots__ = (
        "_closed",
        "_command_handle",
        "_host_handle_id",
        "_projection_catchup_port",
        "_scheduler",
    )

    def __init__(
        self,
        *,
        command_handle: HostCommandHandle,
        host_handle_id: str,
        scheduler: HostDispatchScheduler,
        projection_catchup_port: ProjectionCatchupPort,
    ) -> None:
        """初始化 public Host handle。

        :param command_handle: 内部同步 command handle。
        :param host_handle_id: 当前 Host handle 诊断 id。
        :param scheduler: 内部 dispatch scheduler。
        :param projection_catchup_port: close 阶段使用的 projection flush 端口。
        :returns: ``None``。
        """

        self._command_handle = command_handle
        self._host_handle_id = host_handle_id
        self._scheduler = scheduler
        self._projection_catchup_port = projection_catchup_port
        self._closed: bool = False

    async def ensure_session(
        self, request: EnsureSessionRequest
    ) -> SessionSnapshot:
        """确保 slot 绑定到 Session。

        :param request: ensure session 请求。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _ensure_session(self._command_handle, request)

    async def create_session(
        self, request: CreateSessionRequest
    ) -> SessionSnapshot:
        """显式创建 Session。

        :param request: create session 请求。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _create_session(self._command_handle, request)

    async def get_session(self, session_id: str) -> SessionSnapshot:
        """读取 Session snapshot。

        :param session_id: 目标 Session id。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _get_session(self._command_handle, session_id)

    async def get_run(self, run_id: str) -> RunSnapshot:
        """读取 Run snapshot。

        :param run_id: 目标 Run id。
        :returns: Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _get_run(self._command_handle, run_id)

    async def submit_followup(
        self, session_id: str, request: SubmitFollowupRequest
    ) -> FollowupSnapshot:
        """提交普通 queue / steer follow-up。

        :param session_id: 目标 Session id。
        :param request: follow-up 请求。
        :returns: follow-up 接受结果 snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _submit_followup(self._command_handle, session_id, request)

    async def retry_run(
        self, run_id: str, request: RetryRunRequest
    ) -> RunSnapshot:
        """重试源 Run。

        :param run_id: 源 Run id。
        :param request: retry 请求。
        :returns: 新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _retry_run(self._command_handle, run_id, request)

    async def replay_run(
        self, run_id: str, request: ReplayRunRequest
    ) -> RunSnapshot:
        """基于源 Run 创建结构化 replay Run。

        :param run_id: 源 Run id。
        :param request: replay 请求。
        :returns: 新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _replay_run(self._command_handle, run_id, request)

    async def resolve_wait(
        self, wait_id: str, request: ResolveWaitRequest
    ) -> RunSnapshot:
        """接收已取得的 wait result 并恢复治理路径。

        :param wait_id: 待 resolve 的 wait id。
        :param request: resolve wait 请求。
        :returns: 最新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _resolve_wait(self._command_handle, wait_id, request)

    async def cancel_run(
        self, run_id: str, request: CancelRunRequest
    ) -> RunSnapshot:
        """取消单个 Run。

        :param run_id: 目标 Run id。
        :param request: cancel run 请求。
        :returns: 最新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _cancel_run(self._command_handle, run_id, request)

    async def cancel_session_runs(
        self, session_id: str, request: CancelSessionRunsRequest
    ) -> SessionSnapshot:
        """取消 Session 下全部未终态 Run。

        :param session_id: 目标 Session id。
        :param request: cancel session runs 请求。
        :returns: 最新 Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _cancel_session_runs(self._command_handle, session_id, request)

    async def close_session(
        self, session_id: str, request: CloseSessionRequest
    ) -> SessionSnapshot:
        """关闭 Session 的新输入入口。

        :param session_id: 目标 Session id。
        :param request: close session 请求。
        :returns: 最新 Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        self._raise_if_closed()
        return _close_session(self._command_handle, session_id, request)

    def watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]:
        """创建 Session live HostEvent 订阅。

        :param session_id: 目标 Session id。
        :returns: Host-owned typed event async iterator。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Session 不存在或不可 watch 时抛出。
        """

        self._raise_if_closed()
        cursor = _session_live_event_start_cursor(
            self._command_handle,
            session_id,
        )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.public_handle.watch_attached host_handle_id=%s "
            "session_id=%s cursor=%s",
            self._host_handle_id,
            session_id,
            cursor,
        )
        return self._watch_session_events_after(session_id, cursor)

    async def _watch_session_events_after(
        self, session_id: str, cursor: int
    ) -> AsyncIterator[HostEvent]:
        """从指定 cursor 后持续产出 Session live HostEvent。

        :param session_id: 目标 Session id。
        :param cursor: live watch attach 时的 EventLog 全局序号。
        :returns: Host-owned typed event async iterator。
        :raises HostApiError: Session 在 watch 期间消失时抛出。
        :raises HostDurableError: EventLog 或 payload 投影失败时抛出。
        """

        next_cursor = cursor
        while not self._closed:
            batch = _read_session_host_events_after(
                self._command_handle,
                session_id,
                next_cursor,
            )
            next_cursor = batch.next_cursor
            if len(batch.events) == 0:
                await asyncio.sleep(_SESSION_WATCH_POLL_INTERVAL_SECONDS)
                continue
            for event in batch.events:
                yield event

    async def close(self) -> None:
        """关闭当前 Host handle lifecycle。

        关闭顺序为 public gate、scheduler、projection flush、durable store。
        scheduler close 失败时仍会尽力执行 projection flush 与 durable
        store close；本方法幂等，不写 cancel / failed terminal facts。

        :returns: ``None``。
        """

        if self._closed:
            return
        self._closed = True
        _LOGGER.info(
            "host.public_handle.close_start host_handle_id=%s",
            self._host_handle_id,
        )
        try:
            await self._scheduler.close()
        finally:
            try:
                self._projection_catchup_port.catch_up_projection()
            finally:
                self._command_handle.close()
                _LOGGER.info(
                    "host.public_handle.close_done host_handle_id=%s",
                    self._host_handle_id,
                )

    def _raise_if_closed(self) -> None:
        """校验 public handle 仍处于打开状态。

        :returns: ``None``。
        :raises HostClosedError: Host handle 已关闭时抛出。
        """

        if self._closed:
            raise HostClosedError()


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
        local_execution = _local_execution_options_from_open_host_options(
            self._options
        )
        _LOGGER.info(
            "host.open.start host_handle_id=%s",
            host_handle_id,
        )
        durable_store = open_host_durable_store(
            _durable_options_from_command_options(command_options)
        )
        scheduler: HostDispatchScheduler | None = None
        try:
            active_registry = ActiveWorkerRegistry()
            projection_catchup_port = _MemoryProjectionCatchupPort(
                durable_store=durable_store,
                options=self._options,
            )
            scheduler = await HostDispatchScheduler.open(
                transaction_runner=durable_store.transaction_runner,
                local_execution=local_execution,
                host_handle_id=host_handle_id,
                active_registry=active_registry,
                projection_catchup_port=projection_catchup_port,
            )
            StartupRecoveryScanner(
                transaction_runner=durable_store.transaction_runner,
                event_log_store=EventLogStore(),
                dispatch_wakeup_port=scheduler,
                recovery_owner_host_instance_id=scheduler.host_instance_id,
            ).scan()
            admission_service = create_host_admission_service(
                durable_store.transaction_runner,
                wakeup_port=scheduler,
                projection_catchup_port=projection_catchup_port,
                ordinary_run_baseline=self._options.ordinary_run_baseline,
                tooling_options=self._options.tooling_options,
            )
            command_handle = HostCommandHandle(
                host_handle_id=host_handle_id,
                durable_store=durable_store,
                admission_service=admission_service,
                active_registry=active_registry,
            )
            self._host = _PublicHostHandle(
                command_handle=command_handle,
                host_handle_id=host_handle_id,
                scheduler=scheduler,
                projection_catchup_port=projection_catchup_port,
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
            if scheduler is not None:
                try:
                    await scheduler.close()
                except Exception as cleanup_exc:
                    _LOGGER.error(
                        "host.open.cleanup_scheduler_failed host_handle_id=%s "
                        "error_type=%s",
                        host_handle_id,
                        cleanup_exc.__class__.__name__,
                        exc_info=True,
                    )
            try:
                durable_store.close()
            except Exception as cleanup_exc:
                _LOGGER.error(
                    "host.open.cleanup_durable_store_failed host_handle_id=%s "
                    "error_type=%s",
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

        del exc_type, exc_value, traceback
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
    context_budget_fields = _command_context_budget_fields_from_open_host_options(
        options
    )
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
        context_window_size=context_budget_fields.context_window_size,
        reserved_output_tokens=context_budget_fields.reserved_output_tokens,
        context_budget_hard_threshold_tokens=None,
        context_budget_minimum_protection_tokens=None,
        local_execution=local_execution,
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
            reserved_output_tokens=(
                _INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS
            ),
        )
    return _CommandContextBudgetFields(
        context_window_size=context_policy.context_window_size,
        reserved_output_tokens=_internal_reserved_output_tokens_for_policy(
            context_policy.context_window_size
        ),
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
            user_prompt_template=(
                compactor_runner_baseline.compactor_user_prompt_template
            ),
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
            compactor_runner_baseline.compactor_runner_spec
            if compactor_runner_baseline is not None
            else None
        ),
        compactor_runner_options=(
            compactor_runner_baseline.compactor_runner_options
            if compactor_runner_baseline is not None
            else None
        ),
        compactor_policy_ref=None,
        compact_artifact_root=(
            compactor_runner_baseline.compact_artifact_root
            if compactor_runner_baseline is not None
            else None
        ),
        compact_artifact_create_parent_dirs=(
            compactor_runner_baseline.compact_artifact_create_parent_dirs
            if compactor_runner_baseline is not None
            else options.create_parent_dirs
        ),
        memory_projection_policy=options.memory_projection_policy,
        memory_projection_catchup_batch_size=(
            options.memory_projection_catchup_batch_size
        ),
        tooling_options=options.tooling_options,
        enable_truncation_manager=options.enable_truncation_manager,
    )


def _new_open_host_handle_id() -> str:
    """生成 opener runtime 使用的 Host handle id。

    :returns: 本 opener 生命周期唯一的 Host runtime 诊断 id。
    """

    return f"{_GENERATED_OPEN_HOST_ID_PREFIX}-{uuid4().hex}"


__all__ = ["open_host"]
