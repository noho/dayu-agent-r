"""HTTP 状态 / 异常 → :class:`RunnerHTTPErrorCode` 中性分类。

本模块提供 :func:`classify_http_status` / :func:`classify_exception`
两个纯函数，把 provider 侧 HTTP 状态码与底层异常映射为
:class:`~dayu.engine.contracts.runner_events.RunnerHTTPErrorCode` 枚举。

分类规则（与 OLD ``async_openai_runner.py`` 一致）：

- HTTP ``429`` → :attr:`RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED`。
- HTTP ``500`` / ``502`` / ``503`` / ``504`` → :attr:`SERVER_ERROR`。
- HTTP ``4xx`` 其它 → :attr:`CLIENT_ERROR`（不可重试）。
- 其它 HTTP 状态（``1xx`` / ``3xx`` / 自定义）→ :attr:`UNKNOWN_HTTP_STATUS`。
- :class:`asyncio.TimeoutError` / :class:`aiohttp.ServerTimeoutError`
  / :class:`aiohttp.ClientPayloadError`（超时类）→ :attr:`TIMEOUT`。
- :class:`aiohttp.ClientConnectionError` / 其它 :class:`aiohttp.ClientError`
  → :attr:`NETWORK_ERROR`。
"""

from __future__ import annotations

import asyncio

import aiohttp

from dayu.engine.contracts.runner_events import RunnerHTTPErrorCode

_RETRYABLE_5XX: frozenset[int] = frozenset({500, 502, 503, 504})


def classify_http_status(http_status: int) -> RunnerHTTPErrorCode:
    """把 HTTP 状态码归类为中性 :class:`RunnerHTTPErrorCode`。

    :param http_status: provider 返回的 HTTP 状态码。
    :returns: 对应的中性错误枚举。
    """

    if http_status == 429:
        return RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED
    if http_status in _RETRYABLE_5XX:
        return RunnerHTTPErrorCode.SERVER_ERROR
    if 400 <= http_status < 500:
        return RunnerHTTPErrorCode.CLIENT_ERROR
    if 500 <= http_status < 600:
        # 非常规 5xx（如 599）也视为服务端错误。
        return RunnerHTTPErrorCode.SERVER_ERROR
    return RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS


def classify_exception(exc: BaseException) -> RunnerHTTPErrorCode:
    """把底层异常归类为中性 :class:`RunnerHTTPErrorCode`。

    :param exc: 触发的异常实例。
    :returns: 对应的中性错误枚举。

    :raises TypeError: 当 ``exc`` 既不是 :class:`asyncio.TimeoutError`
        也不是 :class:`aiohttp.ClientError` 时抛出，避免静默把无关异常
        归类为传输层错误。
    """

    if isinstance(exc, asyncio.TimeoutError):
        return RunnerHTTPErrorCode.TIMEOUT
    if isinstance(exc, aiohttp.ServerTimeoutError):
        return RunnerHTTPErrorCode.TIMEOUT
    if isinstance(exc, aiohttp.ClientConnectionError):
        return RunnerHTTPErrorCode.NETWORK_ERROR
    if isinstance(exc, aiohttp.ClientError):
        return RunnerHTTPErrorCode.NETWORK_ERROR
    raise TypeError(
        "classify_exception only accepts aiohttp.ClientError / "
        f"asyncio.TimeoutError; got {type(exc).__name__}"
    )


def is_retriable(error_code: RunnerHTTPErrorCode) -> bool:
    """判断中性错误码是否可重试。

    :param error_code: 中性错误枚举。
    :returns: 可重试返回 ``True``，否则 ``False``。

    可重试集合：``RATE_LIMIT_EXCEEDED`` / ``SERVER_ERROR`` /
    ``NETWORK_ERROR`` / ``TIMEOUT``。
    ``CLIENT_ERROR`` / ``UNKNOWN_HTTP_STATUS`` 不重试。
    """

    match error_code:
        case (
            RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED
            | RunnerHTTPErrorCode.SERVER_ERROR
            | RunnerHTTPErrorCode.NETWORK_ERROR
            | RunnerHTTPErrorCode.TIMEOUT
        ):
            return True
        case (
            RunnerHTTPErrorCode.CLIENT_ERROR
            | RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS
        ):
            return False


__all__ = ["classify_http_status", "classify_exception", "is_retriable"]
