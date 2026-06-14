"""``dayu-cli interactive`` 多轮命令实现。

本模块是 CLI UI adapter：负责 REPL 输入、终端展示、HostCallContext /
client_request_id 构造和 SIGINT 到 Host cancel 的转换。Session、turn、
terminal observation 与 cancel 等 Host 语义全部复用 ``dayu.service`` 的
entrypoint runtime helper。
"""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Final, TypeVar

from dayu.cli.arg_parsing import COMMAND_INTERACTIVE, ParsedCliArgs
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
    interactive_process_slot_key,
    interactive_slot_key,
    interactive_submit_client_request_id,
    new_cli_invocation,
)
from dayu.cli.output import render_cli_error, render_interactive_terminal_result
from dayu.contracts import JsonValue
from dayu.host.api import CancelMode, FollowupBehavior, Host
from dayu.host.open_host import open_host
from dayu.runtime.location import RuntimeLocationError
from dayu.service.entrypoint_runtime import (
    EntrypointCancelRequest,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointRunTerminalResult,
    EntrypointTurnRequest,
    cancel_entrypoint_run_and_wait,
    ensure_or_create_entrypoint_session,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides

DEFAULT_FINS_SUBJECT: Final[str] = "未指定具体公司"
DEFAULT_BASE_USER: Final[str] = "本地 CLI 用户"
CONTEXT_SLOT_FINS_DEFAULT_SUBJECT: Final[str] = "fins_default_subject"
CONTEXT_SLOT_BASE_USER: Final[str] = "base_user"
INTERACTIVE_INPUT_PROMPT: Final[str] = "dayu> "
_BASE_OPTION: Final[str] = "--base"
_CONFIG_DIR_OPTION: Final[str] = "--config"
_TICKER_OPTION: Final[str] = "--ticker"
_MODEL_NAME_OPTION: Final[str] = "--model-name"
_LABEL_OPTION: Final[str] = "--label"
_FALLBACK_MODE_OPTION: Final[str] = "--fallback-mode"
_FALLBACK_PROMPT_OPTION: Final[str] = "--fallback-prompt"
_INTERACTIVE_OPERATION_CREATE_SESSION: Final[str] = "create_session"
_INTERACTIVE_OPERATION_SUBMIT_FOLLOWUP: Final[str] = "submit_followup"
_INTERACTIVE_OPERATION_CANCEL_RUN: Final[str] = "cancel_run"
_UNSUPPORTED_OPTION_PREFIX: Final[str] = "unsupported option"
_TaskResult = TypeVar("_TaskResult")


class CliInteractiveUsageError(ValueError):
    """interactive 命令用法错误。"""


class _InteractiveSigintMonitor:
    """interactive 运行阶段的 SIGINT 观察器。

    观察器只在单轮 Run pending / running 阶段安装事件循环 signal handler。
    输入态 Ctrl-C 仍沿用 Python 默认 ``KeyboardInterrupt`` 语义。
    """

    count: int
    _event: asyncio.Event
    _loop: asyncio.AbstractEventLoop | None
    _installed: bool

    def __init__(self) -> None:
        """初始化 SIGINT monitor。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.count = 0
        self._event = asyncio.Event()
        self._loop = None
        self._installed = False

    def install(self) -> None:
        """在当前事件循环安装 SIGINT handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常；不支持 loop signal handler 时保留
            默认 ``KeyboardInterrupt`` 行为。
        """

        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, self.notify)
        except (NotImplementedError, RuntimeError):
            self._installed = False
            self._loop = None
            return
        self._installed = True
        self._loop = loop

    def close(self) -> None:
        """移除当前 monitor 安装的 SIGINT handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._installed and self._loop is not None:
            self._loop.remove_signal_handler(signal.SIGINT)
        self._installed = False
        self._loop = None

    def notify(
        self,
        _signal_number: int | None = None,
        _frame: FrameType | None = None,
    ) -> None:
        """记录一次 SIGINT。

        :param _signal_number: ``signal.signal`` 风格 handler 兼容参数。
        :param _frame: ``signal.signal`` 风格 handler 兼容参数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.count += 1
        self._event.set()

    async def wait_next(self, observed_count: int) -> int:
        """等待下一次 SIGINT。

        :param observed_count: 调用方已经观察到的 SIGINT 计数。
        :returns: 新的 SIGINT 计数。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        while self.count <= observed_count:
            await self._event.wait()
            self._event.clear()
        return self.count


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


_RunIdWaitOutcome = (
    _RunIdAccepted | _SubmitCompletedWhileWaitingForRunId | _LocalExitRequested
)


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
                input_reader=_read_user_input,
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
    input_reader: Callable[[str], str],
) -> int:
    """异步执行 interactive command 主流程。

    :param args: argparse 已解析的 interactive 命令参数。
    :param input_reader: 输入态读取一行用户文本的函数。
    :returns: CLI 退出码。
    :raises CliInteractiveUsageError: 用户输入参数非法时抛出。
    :raises Exception: runtime assembly 或 Host public API 失败时向上抛出。
    """

    _raise_for_unsupported_execution_options(args)
    workspace_root = _resolve_workspace_root(args.workspace_root)
    explicit_config_dir = _resolve_explicit_config_dir(
        config_dir=args.config_dir,
        workspace_root=workspace_root,
    )
    ticker = _optional_stripped_text(args.ticker, field_name=_TICKER_OPTION)
    invocation = new_cli_invocation(
        command_name=COMMAND_INTERACTIVE,
        scenario=CLI_INTERACTIVE_SCENARIO,
        display_user=DEFAULT_BASE_USER,
        ticker=ticker,
    )
    runtime = await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=_package_config_root(),
            explicit_config_dir=explicit_config_dir,
            scene_id=CLI_INTERACTIVE_SCENARIO,
            context_slot_values=_interactive_context_slot_values(ticker=ticker),
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=_optional_stripped_text(
                    args.model_name,
                    field_name=_MODEL_NAME_OPTION,
                )
            ),
            env=os.environ,
        )
    )
    async with open_host(runtime.host_assembly.options) as host:
        session_id = await _ensure_interactive_session(
            host=host,
            args=args,
            invocation=invocation,
        )
        return await _run_interactive_repl(
            host=host,
            runtime=runtime,
            invocation=invocation,
            session_id=session_id,
            run_overrides=_service_run_overrides_from_args(args),
            input_reader=input_reader,
            sigint_monitor_factory=_InteractiveSigintMonitor,
        )


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
    if args.new_session:
        session = await ensure_or_create_entrypoint_session(
            host,
            create_new=True,
            bind_slot=True,
            scope=INTERACTIVE_SESSION_SCOPE,
            slot_key=interactive_process_slot_key(invocation),
            metadata=(),
            create_context=build_interactive_host_context(
                invocation,
                operation=_INTERACTIVE_OPERATION_CREATE_SESSION,
            ),
            create_client_request_id=interactive_create_session_client_request_id(
                invocation
            ),
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
        create_client_request_id=interactive_create_session_client_request_id(
            invocation
        ),
    )
    return session.session_id


async def _run_interactive_repl(
    *,
    host: Host,
    runtime: EntrypointRuntimeResult,
    invocation: CliInvocation,
    session_id: str,
    run_overrides: ServiceRunOverrides,
    input_reader: Callable[[str], str],
    sigint_monitor_factory: Callable[[], _InteractiveSigintMonitor],
) -> int:
    """运行 interactive REPL。

    :param host: Host public handle。
    :param runtime: entrypoint runtime assembly 结果。
    :param invocation: 当前 CLI invocation 身份。
    :param session_id: 目标 Host Session id。
    :param run_overrides: 本命令所有 turn 复用的运行时 override。
    :param input_reader: 输入态读取一行用户文本的函数。
    :param sigint_monitor_factory: 单轮 SIGINT monitor 工厂。
    :returns: CLI 退出码。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    turn_index = 1
    while True:
        try:
            user_prompt = input_reader(INTERACTIVE_INPUT_PROMPT)
        except EOFError:
            return EXIT_SUCCESS
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
        )
        if terminal is None:
            return EXIT_KEYBOARD_INTERRUPT
        render_exit_code = render_interactive_terminal_result(terminal)
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
    sigint_monitor: _InteractiveSigintMonitor,
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
    :returns: Host terminal result；第二次 SIGINT 本地退出时返回 ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    accepted_run = _AcceptedRunState()
    sigint_monitor.install()
    observed_sigint_count = sigint_monitor.count
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
        )
    )
    sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))
    try:
        done, _pending = await asyncio.wait(
            (submit_task, sigint_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if submit_task in done:
            return await submit_task
        first_sigint_count = await sigint_task
        return await _cancel_interactive_turn_after_first_sigint(
            host=host,
            invocation=invocation,
            turn_index=turn_index,
            accepted_run=accepted_run,
            submit_task=submit_task,
            sigint_monitor=sigint_monitor,
            observed_sigint_count=first_sigint_count,
        )
    finally:
        sigint_monitor.close()
        await _cancel_and_await_task(sigint_task)


async def _cancel_and_await_task(task: asyncio.Task[_TaskResult]) -> None:
    """取消并回收 asyncio task。

    :param task: 待取消或已结束的 task。
    :returns: ``None``。
    :raises Exception: task 已经以非取消异常结束时向上透传，避免吞掉异步
        状态机错误。
    """

    if not task.done():
        task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _cancel_interactive_turn_after_first_sigint(
    *,
    host: Host,
    invocation: CliInvocation,
    turn_index: int,
    accepted_run: _AcceptedRunState,
    submit_task: asyncio.Task[EntrypointRunTerminalResult],
    sigint_monitor: _InteractiveSigintMonitor,
    observed_sigint_count: int,
) -> EntrypointRunTerminalResult | None:
    """第一次 SIGINT 后等待 run id 并发起 Host cancel。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: 当前交互轮次。
    :param accepted_run: 本轮 accepted Run id 状态。
    :param submit_task: 正在运行的 submit / terminal wait task。
    :param sigint_monitor: 本轮 SIGINT monitor。
    :param observed_sigint_count: 第一次 SIGINT 后的计数。
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
    return await _cancel_run_waiting_for_terminal_or_second_sigint(
        host=host,
        invocation=invocation,
        turn_index=turn_index,
        run_id=run_id,
        sigint_monitor=sigint_monitor,
        observed_sigint_count=observed_sigint_count,
    )


async def _wait_for_run_id_or_local_exit(
    *,
    accepted_run: _AcceptedRunState,
    submit_task: asyncio.Task[EntrypointRunTerminalResult],
    sigint_monitor: _InteractiveSigintMonitor,
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
    second_sigint_task = asyncio.create_task(
        sigint_monitor.wait_next(observed_sigint_count)
    )
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
        await _cancel_and_await_task(run_id_task)
        await _cancel_and_await_task(second_sigint_task)


async def _cancel_run_waiting_for_terminal_or_second_sigint(
    *,
    host: Host,
    invocation: CliInvocation,
    turn_index: int,
    run_id: str,
    sigint_monitor: _InteractiveSigintMonitor,
    observed_sigint_count: int,
) -> EntrypointRunTerminalResult | None:
    """发起 Host cancel，并在第二次 SIGINT 时本地退出。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: 当前交互轮次。
    :param run_id: 待取消 Run id。
    :param sigint_monitor: 本轮 SIGINT monitor。
    :param observed_sigint_count: 第一次 SIGINT 后的计数。
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
    second_sigint_task = asyncio.create_task(
        sigint_monitor.wait_next(observed_sigint_count)
    )
    try:
        done, _pending = await asyncio.wait(
            (cancel_task, second_sigint_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done:
            return await cancel_task
        cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task
        return None
    finally:
        await _cancel_and_await_task(second_sigint_task)


def _raise_for_unsupported_execution_options(args: ParsedCliArgs) -> None:
    """检查当前 S4 不支持的旧执行参数。

    :param args: interactive 命令参数。
    :returns: ``None``。
    :raises CliInteractiveUsageError: 任一 unsupported option 被用户显式使用时抛出。
    """

    unsupported = _unsupported_execution_option_names(args)
    if unsupported:
        raise CliInteractiveUsageError(
            f"{_UNSUPPORTED_OPTION_PREFIX}: {', '.join(unsupported)}"
        )


def _unsupported_execution_option_names(args: ParsedCliArgs) -> tuple[str, ...]:
    """返回用户显式使用但当前 S4 不支持的旧执行选项名。

    :param args: interactive 命令参数。
    :returns: unsupported option 名称元组。
    :raises Exception: 不主动抛出异常。
    """

    names: list[str] = []
    if args.thinking is not None:
        names.append("--thinking/--no-thinking")
    if args.web_provider is not None:
        names.append("--web-provider")
    if args.debug_sse:
        names.append("--debug-sse")
    if args.debug_tool_delta:
        names.append("--debug-tool-delta")
    if args.debug_sse_sample_rate is not None:
        names.append("--debug-sse-sample-rate")
    if args.debug_sse_throttle_sec is not None:
        names.append("--debug-sse-throttle-sec")
    if args.enable_tool_trace:
        names.append("--enable-tool-trace")
    if args.tool_trace_dir is not None:
        names.append("--tool-trace-dir")
    if args.max_duplicate_tool_calls is not None:
        names.append("--max-duplicate-tool-calls")
    if args.duplicate_tool_hint_prompt is not None:
        names.append("--duplicate-tool-hint-prompt")
    if args.doc_limits_json is not None:
        names.append("--doc-limits-json")
    if args.fins_limits_json is not None:
        names.append("--fins-limits-json")
    return tuple(names)


def _service_run_overrides_from_args(args: ParsedCliArgs) -> ServiceRunOverrides:
    """把 interactive 可映射执行参数转换为 ServiceRunOverrides。

    :param args: interactive 命令参数。
    :returns: ServiceRunOverrides。
    :raises CliInteractiveUsageError: 数值或枚举 override 非法时抛出。
    """

    try:
        return ServiceRunOverrides(
            temperature=args.temperature,
            tool_execution_timeout_seconds=args.tool_timeout_seconds,
            max_iterations=args.max_iterations,
            fallback_mode=_optional_stripped_text(
                args.fallback_mode,
                field_name=_FALLBACK_MODE_OPTION,
            ),
            fallback_prompt=_optional_stripped_text(
                args.fallback_prompt,
                field_name=_FALLBACK_PROMPT_OPTION,
            ),
            max_consecutive_failed_tool_batches=(
                args.max_consecutive_failed_tool_batches
            ),
        )
    except ValueError as exc:
        raise CliInteractiveUsageError(str(exc)) from exc


def _interactive_context_slot_values(*, ticker: str | None) -> dict[str, JsonValue]:
    """构造 interactive scene required context slots。

    :param ticker: 用户显式提供的业务主体；未提供时为 ``None``。
    :returns: 传给 ScenePrepare 的 context slot 值。
    :raises Exception: 不主动抛出异常。
    """

    return {
        CONTEXT_SLOT_FINS_DEFAULT_SUBJECT: (
            ticker if ticker is not None else DEFAULT_FINS_SUBJECT
        ),
        CONTEXT_SLOT_BASE_USER: DEFAULT_BASE_USER,
    }


def _resolve_workspace_root(value: str) -> Path:
    """解析 CLI workspace root。

    :param value: argparse 解析到的 workspace root 文本。
    :returns: 解析后的绝对路径。
    :raises CliInteractiveUsageError: workspace root 为空时抛出。
    """

    stripped = _require_cli_text(value, field_name=_BASE_OPTION)
    return Path(stripped).expanduser().resolve(strict=False)


def _resolve_explicit_config_dir(
    *, config_dir: str | None, workspace_root: Path
) -> Path | None:
    """解析并校验显式 ``--config`` 目录。

    :param config_dir: 用户显式传入的配置目录；未提供时为 ``None``。
    :param workspace_root: 已解析的 workspace root。
    :returns: 解析后的显式配置目录；未提供时为 ``None``。
    :raises CliInteractiveUsageError: 路径为空、逃逸 workspace 或不是目录时抛出。
    """

    if config_dir is None:
        return None
    stripped = _require_cli_text(config_dir, field_name=_CONFIG_DIR_OPTION)
    raw_path = Path(stripped).expanduser()
    candidate = raw_path if raw_path.is_absolute() else workspace_root / raw_path
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise CliInteractiveUsageError(
            f"{_CONFIG_DIR_OPTION} must stay inside workspace root: {resolved}"
        ) from exc
    if not resolved.is_dir():
        raise CliInteractiveUsageError(
            f"{_CONFIG_DIR_OPTION} is not a directory: {resolved}"
        )
    return resolved


def _optional_stripped_text(value: str | None, *, field_name: str) -> str | None:
    """校验并裁剪可选 CLI 文本。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :returns: 裁剪后的文本；未提供时返回 ``None``。
    :raises CliInteractiveUsageError: 文本为空或仅包含空白时抛出。
    """

    if value is None:
        return None
    return _require_cli_text(value, field_name=field_name)


def _require_cli_text(value: str, *, field_name: str) -> str:
    """校验 CLI 文本参数非空并裁剪。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :returns: 裁剪后的文本。
    :raises CliInteractiveUsageError: 文本为空或仅包含空白时抛出。
    """

    stripped = value.strip()
    if stripped == "":
        raise CliInteractiveUsageError(f"{field_name} must not be empty")
    return stripped


def _read_user_input(prompt: str) -> str:
    """读取一行 interactive 用户输入。

    :param prompt: 输入提示文本。
    :returns: 用户输入文本。
    :raises EOFError: 用户输入 Ctrl-D 时由 ``input`` 抛出。
    :raises KeyboardInterrupt: 输入态 Ctrl-C 时由 ``input`` 抛出。
    """

    return input(prompt)


def _package_config_root() -> Path:
    """返回包内默认配置根目录。

    :returns: ``dayu/config`` 绝对路径。
    :raises Exception: 不主动抛出异常。
    """

    return Path(__file__).resolve().parents[2] / "config"


__all__: tuple[str, ...] = (
    "CliInteractiveUsageError",
    "run_interactive_command",
)
