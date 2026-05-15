"""``error_classifier`` 纯单元测试。"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from dayu.engine.contracts.runner_events import RunnerHTTPErrorCode
from dayu.engine.runners.openai.error_classifier import (
    classify_exception,
    classify_http_status,
    is_retriable,
)


@pytest.mark.parametrize(
    "status, expected",
    [
        (408, RunnerHTTPErrorCode.TIMEOUT),
        (429, RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED),
        (500, RunnerHTTPErrorCode.SERVER_ERROR),
        (502, RunnerHTTPErrorCode.SERVER_ERROR),
        (503, RunnerHTTPErrorCode.SERVER_ERROR),
        (504, RunnerHTTPErrorCode.SERVER_ERROR),
        (599, RunnerHTTPErrorCode.SERVER_ERROR),
        (400, RunnerHTTPErrorCode.CLIENT_ERROR),
        (401, RunnerHTTPErrorCode.CLIENT_ERROR),
        (404, RunnerHTTPErrorCode.CLIENT_ERROR),
        (199, RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS),
        (300, RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS),
        (200, RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS),
    ],
)
def test_classify_http_status_branches(
    status: int, expected: RunnerHTTPErrorCode
) -> None:
    """覆盖 ``classify_http_status`` 各分支。"""

    assert classify_http_status(status) is expected


def test_classify_exception_timeout_async() -> None:
    """``asyncio.TimeoutError`` → ``TIMEOUT``。"""

    assert (
        classify_exception(asyncio.TimeoutError())
        is RunnerHTTPErrorCode.TIMEOUT
    )


def test_classify_exception_server_timeout() -> None:
    """``aiohttp.ServerTimeoutError`` → ``TIMEOUT``。"""

    assert (
        classify_exception(aiohttp.ServerTimeoutError())
        is RunnerHTTPErrorCode.TIMEOUT
    )


def test_classify_exception_client_error() -> None:
    """通用 ``aiohttp.ClientError`` → ``NETWORK_ERROR``。"""

    assert (
        classify_exception(aiohttp.ClientError("x"))
        is RunnerHTTPErrorCode.NETWORK_ERROR
    )


def test_classify_exception_client_payload_error_is_network_error() -> None:
    """``aiohttp.ClientPayloadError`` 属于读取失败，不应归为超时。"""

    assert (
        classify_exception(aiohttp.ClientPayloadError("broken payload"))
        is RunnerHTTPErrorCode.NETWORK_ERROR
    )


def test_classify_exception_rejects_unrelated() -> None:
    """非传输层异常应抛出 :class:`TypeError`。"""

    with pytest.raises(TypeError):
        classify_exception(ValueError("oops"))


def test_is_retriable_branches() -> None:
    """``is_retriable`` 分类规则。"""

    retriable = {
        RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
        RunnerHTTPErrorCode.SERVER_ERROR,
        RunnerHTTPErrorCode.NETWORK_ERROR,
        RunnerHTTPErrorCode.TIMEOUT,
    }
    not_retriable = {
        RunnerHTTPErrorCode.CLIENT_ERROR,
        RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED,
        RunnerHTTPErrorCode.UNKNOWN_HTTP_STATUS,
    }
    for code in retriable:
        assert is_retriable(code) is True
    for code in not_retriable:
        assert is_retriable(code) is False
