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
from dayu.cli.commands.interactive import (
    CliInteractiveUsageError,
    _execute_interactive_on_existing_session,
    _prepare_interactive_existing_session_execution,
)
from dayu.cli.commands.prompt import (
    CliCommandUsageError,
    _execute_prompt_on_existing_session,
    _prepare_prompt_existing_session_execution,
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
from dayu.cli.session_identity import CliSessionLabelKind, slot_ref_for_cli_label
from dayu.contracts import JsonValue
from dayu.host.api import (
    Host,
    HostApiError,
    HostApiErrorCode,
    PurgeSessionRequest,
    SessionSlotRef,
    SessionStatus,
)
from dayu.host.open_host import open_host
from dayu.runtime.location import RuntimeLocationError
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeError,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    prepare_entrypoint_runtime,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides
from dayu.service.scene_context import (
    EntrypointContextSlotRequest,
    build_entrypoint_context_slot_values,
)

DEFAULT_DISPLAY_USER: Final[str] = "本地 CLI 用户"
DEFAULT_PURGE_REASON: Final[str] = "cli_session_purge"
_SESSION_CONTEXT_SCENARIO: Final[str] = "session"
_SESSION_ID_OPTION: Final[str] = "--session-id"
_LABEL_OPTION: Final[str] = "--label"
_KIND_OPTION: Final[str] = "--kind"
_MODE_OPTION: Final[str] = "--mode"
_REASON_OPTION: Final[str] = "--reason"
_PURGE_OPERATION: Final[str] = "purge_session"
_HOST_ERROR_TEMPLATE: Final[str] = "host_code={code} host_message={message}"
_RESUME_MODE_PROMPT: Final[str] = "prompt"
_RESUME_MODE_INTERACTIVE: Final[str] = "interactive"


class CliSessionUsageError(ValueError):
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
    except (CliCommandUsageError, CliInteractiveUsageError) as exc:
        render_cli_error(f"dayu-cli session resume: {exc}")
        return EXIT_USAGE_ERROR
    except CliSessionUsageError as exc:
        render_cli_error(f"dayu-cli session: {exc}")
        return EXIT_USAGE_ERROR
    except RuntimeLocationError as exc:
        render_cli_error(f"dayu-cli session: {exc}")
        return EXIT_USAGE_ERROR
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except HostApiError as exc:
        render_cli_error(
            f"dayu-cli session {args.session_action}: {_host_error_context(exc)}"
        )
        return _exit_code_for_host_error(exc, resolved_from_label=False)
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
    runtime = await _prepare_session_runtime(args)
    async with open_host(runtime.host_assembly.options) as host:
        if args.session_action == SESSION_ACTION_LIST:
            return await _run_session_list(host)
        if args.session_action == SESSION_ACTION_PURGE:
            return await _run_session_purge(
                host=host,
                args=args,
                invocation=invocation,
            )
    raise CliSessionUsageError(f"unsupported session command: {args.session_action}")


async def _prepare_session_runtime(
    args: ParsedCliArgs,
) -> EntrypointRuntimeResult:
    """准备 session 命令打开 Host 所需的 runtime assembly。

    :param args: argparse 已解析的 session 命令参数。
    :returns: entrypoint runtime 准备结果。
    :raises CliSessionUsageError: workspace 或 config 参数非法时抛出。
    :raises Exception: runtime assembly 失败时向上抛出。
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
    return await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=package_config_root(),
            explicit_config_dir=explicit_config_dir,
            scene_id=CLI_PROMPT_SCENARIO,
            context_slot_values=_session_context_slot_values(),
            assembly_overrides=ServiceAssemblyOverrides(),
            env=os.environ,
        )
    )


async def _run_session_list(host: Host) -> int:
    """执行 ``session list``。

    :param host: Host public handle。
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
    :raises CliCommandUsageError: prompt 兼容执行参数非法时抛出。
    :raises CliInteractiveUsageError: interactive 兼容执行参数非法时抛出。
    :raises Exception: runtime assembly、Host public API 或输出失败时向上抛出。
    """

    mode = _require_resume_mode(args.mode)
    if mode == _RESUME_MODE_PROMPT:
        user_prompt = _require_resume_prompt(args)
        prepared = await _prepare_prompt_existing_session_execution(
            args,
            command_name=COMMAND_SESSION,
            scenario=CLI_PROMPT_SCENARIO,
            user_prompt=user_prompt,
        )
        async with open_host(prepared.runtime.host_assembly.options) as host:
            target = await _resolve_existing_session_target(host=host, args=args)
            try:
                return await _execute_prompt_on_existing_session(
                    host=host,
                    prepared=prepared,
                    session_id=target.session_id,
                    sigint_monitor=CliSigintMonitor(),
                    detail=args.detail,
                    thinking=args.thinking,
                )
            except HostApiError as exc:
                render_cli_error(_resume_host_error_message(target=target, error=exc))
                return _exit_code_for_host_error(
                    exc,
                    resolved_from_label=target.resolved_from_label,
                )
    _reject_interactive_resume_prompt(args)
    prepared_interactive = await _prepare_interactive_existing_session_execution(
        args,
        command_name=COMMAND_SESSION,
        scenario=CLI_INTERACTIVE_SCENARIO,
    )
    async with open_host(prepared_interactive.runtime.host_assembly.options) as host:
        target = await _resolve_existing_session_target(host=host, args=args)
        try:
            return await _execute_interactive_on_existing_session(
                host=host,
                prepared=prepared_interactive,
                session_id=target.session_id,
                detail=args.detail,
                thinking=args.thinking,
            )
        except HostApiError as exc:
            render_cli_error(_resume_host_error_message(target=target, error=exc))
            return _exit_code_for_host_error(
                exc,
                resolved_from_label=target.resolved_from_label,
            )
        except EntrypointRuntimeError as exc:
            render_cli_error(_resume_startup_error_message(target=target, error=exc))
            return EXIT_FAILURE


async def _run_session_purge(
    *,
    host: Host,
    args: ParsedCliArgs,
    invocation: CliInvocation,
) -> int:
    """执行 ``session purge``。

    :param host: Host public handle。
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
        return _exit_code_for_host_error(
            exc,
            resolved_from_label=target.resolved_from_label,
        )
    render_session_purge_result(result)
    return EXIT_SUCCESS


async def _resolve_existing_session_target(
    *,
    host: Host,
    args: ParsedCliArgs,
) -> _ExistingSessionTarget:
    """把 resume selector 解析为当前存在且 OPEN 的 Host Session。

    :param host: Host public handle。
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
    kind = _require_label_kind(args.kind)
    slot = slot_ref_for_cli_label(kind, label)
    result = await host.list_sessions()
    for item in result.sessions:
        if item.slot == slot:
            if item.status is not SessionStatus.OPEN:
                raise CliSessionUsageError(
                    f"session is closed and cannot be resumed: {item.session_id}"
                )
            return _ExistingSessionTarget(
                session_id=item.session_id,
                selector=f"{_LABEL_OPTION} {label} {_KIND_OPTION} {kind.value}",
                resolved_from_label=True,
            )
    raise CliSessionUsageError(
        f"no session found for label {label!r} kind {kind.value!r}"
    )


async def _resolve_purge_target(
    *,
    host: Host,
    args: ParsedCliArgs,
) -> _PurgeTarget:
    """解析 purge selector 为 Host Session id。

    :param host: Host public handle。
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
    kind = _require_label_kind(args.kind)
    slot = slot_ref_for_cli_label(kind, label)
    resolved_session_id = await _resolve_session_id_for_slot(host=host, slot=slot)
    if resolved_session_id is None:
        raise CliSessionUsageError(
            f"no session found for label {label!r} kind {kind.value!r}"
        )
    return _PurgeTarget(
        session_id=resolved_session_id,
        selector=f"{_LABEL_OPTION} {label} {_KIND_OPTION} {kind.value}",
        resolved_from_label=True,
    )


async def _resolve_session_id_for_slot(
    *,
    host: Host,
    slot: SessionSlotRef,
) -> str | None:
    """通过 Host public list 解析 slot 当前绑定的 Session id。

    :param host: Host public handle。
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


def _require_label_kind(value: str | None) -> CliSessionLabelKind:
    """校验并转换 label selector kind。

    :param value: argparse 解析到的 ``--kind`` 值。
    :returns: CLI Session label kind。
    :raises CliSessionUsageError: ``--kind`` 缺失或非法时抛出。
    """

    if value is None:
        raise CliSessionUsageError("--label requires --kind prompt|interactive")
    try:
        return CliSessionLabelKind(value)
    except ValueError as exc:
        raise CliSessionUsageError(
            "--kind must be prompt or interactive"
        ) from exc


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

    host_context = _host_error_context(error)
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
        f"{_host_error_context(error)}"
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


def _host_error_context(error: HostApiError) -> str:
    """格式化 HostApiError 的 code/message。

    :param error: Host public API 结构化错误。
    :returns: 用户可读 Host 错误上下文。
    :raises Exception: 不主动抛出异常。
    """

    return _HOST_ERROR_TEMPLATE.format(code=error.code.value, message=error.message)


def _exit_code_for_host_error(
    error: HostApiError,
    *,
    resolved_from_label: bool,
) -> int:
    """把 HostApiError 映射为 CLI 固定退出码。

    :param error: Host public API 结构化错误。
    :param resolved_from_label: 错误是否发生在 label selector 已解析之后。
    :returns: CLI 退出码。
    :raises Exception: 不主动抛出异常。
    """

    if error.code is HostApiErrorCode.NOT_FOUND and not resolved_from_label:
        return EXIT_USAGE_ERROR
    return EXIT_FAILURE


def _session_context_slot_values() -> dict[str, JsonValue]:
    """构造 session 命令 runtime 准备所需的上下文槽位。

    :returns: ScenePrepare 可消费的上下文槽位值。
    :raises Exception: 不主动抛出异常。
    """

    return build_entrypoint_context_slot_values(
        EntrypointContextSlotRequest(ticker=None)
    )


__all__: tuple[str, ...] = ("run_session_command",)
