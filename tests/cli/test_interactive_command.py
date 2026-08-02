"""``dayu-cli interactive`` 命令测试。"""

from __future__ import annotations

import asyncio
import io
import signal
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
from pathlib import Path
from types import FrameType, TracebackType
from typing import TypeAlias, cast

import pytest
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

import dayu.cli.agent_entrypoint as agent_entrypoint
import dayu.cli.composer as composer_module
import dayu.cli.commands.interactive as interactive_command
import dayu.cli.main as cli_main
import dayu.cli.session_execution as session_execution
from dayu.cli.composer import (
    InteractiveComposerEvent,
    InteractiveComposerEventKind,
    InteractiveComposerPhase,
    PromptToolkitInteractiveComposer,
)
from dayu.cli.run_keys import RunningKeyAction
from dayu.cli.run_view import InteractiveRunViewOptions, TerminalInteractiveRunView
from dayu.cli.runtime_display import RuntimeDisplayController
from dayu.cli.session_terminal_cursor import CliTerminalCursorError, read_cli_terminal_cursor
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
    HostSessionEventIterator,
    HostSessionAccessMode,
    HostSessionAttachment,
    HostSessionMutationErrorDetail,
    HostSessionMutationRejectionReason,
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
_TestSignalHandler: TypeAlias = signal.Handlers | int | Callable[[int, FrameType | None], None]
_REMOVED_INTERACTIVE_DEBUG_OPTIONS: tuple[tuple[str, ...], ...] = (
    ("--debug-sse",),
    ("--debug-tool-delta",),
    ("--debug-sse-sample-rate", "0.5"),
    ("--debug-sse-throttle-sec", "1.0"),
)
_API_KEY = "test-provider-key"
_TRANSIENT_OBSERVED_AT = datetime(2026, 7, 20, 1, 2, 3, tzinfo=UTC)


class _InteractiveEditorFailureCase(StrEnum):
    """真实 composer 接入 REPL 的 editor 失败/取消矩阵。"""

    MISSING = "missing"
    NON_EXECUTABLE = "non_executable"
    SPAWN_ERROR = "spawn_error"
    NONZERO = "nonzero"


class _InteractiveEditorProcess:
    """记录 integration exact argv 并模拟 spawn/nonzero 结果。"""

    case: _InteractiveEditorFailureCase
    calls: list[tuple[str, ...]]

    def __init__(self, case: _InteractiveEditorFailureCase) -> None:
        """初始化 process 替身。

        :param case: 当前 integration case。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.case = case
        self.calls = []

    def __call__(self, argv: tuple[str, ...]) -> int:
        """记录 argv，并返回非零或抛 spawn ``OSError``。

        :param argv: production 显式 launcher 生成的 exact argv。
        :returns: nonzero case 返回九。
        :raises OSError: spawn-error case 模拟进程启动失败。
        :raises AssertionError: 非进程 case 错误进入 launcher 时抛出。
        """

        self.calls.append(argv)
        if self.case is _InteractiveEditorFailureCase.SPAWN_ERROR:
            raise OSError("secret integration spawn payload")
        if self.case is _InteractiveEditorFailureCase.NONZERO:
            return 9
        raise AssertionError(f"invalid editor case entered process launcher: {self.case}")


def _runtime_assembly_env() -> dict[str, str]:
    """构造 interactive 测试完整 runtime assembly 所需的环境输入。

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


class _FakeHostEventIterator:
    """测试用 Host event iterator。"""

    closed_count: int
    cancelled_count: int
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
        self.cancelled_count = 0
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
            try:
                await self._changed.wait()
            except asyncio.CancelledError:
                self.cancelled_count += 1
                raise
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


class _FakeSessionAttachment:
    """CLI interactive fake Host 返回的显式 RW attachment。"""

    def __init__(
        self,
        session_id: str,
        *,
        access_mode: HostSessionAccessMode = HostSessionAccessMode.READ_WRITE,
        identity: str | None = None,
        timeline: list[str] | None = None,
    ) -> None:
        """初始化测试 attachment。

        :param session_id: attachment 绑定的 Session id。
        :param access_mode: attachment 生命周期内冻结的 mode。
        :param identity: timeline 中使用的可选 attachment identity。
        :param timeline: 可选生命周期顺序记录。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.session_id = session_id
        self.access_mode = access_mode
        self.identity = identity
        self.timeline = timeline
        self.close_count = 0

    async def aclose(self) -> None:
        """记录 attachment lexical close。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1
        if self.timeline is not None and self.identity is not None:
            self.timeline.extend(
                (
                    f"close-start:{self.identity}",
                    f"close-complete:{self.identity}",
                )
            )


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
    attach_session_ids: list[str]
    attachments: list[_FakeSessionAttachment]

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
        self._submit_index += 1
        run_id = f"run-{self._submit_index}"
        status_index = self._submit_index - 1
        status = None
        if status_index < len(self._submit_statuses):
            status = self._submit_statuses[status_index]
        if status is not None:
            if status_index < len(self._submit_thinking) and self._submit_thinking[status_index]:
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


def _test_attachment_controller(
    host: _FakeHost,
    *,
    access_mode: HostSessionAccessMode = HostSessionAccessMode.READ_WRITE,
) -> session_execution._InteractiveSessionAttachmentController:
    """构造 owner-level TTY driver 使用的 attachment controller。

    :param host: 提供 fresh attach callback 的 fake Host。
    :param access_mode: 初始 attachment 的冻结访问模式。
    :returns: 绑定初始 attachment 与 fake Host fresh callback 的 controller。
    :raises Exception: controller 构造不主动抛出异常。
    """

    initial = _FakeSessionAttachment("session-1", access_mode=access_mode)
    return session_execution._InteractiveSessionAttachmentController(
        current=initial,
        open_fresh=partial(host.attach_session, "session-1"),
        close_current=session_execution._close_interactive_session_attachment,
    )


class _AttachmentControllerLifecycleProbe:
    """观测 attachment controller 关闭、打开与失败时序。"""

    controller: session_execution._InteractiveSessionAttachmentController | None
    close_error: BaseException | None
    close_attempts: list[HostSessionAttachment]
    close_states: list[tuple[HostSessionAttachment | None, bool, bool]]
    open_errors: list[BaseException]
    open_attempt_count: int
    open_states: list[tuple[HostSessionAttachment | None, bool, bool]]

    def __init__(
        self,
        *,
        fresh_attachments: tuple[_FakeSessionAttachment, ...] = (),
        close_error: BaseException | None = None,
        open_errors: tuple[BaseException, ...] = (),
        block_close: bool = False,
    ) -> None:
        """初始化可控 lifecycle callbacks。

        :param fresh_attachments: open callback 依次返回的 fresh attachments。
        :param close_error: close callback 记录尝试后抛出的原始异常。
        :param open_errors: open callback 各次优先抛出的原始异常。
        :param block_close: 是否阻塞 close，直到测试显式放行。
        :returns: ``None``。
        :raises Exception: 初始化不主动抛出异常。
        """

        self.controller = None
        self.close_error = close_error
        self.close_attempts = []
        self.close_states = []
        self.open_errors = list(open_errors)
        self.open_attempt_count = 0
        self.open_states = []
        self._fresh_attachments = list(fresh_attachments)
        self.close_started = asyncio.Event()
        self._close_release = asyncio.Event()
        if not block_close:
            self._close_release.set()

    def bind(
        self,
        controller: session_execution._InteractiveSessionAttachmentController,
    ) -> None:
        """绑定被观测的 controller。

        :param controller: 使用本 probe callbacks 的 controller。
        :returns: ``None``。
        :raises AssertionError: probe 被重复绑定时抛出。
        """

        if self.controller is not None:
            raise AssertionError("attachment controller probe already bound")
        self.controller = controller

    def release_close(self) -> None:
        """放行被阻塞的 close callback。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._close_release.set()

    async def close_current(self, attachment: HostSessionAttachment) -> None:
        """记录 controller 在底层 close await 时已提交的状态。

        :param attachment: controller take-and-clear 后交出的旧 attachment。
        :returns: close 成功时返回 ``None``。
        :raises BaseException: 配置了 close_error 时原样抛出。
        :raises AssertionError: probe 尚未绑定 controller 时抛出。
        """

        controller = self.controller
        if controller is None:
            raise AssertionError("attachment controller probe is not bound")
        self.close_attempts.append(attachment)
        self.close_states.append((controller.current, controller.refresh_required, controller._closed))
        self.close_started.set()
        await self._close_release.wait()
        if self.close_error is not None:
            raise self.close_error
        await attachment.aclose()

    async def open_fresh(self) -> HostSessionAttachment:
        """记录 open 前状态并按脚本失败或返回 fresh attachment。

        :returns: 脚本中的下一个 fresh attachment。
        :raises BaseException: 当前 open attempt 配置失败时原样抛出。
        :raises AssertionError: probe 未绑定或 fresh 脚本耗尽时抛出。
        """

        controller = self.controller
        if controller is None:
            raise AssertionError("attachment controller probe is not bound")
        self.open_attempt_count += 1
        self.open_states.append((controller.current, controller.refresh_required, controller._closed))
        if self.open_errors:
            raise self.open_errors.pop(0)
        if not self._fresh_attachments:
            raise AssertionError("unexpected fresh attachment open")
        return self._fresh_attachments.pop(0)


def _controlled_attachment_controller(
    *,
    initial: _FakeSessionAttachment,
    probe: _AttachmentControllerLifecycleProbe,
) -> session_execution._InteractiveSessionAttachmentController:
    """构造并绑定 lifecycle failure owner test controller。

    :param initial: 初始 live attachment。
    :param probe: 提供可控 close/open callbacks 的 probe。
    :returns: 已绑定 probe 的 attachment controller。
    :raises AssertionError: probe 已被其他 controller 绑定时抛出。
    """

    controller = session_execution._InteractiveSessionAttachmentController(
        current=initial,
        open_fresh=probe.open_fresh,
        close_current=probe.close_current,
    )
    probe.bind(controller)
    return controller


class _ReadOnlyRetryHost(_FakeHost):
    """按 attachment mode 真实拒绝 mutation 的 interactive Host fake。"""

    def __init__(
        self,
        *,
        attachment_modes: tuple[HostSessionAccessMode, ...],
        submit_statuses: tuple[HostTerminalStatus | None, ...] = (),
        rejection_reason: HostSessionMutationRejectionReason = (HostSessionMutationRejectionReason.READ_ONLY),
        rejection_actual_mode: HostSessionAccessMode | None = (HostSessionAccessMode.READ_ONLY),
    ) -> None:
        """初始化 attachment mode 序列与 typed rejection。

        :param attachment_modes: 每次 fresh attach 返回的冻结 mode。
        :param submit_statuses: 成功接受 mutation 后的 terminal 序列。
        :param rejection_reason: RO attachment submit 使用的 typed reason。
        :param rejection_actual_mode: RO attachment submit 使用的 typed actual mode。
        :returns: ``None``。
        :raises ValueError: mode 序列为空时抛出。
        """

        if not attachment_modes:
            raise ValueError("attachment_modes must not be empty")
        super().__init__(submit_statuses=submit_statuses)
        self.attachment_modes = attachment_modes
        self.rejection_reason = rejection_reason
        self.rejection_actual_mode = rejection_actual_mode
        self.timeline: list[str] = []
        self.mutation_attempts: list[SubmitFollowupRequest] = []

    async def attach_session(self, session_id: str) -> HostSessionAttachment:
        """按脚本创建 mode 不可变的 fresh attachment。

        :param session_id: 目标 Session id。
        :returns: 带稳定 identity 与 timeline 的 fake attachment。
        :raises AssertionError: attach 次数超过脚本时抛出。
        """

        attach_index = len(self.attachments)
        if attach_index >= len(self.attachment_modes):
            raise AssertionError("unexpected fresh attachment")
        identity = f"B{attach_index + 1}"
        attachment = _FakeSessionAttachment(
            session_id,
            access_mode=self.attachment_modes[attach_index],
            identity=identity,
            timeline=self.timeline,
        )
        self.timeline.append(f"open:{identity}:{attachment.access_mode.value}")
        self.attach_session_ids.append(session_id)
        self.attachments.append(attachment)
        return attachment

    async def submit_followup(
        self,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """RO 时返回 typed rejection，RW 时委托既有 accepted Run fake。

        :param session_id: 目标 Session id。
        :param request: Host submit request。
        :returns: RW attachment 下 accepted follow-up。
        :raises HostApiError: current attachment 为 RO 时抛出配置的 typed rejection。
        """

        self.mutation_attempts.append(request)
        current = self.attachments[-1]
        if current.access_mode is HostSessionAccessMode.READ_ONLY:
            raise HostApiError(
                code=HostApiErrorCode.PERMISSION_DENIED,
                message="opaque rejection text that must not drive CLI dispatch",
                retryable=False,
                detail=HostSessionMutationErrorDetail(
                    kind="session_mutation_access",
                    session_id=session_id,
                    reason=self.rejection_reason,
                    required_mode=HostSessionAccessMode.READ_WRITE,
                    actual_mode=self.rejection_actual_mode,
                ),
            )
        return await super().submit_followup(session_id, request)


class _ControlledInteractiveHost(_FakeHost):
    """为 current/queued/cancel terminal race 提供显式 barrier 的 Host fake。"""

    submit_accepted: asyncio.Event
    cancel_started: asyncio.Event
    release_cancel_terminal: asyncio.Event
    cancel_waiter_cancelled: bool
    _run_watchers: dict[str, _FakeHostEventIterator]

    def __init__(self) -> None:
        """初始化可控 acceptance、cancel 与 terminal barriers。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(run_statuses=(RunStatus.RUNNING,))
        self.submit_accepted = asyncio.Event()
        self.cancel_started = asyncio.Event()
        self.release_cancel_terminal = asyncio.Event()
        self.cancel_waiter_cancelled = False
        self._run_watchers = {}

    async def submit_followup(
        self,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """接受 current/queued Run，并把对应 submit watcher 绑定到 Run id。

        :param session_id: 目标 Session id。
        :param request: Host submit request。
        :returns: accepted current 或 queued snapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        self._submit_index += 1
        run_id = f"run-{self._submit_index}"
        self._run_watchers[run_id] = self.watchers[-1]
        self.submit_accepted.set()
        return FollowupSnapshot(
            accepted_input_ref=f"input-{self._submit_index}",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id=run_id,
            accepted_run_status=(RunStatus.RUNNING if self._submit_index == 1 else RunStatus.QUEUED),
            command_watermark=HostStreamCursor(event_sequence=self._submit_index),
            queued_run_id=None if self._submit_index == 1 else run_id,
            target_run_id=None,
        )

    async def cancel_run(
        self,
        run_id: str,
        request: CancelRunRequest,
    ) -> RunSnapshot:
        """记录 single cancel，并在 barrier 释放后同时通知两个 canonical waiter。

        :param run_id: 待取消 Run id。
        :param request: Host cancel request。
        :returns: cancelling Run snapshot。
        :raises asyncio.CancelledError: cancel canonical waiter 被错误取消时透传。
        """

        self.calls.append(f"cancel:{run_id}")
        self.cancel_requests.append(request)
        cancel_watcher = self.watchers[-1]
        self.cancel_started.set()
        try:
            await self.release_cancel_terminal.wait()
        except asyncio.CancelledError:
            self.cancel_waiter_cancelled = True
            raise
        terminal = _terminal_event(
            run_id=run_id,
            status=HostTerminalStatus.CANCELLED,
        )
        await self._run_watchers[run_id].push(terminal)
        await cancel_watcher.push(terminal)
        await asyncio.sleep(0)
        return _run_snapshot(run_id=run_id, status=RunStatus.CANCELLING)

    async def finish_run(
        self,
        run_id: str,
        *,
        status: HostTerminalStatus = HostTerminalStatus.SUCCEEDED,
    ) -> None:
        """向指定 submit canonical waiter 发布 terminal。

        :param run_id: 待完成 Run id。
        :param status: terminal status。
        :returns: ``None``。
        :raises KeyError: Run 尚未 accepted 时抛出。
        """

        await self._run_watchers[run_id].push(_terminal_event(run_id=run_id, status=status))
        await asyncio.sleep(0)


class _DelayedAcceptanceControlledHost(_ControlledInteractiveHost):
    """把第一轮 durable acceptance 与 public submit response 分离。"""

    committed: asyncio.Event
    release_response: asyncio.Event

    def __init__(self) -> None:
        """初始化第一轮 acceptance response barrier。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.committed = asyncio.Event()
        self.release_response = asyncio.Event()

    async def submit_followup(
        self,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """先记录 durable acceptance，再等待测试释放 response。

        :param session_id: 目标 Session id。
        :param request: Host submit request。
        :returns: accepted snapshot。
        :raises asyncio.CancelledError: acceptance barrier 语义回归时透传。
        """

        snapshot = await super().submit_followup(session_id, request)
        self.committed.set()
        await self.release_response.wait()
        return snapshot


class _DelayedQueuedResponseHost(_ControlledInteractiveHost):
    """只延迟 sole queued submit 的 public acceptance response。"""

    queued_committed: asyncio.Event
    release_queued_response: asyncio.Event

    def __init__(self) -> None:
        """初始化 queued acceptance response barrier。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.queued_committed = asyncio.Event()
        self.release_queued_response = asyncio.Event()

    async def submit_followup(
        self,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """第二轮先 durable accept，再延迟 public response。

        :param session_id: 目标 Session id。
        :param request: Host submit request。
        :returns: accepted snapshot。
        :raises asyncio.CancelledError: queued task 被错误取消时透传。
        """

        snapshot = await super().submit_followup(session_id, request)
        if len(self.submit_requests) == 2:
            self.queued_committed.set()
            await self.release_queued_response.wait()
        return snapshot


class _FailingCancelControlledHost(_ControlledInteractiveHost):
    """让 Host cancel waiter 在 submit terminal 前失败的可控 fake。"""

    async def cancel_run(
        self,
        run_id: str,
        request: CancelRunRequest,
    ) -> RunSnapshot:
        """记录 single cancel 后立即抛出稳定 Host cancel failure。

        :param run_id: 待取消 Run id。
        :param request: Host cancel request。
        :returns: 正常路径不会返回。
        :raises RuntimeError: 始终抛出，用于验证 cancel-error owner。
        """

        self.calls.append(f"cancel:{run_id}")
        self.cancel_requests.append(request)
        self.cancel_started.set()
        raise RuntimeError("cancel waiter failed")


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


class _ComposerReadInterrupt:
    """测试 composer 读取异常步骤。"""

    exception_type: type[BaseException]

    def __init__(self, exception_type: type[BaseException]) -> None:
        """初始化兼容旧输入脚本语义的 typed event 步骤。

        :param exception_type: 待投影为 typed composer event 的异常类型。
        :returns: ``None``。
        :raises ValueError: 异常类型不是 ``KeyboardInterrupt`` 或 ``EOFError`` 时抛出。
        """

        if exception_type not in {KeyboardInterrupt, EOFError}:
            raise ValueError("unsupported scripted composer interrupt type")
        self.exception_type = exception_type


_ComposerReadStep = str | _ComposerReadInterrupt | InteractiveComposerEvent


class _ScriptedComposer:
    """按脚本返回 typed event 的测试 composer。"""

    prompt_calls: list[str]
    phase_calls: list[InteractiveComposerPhase]
    accepted_history_flags: list[bool]
    _remaining: list[_ComposerReadStep]
    _pending_submit: bool
    _revision: int
    _phase: InteractiveComposerPhase
    _phase_changed: asyncio.Event

    def __init__(self, steps: tuple[_ComposerReadStep, ...]) -> None:
        """初始化 scripted composer。

        :param steps: 每次读取的返回文本或异常步骤。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.prompt_calls = []
        self.phase_calls = []
        self.accepted_history_flags = []
        self._remaining = list(steps)
        self._pending_submit = False
        self._revision = 0
        self._phase = InteractiveComposerPhase.IDLE
        self._phase_changed = asyncio.Event()

    def set_phase(self, phase: InteractiveComposerPhase) -> None:
        """记录 REPL phase 更新。

        :param phase: 新 composer phase。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.phase_calls.append(phase)
        self._phase = phase
        self._phase_changed.set()

    def accept_submit(self, *, record_history: bool) -> None:
        """确认上一份 scripted submit。

        :param record_history: REPL 是否要求记录 history。
        :returns: ``None``。
        :raises RuntimeError: 没有 pending submit 时抛出。
        """

        if not self._pending_submit:
            raise RuntimeError("scripted composer has no pending submit")
        self._pending_submit = False
        self.accepted_history_flags.append(record_history)

    async def read_event(self, prompt: str) -> InteractiveComposerEvent:
        """读取下一条 scripted typed event。

        :param prompt: 输入提示文本。
        :returns: 脚本中的 typed event。
        :raises Exception: 不主动抛出异常。
        """

        self.prompt_calls.append(prompt)
        if not self._remaining:
            while self._phase is not InteractiveComposerPhase.IDLE:
                self._phase_changed.clear()
                await self._phase_changed.wait()
            return InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.EOF,
                input_revision=self._revision,
            )
        step = self._remaining.pop(0)
        if isinstance(step, str):
            self._revision += 1
            self._pending_submit = True
            return InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.SUBMIT,
                draft=step,
                input_revision=self._revision,
            )
        if isinstance(step, InteractiveComposerEvent):
            self._pending_submit = step.kind is InteractiveComposerEventKind.SUBMIT
            return step
        if step.exception_type is EOFError:
            return InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.EOF,
                input_revision=self._revision,
            )
        if step.exception_type is KeyboardInterrupt:
            return InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.EOF,
                input_revision=self._revision,
            )
        raise AssertionError(f"unsupported composer interrupt: {step.exception_type}")


class _BarrierScriptedComposer(_ScriptedComposer):
    """在指定 read call 前提供 terminal/Enter 顺序 barrier。"""

    blocked_call_index: int
    read_entered: asyncio.Event
    release_read: asyncio.Event

    def __init__(
        self,
        steps: tuple[_ComposerReadStep, ...],
        *,
        blocked_call_index: int,
    ) -> None:
        """初始化 composer read barrier。

        :param steps: scripted event 序列。
        :param blocked_call_index: 从一开始计数的阻塞 read 调用序号。
        :returns: ``None``。
        :raises ValueError: 阻塞序号小于一时抛出。
        """

        if blocked_call_index < 1:
            raise ValueError("blocked_call_index must be positive")
        super().__init__(steps)
        self.blocked_call_index = blocked_call_index
        self.read_entered = asyncio.Event()
        self.release_read = asyncio.Event()

    async def read_event(self, prompt: str) -> InteractiveComposerEvent:
        """在指定调用先等待显式 release，再返回 scripted event。

        :param prompt: 输入提示文本。
        :returns: scripted typed event。
        :raises Exception: parent composer 失败时向上透传。
        """

        call_index = len(self.prompt_calls) + 1
        if call_index == self.blocked_call_index:
            self.read_entered.set()
            await self.release_read.wait()
        return await super().read_event(prompt)


class _ReadOnlyThenErrorComposer(_ScriptedComposer):
    """首个 SUBMIT 后在下一次 REPL read 抛出测试异常。"""

    read_count: int

    def __init__(self, draft: str) -> None:
        """初始化单次 submit 与后续异常脚本。

        :param draft: 首次提交草稿。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__((draft,))
        self.read_count = 0

    async def read_event(self, prompt: str) -> InteractiveComposerEvent:
        """首次委托 submit，第二次抛出稳定测试异常。

        :param prompt: REPL prompt 文本。
        :returns: 首次调用返回 SUBMIT event。
        :raises RuntimeError: 第二次调用模拟 composer 异常。
        """

        self.read_count += 1
        if self.read_count > 1:
            raise RuntimeError("composer read failed after read-only rejection")
        return await super().read_event(prompt)


class _IdleSequencedComposer(_ScriptedComposer):
    """仅在 IDLE phase 投递下一份 submit 的测试 composer。"""

    async def read_event(self, prompt: str) -> InteractiveComposerEvent:
        """等待 IDLE 后读取下一条 scripted event。

        :param prompt: 输入提示文本。
        :returns: parent composer 产生的 typed event。
        :raises Exception: parent composer 失败时向上透传。
        """

        while self._phase is not InteractiveComposerPhase.IDLE:
            self._phase_changed.clear()
            await self._phase_changed.wait()
        return await super().read_event(prompt)


class _ReportedTty(io.StringIO):
    """只用于强制 execute 进入显式 composer TTY path 的文本流。"""

    def isatty(self) -> bool:
        """报告 TTY capability。

        :returns: 恒为 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True


def _install_cli_tty_composer(
    monkeypatch: pytest.MonkeyPatch,
    steps: tuple[_ComposerReadStep, ...],
) -> _ScriptedComposer:
    """让真实 CLI main 走显式 typed composer TTY path。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param steps: scripted composer event/input 序列。
    :returns: 安装到 session execution 的 composer。
    :raises Exception: monkeypatch 设置失败时向上透传。
    """

    composer = _ScriptedComposer(steps)
    monkeypatch.setattr(session_execution.sys, "stdin", _ReportedTty())
    monkeypatch.setattr(
        session_execution,
        "new_interactive_composer",
        lambda: composer,
    )
    return composer


def _install_cli_pipe_stdin(
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
) -> io.TextIOWrapper:
    """安装带显式 ``buffer`` 的真实 non-TTY stdin。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param data: whole stdin 原始 bytes。
    :returns: 安装后的 TextIOWrapper，供测试保持生命周期。
    :raises Exception: stream 构造或 monkeypatch 失败时向上透传。
    """

    stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
    monkeypatch.setattr(session_execution.sys, "stdin", stream)
    return stream


class _SyncSigintFallbackHarness:
    """模拟不支持 asyncio signal API 的同步 signal owner。"""

    current_handler: _TestSignalHandler
    installed: asyncio.Event
    signal_calls: list[_TestSignalHandler]

    def __init__(self) -> None:
        """初始化 previous handler 与调用记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.current_handler = signal.SIG_IGN
        self.installed = asyncio.Event()
        self.signal_calls = []

    def getsignal(self, _signal_number: int) -> _TestSignalHandler:
        """返回当前测试 handler。

        :param _signal_number: 待读取的 signal 编号。
        :returns: 当前测试 handler。
        :raises Exception: 不主动抛出异常。
        """

        return self.current_handler

    def set_signal_handler(
        self,
        _signal_number: int,
        handler: _TestSignalHandler,
    ) -> _TestSignalHandler:
        """记录同步安装或恢复，并更新当前 handler。

        :param _signal_number: 待设置的 signal 编号。
        :param handler: 新 handler。
        :returns: 被替换的 previous handler。
        :raises Exception: 不主动抛出异常。
        """

        previous = self.current_handler
        self.current_handler = handler
        self.signal_calls.append(handler)
        if callable(handler):
            self.installed.set()
        return previous

    def reject_asyncio_handler(
        self,
        _signal_number: int,
        _callback: Callable[[], None],
    ) -> None:
        """模拟事件循环不支持 ``add_signal_handler``。

        :param _signal_number: 待设置的 signal 编号。
        :param _callback: asyncio handler callback。
        :returns: 正常路径不返回。
        :raises NotImplementedError: 始终抛出以进入同步 fallback。
        """

        raise NotImplementedError("asyncio signal handlers are unavailable")

    def reject_asyncio_remove(self, _signal_number: int) -> bool:
        """拒绝 fallback close 错误调用 asyncio remove API。

        :param _signal_number: 待移除的 signal 编号。
        :returns: 正常路径不返回。
        :raises AssertionError: 始终抛出以证明恢复模式同源。
        """

        raise AssertionError("synchronous fallback must not call remove_signal_handler")

    def installed_handler(self) -> Callable[[int, FrameType | None], None]:
        """返回 monitor 安装的同步 callable handler。

        :returns: 已安装的同步 handler。
        :raises AssertionError: 当前 handler 不是 callable 时抛出。
        """

        if not callable(self.current_handler):
            raise AssertionError("synchronous SIGINT handler was not installed")
        return self.current_handler


def _install_sync_sigint_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> _SyncSigintFallbackHarness:
    """安装不支持 asyncio signal API 的确定性测试环境。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: 可触发与检查同步 handler 的 harness。
    :raises Exception: monkeypatch 失败时向上透传。
    """

    harness = _SyncSigintFallbackHarness()
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(signal, "getsignal", harness.getsignal)
    monkeypatch.setattr(signal, "signal", harness.set_signal_handler)
    monkeypatch.setattr(loop, "add_signal_handler", harness.reject_asyncio_handler)
    monkeypatch.setattr(loop, "remove_signal_handler", harness.reject_asyncio_remove)
    return harness


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


class _ManualSigintMonitor(CliSigintMonitor):
    """测试可逐次触发并观察消费进度的 OS SIGINT monitor。"""

    observed_counts: list[int]

    def __init__(self) -> None:
        """初始化手动 SIGINT 计数与消费记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.observed_counts = []

    async def wait_next(self, observed_count: int) -> int:
        """等待下一次手动通知并记录 driver 已消费的新计数。

        :param observed_count: driver 已观察的 SIGINT 计数。
        :returns: 新的 SIGINT 计数。
        :raises asyncio.CancelledError: driver cleanup 取消等待时透传。
        """

        new_count = await super().wait_next(observed_count)
        self.observed_counts.append(new_count)
        return new_count


class _InvocationManualSigintMonitor(_ManualSigintMonitor):
    """不安装真实 signal handler 的 invocation 级手动 monitor。"""

    install_count: int
    close_count: int

    def __init__(self) -> None:
        """初始化手动通知与 lifecycle 调用计数。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.install_count = 0
        self.close_count = 0

    def install(self) -> None:
        """记录 invocation 安装而不接管测试进程 signal handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.install_count += 1

    def close(self) -> None:
        """记录 invocation 关闭而不修改测试进程 signal handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1


def test_interactive_label_targets_shared_agent_slot_and_default_context(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--label`` 应指向共享 Agent slot，并使用默认分析主体。"""

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
    _install_cli_tty_composer(monkeypatch, ("请总结收入变化",))

    exit_code = cli_main.main(
        (
            "interactive",
            "--base",
            str(tmp_path),
            "--label",
            "earnings",
            "--model",
            _MODEL_ID,
        )
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "answer for run-1"
    assert captured_requests[0].workspace_root == tmp_path
    assert captured_requests[0].scene_id == "interactive"
    assert captured_requests[0].assembly_overrides.model_id == _MODEL_ID
    assert tuple(captured_requests[0].context_slot_values) == (
        _FINS_DEFAULT_SUBJECT_SLOT,
        _CURRENT_TIME_SLOT,
    )
    assert captured_requests[0].context_slot_values[_FINS_DEFAULT_SUBJECT_SLOT] == ""
    assert "Asia/Shanghai" in str(captured_requests[0].context_slot_values[_CURRENT_TIME_SLOT])
    assert fake_host.ensure_requests[0].scope == "cli.agent"
    assert fake_host.ensure_requests[0].slot_key == "cli.agent.earnings"
    assert fake_host.create_requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", tuple(_InteractiveEditorFailureCase))
async def test_editor_failure_or_cancel_preserves_repl_until_explicit_submit(
    case: _InteractiveEditorFailureCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """missing/nonexec/spawn/nonzero 后同一 REPL 保留 draft/cursor/history 与零 Run。

    :param case: editor 失败或取消 integration case。
    :param tmp_path: pytest 临时 workspace。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: editor 动作提前提交、破坏草稿或退出 REPL 时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _FakeHost(submit_statuses=(HostTerminalStatus.SUCCEEDED,))
    process = _InteractiveEditorProcess(case)
    monkeypatch.setattr(composer_module, "_run_editor_process", process)
    monkeypatch.setattr(Buffer, "open_in_editor", _reject_system_editor_fallback)
    _configure_editor_failure_case(case, tmp_path=tmp_path, monkeypatch=monkeypatch)
    stderr = io.StringIO()
    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            stderr=stderr,
            input=pipe_input,
            output=DummyOutput(),
        )
        driver = asyncio.create_task(
            session_execution._drive_interactive_tty_repl(
                host=cast(Host, host),
                runtime=runtime,
                workspace_root=tmp_path,
                invocation=session_execution.new_cli_invocation(
                    command_name="interactive",
                    scenario="interactive",
                    display_user="本地 CLI 用户",
                    ticker=None,
                ),
                session_id="session-1",
                run_overrides=ServiceRunOverrides(),
                composer=composer,
                sigint_monitor=_NoopSigintMonitor(),
                attachment_controller=_test_attachment_controller(host),
            )
        )
        pipe_input.send_text("abc\x1b[D\x18\x05")
        await _wait_for_editor_integration_completion(
            case=case,
            composer=composer,
            process=process,
            stderr=stderr,
        )

        assert host.submit_requests == []
        assert composer._history.get_strings() == []
        pipe_input.send_text("X\r")
        await _wait_for_submit_count(host, 1)
        await _wait_for_real_composer_history(composer, ("abXc",))
        await _wait_for_real_composer_phase(
            composer,
            phase=InteractiveComposerPhase.IDLE,
        )
        pipe_input.send_text("\x04")
        exit_code = await asyncio.wait_for(driver, timeout=2.0)

    assert exit_code == EXIT_SUCCESS
    assert [request.user_prompt for request in host.submit_requests] == ["abXc"]
    assert composer._history.get_strings() == ["abXc"]
    if case is _InteractiveEditorFailureCase.NONZERO:
        assert stderr.getvalue() == ""
    else:
        diagnostic = stderr.getvalue()
        assert "VISUAL" in diagnostic
        assert "取消 VISUAL/EDITOR" in diagnostic
        assert "Traceback" not in diagnostic
        assert "secret" not in diagnostic
    if process.calls:
        assert len(process.calls) == 1
        assert process.calls[0][0] == str(Path(sys.executable).resolve())
        assert not Path(process.calls[0][-1]).exists()


@pytest.mark.parametrize(
    ("raw", "expected_prompt"),
    (
        (b"", None),
        (b" \t\r\n", None),
        (b"single line\n", "single line"),
        ("第一行\n第二行".encode(), "第一行\n第二行"),
        (b" first\r\nsecond\r\n ", "first\nsecond"),
        (b"first\rsecond", "first\nsecond"),
        (b"no-final-newline", "no-final-newline"),
        (b"left\x04right", "left\x04right"),
    ),
)
def test_interactive_non_tty_reads_whole_stdin_as_zero_or_one_batch(
    raw: bytes,
    expected_prompt: str | None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pipe matrix 必须只产生零或一个 QUEUE Run 且从不输出 prompt。

    :param raw: whole stdin 原始 bytes。
    :param expected_prompt: outer trim/换行规范化后的预期输入。
    :param tmp_path: pytest 临时 workspace。
    :param capsys: pytest 输出捕获。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: batch 数量、文本或输出通道不符合契约时抛出。
    """

    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.SUCCEEDED,))
    stdin_stream = _install_cli_pipe_stdin(monkeypatch, raw)
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()
    stdin_stream.detach()

    assert exit_code == EXIT_SUCCESS
    assert "dayu> " not in captured.out
    assert "dayu> " not in captured.err
    if expected_prompt is None:
        assert fake_host.submit_requests == []
        assert captured.out == ""
    else:
        assert len(fake_host.submit_requests) == 1
        request = fake_host.submit_requests[0]
        assert request.user_prompt == expected_prompt
        assert request.behavior is FollowupBehavior.QUEUE
        assert request.target_run_id is None
        assert captured.out.strip() == "answer for run-1"


def test_interactive_non_tty_invalid_utf8_is_stable_and_redacted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """invalid UTF-8 必须返回稳定用法错误且不泄漏 bytes/codec/traceback。

    :param tmp_path: pytest 临时 workspace。
    :param capsys: pytest 输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 错误不稳定或泄漏输入 payload 时抛出。
    """

    fake_host = _FakeHost()
    stdin_stream = _install_cli_pipe_stdin(monkeypatch, b"secret\xffpayload")
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()
    stdin_stream.detach()

    assert exit_code == EXIT_USAGE_ERROR
    assert "interactive stdin is not valid UTF-8" in captured.err
    assert "secret" not in captured.err
    assert "payload" not in captured.err
    assert "UnicodeDecodeError" not in captured.err
    assert "Traceback" not in captured.err
    assert fake_host.submit_requests == []


@pytest.mark.parametrize(
    ("terminal_status", "expected_exit_code"),
    (
        (HostTerminalStatus.FAILED, EXIT_SUCCESS),
        (HostTerminalStatus.CANCELLED, EXIT_SUCCESS),
        (HostTerminalStatus.LOST, EXIT_FAILURE),
    ),
)
def test_interactive_non_tty_exits_after_first_terminal(
    terminal_status: HostTerminalStatus,
    expected_exit_code: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """non-TTY 任意 terminal 都必须在唯一 Run 后结束进程。

    :param terminal_status: 唯一 Run 的 terminal status。
    :param expected_exit_code: frozen terminal renderer 退出码。
    :param tmp_path: pytest 临时 workspace。
    :param capsys: pytest 输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: terminal 后仍读下一 batch 或启动第二 Run 时抛出。
    """

    fake_host = _FakeHost(submit_statuses=(terminal_status,))
    stdin_stream = _install_cli_pipe_stdin(monkeypatch, b"only batch")
    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        interactive_command,
        "open_host",
        lambda _options: _FakeOpenHostContext(fake_host),
    )

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()
    stdin_stream.detach()

    assert exit_code == expected_exit_code
    assert len(fake_host.submit_requests) == 1
    assert "dayu> " not in captured.out
    assert "dayu> " not in captured.err


@pytest.mark.asyncio
async def test_interactive_non_tty_single_sigint_crosses_acceptance_barrier_without_orphan(
    tmp_path: Path,
) -> None:
    """non-TTY pre-accept SIGINT 必须保留 submit 并在接受后只取消一次。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: acceptance、canonical waiter 或 cleanup 契约漂移时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _DelayedAcceptanceControlledHost()
    monitor = _InvocationManualSigintMonitor()
    execution = asyncio.create_task(
        session_execution.execute_interactive_on_session(
            host=cast(Host, host),
            prepared=_prepared_interactive_execution(
                tmp_path=tmp_path,
                runtime=runtime,
            ),
            session_id="session-1",
            stdin=io.StringIO(),
            binary_stdin=io.BytesIO(b"whole batch"),
            sigint_monitor_factory=lambda: monitor,
            run_startup_reconnect=False,
            detail=False,
            thinking=False,
        )
    )

    await asyncio.wait_for(host.committed.wait(), timeout=2.0)
    monitor.notify()
    await _wait_for_sigint_observation(monitor, 1)
    assert host.cancel_requests == []
    assert not execution.done()

    host.release_response.set()
    await asyncio.wait_for(host.cancel_started.wait(), timeout=2.0)
    host.release_cancel_terminal.set()
    exit_code = await asyncio.wait_for(execution, timeout=2.0)

    assert exit_code == EXIT_SUCCESS
    assert len(host.cancel_requests) == 1
    assert host.cancel_requests[0].mode is CancelMode.GRACEFUL
    assert host.cancel_requests[0].reason == "cli_sigint"
    assert not host.cancel_waiter_cancelled
    assert monitor.install_count == 1
    assert monitor.close_count == 1
    assert [attachment.close_count for attachment in host.attachments] == [1]


@pytest.mark.asyncio
async def test_interactive_non_tty_second_sigint_waits_terminal_then_returns_130_and_third_is_noop(
    tmp_path: Path,
) -> None:
    """non-TTY 第二次 SIGINT 只登记退出，第三次不得重复取消。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: signal 计数、terminal 等待或 cleanup 契约漂移时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ControlledInteractiveHost()
    monitor = _InvocationManualSigintMonitor()
    execution = asyncio.create_task(
        session_execution.execute_interactive_on_session(
            host=cast(Host, host),
            prepared=_prepared_interactive_execution(
                tmp_path=tmp_path,
                runtime=runtime,
            ),
            session_id="session-1",
            stdin=io.StringIO(),
            binary_stdin=io.BytesIO(b"whole batch"),
            sigint_monitor_factory=lambda: monitor,
            run_startup_reconnect=False,
            detail=False,
            thinking=False,
        )
    )

    await _wait_for_submit_count(host, 1)
    monitor.notify()
    await asyncio.wait_for(host.cancel_started.wait(), timeout=2.0)
    await _wait_for_sigint_observation(monitor, 1)
    monitor.notify()
    await _wait_for_sigint_observation(monitor, 2)
    monitor.notify()
    await _wait_for_sigint_observation(monitor, 3)

    assert not execution.done()
    assert len(host.cancel_requests) == 1
    host.release_cancel_terminal.set()
    exit_code = await asyncio.wait_for(execution, timeout=2.0)

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(host.cancel_requests) == 1
    assert not host.cancel_waiter_cancelled
    assert monitor.install_count == 1
    assert monitor.close_count == 1
    assert [attachment.close_count for attachment in host.attachments] == [1]


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
        composer=_ScriptedComposer(("第一轮", "第二轮")),
        sigint_monitor_factory=_NoopSigintMonitor,
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.splitlines() == ["answer for run-1", "answer for run-2"]
    assert fake_host.ensure_requests == []
    assert fake_host.create_requests == []
    assert fake_host.attach_session_ids == ["session-existing"]
    assert [attachment.close_count for attachment in fake_host.attachments] == [1]
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

    monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)
    monkeypatch.setattr(
        session_execution,
        "startup_reconnect_entrypoint_session",
        fake_startup_reconnect,
    )

    composer = _ScriptedComposer(("第一轮",))
    exit_code = await session_execution.execute_interactive_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        composer=composer,
        sigint_monitor_factory=_NoopSigintMonitor,
    )

    cursor_record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-existing",
    )
    assert exit_code == EXIT_SUCCESS
    assert events == ["startup:session-existing"]
    assert composer.prompt_calls == ["dayu> ", "dayu> "]
    assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=5)
    assert cursor_record.seen_terminal_event_ids == (
        "terminal-startup",
        "terminal-run-1",
    )


@pytest.mark.asyncio
async def test_interactive_startup_single_sigint_cleans_up_and_returns_130(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """startup 一次 OS SIGINT 必须 cleanup、exit 130 且不创建 Run。

    :param tmp_path: pytest 临时 workspace。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: observation/attachment 未收口或创建 Run 时抛出。
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
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    fake_host = _FakeHost()
    startup_cancelled = asyncio.Event()
    fallback = _install_sync_sigint_fallback(monkeypatch)
    monitor = CliSigintMonitor()

    async def blocking_startup(
        *,
        host: Host,
        prepared: session_execution.PreparedInteractiveSessionExecution,
        session_id: str,
    ) -> int:
        """阻塞 startup 直到 invocation SIGINT 取消本地 observation。

        :param host: fake Host。
        :param prepared: interactive prepare result。
        :param session_id: startup Session id。
        :returns: 正常路径不会返回。
        :raises asyncio.CancelledError: startup task 被安全取消时透传。
        """

        del host, prepared, session_id
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            startup_cancelled.set()
            raise
        raise AssertionError("startup should be cancelled")

    monkeypatch.setattr(
        session_execution,
        "_run_existing_session_startup_reconnect",
        blocking_startup,
    )

    execution_task = asyncio.create_task(
        session_execution.execute_interactive_on_session(
            host=cast(Host, fake_host),
            prepared=prepared,
            session_id="session-existing",
            composer=_ScriptedComposer(()),
            sigint_monitor_factory=lambda: monitor,
        )
    )
    await asyncio.wait_for(fallback.installed.wait(), timeout=2.0)
    fallback.installed_handler()(signal.SIGINT, None)
    exit_code = await asyncio.wait_for(execution_task, timeout=2.0)

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert monitor.count == 1
    assert len(fallback.signal_calls) == 2
    assert callable(fallback.signal_calls[0])
    assert fallback.signal_calls[1] is signal.SIG_IGN
    assert fallback.current_handler is signal.SIG_IGN
    assert startup_cancelled.is_set()
    assert fake_host.submit_requests == []
    assert fake_host.cancel_requests == []
    assert [attachment.close_count for attachment in fake_host.attachments] == [1]


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
        composer=_ScriptedComposer(()),
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
            composer=_ScriptedComposer(()),
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
    _install_cli_tty_composer(monkeypatch, ("请总结收入变化",))

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
    fake_host = _ControlledInteractiveHost()
    composer = _BarrierScriptedComposer(
        (_ComposerReadInterrupt(EOFError),),
        blocked_call_index=1,
    )
    monitor = _ManualSigintMonitor()

    driver = asyncio.create_task(
        session_execution._drive_interactive_tty_repl(
            host=cast(Host, fake_host),
            runtime=runtime,
            workspace_root=tmp_path,
            invocation=invocation,
            session_id="session-1",
            run_overrides=ServiceRunOverrides(),
            composer=composer,
            sigint_monitor=monitor,
            attachment_controller=_test_attachment_controller(fake_host),
        )
    )
    await asyncio.wait_for(composer.read_entered.wait(), timeout=2.0)
    monitor.notify()
    await _wait_for_sigint_observation(monitor, 1)
    assert not driver.done()
    composer.release_read.set()
    exit_code = await asyncio.wait_for(driver, timeout=2.0)

    assert exit_code == EXIT_SUCCESS
    assert composer.prompt_calls == ["dayu> "]
    assert fake_host.submit_requests == []
    assert fake_host.cancel_requests == []


@pytest.mark.asyncio
async def test_interactive_second_consecutive_input_keyboard_interrupt_exits_without_run_requests(
    tmp_path: Path,
) -> None:
    """输入态连续两次空 prompt Ctrl-C 应退出当前 command，且不发 submit / cancel。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    fake_host = _ControlledInteractiveHost()
    composer = _BarrierScriptedComposer(
        (_ComposerReadInterrupt(EOFError),),
        blocked_call_index=1,
    )
    monitor = _ManualSigintMonitor()
    driver = _start_tty_driver(
        host=fake_host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
        sigint_monitor=monitor,
    )
    await asyncio.wait_for(composer.read_entered.wait(), timeout=2.0)
    monitor.notify()
    await _wait_for_sigint_observation(monitor, 1)
    monitor.notify()
    exit_code = await asyncio.wait_for(driver, timeout=2.0)

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

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path), "--label", " "))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "--label" in captured.err


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
    _install_cli_tty_composer(monkeypatch, ("第一轮", "第二轮"))

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
    _install_cli_tty_composer(monkeypatch, ("第一轮", "第二轮"))
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
    _install_cli_tty_composer(monkeypatch, ("第一轮",))
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
    _install_cli_tty_composer(monkeypatch, ("第一轮",))
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

    thinking_exit = cli_main.main(("interactive", "--base", str(tmp_path), "--thinking"))
    thinking_captured = capsys.readouterr()

    _install_cli_tty_composer(monkeypatch, ("第一轮",))
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

    no_thinking_exit = cli_main.main(("interactive", "--base", str(tmp_path), "--no-thinking"))
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
    _install_cli_tty_composer(monkeypatch, ("   ", "有效问题"))

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
    composer = _IdleSequencedComposer(("失败轮", "取消轮", "成功轮"))
    monkeypatch.setattr(session_execution, "new_interactive_composer", lambda: composer)
    monkeypatch.setattr(session_execution.sys, "stdin", _ReportedTty())

    exit_code = cli_main.main(("interactive", "--base", str(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert captured.out.strip() == "answer for run-3"
    assert "failed for run-1" in captured.err
    assert "Cancelled." in captured.err
    assert "cancelled for run-2" not in captured.err
    assert len(fake_host.submit_requests) == 3


@pytest.mark.asyncio
async def test_attachment_controller_close_failure_is_terminal_and_attempted_once() -> None:
    """close 失败前先 terminal/take-and-clear，异常原样传播且后续 no-op。

    :returns: ``None``。
    :raises AssertionError: close attempt、状态或异常 identity 漂移时抛出。
    """

    initial = _FakeSessionAttachment("session-1", identity="B1")
    close_error = RuntimeError("controlled attachment close failure")
    probe = _AttachmentControllerLifecycleProbe(close_error=close_error)
    controller = _controlled_attachment_controller(initial=initial, probe=probe)

    with pytest.raises(RuntimeError) as exc_info:
        await controller.close()

    assert exc_info.value is close_error
    assert probe.close_attempts == [initial]
    assert probe.close_states == [(None, False, True)]
    assert controller.current is None
    assert controller._closed is True

    await controller.close()
    assert probe.close_attempts == [initial]


@pytest.mark.asyncio
async def test_attachment_controller_refresh_close_failure_retries_with_fresh_open() -> None:
    """refresh close 失败不 open/double-close，下一次 mutation 只 fresh open。

    :returns: ``None``。
    :raises AssertionError: failure state、异常 identity 或 retry owner 偏序漂移时抛出。
    """

    initial = _FakeSessionAttachment("session-1", identity="B1")
    fresh = _FakeSessionAttachment("session-1", identity="B2")
    close_error = RuntimeError("controlled refresh close failure")
    probe = _AttachmentControllerLifecycleProbe(
        fresh_attachments=(fresh,),
        close_error=close_error,
    )
    controller = _controlled_attachment_controller(initial=initial, probe=probe)
    controller.require_refresh()

    with pytest.raises(RuntimeError) as exc_info:
        await controller.attachment_for_mutation()

    assert exc_info.value is close_error
    assert probe.close_attempts == [initial]
    assert probe.close_states == [(None, True, False)]
    assert probe.open_attempt_count == 0
    assert controller.current is None
    assert controller.refresh_required is True
    assert controller._closed is False

    probe.close_error = None
    assert await controller.attachment_for_mutation() is fresh
    assert probe.close_attempts == [initial]
    assert probe.open_attempt_count == 1
    assert probe.open_states == [(None, True, False)]
    assert controller.current is fresh
    assert controller.refresh_required is False


@pytest.mark.asyncio
async def test_attachment_controller_refresh_never_opens_before_close_completes() -> None:
    """refresh 必须完整等待旧 attachment close 后才 fresh open。

    :returns: ``None``。
    :raises AssertionError: current 清理或 close-before-open 偏序漂移时抛出。
    """

    initial = _FakeSessionAttachment("session-1", identity="B1")
    fresh = _FakeSessionAttachment("session-1", identity="B2")
    probe = _AttachmentControllerLifecycleProbe(
        fresh_attachments=(fresh,),
        block_close=True,
    )
    controller = _controlled_attachment_controller(initial=initial, probe=probe)
    controller.require_refresh()

    refresh_task = asyncio.create_task(controller.attachment_for_mutation())
    await probe.close_started.wait()

    assert controller.current is None
    assert controller.refresh_required is True
    assert probe.close_attempts == [initial]
    assert probe.open_attempt_count == 0
    assert refresh_task.done() is False

    probe.release_close()
    assert await refresh_task is fresh
    assert initial.close_count == 1
    assert probe.open_attempt_count == 1
    assert probe.open_states == [(None, True, False)]


@pytest.mark.asyncio
async def test_attachment_controller_open_failure_keeps_refresh_for_fresh_retry() -> None:
    """fresh open 失败保持 None/refresh，下一次 mutation 再次 fresh open。

    :returns: ``None``。
    :raises AssertionError: open 异常、state 或 retry attempt 次数漂移时抛出。
    """

    initial = _FakeSessionAttachment("session-1", identity="B1")
    fresh = _FakeSessionAttachment("session-1", identity="B2")
    open_error = RuntimeError("controlled fresh open failure")
    probe = _AttachmentControllerLifecycleProbe(
        fresh_attachments=(fresh,),
        open_errors=(open_error,),
    )
    controller = _controlled_attachment_controller(initial=initial, probe=probe)
    controller.require_refresh()

    with pytest.raises(RuntimeError) as exc_info:
        await controller.attachment_for_mutation()

    assert exc_info.value is open_error
    assert probe.close_attempts == [initial]
    assert initial.close_count == 1
    assert probe.open_attempt_count == 1
    assert controller.current is None
    assert controller.refresh_required is True
    assert controller._closed is False

    assert await controller.attachment_for_mutation() is fresh
    assert probe.close_attempts == [initial]
    assert probe.open_attempt_count == 2
    assert probe.open_states == [(None, True, False), (None, True, False)]
    assert controller.current is fresh
    assert controller.refresh_required is False


def test_session_mutation_detail_rejects_raw_string_enum_values() -> None:
    """Host typed detail owner 拒绝裸字符串，CLI 不提供 StrEnum 值兼容。

    :returns: ``None``。
    :raises AssertionError: typed enum contract 被宽松字符串输入绕过时抛出。
    """

    with pytest.raises(
        TypeError,
        match="reason must be HostSessionMutationRejectionReason",
    ):
        HostSessionMutationErrorDetail(
            kind="session_mutation_access",
            session_id="session-1",
            reason=cast(HostSessionMutationRejectionReason, "read_only"),
            required_mode=HostSessionAccessMode.READ_WRITE,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )

    with pytest.raises(TypeError, match="actual_mode must be HostSessionAccessMode"):
        HostSessionMutationErrorDetail(
            kind="session_mutation_access",
            session_id="session-1",
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            required_mode=HostSessionAccessMode.READ_WRITE,
            actual_mode=cast(HostSessionAccessMode, "read_only"),
        )


@pytest.mark.asyncio
async def test_interactive_read_only_retry_preserves_composer_and_uses_fresh_rw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RO 拒绝保留 draft/cursor/history，同语义 fresh RW 后只接受一个 Run。

    :param tmp_path: pytest 临时 workspace。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: REPL、identity、close-open 或 acceptance 不变量失效时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ReadOnlyRetryHost(
        attachment_modes=(
            HostSessionAccessMode.READ_ONLY,
            HostSessionAccessMode.READ_WRITE,
        ),
        submit_statuses=(HostTerminalStatus.SUCCEEDED,),
    )
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            stderr=stderr,
            input=pipe_input,
            output=DummyOutput(),
        )
        execution = asyncio.create_task(
            session_execution.execute_interactive_on_session(
                host=cast(Host, host),
                prepared=_prepared_interactive_execution(
                    tmp_path=tmp_path,
                    runtime=runtime,
                ),
                session_id="session-1",
                composer=composer,
                sigint_monitor_factory=_NoopSigintMonitor,
                run_startup_reconnect=False,
                detail=False,
                thinking=False,
            )
        )
        pipe_input.send_text("abc\x1b[D\r")
        await _wait_for_mutation_attempt_count(host, 1)
        await _wait_for_stderr_text(stderr, "session is read-only")

        assert composer._draft == "abc"
        assert composer._cursor_position == 2
        assert composer._history.get_strings() == []
        assert host._submit_index == 0
        assert execution.done() is False

        pipe_input.send_text("\r")
        await _wait_for_mutation_attempt_count(host, 2)
        await _wait_for_real_composer_history(composer, ("abc",))
        await _wait_for_real_composer_phase(
            composer,
            phase=InteractiveComposerPhase.IDLE,
        )
        pipe_input.send_text("\x04")
        exit_code = await asyncio.wait_for(execution, timeout=2.0)

    request_ids = [request.client_request_id for request in host.mutation_attempts]
    assert exit_code == EXIT_SUCCESS
    assert request_ids[0] == request_ids[1]
    assert host._submit_index == 1
    assert host.timeline == [
        "open:B1:read_only",
        "close-start:B1",
        "close-complete:B1",
        "open:B2:read_write",
        "close-start:B2",
        "close-complete:B2",
    ]
    assert [attachment.close_count for attachment in host.attachments] == [1, 1]
    assert stderr.getvalue().count("session is read-only") == 1


@pytest.mark.asyncio
async def test_interactive_repeated_read_only_keeps_identity_and_eof_closes_current(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """fresh attachment 仍 RO 时重复 typed 提示、零 Run，并在 EOF 关闭 current。

    :param tmp_path: pytest 临时 workspace。
    :param capsys: pytest 输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: identity、REPL continuation 或 cleanup 次数漂移时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ReadOnlyRetryHost(
        attachment_modes=(
            HostSessionAccessMode.READ_ONLY,
            HostSessionAccessMode.READ_ONLY,
        )
    )
    same_submit = InteractiveComposerEvent(
        kind=InteractiveComposerEventKind.SUBMIT,
        draft="same draft",
        input_revision=1,
    )
    composer = _ScriptedComposer((same_submit, same_submit))

    exit_code = await session_execution.execute_interactive_on_session(
        host=cast(Host, host),
        prepared=_prepared_interactive_execution(tmp_path=tmp_path, runtime=runtime),
        session_id="session-1",
        composer=composer,
        sigint_monitor_factory=_NoopSigintMonitor,
        run_startup_reconnect=False,
        detail=False,
        thinking=False,
    )

    captured = capsys.readouterr()
    request_ids = [request.client_request_id for request in host.mutation_attempts]
    assert exit_code == EXIT_SUCCESS
    assert len(request_ids) == 2
    assert request_ids[0] == request_ids[1]
    assert host._submit_index == 0
    assert composer.accepted_history_flags == []
    assert captured.err.count("session is read-only") == 2
    assert host.timeline.index("close-complete:B1") < host.timeline.index("open:B2:read_only")
    assert [attachment.close_count for attachment in host.attachments] == [1, 1]


@pytest.mark.asyncio
async def test_interactive_edit_after_read_only_allocates_new_turn_identity(
    tmp_path: Path,
) -> None:
    """RO 后用户编辑才创建新 request/turn identity，旧 pending 不进 history。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: edited submission 复用旧 identity 或重复 Run 时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ReadOnlyRetryHost(
        attachment_modes=(
            HostSessionAccessMode.READ_ONLY,
            HostSessionAccessMode.READ_WRITE,
        ),
        submit_statuses=(HostTerminalStatus.SUCCEEDED,),
    )
    composer = _ScriptedComposer(
        (
            InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.SUBMIT,
                draft="draft",
                input_revision=1,
            ),
            InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.SUBMIT,
                draft="draft edited",
                input_revision=2,
            ),
        )
    )

    exit_code = await session_execution.execute_interactive_on_session(
        host=cast(Host, host),
        prepared=_prepared_interactive_execution(tmp_path=tmp_path, runtime=runtime),
        session_id="session-1",
        composer=composer,
        sigint_monitor_factory=_NoopSigintMonitor,
        run_startup_reconnect=False,
        detail=False,
        thinking=False,
    )

    requests = host.mutation_attempts
    assert exit_code == EXIT_SUCCESS
    assert [request.user_prompt for request in requests] == ["draft", "draft edited"]
    assert requests[0].client_request_id != requests[1].client_request_id
    assert requests[0].client_request_id.endswith(":turn-1:submit")
    assert requests[1].client_request_id.endswith(":turn-2:submit")
    assert host._submit_index == 1
    assert composer.accepted_history_flags == [True]


@pytest.mark.asyncio
async def test_interactive_read_only_then_composer_error_closes_without_double_close(
    tmp_path: Path,
) -> None:
    """RO 后 composer 异常必须传播，并由 outer lifecycle 关闭 current 一次。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: 异常被吞、Run 被创建或 attachment 泄漏时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ReadOnlyRetryHost(attachment_modes=(HostSessionAccessMode.READ_ONLY,))

    with pytest.raises(RuntimeError, match="composer read failed"):
        await session_execution.execute_interactive_on_session(
            host=cast(Host, host),
            prepared=_prepared_interactive_execution(tmp_path=tmp_path, runtime=runtime),
            session_id="session-1",
            composer=_ReadOnlyThenErrorComposer("draft"),
            sigint_monitor_factory=_NoopSigintMonitor,
            run_startup_reconnect=False,
            detail=False,
            thinking=False,
        )

    assert host._submit_index == 0
    assert [attachment.close_count for attachment in host.attachments] == [1]


@pytest.mark.asyncio
async def test_interactive_only_swallows_exact_typed_read_only_detail(
    tmp_path: Path,
) -> None:
    """误导文本但 typed reason 非 READ_ONLY 的 Host 错误必须保持 fatal。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: CLI 使用 message 字符串匹配并误吞错误时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ReadOnlyRetryHost(
        attachment_modes=(HostSessionAccessMode.READ_ONLY,),
        rejection_reason=HostSessionMutationRejectionReason.ATTACHMENT_REQUIRED,
        rejection_actual_mode=None,
    )

    with pytest.raises(HostApiError) as exc_info:
        await session_execution.execute_interactive_on_session(
            host=cast(Host, host),
            prepared=_prepared_interactive_execution(tmp_path=tmp_path, runtime=runtime),
            session_id="session-1",
            composer=_ScriptedComposer(("draft",)),
            sigint_monitor_factory=_NoopSigintMonitor,
            run_startup_reconnect=False,
            detail=False,
            thinking=False,
        )

    detail = exc_info.value.detail
    assert isinstance(detail, HostSessionMutationErrorDetail)
    assert detail.reason is HostSessionMutationRejectionReason.ATTACHMENT_REQUIRED
    assert host._submit_index == 0
    assert [attachment.close_count for attachment in host.attachments] == [1]


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
    _install_cli_tty_composer(monkeypatch, ("触发 lost",))

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
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    fake_host = _FakeHost(submit_statuses=(terminal_status,))

    exit_code = await session_execution.execute_interactive_on_session(
        host=cast(Host, fake_host),
        prepared=prepared,
        session_id="session-existing",
        composer=_ScriptedComposer(("触发非成功终态",)),
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
        context_slot_values=interactive_command.build_interactive_context_slot_values(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )
    fake_host = _FakeHost(submit_statuses=(HostTerminalStatus.LOST,))

    with pytest.raises(CliTerminalCursorError, match="cursor write failed"):
        await session_execution.execute_interactive_on_session(
            host=cast(Host, fake_host),
            prepared=prepared,
            session_id="session-existing",
            composer=_ScriptedComposer(("触发终态",)),
            sigint_monitor_factory=_NoopSigintMonitor,
            run_startup_reconnect=False,
        )


@pytest.mark.asyncio
async def test_interactive_escape_crosses_pre_acceptance_barrier_once(
    tmp_path: Path,
) -> None:
    """pre-accept Escape 必须等 exact Run id 后只发一次 graceful cancel。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: acceptance barrier 或 single cancel 语义不符时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _DelayedAcceptanceControlledHost()
    composer = _ScriptedComposer(
        (
            "第一轮",
            InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.RUNNING_KEY_ACTION,
                running_key_action=RunningKeyAction.CANCEL_RUN,
            ),
        )
    )
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
    )

    await asyncio.wait_for(host.committed.wait(), timeout=2.0)
    assert host.cancel_requests == []
    host.release_response.set()
    await asyncio.wait_for(host.cancel_started.wait(), timeout=2.0)
    host.release_cancel_terminal.set()
    exit_code = await asyncio.wait_for(driver, timeout=2.0)

    assert exit_code == EXIT_SUCCESS
    assert len(host.cancel_requests) == 1
    assert host.cancel_requests[0].mode is CancelMode.GRACEFUL
    assert host.cancel_requests[0].reason == "cli_sigint"
    assert not host.cancel_waiter_cancelled


@pytest.mark.asyncio
async def test_interactive_repeated_escape_merges_once_after_accepted_activity(
    tmp_path: Path,
) -> None:
    """accepted active turn 的重复 Escape 必须合并为 single cancel。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: active cancel 次数或终态不符合契约时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ControlledInteractiveHost()
    cancel_event = InteractiveComposerEvent(
        kind=InteractiveComposerEventKind.RUNNING_KEY_ACTION,
        running_key_action=RunningKeyAction.CANCEL_RUN,
    )
    composer = _BarrierScriptedComposer(
        (
            "第一轮",
            cancel_event,
            cancel_event,
        ),
        blocked_call_index=2,
    )
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
    )

    await _wait_for_submit_count(host, 1)
    await asyncio.wait_for(composer.read_entered.wait(), timeout=2.0)
    await host._run_watchers["run-1"].push(_thinking_event(run_id="run-1"))
    await host._run_watchers["run-1"].push(_activity_event(run_id="run-1"))
    composer.release_read.set()
    await asyncio.wait_for(host.cancel_started.wait(), timeout=2.0)
    host.release_cancel_terminal.set()
    exit_code = await asyncio.wait_for(driver, timeout=2.0)

    assert exit_code == EXIT_SUCCESS
    assert len(host.cancel_requests) == 1
    assert composer._remaining == []


@pytest.mark.asyncio
async def test_interactive_cancel_waiter_failure_propagates_before_submit_terminal(
    tmp_path: Path,
) -> None:
    """cancel waiter 先失败时必须立即传播，不能永久等待 submit terminal。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: cancel failure 被吞掉、延迟或重复请求时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _FailingCancelControlledHost()
    composer = _ScriptedComposer(
        (
            "current",
            InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.RUNNING_KEY_ACTION,
                running_key_action=RunningKeyAction.CANCEL_RUN,
            ),
        )
    )
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
    )

    with pytest.raises(RuntimeError, match="cancel waiter failed"):
        await asyncio.wait_for(driver, timeout=2.0)

    assert len(host.cancel_requests) == 1


@pytest.mark.asyncio
async def test_interactive_ctrl_c_first_cancels_second_exits_and_third_is_noop(
    tmp_path: Path,
) -> None:
    """active Ctrl+C 的 single-cancel/exit-after/no-op 矩阵不得取消 waiter。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: Ctrl+C 生命周期或 waiter ownership 回归时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ControlledInteractiveHost()
    composer = _ScriptedComposer(("第一轮",))
    monitor = _ManualSigintMonitor()
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
        sigint_monitor=monitor,
    )

    await _wait_for_submit_count(host, 1)
    monitor.notify()
    await asyncio.wait_for(host.cancel_started.wait(), timeout=2.0)
    await _wait_for_sigint_observation(monitor, 1)
    monitor.notify()
    await _wait_for_sigint_observation(monitor, 2)
    monitor.notify()
    await _wait_for_sigint_observation(monitor, 3)
    assert not driver.done()
    host.release_cancel_terminal.set()
    exit_code = await asyncio.wait_for(driver, timeout=2.0)

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(host.cancel_requests) == 1
    assert not host.cancel_waiter_cancelled


@pytest.mark.asyncio
async def test_interactive_os_sigint_first_second_and_third_follow_same_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同步 fallback 的 OS SIGINT 三次必须复用统一 active 生命周期。

    :param tmp_path: pytest 临时 workspace。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: OS signal 与 composer Ctrl+C 生命周期不一致时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ControlledInteractiveHost()
    composer = _ScriptedComposer(("current",))
    monitor = _ManualSigintMonitor()
    fallback = _install_sync_sigint_fallback(monkeypatch)
    monitor.install()
    try:
        driver = _start_tty_driver(
            host=host,
            runtime=runtime,
            workspace_root=tmp_path,
            composer=composer,
            sigint_monitor=monitor,
        )

        await _wait_for_submit_count(host, 1)
        handler = fallback.installed_handler()
        handler(signal.SIGINT, None)
        await asyncio.wait_for(host.cancel_started.wait(), timeout=2.0)
        await _wait_for_sigint_observation(monitor, 1)
        handler(signal.SIGINT, None)
        await _wait_for_sigint_observation(monitor, 2)
        handler(signal.SIGINT, None)
        await _wait_for_sigint_observation(monitor, 3)

        assert not driver.done()
        assert len(host.cancel_requests) == 1
        host.release_cancel_terminal.set()
        exit_code = await asyncio.wait_for(driver, timeout=2.0)
    finally:
        monitor.close()

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert monitor.count == 3
    assert len(host.cancel_requests) == 1
    assert not host.cancel_waiter_cancelled
    assert len(fallback.signal_calls) == 2
    assert fallback.signal_calls[1] is signal.SIG_IGN
    assert fallback.current_handler is signal.SIG_IGN


@pytest.mark.asyncio
async def test_interactive_typeahead_creates_sole_queue_and_preserves_rejected_draft(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """active Enter 只建 sole QUEUE；第二份 draft 保留且绝不 STEER。

    :param tmp_path: pytest 临时 workspace。
    :param capsys: pytest 输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: queue 数量、behavior 或 draft ownership 回归时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ControlledInteractiveHost()
    composer = _ScriptedComposer(("current", "queued", "kept draft"))
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
    )

    await _wait_for_submit_count(host, 2)
    await _wait_for_prompt_call_count(composer, 3)
    assert len(host.submit_requests) == 2
    assert all(
        request.behavior is FollowupBehavior.QUEUE and request.target_run_id is None for request in host.submit_requests
    )
    await host.finish_run("run-1")
    await asyncio.sleep(0)
    await host.finish_run("run-2")
    exit_code = await asyncio.wait_for(driver, timeout=2.0)
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert [request.user_prompt for request in host.submit_requests] == [
        "current",
        "queued",
    ]
    assert composer.accepted_history_flags == [True, True]
    assert composer._pending_submit
    assert "one follow-up is already queued; draft kept" in captured.err


@pytest.mark.asyncio
async def test_interactive_lost_waits_accepted_sole_queue_terminal_before_failure(
    tmp_path: Path,
) -> None:
    """current LOST 后必须等待 accepted sole QUEUE 终态再失败退出。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: queued 被跳过、取消、重复提交或退出码错误时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ControlledInteractiveHost()
    composer = _ScriptedComposer(("current", "queued"))
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
    )

    await _wait_for_submit_count(host, 2)
    await host.finish_run("run-1", status=HostTerminalStatus.LOST)
    await _wait_for_phase_call_count(
        composer,
        phase=InteractiveComposerPhase.RUNNING,
        expected_count=2,
    )

    assert not driver.done()
    assert [request.user_prompt for request in host.submit_requests] == [
        "current",
        "queued",
    ]
    assert all(
        request.behavior is FollowupBehavior.QUEUE and request.target_run_id is None for request in host.submit_requests
    )
    assert host.cancel_requests == []

    await host.finish_run("run-2")
    exit_code = await asyncio.wait_for(driver, timeout=2.0)

    assert exit_code == EXIT_FAILURE
    assert len(host.submit_requests) == 2
    assert host.cancel_requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("enter_before_terminal", (True, False))
async def test_interactive_terminal_enter_race_submits_exactly_once(
    enter_before_terminal: bool,
    tmp_path: Path,
) -> None:
    """terminal/Enter 双序都必须得到两个且仅两个 QUEUE Run。

    :param enter_before_terminal: 是否先释放第二份 Enter event。
    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: generation 裁决重复或丢失 submit 时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ControlledInteractiveHost()
    composer = _BarrierScriptedComposer(
        ("first", "second"),
        blocked_call_index=2,
    )
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
    )

    await _wait_for_submit_count(host, 1)
    await asyncio.wait_for(composer.read_entered.wait(), timeout=2.0)
    if enter_before_terminal:
        composer.release_read.set()
        await _wait_for_submit_count(host, 2)
        await host.finish_run("run-1")
    else:
        await host.finish_run("run-1")
        composer.release_read.set()
        await _wait_for_submit_count(host, 2)
    await host.finish_run("run-2")
    exit_code = await asyncio.wait_for(driver, timeout=2.0)

    assert exit_code == EXIT_SUCCESS
    assert [request.user_prompt for request in host.submit_requests] == [
        "first",
        "second",
    ]
    assert all(
        request.behavior is FollowupBehavior.QUEUE and request.target_run_id is None for request in host.submit_requests
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("delay_queued_response", (False, True))
async def test_interactive_exit_after_cancel_waits_accepted_sole_queue_terminal(
    delay_queued_response: bool,
    tmp_path: Path,
) -> None:
    """exit-after-cancel 前后 accepted sole QUEUE 都必须恰好执行并终态。

    :param delay_queued_response: 是否把 queued public response 延迟到 exit intent 后。
    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: queued Run 被取消、重复或永久 queued 时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host: _ControlledInteractiveHost
    if delay_queued_response:
        host = _DelayedQueuedResponseHost()
    else:
        host = _ControlledInteractiveHost()
    composer = _ScriptedComposer(("current", "queued"))
    monitor = _ManualSigintMonitor()
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
        sigint_monitor=monitor,
    )

    await _wait_for_submit_count(host, 2)
    if isinstance(host, _DelayedQueuedResponseHost):
        await asyncio.wait_for(host.queued_committed.wait(), timeout=2.0)
    monitor.notify()
    await asyncio.wait_for(host.cancel_started.wait(), timeout=2.0)
    await _wait_for_sigint_observation(monitor, 1)
    monitor.notify()
    await _wait_for_sigint_observation(monitor, 2)
    host.release_cancel_terminal.set()
    await asyncio.sleep(0)
    assert not driver.done()
    if isinstance(host, _DelayedQueuedResponseHost):
        host.release_queued_response.set()
        await asyncio.sleep(0)
    await host.finish_run("run-2")
    exit_code = await asyncio.wait_for(driver, timeout=2.0)

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(host.cancel_requests) == 1
    assert len(host.submit_requests) == 2
    assert host.submit_requests[1].behavior is FollowupBehavior.QUEUE
    assert host.submit_requests[1].target_run_id is None
    assert not host.cancel_waiter_cancelled


@pytest.mark.asyncio
async def test_interactive_ctrl_t_toggles_without_cancel(
    tmp_path: Path,
) -> None:
    """active Ctrl+T 必须经 composer 切换 view，且不提交或取消 draft。

    :param tmp_path: pytest 临时 workspace。
    :returns: ``None``。
    :raises AssertionError: view toggle 误触 submit/cancel 时抛出。
    """

    runtime = await _prepare_interactive_runtime(tmp_path)
    host = _ControlledInteractiveHost()
    stderr = io.StringIO()
    run_view = TerminalInteractiveRunView(
        stderr=stderr,
        options=InteractiveRunViewOptions(enabled=True),
    )
    composer = _ScriptedComposer(
        (
            "first",
            InteractiveComposerEvent(
                kind=InteractiveComposerEventKind.RUNNING_KEY_ACTION,
                running_key_action=RunningKeyAction.TOGGLE_ACTIVITY,
            ),
        )
    )
    display = RuntimeDisplayController(
        activity_display=run_view,
        thinking_display=None,
    )
    await display.install_runtime_line_guard()
    driver = _start_tty_driver(
        host=host,
        runtime=runtime,
        workspace_root=tmp_path,
        composer=composer,
        run_view=run_view,
        runtime_display=display,
    )

    await _wait_for_submit_count(host, 1)
    await _wait_for_prompt_call_count(composer, 2)
    await host.finish_run("run-1")
    exit_code = await asyncio.wait_for(driver, timeout=2.0)
    await display.aclose()

    assert exit_code == EXIT_SUCCESS
    assert host.cancel_requests == []
    assert "[Interactive activity]" in stderr.getvalue()


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


@pytest.mark.parametrize(
    "argv",
    (
        ("--config=/tmp/x", "interactive"),
        ("interactive", "--config=/tmp/x"),
    ),
)
def test_interactive_removed_config_fails_before_service_preparation(
    argv: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """interactive 的旧配置选项必须在 Service preparation 前被拒绝。

    :param argv: 覆盖 root 与 command scope 的旧选项调用。
    :param capsys: pytest 标准错误捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: parser 未先失败或 Service 被调用时抛出。
    """

    captured_requests: list[EntrypointRuntimeRequest] = []

    async def unexpected_prepare(
        request: EntrypointRuntimeRequest,
    ) -> EntrypointRuntimeResult:
        """记录越过 parser boundary 的意外 Service 请求并立即失败。

        :param request: 意外收到的 runtime request。
        :returns: 正常路径不会返回。
        :raises AssertionError: 只要被调用就抛出。
        """

        captured_requests.append(request)
        raise AssertionError("Service preparation must not run")

    monkeypatch.setattr(
        session_execution,
        "prepare_entrypoint_runtime",
        unexpected_prepare,
    )

    exit_code = cli_main.main(argv)
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "unrecognized arguments" in captured.err
    assert "--config" in captured.err
    assert captured_requests == []


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
async def test_interactive_sync_sigint_handler_defers_notification_to_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同步 fallback handler 必须只向 loop 投递一次通知。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: handler 同步修改状态或安装状态发布不完整时抛出。
    """

    fallback = _install_sync_sigint_fallback(monkeypatch)
    monitor = CliSigintMonitor()
    original_signal = fallback.set_signal_handler

    def install_after_state_is_visible(
        signal_number: int,
        handler: _TestSignalHandler,
    ) -> _TestSignalHandler:
        """确认完整状态先于同步 handler 安装可见。

        :param signal_number: 待设置的 signal 编号。
        :param handler: 新同步 handler。
        :returns: 被替换的 previous handler。
        :raises AssertionError: 安装时 owner 状态尚未完整发布时抛出。
        """

        if callable(handler):
            assert monitor._installation_mode is agent_entrypoint._CliSigintInstallationMode.SYNCHRONOUS
            assert monitor._loop is asyncio.get_running_loop()
            assert monitor._previous_handler is signal.SIG_IGN
        return original_signal(signal_number, handler)

    monkeypatch.setattr(signal, "signal", install_after_state_is_visible)
    monitor.install()
    wait_task = asyncio.create_task(monitor.wait_next(0))
    await asyncio.sleep(0)
    try:
        fallback.installed_handler()(signal.SIGINT, None)

        assert monitor.count == 0
        assert not wait_task.done()
        assert await asyncio.wait_for(wait_task, timeout=2.0) == 1
        assert monitor.count == 1
    finally:
        monitor.close()

    restored_call_count = len(fallback.signal_calls)
    monitor.close()
    assert fallback.current_handler is signal.SIG_IGN
    assert len(fallback.signal_calls) == restored_call_count
    assert monitor._loop is None


@pytest.mark.asyncio
async def test_interactive_sync_sigint_install_failure_rolls_back_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同步 fallback 安装失败必须回滚为完整 NONE 状态。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 安装失败后残留 mode、loop 或 previous 时抛出。
    """

    _install_sync_sigint_fallback(monkeypatch)
    monitor = CliSigintMonitor()

    def fail_sync_install(
        _signal_number: int,
        _handler: _TestSignalHandler,
    ) -> _TestSignalHandler:
        """模拟底层同步 handler 安装失败。

        :param _signal_number: 待设置的 signal 编号。
        :param _handler: 待安装的同步 handler。
        :returns: 正常路径不会返回。
        :raises OSError: 始终抛出以验证 owner 回滚。
        """

        raise OSError("synchronous handler install failed")

    monkeypatch.setattr(signal, "signal", fail_sync_install)

    with pytest.raises(OSError, match="synchronous handler install failed"):
        monitor.install()

    assert monitor._installation_mode is agent_entrypoint._CliSigintInstallationMode.NONE
    assert monitor._loop is None
    assert monitor._previous_handler is None
    monitor.close()


def _reject_system_editor_fallback(
    _buffer: Buffer,
    validate_and_handle: bool = False,
) -> asyncio.Task[None]:
    """拒绝显式 editor integration 误入 public system fallback。

    :param _buffer: prompt_toolkit public buffer。
    :param validate_and_handle: fallback 的 accept 参数。
    :returns: 正常路径不会返回。
    :raises AssertionError: production 错误调用 system fallback 时始终抛出。
    """

    raise AssertionError(f"explicit editor entered system fallback: validate={validate_and_handle}")


def _configure_editor_failure_case(
    case: _InteractiveEditorFailureCase,
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """设置 integration case 的 VISUAL，并保留一个不可 fallback 的 EDITOR。

    :param case: editor 失败或取消 case。
    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 收到未支持 case 时抛出。
    """

    if case is _InteractiveEditorFailureCase.MISSING:
        visual = str(tmp_path / "missing-editor")
    elif case is _InteractiveEditorFailureCase.NON_EXECUTABLE:
        non_executable = tmp_path / "non-executable-editor"
        non_executable.write_text("not executable", encoding="utf-8")
        non_executable.chmod(0o600)
        visual = str(non_executable)
    elif case in {
        _InteractiveEditorFailureCase.SPAWN_ERROR,
        _InteractiveEditorFailureCase.NONZERO,
    }:
        visual = sys.executable
    else:
        raise AssertionError(f"unsupported editor integration case: {case}")
    monkeypatch.setenv("VISUAL", visual)
    monkeypatch.setenv("EDITOR", "/must/not/fallback")


async def _wait_for_editor_integration_completion(
    *,
    case: _InteractiveEditorFailureCase,
    composer: PromptToolkitInteractiveComposer,
    process: _InteractiveEditorProcess,
    stderr: io.StringIO,
) -> None:
    """等待 editor binding 完成失败/取消且恢复同一 composer。

    :param case: editor 失败或取消 case。
    :param composer: 真实 prompt_toolkit composer。
    :param process: exact argv process 替身。
    :param stderr: composer diagnostic 流。
    :returns: ``None``。
    :raises AssertionError: 有界调度内未完成时抛出。
    """

    for _attempt in range(1_000):
        invalid_complete = (
            case
            in {
                _InteractiveEditorFailureCase.MISSING,
                _InteractiveEditorFailureCase.NON_EXECUTABLE,
            }
            and stderr.getvalue() != ""
        )
        explicit_complete = (
            case
            in {
                _InteractiveEditorFailureCase.SPAWN_ERROR,
                _InteractiveEditorFailureCase.NONZERO,
            }
            and bool(process.calls)
            and not composer._editor_tasks
        )
        if invalid_complete or explicit_complete:
            await asyncio.sleep(0)
            return
        await asyncio.sleep(0)
    raise AssertionError(f"editor integration case did not complete: {case}")


async def _wait_for_real_composer_phase(
    composer: PromptToolkitInteractiveComposer,
    *,
    phase: InteractiveComposerPhase,
) -> None:
    """等待真实 composer 进入指定 REPL phase。

    :param composer: 真实 prompt_toolkit composer。
    :param phase: 预期 phase。
    :returns: ``None``。
    :raises AssertionError: 有界调度内未进入指定 phase 时抛出。
    """

    for _attempt in range(1_000):
        if composer._phase is phase:
            await asyncio.sleep(0)
            return
        await asyncio.sleep(0)
    raise AssertionError(f"composer phase did not reach {phase}")


async def _wait_for_real_composer_history(
    composer: PromptToolkitInteractiveComposer,
    expected: tuple[str, ...],
) -> None:
    """等待真实 composer history 达到 acceptance 后的精确内容。

    :param composer: 真实 prompt_toolkit composer。
    :param expected: 预期 history 字符串序列。
    :returns: ``None``。
    :raises AssertionError: 有界调度内 history 未达到预期时抛出。
    """

    for _attempt in range(1_000):
        if tuple(composer._history.get_strings()) == expected:
            await asyncio.sleep(0)
            return
        await asyncio.sleep(0)
    raise AssertionError(f"composer history did not reach {expected}")


def _start_tty_driver(
    *,
    host: _ControlledInteractiveHost,
    runtime: EntrypointRuntimeResult,
    workspace_root: Path,
    composer: _ScriptedComposer,
    sigint_monitor: CliSigintMonitor | None = None,
    run_view: TerminalInteractiveRunView | None = None,
    runtime_display: RuntimeDisplayController | None = None,
) -> asyncio.Task[int]:
    """启动 owner-level interactive TTY driver task。

    :param host: 可控 Host fake。
    :param runtime: 真实 interactive runtime assembly。
    :param workspace_root: 测试 workspace root。
    :param composer: scripted typed composer。
    :param sigint_monitor: 可选手动 SIGINT monitor；省略时永不触发。
    :param run_view: 可选 terminal run view。
    :param runtime_display: 可选串行 display controller。
    :returns: 正在运行的 TTY driver task。
    :raises Exception: task 创建失败时向上透传。
    """

    return asyncio.create_task(
        session_execution._drive_interactive_tty_repl(
            host=cast(Host, host),
            runtime=runtime,
            workspace_root=workspace_root,
            invocation=session_execution.new_cli_invocation(
                command_name="interactive",
                scenario="interactive",
                display_user="本地 CLI 用户",
                ticker=None,
            ),
            session_id="session-1",
            run_overrides=ServiceRunOverrides(),
            composer=composer,
            sigint_monitor=(_NoopSigintMonitor() if sigint_monitor is None else sigint_monitor),
            attachment_controller=_test_attachment_controller(host),
            run_view=run_view,
            runtime_display=runtime_display,
        )
    )


async def _wait_for_submit_count(
    host: _FakeHost,
    expected_count: int,
) -> None:
    """在有界 event-loop ticks 内等待 submit 请求数。

    :param host: 可控 Host fake。
    :param expected_count: 预期最小 submit 数。
    :returns: ``None``。
    :raises AssertionError: 有界等待内未达到预期时抛出。
    """

    for _attempt in range(1_000):
        if len(host.submit_requests) >= expected_count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"submit count did not reach {expected_count}")


async def _wait_for_mutation_attempt_count(
    host: _ReadOnlyRetryHost,
    expected_count: int,
) -> None:
    """等待 RO/RW Host fake 观察到指定 mutation attempt 数。

    :param host: typed READ_ONLY retry Host fake。
    :param expected_count: 预期最小 mutation attempt 数。
    :returns: ``None``。
    :raises AssertionError: 有界调度内未达到预期时抛出。
    """

    for _attempt in range(1_000):
        if len(host.mutation_attempts) >= expected_count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"mutation attempt count did not reach {expected_count}")


async def _wait_for_stderr_text(stderr: io.StringIO, expected: str) -> None:
    """等待 stderr 出现指定稳定用户提示。

    :param stderr: 被测 CLI stderr 流。
    :param expected: 必须出现的文本。
    :returns: ``None``。
    :raises AssertionError: 有界调度内文本未出现时抛出。
    """

    for _attempt in range(1_000):
        if expected in stderr.getvalue():
            return
        await asyncio.sleep(0)
    raise AssertionError(f"stderr did not contain {expected}")


async def _wait_for_prompt_call_count(
    composer: _ScriptedComposer,
    expected_count: int,
) -> None:
    """在有界 event-loop ticks 内等待 composer read 次数。

    :param composer: scripted composer。
    :param expected_count: 预期最小 read 次数。
    :returns: ``None``。
    :raises AssertionError: 有界等待内未达到预期时抛出。
    """

    for _attempt in range(1_000):
        if len(composer.prompt_calls) >= expected_count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"prompt call count did not reach {expected_count}")


async def _wait_for_phase_call_count(
    composer: _ScriptedComposer,
    *,
    phase: InteractiveComposerPhase,
    expected_count: int,
) -> None:
    """在有界 event-loop ticks 内等待指定 phase 调用次数。

    :param composer: scripted composer。
    :param phase: 待观察的 composer phase。
    :param expected_count: 预期最小调用次数。
    :returns: ``None``。
    :raises AssertionError: 有界等待内未达到预期时抛出。
    """

    for _attempt in range(1_000):
        if composer.phase_calls.count(phase) >= expected_count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"phase {phase} count did not reach {expected_count}")


async def _wait_for_sigint_observation(
    monitor: _ManualSigintMonitor,
    expected_count: int,
) -> None:
    """在有界 event-loop ticks 内等待 driver 消费 SIGINT 计数。

    :param monitor: 手动 SIGINT monitor。
    :param expected_count: 预期已消费的最新 SIGINT 计数。
    :returns: ``None``。
    :raises AssertionError: 有界等待内未消费预期计数时抛出。
    """

    for _attempt in range(1_000):
        if monitor.observed_counts and monitor.observed_counts[-1] >= expected_count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"SIGINT observation did not reach {expected_count}")


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
            scene_id="interactive",
            context_slot_values={
                _FINS_DEFAULT_SUBJECT_SLOT: "",
                _CURRENT_TIME_SLOT: _CURRENT_TIME_TEXT,
            },
            assembly_overrides=ServiceAssemblyOverrides(model_id=_MODEL_ID),
            env=_runtime_assembly_env(),
        )
    )


def _prepared_interactive_execution(
    *,
    tmp_path: Path,
    runtime: EntrypointRuntimeResult,
) -> session_execution.PreparedInteractiveSessionExecution:
    """构造 existing-session interactive invocation 准备结果。

    :param tmp_path: pytest 临时 workspace root。
    :param runtime: 已装配的 interactive runtime。
    :returns: 使用默认 run override 的 invocation 准备结果。
    :raises Exception: invocation contract 构造失败时向上透传。
    """

    return session_execution.PreparedInteractiveSessionExecution(
        runtime=runtime,
        workspace_root=tmp_path,
        invocation=session_execution.new_cli_invocation(
            command_name="interactive",
            scenario="interactive",
            display_user="本地 CLI 用户",
            ticker=None,
        ),
        run_overrides=ServiceRunOverrides(),
        usage_error_factory=interactive_command.CliInteractiveUsageError,
    )


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
        final_answer=(_final_answer(run_id="run-startup") if status is HostTerminalStatus.SUCCEEDED else None),
        error_message=_error_message(run_id="run-startup", status=status),
        cancel_reason=("cancelled for run-startup" if status is HostTerminalStatus.CANCELLED else None),
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
