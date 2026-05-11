"""Host 私有 ordinary tool result 截断 hint helper。

本模块只处理 Host RuntimeTruncateManager 注入到
``ToolResultSuccess.value`` 的普通 JSON payload。它不是公共契约，不向
Engine 暴露截断类型，也不持有 cursor registry 状态。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue

TRUNCATION_FIELD: str = "truncation"
TRUNCATION_HAS_MORE_FIELD: str = "has_more"
TRUNCATION_NEXT_ACTION_FIELD: str = "next_action"
TRUNCATION_FETCH_MORE_ARGS_FIELD: str = "fetch_more_args"
TRUNCATION_TTL_SECONDS_FIELD: str = "ttl_seconds"
FETCH_MORE_CURSOR_FIELD: str = "cursor"
FETCH_MORE_SCOPE_TOKEN_FIELD: str = "scope_token"
FETCH_MORE_LIMIT_FIELD: str = "limit"
FETCH_MORE_ACTION_NAME: str = "fetch_more"
CONTENT_FIELD: str = "content"


@dataclass(frozen=True, slots=True)
class ToolResultTruncationHint:
    """Host ordinary tool result 截断 hint。

    :param cursor: 单次有效的补读 cursor 原文。
    :param scope_token: 单次有效的补读 scope token。
    :param has_more: 是否仍有后续数据。
    :param limit: 建议 ``fetch_more`` 单次读取上限；无上限为 ``None``。
    :param ttl_seconds: cursor 有效期秒数；无明确 TTL 为 ``None``。
    """

    cursor: str
    scope_token: str
    has_more: bool
    limit: int | None
    ttl_seconds: int | None


def inject_truncation_hint(
    *,
    value: JsonValue,
    hint: ToolResultTruncationHint,
) -> JsonValue:
    """把截断 hint 注入普通工具成功 payload。

    :param value: 原始工具成功值。
    :param hint: Host 私有截断 hint。
    :returns: 注入 ``truncation`` 后的 JSON 值；原值为 object 且没有
        ``truncation`` 字段时顶层追加；已有同名业务字段或原值非 object
        时包装为 ``{"content": value, "truncation": ...}``。
    :raises Exception: 不主动抛出异常。
    """

    truncation = build_truncation_payload(hint)
    if isinstance(value, Mapping):
        if TRUNCATION_FIELD in value:
            return {
                CONTENT_FIELD: dict(value),
                TRUNCATION_FIELD: truncation,
            }
        projected: dict[str, JsonValue] = dict(value)
        projected[TRUNCATION_FIELD] = truncation
        return projected
    return {
        CONTENT_FIELD: value,
        TRUNCATION_FIELD: truncation,
    }


def build_truncation_payload(
    hint: ToolResultTruncationHint,
) -> Mapping[str, JsonValue]:
    """构造 LLM-facing 截断 hint payload。

    :param hint: Host 私有截断 hint。
    :returns: 可放入普通工具结果 ``truncation`` 字段的 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    payload: dict[str, JsonValue] = {
        TRUNCATION_HAS_MORE_FIELD: hint.has_more,
    }
    if hint.has_more:
        fetch_more_args: dict[str, JsonValue] = {
            FETCH_MORE_CURSOR_FIELD: hint.cursor,
            FETCH_MORE_SCOPE_TOKEN_FIELD: hint.scope_token,
        }
        if hint.limit is not None:
            fetch_more_args[FETCH_MORE_LIMIT_FIELD] = hint.limit
        payload[TRUNCATION_NEXT_ACTION_FIELD] = FETCH_MORE_ACTION_NAME
        payload[TRUNCATION_FETCH_MORE_ARGS_FIELD] = fetch_more_args
        if hint.ttl_seconds is not None:
            payload[TRUNCATION_TTL_SECONDS_FIELD] = hint.ttl_seconds
    return payload


def extract_truncation_hint(value: JsonValue) -> ToolResultTruncationHint | None:
    """从普通工具成功 payload 中提取截断 hint。

    :param value: 工具成功 ``value``。
    :returns: 提取成功返回 hint；不存在或结构非法时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(value, Mapping):
        return None
    payload = value.get(TRUNCATION_FIELD)
    if not isinstance(payload, Mapping):
        return None
    has_more = payload.get(TRUNCATION_HAS_MORE_FIELD)
    if not isinstance(has_more, bool):
        return None
    if not has_more:
        return None
    fetch_more_args = payload.get(TRUNCATION_FETCH_MORE_ARGS_FIELD)
    cursor: str = ""
    scope_token: str = ""
    limit: int | None = None
    if isinstance(fetch_more_args, Mapping):
        cursor_value = fetch_more_args.get(FETCH_MORE_CURSOR_FIELD)
        scope_token_value = fetch_more_args.get(FETCH_MORE_SCOPE_TOKEN_FIELD)
        limit_value = fetch_more_args.get(FETCH_MORE_LIMIT_FIELD)
        if isinstance(cursor_value, str):
            cursor = cursor_value
        if isinstance(scope_token_value, str):
            scope_token = scope_token_value
        if isinstance(limit_value, int) and not isinstance(limit_value, bool):
            limit = limit_value
    if cursor == "" or scope_token == "":
        return None
    ttl_value = payload.get(TRUNCATION_TTL_SECONDS_FIELD)
    ttl_seconds: int | None = None
    if isinstance(ttl_value, int) and not isinstance(ttl_value, bool):
        ttl_seconds = ttl_value
    return ToolResultTruncationHint(
        cursor=cursor,
        scope_token=scope_token,
        has_more=has_more,
        limit=limit,
        ttl_seconds=ttl_seconds,
    )


__all__: list[str] = []
