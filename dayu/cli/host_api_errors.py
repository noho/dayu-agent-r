"""CLI HostApiError 展示与退出码映射。

本模块只拥有 ``HostApiError`` 在 CLI stderr 中的用户可见文本，以及对应
process exit code 的映射策略。Host 仍然拥有结构化错误事实与 durable
状态；本模块不读取 Host 内部存储，也不改变 Service / Host public API。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from dayu.cli.exit_codes import EXIT_FAILURE, EXIT_USAGE_ERROR
from dayu.host.api import HostApiError, HostApiErrorCode

_HOST_ERROR_TEMPLATE: Final[str] = "host_code={code} host_message={message}"


@dataclass(frozen=True, slots=True)
class CliHostApiErrorTarget:
    """CLI HostApiError 可见目标上下文。

    :param selector: 用户输入的 selector 可读摘要；无 selector 时为 ``None``。
    :param session_id: 已解析出的 Host Session id；未解析时为 ``None``。
    :param explicit_session_id_selector: 错误是否属于用户显式 ``--session-id``
        selector 所选目标。
    :param resolved_from_label: 错误是否发生在 label selector 已解析成
        Session id 之后。
    """

    selector: str | None = None
    session_id: str | None = None
    explicit_session_id_selector: bool = False
    resolved_from_label: bool = False


def host_api_error_context(error: HostApiError) -> str:
    """格式化 HostApiError 的统一 code/message 核心文本。

    :param error: Host public API 结构化错误。
    :returns: 用户可见 Host 错误核心上下文。
    :raises Exception: 不主动抛出异常。
    """

    return _HOST_ERROR_TEMPLATE.format(code=error.code.value, message=error.message)


def format_host_api_error(
    command_name: str,
    error: HostApiError,
    *,
    action: str | None = None,
    target: CliHostApiErrorTarget | None = None,
) -> str:
    """格式化 CLI HostApiError 完整错误文本。

    :param command_name: CLI command 名称，不包含 ``dayu-cli`` 前缀。
    :param error: Host public API 结构化错误。
    :param action: command 下的动作名；没有子动作时为 ``None``。
    :param target: 可选用户选择目标上下文。
    :returns: stderr 可直接输出的错误文本。
    :raises Exception: 不主动抛出异常。
    """

    prefix = f"dayu-cli {command_name}"
    if action is not None:
        prefix = f"{prefix} {action}"
    context_parts: list[str] = []
    if target is not None:
        if target.selector is not None:
            context_parts.append(f"selector={target.selector}")
        if target.session_id is not None:
            context_parts.append(f"session_id={target.session_id}")
    context_parts.append(host_api_error_context(error))
    return f"{prefix}: {' '.join(context_parts)}"


def exit_code_for_host_api_error(
    error: HostApiError,
    *,
    target: CliHostApiErrorTarget | None = None,
) -> int:
    """把 HostApiError 映射为 CLI 退出码。

    :param error: Host public API 结构化错误。
    :param target: 可选用户选择目标上下文。
    :returns: CLI 退出码。
    :raises Exception: 不主动抛出异常。
    """

    if (
        error.code is HostApiErrorCode.NOT_FOUND
        and target is not None
        and target.explicit_session_id_selector
    ):
        return EXIT_USAGE_ERROR
    return EXIT_FAILURE


__all__: tuple[str, ...] = (
    "CliHostApiErrorTarget",
    "exit_code_for_host_api_error",
    "format_host_api_error",
    "host_api_error_context",
)
