"""``dayu-cli interactive`` 多轮命令实现。

本模块是 CLI UI adapter：负责 REPL 输入、终端展示、HostCallContext /
client_request_id 构造和 SIGINT 到 Host cancel 的转换。Session、turn、
terminal observation 与 cancel 等 Host 语义全部复用 ``dayu.service`` 的
entrypoint runtime helper。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    cancel_and_await_task,
    optional_stripped_text,
    package_config_root,
    resolve_explicit_config_dir,
    resolve_workspace_root,
    service_run_overrides_from_args,
    unsupported_execution_option_names,
)
from dayu.cli.arg_parsing import COMMAND_INTERACTIVE, ParsedCliArgs
from dayu.cli.composer import (
    InputReaderComposer,
    InteractiveComposer,
    new_interactive_composer,
)
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.host_context import (
    CLI_INTERACTIVE_SCENARIO,
    CLI_SIGINT_REASON,
    INTERACTIVE_SESSION_SCOPE,
    CliInvocation,
    build_interactive_host_context,
    interactive_cancel_client_request_id,
    interactive_create_session_client_request_id,
    interactive_slot_key,
    interactive_submit_client_request_id,
    new_cli_invocation,
)
from dayu.cli.output import render_cli_error, render_interactive_terminal_result
from dayu.cli.run_keys import (
    NoopRunningKeyMonitor,
    RunningKeyAction,
    RunningKeyMonitor,
    new_running_key_monitor,
)
from dayu.cli.run_view import InteractiveRunView, new_interactive_run_view
from dayu.cli.session_terminal_cursor import (
    advance_cli_terminal_cursor,
    read_cli_terminal_cursor,
)
from dayu.contracts import JsonValue
from dayu.host.api import CancelMode, FollowupBehavior, Host
from dayu.host.open_host import open_host
from dayu.runtime.location import RuntimeLocationError
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
    ensure_or_create_entrypoint_session,
    prepare_entrypoint_runtime,
    startup_reconnect_entrypoint_session,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides

DEFAULT_FINS_SUBJECT: Final[str] = "未指定具体公司"
DEFAULT_BASE_USER: Final[str] = "本地 CLI 用户"
CONTEXT_SLOT_FINS_DEFAULT_SUBJECT: Final[str] = "fins_default_subject"
CONTEXT_SLOT_BASE_USER: Final[str] = "base_user"
INTERACTIVE_INPUT_PROMPT: Final[str] = "dayu> "
_TICKER_OPTION: Final[str] = "--ticker"
_MODEL_NAME_OPTION: Final[str] = "--model-name"
_LABEL_OPTION: Final[str] = "--label"
_INTERACTIVE_OPERATION_CREATE_SESSION: Final[str] = "create_session"
_INTERACTIVE_OPERATION_STARTUP_RECONNECT: Final[str] = "startup_reconnect"
_INTERACTIVE_OPERATION_SUBMIT_FOLLOWUP: Final[str] = "submit_followup"
_INTERACTIVE_OPERATION_CANCEL_RUN: Final[str] = "cancel_run"
_UNSUPPORTED_OPTION_PREFIX: Final[str] = "unsupported option"


class CliInteractiveUsageError(ValueError):
    """interactive 命令用法错误。"""


@dataclass(frozen=True, slots=True)
class _PreparedInteractiveExistingSessionExecution:
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


class _AcceptedRunState:
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


def run_interactive_command(args: ParsedCliArgs) -> int:
    """执行 ``dayu-cli interactive`` 命令。

    :param args: argparse 已解析的 interactive 命令参数。
    :returns: CLI 退出码。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    try:
        return asyncio.run(
            _run_interactive_command_async(
                args,
            )
        )
    except CliInteractiveUsageError as exc:
        render_cli_error(f"dayu-cli interactive: {exc}")
        return EXIT_USAGE_ERROR
    except RuntimeLocationError as exc:
        render_cli_error(f"dayu-cli interactive: {exc}")
        return EXIT_USAGE_ERROR
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except Exception as exc:
        render_cli_error(f"dayu-cli interactive: {exc}")
        return EXIT_FAILURE


async def _run_interactive_command_async(
    args: ParsedCliArgs,
    *,
    input_reader: Callable[[str], str] | None = None,
    composer: InteractiveComposer | None = None,
) -> int:
    """异步执行 interactive command 主流程。

    :param args: argparse 已解析的 interactive 命令参数。
    :param input_reader: 非 TTY 或测试路径使用的输入函数；``None`` 表示默认输入函数。
    :param composer: 可注入 composer；``None`` 表示按 TTY policy 创建。
    :returns: CLI 退出码。
    :raises CliInteractiveUsageError: 用户输入参数非法时抛出。
    :raises Exception: runtime assembly 或 Host public API 失败时向上抛出。
    """

    prepared = await _prepare_interactive_existing_session_execution(
        args,
        command_name=COMMAND_INTERACTIVE,
        scenario=CLI_INTERACTIVE_SCENARIO,
    )
    async with open_host(prepared.runtime.host_assembly.options) as host:
        session_id = await _ensure_interactive_session(
            host=host,
            args=args,
            invocation=prepared.invocation,
        )
        return await _execute_interactive_on_existing_session(
            host=host,
            prepared=prepared,
            session_id=session_id,
            run_startup_reconnect=args.label is not None,
            input_reader=input_reader,
            composer=composer,
            sigint_monitor_factory=CliSigintMonitor,
        )


async def _prepare_interactive_existing_session_execution(
    args: ParsedCliArgs,
    *,
    command_name: str,
    scenario: str,
) -> _PreparedInteractiveExistingSessionExecution:
    """准备在已有 Session 上运行 interactive REPL 所需的 runtime 与调用身份。

    :param args: argparse 已解析的 interactive 兼容命令参数。
    :param command_name: 当前 CLI command 名称。
    :param scenario: interactive scene id。
    :returns: 已准备的 interactive existing-session 执行输入。
    :raises CliInteractiveUsageError: 用户输入参数非法时抛出。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    _raise_for_unsupported_execution_options(args)
    workspace_root = resolve_workspace_root(
        args.workspace_root,
        error_factory=CliInteractiveUsageError,
    )
    explicit_config_dir = resolve_explicit_config_dir(
        config_dir=args.config_dir,
        workspace_root=workspace_root,
        error_factory=CliInteractiveUsageError,
    )
    ticker = optional_stripped_text(
        args.ticker,
        field_name=_TICKER_OPTION,
        error_factory=CliInteractiveUsageError,
    )
    invocation = new_cli_invocation(
        command_name=command_name,
        scenario=scenario,
        display_user=DEFAULT_BASE_USER,
        ticker=ticker,
    )
    runtime = await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root(),
            explicit_config_dir=explicit_config_dir,
            scene_id=scenario,
            context_slot_values=_interactive_context_slot_values(ticker=ticker),
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=optional_stripped_text(
                    args.model_name,
                    field_name=_MODEL_NAME_OPTION,
                    error_factory=CliInteractiveUsageError,
                )
            ),
            env=os.environ,
        )
    )
    return _PreparedInteractiveExistingSessionExecution(
        runtime=runtime,
        workspace_root=workspace_root,
        invocation=invocation,
        run_overrides=service_run_overrides_from_args(
            args,
            error_factory=CliInteractiveUsageError,
        ),
    )


async def _execute_interactive_on_existing_session(
    *,
    host: Host,
    prepared: _PreparedInteractiveExistingSessionExecution,
    session_id: str,
    input_reader: Callable[[str], str] | None = None,
    composer: InteractiveComposer | None = None,
    sigint_monitor_factory: Callable[[], CliSigintMonitor] | None = None,
    key_monitor_factory: Callable[[], RunningKeyMonitor] | None = None,
    run_view: InteractiveRunView | None = None,
    run_startup_reconnect: bool = True,
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
    :returns: CLI 退出码。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    effective_input_reader = _read_user_input if input_reader is None else input_reader
    effective_composer = new_interactive_composer(input_reader=effective_input_reader) if composer is None else composer
    effective_sigint_monitor_factory = CliSigintMonitor if sigint_monitor_factory is None else sigint_monitor_factory
    effective_key_monitor_factory = new_running_key_monitor if key_monitor_factory is None else key_monitor_factory
    if run_startup_reconnect:
        startup_exit_code = await _run_existing_session_startup_reconnect(
            host=host,
            prepared=prepared,
            session_id=session_id,
        )
        if startup_exit_code != EXIT_SUCCESS:
            return startup_exit_code
    return await _run_interactive_repl(
        host=host,
        runtime=prepared.runtime,
        workspace_root=prepared.workspace_root,
        invocation=prepared.invocation,
        session_id=session_id,
        run_overrides=prepared.run_overrides,
        composer=effective_composer,
        sigint_monitor_factory=effective_sigint_monitor_factory,
        key_monitor_factory=effective_key_monitor_factory,
        run_view=run_view,
    )


async def _run_existing_session_startup_reconnect(
    *,
    host: Host,
    prepared: _PreparedInteractiveExistingSessionExecution,
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
            promotion_poll_interval_seconds=(
                DEFAULT_ENTRYPOINT_STARTUP_PROMOTION_POLL_INTERVAL_SECONDS
            ),
            promotion_max_attempts=ENTRYPOINT_STARTUP_PROMOTION_MAX_ATTEMPTS,
        ),
    )
    for terminal in startup.terminal_results:
        render_exit_code = render_interactive_terminal_result(terminal)
        if render_exit_code != EXIT_SUCCESS:
            return render_exit_code
        await advance_cli_terminal_cursor(
            workspace_root=prepared.workspace_root,
            session_id=session_id,
            terminal_event_id=terminal.terminal_event_id,
            event_sequence=terminal.event_sequence,
        )
    return EXIT_SUCCESS


async def _ensure_interactive_session(
    *,
    host: Host,
    args: ParsedCliArgs,
    invocation: CliInvocation,
) -> str:
    """确保 interactive 命令使用的 Host Session。

    :param host: Host public handle。
    :param args: interactive 命令参数。
    :param invocation: 当前 CLI invocation 身份。
    :returns: Host session id。
    :raises CliInteractiveUsageError: label 为空时抛出。
    :raises Exception: Host public API 失败时向上抛出。
    """

    if args.label is not None:
        try:
            slot_key = interactive_slot_key(args.label)
        except ValueError as exc:
            raise CliInteractiveUsageError(f"{_LABEL_OPTION}: {exc}") from exc
        session = await ensure_or_create_entrypoint_session(
            host,
            create_new=False,
            bind_slot=True,
            scope=INTERACTIVE_SESSION_SCOPE,
            slot_key=slot_key,
            metadata=(),
        )
        return session.session_id
    session = await ensure_or_create_entrypoint_session(
        host,
        create_new=True,
        bind_slot=False,
        scope=None,
        slot_key=None,
        metadata=(),
        create_context=build_interactive_host_context(
            invocation,
            operation=_INTERACTIVE_OPERATION_CREATE_SESSION,
        ),
        create_client_request_id=interactive_create_session_client_request_id(invocation),
    )
    return session.session_id


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
    :param run_view: interactive 运行态 view；``None`` 表示按 TTY policy 创建。
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
    effective_run_view = new_interactive_run_view() if run_view is None else run_view
    idle_interrupt_exit_pending = False
    try:
        while True:
            try:
                user_prompt = await effective_composer.read(INTERACTIVE_INPUT_PROMPT)
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
                run_view=effective_run_view,
                key_monitor=effective_key_monitor_factory(),
            )
            if terminal is None:
                return EXIT_KEYBOARD_INTERRUPT
            render_exit_code = effective_run_view.render_terminal_result(terminal)
            if render_exit_code != EXIT_SUCCESS:
                return render_exit_code
            await advance_cli_terminal_cursor(
                workspace_root=workspace_root,
                session_id=session_id,
                terminal_event_id=terminal.terminal_event_id,
                event_sequence=terminal.event_sequence,
            )
            turn_index += 1
    finally:
        effective_run_view.close()


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
    :param key_monitor: 运行态 TTY 按键 monitor；``None`` 表示 no-op。
    :returns: Host terminal result；第二次 SIGINT 本地退出时返回 ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    accepted_run = _AcceptedRunState()
    view = run_view
    monitor = NoopRunningKeyMonitor() if key_monitor is None else key_monitor
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
            on_activity=None if view is None else view.activity_sink().record_activity,
        )
    )
    sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
    key_task = asyncio.create_task(monitor.wait_next())
    try:
        while True:
            done, _pending = await asyncio.wait(
                (submit_task, sigint_task, key_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if submit_task in done:
                return await submit_task
            if key_task in done:
                action = await key_task
                if action is RunningKeyAction.TOGGLE_ACTIVITY:
                    if view is not None:
                        view.toggle_view()
                    key_task = asyncio.create_task(monitor.wait_next())
                    continue
                return await _cancel_interactive_turn_after_first_sigint(
                    host=host,
                    invocation=invocation,
                    turn_index=turn_index,
                    accepted_run=accepted_run,
                    submit_task=submit_task,
                    sigint_monitor=sigint_monitor,
                    observed_sigint_count=observed_sigint_count,
                    run_view=view,
                )
            first_sigint_count = await sigint_task
            return await _cancel_interactive_turn_after_first_sigint(
                host=host,
                invocation=invocation,
                turn_index=turn_index,
                accepted_run=accepted_run,
                submit_task=submit_task,
                sigint_monitor=sigint_monitor,
                observed_sigint_count=first_sigint_count,
                run_view=view,
            )
    finally:
        monitor.close()
        sigint_monitor.close()
        await cancel_and_await_task(sigint_task)
        await cancel_and_await_task(key_task)


async def _cancel_interactive_turn_after_first_sigint(
    *,
    host: Host,
    invocation: CliInvocation,
    turn_index: int,
    accepted_run: _AcceptedRunState,
    submit_task: asyncio.Task[EntrypointRunTerminalResult],
    sigint_monitor: CliSigintMonitor,
    observed_sigint_count: int,
    run_view: InteractiveRunView | None = None,
) -> EntrypointRunTerminalResult | None:
    """第一次 SIGINT 后等待 run id 并发起 Host cancel。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: 当前交互轮次。
    :param accepted_run: 本轮 accepted Run id 状态。
    :param submit_task: 正在运行的 submit / terminal wait task。
    :param sigint_monitor: 本轮 SIGINT monitor。
    :param observed_sigint_count: 第一次 SIGINT 后的计数。
    :param run_view: 运行态 view；``None`` 表示不输出提示。
    :returns: cancel 后的 terminal result；第二次 SIGINT 本地退出时返回
        ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

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
    if run_view is not None:
        run_view.render_cancel_requested()
    return await _cancel_run_waiting_for_terminal_or_second_sigint(
        host=host,
        invocation=invocation,
        turn_index=turn_index,
        run_id=run_id,
        sigint_monitor=sigint_monitor,
        observed_sigint_count=observed_sigint_count,
        run_view=run_view,
    )


async def _wait_for_run_id_or_local_exit(
    *,
    accepted_run: _AcceptedRunState,
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
    run_view: InteractiveRunView | None = None,
) -> EntrypointRunTerminalResult | None:
    """发起 Host cancel，并在第二次 SIGINT 时本地退出。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: 当前交互轮次。
    :param run_id: 待取消 Run id。
    :param sigint_monitor: 本轮 SIGINT monitor。
    :param observed_sigint_count: 第一次 SIGINT 后的计数。
    :param run_view: 运行态 view；``None`` 表示不输出提示。
    :returns: cancel terminal result；第二次 SIGINT 本地退出时返回 ``None``。
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
        if run_view is not None:
            run_view.render_local_exit_after_cancel()
        cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task
        return None
    finally:
        await cancel_and_await_task(second_sigint_task)


def _raise_for_unsupported_execution_options(args: ParsedCliArgs) -> None:
    """检查当前 S4 不支持的旧执行参数。

    :param args: interactive 命令参数。
    :returns: ``None``。
    :raises CliInteractiveUsageError: 任一 unsupported option 被用户显式使用时抛出。
    """

    unsupported = unsupported_execution_option_names(args)
    if unsupported:
        raise CliInteractiveUsageError(f"{_UNSUPPORTED_OPTION_PREFIX}: {', '.join(unsupported)}")


def _interactive_context_slot_values(*, ticker: str | None) -> dict[str, JsonValue]:
    """构造 interactive scene required context slots。

    :param ticker: 用户显式提供的业务主体；未提供时为 ``None``。
    :returns: 传给 ScenePrepare 的 context slot 值。
    :raises Exception: 不主动抛出异常。
    """

    return {
        CONTEXT_SLOT_FINS_DEFAULT_SUBJECT: (ticker if ticker is not None else DEFAULT_FINS_SUBJECT),
        CONTEXT_SLOT_BASE_USER: DEFAULT_BASE_USER,
    }


def _read_user_input(prompt: str) -> str:
    """读取一行 interactive 用户输入。

    :param prompt: 输入提示文本。
    :returns: 用户输入文本。
    :raises EOFError: 用户输入 Ctrl-D 时由 ``input`` 抛出。
    :raises KeyboardInterrupt: 输入态 Ctrl-C 时由 ``input`` 抛出。
    """

    return input(prompt)


__all__: tuple[str, ...] = (
    "CliInteractiveUsageError",
    "run_interactive_command",
)
