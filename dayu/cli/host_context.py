"""CLI 到 Host public API 的上下文与幂等 id 构造 helper。

本模块只构造 Host public DTO 与 CLI-local 稳定 id，不调用 Host 方法、不读取
Host durable 状态，也不把 Host 内部治理 id 暴露为业务上下文。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from dayu.host.api import HostCallContext, OperationContext

CLI_ACTOR: str = "cli-user"
CLI_SOURCE: str = "dayu-cli"
CLI_PROMPT_COMMAND: str = "prompt"
CLI_PROMPT_OPERATION_KIND: str = "cli_prompt"
CLI_INTERACTIVE_COMMAND: str = "interactive"
CLI_INTERACTIVE_OPERATION_KIND: str = "cli_interactive"
CLI_SESSION_COMMAND: str = "session"
CLI_SESSION_OPERATION_KIND: str = "cli_session"
CLI_BUSINESS_DOMAIN: str = "fins"
CLI_TICKER_OBJECT_TYPE: str = "ticker"
CLI_PROMPT_SCENARIO: str = "prompt"
CLI_INTERACTIVE_SCENARIO: str = "interactive"
PROMPT_SESSION_SCOPE: str = "cli.prompt"
PROMPT_SLOT_KEY_PREFIX: str = "cli.prompt."
INTERACTIVE_SESSION_SCOPE: str = "cli.interactive"
INTERACTIVE_SLOT_KEY_PREFIX: str = "cli.interactive."
CLI_SIGINT_REASON: str = "cli_sigint"
_REQUEST_ID_OPERATION_SEPARATOR: str = ":"


@dataclass(frozen=True, slots=True)
class CliInvocation:
    """单次 CLI command invocation 的稳定身份。

    :param command_name: 当前 CLI 命令名。
    :param invocation_id: 本次 CLI 进程内的随机 invocation id。
    :param scenario: 当前 Agent scene id。
    :param display_user: LLM-facing 的人类可读用户名。
    :param ticker: 用户显式提供的业务主体；未提供时为 ``None``。
    :param correlation_id: 同一 CLI invocation 内 Host 调用共享的关联 id。
    """

    command_name: str
    invocation_id: str
    scenario: str
    display_user: str
    ticker: str | None
    correlation_id: str


def new_cli_invocation(
    *,
    command_name: str,
    scenario: str,
    display_user: str,
    ticker: str | None,
) -> CliInvocation:
    """创建单次 CLI invocation 身份。

    :param command_name: 当前 CLI 命令名。
    :param scenario: 当前 Agent scene id。
    :param display_user: 人类可读用户名。
    :param ticker: 用户显式提供的业务主体；未提供时为 ``None``。
    :returns: CLI invocation 身份。
    :raises ValueError: 必填文本为空时抛出。
    """

    _require_non_empty_text(command_name, field_name="command_name")
    _require_non_empty_text(scenario, field_name="scenario")
    _require_non_empty_text(display_user, field_name="display_user")
    invocation_id = uuid4().hex
    return CliInvocation(
        command_name=command_name,
        invocation_id=invocation_id,
        scenario=scenario,
        display_user=display_user,
        ticker=_optional_stripped_text(ticker, field_name="ticker"),
        correlation_id=f"dayu-cli:{command_name}:{invocation_id}",
    )


def prompt_slot_key(label: str) -> str:
    """把用户 label 映射为稳定 Host slot key。

    :param label: 用户通过 ``--label`` 传入的会话标签。
    :returns: 形如 ``cli.prompt.<label>`` 的 Host slot key。
    :raises ValueError: label 为空或仅包含空白时抛出。
    """

    stripped_label = _require_non_empty_text(label, field_name="label").strip()
    return f"{PROMPT_SLOT_KEY_PREFIX}{stripped_label}"


def interactive_slot_key(label: str) -> str:
    """把 interactive 用户 label 映射为稳定 Host slot key。

    :param label: 用户通过 ``--label`` 传入的会话标签。
    :returns: 形如 ``cli.interactive.<label>`` 的 Host slot key。
    :raises ValueError: label 为空或仅包含空白时抛出。
    """

    stripped_label = _require_non_empty_text(label, field_name="label").strip()
    return f"{INTERACTIVE_SLOT_KEY_PREFIX}{stripped_label}"


def prompt_create_session_client_request_id(invocation: CliInvocation) -> str:
    """构造 prompt create-session 幂等 id。

    :param invocation: 当前 CLI invocation 身份。
    :returns: Host create-session client_request_id。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"dayu-cli:{invocation.command_name}:{invocation.invocation_id}:"
        "session:create"
    )


def interactive_create_session_client_request_id(invocation: CliInvocation) -> str:
    """构造 interactive create-session 幂等 id。

    :param invocation: 当前 CLI invocation 身份。
    :returns: Host create-session client_request_id。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"dayu-cli:{invocation.command_name}:{invocation.invocation_id}:"
        "session:create"
    )


def session_purge_client_request_id(invocation: CliInvocation) -> str:
    """构造 session purge 幂等 id。

    :param invocation: 当前 CLI invocation 身份。
    :returns: Host purge-session client_request_id。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"dayu-cli:{invocation.command_name}:{invocation.invocation_id}:"
        "session:purge"
    )


def prompt_submit_client_request_id(invocation: CliInvocation, *, turn_index: int) -> str:
    """构造 prompt submit 幂等 id。

    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: prompt one-shot 的轮次序号。
    :returns: Host submit client_request_id。
    :raises ValueError: 轮次序号小于 1 时抛出。
    """

    _require_positive_turn_index(turn_index)
    return (
        f"dayu-cli:{invocation.command_name}:{invocation.invocation_id}:"
        f"turn-{turn_index}:submit"
    )


def interactive_submit_client_request_id(
    invocation: CliInvocation, *, turn_index: int
) -> str:
    """构造 interactive 单轮 submit 幂等 id。

    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: interactive 轮次序号。
    :returns: Host submit client_request_id。
    :raises ValueError: 轮次序号小于 1 时抛出。
    """

    _require_positive_turn_index(turn_index)
    return (
        f"dayu-cli:{invocation.command_name}:{invocation.invocation_id}:"
        f"turn-{turn_index}:submit"
    )


def prompt_cancel_client_request_id(
    invocation: CliInvocation, *, turn_index: int, run_id: str
) -> str:
    """构造 prompt cancel 幂等 id。

    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: prompt one-shot 的轮次序号。
    :param run_id: 待取消的 Host Run id。
    :returns: Host cancel client_request_id；同一 Run 重复取消应复用该值。
    :raises ValueError: 轮次序号或 run id 非法时抛出。
    """

    _require_positive_turn_index(turn_index)
    _require_non_empty_text(run_id, field_name="run_id")
    return (
        f"dayu-cli:{invocation.command_name}:{invocation.invocation_id}:"
        f"turn-{turn_index}:run-{run_id}:cancel:{CLI_SIGINT_REASON}"
    )


def interactive_cancel_client_request_id(
    invocation: CliInvocation, *, turn_index: int, run_id: str
) -> str:
    """构造 interactive 单轮 cancel 幂等 id。

    :param invocation: 当前 CLI invocation 身份。
    :param turn_index: interactive 轮次序号。
    :param run_id: 待取消的 Host Run id。
    :returns: Host cancel client_request_id；同一 Run 重复取消应复用该值。
    :raises ValueError: 轮次序号或 run id 非法时抛出。
    """

    _require_positive_turn_index(turn_index)
    _require_non_empty_text(run_id, field_name="run_id")
    return (
        f"dayu-cli:{invocation.command_name}:{invocation.invocation_id}:"
        f"turn-{turn_index}:run-{run_id}:cancel:{CLI_SIGINT_REASON}"
    )


def build_prompt_host_context(
    invocation: CliInvocation,
    *,
    operation: str,
) -> HostCallContext:
    """构造 prompt 命令调用 Host public API 的上下文。

    :param invocation: 当前 CLI invocation 身份。
    :param operation: 当前 Host API 操作短名。
    :returns: HostCallContext。
    :raises ValueError: operation 为空时抛出。
    """

    return _build_host_context(
        invocation,
        operation=operation,
        operation_kind=CLI_PROMPT_OPERATION_KIND,
    )


def build_interactive_host_context(
    invocation: CliInvocation,
    *,
    operation: str,
) -> HostCallContext:
    """构造 interactive 命令调用 Host public API 的上下文。

    :param invocation: 当前 CLI invocation 身份。
    :param operation: 当前 Host API 操作短名。
    :returns: HostCallContext。
    :raises ValueError: operation 为空时抛出。
    """

    return _build_host_context(
        invocation,
        operation=operation,
        operation_kind=CLI_INTERACTIVE_OPERATION_KIND,
    )


def build_session_host_context(
    invocation: CliInvocation,
    *,
    operation: str,
) -> HostCallContext:
    """构造 session 命令调用 Host public API 的上下文。

    :param invocation: 当前 CLI invocation 身份。
    :param operation: 当前 Host API 操作短名。
    :returns: HostCallContext。
    :raises ValueError: operation 为空时抛出。
    """

    return _build_host_context(
        invocation,
        operation=operation,
        operation_kind=CLI_SESSION_OPERATION_KIND,
    )


def _build_host_context(
    invocation: CliInvocation,
    *,
    operation: str,
    operation_kind: str,
) -> HostCallContext:
    """按 CLI invocation 构造 Host public 调用上下文。

    :param invocation: 当前 CLI invocation 身份。
    :param operation: 当前 Host API 操作短名。
    :param operation_kind: Host operation kind。
    :returns: HostCallContext。
    :raises ValueError: operation 或 operation_kind 为空时抛出。
    """

    operation_name = _require_non_empty_text(operation, field_name="operation")
    checked_operation_kind = _require_non_empty_text(
        operation_kind,
        field_name="operation_kind",
    )
    business_object_type = None
    business_object_id = None
    if invocation.ticker is not None:
        business_object_type = CLI_TICKER_OBJECT_TYPE
        business_object_id = invocation.ticker
    return HostCallContext(
        actor=CLI_ACTOR,
        source=CLI_SOURCE,
        request_id=_new_host_request_id(
            command_name=invocation.command_name,
            operation=operation_name,
        ),
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name=f"dayu_cli.{invocation.command_name}.{operation_name}",
            operation_kind=checked_operation_kind,
            business_domain=CLI_BUSINESS_DOMAIN,
            business_object_type=business_object_type,
            business_object_id=business_object_id,
            scenario=invocation.scenario,
            correlation_id=invocation.correlation_id,
        ),
    )


def _new_host_request_id(*, command_name: str, operation: str) -> str:
    """构造单次 Host API 调用的追踪 request id。

    :param command_name: 当前 CLI 命令名。
    :param operation: 当前 Host API 操作短名。
    :returns: HostCallContext.request_id。
    :raises Exception: 不主动抛出异常。
    """

    return _REQUEST_ID_OPERATION_SEPARATOR.join(
        ("dayu-cli", command_name, uuid4().hex, operation)
    )


def _optional_stripped_text(value: str | None, *, field_name: str) -> str | None:
    """校验并裁剪可选文本。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :returns: 裁剪后的文本；未提供时返回 ``None``。
    :raises ValueError: 文本为空白时抛出。
    """

    if value is None:
        return None
    return _require_non_empty_text(value, field_name=field_name).strip()


def _require_non_empty_text(value: str, *, field_name: str) -> str:
    """校验字符串字段非空。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :returns: 原始文本。
    :raises ValueError: 文本为空或仅包含空白时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")
    return value


def _require_positive_turn_index(value: int) -> None:
    """校验 CLI turn index 为正整数。

    :param value: 待校验轮次序号。
    :returns: ``None``。
    :raises ValueError: 轮次序号小于 1 时抛出。
    """

    if value < 1:
        raise ValueError("turn_index must be >= 1")


__all__: tuple[str, ...] = (
    "CLI_INTERACTIVE_COMMAND",
    "CLI_INTERACTIVE_SCENARIO",
    "CLI_PROMPT_COMMAND",
    "CLI_PROMPT_SCENARIO",
    "CLI_SESSION_COMMAND",
    "CLI_SIGINT_REASON",
    "CliInvocation",
    "INTERACTIVE_SESSION_SCOPE",
    "PROMPT_SESSION_SCOPE",
    "build_interactive_host_context",
    "build_prompt_host_context",
    "build_session_host_context",
    "interactive_cancel_client_request_id",
    "interactive_create_session_client_request_id",
    "interactive_slot_key",
    "interactive_submit_client_request_id",
    "new_cli_invocation",
    "prompt_cancel_client_request_id",
    "prompt_create_session_client_request_id",
    "prompt_slot_key",
    "prompt_submit_client_request_id",
    "session_purge_client_request_id",
)
