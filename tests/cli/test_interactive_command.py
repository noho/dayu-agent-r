"""``dayu-cli interactive`` 命令测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import cast

import pytest

import dayu.cli.commands.interactive as interactive_command
import dayu.cli.main as cli_main
from dayu.cli.agent_entrypoint import CliSigintMonitor, package_config_root
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
    HostEvent,
    HostEventKind,
    HostFinalAnswerView,
    HostStreamCursor,
    HostTerminalStatus,
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
)
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointTerminalSource,
)

_MODEL_ID = "deepseek-v4-flash"
_API_KEY = "test-provider-key"


@dataclass(frozen=True, slots=True)
class _StopSignal:
    """测试 watcher 停止信号。"""


class _FakeHostEventIterator:
    """测试用 Host event iterator。"""

    closed_count: int
    _queue: asyncio.Queue[HostEvent | _StopSignal]

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
        return item

    async def push(self, event: HostEvent) -> None:
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
    _cancel_status: HostTerminalStatus | None
    _run_statuses: tuple[RunStatus, ...]
    _submit_index: int
    _run_status_index: int
    block_cancel_after_record: bool

    def __init__(
        self,
        *,
        submit_statuses: tuple[HostTerminalStatus | None, ...] = (),
        cancel_status: HostTerminalStatus | None = None,
        run_statuses: tuple[RunStatus, ...] = (RunStatus.SUCCEEDED,),
        block_cancel_after_record: bool = False,
    ) -> None:
        """初始化 fake Host。

        :param submit_statuses: 每轮 submit 返回前推入 watcher 的 terminal
            状态；``None`` 表示该轮 watcher 不产生 terminal。
        :param cancel_status: cancel 返回前推入 watcher 的 terminal 状态。
        :param run_statuses: ``get_run`` 依次返回的状态。
        :param block_cancel_after_record: 是否在记录 cancel 后阻塞。
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
        self._cancel_status = cancel_status
        self._run_statuses = run_statuses
        self._submit_index = 0
        self._run_status_index = 0
        self.block_cancel_after_record = block_cancel_after_record

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

    async def submit_followup(
        self, session_id: str, request: SubmitFollowupRequest
    ) -> FollowupSnapshot:
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
            await self.watchers[-1].push(
                _terminal_event(run_id=run_id, status=self._cancel_status)
            )
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
    real_prepare = interactive_command.prepare_entrypoint_runtime

    async def capture_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """捕获 runtime request。"""

        captured_requests.append(request)
        return await real_prepare(request)

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
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
    assert captured_requests[0].context_slot_values == {
        "fins_default_subject": "AAPL",
        "base_user": "本地 CLI 用户",
    }
    assert fake_host.ensure_requests[0].scope == "cli.interactive"
    assert fake_host.ensure_requests[0].slot_key == "cli.interactive.earnings"
    assert fake_host.create_requests == []


@pytest.mark.parametrize("log_flag", ("--verbose", "--debug"))
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


def test_interactive_new_session_creates_bound_process_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--new-session`` 应走 create_session(bind_slot=True)。"""

    fake_host = _FakeHost()
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )
    monkeypatch.setattr(interactive_command, "_read_user_input", _input_reader(()))

    exit_code = cli_main.main(
        ("interactive", "--base", str(tmp_path), "--new-session")
    )

    assert exit_code == EXIT_SUCCESS
    assert fake_host.create_requests[0].bind_slot is True
    assert fake_host.create_requests[0].scope == "cli.interactive"
    assert fake_host.create_requests[0].slot_key is not None
    assert fake_host.create_requests[0].slot_key.startswith("cli.interactive.")


def test_interactive_input_keyboard_interrupt_exits_without_run_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """输入态 Ctrl-C 应退出当前 command，且不发 submit / cancel。"""

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

    exit_code = cli_main.main(
        ("interactive", "--base", str(tmp_path), "--label", " ")
    )
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
    assert [watcher.closed_count for watcher in fake_host.watchers] == [1, 1]
    first_submit = fake_host.submit_requests[0]
    second_submit = fake_host.submit_requests[1]
    assert first_submit.client_request_id.endswith(":turn-1:submit")
    assert second_submit.client_request_id.endswith(":turn-2:submit")
    assert first_submit.context.request_id != second_submit.context.request_id


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
async def test_interactive_sigint_after_run_id_cancels_host_run(
    tmp_path: Path,
) -> None:
    """运行态第一次 SIGINT 应发完整 CancelRunRequest 并返回取消终态。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = interactive_command.new_cli_invocation(
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

    result = await interactive_command._submit_interactive_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        turn_index=1,
        user_prompt="请总结收入变化",
        run_overrides=interactive_command.ServiceRunOverrides(),
        sigint_monitor=_AutoSigintMonitor(),
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.CANCELLED
    assert len(fake_host.cancel_requests) == 1
    cancel_request = fake_host.cancel_requests[0]
    assert cancel_request.reason == "cli_sigint"
    assert cancel_request.mode is CancelMode.GRACEFUL
    assert cancel_request.client_request_id.endswith(
        ":turn-1:run-run-1:cancel:cli_sigint"
    )
    assert cancel_request.context.operation_context.operation_name == (
        "dayu_cli.interactive.cancel_run"
    )


@pytest.mark.asyncio
async def test_interactive_second_sigint_exits_after_cancel_request(
    tmp_path: Path,
) -> None:
    """运行态第二次 SIGINT 应本地退出 130，且已有 run 必须已发 cancel。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = interactive_command.new_cli_invocation(
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

    result = await interactive_command._submit_interactive_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        turn_index=1,
        user_prompt="请总结收入变化",
        run_overrides=interactive_command.ServiceRunOverrides(),
        sigint_monitor=_SecondSigintAfterCancelMonitor(fake_host),
    )

    assert result is None
    assert len(fake_host.cancel_requests) == 1
    assert fake_host.cancel_requests[0].client_request_id.endswith(
        ":turn-1:run-run-1:cancel:cli_sigint"
    )


@pytest.mark.asyncio
async def test_interactive_repl_returns_130_on_second_sigint(
    tmp_path: Path,
) -> None:
    """REPL 中第二次 SIGINT 应返回 130。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    invocation = interactive_command.new_cli_invocation(
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

    exit_code = await interactive_command._run_interactive_repl(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        run_overrides=interactive_command.ServiceRunOverrides(),
        input_reader=_input_reader(("请总结收入变化",)),
        sigint_monitor_factory=lambda: _SecondSigintAfterCancelMonitor(fake_host),
    )

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(fake_host.cancel_requests) == 1


def test_interactive_unsupported_old_flag_exits_with_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """unsupported 旧执行参数应 fail fast。"""

    exit_code = cli_main.main(("interactive", "--thinking"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "unsupported option" in captured.err
    assert "--thinking/--no-thinking" in captured.err


def test_interactive_reports_all_unsupported_old_execution_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """unsupported 旧参数应统一列入清晰错误。"""

    exit_code = cli_main.main(
        (
            "interactive",
            "--debug-sse",
            "--debug-tool-delta",
            "--debug-sse-sample-rate",
            "0.5",
            "--debug-sse-throttle-sec",
            "1.0",
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
    for expected in (
        "--debug-sse",
        "--debug-tool-delta",
        "--debug-sse-sample-rate",
        "--debug-sse-throttle-sec",
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

    accepted_run = interactive_command._AcceptedRunState()
    submit_task = asyncio.create_task(_never_finishes_terminal())
    monitor = _ImmediateSecondSigintMonitor()

    result = await interactive_command._wait_for_run_id_or_local_exit(
        accepted_run=accepted_run,
        submit_task=submit_task,
        sigint_monitor=monitor,
        observed_sigint_count=1,
    )

    assert isinstance(result, interactive_command._LocalExitRequested)
    assert submit_task.cancelled()


@pytest.mark.asyncio
async def test_wait_for_run_id_returns_submit_terminal_when_submit_completes_first() -> None:
    """等待 run id 阶段 submit task 先返回成功终态时不得映射成本地 130。"""

    accepted_run = interactive_command._AcceptedRunState()
    terminal = _terminal_result(status=HostTerminalStatus.SUCCEEDED)
    submit_task = asyncio.create_task(_already_terminal(terminal))
    await asyncio.sleep(0)

    result = await interactive_command._wait_for_run_id_or_local_exit(
        accepted_run=accepted_run,
        submit_task=submit_task,
        sigint_monitor=_NeverSigintMonitor(),
        observed_sigint_count=1,
    )

    assert isinstance(
        result,
        interactive_command._SubmitCompletedWhileWaitingForRunId,
    )
    assert result.terminal is terminal


@pytest.mark.asyncio
async def test_wait_for_run_id_propagates_submit_failure_when_submit_fails_first() -> None:
    """等待 run id 阶段 submit task 先失败时必须向上透传 Host/API fatal。"""

    accepted_run = interactive_command._AcceptedRunState()
    submit_task = asyncio.create_task(_raise_runtime_error_terminal())
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="host fatal"):
        await interactive_command._wait_for_run_id_or_local_exit(
            accepted_run=accepted_run,
            submit_task=submit_task,
            sigint_monitor=_NeverSigintMonitor(),
            observed_sigint_count=1,
        )


@pytest.mark.asyncio
async def test_cancel_after_first_sigint_returns_completed_submit_terminal() -> None:
    """第一次 SIGINT 竞争中若 submit 已终态，应直接返回 submit terminal。"""

    accepted_run = interactive_command._AcceptedRunState()
    accepted_run.record("run-1")
    submit_task = asyncio.create_task(
        _already_terminal(_terminal_result(status=HostTerminalStatus.SUCCEEDED))
    )
    await asyncio.sleep(0)

    result = await interactive_command._cancel_interactive_turn_after_first_sigint(
        host=cast(Host, _FakeHost()),
        invocation=interactive_command.new_cli_invocation(
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
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.SUCCEEDED


async def _prepare_interactive_runtime(tmp_path: Path) -> EntrypointRuntimeResult:
    """构造真实 interactive runtime assembly 测试结果。

    :param tmp_path: pytest 临时 workspace root。
    :returns: entrypoint runtime result。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    return await interactive_command.prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=package_config_root(),
            explicit_config_dir=None,
            scene_id="interactive",
            context_slot_values={
                "fins_default_subject": "AAPL",
                "base_user": "本地 CLI 用户",
            },
            assembly_overrides=interactive_command.ServiceAssemblyOverrides(
                model_id=_MODEL_ID
            ),
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


async def _never_finishes_terminal() -> interactive_command.EntrypointRunTerminalResult:
    """构造永不完成的 terminal task。

    :returns: 正常路径不会返回。
    :raises asyncio.CancelledError: task 被取消时透传。
    """

    await asyncio.Event().wait()
    raise AssertionError("terminal task should be cancelled")


async def _already_terminal(
    result: interactive_command.EntrypointRunTerminalResult,
) -> interactive_command.EntrypointRunTerminalResult:
    """返回已完成 terminal result。

    :param result: 待返回的 terminal result。
    :returns: 传入的 terminal result。
    :raises Exception: 不主动抛出异常。
    """

    return result


async def _raise_runtime_error_terminal() -> interactive_command.EntrypointRunTerminalResult:
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

    return RunSnapshot(
        run_id=run_id,
        session_id="session-1",
        status=status,
        current_attempt_id=None,
        terminal_result_summary=None,
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
        kind=_event_kind(status),
        dedupe_key=f"terminal-{run_id}",
        terminal_status=status,
        final_answer=_final_answer(run_id=run_id)
        if status is HostTerminalStatus.SUCCEEDED
        else None,
        error_message=_error_message(run_id=run_id, status=status),
        cancel_reason=f"cancelled for {run_id}"
        if status is HostTerminalStatus.CANCELLED
        else None,
    )


def _terminal_result(
    *, status: HostTerminalStatus
) -> interactive_command.EntrypointRunTerminalResult:
    """构造 interactive terminal result。

    :param status: terminal status。
    :returns: EntrypointRunTerminalResult。
    :raises Exception: 不主动抛出异常。
    """

    return interactive_command.EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        session_id="session-1",
        run_id="run-1",
        terminal_event_id="terminal-run-1",
        event_sequence=2,
        terminal_status=status,
        dedupe_key="terminal-run-1",
        final_answer=_final_answer(run_id="run-1")
        if status is HostTerminalStatus.SUCCEEDED
        else None,
        error_message=_error_message(run_id="run-1", status=status),
        cancel_reason="cancelled for run-1"
        if status is HostTerminalStatus.CANCELLED
        else None,
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
