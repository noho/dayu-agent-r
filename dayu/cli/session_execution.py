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
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Never

from dayu.cli.activity import CliActivityRenderer, CliActivityRendererOptions
from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    cancel_and_await_task,
    optional_stripped_text,
    package_config_root,
    resolve_explicit_config_dir,
    resolve_workspace_root,
    service_run_overrides_from_args,
)
from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.cli.composer import (
    InputReaderComposer,
    InteractiveComposer,
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
_MODEL_NAME_OPTION: Final[str] = "--model-name"
_PROMPT_OPERATION_SUBMIT_FOLLOWUP: Final[str] = "submit_followup"
_PROMPT_OPERATION_CANCEL_RUN: Final[str] = "cancel_run"
_INTERACTIVE_OPERATION_STARTUP_RECONNECT: Final[str] = "startup_reconnect"
_INTERACTIVE_OPERATION_SUBMIT_FOLLOWUP: Final[str] = "submit_followup"
_INTERACTIVE_OPERATION_CANCEL_RUN: Final[str] = "cancel_run"


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
    """

    runtime: EntrypointRuntimeResult
    workspace_root: Path
    invocation: CliInvocation
    run_overrides: ServiceRunOverrides


class _PromptAcceptedRunState:
    """prompt submit 后当前 accepted Run id 的本地状态。"""

    run_id: str | None

    def __init__(self) -> None:
        """初始化 accepted Run 状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.run_id = None

    def record(self, run_id: str) -> None:
        """记录 Host 已接受的 Run id。

        :param run_id: Host accepted_run_id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.run_id = run_id


class _InteractiveAcceptedRunState:
    """interactive 单轮 submit 后 accepted Run id 的本地状态。"""

    run_id: str | None
    _event: asyncio.Event

    def __init__(self) -> None:
        """初始化 accepted Run 状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.run_id = None
        self._event = asyncio.Event()

    def record(self, run_id: str) -> None:
        """记录 Host 已接受的 Run id。

        :param run_id: Host accepted_run_id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.run_id = run_id
        self._event.set()

    async def wait_run_id(self) -> str:
        """等待并返回 accepted Run id。

        :returns: Host accepted_run_id。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        :raises RuntimeError: 状态事件触发但 run id 缺失时抛出。
        """

        await self._event.wait()
        if self.run_id is None:
            raise RuntimeError("accepted run id missing")
        return self.run_id


@dataclass(frozen=True, slots=True)
class _RunIdAccepted:
    """第一次 SIGINT 后已取得 accepted Run id。"""

    run_id: str


@dataclass(frozen=True, slots=True)
class _SubmitCompletedWhileWaitingForRunId:
    """等待 run id 期间 submit / terminal wait task 已先完成。"""

    terminal: EntrypointRunTerminalResult


@dataclass(frozen=True, slots=True)
class _LocalExitRequested:
    """等待 run id 期间用户第二次 SIGINT 请求本地退出。"""


_RunIdWaitOutcome = _RunIdAccepted | _SubmitCompletedWhileWaitingForRunId | _LocalExitRequested
_UsageErrorFactory = Callable[[str], ValueError]


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
    explicit_config_dir = resolve_explicit_config_dir(
        config_dir=args.config_dir,
        workspace_root=workspace_root,
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
        explicit_config_dir=explicit_config_dir,
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
    ticker: str | None,
    context_slot_values: dict[str, JsonValue],
    usage_error_factory: _UsageErrorFactory,
) -> PreparedInteractiveSessionExecution:
    """准备在已有 Session 上运行 interactive REPL 所需的 runtime 与调用身份。

    :param args: argparse 已解析的 interactive 兼容命令参数。
    :param command_name: 当前 CLI command 名称。
    :param scenario: interactive scene id。
    :param ticker: 调用方已校验的业务主体；未提供时为 ``None``。
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
    explicit_config_dir = resolve_explicit_config_dir(
        config_dir=args.config_dir,
        workspace_root=workspace_root,
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
        explicit_config_dir=explicit_config_dir,
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

    terminal = await _submit_prompt_turn_handling_sigint(
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
    if terminal is None:
        return EXIT_KEYBOARD_INTERRUPT
    render_exit_code = render_prompt_terminal_result(terminal)
    await advance_cli_terminal_cursor(
        workspace_root=prepared.workspace_root,
        session_id=session_id,
        terminal_event_id=terminal.terminal_event_id,
        event_sequence=terminal.event_sequence,
    )
    return render_exit_code


async def execute_interactive_on_session(
    *,
    host: Host,
    prepared: PreparedInteractiveSessionExecution,
    session_id: str,
    input_reader: Callable[[str], str] | None = None,
    composer: InteractiveComposer | None = None,
    sigint_monitor_factory: Callable[[], CliSigintMonitor] | None = None,
    key_monitor_factory: Callable[[], RunningKeyMonitor] | None = None,
    run_view: InteractiveRunView | None = None,
    run_startup_reconnect: bool = True,
    detail: bool = True,
    thinking: bool = True,
) -> int:
    """在已解析的已有 Session 上运行 interactive REPL。

    :param host: Host public handle。
    :param prepared: interactive existing-session 执行准备结果。
    :param session_id: 已存在且调用方已选择的 Host Session id。
    :param input_reader: 输入态读取一行用户文本的函数；``None`` 表示使用标准输入。
    :param composer: 输入态 composer；``None`` 表示按 TTY policy 创建。
    :param sigint_monitor_factory: 单轮 SIGINT monitor 工厂；``None`` 表示创建默认 monitor。
    :param key_monitor_factory: 单轮运行态按键 monitor 工厂；``None`` 表示默认 TTY policy。
    :param run_view: interactive 运行态 view；``None`` 表示按 TTY policy 创建。
    :param run_startup_reconnect: 是否在输入态前执行已有 Session startup reconnect。
    :param detail: 是否显示运行态 activity stream。
    :param thinking: 是否显示运行态 thinking 增量。
    :returns: CLI 退出码。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    effective_input_reader = _read_user_input if input_reader is None else input_reader
    effective_composer = new_interactive_composer(input_reader=effective_input_reader) if composer is None else composer
    effective_sigint_monitor_factory = CliSigintMonitor if sigint_monitor_factory is None else sigint_monitor_factory
    effective_key_monitor_factory = new_running_key_monitor if key_monitor_factory is None else key_monitor_factory
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
    try:
        if runtime_display is not None:
            await runtime_display.install_runtime_line_guard()
        if run_startup_reconnect:
            startup_exit_code = await _run_existing_session_startup_reconnect(
                host=host,
                prepared=prepared,
                session_id=session_id,
            )
            if startup_exit_code != EXIT_SUCCESS:
                exit_code = startup_exit_code
            else:
                exit_code = await _run_interactive_repl(
                    host=host,
                    runtime=prepared.runtime,
                    workspace_root=prepared.workspace_root,
                    invocation=prepared.invocation,
                    session_id=session_id,
                    run_overrides=prepared.run_overrides,
                    composer=effective_composer,
                    sigint_monitor_factory=effective_sigint_monitor_factory,
                    key_monitor_factory=effective_key_monitor_factory,
                    run_view=effective_run_view if detail else None,
                    thinking_renderer=effective_thinking_renderer,
                    runtime_display=runtime_display,
                )
        else:
            exit_code = await _run_interactive_repl(
                host=host,
                runtime=prepared.runtime,
                workspace_root=prepared.workspace_root,
                invocation=prepared.invocation,
                session_id=session_id,
                run_overrides=prepared.run_overrides,
                composer=effective_composer,
                sigint_monitor_factory=effective_sigint_monitor_factory,
                key_monitor_factory=effective_key_monitor_factory,
                run_view=effective_run_view if detail else None,
                thinking_renderer=effective_thinking_renderer,
                runtime_display=runtime_display,
            )
    except BaseException as error:
        primary_error = error
    cleanup_error = await _close_runtime_display(runtime_display)
    if primary_error is not None:
        _raise_lifecycle_primary(primary_error, cleanup_error)
    if cleanup_error is not None:
        raise cleanup_error
    return exit_code


async def _prepare_session_runtime(
    *,
    args: ParsedCliArgs,
    workspace_root: Path,
    explicit_config_dir: Path | None,
    scenario: str,
    context_slot_values: dict[str, JsonValue],
    usage_error_factory: _UsageErrorFactory,
) -> EntrypointRuntimeResult:
    """准备 existing-session 执行所需的 Service entrypoint runtime。

    :param args: argparse 已解析的兼容命令参数。
    :param workspace_root: 已解析 workspace 根目录。
    :param explicit_config_dir: 显式配置目录；未提供时为 ``None``。
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
            explicit_config_dir=explicit_config_dir,
            scene_id=scenario,
            context_slot_values=context_slot_values,
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=optional_stripped_text(
                    args.model_name,
                    field_name=_MODEL_NAME_OPTION,
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


async def _close_interactive_turn_lifecycle(
    *,
    close_runtime_display: bool,
    runtime_display: RuntimeDisplayController | None,
    monitor: RunningKeyMonitor,
    sigint_monitor: CliSigintMonitor,
    submit_task: asyncio.Task[EntrypointRunTerminalResult] | None,
    sigint_task: asyncio.Task[int] | None,
    key_task: asyncio.Task[RunningKeyAction] | None,
) -> BaseException | None:
    """关闭 interactive failure display 与单轮 caller-local resource。

    :param close_runtime_display: 当前 turn failure 是否结束整个 display lifecycle。
    :param runtime_display: interactive invocation display controller。
    :param monitor: 单轮按键 monitor。
    :param sigint_monitor: 单轮 SIGINT monitor。
    :param submit_task: 可选 Service submit/observation task。
    :param sigint_task: 可选 SIGINT wait task。
    :param key_task: 可选按键 wait task。
    :returns: 首个 cleanup failure；全部成功时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    cleanup_error: BaseException | None = None
    if close_runtime_display and runtime_display is not None:
        runtime_display.begin_closing()
    if submit_task is not None and not submit_task.done():
        try:
            await cancel_and_await_task(submit_task)
        except BaseException as error:
            cleanup_error = error
    if close_runtime_display:
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
) -> EntrypointRunTerminalResult | None:
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
    :returns: Host terminal result；Run accepted 前 SIGINT 返回 ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    accepted_run = _PromptAcceptedRunState()
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
                on_run_accepted=accepted_run.record,
                on_activity=None if renderer is None else renderer.record,
                on_thinking=None if thinking is None else thinking.record,
                callback_execution_port=runtime_display,
            )
        )
        sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
        key_task = asyncio.create_task(monitor.wait_next())
        while True:
            done, _pending = await asyncio.wait(
                (submit_task, sigint_task, key_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if submit_task in done:
                terminal_result = await submit_task
                if runtime_display is not None:
                    await runtime_display.finish_runtime_display()
                break
            if key_task in done:
                action = await key_task
                if action is RunningKeyAction.TOGGLE_ACTIVITY:
                    if runtime_display is not None:
                        await runtime_display.toggle_activity_display()
                    key_task = asyncio.create_task(monitor.wait_next())
                    continue
                terminal_result = await _cancel_prompt_turn_after_local_request(
                    host=host,
                    invocation=invocation,
                    accepted_run=accepted_run,
                    submit_task=submit_task,
                    sigint_monitor=sigint_monitor,
                    observed_sigint_count=observed_sigint_count,
                    runtime_display=runtime_display,
                )
                break
            first_sigint_count = await sigint_task
            terminal_result = await _cancel_prompt_turn_after_local_request(
                host=host,
                invocation=invocation,
                accepted_run=accepted_run,
                submit_task=submit_task,
                sigint_monitor=sigint_monitor,
                observed_sigint_count=first_sigint_count,
                runtime_display=runtime_display,
            )
            break
    except BaseException as error:
        primary_error = error
    cleanup_error = await _close_prompt_lifecycle(
        runtime_display=runtime_display,
        monitor=monitor,
        sigint_monitor=sigint_monitor,
        submit_task=submit_task,
        sigint_task=sigint_task,
        key_task=key_task,
    )
    if primary_error is not None:
        _raise_lifecycle_primary(primary_error, cleanup_error)
    if cleanup_error is not None:
        raise cleanup_error
    return terminal_result


async def _cancel_prompt_turn_after_local_request(
    *,
    host: Host,
    invocation: CliInvocation,
    accepted_run: _PromptAcceptedRunState,
    submit_task: asyncio.Task[EntrypointRunTerminalResult],
    sigint_monitor: CliSigintMonitor,
    observed_sigint_count: int,
    runtime_display: RuntimeDisplayController | None,
) -> EntrypointRunTerminalResult | None:
    """本地取消请求后取消 prompt turn 并等待 Host terminal 或二次 SIGINT。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param accepted_run: 本轮 accepted Run id 状态。
    :param submit_task: 正在运行的 submit / terminal wait task。
    :param sigint_monitor: prompt 运行阶段 SIGINT monitor。
    :param observed_sigint_count: 第一次取消请求后的 SIGINT 计数；Esc 取消
        时传入进入运行态前的计数，避免 Esc 被当作 Ctrl+C 次数。
    :param runtime_display: 运行态展示 controller。
    :returns: cancel 后 terminal result；Run accepted 前或二次 SIGINT 时返回
        ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    if runtime_display is not None:
        await runtime_display.finish_thinking_display()
    if submit_task.done():
        return await submit_task
    submit_task.cancel()
    with suppress(asyncio.CancelledError):
        await submit_task
    if accepted_run.run_id is None:
        return None
    if runtime_display is not None:
        await runtime_display.render_cancel_requested()
    return await _cancel_prompt_run_waiting_for_terminal_or_second_sigint(
        host=host,
        invocation=invocation,
        run_id=accepted_run.run_id,
        sigint_monitor=sigint_monitor,
        observed_sigint_count=observed_sigint_count,
        runtime_display=runtime_display,
    )


async def _cancel_prompt_run_waiting_for_terminal_or_second_sigint(
    *,
    host: Host,
    invocation: CliInvocation,
    run_id: str,
    sigint_monitor: CliSigintMonitor,
    observed_sigint_count: int,
    runtime_display: RuntimeDisplayController | None,
) -> EntrypointRunTerminalResult | None:
    """发起 prompt Host cancel，并在二次 SIGINT 时本地退出。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param run_id: 待取消 Run id。
    :param sigint_monitor: prompt 运行阶段 SIGINT monitor。
    :param observed_sigint_count: 第一次取消请求后的 SIGINT 计数。
    :param runtime_display: 运行态展示 controller。
    :returns: cancel terminal result；二次 SIGINT 先到时返回 ``None``。
    :raises Exception: cancel 或 terminal observation 失败时向上抛出。
    """

    cancel_task = asyncio.create_task(
        cancel_entrypoint_run_and_wait(
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
                reason=CLI_SIGINT_REASON,
                mode=CancelMode.GRACEFUL,
            ),
        )
    )
    second_sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
    try:
        done, _pending = await asyncio.wait(
            (cancel_task, second_sigint_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done:
            return await cancel_task
        if runtime_display is not None:
            await runtime_display.render_local_exit_after_cancel()
        cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task
        return None
    finally:
        await cancel_and_await_task(second_sigint_task)


async def _run_interactive_repl(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    workspace_root: Path,
    invocation: CliInvocation,
    session_id: str,
    run_overrides: ServiceRunOverrides,
    sigint_monitor_factory: Callable[[], CliSigintMonitor],
    key_monitor_factory: Callable[[], RunningKeyMonitor] | None = None,
    run_view: InteractiveRunView | None = None,
    thinking_renderer: CliThinkingRenderer | None = None,
    runtime_display: RuntimeDisplayController | None = None,
    composer: InteractiveComposer | None = None,
    input_reader: Callable[[str], str] | None = None,
) -> int:
    """运行 interactive REPL。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param workspace_root: 当前 workspace 根目录。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Host Session id。
    :param run_overrides: 本命令所有 turn 复用的运行时 override。
    :param sigint_monitor_factory: 单轮 SIGINT monitor 工厂。
    :param key_monitor_factory: 单轮运行态按键 monitor 工厂；``None`` 表示默认 TTY policy。
    :param run_view: interactive 运行态 view；``None`` 表示不输出 activity。
    :param thinking_renderer: invocation 级 thinking renderer；``None`` 表示不输出。
    :param runtime_display: invocation 级私有 display execution domain。
    :param composer: 输入态 composer；``None`` 时使用 input reader adapter。
    :param input_reader: 旧式输入函数；仅在 ``composer`` 为 ``None`` 时使用。
    :returns: CLI 退出码。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    turn_index = 1
    effective_composer = (
        composer
        if composer is not None
        else InputReaderComposer(_read_user_input if input_reader is None else input_reader)
    )
    effective_key_monitor_factory = new_running_key_monitor if key_monitor_factory is None else key_monitor_factory
    idle_interrupt_exit_pending = False
    while True:
        try:
            user_prompt = await effective_composer.read("dayu> ")
        except EOFError:
            idle_interrupt_exit_pending = False
            return EXIT_SUCCESS
        except KeyboardInterrupt:
            if idle_interrupt_exit_pending:
                return EXIT_KEYBOARD_INTERRUPT
            idle_interrupt_exit_pending = True
            continue
        idle_interrupt_exit_pending = False
        stripped_prompt = user_prompt.strip()
        if stripped_prompt == "":
            continue
        terminal = await _submit_interactive_turn_handling_sigint(
            host=host,
            runtime=runtime,
            invocation=invocation,
            session_id=session_id,
            turn_index=turn_index,
            user_prompt=stripped_prompt,
            run_overrides=run_overrides,
            sigint_monitor=sigint_monitor_factory(),
            run_view=run_view,
            thinking_renderer=thinking_renderer,
            runtime_display=runtime_display,
            key_monitor=effective_key_monitor_factory(),
        )
        if terminal is None:
            return EXIT_KEYBOARD_INTERRUPT
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
        if render_exit_code != EXIT_SUCCESS:
            return render_exit_code
        turn_index += 1


async def _submit_interactive_turn_handling_sigint(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    invocation: CliInvocation,
    session_id: str,
    turn_index: int,
    user_prompt: str,
    run_overrides: ServiceRunOverrides,
    sigint_monitor: CliSigintMonitor,
    run_view: InteractiveRunView | None = None,
    thinking_renderer: CliThinkingRenderer | None = None,
    runtime_display: RuntimeDisplayController | None = None,
    key_monitor: RunningKeyMonitor | None = None,
) -> EntrypointRunTerminalResult | None:
    """提交 interactive turn，并在 SIGINT 时按 Host cancel 语义收口。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Host Session id。
    :param turn_index: 当前交互轮次，从 1 开始。
    :param user_prompt: 本轮用户输入。
    :param run_overrides: 本轮可映射执行 override。
    :param sigint_monitor: 本轮运行阶段 SIGINT monitor。
    :param run_view: 运行态 view；``None`` 表示不输出 activity。
    :param thinking_renderer: invocation 级 thinking renderer；``None`` 表示不输出。
    :param runtime_display: interactive invocation 私有 display execution domain。
    :param key_monitor: 运行态 TTY 按键 monitor；``None`` 表示 no-op。
    :returns: Host terminal result；第二次 SIGINT 本地退出时返回 ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    accepted_run = _InteractiveAcceptedRunState()
    view = run_view
    monitor = NoopRunningKeyMonitor() if key_monitor is None else key_monitor
    submit_task: asyncio.Task[EntrypointRunTerminalResult] | None = None
    sigint_task: asyncio.Task[int] | None = None
    key_task: asyncio.Task[RunningKeyAction] | None = None
    primary_error: BaseException | None = None
    terminal_result: EntrypointRunTerminalResult | None = None
    try:
        sigint_monitor.install()
        observed_sigint_count = sigint_monitor.count
        monitor.start()
        submit_task = asyncio.create_task(
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
                on_run_accepted=accepted_run.record,
                on_activity=(None if view is None else view.activity_sink().record_activity),
                on_thinking=(None if thinking_renderer is None else thinking_renderer.record),
                callback_execution_port=runtime_display,
            )
        )
        sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
        key_task = asyncio.create_task(monitor.wait_next())
        while True:
            done, _pending = await asyncio.wait(
                (submit_task, sigint_task, key_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if submit_task in done:
                terminal_result = await submit_task
                if runtime_display is not None:
                    await runtime_display.finish_runtime_display()
                break
            if key_task in done:
                action = await key_task
                if action is RunningKeyAction.TOGGLE_ACTIVITY:
                    if runtime_display is not None:
                        await runtime_display.toggle_activity_display()
                    key_task = asyncio.create_task(monitor.wait_next())
                    continue
                terminal_result = await _cancel_interactive_turn_after_first_sigint(
                    host=host,
                    invocation=invocation,
                    turn_index=turn_index,
                    accepted_run=accepted_run,
                    submit_task=submit_task,
                    sigint_monitor=sigint_monitor,
                    observed_sigint_count=observed_sigint_count,
                    runtime_display=runtime_display,
                )
                break
            first_sigint_count = await sigint_task
            terminal_result = await _cancel_interactive_turn_after_first_sigint(
                host=host,
                invocation=invocation,
                turn_index=turn_index,
                accepted_run=accepted_run,
                submit_task=submit_task,
                sigint_monitor=sigint_monitor,
                observed_sigint_count=first_sigint_count,
                runtime_display=runtime_display,
            )
            break
    except BaseException as error:
        primary_error = error
    cleanup_error = await _close_interactive_turn_lifecycle(
        close_runtime_display=primary_error is not None,
        runtime_display=runtime_display,
        monitor=monitor,
        sigint_monitor=sigint_monitor,
        submit_task=submit_task,
        sigint_task=sigint_task,
        key_task=key_task,
    )
    if primary_error is not None:
        _raise_lifecycle_primary(primary_error, cleanup_error)
    if cleanup_error is not None:
        raise cleanup_error
    return terminal_result


async def _cancel_interactive_turn_after_first_sigint(
    *,
    host: Host,
    invocation: CliInvocation,
    turn_index: int,
    accepted_run: _InteractiveAcceptedRunState,
    submit_task: asyncio.Task[EntrypointRunTerminalResult],
    sigint_monitor: CliSigintMonitor,
    observed_sigint_count: int,
    runtime_display: RuntimeDisplayController | None,
) -> EntrypointRunTerminalResult | None:
    """第一次 SIGINT 后等待 run id 并发起 Host cancel。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: 当前交互轮次。
    :param accepted_run: 本轮 accepted Run id 状态。
    :param submit_task: 正在运行的 submit / terminal wait task。
    :param sigint_monitor: 本轮 SIGINT monitor。
    :param observed_sigint_count: 第一次 SIGINT 后的计数。
    :param runtime_display: 运行态展示 controller。
    :returns: cancel 后的 terminal result；第二次 SIGINT 本地退出时返回
        ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    if runtime_display is not None:
        await runtime_display.finish_thinking_display()
    run_id = accepted_run.run_id
    if run_id is None:
        wait_outcome = await _wait_for_run_id_or_local_exit(
            accepted_run=accepted_run,
            submit_task=submit_task,
            sigint_monitor=sigint_monitor,
            observed_sigint_count=observed_sigint_count,
        )
        if isinstance(wait_outcome, _SubmitCompletedWhileWaitingForRunId):
            return wait_outcome.terminal
        if isinstance(wait_outcome, _LocalExitRequested):
            return None
        run_id = wait_outcome.run_id
    if submit_task.done():
        return await submit_task
    submit_task.cancel()
    with suppress(asyncio.CancelledError):
        await submit_task
    if runtime_display is not None:
        await runtime_display.render_cancel_requested()
    return await _cancel_run_waiting_for_terminal_or_second_sigint(
        host=host,
        invocation=invocation,
        turn_index=turn_index,
        run_id=run_id,
        sigint_monitor=sigint_monitor,
        observed_sigint_count=observed_sigint_count,
        runtime_display=runtime_display,
    )


async def _wait_for_run_id_or_local_exit(
    *,
    accepted_run: _InteractiveAcceptedRunState,
    submit_task: asyncio.Task[EntrypointRunTerminalResult],
    sigint_monitor: CliSigintMonitor,
    observed_sigint_count: int,
) -> _RunIdWaitOutcome:
    """第一次 SIGINT 早于 run id 时等待 run id 或第二次 SIGINT。

    :param accepted_run: 本轮 accepted Run id 状态。
    :param submit_task: 正在运行的 submit / terminal wait task。
    :param sigint_monitor: 本轮 SIGINT monitor。
    :param observed_sigint_count: 第一次 SIGINT 后的计数。
    :returns: typed outcome，区分 accepted Run id、submit 已完成和本地退出。
    :raises Exception: submit task 已失败时通过 ``await submit_task`` 向上透传异常。
    """

    run_id_task = asyncio.create_task(accepted_run.wait_run_id())
    second_sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
    try:
        done, _pending = await asyncio.wait(
            (submit_task, run_id_task, second_sigint_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if submit_task in done:
            return _SubmitCompletedWhileWaitingForRunId(terminal=await submit_task)
        if second_sigint_task in done:
            submit_task.cancel()
            with suppress(asyncio.CancelledError):
                await submit_task
            return _LocalExitRequested()
        return _RunIdAccepted(run_id=await run_id_task)
    finally:
        await cancel_and_await_task(run_id_task)
        await cancel_and_await_task(second_sigint_task)


async def _cancel_run_waiting_for_terminal_or_second_sigint(
    *,
    host: Host,
    invocation: CliInvocation,
    turn_index: int,
    run_id: str,
    sigint_monitor: CliSigintMonitor,
    observed_sigint_count: int,
    runtime_display: RuntimeDisplayController | None,
) -> EntrypointRunTerminalResult | None:
    """发起 Host cancel，并在第二次 SIGINT 时本地退出。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: 当前交互轮次。
    :param run_id: 待取消 Run id。
    :param sigint_monitor: 本轮 SIGINT monitor。
    :param observed_sigint_count: 第一次 SIGINT 后的计数。
    :param runtime_display: 运行态展示 controller。
    :returns: cancel terminal result；第二次 SIGINT 先到时返回 ``None``。
    :raises Exception: cancel 或 terminal observation 失败时向上抛出。
    """

    cancel_task = asyncio.create_task(
        cancel_entrypoint_run_and_wait(
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
                reason=CLI_SIGINT_REASON,
                mode=CancelMode.GRACEFUL,
            ),
        )
    )
    second_sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
    try:
        done, _pending = await asyncio.wait(
            (cancel_task, second_sigint_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done:
            return await cancel_task
        if runtime_display is not None:
            await runtime_display.render_local_exit_after_cancel()
        cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task
        return None
    finally:
        await cancel_and_await_task(second_sigint_task)


def _read_user_input(prompt: str) -> str:
    """读取一行 interactive 用户输入。

    :param prompt: 输入提示文本。
    :returns: 用户输入文本。
    :raises EOFError: 用户输入 Ctrl-D 时由 ``input`` 抛出。
    :raises KeyboardInterrupt: 输入态 Ctrl-C 时由 ``input`` 抛出。
    """

    return input(prompt)


__all__: tuple[str, ...] = (
    "DEFAULT_DISPLAY_USER",
    "PreparedInteractiveSessionExecution",
    "PreparedPromptSessionExecution",
    "execute_interactive_on_session",
    "execute_prompt_on_session",
    "prepare_interactive_session_execution",
    "prepare_prompt_session_execution",
)
