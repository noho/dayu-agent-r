"""Host 私有显式凭证清洗工具。

本模块只处理普通工具 payload 中的显式凭证字段。cursor、
``scope_token``、普通 ``token``、业务参数和业务结果都不是清洗触发条件。
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from dayu.contracts import JsonValue
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess

_SCRUBBED_CREDENTIAL_VALUE: str = "***"
_EXPLICIT_CREDENTIAL_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "api-key",
        "api key",
        "anthropic-api-key",
        "x-api-key",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "client_secret",
        "client-secret",
        "private_key",
        "private-key",
    }
)
_TEXT_CREDENTIAL_ASSIGNMENT_PATTERN: re.Pattern[str] = re.compile(
    r"\b(api(?:[_-]|\s+)?key|anthropic-api-key|x-api-key|authorization|cookie|"
    r"credentials?|password|passwd|client[_-]?secret|private[_-]?key)"
    r"\b(\s*[:=]\s*)([^\r\n,}&]+)",
    flags=re.IGNORECASE,
)


def scrub_explicit_credentials(payload: JsonValue) -> JsonValue:
    """递归清洗 JSON payload 中的显式凭证。

    :param payload: 任意 JSON 值。
    :returns: 清洗后的 JSON 值；结构保持不变，命中凭证的值替换为
        ``"***"``。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(payload, Mapping):
        scrubbed: dict[str, JsonValue] = {}
        for key, value in payload.items():
            if _is_explicit_credential_key(key):
                scrubbed[key] = _SCRUBBED_CREDENTIAL_VALUE
                continue
            scrubbed[key] = scrub_explicit_credentials(value)
        return scrubbed
    if isinstance(payload, list):
        return [scrub_explicit_credentials(item) for item in payload]
    if isinstance(payload, str):
        return _scrub_text_credential_assignments(payload)
    return payload


def scrub_tool_arguments(
    arguments: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """清洗普通工具调用参数中的显式凭证。

    :param arguments: 工具调用参数。
    :returns: 清洗后的参数映射。
    :raises Exception: 不主动抛出异常。
    """

    scrubbed = scrub_explicit_credentials(arguments)
    if isinstance(scrubbed, Mapping):
        return scrubbed
    return {}


def scrub_tool_execution_outcome(
    outcome: ToolExecutionOutcome,
) -> ToolExecutionOutcome:
    """清洗工具执行 outcome 中的显式凭证。

    :param outcome: 工具执行 outcome。
    :returns: 清洗后的 outcome；未命中时仍返回等价强类型对象。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        result = outcome.result
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=scrub_explicit_credentials(result.value),
                truncation=result.truncation,
                meta=result.meta,
            )
        )
    if isinstance(outcome, ToolFailedOutcome):
        result = outcome.result
        return ToolFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error=_scrub_text_credential_assignments(result.error),
                message=_scrub_text_credential_assignments(result.message),
                hint=(None if result.hint is None else _scrub_text_credential_assignments(result.hint)),
                meta=result.meta,
            )
        )
    if isinstance(outcome, ToolAwaitingOutcome):
        return outcome
    return outcome


def _is_explicit_credential_key(key: str) -> bool:
    """判断字段名是否为显式凭证字段。

    :param key: JSON 对象字段名。
    :returns: 命中显式凭证字段时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return key.lower() in _EXPLICIT_CREDENTIAL_KEYS


def _scrub_text_credential_assignments(value: str) -> str:
    """清洗字符串内的显式凭证赋值片段。

    :param value: 待处理字符串。
    :returns: 清洗后的字符串。
    :raises Exception: 不主动抛出异常。
    """

    return _TEXT_CREDENTIAL_ASSIGNMENT_PATTERN.sub(
        rf"\1\2{_SCRUBBED_CREDENTIAL_VALUE}",
        value,
    )


__all__ = [
    "scrub_explicit_credentials",
    "scrub_tool_arguments",
    "scrub_tool_execution_outcome",
]
