"""``dayu-cli session`` 命令实现。

本模块是 CLI UI adapter：只通过 Host public API 解析已有 Session、读取
Session 列表或请求 purge。resume 执行会路由到 prompt / interactive 的
existing-session 窄入口；本模块不复制 submit/watch/cancel 业务路径，不读取
durable internals，不自动 close / cancel，也不承载 Host 状态机判断。
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Final

from dayu.cli.agent_entrypoint import (
    CliSigintMonitor,
    optional_stripped_text,
    package_config_root,
    resolve_explicit_config_dir,
    resolve_workspace_root,
)
from dayu.cli.arg_parsing import (
    COMMAND_SESSION,
    SESSION_ACTION_LIST,
    SESSION_ACTION_PURGE,
    SESSION_ACTION_RESUME,
    ParsedCliArgs,
)
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.errors import CliUsageError
from dayu.cli.commands.interactive import (
    build_interactive_context_slot_values,
)
from dayu.cli.commands.prompt import (
    build_prompt_context_slot_values,
)
from dayu.cli.host_api_errors import (
    CliHostApiErrorTarget,
    exit_code_for_host_api_error,
    format_host_api_error,
    host_api_error_context,
)
from dayu.cli.host_context import (
    CLI_INTERACTIVE_SCENARIO,
    CLI_PROMPT_SCENARIO,
    CliInvocation,
    build_session_host_context,
    new_cli_invocation,
    session_purge_client_request_id,
)
from dayu.cli.output import (
    render_cli_error,
    render_session_list,
    render_session_purge_result,
)
from dayu.cli.session_execution import (
    execute_interactive_on_session,
    execute_prompt_on_session,
    prepare_interactive_session_execution,
    prepare_prompt_session_execution,
)
from dayu.cli.session_identity import slot_ref_for_cli_label
from dayu.host.api import (
    HostAdmin,
    HostApiError,
    HostApiErrorCode,
    PurgeSessionRequest,
    SessionSlotRef,
    SessionStatus,
)
from dayu.host.open_host import open_host, open_host_admin
from dayu.runtime.location import RuntimeLocationError
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeError,
)
from dayu.service.host_admin import (
    ServiceHostAdminRequest,
    ServiceHostAdminResult,
    prepare_host_admin,
)
from dayu.service.scene_context import (
    FMP_API_KEY_ENV,
)

DEFAULT_DISPLAY_USER: Final[str] = "本地 CLI 用户"
DEFAULT_PURGE_REASON: Final[str] = "cli_session_purge"
_SESSION_CONTEXT_SCENARIO: Final[str] = "session"
_SESSION_ID_OPTION: Final[str] = "--session-id"
_LABEL_OPTION: Final[str] = "--label"
_MODE_OPTION: Final[str] = "--mode"
_TICKER_OPTION: Final[str] = "--ticker"
_REASON_OPTION: Final[str] = "--reason"
_PURGE_OPERATION: Final[str] = "purge_session"
_RESUME_MODE_PROMPT: Final[str] = "prompt"
_RESUME_MODE_INTERACTIVE: Final[str] = "interactive"


class CliSessionUsageError(CliUsageError):
    """``dayu-cli session`` 用户用法错误。"""


@dataclass(frozen=True, slots=True)
class _PurgeTarget:
    """一次 purge 操作已经解析出的目标。

    :param session_id: 最终传给 Host ``purge_session`` 的 Session id。
    :param selector: 用户原始 selector 的可读摘要。
    :param resolved_from_label: 目标是否经 label selector 反解得到。
    """

    session_id: str
    selector: str
    resolved_from_label: bool


@dataclass(frozen=True, slots=True)
class _ExistingSessionTarget:
    """一次 resume 操作已经解析出的目标。

    :param session_id: 最终用于提交 follow-up 的 Session id。
    :param selector: 用户原始 selector 的可读摘要。
    :param resolved_from_label: 目标是否经 label selector 反解得到。
    """

    session_id: str
    selector: str
    resolved_from_label: bool


def run_session_command(args: ParsedCliArgs) -> int:
    """执行 ``dayu-cli session`` 命令。

    :param args: argparse 已解析的 session 命令参数。
    :returns: CLI 退出码。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    try:
        return asyncio.run(_run_session_command_async(args))
    except CliSessionUsageError as exc:
        render_cli_error(f"dayu-cli session: {exc}")
        return EXIT_USAGE_ERROR
    except CliUsageError as exc:
        render_cli_error(f"dayu-cli session resume: {exc}")
        return EXIT_USAGE_ERROR
    except RuntimeLocationError as exc:
        render_cli_error(f"dayu-cli session: {exc}")
        return EXIT_USAGE_ERROR
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except HostApiError as exc:
        render_cli_error(
            format_host_api_error(
                COMMAND_SESSION,
                exc,
                action=args.session_action,
            )
        )
        return exit_code_for_host_api_error(exc)
    except Exception as exc:
        render_cli_error(f"dayu-cli session {args.session_action}: {exc}")
        return EXIT_FAILURE


async def _run_session_command_async(args: ParsedCliArgs) -> int:
    """异步执行 session command 主流程。

    :param args: argparse 已解析的 session 命令参数。
    :returns: CLI 退出码。
    :raises CliSessionUsageError: 用户输入参数非法时抛出。
    :raises HostApiError: Host public API 失败且当前流程未内联处理时抛出。
    :raises Exception: runtime assembly 或 Host opener 失败时向上抛出。
    """

    if args.session_action == SESSION_ACTION_RESUME:
        return await _run_session_resume(args)
    invocation = new_cli_invocation(
        command_name=COMMAND_SESSION,
        scenario=_SESSION_CONTEXT_SCENARIO,
        display_user=DEFAULT_DISPLAY_USER,
        ticker=None,
    )
    admin = _prepare_session_admin(args)
    async with open_host_admin(admin.options) as host:
        if args.session_action == SESSION_ACTION_LIST:
            return await _run_session_list(host)
        if args.session_action == SESSION_ACTION_PURGE:
            return await _run_session_purge(
                host=host,
                args=args,
                invocation=invocation,
            )
    raise CliSessionUsageError(f"unsupported session command: {args.session_action}")


def _prepare_session_admin(
    args: ParsedCliArgs,
) -> ServiceHostAdminResult:
    """准备 session list/purge 所需的纯 durable admin assembly。

    :param args: argparse 已解析的 session 命令参数。
    :returns: HostAdmin opener 装配结果。
    :raises CliSessionUsageError: workspace 或 config 参数非法时抛出。
    :raises Exception: Host runtime 配置或路径装配失败时向上抛出。
    """

    workspace_root = resolve_workspace_root(
        args.workspace_root,
        error_factory=CliSessionUsageError,
    )
    explicit_config_dir = resolve_explicit_config_dir(
        config_dir=args.config_dir,
        workspace_root=workspace_root,
        error_factory=CliSessionUsageError,
    )
    return prepare_host_admin(
        ServiceHostAdminRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root(),
            config_overlay_dir=explicit_config_dir,
        )
    )


async def _run_session_list(host: HostAdmin) -> int:
    """执行 ``session list``。

    :param host: HostAdmin public handle。
    :returns: CLI 退出码。
    :raises HostApiError: Host 读取失败时向上抛出。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    render_session_list(await host.list_sessions())
    return EXIT_SUCCESS


async def _run_session_resume(args: ParsedCliArgs) -> int:
    """执行 ``session resume``。

    :param args: argparse 已解析的 session 命令参数。
    :returns: CLI 退出码。
    :raises CliSessionUsageError: selector、mode 或 prompt 参数非法时抛出。
    :raises CliSessionUsageError: prompt / interactive 兼容执行参数非法时抛出。
    :raises Exception: runtime assembly、Host public API 或输出失败时向上抛出。
    """

    mode = _require_resume_mode(args.mode)
    if mode == _RESUME_MODE_PROMPT:
        user_prompt = _require_resume_prompt(args)
        ticker = _resume_prompt_ticker(args)
        prepared = await prepare_prompt_session_execution(
            args,
            command_name=COMMAND_SESSION,
            scenario=CLI_PROMPT_SCENARIO,
            user_prompt=user_prompt,
            ticker=ticker,
            context_slot_values=build_prompt_context_slot_values(
                ticker=ticker,
                fmp_api_key=os.environ.get(FMP_API_KEY_ENV),
            ),
            usage_error_factory=CliSessionUsageError,
        )
        target = await _resolve_existing_session_target_with_admin(args)
        async with open_host(prepared.runtime.host_assembly.options) as host:
            try:
                return await execute_prompt_on_session(
                    host=host,
                    prepared=prepared,
                    session_id=target.session_id,
                    sigint_monitor=CliSigintMonitor(),
                    detail=args.detail,
                    thinking=args.thinking,
                )
            except HostApiError as exc:
                render_cli_error(_resume_host_error_message(target=target, error=exc))
                return exit_code_for_host_api_error(
                    exc,
                    target=_host_error_target(target),
                )
    _reject_interactive_resume_prompt(args)
    _reject_interactive_resume_ticker(args)
    prepared_interactive = await prepare_interactive_session_execution(
        args,
        command_name=COMMAND_SESSION,
        scenario=CLI_INTERACTIVE_SCENARIO,
        context_slot_values=build_interactive_context_slot_values(),
        usage_error_factory=CliSessionUsageError,
    )
    target = await _resolve_existing_session_target_with_admin(args)
    async with open_host(prepared_interactive.runtime.host_assembly.options) as host:
        try:
            return await execute_interactive_on_session(
                host=host,
                prepared=prepared_interactive,
                session_id=target.session_id,
                detail=args.detail,
                thinking=args.thinking,
            )
        except HostApiError as exc:
            render_cli_error(_resume_host_error_message(target=target, error=exc))
            return exit_code_for_host_api_error(
                exc,
                target=_host_error_target(target),
            )
        except EntrypointRuntimeError as exc:
            render_cli_error(_resume_startup_error_message(target=target, error=exc))
            return EXIT_FAILURE


async def _run_session_purge(
    *,
    host: HostAdmin,
    args: ParsedCliArgs,
    invocation: CliInvocation,
) -> int:
    """执行 ``session purge``。

    :param host: HostAdmin public handle。
    :param args: argparse 已解析的 session 命令参数。
    :param invocation: 当前 CLI invocation 身份。
    :returns: CLI 退出码。
    :raises CliSessionUsageError: selector 或 reason 非法时抛出。
    :raises HostApiError: label 解析读取 Host list 失败时向上抛出。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    if not args.yes:
        raise CliSessionUsageError("session purge requires --yes")
    target = await _resolve_purge_target(host=host, args=args)
    request = PurgeSessionRequest(
        context=build_session_host_context(
            invocation,
            operation=_PURGE_OPERATION,
        ),
        client_request_id=session_purge_client_request_id(invocation),
        reason=_purge_reason(args),
    )
    try:
        result = await host.purge_session(target.session_id, request)
    except HostApiError as exc:
        render_cli_error(_purge_host_error_message(target=target, error=exc))
        return exit_code_for_host_api_error(
            exc,
            target=_host_error_target(target),
        )
    render_session_purge_result(result)
    return EXIT_SUCCESS


async def _resolve_existing_session_target(
    *,
    host: HostAdmin,
    args: ParsedCliArgs,
) -> _ExistingSessionTarget:
    """把 resume selector 解析为当前存在且 OPEN 的 Host Session。

    :param host: HostAdmin public handle。
    :param args: argparse 已解析的 session 命令参数。
    :returns: 已解析的 existing Session 目标。
    :raises CliSessionUsageError: selector 非法、目标缺失或目标 CLOSED 时抛出。
    :raises HostApiError: 非 NOT_FOUND 的 Host 读取错误向上抛出。
    """

    session_id = optional_stripped_text(
        args.session_id,
        field_name=_SESSION_ID_OPTION,
        error_factory=CliSessionUsageError,
    )
    if session_id is not None:
        try:
            snapshot = await host.get_session(session_id)
        except HostApiError as exc:
            if exc.code is HostApiErrorCode.NOT_FOUND:
                raise CliSessionUsageError(f"session not found: {session_id}") from exc
            raise
        if snapshot.status is not SessionStatus.OPEN:
            raise CliSessionUsageError(
                f"session is closed and cannot be resumed: {session_id}"
            )
        return _ExistingSessionTarget(
            session_id=session_id,
            selector=f"{_SESSION_ID_OPTION} {session_id}",
            resolved_from_label=False,
        )
    label = optional_stripped_text(
        args.label,
        field_name=_LABEL_OPTION,
        error_factory=CliSessionUsageError,
    )
    if label is None:
        raise CliSessionUsageError("session resume requires a selector")
    slot = slot_ref_for_cli_label(label)
    result = await host.list_sessions()
    for item in result.sessions:
        if item.slot == slot:
            if item.status is not SessionStatus.OPEN:
                raise CliSessionUsageError(
                    f"session is closed and cannot be resumed: {item.session_id}"
                )
            return _ExistingSessionTarget(
                session_id=item.session_id,
                selector=f"{_LABEL_OPTION} {label}",
                resolved_from_label=True,
            )
    raise CliSessionUsageError(
        f"no session found for label {label!r}"
    )


async def _resolve_existing_session_target_with_admin(
    args: ParsedCliArgs,
) -> _ExistingSessionTarget:
    """通过短生命周期 HostAdmin 解析 resume 目标。

    :param args: argparse 已解析的 session resume 参数。
    :returns: 已解析且仍为 OPEN 的 Session 目标。
    :raises CliSessionUsageError: selector 非法或目标不可 resume 时抛出。
    :raises HostApiError: durable 列表读取失败时抛出。
    :raises Exception: admin assembly 或 opener 失败时透传。
    """

    admin = _prepare_session_admin(args)
    async with open_host_admin(admin.options) as host_admin:
        return await _resolve_existing_session_target(
            host=host_admin,
            args=args,
        )


async def _resolve_purge_target(
    *,
    host: HostAdmin,
    args: ParsedCliArgs,
) -> _PurgeTarget:
    """解析 purge selector 为 Host Session id。

    :param host: HostAdmin public handle。
    :param args: argparse 已解析的 session 命令参数。
    :returns: purge 目标。
    :raises CliSessionUsageError: selector 非法或 label 无匹配 Session 时抛出。
    :raises HostApiError: label 解析读取 Host list 失败时向上抛出。
    """

    session_id = optional_stripped_text(
        args.session_id,
        field_name=_SESSION_ID_OPTION,
        error_factory=CliSessionUsageError,
    )
    if session_id is not None:
        return _PurgeTarget(
            session_id=session_id,
            selector=f"{_SESSION_ID_OPTION} {session_id}",
            resolved_from_label=False,
        )
    label = optional_stripped_text(
        args.label,
        field_name=_LABEL_OPTION,
        error_factory=CliSessionUsageError,
    )
    if label is None:
        raise CliSessionUsageError("session purge requires a selector")
    slot = slot_ref_for_cli_label(label)
    resolved_session_id = await _resolve_session_id_for_slot(host=host, slot=slot)
    if resolved_session_id is None:
        raise CliSessionUsageError(
            f"no session found for label {label!r}"
        )
    return _PurgeTarget(
        session_id=resolved_session_id,
        selector=f"{_LABEL_OPTION} {label}",
        resolved_from_label=True,
    )


async def _resolve_session_id_for_slot(
    *,
    host: HostAdmin,
    slot: SessionSlotRef,
) -> str | None:
    """通过 Host public list 解析 slot 当前绑定的 Session id。

    :param host: HostAdmin public handle。
    :param slot: 待匹配的 Host public slot ref。
    :returns: 匹配到的 Session id；未匹配时为 ``None``。
    :raises HostApiError: Host list 失败时向上抛出。
    """

    result = await host.list_sessions()
    for item in result.sessions:
        if item.slot == slot:
            return item.session_id
    return None


def _require_resume_mode(value: str | None) -> str:
    """校验 session resume mode。

    :param value: argparse 解析到的 ``--mode`` 值。
    :returns: resume mode 字符串。
    :raises CliSessionUsageError: ``--mode`` 缺失或非法时抛出。
    """

    mode = optional_stripped_text(
        value,
        field_name=_MODE_OPTION,
        error_factory=CliSessionUsageError,
    )
    if mode in (_RESUME_MODE_PROMPT, _RESUME_MODE_INTERACTIVE):
        return mode
    raise CliSessionUsageError("--mode must be prompt or interactive")


def _require_resume_prompt(args: ParsedCliArgs) -> str:
    """读取 prompt mode resume 的 positional prompt。

    :param args: argparse 已解析的 session 命令参数。
    :returns: 本轮用户 prompt。
    :raises CliSessionUsageError: prompt 缺失或为空白时抛出。
    """

    prompt = optional_stripped_text(
        args.session_prompt,
        field_name="prompt",
        error_factory=CliSessionUsageError,
    )
    if prompt is None:
        raise CliSessionUsageError("session resume --mode prompt requires prompt")
    return prompt


def _reject_interactive_resume_prompt(args: ParsedCliArgs) -> None:
    """拒绝 interactive mode resume 携带 positional prompt。

    :param args: argparse 已解析的 session 命令参数。
    :returns: ``None``。
    :raises CliSessionUsageError: interactive mode 携带 prompt 时抛出。
    """

    if args.session_prompt is not None:
        raise CliSessionUsageError(
            "session resume --mode interactive does not accept prompt"
        )


def _resume_prompt_ticker(args: ParsedCliArgs) -> str | None:
    """读取 prompt resume 兼容执行的 ticker 参数。

    :param args: argparse 已解析的 session resume 命令参数。
    :returns: 裁剪后的 ticker；未提供时为 ``None``。
    :raises CliSessionUsageError: ticker 为空白时抛出。
    """

    return optional_stripped_text(
        args.ticker,
        field_name=_TICKER_OPTION,
        error_factory=CliSessionUsageError,
    )


def _reject_interactive_resume_ticker(args: ParsedCliArgs) -> None:
    """拒绝 interactive resume 携带 prompt 专属 ticker 参数。

    :param args: argparse 已解析的 session resume 命令参数。
    :returns: ``None``。
    :raises CliSessionUsageError: interactive mode 携带 ticker 时抛出。
    """

    if args.ticker is not None:
        raise CliSessionUsageError(
            "session resume --mode interactive does not accept --ticker"
        )


def _purge_reason(args: ParsedCliArgs) -> str:
    """读取 purge reason，未提供时返回 CLI 默认 reason。

    :param args: argparse 已解析的 session 命令参数。
    :returns: Host purge reason。
    :raises CliSessionUsageError: 显式 reason 为空白时抛出。
    """

    reason = optional_stripped_text(
        args.reason,
        field_name=_REASON_OPTION,
        error_factory=CliSessionUsageError,
    )
    if reason is None:
        return DEFAULT_PURGE_REASON
    return reason


def _purge_host_error_message(
    *,
    target: _PurgeTarget,
    error: HostApiError,
) -> str:
    """把 purge HostApiError 映射成用户可读错误。

    :param target: 已解析 purge 目标。
    :param error: Host public API 结构化错误。
    :returns: stderr 错误文本。
    :raises Exception: 不主动抛出异常。
    """

    host_context = host_api_error_context(error)
    if error.code is HostApiErrorCode.INVALID_STATE:
        return (
            "dayu-cli session purge: purge requires a closed Session with "
            "terminal Runs; no close/cancel was attempted. "
            f"selector={target.selector} session_id={target.session_id} "
            f"{host_context}"
        )
    return (
        "dayu-cli session purge: "
        f"selector={target.selector} session_id={target.session_id} {host_context}"
    )


def _resume_host_error_message(
    *,
    target: _ExistingSessionTarget,
    error: HostApiError,
) -> str:
    """把 resume submit 阶段 HostApiError 映射成用户可读错误。

    :param target: 已解析 resume 目标。
    :param error: Host public API 结构化错误。
    :returns: stderr 错误文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "dayu-cli session resume: "
        f"selector={target.selector} session_id={target.session_id} "
        f"{host_api_error_context(error)}"
    )


def _resume_startup_error_message(
    *,
    target: _ExistingSessionTarget,
    error: EntrypointRuntimeError,
) -> str:
    """把 interactive resume startup 错误映射成用户可读错误。

    :param target: 已解析 resume 目标。
    :param error: Service startup barrier 抛出的运行期错误。
    :returns: stderr 错误文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "dayu-cli session resume: interactive startup failed "
        f"selector={target.selector} session_id={target.session_id} "
        f"message={error}"
    )


def _host_error_target(
    target: _ExistingSessionTarget | _PurgeTarget,
) -> CliHostApiErrorTarget:
    """把 session command 目标转换为统一 HostApiError 展示目标。

    :param target: 已解析的 resume 或 purge 目标。
    :returns: CLI HostApiError target。
    :raises Exception: 不主动抛出异常。
    """

    return CliHostApiErrorTarget(
        selector=target.selector,
        session_id=target.session_id,
        explicit_session_id_selector=not target.resolved_from_label,
        resolved_from_label=target.resolved_from_label,
    )

__all__: tuple[str, ...] = ("run_session_command",)
