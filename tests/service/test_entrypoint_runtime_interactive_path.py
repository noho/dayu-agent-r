"""interactive entrypoint runtime path 集成测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Literal, TypeAlias, cast

import pytest

import dayu.cli.commands.interactive as interactive_command
import dayu.cli.commands.prompt as prompt_command
import dayu.cli.main as cli_main
from dayu.engine.contracts.messages import AssistantMessage, UserMessage
from dayu.host.api import (
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
_EXCLUDED_UPLOAD_TOOL_NAME = "start_fins_upload"
_INTERACTIVE_SUBJECT_TEXT = "# 当前分析对象\n你正在分析的是 AAPL。"
_INTERACTIVE_CURRENT_TIME_TEXT = (
    "# 当前时间\n"
    "现在是 2026年7月7日 17:20（Asia/Shanghai，星期二）。\n"
    "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
)
_AgentSurface: TypeAlias = Literal["prompt", "interactive"]


class _SingleTurnInteractiveInput:
    """只返回一轮用户输入、随后报告 EOF 的真实 CLI 输入替身。"""

    _user_prompt: str
    _consumed: bool

    def __init__(self, user_prompt: str) -> None:
        """保存单轮输入。

        :param user_prompt: 第一次读取时返回的用户文本。
        :returns: ``None``。
        :raises ValueError: 用户文本为空时抛出。
        """

        if user_prompt.strip() == "":
            raise ValueError("user_prompt must not be empty")
        self._user_prompt = user_prompt
        self._consumed = False

    def __call__(self, prompt: str) -> str:
        """返回单轮输入，下一次读取抛出 EOF。

        :param prompt: interactive 输入提示文本。
        :returns: 首次调用返回保存的用户文本。
        :raises EOFError: 第二次及后续读取时抛出。
        """

        del prompt
        if self._consumed:
            raise EOFError
        self._consumed = True
        return self._user_prompt


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
    worker_factory: FinalAnswerWorkerFactory,
) -> AsyncIterator[Host]:
    """使用原始 durable options 打开记录型真实 Host。

    :param options: Service runtime 生成的 Host options。
    :param worker_factory: 记录 Engine request 的 deterministic factory。
    :returns: 真实 Host public handle 的异步迭代器。
    :raises Exception: Host 打开、执行或关闭失败时透传。
    """

    async with open_host(
        replace(options, worker_factory=worker_factory)
    ) as host:
        yield host


def _runtime_assembly_env() -> dict[str, str]:
    """构造真实 interactive runtime assembly 所需的测试 credential 环境。

    :returns: 同时包含显式 DeepSeek 主 Run 与 package MiMo compactor credential 的新字典。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "DEEPSEEK_API_KEY": _API_KEY,
        "MIMO_PLAN_API_KEY": _API_KEY,
    }


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
    assert _DEFAULT_PREPROCESS_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _EXCLUDED_UPLOAD_TOOL_NAME not in result.scene_inputs.tool_selection.tool_names
    assert result.host_assembly.options.wait_poller_policy is not None
    assert result.host_assembly.options.wait_poller_policy.enabled
    assert result.host_assembly.options.tooling_options is not None
    assert result.host_assembly.options.tooling_options.wait_poll_adapter_registry is not None
    assert "财报工具指引" in result.scene_inputs.system_prompt
    assert _DEFAULT_TIME_TOOL_NAME in result.scene_inputs.system_prompt
    assert _DEFAULT_DOWNLOAD_TOOL_NAME in result.scene_inputs.system_prompt
    assert _DEFAULT_PREPROCESS_TOOL_NAME in result.scene_inputs.system_prompt
    assert _EXCLUDED_UPLOAD_TOOL_NAME not in result.scene_inputs.system_prompt
    assert "<when_tag" not in result.scene_inputs.system_prompt
    assert "</when_tag>" not in result.scene_inputs.system_prompt
    assert "<when_tool" not in result.scene_inputs.system_prompt
    assert "</when_tool>" not in result.scene_inputs.system_prompt
    assert result.host_assembly.diagnostics.model_id == _MODEL_ID
    assert result.host_assembly.diagnostics.runner_option_hint_id == _RUNNER_HINT_ID


@pytest.mark.asyncio
async def test_interactive_runtime_requires_subject_and_current_time_context_slots(
    tmp_path: Path,
) -> None:
    """真实 interactive scene 要求共享研究主体与当前时间 context slots。"""

    runtime = await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            explicit_config_dir=None,
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
    assert tuple(
        message.content
        for message in second_request.messages
        if isinstance(message, UserMessage)
    )[-2:] == (first_prompt, second_prompt)
    assert tuple(
        message.content
        for message in second_request.messages
        if isinstance(message, AssistantMessage)
    )[-1:] == (f"final:1:{first_snapshot.run_id}",)


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
        message.content
        for message in worker_factory.requests[1].messages
        if isinstance(message, UserMessage)
    ) == (second_prompt,)
    assert not any(
        isinstance(message, AssistantMessage)
        for message in worker_factory.requests[1].messages
    )


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
        monkeypatch.setattr(
            interactive_command,
            "_read_user_input",
            _SingleTurnInteractiveInput(user_prompt),
        )
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
            explicit_config_dir=None,
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
