"""``dayu-cli prompt`` 命令测试。"""

from __future__ import annotations

import asyncio
import builtins
import getpass
import io
import signal
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from pathlib import Path
from typing import Never, cast
from unittest.mock import Mock

import pytest

import dayu.cli.__main__ as cli_module
import dayu.cli.commands.init as init_command
import dayu.cli.commands.prompt as prompt_command
import dayu.cli.main as cli_main
import dayu.cli.session_execution as session_execution
import dayu.service.scene_context as scene_context
from dayu.cli.__main__ import run_module
from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    package_config_root,
)
from dayu.cli.arg_parsing import ParsedCliArgs, parse_cli_args
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.host_context import CliInvocation
from dayu.host.api import (
    CancelMode,
    CancelRunRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    FollowupSnapshot,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostActivityCounts,
    HostActivityKind,
    HostActivitySeverity,
    HostActivityStatus,
    HostActivityView,
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostFinalAnswerView,
    HostReasoningDelta,
    HostSessionEvent,
    HostSessionEventDeliveryDetail,
    HostSessionEventDeliveryReason,
    HostSessionEventIterator,
    HostSessionAccessMode,
    HostSessionAttachment,
    HostStreamCursor,
    HostTerminalStatus,
    HostTransientDelta,
    HostTransientDeltaType,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItem,
    OutboxTerminalItemsBatch,
    OutboxTerminalItemState,
    OpenHostOptions,
    ReadOutboxTerminalItemsRequest,
    RunSnapshot,
    RunStatus,
    SessionSlotRef,
    SessionSnapshot,
    SessionStatus,
    SubmitFollowupRequest,
    TerminalResultSummary,
    is_terminal_run_status,
)
from dayu.service.entrypoint_runtime import EntrypointRuntimeRequest
from dayu.service.entrypoint_runtime import EntrypointRuntimeResult
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides
from dayu.cli.activity import CliActivityRenderer, CliActivityRendererOptions
from dayu.cli.output import render_prompt_terminal_result
from dayu.cli.run_keys import RunningKeyAction
from dayu.cli.runtime_display import (
    RuntimeActivityDisplay,
    RuntimeDisplayController,
    RuntimeThinkingDisplay,
)
from dayu.cli.session_terminal_cursor import CliTerminalCursorError, read_cli_terminal_cursor
from dayu.cli.thinking import CliThinkingRenderer, CliThinkingRendererOptions
from dayu.service.entrypoint_runtime import (
    EntrypointRunTerminalResult,
    EntrypointTerminalSource,
    EntrypointThinking,
)
from dayu.fins.resolver import FmpCompanyInfo

_REMOVED_PROMPT_DEBUG_OPTIONS: tuple[tuple[str, ...], ...] = (
    ("--debug-sse",),
    ("--debug-tool-delta",),
    ("--debug-sse-sample-rate", "0.5"),
    ("--debug-sse-throttle-sec", "1.0"),
)

_NOW = datetime(2026, 6, 14, 8, 0, 0, tzinfo=UTC)
_MODEL_ID = "deepseek-v4-flash"
_API_KEY = "test-provider-key"
_PROMPT_CURRENT_TIME_TEXT = (
    "# 当前时间\n"
    "现在是 2026年6月14日 16:00（Asia/Shanghai，星期日）。\n"
    "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
)
_DEFAULT_PROMPT_TOOL_NAME = "get_financial_statement"
_DEFAULT_TIME_TOOL_NAME = "get_current_time"
_EXCLUDED_UPLOAD_TOOL_NAME = "start_fins_upload"
_TEST_ASYNC_TIMEOUT_SECONDS = 2.0


def _runtime_assembly_env() -> dict[str, str]:
    """构造 prompt 测试完整 runtime assembly 所需的环境输入。

    本 helper 仅供经过完整 ``prepare_entrypoint_runtime -> Service assembly ->
    compactor`` 装配路径的测试使用；mock-assembly 测试继续只声明自身消费的输入。

    :returns: 同时满足单次 DeepSeek ordinary override 与 package Mimo compactor
        baseline 的环境变量映射。
    :raises Exception: 本函数不主动抛出异常。
    """

    return {
        "DEEPSEEK_API_KEY": _API_KEY,
        "MIMO_PLAN_API_KEY": _API_KEY,
    }


class _TtySecretInput(io.StringIO):
    """只允许 capability 检查、禁止 init secret owner 逐行读取的 TTY fake。"""

    def isatty(self) -> bool:
        """声明 caller-owned stdin 具有 TTY 能力。

        :returns: 始终返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    def readline(self, size: int = -1, /) -> str:
        """拒绝 TTY secret owner 误入 redirected stdin 路径。

        :param size: 兼容文本流协议的最大读取长度；测试不消费。
        :returns: 本方法不返回。
        :raises AssertionError: 任何调用都表示 TTY capability 分流漂移。
        """

        del size
        raise AssertionError("TTY secret input must not call stdin.readline")


async def _raise_cli_terminal_cursor_error(
    *,
    workspace_root: Path,
    session_id: str,
    terminal_event_id: str,
    event_sequence: int,
) -> None:
    """模拟 CLI terminal cursor 持久化失败。

    :param workspace_root: workspace 根目录。
    :param session_id: Host Session id。
    :param terminal_event_id: 已渲染 terminal event id。
    :param event_sequence: 已渲染 terminal event sequence。
    :returns: ``None``。
    :raises CliTerminalCursorError: 始终抛出，模拟本地 cursor 写入失败。
    """

    raise CliTerminalCursorError("cursor write failed")


@dataclass(frozen=True, slots=True)
class _RaiseSignal:
    """测试 watcher 异常信号。"""

    error: Exception


class _FakePromptFmpResolver:
    """prompt command 测试用 FMP resolver。"""

    def __init__(self, *, api_key: str, timeout_seconds: float) -> None:
        """初始化 fake resolver。

        :param api_key: FMP API key。
        :param timeout_seconds: FMP timeout。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del api_key, timeout_seconds

    def resolve_company_info(self, canonical_ticker: str) -> FmpCompanyInfo:
        """返回固定公司信息。

        :param canonical_ticker: canonical ticker。
        :returns: fake 公司信息。
        :raises Exception: 不主动抛出异常。
        """

        return FmpCompanyInfo(
            canonical_ticker=canonical_ticker,
            company_name="Visa Inc.",
            ticker_aliases=(canonical_ticker,),
        )


class _BlockingFinishThinkingDisplay:
    """用线程 barrier 冻结 prompt finish-thinking 窗口。"""

    finish_started: threading.Event
    release_finish: threading.Event
    close_count: int

    def __init__(self) -> None:
        """初始化 finish 与 close 观测状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.finish_started = threading.Event()
        self.release_finish = threading.Event()
        self.close_count = 0

    def finish_runtime_display(self) -> None:
        """阻塞 finish，直到测试允许 helper 继续取消仲裁。

        :returns: ``None``。
        :raises AssertionError: 测试未在时限内释放 barrier 时抛出。
        """

        self.finish_started.set()
        released = self.release_finish.wait(timeout=_TEST_ASYNC_TIMEOUT_SECONDS)
        if not released:
            raise AssertionError("finish-thinking barrier was not released")

    def close(self) -> None:
        """记录 thinking display 关闭次数。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1


class _CloseFailingActivityRenderer(CliActivityRenderer):
    """在真实 prompt renderer contract 上注入 caller-close failure。"""

    close_count: int
    _close_error: RuntimeError

    def __init__(self, close_error: RuntimeError) -> None:
        """初始化关闭失败 renderer。

        :param close_error: ``close`` 必须原样抛出的异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(
            stderr=io.StringIO(),
            options=CliActivityRendererOptions(visible=True, enabled=False),
        )
        self.close_count = 0
        self._close_error = close_error

    def close(self) -> None:
        """关闭 renderer 后原样抛出配置的 lifecycle failure。

        :returns: 本方法不返回。
        :raises RuntimeError: 始终抛出配置的关闭异常。
        """

        self.close_count += 1
        super().close()
        raise self._close_error


class _FakeHostEventIterator:
    """测试用 Host event iterator。"""

    closed_count: int
    _items: tuple[HostSessionEvent | _RaiseSignal, ...]
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
        if isinstance(item, _RaiseSignal):
            raise item.error
        return item

    async def push(self, event: HostSessionEvent) -> None:
        """推入一条 Host event。

        :param event: 待推入事件。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._items = (*self._items, event)
        self._changed.set()

    async def fail(self, error: Exception) -> None:
        """推入 watcher drain 应观察到的异常。

        :param error: watcher drain 应观察到的异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._items = (*self._items, _RaiseSignal(error=error))
        self._changed.set()

    async def aclose(self) -> None:
        """关闭 watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count += 1
        self._closed = True
        self._changed.set()


class _FakeSessionAttachment:
    """CLI prompt fake Host 返回的显式 RW attachment。"""

    def __init__(self, session_id: str) -> None:
        """初始化测试 attachment。

        :param session_id: attachment 绑定的 Session id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.session_id = session_id
        self.access_mode = HostSessionAccessMode.READ_WRITE
        self.close_count = 0

    async def aclose(self) -> None:
        """记录 attachment lexical close。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1


class _FakeHost:
    """CLI prompt 测试用 Host public API 替身。"""

    calls: list[str]
    watchers: list[_FakeHostEventIterator]
    ensure_requests: list[EnsureSessionRequest]
    create_requests: list[CreateSessionRequest]
    submit_requests: list[SubmitFollowupRequest]
    cancel_requests: list[CancelRunRequest]
    read_outbox_requests: list[ReadOutboxTerminalItemsRequest]
    _submit_terminal: HostEvent | None
    _submit_events: tuple[HostSessionEvent, ...]
    _submit_watcher_errors: tuple[Exception, ...]
    _cancel_terminal: HostEvent | None
    _outbox_item: OutboxTerminalItem | None
    _run_statuses: tuple[RunStatus, ...]
    _run_status_index: int
    _create_error: HostApiError | None
    attach_session_ids: list[str]
    attachments: list["_FakeSessionAttachment"]

    def __init__(
        self,
        *,
        submit_terminal: HostEvent | None,
        submit_events: tuple[HostSessionEvent, ...] = (),
        submit_watcher_errors: tuple[Exception, ...] = (),
        run_statuses: tuple[RunStatus, ...] = (RunStatus.SUCCEEDED,),
        outbox_item: OutboxTerminalItem | None = None,
        cancel_terminal: HostEvent | None = None,
        create_error: HostApiError | None = None,
    ) -> None:
        """初始化 fake Host。

        :param submit_terminal: submit 返回前推入的 terminal event；``None``
            表示 watcher 不产生 terminal。
        :param submit_events: submit 返回前推入的非终态 Host events。
        :param submit_watcher_errors: submit 返回前推入 watcher 的异常。
        :param run_statuses: ``get_run`` 依次返回的状态。
        :param outbox_item: outbox fallback 返回的 terminal item。
        :param cancel_terminal: cancel 返回前推入的 terminal event。
        :param create_error: create_session 时抛出的 HostApiError。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []
        self.watchers = []
        self.ensure_requests = []
        self.create_requests = []
        self.submit_requests = []
        self.cancel_requests = []
        self.read_outbox_requests = []
        self._submit_terminal = submit_terminal
        self._submit_events = submit_events
        self._submit_watcher_errors = submit_watcher_errors
        self._cancel_terminal = cancel_terminal
        self._outbox_item = outbox_item
        self._run_statuses = run_statuses
        self._run_status_index = 0
        self._create_error = create_error
        self.attach_session_ids = []
        self.attachments = []

    async def attach_session(self, session_id: str) -> HostSessionAttachment:
        """记录显式 Session attachment 并返回可关闭对象。

        :param session_id: 目标 Session id。
        :returns: 测试用 RW attachment。
        :raises Exception: 不主动抛出异常。
        """

        attachment = _FakeSessionAttachment(session_id)
        self.attach_session_ids.append(session_id)
        self.attachments.append(attachment)
        return attachment

    async def ensure_session(self, request: EnsureSessionRequest) -> SessionSnapshot:
        """记录 ensure_session 请求。

        :param request: ensure session 请求。
        :returns: SessionSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append("ensure_session")
        self.ensure_requests.append(request)
        return _session_snapshot(
            session_id="session-1",
            slot=SessionSlotRef(scope=request.scope, slot_key=request.slot_key),
        )

    async def create_session(self, request: CreateSessionRequest) -> SessionSnapshot:
        """记录 create_session 请求。

        :param request: create session 请求。
        :returns: SessionSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append("create_session")
        self.create_requests.append(request)
        if self._create_error is not None:
            raise self._create_error
        slot = None
        if request.scope is not None and request.slot_key is not None:
            slot = SessionSlotRef(scope=request.scope, slot_key=request.slot_key)
        return _session_snapshot(session_id="session-1", slot=slot)

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
        """记录 submit_followup 请求。

        :param session_id: 目标 Session id。
        :param request: SubmitFollowupRequest。
        :returns: FollowupSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        for event in self._submit_events:
            await self.watchers[-1].push(event)
        for error in self._submit_watcher_errors:
            await self.watchers[-1].fail(error)
        if self._submit_terminal is not None:
            await self.watchers[-1].push(self._submit_terminal)
        if self._submit_events or self._submit_watcher_errors or self._submit_terminal is not None:
            await asyncio.sleep(0)
        return FollowupSnapshot(
            accepted_input_ref="input-1",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id="run-1",
            accepted_run_status=RunStatus.RUNNING,
            command_watermark=HostStreamCursor(event_sequence=1),
            queued_run_id=None,
            target_run_id=None,
        )

    async def get_run(self, run_id: str) -> RunSnapshot:
        """按预设状态返回 RunSnapshot。

        :param run_id: 目标 Run id。
        :returns: RunSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"get_run:{run_id}")
        status_index = min(self._run_status_index, len(self._run_statuses) - 1)
        status = self._run_statuses[status_index]
        self._run_status_index += 1
        return _run_snapshot(run_id=run_id, status=status)

    async def read_outbox_terminal_items(
        self,
        session_id: str,
        request: ReadOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """返回 outbox fallback 批次。

        :param session_id: 目标 Session id。
        :param request: outbox read 请求。
        :returns: OutboxTerminalItemsBatch。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"read_outbox:{session_id}")
        self.read_outbox_requests.append(request)
        items: tuple[OutboxTerminalItem, ...] = ()
        if self._outbox_item is not None:
            items = (self._outbox_item,)
        return OutboxTerminalItemsBatch(
            items=items,
            next_cursor=OutboxTerminalCursor(event_sequence=5),
            scanned_watermark=OutboxTerminalCursor(event_sequence=5),
            projection_checkpoint=OutboxTerminalCursor(event_sequence=5),
            projection_status=OutboxProjectionStatus.CAUGHT_UP,
            projection_error_code=None,
            projection_error_message=None,
            has_more=False,
        )

    async def cancel_run(self, run_id: str, request: CancelRunRequest) -> RunSnapshot:
        """记录 cancel_run 请求。

        :param run_id: 目标 Run id。
        :param request: CancelRunRequest。
        :returns: RunSnapshot。
        :raises Exception: watcher 推送失败时向上透传。
        """

        self.calls.append(f"cancel:{run_id}")
        self.cancel_requests.append(request)
        if self._cancel_terminal is not None:
            await self.watchers[-1].push(self._cancel_terminal)
            await asyncio.sleep(0)
        return _run_snapshot(run_id=run_id, status=RunStatus.CANCELLING)


class _ControlledCancelHost(_FakeHost):
    """用显式 barrier 控制 prompt cancel terminal 的 fake Host。"""

    cancel_recorded: asyncio.Event
    release_cancel_terminal: asyncio.Event

    def __init__(self) -> None:
        """初始化 cancel 记录与 terminal 释放 barrier。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(
            submit_terminal=None,
            run_statuses=(RunStatus.RUNNING,),
        )
        self.cancel_recorded = asyncio.Event()
        self.release_cancel_terminal = asyncio.Event()

    async def cancel_run(self, run_id: str, request: CancelRunRequest) -> RunSnapshot:
        """记录 graceful cancel，并在测试释放后推送 canonical terminal。

        :param run_id: 目标 Run id。
        :param request: Host cancel 请求。
        :returns: cancelling Run snapshot。
        :raises asyncio.CancelledError: terminal barrier 等待 task 被取消时透传。
        """

        self.calls.append(f"cancel:{run_id}")
        self.cancel_requests.append(request)
        self.cancel_recorded.set()
        await self.release_cancel_terminal.wait()
        await self.watchers[-1].push(
            _terminal_event(status=HostTerminalStatus.CANCELLED)
        )
        return _run_snapshot(run_id=run_id, status=RunStatus.CANCELLING)


class _DurablyAcceptedDelayedResponseHost(_FakeHost):
    """模拟 Run 已 durable accepted、但 submit response 延迟返回的 Host。"""

    committed: asyncio.Event
    release_response: asyncio.Event

    def __init__(self) -> None:
        """初始化 durable acceptance 与 response barrier。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(
            submit_terminal=None,
            run_statuses=(RunStatus.RUNNING,),
            cancel_terminal=_terminal_event(status=HostTerminalStatus.CANCELLED),
        )
        self.committed = asyncio.Event()
        self.release_response = asyncio.Event()

    async def submit_followup(
        self,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """记录 durable acceptance，并等待测试释放 public response。

        :param session_id: 目标 Session id。
        :param request: SubmitFollowupRequest。
        :returns: accepted Run 的 FollowupSnapshot。
        :raises asyncio.CancelledError: response barrier 被取消时透传。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        self.committed.set()
        await self.release_response.wait()
        return FollowupSnapshot(
            accepted_input_ref="input-1",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id="run-1",
            accepted_run_status=RunStatus.RUNNING,
            command_watermark=HostStreamCursor(event_sequence=1),
            queued_run_id=None,
            target_run_id=None,
        )


class _DelayedTerminalHost(_FakeHost):
    """submit accepted 后延迟推送 terminal 的 fake Host。"""

    _terminal_delay_ticks: int

    def __init__(
        self,
        *,
        submit_terminal: HostEvent,
        terminal_delay_ticks: int,
    ) -> None:
        """初始化 delayed terminal fake Host。

        :param submit_terminal: 延迟推送到 watcher 的 terminal event。
        :param terminal_delay_ticks: 推送 terminal 前等待的 event loop tick 数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(
            submit_terminal=submit_terminal,
            run_statuses=(RunStatus.RUNNING,),
        )
        self._terminal_delay_ticks = terminal_delay_ticks

    async def submit_followup(self, session_id: str, request: SubmitFollowupRequest) -> FollowupSnapshot:
        """记录 submit 并在后台延迟推送 terminal。

        :param session_id: 目标 Session id。
        :param request: SubmitFollowupRequest。
        :returns: FollowupSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        asyncio.create_task(self._push_terminal_after_delay())
        return FollowupSnapshot(
            accepted_input_ref="input-1",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id="run-1",
            accepted_run_status=RunStatus.RUNNING,
            command_watermark=HostStreamCursor(event_sequence=1),
            queued_run_id=None,
            target_run_id=None,
        )

    async def _push_terminal_after_delay(self) -> None:
        """等待预设 tick 后推送 terminal。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        for _tick_index in range(self._terminal_delay_ticks):
            await asyncio.sleep(0)
        if self._submit_terminal is not None:
            await self.watchers[-1].push(self._submit_terminal)


class _FakeOpenHostContext:
    """fake open_host async context manager。"""

    host: _FakeHost
    exit_count: int

    def __init__(self, host: _FakeHost) -> None:
        """初始化 fake context manager。

        :param host: fake Host。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.host = host
        self.exit_count = 0

    async def __aenter__(self) -> Host:
        """返回 fake Host public handle。

        :returns: fake Host。
        :raises Exception: 不主动抛出异常。
        """

        return cast(Host, self.host)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """退出 fake context manager。

        :param exc_type: 异常类型。
        :param exc_value: 异常值。
        :param traceback: traceback。
        :returns: ``None`` 表示不吞异常。
        :raises Exception: 不主动抛出异常。
        """

        self.exit_count += 1
        return None


class _FixedOpenHostFactory:
    """始终返回同一 fake Host context 的 opener factory。"""

    context: _FakeOpenHostContext

    def __init__(self, context: _FakeOpenHostContext) -> None:
        """保存待返回的 fake context。

        :param context: 每次调用应返回的 fake Host context。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.context = context

    def __call__(self, _options: OpenHostOptions) -> _FakeOpenHostContext:
        """返回预先提供的 fake Host context。

        :param _options: Host opener options；测试不消费。
        :returns: 固定 fake Host context。
        :raises Exception: 不主动抛出异常。
        """

        return self.context


async def _raise_runtime_prepare_startup_interrupt(
    _request: EntrypointRuntimeRequest,
) -> EntrypointRuntimeResult:
    """模拟 prompt runtime prepare 阶段发生 Ctrl+C。

    :param _request: Service runtime prepare 请求；测试不消费。
    :returns: 本函数不会返回。
    :raises KeyboardInterrupt: 始终抛出启动中断。
    """

    raise KeyboardInterrupt


def _raise_host_open_startup_interrupt(_options: OpenHostOptions) -> Never:
    """模拟 Host public opener 建立前发生 Ctrl+C。

    :param _options: Host opener options；测试不消费。
    :returns: 本函数不会返回。
    :raises KeyboardInterrupt: 始终抛出启动中断。
    """

    raise KeyboardInterrupt


async def _raise_session_ensure_startup_interrupt(
    *,
    host: Host,
    args: ParsedCliArgs,
    invocation: CliInvocation,
) -> str:
    """模拟 Host 已打开但 Session ensure 尚未提交时的 Ctrl+C。

    :param host: Host public handle；测试不消费。
    :param args: 已解析 CLI 参数；测试不消费。
    :param invocation: 当前 CLI invocation；测试不消费。
    :returns: 本函数不会返回。
    :raises KeyboardInterrupt: 始终抛出启动中断。
    """

    del host, args, invocation
    raise KeyboardInterrupt


class _InterruptedInstallSigintMonitor(CliSigintMonitor):
    """在 prompt Run cancellation hook 安装阶段模拟 Ctrl+C。"""

    def install(self) -> None:
        """在 handler 完全安装前抛出启动中断。

        :returns: 本方法不会返回。
        :raises KeyboardInterrupt: 始终抛出启动中断。
        """

        raise KeyboardInterrupt


def test_prompt_startup_interrupt_during_runtime_prepare_has_no_business_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """runtime prepare 中断必须由公共 bootstrap 收敛且不打开 Host。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest argv、环境与函数替换夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 退出码、输出或零业务状态 contract 失败时抛出。
    """

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        sys,
        "argv",
        ["dayu-cli", "prompt", "--base", str(tmp_path), "请总结收入变化"],
    )
    monkeypatch.setattr(
        session_execution,
        "prepare_entrypoint_runtime",
        _raise_runtime_prepare_startup_interrupt,
    )
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        _raise_host_open_startup_interrupt,
    )

    assert run_module() == EXIT_KEYBOARD_INTERRUPT
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert not (tmp_path / ".dayu" / "host" / "dayu_host.sqlite3").exists()


@pytest.mark.parametrize(
    ("exit_code", "expected_mask_count"),
    ((EXIT_KEYBOARD_INTERRUPT, 1), (EXIT_SUCCESS, 0)),
)
def test_process_exit_masks_only_canonical_keyboard_interrupt_teardown(
    exit_code: int,
    expected_mask_count: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """进程收尾只能在 canonical 130 后屏蔽后续 SIGINT。

    :param exit_code: 模拟 application 已确定的退出码。
    :param expected_mask_count: 预期安装 ``SIG_IGN`` 的次数。
    :param monkeypatch: pytest 函数与 signal 替换夹具。
    :returns: ``None``。
    :raises AssertionError: SystemExit code 或 handler 安装契约漂移时抛出。
    """

    run_module_mock = Mock(return_value=exit_code)
    signal_mock = Mock()
    monkeypatch.setattr(cli_module, "run_module", run_module_mock)
    monkeypatch.setattr(cli_module.signal, "signal", signal_mock)

    with pytest.raises(SystemExit) as captured:
        cli_module.exit_module()

    assert captured.value.code == exit_code
    assert signal_mock.call_count == expected_mask_count
    if expected_mask_count == 1:
        signal_mock.assert_called_once_with(signal.SIGINT, signal.SIG_IGN)


def test_prompt_startup_interrupt_during_host_open_has_no_host_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Host opener 建立前中断必须退出 130 且不创建 Host durable state。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest argv、环境与函数替换夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 退出码、输出或 Host 文件副作用不符合 contract 时抛出。
    """

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        sys,
        "argv",
        ["dayu-cli", "prompt", "--base", str(tmp_path), "请总结收入变化"],
    )
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        _raise_host_open_startup_interrupt,
    )

    assert run_module() == EXIT_KEYBOARD_INTERRUPT
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert not (tmp_path / ".dayu" / "host" / "dayu_host.sqlite3").exists()


def test_prompt_startup_interrupt_before_session_commit_closes_host_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Session ensure 提交前中断必须关闭 Host context 且无业务调用。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest argv、环境与函数替换夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: cleanup、零调用、退出码或输出 contract 失败时抛出。
    """

    fake_host = _FakeHost(submit_terminal=None)
    host_context = _FakeOpenHostContext(fake_host)
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        sys,
        "argv",
        ["dayu-cli", "prompt", "--base", str(tmp_path), "请总结收入变化"],
    )
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        _FixedOpenHostFactory(host_context),
    )
    monkeypatch.setattr(
        prompt_command,
        "_ensure_prompt_session",
        _raise_session_ensure_startup_interrupt,
    )

    assert run_module() == EXIT_KEYBOARD_INTERRUPT
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert host_context.exit_count == 1
    assert fake_host.calls == []
    assert fake_host.create_requests == []
    assert fake_host.ensure_requests == []
    assert fake_host.submit_requests == []


def test_prompt_startup_interrupt_during_monitor_install_closes_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run monitor 安装中断必须关闭 attachment/context 且不得 submit Run。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest argv、环境与类替换夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: cleanup、Run 零创建、退出码或输出 contract 失败时抛出。
    """

    fake_host = _FakeHost(submit_terminal=None)
    host_context = _FakeOpenHostContext(fake_host)
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        sys,
        "argv",
        ["dayu-cli", "prompt", "--base", str(tmp_path), "请总结收入变化"],
    )
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        _FixedOpenHostFactory(host_context),
    )
    monkeypatch.setattr(
        prompt_command,
        "CliSigintMonitor",
        _InterruptedInstallSigintMonitor,
    )

    assert run_module() == EXIT_KEYBOARD_INTERRUPT
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert host_context.exit_count == 1
    assert len(fake_host.create_requests) == 1
    assert fake_host.ensure_requests == []
    assert fake_host.submit_requests == []
    assert fake_host.cancel_requests == []
    assert fake_host.attach_session_ids == ["session-1"]
    assert [attachment.close_count for attachment in fake_host.attachments] == [1]


class _AutoSigintMonitor(CliSigintMonitor):
    """测试用自动 SIGINT monitor。"""

    def install(self) -> None:
        """测试中不安装真实 OS signal handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return

    def close(self) -> None:
        """测试中无需恢复 OS signal handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return

    async def wait_next(self, observed_count: int) -> int:
        """等待 submit callback 有机会记录 run id 后触发两次 SIGINT。

        :param observed_count: 已观察到的 SIGINT 计数。
        :returns: 新的 SIGINT 计数。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        if self.count <= observed_count:
            self.notify()
            self.notify()
        return self.count


class _NoopSigintMonitor(CliSigintMonitor):
    """测试用不触发 SIGINT monitor。"""

    def install(self) -> None:
        """测试中不安装真实 OS signal handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return

    def close(self) -> None:
        """测试中无需恢复 OS signal handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return

    async def wait_next(self, observed_count: int) -> int:
        """一直等待下一次 SIGINT，直到调用方取消等待任务。

        :param observed_count: 已观察到的 SIGINT 计数。
        :returns: 正常路径不会返回。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        await asyncio.Event().wait()
        return observed_count


class _ControlledSigintMonitor(CliSigintMonitor):
    """允许测试在 handler 安装后精确注入 SIGINT 的 monitor。"""

    installed: asyncio.Event
    closed_count: int

    def __init__(self) -> None:
        """初始化安装 barrier 与关闭计数。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.installed = asyncio.Event()
        self.closed_count = 0

    def install(self) -> None:
        """测试中不安装真实 OS signal handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.installed.set()

    def close(self) -> None:
        """记录 prompt lifecycle 已移除 SIGINT handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count += 1


class _FakeRunningKeyMonitor:
    """测试用运行态按键 monitor。"""

    started_count: int
    closed_count: int
    _actions: tuple[RunningKeyAction, ...]
    _action_index: int
    _closed_event: asyncio.Event
    _delay_ticks: int

    def __init__(
        self,
        actions: tuple[RunningKeyAction, ...],
        *,
        delay_ticks: int = 0,
    ) -> None:
        """初始化 fake monitor。

        :param actions: 依次返回的运行态按键动作。
        :param delay_ticks: 返回每个动作前等待的 event loop tick 数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.started_count = 0
        self.closed_count = 0
        self._actions = actions
        self._action_index = 0
        self._closed_event = asyncio.Event()
        self._delay_ticks = delay_ticks

    def start(self) -> None:
        """记录 monitor 启动。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.started_count += 1

    async def wait_next(self) -> RunningKeyAction:
        """返回下一条预设按键动作。

        :returns: 运行态按键动作。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        for _tick_index in range(self._delay_ticks):
            await asyncio.sleep(0)
        if self._action_index < len(self._actions):
            action = self._actions[self._action_index]
            self._action_index += 1
            return action
        await self._closed_event.wait()
        raise asyncio.CancelledError

    def close(self) -> None:
        """记录 monitor 关闭。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count += 1
        self._closed_event.set()


def test_prompt_command_outputs_fast_live_terminal_and_converts_requests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt 命令应经 Service helper 提交并输出 live final answer。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        submit_events=(_activity_event(),),
    )
    captured_requests: list[EntrypointRuntimeRequest] = []
    real_prepare = session_execution.prepare_entrypoint_runtime

    async def capture_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """捕获 CLI 传给 Service helper 的 runtime request。"""

        captured_requests.append(request)
        return await real_prepare(request)

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(session_execution, "prepare_entrypoint_runtime", capture_prepare)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(
        (
            "prompt",
            "--base",
            str(workspace_root),
            "--ticker",
            " AAPL ",
            "--label",
            "earnings",
            "--model",
            _MODEL_ID,
            "--temperature",
            "0.2",
            "请总结收入变化",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "prompt answer"
    assert "Activity:" in captured.err
    assert "工具批次完成" in captured.err
    assert captured_requests[0].scene_id == "prompt"
    assert captured_requests[0].explicit_config_dir is None
    assert captured_requests[0].context_slot_values["fins_default_subject"] == "# 当前分析对象\n你正在分析的是 AAPL。"
    assert "Asia/Shanghai" in str(captured_requests[0].context_slot_values["current_time"])
    assert captured_requests[0].assembly_overrides.model_id == _MODEL_ID
    assert fake_host.ensure_requests[0].scope == "cli.agent"
    assert fake_host.ensure_requests[0].slot_key == "cli.agent.earnings"
    assert fake_host.calls[:3] == ["ensure_session", "watch:session-1", "submit:session-1"]
    assert fake_host.attach_session_ids == ["session-1"]
    assert [attachment.close_count for attachment in fake_host.attachments] == [1]
    submit_request = fake_host.submit_requests[0]
    assert submit_request.user_prompt == "请总结收入变化"
    assert submit_request.tool_names is not None
    assert _DEFAULT_PROMPT_TOOL_NAME in submit_request.tool_names
    assert _DEFAULT_TIME_TOOL_NAME not in submit_request.tool_names
    assert _EXCLUDED_UPLOAD_TOOL_NAME not in submit_request.tool_names
    assert submit_request.runner_options is not None
    assert submit_request.runner_options.temperature == 0.2
    assert submit_request.agent_policy is not None
    assert submit_request.context.request_id != submit_request.client_request_id
    assert submit_request.context.operation_context.business_object_id == "AAPL"


def test_prompt_command_ticker_uses_fmp_company_name_when_resolved(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt --ticker 应捕获带公司名的 LLM-facing subject slot。"""

    fake_host = _FakeHost(submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED))
    captured_requests: list[EntrypointRuntimeRequest] = []
    real_prepare = session_execution.prepare_entrypoint_runtime

    async def capture_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """捕获 runtime request。"""

        captured_requests.append(request)
        return await real_prepare(request)

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setenv("FMP_API_KEY", "test-fmp-key")
    monkeypatch.setattr(scene_context, "FmpCompanyInfoResolver", _FakePromptFmpResolver)
    monkeypatch.setattr(session_execution, "prepare_entrypoint_runtime", capture_prepare)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(tmp_path), "--ticker", "V", "请总结"))

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out.strip() == "prompt answer"
    assert (
        captured_requests[0].context_slot_values["fins_default_subject"]
        == "# 当前分析对象\n你正在分析的是 V（Visa Inc.）。"
    )


@pytest.mark.asyncio
async def test_prompt_existing_session_execution_does_not_create_or_ensure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt existing-session 入口只能在指定 Session 上 submit。

    :param tmp_path: pytest 临时目录夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: helper 调用了 create / ensure 或 submit 目标错误时抛出。
    """

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    args = parse_cli_args(
        (
            "session",
            "resume",
            "--session-id",
            "session-existing",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "请继续分析",
        )
    )
    prepared = await session_execution.prepare_prompt_session_execution(
        args,
        command_name="session",
        scenario="prompt",
        user_prompt="请继续分析",
        ticker=None,
        context_slot_values=prompt_command.build_prompt_context_slot_values(
            ticker=None,
            fmp_api_key=_API_KEY,
        ),
        usage_error_factory=prompt_command.CliCommandUsageError,
    )
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        submit_events=(_activity_event(),),
    )

    exit_code = await session_execution.execute_prompt_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        sigint_monitor=_NoopSigintMonitor(),
    )

    assert exit_code == EXIT_SUCCESS
    assert fake_host.ensure_requests == []
    assert fake_host.create_requests == []
    assert fake_host.calls == ["watch:session-existing", "submit:session-existing"]
    assert fake_host.read_outbox_requests == []
    assert fake_host.submit_requests[0].user_prompt == "请继续分析"
    assert fake_host.submit_requests[0].behavior is FollowupBehavior.QUEUE
    assert fake_host.submit_requests[0].target_run_id is None
    cursor_record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-existing",
    )
    assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=2)
    assert cursor_record.seen_terminal_event_ids == ("terminal-run-1-2",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("terminal_status", "expected_exit_code"),
    (
        (HostTerminalStatus.FAILED, EXIT_FAILURE),
        (HostTerminalStatus.CANCELLED, EXIT_KEYBOARD_INTERRUPT),
        (HostTerminalStatus.LOST, EXIT_FAILURE),
    ),
)
async def test_prompt_existing_session_advances_terminal_cursor_after_rendering_non_success_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: HostTerminalStatus,
    expected_exit_code: int,
) -> None:
    """prompt 已渲染非成功 terminal 后必须推进本地 cursor。

    :param tmp_path: pytest 临时目录夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param terminal_status: 本轮 Host terminal status。
    :param expected_exit_code: renderer policy 产生的 CLI 退出码。
    :returns: ``None``。
    :raises AssertionError: cursor 未推进或退出码被 cursor 逻辑改写时抛出。
    """

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    args = parse_cli_args(
        (
            "session",
            "resume",
            "--session-id",
            "session-existing",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "请继续分析",
        )
    )
    prepared = await session_execution.prepare_prompt_session_execution(
        args,
        command_name="session",
        scenario="prompt",
        user_prompt="请继续分析",
        ticker=None,
        context_slot_values=prompt_command.build_prompt_context_slot_values(
            ticker=None,
            fmp_api_key=_API_KEY,
        ),
        usage_error_factory=prompt_command.CliCommandUsageError,
    )
    fake_host = _FakeHost(submit_terminal=_terminal_event(status=terminal_status))

    exit_code = await session_execution.execute_prompt_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        sigint_monitor=_NoopSigintMonitor(),
    )

    cursor_record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-existing",
    )
    assert exit_code == expected_exit_code
    assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=2)
    assert cursor_record.seen_terminal_event_ids == ("terminal-run-1-2",)


@pytest.mark.asyncio
async def test_prompt_cursor_write_failure_propagates_after_terminal_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt 已渲染 terminal 后 cursor 写失败必须作为本地投递错误传播。

    :param tmp_path: pytest 临时目录夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: cursor 异常被吞掉或改写成 renderer 退出码时抛出。
    """

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        session_execution,
        "advance_cli_terminal_cursor",
        _raise_cli_terminal_cursor_error,
    )
    args = parse_cli_args(
        (
            "session",
            "resume",
            "--session-id",
            "session-existing",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "请继续分析",
        )
    )
    prepared = await session_execution.prepare_prompt_session_execution(
        args,
        command_name="session",
        scenario="prompt",
        user_prompt="请继续分析",
        ticker=None,
        context_slot_values=prompt_command.build_prompt_context_slot_values(
            ticker=None,
            fmp_api_key=_API_KEY,
        ),
        usage_error_factory=prompt_command.CliCommandUsageError,
    )
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.FAILED),
    )

    with pytest.raises(CliTerminalCursorError, match="cursor write failed"):
        await session_execution.execute_prompt_on_session(
            host=cast(Host, fake_host),
            prepared=prepared,
            session_id="session-existing",
            sigint_monitor=_NoopSigintMonitor(),
        )


def test_prompt_host_api_error_uses_structured_presentation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt 首次 create 阶段 HostApiError 必须结构化展示并返回 failure。"""

    fake_host = _FakeHost(
        submit_terminal=None,
        create_error=HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="workspace session root missing",
            retryable=False,
        ),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(tmp_path), "hello"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "dayu-cli prompt" in captured.err
    assert "host_code=not_found" in captured.err
    assert "host_message=workspace session root missing" in captured.err
    assert fake_host.calls == ["create_session"]


@pytest.mark.parametrize("log_flag", ("--verbose", "--debug", "--debug-stream"))
def test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout(
    log_flag: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt verbose/debug 诊断不得写入 stdout 用户结果通道。

    :param log_flag: 待验证的全局日志 flag。
    :param tmp_path: pytest 临时目录夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: stdout 被诊断日志污染时抛出。
    """

    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        submit_events=(_activity_event(),),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(
        (
            log_flag,
            "prompt",
            "--base",
            str(tmp_path),
            "请总结收入变化",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "prompt answer"
    assert "[VERBOSE]" not in captured.out
    assert "[DEBUG]" not in captured.out
    assert "Activity:" not in captured.out
    assert "Activity:" in captured.err


def test_prompt_command_without_ticker_uses_default_context_slots(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未传 ticker 时 prompt command 应填充默认 LLM-facing slots。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED))
    captured_requests: list[EntrypointRuntimeRequest] = []
    real_prepare = session_execution.prepare_entrypoint_runtime

    async def capture_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """捕获 runtime request。"""

        captured_requests.append(request)
        return await real_prepare(request)

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(session_execution, "prepare_entrypoint_runtime", capture_prepare)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(workspace_root), "请总结收入变化"))

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out.strip() == "prompt answer"
    assert captured_requests[0].context_slot_values["fins_default_subject"] == ""
    assert "未指定具体公司" not in str(captured_requests[0].context_slot_values)
    assert "Asia/Shanghai" in str(captured_requests[0].context_slot_values["current_time"])
    assert fake_host.create_requests[0].bind_slot is False
    assert fake_host.submit_requests[0].context.operation_context.business_object_id is None


def test_prompt_command_uses_init_generated_workspace_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt entrypoint 必须使用 init 在 workspace root 下生成的 config。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: prompt 未使用 init 生成配置或路径嵌套时抛出。
    """

    workspace_root = tmp_path / "workspace"
    monkeypatch.setattr(
        builtins,
        "input",
        Mock(side_effect=("14", "", "", "")),
    )
    monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())
    monkeypatch.setattr(
        getpass,
        "getpass",
        Mock(side_effect=("", "", "", "", "")),
    )
    assert cli_main.main(("init", "--base", str(workspace_root))) == EXIT_SUCCESS
    capsys.readouterr()
    fake_host = _FakeHost(submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED))
    captured_results: list[EntrypointRuntimeResult] = []
    real_prepare = session_execution.prepare_entrypoint_runtime

    async def capture_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """捕获 runtime assembly 结果。

        :param request: CLI 传给 Service 的 runtime request。
        :returns: 真实 prepare 结果。
        :raises Exception: 真实 prepare 失败时透传。
        """

        result = await real_prepare(request)
        captured_results.append(result)
        return result

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(session_execution, "prepare_entrypoint_runtime", capture_prepare)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(workspace_root), "请总结收入变化"))

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out.strip() == "prompt answer"
    assert captured_results[0].locations.config_overlay_dir == workspace_root / "config"
    assert captured_results[0].host_assembly.options.db_path == (
        workspace_root / ".dayu" / "host" / "dayu_host.sqlite3"
    ).resolve(strict=False)
    assert not (workspace_root / "workspace").exists()


def test_prompt_command_uses_outbox_fallback_when_watcher_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """watcher 断线时 prompt command 应通过 public outbox fallback 输出。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(
        submit_terminal=None,
        submit_watcher_errors=(
            HostApiError(
                code=HostApiErrorCode.DELIVERY_INTERRUPTED,
                message="delivery interrupted",
                retryable=False,
                detail=HostSessionEventDeliveryDetail(
                    reason=(HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW)
                ),
            ),
        ),
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_item=_outbox_item(),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(workspace_root), "请总结收入变化"))

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out.strip() == "prompt answer"
    assert fake_host.read_outbox_requests[0].after == OutboxTerminalCursor(event_sequence=0)
    assert fake_host.read_outbox_requests[0].limit == 50


def test_prompt_default_detail_outputs_activity_and_keeps_final_answer_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt 默认显示 activity，final answer 仍只写 stdout。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        submit_events=(_activity_event(),),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(workspace_root), "请总结收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "prompt answer"
    assert "Activity:" in captured.err
    assert "工具批次完成" in captured.err
    assert "记录烟测事实" in captured.err


def test_prompt_no_detail_suppresses_activity_and_keeps_final_answer_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--no-detail`` 不注册 activity renderer，final answer 仍只写 stdout。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        submit_events=(_activity_event(),),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(workspace_root), "--no-detail", "请总结收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "prompt answer"
    assert "Activity:" not in captured.err
    assert "工具批次完成" not in captured.err
    assert "记录烟测事实" not in captured.err


def test_prompt_thinking_flag_outputs_reasoning_delta_and_no_thinking_suppresses_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有 thinking event 时，``--thinking`` 与 ``--no-thinking`` 输出必须不同。"""

    workspace_root = tmp_path
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(
            _FakeHost(
                submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
                submit_events=(_thinking_event(),),
            )
        ),
    )

    thinking_exit = cli_main.main(("prompt", "--base", str(workspace_root), "--thinking", "请总结收入变化"))
    thinking_captured = capsys.readouterr()

    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(
            _FakeHost(
                submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
                submit_events=(_thinking_event(),),
            )
        ),
    )
    no_thinking_exit = cli_main.main(("prompt", "--base", str(workspace_root), "--no-thinking", "请总结收入变化"))
    no_thinking_captured = capsys.readouterr()

    assert thinking_exit == EXIT_SUCCESS
    assert no_thinking_exit == EXIT_SUCCESS
    assert thinking_captured.out.strip() == "prompt answer"
    assert no_thinking_captured.out.strip() == "prompt answer"
    assert "Thinking: 正在分析收入变化" in thinking_captured.err
    assert "Thinking:" not in no_thinking_captured.err


def test_prompt_detail_outputs_activity_for_non_tty_and_keeps_final_answer_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 ``--detail`` 应在非 TTY 捕获流下输出 activity。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        submit_events=(_activity_event(),),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(workspace_root), "--detail", "请总结收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "prompt answer"
    assert "Activity:" in captured.err
    assert "工具批次完成" in captured.err
    assert "记录烟测事实" in captured.err
    assert "[VERBOSE]" not in captured.err
    assert "[DEBUG]" not in captured.err


def test_prompt_detail_activity_does_not_enter_log_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--detail`` activity 属于 UI 输出，不写入 ``--log-file``。"""

    workspace_root = tmp_path
    log_file = tmp_path / "dayu.log"
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        submit_events=(_activity_event(),),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(
        (
            "prompt",
            "--base",
            str(workspace_root),
            "--detail",
            "--log-file",
            str(log_file),
            "请总结收入变化",
        )
    )
    captured = capsys.readouterr()
    log_content = log_file.read_text(encoding="utf-8")

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "prompt answer"
    assert "Activity:" in captured.err
    assert "Activity:" not in log_content
    assert "工具批次完成" not in log_content


@pytest.mark.asyncio
async def test_prompt_tty_runtime_display_closes_thinking_before_activity_and_final(
    tmp_path: Path,
) -> None:
    """TTY prompt 应在 activity 前闭合 thinking，并在 final 前清理运行态展示。"""

    runtime = await _prepare_prompt_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="prompt",
        scenario="prompt",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    terminal_columns = 40
    stream = io.StringIO()
    activity_renderer = CliActivityRenderer(
        stderr=stream,
        options=CliActivityRendererOptions(
            visible=True,
            enabled=True,
            terminal_control=True,
            terminal_columns=terminal_columns,
        ),
    )
    thinking_renderer = CliThinkingRenderer(
        stderr=stream,
        options=CliThinkingRendererOptions(
            enabled=True,
            terminal_control=True,
            terminal_columns=terminal_columns,
        ),
    )
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        submit_events=(
            _activity_event_with_sequence(
                event_sequence=1,
                dedupe_key="activity-long",
                title="工具批次完成并生成较长运行态展示",
                summary="这一条 activity 故意足够长，用于覆盖终端软换行后的多屏幕行清理。",
            ),
            _thinking_event_with_sequence(
                runtime_sequence=2,
                dedupe_key="thinking-1",
                text_delta="The user is asking",
            ),
            _activity_event_with_sequence(
                event_sequence=3,
                dedupe_key="activity-tool",
                title="工具调用完成",
                summary="tool activity",
            ),
        ),
    )

    terminal = await session_execution._submit_prompt_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        user_prompt="请总结收入变化",
        run_overrides=ServiceRunOverrides(),
        sigint_monitor=_NoopSigintMonitor(),
        activity_renderer=activity_renderer,
        thinking_renderer=thinking_renderer,
    )

    assert terminal is not None
    render_exit_code = render_prompt_terminal_result(
        terminal,
        stdout=stream,
        stderr=stream,
    )

    output = stream.getvalue()
    final_answer_index = output.index("prompt answer")
    last_activity_index = output.rfind("Activity:", 0, final_answer_index)
    last_thinking_index = output.rfind("Thinking:", 0, final_answer_index)
    last_clear_index = output.rfind("\x1b[2K", 0, final_answer_index)
    assert render_exit_code == EXIT_SUCCESS
    assert "Thinking: The user is asking\r\x1b[2KActivity:" in output
    assert output.count("\x1b[1A\r\x1b[2K") >= 3
    assert last_clear_index > last_activity_index
    assert last_clear_index > last_thinking_index
    assert output.endswith("prompt answer\n")


@pytest.mark.asyncio
async def test_prompt_display_domain_construction_failure_precedes_host_attach(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """私有 execution domain 构造失败必须在 Host attach/submit 前原样传播。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises Exception: construction ordering 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_prompt_runtime(tmp_path)
    domain_error = RuntimeError("display domain construction failed")
    fake_host = _FakeHost(submit_terminal=None)

    def fail_domain_construction(
        *,
        activity_display: RuntimeActivityDisplay | None,
        thinking_display: RuntimeThinkingDisplay | None,
    ) -> RuntimeDisplayController:
        """模拟私有 executor 构造失败。

        :param activity_display: caller 已构造的 activity renderer。
        :param thinking_display: caller 已构造的 thinking renderer。
        :returns: 本函数不返回。
        :raises RuntimeError: 原样抛出固定构造失败。
        """

        del activity_display, thinking_display
        raise domain_error

    monkeypatch.setattr(
        session_execution,
        "RuntimeDisplayController",
        fail_domain_construction,
    )

    with pytest.raises(
        RuntimeError,
        match="display domain construction failed",
    ) as exc_info:
        await session_execution._submit_prompt_turn_handling_sigint(
            host=cast(Host, fake_host),
            runtime=runtime,
            invocation=session_execution.new_cli_invocation(
                command_name="prompt",
                scenario="prompt",
                display_user="本地 CLI 用户",
                ticker="AAPL",
            ),
            session_id="session-1",
            user_prompt="请总结收入变化",
            run_overrides=ServiceRunOverrides(),
            sigint_monitor=_NoopSigintMonitor(),
            activity_renderer=CliActivityRenderer(
                stderr=io.StringIO(),
                options=CliActivityRendererOptions(
                    visible=True,
                    enabled=True,
                ),
            ),
        )

    assert exc_info.value is domain_error
    assert fake_host.calls == []


@pytest.mark.asyncio
async def test_prompt_sigint_after_run_id_cancels_host_run(
    tmp_path: Path,
) -> None:
    """Run accepted 后 SIGINT 应构造完整 CancelRunRequest 并复用幂等 id。"""

    workspace_root = tmp_path
    runtime = await session_execution.prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root(),
            explicit_config_dir=None,
            scene_id="prompt",
            context_slot_values={
                "fins_default_subject": "# 当前分析对象\n你正在分析的是 AAPL。",
                "current_time": _PROMPT_CURRENT_TIME_TEXT,
            },
            assembly_overrides=ServiceAssemblyOverrides(model_id=_MODEL_ID),
            env=_runtime_assembly_env(),
        )
    )
    invocation = session_execution.new_cli_invocation(
        command_name="prompt",
        scenario="prompt",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost(
        submit_terminal=None,
        run_statuses=(RunStatus.RUNNING,),
        cancel_terminal=_terminal_event(status=HostTerminalStatus.CANCELLED),
    )

    result = await session_execution._submit_prompt_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        user_prompt="请总结收入变化",
        run_overrides=ServiceRunOverrides(),
        sigint_monitor=_AutoSigintMonitor(),
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.CANCELLED
    assert len(fake_host.cancel_requests) == 1
    cancel_request = fake_host.cancel_requests[0]
    assert cancel_request.reason == "cli_sigint"
    assert cancel_request.mode is CancelMode.GRACEFUL
    assert cancel_request.client_request_id.endswith(":turn-1:run-run-1:cancel:cli_sigint")
    assert cancel_request.context.operation_context.operation_name == ("dayu_cli.prompt.cancel_run")
    assert fake_host.calls[0:2] == ["watch:session-1", "submit:session-1"]
    assert fake_host.calls[-2:] == ["watch:session-1", "cancel:run-1"]


@pytest.mark.asyncio
async def test_prompt_cancel_helper_closes_thinking_renderer() -> None:
    """prompt 本地取消 helper 应先收尾，并由 caller 关闭 thinking renderer。"""

    accepted_run = session_execution._PromptAcceptedRunState()
    submit_task = asyncio.create_task(_never_finishes_prompt_terminal())
    stderr = io.StringIO()
    thinking_renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )
    thinking_renderer.record(
        _entrypoint_thinking(
            dedupe_key="thinking-before-cancel",
            text_delta="The user is asking",
        )
    )
    fake_host = _FakeHost(
        submit_terminal=None,
    )
    runtime_display = RuntimeDisplayController(
        activity_display=None,
        thinking_display=thinking_renderer,
    )

    result = await session_execution._cancel_prompt_turn_after_local_request(
        host=cast(Host, fake_host),
        invocation=session_execution.new_cli_invocation(
            command_name="prompt",
            scenario="prompt",
            display_user="本地 CLI 用户",
            ticker="AAPL",
        ),
        accepted_run=accepted_run,
        submit_task=submit_task,
        runtime_display=runtime_display,
    )

    assert result is None
    assert fake_host.cancel_requests == []
    assert stderr.getvalue() == "Thinking: The user is asking\n"
    thinking_renderer.record(_entrypoint_thinking(dedupe_key="thinking-after-cancel"))
    assert stderr.getvalue() == "Thinking: The user is asking\n"
    await runtime_display.aclose()


@pytest.mark.asyncio
async def test_prompt_cancel_returns_submit_terminal_completed_during_finish() -> None:
    """finish-thinking 窗口自然完成时应保留 live terminal 且不发 Host cancel。

    :returns: ``None``。
    :raises Exception: prompt cancel 仲裁、identity 或 cleanup 断言失败时抛出。
    """

    accepted_run = session_execution._PromptAcceptedRunState()
    accepted_run.record("run-1")
    terminal = _entrypoint_terminal_result()
    submit_release = asyncio.Event()
    submit_task = asyncio.create_task(
        _complete_prompt_terminal_after_release(submit_release, terminal)
    )
    thinking_display = _BlockingFinishThinkingDisplay()
    runtime_display = RuntimeDisplayController(
        activity_display=None,
        thinking_display=thinking_display,
    )
    fake_host = _FakeHost(submit_terminal=None)
    cancel_task = asyncio.create_task(
        session_execution._cancel_prompt_turn_after_local_request(
            host=cast(Host, fake_host),
            invocation=session_execution.new_cli_invocation(
                command_name="prompt",
                scenario="prompt",
                display_user="本地 CLI 用户",
                ticker="AAPL",
            ),
            accepted_run=accepted_run,
            submit_task=submit_task,
            runtime_display=runtime_display,
        )
    )

    try:
        await asyncio.wait_for(
            _wait_for_thread_event(thinking_display.finish_started),
            timeout=_TEST_ASYNC_TIMEOUT_SECONDS,
        )
        assert submit_task.done() is False
        submit_release.set()
        observed_terminal = await asyncio.wait_for(
            asyncio.shield(submit_task),
            timeout=_TEST_ASYNC_TIMEOUT_SECONDS,
        )
        assert observed_terminal is terminal
        thinking_display.release_finish.set()
        result = await asyncio.wait_for(
            cancel_task,
            timeout=_TEST_ASYNC_TIMEOUT_SECONDS,
        )
    finally:
        thinking_display.release_finish.set()
        if not cancel_task.done():
            cancel_task.cancel()
            with suppress(asyncio.CancelledError):
                await cancel_task
        await runtime_display.aclose()

    assert result is terminal
    assert result is not None
    assert result.source is EntrypointTerminalSource.LIVE_EVENT
    assert result.terminal_event_id == "terminal-run-1-finish-race"
    assert fake_host.cancel_requests == []
    assert thinking_display.close_count == 1


@pytest.mark.asyncio
async def test_prompt_terminal_surfaces_display_close_failure_from_caller_lifecycle(
    tmp_path: Path,
) -> None:
    """无业务 primary 时 prompt caller 必须原样传播 display close failure。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: caller lifecycle owner contract 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_prompt_runtime(tmp_path)
    close_error = RuntimeError("prompt display close failed")
    renderer = _CloseFailingActivityRenderer(close_error)
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
    )

    with pytest.raises(RuntimeError, match="prompt display close failed") as exc_info:
        await session_execution._submit_prompt_turn_handling_sigint(
            host=cast(Host, fake_host),
            runtime=runtime,
            invocation=session_execution.new_cli_invocation(
                command_name="prompt",
                scenario="prompt",
                display_user="本地 CLI 用户",
                ticker="AAPL",
            ),
            session_id="session-1",
            user_prompt="请总结收入变化",
            run_overrides=ServiceRunOverrides(),
            sigint_monitor=_NoopSigintMonitor(),
            activity_renderer=renderer,
        )

    assert exc_info.value is close_error
    assert renderer.close_count == 1
    assert fake_host.cancel_requests == []
    assert fake_host.watchers[0].closed_count == 1


def test_session_execution_appends_later_cleanup_error_to_existing_cause_chain() -> None:
    """共享 lifecycle owner 必须保留首错并把后续 cleanup 错误追加到链尾。

    :returns: ``None``。
    :raises AssertionError: 首错 identity 或既有 cause 顺序被改写时抛出。
    """

    primary_error = RuntimeError("primary cleanup failed")
    existing_cause = ValueError("existing cleanup cause")
    later_error = OSError("later cleanup failed")
    primary_error.__cause__ = existing_cause

    combined_error = session_execution._combine_lifecycle_cleanup_errors(
        primary_error,
        later_error,
    )

    assert combined_error is primary_error
    assert primary_error.__cause__ is existing_cause
    assert existing_cause.__cause__ is later_error


@pytest.mark.asyncio
async def test_prompt_ctrl_t_toggles_running_activity_without_cancel(
    tmp_path: Path,
) -> None:
    """运行态 Ctrl+T 应切换 activity 可见性，且不发 Host cancel。"""

    runtime = await _prepare_prompt_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="prompt",
        scenario="prompt",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _DelayedTerminalHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED),
        terminal_delay_ticks=4,
    )
    key_monitor = _FakeRunningKeyMonitor((RunningKeyAction.TOGGLE_ACTIVITY,))
    renderer = CliActivityRenderer(
        stderr=io.StringIO(),
        options=CliActivityRendererOptions(visible=True, enabled=False),
    )

    result = await session_execution._submit_prompt_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        user_prompt="请总结收入变化",
        run_overrides=ServiceRunOverrides(),
        sigint_monitor=_NoopSigintMonitor(),
        activity_renderer=renderer,
        key_monitor=key_monitor,
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.SUCCEEDED
    assert renderer.visible is False
    assert fake_host.cancel_requests == []
    assert key_monitor.started_count == 1
    assert key_monitor.closed_count == 1


@pytest.mark.asyncio
async def test_prompt_esc_requests_cancel_after_run_id(
    tmp_path: Path,
) -> None:
    """运行态 Esc 应请求取消当前 accepted Run。"""

    runtime = await _prepare_prompt_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="prompt",
        scenario="prompt",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    stderr = io.StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(
            visible=True,
            enabled=True,
            terminal_control=True,
            terminal_columns=80,
        ),
    )
    thinking_renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(
            enabled=True,
            terminal_control=True,
            terminal_columns=80,
        ),
    )
    key_monitor = _FakeRunningKeyMonitor(
        (RunningKeyAction.CANCEL_RUN,),
        delay_ticks=2,
    )
    fake_host = _FakeHost(
        submit_terminal=None,
        run_statuses=(RunStatus.RUNNING,),
        cancel_terminal=_terminal_event(status=HostTerminalStatus.CANCELLED),
    )
    thinking_renderer.record(
        _entrypoint_thinking(
            dedupe_key="thinking-before-esc",
            text_delta="The user is asking",
        )
    )

    result = await session_execution._submit_prompt_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        user_prompt="请总结收入变化",
        run_overrides=ServiceRunOverrides(),
        sigint_monitor=_NoopSigintMonitor(),
        activity_renderer=renderer,
        thinking_renderer=thinking_renderer,
        key_monitor=key_monitor,
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.CANCELLED
    assert len(fake_host.cancel_requests) == 1
    assert fake_host.cancel_requests[0].mode is CancelMode.GRACEFUL
    assert "Thinking: The user is asking\r\x1b[2KActivity: cancel requested" in (stderr.getvalue())
    thinking_renderer.record(_entrypoint_thinking(dedupe_key="thinking-after-esc"))
    assert stderr.getvalue().count("Thinking:") == 1
    assert key_monitor.closed_count == 1


@pytest.mark.asyncio
async def test_prompt_repeated_sigint_waits_for_cancel_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt 连续 Ctrl+C 必须等待 Host canonical cancel terminal。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest 环境变量替换夹具。
    :returns: ``None``。
    :raises Exception: graceful cancel、terminal 或 cursor 断言失败时抛出。
    """

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    args = parse_cli_args(
        (
            "session",
            "resume",
            "--session-id",
            "session-existing",
            "--mode",
            "prompt",
            "--base",
            str(tmp_path),
            "请总结收入变化",
        )
    )
    prepared = await session_execution.prepare_prompt_session_execution(
        args,
        command_name="session",
        scenario="prompt",
        user_prompt="请总结收入变化",
        ticker=None,
        context_slot_values=prompt_command.build_prompt_context_slot_values(
            ticker=None,
            fmp_api_key=_API_KEY,
        ),
        usage_error_factory=prompt_command.CliCommandUsageError,
    )
    fake_host = _ControlledCancelHost()
    sigint_monitor = _ControlledSigintMonitor()
    execution_task = asyncio.create_task(
        session_execution.execute_prompt_on_session(
            host=cast(Host, fake_host),
            prepared=prepared,
            session_id="session-existing",
            sigint_monitor=sigint_monitor,
        )
    )

    try:
        await asyncio.wait_for(
            sigint_monitor.installed.wait(),
            timeout=_TEST_ASYNC_TIMEOUT_SECONDS,
        )
        sigint_monitor.notify()
        await asyncio.wait_for(
            fake_host.cancel_recorded.wait(),
            timeout=_TEST_ASYNC_TIMEOUT_SECONDS,
        )
        assert execution_task.done() is False
        assert len(fake_host.cancel_requests) == 1

        sigint_monitor.notify()
        assert sigint_monitor.count == 2
        assert execution_task.done() is False
        cursor_before_terminal = await read_cli_terminal_cursor(
            workspace_root=tmp_path,
            session_id="session-existing",
        )
        assert cursor_before_terminal.terminal_cursor == OutboxTerminalCursor(
            event_sequence=0
        )

        fake_host.release_cancel_terminal.set()
        exit_code = await asyncio.wait_for(
            execution_task,
            timeout=_TEST_ASYNC_TIMEOUT_SECONDS,
        )
    finally:
        fake_host.release_cancel_terminal.set()
        if not execution_task.done():
            execution_task.cancel()
            with suppress(asyncio.CancelledError):
                await execution_task

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(fake_host.cancel_requests) == 1
    assert fake_host.cancel_requests[0].mode is CancelMode.GRACEFUL
    assert sigint_monitor.closed_count == 1
    assert fake_host.watchers[-1].closed_count == 1
    cursor_after_terminal = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-existing",
    )
    assert cursor_after_terminal.terminal_cursor == OutboxTerminalCursor(
        event_sequence=2
    )
    assert cursor_after_terminal.seen_terminal_event_ids == ("terminal-run-1-2",)


@pytest.mark.asyncio
async def test_prompt_cancel_terminal_is_returned_after_coalesced_sigint(
    tmp_path: Path,
) -> None:
    """prompt 合并连续 SIGINT 后仍必须返回 Host cancel terminal。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: repeated SIGINT 或 terminal contract 失败时抛出。
    """

    runtime = await _prepare_prompt_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="prompt",
        scenario="prompt",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost(
        submit_terminal=None,
        run_statuses=(RunStatus.RUNNING,),
        cancel_terminal=_terminal_event(status=HostTerminalStatus.CANCELLED),
    )

    result = await session_execution._submit_prompt_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        user_prompt="请总结收入变化",
        run_overrides=ServiceRunOverrides(),
        sigint_monitor=_AutoSigintMonitor(),
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.CANCELLED
    assert len(fake_host.cancel_requests) == 1


@pytest.mark.parametrize(
    "unsupported_args, expected_fragment",
    (
        (("--web-provider", "serper"), "--web-provider"),
        (("--enable-tool-trace",), "--enable-tool-trace"),
        (("--doc-limits-json", "{}"), "--doc-limits-json"),
    ),
)
def test_prompt_command_rejects_removed_execution_flags_as_unknown(
    unsupported_args: tuple[str, ...],
    expected_fragment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """没有 public contract 的旧执行参数必须从 parser surface 删除。"""

    exit_code = cli_main.main(("prompt", *unsupported_args, "请总结收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "unrecognized arguments" in captured.err
    assert expected_fragment in captured.err


def test_prompt_thinking_flags_are_display_options() -> None:
    """``--thinking`` / ``--no-thinking`` 保持为明确的展示选项。

    :returns: ``None``。
    :raises AssertionError: thinking 展示参数未被正确解析时抛出。
    """

    thinking_args = parse_cli_args(("prompt", "hello", "--thinking"))
    no_thinking_args = parse_cli_args(("prompt", "hello", "--no-thinking"))

    assert thinking_args.thinking is True
    assert no_thinking_args.thinking is False


def test_prompt_debug_stream_is_global_log_option() -> None:
    """``--debug-stream`` 保持为全局日志开关。

    :returns: ``None``。
    :raises AssertionError: debug-stream 未被正确解析时抛出。
    """

    args = parse_cli_args(("prompt", "--debug-stream", "请总结收入变化"))

    assert args.debug_stream is True


@pytest.mark.parametrize("removed_args", _REMOVED_PROMPT_DEBUG_OPTIONS)
def test_prompt_removed_debug_options_are_argparse_unknown(
    removed_args: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """已删除 debug 参数应由 argparse 作为未知参数拒绝。

    :param removed_args: 单个已删除 debug 参数及其取值。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 参数未按未知参数返回用法错误时抛出。
    """

    exit_code = cli_main.main(("prompt", *removed_args, "请总结收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "unrecognized arguments" in captured.err
    assert removed_args[0] in captured.err


def test_prompt_command_rejects_all_removed_execution_flags_as_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """所有已删除旧参数都应由 argparse 清晰拒绝。"""

    exit_code = cli_main.main(
        (
            "prompt",
            "--tool-trace-dir",
            "trace",
            "--max-duplicate-tool-calls",
            "2",
            "--duplicate-tool-hint-prompt",
            "hint",
            "--fins-limits-json",
            "{}",
            "请总结收入变化",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "unrecognized arguments" in captured.err
    for expected in (
        "--tool-trace-dir",
        "--max-duplicate-tool-calls",
        "--duplicate-tool-hint-prompt",
        "--fins-limits-json",
    ):
        assert expected in captured.err


def test_prompt_empty_prompt_exits_with_usage_error() -> None:
    """空白 positional prompt 应由 argparse 返回用法错误 2。"""

    assert cli_main.main(("prompt", "")) == EXIT_USAGE_ERROR


def test_prompt_empty_label_exits_with_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空白 label 应在 CLI adapter 层返回用法错误。"""

    fake_host = _FakeHost(submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED))
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(tmp_path), "--label", " ", "请总结收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "--label" in captured.err


def test_prompt_invalid_ticker_exits_with_usage_error_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """非法 ticker 应在 prompt CLI adapter 层返回清晰用法错误。"""

    exit_code = cli_main.main(("prompt", "--base", str(tmp_path), "--ticker", "!@#$", "请总结"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "dayu-cli prompt" in captured.err
    assert "无法识别的 ticker 形态" in captured.err
    assert "!@#$" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


@pytest.mark.asyncio
async def test_prompt_sigint_after_durable_acceptance_waits_response_then_cancels(
    tmp_path: Path,
) -> None:
    """durable accepted 与 callback 之间 SIGINT 必须等待 response 后 canonical cancel。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: acceptance barrier、cancel 或 terminal 断言失败时抛出。
    """

    runtime = await _prepare_prompt_runtime(tmp_path)
    fake_host = _DurablyAcceptedDelayedResponseHost()
    sigint_monitor = _ControlledSigintMonitor()
    execution_task = asyncio.create_task(
        session_execution._submit_prompt_turn_handling_sigint(
            host=cast(Host, fake_host),
            runtime=runtime,
            invocation=session_execution.new_cli_invocation(
                command_name="prompt",
                scenario="prompt",
                display_user="本地 CLI 用户",
                ticker="AAPL",
            ),
            session_id="session-1",
            user_prompt="请总结收入变化",
            run_overrides=ServiceRunOverrides(),
            sigint_monitor=sigint_monitor,
        )
    )
    await fake_host.committed.wait()

    sigint_monitor.notify()
    await asyncio.sleep(0)
    assert execution_task.done() is False
    assert fake_host.cancel_requests == []

    fake_host.release_response.set()
    result = await execution_task

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.CANCELLED
    assert len(fake_host.cancel_requests) == 1
    assert fake_host.cancel_requests[0].mode is CancelMode.GRACEFUL


@pytest.mark.asyncio
async def test_prompt_sigint_monitor_waits_for_notification() -> None:
    """SIGINT monitor wait_next 应等待 notify 并返回新计数。"""

    monitor = CliSigintMonitor()
    wait_task = asyncio.create_task(monitor.wait_next(0))

    await asyncio.sleep(0)
    monitor.notify()

    assert await wait_task == 1


@pytest.mark.asyncio
async def test_prompt_sigint_monitor_restores_previous_process_handler() -> None:
    """关闭 monitor 必须恢复 asyncio runner 已有的进程级 SIGINT handler。

    :returns: ``None``。
    :raises AssertionError: monitor 关闭后 handler identity 漂移时抛出。
    """

    previous_handler = signal.getsignal(signal.SIGINT)
    assert previous_handler is not None
    monitor = CliSigintMonitor()

    monitor.install()
    installed_handler = signal.getsignal(signal.SIGINT)
    assert installed_handler != previous_handler
    monitor.close()

    assert signal.getsignal(signal.SIGINT) == previous_handler


def test_prompt_terminal_failed_outputs_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host FAILED terminal 应输出 error_message 并 exit 1。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(submit_terminal=_terminal_event(status=HostTerminalStatus.FAILED))
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("prompt", "--base", str(workspace_root), "请总结收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert captured.out == ""
    assert "prompt failed" in captured.err


def _session_snapshot(*, session_id: str, slot: SessionSlotRef | None) -> SessionSnapshot:
    """构造 SessionSnapshot。

    :param session_id: Session id。
    :param slot: Session slot。
    :returns: SessionSnapshot。
    :raises Exception: 不主动抛出异常。
    """

    return SessionSnapshot(
        session_id=session_id,
        status=SessionStatus.OPEN,
        slot=slot,
        active_run_id=None,
        queued_run_ids=(),
        timeline_cursor=HostStreamCursor(event_sequence=0),
    )


async def _prepare_prompt_runtime(workspace_root: Path) -> EntrypointRuntimeResult:
    """准备 prompt 测试 runtime。

    :param workspace_root: 测试 workspace root。
    :returns: EntrypointRuntimeResult。
    :raises Exception: runtime assembly 失败时向上透传。
    """

    return await session_execution.prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root(),
            explicit_config_dir=None,
            scene_id="prompt",
            context_slot_values={
                "fins_default_subject": "# 当前分析对象\n你正在分析的是 AAPL。",
                "current_time": _PROMPT_CURRENT_TIME_TEXT,
            },
            assembly_overrides=ServiceAssemblyOverrides(model_id=_MODEL_ID),
            env=_runtime_assembly_env(),
        )
    )


async def _never_finishes_prompt_terminal() -> EntrypointRunTerminalResult:
    """构造永不完成的 prompt terminal awaitable。

    :returns: 永不实际返回的 prompt terminal result。
    :raises asyncio.CancelledError: 调用方取消 task 时透传。
    """

    await asyncio.Event().wait()
    raise RuntimeError("unreachable prompt terminal")


async def _complete_prompt_terminal_after_release(
    release: asyncio.Event,
    terminal: EntrypointRunTerminalResult,
) -> EntrypointRunTerminalResult:
    """等待 event-loop barrier 后返回指定 prompt terminal。

    :param release: 允许 submit task 自然完成的 barrier。
    :param terminal: 必须原 identity 返回的 terminal。
    :returns: ``terminal`` 原对象。
    :raises asyncio.CancelledError: 等待期间 task 被取消时透传。
    """

    await release.wait()
    return terminal


async def _wait_for_thread_event(event: threading.Event) -> None:
    """在不占用 default executor 的情况下等待线程侧测试事件。

    :param event: renderer worker 设置的同步事件。
    :returns: ``None``。
    :raises asyncio.CancelledError: 等待 task 被取消时透传。
    """

    while not event.is_set():
        await asyncio.sleep(0)


def _entrypoint_terminal_result() -> EntrypointRunTerminalResult:
    """构造 prompt finish-thinking race 使用的 live terminal。

    :returns: 固定 successful live terminal。
    :raises Exception: DTO 字段非法时由构造函数抛出。
    """

    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        session_id="session-1",
        run_id="run-1",
        terminal_event_id="terminal-run-1-finish-race",
        event_sequence=7,
        terminal_status=HostTerminalStatus.SUCCEEDED,
        dedupe_key="terminal-run-1-finish-race",
        final_answer=_final_answer(),
        error_message=None,
        cancel_reason=None,
        watcher_failure_message=None,
    )


def _run_snapshot(*, run_id: str, status: RunStatus) -> RunSnapshot:
    """构造 RunSnapshot。

    :param run_id: Run id。
    :param status: Run status。
    :returns: RunSnapshot。
    :raises Exception: 不主动抛出异常。
    """

    terminal_summary = None
    if is_terminal_run_status(status):
        terminal_summary = TerminalResultSummary(
            status=status,
            summary_ref=None,
            summary_digest=None,
        )
    return RunSnapshot(
        run_id=run_id,
        session_id="session-1",
        status=status,
        current_attempt_id=None,
        terminal_result_summary=terminal_summary,
        event_cursor=HostStreamCursor(event_sequence=0),
        source_run_id=None,
        source_run_relation=None,
        outbox_summary=None,
    )


def _terminal_event(*, status: HostTerminalStatus) -> HostEvent:
    """构造 Host terminal event。

    :param status: terminal status。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    final_answer = None
    error_message = None
    cancel_reason = None
    if status is HostTerminalStatus.SUCCEEDED:
        final_answer = _final_answer()
    elif status is HostTerminalStatus.FAILED:
        error_message = "prompt failed"
    elif status is HostTerminalStatus.CANCELLED:
        cancel_reason = "cli_sigint"
    return HostEvent(
        event_id="terminal-run-1-2",
        event_sequence=2,
        session_id="session-1",
        run_id="run-1",
        event_class=HostEventClass.CANONICAL_FACT,
        event_type=_event_type(status),
        kind=_event_kind(status),
        activity=None,
        dedupe_key="terminal-run-1-2",
        terminal_status=status,
        final_answer=final_answer,
        error_message=error_message,
        cancel_reason=cancel_reason,
    )


def _activity_event() -> HostEvent:
    """构造 Host activity event。

    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return _activity_event_with_sequence(
        event_sequence=1,
        dedupe_key="activity-run-1-1",
        title="工具批次完成",
        summary="完成 1 个工具调用。",
    )


def _activity_event_with_sequence(
    *,
    event_sequence: int,
    dedupe_key: str,
    title: str,
    summary: str,
) -> HostEvent:
    """构造可指定 sequence 的 Host activity event。

    :param event_sequence: Host event sequence。
    :param dedupe_key: activity dedupe key。
    :param title: activity 标题。
    :param summary: activity 摘要。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id=dedupe_key,
        event_sequence=event_sequence,
        session_id="session-1",
        run_id="run-1",
        event_class=HostEventClass.PREVIEW,
        event_type="TOOL_CALLS_BATCH_DONE",
        kind=HostEventKind.PROGRESS,
        activity=HostActivityView(
            kind=HostActivityKind.TOOL_BATCH,
            status=HostActivityStatus.COMPLETED,
            title=title,
            summary=summary,
            severity=HostActivitySeverity.INFO,
            tool_name="record_smoke_fact",
            tool_display_name="记录烟测事实",
            counts=HostActivityCounts(total=1, completed=1, failed=0, cancelled=0),
        ),
        dedupe_key=dedupe_key,
        terminal_status=None,
        final_answer=None,
        error_message=None,
        cancel_reason=None,
    )


def _thinking_event() -> HostTransientDelta:
    """构造 Host thinking event。

    :returns: HostTransientDelta。
    :raises Exception: 不主动抛出异常。
    """

    return _thinking_event_with_sequence(
        runtime_sequence=1,
        dedupe_key="thinking-run-1-1",
        text_delta="正在分析收入变化",
    )


def _thinking_event_with_sequence(
    *,
    runtime_sequence: int,
    dedupe_key: str,
    text_delta: str,
) -> HostTransientDelta:
    """构造可指定 sequence 的 Host thinking event。

    :param runtime_sequence: 当前 Host runtime 瞬态序列。
    :param dedupe_key: thinking dedupe key。
    :param text_delta: thinking 文本增量。
    :returns: HostTransientDelta。
    :raises Exception: 不主动抛出异常。
    """

    return HostTransientDelta(
        runtime_id="runtime-1",
        runtime_sequence=runtime_sequence,
        session_id="session-1",
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        worker_event_index=runtime_sequence,
        observed_at=_NOW,
        type=HostTransientDeltaType.REASONING_DELTA,
        data=HostReasoningDelta(
            iteration_id="iteration-1",
            text_delta=text_delta,
        ),
        dedupe_key=dedupe_key,
    )


def _entrypoint_thinking(
    *,
    dedupe_key: str,
    text_delta: str = "取消后不应输出",
) -> EntrypointThinking:
    """构造 Service entrypoint thinking。

    :param dedupe_key: thinking dedupe key。
    :param text_delta: thinking 文本增量。
    :returns: Service entrypoint thinking。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointThinking(
        run_id="run-1",
        runtime_id="runtime-1",
        runtime_sequence=1,
        dedupe_key=dedupe_key,
        text_delta=text_delta,
    )


def _outbox_item() -> OutboxTerminalItem:
    """构造 outbox terminal item。

    :returns: OutboxTerminalItem。
    :raises Exception: 不主动抛出异常。
    """

    return OutboxTerminalItem(
        item_id="item-run-1-5",
        idempotency_key="idem-run-1-5",
        terminal_event_id="terminal-run-1-5",
        event_sequence=5,
        session_id="session-1",
        run_id="run-1",
        terminal_status=HostTerminalStatus.SUCCEEDED,
        dedupe_key="terminal-run-1-5",
        final_answer=_final_answer(),
        error_message=None,
        cancel_reason=None,
        result_ref=None,
        result_digest=None,
        terminal_summary_ref=None,
        terminal_summary_digest=None,
        projected_at=_NOW,
        item_state=OutboxTerminalItemState.PENDING,
    )


def _final_answer() -> HostFinalAnswerView:
    """构造成功 final answer view。

    :returns: HostFinalAnswerView。
    :raises Exception: 不主动抛出异常。
    """

    return HostFinalAnswerView(
        content="prompt answer",
        filtered=False,
        degraded=False,
        finish_reason="stop",
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )


def _event_kind(status: HostTerminalStatus) -> HostEventKind:
    """把 terminal status 映射为 HostEventKind。

    :param status: terminal status。
    :returns: HostEventKind。
    :raises AssertionError: 未覆盖状态时抛出。
    """

    if status is HostTerminalStatus.SUCCEEDED:
        return HostEventKind.SUCCEEDED
    if status is HostTerminalStatus.FAILED:
        return HostEventKind.FAILED
    if status is HostTerminalStatus.CANCELLED:
        return HostEventKind.CANCELLED
    if status is HostTerminalStatus.LOST:
        return HostEventKind.LOST
    raise AssertionError(f"unexpected terminal status: {status}")


def _event_type(status: HostTerminalStatus) -> str:
    """把 terminal status 映射为 EventLog event_type。

    :param status: terminal status。
    :returns: EventLog event_type。
    :raises AssertionError: 未覆盖状态时抛出。
    """

    if status is HostTerminalStatus.SUCCEEDED:
        return "RUN_SUCCEEDED"
    if status is HostTerminalStatus.FAILED:
        return "RUN_FAILED"
    if status is HostTerminalStatus.CANCELLED:
        return "RUN_CANCELLED"
    if status is HostTerminalStatus.LOST:
        return "RUN_LOST"
    raise AssertionError(f"unexpected terminal status: {status}")
