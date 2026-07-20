"""网页挑战页/访问门禁识别模块。

该模块集中维护 `fetch_web_page` 使用的 challenge/access-gate 判定逻辑，
避免检测规则散落在 `requests`、Playwright 与错误处理分支中，方便后续扩展。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Collection

import requests

_EMPTY_CONTENT_MIN_CHARS = 5

_CONTENT_CHALLENGE_PATTERNS: tuple[tuple[str, str], ...] = (
    # --- Cloudflare（英文 + 本地化中文变体） ---
    ("just a moment", "content:just a moment"),
    ("请稍候", "content:cf_challenge_zh"),
    ("执行安全验证", "content:cf_security_verification_zh"),
    ("checking your browser", "content:checking your browser"),
    ("checking if the site connection is secure", "content:cf_connection_check"),
    ("此网站使用安全服务", "content:cf_security_service_zh"),
    # --- 通用反爬/访问门禁 ---
    ("attention required", "content:attention required"),
    ("verify you are human", "content:verify you are human"),
    ("are you a robot", "content:are you a robot"),
    ("not a robot", "content:not a robot"),
    ("bot challenge", "content:bot challenge"),
    ("access denied", "content:access denied"),
    ("unusual activity", "content:unusual activity"),
    ("captcha-delivery", "content:captcha-delivery"),
    (
        "please enable js and disable any ad blocker",
        "content:please enable js and disable any ad blocker",
    ),
    ("please turn javascript on", "content:please turn javascript on"),
    # --- 中国 WAF ---
    ("aliyun_waf", "content:aliyun_waf"),
    ("_waf_ticket", "content:_waf_ticket"),
    ("_waf_sess", "content:_waf_sess"),
    ("eo_bot", "content:eo_bot"),
    ("antibot", "content:antibot"),
    # --- 特定厂商指纹 ---
    ("/u21pn7x6/", "content:/u21pn7x6/"),
    ("cf-please-wait", "content:cf-please-wait"),
    ("challenges.cloudflare.com", "content:challenges.cloudflare.com"),
)
_CHALLENGE_INFRA_SIGNALS = frozenset(
    {
        "header:cf-ray",
        "server:cloudflare",
        "server:akamai",
    }
)
_CHALLENGE_VENDOR_HEADER_SIGNALS = frozenset(
    {
        "header:x-datadome",
        "header:x-dd-b",
    }
)
_BOT_CHALLENGE_HTTP_STATUS = frozenset({401, 403, 429, 503})
_STRONG_VENDOR_CONTENT_SIGNALS = frozenset(
    {
        "content:cf_challenge_zh",
        "content:cf_security_verification_zh",
        "content:cf_connection_check",
        "content:cf_security_service_zh",
        "content:captcha-delivery",
        "content:aliyun_waf",
        "content:_waf_ticket",
        "content:_waf_sess",
        "content:eo_bot",
        "content:antibot",
        "content:/u21pn7x6/",
        "content:cf-please-wait",
        "content:challenges.cloudflare.com",
    }
)


class BotChallengeDecision(str, Enum):
    """挑战页证据强度的封闭判定。"""

    NONE = "none"
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"


class BotChallengeEvidenceClass(str, Enum):
    """挑战页证据来源的封闭分类。"""

    STRONG_VENDOR_CONTENT = "strong_vendor_content"
    BROAD_CONTENT = "broad_content"
    VENDOR_GATE_HEADER = "vendor_gate_header"
    INFRASTRUCTURE_HEADER = "infrastructure_header"
    COOKIE = "cookie"
    ERROR_STATUS = "error_status"


class ChallengeFallbackAction(str, Enum):
    """confirmed challenge 的唯一 fallback 动作。"""

    CONTINUE = "continue"
    TRY_BROWSER = "try_browser"
    FAIL_BLOCKED = "fail_blocked"


@dataclass(frozen=True)
class BotChallengeDetectionResult:
    """挑战页检测结果。"""

    decision: BotChallengeDecision
    challenge_signals: tuple[str, ...]
    evidence_classes: tuple[BotChallengeEvidenceClass, ...]


def detect_bot_challenge(
    *,
    response: requests.Response | None,
    response_headers: Mapping[str, str] | None = None,
    http_status: int | None = None,
    content_text: str,
) -> BotChallengeDetectionResult:
    """检测响应是否疑似挑战页/反爬页。

    Args:
        response: 可选 HTTP 响应对象；存在时优先读取其中的头部与状态码。
        response_headers: 独立响应头；用于无 `requests.Response` 的场景。
        http_status: 独立状态码；用于无 `requests.Response` 的场景。
        content_text: 待检测文本，可为 Markdown、原始 HTML、`response.text` 或文本摘录。

    Returns:
        挑战页检测结果。

    Raises:
        无。
    """

    signals = _collect_bot_challenge_signals(
        response=response,
        response_headers=response_headers,
        http_status=http_status,
        content_text=content_text,
    )
    status_code = response.status_code if response is not None else http_status
    normalized_signals = tuple(sorted(set(signals)))
    decision = decide_bot_challenge(
        signals=normalized_signals,
        http_status=status_code,
    )
    return BotChallengeDetectionResult(
        decision=decision,
        challenge_signals=normalized_signals,
        evidence_classes=_classify_evidence(
            signals=normalized_signals,
            http_status=status_code,
        ),
    )


def decide_bot_challenge(
    *,
    signals: Collection[str],
    http_status: int | None,
) -> BotChallengeDecision:
    """根据挑战信号强弱与状态码判断是否应视为反爬页。

    Args:
        signals: 已收集到的信号集合。
        http_status: 当前响应状态码。

    Returns:
        ``none``、``suspected`` 或 ``confirmed`` 封闭判定。

    Raises:
        无。
    """

    signal_set = set(signals)
    if not signal_set:
        return BotChallengeDecision.NONE

    content_signals = {
        signal
        for signal in signal_set
        if signal.startswith("content:") and signal != "content:empty_near_error"
    }
    if content_signals & _STRONG_VENDOR_CONTENT_SIGNALS:
        return BotChallengeDecision.CONFIRMED

    broad_content_signals = content_signals - _STRONG_VENDOR_CONTENT_SIGNALS
    vendor_gate_headers = signal_set & _CHALLENGE_VENDOR_HEADER_SIGNALS
    cookie_signals = {signal for signal in signal_set if signal.startswith("cookie:")}
    has_error_status = http_status in _BOT_CHALLENGE_HTTP_STATUS
    if len(broad_content_signals) >= 2:
        return BotChallengeDecision.CONFIRMED
    if broad_content_signals and (vendor_gate_headers or has_error_status):
        return BotChallengeDecision.CONFIRMED
    if vendor_gate_headers and (cookie_signals or has_error_status):
        return BotChallengeDecision.CONFIRMED
    if cookie_signals and has_error_status:
        return BotChallengeDecision.CONFIRMED
    return BotChallengeDecision.SUSPECTED


def challenge_fallback_action(
    *,
    decision: BotChallengeDecision,
    browser_available: bool,
) -> ChallengeFallbackAction:
    """按 challenge decision 与 browser 可用性决定唯一 fallback 动作。

    Args:
        decision: challenge detector 的封闭判定。
        browser_available: 当前调用是否仍可尝试安全 browser profile。

    Returns:
        继续普通流程、尝试 browser 或稳定 blocked 失败。

    Raises:
        无。
    """

    if decision is not BotChallengeDecision.CONFIRMED:
        return ChallengeFallbackAction.CONTINUE
    if browser_available:
        return ChallengeFallbackAction.TRY_BROWSER
    return ChallengeFallbackAction.FAIL_BLOCKED


def _classify_evidence(
    *,
    signals: Collection[str],
    http_status: int | None,
) -> tuple[BotChallengeEvidenceClass, ...]:
    """把原始 detector signals 投影为封闭 evidence classes。

    Args:
        signals: 已去重的 detector signals。
        http_status: 当前响应状态码。

    Returns:
        稳定排序、去重后的 evidence classes。

    Raises:
        无。
    """

    signal_set = set(signals)
    evidence: set[BotChallengeEvidenceClass] = set()
    content_signals = {
        signal
        for signal in signal_set
        if signal.startswith("content:") and signal != "content:empty_near_error"
    }
    if content_signals & _STRONG_VENDOR_CONTENT_SIGNALS:
        evidence.add(BotChallengeEvidenceClass.STRONG_VENDOR_CONTENT)
    if (content_signals - _STRONG_VENDOR_CONTENT_SIGNALS) or "content:empty_near_error" in signal_set:
        evidence.add(BotChallengeEvidenceClass.BROAD_CONTENT)
    if signal_set & _CHALLENGE_VENDOR_HEADER_SIGNALS:
        evidence.add(BotChallengeEvidenceClass.VENDOR_GATE_HEADER)
    if signal_set & _CHALLENGE_INFRA_SIGNALS:
        evidence.add(BotChallengeEvidenceClass.INFRASTRUCTURE_HEADER)
    if any(signal.startswith("cookie:") for signal in signal_set):
        evidence.add(BotChallengeEvidenceClass.COOKIE)
    if signal_set and http_status in _BOT_CHALLENGE_HTTP_STATUS:
        evidence.add(BotChallengeEvidenceClass.ERROR_STATUS)
    return tuple(sorted(evidence, key=lambda item: item.value))


def _collect_bot_challenge_signals(
    *,
    response: requests.Response | None,
    response_headers: Mapping[str, str] | None,
    http_status: int | None,
    content_text: str,
) -> list[str]:
    """收集挑战页判定信号。

    Args:
        response: 可选 HTTP 响应对象。
        response_headers: 独立响应头。
        http_status: 独立状态码。
        content_text: 待检测的正文或原始页面文本。

    Returns:
        原始信号列表，允许重复；调用方可自行去重排序。

    Raises:
        无。
    """

    signals: list[str] = []
    headers = response.headers if response is not None else (response_headers or {})
    server = str(headers.get("server", "")).lower()
    set_cookie = str(headers.get("set-cookie", "")).lower()
    header_names = {str(key).lower() for key in headers.keys()}
    if "cf-ray" in header_names:
        signals.append("header:cf-ray")
    if "x-datadome" in header_names:
        signals.append("header:x-datadome")
    if "x-dd-b" in header_names:
        signals.append("header:x-dd-b")
    if "__cf_bm" in set_cookie:
        signals.append("cookie:__cf_bm")
    if "datadome" in set_cookie:
        signals.append("cookie:datadome")
    if "cloudflare" in server:
        signals.append("server:cloudflare")
    if "akamai" in server:
        signals.append("server:akamai")

    normalized_text = str(content_text or "").lower()
    for pattern, signal in _CONTENT_CHALLENGE_PATTERNS:
        if pattern in normalized_text:
            signals.append(signal)

    if len(normalized_text.strip()) < _EMPTY_CONTENT_MIN_CHARS:
        status_code = response.status_code if response is not None else http_status
        if status_code in _BOT_CHALLENGE_HTTP_STATUS:
            signals.append("content:empty_near_error")

    return signals
