"""``dayu-cli interactive`` 命令测试。"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import cast

import pytest

import dayu.cli.commands.interactive as interactive_command
import dayu.cli.main as cli_main
import dayu.cli.session_execution as session_execution
from dayu.cli.composer import InputReaderComposer
from dayu.cli.run_keys import RunningKeyAction
from dayu.cli.run_view import InteractiveRunViewOptions, TerminalInteractiveRunView
from dayu.cli.runtime_display import RuntimeDisplayController
from dayu.cli.session_terminal_cursor import CliTerminalCursorError, read_cli_terminal_cursor
from dayu.cli.thinking import CliThinkingRenderer, CliThinkingRendererOptions
from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    package_config_root,
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
    HostReasoningDelta,
    HostSessionEvent,
    HostStreamCursor,
    HostTerminalStatus,
    HostTransientDelta,
    HostTransientDeltaType,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItemsBatch,
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
from dayu.service.entrypoint_runtime import (
    EntrypointThinking,
    EntrypointRunTerminalResult,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointStartupReconnectRequest,
    EntrypointStartupReconnectResult,
    EntrypointTerminalSource,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides

_MODEL_ID = "deepseek-v4-flash"
_FINS_DEFAULT_SUBJECT_SLOT = "fins_default_subject"
_CURRENT_TIME_SLOT = "current_time"
_CURRENT_TIME_TEXT = (
    "# 当前时间\n"
    "现在是 2026年7月7日 17:20（Asia/Shanghai，星期二）。\n"
    "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
)
_REMOVED_INTERACTIVE_DEBUG_OPTIONS: tuple[tuple[str, ...], ...] = (
    ("--debug-sse",),
    ("--debug-tool-delta",),
    ("--debug-sse-sample-rate", "0.5"),
    ("--debug-sse-throttle-sec", "1.0"),
)
_API_KEY = "test-provider-key"
_TRANSIENT_OBSERVED_AT = datetime(2026, 7, 20, 1, 2, 3, tzinfo=UTC)


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


class _FakeHostEventIterator:
    """测试用 Host event iterator。"""

    closed_count: int
    _queue: asyncio.Queue[HostSessionEvent | _StopSignal]

    def __init__(self) -> None:
        """初始化 fake watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count = 0
        self._queue = asyncio.Queue()

    def __aiter__(self) -> AsyncIterator[HostSessionEvent]:
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

        item = await self._queue.get()
        if isinstance(item, _StopSignal):
            raise StopAsyncIteration
        return item

    async def push(self, event: HostSessionEvent) -> None:
        """推入一条 Host event。

        :param event: 待推入事件。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        await self._queue.put(event)

    async def aclose(self) -> None:
        """关闭 watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count += 1
        await self._queue.put(_StopSignal())


class _FakeHost:
    """CLI interactive 测试用 Host public API 替身。"""

    calls: list[str]
    watchers: list[_FakeHostEventIterator]
    ensure_requests: list[EnsureSessionRequest]
    create_requests: list[CreateSessionRequest]
    submit_requests: list[SubmitFollowupRequest]
    cancel_requests: list[CancelRunRequest]
    read_outbox_requests: list[ReadOutboxTerminalItemsRequest]
    _submit_statuses: tuple[HostTerminalStatus | None, ...]
    _submit_activities: tuple[bool, ...]
    _submit_thinking: tuple[bool, ...]
    _cancel_status: HostTerminalStatus | None
    _run_statuses: tuple[RunStatus, ...]
    _submit_index: int
    _run_status_index: int
    block_cancel_after_record: bool
    _create_error: HostApiError | None

    def __init__(
        self,
        *,
        submit_statuses: tuple[HostTerminalStatus | None, ...] = (),
        submit_activities: tuple[bool, ...] = (),
        submit_thinking: tuple[bool, ...] = (),
        cancel_status: HostTerminalStatus | None = None,
        run_statuses: tuple[RunStatus, ...] = (RunStatus.SUCCEEDED,),
        block_cancel_after_record: bool = False,
        create_error: HostApiError | None = None,
    ) -> None:
        """初始化 fake Host。

        :param submit_statuses: 每轮 submit 返回前推入 watcher 的 terminal
            状态；``None`` 表示该轮 watcher 不产生 terminal。
        :param submit_activities: 每轮 submit 是否先推入 activity event。
        :param submit_thinking: 每轮 submit 是否先推入 thinking event。
        :param cancel_status: cancel 返回前推入 watcher 的 terminal 状态。
        :param run_statuses: ``get_run`` 依次返回的状态。
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
        self._submit_statuses = submit_statuses
        self._submit_activities = submit_activities
        self._submit_thinking = submit_thinking
        self._cancel_status = cancel_status
        self._run_statuses = run_statuses
        self._submit_index = 0
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

    def watch_session_events(
        self,
        session_id: str,
    ) -> AsyncIterator[HostSessionEvent]:
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
        self._submit_index += 1
        run_id = f"run-{self._submit_index}"
        status_index = self._submit_index - 1
        status = None
        if status_index < len(self._submit_statuses):
            status = self._submit_statuses[status_index]
        if status is not None:
            if status_index < len(self._submit_thinking) and self._submit_thinking[
                status_index
            ]:
                await self.watchers[-1].push(_thinking_event(run_id=run_id))
            if status_index < len(self._submit_activities) and self._submit_activities[status_index]:
                await self.watchers[-1].push(_activity_event(run_id=run_id))
            await self.watchers[-1].push(_terminal_event(run_id=run_id, status=status))
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

    async def get_session(self, session_id: str) -> SessionSnapshot:
        """返回 idle SessionSnapshot 供 startup barrier 结束。

        :param session_id: 目标 Session id。
        :returns: SessionSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"get_session:{session_id}")
        return _session_snapshot(session_id=session_id, slot=None)

    async def read_outbox_terminal_items(
        self,
        session_id: str,
        request: ReadOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """返回空 outbox fallback 批次。

        :param session_id: 目标 Session id。
        :param request: outbox read 请求。
        :returns: OutboxTerminalItemsBatch。
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

    async def cancel_run(self, run_id: str, request: CancelRunRequest) -> RunSnapshot:
        """记录 cancel_run 请求。

        :param run_id: 目标 Run id。
        :param request: CancelRunRequest。
        :returns: RunSnapshot。
        :raises asyncio.CancelledError: 测试设置阻塞且 task 被取消时透传。
        """

        self.calls.append(f"cancel:{run_id}")
        self.cancel_requests.append(request)
        if self._cancel_status is not None:
            await self.watchers[-1].push(_terminal_event(run_id=run_id, status=self._cancel_status))
            await asyncio.sleep(0)
        if self.block_cancel_after_record:
            await asyncio.Event().wait()
        return _run_snapshot(run_id=run_id, status=RunStatus.CANCELLING)


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


class _InputReader:
    """测试用输入读取器。"""

    _remaining: list[str]

    def __init__(self, values: tuple[str, ...]) -> None:
        """初始化输入读取器。

        :param values: 依次返回的输入文本。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._remaining = list(values)

    def __call__(self, _prompt: str) -> str:
        """读取下一条测试输入。

        :param _prompt: 输入提示文本。
        :returns: 下一条用户输入。
        :raises EOFError: 输入耗尽时抛出。
        """

        if not self._remaining:
            raise EOFError
        return self._remaining.pop(0)


class _KeyboardInterruptInputReader:
    """测试用输入态 Ctrl-C 读取器。"""

    def __call__(self, _prompt: str) -> str:
        """模拟输入态 Ctrl-C。

        :param _prompt: 输入提示文本。
        :returns: 正常路径不会返回。
        :raises KeyboardInterrupt: 始终抛出，用于固定输入态 Ctrl-C 语义。
        """

        raise KeyboardInterrupt


@dataclass(frozen=True, slots=True)
class _ComposerReadInterrupt:
    """测试 composer 读取异常步骤。"""

    exception_type: type[BaseException]


_ComposerReadStep = str | _ComposerReadInterrupt


class _ScriptedComposer:
    """按脚本返回输入或抛出异常的测试 composer。"""

    prompt_calls: list[str]
    _remaining: list[_ComposerReadStep]

    def __init__(self, steps: tuple[_ComposerReadStep, ...]) -> None:
        """初始化 scripted composer。

        :param steps: 每次读取的返回文本或异常步骤。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.prompt_calls = []
        self._remaining = list(steps)

    async def read(self, prompt: str) -> str:
        """读取下一条脚本输入。

        :param prompt: 输入提示文本。
        :returns: 脚本中的输入文本。
        :raises EOFError: 脚本耗尽或脚本要求 EOF 时抛出。
        :raises KeyboardInterrupt: 脚本要求输入态中断时抛出。
        """

        self.prompt_calls.append(prompt)
        if not self._remaining:
            raise EOFError
        step = self._remaining.pop(0)
        if isinstance(step, str):
            return step
        raise step.exception_type()


class _AutoSigintMonitor(CliSigintMonitor):
    """测试用一次 SIGINT monitor。"""

    def install(self) -> None:
        """测试中不安装真实 OS signal handler。"""

        return

    def close(self) -> None:
        """测试中无需恢复 OS signal handler。"""

        return

    async def wait_next(self, observed_count: int) -> int:
        """等待 submit callback 记录 run id 后触发一次 SIGINT。"""

        await asyncio.sleep(0)
        await asyncio.sleep(0)
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
        """测试中不安装真实 OS signal handler。"""

        return

    def close(self) -> None:
        """测试中无需恢复 OS signal handler。"""

        return

    async def wait_next(self, observed_count: int) -> int:
        """第一次立即触发，第二次等 cancel 请求已记录后触发。

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
        self.notify()
        return self.count


def test_interactive_label_reuses_host_slot_and_fills_context_slots(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--label`` 应复用 cli.interactive.<label> slot。"""

    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.SUCCEEDED,))
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
    monkeypatch.setattr(
        session_execution,
        "prepare_entrypoint_runtime",
        capture_prepare,
    )
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("请总结收入变化",)),
    )

    exit_code = cli_main.main(
        (
            "interactive",
            "--base",
            str(tmp_path),
            "--ticker",
            " AAPL ",
            "--label",
            "earnings",
            "--model-name",
            _MODEL_ID,
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "answer for run-1"
    assert captured_requests[0].scene_id == "interactive"
    assert tuple(captured_requests[0].context_slot_values) == (
        _FINS_DEFAULT_SUBJECT_SLOT,
        _CURRENT_TIME_SLOT,
    )
    assert (
        captured_requests[0].context_slot_values[_FINS_DEFAULT_SUBJECT_SLOT]
        == "# 当前分析对象\n你正在分析的是 AAPL。"
    )
    assert "Asia/Shanghai" in str(captured_requests[0].context_slot_values[_CURRENT_TIME_SLOT])
    assert fake_host.ensure_requests[0].scope == "cli.interactive"
    assert fake_host.ensure_requests[0].slot_key == "cli.interactive.earnings"
    assert fake_host.create_requests == []


@pytest.mark.asyncio
async def test_interactive_existing_session_execution_does_not_create_or_ensure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """interactive existing-session 入口只能在指定 Session 上运行 REPL。

    :param tmp_path: pytest 临时目录夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: helper 调用了 create / ensure 或多轮 Session 不一致时抛出。
    """

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    args = parse_cli_args(
        (
            "session",
            "resume",
            "--session-id",
            "session-existing",
            "--mode",
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    prepared = await session_execution.prepare_interactive_session_execution(
        args,
        command_name="session",
        scenario="interactive",
        ticker=None,
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    assert prepared.runtime.host_assembly.options.wait_poller_policy is not None
    assert prepared.runtime.host_assembly.options.wait_poller_policy.enabled
    assert prepared.runtime.host_assembly.options.tooling_options is not None
    assert prepared.runtime.host_assembly.options.tooling_options.wait_poll_adapter_registry is not None
    fake_host = _FakeHost(
        submit_statuses=(
            HostTerminalStatus.SUCCEEDED,
            HostTerminalStatus.SUCCEEDED,
        )
    )

    exit_code = await session_execution.execute_interactive_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        input_reader=_input_reader(("第一轮", "第二轮")),
        sigint_monitor_factory=_NoopSigintMonitor,
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.splitlines() == ["answer for run-1", "answer for run-2"]
    assert fake_host.ensure_requests == []
    assert fake_host.create_requests == []
    assert fake_host.calls == [
        "watch:session-existing",
        "read_outbox:session-existing",
        "get_session:session-existing",
        "read_outbox:session-existing",
        "watch:session-existing",
        "submit:session-existing",
        "watch:session-existing",
        "submit:session-existing",
    ]
    assert [request.user_prompt for request in fake_host.submit_requests] == [
        "第一轮",
        "第二轮",
    ]


@pytest.mark.asyncio
async def test_interactive_existing_session_runs_startup_before_first_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """existing-session interactive 必须在读取第一条输入前执行 startup。"""

    events: list[str] = []
    args = parse_cli_args(
        (
            "session",
            "resume",
            "--session-id",
            "session-existing",
            "--mode",
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    prepared = await session_execution.prepare_interactive_session_execution(
        args,
        command_name="session",
        scenario="interactive",
        ticker=None,
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.SUCCEEDED,))

    async def fake_startup_reconnect(
        host: Host,
        *,
        request: EntrypointStartupReconnectRequest,
    ) -> EntrypointStartupReconnectResult:
        """记录 startup 调用并返回一条离线 terminal。

        :param host: Host public handle。
        :param request: startup reconnect 请求。
        :returns: startup reconnect result。
        :raises Exception: 不主动抛出异常。
        """

        events.append(f"startup:{request.session_id}")
        return EntrypointStartupReconnectResult(
            terminal_results=(
                EntrypointRunTerminalResult(
                    source=EntrypointTerminalSource.OUTBOX_READ,
                    session_id=request.session_id,
                    run_id="run-startup",
                    terminal_event_id="terminal-startup",
                    event_sequence=5,
                    terminal_status=HostTerminalStatus.SUCCEEDED,
                    dedupe_key="terminal-startup",
                    final_answer=_final_answer(run_id="run-startup"),
                    error_message=None,
                    cancel_reason=None,
                    watcher_failure_message=None,
                ),
            ),
            next_terminal_cursor=OutboxTerminalCursor(event_sequence=5),
            seen_terminal_event_ids=frozenset({"terminal-startup"}),
        )

    def input_reader(prompt: str) -> str:
        """记录输入读取顺序。

        :param prompt: 输入提示文本。
        :returns: 第一轮用户输入。
        :raises EOFError: 第二次读取时表示输入结束。
        """

        events.append(f"input:{prompt}")
        if events.count(f"input:{prompt}") > 1:
            raise EOFError
        return "第一轮"

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        session_execution,
        "startup_reconnect_entrypoint_session",
        fake_startup_reconnect,
    )

    exit_code = await session_execution.execute_interactive_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        input_reader=input_reader,
        sigint_monitor_factory=_NoopSigintMonitor,
    )

    cursor_record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-existing",
    )
    assert exit_code == EXIT_SUCCESS
    assert events[:2] == ["startup:session-existing", "input:dayu> "]
    assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=5)
    assert cursor_record.seen_terminal_event_ids == (
        "terminal-startup",
        "terminal-run-1",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("terminal_status", "expected_exit_code"),
    (
        (HostTerminalStatus.FAILED, EXIT_SUCCESS),
        (HostTerminalStatus.CANCELLED, EXIT_SUCCESS),
        (HostTerminalStatus.LOST, EXIT_FAILURE),
    ),
)
async def test_interactive_startup_reconnect_advances_terminal_cursor_after_rendering_non_success_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: HostTerminalStatus,
    expected_exit_code: int,
) -> None:
    """startup reconnect 渲染非成功 terminal 后必须推进本地 cursor。

    :param tmp_path: pytest 临时目录夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param terminal_status: startup 返回的 Host terminal status。
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
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    prepared = await session_execution.prepare_interactive_session_execution(
        args,
        command_name="session",
        scenario="interactive",
        ticker=None,
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    fake_host = _FakeHost()

    async def fake_startup_reconnect(
        host: Host,
        *,
        request: EntrypointStartupReconnectRequest,
    ) -> EntrypointStartupReconnectResult:
        """返回一条非成功 startup terminal。

        :param host: Host public handle。
        :param request: startup reconnect 请求。
        :returns: startup reconnect result。
        :raises Exception: 不主动抛出异常。
        """

        return EntrypointStartupReconnectResult(
            terminal_results=(
                _startup_terminal_result(
                    session_id=request.session_id,
                    status=terminal_status,
                ),
            ),
            next_terminal_cursor=OutboxTerminalCursor(event_sequence=5),
            seen_terminal_event_ids=frozenset({"terminal-startup"}),
        )

    monkeypatch.setattr(
        session_execution,
        "startup_reconnect_entrypoint_session",
        fake_startup_reconnect,
    )

    exit_code = await session_execution.execute_interactive_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        input_reader=_input_reader(()),
        sigint_monitor_factory=_NoopSigintMonitor,
    )

    cursor_record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-existing",
    )
    assert exit_code == expected_exit_code
    assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=5)
    assert cursor_record.seen_terminal_event_ids == ("terminal-startup",)


@pytest.mark.asyncio
async def test_interactive_startup_cursor_write_failure_propagates_after_terminal_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """startup reconnect 已渲染 terminal 后 cursor 写失败必须传播。

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
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    prepared = await session_execution.prepare_interactive_session_execution(
        args,
        command_name="session",
        scenario="interactive",
        ticker=None,
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    fake_host = _FakeHost()

    async def fake_startup_reconnect(
        host: Host,
        *,
        request: EntrypointStartupReconnectRequest,
    ) -> EntrypointStartupReconnectResult:
        """返回一条 startup terminal 供 cursor 写失败测试消费。

        :param host: Host public handle。
        :param request: startup reconnect 请求。
        :returns: startup reconnect result。
        :raises Exception: 不主动抛出异常。
        """

        return EntrypointStartupReconnectResult(
            terminal_results=(
                _startup_terminal_result(
                    session_id=request.session_id,
                    status=HostTerminalStatus.LOST,
                ),
            ),
            next_terminal_cursor=OutboxTerminalCursor(event_sequence=5),
            seen_terminal_event_ids=frozenset({"terminal-startup"}),
        )

    monkeypatch.setattr(
        session_execution,
        "startup_reconnect_entrypoint_session",
        fake_startup_reconnect,
    )

    with pytest.raises(CliTerminalCursorError, match="cursor write failed"):
        await session_execution.execute_interactive_on_session(
            host=cast(Host, fake_host),
            prepared=prepared,
            session_id="session-existing",
            input_reader=_input_reader(()),
            sigint_monitor_factory=_NoopSigintMonitor,
        )


def test_interactive_host_api_error_uses_structured_presentation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """interactive 首次 create 阶段 HostApiError 必须结构化展示并返回 failure。"""

    fake_host = _FakeHost(
        create_error=HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="workspace session root missing",
            retryable=False,
        )
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "dayu-cli interactive" in captured.err
    assert "host_code=not_found" in captured.err
    assert "host_message=workspace session root missing" in captured.err
    assert fake_host.calls == ["create_session"]


@pytest.mark.parametrize("log_flag", ("--verbose", "--debug", "--debug-stream"))
def test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout(
    log_flag: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """interactive verbose/debug 诊断不得写入 stdout 用户结果通道。

    :param log_flag: 待验证的全局日志 flag。
    :param tmp_path: pytest 临时目录夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: stdout 被诊断日志污染时抛出。
    """

    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.SUCCEEDED,))
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("请总结收入变化",)),
    )

    exit_code = cli_main.main(
        (
            log_flag,
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "answer for run-1"
    assert "[VERBOSE]" not in captured.out
    assert "[DEBUG]" not in captured.out


@pytest.mark.asyncio
async def test_interactive_first_idle_keyboard_interrupt_redisplays_prompt_without_exit(
    tmp_path: Path,
) -> None:
    """输入态第一次空 prompt Ctrl-C 应重绘 prompt，且不得发 submit / cancel。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="interactive",
        scenario="interactive",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost()
    composer = _ScriptedComposer(
        (
            _ComposerReadInterrupt(KeyboardInterrupt),
            _ComposerReadInterrupt(EOFError),
        )
    )

    exit_code = await session_execution._run_interactive_repl(
        host=cast(Host, fake_host),
        runtime=runtime,
        workspace_root=tmp_path,
        invocation=invocation,
        session_id="session-1",
        run_overrides=ServiceRunOverrides(),
        composer=composer,
        sigint_monitor_factory=_NoopSigintMonitor,
    )

    assert exit_code == EXIT_SUCCESS
    assert composer.prompt_calls == ["dayu> ", "dayu> "]
    assert fake_host.submit_requests == []
    assert fake_host.cancel_requests == []


def test_interactive_second_consecutive_input_keyboard_interrupt_exits_without_run_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """输入态连续两次空 prompt Ctrl-C 应退出当前 command，且不发 submit / cancel。"""

    fake_host = _FakeHost()
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _KeyboardInterruptInputReader(),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert fake_host.submit_requests == []
    assert fake_host.cancel_requests == []


@pytest.mark.asyncio
async def test_interactive_normal_input_resets_idle_keyboard_interrupt_exit_pending(
    tmp_path: Path,
) -> None:
    """输入态第一次 Ctrl-C 后提交正常输入，应重置本地退出待确认状态。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="interactive",
        scenario="interactive",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.SUCCEEDED,))
    composer = _ScriptedComposer(
        (
            _ComposerReadInterrupt(KeyboardInterrupt),
            "请总结收入变化",
            _ComposerReadInterrupt(KeyboardInterrupt),
            _ComposerReadInterrupt(EOFError),
        )
    )

    exit_code = await session_execution._run_interactive_repl(
        host=cast(Host, fake_host),
        runtime=runtime,
        workspace_root=tmp_path,
        invocation=invocation,
        session_id="session-1",
        run_overrides=ServiceRunOverrides(),
        composer=composer,
        sigint_monitor_factory=_NoopSigintMonitor,
    )

    assert exit_code == EXIT_SUCCESS
    assert composer.prompt_calls == ["dayu> ", "dayu> ", "dayu> ", "dayu> "]
    assert len(fake_host.submit_requests) == 1
    assert fake_host.submit_requests[0].user_prompt == "请总结收入变化"
    assert fake_host.cancel_requests == []


def test_interactive_empty_label_exits_with_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空白 label 应在 CLI adapter 层返回用法错误。"""

    fake_host = _FakeHost()
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path), "--label", " "))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "--label" in captured.err


def test_interactive_explicit_config_outside_workspace_exits_with_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """显式 config 目录逃逸 workspace 时应返回用法错误。"""

    outside_config = tmp_path.parent / "outside-interactive-config"
    outside_config.mkdir()

    exit_code = cli_main.main(
        (
            "interactive",
            "--base",
            str(tmp_path),
            "--config",
            str(outside_config),
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "inside workspace root" in captured.err


def test_interactive_explicit_config_missing_exits_with_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """显式 config 目录不存在时应返回用法错误。"""

    exit_code = cli_main.main(
        (
            "interactive",
            "--base",
            str(tmp_path),
            "--config",
            "missing-config",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "not a directory" in captured.err


def test_interactive_two_turns_use_same_session_and_independent_watchers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两轮 follow-up 应使用同一 Session 且每轮独立 attach/close watcher。"""

    fake_host = _FakeHost(
        submit_statuses=(
            HostTerminalStatus.SUCCEEDED,
            HostTerminalStatus.SUCCEEDED,
        )
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("第一轮", "第二轮")),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.splitlines() == ["answer for run-1", "answer for run-2"]
    assert fake_host.calls == [
        "create_session",
        "watch:session-1",
        "submit:session-1",
        "watch:session-1",
        "submit:session-1",
    ]
    assert len(fake_host.create_requests) == 1
    assert fake_host.create_requests[0].bind_slot is False
    assert fake_host.create_requests[0].scope is None
    assert fake_host.create_requests[0].slot_key is None
    assert [watcher.closed_count for watcher in fake_host.watchers] == [1, 1]
    first_submit = fake_host.submit_requests[0]
    second_submit = fake_host.submit_requests[1]
    assert first_submit.client_request_id.endswith(":turn-1:submit")
    assert second_submit.client_request_id.endswith(":turn-2:submit")
    assert first_submit.context.request_id != second_submit.context.request_id


def test_interactive_activity_uses_run_view_buffer_before_next_prompt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """interactive activity 应进入 run view buffer，final answer 保持 stdout 清晰。"""

    fake_host = _FakeHost(
        submit_statuses=(
            HostTerminalStatus.SUCCEEDED,
            HostTerminalStatus.SUCCEEDED,
        ),
        submit_activities=(True, True),
    )
    run_view = TerminalInteractiveRunView(
        options=InteractiveRunViewOptions(enabled=True),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("第一轮", "第二轮")),
    )
    monkeypatch.setattr(
        session_execution,
        "new_interactive_run_view",
        lambda show_activity=False: run_view,
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.splitlines() == ["answer for run-1", "answer for run-2"]
    assert "Activity:" not in captured.err
    assert len(run_view.activity_lines) == 2
    assert all("工具批次完成" in line for line in run_view.activity_lines)
    assert run_view.transcript_lines == ("answer for run-1", "answer for run-2")


def test_interactive_no_detail_omits_activity_and_keeps_final_answer_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--no-detail`` 不注册 activity callback，final answer 仍写 stdout。"""

    fake_host = _FakeHost(
        submit_statuses=(HostTerminalStatus.SUCCEEDED,),
        submit_activities=(True,),
    )
    run_view_factory_calls: list[bool] = []
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("第一轮",)),
    )
    monkeypatch.setattr(
        session_execution,
        "new_interactive_run_view",
        lambda show_activity=False: run_view_factory_calls.append(show_activity),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path), "--no-detail"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "answer for run-1"
    assert "Activity:" not in captured.err
    assert run_view_factory_calls == []


def test_interactive_thinking_flag_outputs_reasoning_delta_and_no_thinking_suppresses_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有 thinking event 时，``--thinking`` 与 ``--no-thinking`` 输出必须不同。"""

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("第一轮",)),
    )
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(
            _FakeHost(
                submit_statuses=(HostTerminalStatus.SUCCEEDED,),
                submit_thinking=(True,),
            )
        ),
    )

    thinking_exit = cli_main.main(
        ("interactive", "--base", str(tmp_path), "--thinking")
    )
    thinking_captured = capsys.readouterr()

    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("第一轮",)),
    )
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(
            _FakeHost(
                submit_statuses=(HostTerminalStatus.SUCCEEDED,),
                submit_thinking=(True,),
            )
        ),
    )

    no_thinking_exit = cli_main.main(
        ("interactive", "--base", str(tmp_path), "--no-thinking")
    )
    no_thinking_captured = capsys.readouterr()

    assert thinking_exit == EXIT_SUCCESS
    assert no_thinking_exit == EXIT_SUCCESS
    assert thinking_captured.out.strip() == "answer for run-1"
    assert no_thinking_captured.out.strip() == "answer for run-1"
    assert "Thinking: 正在分析收入变化" in thinking_captured.err
    assert "Thinking:" not in no_thinking_captured.err


def test_interactive_skips_blank_input_before_submit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """输入空白行时 interactive 应继续等待下一条有效输入。"""

    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.SUCCEEDED,))
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("   ", "有效问题")),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out.strip() == "answer for run-1"
    assert len(fake_host.submit_requests) == 1


def test_interactive_failed_and_cancelled_continue_until_eof(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FAILED / CANCELLED terminal 应展示状态并回到输入态。"""

    fake_host = _FakeHost(
        submit_statuses=(
            HostTerminalStatus.FAILED,
            HostTerminalStatus.CANCELLED,
            HostTerminalStatus.SUCCEEDED,
        )
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("失败轮", "取消轮", "成功轮")),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "answer for run-3"
    assert "failed for run-1" in captured.err
    assert "cancelled for run-2" in captured.err
    assert len(fake_host.submit_requests) == 3


def test_interactive_lost_is_fatal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LOST terminal 应退出 interactive 并返回 1。"""

    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.LOST,))
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(
        interactive_command,
        "_read_user_input",
        _input_reader(("触发 lost", "不应执行")),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "lost for run-1" in captured.err
    assert len(fake_host.submit_requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("terminal_status", "expected_exit_code"),
    (
        (HostTerminalStatus.FAILED, EXIT_SUCCESS),
        (HostTerminalStatus.CANCELLED, EXIT_SUCCESS),
        (HostTerminalStatus.LOST, EXIT_FAILURE),
    ),
)
async def test_interactive_existing_session_advances_terminal_cursor_after_rendering_non_success_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: HostTerminalStatus,
    expected_exit_code: int,
) -> None:
    """interactive turn 渲染非成功 terminal 后必须推进本地 cursor。

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
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    prepared = await session_execution.prepare_interactive_session_execution(
        args,
        command_name="session",
        scenario="interactive",
        ticker=None,
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    fake_host = _FakeHost(submit_statuses=(terminal_status,))

    exit_code = await session_execution.execute_interactive_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        input_reader=_input_reader(("触发非成功终态",)),
        sigint_monitor_factory=_NoopSigintMonitor,
        run_startup_reconnect=False,
    )

    cursor_record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-existing",
    )
    assert exit_code == expected_exit_code
    assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=2)
    assert cursor_record.seen_terminal_event_ids == ("terminal-run-1",)


@pytest.mark.asyncio
async def test_interactive_turn_cursor_write_failure_propagates_after_terminal_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """interactive turn 已渲染 terminal 后 cursor 写失败必须传播。

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
            "interactive",
            "--base",
            str(tmp_path),
        )
    )
    prepared = await session_execution.prepare_interactive_session_execution(
        args,
        command_name="session",
        scenario="interactive",
        ticker=None,
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.LOST,))

    with pytest.raises(CliTerminalCursorError, match="cursor write failed"):
        await session_execution.execute_interactive_on_session(
            host=cast(Host, fake_host),
            prepared=prepared,
            session_id="session-existing",
            input_reader=_input_reader(("触发终态",)),
            sigint_monitor_factory=_NoopSigintMonitor,
            run_startup_reconnect=False,
        )


@pytest.mark.asyncio
async def test_interactive_sigint_after_run_id_cancels_host_run(
    tmp_path: Path,
) -> None:
    """运行态第一次 SIGINT 应发完整 CancelRunRequest 并返回取消终态。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="interactive",
        scenario="interactive",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost(
        submit_statuses=(None,),
        cancel_status=HostTerminalStatus.CANCELLED,
        run_statuses=(RunStatus.RUNNING,),
    )

    result = await session_execution._submit_interactive_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        turn_index=1,
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
    assert cancel_request.context.operation_context.operation_name == ("dayu_cli.interactive.cancel_run")


@pytest.mark.asyncio
async def test_interactive_esc_requests_cancel_after_run_id(
    tmp_path: Path,
) -> None:
    """interactive 运行态 Esc 应请求取消当前 accepted Run。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="interactive",
        scenario="interactive",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost(
        submit_statuses=(None,),
        cancel_status=HostTerminalStatus.CANCELLED,
        run_statuses=(RunStatus.RUNNING,),
    )
    stderr = io.StringIO()
    run_view = TerminalInteractiveRunView(
        stderr=stderr,
        options=InteractiveRunViewOptions(
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
    thinking_renderer.record(
        _entrypoint_thinking(
            dedupe_key="thinking-before-esc",
            text_delta="The user is asking",
        )
    )

    result = await session_execution._submit_interactive_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        turn_index=1,
        user_prompt="请总结收入变化",
        run_overrides=ServiceRunOverrides(),
        sigint_monitor=_NoopSigintMonitor(),
        run_view=run_view,
        thinking_renderer=thinking_renderer,
        key_monitor=key_monitor,
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.CANCELLED
    assert len(fake_host.cancel_requests) == 1
    assert fake_host.cancel_requests[0].client_request_id.endswith(":turn-1:run-run-1:cancel:cli_sigint")
    assert "Thinking: The user is asking\r\x1b[2KInteractive: cancel requested" in (
        stderr.getvalue()
    )
    thinking_renderer.record(_entrypoint_thinking(dedupe_key="thinking-after-esc"))
    assert stderr.getvalue().count("Thinking:") == 1
    assert key_monitor.started_count == 1
    assert key_monitor.closed_count == 1


@pytest.mark.asyncio
async def test_interactive_ctrl_t_switches_run_view_without_cancel(
    tmp_path: Path,
) -> None:
    """interactive 运行态 Ctrl+T 应切换 run view，且不得触发 Host cancel。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="interactive",
        scenario="interactive",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost(
        submit_statuses=(HostTerminalStatus.SUCCEEDED,),
        submit_activities=(True,),
    )
    stderr = io.StringIO()
    run_view = TerminalInteractiveRunView(
        stderr=stderr,
        options=InteractiveRunViewOptions(enabled=True),
    )
    key_monitor = _FakeRunningKeyMonitor((RunningKeyAction.TOGGLE_ACTIVITY,))

    result = await session_execution._submit_interactive_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        turn_index=1,
        user_prompt="请总结收入变化",
        run_overrides=ServiceRunOverrides(),
        sigint_monitor=_NoopSigintMonitor(),
        run_view=run_view,
        key_monitor=key_monitor,
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.SUCCEEDED
    assert fake_host.cancel_requests == []
    assert run_view.activity_lines
    assert "[Interactive activity]" in stderr.getvalue()
    assert "Activity hidden" not in stderr.getvalue()
    assert key_monitor.started_count == 1
    assert key_monitor.closed_count == 1


@pytest.mark.asyncio
async def test_interactive_second_sigint_exits_after_cancel_request(
    tmp_path: Path,
) -> None:
    """运行态第二次 SIGINT 应本地退出 130，且已有 run 必须已发 cancel。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="interactive",
        scenario="interactive",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost(
        submit_statuses=(None,),
        run_statuses=(RunStatus.RUNNING,),
        block_cancel_after_record=True,
    )

    result = await session_execution._submit_interactive_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        turn_index=1,
        user_prompt="请总结收入变化",
        run_overrides=ServiceRunOverrides(),
        sigint_monitor=_SecondSigintAfterCancelMonitor(fake_host),
    )

    assert result is None
    assert len(fake_host.cancel_requests) == 1
    assert fake_host.cancel_requests[0].client_request_id.endswith(":turn-1:run-run-1:cancel:cli_sigint")


@pytest.mark.asyncio
async def test_interactive_repl_returns_130_on_second_sigint(
    tmp_path: Path,
) -> None:
    """REPL 中第二次 SIGINT 应返回 130，且没有 terminal 时不得推进 cursor。

    :param tmp_path: pytest 临时目录夹具。
    :returns: ``None``。
    :raises AssertionError: 退出码、cancel 请求或 cursor 水位错误时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = session_execution.new_cli_invocation(
        command_name="interactive",
        scenario="interactive",
        display_user="本地 CLI 用户",
        ticker="AAPL",
    )
    fake_host = _FakeHost(
        submit_statuses=(None,),
        run_statuses=(RunStatus.RUNNING,),
        block_cancel_after_record=True,
    )

    exit_code = await session_execution._run_interactive_repl(
        host=cast(Host, fake_host),
        runtime=runtime,
        workspace_root=tmp_path,
        invocation=invocation,
        session_id="session-1",
        run_overrides=ServiceRunOverrides(),
        input_reader=_input_reader(("请总结收入变化",)),
        sigint_monitor_factory=lambda: _SecondSigintAfterCancelMonitor(fake_host),
    )

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(fake_host.cancel_requests) == 1
    cursor_record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-1",
    )
    assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=0)
    assert cursor_record.seen_terminal_event_ids == ()


def test_interactive_thinking_flags_are_display_options() -> None:
    """``--thinking`` / ``--no-thinking`` 保持为明确的展示选项。

    :returns: ``None``。
    :raises AssertionError: thinking 展示参数未被正确解析时抛出。
    """

    thinking_args = parse_cli_args(("interactive", "--thinking"))
    no_thinking_args = parse_cli_args(("interactive", "--no-thinking"))

    assert thinking_args.thinking is True
    assert no_thinking_args.thinking is False


def test_interactive_debug_stream_is_global_log_option() -> None:
    """``--debug-stream`` 保持为全局日志开关。

    :returns: ``None``。
    :raises AssertionError: debug-stream 未被正确解析时抛出。
    """

    args = parse_cli_args(("interactive", "--debug-stream"))

    assert args.debug_stream is True


@pytest.mark.parametrize("removed_args", _REMOVED_INTERACTIVE_DEBUG_OPTIONS)
def test_interactive_removed_debug_options_are_argparse_unknown(
    removed_args: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """已删除 debug 参数应由 argparse 作为未知参数拒绝。

    :param removed_args: 单个已删除 debug 参数及其取值。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 参数未按未知参数返回用法错误时抛出。
    """

    exit_code = cli_main.main(("interactive", *removed_args))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "unrecognized arguments" in captured.err
    assert removed_args[0] in captured.err


def test_interactive_rejects_all_removed_execution_flags_as_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """所有已删除旧参数都应由 argparse 清晰拒绝。"""

    exit_code = cli_main.main(
        (
            "interactive",
            "--tool-trace-dir",
            "trace",
            "--max-duplicate-tool-calls",
            "2",
            "--duplicate-tool-hint-prompt",
            "hint",
            "--fins-limits-json",
            "{}",
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


@pytest.mark.asyncio
async def test_interactive_sigint_monitor_waits_for_notification() -> None:
    """SIGINT monitor wait_next 应等待 notify 并返回新计数。"""

    monitor = CliSigintMonitor()
    wait_task = asyncio.create_task(monitor.wait_next(0))

    await asyncio.sleep(0)
    monitor.notify()

    assert await wait_task == 1


@pytest.mark.asyncio
async def test_wait_for_run_id_returns_none_when_second_sigint_wins() -> None:
    """run id 尚未 accepted 时第二次 SIGINT 应取消 submit task 并返回本地退出 outcome。"""

    accepted_run = session_execution._InteractiveAcceptedRunState()
    submit_task = asyncio.create_task(_never_finishes_terminal())
    monitor = _ImmediateSecondSigintMonitor()

    result = await session_execution._wait_for_run_id_or_local_exit(
        accepted_run=accepted_run,
        submit_task=submit_task,
        sigint_monitor=monitor,
        observed_sigint_count=1,
    )

    assert isinstance(result, session_execution._LocalExitRequested)
    assert submit_task.cancelled()


@pytest.mark.asyncio
async def test_wait_for_run_id_returns_submit_terminal_when_submit_completes_first() -> None:
    """等待 run id 阶段 submit task 先返回成功终态时不得映射成本地 130。"""

    accepted_run = session_execution._InteractiveAcceptedRunState()
    terminal = _terminal_result(status=HostTerminalStatus.SUCCEEDED)
    submit_task = asyncio.create_task(_already_terminal(terminal))
    await asyncio.sleep(0)

    result = await session_execution._wait_for_run_id_or_local_exit(
        accepted_run=accepted_run,
        submit_task=submit_task,
        sigint_monitor=_NeverSigintMonitor(),
        observed_sigint_count=1,
    )

    assert isinstance(
        result,
        session_execution._SubmitCompletedWhileWaitingForRunId,
    )
    assert result.terminal is terminal


@pytest.mark.asyncio
async def test_wait_for_run_id_propagates_submit_failure_when_submit_fails_first() -> None:
    """等待 run id 阶段 submit task 先失败时必须向上透传 Host/API fatal。"""

    accepted_run = session_execution._InteractiveAcceptedRunState()
    submit_task = asyncio.create_task(_raise_runtime_error_terminal())
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="host fatal"):
        await session_execution._wait_for_run_id_or_local_exit(
            accepted_run=accepted_run,
            submit_task=submit_task,
            sigint_monitor=_NeverSigintMonitor(),
            observed_sigint_count=1,
        )


@pytest.mark.asyncio
async def test_cancel_after_first_sigint_returns_completed_submit_terminal() -> None:
    """第一次 SIGINT 竞争中若 submit 已终态，应直接返回 submit terminal。"""

    accepted_run = session_execution._InteractiveAcceptedRunState()
    accepted_run.record("run-1")
    submit_task = asyncio.create_task(_already_terminal(_terminal_result(status=HostTerminalStatus.SUCCEEDED)))
    await asyncio.sleep(0)
    stderr = io.StringIO()
    thinking_renderer = CliThinkingRenderer(
        stderr=stderr,
        options=CliThinkingRendererOptions(enabled=True),
    )

    result = await session_execution._cancel_interactive_turn_after_first_sigint(
        host=cast(Host, _FakeHost()),
        invocation=session_execution.new_cli_invocation(
            command_name="interactive",
            scenario="interactive",
            display_user="本地 CLI 用户",
            ticker="AAPL",
        ),
        turn_index=1,
        accepted_run=accepted_run,
        submit_task=submit_task,
        sigint_monitor=_ImmediateSecondSigintMonitor(),
        observed_sigint_count=1,
        runtime_display=RuntimeDisplayController(
            activity_display=None,
            thinking_display=thinking_renderer,
        ),
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.SUCCEEDED
    thinking_renderer.record(_entrypoint_thinking(dedupe_key="thinking-1"))
    assert stderr.getvalue() == ""


async def _prepare_interactive_runtime(tmp_path: Path) -> EntrypointRuntimeResult:
    """构造真实 interactive runtime assembly 测试结果。

    :param tmp_path: pytest 临时 workspace root。
    :returns: entrypoint runtime result。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    return await session_execution.prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=package_config_root(),
            explicit_config_dir=None,
            scene_id="interactive",
            context_slot_values={
                _FINS_DEFAULT_SUBJECT_SLOT: "",
                _CURRENT_TIME_SLOT: _CURRENT_TIME_TEXT,
            },
            assembly_overrides=ServiceAssemblyOverrides(model_id=_MODEL_ID),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )


def _input_reader(values: tuple[str, ...]) -> Callable[[str], str]:
    """构造测试输入函数。

    :param values: 依次返回的输入文本。
    :returns: 输入函数；耗尽后抛 ``EOFError``。
    :raises Exception: 不主动抛出异常。
    """

    return _InputReader(values)


class _ImmediateSecondSigintMonitor(CliSigintMonitor):
    """测试用立即第二次 SIGINT monitor。"""

    def install(self) -> None:
        """测试中不安装真实 OS signal handler。"""

        return

    def close(self) -> None:
        """测试中无需恢复 OS signal handler。"""

        return

    async def wait_next(self, observed_count: int) -> int:
        """立即触发下一次 SIGINT。"""

        if self.count <= observed_count:
            self.count = observed_count
            self.notify()
        return self.count


class _NeverSigintMonitor(CliSigintMonitor):
    """测试用永不触发的 SIGINT monitor。"""

    def install(self) -> None:
        """测试中不安装真实 OS signal handler。"""

        return

    def close(self) -> None:
        """测试中无需恢复 OS signal handler。"""

        return

    async def wait_next(self, observed_count: int) -> int:
        """永不主动返回，等待任务取消。

        :param observed_count: 已观察到的 SIGINT 计数。
        :returns: 正常路径不会返回。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        await asyncio.Event().wait()
        return observed_count


async def _never_finishes_terminal() -> EntrypointRunTerminalResult:
    """构造永不完成的 terminal task。

    :returns: 正常路径不会返回。
    :raises asyncio.CancelledError: task 被取消时透传。
    """

    await asyncio.Event().wait()
    raise AssertionError("terminal task should be cancelled")


async def _already_terminal(
    result: EntrypointRunTerminalResult,
) -> EntrypointRunTerminalResult:
    """返回已完成 terminal result。

    :param result: 待返回的 terminal result。
    :returns: 传入的 terminal result。
    :raises Exception: 不主动抛出异常。
    """

    return result


async def _raise_runtime_error_terminal() -> EntrypointRunTerminalResult:
    """构造抛出 RuntimeError 的 terminal task。

    :returns: 正常路径不会返回。
    :raises RuntimeError: 始终抛出，用于验证 fatal 透传。
    """

    raise RuntimeError("host fatal")


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


def _terminal_event(*, run_id: str, status: HostTerminalStatus) -> HostEvent:
    """构造 Host terminal event。

    :param run_id: Run id。
    :param status: terminal status。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id=f"terminal-{run_id}",
        event_sequence=int(run_id.removeprefix("run-")) + 1,
        session_id="session-1",
        run_id=run_id,
        event_class=HostEventClass.CANONICAL_FACT,
        event_type=_event_type(status),
        kind=_event_kind(status),
        activity=None,
        dedupe_key=f"terminal-{run_id}",
        terminal_status=status,
        final_answer=_final_answer(run_id=run_id) if status is HostTerminalStatus.SUCCEEDED else None,
        error_message=_error_message(run_id=run_id, status=status),
        cancel_reason=f"cancelled for {run_id}" if status is HostTerminalStatus.CANCELLED else None,
    )


def _activity_event(*, run_id: str) -> HostEvent:
    """构造 Host activity event。

    :param run_id: Run id。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id=f"activity-{run_id}",
        event_sequence=int(run_id.removeprefix("run-")) + 1,
        session_id="session-1",
        run_id=run_id,
        event_class=HostEventClass.PREVIEW,
        event_type="TOOL_CALLS_BATCH_DONE",
        kind=HostEventKind.PROGRESS,
        activity=HostActivityView(
            kind=HostActivityKind.TOOL_BATCH,
            status=HostActivityStatus.COMPLETED,
            title="工具批次完成",
            summary="完成 1 个工具调用。",
            severity=HostActivitySeverity.INFO,
            tool_name="record_smoke_fact",
            tool_display_name="记录烟测事实",
            counts=HostActivityCounts(total=1, completed=1, failed=0, cancelled=0),
        ),
        dedupe_key=f"activity-{run_id}",
        terminal_status=None,
        final_answer=None,
        error_message=None,
        cancel_reason=None,
    )


def _thinking_event(*, run_id: str) -> HostTransientDelta:
    """构造 Host thinking event。

    :param run_id: Run id。
    :returns: HostTransientDelta。
    :raises Exception: 不主动抛出异常。
    """

    runtime_sequence = int(run_id.removeprefix("run-"))
    return HostTransientDelta(
        runtime_id="runtime-1",
        runtime_sequence=runtime_sequence,
        session_id="session-1",
        run_id=run_id,
        attempt_id=f"attempt-{run_id}",
        execution_id=f"execution-{run_id}",
        worker_event_index=runtime_sequence,
        observed_at=_TRANSIENT_OBSERVED_AT,
        type=HostTransientDeltaType.REASONING_DELTA,
        data=HostReasoningDelta(
            iteration_id=f"iteration-{run_id}",
            text_delta="正在分析收入变化",
        ),
        dedupe_key=f"thinking-{run_id}",
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


def _terminal_result(*, status: HostTerminalStatus) -> EntrypointRunTerminalResult:
    """构造 interactive terminal result。

    :param status: terminal status。
    :returns: EntrypointRunTerminalResult。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        session_id="session-1",
        run_id="run-1",
        terminal_event_id="terminal-run-1",
        event_sequence=2,
        terminal_status=status,
        dedupe_key="terminal-run-1",
        final_answer=_final_answer(run_id="run-1") if status is HostTerminalStatus.SUCCEEDED else None,
        error_message=_error_message(run_id="run-1", status=status),
        cancel_reason="cancelled for run-1" if status is HostTerminalStatus.CANCELLED else None,
        watcher_failure_message=None,
    )


def _startup_terminal_result(
    *,
    session_id: str,
    status: HostTerminalStatus,
) -> EntrypointRunTerminalResult:
    """构造 startup reconnect terminal result。

    :param session_id: startup reconnect 目标 Session id。
    :param status: terminal status。
    :returns: EntrypointRunTerminalResult。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.OUTBOX_READ,
        session_id=session_id,
        run_id="run-startup",
        terminal_event_id="terminal-startup",
        event_sequence=5,
        terminal_status=status,
        dedupe_key="terminal-startup",
        final_answer=(
            _final_answer(run_id="run-startup")
            if status is HostTerminalStatus.SUCCEEDED
            else None
        ),
        error_message=_error_message(run_id="run-startup", status=status),
        cancel_reason=(
            "cancelled for run-startup"
            if status is HostTerminalStatus.CANCELLED
            else None
        ),
        watcher_failure_message=None,
    )


def _error_message(*, run_id: str, status: HostTerminalStatus) -> str | None:
    """构造测试 terminal 错误消息。

    :param run_id: Run id。
    :param status: terminal status。
    :returns: 错误消息；非错误状态返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if status is HostTerminalStatus.FAILED:
        return f"failed for {run_id}"
    if status is HostTerminalStatus.LOST:
        return f"lost for {run_id}"
    return None


def _final_answer(*, run_id: str) -> HostFinalAnswerView:
    """构造成功 final answer view。

    :param run_id: Run id。
    :returns: HostFinalAnswerView。
    :raises Exception: 不主动抛出异常。
    """

    return HostFinalAnswerView(
        content=f"answer for {run_id}",
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
