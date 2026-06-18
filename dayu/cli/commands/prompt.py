"""``dayu-cli prompt`` one-shot 命令实现。

本模块是 CLI UI adapter：解析后的用户输入在这里转换为 Service public
request，随后经 ConfigLoader、ScenePrepare、ToolsDiscovery、Service assembly
与 Host public API 完成一次 prompt Run。CLI 不构造 Engine request，不读取
Host durable internals，也不访问 Fins storage。
"""

from __future__ import annotations

import asyncio
import os
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
from dayu.cli.activity import CliActivityRenderer, CliActivityRendererOptions
from dayu.cli.arg_parsing import COMMAND_PROMPT, ParsedCliArgs
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.host_context import (
    CLI_PROMPT_SCENARIO,
    CLI_SIGINT_REASON,
    PROMPT_SESSION_SCOPE,
    CliInvocation,
    build_prompt_host_context,
    new_cli_invocation,
    prompt_cancel_client_request_id,
    prompt_create_session_client_request_id,
    prompt_slot_key,
    prompt_submit_client_request_id,
)
from dayu.cli.output import render_cli_error, render_prompt_terminal_result
from dayu.cli.run_keys import (
    NoopRunningKeyMonitor,
    RunningKeyAction,
    RunningKeyMonitor,
    new_running_key_monitor,
)
from dayu.cli.session_terminal_cursor import advance_cli_terminal_cursor
from dayu.contracts import JsonValue
from dayu.host.api import (
    CancelMode,
    FollowupBehavior,
    Host,
)
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
PROMPT_TURN_INDEX: Final[int] = 1
_TICKER_OPTION: Final[str] = "--ticker"
_MODEL_NAME_OPTION: Final[str] = "--model-name"
_LABEL_OPTION: Final[str] = "--label"
_PROMPT_OPERATION_CREATE_SESSION: Final[str] = "create_session"
_PROMPT_OPERATION_SUBMIT_FOLLOWUP: Final[str] = "submit_followup"
_PROMPT_OPERATION_CANCEL_RUN: Final[str] = "cancel_run"
_UNSUPPORTED_OPTION_PREFIX: Final[str] = "unsupported option"


class CliCommandUsageError(ValueError):
    """CLI 命令用法错误。"""


@dataclass(frozen=True, slots=True)
class _PreparedPromptExistingSessionExecution:
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


class _AcceptedRunState:
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


def run_prompt_command(args: ParsedCliArgs) -> int:
    """执行 ``dayu-cli prompt`` 命令。

    :param args: argparse 已解析的 prompt 命令参数。
    :returns: CLI 退出码。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    try:
        return asyncio.run(_run_prompt_command_async(args))
    except CliCommandUsageError as exc:
        render_cli_error(f"dayu-cli prompt: {exc}")
        return EXIT_USAGE_ERROR
    except RuntimeLocationError as exc:
        render_cli_error(f"dayu-cli prompt: {exc}")
        return EXIT_USAGE_ERROR
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except Exception as exc:
        render_cli_error(f"dayu-cli prompt: {exc}")
        return EXIT_FAILURE


async def _run_prompt_command_async(args: ParsedCliArgs) -> int:
    """异步执行 prompt command 主流程。

    :param args: argparse 已解析的 prompt 命令参数。
    :returns: CLI 退出码。
    :raises CliCommandUsageError: 用户输入参数非法时抛出。
    :raises Exception: runtime assembly 或 Host public API 失败时向上抛出。
    """

    prepared = await _prepare_prompt_existing_session_execution(
        args,
        command_name=COMMAND_PROMPT,
        scenario=CLI_PROMPT_SCENARIO,
        user_prompt=args.prompt,
    )
    async with open_host(prepared.runtime.host_assembly.options) as host:
        session_id = await _ensure_prompt_session(
            host=host,
            args=args,
            invocation=prepared.invocation,
        )
        return await _execute_prompt_on_existing_session(
            host=host,
            prepared=prepared,
            session_id=session_id,
            sigint_monitor=CliSigintMonitor(),
            detail=args.detail,
        )


async def _prepare_prompt_existing_session_execution(
    args: ParsedCliArgs,
    *,
    command_name: str,
    scenario: str,
    user_prompt: str,
) -> _PreparedPromptExistingSessionExecution:
    """准备在已有 Session 上执行 prompt turn 所需的 runtime 与调用身份。

    :param args: argparse 已解析的 prompt 兼容命令参数。
    :param command_name: 当前 CLI command 名称。
    :param scenario: prompt scene id。
    :param user_prompt: 本轮用户 prompt。
    :returns: 已准备的 prompt existing-session 执行输入。
    :raises CliCommandUsageError: 用户输入参数非法时抛出。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    _raise_for_unsupported_execution_options(args)
    workspace_root = resolve_workspace_root(
        args.workspace_root,
        error_factory=CliCommandUsageError,
    )
    explicit_config_dir = resolve_explicit_config_dir(
        config_dir=args.config_dir,
        workspace_root=workspace_root,
        error_factory=CliCommandUsageError,
    )
    ticker = optional_stripped_text(
        args.ticker,
        field_name=_TICKER_OPTION,
        error_factory=CliCommandUsageError,
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
            context_slot_values=_prompt_context_slot_values(ticker=ticker),
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=optional_stripped_text(
                    args.model_name,
                    field_name=_MODEL_NAME_OPTION,
                    error_factory=CliCommandUsageError,
                )
            ),
            env=os.environ,
        )
    )
    return _PreparedPromptExistingSessionExecution(
        runtime=runtime,
        workspace_root=workspace_root,
        invocation=invocation,
        user_prompt=user_prompt,
        run_overrides=service_run_overrides_from_args(
            args,
            error_factory=CliCommandUsageError,
        ),
    )


async def _execute_prompt_on_existing_session(
    *,
    host: Host,
    prepared: _PreparedPromptExistingSessionExecution,
    session_id: str,
    sigint_monitor: CliSigintMonitor,
    detail: bool = False,
) -> int:
    """在已解析的已有 Session 上执行 prompt turn。

    :param host: Host public handle。
    :param prepared: prompt existing-session 执行准备结果。
    :param session_id: 已存在且调用方已选择的 Host Session id。
    :param sigint_monitor: prompt 运行阶段 SIGINT monitor。
    :param detail: 是否显示运行态 activity stream。
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
        key_monitor=new_running_key_monitor(),
    )
    if terminal is None:
        return EXIT_KEYBOARD_INTERRUPT
    render_exit_code = render_prompt_terminal_result(terminal)
    if render_exit_code == EXIT_SUCCESS:
        await advance_cli_terminal_cursor(
            workspace_root=prepared.workspace_root,
            session_id=session_id,
            terminal_event_id=terminal.terminal_event_id,
            event_sequence=terminal.event_sequence,
        )
    return render_exit_code


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


async def _ensure_prompt_session(
    *,
    host: Host,
    args: ParsedCliArgs,
    invocation: CliInvocation,
) -> str:
    """确保 prompt 命令使用的 Host Session。

    :param host: Host public handle。
    :param args: prompt 命令参数。
    :param invocation: 当前 CLI invocation 身份。
    :returns: Host session id。
    :raises CliCommandUsageError: label 为空时抛出。
    :raises Exception: Host public API 失败时向上抛出。
    """

    if args.label is None:
        session = await ensure_or_create_entrypoint_session(
            host,
            create_new=True,
            bind_slot=False,
            scope=None,
            slot_key=None,
            metadata=(),
            create_context=build_prompt_host_context(
                invocation,
                operation=_PROMPT_OPERATION_CREATE_SESSION,
            ),
            create_client_request_id=prompt_create_session_client_request_id(invocation),
        )
        return session.session_id
    try:
        slot_key = prompt_slot_key(args.label)
    except ValueError as exc:
        raise CliCommandUsageError(f"{_LABEL_OPTION}: {exc}") from exc
    session = await ensure_or_create_entrypoint_session(
        host,
        create_new=False,
        bind_slot=True,
        scope=PROMPT_SESSION_SCOPE,
        slot_key=slot_key,
        metadata=(),
    )
    return session.session_id


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
    :param key_monitor: 运行态 TTY 按键 monitor；``None`` 表示 no-op。
    :returns: Host terminal result；Run accepted 前 SIGINT 返回 ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    accepted_run = _AcceptedRunState()
    renderer = activity_renderer
    monitor = NoopRunningKeyMonitor() if key_monitor is None else key_monitor
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
                    if renderer is not None:
                        renderer.toggle_visible()
                    key_task = asyncio.create_task(monitor.wait_next())
                    continue
                return await _cancel_prompt_turn_after_local_request(
                    host=host,
                    invocation=invocation,
                    accepted_run=accepted_run,
                    submit_task=submit_task,
                    sigint_monitor=sigint_monitor,
                    observed_sigint_count=observed_sigint_count,
                    activity_renderer=renderer,
                )
            first_sigint_count = await sigint_task
            return await _cancel_prompt_turn_after_local_request(
                host=host,
                invocation=invocation,
                accepted_run=accepted_run,
                submit_task=submit_task,
                sigint_monitor=sigint_monitor,
                observed_sigint_count=first_sigint_count,
                activity_renderer=renderer,
            )
    finally:
        if renderer is not None:
            renderer.close()
        monitor.close()
        sigint_monitor.close()
        await cancel_and_await_task(sigint_task)
        await cancel_and_await_task(key_task)


async def _cancel_prompt_turn_after_local_request(
    *,
    host: Host,
    invocation: CliInvocation,
    accepted_run: _AcceptedRunState,
    submit_task: asyncio.Task[EntrypointRunTerminalResult],
    sigint_monitor: CliSigintMonitor,
    observed_sigint_count: int,
    activity_renderer: CliActivityRenderer | None = None,
) -> EntrypointRunTerminalResult | None:
    """本地取消请求后取消 prompt turn 并等待 Host terminal 或二次 SIGINT。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param accepted_run: 本轮 accepted Run id 状态。
    :param submit_task: 正在运行的 submit / terminal wait task。
    :param sigint_monitor: prompt 运行阶段 SIGINT monitor。
    :param observed_sigint_count: 第一次取消请求后的 SIGINT 计数；Esc 取消
        时传入进入运行态前的计数，避免 Esc 被当作 Ctrl+C 次数。
    :param activity_renderer: 运行态 activity renderer；``None`` 表示不输出。
    :returns: cancel 后 terminal result；Run accepted 前或二次 SIGINT 时返回
        ``None``。
    :raises Exception: submit、cancel 或 terminal observation 失败时向上抛出。
    """

    submit_task.cancel()
    with suppress(asyncio.CancelledError):
        await submit_task
    if accepted_run.run_id is None:
        return None
    if activity_renderer is not None:
        activity_renderer.render_cancel_requested()
    return await _cancel_prompt_run_waiting_for_terminal_or_second_sigint(
        host=host,
        invocation=invocation,
        run_id=accepted_run.run_id,
        sigint_monitor=sigint_monitor,
        observed_sigint_count=observed_sigint_count,
        activity_renderer=activity_renderer,
    )


async def _cancel_prompt_run_waiting_for_terminal_or_second_sigint(
    *,
    host: Host,
    invocation: CliInvocation,
    run_id: str,
    sigint_monitor: CliSigintMonitor,
    observed_sigint_count: int,
    activity_renderer: CliActivityRenderer | None = None,
) -> EntrypointRunTerminalResult | None:
    """发起 prompt Host cancel，并在二次 SIGINT 时本地退出。

    :param host: Host public handle。
    :param invocation: 当前 CLI invocation 身份。
    :param run_id: 待取消 Run id。
    :param sigint_monitor: prompt 运行阶段 SIGINT monitor。
    :param observed_sigint_count: 第一次取消请求后的 SIGINT 计数。
    :param activity_renderer: 运行态 activity renderer；``None`` 表示不输出。
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
        if activity_renderer is not None:
            activity_renderer.render_local_exit_after_cancel()
        cancel_task.cancel()
        with suppress(asyncio.CancelledError):
            await cancel_task
        return None
    finally:
        await cancel_and_await_task(second_sigint_task)


def _raise_for_unsupported_execution_options(args: ParsedCliArgs) -> None:
    """检查当前 S3 不支持的旧执行参数。

    :param args: prompt 命令参数。
    :returns: ``None``。
    :raises CliCommandUsageError: 任一 unsupported option 被用户显式使用时抛出。
    """

    unsupported = unsupported_execution_option_names(args)
    if unsupported:
        raise CliCommandUsageError(f"{_UNSUPPORTED_OPTION_PREFIX}: {', '.join(unsupported)}")


def _prompt_context_slot_values(*, ticker: str | None) -> dict[str, JsonValue]:
    """构造 prompt scene required context slots。

    :param ticker: 用户显式提供的业务主体；未提供时为 ``None``。
    :returns: 传给 ScenePrepare 的 context slot 值。
    :raises Exception: 不主动抛出异常。
    """

    return {
        CONTEXT_SLOT_FINS_DEFAULT_SUBJECT: (ticker if ticker is not None else DEFAULT_FINS_SUBJECT),
        CONTEXT_SLOT_BASE_USER: DEFAULT_BASE_USER,
    }


__all__: tuple[str, ...] = ("CliCommandUsageError", "run_prompt_command")
