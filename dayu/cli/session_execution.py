"""CLI 已有 Session 执行公共 helper。

本模块拥有 ``dayu-cli prompt``、``dayu-cli interactive`` 与
``dayu-cli session resume`` 共享的 existing-session runtime prepare、
Host submit/watch 执行组合和 CLI invocation identity。它只复用
``dayu.service.entrypoint_runtime`` 的 public helper，不读取 Host durable
internals，不访问 Fins storage，也不根据 scenario 字符串构造业务
context slot；调用方必须传入已经构造好的 ``context_slot_values``。
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import BinaryIO, Final, Never, TextIO

from dayu.cli.activity import CliActivityRenderer, CliActivityRendererOptions
from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    cancel_and_await_task,
    optional_stripped_text,
    package_config_root,
    resolve_workspace_root,
    service_run_overrides_from_args,
)
from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.cli.composer import (
    InteractiveComposer,
    InteractiveComposerEvent,
    InteractiveComposerEventKind,
    InteractiveComposerPhase,
    new_interactive_composer,
)
from dayu.cli.exit_codes import EXIT_KEYBOARD_INTERRUPT, EXIT_SUCCESS
from dayu.cli.host_context import (
    CLI_SIGINT_REASON,
    CliInvocation,
    build_interactive_host_context,
    build_prompt_host_context,
    interactive_cancel_client_request_id,
    interactive_submit_client_request_id,
    new_cli_invocation,
    prompt_cancel_client_request_id,
    prompt_submit_client_request_id,
)
from dayu.cli.output import (
    render_interactive_terminal_result,
    render_prompt_terminal_result,
)
from dayu.cli.run_keys import (
    NoopRunningKeyMonitor,
    RunningKeyAction,
    RunningKeyMonitor,
    new_running_key_monitor,
)
from dayu.cli.run_view import InteractiveRunView, new_interactive_run_view
from dayu.cli.runtime_display import (
    RuntimeActivityDisplay,
    RuntimeDisplayController,
    RuntimeThinkingDisplay,
)
from dayu.cli.session_terminal_cursor import (
    advance_cli_terminal_cursor,
    read_cli_terminal_cursor,
)
from dayu.cli.thinking import CliThinkingRenderer, CliThinkingRendererOptions
from dayu.contracts import JsonValue
from dayu.host.api import CancelMode, FollowupBehavior, Host
from dayu.service.entrypoint_runtime import (
    DEFAULT_ENTRYPOINT_STARTUP_PROMOTION_POLL_INTERVAL_SECONDS,
    DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS,
    ENTRYPOINT_STARTUP_OUTBOX_LAGGED_MAX_ATTEMPTS,
    ENTRYPOINT_STARTUP_PROMOTION_MAX_ATTEMPTS,
    EntrypointCancelRequest,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointRunTerminalResult,
    EntrypointStartupReconnectRequest,
    EntrypointTurnRequest,
    cancel_entrypoint_run_and_wait,
    prepare_entrypoint_runtime,
    startup_reconnect_entrypoint_session,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides

DEFAULT_DISPLAY_USER: Final[str] = "本地 CLI 用户"
PROMPT_TURN_INDEX: Final[int] = 1
_MODEL_OPTION: Final[str] = "--model"
_PROMPT_OPERATION_SUBMIT_FOLLOWUP: Final[str] = "submit_followup"
_PROMPT_OPERATION_CANCEL_RUN: Final[str] = "cancel_run"
_INTERACTIVE_OPERATION_STARTUP_RECONNECT: Final[str] = "startup_reconnect"
_INTERACTIVE_OPERATION_SUBMIT_FOLLOWUP: Final[str] = "submit_followup"
_INTERACTIVE_OPERATION_CANCEL_RUN: Final[str] = "cancel_run"
_INTERACTIVE_INPUT_PROMPT: Final[str] = "dayu> "
_INTERACTIVE_QUEUED_DRAFT_MESSAGE: Final[str] = "Interactive: one follow-up is already queued; draft kept."
_INTERACTIVE_INVALID_UTF8_MESSAGE: Final[str] = "interactive stdin is not valid UTF-8"
_UsageErrorFactory = Callable[[str], ValueError]
_CancelRunAndWait = Callable[[str, str], Awaitable[EntrypointRunTerminalResult]]


@dataclass(frozen=True, slots=True)
class PreparedPromptSessionExecution:
    """在已有 Session 上执行 prompt turn 所需的准备结果。

    :param runtime: entrypoint runtime assembly 结果。
    :param workspace_root: 当前 workspace 根目录。
    :param invocation: 当前 CLI invocation 身份。
    :param user_prompt: 本轮用户 prompt。
    :param run_overrides: 本轮可映射执行 override。
    """

    runtime: EntrypointRuntimeResult
    workspace_root: Path
    invocation: CliInvocation
    user_prompt: str
    run_overrides: ServiceRunOverrides


@dataclass(frozen=True, slots=True)
class PreparedInteractiveSessionExecution:
    """在已有 Session 上运行 interactive REPL 所需的准备结果。

    :param runtime: entrypoint runtime assembly 结果。
    :param workspace_root: 当前 workspace 根目录。
    :param invocation: 当前 CLI invocation 身份。
    :param run_overrides: 本命令所有 turn 复用的运行时 override。
    :param usage_error_factory: interactive 输入用法错误构造器。
    """

    runtime: EntrypointRuntimeResult
    workspace_root: Path
    invocation: CliInvocation
    run_overrides: ServiceRunOverrides
    usage_error_factory: _UsageErrorFactory


@dataclass(frozen=True, slots=True)
class _PromptTurnOutcome:
    """prompt outer driver 消费的 terminal 与 cleanup 后退出意图。

    :param terminal: Host canonical terminal truth。
    :param exit_after_cancel: second Ctrl+C 是否要求 outer cleanup 后返回 130。
    """

    terminal: EntrypointRunTerminalResult
    exit_after_cancel: bool


class _LocalCancelIntent(StrEnum):
    """单个 active turn 的单调本地取消意图。"""

    NONE = "none"
    CANCEL_REQUESTED = "cancel_requested"
    EXIT_AFTER_CANCEL = "exit_after_cancel"


@dataclass(slots=True)
class _AcceptedRunBarrier:
    """Host public acceptance callback 的唯一 Run id barrier。

    :param accepted_run_id: Host callback 发布的 exact Run id。
    :param accepted: acceptance 发布事件。
    """

    accepted_run_id: str | None = None
    accepted: asyncio.Event = field(default_factory=asyncio.Event)

    def publish_accepted(self, run_id: str) -> None:
        """发布 Host accepted Run id。

        :param run_id: Host public acceptance callback 的 exact Run id。
        :returns: ``None``。
        :raises ValueError: Run id 为空或与已发布 identity 冲突时抛出。
        """

        if not run_id:
            raise ValueError("accepted run id must not be empty")
        if self.accepted_run_id is None:
            self.accepted_run_id = run_id
            self.accepted.set()
            return
        if self.accepted_run_id != run_id:
            raise ValueError("accepted run id conflicts with published identity")

    async def wait_run_id(self) -> str:
        """等待并返回 Host callback 发布的 exact Run id。

        :returns: Host accepted Run id。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        :raises RuntimeError: event 已触发但 Run id 缺失时抛出。
        """

        await self.accepted.wait()
        if self.accepted_run_id is None:
            raise RuntimeError("accepted run id missing")
        return self.accepted_run_id


@dataclass(slots=True)
class _ActiveTurnCloseout:
    """协调单个 turn 的 acceptance、graceful cancel 与 canonical terminal。

    本类型不持有或操作 composer、display、cursor、attachment、key/signal
    monitor、generation、queued draft 或 history；这些副作用仍由 outer driver
    唯一拥有。

    :param cancel_run_and_wait: 针对本 turn 构造 Host cancel request 并等待
        canonical terminal 的 typed callable。
    :param barrier: Host public acceptance barrier。
    :param intent: 当前单调本地取消意图。
    """

    cancel_run_and_wait: _CancelRunAndWait
    barrier: _AcceptedRunBarrier = field(default_factory=_AcceptedRunBarrier)
    intent: _LocalCancelIntent = _LocalCancelIntent.NONE
    _cancel_reason: str | None = None
    _cancel_task: asyncio.Task[EntrypointRunTerminalResult] | None = None
    _terminal: EntrypointRunTerminalResult | None = None
    _terminal_observed: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def cancel_reason(self) -> str | None:
        """返回首次冻结的 Host cancel reason。

        :returns: 首次 cancel reason；尚未请求取消时为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self._cancel_reason

    @property
    def cancel_task(self) -> asyncio.Task[EntrypointRunTerminalResult] | None:
        """返回 coordinator 唯一 Host cancel/terminal task。

        :returns: 已创建的 cancel task；尚未请求取消时为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self._cancel_task

    def publish_accepted(self, run_id: str) -> None:
        """向唯一 acceptance barrier 发布 exact Run id。

        :param run_id: Host public acceptance callback 的 exact Run id。
        :returns: ``None``。
        :raises ValueError: Run identity 冲突时抛出。
        """

        self.barrier.publish_accepted(run_id)

    def request_cancel(
        self,
        *,
        reason: str,
        exit_after: bool,
    ) -> _LocalCancelIntent:
        """登记本地取消并确保至多一个 Host graceful cancel path。

        :param reason: 首次请求冻结的 Host cancel reason。
        :param exit_after: 是否把既有取消单调升级为 terminal 后退出意图。
        :returns: 更新后的本地取消意图。
        :raises ValueError: 首次 cancel reason 为空时抛出。
        :raises RuntimeError: 当前线程没有运行中的 asyncio loop 时抛出。
        """

        if self.intent is _LocalCancelIntent.NONE:
            if not reason:
                raise ValueError("cancel reason must not be empty")
            self._cancel_reason = reason
            self.intent = _LocalCancelIntent.CANCEL_REQUESTED
            self._cancel_task = asyncio.create_task(self.wait_accepted_then_cancel())
            return self.intent
        if exit_after:
            self.intent = _LocalCancelIntent.EXIT_AFTER_CANCEL
        return self.intent

    async def wait_accepted_then_cancel(self) -> EntrypointRunTerminalResult:
        """跨 acceptance barrier 发起一次 Host cancel 并等待 canonical terminal。

        terminal 若先于 acceptance/cancel commit 到达，则保留真实 Host terminal，
        且不发送迟到 cancel。

        :returns: 本 turn 唯一 Host canonical terminal。
        :raises asyncio.CancelledError: coordinator task 被 outer abnormal cleanup 取消时透传。
        :raises RuntimeError: cancel reason 缺失或 terminal 状态不完整时抛出。
        :raises Exception: Host cancel/terminal observation 失败时向上透传。
        """

        reason = self._cancel_reason
        if reason is None:
            raise RuntimeError("cancel reason missing")
        accepted_task = asyncio.create_task(self.barrier.wait_run_id())
        terminal_task = asyncio.create_task(self._terminal_observed.wait())
        try:
            done, _pending = await asyncio.wait(
                (accepted_task, terminal_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if terminal_task in done and accepted_task not in done:
                return self._require_terminal()
            run_id = await accepted_task
            if self._terminal_observed.is_set():
                return self._require_terminal()
            terminal = await self.cancel_run_and_wait(run_id, reason)
            self.observe_terminal(terminal)
            return self._require_terminal()
        finally:
            await cancel_and_await_task(accepted_task)
            await cancel_and_await_task(terminal_task)

    def observe_terminal(self, result: EntrypointRunTerminalResult) -> None:
        """记录本 turn 唯一 Host canonical terminal。

        :param result: Host public terminal observation。
        :returns: ``None``。
        :raises ValueError: terminal Run identity 或结果与既有 truth 冲突时抛出。
        """

        accepted_run_id = self.barrier.accepted_run_id
        if accepted_run_id is not None and result.run_id != accepted_run_id:
            raise ValueError("terminal run id conflicts with accepted run id")
        if self._terminal is None:
            self._terminal = result
            self._terminal_observed.set()
            return
        if self._terminal != result:
            raise ValueError("terminal result conflicts with canonical terminal")

    async def wait_closeout(self) -> EntrypointRunTerminalResult:
        """等待 Host cancel 与 canonical terminal 协调完成。

        :returns: 本 turn 唯一 Host canonical terminal。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        :raises RuntimeError: terminal event 与结果不一致时抛出。
        :raises Exception: Host cancel/terminal task 失败时向上透传。
        """

        if self._cancel_task is not None:
            await self._cancel_task
        await self._terminal_observed.wait()
        return self._require_terminal()

    def _require_terminal(self) -> EntrypointRunTerminalResult:
        """返回已观察 terminal 或报告 coordinator invariant failure。

        :returns: 已观察的唯一 Host canonical terminal。
        :raises RuntimeError: terminal 尚未记录时抛出。
        """

        if self._terminal is None:
            raise RuntimeError("canonical terminal missing")
        return self._terminal


class _InteractiveExitIntent(StrEnum):
    """interactive REPL 本地退出意图。"""

    CONTINUE = "continue"
    IDLE_EXIT_PENDING = "idle_exit_pending"


@dataclass(slots=True)
class _InteractiveActiveTurn:
    """当前 interactive turn 的 submit、acceptance 与 cancel 状态。

    :param generation: 当前 turn 的 REPL generation。
    :param turn_index: 当前 invocation 内稳定轮次序号。
    :param submit_task: submit + canonical terminal waiter。
    :param closeout: 本 turn 唯一 acceptance/cancel/terminal coordinator。
    :param cancel_rendered: outer driver 是否已展示 cancel requested。
    """

    generation: int
    turn_index: int
    submit_task: asyncio.Task[EntrypointRunTerminalResult]
    closeout: _ActiveTurnCloseout
    cancel_rendered: bool = False


@dataclass(frozen=True, slots=True)
class _InteractiveQueuedFollowup:
    """当前 invocation 唯一 queued follow-up。

    :param turn_index: queued submit 的稳定轮次序号。
    :param submit_task: queued submit + terminal waiter。
    :param closeout: queued turn 原有 coordinator identity。
    """

    turn_index: int
    submit_task: asyncio.Task[EntrypointRunTerminalResult]
    closeout: _ActiveTurnCloseout


@dataclass(frozen=True, slots=True)
class _InteractiveComposerCompletion:
    """带 current generation 的 composer 读取结果。

    :param generation: 开始读取时的 current generation。
    :param event: composer typed event。
    """

    generation: int
    event: InteractiveComposerEvent


async def prepare_prompt_session_execution(
    args: ParsedCliArgs,
    *,
    command_name: str,
    scenario: str,
    user_prompt: str,
    ticker: str | None,
    context_slot_values: dict[str, JsonValue],
    usage_error_factory: _UsageErrorFactory,
) -> PreparedPromptSessionExecution:
    """准备在已有 Session 上执行 prompt turn 所需的 runtime 与调用身份。

    :param args: argparse 已解析的 prompt 兼容命令参数。
    :param command_name: 当前 CLI command 名称。
    :param scenario: prompt scene id。
    :param user_prompt: 本轮用户 prompt。
    :param ticker: 调用方已校验的业务主体；未提供时为 ``None``。
    :param context_slot_values: 调用方按 prompt 语义构造好的 context slot。
    :param usage_error_factory: 当前命令用法错误构造器。
    :returns: 已准备的 prompt existing-session 执行输入。
    :raises ValueError: 用户输入参数非法时通过 ``usage_error_factory`` 抛出。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    workspace_root = resolve_workspace_root(
        args.workspace_root,
        error_factory=usage_error_factory,
    )
    invocation = new_cli_invocation(
        command_name=command_name,
        scenario=scenario,
        display_user=DEFAULT_DISPLAY_USER,
        ticker=ticker,
    )
    runtime = await _prepare_session_runtime(
        args=args,
        workspace_root=workspace_root,
        scenario=scenario,
        context_slot_values=context_slot_values,
        usage_error_factory=usage_error_factory,
    )
    return PreparedPromptSessionExecution(
        runtime=runtime,
        workspace_root=workspace_root,
        invocation=invocation,
        user_prompt=user_prompt,
        run_overrides=service_run_overrides_from_args(
            args,
            error_factory=usage_error_factory,
        ),
    )


async def prepare_interactive_session_execution(
    args: ParsedCliArgs,
    *,
    command_name: str,
    scenario: str,
    context_slot_values: dict[str, JsonValue],
    usage_error_factory: _UsageErrorFactory,
) -> PreparedInteractiveSessionExecution:
    """准备在已有 Session 上运行 interactive REPL 所需的 runtime 与调用身份。

    :param args: argparse 已解析的 interactive 兼容命令参数。
    :param command_name: 当前 CLI command 名称。
    :param scenario: interactive scene id。
    :param context_slot_values: 调用方按 interactive 语义构造好的 context slot。
    :param usage_error_factory: 当前命令用法错误构造器。
    :returns: 已准备的 interactive existing-session 执行输入。
    :raises ValueError: 用户输入参数非法时通过 ``usage_error_factory`` 抛出。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    workspace_root = resolve_workspace_root(
        args.workspace_root,
        error_factory=usage_error_factory,
    )
    invocation = new_cli_invocation(
        command_name=command_name,
        scenario=scenario,
        display_user=DEFAULT_DISPLAY_USER,
        ticker=None,
    )
    runtime = await _prepare_session_runtime(
        args=args,
        workspace_root=workspace_root,
        scenario=scenario,
        context_slot_values=context_slot_values,
        usage_error_factory=usage_error_factory,
    )
    return PreparedInteractiveSessionExecution(
        runtime=runtime,
        workspace_root=workspace_root,
        invocation=invocation,
        run_overrides=service_run_overrides_from_args(
            args,
            error_factory=usage_error_factory,
        ),
        usage_error_factory=usage_error_factory,
    )


async def execute_prompt_on_session(
    *,
    host: Host,
    prepared: PreparedPromptSessionExecution,
    session_id: str,
    sigint_monitor: CliSigintMonitor,
    detail: bool = True,
    thinking: bool = True,
) -> int:
    """在已解析的已有 Session 上执行 prompt turn。

    :param host: Host public handle。
    :param prepared: prompt existing-session 执行准备结果。
    :param session_id: 已存在且调用方已选择的 Host Session id。
    :param sigint_monitor: prompt 运行阶段 SIGINT monitor。
    :param detail: 是否显示运行态 activity stream。
    :param thinking: 是否显示运行态 thinking 增量。
    :returns: CLI 退出码。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    attachment = await host.attach_session(session_id)
    try:
        outcome = await _submit_prompt_turn_handling_sigint(
            host=host,
            runtime=prepared.runtime,
            invocation=prepared.invocation,
            session_id=session_id,
            user_prompt=prepared.user_prompt,
            run_overrides=prepared.run_overrides,
            sigint_monitor=sigint_monitor,
            activity_renderer=_new_detail_activity_renderer() if detail else None,
            thinking_renderer=_new_thinking_renderer() if thinking else None,
            key_monitor=new_running_key_monitor(),
        )
        terminal = outcome.terminal
        render_exit_code = render_prompt_terminal_result(terminal)
        await advance_cli_terminal_cursor(
            workspace_root=prepared.workspace_root,
            session_id=session_id,
            terminal_event_id=terminal.terminal_event_id,
            event_sequence=terminal.event_sequence,
        )
        if outcome.exit_after_cancel:
            return EXIT_KEYBOARD_INTERRUPT
        return render_exit_code
    finally:
        await asyncio.shield(attachment.aclose())


async def execute_interactive_on_session(
    *,
    host: Host,
    prepared: PreparedInteractiveSessionExecution,
    session_id: str,
    stdin: TextIO | None = None,
    binary_stdin: BinaryIO | None = None,
    composer: InteractiveComposer | None = None,
    sigint_monitor_factory: Callable[[], CliSigintMonitor] | None = None,
    run_view: InteractiveRunView | None = None,
    run_startup_reconnect: bool = True,
    detail: bool = True,
    thinking: bool = True,
) -> int:
    """在已解析的已有 Session 上运行 interactive REPL。

    :param host: Host public handle。
    :param prepared: interactive existing-session 执行准备结果。
    :param session_id: 已存在且调用方已选择的 Host Session id。
    :param stdin: 用于判定 TTY capability 的文本输入流；``None`` 表示标准输入。
    :param binary_stdin: non-TTY whole-stream 二进制输入；显式 ``stdin`` 为
        non-TTY 时必须同时提供，生产标准输入自动使用其 ``buffer``。
    :param composer: 可注入的 TTY composer；存在时强制走 TTY 状态机。
    :param sigint_monitor_factory: invocation 级 SIGINT monitor 工厂。
    :param run_view: interactive 运行态 view；``None`` 表示按 TTY policy 创建。
    :param run_startup_reconnect: 是否在输入态前执行已有 Session startup reconnect。
    :param detail: 是否显示运行态 activity stream。
    :param thinking: 是否显示运行态 thinking 增量。
    :returns: CLI 退出码。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    effective_stdin = sys.stdin if stdin is None else stdin
    tty_mode = composer is not None or effective_stdin.isatty()
    effective_composer = new_interactive_composer() if tty_mode and composer is None else composer
    effective_binary_stdin = None
    if not tty_mode:
        effective_binary_stdin = _resolve_interactive_binary_stdin(
            stdin=effective_stdin,
            explicit_binary_stdin=binary_stdin,
        )
    effective_sigint_monitor_factory = CliSigintMonitor if sigint_monitor_factory is None else sigint_monitor_factory
    sigint_monitor = effective_sigint_monitor_factory()
    effective_run_view = run_view
    if effective_run_view is None and detail:
        effective_run_view = new_interactive_run_view(show_activity=True)
    effective_thinking_renderer = _new_thinking_renderer() if thinking else None
    runtime_display = _new_runtime_display_controller(
        activity_display=effective_run_view if detail else None,
        thinking_display=effective_thinking_renderer,
    )
    primary_error: BaseException | None = None
    exit_code = EXIT_SUCCESS
    attachment = await host.attach_session(session_id)
    try:
        if runtime_display is not None:
            await runtime_display.install_runtime_line_guard()
        sigint_monitor.install()
        if run_startup_reconnect:
            startup_exit_code = await _run_existing_session_startup_handling_sigint(
                host=host,
                prepared=prepared,
                session_id=session_id,
                sigint_monitor=sigint_monitor,
            )
            if startup_exit_code != EXIT_SUCCESS:
                exit_code = startup_exit_code
            elif tty_mode:
                if effective_composer is None:
                    raise RuntimeError("interactive TTY composer is missing")
                exit_code = await _drive_interactive_tty_repl(
                    host=host,
                    runtime=prepared.runtime,
                    workspace_root=prepared.workspace_root,
                    invocation=prepared.invocation,
                    session_id=session_id,
                    run_overrides=prepared.run_overrides,
                    composer=effective_composer,
                    sigint_monitor=sigint_monitor,
                    run_view=effective_run_view if detail else None,
                    thinking_renderer=effective_thinking_renderer,
                    runtime_display=runtime_display,
                )
            else:
                if effective_binary_stdin is None:
                    raise RuntimeError("interactive binary stdin is missing")
                exit_code = await _run_interactive_non_tty_batch(
                    host=host,
                    runtime=prepared.runtime,
                    workspace_root=prepared.workspace_root,
                    invocation=prepared.invocation,
                    session_id=session_id,
                    run_overrides=prepared.run_overrides,
                    binary_stdin=effective_binary_stdin,
                    usage_error_factory=prepared.usage_error_factory,
                    sigint_monitor=sigint_monitor,
                    run_view=effective_run_view if detail else None,
                    thinking_renderer=effective_thinking_renderer,
                    runtime_display=runtime_display,
                )
        elif tty_mode:
            if effective_composer is None:
                raise RuntimeError("interactive TTY composer is missing")
            exit_code = await _drive_interactive_tty_repl(
                host=host,
                runtime=prepared.runtime,
                workspace_root=prepared.workspace_root,
                invocation=prepared.invocation,
                session_id=session_id,
                run_overrides=prepared.run_overrides,
                composer=effective_composer,
                sigint_monitor=sigint_monitor,
                run_view=effective_run_view if detail else None,
                thinking_renderer=effective_thinking_renderer,
                runtime_display=runtime_display,
            )
        else:
            if effective_binary_stdin is None:
                raise RuntimeError("interactive binary stdin is missing")
            exit_code = await _run_interactive_non_tty_batch(
                host=host,
                runtime=prepared.runtime,
                workspace_root=prepared.workspace_root,
                invocation=prepared.invocation,
                session_id=session_id,
                run_overrides=prepared.run_overrides,
                binary_stdin=effective_binary_stdin,
                usage_error_factory=prepared.usage_error_factory,
                sigint_monitor=sigint_monitor,
                run_view=effective_run_view if detail else None,
                thinking_renderer=effective_thinking_renderer,
                runtime_display=runtime_display,
            )
    except BaseException as error:
        primary_error = error
    cleanup_error: BaseException | None = None
    try:
        sigint_monitor.close()
    except BaseException as error:
        cleanup_error = error
    display_error = await _close_runtime_display(runtime_display)
    if display_error is not None:
        cleanup_error = _combine_lifecycle_cleanup_errors(
            cleanup_error,
            display_error,
        )
    try:
        await asyncio.shield(attachment.aclose())
    except BaseException as error:
        cleanup_error = _combine_lifecycle_cleanup_errors(
            cleanup_error,
            error,
        )
    if primary_error is not None:
        _raise_lifecycle_primary(primary_error, cleanup_error)
    if cleanup_error is not None:
        raise cleanup_error
    return exit_code


async def _prepare_session_runtime(
    *,
    args: ParsedCliArgs,
    workspace_root: Path,
    scenario: str,
    context_slot_values: dict[str, JsonValue],
    usage_error_factory: _UsageErrorFactory,
) -> EntrypointRuntimeResult:
    """准备 existing-session 执行所需的 Service entrypoint runtime。

    :param args: argparse 已解析的兼容命令参数。
    :param workspace_root: 已解析 workspace 根目录。
    :param scenario: Service scene id。
    :param context_slot_values: 调用方已经构造好的 context slot。
    :param usage_error_factory: 当前命令用法错误构造器。
    :returns: entrypoint runtime 准备结果。
    :raises ValueError: model 参数非法时通过 ``usage_error_factory`` 抛出。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    return await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root(),
            scene_id=scenario,
            context_slot_values=context_slot_values,
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=optional_stripped_text(
                    args.model,
                    field_name=_MODEL_OPTION,
                    error_factory=usage_error_factory,
                )
            ),
            env=os.environ,
        )
    )


async def _run_existing_session_startup_reconnect(
    *,
    host: Host,
    prepared: PreparedInteractiveSessionExecution,
    session_id: str,
) -> int:
    """在 interactive 输入态前执行已有 Session startup reconnect。

    :param host: Host public handle。
    :param prepared: interactive existing-session 执行准备结果。
    :param session_id: 已存在且调用方已选择的 Host Session id。
    :returns: CLI 退出码；成功完成 startup barrier 时返回 ``EXIT_SUCCESS``。
    :raises Exception: cursor store、Host public API 或 startup helper 失败时向上抛出。
    """

    cursor_record = await read_cli_terminal_cursor(
        workspace_root=prepared.workspace_root,
        session_id=session_id,
    )
    startup = await startup_reconnect_entrypoint_session(
        host,
        request=EntrypointStartupReconnectRequest(
            context=build_interactive_host_context(
                prepared.invocation,
                operation=_INTERACTIVE_OPERATION_STARTUP_RECONNECT,
            ),
            session_id=session_id,
            terminal_cursor=cursor_record.terminal_cursor,
            seen_terminal_event_ids=frozenset(cursor_record.seen_terminal_event_ids),
            poll_interval_seconds=DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS,
            outbox_lagged_max_attempts=ENTRYPOINT_STARTUP_OUTBOX_LAGGED_MAX_ATTEMPTS,
            promotion_poll_interval_seconds=(DEFAULT_ENTRYPOINT_STARTUP_PROMOTION_POLL_INTERVAL_SECONDS),
            promotion_max_attempts=ENTRYPOINT_STARTUP_PROMOTION_MAX_ATTEMPTS,
        ),
    )
    for terminal in startup.terminal_results:
        render_exit_code = render_interactive_terminal_result(terminal)
        await advance_cli_terminal_cursor(
            workspace_root=prepared.workspace_root,
            session_id=session_id,
            terminal_event_id=terminal.terminal_event_id,
            event_sequence=terminal.event_sequence,
        )
        if render_exit_code != EXIT_SUCCESS:
            return render_exit_code
    return EXIT_SUCCESS


async def _run_existing_session_startup_handling_sigint(
    *,
    host: Host,
    prepared: PreparedInteractiveSessionExecution,
    session_id: str,
    sigint_monitor: CliSigintMonitor,
) -> int:
    """执行 startup reconnect，并让一次 OS SIGINT 安全结束本地 invocation。

    startup helper 不创建当前 invocation 的新 Run；SIGINT 只取消本地 startup
    observation，随后由 invocation 统一关闭 display、monitor 与 attachment。

    :param host: Host public handle。
    :param prepared: interactive existing-session 执行准备结果。
    :param session_id: 已存在 Session id。
    :param sigint_monitor: 已安装的 invocation SIGINT monitor。
    :returns: startup 退出码；SIGINT 返回 ``EXIT_KEYBOARD_INTERRUPT``。
    :raises Exception: startup reconnect 失败时向上透传。
    """

    observed_count = sigint_monitor.count
    startup_task = asyncio.create_task(
        _run_existing_session_startup_reconnect(
            host=host,
            prepared=prepared,
            session_id=session_id,
        )
    )
    sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_count))
    try:
        done, _pending = await asyncio.wait(
            (startup_task, sigint_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if sigint_task in done:
            await sigint_task
            await cancel_and_await_task(startup_task)
            return EXIT_KEYBOARD_INTERRUPT
        return await startup_task
    finally:
        await cancel_and_await_task(sigint_task)


def _new_detail_activity_renderer() -> CliActivityRenderer:
    """创建 ``--detail`` 模式使用的 activity renderer。

    :returns: 强制可见且启用的 CLI activity renderer。
    :raises Exception: 不主动抛出异常。
    """

    return CliActivityRenderer(
        options=CliActivityRendererOptions(
            visible=True,
            enabled=True,
        )
    )


def _new_thinking_renderer() -> CliThinkingRenderer:
    """创建 ``--thinking`` 模式使用的 thinking renderer。

    :returns: 强制启用的 CLI thinking renderer。
    :raises Exception: 不主动抛出异常。
    """

    return CliThinkingRenderer(options=CliThinkingRendererOptions(enabled=True))


def _new_runtime_display_controller(
    *,
    activity_display: RuntimeActivityDisplay | None,
    thinking_display: RuntimeThinkingDisplay | None,
) -> RuntimeDisplayController | None:
    """只在存在真实 callback/display consumer 时创建执行域。

    :param activity_display: activity-like renderer；无 renderer 时为 ``None``。
    :param thinking_display: thinking renderer；无 renderer 时为 ``None``。
    :returns: 私有 display controller；两类 renderer 都不存在时返回 ``None``。
    :raises RuntimeError: 私有 executor 构造失败时透传。
    """

    if activity_display is None and thinking_display is None:
        return None
    return RuntimeDisplayController(
        activity_display=activity_display,
        thinking_display=thinking_display,
    )


async def _close_runtime_display(
    runtime_display: RuntimeDisplayController | None,
) -> BaseException | None:
    """关闭可选 display controller 并捕获 caller-cleanup failure。

    :param runtime_display: invocation/prompt display controller。
    :returns: close failure；无 controller 或成功时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if runtime_display is None:
        return None
    try:
        await runtime_display.aclose()
    except BaseException as error:
        return error
    return None


async def _close_prompt_lifecycle(
    *,
    runtime_display: RuntimeDisplayController | None,
    monitor: RunningKeyMonitor,
    sigint_monitor: CliSigintMonitor,
    submit_task: asyncio.Task[EntrypointRunTerminalResult] | None,
    sigint_task: asyncio.Task[int] | None,
    key_task: asyncio.Task[RunningKeyAction] | None,
) -> BaseException | None:
    """按 display -> caller-local 顺序关闭 prompt lifecycle。

    :param runtime_display: prompt display controller。
    :param monitor: prompt 按键 monitor。
    :param sigint_monitor: prompt SIGINT monitor。
    :param submit_task: 可选 Service submit/observation task。
    :param sigint_task: 可选 SIGINT wait task。
    :param key_task: 可选按键 wait task。
    :returns: 首个 cleanup failure；全部成功时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    cleanup_error: BaseException | None = None
    if runtime_display is not None:
        runtime_display.begin_closing()
    if submit_task is not None and not submit_task.done():
        try:
            await cancel_and_await_task(submit_task)
        except BaseException as error:
            cleanup_error = error
    display_error = await _close_runtime_display(runtime_display)
    if display_error is not None:
        cleanup_error = _combine_lifecycle_cleanup_errors(
            cleanup_error,
            display_error,
        )
    try:
        monitor.close()
    except BaseException as error:
        cleanup_error = _combine_lifecycle_cleanup_errors(cleanup_error, error)
    try:
        sigint_monitor.close()
    except BaseException as error:
        cleanup_error = _combine_lifecycle_cleanup_errors(cleanup_error, error)
    if sigint_task is not None:
        try:
            await cancel_and_await_task(sigint_task)
        except BaseException as error:
            cleanup_error = _combine_lifecycle_cleanup_errors(cleanup_error, error)
    if key_task is not None:
        try:
            await cancel_and_await_task(key_task)
        except BaseException as error:
            cleanup_error = _combine_lifecycle_cleanup_errors(cleanup_error, error)
    return cleanup_error


def _combine_lifecycle_cleanup_errors(
    primary_error: BaseException | None,
    later_error: BaseException,
) -> BaseException:
    """保留首个 lifecycle cleanup failure 并串接后续 failure。

    :param primary_error: 既有首个 cleanup failure；尚无失败时为 ``None``。
    :param later_error: 后续 cleanup failure。
    :returns: 应继续传播的首个 cleanup failure。
    :raises Exception: 不主动抛出异常。
    """

    if primary_error is None:
        return later_error
    _append_lifecycle_cleanup_cause(primary_error, later_error)
    return primary_error


def _append_lifecycle_cleanup_cause(
    primary_error: BaseException,
    later_error: BaseException,
) -> None:
    """把后续 caller cleanup failure 追加到既有 cause 链尾部。

    :param primary_error: 必须保持 top-level identity 的首个 cleanup failure。
    :param later_error: 后续 caller cleanup failure。
    :returns: ``None``。
    :raises RuntimeError: 检测到既有 cause 环时抛出。
    """

    current = primary_error
    seen_ids: set[int] = set()
    while current.__cause__ is not None:
        current_id = id(current)
        if current_id in seen_ids:
            raise RuntimeError("CLI lifecycle cleanup cause chain contains a cycle")
        seen_ids.add(current_id)
        current = current.__cause__
    current.__cause__ = later_error


def _raise_lifecycle_primary(
    primary_error: BaseException,
    cleanup_error: BaseException | None,
) -> Never:
    """保持业务/cancellation primary，并附加 lifecycle cleanup cause。

    :param primary_error: caller-visible primary failure。
    :param cleanup_error: lifecycle cleanup failure；无失败时为 ``None``。
    :returns: 本函数不返回。
    :raises BaseException: 原样抛出 ``primary_error``。
    """

    if cleanup_error is None:
        raise primary_error
    raise primary_error from cleanup_error


async def _submit_prompt_turn_handling_sigint(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    invocation: CliInvocation,
    session_id: str,
    user_prompt: str,
    run_overrides: ServiceRunOverrides,
    sigint_monitor: CliSigintMonitor,
    activity_renderer: CliActivityRenderer | None = None,
    thinking_renderer: CliThinkingRenderer | None = None,
    key_monitor: RunningKeyMonitor | None = None,
) -> _PromptTurnOutcome:
    """提交 prompt turn，并在 SIGINT 时按 Host public cancel 语义收口。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Host Session id。
    :param user_prompt: 本轮用户 prompt。
    :param run_overrides: 本轮可映射执行 override。
    :param sigint_monitor: prompt 运行阶段 SIGINT monitor。
    :param activity_renderer: 运行态 activity renderer；``None`` 表示不输出。
    :param thinking_renderer: 运行态 thinking renderer；``None`` 表示不输出。
    :param key_monitor: 运行态 TTY 按键 monitor；``None`` 表示 no-op。
    :returns: Host terminal 与 second Ctrl+C cleanup 后退出意图。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    closeout = _ActiveTurnCloseout(
        cancel_run_and_wait=partial(
            _cancel_prompt_run_for_closeout,
            host=host,
            invocation=invocation,
        )
    )
    renderer = activity_renderer
    thinking = thinking_renderer
    runtime_display = _new_runtime_display_controller(
        activity_display=renderer,
        thinking_display=thinking,
    )
    monitor = NoopRunningKeyMonitor() if key_monitor is None else key_monitor
    submit_task: asyncio.Task[EntrypointRunTerminalResult] | None = None
    sigint_task: asyncio.Task[int] | None = None
    key_task: asyncio.Task[RunningKeyAction] | None = None
    primary_error: BaseException | None = None
    terminal_result: EntrypointRunTerminalResult | None = None
    observed_turn_sigint_count = 0
    try:
        if runtime_display is not None:
            await runtime_display.install_runtime_line_guard()
        sigint_monitor.install()
        observed_sigint_count = sigint_monitor.count
        monitor.start()
        submit_task = asyncio.create_task(
            submit_entrypoint_turn_and_wait(
                host,
                request=EntrypointTurnRequest(
                    context=build_prompt_host_context(
                        invocation,
                        operation=_PROMPT_OPERATION_SUBMIT_FOLLOWUP,
                    ),
                    session_id=session_id,
                    client_request_id=prompt_submit_client_request_id(
                        invocation,
                        turn_index=PROMPT_TURN_INDEX,
                    ),
                    user_prompt=user_prompt,
                    tool_names=runtime.scene_inputs.tool_selection.tool_names,
                    behavior=FollowupBehavior.QUEUE,
                    target_run_id=None,
                    run_overrides=run_overrides,
                ),
                scene_inputs=runtime.scene_inputs,
                host_assembly=runtime.host_assembly,
                on_run_accepted=closeout.publish_accepted,
                on_activity=None if renderer is None else renderer.record,
                on_thinking=None if thinking is None else thinking.record,
                callback_execution_port=runtime_display,
            )
        )
        sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
        key_task = asyncio.create_task(monitor.wait_next())
        while True:
            wait_tasks: set[
                asyncio.Task[EntrypointRunTerminalResult]
                | asyncio.Task[int]
                | asyncio.Task[RunningKeyAction]
            ] = {submit_task, sigint_task, key_task}
            cancel_task = closeout.cancel_task
            if cancel_task is not None and not cancel_task.done():
                wait_tasks.add(cancel_task)
            done, _pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if key_task in done:
                action = await key_task
                if action is RunningKeyAction.TOGGLE_ACTIVITY:
                    if runtime_display is not None:
                        await runtime_display.toggle_activity_display()
                else:
                    was_pending = closeout.intent is not _LocalCancelIntent.NONE
                    closeout.request_cancel(
                        reason=CLI_SIGINT_REASON,
                        exit_after=False,
                    )
                    if not was_pending:
                        if runtime_display is not None:
                            await runtime_display.finish_thinking_display()
                            await runtime_display.render_cancel_requested()
                key_task = asyncio.create_task(monitor.wait_next())
            if sigint_task in done:
                new_sigint_count = await sigint_task
                pending_interrupts = new_sigint_count - observed_sigint_count
                observed_sigint_count = new_sigint_count
                for _interrupt_index in range(pending_interrupts):
                    observed_turn_sigint_count += 1
                    was_pending = closeout.intent is not _LocalCancelIntent.NONE
                    exit_after = observed_turn_sigint_count >= 2
                    closeout.request_cancel(
                        reason=CLI_SIGINT_REASON,
                        exit_after=exit_after,
                    )
                    if not was_pending:
                        if runtime_display is not None:
                            await runtime_display.finish_thinking_display()
                            await runtime_display.render_cancel_requested()
                    elif exit_after and runtime_display is not None:
                        await runtime_display.render_local_exit_after_cancel()
                sigint_task = asyncio.create_task(
                    sigint_monitor.wait_next(observed_sigint_count)
                )
            if submit_task in done:
                closeout.observe_terminal(await submit_task)
                terminal_result = await closeout.wait_closeout()
                if runtime_display is not None:
                    await runtime_display.finish_runtime_display()
                break
            cancel_task = closeout.cancel_task
            if cancel_task is not None and cancel_task in done:
                terminal_result = await closeout.wait_closeout()
                if runtime_display is not None:
                    await runtime_display.finish_runtime_display()
                break
    except BaseException as error:
        primary_error = error
    closeout_cleanup_error: BaseException | None = None
    closeout_task = closeout.cancel_task
    if closeout_task is not None and not closeout_task.done():
        try:
            await cancel_and_await_task(closeout_task)
        except BaseException as error:
            closeout_cleanup_error = error
    cleanup_error = await _close_prompt_lifecycle(
        runtime_display=runtime_display,
        monitor=monitor,
        sigint_monitor=sigint_monitor,
        submit_task=submit_task,
        sigint_task=sigint_task,
        key_task=key_task,
    )
    if closeout_cleanup_error is not None:
        if cleanup_error is not None:
            _append_lifecycle_cleanup_cause(closeout_cleanup_error, cleanup_error)
        cleanup_error = closeout_cleanup_error
    if primary_error is not None:
        _raise_lifecycle_primary(primary_error, cleanup_error)
    if cleanup_error is not None:
        raise cleanup_error
    if terminal_result is None:
        raise RuntimeError("prompt canonical terminal missing")
    return _PromptTurnOutcome(
        terminal=terminal_result,
        exit_after_cancel=closeout.intent is _LocalCancelIntent.EXIT_AFTER_CANCEL,
    )


async def _cancel_prompt_run_for_closeout(
    run_id: str,
    reason: str,
    *,
    host: Host,
    invocation: CliInvocation,
) -> EntrypointRunTerminalResult:
    """发起 prompt Host graceful cancel，并等待 canonical terminal。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param run_id: 待取消 Run id。
    :param reason: 首次本地取消冻结的 Host reason。
    :returns: Host canonical cancel terminal result。
    :raises Exception: cancel 或 terminal observation 失败时向上抛出。
    """

    return await cancel_entrypoint_run_and_wait(
        host,
        request=EntrypointCancelRequest(
            context=build_prompt_host_context(
                invocation,
                operation=_PROMPT_OPERATION_CANCEL_RUN,
            ),
            run_id=run_id,
            client_request_id=prompt_cancel_client_request_id(
                invocation,
                turn_index=PROMPT_TURN_INDEX,
                run_id=run_id,
            ),
            reason=reason,
            mode=CancelMode.GRACEFUL,
        ),
    )


def _resolve_interactive_binary_stdin(
    *,
    stdin: TextIO,
    explicit_binary_stdin: BinaryIO | None,
) -> BinaryIO:
    """解析 non-TTY whole-stream 的唯一二进制输入 owner。

    :param stdin: 已用于 TTY capability 判定的文本输入流。
    :param explicit_binary_stdin: 测试或嵌入调用方显式注入的二进制流。
    :returns: 可一次读取到真实 EOF 的二进制输入流。
    :raises RuntimeError: 非标准文本流没有显式二进制输入时抛出。
    """

    if explicit_binary_stdin is not None:
        return explicit_binary_stdin
    if stdin is sys.stdin and isinstance(stdin, io.TextIOWrapper):
        return stdin.buffer
    raise RuntimeError("non-TTY interactive stdin requires an explicit binary stream")


def _read_interactive_non_tty_text(
    *,
    binary_stdin: BinaryIO,
    usage_error_factory: _UsageErrorFactory,
) -> str:
    """一次读取、严格解码并规范化 non-TTY whole stdin。

    :param binary_stdin: 二进制输入流。
    :param usage_error_factory: 当前 CLI surface 的用法错误构造器。
    :returns: CRLF/CR 已规范为 LF 且完成一次 outer trim 的文本。
    :raises ValueError: 输入不是合法 UTF-8 时通过错误构造器抛出稳定错误。
    :raises Exception: 二进制流读取失败时向上透传。
    """

    raw = binary_stdin.read()
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise usage_error_factory(_INTERACTIVE_INVALID_UTF8_MESSAGE) from None
    return decoded.replace("\r\n", "\n").replace("\r", "\n").strip()


async def _run_interactive_non_tty_batch(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    workspace_root: Path,
    invocation: CliInvocation,
    session_id: str,
    run_overrides: ServiceRunOverrides,
    binary_stdin: BinaryIO,
    usage_error_factory: _UsageErrorFactory,
    sigint_monitor: CliSigintMonitor,
    run_view: InteractiveRunView | None,
    thinking_renderer: CliThinkingRenderer | None,
    runtime_display: RuntimeDisplayController | None,
) -> int:
    """把 non-TTY whole stdin 作为至多一个 QUEUE turn 执行。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param workspace_root: 当前 workspace 根目录。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Session id。
    :param run_overrides: 本轮执行 override。
    :param binary_stdin: whole-stream 二进制输入。
    :param usage_error_factory: UTF-8 用法错误构造器。
    :param sigint_monitor: invocation 唯一 OS SIGINT monitor。
    :param run_view: 可选 interactive run view。
    :param thinking_renderer: 可选 thinking renderer。
    :param runtime_display: 可选串行 display controller。
    :returns: blank batch 返回成功；非空 batch 返回 terminal mapping。
    :raises Exception: 读取、submit、terminal、render 或 cursor 失败时向上透传。
    """

    user_prompt = _read_interactive_non_tty_text(
        binary_stdin=binary_stdin,
        usage_error_factory=usage_error_factory,
    )
    if user_prompt == "":
        return EXIT_SUCCESS
    active = _start_interactive_turn(
        host=host,
        runtime=runtime,
        invocation=invocation,
        session_id=session_id,
        turn_index=1,
        generation=1,
        user_prompt=user_prompt,
        run_overrides=run_overrides,
        run_view=run_view,
        thinking_renderer=thinking_renderer,
        runtime_display=runtime_display,
    )
    terminal, exit_after_cancel = await _wait_interactive_batch_terminal_handling_sigint(
        active=active,
        sigint_monitor=sigint_monitor,
        runtime_display=runtime_display,
    )
    terminal_exit_code = await _finish_interactive_terminal(
        terminal=terminal,
        workspace_root=workspace_root,
        session_id=session_id,
        run_view=run_view,
        runtime_display=runtime_display,
    )
    if exit_after_cancel:
        return EXIT_KEYBOARD_INTERRUPT
    return terminal_exit_code


async def _wait_interactive_batch_terminal_handling_sigint(
    *,
    active: _InteractiveActiveTurn,
    sigint_monitor: CliSigintMonitor,
    runtime_display: RuntimeDisplayController | None,
) -> tuple[EntrypointRunTerminalResult, bool]:
    """等待 non-TTY active Run 终态并消费 invocation SIGINT。

    第一次中断只登记 single graceful cancel；第二次只登记 terminal 后本地
    ``130``；后续中断不再改变状态。submit 与 cancel canonical waiter 在正常
    SIGINT 路径始终保留到 Host terminal，只有调用方异常取消本 helper 时才回收。

    :param active: whole-batch 唯一 active turn。
    :param sigint_monitor: invocation 唯一 OS SIGINT monitor。
    :param runtime_display: 可选串行 display controller。
    :returns: Host canonical terminal 与是否在其后返回 ``130``。
    :raises Exception: submit、acceptance、cancel 或 terminal observation 失败时
        向上透传。
    """

    observed_sigint_count = sigint_monitor.count
    sigint_task: asyncio.Task[int] | None = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
    observed_turn_sigint_count = 0
    normal_completion = False
    try:
        while True:
            wait_tasks: set[asyncio.Task[InteractiveComposerCompletionResult]] = {
                active.submit_task,
            }
            if sigint_task is not None:
                wait_tasks.add(sigint_task)
            cancel_task = active.closeout.cancel_task
            if cancel_task is not None and not cancel_task.done():
                wait_tasks.add(cancel_task)
            done, _pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if sigint_task is not None and sigint_task in done:
                new_sigint_count = await sigint_task
                sigint_task = None
                pending_interrupts = new_sigint_count - observed_sigint_count
                observed_sigint_count = new_sigint_count
                for _interrupt_index in range(pending_interrupts):
                    observed_turn_sigint_count += 1
                    await _request_interactive_cancel(
                        active=active,
                        reason=CLI_SIGINT_REASON,
                        composer=None,
                        runtime_display=runtime_display,
                        exit_after=observed_turn_sigint_count >= 2,
                    )

            await _render_interactive_cancel_requested_once(
                active=active,
                runtime_display=runtime_display,
            )

            if active.submit_task in done:
                active.closeout.observe_terminal(await active.submit_task)
                terminal = await active.closeout.wait_closeout()
                normal_completion = True
                return (
                    terminal,
                    active.closeout.intent is _LocalCancelIntent.EXIT_AFTER_CANCEL,
                )

            cancel_task = active.closeout.cancel_task
            if cancel_task is not None and cancel_task in done:
                terminal = await active.closeout.wait_closeout()
                normal_completion = True
                return (
                    terminal,
                    active.closeout.intent is _LocalCancelIntent.EXIT_AFTER_CANCEL,
                )

            if sigint_task is None:
                sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
    finally:
        if sigint_task is not None:
            await cancel_and_await_task(sigint_task)
        if not active.submit_task.done():
            await cancel_and_await_task(active.submit_task)
        if not normal_completion:
            cancel_task = active.closeout.cancel_task
            if cancel_task is not None:
                await cancel_and_await_task(cancel_task)


async def _drive_interactive_tty_repl(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    workspace_root: Path,
    invocation: CliInvocation,
    session_id: str,
    run_overrides: ServiceRunOverrides,
    composer: InteractiveComposer,
    sigint_monitor: CliSigintMonitor,
    run_view: InteractiveRunView | None = None,
    thinking_renderer: CliThinkingRenderer | None = None,
    runtime_display: RuntimeDisplayController | None = None,
) -> int:
    """驱动单 stdin owner 的 interactive TTY REPL 状态机。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param workspace_root: 当前 workspace 根目录。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Session id。
    :param run_overrides: 所有 turn 复用的执行 override。
    :param composer: invocation 唯一 prompt_toolkit stdin owner。
    :param sigint_monitor: invocation 唯一 OS SIGINT monitor。
    :param run_view: 可选 interactive run view。
    :param thinking_renderer: 可选 thinking renderer。
    :param runtime_display: 可选串行 display controller。
    :returns: frozen interactive terminal/interrupt 退出码。
    :raises Exception: composer、submit、cancel、render 或 cursor 失败时向上透传。
    """

    generation = 0
    next_turn_index = 1
    current: _InteractiveActiveTurn | None = None
    queued: _InteractiveQueuedFollowup | None = None
    exit_intent = _InteractiveExitIntent.CONTINUE
    exit_after_closeout = False
    active_sigint_count = 0
    deferred_exit_code: int | None = None
    composer.set_phase(InteractiveComposerPhase.IDLE)
    composer_task: asyncio.Task[_InteractiveComposerCompletion] | None = asyncio.create_task(
        _read_interactive_composer_event(
            composer=composer,
            generation=generation,
        )
    )
    observed_sigint_count = sigint_monitor.count
    sigint_task: asyncio.Task[int] | None = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
    normal_completion = False
    try:
        while True:
            wait_tasks: set[asyncio.Task[InteractiveComposerCompletionResult]] = set()
            if composer_task is not None:
                wait_tasks.add(composer_task)
            if sigint_task is not None:
                wait_tasks.add(sigint_task)
            if current is not None:
                wait_tasks.add(current.submit_task)
                cancel_task = current.closeout.cancel_task
                if cancel_task is not None and not cancel_task.done():
                    wait_tasks.add(cancel_task)
            if not wait_tasks:
                raise RuntimeError("interactive TTY driver has no waitable owner")
            done, _pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if composer_task is not None and composer_task in done:
                completion = await composer_task
                composer_task = None
                event = completion.event
                stale_control = (
                    event.kind
                    in {
                        InteractiveComposerEventKind.RUNNING_KEY_ACTION,
                    }
                    and completion.generation != generation
                )
                if not stale_control and deferred_exit_code is None:
                    if event.kind is InteractiveComposerEventKind.SUBMIT:
                        exit_intent = _InteractiveExitIntent.CONTINUE
                        draft = event.draft
                        if draft is None:
                            raise RuntimeError("interactive submit event draft is missing")
                        user_prompt = draft.strip()
                        if user_prompt == "":
                            composer.accept_submit(record_history=False)
                        elif current is None:
                            current = _start_interactive_turn(
                                host=host,
                                runtime=runtime,
                                invocation=invocation,
                                session_id=session_id,
                                turn_index=next_turn_index,
                                generation=generation,
                                user_prompt=user_prompt,
                                run_overrides=run_overrides,
                                run_view=run_view,
                                thinking_renderer=thinking_renderer,
                                runtime_display=runtime_display,
                            )
                            next_turn_index += 1
                            composer.accept_submit(record_history=True)
                            composer.set_phase(InteractiveComposerPhase.RUNNING)
                        elif queued is None:
                            queued = _start_interactive_queued_followup(
                                host=host,
                                runtime=runtime,
                                invocation=invocation,
                                session_id=session_id,
                                turn_index=next_turn_index,
                                user_prompt=user_prompt,
                                run_overrides=run_overrides,
                                run_view=run_view,
                                thinking_renderer=thinking_renderer,
                                runtime_display=runtime_display,
                            )
                            next_turn_index += 1
                            composer.accept_submit(record_history=True)
                        else:
                            print(_INTERACTIVE_QUEUED_DRAFT_MESSAGE, file=sys.stderr)
                    elif event.kind is InteractiveComposerEventKind.RUNNING_KEY_ACTION:
                        action = event.running_key_action
                        if action is None:
                            raise RuntimeError("interactive running key action is missing")
                        if action is RunningKeyAction.CANCEL_RUN and current is not None:
                            await _request_interactive_cancel(
                                active=current,
                                reason=CLI_SIGINT_REASON,
                                composer=composer,
                                runtime_display=runtime_display,
                                exit_after=False,
                            )
                        elif (
                            action is RunningKeyAction.TOGGLE_ACTIVITY
                            and current is not None
                            and runtime_display is not None
                        ):
                            await runtime_display.toggle_activity_display()
                    elif event.kind is InteractiveComposerEventKind.EOF:
                        exit_intent = _InteractiveExitIntent.CONTINUE
                        if current is None:
                            normal_completion = True
                            return EXIT_SUCCESS

            if sigint_task is not None and sigint_task in done:
                new_sigint_count = await sigint_task
                sigint_task = None
                pending_interrupts = new_sigint_count - observed_sigint_count
                observed_sigint_count = new_sigint_count
                for _interrupt_index in range(pending_interrupts):
                    if current is None:
                        if exit_intent is _InteractiveExitIntent.IDLE_EXIT_PENDING:
                            normal_completion = True
                            return EXIT_KEYBOARD_INTERRUPT
                        exit_intent = _InteractiveExitIntent.IDLE_EXIT_PENDING
                        continue
                    active_sigint_count += 1
                    exit_after = active_sigint_count >= 2
                    await _request_interactive_cancel(
                        active=current,
                        reason=CLI_SIGINT_REASON,
                        composer=composer,
                        runtime_display=runtime_display,
                        exit_after=exit_after,
                    )
                    if exit_after:
                        exit_after_closeout = True
                        if composer_task is not None:
                            await cancel_and_await_task(composer_task)
                            composer_task = None

            if current is not None:
                await _render_interactive_cancel_requested_once(
                    active=current,
                    runtime_display=runtime_display,
                )

            current_cancel_task = None if current is None else current.closeout.cancel_task
            if current is not None and (
                current.submit_task in done
                or (current_cancel_task is not None and current_cancel_task in done)
            ):
                completed = current
                if completed.submit_task in done:
                    completed.closeout.observe_terminal(await completed.submit_task)
                terminal = await completed.closeout.wait_closeout()
                terminal_exit_code = await _finish_interactive_terminal(
                    terminal=terminal,
                    workspace_root=workspace_root,
                    session_id=session_id,
                    run_view=run_view,
                    runtime_display=runtime_display,
                )
                if terminal_exit_code != EXIT_SUCCESS:
                    deferred_exit_code = terminal_exit_code
                if completed.closeout.intent is _LocalCancelIntent.EXIT_AFTER_CANCEL:
                    exit_after_closeout = True
                if not completed.submit_task.done():
                    await cancel_and_await_task(completed.submit_task)
                current = None
                generation += 1
                active_sigint_count = 0
                if queued is not None:
                    current = _promote_interactive_queued_followup(
                        queued=queued,
                        generation=generation,
                    )
                    queued = None
                    composer.set_phase(InteractiveComposerPhase.RUNNING)
                else:
                    composer.set_phase(InteractiveComposerPhase.IDLE)

            if current is None and (
                deferred_exit_code is not None or exit_after_closeout
            ):
                normal_completion = True
                if deferred_exit_code is not None:
                    return deferred_exit_code
                return EXIT_KEYBOARD_INTERRUPT

            accepting_input = deferred_exit_code is None and not exit_after_closeout
            if composer_task is None and accepting_input:
                composer_task = asyncio.create_task(
                    _read_interactive_composer_event(
                        composer=composer,
                        generation=generation,
                    )
                )
            if sigint_task is None:
                sigint_task = asyncio.create_task(
                    sigint_monitor.wait_next(observed_sigint_count)
                )
    finally:
        if composer_task is not None:
            await cancel_and_await_task(composer_task)
        if sigint_task is not None:
            await cancel_and_await_task(sigint_task)
        if not normal_completion:
            if current is not None:
                cancel_task = current.closeout.cancel_task
                if cancel_task is not None:
                    await cancel_and_await_task(cancel_task)
                await cancel_and_await_task(current.submit_task)
            if queued is not None:
                await cancel_and_await_task(queued.submit_task)


InteractiveComposerCompletionResult = _InteractiveComposerCompletion | EntrypointRunTerminalResult | str | int


async def _read_interactive_composer_event(
    *,
    composer: InteractiveComposer,
    generation: int,
) -> _InteractiveComposerCompletion:
    """读取 composer event 并绑定开始读取时的 current generation。

    :param composer: invocation 唯一 composer。
    :param generation: 当前 turn generation。
    :returns: 带 generation 的 composer completion。
    :raises Exception: composer 失败时向上透传。
    """

    return _InteractiveComposerCompletion(
        generation=generation,
        event=await composer.read_event(_INTERACTIVE_INPUT_PROMPT),
    )


def _start_interactive_turn(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    invocation: CliInvocation,
    session_id: str,
    turn_index: int,
    generation: int,
    user_prompt: str,
    run_overrides: ServiceRunOverrides,
    run_view: InteractiveRunView | None,
    thinking_renderer: CliThinkingRenderer | None,
    runtime_display: RuntimeDisplayController | None,
) -> _InteractiveActiveTurn:
    """创建 current QUEUE turn 及其唯一 submit/terminal waiter。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Session id。
    :param turn_index: 稳定轮次序号。
    :param generation: current turn generation。
    :param user_prompt: outer-trim 后的用户输入。
    :param run_overrides: 执行 override。
    :param run_view: 可选 run view。
    :param thinking_renderer: 可选 thinking renderer。
    :param runtime_display: 可选 display controller。
    :returns: 新 current turn。
    :raises Exception: task 创建失败时向上透传。
    """

    closeout = _ActiveTurnCloseout(
        cancel_run_and_wait=partial(
            _cancel_interactive_run_for_closeout,
            host=host,
            invocation=invocation,
            turn_index=turn_index,
        )
    )
    return _InteractiveActiveTurn(
        generation=generation,
        turn_index=turn_index,
        submit_task=_create_interactive_submit_task(
            host=host,
            runtime=runtime,
            invocation=invocation,
            session_id=session_id,
            turn_index=turn_index,
            user_prompt=user_prompt,
            run_overrides=run_overrides,
            closeout=closeout,
            run_view=run_view,
            thinking_renderer=thinking_renderer,
            runtime_display=runtime_display,
        ),
        closeout=closeout,
    )


def _start_interactive_queued_followup(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    invocation: CliInvocation,
    session_id: str,
    turn_index: int,
    user_prompt: str,
    run_overrides: ServiceRunOverrides,
    run_view: InteractiveRunView | None,
    thinking_renderer: CliThinkingRenderer | None,
    runtime_display: RuntimeDisplayController | None,
) -> _InteractiveQueuedFollowup:
    """创建 sole QUEUE follow-up，不携带 STEER target。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Session id。
    :param turn_index: 稳定轮次序号。
    :param user_prompt: outer-trim 后的用户输入。
    :param run_overrides: 执行 override。
    :param run_view: 可选 run view。
    :param thinking_renderer: 可选 thinking renderer。
    :param runtime_display: 可选 display controller。
    :returns: sole queued follow-up。
    :raises Exception: task 创建失败时向上透传。
    """

    closeout = _ActiveTurnCloseout(
        cancel_run_and_wait=partial(
            _cancel_interactive_run_for_closeout,
            host=host,
            invocation=invocation,
            turn_index=turn_index,
        )
    )
    return _InteractiveQueuedFollowup(
        turn_index=turn_index,
        submit_task=_create_interactive_submit_task(
            host=host,
            runtime=runtime,
            invocation=invocation,
            session_id=session_id,
            turn_index=turn_index,
            user_prompt=user_prompt,
            run_overrides=run_overrides,
            closeout=closeout,
            run_view=run_view,
            thinking_renderer=thinking_renderer,
            runtime_display=runtime_display,
        ),
        closeout=closeout,
    )


def _create_interactive_submit_task(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    invocation: CliInvocation,
    session_id: str,
    turn_index: int,
    user_prompt: str,
    run_overrides: ServiceRunOverrides,
    closeout: _ActiveTurnCloseout,
    run_view: InteractiveRunView | None,
    thinking_renderer: CliThinkingRenderer | None,
    runtime_display: RuntimeDisplayController | None,
) -> asyncio.Task[EntrypointRunTerminalResult]:
    """创建一个 QUEUE submit + canonical terminal waiter task。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Session id。
    :param turn_index: 稳定轮次序号。
    :param user_prompt: outer-trim 后的用户输入。
    :param run_overrides: 执行 override。
    :param closeout: 本 turn 唯一 acceptance/cancel/terminal coordinator。
    :param run_view: 可选 run view。
    :param thinking_renderer: 可选 thinking renderer。
    :param runtime_display: 可选 display controller。
    :returns: submit + terminal waiter task。
    :raises Exception: task 创建失败时向上透传。
    """

    return asyncio.create_task(
        submit_entrypoint_turn_and_wait(
            host,
            request=EntrypointTurnRequest(
                context=build_interactive_host_context(
                    invocation,
                    operation=_INTERACTIVE_OPERATION_SUBMIT_FOLLOWUP,
                ),
                session_id=session_id,
                client_request_id=interactive_submit_client_request_id(
                    invocation,
                    turn_index=turn_index,
                ),
                user_prompt=user_prompt,
                tool_names=runtime.scene_inputs.tool_selection.tool_names,
                behavior=FollowupBehavior.QUEUE,
                target_run_id=None,
                run_overrides=run_overrides,
            ),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
            on_run_accepted=closeout.publish_accepted,
            on_activity=(None if run_view is None else run_view.activity_sink().record_activity),
            on_thinking=(None if thinking_renderer is None else thinking_renderer.record),
            callback_execution_port=runtime_display,
        )
    )


def _promote_interactive_queued_followup(
    *,
    queued: _InteractiveQueuedFollowup,
    generation: int,
) -> _InteractiveActiveTurn:
    """把唯一 queued follow-up 提升为本地 current turn。

    :param queued: 已提交的 sole queued follow-up。
    :param generation: 新 current generation。
    :returns: 复用原 submit/terminal waiter 的 current turn。
    :raises Exception: 不主动抛出异常。
    """

    return _InteractiveActiveTurn(
        generation=generation,
        turn_index=queued.turn_index,
        submit_task=queued.submit_task,
        closeout=queued.closeout,
    )


async def _request_interactive_cancel(
    *,
    active: _InteractiveActiveTurn,
    reason: str,
    composer: InteractiveComposer | None,
    runtime_display: RuntimeDisplayController | None,
    exit_after: bool,
) -> None:
    """按 current generation 合并并启动 single graceful cancel intent。

    :param active: 当前 active turn。
    :param reason: Host cancel reason。
    :param composer: TTY invocation 唯一 composer；non-TTY 时为 ``None``。
    :param runtime_display: 可选 display controller。
    :param exit_after: 是否由 second Ctrl+C 升级为 terminal 后退出。
    :returns: ``None``。
    :raises Exception: display 或 cancel task 创建失败时向上透传。
    """

    previous_intent = active.closeout.intent
    was_pending = previous_intent is not _LocalCancelIntent.NONE
    active.closeout.request_cancel(
        reason=reason,
        exit_after=exit_after,
    )
    if was_pending:
        if (
            exit_after
            and previous_intent is not _LocalCancelIntent.EXIT_AFTER_CANCEL
            and runtime_display is not None
        ):
            await runtime_display.render_local_exit_after_cancel()
        return
    if composer is not None:
        composer.set_phase(InteractiveComposerPhase.CANCELLING)
    if runtime_display is not None:
        await runtime_display.finish_thinking_display()
    await _render_interactive_cancel_requested_once(
        active=active,
        runtime_display=runtime_display,
    )


async def _render_interactive_cancel_requested_once(
    *,
    active: _InteractiveActiveTurn,
    runtime_display: RuntimeDisplayController | None,
) -> None:
    """由 interactive outer driver 恰好展示一次取消请求。

    :param active: 当前 active turn。
    :param runtime_display: 可选 display controller。
    :returns: ``None``。
    :raises Exception: display 渲染失败时向上透传。
    """

    if active.cancel_rendered or active.closeout.cancel_reason is None:
        return
    if runtime_display is not None:
        await runtime_display.render_cancel_requested()
    active.cancel_rendered = True


async def _cancel_interactive_run_for_closeout(
    run_id: str,
    reason: str,
    *,
    host: Host,
    invocation: CliInvocation,
    turn_index: int,
) -> EntrypointRunTerminalResult:
    """构造 interactive Host graceful cancel 并等待 canonical terminal。

    :param run_id: acceptance barrier 发布的 exact Run id。
    :param reason: 首次本地取消冻结的 Host reason。
    :param host: Host public handle。
    :param invocation: 当前 CLI invocation identity。
    :param turn_index: 当前 invocation 内稳定 turn index。
    :returns: Host canonical terminal observation。
    :raises Exception: Host cancel 或 terminal observation 失败时向上透传。
    """

    return await cancel_entrypoint_run_and_wait(
        host,
        request=EntrypointCancelRequest(
            context=build_interactive_host_context(
                invocation,
                operation=_INTERACTIVE_OPERATION_CANCEL_RUN,
            ),
            run_id=run_id,
            client_request_id=interactive_cancel_client_request_id(
                invocation,
                turn_index=turn_index,
                run_id=run_id,
            ),
            reason=reason,
            mode=CancelMode.GRACEFUL,
        ),
    )


async def _finish_interactive_terminal(
    *,
    terminal: EntrypointRunTerminalResult,
    workspace_root: Path,
    session_id: str,
    run_view: InteractiveRunView | None,
    runtime_display: RuntimeDisplayController | None,
) -> int:
    """按 render、cursor 的固定顺序收口一个 interactive terminal。

    :param terminal: Host canonical terminal projection。
    :param workspace_root: 当前 workspace 根目录。
    :param session_id: 目标 Session id。
    :param run_view: 可选 interactive run view。
    :param runtime_display: 可选 display controller。
    :returns: frozen interactive terminal exit mapping。
    :raises Exception: display、render 或 cursor 持久化失败时向上透传。
    """

    if runtime_display is not None:
        await runtime_display.finish_runtime_display()
    if run_view is None:
        render_exit_code = render_interactive_terminal_result(terminal)
    elif runtime_display is None:
        raise RuntimeError("interactive run view requires runtime display")
    else:
        render_exit_code = await runtime_display.render_terminal_result(
            run_view.render_terminal_result,
            terminal,
        )
    await advance_cli_terminal_cursor(
        workspace_root=workspace_root,
        session_id=session_id,
        terminal_event_id=terminal.terminal_event_id,
        event_sequence=terminal.event_sequence,
    )
    return render_exit_code


__all__: tuple[str, ...] = (
    "DEFAULT_DISPLAY_USER",
    "PreparedInteractiveSessionExecution",
    "PreparedPromptSessionExecution",
    "execute_interactive_on_session",
    "execute_prompt_on_session",
    "prepare_interactive_session_execution",
    "prepare_prompt_session_execution",
)
