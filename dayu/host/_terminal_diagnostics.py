"""Host terminal public projection 诊断文本 helper。

本模块只服务 Host public projection 边界，把 terminal payload 中已经存在
的诊断 id 格式化为展示后缀；不得写入 EventLog、payload store 或其它
durable truth。
"""

from __future__ import annotations

_TERMINAL_DIAGNOSTIC_ID_MAX_CHARS: int = 256


def _append_terminal_diagnostic_suffix(
    message: str | None,
    *,
    provider_request_id: str | None,
    client_correlation_id: str | None,
) -> str | None:
    """给 terminal 展示消息追加有界诊断 id 后缀。

    :param message: 原始 terminal 展示消息；无消息时为 ``None``。
    :param provider_request_id: provider 返回的 request id；无时为 ``None``。
    :param client_correlation_id: 本地客户端关联 id；无时为 ``None``。
    :returns: 追加诊断后缀后的展示消息；无消息且无诊断 id 时返回
        ``None``。
    :raises Exception: 不主动抛出异常。
    """

    suffix = _terminal_diagnostic_suffix(
        provider_request_id=provider_request_id,
        client_correlation_id=client_correlation_id,
    )
    if suffix is None:
        return message
    if message is None or message == "":
        return suffix
    return f"{message}\n{suffix}"


def _terminal_diagnostic_suffix(
    *,
    provider_request_id: str | None,
    client_correlation_id: str | None,
) -> str | None:
    """格式化 terminal public projection 诊断 id 后缀。

    :param provider_request_id: provider 返回的 request id；无时为 ``None``。
    :param client_correlation_id: 本地客户端关联 id；无时为 ``None``。
    :returns: 一行或多行诊断后缀；两个 id 都缺失时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    if provider_request_id is not None:
        parts.append(
            "provider_request_id="
            f"{_bounded_diagnostic_id(provider_request_id)}"
        )
    if client_correlation_id is not None:
        parts.append(
            "client_correlation_id="
            f"{_bounded_diagnostic_id(client_correlation_id)}"
        )
    if not parts:
        return None
    return "\n".join(parts)


def _bounded_diagnostic_id(value: str) -> str:
    """把诊断 id 限制在 terminal public projection 的展示长度内。

    :param value: 已通过 payload text 校验的诊断 id。
    :returns: 可展示的有界 id 文本。
    :raises Exception: 不主动抛出异常。
    """

    if len(value) <= _TERMINAL_DIAGNOSTIC_ID_MAX_CHARS:
        return value
    return value[:_TERMINAL_DIAGNOSTIC_ID_MAX_CHARS]
