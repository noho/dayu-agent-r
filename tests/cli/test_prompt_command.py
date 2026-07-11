"""``dayu-cli prompt`` 命令测试。"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from pathlib import Path
from typing import cast

import pytest

import dayu.cli.commands.prompt as prompt_command
import dayu.cli.main as cli_main
import dayu.cli.session_execution as session_execution
import dayu.service.scene_context as scene_context
from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    package_config_root,
    unsupported_execution_option_names,
)
from dayu.cli.arg_parsing import parse_cli_args
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
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
    HostStreamCursor,
    HostTerminalStatus,
    HostThinkingView,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItem,
    OutboxTerminalItemsBatch,
    OutboxTerminalItemState,
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
from dayu.cli.runtime_display import RuntimeDisplayController
from dayu.cli.session_terminal_cursor import CliTerminalCursorError, read_cli_terminal_cursor
from dayu.cli.thinking import CliThinkingRenderer, CliThinkingRendererOptions
from dayu.service.entrypoint_runtime import EntrypointRunTerminalResult, EntrypointThinking
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
class _StopSignal:
    """测试 watcher 停止信号。"""


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


class _FakeHostEventIterator:
    """测试用 Host event iterator。"""

    closed_count: int
    _queue: asyncio.Queue[HostEvent | _StopSignal | _RaiseSignal]

    def __init__(self) -> None:
        """初始化 fake watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count = 0
        self._queue = asyncio.Queue()

    def __aiter__(self) -> AsyncIterator[HostEvent]:
        """返回自身作为 async iterator。

        :returns: HostEvent async iterator。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> HostEvent:
        """读取下一条 Host event。

        :returns: HostEvent。
        :raises StopAsyncIteration: 收到停止信号时抛出。
        """

        item = await self._queue.get()
        if isinstance(item, _StopSignal):
            raise StopAsyncIteration
        if isinstance(item, _RaiseSignal):
            raise item.error
        return item

    async def push(self, event: HostEvent) -> None:
        """推入一条 Host event。

        :param event: 待推入事件。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        await self._queue.put(event)

    async def fail(self, error: Exception) -> None:
        """推入 watcher drain 应观察到的异常。

        :param error: watcher drain 应观察到的异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        await self._queue.put(_RaiseSignal(error=error))

    async def aclose(self) -> None:
        """关闭 watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count += 1
        await self._queue.put(_StopSignal())


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
    _submit_events: tuple[HostEvent, ...]
    _submit_watcher_errors: tuple[Exception, ...]
    _cancel_terminal: HostEvent | None
    _outbox_item: OutboxTerminalItem | None
    _run_statuses: tuple[RunStatus, ...]
    _run_status_index: int
    block_cancel_after_record: bool
    _create_error: HostApiError | None

    def __init__(
        self,
        *,
        submit_terminal: HostEvent | None,
        submit_events: tuple[HostEvent, ...] = (),
        submit_watcher_errors: tuple[Exception, ...] = (),
        run_statuses: tuple[RunStatus, ...] = (RunStatus.SUCCEEDED,),
        outbox_item: OutboxTerminalItem | None = None,
        cancel_terminal: HostEvent | None = None,
        block_cancel_after_record: bool = False,
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
        :param block_cancel_after_record: 是否在记录 cancel 后阻塞。
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
        self.block_cancel_after_record = block_cancel_after_record
        self._create_error = create_error

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

    def watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]:
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
        :raises asyncio.CancelledError: 测试设置阻塞且 task 被取消时透传。
        """

        self.calls.append(f"cancel:{run_id}")
        self.cancel_requests.append(request)
        if self._cancel_terminal is not None:
            await self.watchers[-1].push(self._cancel_terminal)
            await asyncio.sleep(0)
        if self.block_cancel_after_record:
            await asyncio.Event().wait()
        return _run_snapshot(run_id=run_id, status=RunStatus.CANCELLING)


class _BlockingSubmitHost(_FakeHost):
    """submit_followup 永不接受 Run 的 fake Host。"""

    async def submit_followup(self, session_id: str, request: SubmitFollowupRequest) -> FollowupSnapshot:
        """阻塞 submit，用于测试 Run accepted 前 SIGINT。

        :param session_id: 目标 Session id。
        :param request: SubmitFollowupRequest。
        :returns: 正常路径不会返回。
        :raises asyncio.CancelledError: submit task 被取消时透传。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        await asyncio.Event().wait()
        raise AssertionError("blocking submit should be cancelled")


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

    def __init__(self, host: _FakeHost) -> None:
        """初始化 fake context manager。

        :param host: fake Host。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.host = host

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

        return None


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


class _ImmediateSigintMonitor(CliSigintMonitor):
    """测试用立即 SIGINT monitor。"""

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
        """立即触发一次 SIGINT。

        :param observed_count: 已观察到的 SIGINT 计数。
        :returns: 新的 SIGINT 计数。
        :raises Exception: 不主动抛出异常。
        """

        if self.count <= observed_count:
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


class _SecondSigintAfterCancelMonitor(CliSigintMonitor):
    """测试用第二次 SIGINT monitor。"""

    host: _FakeHost

    def __init__(self, host: _FakeHost) -> None:
        """初始化 monitor。

        :param host: fake Host。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.host = host

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
        """第一次等待触发 Ctrl+C，第二次等待 cancel 记录后再触发。

        :param observed_count: 已观察到的 SIGINT 计数。
        :returns: 新的 SIGINT 计数。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        if observed_count == 0:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.notify()
            return self.count
        while not self.host.cancel_requests:
            await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.notify()
        return self.count


class _FakeRunningKeyMonitor:
    """测试用运行态按键 monitor。"""

    started_count: int
    closed_count: int
    _actions: asyncio.Queue[RunningKeyAction]
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
        self._actions = asyncio.Queue()
        self._delay_ticks = delay_ticks
        for action in actions:
            self._actions.put_nowait(action)

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
        return await self._actions.get()

    def close(self) -> None:
        """记录 monitor 关闭。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count += 1


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
            "--model-name",
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
    assert (
        captured_requests[0].context_slot_values["fins_default_subject"]
        == "# 当前分析对象\n你正在分析的是 AAPL。"
    )
    assert "Asia/Shanghai" in str(captured_requests[0].context_slot_values["current_time"])
    assert captured_requests[0].assembly_overrides.model_id == _MODEL_ID
    assert fake_host.ensure_requests[0].scope == "cli.prompt"
    assert fake_host.ensure_requests[0].slot_key == "cli.prompt.earnings"
    assert fake_host.calls[:3] == ["ensure_session", "watch:session-1", "submit:session-1"]
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
        submit_watcher_errors=(RuntimeError("watch stream disconnected"),),
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
                event_sequence=2,
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
            env={"DEEPSEEK_API_KEY": _API_KEY},
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
    """prompt 本地取消 helper 应先收尾再关闭 thinking renderer。"""

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
        sigint_monitor=_NoopSigintMonitor(),
        observed_sigint_count=0,
        runtime_display=RuntimeDisplayController(
            activity_display=None,
            thinking_display=thinking_renderer,
        ),
    )

    assert result is None
    assert fake_host.cancel_requests == []
    assert stderr.getvalue() == "Thinking: The user is asking\n"
    thinking_renderer.record(_entrypoint_thinking(dedupe_key="thinking-after-cancel"))
    assert stderr.getvalue() == "Thinking: The user is asking\n"


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
async def test_prompt_second_sigint_exits_after_cancel_request(
    tmp_path: Path,
) -> None:
    """prompt 运行态第二次 Ctrl+C 应在 cancel terminal 前本地退出。"""

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
        block_cancel_after_record=True,
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
    thinking_renderer.record(
        _entrypoint_thinking(
            dedupe_key="thinking-before-second-sigint",
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
        sigint_monitor=_SecondSigintAfterCancelMonitor(fake_host),
        activity_renderer=renderer,
        thinking_renderer=thinking_renderer,
    )

    assert result is None
    assert len(fake_host.cancel_requests) == 1
    assert "Thinking: The user is asking\r\x1b[2KActivity: cancel requested" in (stderr.getvalue())
    assert "local process exiting" in stderr.getvalue()
    assert stderr.getvalue().count("Thinking:") == 1


@pytest.mark.asyncio
async def test_prompt_cancel_terminal_wins_over_second_sigint(
    tmp_path: Path,
) -> None:
    """prompt cancel terminal 与第二次 Ctrl+C 竞争时应返回 terminal。"""

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
        sigint_monitor=_SecondSigintAfterCancelMonitor(fake_host),
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
def test_prompt_command_rejects_unsupported_old_execution_flags(
    unsupported_args: tuple[str, ...],
    expected_fragment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """旧执行参数缺少 typed public contract 时应 fail fast。"""

    exit_code = cli_main.main(("prompt", *unsupported_args, "请总结收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "unsupported option" in captured.err
    assert expected_fragment in captured.err


def test_prompt_thinking_flags_are_display_options_not_execution_overrides() -> None:
    """``--thinking`` / ``--no-thinking`` 不进入旧执行参数拒绝集合。

    :returns: ``None``。
    :raises AssertionError: thinking 展示参数被错误列为 unsupported 时抛出。
    """

    thinking_args = parse_cli_args(("prompt", "hello", "--thinking"))
    no_thinking_args = parse_cli_args(("prompt", "hello", "--no-thinking"))

    assert thinking_args.thinking is True
    assert no_thinking_args.thinking is False
    assert "--thinking/--no-thinking" not in unsupported_execution_option_names(thinking_args)
    assert "--thinking/--no-thinking" not in unsupported_execution_option_names(no_thinking_args)


def test_prompt_debug_stream_is_not_unsupported_execution_option() -> None:
    """debug-stream 是全局日志开关，不是旧 Agent 执行参数。

    :returns: ``None``。
    :raises AssertionError: debug-stream 被错误列为 unsupported option 时抛出。
    """

    args = parse_cli_args(("prompt", "--debug-stream", "请总结收入变化"))

    assert "--debug-stream" not in unsupported_execution_option_names(args)


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


def test_prompt_command_reports_all_unsupported_old_execution_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """unsupported 旧参数应统一列入清晰错误。"""

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


def test_prompt_explicit_config_outside_workspace_exits_with_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """显式 config 目录逃逸 workspace 时应返回用法错误。"""

    outside_config = tmp_path.parent / "outside-config"
    outside_config.mkdir()

    exit_code = cli_main.main(
        (
            "prompt",
            "--base",
            str(tmp_path),
            "--config",
            str(outside_config),
            "请总结收入变化",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "inside workspace root" in captured.err


def test_prompt_explicit_config_missing_exits_with_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """显式 config 目录不存在时应返回用法错误。"""

    exit_code = cli_main.main(
        (
            "prompt",
            "--base",
            str(tmp_path),
            "--config",
            "missing-config",
            "请总结收入变化",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "not a directory" in captured.err


@pytest.mark.asyncio
async def test_prompt_sigint_before_run_id_returns_local_interrupt(
    tmp_path: Path,
) -> None:
    """Run accepted 前 SIGINT 应只本地退出，不发 Host cancel。"""

    runtime = await session_execution.prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=package_config_root(),
            explicit_config_dir=None,
            scene_id="prompt",
            context_slot_values={
                "fins_default_subject": "# 当前分析对象\n你正在分析的是 AAPL。",
                "current_time": _PROMPT_CURRENT_TIME_TEXT,
            },
                assembly_overrides=ServiceAssemblyOverrides(model_id=_MODEL_ID),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )
    fake_host = _BlockingSubmitHost(submit_terminal=None)

    result = await session_execution._submit_prompt_turn_handling_sigint(
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
        sigint_monitor=_ImmediateSigintMonitor(),
    )

    assert result is None
    assert fake_host.cancel_requests == []


@pytest.mark.asyncio
async def test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run accepted 前本地退出没有 terminal 可渲染，不得推进 cursor。

    :param tmp_path: pytest 临时目录夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 本地退出推进 cursor 或返回码错误时抛出。
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
    fake_host = _BlockingSubmitHost(submit_terminal=None)

    exit_code = await session_execution.execute_prompt_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        sigint_monitor=_ImmediateSigintMonitor(),
    )

    cursor_record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-existing",
    )
    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert fake_host.cancel_requests == []
    assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=0)
    assert cursor_record.seen_terminal_event_ids == ()


@pytest.mark.asyncio
async def test_prompt_sigint_monitor_waits_for_notification() -> None:
    """SIGINT monitor wait_next 应等待 notify 并返回新计数。"""

    monitor = CliSigintMonitor()
    wait_task = asyncio.create_task(monitor.wait_next(0))

    await asyncio.sleep(0)
    monitor.notify()

    assert await wait_task == 1


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
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )


async def _never_finishes_prompt_terminal() -> EntrypointRunTerminalResult:
    """构造永不完成的 prompt terminal awaitable。

    :returns: 永不实际返回的 prompt terminal result。
    :raises asyncio.CancelledError: 调用方取消 task 时透传。
    """

    await asyncio.Event().wait()
    raise RuntimeError("unreachable prompt terminal")


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


def _thinking_event() -> HostEvent:
    """构造 Host thinking event。

    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return _thinking_event_with_sequence(
        event_sequence=1,
        dedupe_key="thinking-run-1-1",
        text_delta="正在分析收入变化",
    )


def _thinking_event_with_sequence(
    *,
    event_sequence: int,
    dedupe_key: str,
    text_delta: str,
) -> HostEvent:
    """构造可指定 sequence 的 Host thinking event。

    :param event_sequence: Host event sequence。
    :param dedupe_key: thinking dedupe key。
    :param text_delta: thinking 文本增量。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id=dedupe_key,
        event_sequence=event_sequence,
        session_id="session-1",
        run_id="run-1",
        event_class=HostEventClass.PREVIEW,
        event_type="REASONING_DELTA",
        kind=HostEventKind.PROGRESS,
        activity=None,
        thinking=HostThinkingView(text_delta=text_delta),
        dedupe_key=dedupe_key,
        terminal_status=None,
        final_answer=None,
        error_message=None,
        cancel_reason=None,
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
        event_sequence=1,
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
