"""Web tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
import gzip
import json as json_module
import logging
import multiprocessing
import os
import pickle
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
import zlib
from io import BytesIO
from importlib.metadata import version as package_version
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import ParamSpec, Protocol, TypeVar, cast

import pytest
import requests
from urllib3.response import HTTPResponse

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_execution import (
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
)
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    HostEventRef,
    HostToolFactAcceptPort,
    ProcessBackedToolExecutionCapsule,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptedAck,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
    ToolRuntimeHandle,
)
from dayu.host.tooling import default_framework_tool_policy_view
from dayu.runtime.interruptible_process import ProcessGroupCleanupReason
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderSpec,
)
from dayu.tools.web import discover_tools
from dayu.tools.web import web_playwright_backend
from dayu.tools.web import web_challenge_detection
from dayu.tools.web import web_fetch_orchestrator
from dayu.tools.web import web_tool_projection_text
from dayu.tools.web import web_search_providers
from dayu.tools.web import web_tools
from dayu.tools.web import web_http_session
from dayu.tools.web import provider as web_provider
from dayu.tools.web.web_egress_policy import AuthorizedHttpTarget, WebEgressPolicy
from dayu.tools.web.web_resource_budget import WebResourceBudget

_WEB_TOOL_NAMES = ("search_web", "fetch_web_page")
_WEB_PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "dayu" / "tools" / "web"
_CANCEL_REQUESTED_AT = datetime(2026, 6, 8)
_FORBIDDEN_CANCEL_MESSAGE_PARTS = (
    "run_id",
    "session_id",
    "payload_ref",
    "digest",
    "correlation_id",
    "cancellation_token",
    "host cancelled",
    "Host cancelled",
    "continue_without_web",
)
_P = ParamSpec("_P")
_R = TypeVar("_R")
_LIVE_BROWSER_CLEANUP_SMOKE_ENV = "DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE"
_PROCESS_DESCENDANT_WAIT_SECONDS = 3.0
_DEFAULT_RESOURCE_BUDGET = WebResourceBudget()


class _ZstdTestCompressor(Protocol):
    """测试所需 zstandard compressor 协议。"""

    def compress(self, data: bytes) -> bytes:
        """压缩测试字节。"""
        ...


class _ZstdTestModule(Protocol):
    """测试所需 zstandard module 协议。"""

    def ZstdCompressor(self) -> _ZstdTestCompressor:
        """创建测试 compressor。"""
        ...
_PINNED_TEST_CERTIFICATE = """-----BEGIN CERTIFICATE-----
MIIDJTCCAg2gAwIBAgIUGUkR/EMkG5dZOX3VCiJfSvuYJ6MwDQYJKoZIhvcNAQEL
BQAwFjEUMBIGA1UEAwwLcGlubmVkLnRlc3QwHhcNMjYwNzEzMDQ0NzE0WhcNMzYw
NzEwMDQ0NzE0WjAWMRQwEgYDVQQDDAtwaW5uZWQudGVzdDCCASIwDQYJKoZIhvcN
AQEBBQADggEPADCCAQoCggEBANP1p1qJx6lJJjUicPqvPcfI0+Otn3/7ybGUjBwH
YB7xU2SYNqD9Q+mu3KUjPJ4xBpyp32yBD5DCYPUjdvvOZlRi2s2sScAr2KmD3byD
EKaBIKddK9xHtIws3fgXOe/9BT1GtyGe9/o8U3ESgs/KyFfhLCrvAudf7NZoENyi
3rEmJfDyICdE+L9+RRUkKhYIyoSpRZV+oiFCQdOkAEjbp60avQ7euaL3VwHdWVYj
3YB1ZaXobbUf4mjJ77AeHFRaV2/V4loIZA/SYSyonr3NxBdpSH2PunCJO71G87P2
sfJokGMFwMFGtPj4kXC1GAajstpHNSuVdQ9OgeEUWTkMNvkCAwEAAaNrMGkwHQYD
VR0OBBYEFDazPkZEMXXbPu3xuLjEOZhZiV26MB8GA1UdIwQYMBaAFDazPkZEMXXb
Pu3xuLjEOZhZiV26MA8GA1UdEwEB/wQFMAMBAf8wFgYDVR0RBA8wDYILcGlubmVk
LnRlc3QwDQYJKoZIhvcNAQELBQADggEBAEOi/Q5iVZJ123T1YwGU+CXqxeUJzk0f
k7guyDSpkIHEmI/dHDhR22jp3e346THGvwttqBj48bpeCGKJJePRIWPu/FU+Cs4P
FO7qZmQfVxhR1bza586fii6lIGRa29UZ5L1HbgA4p0DpLYew52sU9349gDm15rHj
/2EWIcCrYCu7vZQB6v0E+a3NkcQ0XPAQKTypK6jrA42ltm2Z8bMKZxEEye1svybk
RBYlLkSmWQEsiMBEvVOTfozMNj1VKmg7KoMLJfk7oGMnuQ7huL8ABetWeUwBh9hu
tN9QmnqppWuQn5x1xotnUD1/1eZ+TSqcW9HVwVmBiy/4Duw3c6oXQqo=
-----END CERTIFICATE-----
"""
_PINNED_TEST_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQDT9adaicepSSY1
InD6rz3HyNPjrZ9/+8mxlIwcB2Ae8VNkmDag/UPprtylIzyeMQacqd9sgQ+QwmD1
I3b7zmZUYtrNrEnAK9ipg928gxCmgSCnXSvcR7SMLN34Fznv/QU9Rrchnvf6PFNx
EoLPyshX4Swq7wLnX+zWaBDcot6xJiXw8iAnRPi/fkUVJCoWCMqEqUWVfqIhQkHT
pABI26etGr0O3rmi91cB3VlWI92AdWWl6G21H+Joye+wHhxUWldv1eJaCGQP0mEs
qJ69zcQXaUh9j7pwiTu9RvOz9rHyaJBjBcDBRrT4+JFwtRgGo7LaRzUrlXUPToHh
FFk5DDb5AgMBAAECggEAHEm0OJqbyYWIMl4y2toJckDkuoWg/FkzvV34ZwM6+lY1
zX6dB9ZVOnpKW0W9INWlLsJjHZ2J4MV4YC8IAao1sPxyfDGKtDmF1HXTYYXSco5Y
N83w/RiayXxxcVtUManAicGGzldjfAOSFUylparIGyZjmSVF63A7cQ/5dCDOfLC+
+NI4T4cHceq23Rg0CmBEKYejamI7/xkuLtMjEM/GACQtEzH1JjaJO8brRKH1ctUQ
Y3TdeLH5LKTyzQt80gPWKWY6VowSYqLqhZPbJ3hCnz0W4wM29lq6mK4x63O3CAtA
Dd0d0FJ0+6KkF6BLK1YuDxtmnxDtrvOpVpGHqv/kyQKBgQDwn5cC/eo+GxMSEerH
9pzSaE+QdcmJsxVo9LVLw6gSRTiSwXw1iU0WEOaUNmuwmXr9Ja87DkSSBkxaHIYw
peGWUe9R/5hED8MGFZ+Jh03af9mcbDHP7d6d+j2GOD9z5YHiUbsXZZfUFW3f4eDl
SMfJ4tdBJH1zrJfnY1hKrk1jHQKBgQDhgSV10wQYFat+ph40BaB9syJ+UTnVSuLr
ocuKthXO3PBl8PtryZg9gfUV8sU91ySx+s7/eTLrY50jQKqVXhwGhV6HqsEdJ7Ih
QUJmLPXkfBJTGii/+xKrIDDojfJDdSJEucIWgOP6Vdy9/Uc7FFaX7WY286/jiO2m
UtwOLN0gjQKBgQCpG8/65074JPkLKxJxRI3EhlDcuxtQLk8uu0SrIa/+Xy26XkcY
LQ3DI0+Z/IFE1SkNvq1feNCSO+DvN7rLd9mKVr02SMbPlrA+l3XPJwt9M3tRpux/
MLLTHiqdKOzXXAYjc8NkVx8Ui5bz0IDJQ5Q9+7HCc43DfRopIbXMjqGOtQKBgQDT
yufT8Yw20qNvH7XeRiql5EjROpiGqv7VL/BrJvj0gK2IEP0SDxTdL+Fv68M0gYwF
XPptFver/LLpGSMdhnXr6fcOlGErcMzsTs5+CFwpbB4JztfW94hhEKrev/J5SNoW
kiCn4gY8Z8ga6HauFjv+FQmbMuRPX5tUSx5CcgB9QQKBgQCi/FBJqj99EMG09FrQ
StLJFBZcadxx55QhafoeUmOt7AhqF55Xb73Y/Yj458ppYHiwZvxnhsMaXasxEsxm
7wbb4JBEQ/t8lCvhPDSXPvfC691SkdkpTQd4+Zfd9gjYIJuWEr4nbsbl1fZRLAt6
LOVZQZayV5kp1t5dtIfJp9oVHw==
-----END PRIVATE KEY-----
"""
_FORBIDDEN_IMPORTS = (
    "dayu.engine.tool_registry",
    "dayu.engine.truncation_manager",
    "dayu.engine.tools.fetch_more",
    "dayu.web",
    "dayu.tools." + "_legacy" + "_adapter",
)


def _raw_response(
    *,
    url: str,
    status_code: int,
    body: bytes,
    headers: Mapping[str, str] | None = None,
) -> requests.Response:
    """构造带 raw stream 的 requests 响应。

    :param url: 响应 URL。
    :param status_code: HTTP 状态码。
    :param body: wire body 字节。
    :param headers: 响应头。
    :returns: 可被 Web fetch owner 消费的响应对象。
    """

    response = requests.Response()
    response.status_code = status_code
    response.url = url
    response.headers.update(dict(headers or {}))
    response.raw = HTTPResponse(
        body=BytesIO(body),
        headers=dict(headers or {}),
        preload_content=False,
    )
    return response


class _CloseCountingResponse(requests.Response):
    """记录 response.close 调用次数的 owner 测试替身。"""

    def __init__(self) -> None:
        """初始化关闭计数。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.close_count = 0

    def close(self) -> None:
        """记录并执行真实 response close。

        :returns: ``None``。
        :raises Exception: 底层 close 失败时透出。
        """

        self.close_count += 1
        super().close()


class _InspectableBytesIO(BytesIO):
    """关闭后仍允许检查读取位置的测试 byte stream。"""

    def __init__(self, initial_bytes: bytes) -> None:
        """初始化 byte stream。

        Args:
            initial_bytes: 初始字节。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(initial_bytes)
        self.close_calls = 0

    def close(self) -> None:
        """记录 close，但保留 stream 供断言读取位置。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_calls += 1


class _BudgetProbePage:
    """记录 Playwright budget preflight 与完整投影调用的测试 Page。"""

    def __init__(
        self,
        *,
        metrics: Mapping[str, JsonValue],
        html: str,
        page_text: str,
        page_text_error: RuntimeError | None = None,
    ) -> None:
        """初始化可配置 Page。

        Args:
            metrics: bounded preflight 返回值。
            html: 完整 HTML 投影。
            page_text: 完整页面文本投影。
            page_text_error: 完整页面文本投影时抛出的可选错误。

        Returns:
            无。

        Raises:
            无。
        """

        self.metrics = dict(metrics)
        self.html = html
        self.page_text = page_text
        self.page_text_error = page_text_error
        self.evaluate_calls: list[tuple[str, Mapping[str, int] | None]] = []
        self.content_calls = 0

    def evaluate(
        self,
        expression: str,
        arg: Mapping[str, int] | None = None,
    ) -> JsonValue:
        """按脚本类型返回 metrics 或完整文本。

        Args:
            expression: 页面脚本。
            arg: 可选预算参数。

        Returns:
            metrics object 或完整文本。

        Raises:
            RuntimeError: 配置了完整页面文本投影错误时抛出。
        """

        self.evaluate_calls.append((expression, arg))
        if arg is not None:
            return cast(JsonValue, self.metrics)
        if self.page_text_error is not None:
            raise self.page_text_error
        return self.page_text

    def content(self) -> str:
        """返回完整 HTML 并记录调用。

        Args:
            无。

        Returns:
            完整 HTML。

        Raises:
            无。
        """

        self.content_calls += 1
        return self.html


def _counting_response(
    *,
    url: str,
    status_code: int,
    body: bytes,
    headers: Mapping[str, str] | None = None,
) -> _CloseCountingResponse:
    """构造带 raw body 与 close count 的 response。

    :param url: 响应 URL。
    :param status_code: HTTP 状态码。
    :param body: wire body。
    :param headers: 可选响应头。
    :returns: 关闭计数 response。
    :raises Exception: 不主动抛出异常。
    """

    response = _CloseCountingResponse()
    response.status_code = status_code
    response.url = url
    response.headers.update(dict(headers or {}))
    response.raw = HTTPResponse(
        body=BytesIO(body),
        headers=dict(headers or {}),
        preload_content=False,
    )
    return response


class _QueuedSession:
    """按调用顺序返回预设 response 的测试 Session。"""

    calls: list[tuple[str, str, bool]]
    _responses: list[requests.Response]

    def __init__(self, responses: list[requests.Response]) -> None:
        """初始化测试 Session。

        :param responses: 待返回响应列表。
        :returns: ``None``。
        """

        self.calls = []
        self._responses = responses

    def request(
        self,
        method: str | bytes,
        url: str | bytes,
        **kwargs: bool | float | Mapping[str, str] | None,
    ) -> requests.Response:
        """返回下一条预设响应。

        :param method: HTTP 方法。
        :param url: 请求 URL。
        :param kwargs: requests 参数。
        :returns: 下一条响应。
        :raises AssertionError: 预设响应耗尽时抛出。
        """

        stream = kwargs.get("stream")
        self.calls.append((str(method), str(url), stream is True))
        if not self._responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        return self._responses.pop(0)

    def close(self) -> None:
        """关闭测试 Session。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return


def _resolve_public_test_address(hostname: str, port: int) -> tuple[str, ...]:
    """把测试 hostname 固定解析到公开地址。

    :param hostname: 待解析 hostname。
    :param port: 目标端口。
    :returns: 单一公开测试地址。
    :raises Exception: 不主动抛出异常。
    """

    del hostname, port
    return ("93.184.216.34",)


def _public_test_policy() -> WebEgressPolicy:
    """构造不会访问真实 DNS 的公网 egress policy。

    :returns: 将测试 hostname 固定解析到公开地址的 policy。
    :raises Exception: 不主动抛出异常。
    """

    return WebEgressPolicy(resolver=_resolve_public_test_address)


def _resource_budget(
    *,
    wire_body_bytes: int = 1024,
    decoded_body_bytes: int = 2048,
    warmup_body_bytes: int = 64,
    browser_dom_chars: int = 2048,
    browser_text_chars: int = 1024,
) -> WebResourceBudget:
    """构造测试用完整 Web 资源预算。

    Args:
        wire_body_bytes: wire body 上限。
        decoded_body_bytes: decoded body 上限。
        warmup_body_bytes: warmup body 上限。
        browser_dom_chars: browser DOM 字符上限。
        browser_text_chars: browser text 字符上限。

    Returns:
        完整资源预算。

    Raises:
        ValueError: 参数不是正整数时由 owner 抛出。
    """

    return WebResourceBudget(
        wire_body_bytes=wire_body_bytes,
        decoded_body_bytes=decoded_body_bytes,
        warmup_body_bytes=warmup_body_bytes,
        browser_dom_chars=browser_dom_chars,
        browser_text_chars=browser_text_chars,
        diagnostic_error_chars=128,
        diagnostic_events=8,
    )


def _resource_budget_json(
    *,
    wire_body_bytes: int = 1024,
    decoded_body_bytes: int = 2048,
    warmup_body_bytes: int = 64,
    browser_dom_chars: int = 2048,
    browser_text_chars: int = 1024,
) -> dict[str, JsonValue]:
    """构造 provider config 使用的完整 resource_budget object。

    Args:
        wire_body_bytes: wire body 上限。
        decoded_body_bytes: decoded body 上限。
        warmup_body_bytes: warmup body 上限。
        browser_dom_chars: browser DOM 字符上限。
        browser_text_chars: browser text 字符上限。

    Returns:
        完整 JSON object。

    Raises:
        无。
    """

    return {
        "wire_body_bytes": wire_body_bytes,
        "decoded_body_bytes": decoded_body_bytes,
        "warmup_body_bytes": warmup_body_bytes,
        "browser_dom_chars": browser_dom_chars,
        "browser_text_chars": browser_text_chars,
        "diagnostic_error_chars": 128,
        "diagnostic_events": 8,
    }


def _encode_http_body(body: bytes, encoding: str) -> bytes:
    """按测试矩阵编码 HTTP body。

    Args:
        body: 原始 body。
        encoding: ``gzip``、``deflate`` 或 ``raw-deflate``。

    Returns:
        编码后的 wire body。

    Raises:
        ValueError: encoding 不在封闭测试集合时抛出。
    """

    if encoding == "gzip":
        return gzip.compress(body)
    if encoding == "deflate":
        return zlib.compress(body)
    if encoding == "raw-deflate":
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        return compressor.compress(body) + compressor.flush()
    raise ValueError(f"unsupported test content encoding: {encoding}")


def _queued_send_authorized_request(
    source_session: requests.Session,
    *,
    target: AuthorizedHttpTarget,
    method: str,
    timeout: float,
    headers: Mapping[str, str],
    stream: bool,
) -> web_http_session.AuthorizedResponseLease:
    """让编排测试替身显式消费 AuthorizedHttpTarget。

    :param source_session: 按顺序返回 response 的测试 Session。
    :param target: 当前 hop 的授权目标。
    :param method: HTTP 方法。
    :param timeout: 请求超时。
    :param headers: 请求头。
    :param stream: 是否流式读取。
    :returns: response lease。
    :raises AssertionError: Session 不是预期替身时抛出。
    """

    assert isinstance(source_session, _QueuedSession)
    response = source_session.request(
        method,
        target.normalized_url,
        timeout=timeout,
        headers=headers,
        stream=stream,
        allow_redirects=False,
    )
    return web_http_session.AuthorizedResponseLease(
        response=response,
        session=cast(requests.Session, source_session),
    )


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


class _ManualCancellationToken:
    """测试用可手动切换取消状态的 token。"""

    def __init__(self) -> None:
        """初始化为未取消状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._is_cancelled = False
        self._reason: str | None = None
        self._requested_at: datetime | None = None

    def cancel(self, reason: str) -> None:
        """请求取消。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._is_cancelled = True
        self._reason = reason
        self._requested_at = _CANCEL_REQUESTED_AT

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已调用 ``cancel`` 后返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self._is_cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 已取消时返回原因。
        :raises Exception: 不主动抛出异常。
        """

        return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 已取消时返回固定时间戳。
        :raises Exception: 不主动抛出异常。
        """

        return self._requested_at


class _AcceptingPort(HostToolFactAcceptPort):
    """测试用 Host accept barrier。"""

    def __init__(self) -> None:
        """初始化记录列表。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self,
        candidate: ToolFactAcceptCandidate,
    ) -> ToolFactAcceptResult:
        """接受工具事实候选。

        :param candidate: ToolRuntime 构造的工具事实候选。
        :returns: accepted ack。
        :raises Exception: 不主动抛出异常。
        """

        self.candidates.append(candidate)
        requested_ref = HostEventRef(
            event_id=f"event-requested-{len(self.candidates)}",
            event_sequence=len(self.candidates) * 2 - 1,
        )
        result_ref = HostEventRef(
            event_id=f"event-result-{len(self.candidates)}",
            event_sequence=len(self.candidates) * 2,
        )
        return ToolFactAcceptedAck(
            accepted_event_refs=(requested_ref, result_ref),
            tool_fact_id=f"tool-fact-{len(self.candidates)}",
            tool_call_requested_event_ref=requested_ref,
            tool_call_governed_event_ref=None,
            tool_result_event_ref=result_ref,
            result_payload_ref=None,
            result_digest=f"sha256:{'1' * 64}",
            reuse_prior_event_refs=(),
            diagnostic_refs=(),
            idempotency_record_ref=f"idempotency-{len(self.candidates)}",
        )


@dataclass(slots=True)
class _SocketWebServer:
    """测试用最小本地 HTTP server。

    Args:
        response_body: 响应正文。
        delay_seconds: 每个连接发送响应前等待的秒数。
        max_connections: 最多处理的连接数。

    Returns:
        dataclass 实例。

    Raises:
        OSError: 监听 socket 创建失败时抛出。
    """

    response_body: bytes
    delay_seconds: float
    max_connections: int
    _socket: socket.socket
    _thread: threading.Thread
    _stop_requested: threading.Event
    _ssl_context: ssl.SSLContext | None
    _received_requests: list[bytes]

    @classmethod
    def start(
        cls,
        *,
        response_body: bytes,
        delay_seconds: float = 0.0,
        max_connections: int = 8,
        ssl_context: ssl.SSLContext | None = None,
    ) -> "_SocketWebServer":
        """启动本地 HTTP server。

        :param response_body: 响应正文。
        :param delay_seconds: 每个连接发送响应前等待的秒数。
        :param max_connections: 最多处理的连接数。
        :param ssl_context: 可选 server-side TLS context。
        :returns: 已启动的 server。
        :raises OSError: socket 监听失败时抛出。
        """

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        server_socket.settimeout(0.2)
        stop_requested = threading.Event()
        server = cls(
            response_body=response_body,
            delay_seconds=delay_seconds,
            max_connections=max_connections,
            _socket=server_socket,
            _thread=threading.Thread(),
            _stop_requested=stop_requested,
            _ssl_context=ssl_context,
            _received_requests=[],
        )
        server._thread = threading.Thread(
            target=server._serve,
            name="web-tool-test-server",
            daemon=True,
        )
        server._thread.start()
        return server

    @property
    def url(self) -> str:
        """返回本地 server URL。

        :returns: ``http://127.0.0.1:<port>/page``。
        :raises OSError: socket 地址读取失败时抛出。
        """

        host, port = self._socket.getsockname()
        return f"http://{host}:{port}/page"

    @property
    def port(self) -> int:
        """返回本地 server 监听端口。

        :returns: TCP 监听端口。
        :raises OSError: socket 地址读取失败时抛出。
        """

        return int(self._socket.getsockname()[1])

    @property
    def received_requests(self) -> tuple[bytes, ...]:
        """返回已收到的 HTTP request bytes 快照。

        :returns: 按连接顺序记录的 request bytes。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._received_requests)

    def close(self) -> None:
        """停止 server 并释放 socket。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._stop_requested.set()
        self._socket.close()
        self._thread.join(timeout=1.0)

    def _serve(self) -> None:
        """处理有限数量的测试 HTTP 连接。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        handled = 0
        while handled < self.max_connections and not self._stop_requested.is_set():
            try:
                connection, _address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            handled += 1
            try:
                accepted_connection = (
                    self._ssl_context.wrap_socket(connection, server_side=True)
                    if self._ssl_context is not None
                    else connection
                )
            except ssl.SSLError:
                connection.close()
                continue
            with accepted_connection:
                self._handle_connection(accepted_connection)

    def _handle_connection(self, connection: socket.socket) -> None:
        """处理单个 HTTP 连接。

        :param connection: 已接受的 socket 连接。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        try:
            request = connection.recv(4096)
            self._received_requests.append(request)
            if self.delay_seconds > 0:
                time.sleep(self.delay_seconds)
            body = b"" if request.startswith(b"HEAD ") else self.response_body
            header = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"Connection: close\r\n\r\n"
            )
            connection.sendall(header + body)
        except OSError:
            return


@dataclass(frozen=True, slots=True)
class _SyntheticNestedPlaywrightWorker:
    """测试用可 pickle Playwright worker，负责启动 synthetic nested child。"""

    def __call__(
        self,
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
    ) -> web_playwright_backend.WebPayload:
        """启动长生命周期 nested child 后保持 worker 存活。

        :param url: 测试 URL。
        :param timeout_seconds: worker 总预算。
        :param headers: 可选请求头。
        :param playwright_channel: 可选浏览器 channel。
        :param playwright_storage_state_path: 用作 nested child PID 文件路径。
        :returns: 理论成功载荷；测试会在返回前中断 worker。
        :raises RuntimeError: PID 文件路径为空时抛出。
        """

        del url, timeout_seconds, headers, playwright_channel, egress_policy, resource_budget
        if not playwright_storage_state_path:
            raise RuntimeError("synthetic nested child pid path is required")
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time\n"
                "time.sleep(60)\n",
            ],
        )
        Path(playwright_storage_state_path).write_text(
            str(child.pid),
            encoding="utf-8",
        )
        time.sleep(60)
        return {"ok": True, "content": "unexpected synthetic result"}


@dataclass(frozen=True, slots=True)
class _LiveBrowserLongRunningWorker:
    """测试用可 pickle Playwright worker，负责启动真实 Chromium 子进程。"""

    def __call__(
        self,
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
    ) -> web_playwright_backend.WebPayload:
        """启动真实浏览器并保持 worker 存活。

        :param url: 本地 fixture URL。
        :param timeout_seconds: worker 总预算。
        :param headers: 可选请求头。
        :param playwright_channel: 可选浏览器 channel。
        :param playwright_storage_state_path: 用作 ready marker 文件路径。
        :returns: 理论成功载荷；测试会在返回前中断 worker。
        :raises RuntimeError: ready marker 路径为空时抛出。
        """

        del timeout_seconds, headers, playwright_channel, egress_policy, resource_budget
        if not playwright_storage_state_path:
            raise RuntimeError("live browser ready marker path is required")
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=5000)
        Path(playwright_storage_state_path).write_text("ready", encoding="utf-8")
        time.sleep(60)
        context.close()
        browser.close()
        playwright.stop()
        return {"ok": True, "content": "unexpected live browser result"}


@dataclass(frozen=True, slots=True)
class _BlockedPlaywrightWorker:
    """测试用可 pickle Playwright worker，模拟 URL safety 拒绝。"""

    blocked_url: str
    blocked_stage: str

    def __call__(
        self,
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
    ) -> web_playwright_backend.WebPayload:
        """抛出 Web fetch owner 的 URL safety 异常。

        :param url: 测试 URL。
        :param timeout_seconds: worker 总预算。
        :param headers: 可选请求头。
        :param playwright_channel: 可选浏览器 channel。
        :param playwright_storage_state_path: storage state 路径。
        :param egress_policy: Web 出站策略。
        :returns: 不返回。
        :raises web_fetch_orchestrator._FetchUrlSafetyError: 始终抛出。
        """

        del (
            url,
            timeout_seconds,
            headers,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            resource_budget,
        )
        raise web_fetch_orchestrator._FetchUrlSafetyError(
            url=self.blocked_url,
            reason=self.blocked_stage,
        )


def test_web_provider_discovers_search_and_fetch() -> None:
    """ToolsDiscovery 应发现两个 Web tools。"""

    spec = _spec({})
    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=spec, provider=discover_tools),)
    )

    assert tuple(definition.name for definition in result.tool_bundle.definitions) == _WEB_TOOL_NAMES
    assert result.provider_reports[0].tool_names == _WEB_TOOL_NAMES


@pytest.mark.parametrize(
    "url",
    (
        "http://user@example.com/report",
        "http://example.com:8080/report",
        "http://127.0.0.1/report",
        "http://169.254.169.254/latest/meta-data",
        "http://198.18.0.1/report",
        "http://[fe80::1]/report",
        "http://[::ffff:10.0.0.1]/report",
    ),
)
def test_egress_policy_rejects_unsafe_target_matrix(url: str) -> None:
    """公网 profile 必须 fail closed 拒绝高风险 URL/地址矩阵。"""

    with pytest.raises(ValueError, match="Web egress policy rejected"):
        _public_test_policy().authorize_http_target(url, stage="test_matrix")


def test_egress_policy_rejects_mixed_public_private_dns_answer() -> None:
    """DNS 同时返回公网与私网地址时不得挑选性放行。"""

    policy = WebEgressPolicy(
        resolver=lambda hostname, port: ("93.184.216.34", "10.0.0.7"),
    )

    with pytest.raises(ValueError, match="resolved address is not allowed"):
        policy.authorize_http_target("https://mixed.example/report", stage="test_mixed_dns")


def test_egress_transport_dependency_versions_are_locked() -> None:
    """target-bound 扩展点必须在 plan 锁定的 requests/urllib3 版本上运行。"""

    assert package_version("requests") == "2.33.1"
    assert package_version("urllib3") == "2.6.3"


def test_egress_target_bound_http_preserves_host_and_numeric_destination() -> None:
    """真实 adapter/pool/connection 必须只连接授权 IP 并保留 HTTP Host。"""

    server = _SocketWebServer.start(response_body=b"pinned http", max_connections=2)
    resolver_calls: list[tuple[str, int]] = []

    def resolver(hostname: str, port: int) -> tuple[str, ...]:
        """记录 owner DNS 调用并固定到 loopback fixture。"""

        resolver_calls.append((hostname, port))
        return ("127.0.0.1",)

    policy = WebEgressPolicy(allow_private_network=True, resolver=resolver)
    server_port = server.port
    target = policy.authorize_http_target(
        f"http://pinned.test:{server_port}/page",
        stage="test_http",
    )
    source_session = web_http_session._create_no_retry_session()
    try:
        lease = web_http_session._send_authorized_request(
            source_session,
            target=target,
            method="GET",
            timeout=2.0,
            headers={},
            stream=False,
        )
        with lease:
            assert lease.response.content == b"pinned http"
    finally:
        source_session.close()
        server.close()

    assert resolver_calls == [("pinned.test", server_port)]
    assert len(server.received_requests) == 1
    assert f"Host: pinned.test:{server_port}\r\n".encode("ascii") in server.received_requests[0]


def test_egress_target_bound_https_preserves_sni_certificate_and_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTPS numeric connect 不得改变 TLS SNI、证书 hostname 或 HTTP Host。"""

    certificate_path = tmp_path / "pinned-test-cert.pem"
    private_key_path = tmp_path / "pinned-test-key.pem"
    certificate_path.write_text(_PINNED_TEST_CERTIFICATE, encoding="ascii")
    private_key_path.write_text(_PINNED_TEST_PRIVATE_KEY, encoding="ascii")
    observed_server_names: list[str | None] = []
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certfile=certificate_path, keyfile=private_key_path)

    def record_server_name(
        tls_socket: ssl.SSLSocket | ssl.SSLObject,
        server_name: str | None,
        context: ssl.SSLSocket,
    ) -> None:
        """记录 TLS client 发送的 SNI hostname。"""

        del tls_socket, context
        observed_server_names.append(server_name)

    server_context.set_servername_callback(record_server_name)
    server = _SocketWebServer.start(
        response_body=b"pinned https",
        max_connections=2,
        ssl_context=server_context,
    )
    policy = WebEgressPolicy(
        allow_private_network=True,
        resolver=lambda hostname, port: ("127.0.0.1",),
    )
    server_port = server.port
    target = policy.authorize_http_target(
        f"https://pinned.test:{server_port}/page",
        stage="test_https",
    )
    original_create_connection = web_http_session.urllib3_connection.create_connection
    attempted_addresses: list[str] = []

    def retrying_tls_create_connection(
        address: tuple[str, int],
        timeout: float | None = None,
        source_address: tuple[str, int] | None = None,
        socket_options: list[tuple[int, int, int | bytes]] | None = None,
    ) -> socket.socket:
        """第一次模拟 TLS 前 connect 失败，第二次执行真实 numeric connect。"""

        attempted_addresses.append(address[0])
        if len(attempted_addresses) == 1:
            raise ConnectionResetError("synthetic HTTPS first connect reset")
        return original_create_connection(
            address,
            timeout,
            source_address=source_address,
            socket_options=socket_options,
        )

    monkeypatch.setattr(
        web_http_session.urllib3_connection,
        "create_connection",
        retrying_tls_create_connection,
    )
    source_session = web_http_session._create_retry_session()
    source_session.verify = str(certificate_path)
    try:
        lease = web_http_session._send_authorized_request(
            source_session,
            target=target,
            method="GET",
            timeout=2.0,
            headers={},
            stream=False,
        )
        with lease:
            assert lease.response.content == b"pinned https"
    finally:
        source_session.close()
        server.close()

    assert observed_server_names == ["pinned.test"]
    assert attempted_addresses == ["127.0.0.1", "127.0.0.1"]
    assert len(server.received_requests) == 1
    assert f"Host: pinned.test:{server_port}\r\n".encode("ascii") in server.received_requests[0]


def test_egress_pinned_retry_uses_same_approved_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect retry 只能重建到同一 immutable approved address set。"""

    server = _SocketWebServer.start(response_body=b"retry ok", max_connections=2)
    policy = WebEgressPolicy(
        allow_private_network=True,
        resolver=lambda hostname, port: ("127.0.0.1",),
    )
    target = policy.authorize_http_target(
        f"http://pinned.test:{server.port}/retry",
        stage="test_retry",
    )
    original_create_connection = web_http_session.urllib3_connection.create_connection
    attempted_addresses: list[str] = []

    def flaky_create_connection(
        address: tuple[str, int],
        timeout: float | None = None,
        source_address: tuple[str, int] | None = None,
        socket_options: list[tuple[int, int, int | bytes]] | None = None,
    ) -> socket.socket:
        """第一次模拟 RST，后续使用真实 numeric connect。"""

        attempted_addresses.append(address[0])
        if len(attempted_addresses) == 1:
            raise ConnectionResetError("synthetic first connect reset")
        return original_create_connection(
            address,
            timeout,
            source_address=source_address,
            socket_options=socket_options,
        )

    monkeypatch.setattr(
        web_http_session.urllib3_connection,
        "create_connection",
        flaky_create_connection,
    )
    source_session = web_http_session._create_retry_session()
    try:
        lease = web_http_session._send_authorized_request(
            source_session,
            target=target,
            method="GET",
            timeout=2.0,
            headers={},
            stream=False,
        )
        with lease:
            assert lease.response.content == b"retry ok"
    finally:
        source_session.close()
        server.close()

    assert attempted_addresses == ["127.0.0.1", "127.0.0.1"]


def test_egress_pinned_retry_exhaustion_has_no_fallback_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """approved address 全失败时 retry 耗尽，不得重新解析或连接 hostname。"""

    resolver_calls: list[tuple[str, int]] = []

    def resolver(hostname: str, port: int) -> tuple[str, ...]:
        """记录唯一一次 owner DNS 解析。"""

        resolver_calls.append((hostname, port))
        return ("127.0.0.1",)

    target = WebEgressPolicy(allow_private_network=True, resolver=resolver).authorize_http_target(
        "http://pinned.test:43119/fail",
        stage="test_retry_exhaustion",
    )
    attempted_addresses: list[str] = []

    def failed_create_connection(
        address: tuple[str, int],
        timeout: float | None = None,
        source_address: tuple[str, int] | None = None,
        socket_options: list[tuple[int, int, int | bytes]] | None = None,
    ) -> socket.socket:
        """记录目标并始终模拟 connection refused。"""

        del timeout, source_address, socket_options
        attempted_addresses.append(address[0])
        raise ConnectionRefusedError("synthetic approved address failure")

    monkeypatch.setattr(
        web_http_session.urllib3_connection,
        "create_connection",
        failed_create_connection,
    )
    source_session = web_http_session._create_retry_session()
    try:
        with pytest.raises(requests.ConnectionError):
            web_http_session._send_authorized_request(
                source_session,
                target=target,
                method="GET",
                timeout=1.0,
                headers={},
                stream=False,
            )
    finally:
        source_session.close()

    assert resolver_calls == [("pinned.test", 43119)]
    assert attempted_addresses == ["127.0.0.1"] * 4


def test_egress_peer_mismatch_closes_socket_before_http_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """peer 不属于 approved set 时 socket 必须在交给 HTTP 层前关闭。"""

    class FakeSocket:
        """只暴露 peer 与 close 的 socket 替身。"""

        def __init__(self) -> None:
            """初始化未关闭状态。"""

            self.closed = False

        def getpeername(self) -> tuple[str, int]:
            """返回未授权 peer。"""

            return ("127.0.0.2", 80)

        def close(self) -> None:
            """记录 socket 已关闭。"""

            self.closed = True

    fake_socket = FakeSocket()
    monkeypatch.setattr(
        web_http_session.urllib3_connection,
        "create_connection",
        lambda address, timeout, source_address, socket_options: cast(socket.socket, fake_socket),
    )
    connection = web_http_session._PinnedHTTPConnection("pinned.test", 80)
    connection.bind_approved_addresses(("127.0.0.1",))

    with pytest.raises(Exception, match="peer mismatch"):
        connection._new_conn()

    assert fake_socket.closed is True


def test_web_tool_display_and_description_stay_at_declaration_boundary() -> None:
    """Web 工具展示名和描述应保留在 tool declaration 边界。"""

    definitions = _definitions_by_name(_discover_definitions({}))
    search_definition = definitions["search_web"]
    fetch_definition = definitions["fetch_web_page"]

    assert search_definition.display is not None
    assert search_definition.display.name == "联网搜索"
    assert search_definition.schema.function.description == "搜索公开网页来源。"
    assert fetch_definition.display is not None
    assert fetch_definition.display.name == "抓取网页"
    assert fetch_definition.schema.function.description == (
        "抓取网页正文并转成 Markdown。失败时先看 hint 和 next_action，再决定重试、换来源或忽略当前网页。"
    )


def test_web_audit_matrix_context_injection_and_schema_no_leak() -> None:
    """Web 工具 schema 不得暴露 Host 治理字段。"""

    definitions = _definitions_by_name(_discover_definitions({}))

    for tool_name in _WEB_TOOL_NAMES:
        definition = definitions[tool_name]
        properties = definition.schema.function.parameters.properties
        required = definition.schema.function.parameters.required
        assert "run_id" not in properties
        assert "session_id" not in properties
        assert "execution_context" not in properties
        assert "cancellation_token" not in properties
        assert "correlation_id" not in properties
        assert "run_id" not in required
        assert "session_id" not in required
        assert "execution_context" not in required
        assert "cancellation_token" not in required
        assert "correlation_id" not in required


def test_web_tool_definitions_declare_process_backed_execution() -> None:
    """两个 Web tool 的生产 execution 必须声明为 process-backed。"""

    definitions = _definitions_by_name(_discover_definitions({}))

    for tool_name in _WEB_TOOL_NAMES:
        definition = definitions[tool_name]
        assert isinstance(definition.execution, ProcessBackedToolExecutionCapability)


def test_web_tools_do_not_redeclare_process_envelope_constants() -> None:
    """Web 工具不得重新声明本地 process envelope 常量。"""

    source = Path(web_tools.__file__).read_text(encoding="utf-8")

    assert "_WEB_PROCESS_" not in source


def test_web_process_target_factory_is_pickle_round_trippable() -> None:
    """Web process target factory 和 target 必须可 pickle round-trip。"""

    definitions = _definitions_by_name(
        _discover_definitions(
            {
                "provider": "duckduckgo",
                "request_timeout_seconds": 1.25,
                "allow_private_network_url": True,
                "playwright_channel": "chrome",
                "playwright_storage_state_dir": "/tmp/dayu-web-state",
            }
        )
    )
    definition = definitions["fetch_web_page"]
    execution = cast(ProcessBackedToolExecutionCapability, definition.execution)
    factory = cast(
        web_tools._WebProcessTargetFactory,
        pickle.loads(pickle.dumps(execution.target_factory)),
    )

    process_target = factory.build_process_target(
        _call("fetch_web_page", {"url": "http://127.0.0.1/page"}),
        ProcessBackedToolContext(
            run_id="run-web",
            session_id="session-web",
            iteration_id="iteration-web",
            timeout_seconds=3.5,
            correlation_id="correlation-web",
        ),
    )
    round_tripped_target = cast(
        web_tools._WebProcessTarget,
        pickle.loads(pickle.dumps(process_target)),
    )

    assert round_tripped_target.tool_name == "fetch_web_page"
    assert round_tripped_target.timeout_seconds == 3.5
    target_repr = repr(round_tripped_target)
    assert "Session" not in target_repr
    assert "provider_lock" not in target_repr
    assert "CancellationToken" not in target_repr
    assert "Host" not in target_repr
    assert "Browser" not in target_repr
    assert "Playwright" not in target_repr


def test_web_process_target_fast_search_success_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web process target 成功路径应返回 completed JSON 信封。"""

    budgets: list[float | None] = []

    def fake_search_business(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 timeout budget 并返回确定性搜索结果。

        :param kwargs: process target 传入的业务参数。
        :returns: 搜索成功载荷。
        """

        budgets.append(cast(float | None, kwargs.get("timeout_budget")))
        return {
            "query": "revenue",
            "domains": [],
            "total": 1,
            "preferred_result": None,
            "preferred_result_summary": "",
            "next_action": "refine_query",
            "next_action_args": {},
            "hint": "ok",
            "results": [],
        }

    monkeypatch.setattr(web_tools, "_search_web_business", fake_search_business)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    envelope = _run_definition_process_target(
        definition,
        _call("search_web", {"query": "revenue"}),
        timeout_seconds=4.25,
    )

    assert isinstance(envelope, Mapping)
    assert envelope["status"] == "completed"
    value = cast(Mapping[str, JsonValue], envelope["value"])
    assert value["total"] == 1
    assert budgets == [4.25]


def test_web_process_target_failed_json_envelope_preserves_code_and_hint() -> None:
    """process target 参数失败时应分离 failed message 与 hint。"""

    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    envelope = _run_definition_process_target(
        definition,
        _call("fetch_web_page", {}),
    )

    assert isinstance(envelope, Mapping)
    assert envelope["status"] == "failed"
    assert envelope["error_type"] == "invalid_argument"
    assert "url" in str(envelope["message"])
    assert "Hint:" not in str(envelope["message"])
    assert envelope["hint"] == "Add required fields and retry: url."


@pytest.mark.parametrize("tool_name", _WEB_TOOL_NAMES)
def test_web_process_target_timeout_budget_is_serialized_to_target(
    tool_name: str,
) -> None:
    """process target 必须携带父进程投影的 timeout 标量。"""

    definition = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )[tool_name]
    execution = cast(ProcessBackedToolExecutionCapability, definition.execution)
    target = execution.target_factory.build_process_target(
        _call(tool_name, _process_arguments_for_tool(tool_name)),
        ProcessBackedToolContext(
            run_id="run-web",
            session_id="session-web",
            iteration_id="iteration-web",
            timeout_seconds=6.75,
            correlation_id="correlation-web",
        ),
    )

    assert isinstance(target, web_tools._WebProcessTarget)
    assert target.timeout_seconds == 6.75


def test_web_process_backed_capsule_spawns_child_success() -> None:
    """真实 ProcessBackedToolExecutionCapsule 应能运行 Web 子进程成功路径。"""

    server = _SocketWebServer.start(
        response_body=b"<html><head><title>Example</title></head><body>Revenue grew quickly.</body></html>",
        max_connections=8,
    )
    try:
        definition = _definitions_by_name(
            _discover_definitions({"allow_private_network_url": True})
        )["fetch_web_page"]
        execution = cast(ProcessBackedToolExecutionCapability, definition.execution)
        target = execution.target_factory.build_process_target(
            _call("fetch_web_page", {"url": server.url}),
            ProcessBackedToolContext(
                run_id="run-web",
                session_id="session-web",
                iteration_id="iteration-web",
                timeout_seconds=10.0,
                correlation_id="correlation-web",
            ),
        )
        capsule = ProcessBackedToolExecutionCapsule(target)

        outcome = asyncio.run(capsule.run())
        asyncio.run(capsule.close())
    finally:
        server.close()

    assert isinstance(outcome, ToolCompletedOutcome)
    value = _mapping_value(outcome.result.value)
    assert value["fetch_backend"] == "requests"
    assert "Revenue grew quickly" in str(value["content"])


def test_web_toolruntime_cancel_real_process_target_has_no_late_accept() -> None:
    """真实 Web process target 取消后不得接受旧子进程 late result。"""

    server = _SocketWebServer.start(
        response_body=b"<html><body>late web content</body></html>",
        delay_seconds=5.0,
        max_connections=4,
    )
    try:
        output = discover_tools(
            _spec(
                {
                    "allow_private_network_url": True,
                    "request_timeout_seconds": 20.0,
                }
            )
        )
        accept_port = _AcceptingPort()
        token = _ManualCancellationToken()
        tool_runtime = DefaultToolRuntimeFactory(
            EffectiveToolBundleBuilder()
        ).create_tool_runtime(
            ToolRuntimeBuildRequest(
                effective_bundle_request=EffectiveToolBundleBuildRequest(
                    business_tool_bundle=ToolBundle(definitions=output.definitions),
                    source_refs=output.source_refs,
                    framework_tool_policy=default_framework_tool_policy_view(),
                    policy_snapshot_digest="sha256:" + "2" * 64,
                    enable_truncation_manager=False,
                ),
                execution_scope=ToolRuntimeExecutionScope(
                    session_id="session-web",
                    run_id="run-web",
                    attempt_id="attempt-web",
                    execution_id="execution-web",
                    allow_tool_calls=True,
                ),
                accept_port=accept_port,
            )
        )

        started_at = time.monotonic()
        governed_outcome = asyncio.run(
            _execute_web_runtime_fetch_and_cancel(
                tool_runtime,
                server.url,
                token,
            )
        )
        elapsed = time.monotonic() - started_at
        time.sleep(0.3)
    finally:
        server.close()

    assert elapsed < 2.0
    assert governed_outcome.result.hint is None
    assert len(accept_port.candidates) == 1
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_runtime_cancelled"
    )


def test_search_public_web_provider_result_excludes_llm_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search provider 边界只返回结构化事实，不生成 LLM guidance 字段。"""

    observed_budgets: list[WebResourceBudget] = []

    def fake_search_with_duckduckgo(
        *,
        query: str,
        domains: list[str],
        max_results: int,
        timeout_seconds: float,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        resource_budget: WebResourceBudget,
    ) -> list[web_search_providers.SearchResultRow]:
        """返回确定性 provider 原始结果。

        :param query: 检索关键词。
        :param domains: 域名过滤。
        :param max_results: 返回数量。
        :param timeout_seconds: HTTP 请求超时秒数。
        :param timeout_budget: 工具调用总预算。
        :param deadline_monotonic: 工具调用 deadline。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param resource_budget: Web response 资源预算。
        :returns: 单条 provider 原始结果。
        :raises Exception: 不主动抛出异常。
        """

        del (
            query,
            domains,
            max_results,
            timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            normalize_whitespace,
            resolve_timeout_budget,
        )
        observed_budgets.append(resource_budget)
        return [
            {
                "title": "10-K",
                "url": "https://www.sec.gov/Archives/example.htm",
                "snippet": "annual report",
                "published_date": "",
            }
        ]

    def is_safe_public_url(
        url: str,
        *,
        allow_private_network_url: bool = False,
    ) -> bool:
        """测试用 URL 安全判断。

        :param url: 候选 URL。
        :param allow_private_network_url: 是否允许私网 URL。
        :returns: 始终允许。
        :raises Exception: 不主动抛出异常。
        """

        del url, allow_private_network_url
        return True

    def normalize_whitespace(value: str) -> str:
        """规整测试文本空白。

        :param value: 原始文本。
        :returns: 合并连续空白后的文本。
        :raises Exception: 不主动抛出异常。
        """

        return " ".join(value.split())

    def resolve_timeout_budget(
        timeout_seconds: float,
        *,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
    ) -> float:
        """返回测试 timeout。

        :param timeout_seconds: 基础 timeout。
        :param timeout_budget: 工具调用总预算。
        :param deadline_monotonic: 工具调用 deadline。
        :returns: 原始 timeout。
        :raises Exception: 不主动抛出异常。
        """

        del timeout_budget, deadline_monotonic
        return timeout_seconds

    monkeypatch.setattr(
        web_search_providers,
        "_search_with_duckduckgo",
        fake_search_with_duckduckgo,
    )

    result = web_search_providers.search_public_web(
        query="revenue",
        domains=["sec.gov"],
        recency_days=None,
        max_results=3,
        max_search_results=10,
        provider="duckduckgo",
        request_timeout_seconds=1.0,
        timeout_budget=None,
        deadline_monotonic=None,
        allow_private_network_url=False,
        is_safe_public_url=is_safe_public_url,
        normalize_whitespace=normalize_whitespace,
        resolve_timeout_budget=resolve_timeout_budget,
        resource_budget=_DEFAULT_RESOURCE_BUDGET,
    )
    result_mapping = cast(Mapping[str, JsonValue], result)

    assert set(result_mapping) == {
        "query",
        "domains",
        "total",
        "preferred_result",
        "results",
    }
    assert "hint" not in result_mapping
    assert "next_action" not in result_mapping
    assert "next_action_args" not in result_mapping
    assert "preferred_result_summary" not in result_mapping
    assert observed_budgets == [_DEFAULT_RESOURCE_BUDGET]


def test_search_web_projects_optional_arguments_and_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web optional 参数必须先经 adapter 校验/转换。"""

    calls: list[Mapping[str, JsonValue]] = []

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录搜索调用参数并返回确定性 provider 事实。

        :param kwargs: search_web 传入的关键字参数。
        :returns: 确定性 provider 搜索事实。
        """

        calls.append(kwargs)
        return {
            "query": "revenue",
            "domains": ["sec.gov"],
            "total": 1,
            "preferred_result": {
                "title": "10-K",
                "url": "https://www.sec.gov/Archives/example.htm",
                "snippet": "annual report",
                "published_date": "",
            },
            "results": [
                {
                    "title": "10-K",
                    "url": "https://www.sec.gov/Archives/example.htm",
                    "snippet": "annual report",
                    "published_date": "",
                }
            ],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "search_web",
                {
                    "query": "revenue",
                    "domains": ["sec.gov"],
                    "recency_days": 7.0,
                    "max_results": 3.0,
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    value = _mapping_value(outcome.result.value)
    assert value["total"] == 1
    assert value["preferred_result_summary"] == (
        "首选结果；标题：10-K；URL：https://www.sec.gov/Archives/example.htm；摘要：annual report"
    )
    assert value["next_action"] == "fetch_web_page"
    assert value["next_action_args"] == {"url": "https://www.sec.gov/Archives/example.htm"}
    assert "fetch_web_page" in str(value["hint"])
    assert calls[0]["domains"] == ["sec.gov"]
    assert calls[0]["recency_days"] == 7
    assert calls[0]["max_results"] == 3
    assert "ok" not in value


def test_search_web_receives_provider_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web 闭包必须接收 Web provider config。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: provider config 未传入搜索路径时抛出。
    """

    calls: list[Mapping[str, JsonValue]] = []

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 search_web 闭包参数并返回 provider 事实。

        :param kwargs: search_web 传入的关键字参数。
        :returns: 确定性空 provider 搜索事实。
        """

        calls.append(kwargs)
        return {
            "query": "revenue",
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "results": [],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(
        _discover_definitions(
            {
                "provider": "serper",
                "request_timeout_seconds": 3.5,
                "max_search_results": 4,
                "allow_private_network_url": True,
            }
        )
    )["search_web"]

    outcome = asyncio.run(
        definition.callable(_call("search_web", {"query": "revenue"}), _context())
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert calls[0]["provider"] == "serper"
    assert calls[0]["request_timeout_seconds"] == 3.5
    assert calls[0]["max_search_results"] == 4
    assert calls[0]["allow_private_network_url"] is True
    assert calls[0]["resource_budget"] == WebResourceBudget()


def test_search_web_receives_execution_context_and_passes_cancellation_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web 必须接收 execution context 并向 provider 传递同一个 token。"""

    token = _ManualCancellationToken()
    received_tokens: list[CancellationToken | None] = []

    def fake_search_public_web(
        *,
        query: str,
        domains: list[str] | None,
        recency_days: int | None,
        max_results: int,
        max_search_results: int,
        provider: str,
        request_timeout_seconds: float,
        timeout_budget: float | None,
        deadline_monotonic: float | None,
        allow_private_network_url: bool,
        is_safe_public_url: web_search_providers._PublicUrlSafetyChecker,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebProviderResult:
        """记录 token identity 并返回确定性搜索结果。

        :param query: 检索关键词。
        :param domains: 可选域名限制。
        :param recency_days: 可选最近天数。
        :param max_results: 请求结果数量。
        :param max_search_results: 注册配置中的结果上限。
        :param provider: provider 策略。
        :param request_timeout_seconds: 单次 provider 请求超时。
        :param timeout_budget: 当前工具调用预算。
        :param deadline_monotonic: 当前工具调用 deadline。
        :param allow_private_network_url: 是否允许私网结果。
        :param is_safe_public_url: URL 安全校验函数。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param resource_budget: Web response 资源预算。
        :param cancellation_token: execution context 注入的取消令牌。
        :returns: 确定性 provider 搜索事实。
        :raises Exception: 不主动抛出异常。
        """

        del (
            domains,
            recency_days,
            max_search_results,
            provider,
            request_timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            allow_private_network_url,
            is_safe_public_url,
            normalize_whitespace,
            resolve_timeout_budget,
            resource_budget,
        )
        received_tokens.append(cancellation_token)
        return {
            "query": query,
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "results": [],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call("search_web", {"query": "revenue"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert received_tokens == [token]


def test_search_web_cancelled_before_provider_returns_host_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web pre-cancel 必须返回 cancelled outcome 且不调用 provider。"""

    token = _ManualCancellationToken()
    token.cancel("run_id=run-web session_id=session-web payload_ref=payload-web")
    search_calls: list[str] = []

    def fake_search_public_web(
        *,
        query: str,
        domains: list[str] | None,
        recency_days: int | None,
        max_results: int,
        max_search_results: int,
        provider: str,
        request_timeout_seconds: float,
        timeout_budget: float | None,
        deadline_monotonic: float | None,
        allow_private_network_url: bool,
        is_safe_public_url: web_search_providers._PublicUrlSafetyChecker,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebProviderResult:
        """记录非预期 provider 调用。

        :param query: 检索关键词。
        :param domains: 可选域名限制。
        :param recency_days: 可选最近天数。
        :param max_results: 请求结果数量。
        :param max_search_results: 注册配置中的结果上限。
        :param provider: provider 策略。
        :param request_timeout_seconds: 单次 provider 请求超时。
        :param timeout_budget: 当前工具调用预算。
        :param deadline_monotonic: 当前工具调用 deadline。
        :param allow_private_network_url: 是否允许私网结果。
        :param is_safe_public_url: URL 安全校验函数。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param resource_budget: Web response 资源预算。
        :param cancellation_token: execution context 注入的取消令牌。
        :returns: 空 provider 搜索事实。
        :raises Exception: 不主动抛出异常。
        """

        del (
            domains,
            recency_days,
            max_results,
            max_search_results,
            provider,
            request_timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            allow_private_network_url,
            is_safe_public_url,
            normalize_whitespace,
            resolve_timeout_budget,
            resource_budget,
            cancellation_token,
        )
        search_calls.append(query)
        return {
            "query": query,
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "results": [],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call("search_web", {"query": "revenue"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == "search_web"
    assert outcome.message == web_tool_projection_text.WEB_SEARCH_CANCELLED_MESSAGE
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")
    assert outcome.hint is not None
    assert outcome.hint == web_tool_projection_text.WEB_CANCELLED_HINT
    assert search_calls == []


def test_search_web_deep_cancel_message_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search provider 深层取消不得把 token reason 投影给 LLM。"""

    def fake_search_public_web(
        *,
        query: str,
        domains: list[str] | None,
        recency_days: int | None,
        max_results: int,
        max_search_results: int,
        provider: str,
        request_timeout_seconds: float,
        timeout_budget: float | None,
        deadline_monotonic: float | None,
        allow_private_network_url: bool,
        is_safe_public_url: web_search_providers._PublicUrlSafetyChecker,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebProviderResult:
        """模拟搜索 provider 在深层 checkpoint 抛出携带治理字段的取消。

        :param query: 检索关键词。
        :param domains: 可选域名限制。
        :param recency_days: 可选最近天数。
        :param max_results: 请求结果数量。
        :param max_search_results: 注册配置中的结果上限。
        :param provider: provider 策略。
        :param request_timeout_seconds: 单次 provider 请求超时。
        :param timeout_budget: 当前工具调用预算。
        :param deadline_monotonic: 当前工具调用 deadline。
        :param allow_private_network_url: 是否允许私网结果。
        :param is_safe_public_url: URL 安全校验函数。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param resource_budget: Web response 资源预算。
        :param cancellation_token: execution context 注入的取消令牌。
        :returns: 不返回。
        :raises web_search_providers.WebSearchCancelledError: 始终抛出测试取消。
        """

        del (
            query,
            domains,
            recency_days,
            max_results,
            max_search_results,
            provider,
            request_timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            allow_private_network_url,
            is_safe_public_url,
            normalize_whitespace,
            resolve_timeout_budget,
            resource_budget,
            cancellation_token,
        )
        raise web_search_providers.WebSearchCancelledError(
            message="run_id=run-web correlation_id=correlation-web digest=sha256:web",
        )

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call("search_web", {"query": "revenue"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.message == web_tool_projection_text.WEB_SEARCH_CANCELLED_MESSAGE
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")


def test_search_web_cancelled_between_provider_attempts_stops_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider attempt 间取消后必须停止后续 fallback。"""

    token = _ManualCancellationToken()
    attempted_providers: list[str] = []

    def fake_search_with_tavily(
        *,
        query: str,
        domains: list[str],
        recency_days: int | None,
        max_results: int,
        timeout_seconds: float,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver = web_search_providers._default_resolve_timeout_budget,
        resource_budget: WebResourceBudget,
    ) -> list[web_search_providers.SearchResultRow]:
        """模拟首个 provider 失败并同时触发 Host cancel。

        :param query: 检索关键词。
        :param domains: 域名限制。
        :param recency_days: 最近天数。
        :param max_results: 返回数量。
        :param timeout_seconds: HTTP 请求超时。
        :param timeout_budget: 当前工具预算。
        :param deadline_monotonic: 当前工具 deadline。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param resource_budget: Web response 资源预算。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 provider 失败。
        """

        del (
            query,
            domains,
            recency_days,
            max_results,
            timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            resolve_timeout_budget,
            resource_budget,
        )
        attempted_providers.append("tavily")
        token.cancel("cancel after first provider")
        raise RuntimeError("tavily unavailable")

    def fake_search_with_duckduckgo(
        *,
        query: str,
        domains: list[str],
        max_results: int,
        timeout_seconds: float,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        normalize_whitespace: Callable[[str], str] = lambda value: " ".join(value.split()),
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver = web_search_providers._default_resolve_timeout_budget,
        resource_budget: WebResourceBudget,
    ) -> list[web_search_providers.SearchResultRow]:
        """记录非预期 DuckDuckGo fallback。

        :param query: 检索关键词。
        :param domains: 域名限制。
        :param max_results: 返回数量。
        :param timeout_seconds: HTTP 请求超时。
        :param timeout_budget: 当前工具预算。
        :param deadline_monotonic: 当前工具 deadline。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param resource_budget: Web response 资源预算。
        :returns: 空结果。
        :raises Exception: 不主动抛出异常。
        """

        del (
            query,
            domains,
            max_results,
            timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            normalize_whitespace,
            resolve_timeout_budget,
            resource_budget,
        )
        attempted_providers.append("duckduckgo")
        return []

    monkeypatch.setattr(web_search_providers, "_search_with_tavily", fake_search_with_tavily)
    monkeypatch.setattr(
        web_search_providers,
        "_search_with_duckduckgo",
        fake_search_with_duckduckgo,
    )
    definition = _definitions_by_name(_discover_definitions({"provider": "tavily"}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call("search_web", {"query": "revenue"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == "search_web"
    assert attempted_providers == ["tavily"]


def test_fetch_web_page_cancelled_before_work_returns_safe_host_cancelled() -> None:
    """fetch_web_page pre-cancel 必须返回安全 cancelled outcome。"""

    token = _ManualCancellationToken()
    token.cancel("run_id=run-web session_id=session-web cancellation_token=token-web")
    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://example.com/report"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == "fetch_web_page"
    assert outcome.message == web_tool_projection_text.WEB_FETCH_CANCELLED_MESSAGE
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")
    assert outcome.hint == web_tool_projection_text.WEB_CANCELLED_HINT


def test_fetch_web_page_deep_runtime_cancel_message_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch 深层 RuntimeError 取消不得把 token reason 投影给 LLM。"""

    token = _ManualCancellationToken()

    def fake_warmup_domain(*args: JsonValue, **kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """模拟深层联网阶段观察到取消并抛出携带治理字段的 RuntimeError。

        :param args: 位置参数。
        :param kwargs: 关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出测试取消。
        """

        del args, kwargs
        token.cancel("run_id=run-web payload_ref=payload-web digest=sha256:web")
        raise RuntimeError("run_id=run-web payload_ref=payload-web digest=sha256:web")

    monkeypatch.setattr(web_tools, "_warmup_domain", fake_warmup_domain)
    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://example.com/report"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.message == web_tool_projection_text.WEB_FETCH_CANCELLED_MESSAGE
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")


def test_fetch_private_url_fails_closed_by_default() -> None:
    """默认配置必须拒绝 private/local URL。"""

    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "permission_denied"


def test_fetch_private_url_can_be_allowed_with_explicit_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式允许 private URL 后，抓取路径才可继续执行。"""

    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": True})
    monkeypatch.setattr(web_tools, "_probe_content_type", lambda *args, **kwargs: {"attempted": True, "ok": True})
    monkeypatch.setattr(web_tools, "_try_playwright_fallback", lambda *args, **kwargs: None)

    def fake_fetch_and_convert_content(url: str, **kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """返回确定性网页内容。

        :param url: 已标准化 URL。
        :param kwargs: 抓取辅助参数。
        :returns: 确定性抓取结果。
        """

        return {
            "final_url": url,
            "title": "Internal",
            "content": "local test content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "response_excerpt": "local test content",
            "extraction_source": "mock",
            "renderer_source": "mock",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(web_tools, "_fetch_and_convert_content", fake_fetch_and_convert_content)
    definition = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    value = _mapping_value(outcome.result.value)
    assert value["fetch_backend"] == "requests"
    assert value["content"] == "local test content"
    assert "ok" not in value


def test_fetch_redirect_to_private_url_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP redirect 每一跳都必须复用 private-network safety owner。"""

    response = _counting_response(
        url="https://example.com/report",
        status_code=302,
        body=b"",
        headers={"Location": "http://127.0.0.1/internal"},
    )
    session = _QueuedSession(
        [response]
    )

    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)
    with pytest.raises(web_fetch_orchestrator._FetchUrlSafetyError) as exc_info:
        web_fetch_orchestrator._fetch_and_convert_content(
            "https://example.com/report",
            timeout_seconds=1.0,
            resolve_timeout_budget=web_tools._resolve_timeout_budget,
            normalize_url_for_http=web_tools._normalize_url_for_http,
            build_referer=web_tools._build_referer,
            convert_html=web_tools.convert_html_to_llm_markdown,
            convert_non_html=web_tools._docling_convert_to_markdown,
            session=cast(requests.Session, session),
            headers={},
            egress_policy=_public_test_policy(),
            resource_budget=_DEFAULT_RESOURCE_BUDGET,
        )

    assert exc_info.value.url == "http://127.0.0.1/internal"
    assert session.calls == [("GET", "https://example.com/report", True)]
    assert response.close_count == 1


def test_response_lease_transfers_final_response_and_closes_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """最终 response 在 transfer 前保持打开，由 caller 幂等关闭一次。"""

    response = _counting_response(
        url="https://example.com/report",
        status_code=200,
        body=b"ok",
    )
    session = _QueuedSession([response])
    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)

    lease, redirect_hops, _visited_urls = web_fetch_orchestrator._request_with_safe_redirects(
        cast(requests.Session, session),
        method="GET",
        url="https://example.com/report",
        timeout=1.0,
        headers={},
        normalize_url_for_http=web_tools._normalize_url_for_http,
        egress_policy=_public_test_policy(),
        stream=True,
        cancellation_token=None,
    )

    assert redirect_hops == 0
    assert response.close_count == 0
    lease.close()
    lease.close()
    assert response.close_count == 1


def test_response_lease_closes_when_cancelled_after_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request 返回后观察到取消时 callee 必须关闭 response 与 pool。"""

    class CancelAfterRequestToken:
        """第一次检查放行、第二次检查报告取消的 token。"""

        def __init__(self) -> None:
            """初始化检查计数。"""

            self.check_count = 0

        def is_cancelled(self) -> bool:
            """第二次及后续检查返回 ``True``。"""

            self.check_count += 1
            return self.check_count >= 2

        def cancel_reason(self) -> str | None:
            """返回固定取消原因。"""

            return "cancelled after request"

        def requested_at(self) -> datetime | None:
            """返回空请求时间。"""

            return None

    response = _counting_response(
        url="https://example.com/report",
        status_code=200,
        body=b"ok",
    )
    session = _QueuedSession([response])
    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)

    with pytest.raises(RuntimeError, match="cancelled after request"):
        web_fetch_orchestrator._request_with_safe_redirects(
            cast(requests.Session, session),
            method="GET",
            url="https://example.com/report",
            timeout=1.0,
            headers={},
            normalize_url_for_http=web_tools._normalize_url_for_http,
            egress_policy=_public_test_policy(),
            stream=True,
            cancellation_token=cast(CancellationToken, CancelAfterRequestToken()),
        )

    assert response.close_count == 1


@pytest.mark.parametrize(
    ("response_url", "status_code", "headers", "expected_error"),
    (
        ("http://127.0.0.1/internal", 200, {}, web_fetch_orchestrator._FetchUrlSafetyError),
        ("https://example.com/report", 302, {}, RuntimeError),
    ),
)
def test_response_lease_closes_on_response_or_location_reject(
    monkeypatch: pytest.MonkeyPatch,
    response_url: str,
    status_code: int,
    headers: Mapping[str, str],
    expected_error: type[Exception],
) -> None:
    """response URL 与 Location 拒绝均必须关闭当前 lease。"""

    response = _counting_response(
        url=response_url,
        status_code=status_code,
        body=b"",
        headers=headers,
    )
    session = _QueuedSession([response])
    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)

    with pytest.raises(expected_error):
        web_fetch_orchestrator._request_with_safe_redirects(
            cast(requests.Session, session),
            method="GET",
            url="https://example.com/report",
            timeout=1.0,
            headers={},
            normalize_url_for_http=web_tools._normalize_url_for_http,
            egress_policy=_public_test_policy(),
            stream=True,
            cancellation_token=None,
        )

    assert response.close_count == 1


def test_response_lease_closes_on_too_many_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    """redirect 上限拒绝不得把当前 response 留给异常路径。"""

    response = _counting_response(
        url="https://example.com/report",
        status_code=302,
        body=b"",
        headers={"Location": "https://example.com/next"},
    )
    session = _QueuedSession([response])
    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)
    monkeypatch.setattr(web_fetch_orchestrator, "_MAX_HTTP_REDIRECT_HOPS", 0)

    with pytest.raises(requests.TooManyRedirects):
        web_fetch_orchestrator._request_with_safe_redirects(
            cast(requests.Session, session),
            method="GET",
            url="https://example.com/report",
            timeout=1.0,
            headers={},
            normalize_url_for_http=web_tools._normalize_url_for_http,
            egress_policy=_public_test_policy(),
            stream=True,
            cancellation_token=None,
        )

    assert response.close_count == 1


def test_response_lease_closes_head_probe_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """HEAD probe 成功复制 facts 后必须立即关闭 response lease。"""

    response = _counting_response(
        url="https://example.com/report",
        status_code=200,
        body=b"",
        headers={"Content-Type": "text/html"},
    )
    session = _QueuedSession([response])
    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)

    result = web_fetch_orchestrator._probe_content_type(
        cast(requests.Session, session),
        url="https://example.com/report",
        timeout_seconds=1.0,
        headers={},
        resolve_timeout_budget=lambda timeout_seconds, **kwargs: timeout_seconds,
        normalize_url_for_http=web_tools._normalize_url_for_http,
        is_timeout_like_exception=lambda error: False,
        egress_policy=_public_test_policy(),
        resource_budget=_DEFAULT_RESOURCE_BUDGET,
    )

    assert result["ok"] is True
    assert response.close_count == 1


def test_fetch_meta_refresh_to_private_url_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTML meta refresh 目标必须在继续抓取前复用同一 URL safety owner。"""

    html = (
        b'<html><head><meta http-equiv="refresh" '
        b'content="0;url=http://127.0.0.1/internal"></head></html>'
    )
    session = _QueuedSession(
        [
            _raw_response(
                url="https://example.com/report",
                status_code=200,
                body=html,
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        ]
    )

    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)
    with pytest.raises(web_fetch_orchestrator._FetchUrlSafetyError) as exc_info:
        web_fetch_orchestrator._fetch_and_convert_content(
            "https://example.com/report",
            timeout_seconds=1.0,
            resolve_timeout_budget=web_tools._resolve_timeout_budget,
            normalize_url_for_http=web_tools._normalize_url_for_http,
            build_referer=web_tools._build_referer,
            convert_html=web_tools.convert_html_to_llm_markdown,
            convert_non_html=web_tools._docling_convert_to_markdown,
            session=cast(requests.Session, session),
            headers={},
            egress_policy=_public_test_policy(),
            resource_budget=_DEFAULT_RESOURCE_BUDGET,
        )

    assert exc_info.value.url == "http://127.0.0.1/internal"
    assert session.calls == [("GET", "https://example.com/report", True)]


def test_fetch_meta_refresh_treats_redirect_hop_as_visited(monkeypatch: pytest.MonkeyPatch) -> None:
    """meta refresh 防环必须消费 HTTP redirect 已访问 URL 记录。"""

    html = (
        b'<html><head><meta http-equiv="refresh" '
        b'content="0;url=https://example.com/redirected"></head></html>'
    )
    session = _QueuedSession(
        [
            _raw_response(
                url="https://example.com/report",
                status_code=302,
                body=b"",
                headers={"Location": "https://example.com/redirected"},
            ),
            _raw_response(
                url="https://example.com/redirected",
                status_code=200,
                body=html,
                headers={"Content-Type": "text/html; charset=utf-8"},
            ),
        ]
    )

    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)
    with pytest.raises(web_fetch_orchestrator._FetchContentConversionError) as exc_info:
        web_fetch_orchestrator._fetch_and_convert_content(
            "https://example.com/report",
            timeout_seconds=1.0,
            resolve_timeout_budget=lambda timeout_seconds, **kwargs: timeout_seconds,
            normalize_url_for_http=web_tools._normalize_url_for_http,
            build_referer=web_tools._build_referer,
            convert_html=lambda **kwargs: pytest.fail("conversion must not run"),
            convert_non_html=lambda raw_bytes, stream_name: ("", "", ""),
            session=cast(requests.Session, session),
            headers={},
            egress_policy=_public_test_policy(),
            resource_budget=_DEFAULT_RESOURCE_BUDGET,
        )

    assert exc_info.value.failure_reason == "meta_refresh_requires_browser"
    assert session.calls == [
        ("GET", "https://example.com/report", True),
        ("GET", "https://example.com/redirected", True),
    ]


def test_fetch_body_limit_maps_to_structured_tool_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """body 超限必须投影为结构化 fetch_web_page 失败。"""

    session = _QueuedSession(
        [
            _raw_response(
                url="http://127.0.0.1/",
                status_code=200,
                body=b"home",
                headers={"Content-Type": "text/html"},
            ),
            _raw_response(
                url="http://127.0.0.1/report",
                status_code=200,
                body=b"head",
                headers={"Content-Type": "text/html"},
            ),
            _raw_response(
                url="http://127.0.0.1/report",
                status_code=200,
                body=b"0123456789",
                headers={"Content-Type": "text/html"},
            ),
        ]
    )
    monkeypatch.setattr(web_tools, "_get_web_session", lambda: cast(requests.Session, session))
    monkeypatch.setattr(web_fetch_orchestrator, "_send_authorized_request", _queued_send_authorized_request)
    definition = _definitions_by_name(
        _discover_definitions(
            {
                "allow_private_network_url": True,
                "resource_budget": _resource_budget_json(
                    wire_body_bytes=4,
                    decoded_body_bytes=4,
                    warmup_body_bytes=4,
                ),
            }
        )
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/report"}),
            _context(timeout_seconds=None),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "response_body_too_large"
    assert "size limit" in outcome.result.message
    assert outcome.result.meta is not None


def test_fetch_body_limit_context_does_not_decode_unbounded_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """body limit 异常上下文不得调用会读取剩余 raw body 的解码 helper。"""

    response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=b"0123456789",
        headers={"Content-Type": "text/html"},
    )
    decode_calls: list[str] = []

    def fake_decode_response_text(decoded_response: requests.Response) -> str:
        """记录非预期响应解码调用。

        :param decoded_response: 当前响应对象。
        :returns: 空字符串。
        """

        decode_calls.append(str(decoded_response.url))
        return ""

    monkeypatch.setattr(web_fetch_orchestrator, "_decode_response_text", fake_decode_response_text)

    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded):
        web_fetch_orchestrator._read_limited_response_body(
            response,
            resource_budget=_resource_budget(
                wire_body_bytes=4,
                decoded_body_bytes=4,
            ),
        )

    assert decode_calls == []


def test_fetch_http_error_body_is_bounded_before_status_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP error response 也必须先过 body cap，不能由诊断 snippet 无界读取。"""

    session = _QueuedSession(
        [
            _raw_response(
                url="https://example.com/report",
                status_code=500,
                body=b"x" * 10,
                headers={"Content-Type": "text/html"},
            )
        ]
    )
    monkeypatch.setattr(
        web_fetch_orchestrator,
        "_send_authorized_request",
        _queued_send_authorized_request,
    )

    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded):
        web_fetch_orchestrator._fetch_and_convert_content(
            "https://example.com/report",
            timeout_seconds=1.0,
            resolve_timeout_budget=lambda timeout_seconds, **kwargs: timeout_seconds,
            normalize_url_for_http=web_tools._normalize_url_for_http,
            build_referer=web_tools._build_referer,
            convert_html=lambda **kwargs: pytest.fail("conversion must not run"),
            convert_non_html=lambda raw_bytes, stream_name: ("", "", ""),
            session=cast(requests.Session, session),
            headers={},
            egress_policy=_public_test_policy(),
            resource_budget=_resource_budget(
                wire_body_bytes=4,
                decoded_body_bytes=4,
            ),
        )


@pytest.mark.parametrize("invalid_value", [True, 0, -1, cast(int, 1.5)])
def test_resource_budget_constructor_rejects_bool_and_non_positive_integer(
    invalid_value: int,
) -> None:
    """资源预算 owner 构造期必须拒绝 bool、非整数与非正整数。"""

    with pytest.raises(ValueError, match="wire_body_bytes"):
        WebResourceBudget(wire_body_bytes=invalid_value)


def test_resource_budget_provider_config_complete_object_and_default() -> None:
    """完整 resource_budget 成功，整个 object 缺失时使用完整默认。"""

    parsed = web_provider._parse_config(
        {"resource_budget": _resource_budget_json()}
    )
    defaulted = web_provider._parse_config({})

    assert parsed.resource_budget == _resource_budget()
    assert defaulted.resource_budget == WebResourceBudget()

    with pytest.raises(ValueError, match="must be an object"):
        web_provider._parse_config({"resource_budget": "invalid"})


@pytest.mark.parametrize(
    "missing_field",
    [
        "wire_body_bytes",
        "decoded_body_bytes",
        "warmup_body_bytes",
        "browser_dom_chars",
        "browser_text_chars",
        "diagnostic_error_chars",
        "diagnostic_events",
    ],
)
def test_resource_budget_provider_config_rejects_partial_object(
    missing_field: str,
) -> None:
    """resource_budget 少任一字段都必须整体 fail fast。"""

    budget_json = _resource_budget_json()
    budget_json.pop(missing_field)

    with pytest.raises(ValueError, match="missing fields"):
        web_provider._parse_config({"resource_budget": budget_json})


@pytest.mark.parametrize("invalid_value", [True, 0, -1])
def test_resource_budget_provider_config_rejects_unknown_and_invalid_values(
    invalid_value: int,
) -> None:
    """resource_budget 未知字段、bool 与非正整数不得 partial fallback。"""

    invalid_budget = _resource_budget_json()
    invalid_budget["wire_body_bytes"] = invalid_value
    with pytest.raises(ValueError, match="wire_body_bytes"):
        web_provider._parse_config({"resource_budget": invalid_budget})

    unknown_budget = _resource_budget_json()
    unknown_budget["unexpected"] = 1
    with pytest.raises(ValueError, match="unknown fields"):
        web_provider._parse_config({"resource_budget": unknown_budget})


@pytest.mark.parametrize(
    ("header_encoding", "encoder"),
    [
        ("gzip", "gzip"),
        ("deflate", "deflate"),
        ("deflate", "raw-deflate"),
    ],
)
def test_decompress_incremental_codec_exact_limit_and_limit_plus_one(
    monkeypatch: pytest.MonkeyPatch,
    header_encoding: str,
    encoder: str,
) -> None:
    """gzip/zlib/raw-deflate 必须增量解码并在 limit+1 物化前失败。"""

    monkeypatch.setattr(web_fetch_orchestrator, "_FETCH_BODY_CHUNK_BYTES", 3)
    exact_body = b"incremental-body"
    exact_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=_encode_http_body(exact_body, encoder),
        headers={"Content-Encoding": header_encoding},
    )
    exact_budget = _resource_budget(
        wire_body_bytes=1024,
        decoded_body_bytes=len(exact_body),
    )
    assert web_fetch_orchestrator._read_limited_response_body(
        exact_response,
        resource_budget=exact_budget,
    ) == exact_body

    overflow_body = exact_body + b"!"
    overflow_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=_encode_http_body(overflow_body, encoder),
        headers={"Content-Encoding": header_encoding},
    )
    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded) as exc_info:
        web_fetch_orchestrator._read_limited_response_body(
            overflow_response,
            resource_budget=exact_budget,
        )
    assert exc_info.value.observed_bytes == len(exact_body) + 1


def test_identity_body_exact_decoded_limit_and_limit_plus_one() -> None:
    """未编码 body 必须独立遵守 decoded cap 的 exact 与 limit-plus-one 边界。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: identity body 未遵守 decoded cap owner contract 时抛出。
    """

    exact_body = b"identity-body"
    exact_budget = _resource_budget(
        wire_body_bytes=1024,
        decoded_body_bytes=len(exact_body),
    )
    exact_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=exact_body,
    )
    assert web_fetch_orchestrator._read_limited_response_body(
        exact_response,
        resource_budget=exact_budget,
    ) == exact_body

    overflow_body = exact_body + b"!"
    overflow_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=overflow_body,
    )
    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded) as exc_info:
        web_fetch_orchestrator._read_limited_response_body(
            overflow_response,
            resource_budget=exact_budget,
        )
    assert exc_info.value.limit_kind == "decompressed"
    assert exc_info.value.observed_bytes == len(exact_body) + 1


def test_decompress_incremental_multi_layer_and_compression_bomb() -> None:
    """多层 encoding 与压缩炸弹都必须逐层受 decoded cap 约束。"""

    body = b"bounded multi layer"
    multi_layer_wire = zlib.compress(gzip.compress(body))
    multi_layer_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=multi_layer_wire,
        headers={"Content-Encoding": "gzip, deflate"},
    )
    assert web_fetch_orchestrator._read_limited_response_body(
        multi_layer_response,
        resource_budget=_resource_budget(
            wire_body_bytes=1024,
            decoded_body_bytes=1024,
        ),
    ) == body

    bomb_response = _raw_response(
        url="https://example.com/bomb",
        status_code=200,
        body=gzip.compress(b"x" * 10_000),
        headers={"Content-Encoding": "gzip"},
    )
    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded) as exc_info:
        web_fetch_orchestrator._read_limited_response_body(
            bomb_response,
            resource_budget=_resource_budget(
                wire_body_bytes=1024,
                decoded_body_bytes=100,
            ),
        )
    assert exc_info.value.observed_bytes == 101


def test_decompress_brotli_without_bounded_output_api_is_unsupported() -> None:
    """不能限制单次 decoder 输出的 brotli 路径必须显式 unsupported。"""

    response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=b"synthetic-brotli",
        headers={"Content-Encoding": "br"},
    )

    with pytest.raises(RuntimeError, match="有界 brotli"):
        web_fetch_orchestrator._read_limited_response_body(
            response,
            resource_budget=_resource_budget(),
        )
    assert web_tools._build_fetch_headers("https://example.com/report")[
        "Accept-Encoding"
    ] == "gzip, deflate"


def test_decompress_zstd_streaming_when_dependency_available() -> None:
    """zstandard 可用时必须通过 stream_reader 完成有界解码。"""

    zstandard = cast(
        _ZstdTestModule,
        pytest.importorskip("zstandard", reason="zstandard is optional"),
    )
    body = b"zstd bounded body"
    response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=zstandard.ZstdCompressor().compress(body),
        headers={"Content-Encoding": "zstd"},
    )

    assert web_fetch_orchestrator._read_limited_response_body(
        response,
        resource_budget=_resource_budget(decoded_body_bytes=len(body)),
    ) == body


def test_warmup_streams_only_budgeted_body_and_closes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warmup 只能流式消费 owner budget，并在复制 headers 后关闭 lease。"""

    source = _InspectableBytesIO(b"x" * 1024)
    response = _CloseCountingResponse()
    response.status_code = 200
    response.url = "https://example.com/"
    response.raw = HTTPResponse(body=source, preload_content=False)
    session = _QueuedSession([response])
    monkeypatch.setattr(
        web_fetch_orchestrator,
        "_send_authorized_request",
        _queued_send_authorized_request,
    )

    result = web_fetch_orchestrator._warmup_domain(
        cast(requests.Session, session),
        url="https://example.com/report",
        timeout_seconds=1.0,
        headers={},
        resolve_timeout_budget=web_tools._resolve_timeout_budget,
        build_domain_home_url=web_tools._build_domain_home_url,
        normalize_url_for_http=web_tools._normalize_url_for_http,
        is_timeout_like_exception=web_tools._is_timeout_like_exception,
        egress_policy=_public_test_policy(),
        resource_budget=_resource_budget(warmup_body_bytes=7),
    )

    assert result["consumed_body_bytes"] == 7
    assert session.calls == [("GET", "https://example.com/", True)]
    assert source.tell() == 7
    assert response.close_count == 1


def test_playwright_budget_preflight_uses_only_tree_walker_before_projection() -> None:
    """DOM 超限预检不得调用完整 serialization 或 full text extraction。"""

    page = _BudgetProbePage(
        metrics={
            "domChars": 11,
            "textChars": 1,
            "domExceeded": True,
            "textExceeded": False,
        },
        html="must-not-be-read",
        page_text="must-not-be-read",
    )
    budget = _resource_budget(browser_dom_chars=10, browser_text_chars=10)

    with pytest.raises(
        web_playwright_backend._BrowserResourceBudgetExceeded,
        match="browser_dom_too_large",
    ):
        web_playwright_backend._materialize_bounded_page_projection(
            cast(web_playwright_backend._PageProtocol, page),
            resource_budget=budget,
        )

    assert page.content_calls == 0
    assert len(page.evaluate_calls) == 1
    script, limits = page.evaluate_calls[0]
    assert "document.createTreeWalker" in script
    assert limits == {"domLimit": 10, "textLimit": 10}
    for forbidden in (
        "page.content(",
        "outerHTML",
        "innerHTML",
        "textContent",
        "innerText",
    ):
        assert forbidden not in script


def test_playwright_budget_rechecks_dynamic_full_projection_lengths() -> None:
    """预检后动态变大的 HTML/text 必须由实际长度复核拒绝。"""

    dynamic_dom_page = _BudgetProbePage(
        metrics={
            "domChars": 5,
            "textChars": 2,
            "domExceeded": False,
            "textExceeded": False,
        },
        html="x" * 11,
        page_text="ok",
    )
    budget = _resource_budget(browser_dom_chars=10, browser_text_chars=10)
    with pytest.raises(
        web_playwright_backend._BrowserResourceBudgetExceeded,
        match="browser_dom_too_large",
    ):
        web_playwright_backend._materialize_bounded_page_projection(
            cast(web_playwright_backend._PageProtocol, dynamic_dom_page),
            resource_budget=budget,
        )
    assert dynamic_dom_page.content_calls == 1
    assert len(dynamic_dom_page.evaluate_calls) == 1

    dynamic_text_page = _BudgetProbePage(
        metrics={
            "domChars": 5,
            "textChars": 2,
            "domExceeded": False,
            "textExceeded": False,
        },
        html="short",
        page_text="x" * 11,
    )
    with pytest.raises(
        web_playwright_backend._BrowserResourceBudgetExceeded,
        match="browser_text_too_large",
    ):
        web_playwright_backend._materialize_bounded_page_projection(
            cast(web_playwright_backend._PageProtocol, dynamic_text_page),
            resource_budget=budget,
        )
    assert dynamic_text_page.content_calls == 1
    assert len(dynamic_text_page.evaluate_calls) == 2


def test_playwright_full_text_failure_logs_debug_and_falls_back_to_html(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """完整页面文本提取失败必须记录 debug 并保持 HTML fallback。

    Args:
        caplog: pytest 日志捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: fallback 行为或 owner-local debug 日志不符合契约时抛出。
    """

    caplog.set_level(logging.DEBUG, logger=web_playwright_backend.__name__)
    page = _BudgetProbePage(
        metrics={
            "domChars": 5,
            "textChars": 2,
            "domExceeded": False,
            "textExceeded": False,
        },
        html="<p>fallback</p>",
        page_text="must-not-be-returned",
        page_text_error=RuntimeError("synthetic full text extraction failure"),
    )

    projection = web_playwright_backend._materialize_bounded_page_projection(
        cast(web_playwright_backend._PageProtocol, page),
        resource_budget=_resource_budget(
            browser_dom_chars=64,
            browser_text_chars=64,
        ),
    )

    assert projection.html == "<p>fallback</p>"
    assert projection.page_text == projection.html
    assert len(page.evaluate_calls) == 2
    assert any(
        record.name == web_playwright_backend.__name__
        and record.levelno == logging.DEBUG
        and "Playwright 页面全文本提取失败，回退到 HTML。" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize(
    "failure_code",
    ["browser_dom_too_large", "browser_text_too_large"],
)
def test_playwright_budget_failure_projects_stable_tool_error(
    monkeypatch: pytest.MonkeyPatch,
    failure_code: str,
) -> None:
    """浏览器 DOM/text 超限必须投影为同名稳定工具失败码。"""

    def fake_fetch_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """返回确定性 browser budget failure。

        Args:
            url: 目标 URL。
            timeout_seconds: browser timeout。
            headers: 请求头。
            timeout_budget: 工具预算。
            deadline_monotonic: 工具 deadline。
            playwright_channel: browser channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: Web 出站策略。
            resource_budget: Web 资源预算。
            cancellation_token: 取消令牌。

        Returns:
            确定性资源超限 payload。

        Raises:
            无。
        """

        del (
            url,
            timeout_seconds,
            headers,
            timeout_budget,
            deadline_monotonic,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            resource_budget,
            cancellation_token,
        )
        return {
            "ok": False,
            "availability": "unprocessable",
            "reason": failure_code,
        }

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_with_playwright,
    )

    with pytest.raises(web_tools.ToolBusinessError) as exc_info:
        web_tools._try_playwright_fallback(
            url="http://127.0.0.1/report",
            timeout_seconds=1.0,
            headers={},
            timeout_budget=None,
            deadline_monotonic=None,
            egress_policy=WebEgressPolicy(allow_private_network=True),
            resource_budget=_DEFAULT_RESOURCE_BUDGET,
        )
    assert exc_info.value.code == failure_code


@pytest.mark.parametrize("http_status", [200, 401, 403, 429, 500, 503])
def test_challenge_strong_vendor_signal_is_confirmed_for_all_statuses(
    http_status: int,
) -> None:
    """强 vendor token 的 confirmed 决策不得依赖旧 status allowlist。"""

    result = web_challenge_detection.detect_bot_challenge(
        response=None,
        http_status=http_status,
        content_text="asset from challenges.cloudflare.com",
    )

    assert result.decision is web_challenge_detection.BotChallengeDecision.CONFIRMED
    assert (
        web_challenge_detection.BotChallengeEvidenceClass.STRONG_VENDOR_CONTENT
        in result.evidence_classes
    )


def test_challenge_broad_text_and_header_single_signals_are_only_suspected() -> None:
    """普通正文引用或单一基础设施/header 信号不能单独 confirmed。"""

    broad_text = web_challenge_detection.detect_bot_challenge(
        response=None,
        http_status=200,
        content_text="The article quoted an access denied error from another service.",
    )
    infrastructure_header = web_challenge_detection.detect_bot_challenge(
        response=None,
        response_headers={"cf-ray": "synthetic"},
        http_status=200,
        content_text="ordinary report",
    )
    vendor_header = web_challenge_detection.detect_bot_challenge(
        response=None,
        response_headers={"x-datadome": "synthetic"},
        http_status=200,
        content_text="ordinary report",
    )

    assert broad_text.decision is web_challenge_detection.BotChallengeDecision.SUSPECTED
    assert infrastructure_header.decision is web_challenge_detection.BotChallengeDecision.SUSPECTED
    assert vendor_header.decision is web_challenge_detection.BotChallengeDecision.SUSPECTED


def test_challenge_independent_signal_combinations_confirm_and_own_fallback() -> None:
    """宽泛组合信号可 confirmed，fallback action 只消费 decision/availability。"""

    two_text_signals = web_challenge_detection.detect_bot_challenge(
        response=None,
        http_status=200,
        content_text="access denied; please verify you are human",
    )
    text_and_vendor_header = web_challenge_detection.detect_bot_challenge(
        response=None,
        response_headers={"x-datadome": "synthetic"},
        http_status=200,
        content_text="access denied",
    )

    assert two_text_signals.decision is web_challenge_detection.BotChallengeDecision.CONFIRMED
    assert text_and_vendor_header.decision is web_challenge_detection.BotChallengeDecision.CONFIRMED
    assert web_challenge_detection.challenge_fallback_action(
        decision=two_text_signals.decision,
        browser_available=True,
    ) is web_challenge_detection.ChallengeFallbackAction.TRY_BROWSER
    assert web_challenge_detection.challenge_fallback_action(
        decision=two_text_signals.decision,
        browser_available=False,
    ) is web_challenge_detection.ChallengeFallbackAction.FAIL_BLOCKED


def test_challenge_confirmed_http_500_invokes_fallback_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """confirmed challenge + HTTP 500 也必须且只能调用一次 browser fallback。"""

    session = _QueuedSession(
        [
            _raw_response(
                url="http://127.0.0.1/",
                status_code=200,
                body=b"home",
                headers={"Content-Type": "text/html"},
            ),
            _raw_response(
                url="http://127.0.0.1/report",
                status_code=200,
                body=b"",
                headers={"Content-Type": "text/html"},
            ),
            _raw_response(
                url="http://127.0.0.1/report",
                status_code=500,
                body=b"challenges.cloudflare.com",
                headers={"Content-Type": "text/html"},
            ),
        ]
    )
    def get_test_session() -> requests.Session:
        """返回 challenge integration 使用的 queued Session。

        Args:
            无。

        Returns:
            当前测试的 queued Session。

        Raises:
            无。
        """

        return cast(requests.Session, session)

    monkeypatch.setattr(web_tools, "_get_web_session", get_test_session)
    monkeypatch.setattr(
        web_fetch_orchestrator,
        "_send_authorized_request",
        _queued_send_authorized_request,
    )
    fallback_calls: list[str] = []

    def fake_playwright_fallback(
        *,
        url: str,
        timeout_seconds: float,
        headers: dict[str, str],
        timeout_budget: float | None,
        deadline_monotonic: float | None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """记录 confirmed challenge browser fallback。

        Args:
            url: 原始 URL。
            timeout_seconds: browser timeout。
            headers: 请求头。
            timeout_budget: 工具预算。
            deadline_monotonic: 工具 deadline。
            playwright_channel: browser channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: Web 出站策略。
            resource_budget: Web 资源预算。
            cancellation_token: 取消令牌。

        Returns:
            确定性 browser 成功 payload。

        Raises:
            无。
        """

        del (
            timeout_seconds,
            headers,
            timeout_budget,
            deadline_monotonic,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            resource_budget,
            cancellation_token,
        )
        fallback_calls.append(url)
        return {"ok": True, "content": "browser result"}

    monkeypatch.setattr(web_tools, "_try_playwright_fallback", fake_playwright_fallback)

    result = web_tools._fetch_web_page_business(
        url="http://127.0.0.1/report",
        config=web_tools.WebToolsConfig(allow_private_network_url=True),
        timeout_budget=None,
        cancellation_token=cast(CancellationToken, _OpenCancellationToken()),
    )

    assert result["content"] == "browser result"
    assert fallback_calls == ["http://127.0.0.1/report"]


def test_duckduckgo_known_shape_and_exact_half_malformed_are_valid() -> None:
    """已知 result shape 可解析，50% malformed 不超过冻结阈值。"""

    html = """
    <html><body>
      <div class="result">
        <a class="result__a" href="https://example.com/a">Access denied case study</a>
      </div>
      <div class="result"><span>malformed</span></div>
    </body></html>
    """

    results = web_search_providers._parse_duckduckgo_html(
        html=html,
        response=None,
        max_results=1,
        normalize_whitespace=web_tools._normalize_whitespace,
    )

    assert results == [
        {
            "title": "Access denied case study",
            "url": "https://example.com/a",
            "snippet": "",
            "published_date": "",
        }
    ]


@pytest.mark.parametrize("marker", ["No results.", "No more results."])
def test_duckduckgo_explicit_no_results_allowlist(marker: str) -> None:
    """只有封闭 no-results 文本才能完成空成功。"""

    results = web_search_providers._parse_duckduckgo_html(
        html=f'<html><div class="no-results">{marker}</div></html>',
        response=None,
        max_results=5,
        normalize_whitespace=web_tools._normalize_whitespace,
    )

    assert results == []


@pytest.mark.parametrize(
    "html",
    [
        "<html><div class='unknown-results'>nothing</div></html>",
        "<html><div class='no-results'>Try another query</div></html>",
        (
            "<html><div class='result'><a class='result__a' "
            "href='https://example.com/a'>valid</a></div>"
            "<div class='result'>bad one</div><div class='result'>bad two</div></html>"
        ),
        "<html><div class='result'>all malformed</div></html>",
    ],
)
def test_duckduckgo_shape_drift_and_malformed_threshold_fail_closed(
    html: str,
) -> None:
    """未知 HTML、未知 empty marker、>50%/100% malformed 都不是空成功。"""

    with pytest.raises(
        web_search_providers.WebSearchProviderResponseError,
        match="DuckDuckGo",
    ) as exc_info:
        web_search_providers._parse_duckduckgo_html(
            html=html,
            response=None,
            max_results=5,
            normalize_whitespace=web_tools._normalize_whitespace,
        )
    assert exc_info.value.reason == "response_shape_changed"


@pytest.mark.parametrize(
    "html",
    [
        (
            "<html>challenges.cloudflare.com<div class='no-results'>No results.</div>"
            "<div class='result'><a class='result__a' "
            "href='https://example.com/a'>valid</a></div></html>"
        ),
        (
            "<html><form action='/login'><input type='password'></form>"
            "<div class='no-results'>No results.</div></html>"
        ),
        (
            "<html><form id='challenge-form'></form>"
            "<div class='result'><a class='result__a' "
            "href='https://example.com/a'>valid</a></div></html>"
        ),
    ],
)
def test_duckduckgo_challenge_or_login_shape_overrides_results_and_empty(
    html: str,
) -> None:
    """challenge/login/anomaly shape 必须覆盖 result 与 no-results。"""

    with pytest.raises(web_search_providers.WebSearchProviderResponseError) as exc_info:
        web_search_providers._parse_duckduckgo_html(
            html=html,
            response=None,
            max_results=5,
            normalize_whitespace=web_tools._normalize_whitespace,
        )
    assert exc_info.value.reason in {
        "challenge_response",
        "challenge_or_login_shape",
    }


def test_duckduckgo_shape_drift_projects_typed_search_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider shape drift 必须投影 search_provider_response_invalid。"""

    def fail_search_business(
        *,
        query: str,
        domains: list[str] | None,
        recency_days: int | None,
        max_results: int,
        config: web_tools.WebToolsConfig,
        timeout_budget: float | None,
        cancellation_token: CancellationToken,
    ) -> dict[str, JsonValue]:
        """模拟 DuckDuckGo response shape drift。

        Args:
            query: 搜索词。
            domains: 域名过滤。
            recency_days: 时效过滤。
            max_results: 结果上限。
            config: Web 配置。
            timeout_budget: 工具预算。
            cancellation_token: 取消令牌。

        Returns:
            不返回。

        Raises:
            WebSearchProviderResponseError: 始终抛出。
        """

        del (
            query,
            domains,
            recency_days,
            max_results,
            config,
            timeout_budget,
            cancellation_token,
        )
        raise web_search_providers.WebSearchProviderResponseError(
            reason="response_shape_changed",
            message="DuckDuckGo response shape changed.",
        )

    monkeypatch.setattr(web_tools, "_search_web_business", fail_search_business)
    outcome = asyncio.run(
        web_tools._call_search_web(
            call=_call("search_web", {"query": "revenue"}),
            context=_context(timeout_seconds=1.0),
            config=web_tools.WebToolsConfig(provider="duckduckgo"),
            provider_lock=asyncio.Lock(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "search_provider_response_invalid"
    assert outcome.result.hint is not None
    assert "another provider" in outcome.result.hint


def test_tavily_provider_builds_typed_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tavily producer 应把完整配置投影为稳定结果行。"""

    monkeypatch.setenv(web_search_providers.TAVILY_API_KEY_ENV, "test-key")
    captured_payloads: list[Mapping[str, JsonValue]] = []
    responses: list[_CloseCountingResponse] = []

    def fake_post(
        url: str,
        *,
        json: Mapping[str, JsonValue],
        timeout: float,
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool = True,
        stream: bool = False,
    ) -> requests.Response:
        """返回确定性 Tavily JSON response。

        Args:
            url: provider URL。
            json: 请求 JSON。
            timeout: 请求 timeout。
            headers: 可选 headers。
            allow_redirects: 是否允许 requests 自动跟随 redirect。
            stream: 是否流式获取 response。

        Returns:
            确定性 JSON response。

        Raises:
            无。
        """

        del url, timeout
        assert stream is True
        assert allow_redirects is False
        assert headers is not None
        assert headers["Accept-Encoding"] == "gzip, deflate"
        captured_payloads.append(dict(json))
        response = _counting_response(
            url="https://api.tavily.com/search",
            status_code=200,
            body=json_module.dumps(
                {
                    "results": [
                        {
                            "title": " Example ",
                            "url": " https://example.com/report ",
                            "content": " Revenue grew ",
                            "published_date": " 2026-01-01 ",
                        }
                    ]
                }
            ).encode("utf-8"),
        )
        responses.append(response)
        return response

    monkeypatch.setattr(web_search_providers.requests, "post", fake_post)
    rows = web_search_providers._search_with_tavily(
        query="revenue",
        domains=["example.com"],
        recency_days=7,
        max_results=3,
        timeout_seconds=1.0,
        resource_budget=_DEFAULT_RESOURCE_BUDGET,
    )

    assert rows == [
        {
            "title": "Example",
            "url": "https://example.com/report",
            "snippet": "Revenue grew",
            "published_date": "2026-01-01",
        }
    ]
    assert captured_payloads[0]["include_domains"] == ["example.com"]
    assert captured_payloads[0]["days"] == 7
    assert responses[0].close_count == 1


def test_serper_provider_builds_typed_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serper producer 应生成 domain query 与稳定结果行。"""

    monkeypatch.setenv(web_search_providers.SERPER_API_KEY_ENV, "test-key")
    captured_payloads: list[Mapping[str, JsonValue]] = []
    responses: list[_CloseCountingResponse] = []

    def fake_post(
        url: str,
        *,
        json: Mapping[str, JsonValue],
        timeout: float,
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool = True,
        stream: bool = False,
    ) -> requests.Response:
        """返回确定性 Serper JSON response。

        Args:
            url: provider URL。
            json: 请求 JSON。
            timeout: 请求 timeout。
            headers: provider headers。
            allow_redirects: 是否允许 requests 自动跟随 redirect。
            stream: 是否流式获取 response。

        Returns:
            确定性 JSON response。

        Raises:
            无。
        """

        del url, timeout
        assert stream is True
        assert allow_redirects is False
        assert headers is not None
        assert headers["Accept-Encoding"] == "gzip, deflate"
        captured_payloads.append(dict(json))
        response = _counting_response(
            url="https://google.serper.dev/search",
            status_code=200,
            body=json_module.dumps(
                {
                    "organic": [
                        {
                            "title": " Example ",
                            "link": " https://example.com/report ",
                            "snippet": " Revenue grew ",
                        }
                    ]
                }
            ).encode("utf-8"),
        )
        responses.append(response)
        return response

    monkeypatch.setattr(web_search_providers.requests, "post", fake_post)
    rows = web_search_providers._search_with_serper(
        query="revenue",
        domains=["example.com"],
        recency_days=7,
        max_results=3,
        timeout_seconds=1.0,
        resource_budget=_DEFAULT_RESOURCE_BUDGET,
    )

    assert rows == [
        {
            "title": "Example",
            "url": "https://example.com/report",
            "snippet": "Revenue grew",
            "published_date": "",
        }
    ]
    assert captured_payloads[0]["q"] == "(revenue) (site:example.com)"
    assert captured_payloads[0]["tbs"] == "qdr:d7"
    assert responses[0].close_count == 1


@pytest.mark.parametrize(
    ("wire_limit_delta", "expected_error"),
    ((0, False), (-1, True)),
)
def test_duckduckgo_provider_streams_budgeted_body_and_closes_response(
    monkeypatch: pytest.MonkeyPatch,
    wire_limit_delta: int,
    expected_error: bool,
) -> None:
    """DuckDuckGo provider 必须在解析前按 wire budget 流式读取并关闭 response。"""

    body = b'<div class="no-results">No results.</div>'
    response = _counting_response(
        url="https://duckduckgo.com/html/",
        status_code=200,
        body=body,
    )

    def fake_get(
        url: str,
        *,
        params: Mapping[str, str],
        timeout: float,
        headers: Mapping[str, str],
        allow_redirects: bool,
        stream: bool,
    ) -> requests.Response:
        """返回带关闭计数的流式 DuckDuckGo response。

        Args:
            url: provider URL。
            params: query 参数。
            timeout: 请求 timeout。
            headers: provider headers。
            allow_redirects: 是否允许 requests 自动跟随 redirect。
            stream: 是否流式获取 response。

        Returns:
            可计数关闭的 response。

        Raises:
            无。
        """

        del url, timeout
        assert params == {"q": "revenue"}
        assert headers["Accept-Encoding"] == "gzip, deflate"
        assert allow_redirects is False
        assert stream is True
        return response

    monkeypatch.setattr(web_search_providers.requests, "get", fake_get)
    budget = _resource_budget(
        wire_body_bytes=len(body) + wire_limit_delta,
        decoded_body_bytes=len(body),
    )

    if expected_error:
        with pytest.raises(web_search_providers.WebSearchProviderResourceError):
            web_search_providers._search_with_duckduckgo(
                query="revenue",
                domains=[],
                max_results=3,
                timeout_seconds=1.0,
                resource_budget=budget,
            )
    else:
        assert web_search_providers._search_with_duckduckgo(
            query="revenue",
            domains=[],
            max_results=3,
            timeout_seconds=1.0,
            resource_budget=budget,
        ) == []

    assert response.close_count == 1


def test_search_resource_budget_failure_projects_stable_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """最终 search response 超限必须投影稳定 resource failure。"""

    def fail_search_business(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """模拟所有 provider 的 response resource failure。

        Args:
            kwargs: search business 参数。

        Returns:
            不返回。

        Raises:
            WebSearchProviderResourceError: 始终抛出资源失败。
        """

        del kwargs
        raise web_search_providers.WebSearchProviderResourceError(
            "Search provider response body exceeded the configured Web resource limit."
        )

    monkeypatch.setattr(web_tools, "_search_web_business", fail_search_business)
    outcome = asyncio.run(
        web_tools._call_search_web(
            call=_call("search_web", {"query": "revenue"}),
            context=_context(timeout_seconds=1.0),
            config=web_tools.WebToolsConfig(provider="duckduckgo"),
            provider_lock=asyncio.Lock(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "response_body_too_large"
    assert outcome.result.hint == (
        web_tool_projection_text.WEB_SEARCH_RESPONSE_BODY_TOO_LARGE_HINT
    )


def test_playwright_route_blocks_private_request_before_continue() -> None:
    """Playwright request 目标必须在 continue 前复用 URL safety owner。"""

    class FakeRequest:
        """测试用 Playwright request。"""

        resource_type: str = "document"
        url: str = "http://127.0.0.1/internal"

    class FakeRoute:
        """测试用 Playwright route。"""

        request: web_playwright_backend._RouteRequestProtocol = FakeRequest()
        aborted: bool = False
        continued: bool = False

        def abort(self) -> None:
            """记录 abort 调用。"""

            self.aborted = True

        def continue_(self) -> None:
            """记录 continue 调用。"""

            self.continued = True

    route = FakeRoute()

    web_playwright_backend._route_handler_abort_resources(
        route,
        egress_policy=_public_test_policy(),
    )

    assert route.aborted is True
    assert route.continued is False


def test_playwright_public_direct_reports_typed_egress_policy_unavailable() -> None:
    """公网 browser direct 无 peer 证明时必须在 worker 启动前 typed fail closed。"""

    worker_calls: list[str] = []

    def unexpected_worker(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
    ) -> dict[str, JsonValue]:
        """记录不应发生的公网 browser worker 调用。"""

        del (
            timeout_seconds,
            headers,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            resource_budget,
        )
        worker_calls.append(url)
        return {"ok": True}

    result = web_playwright_backend._fetch_and_convert_with_playwright(
        url="https://example.com/report",
        timeout_seconds=1.0,
        egress_policy=_public_test_policy(),
        resource_budget=_DEFAULT_RESOURCE_BUDGET,
        resolve_timeout_budget=lambda timeout_seconds, **kwargs: timeout_seconds,
        playwright_sync_worker=unexpected_worker,
        detect_bot_challenge=lambda **kwargs: web_tools.BotChallengeDetectionResult(
            decision=web_tools.BotChallengeDecision.NONE,
            challenge_signals=(),
            evidence_classes=(),
        ),
    )

    assert result == {
        "ok": False,
        "availability": "unprocessable",
        "reason": "browser_egress_policy_unavailable",
    }
    assert worker_calls == []


def test_playwright_url_safety_error_survives_worker_process() -> None:
    """Playwright worker 子进程必须保留 Web fetch URL safety 异常语义。"""

    worker_kwargs: web_playwright_backend._WorkerKwargs = {
        "url": "https://example.com/report",
        "timeout_seconds": 1.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": "",
        "egress_policy": _public_test_policy(),
        "resource_budget": _DEFAULT_RESOURCE_BUDGET,
    }

    with pytest.raises(web_fetch_orchestrator._FetchUrlSafetyError) as exc_info:
        web_playwright_backend._run_playwright_worker_process(
            playwright_sync_worker=_BlockedPlaywrightWorker(
                blocked_url="http://127.0.0.1/internal",
                blocked_stage="playwright_goto",
            ),
            worker_kwargs=worker_kwargs,
            total_timeout=5.0,
            cancellation_token=None,
        )

    assert exc_info.value.url == "http://127.0.0.1/internal"
    assert exc_info.value.reason == "playwright_goto"


def test_fetch_playwright_url_safety_projects_permission_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright URL safety 拒绝必须投影为 permission_denied。"""

    monkeypatch.setattr(
        web_tools,
        "_warmup_domain",
        lambda *args, **kwargs: {"attempted": True, "timeout_like": True},
    )
    monkeypatch.setattr(web_tools, "_should_escalate_stage_result_to_browser", lambda stage_result: True)

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_playwright_backend.WebPayload:
        """模拟 Playwright 导航阶段 URL safety 拒绝。

        :param url: 目标 URL。
        :param timeout_seconds: 浏览器抓取超时。
        :param headers: 请求头。
        :param timeout_budget: 工具总预算。
        :param deadline_monotonic: 工具调用 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 路径。
        :param egress_policy: Web 出站策略。
        :param cancellation_token: 取消令牌。
        :returns: 不返回。
        :raises web_fetch_orchestrator._FetchUrlSafetyError: 始终抛出。
        """

        del (
            url,
            timeout_seconds,
            headers,
            timeout_budget,
            deadline_monotonic,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            resource_budget,
            cancellation_token,
        )
        raise web_fetch_orchestrator._FetchUrlSafetyError(
            url="http://127.0.0.1/internal",
            reason="playwright_goto",
        )

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )
    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "https://example.com/report"}),
            _context(timeout_seconds=None),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "permission_denied"
    assert outcome.result.meta is not None


def test_fetch_playwright_cancel_projects_to_host_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright fallback 取消必须投影为 cancelled outcome。"""

    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": False})
    monkeypatch.setattr(web_tools, "_should_escalate_stage_result_to_browser", lambda stage_result: True)
    token = _ManualCancellationToken()
    received_playwright_tokens: list[CancellationToken | None] = []

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """模拟 Playwright worker 在 fallback 内部收到取消。

        :param url: 目标 URL。
        :param timeout_seconds: 浏览器抓取超时。
        :param headers: 请求头。
        :param timeout_budget: 工具总预算。
        :param deadline_monotonic: 工具调用 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 路径。
        :param egress_policy: Web 出站策略。
        :param cancellation_token: 取消令牌。
        :returns: 不返回。
        :raises web_playwright_backend.CancelledError: 始终抛出。
        """

        received_playwright_tokens.append(cancellation_token)
        del (
            url,
            timeout_seconds,
            headers,
            timeout_budget,
            deadline_monotonic,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            resource_budget,
        )
        raise web_playwright_backend.CancelledError("cancelled by host")

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )
    definition = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == "fetch_web_page"
    assert outcome.message == web_tool_projection_text.WEB_FETCH_CANCELLED_MESSAGE
    assert outcome.hint is not None
    assert outcome.hint == web_tool_projection_text.WEB_CANCELLED_HINT
    assert received_playwright_tokens == [token]


def test_search_and_fetch_pass_tool_timeout_budget_to_business(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search/fetch 主路径必须把工具剩余预算传入 HTTP 预算边界。"""

    budgets: list[float | None] = []

    async def fake_to_thread(
        func: Callable[_P, _R],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _R:
        """同步执行业务函数，保留 ``asyncio.to_thread`` 调用形状。"""

        return func(*args, **kwargs)

    def fake_search_business(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 search_web 传入的 timeout budget。"""

        budgets.append(cast(float | None, kwargs.get("timeout_budget")))
        return {
            "query": "revenue",
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "preferred_result_summary": "",
            "next_action": "refine_query",
            "next_action_args": {},
            "hint": "refine query",
            "results": [],
        }

    def fake_fetch_business(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 fetch_web_page 传入的 timeout budget。"""

        budgets.append(cast(float | None, kwargs.get("timeout_budget")))
        return {
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "title": "Example",
            "content": "budgeted content",
            "fetch_backend": "requests",
        }

    monkeypatch.setattr(web_tools.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(web_tools, "_search_web_business", fake_search_business)
    monkeypatch.setattr(web_tools, "_fetch_web_page_business", fake_fetch_business)
    definitions = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )
    context = _context(timeout_seconds=2.5)

    search_outcome = asyncio.run(
        definitions["search_web"].callable(
            _call("search_web", {"query": "revenue"}),
            context,
        )
    )
    fetch_outcome = asyncio.run(
        definitions["fetch_web_page"].callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
            context,
        )
    )

    assert isinstance(search_outcome, ToolCompletedOutcome)
    assert isinstance(fetch_outcome, ToolCompletedOutcome)
    assert budgets == [2.5, 2.5]


def test_try_playwright_fallback_pre_cancel_does_not_start_playwright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fallback 入口已取消时不得启动 Playwright worker。"""

    token = _ManualCancellationToken()
    token.cancel("payload_ref=payload-web digest=sha256:web correlation_id=correlation-web")
    playwright_calls: list[str] = []

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """记录非预期 Playwright worker 调用。

        :param url: 目标 URL。
        :param timeout_seconds: 浏览器抓取超时。
        :param headers: 请求头。
        :param timeout_budget: 工具总预算。
        :param deadline_monotonic: 工具调用 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 路径。
        :param egress_policy: Web 出站策略。
        :param cancellation_token: 取消令牌。
        :returns: 成功结果。
        :raises Exception: 不主动抛出异常。
        """

        del (
            timeout_seconds,
            headers,
            timeout_budget,
            deadline_monotonic,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            resource_budget,
            cancellation_token,
        )
        playwright_calls.append(url)
        return {"ok": True, "content": "unexpected", "title": "unexpected"}

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )

    with pytest.raises(web_tools.WebToolCancelledError) as captured:
        web_tools._try_playwright_fallback(
            url="http://example.com/report",
            timeout_seconds=1.0,
            headers={},
            timeout_budget=None,
            deadline_monotonic=None,
            egress_policy=_public_test_policy(),
            resource_budget=_DEFAULT_RESOURCE_BUDGET,
            cancellation_token=token,
        )

    assert playwright_calls == []
    _assert_no_governance_text(f"{captured.value.message} {captured.value.hint}")


def test_playwright_unpicklable_worker_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不可序列化 Playwright worker 不得回落到同进程执行。"""

    monkeypatch.setattr(
        web_playwright_backend,
        "_is_picklable_worker",
        lambda worker: False,
    )
    worker_calls: list[str] = []

    def fake_worker(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
    ) -> dict[str, JsonValue]:
        """记录不应发生的同进程 Playwright 调用。"""

        del (
            timeout_seconds,
            headers,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            resource_budget,
        )
        worker_calls.append(url)
        return {"ok": True, "content": "unexpected"}

    result = web_playwright_backend._fetch_and_convert_with_playwright(
        url="https://example.com/report",
        timeout_seconds=1.0,
        headers={},
        timeout_budget=1.0,
        deadline_monotonic=None,
        playwright_channel=None,
        playwright_storage_state_path="",
        egress_policy=WebEgressPolicy(allow_private_network=True),
        resource_budget=_DEFAULT_RESOURCE_BUDGET,
        cancellation_token=_OpenCancellationToken(),
        resolve_timeout_budget=lambda timeout_seconds, **kwargs: timeout_seconds,
        playwright_sync_worker=fake_worker,
        detect_bot_challenge=lambda **kwargs: web_tools.BotChallengeDetectionResult(
            decision=web_tools.BotChallengeDecision.NONE,
            challenge_signals=(),
            evidence_classes=(),
        ),
    )

    assert result["ok"] is False
    assert result["reason"] == "playwright_worker_not_picklable"
    assert worker_calls == []


def test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Playwright raw worker cleanup 应通过共享 primitive 清理 synthetic nested child。"""

    if os.name != "posix":
        pytest.skip("process-group cleanup smoke only applies to POSIX")
    caplog.set_level(logging.DEBUG, logger=web_playwright_backend.__name__)
    pid_path = tmp_path / "synthetic-nested-child.pid"
    worker_kwargs: web_playwright_backend._WorkerKwargs = {
        "url": "https://example.com/synthetic",
        "timeout_seconds": 30.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": str(pid_path),
        "egress_policy": WebEgressPolicy(allow_private_network=True),
        "resource_budget": _DEFAULT_RESOURCE_BUDGET,
    }
    process, result_queue = _start_playwright_worker_process(
        worker_callable=_SyntheticNestedPlaywrightWorker(),
        worker_kwargs=worker_kwargs,
    )
    nested_pid: int | None = None
    try:
        nested_pid = _read_pid_file(pid_path, timeout_seconds=3.0)
        assert _pid_exists(nested_pid)

        started_at = time.monotonic()
        cleanup = web_playwright_backend._terminate_playwright_process(process)
        cleanup_elapsed_seconds = time.monotonic() - started_at
        terminate_result = cleanup["terminate"]

        assert terminate_result is not None
        diagnostic = terminate_result.cleanup
        if not diagnostic.group_signal_sent:
            assert diagnostic.reason in {
                ProcessGroupCleanupReason.UNSUPPORTED,
                ProcessGroupCleanupReason.CHILD_PID_UNAVAILABLE,
                ProcessGroupCleanupReason.CHILD_ALREADY_EXITED,
                ProcessGroupCleanupReason.PGID_UNAVAILABLE,
                ProcessGroupCleanupReason.CURRENT_PGID_UNAVAILABLE,
                ProcessGroupCleanupReason.PARENT_PGID_UNAVAILABLE,
                ProcessGroupCleanupReason.PGID_MATCHES_CURRENT_PROCESS_GROUP,
                ProcessGroupCleanupReason.PGID_MATCHES_PARENT_PROCESS_GROUP,
                ProcessGroupCleanupReason.GROUP_SIGNAL_FAILED,
            }
            pytest.skip(f"process-group cleanup fallback: {diagnostic.reason.value}")
        assert diagnostic.reason is ProcessGroupCleanupReason.GROUP_SIGNALED
        assert diagnostic.group_signal_sent is True
        assert "reason=group_signaled" in caplog.text
        assert "group_signal_sent=True" in caplog.text
        assert _wait_for_pid_absent(nested_pid, timeout_seconds=1.0)
        assert cleanup["kill"] is None
        assert terminate_result.elapsed_seconds <= (
            web_playwright_backend._PW_PROCESS_TERMINATE_GRACE_SECONDS
        )
        assert cleanup_elapsed_seconds <= (
            web_playwright_backend._PW_PROCESS_TERMINATE_GRACE_SECONDS
        )
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=1.0)
        if nested_pid is not None and _pid_exists(nested_pid):
            os.kill(nested_pid, signal.SIGKILL)
            _wait_for_pid_absent(nested_pid, timeout_seconds=1.0)
        result_queue.close()
        result_queue.join_thread()


def test_playwright_worker_process_cleanup_supports_running_event_loop(
    tmp_path: Path,
) -> None:
    """Playwright cleanup 在当前线程已有 running loop 时仍应完成。"""

    if os.name != "posix":
        pytest.skip("process-group cleanup bridge smoke only applies to POSIX")
    pid_path = tmp_path / "synthetic-nested-child-loop.pid"
    worker_kwargs: web_playwright_backend._WorkerKwargs = {
        "url": "https://example.com/synthetic-loop",
        "timeout_seconds": 30.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": str(pid_path),
        "egress_policy": WebEgressPolicy(allow_private_network=True),
        "resource_budget": _DEFAULT_RESOURCE_BUDGET,
    }
    process, result_queue = _start_playwright_worker_process(
        worker_callable=_SyntheticNestedPlaywrightWorker(),
        worker_kwargs=worker_kwargs,
    )
    nested_pid: int | None = None
    try:
        nested_pid = _read_pid_file(pid_path, timeout_seconds=3.0)
        cleanup = asyncio.run(_terminate_process_inside_running_loop(process))
        terminate_result = cleanup["terminate"]
        assert terminate_result is not None
        if not terminate_result.cleanup.group_signal_sent:
            pytest.skip(
                "process-group cleanup fallback: "
                f"{terminate_result.cleanup.reason.value}"
            )
        assert terminate_result.cleanup.reason is ProcessGroupCleanupReason.GROUP_SIGNALED
        assert _wait_for_pid_absent(nested_pid, timeout_seconds=1.0)
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=1.0)
        if nested_pid is not None and _pid_exists(nested_pid):
            os.kill(nested_pid, signal.SIGKILL)
            _wait_for_pid_absent(nested_pid, timeout_seconds=1.0)
        result_queue.close()
        result_queue.join_thread()


def test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort(
    tmp_path: Path,
) -> None:
    """可选 live browser cleanup smoke 默认跳过，显式开启后验证 descendants。"""

    if os.environ.get(_LIVE_BROWSER_CLEANUP_SMOKE_ENV) != "1":
        pytest.skip(f"set {_LIVE_BROWSER_CLEANUP_SMOKE_ENV}=1 to run live smoke")
    if os.name != "posix":
        pytest.skip("live browser descendant inspection requires POSIX ps")
    if not _live_playwright_chromium_available():
        pytest.skip("Playwright Chromium binary is not available")
    process_table = _process_table_from_ps()
    if process_table is None:
        pytest.skip("process descendant inspection via ps is unavailable")
    server = _SocketWebServer.start(
        response_body=(
            b"<html><head><title>Live Browser Cleanup</title></head>"
            b"<body>browser cleanup fixture</body></html>"
        ),
        max_connections=8,
    )
    marker_path = tmp_path / "live-browser-ready.txt"
    worker_kwargs: web_playwright_backend._WorkerKwargs = {
        "url": server.url,
        "timeout_seconds": 10.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": str(marker_path),
        "egress_policy": WebEgressPolicy(allow_private_network=True),
        "resource_budget": _DEFAULT_RESOURCE_BUDGET,
    }
    process, result_queue = _start_playwright_worker_process(
        worker_callable=_LiveBrowserLongRunningWorker(),
        worker_kwargs=worker_kwargs,
    )
    descendant_pids: set[int] = set()
    try:
        _wait_for_file(marker_path, timeout_seconds=10.0)
        assert process.pid is not None
        descendant_pids = _descendant_pids(process.pid)
        if not descendant_pids:
            pytest.skip("no live browser descendants were observable")
        cleanup = web_playwright_backend._terminate_playwright_process(process)
        terminate_result = cleanup["terminate"]
        assert terminate_result is not None
        if not terminate_result.cleanup.group_signal_sent:
            pytest.skip(
                "process-group cleanup fallback: "
                f"{terminate_result.cleanup.reason.value}"
            )
        assert _wait_for_pids_absent(
            descendant_pids,
            timeout_seconds=_PROCESS_DESCENDANT_WAIT_SECONDS,
        )
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=1.0)
        _kill_remaining_pids(descendant_pids)
        result_queue.close()
        result_queue.join_thread()
        server.close()


def test_fetch_playwright_fallback_receives_channel_and_storage_state_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright fallback 必须收到 config 派生的 channel 与 storage state。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: browser fallback 参数未由 Web config 派生时抛出。
    """

    storage_dir = tmp_path / "states"
    storage_file = storage_dir / "example.com.json"
    storage_file.parent.mkdir(parents=True)
    storage_file.write_text("{}", encoding="utf-8")
    calls: list[Mapping[str, JsonValue]] = []
    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": False})
    monkeypatch.setattr(web_tools, "_should_escalate_stage_result_to_browser", lambda stage_result: True)

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """记录 browser fallback 参数并返回确定性内容。

        :param url: 目标 URL。
        :param timeout_seconds: 抓取超时。
        :param headers: 请求 headers。
        :param timeout_budget: 工具预算。
        :param deadline_monotonic: 工具 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 文件路径。
        :param egress_policy: Web 出站策略。
        :param cancellation_token: 取消令牌。
        :returns: 确定性抓取内容。
        """

        del (
            headers,
            timeout_budget,
            deadline_monotonic,
            egress_policy,
            resource_budget,
            cancellation_token,
        )
        calls.append(
            {
                "url": url,
                "timeout_seconds": timeout_seconds,
                "playwright_channel": playwright_channel,
                "playwright_storage_state_path": playwright_storage_state_path,
            }
        )
        return {
            "ok": True,
            "final_url": url,
            "title": "Example",
            "content": "browser rendered content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "response_excerpt": "browser rendered content",
            "extraction_source": "playwright",
            "renderer_source": "playwright",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )
    definition = _definitions_by_name(
        _discover_definitions(
            {
                "allow_private_network_url": True,
                "playwright_channel": "msedge",
                "playwright_storage_state_dir": str(storage_dir),
            }
        )
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "https://example.com/page"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert calls[0]["playwright_channel"] == "msedge"
    assert calls[0]["playwright_storage_state_path"] == str(storage_file.resolve())


def test_fetch_playwright_fallback_uses_empty_storage_state_when_dir_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空 storage state dir 配置必须保持 fallback storage state 为空。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 空目录配置被误解析成 storage state path 时抛出。
    """

    calls: list[Mapping[str, JsonValue]] = []
    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": False})
    monkeypatch.setattr(web_tools, "_should_escalate_stage_result_to_browser", lambda stage_result: True)

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        resource_budget: WebResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """记录空 storage state dir 的 browser fallback 参数。

        :param url: 目标 URL。
        :param timeout_seconds: 抓取超时。
        :param headers: 请求 headers。
        :param timeout_budget: 工具预算。
        :param deadline_monotonic: 工具 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 文件路径。
        :param egress_policy: Web 出站策略。
        :param cancellation_token: 取消令牌。
        :returns: 确定性抓取内容。
        """

        del (
            headers,
            timeout_budget,
            deadline_monotonic,
            egress_policy,
            resource_budget,
            cancellation_token,
        )
        calls.append(
            {
                "url": url,
                "timeout_seconds": timeout_seconds,
                "playwright_channel": playwright_channel,
                "playwright_storage_state_path": playwright_storage_state_path,
            }
        )
        return {
            "ok": True,
            "final_url": url,
            "title": "Example",
            "content": "browser rendered content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "response_excerpt": "browser rendered content",
            "extraction_source": "playwright",
            "renderer_source": "playwright",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )
    definition = _definitions_by_name(
        _discover_definitions(
            {
                "allow_private_network_url": True,
                "playwright_channel": "chrome",
                "playwright_storage_state_dir": "",
            }
        )
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "https://example.com/page"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert calls[0]["playwright_channel"] == "chrome"
    assert calls[0]["playwright_storage_state_path"] == ""


def test_invalid_fetch_url_type_fails_before_web_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不可转换的 url JSON 类型必须先由 adapter 拒绝。"""

    calls: list[str] = []

    def fake_fetch_and_convert_content(url: str, **kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录是否进入抓取路径。

        :param url: URL。
        :param kwargs: 抓取辅助参数。
        :returns: 空抓取结果。
        """

        calls.append(url)
        return {}

    monkeypatch.setattr(web_tools, "_fetch_and_convert_content", fake_fetch_and_convert_content)
    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": ["https://example.com"]}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert calls == []


def test_search_provider_unavailable_projects_to_stable_business_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """搜索 provider 全部耗尽必须投影为稳定业务失败。"""

    attempted_providers: list[str] = []

    def fake_search_with_tavily(**kwargs: JsonValue) -> list[web_search_providers.SearchResultRow]:
        """模拟 Tavily provider 不可用。

        :param kwargs: provider 传入的关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 provider 失败。
        """

        del kwargs
        attempted_providers.append("tavily")
        raise RuntimeError("tavily unavailable")

    def fake_search_with_serper(**kwargs: JsonValue) -> list[web_search_providers.SearchResultRow]:
        """模拟 Serper provider 不可用。

        :param kwargs: provider 传入的关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 provider 失败。
        """

        del kwargs
        attempted_providers.append("serper")
        raise RuntimeError("serper unavailable")

    def fake_search_with_duckduckgo(**kwargs: JsonValue) -> list[web_search_providers.SearchResultRow]:
        """模拟 DuckDuckGo provider 不可用。

        :param kwargs: provider 传入的关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 provider 失败。
        """

        del kwargs
        attempted_providers.append("duckduckgo")
        raise RuntimeError("duckduckgo unavailable")

    monkeypatch.setattr(web_search_providers, "_search_with_tavily", fake_search_with_tavily)
    monkeypatch.setattr(web_search_providers, "_search_with_serper", fake_search_with_serper)
    monkeypatch.setattr(web_search_providers, "_search_with_duckduckgo", fake_search_with_duckduckgo)
    monkeypatch.setenv(web_search_providers.TAVILY_API_KEY_ENV, "test-tavily-key")
    monkeypatch.setenv(web_search_providers.SERPER_API_KEY_ENV, "test-serper-key")
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(_call("search_web", {"query": "revenue"}), _context())
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "search_provider_unavailable"
    assert "provider" in outcome.result.message
    assert outcome.result.hint is not None
    assert outcome.result.hint.strip() != ""
    assert attempted_providers == ["tavily", "serper", "duckduckgo"]


def test_web_truncate_specs_use_current_contract() -> None:
    """Web tools 必须声明 current ToolTruncateSpec。"""

    definitions = _definitions_by_name(_discover_definitions({"fetch_truncate_chars": 1234}))

    search_truncate = definitions["search_web"].truncate
    fetch_truncate = definitions["fetch_web_page"].truncate

    assert isinstance(search_truncate, ToolTruncateSpec)
    assert search_truncate.strategy is ToolTruncationStrategy.LIST_ITEMS
    assert search_truncate.target_field == "results"
    assert isinstance(fetch_truncate, ToolTruncateSpec)
    assert fetch_truncate.strategy is ToolTruncationStrategy.TEXT_CHARS
    assert fetch_truncate.limits == {"max_chars": 1234}
    assert fetch_truncate.target_field == "content"


def test_web_provider_serializes_search_and_fetch_business(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一 Web provider 内 search/fetch 不得并发进入业务体。"""

    to_thread_entries: list[str] = []
    business_entries: list[str] = []
    active_business = False
    observed_overlap = False

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录搜索业务体进入并返回确定性 provider 事实。

        :param kwargs: search_web 传入的关键字参数。
        :returns: 确定性 provider 搜索事实。
        :raises Exception: 不主动抛出异常。
        """

        del kwargs
        business_entries.append("search")
        return {
            "query": "revenue",
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "results": [],
        }

    def fake_fetch_and_convert_content(url: str, **kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 fetch 业务体进入并返回确定性页面。

        :param url: URL。
        :param kwargs: 抓取辅助参数。
        :returns: 确定性抓取结果。
        """

        del kwargs
        business_entries.append("fetch")
        return {
            "final_url": url,
            "title": "Example",
            "content": "serialized fetch content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "response_excerpt": "serialized fetch content",
            "extraction_source": "mock",
            "renderer_source": "mock",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": True})
    monkeypatch.setattr(web_tools, "_probe_content_type", lambda *args, **kwargs: {"attempted": True, "ok": True})
    monkeypatch.setattr(web_tools, "_try_playwright_fallback", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_tools, "_fetch_and_convert_content", fake_fetch_and_convert_content)

    definitions = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )

    async def run_competing_calls() -> tuple[ToolCompletedOutcome, ToolCompletedOutcome]:
        """并发执行 search 与 fetch。

        :returns: 两个成功 outcome。
        :raises AssertionError: 搜索未进入业务体或 outcome 类型不符时抛出。
        """

        first_to_thread_entered = asyncio.Event()
        release_first_to_thread = asyncio.Event()

        async def fake_to_thread(
            func: Callable[_P, _R],
            /,
            *args: _P.args,
            **kwargs: _P.kwargs,
        ) -> _R:
            """模拟 ``asyncio.to_thread`` 并记录业务体重叠。

            :param func: 待执行的同步 callable。
            :param args: 位置参数。
            :param kwargs: 关键字参数。
            :returns: callable 返回值。
            :raises Exception: callable 执行失败时透出。
            """

            nonlocal active_business, observed_overlap
            if active_business:
                observed_overlap = True
            active_business = True
            to_thread_entries.append("enter")
            if len(to_thread_entries) == 1:
                first_to_thread_entered.set()
                await release_first_to_thread.wait()
            try:
                return func(*args, **kwargs)
            finally:
                active_business = False

        monkeypatch.setattr(web_tools.asyncio, "to_thread", fake_to_thread)
        search_task = asyncio.create_task(
            definitions["search_web"].callable(
                _call("search_web", {"query": "revenue"}),
                _context(),
            )
        )
        await first_to_thread_entered.wait()
        fetch_task = asyncio.create_task(
            definitions["fetch_web_page"].callable(
                _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
                _context(),
            )
        )
        await asyncio.sleep(0)
        assert to_thread_entries == ["enter"]
        release_first_to_thread.set()
        search_outcome, fetch_outcome = await asyncio.gather(search_task, fetch_task)
        assert isinstance(search_outcome, ToolCompletedOutcome)
        assert isinstance(fetch_outcome, ToolCompletedOutcome)
        return search_outcome, fetch_outcome

    outcomes = asyncio.run(run_competing_calls())

    assert len(outcomes) == 2
    assert observed_overlap is False
    assert to_thread_entries == ["enter", "enter"]
    assert business_entries == ["search", "fetch"]


def test_web_modules_do_not_import_legacy_registry_truncation_fetch_more_or_ui() -> None:
    """Web 模块不得导入 legacy registry/truncation/fetch_more/UI。"""

    for source_path in _WEB_PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not any(
                    node.module == forbidden or node.module.startswith(f"{forbidden}.")
                    for forbidden in _FORBIDDEN_IMPORTS
                ), f"{source_path} imports {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == forbidden or alias.name.startswith(f"{forbidden}.")
                        for forbidden in _FORBIDDEN_IMPORTS
                    ), f"{source_path} imports {alias.name}"


def _discover_definitions(config: Mapping[str, JsonValue]) -> tuple[ToolDefinition, ...]:
    """发现 Web 工具定义。

    :param config: provider config。
    :returns: 工具定义元组。
    """

    return discover_tools(_spec(config)).definitions


def _definitions_by_name(
    definitions: tuple[ToolDefinition, ...],
) -> Mapping[str, ToolDefinition]:
    """按工具名索引定义。

    :param definitions: 工具定义元组。
    :returns: 工具名字典。
    """

    return {definition.name: definition for definition in definitions}


def _mapping_value(value: JsonValue) -> Mapping[str, JsonValue]:
    """把 JsonValue 收窄为 JSON object。

    :param value: 工具返回值。
    :returns: JSON object。
    :raises AssertionError: 值不是 JSON object 时抛出。
    """

    assert isinstance(value, Mapping)
    return value


def _assert_no_governance_text(text: str) -> None:
    """断言 LLM-facing 文本未泄漏 Host 治理字符串。

    :param text: 待检查的 outcome message / hint 文本。
    :returns: 无。
    :raises AssertionError: 文本包含治理字符串时抛出。
    """

    for forbidden in _FORBIDDEN_CANCEL_MESSAGE_PARTS:
        assert forbidden not in text


def _run_definition_process_target(
    definition: ToolDefinition,
    call: ToolCallRequest,
    *,
    timeout_seconds: float | None = 10.0,
) -> JsonValue:
    """构造并直接执行定义声明的 Web process target。

    :param definition: Web 工具定义。
    :param call: 工具调用请求。
    :param timeout_seconds: process-backed 上下文 timeout 标量。
    :returns: process target 返回的 JSON 信封。
    :raises AssertionError: 工具未声明 process-backed execution 时抛出。
    """

    assert isinstance(definition.execution, ProcessBackedToolExecutionCapability)
    target = definition.execution.target_factory.build_process_target(
        call,
        ProcessBackedToolContext(
            run_id="run-web",
            session_id="session-web",
            iteration_id="iteration-web",
            timeout_seconds=timeout_seconds,
            correlation_id="correlation-web",
        ),
    )
    return target()


def _process_arguments_for_tool(tool_name: str) -> Mapping[str, JsonValue]:
    """返回 process target 构造测试所需的最小参数。

    :param tool_name: Web 工具名。
    :returns: 对应工具的参数。
    :raises ValueError: 工具名未知时抛出。
    """

    if tool_name == "search_web":
        return {"query": "revenue"}
    if tool_name == "fetch_web_page":
        return {"url": "http://127.0.0.1/page"}
    raise ValueError(f"unknown web tool: {tool_name}")


def _start_playwright_worker_process(
    *,
    worker_callable: web_playwright_backend._PlaywrightWorkerProtocol,
    worker_kwargs: web_playwright_backend._WorkerKwargs,
) -> tuple[BaseProcess, web_playwright_backend._ResultQueueProtocol]:
    """通过生产 Playwright worker entrypoint 启动测试 worker。

    :param worker_callable: 可 pickle 的 worker callable。
    :param worker_kwargs: worker 关键字参数。
    :returns: 已启动进程与父进程侧结果队列。
    """

    ctx = multiprocessing.get_context("spawn")
    result_queue = cast(
        web_playwright_backend._ResultQueueProtocol,
        ctx.Queue(maxsize=1),
    )
    process = ctx.Process(
        target=web_playwright_backend._playwright_process_entry,
        args=(result_queue, worker_callable, worker_kwargs),
    )
    process.daemon = True
    process.start()
    return process, result_queue


async def _terminate_process_inside_running_loop(
    process: BaseProcess,
) -> web_playwright_backend._PlaywrightProcessCleanup:
    """在已有 running event loop 的线程中调用同步 cleanup helper。

    :param process: 待 cleanup 的 Playwright worker 进程。
    :returns: cleanup 诊断。
    """

    return web_playwright_backend._terminate_playwright_process(process)


def _live_playwright_chromium_available() -> bool:
    """探测当前环境是否可启动 Playwright Chromium。

    :returns: 可启动返回 ``True``，缺少依赖或 browser binary 时返回 ``False``。
    """

    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        browser.close()
        playwright.stop()
    except Exception:
        return False
    return True


def _wait_for_file(path: Path, *, timeout_seconds: float) -> None:
    """等待文件出现。

    :param path: 待等待文件路径。
    :param timeout_seconds: 最多等待秒数。
    :returns: 无返回值。
    :raises AssertionError: 超时仍未出现时抛出。
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.02)
    raise AssertionError(f"file was not written: {path}")


def _process_table_from_ps() -> dict[int, int] | None:
    """通过 POSIX ``ps`` 读取 PID 到 PPID 的映射。

    :returns: PID 到 PPID 的映射；``ps`` 不可用时返回 ``None``。
    """

    try:
        completed = subprocess.run(
            ["ps", "-axo", "pid=,ppid="],
            check=True,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    table: dict[int, int] = {}
    for line in completed.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        table[pid] = ppid
    return table


def _descendant_pids(root_pid: int) -> set[int]:
    """读取某个 PID 当前可观察到的后代 PID 集合。

    :param root_pid: 根进程 PID。
    :returns: 当前进程表中可观察到的后代 PID 集合。
    """

    process_table = _process_table_from_ps()
    if process_table is None:
        return set()
    children_by_parent: dict[int, set[int]] = {}
    for pid, ppid in process_table.items():
        children_by_parent.setdefault(ppid, set()).add(pid)
    descendants: set[int] = set()
    pending = list(children_by_parent.get(root_pid, set()))
    while pending:
        pid = pending.pop()
        if pid in descendants:
            continue
        descendants.add(pid)
        pending.extend(children_by_parent.get(pid, set()))
    return descendants


def _wait_for_pids_absent(pids: set[int], *, timeout_seconds: float) -> bool:
    """等待一组 PID 全部消失。

    :param pids: 待检查 PID 集合。
    :param timeout_seconds: 最多等待秒数。
    :returns: 全部消失返回 ``True``。
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if all(not _pid_exists(pid) for pid in pids):
            return True
        time.sleep(0.05)
    return all(not _pid_exists(pid) for pid in pids)


def _kill_remaining_pids(pids: set[int]) -> None:
    """清理 optional live smoke 中仍可见的后代 PID。

    :param pids: 待清理 PID 集合。
    :returns: 无返回值。
    """

    for pid in pids:
        if not _pid_exists(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            continue
    _wait_for_pids_absent(pids, timeout_seconds=1.0)


def _read_pid_file(path: Path, *, timeout_seconds: float) -> int:
    """在限定时间内读取 PID 文件。

    :param path: PID 文件路径。
    :param timeout_seconds: 最多等待秒数。
    :returns: 文件中记录的 PID。
    :raises AssertionError: 超时仍未读到合法 PID 时抛出。
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            raw_pid = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            time.sleep(0.02)
            continue
        if raw_pid:
            return int(raw_pid)
        time.sleep(0.02)
    raise AssertionError(f"pid file was not written: {path}")


def _pid_exists(pid: int) -> bool:
    """判断 PID 是否仍存在。

    :param pid: 待检查 PID。
    :returns: PID 仍存在返回 ``True``。
    """

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_pid_absent(pid: int, *, timeout_seconds: float) -> bool:
    """等待 PID 消失。

    :param pid: 待检查 PID。
    :param timeout_seconds: 最多等待秒数。
    :returns: PID 在时限内消失返回 ``True``。
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.02)
    return not _pid_exists(pid)


async def _execute_web_runtime_fetch_and_cancel(
    tool_runtime: ToolRuntimeHandle,
    url: str,
    token: _ManualCancellationToken,
) -> ToolFailedOutcome:
    """启动 fetch_web_page 后触发取消并返回 governed outcome。

    :param tool_runtime: 已装配的 ToolRuntime。
    :param url: 本地测试 URL。
    :param token: 可手动取消的 token。
    :returns: ToolRuntime 返回的受治理失败 outcome。
    :raises AssertionError: 结果不是受治理失败 outcome 时抛出。
    """

    task = asyncio.create_task(
        tool_runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(_call("fetch_web_page", {"url": url}),),
                context=_context(cancellation_token=token, timeout_seconds=20.0),
            )
        )
    )
    await asyncio.sleep(0.4)
    token.cancel("cancel-real-web-process")
    result = await asyncio.wait_for(task, timeout=2.0)
    outcome = result.records[0].outcome
    assert isinstance(outcome, ToolFailedOutcome)
    return outcome


def _spec(config: Mapping[str, JsonValue]) -> ToolsDiscoveryProviderSpec:
    """构造 Web provider spec。

    :param config: provider config。
    :returns: provider spec。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id="web-tools",
        location=PythonImportPathProvider("dayu.tools.web:discover_tools"),
        enabled=True,
        config=config,
    )


def _call(name: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    :param name: 工具名。
    :param arguments: 调用参数。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=f"call-{name}",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _context(
    cancellation_token: CancellationToken | None = None,
    timeout_seconds: float | None = 10.0,
) -> BatchToolExecutionContext:
    """构造测试工具执行上下文。

    :param cancellation_token: 可选取消令牌。
    :param timeout_seconds: 可选工具执行预算秒数。
    :returns: 批式执行上下文。
    """

    return BatchToolExecutionContext(
        run_id="run-web",
        session_id="session-web",
        iteration_id="iteration-web",
        timeout_seconds=timeout_seconds,
        cancellation_token=cancellation_token or _OpenCancellationToken(),
        correlation_id="run-web:iteration-web:tool_batch",
    )
