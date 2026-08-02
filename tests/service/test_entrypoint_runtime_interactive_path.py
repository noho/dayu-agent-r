"""interactive entrypoint runtime path 集成测试。"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Literal, TypeAlias, cast

import pytest

import dayu.cli.commands.interactive as interactive_command
import dayu.cli.commands.prompt as prompt_command
import dayu.cli.main as cli_main
import dayu.cli.session_execution as session_execution
from dayu.cli.agent_entrypoint import CliSigintMonitor
from dayu.cli.composer import InteractiveComposerEvent, InteractiveComposerEventKind, InteractiveComposerPhase
from dayu.cli.exit_codes import EXIT_KEYBOARD_INTERRUPT
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunCancelledData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AssistantMessage, UserMessage
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AttemptStatus,
    FollowupBehavior,
    FollowupSnapshot,
    Host,
    HostCallContext,
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostFinalAnswerView,
    HostSessionEvent,
    HostSessionEventIterator,
    HostStreamCursor,
    HostTerminalStatus,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OperationContext,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItemsBatch,
    ReadOutboxTerminalItemsRequest,
    RunSnapshot,
    RunStatus,
    SubmitFollowupRequest,
    TerminalResultSummary,
)
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.state import (
    AttemptRow,
    RunRow,
    read_attempt_by_id,
    read_non_terminal_runs_for_session,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.open_host import OpenHostOptions, open_host
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointTurnRequest,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides
from tests.host.public_smoke_support import FinalAnswerWorkerFactory

_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"
_DEFAULT_INTERACTIVE_TOOL_NAME = "get_financial_statement"
_DEFAULT_TIME_TOOL_NAME = "get_current_time"
_DEFAULT_DOWNLOAD_TOOL_NAME = "start_fins_download"
_DEFAULT_PREPROCESS_TOOL_NAME = "start_fins_preprocess"
_DEFAULT_LIST_TOOL_NAME = "list_documents"
_DEFAULT_READ_TOOL_NAME = "read_section"
_EXCLUDED_UPLOAD_TOOL_NAME = "start_fins_upload"
_INTERACTIVE_SUBJECT_TEXT = "# 当前分析对象\n你正在分析的是 AAPL。"
_INTERACTIVE_CURRENT_TIME_TEXT = (
    "# 当前时间\n"
    "现在是 2026年7月7日 17:20（Asia/Shanghai，星期二）。\n"
    "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
)
_REAL_HOST_BARRIER_TIMEOUT_SECONDS = 2.0
_REAL_HOST_BARRIER_POLL_SECONDS = 0.01
_WORKER_EVENT_TIME = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
_AgentSurface: TypeAlias = Literal["prompt", "interactive"]
_LifecycleDurableTruth: TypeAlias = tuple[
    tuple[RunRow, ...],
    tuple[tuple[RunRow, AttemptRow], ...],
]


class _RecordingHostOpener:
    """把 Service 生成的 Host options 接到记录型 deterministic worker。"""

    _worker_factory: FinalAnswerWorkerFactory

    def __init__(self, worker_factory: FinalAnswerWorkerFactory) -> None:
        """保存跨 CLI invocation 复用的记录型 worker factory。

        :param worker_factory: 记录真实 Host runner input 的 deterministic factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._worker_factory = worker_factory

    def __call__(
        self,
        options: OpenHostOptions,
    ) -> AbstractAsyncContextManager[Host]:
        """返回使用记录型 worker 的真实 Host context manager。

        :param options: Service runtime 生成的 Host options。
        :returns: 真实 Host async context manager。
        :raises Exception: Host opener 异常在进入 context 时透传。
        """

        return _open_recording_host(options, worker_factory=self._worker_factory)


@asynccontextmanager
async def _open_recording_host(
    options: OpenHostOptions,
    *,
    worker_factory: LocalEngineWorkerFactory,
) -> AsyncIterator[Host]:
    """使用原始 durable options 打开记录型真实 Host。

    :param options: Service runtime 生成的 Host options。
    :param worker_factory: 记录 Engine request 的 deterministic factory。
    :returns: 真实 Host public handle 的异步迭代器。
    :raises Exception: Host 打开、执行或关闭失败时透传。
    """

    async with open_host(replace(options, worker_factory=worker_factory)) as host:
        yield host


class _FreshQueuedLifecycleCurrentHandle:
    """真实 Host current Run 使用的可取消 worker handle。"""

    _factory: _FreshQueuedLifecycleWorkerFactory
    _snapshot: AttemptDispatchSnapshot

    def __init__(
        self,
        factory: _FreshQueuedLifecycleWorkerFactory,
        snapshot: AttemptDispatchSnapshot,
    ) -> None:
        """保存 current dispatch identity 与 worker barriers。

        :param factory: 生命周期 worker factory。
        :param snapshot: current dispatch snapshot。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory
        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回 current worker id。

        :returns: 稳定测试 worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "interactive-fresh-current-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """在真实 cancel hook 与 exit-after barrier 后产出取消终态。

        :returns: 单条 ``RUN_CANCELLED`` Engine event 流。
        :raises asyncio.CancelledError: Host 错误取消 worker task 时透传。
        """

        self._factory.current_events_started.set()
        await self._factory.release_current_terminal.wait()
        yield EngineEvent(
            occurred_at=_WORKER_EVENT_TIME,
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.RUN_CANCELLED,
            data=RunCancelledData(
                reason="cli_sigint",
                requested_at=_WORKER_EVENT_TIME,
                accepted_at=_WORKER_EVENT_TIME,
                finished_at=_WORKER_EVENT_TIME,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """记录 current handle 已由真实 Host 关闭。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.closed_run_ids.append(self._snapshot.run_id)

    def on_cancel(self, reason: str) -> None:
        """记录真实 Host 传播的 canonical cancel 并打开观察 barrier。

        :param reason: Host 传播的取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.current_cancel_reasons.append(reason)
        self._factory.current_cancel_observed.set()


class _FreshQueuedLifecycleFinalHandle:
    """queued promotion 后立即产出 final answer 的 worker handle。"""

    _factory: _FreshQueuedLifecycleWorkerFactory
    _snapshot: AttemptDispatchSnapshot
    _request: AgentRunRequest

    def __init__(
        self,
        factory: _FreshQueuedLifecycleWorkerFactory,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> None:
        """保存 promoted queued dispatch identity。

        :param factory: 生命周期 worker factory。
        :param snapshot: promoted queued dispatch snapshot。
        :param request: promoted queued Run 的 Engine request。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory
        self._snapshot = snapshot
        self._request = request

    @property
    def local_worker_id(self) -> str:
        """返回 promoted queued worker id。

        :returns: 稳定测试 worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "interactive-fresh-queued-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出 promoted queued Run 的成功 final answer。

        :returns: 单条 ``FINAL_ANSWER`` Engine event 流。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=_WORKER_EVENT_TIME,
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=f"queued final:{self._snapshot.run_id}",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
                response_identity=_successful_response_identity(
                    self._request
                ),
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """记录 promoted queued handle 已由真实 Host 关闭。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.closed_run_ids.append(self._snapshot.run_id)

    def on_cancel(self, reason: str) -> None:
        """拒绝测试中意外取消 promoted queued Run。

        :param reason: 意外取消原因。
        :returns: ``None``。
        :raises AssertionError: 始终抛出，queued Run 不应被 exit intent 取消。
        """

        raise AssertionError(f"promoted queued Run was unexpectedly cancelled: {reason}")


class _FreshQueuedLifecycleWorker:
    """按 dispatch 顺序返回 current-cancel 或 queued-final handle。"""

    _factory: _FreshQueuedLifecycleWorkerFactory

    def __init__(self, factory: _FreshQueuedLifecycleWorkerFactory) -> None:
        """保存生命周期 worker factory。

        :param factory: 生命周期 worker factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """记录真实 Host dispatch，并按第一/第二轮选择 handle。

        :param snapshot: 真实 Host dispatch snapshot。
        :param request: 真实 Engine request。
        :returns: current cancel handle 或 promoted queued final handle。
        :raises RuntimeError: 出现第三次 dispatch 时抛出。
        """

        self._factory.snapshots.append(snapshot)
        self._factory.requests.append(request)
        if len(self._factory.snapshots) == 1:
            return _FreshQueuedLifecycleCurrentHandle(self._factory, snapshot)
        if len(self._factory.snapshots) == 2:
            self._factory.queued_promoted.set()
            return _FreshQueuedLifecycleFinalHandle(
                self._factory,
                snapshot,
                request,
            )
        raise RuntimeError("fresh queued lifecycle dispatched more than two Runs")


def _successful_response_identity(
    request: AgentRunRequest,
) -> SuccessfulRunnerResponseIdentity:
    """构造与 queued final 的 Engine request 同源的测试响应身份。

    :param request: promoted queued Run 的真实 Engine request。
    :returns: provider request id 明确不可用的成功响应身份。
    :raises ValueError: request identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider=request.runner_spec.provider,
        effective_model=request.runner_spec.model,
        runner_request_identity=build_runner_request_identity(
            run_id=request.run_id,
            attempt_id=request.attempt_id,
            execution_id=request.execution_id,
            iteration_id=f"{request.run_id}:queued-final",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=(
            ProviderRequestIdAvailability.UNAVAILABLE
        ),
        provider_request_id=None,
    )


class _FreshQueuedLifecycleWorkerFactory:
    """记录 fresh Session current cancel 与 queued promotion 的真实 worker barrier。"""

    def __init__(self) -> None:
        """初始化 worker barrier 与 owner observations。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.requests: list[AgentRunRequest] = []
        self.snapshots: list[AttemptDispatchSnapshot] = []
        self.current_events_started = asyncio.Event()
        self.current_cancel_observed = asyncio.Event()
        self.release_current_terminal = asyncio.Event()
        self.queued_promoted = asyncio.Event()
        self.current_cancel_reasons: list[str] = []
        self.closed_run_ids: list[str] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建共享生命周期记录器的真实 Host worker。

        :param snapshot: Host 创建 worker 时的 dispatch snapshot。
        :returns: 生命周期 worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return _FreshQueuedLifecycleWorker(self)


class _FreshQueuedLifecycleHostOpener:
    """为 fresh queued integration 注入 worker 并保留真实 Host options。"""

    _worker_factory: _FreshQueuedLifecycleWorkerFactory
    opened_options: OpenHostOptions | None

    def __init__(self, worker_factory: _FreshQueuedLifecycleWorkerFactory) -> None:
        """保存 worker factory。

        :param worker_factory: fresh queued 生命周期 worker factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._worker_factory = worker_factory
        self.opened_options = None

    def __call__(
        self,
        options: OpenHostOptions,
    ) -> AbstractAsyncContextManager[Host]:
        """记录 Service 生成 options 并打开真实 Host。

        :param options: Service runtime 生成的 Host options。
        :returns: 注入 deterministic worker 的真实 Host context manager。
        :raises Exception: Host 打开失败时透传。
        """

        self.opened_options = options
        return _open_recording_host(options, worker_factory=self._worker_factory)

    def require_opened_options(self) -> OpenHostOptions:
        """返回已经由真实 CLI 路径产生的 Host options。

        :returns: 已捕获的 Host options。
        :raises AssertionError: CLI 尚未调用 opener 时抛出。
        """

        if self.opened_options is None:
            raise AssertionError("interactive CLI did not open the real Host")
        return self.opened_options


class _FreshQueuedLifecycleSigintMonitor(CliSigintMonitor):
    """在 exit-after 已被 driver 消费后释放真实 worker cancel terminal。"""

    _release_current_terminal: asyncio.Event

    def __init__(self, release_current_terminal: asyncio.Event) -> None:
        """保存 current worker terminal release barrier。

        :param release_current_terminal: current worker terminal release barrier。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self._release_current_terminal = release_current_terminal

    def install(self) -> None:
        """integration 不安装真实进程 signal handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return

    def close(self) -> None:
        """integration 无进程 signal handler 需要恢复。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return

    async def wait_next(self, observed_count: int) -> int:
        """等待下一次通知，并以第三个 waiter 证明 exit-after 已生效。

        :param observed_count: driver 已消费的 SIGINT 计数。
        :returns: 下一次 SIGINT 计数。
        :raises asyncio.CancelledError: driver cleanup 取消 waiter 时透传。
        """

        if observed_count >= 2:
            self._release_current_terminal.set()
        return await super().wait_next(observed_count)


class _FreshQueuedLifecycleComposer:
    """按真实 Host durable/worker barrier 驱动 current、queued 与两次 Ctrl+C。"""

    def __init__(
        self,
        *,
        opener: _FreshQueuedLifecycleHostOpener,
        worker_factory: _FreshQueuedLifecycleWorkerFactory,
        sigint_monitor: _FreshQueuedLifecycleSigintMonitor,
    ) -> None:
        """保存真实 Host owner observations。

        :param opener: 记录真实 Host options 的 opener。
        :param worker_factory: 记录真实 worker barriers 的 factory。
        :param sigint_monitor: 驱动两次 invocation SIGINT 的 monitor。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._opener = opener
        self._worker_factory = worker_factory
        self._sigint_monitor = sigint_monitor
        self._call_index = 0
        self._pending_submit = False
        self.phase_calls: list[InteractiveComposerPhase] = []
        self.observed_current_and_queue: tuple[RunRow, RunRow] | None = None

    def set_phase(self, phase: InteractiveComposerPhase) -> None:
        """记录真实 CLI state machine 投影的 composer phase。

        :param phase: 新 composer phase。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.phase_calls.append(phase)

    def accept_submit(self, *, record_history: bool) -> None:
        """确认 current 或 queued submit 已被 CLI 接受。

        :param record_history: 是否记录本次 submit history。
        :returns: ``None``。
        :raises AssertionError: 没有 pending submit 或未要求记录 history 时抛出。
        """

        if not self._pending_submit:
            raise AssertionError("fresh lifecycle composer has no pending submit")
        if not record_history:
            raise AssertionError("fresh lifecycle non-empty submit must record history")
        self._pending_submit = False

    async def read_event(self, _prompt: str) -> InteractiveComposerEvent:
        """按 owner barrier 依次提交 current、queued 与两次 Ctrl+C。

        :param _prompt: CLI 输入提示文本。
        :returns: 下一条 typed composer event。
        :raises AssertionError: 真实 Host 未形成 current + sole QUEUE 时抛出。
        """

        self._call_index += 1
        if self._call_index == 1:
            return self._submit_event("current from fresh CLI")
        if self._call_index == 2:
            await asyncio.wait_for(
                self._worker_factory.current_events_started.wait(),
                timeout=_REAL_HOST_BARRIER_TIMEOUT_SECONDS,
            )
            return self._submit_event("sole queued from fresh CLI")
        if self._call_index == 3:
            snapshot = self._worker_factory.snapshots[0]
            self.observed_current_and_queue = await _wait_for_current_and_sole_queue(
                options=self._opener.require_opened_options(),
                session_id=snapshot.session_id,
            )
            self._sigint_monitor.notify()
            await asyncio.wait_for(
                self._worker_factory.current_cancel_observed.wait(),
                timeout=_REAL_HOST_BARRIER_TIMEOUT_SECONDS,
            )
            self._sigint_monitor.notify()
        await asyncio.Event().wait()
        raise AssertionError("fresh lifecycle composer wait unexpectedly returned")

    def _submit_event(self, draft: str) -> InteractiveComposerEvent:
        """构造并登记一份非空 submit event。

        :param draft: 待提交的用户输入。
        :returns: typed submit event。
        :raises AssertionError: 前一份 submit 尚未确认时抛出。
        """

        if self._pending_submit:
            raise AssertionError("fresh lifecycle submit acknowledgement is missing")
        self._pending_submit = True
        return InteractiveComposerEvent(
            kind=InteractiveComposerEventKind.SUBMIT,
            draft=draft,
            input_revision=self._call_index,
        )


class _ReportedTty(io.StringIO):
    """只用于让真实 interactive CLI 进入显式 TTY composer path。"""

    def isatty(self) -> bool:
        """报告 TTY capability。

        :returns: 始终为 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True


def _runtime_assembly_env() -> dict[str, str]:
    """构造真实 interactive runtime assembly 所需的测试 credential 环境。

    :returns: 同时包含显式 DeepSeek 主 Run 与 package MiMo compactor credential 的新字典。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "DEEPSEEK_API_KEY": _API_KEY,
        "MIMO_PLAN_API_KEY": _API_KEY,
    }


async def _wait_for_current_and_sole_queue(
    *,
    options: OpenHostOptions,
    session_id: str,
) -> tuple[RunRow, RunRow]:
    """等待真实 Host durable truth 形成一个 current 与一个 sole QUEUE。

    :param options: 当前真实 Host options。
    :param session_id: fresh Session id。
    :returns: 按 current、queued 顺序返回两个 durable Run rows。
    :raises AssertionError: 有界时间内未形成精确状态组合时抛出。
    """

    loop = asyncio.get_running_loop()
    deadline = loop.time() + _REAL_HOST_BARRIER_TIMEOUT_SECONDS
    with open_host_durable_store(_durable_options(options)) as store:
        while loop.time() < deadline:
            rows = store.transaction_runner.run_read(
                partial(
                    read_non_terminal_runs_for_session,
                    session_id=session_id,
                )
            )
            current = tuple(row for row in rows if row.status is RunStatus.RUNNING)
            queued = tuple(row for row in rows if row.status is RunStatus.QUEUED)
            if len(rows) == 2 and len(current) == 1 and len(queued) == 1:
                return current[0], queued[0]
            await asyncio.sleep(_REAL_HOST_BARRIER_POLL_SECONDS)
    raise AssertionError("real Host did not expose current + sole QUEUE durable truth")


def _durable_options(options: OpenHostOptions) -> HostDurableStoreOptions:
    """从真实 Host options 构造只读 durable store options。

    :param options: Service 生成并由真实 Host 消费的 options。
    :returns: 指向同一 SQLite/artifact owner 的 durable options。
    :raises Exception: 不主动抛出异常。
    """

    return HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=options.artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=options.sqlite_write_retry_initial_delay_seconds,
            write_retry_backoff_multiplier=options.sqlite_write_retry_backoff_multiplier,
            write_retry_max_delay_seconds=options.sqlite_write_retry_max_delay_seconds,
        ),
    )


def _read_lifecycle_durable_truth(
    transaction: HostTransaction,
    *,
    session_id: str,
    snapshots: tuple[AttemptDispatchSnapshot, ...],
) -> _LifecycleDurableTruth:
    """读取 fresh Session 的 Run/Attempt durable owner truth。

    :param transaction: Host durable read transaction。
    :param session_id: fresh Session id。
    :param snapshots: 真实 worker 收到的两个 dispatch snapshots。
    :returns: non-terminal Run rows 与逐 snapshot 的 Run/Attempt rows。
    :raises AssertionError: durable row 缺失时抛出。
    """

    pairs: list[tuple[RunRow, AttemptRow]] = []
    for snapshot in snapshots:
        run = read_run_by_id(transaction, snapshot.run_id)
        attempt = read_attempt_by_id(transaction, snapshot.attempt_id)
        if run is None:
            raise AssertionError(f"durable Run row is missing: {snapshot.run_id}")
        if attempt is None:
            raise AssertionError(f"durable Attempt row is missing: {snapshot.attempt_id}")
        pairs.append((run, attempt))
    return (
        read_non_terminal_runs_for_session(transaction, session_id),
        tuple(pairs),
    )


def _read_lifecycle_truth_from_store(
    *,
    options: OpenHostOptions,
    session_id: str,
    snapshots: tuple[AttemptDispatchSnapshot, ...],
) -> _LifecycleDurableTruth:
    """从真实 Host store 读取完整生命周期 durable truth。

    :param options: 当前真实 Host options。
    :param session_id: fresh Session id。
    :param snapshots: 真实 worker dispatch snapshots。
    :returns: non-terminal rows 与 Run/Attempt pairs。
    :raises AssertionError: durable rows 缺失时抛出。
    """

    result: _LifecycleDurableTruth | None = None
    with open_host_durable_store(_durable_options(options)) as store:
        result = store.transaction_runner.run_read(
            partial(
                _read_lifecycle_durable_truth,
                session_id=session_id,
                snapshots=snapshots,
            )
        )
    if result is None:
        raise AssertionError("durable lifecycle truth was not read")
    return result


class _FakeHostEventIterator:
    """测试用 Host event iterator。"""

    closed_count: int
    _items: tuple[HostSessionEvent, ...]
    _item_index: int
    _changed: asyncio.Event
    _closed: bool

    def __init__(self) -> None:
        """初始化 fake watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count = 0
        self._items = ()
        self._item_index = 0
        self._changed = asyncio.Event()
        self._closed = False

    def __aiter__(self) -> HostSessionEventIterator:
        """返回自身作为 async iterator。

        :returns: HostEvent async iterator。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> HostSessionEvent:
        """读取下一条 Host event。

        :returns: HostEvent。
        :raises StopAsyncIteration: 收到停止信号时抛出。
        """

        while self._item_index >= len(self._items):
            if self._closed:
                raise StopAsyncIteration
            self._changed.clear()
            await self._changed.wait()
        item = self._items[self._item_index]
        self._item_index += 1
        return item

    async def push(self, event: HostSessionEvent) -> None:
        """推入一条 Host event。

        :param event: 待推入事件。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._items = (*self._items, event)
        self._changed.set()

    async def aclose(self) -> None:
        """关闭 watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count += 1
        self._closed = True
        self._changed.set()


class _FakeHost:
    """interactive path 测试用 Host public API 替身。"""

    calls: list[str]
    submit_requests: list[SubmitFollowupRequest]
    watchers: list[_FakeHostEventIterator]
    read_outbox_requests: list[ReadOutboxTerminalItemsRequest]
    _submit_index: int

    def __init__(self) -> None:
        """初始化 fake Host。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []
        self.submit_requests = []
        self.watchers = []
        self.read_outbox_requests = []
        self._submit_index = 0

    async def watch_session_events(
        self,
        session_id: str,
    ) -> HostSessionEventIterator:
        """记录 watcher attach。

        :param session_id: 目标 Session id。
        :returns: Host event iterator。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"watch:{session_id}")
        watcher = _FakeHostEventIterator()
        self.watchers.append(watcher)
        return watcher

    async def submit_followup(self, session_id: str, request: SubmitFollowupRequest) -> FollowupSnapshot:
        """记录 submit 请求并推入成功终态。

        :param session_id: 目标 Session id。
        :param request: SubmitFollowupRequest。
        :returns: FollowupSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        self._submit_index += 1
        run_id = f"run-{self._submit_index}"
        await self.watchers[-1].push(_terminal_event(run_id=run_id, event_sequence=self._submit_index + 1))
        await asyncio.sleep(0)
        return FollowupSnapshot(
            accepted_input_ref=f"input-{self._submit_index}",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id=run_id,
            accepted_run_status=RunStatus.RUNNING,
            command_watermark=HostStreamCursor(event_sequence=self._submit_index),
            queued_run_id=None,
            target_run_id=None,
        )

    async def get_run(self, run_id: str) -> RunSnapshot:
        """返回测试 RunSnapshot。

        :param run_id: 目标 Run id。
        :returns: RunSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"get_run:{run_id}")
        return RunSnapshot(
            run_id=run_id,
            session_id="session-1",
            status=RunStatus.SUCCEEDED,
            current_attempt_id=None,
            terminal_result_summary=TerminalResultSummary(
                status=RunStatus.SUCCEEDED,
                summary_ref=None,
                summary_digest=None,
            ),
            event_cursor=HostStreamCursor(event_sequence=2),
            source_run_id=None,
            source_run_relation=None,
            outbox_summary=None,
        )

    async def read_outbox_terminal_items(
        self,
        session_id: str,
        request: ReadOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """返回空 outbox 批次。

        :param session_id: 目标 Session id。
        :param request: outbox read 请求。
        :returns: 空 outbox terminal batch。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"read_outbox:{session_id}")
        self.read_outbox_requests.append(request)
        return OutboxTerminalItemsBatch(
            items=(),
            next_cursor=OutboxTerminalCursor(event_sequence=0),
            scanned_watermark=OutboxTerminalCursor(event_sequence=0),
            projection_checkpoint=OutboxTerminalCursor(event_sequence=0),
            projection_status=OutboxProjectionStatus.CAUGHT_UP,
            projection_error_code=None,
            projection_error_message=None,
            has_more=False,
        )


@pytest.mark.asyncio
async def test_interactive_runtime_uses_real_manifest_required_slots(
    tmp_path: Path,
) -> None:
    """真实 interactive scene 应只要求并消费当前 manifest 所需 slots。"""

    result = await _prepare_interactive_runtime(tmp_path)

    assert result.scene_inputs.tool_selection.tool_names is not None
    assert _DEFAULT_INTERACTIVE_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _DEFAULT_TIME_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _DEFAULT_DOWNLOAD_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _DEFAULT_LIST_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _DEFAULT_READ_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _DEFAULT_PREPROCESS_TOOL_NAME not in result.scene_inputs.tool_selection.tool_names
    assert _EXCLUDED_UPLOAD_TOOL_NAME not in result.scene_inputs.tool_selection.tool_names
    assert result.host_assembly.options.wait_poller_policy is not None
    assert result.host_assembly.options.wait_poller_policy.enabled
    assert result.host_assembly.options.tooling_options is not None
    assert result.host_assembly.options.tooling_options.wait_poll_adapter_registry is not None
    assert "财报工具指引" in result.scene_inputs.system_prompt
    assert _DEFAULT_TIME_TOOL_NAME in result.scene_inputs.system_prompt
    assert _DEFAULT_DOWNLOAD_TOOL_NAME in result.scene_inputs.system_prompt
    assert _DEFAULT_PREPROCESS_TOOL_NAME not in result.scene_inputs.system_prompt
    assert _EXCLUDED_UPLOAD_TOOL_NAME not in result.scene_inputs.system_prompt
    assert "<when_tag" not in result.scene_inputs.system_prompt
    assert "</when_tag>" not in result.scene_inputs.system_prompt
    assert "<when_tool" not in result.scene_inputs.system_prompt
    assert "</when_tool>" not in result.scene_inputs.system_prompt
    assert result.host_assembly.diagnostics.model_id == _MODEL_ID
    assert result.host_assembly.diagnostics.runner_option_hint_id == _RUNNER_HINT_ID


def test_interactive_real_host_effective_schemas_exclude_preprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 manifest/discovery/Service/Host 链只从最终 schema 排除 preprocess。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: 用于安装记录型真实 Host opener 与 non-TTY 输入。
    :returns: ``None``。
    :raises AssertionError: 最终 Engine request 工具 schema 不符合 interactive 契约时抛出。
    """

    worker_factory = FinalAnswerWorkerFactory()
    _install_recording_cli_host(monkeypatch, worker_factory=worker_factory)

    exit_code = _run_agent_surface(
        "interactive",
        workspace_root=tmp_path,
        label=None,
        user_prompt="读取本地财报",
        monkeypatch=monkeypatch,
    )

    assert exit_code == 0
    assert len(worker_factory.requests) == 1
    schema_names = frozenset(
        schema.function.name for schema in worker_factory.requests[0].tool_schemas
    )
    assert _DEFAULT_PREPROCESS_TOOL_NAME not in schema_names
    assert _DEFAULT_DOWNLOAD_TOOL_NAME in schema_names
    assert _DEFAULT_LIST_TOOL_NAME in schema_names
    assert _DEFAULT_READ_TOOL_NAME in schema_names


@pytest.mark.asyncio
async def test_interactive_runtime_requires_subject_and_current_time_context_slots(
    tmp_path: Path,
) -> None:
    """真实 interactive scene 要求共享研究主体与当前时间 context slots。"""

    runtime = await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            scene_id="interactive",
            context_slot_values={
                "fins_default_subject": _INTERACTIVE_SUBJECT_TEXT,
                "current_time": _INTERACTIVE_CURRENT_TIME_TEXT,
            },
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env=_runtime_assembly_env(),
        )
    )

    assert runtime.scene_inputs.tool_selection.tool_names is not None
    assert _DEFAULT_INTERACTIVE_TOOL_NAME in runtime.scene_inputs.tool_selection.tool_names


@pytest.mark.asyncio
async def test_interactive_two_turns_have_independent_terminal_wait_state(
    tmp_path: Path,
) -> None:
    """interactive 两轮应各自 attach/close watcher 且不复用 wait state。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    fake_host = _FakeHost()

    first = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(turn_index=1, user_prompt="第一轮"),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )
    second = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(turn_index=2, user_prompt="第二轮"),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert first.run_id == "run-1"
    assert second.run_id == "run-2"
    assert fake_host.calls == [
        "watch:session-1",
        "submit:session-1",
        "watch:session-1",
        "submit:session-1",
    ]
    assert [watcher.closed_count for watcher in fake_host.watchers] == [1, 1]
    assert fake_host.submit_requests[0].client_request_id == "submit-turn-1"
    assert fake_host.submit_requests[1].client_request_id == "submit-turn-2"


@pytest.mark.parametrize(
    ("first_surface", "second_surface"),
    (
        ("prompt", "prompt"),
        ("prompt", "interactive"),
        ("interactive", "prompt"),
        ("interactive", "interactive"),
    ),
)
def test_labeled_agent_surfaces_share_exact_session_and_prior_turn_runner_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_surface: _AgentSurface,
    second_surface: _AgentSurface,
) -> None:
    """共享 label 必须在四种调用顺序中保留 exact Session 与前轮 memory。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param first_surface: 第一轮 Agent surface。
    :param second_surface: 第二轮 Agent surface。
    :returns: ``None``。
    :raises AssertionError: Session identity 或第二轮 runner input 未保留前轮时抛出。
    """

    worker_factory = FinalAnswerWorkerFactory()
    _install_recording_cli_host(monkeypatch, worker_factory=worker_factory)
    first_prompt = f"第一轮来自 {first_surface}"
    second_prompt = f"第二轮来自 {second_surface}"

    first_exit_code = _run_agent_surface(
        first_surface,
        workspace_root=tmp_path,
        label="财报.共享会话",
        user_prompt=first_prompt,
        monkeypatch=monkeypatch,
    )
    second_exit_code = _run_agent_surface(
        second_surface,
        workspace_root=tmp_path,
        label="财报.共享会话",
        user_prompt=second_prompt,
        monkeypatch=monkeypatch,
    )

    assert first_exit_code == 0
    assert second_exit_code == 0
    assert len(worker_factory.requests) == 2
    assert len(worker_factory.snapshots) == 2
    first_request, second_request = worker_factory.requests
    first_snapshot, second_snapshot = worker_factory.snapshots
    assert first_snapshot.session_id == second_snapshot.session_id
    assert first_request.session_id == first_snapshot.session_id
    assert second_request.session_id == first_snapshot.session_id
    assert tuple(message.content for message in second_request.messages if isinstance(message, UserMessage))[-2:] == (
        first_prompt,
        second_prompt,
    )
    assert tuple(message.content for message in second_request.messages if isinstance(message, AssistantMessage))[
        -1:
    ] == (f"final:1:{first_snapshot.run_id}",)


@pytest.mark.parametrize("surface", ("prompt", "interactive"))
def test_unlabeled_agent_invocations_use_fresh_session_without_prior_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: _AgentSurface,
) -> None:
    """无 label 的 prompt 与 interactive 每次 invocation 都必须 fresh。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param surface: 连续执行两次的 Agent surface。
    :returns: ``None``。
    :raises AssertionError: Session 被复用或前轮 memory 进入第二轮时抛出。
    """

    worker_factory = FinalAnswerWorkerFactory()
    _install_recording_cli_host(monkeypatch, worker_factory=worker_factory)
    first_prompt = f"无标签第一轮 {surface}"
    second_prompt = f"无标签第二轮 {surface}"

    first_exit_code = _run_agent_surface(
        surface,
        workspace_root=tmp_path,
        label=None,
        user_prompt=first_prompt,
        monkeypatch=monkeypatch,
    )
    second_exit_code = _run_agent_surface(
        surface,
        workspace_root=tmp_path,
        label=None,
        user_prompt=second_prompt,
        monkeypatch=monkeypatch,
    )

    assert first_exit_code == 0
    assert second_exit_code == 0
    assert len(worker_factory.requests) == 2
    assert len(worker_factory.snapshots) == 2
    assert worker_factory.snapshots[0].session_id != worker_factory.snapshots[1].session_id
    assert worker_factory.requests[0].session_id == worker_factory.snapshots[0].session_id
    assert worker_factory.requests[1].session_id == worker_factory.snapshots[1].session_id
    assert tuple(
        message.content for message in worker_factory.requests[1].messages if isinstance(message, UserMessage)
    ) == (second_prompt,)
    assert not any(isinstance(message, AssistantMessage) for message in worker_factory.requests[1].messages)


def test_unlabeled_interactive_exit_after_cancel_closes_real_current_and_sole_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fresh CLI 必须取消 current、提升 sole QUEUE 并在 exit 130 前收口 durable truth。

    :param tmp_path: fresh interactive workspace root。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 真实 Host/worker/durable 生命周期任一环节不符合契约时抛出。
    """

    worker_factory = _FreshQueuedLifecycleWorkerFactory()
    opener = _FreshQueuedLifecycleHostOpener(worker_factory)
    sigint_monitor = _FreshQueuedLifecycleSigintMonitor(worker_factory.release_current_terminal)
    composer = _FreshQueuedLifecycleComposer(
        opener=opener,
        worker_factory=worker_factory,
        sigint_monitor=sigint_monitor,
    )
    monkeypatch.setattr(interactive_command, "open_host", opener)
    monkeypatch.setattr(
        interactive_command,
        "CliSigintMonitor",
        lambda: sigint_monitor,
    )
    monkeypatch.setattr(session_execution, "new_interactive_composer", lambda: composer)
    monkeypatch.setattr(session_execution.sys, "stdin", _ReportedTty())
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setenv("MIMO_PLAN_API_KEY", _API_KEY)

    exit_code = cli_main.main(
        (
            "interactive",
            "--base",
            str(tmp_path),
            "--no-detail",
            "--no-thinking",
        )
    )

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(worker_factory.snapshots) == 2
    assert len(worker_factory.requests) == 2
    current_snapshot, queued_snapshot = worker_factory.snapshots
    assert current_snapshot.session_id == queued_snapshot.session_id
    assert worker_factory.current_cancel_reasons == ["cli_sigint"]
    assert worker_factory.queued_promoted.is_set()
    assert worker_factory.closed_run_ids == [
        current_snapshot.run_id,
        queued_snapshot.run_id,
    ]
    assert composer.observed_current_and_queue is not None
    observed_current, observed_queue = composer.observed_current_and_queue
    assert observed_current.run_id == current_snapshot.run_id
    assert observed_current.status is RunStatus.RUNNING
    assert observed_queue.run_id != current_snapshot.run_id
    assert observed_queue.status is RunStatus.QUEUED
    assert queued_snapshot.run_id == observed_queue.run_id

    options = opener.require_opened_options()
    non_terminal, pairs = _read_lifecycle_truth_from_store(
        options=options,
        session_id=current_snapshot.session_id,
        snapshots=tuple(worker_factory.snapshots),
    )
    assert non_terminal == ()
    assert [(run.status, attempt.status) for run, attempt in pairs] == [
        (RunStatus.CANCELLED, AttemptStatus.CANCELLED),
        (RunStatus.SUCCEEDED, AttemptStatus.SUCCEEDED),
    ]


def _install_recording_cli_host(
    monkeypatch: pytest.MonkeyPatch,
    *,
    worker_factory: FinalAnswerWorkerFactory,
) -> None:
    """安装 prompt/interactive 共用的真实记录型 Host opener。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param worker_factory: 跨 invocation 记录真实 Engine request 的 factory。
    :returns: ``None``。
    :raises Exception: monkeypatch 设置失败时透传。
    """

    opener = _RecordingHostOpener(worker_factory)
    monkeypatch.setattr(prompt_command, "open_host", opener)
    monkeypatch.setattr(interactive_command, "open_host", opener)
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setenv("MIMO_PLAN_API_KEY", _API_KEY)


def _run_agent_surface(
    surface: _AgentSurface,
    *,
    workspace_root: Path,
    label: str | None,
    user_prompt: str,
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    """经真实 CLI→Service→Host 路径执行一个 Agent turn。

    :param surface: prompt 或 interactive surface。
    :param workspace_root: 两次 invocation 共用的 workspace root。
    :param label: 可选 durable alias；``None`` 表示 fresh Session。
    :param user_prompt: 本轮用户输入。
    :param monkeypatch: 用于给 interactive 注入单轮 stdin 的夹具。
    :returns: CLI 退出码。
    :raises ValueError: surface 不是 prompt 或 interactive 时抛出。
    """

    label_args = () if label is None else ("--label", label)
    common_args = (
        "--base",
        str(workspace_root),
        *label_args,
        "--no-detail",
        "--no-thinking",
    )
    if surface == "prompt":
        return cli_main.main(("prompt", *common_args, user_prompt))
    if surface == "interactive":
        stdin = io.TextIOWrapper(
            io.BytesIO(user_prompt.encode("utf-8")),
            encoding="utf-8",
        )
        monkeypatch.setattr(session_execution.sys, "stdin", stdin)
        return cli_main.main(("interactive", *common_args))
    raise ValueError(f"unsupported Agent surface: {surface}")


async def _prepare_interactive_runtime(
    tmp_path: Path,
) -> EntrypointRuntimeResult:
    """构造真实 interactive runtime assembly 测试结果。

    :param tmp_path: pytest 临时 workspace root。
    :returns: entrypoint runtime result。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    return await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            scene_id="interactive",
            context_slot_values={
                "fins_default_subject": _INTERACTIVE_SUBJECT_TEXT,
                "current_time": _INTERACTIVE_CURRENT_TIME_TEXT,
            },
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env=_runtime_assembly_env(),
        )
    )


def _turn_request(*, turn_index: int, user_prompt: str) -> EntrypointTurnRequest:
    """构造默认 entrypoint turn request。

    :param turn_index: 测试轮次序号。
    :param user_prompt: 用户输入。
    :returns: entrypoint turn request。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointTurnRequest(
        context=_host_context(f"submit-context-{turn_index}"),
        session_id="session-1",
        client_request_id=f"submit-turn-{turn_index}",
        user_prompt=user_prompt,
        tool_names=frozenset({"get_financial_statement"}),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
        run_overrides=ServiceRunOverrides(temperature=0.2),
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造测试 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises Exception: 不主动抛出异常。
    """

    return HostCallContext(
        actor="service-test",
        source="service-entrypoint-test",
        request_id=request_id,
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name="service_entrypoint.interactive_test",
            operation_kind="service_entrypoint_test",
            business_domain="fins",
            business_object_type=None,
            business_object_id=None,
            scenario="interactive",
            correlation_id="correlation-1",
        ),
    )


def _terminal_event(*, run_id: str, event_sequence: int) -> HostEvent:
    """构造测试 terminal HostEvent。

    :param run_id: Run id。
    :param event_sequence: event sequence。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id=f"terminal-{run_id}-{event_sequence}",
        event_sequence=event_sequence,
        session_id="session-1",
        run_id=run_id,
        event_class=HostEventClass.CANONICAL_FACT,
        event_type="RUN_SUCCEEDED",
        kind=HostEventKind.SUCCEEDED,
        activity=None,
        dedupe_key=f"terminal-{run_id}-{event_sequence}",
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=HostFinalAnswerView(
            content=f"answer for {run_id}",
            filtered=False,
            degraded=False,
            finish_reason="stop",
            terminal_status=HostTerminalStatus.SUCCEEDED,
        ),
        error_message=None,
        cancel_reason=None,
    )
