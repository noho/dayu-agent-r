"""HTTP 状态 / 异常 → :class:`RunnerHTTPErrorCode` 中性分类。

本模块提供 :func:`classify_http_status` / :func:`classify_exception`
两个纯函数，把 provider 侧 HTTP 状态码与底层异常映射为
:class:`~dayu.engine.contracts.runner_events.RunnerHTTPErrorCode` 枚举。

分类规则（与 OLD ``async_openai_runner.py`` 一致）：

- HTTP ``408`` → :attr:`RunnerHTTPErrorCode.TIMEOUT`（OLD 视为可重试
  瞬时超时，归一到中性 ``TIMEOUT`` 类目，``http_status`` 仍保留 408）。
- HTTP ``429`` → :attr:`RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED`。
- HTTP ``500`` / ``502`` / ``503`` / ``504`` → :attr:`SERVER_ERROR`。
- HTTP ``4xx`` 其它 → :attr:`CLIENT_ERROR`（不可重试）。
- 其它 HTTP 状态（``1xx`` / ``3xx`` / 自定义）→ :attr:`UNKNOWN_HTTP_STATUS`。
- :class:`asyncio.TimeoutError` / :class:`aiohttp.ServerTimeoutError`
  → :attr:`TIMEOUT`。
- :class:`aiohttp.ClientConnectionError` / :class:`aiohttp.ClientPayloadError`
  / 其它 :class:`aiohttp.ClientError` → :attr:`NETWORK_ERROR`。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import assert_never

import aiohttp

from dayu.contracts import JsonValue
from dayu.engine.contracts.runner_events import RunnerHTTPErrorCode

_RETRYABLE_5XX: frozenset[int] = frozenset({500, 502, 503, 504})
_OPENAI_CONTEXT_LENGTH_ERROR_CODE: str = "context_length_exceeded"
_CONTEXT_OVERFLOW_MESSAGE_MARKERS: tuple[str, ...] = (
    "maximum context length is",
    "total message token length exceed model limit",
    "model's maximum context length",
    "range of input length should be",
    "model requires more context",
    "context length exceeded",
)


def classify_http_status(http_status: int) -> RunnerHTTPErrorCode:
    """把 HTTP 状态码归类为中性 :class:`RunnerHTTPErrorCode`。

    :param http_status: provider 返回的 HTTP 状态码。
    :returns: 对应的中性错误枚举。
    """

    if http_status == 408:
        # OLD 把 408 视为瞬时超时类可重试错误；NEW 归一到 TIMEOUT 中性
        # 枚举，``http_status=408`` 在事件 data 中保留，便于上层诊断。
        return RunnerHTTPErrorCode.TIMEOUT
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


def detect_context_overflow(
    *,
    http_status: int,
    response_text: str,
) -> bool:
    """识别 provider context overflow 响应。

    本函数是 OpenAI-compatible Runner 的 provider adapter 边界：优先读取
    结构化 ``error.code=context_length_exceeded``，再使用受控 OLD 信号
    矩阵做 message fallback。Host 不应自行匹配 provider 文本。

    :param http_status: HTTP 状态码。
    :param response_text: provider 错误响应文本。
    :returns: 明确为 context overflow 返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if http_status < 400 or http_status >= 600:
        return False
    payload = _parse_json_object(response_text)
    if payload is not None:
        code = _payload_error_code(payload)
        if code is not None:
            return code == _OPENAI_CONTEXT_LENGTH_ERROR_CODE
    lowered = response_text.lower()
    return any(marker in lowered for marker in _CONTEXT_OVERFLOW_MESSAGE_MARKERS)


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
            | RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED
            | RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS
        ):
            return False
        case _:
            assert_never(error_code)


def _parse_json_object(response_text: str) -> Mapping[str, JsonValue] | None:
    """解析 JSON object 响应。

    当前只把顶层 JSON object 交给结构化 code 读取；顶层数组、字符串等
    provider-specific 包装不在 P4 context overflow 矩阵范围内，会返回
    ``None`` 并交由受控 message marker fallback 判断。

    :param response_text: provider 响应文本。
    :returns: JSON object；解析失败或非 object 时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    try:
        value = json.loads(response_text)
    except json.JSONDecodeError:
        return None
    if isinstance(value, Mapping):
        return value
    return None


def _payload_error_code(payload: Mapping[str, JsonValue]) -> str | None:
    """读取 provider JSON payload 中明确的结构化错误 code。

    当前仅支持 ``{"error": {"code": "..."}}`` 与 ``{"code": "..."}``
    两种已知扁平结构；``{"errors": [{"code": "..."}]}`` 等数组包装
    属于新增 provider shape，不在当前 P4 支持范围。

    :param payload: provider JSON object。
    :returns: 明确非空 code；没有结构化 code 时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    error = payload.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        if isinstance(code, str) and code.strip() != "":
            return code
    code = payload.get("code")
    if isinstance(code, str) and code.strip() != "":
        return code
    return None


__all__ = [
    "classify_exception",
    "classify_http_status",
    "detect_context_overflow",
    "is_retriable",
]
