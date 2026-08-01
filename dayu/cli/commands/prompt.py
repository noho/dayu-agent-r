"""``dayu-cli prompt`` one-shot 命令实现。

本模块是 CLI UI adapter：解析后的用户输入在这里转换为 Service public
request，随后经 ConfigLoader、ScenePrepare、ToolsDiscovery、Service assembly
与 Host public API 完成一次 prompt Run。CLI 不构造 Engine request，不读取
Host durable internals，也不访问 Fins storage。
"""

from __future__ import annotations

import asyncio
import os
from typing import Final

from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    optional_stripped_text,
)
from dayu.cli.arg_parsing import COMMAND_PROMPT, ParsedCliArgs
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
    CLI_AGENT_SESSION_SCOPE,
    CLI_PROMPT_SCENARIO,
    CliInvocation,
    build_prompt_host_context,
    cli_label_slot_key,
    prompt_create_session_client_request_id,
)
from dayu.cli.output import render_cli_error
from dayu.cli.session_execution import (
    execute_prompt_on_session,
    prepare_prompt_session_execution,
)
from dayu.contracts import JsonValue
from dayu.host.api import (
    Host,
    HostApiError,
)
from dayu.host.open_host import open_host
from dayu.runtime.location import RuntimeLocationError
from dayu.service.entrypoint_runtime import (
    ensure_or_create_entrypoint_session,
)
from dayu.service.scene_context import (
    FMP_API_KEY_ENV,
    EntrypointContextSlotRequest,
    build_entrypoint_context_slot_values,
)

DEFAULT_DISPLAY_USER: Final[str] = "本地 CLI 用户"
_TICKER_OPTION: Final[str] = "--ticker"
_LABEL_OPTION: Final[str] = "--label"
_PROMPT_OPERATION_CREATE_SESSION: Final[str] = "create_session"


class CliCommandUsageError(CliUsageError):
    """CLI 命令用法错误。"""


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
    except HostApiError as exc:
        render_cli_error(format_host_api_error(COMMAND_PROMPT, exc))
        return exit_code_for_host_api_error(exc)
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

    ticker = _prompt_ticker(args)
    prepared = await prepare_prompt_session_execution(
        args,
        command_name=COMMAND_PROMPT,
        scenario=CLI_PROMPT_SCENARIO,
        user_prompt=args.prompt,
        ticker=ticker,
        context_slot_values=build_prompt_context_slot_values(
            ticker=ticker,
            fmp_api_key=os.environ.get(FMP_API_KEY_ENV),
        ),
        usage_error_factory=CliCommandUsageError,
    )
    async with open_host(prepared.runtime.host_assembly.options) as host:
        session_id = await _ensure_prompt_session(
            host=host,
            args=args,
            invocation=prepared.invocation,
        )
        return await execute_prompt_on_session(
            host=host,
            prepared=prepared,
            session_id=session_id,
            sigint_monitor=CliSigintMonitor(),
            detail=args.detail,
            thinking=args.thinking,
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
        slot_key = cli_label_slot_key(args.label)
    except ValueError as exc:
        raise CliCommandUsageError(f"{_LABEL_OPTION}: {exc}") from exc
    session = await ensure_or_create_entrypoint_session(
        host,
        create_new=False,
        bind_slot=True,
        scope=CLI_AGENT_SESSION_SCOPE,
        slot_key=slot_key,
        metadata=(),
    )
    return session.session_id


def _prompt_ticker(args: ParsedCliArgs) -> str | None:
    """读取并校验 prompt 命令的 ticker 参数。

    :param args: argparse 已解析的 prompt 兼容命令参数。
    :returns: 裁剪后的 ticker；未提供时为 ``None``。
    :raises CliCommandUsageError: ticker 为空白时抛出。
    """

    return optional_stripped_text(
        args.ticker,
        field_name=_TICKER_OPTION,
        error_factory=CliCommandUsageError,
    )


def build_prompt_context_slot_values(
    *,
    ticker: str | None,
    fmp_api_key: str | None,
) -> dict[str, JsonValue]:
    """构造 prompt scene required context slots。

    :param ticker: 用户显式提供的业务主体；未提供时为 ``None``。
    :param fmp_api_key: 调用方显式读取的 FMP API key；缺失时回退到 ticker-only。
    :returns: 传给 ScenePrepare 的 context slot 值。
    :raises ValueError: ticker 形态非法时抛出。
    """

    try:
        return build_entrypoint_context_slot_values(
            EntrypointContextSlotRequest(
                ticker=ticker,
                fmp_api_key=fmp_api_key,
            )
        )
    except ValueError as exc:
        raise CliCommandUsageError(str(exc)) from exc


__all__: tuple[str, ...] = (
    "CliCommandUsageError",
    "build_prompt_context_slot_values",
    "run_prompt_command",
)
