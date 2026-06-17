"""``dayu-cli prompt`` 命令测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from pathlib import Path
from typing import cast

import pytest

import dayu.cli.commands.prompt as prompt_command
import dayu.cli.main as cli_main
from dayu.cli.agent_entrypoint import CliSigintMonitor, package_config_root
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
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostFinalAnswerView,
    HostStreamCursor,
    HostTerminalStatus,
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
)
from dayu.service.entrypoint_runtime import EntrypointRuntimeRequest
from dayu.service.entrypoint_runtime import EntrypointRuntimeResult

_NOW = datetime(2026, 6, 14, 8, 0, 0, tzinfo=UTC)
_MODEL_ID = "deepseek-v4-flash"
_API_KEY = "test-provider-key"
_DEFAULT_PROMPT_TOOL_NAME = "get_financial_statement"


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
    """CLI prompt 测试用 Host public API 替身。"""

    calls: list[str]
    watchers: list[_FakeHostEventIterator]
    ensure_requests: list[EnsureSessionRequest]
    create_requests: list[CreateSessionRequest]
    submit_requests: list[SubmitFollowupRequest]
    cancel_requests: list[CancelRunRequest]
    read_outbox_requests: list[ReadOutboxTerminalItemsRequest]
    _submit_terminal: HostEvent | None
    _cancel_terminal: HostEvent | None
    _outbox_item: OutboxTerminalItem | None
    _run_statuses: tuple[RunStatus, ...]
    _run_status_index: int

    def __init__(
        self,
        *,
        submit_terminal: HostEvent | None,
        run_statuses: tuple[RunStatus, ...] = (RunStatus.SUCCEEDED,),
        outbox_item: OutboxTerminalItem | None = None,
        cancel_terminal: HostEvent | None = None,
    ) -> None:
        """初始化 fake Host。

        :param submit_terminal: submit 返回前推入的 terminal event；``None``
            表示 watcher 不产生 terminal。
        :param run_statuses: ``get_run`` 依次返回的状态。
        :param outbox_item: outbox fallback 返回的 terminal item。
        :param cancel_terminal: cancel 返回前推入的 terminal event。
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
        self._cancel_terminal = cancel_terminal
        self._outbox_item = outbox_item
        self._run_statuses = run_statuses
        self._run_status_index = 0

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
        if self._submit_terminal is not None:
            await self.watchers[-1].push(self._submit_terminal)
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
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"cancel:{run_id}")
        self.cancel_requests.append(request)
        if self._cancel_terminal is not None:
            await self.watchers[-1].push(self._cancel_terminal)
            await asyncio.sleep(0)
        return _run_snapshot(run_id=run_id, status=RunStatus.CANCELLING)


class _BlockingSubmitHost(_FakeHost):
    """submit_followup 永不接受 Run 的 fake Host。"""

    async def submit_followup(
        self, session_id: str, request: SubmitFollowupRequest
    ) -> FollowupSnapshot:
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


def test_prompt_command_outputs_fast_live_terminal_and_converts_requests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt 命令应经 Service helper 提交并输出 live final answer。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED))
    captured_requests: list[EntrypointRuntimeRequest] = []
    real_prepare = prompt_command.prepare_entrypoint_runtime

    async def capture_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """捕获 CLI 传给 Service helper 的 runtime request。"""

        captured_requests.append(request)
        return await real_prepare(request)

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(prompt_command, "prepare_entrypoint_runtime", capture_prepare)
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
    assert captured.err == ""
    assert captured_requests[0].scene_id == "prompt"
    assert captured_requests[0].context_slot_values == {
        "fins_default_subject": "AAPL",
        "base_user": "本地 CLI 用户",
    }
    assert captured_requests[0].assembly_overrides.model_id == _MODEL_ID
    assert fake_host.ensure_requests[0].scope == "cli.prompt"
    assert fake_host.ensure_requests[0].slot_key == "cli.prompt.earnings"
    assert fake_host.calls[:3] == ["ensure_session", "watch:session-1", "submit:session-1"]
    submit_request = fake_host.submit_requests[0]
    assert submit_request.user_prompt == "请总结收入变化"
    assert submit_request.tool_names is not None
    assert _DEFAULT_PROMPT_TOOL_NAME in submit_request.tool_names
    assert submit_request.runner_options is not None
    assert submit_request.runner_options.temperature == 0.2
    assert submit_request.agent_policy is not None
    assert submit_request.context.request_id != submit_request.client_request_id
    assert submit_request.context.operation_context.business_object_id == "AAPL"


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
    prepared = await prompt_command._prepare_prompt_existing_session_execution(
        args,
        command_name="session",
        scenario="prompt",
        user_prompt="请继续分析",
    )
    fake_host = _FakeHost(
        submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED)
    )

    exit_code = await prompt_command._execute_prompt_on_existing_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        sigint_monitor=_NoopSigintMonitor(),
    )

    assert exit_code == EXIT_SUCCESS
    assert fake_host.ensure_requests == []
    assert fake_host.create_requests == []
    assert fake_host.calls == ["watch:session-existing", "submit:session-existing"]
    assert fake_host.submit_requests[0].user_prompt == "请继续分析"
    assert fake_host.submit_requests[0].behavior is FollowupBehavior.QUEUE
    assert fake_host.submit_requests[0].target_run_id is None


@pytest.mark.parametrize("log_flag", ("--verbose", "--debug"))
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

    fake_host = _FakeHost(submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED))
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


def test_prompt_command_without_ticker_uses_default_context_slots(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未传 ticker 时 prompt command 应填充默认 LLM-facing slots。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(submit_terminal=_terminal_event(status=HostTerminalStatus.SUCCEEDED))
    captured_requests: list[EntrypointRuntimeRequest] = []
    real_prepare = prompt_command.prepare_entrypoint_runtime

    async def capture_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """捕获 runtime request。"""

        captured_requests.append(request)
        return await real_prepare(request)

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(prompt_command, "prepare_entrypoint_runtime", capture_prepare)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(
        ("prompt", "--base", str(workspace_root), "请总结收入变化")
    )

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out.strip() == "prompt answer"
    assert captured_requests[0].context_slot_values == {
        "fins_default_subject": "未指定具体公司",
        "base_user": "本地 CLI 用户",
    }
    assert fake_host.create_requests[0].bind_slot is False
    assert fake_host.submit_requests[0].context.operation_context.business_object_id is None


def test_prompt_command_uses_outbox_fallback_when_live_terminal_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """watcher 无 terminal 时 prompt command 应通过 public outbox fallback 输出。"""

    workspace_root = tmp_path
    fake_host = _FakeHost(
        submit_terminal=None,
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_item=_outbox_item(),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        prompt_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(
        ("prompt", "--base", str(workspace_root), "请总结收入变化")
    )

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out.strip() == "prompt answer"
    assert fake_host.read_outbox_requests[0].after == OutboxTerminalCursor(
        event_sequence=0
    )
    assert fake_host.read_outbox_requests[0].limit == 50


@pytest.mark.asyncio
async def test_prompt_sigint_after_run_id_cancels_host_run(
    tmp_path: Path,
) -> None:
    """Run accepted 后 SIGINT 应构造完整 CancelRunRequest 并复用幂等 id。"""

    workspace_root = tmp_path
    runtime = await prompt_command.prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root(),
            explicit_config_dir=None,
            scene_id="prompt",
            context_slot_values={
                "fins_default_subject": "AAPL",
                "base_user": "本地 CLI 用户",
            },
            assembly_overrides=prompt_command.ServiceAssemblyOverrides(
                model_id=_MODEL_ID
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )
    invocation = prompt_command.new_cli_invocation(
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

    result = await prompt_command._submit_prompt_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=invocation,
        session_id="session-1",
        user_prompt="请总结收入变化",
        run_overrides=prompt_command.ServiceRunOverrides(),
        sigint_monitor=_AutoSigintMonitor(),
    )

    assert result is not None
    assert result.terminal_status is HostTerminalStatus.CANCELLED
    assert len(fake_host.cancel_requests) == 1
    cancel_request = fake_host.cancel_requests[0]
    assert cancel_request.reason == "cli_sigint"
    assert cancel_request.mode is CancelMode.GRACEFUL
    assert cancel_request.client_request_id.endswith(":turn-1:run-run-1:cancel:cli_sigint")
    assert cancel_request.context.operation_context.operation_name == (
        "dayu_cli.prompt.cancel_run"
    )
    assert fake_host.calls[0:2] == ["watch:session-1", "submit:session-1"]
    assert fake_host.calls[-2:] == ["watch:session-1", "cancel:run-1"]


@pytest.mark.parametrize(
    "unsupported_args, expected_fragment",
    (
        (("--thinking",), "--thinking/--no-thinking"),
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


def test_prompt_command_reports_all_unsupported_old_execution_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """unsupported 旧参数应统一列入清晰错误。"""

    exit_code = cli_main.main(
        (
            "prompt",
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
            "请总结收入变化",
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

    exit_code = cli_main.main(
        ("prompt", "--base", str(tmp_path), "--label", " ", "请总结收入变化")
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "--label" in captured.err


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

    runtime = await prompt_command.prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=package_config_root(),
            explicit_config_dir=None,
            scene_id="prompt",
            context_slot_values={
                "fins_default_subject": "AAPL",
                "base_user": "本地 CLI 用户",
            },
            assembly_overrides=prompt_command.ServiceAssemblyOverrides(
                model_id=_MODEL_ID
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )
    fake_host = _BlockingSubmitHost(submit_terminal=None)

    result = await prompt_command._submit_prompt_turn_handling_sigint(
        host=cast(Host, fake_host),
        runtime=runtime,
        invocation=prompt_command.new_cli_invocation(
            command_name="prompt",
            scenario="prompt",
            display_user="本地 CLI 用户",
            ticker="AAPL",
        ),
        session_id="session-1",
        user_prompt="请总结收入变化",
        run_overrides=prompt_command.ServiceRunOverrides(),
        sigint_monitor=_ImmediateSigintMonitor(),
    )

    assert result is None
    assert fake_host.cancel_requests == []


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

    exit_code = cli_main.main(
        ("prompt", "--base", str(workspace_root), "请总结收入变化")
    )
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
