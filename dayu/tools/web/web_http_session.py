"""网页抓取的 Session 与 timeout 基础设施。

本模块只承载 requests Session 复用、重试策略与 tool deadline 相关的
超时预算解析，不包含网页抓取编排、内容转换或浏览器回退逻辑。
"""

from __future__ import annotations

import time
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_RETRY_TOTAL = 3
_RETRY_CONNECT = 3
_RETRY_READ = 3
_RETRY_BACKOFF_FACTOR = 0.8
_RETRY_STATUS_FORCELIST = (429, 500, 502, 503, 504)
_MAX_REDIRECTS = 8
_MIN_TIMEOUT_BUDGET_SECONDS = 0.05

_WEB_SESSION: requests.Session | None = None
_WEB_NO_RETRY_SESSION: requests.Session | None = None
_WEB_SESSION_LOCK = Lock()


def _create_retry_session() -> requests.Session:
    """创建带重试策略的会话对象。

    Args:
        无。

    Returns:
        复用连接池和 Cookie 的 `requests.Session` 实例。

    Raises:
        无。
    """

    session = requests.Session()
    retry = Retry(
        total=_RETRY_TOTAL,
        connect=_RETRY_CONNECT,
        read=_RETRY_READ,
        status_forcelist=_RETRY_STATUS_FORCELIST,
        allowed_methods=frozenset({"GET", "HEAD"}),
        backoff_factor=_RETRY_BACKOFF_FACTOR,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.max_redirects = _MAX_REDIRECTS
    return session


def _create_no_retry_session(*, source_session: requests.Session | None = None) -> requests.Session:
    """创建禁用自动重试的会话对象。

    Args:
        source_session: 可选源会话；若提供则复用其 headers/cookies/max_redirects。

    Returns:
        不带 urllib3 自动重试的 `requests.Session`。

    Raises:
        无。
    """

    session = requests.Session()
    if isinstance(source_session, requests.Session):
        session.headers.update(source_session.headers)
        session.cookies.update(source_session.cookies)
        session.max_redirects = getattr(source_session, "max_redirects", _MAX_REDIRECTS)
    else:
        session.max_redirects = _MAX_REDIRECTS

    retry = Retry(
        total=0,
        connect=0,
        read=0,
        redirect=0,
        status=0,
        allowed_methods=frozenset({"GET", "HEAD"}),
        backoff_factor=0.0,
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _get_web_session() -> requests.Session:
    """获取全局复用 Session。

    Args:
        无。

    Returns:
        全局共享的 `requests.Session`。

    Raises:
        无。
    """

    global _WEB_SESSION
    if _WEB_SESSION is not None:
        return _WEB_SESSION
    with _WEB_SESSION_LOCK:
        if _WEB_SESSION is None:
            _WEB_SESSION = _create_retry_session()
    return _WEB_SESSION


def _get_no_retry_web_session() -> requests.Session:
    """获取全局复用的无重试 Session。

    Args:
        无。

    Returns:
        共享的无自动重试 `requests.Session`。

    Raises:
        无。
    """

    global _WEB_NO_RETRY_SESSION
    if _WEB_NO_RETRY_SESSION is not None:
        return _WEB_NO_RETRY_SESSION
    with _WEB_SESSION_LOCK:
        if _WEB_NO_RETRY_SESSION is None:
            _WEB_NO_RETRY_SESSION = _create_no_retry_session()
    return _WEB_NO_RETRY_SESSION


def _safe_timeout(timeout_seconds: float) -> float:
    """规范化超时参数。

    Args:
        timeout_seconds: 原始超时秒数。

    Returns:
        有效的超时值。

    Raises:
        无。
    """

    return max(1.0, float(timeout_seconds))


def _normalize_timeout_budget(timeout_budget: float | None) -> float | None:
    """规范化工具总预算秒数。

    Args:
        timeout_budget: Runner 注入的单次 tool call 总预算。

    Returns:
        规范化后的预算秒数；若未配置则返回 `None`。

    Raises:
        无。
    """

    if timeout_budget is None:
        return None
    return max(0.0, float(timeout_budget))


def _compute_deadline_monotonic(timeout_budget: float | None) -> float | None:
    """基于工具总预算计算当前调用的单调时钟 deadline。

    Args:
        timeout_budget: Runner 注入的单次 tool call 总预算。

    Returns:
        当前调用的 deadline；若未配置预算则返回 `None`。

    Raises:
        无。
    """

    normalized_budget = _normalize_timeout_budget(timeout_budget)
    if normalized_budget is None:
        return None
    return time.monotonic() + normalized_budget


def _resolve_timeout_budget(
    timeout_seconds: float,
    *,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    reserve_seconds: float = 0.0,
) -> float:
    """结合工具总预算与当前剩余时间，解析本阶段允许使用的 timeout。

    Args:
        timeout_seconds: 配置层或调用方声明的基础超时。
        timeout_budget: Runner 注入的单次 tool call 总预算。
        deadline_monotonic: 当前工具调用的单调时钟 deadline。
        reserve_seconds: 需要为后续阶段预留的秒数。

    Returns:
        当前阶段可用的 timeout 秒数。

    Raises:
        requests.Timeout: 当当前工具剩余预算已耗尽时抛出。
    """

    configured_timeout = _safe_timeout(timeout_seconds)
    normalized_budget = _normalize_timeout_budget(timeout_budget)
    if deadline_monotonic is None:
        if normalized_budget is None:
            return configured_timeout
        remaining_timeout = normalized_budget
    else:
        remaining_timeout = max(0.0, deadline_monotonic - time.monotonic())

    if normalized_budget is None and deadline_monotonic is None:
        return configured_timeout

    effective_timeout = min(configured_timeout, max(remaining_timeout - reserve_seconds, 0.0))
    if effective_timeout < _MIN_TIMEOUT_BUDGET_SECONDS:
        raise requests.Timeout("Tool execution deadline exceeded before web request started")
    return effective_timeout


def _prepare_call_session(
    session: requests.Session,
    *,
    timeout_budget: float | None = None,
) -> tuple[requests.Session, bool]:
    """按工具总预算选择当前调用应使用的 Session。

    当工具处于 Runner 的总预算约束内时，返回共享的无自动重试 Session，
    防止单次 HTTP 调用因 urllib3 retry/backoff 放大总耗时，同时保留跨次
    抓取的 Cookie / warmup 状态。

    Args:
        session: 默认复用 Session。
        timeout_budget: Runner 注入的单次 tool call 总预算。

    Returns:
        `(resolved_session, should_close)` 二元组。

    Raises:
        无。
    """

    if timeout_budget is None or not isinstance(session, requests.Session):
        return session, False
    return _get_no_retry_web_session(), False