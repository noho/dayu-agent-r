"""Web 抓取恢复语义模型。

该模块定义面向 LLM 的恢复动作与失败原因枚举，
避免在具体工具实现中散落硬编码字符串，便于跨工具复用。
"""

from __future__ import annotations

from typing import Optional

RECOVERY_CONTRACT_VERSION = "web_recovery_v1"

NEXT_ACTION_RETRY = "retry"
NEXT_ACTION_CHANGE_SOURCE = "change_source"
NEXT_ACTION_CONTINUE_WITHOUT_WEB = "continue_without_web"

ALLOWED_NEXT_ACTIONS = {
    NEXT_ACTION_RETRY,
    NEXT_ACTION_CHANGE_SOURCE,
    NEXT_ACTION_CONTINUE_WITHOUT_WEB,
}

REASON_REQUEST_TIMEOUT = "request_timeout"
REASON_HTTP_ERROR = "http_error"
REASON_BLOCKED_BY_SITE_POLICY = "blocked_by_site_policy"
REASON_REDIRECT_CHAIN_TOO_LONG = "redirect_chain_too_long"
REASON_CONTENT_CONVERSION_FAILED = "content_conversion_failed"
REASON_EMPTY_CONTENT = "empty_content"

ALLOWED_REASONS = {
    REASON_REQUEST_TIMEOUT,
    REASON_HTTP_ERROR,
    REASON_BLOCKED_BY_SITE_POLICY,
    REASON_REDIRECT_CHAIN_TOO_LONG,
    REASON_CONTENT_CONVERSION_FAILED,
    REASON_EMPTY_CONTENT,
}

_REASON_HINTS = {
    REASON_REQUEST_TIMEOUT: (
        "目标：尽快拿到当前网页。允许动作：重试一次。"
        "不允许：连续重试多次。下一步：先重试一次；若仍失败就换来源。"
    ),
    REASON_HTTP_ERROR: (
        "目标：确认当前链接是否可用。允许动作：检查链接或换来源。"
        "不允许：继续依赖当前失败页面。下一步：先检查链接；若仍失败就换来源。"
    ),
    REASON_BLOCKED_BY_SITE_POLICY: (
        "目标：回到可用来源。允许动作：直接换来源。"
        "不允许：继续依赖当前站点。下一步：换到其他来源页。"
    ),
    REASON_REDIRECT_CHAIN_TOO_LONG: (
        "目标：找到更稳定的入口页。允许动作：改用更稳定的同主题链接。"
        "不允许：继续依赖这条重定向链。下一步：换一个更稳定的来源链接。"
    ),
    REASON_CONTENT_CONVERSION_FAILED: (
        "目标：拿到可读正文。允许动作：换同主题的其他页面。"
        "不允许：继续依赖当前页面。下一步：换来源页。"
    ),
    REASON_EMPTY_CONTENT: (
        "目标：继续当前任务。允许动作：忽略这页并继续。"
        "不允许：把这页当事实来源。下一步：继续当前任务，但不要引用这页内容。"
    ),
}


def normalize_next_action(next_action: str) -> str:
    """规范化 next_action，防止返回值漂移。

    Args:
        next_action: 原始动作。

    Returns:
        合法动作；非法值降级为 ``change_source``。

    Raises:
        无。
    """

    if next_action in ALLOWED_NEXT_ACTIONS:
        return next_action
    return NEXT_ACTION_CHANGE_SOURCE


def normalize_reason(reason: str) -> str:
    """规范化 reason，防止返回值漂移。

    Args:
        reason: 原始原因。

    Returns:
        合法原因；非法值降级为 ``http_error``。

    Raises:
        无。
    """

    if reason in ALLOWED_REASONS:
        return reason
    return REASON_HTTP_ERROR


def build_hint(reason: str, *, fallback: Optional[str] = None) -> str:
    """根据 reason 生成面向 LLM 的简短提示。

    Args:
        reason: 失败原因。
        fallback: 可选兜底提示。

    Returns:
        对应 reason 的提示文案；未知 reason 时返回兜底文案。

    Raises:
        无。
    """

    normalized = normalize_reason(reason)
    if normalized in _REASON_HINTS:
        return _REASON_HINTS[normalized]
    return fallback or _REASON_HINTS[REASON_HTTP_ERROR]
