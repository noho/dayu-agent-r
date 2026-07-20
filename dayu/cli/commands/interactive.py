"""``dayu-cli interactive`` 多轮命令实现。

本模块是 CLI UI adapter：负责 REPL 命令参数、HostCallContext /
client_request_id 构造和 interactive scene context slot。已有 Session 上的
runtime prepare、submit/watch/cancel 和 startup reconnect 执行组合由
``dayu.cli.session_execution`` 统一拥有。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Final

from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    optional_stripped_text,
)
from dayu.cli.arg_parsing import COMMAND_INTERACTIVE, ParsedCliArgs
from dayu.cli.composer import InteractiveComposer
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_USAGE_ERROR,
)
from dayu.cli.errors import CliUsageError
from dayu.cli.host_api_errors import (
    exit_code_for_host_api_error,
    format_host_api_error,
)
from dayu.cli.host_context import (
    CLI_INTERACTIVE_SCENARIO,
    INTERACTIVE_SESSION_SCOPE,
    CliInvocation,
    build_interactive_host_context,
    interactive_create_session_client_request_id,
    interactive_slot_key,
)
from dayu.cli.output import render_cli_error
from dayu.cli.session_execution import (
    execute_interactive_on_session,
    prepare_interactive_session_execution,
)
from dayu.contracts import JsonValue
from dayu.host.api import Host, HostApiError
from dayu.host.open_host import open_host
from dayu.runtime.location import RuntimeLocationError
from dayu.service.entrypoint_runtime import ensure_or_create_entrypoint_session
from dayu.service.scene_context import (
    FMP_API_KEY_ENV,
    EntrypointContextSlotRequest,
    build_entrypoint_context_slot_values,
)

INTERACTIVE_INPUT_PROMPT: Final[str] = "dayu> "
_TICKER_OPTION: Final[str] = "--ticker"
_LABEL_OPTION: Final[str] = "--label"
_INTERACTIVE_OPERATION_CREATE_SESSION: Final[str] = "create_session"


class CliInteractiveUsageError(CliUsageError):
    """interactive 命令用法错误。"""


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
    except HostApiError as exc:
        render_cli_error(format_host_api_error(COMMAND_INTERACTIVE, exc))
        return exit_code_for_host_api_error(exc)
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

    ticker = _interactive_ticker(args)
    prepared = await prepare_interactive_session_execution(
        args,
        command_name=COMMAND_INTERACTIVE,
        scenario=CLI_INTERACTIVE_SCENARIO,
        ticker=ticker,
        context_slot_values=build_interactive_context_slot_values(
            ticker=ticker,
            fmp_api_key=os.environ.get(FMP_API_KEY_ENV),
        ),
        usage_error_factory=CliInteractiveUsageError,
    )
    async with open_host(prepared.runtime.host_assembly.options) as host:
        session_id = await _ensure_interactive_session(
            host=host,
            args=args,
            invocation=prepared.invocation,
        )
        return await execute_interactive_on_session(
            host=host,
            prepared=prepared,
            session_id=session_id,
            run_startup_reconnect=args.label is not None,
            detail=args.detail,
            thinking=args.thinking,
            input_reader=_read_user_input if input_reader is None else input_reader,
            composer=composer,
            sigint_monitor_factory=CliSigintMonitor,
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


def _interactive_ticker(args: ParsedCliArgs) -> str | None:
    """读取并校验 interactive 命令的 ticker 参数。

    :param args: argparse 已解析的 interactive 兼容命令参数。
    :returns: 裁剪后的 ticker；未提供时为 ``None``。
    :raises CliInteractiveUsageError: ticker 为空白时抛出。
    """

    return optional_stripped_text(
        args.ticker,
        field_name=_TICKER_OPTION,
        error_factory=CliInteractiveUsageError,
    )


def build_interactive_context_slot_values(
    *,
    ticker: str | None = None,
    fmp_api_key: str | None = None,
) -> dict[str, JsonValue]:
    """构造 interactive scene required context slots。

    :param ticker: 用户显式提供的业务主体；未提供时为 ``None``。
    :param fmp_api_key: 调用方显式读取的 FMP API key；缺失时回退到 ticker-only。
    :returns: 传给 ScenePrepare 的 context slot 值。
    :raises CliInteractiveUsageError: ticker 形态非法时抛出。
    """

    try:
        return build_entrypoint_context_slot_values(
            EntrypointContextSlotRequest(
                ticker=ticker,
                fmp_api_key=fmp_api_key,
            )
        )
    except ValueError as exc:
        raise CliInteractiveUsageError(str(exc)) from exc


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
    "build_interactive_context_slot_values",
    "run_interactive_command",
)
