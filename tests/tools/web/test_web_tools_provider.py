"""Web tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
import gzip
import inspect
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
from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime
from multiprocessing.process import BaseProcess
from pathlib import Path
from queue import Empty
from types import ModuleType
from typing import ParamSpec, TypeVar, cast

import pytest
import requests
import playwright.sync_api as playwright_sync_api
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
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
from dayu.tools.web import web_diagnostics
from dayu.tools.web import web_tool_projection_text
from dayu.tools.web import web_search_providers
from dayu.tools.web import web_tools
from dayu.tools.web import web_http_session
from dayu.tools.web import provider as web_provider
from dayu.tools.web.web_egress_policy import (
    AuthorizedHttpTarget,
    WebEgressPolicy,
    WebEgressPolicyError,
)
from dayu.tools.web.web_resource_budget import (
    DEFAULT_BROWSER_RESOURCE_BUDGET,
    DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    DEFAULT_HTTP_RESOURCE_BUDGET,
    BrowserResourceBudget,
    DiagnosticResourceBudget,
    HttpResourceBudget,
    WebResourceBudgets,
)

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
_PROXY_ALLOWED_TRANSPORT_POLICY = web_http_session.WebHttpTransportPolicy(
    dns_peer_proof_enabled=False,
    allow_environment_proxy=True,
)
_PROXY_DENIED_TRANSPORT_POLICY = web_http_session.WebHttpTransportPolicy(
    dns_peer_proof_enabled=False,
    allow_environment_proxy=False,
)
_PEER_PROOF_TRANSPORT_POLICY = web_http_session.WebHttpTransportPolicy(
    dns_peer_proof_enabled=True,
    allow_environment_proxy=False,
)
_ROUTE_ABORT_ACTION = "abort"
_ROUTE_CONTINUE_ACTION = "continue"


def test_web_diagnostic_projection_removes_secret_content_url_headers_exception_and_network() -> None:
    """所有 Web diagnostic producer 只能保留 length/digest 与 safe URL。"""

    sentinel = "9f" * 32
    secret_url = f"https://{sentinel}:{sentinel}@example.com/report" f"?token={sentinel}#{sentinel}"
    projections: list[JsonValue] = [
        web_diagnostics.completed_text_projection(
            stage="success",
            url=secret_url,
            elapsed_seconds=0.1,
            backend=web_diagnostics.WebDiagnosticBackend.REQUESTS,
            content=f"raw html <body>{sentinel}</body>",
            http_status=200,
            response_headers={
                "Authorization": sentinel,
                "Cache-Control": sentinel,
                "X-Network-Secret": sentinel,
            },
        ).to_json(),
        web_diagnostics.failed_projection(
            stage="failure",
            url=secret_url,
            elapsed_seconds=0.1,
            error_code="synthetic",
            error_message=f"exception={sentinel} url={secret_url}",
            max_error_chars=512,
        ).to_json(),
        web_diagnostics.project_network_event(
            event="request",
            url=secret_url,
            method="GET",
            resource_type="document",
            status_code=None,
        ),
    ]

    serialized = json_module.dumps(projections, ensure_ascii=False)
    assert sentinel not in serialized
    assert sentinel[:16] not in serialized
    assert "raw html" not in serialized
    assert "@example.com" not in serialized
    assert "?token=" not in serialized
    assert "#" not in serialized
    assert "content_length" in serialized
    assert "content_digest" in serialized


def test_docling_stream_name_never_includes_url_query_sentinel() -> None:
    """Docling stream name 必须只从 URL path 推断，不能携带 query sentinel。"""

    sentinel = "7d" * 32
    stream_name = web_fetch_orchestrator._infer_docling_stream_name(
        url=f"https://example.com/report.pdf?token={sentinel}",
        content_type="text/plain",
    )

    assert stream_name == "page.pdf"
    assert sentinel not in stream_name


def test_playwright_success_final_url_uses_safe_projection() -> None:
    """Playwright 工具成功 payload 的 final_url 不得暴露 userinfo/query/fragment。"""

    sentinel = "6c" * 32
    payload = web_tools._build_playwright_success_payload(
        "https://example.com/request",
        {
            "final_url": (f"https://{sentinel}:{sentinel}@example.com/report" f"?token={sentinel}#{sentinel}"),
            "title": "Example",
            "content": "safe projected content",
        },
    )

    assert payload["final_url"] == "https://example.com/report"
    assert sentinel not in str(payload["final_url"])


@pytest.mark.parametrize(
    "url",
    (
        "//example.com/report",
        "https:///report",
        "https://@/report",
    ),
)
def test_normalize_url_for_http_rejects_missing_transport_parts(url: str) -> None:
    """HTTP normalizer 必须直接拒绝缺 scheme、netloc 或 hostname 的输入。

    Args:
        url: 缺少一个 transport URL 必填部分的输入。

    Returns:
        无。

    Raises:
        AssertionError: normalizer 未拒绝非法输入时抛出。
    """

    with pytest.raises(ValueError, match="无效 URL"):
        web_tools._normalize_url_for_http(url)


def test_normalize_url_for_http_encodes_idna_and_userinfo_for_transport() -> None:
    """HTTP normalizer 只负责 IDNA 与 userinfo/path/query/fragment 传输 quoting。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: ASCII/IDNA/userinfo quoting 结果不符合 owner 契约时抛出。
    """

    normalized = web_tools._normalize_url_for_http(
        "https://用户名:密 码@例子.测试/财报?q=营业收入#片段"
    )

    assert normalized == (
        "https://%E7%94%A8%E6%88%B7%E5%90%8D:%E5%AF%86%20%E7%A0%81@"
        "xn--fsqu00a.xn--0zwm56d/%E8%B4%A2%E6%8A%A5?"
        "q=%E8%90%A5%E4%B8%9A%E6%94%B6%E5%85%A5#%E7%89%87%E6%AE%B5"
    )


def test_web_egress_policy_owner_rejects_userinfo_url() -> None:
    """WebEgressPolicy 必须作为唯一安全 owner 拒绝 URL userinfo。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: userinfo URL 未在 egress owner 边界被拒绝时抛出。
    """

    with pytest.raises(WebEgressPolicyError) as exc_info:
        _public_test_policy().authorize_http_target(
            "https://user:secret@example.com/report",
            stage="tool_input",
        )

    assert exc_info.value.reason == "userinfo is not allowed"
    assert exc_info.value.stage == "tool_input"


def test_raise_fetch_failure_accepts_only_owner_projection_inputs() -> None:
    """failure owner 不得接受会被静默丢弃的任意 downstream diagnostics。"""

    assert "internal_diagnostics" not in inspect.signature(web_tools._raise_fetch_failure).parameters
    assert (
        inspect.signature(web_tools._raise_fetch_failure).parameters["diagnostic_error_chars"].default
        is inspect.Signature.empty
    )
    with pytest.raises(web_tools.ToolBusinessError) as exc_info:
        web_tools._raise_fetch_failure(
            url="https://user:secret@example.com/report?token=secret#fragment",
            error_code="synthetic_failure",
            message="synthetic failure with a long diagnostic message",
            hint="change source",
            next_action="change_source",
            diagnostic_error_chars=9,
        )

    diagnostics = exc_info.value.internal_diagnostics
    assert diagnostics["safe_url"] == "https://example.com/report"
    assert diagnostics["error_code"] == "synthetic_failure"
    assert len(str(diagnostics["error_message"])) <= 9
    assert "token=" not in json_module.dumps(diagnostics)


def test_project_error_message_marks_small_cap_truncation_without_false_positive() -> None:
    """诊断错误投影在极小 cap 下仍须有界且显式标记真实截断。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: cap、截断标记或未超限文本投影不符合契约时抛出。
    """

    assert web_diagnostics.project_error_message("xx", max_chars=1) == "…"
    assert web_diagnostics.project_error_message("x" * 15, max_chars=14) == ("x" * 13 + "…")
    assert web_diagnostics.project_error_message("x" * 16, max_chars=15) == ("x...<truncated>")
    assert web_diagnostics.project_error_message("short", max_chars=14) == "short"


def test_ordinary_fetch_failure_consumes_config_diagnostic_error_cap() -> None:
    """普通 fetch failure 必须消费本次 config snapshot 的 Diagnostic owner。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: failure cap 未从当前 config snapshot 投影时抛出。
    """

    config = web_provider._parse_config(
        {
            "resource_budget": {
                "diagnostics": {
                    "error_chars": 5,
                }
            }
        }
    )

    with pytest.raises(web_tools.ToolBusinessError) as exc_info:
        web_tools._fetch_web_page_business(
            url="ftp://example.com/a-very-long-report-path",
            config=config,
            timeout_budget=None,
            cancellation_token=cast(CancellationToken, _OpenCancellationToken()),
        )

    assert config.resource_budgets.diagnostics.error_chars == 5
    assert len(exc_info.value.message) <= 5
    assert len(str(exc_info.value.internal_diagnostics["error_message"])) <= 5


def test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP/runtime ordinary failure 分支必须共用本次 config 的 Diagnostic cap。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: 任一 failure 分支绕过当前 Diagnostic owner 时抛出。
    """

    forbidden_response = requests.Response()
    forbidden_response.status_code = 403
    forbidden_response.url = "https://example.com/report"
    forbidden_error = requests.ConnectionError("synthetic forbidden response")
    forbidden_error.response = forbidden_response
    queued_results: list[web_tools._FetchContentResult | BaseException] = [
        requests.TooManyRedirects("synthetic redirect chain exceeded"),
        requests.Timeout("synthetic request timeout"),
        web_http_session.ProxyPeerProofIncompatibleError(),
        requests.ConnectionError("synthetic connection reset"),
        requests.exceptions.SSLError("synthetic TLS handshake failure"),
        RuntimeError("synthetic conversion failure"),
        {
            "content": "",
            "http_status": 200,
            "final_url": "https://example.com/report",
        },
        {
            "content": "asset from challenges.cloudflare.com",
            "http_status": 200,
            "final_url": "https://example.com/report",
            "response_headers": {"content-type": "text/html"},
        },
        {
            "title": "Example",
            "content": "Revenue grew.",
            "http_status": 200,
            "final_url": "https://example.com/report",
            "response_headers": {"content-type": "text/html"},
            "response_content_length": 13,
            "response_content_digest": "sha256:synthetic",
        },
        requests.ConnectionError(requests.Timeout("browser-owned nested timeout")),
        requests.exceptions.SSLError("browser-owned TLS failure"),
        forbidden_error,
    ]
    active_browser_escalation = False

    def fail_fetch(
        url: str,
        *,
        timeout_seconds: float,
        session: requests.Session | None = None,
        headers: Mapping[str, str] | None = None,
        content_type_probe: web_tools.ContentProbePayload | None = None,
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        http_resource_budget: HttpResourceBudget,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> web_tools._FetchContentResult:
        """依序抛出 ordinary fetch 的精确 failure 或返回成功结果。

        Args:
            url: 目标 URL。
            timeout_seconds: 单次超时秒数。
            session: 可选 HTTP Session。
            headers: 可选请求头。
            content_type_probe: 可选 content probe 事实。
            egress_policy: 当前 Web 出站策略。
            transport_policy: 当前 attempt 的 transport policy。
            http_resource_budget: HTTP child 资源预算。
            timeout_budget: 可选总超时预算。
            deadline_monotonic: 可选绝对 deadline。
            cancellation_token: 可选取消令牌。

        Returns:
            队列中的 typed fetch 成功结果。

        Raises:
            BaseException: 队列中的测试异常原样抛出。
        """

        nonlocal active_browser_escalation
        del (
            url,
            timeout_seconds,
            session,
            headers,
            content_type_probe,
            egress_policy,
            transport_policy,
            http_resource_budget,
            timeout_budget,
            deadline_monotonic,
            cancellation_token,
        )
        queued = queued_results.pop(0)
        active_browser_escalation = "browser-owned" in str(queued) or queued is forbidden_error
        if isinstance(queued, BaseException):
            raise queued
        return queued

    def controlled_browser_fallback(
        *,
        url: str,
        timeout_seconds: float,
        headers: dict[str, str],
        timeout_budget: float | None,
        deadline_monotonic: float | None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        browser_enabled: bool,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_tools.WebPayload | None:
        """仅为明确 escalation 场景返回 browser owner 成功投影。

        Args:
            url: 目标 URL。
            timeout_seconds: 单次超时秒数。
            headers: 请求头。
            timeout_budget: 可选总超时预算。
            deadline_monotonic: 可选绝对 deadline。
            playwright_channel: 可选浏览器 channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: 当前 Web 出站策略。
            browser_enabled: 当前配置是否允许 browser fallback。
            transport_policy: 当前 attempt 的 transport policy。
            browser_resource_budget: Browser child 资源预算。
            diagnostic_resource_budget: Diagnostic child 资源预算。
            cancellation_token: 可选取消令牌。

        Returns:
            escalation 激活时返回 browser 成功 payload，否则返回 ``None``。

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
            browser_enabled,
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
            cancellation_token,
        )
        if active_browser_escalation:
            return {
                "url": "https://example.com/report",
                "final_url": "https://example.com/report",
                "title": "Browser",
                "content": "Browser owner content.",
                "fetch_backend": "playwright",
            }
        return None

    monkeypatch.setattr(web_tools, "_warmup_domain", _stable_owner_warmup)
    monkeypatch.setattr(web_tools, "_probe_content_type", _stable_owner_probe)
    monkeypatch.setattr(web_tools, "_fetch_and_convert_content", fail_fetch)
    monkeypatch.setattr(web_tools, "_try_playwright_fallback", controlled_browser_fallback)
    config = web_provider._parse_config({"resource_budget": {"diagnostics": {"error_chars": 5}}})

    observed_codes: list[str] = []
    for _expected_error in range(8):
        with pytest.raises(web_tools.ToolBusinessError) as exc_info:
            web_tools._fetch_web_page_business(
                url="https://example.com/report",
                config=config,
                timeout_budget=None,
                cancellation_token=cast(CancellationToken, _OpenCancellationToken()),
            )
        observed_codes.append(exc_info.value.code)
        assert len(exc_info.value.message) <= 5

    assert observed_codes == [
        "too_many_redirects",
        "request_timeout",
        "proxy_peer_proof_incompatible",
        "http_error",
        "ssl_error",
        "content_conversion_failed",
        "empty_content",
        "blocked",
    ]

    success = web_tools._fetch_web_page_business(
        url="https://example.com/report",
        config=config,
        timeout_budget=None,
        cancellation_token=cast(CancellationToken, _OpenCancellationToken()),
    )
    assert success == {
        "url": "https://example.com/report",
        "final_url": "https://example.com/report",
        "title": "Example",
        "content": "Revenue grew.",
        "fetch_backend": "requests",
        "response_content_length": 13,
        "response_content_digest": "sha256:synthetic",
    }
    for _expected_browser_success in range(3):
        browser_success = web_tools._fetch_web_page_business(
            url="https://example.com/report",
            config=config,
            timeout_budget=None,
            cancellation_token=cast(CancellationToken, _OpenCancellationToken()),
        )
        assert browser_success["fetch_backend"] == "playwright"
    assert queued_results == []


_P = ParamSpec("_P")
_R = TypeVar("_R")
_LIVE_BROWSER_CLEANUP_SMOKE_ENV = "DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE"
_PROCESS_DESCENDANT_WAIT_SECONDS = 3.0
_DEFAULT_HTTP_RESOURCE_BUDGET = DEFAULT_HTTP_RESOURCE_BUDGET
_DEFAULT_BROWSER_RESOURCE_BUDGET = DEFAULT_BROWSER_RESOURCE_BUDGET
_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET = DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET


class _IdentityZstdReader:
    """实现 keyword-compatible bounded reader protocol。"""

    def __init__(self, source: BytesIO) -> None:
        """保存待读取的 encoded stream。

        Args:
            source: 待按上限读取的 encoded stream。

        Returns:
            无。

        Raises:
            无。
        """

        self._source = source

    def read(self, size: int = -1) -> bytes:
        """读取不超过 ``size`` 的字节。

        Args:
            size: 最大读取字节数；负数表示读取剩余内容。

        Returns:
            当前读取位置后的字节。

        Raises:
            ValueError: 底层 stream 已关闭时透出。
        """

        return self._source.read(size)

    def close(self) -> None:
        """关闭底层 encoded stream。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._source.close()


class _IdentityZstdDecompressor:
    """确定性测试用 bounded zstd stream-reader 替身。"""

    def stream_reader(
        self,
        source: BytesIO,
    ) -> web_fetch_orchestrator._BoundedBinaryReader:
        """返回按 ``read(size)`` 消费的输入 byte stream。

        Args:
            source: 待包装的 encoded stream。

        Returns:
            支持有界读取的 identity reader。

        Raises:
            无。
        """

        return _IdentityZstdReader(source)


class _IdentityZstdModule(ModuleType):
    """提供精确 zstd decompressor API 的确定性测试模块。"""

    def __init__(self) -> None:
        """初始化 synthetic module。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__("zstandard")

    def ZstdDecompressor(self) -> _IdentityZstdDecompressor:
        """创建 bounded identity stream-reader。

        Args:
            无。

        Returns:
            新的 identity zstd decompressor。

        Raises:
            无。
        """

        return _IdentityZstdDecompressor()


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


@dataclass(frozen=True, slots=True)
class _SyntheticPlaywrightResponse:
    """typed browser worker success path 使用的响应替身。"""

    status: int
    headers: Mapping[str, str]


class _SyntheticPlaywrightPage(_BudgetProbePage):
    """实现 browser worker 完整成功路径所需的最小 Page。"""

    def __init__(
        self,
        *,
        content_type: str = "text/html; charset=utf-8",
        goto_error: BaseException | None = None,
        return_response: bool = True,
    ) -> None:
        """初始化稳定 HTML、文本、URL 与调用记录。

        Args:
            content_type: 主导航 response 的 Content-Type。
            goto_error: 每次导航需要抛出的可选错误。
            return_response: 导航是否返回 response。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(
            metrics={
                "domChars": 24,
                "textChars": 12,
                "domExceeded": False,
                "textExceeded": False,
            },
            html="<html><body>Revenue grew.</body></html>",
            page_text="Revenue grew.",
        )
        self.url = "about:blank"
        self.goto_calls: list[tuple[str, str, int]] = []
        self.route_patterns: list[str] = []
        self.load_states: list[tuple[str, int]] = []
        self.wait_timeouts: list[int] = []
        self.init_scripts: list[str] = []
        self.content_type = content_type
        self.goto_error = goto_error
        self.return_response = return_response

    def add_init_script(self, script: str) -> None:
        """记录 stealth 初始化脚本。

        Args:
            script: browser 初始化脚本。

        Returns:
            无。

        Raises:
            无。
        """

        self.init_scripts.append(script)

    def goto(
        self,
        url: str,
        *,
        wait_until: str,
        timeout: int,
    ) -> _SyntheticPlaywrightResponse:
        """记录导航并返回 HTML response。

        Args:
            url: 导航 URL。
            wait_until: 导航等待策略。
            timeout: 当前阶段 timeout 毫秒数。

        Returns:
            确定性 HTML response。

        Raises:
            BaseException: 配置了 ``goto_error`` 时原样抛出。
        """

        self.url = url
        self.goto_calls.append((url, wait_until, timeout))
        if self.goto_error is not None:
            raise self.goto_error
        if not self.return_response:
            return cast(_SyntheticPlaywrightResponse, None)
        return _SyntheticPlaywrightResponse(
            status=200,
            headers={"content-type": self.content_type},
        )

    def route(
        self,
        pattern: str,
        handler: Callable[[web_playwright_backend._RouteProtocol], None],
    ) -> None:
        """记录 route 注册。

        Args:
            pattern: route pattern。
            handler: route handler。

        Returns:
            无。

        Raises:
            无。
        """

        del handler
        self.route_patterns.append(pattern)

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        """记录页面稳定化 load state。

        Args:
            state: load state。
            timeout: 等待毫秒数。

        Returns:
            无。

        Raises:
            无。
        """

        self.load_states.append((state, timeout))

    def wait_for_timeout(self, timeout: int) -> None:
        """记录页面稳定化固定等待。

        Args:
            timeout: 等待毫秒数。

        Returns:
            无。

        Raises:
            无。
        """

        self.wait_timeouts.append(timeout)


class _SyntheticPlaywrightContext:
    """记录 browser worker context close 与 page 获取。"""

    def __init__(self, page: _SyntheticPlaywrightPage) -> None:
        """保存唯一 Page。

        Args:
            page: 测试 Page。

        Returns:
            无。

        Raises:
            无。
        """

        self.page = page
        self.close_calls = 0

    def new_page(self) -> _SyntheticPlaywrightPage:
        """返回唯一测试 Page。

        Args:
            无。

        Returns:
            测试 Page。

        Raises:
            无。
        """

        return self.page

    def close(self) -> None:
        """记录 context close。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_calls += 1


class _SyntheticPlaywrightBrowser:
    """记录 browser worker 创建 context 时的 typed kwargs。"""

    def __init__(self, context: _SyntheticPlaywrightContext) -> None:
        """保存唯一 Context。

        Args:
            context: 测试 Context。

        Returns:
            无。

        Raises:
            无。
        """

        self.context = context
        self.context_kwargs: Mapping[str, JsonValue] | None = None

    def new_context(
        self,
        *,
        viewport: Mapping[str, int],
        user_agent: str,
        locale: str,
        accept_downloads: bool,
        ignore_https_errors: bool,
        extra_http_headers: Mapping[str, str],
        storage_state: str | None = None,
    ) -> _SyntheticPlaywrightContext:
        """记录 worker 的精确 context 输入并返回测试 Context。

        Args:
            viewport: browser viewport。
            user_agent: browser User-Agent。
            locale: browser locale。
            accept_downloads: 是否允许下载。
            ignore_https_errors: 是否忽略 HTTPS 错误。
            extra_http_headers: browser 额外请求头。
            storage_state: 可选只读 storage state 路径。

        Returns:
            测试 Context。

        Raises:
            无。
        """

        context_kwargs: dict[str, JsonValue] = {
            "viewport": cast(JsonValue, dict(viewport)),
            "user_agent": user_agent,
            "locale": locale,
            "accept_downloads": accept_downloads,
            "ignore_https_errors": ignore_https_errors,
            "extra_http_headers": cast(JsonValue, dict(extra_http_headers)),
        }
        if storage_state is not None:
            context_kwargs["storage_state"] = storage_state
        self.context_kwargs = context_kwargs
        return self.context

    def close(self) -> None:
        """关闭测试 Browser。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        return


class _LifecyclePlaywrightBrowser:
    """记录 browser singleton 生命周期动作并可注入关闭异常。"""

    def __init__(self, *, close_error: RuntimeError | None = None) -> None:
        """初始化 browser 生命周期替身。

        Args:
            close_error: ``close`` 调用后需要抛出的可选异常。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_error = close_error
        self.close_calls = 0

    def new_context(
        self,
        **kwargs: JsonValue,
    ) -> web_playwright_backend._BrowserContextProtocol:
        """拒绝生命周期测试范围外的 browser context 创建。

        Args:
            kwargs: Playwright browser context 参数。

        Returns:
            不返回。

        Raises:
            AssertionError: 生命周期 owner 测试意外创建 context 时抛出。
        """

        del kwargs
        raise AssertionError("lifecycle fake browser must not create a context")

    def close(self) -> None:
        """记录 browser close，并按配置抛出异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: 配置了关闭异常时抛出。
        """

        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class _LifecycleChromiumLauncher:
    """记录 Chromium launch 输入并返回指定 lifecycle browser。"""

    def __init__(
        self,
        browser: _LifecyclePlaywrightBrowser,
        *,
        launch_error: RuntimeError | None = None,
    ) -> None:
        """初始化 Chromium launcher 替身。

        Args:
            browser: launch 成功时返回的 browser。
            launch_error: launch 时需要抛出的可选异常。

        Returns:
            无。

        Raises:
            无。
        """

        self.browser = browser
        self.launch_error = launch_error
        self.launch_calls: list[dict[str, JsonValue]] = []

    def launch(
        self,
        **kwargs: JsonValue,
    ) -> web_playwright_backend._BrowserProtocol:
        """记录 launch 参数并返回或拒绝 browser 创建。

        Args:
            kwargs: Chromium launch 参数。

        Returns:
            配置的 browser。

        Raises:
            RuntimeError: 配置了 launch 异常时抛出。
        """

        self.launch_calls.append(dict(kwargs))
        if self.launch_error is not None:
            raise self.launch_error
        return cast(web_playwright_backend._BrowserProtocol, self.browser)


class _LifecyclePlaywrightInstance:
    """提供 typed Chromium launcher 并记录 runtime stop。"""

    def __init__(
        self,
        chromium: _LifecycleChromiumLauncher,
        *,
        stop_error: RuntimeError | None = None,
    ) -> None:
        """初始化 Playwright runtime 替身。

        Args:
            chromium: 当前 runtime 的 Chromium launcher。
            stop_error: ``stop`` 调用后需要抛出的可选异常。

        Returns:
            无。

        Raises:
            无。
        """

        self.chromium = chromium
        self.stop_error = stop_error
        self.stop_calls = 0

    def stop(self) -> None:
        """记录 runtime stop，并按配置抛出异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: 配置了停止异常时抛出。
        """

        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error


class _LifecyclePlaywrightStarter:
    """模拟 ``sync_playwright()`` 返回值的 start 边界。"""

    def __init__(self, instance: _LifecyclePlaywrightInstance) -> None:
        """保存一次 start 应返回的 runtime。

        Args:
            instance: start 后返回的 Playwright runtime。

        Returns:
            无。

        Raises:
            无。
        """

        self.instance = instance
        self.start_calls = 0

    def start(self) -> _LifecyclePlaywrightInstance:
        """记录 start 并返回配置的 runtime。

        Args:
            无。

        Returns:
            配置的 Playwright runtime。

        Raises:
            无。
        """

        self.start_calls += 1
        return self.instance


class _LifecycleSyncPlaywrightFactory:
    """按调用顺序提供 typed Playwright starter。"""

    def __init__(self, instances: tuple[_LifecyclePlaywrightInstance, ...]) -> None:
        """初始化有界 runtime 序列。

        Args:
            instances: 每次 ``sync_playwright`` 调用应启动的 runtime。

        Returns:
            无。

        Raises:
            ValueError: 没有提供 runtime 时抛出。
        """

        if not instances:
            raise ValueError("at least one lifecycle Playwright instance is required")
        self.instances = instances
        self.starters: list[_LifecyclePlaywrightStarter] = []

    def __call__(self) -> _LifecyclePlaywrightStarter:
        """返回下一项 starter，不允许测试静默超用 runtime。

        Args:
            无。

        Returns:
            下一项 typed Playwright starter。

        Raises:
            AssertionError: 调用次数超过配置 runtime 数量时抛出。
        """

        if len(self.starters) >= len(self.instances):
            raise AssertionError("unexpected extra sync_playwright call")
        starter = _LifecyclePlaywrightStarter(self.instances[len(self.starters)])
        self.starters.append(starter)
        return starter


@dataclass(frozen=True, slots=True)
class _RecordingRouteRequest:
    """提供 route owner 所需的资源类型和 URL 输入。"""

    resource_type: str
    url: str


class _RecordingPlaywrightRoute:
    """只记录 browser route owner 选择的 abort/continue 动作。"""

    def __init__(self, *, resource_type: str, url: str) -> None:
        """初始化 route action recorder。

        Args:
            resource_type: Playwright request 资源类型。
            url: Playwright request URL。

        Returns:
            无。

        Raises:
            无。
        """

        self.request = cast(
            web_playwright_backend._RouteRequestProtocol,
            _RecordingRouteRequest(resource_type=resource_type, url=url),
        )
        self.actions: list[str] = []

    def abort(self) -> None:
        """记录 route owner 选择了 abort。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.actions.append(_ROUTE_ABORT_ACTION)

    def continue_(self) -> None:
        """记录 route owner 选择了 continue。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.actions.append(_ROUTE_CONTINUE_ACTION)


@dataclass(frozen=True, slots=True)
class _SyntheticHtmlPipelineResult:
    """browser worker HTML converter 的最小成功结果。"""

    title: str = "Example"
    markdown: str = "Revenue grew."
    extractor_source: str = "synthetic"
    renderer_source: str = "synthetic"
    normalization_applied: bool = False
    quality_flags: tuple[str, ...] = ()
    content_stats: Mapping[str, JsonValue] = field(default_factory=dict)


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
        :raises Exception: 不主动抛出异常。
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


def _http_resource_budget(
    *,
    wire_body_bytes: int = 1024,
    decoded_body_bytes: int = 2048,
) -> HttpResourceBudget:
    """构造测试用 HTTP 资源预算。

    Args:
        wire_body_bytes: wire body 上限。
        decoded_body_bytes: decoded body 上限。
    Returns:
        HTTP 资源预算。

    Raises:
        ValueError: 参数不是正整数时由 owner 抛出。
    """

    return HttpResourceBudget(
        wire_body_bytes=wire_body_bytes,
        decoded_body_bytes=decoded_body_bytes,
    )


def _browser_resource_budget(
    *,
    warmup_body_bytes: int = 64,
    dom_chars: int = 2048,
    text_chars: int = 1024,
) -> BrowserResourceBudget:
    """构造测试用浏览器资源预算。

    Args:
        warmup_body_bytes: warmup body 上限。
        dom_chars: browser DOM 字符上限。
        text_chars: browser text 字符上限。

    Returns:
        浏览器资源预算。

    Raises:
        ValueError: 参数不是正整数时由 owner 抛出。
    """

    return BrowserResourceBudget(
        warmup_body_bytes=warmup_body_bytes,
        dom_chars=dom_chars,
        text_chars=text_chars,
    )


def _diagnostic_resource_budget(
    *,
    error_chars: int = 128,
    events: int = 8,
) -> DiagnosticResourceBudget:
    """构造测试用诊断资源预算。

    Args:
        error_chars: 诊断错误字符上限。
        events: 诊断事件数量上限。

    Returns:
        诊断资源预算。

    Raises:
        ValueError: 参数不是正整数时由 owner 抛出。
    """

    return DiagnosticResourceBudget(error_chars=error_chars, events=events)


def _playwright_worker_process_kwargs() -> web_playwright_backend._WorkerKwargs:
    """构造 process owner 测试共用的 typed worker kwargs。

    Args:
        无。

    Returns:
        不依赖真实浏览器、网络或子进程的 worker 参数。

    Raises:
        无。
    """

    return {
        "url": "https://example.com/report",
        "timeout_seconds": 1.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": "",
        "egress_policy": _public_test_policy(),
        "browser_resource_budget": _DEFAULT_BROWSER_RESOURCE_BUDGET,
    }


def _resource_budgets(
    *,
    wire_body_bytes: int = 1024,
    decoded_body_bytes: int = 2048,
    warmup_body_bytes: int = 64,
    dom_chars: int = 2048,
    text_chars: int = 1024,
    error_chars: int = 128,
    events: int = 8,
) -> WebResourceBudgets:
    """构造测试用 owner 预算纯组合。

    Args:
        wire_body_bytes: HTTP wire body 上限。
        decoded_body_bytes: HTTP decoded body 上限。
        warmup_body_bytes: warmup body 上限。
        dom_chars: browser DOM 字符上限。
        text_chars: browser text 字符上限。
        error_chars: 诊断错误字符上限。
        events: 诊断事件数量上限。

    Returns:
        无 default 的 owner 预算组合。

    Raises:
        ValueError: child 参数不是正整数时由 owner 抛出。
    """

    return WebResourceBudgets(
        http=_http_resource_budget(
            wire_body_bytes=wire_body_bytes,
            decoded_body_bytes=decoded_body_bytes,
        ),
        browser=_browser_resource_budget(
            warmup_body_bytes=warmup_body_bytes,
            dom_chars=dom_chars,
            text_chars=text_chars,
        ),
        diagnostics=_diagnostic_resource_budget(
            error_chars=error_chars,
            events=events,
        ),
    )


def _resource_budget_json(
    *,
    wire_body_bytes: int = 1024,
    decoded_body_bytes: int = 2048,
    warmup_body_bytes: int = 64,
    dom_chars: int = 2048,
    text_chars: int = 1024,
    error_chars: int = 128,
    events: int = 8,
) -> dict[str, JsonValue]:
    """构造 provider config 使用的完整 resource_budget object。

    Args:
        wire_body_bytes: wire body 上限。
        decoded_body_bytes: decoded body 上限。
        warmup_body_bytes: warmup body 上限。
        dom_chars: browser DOM 字符上限。
        text_chars: browser text 字符上限。
        error_chars: 诊断错误字符上限。
        events: 诊断事件数量上限。

    Returns:
        完整 JSON object。

    Raises:
        无。
    """

    return {
        "http": {
            "wire_body_bytes": wire_body_bytes,
            "decoded_body_bytes": decoded_body_bytes,
        },
        "browser": {
            "warmup_body_bytes": warmup_body_bytes,
            "dom_chars": dom_chars,
            "text_chars": text_chars,
        },
        "diagnostics": {
            "error_chars": error_chars,
            "events": events,
        },
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
    transport_policy: web_http_session.WebHttpTransportPolicy,
) -> web_http_session.AuthorizedResponseLease:
    """让编排测试替身显式消费 AuthorizedHttpTarget。

    Args:
        source_session: 按顺序返回 response 的测试 Session。
        target: 当前 hop 的授权目标。
        method: HTTP 方法。
        timeout: 请求超时。
        headers: 请求头。
        stream: 是否流式读取。
        transport_policy: 当前 attempt 的 transport policy。

    Returns:
        response lease。

    Raises:
        AssertionError: Session 不是预期替身时抛出。
    """

    assert isinstance(source_session, _QueuedSession)
    assert isinstance(transport_policy, web_http_session.WebHttpTransportPolicy)
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


def _plain_response_lease(
    response: requests.Response,
) -> web_http_session.AuthorizedResponseLease:
    """为 search provider 测试 response 构造独占关闭 lease。

    Args:
        response: 待交给 provider 消费的确定性 response。

    Returns:
        持有 response 与私有 Session 的 lease。

    Raises:
        无。
    """

    return web_http_session.AuthorizedResponseLease(
        response=response,
        session=requests.Session(),
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


class _FakePlaywrightResultQueue:
    """模拟 multiprocessing Queue，并记录 finally cleanup 动作。"""

    def __init__(
        self,
        payloads: tuple[web_playwright_backend.WebPayload, ...] = (),
    ) -> None:
        """初始化结果队列替身。

        Args:
            payloads: 按读取顺序返回的 worker payload。

        Returns:
            无。

        Raises:
            无。
        """

        self.payloads = list(payloads)
        self.put_calls: list[web_playwright_backend.WebPayload] = []
        self.get_calls: list[float | None] = []
        self.close_calls = 0
        self.join_thread_calls = 0

    def put(
        self,
        obj: web_playwright_backend.WebPayload,
        block: bool = True,
        timeout: float | None = None,
    ) -> None:
        """记录 worker 写入，不执行跨进程通信。

        Args:
            obj: worker 结果 payload。
            block: 是否阻塞写入。
            timeout: 写入 timeout。

        Returns:
            无。

        Raises:
            无。
        """

        del block, timeout
        self.put_calls.append(obj)

    def get(
        self,
        block: bool = True,
        timeout: float | None = None,
    ) -> web_playwright_backend.WebPayload:
        """返回下一项 payload，空队列时立即报告 ``Empty``。

        Args:
            block: 是否阻塞读取。
            timeout: 读取 timeout；仅记录，不等待。

        Returns:
            下一项 worker payload。

        Raises:
            Empty: 没有预置 payload 时抛出。
        """

        del block
        self.get_calls.append(timeout)
        if not self.payloads:
            raise Empty
        return self.payloads.pop(0)

    def get_nowait(self) -> web_playwright_backend.WebPayload:
        """非阻塞返回下一项 payload。

        Args:
            无。

        Returns:
            下一项 worker payload。

        Raises:
            Empty: 没有预置 payload 时抛出。
        """

        return self.get(block=False, timeout=0.0)

    def close(self) -> None:
        """记录父进程关闭 queue 句柄。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_calls += 1

    def join_thread(self) -> None:
        """记录父进程等待 queue feeder thread。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.join_thread_calls += 1


class _FakePlaywrightProcess:
    """模拟 multiprocessing Process 的启动、存活与 join 状态。"""

    def __init__(self, *, alive_after_start: bool) -> None:
        """初始化进程替身。

        Args:
            alive_after_start: ``start`` 后 ``is_alive`` 的初始结果。

        Returns:
            无。

        Raises:
            无。
        """

        self.alive_after_start = alive_after_start
        self.alive = False
        self.started = False
        self.daemon = False
        self.join_timeouts: list[float | None] = []

    def start(self) -> None:
        """记录进程启动但不创建真实子进程。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.started = True
        self.alive = self.alive_after_start

    def is_alive(self) -> bool:
        """返回当前 fake process 存活状态。

        Args:
            无。

        Returns:
            当前存活状态。

        Raises:
            无。
        """

        return self.alive

    def join(self, timeout: float | None = None) -> None:
        """记录非阻塞 join 调用。

        Args:
            timeout: join timeout。

        Returns:
            无。

        Raises:
            无。
        """

        self.join_timeouts.append(timeout)

    def mark_terminated(self) -> None:
        """让 termination collaborator 标记 fake process 已退出。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.alive = False


class _FakePlaywrightMultiprocessingContext:
    """向 process owner 提供固定 queue/process 的 typed context。"""

    def __init__(
        self,
        *,
        result_queue: _FakePlaywrightResultQueue,
        process: _FakePlaywrightProcess,
    ) -> None:
        """初始化 multiprocessing context 替身。

        Args:
            result_queue: 本次 owner 调用应取得的 queue。
            process: 本次 owner 调用应取得的 process。

        Returns:
            无。

        Raises:
            无。
        """

        self.result_queue = result_queue
        self.process = process
        self.queue_maxsizes: list[int] = []
        self.process_target: Callable[
            [
                web_playwright_backend._ResultQueueProtocol,
                web_playwright_backend._PlaywrightWorkerProtocol,
                web_playwright_backend._WorkerKwargs,
                DiagnosticResourceBudget,
                bool,
            ],
            None,
        ] | None = None
        self.process_args: tuple[
            web_playwright_backend._ResultQueueProtocol,
            web_playwright_backend._PlaywrightWorkerProtocol,
            web_playwright_backend._WorkerKwargs,
            DiagnosticResourceBudget,
            bool,
        ] | None = None

    def Queue(
        self,
        *,
        maxsize: int,
    ) -> web_playwright_backend._ResultQueueProtocol:
        """记录 queue 上限并返回固定 fake queue。

        Args:
            maxsize: owner 请求的结果队列容量。

        Returns:
            固定 fake result queue。

        Raises:
            无。
        """

        self.queue_maxsizes.append(maxsize)
        return cast(web_playwright_backend._ResultQueueProtocol, self.result_queue)

    def Process(
        self,
        *,
        target: Callable[
            [
                web_playwright_backend._ResultQueueProtocol,
                web_playwright_backend._PlaywrightWorkerProtocol,
                web_playwright_backend._WorkerKwargs,
                DiagnosticResourceBudget,
                bool,
            ],
            None,
        ],
        args: tuple[
            web_playwright_backend._ResultQueueProtocol,
            web_playwright_backend._PlaywrightWorkerProtocol,
            web_playwright_backend._WorkerKwargs,
            DiagnosticResourceBudget,
            bool,
        ],
    ) -> BaseProcess:
        """记录 process target/args并返回固定 fake process。

        Args:
            target: production worker process entrypoint。
            args: production worker process typed 参数。

        Returns:
            作为 ``BaseProcess`` 消费的固定 fake process。

        Raises:
            无。
        """

        self.process_target = target
        self.process_args = args
        return cast(BaseProcess, self.process)


class _FakePlaywrightContextFactory:
    """记录 ``multiprocessing.get_context`` 的 spawn 请求。"""

    def __init__(self, context: _FakePlaywrightMultiprocessingContext) -> None:
        """保存固定 multiprocessing context。

        Args:
            context: production owner 应取得的 fake context。

        Returns:
            无。

        Raises:
            无。
        """

        self.context = context
        self.methods: list[str | None] = []

    def __call__(self, method: str | None = None) -> _FakePlaywrightMultiprocessingContext:
        """记录 context method 并返回固定 context。

        Args:
            method: multiprocessing start method。

        Returns:
            固定 fake context。

        Raises:
            AssertionError: owner 未请求 ``spawn`` 时抛出。
        """

        self.methods.append(method)
        assert method == "spawn"
        return self.context


class _RecordingPlaywrightProcessTerminator:
    """只记录 process owner 发出的 terminate 动作。"""

    def __init__(self) -> None:
        """初始化 termination 记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.processes: list[_FakePlaywrightProcess] = []

    def __call__(
        self,
        process: BaseProcess,
    ) -> web_playwright_backend._PlaywrightProcessCleanup:
        """记录 fake process 终止并返回空 cleanup 诊断。

        Args:
            process: production owner 要求终止的 process。

        Returns:
            terminate/kill 均未执行真实信号的 cleanup 诊断。

        Raises:
            AssertionError: 收到非 fake process 时抛出。
        """

        assert isinstance(process, _FakePlaywrightProcess)
        self.processes.append(process)
        process.mark_terminated()
        return {"terminate": None, "kill": None}


class _ScriptedMonotonicClock:
    """按序返回单调时钟值，避免 timeout 测试等待真实时间。"""

    def __init__(self, values: tuple[float, ...]) -> None:
        """初始化时钟序列。

        Args:
            values: 每次调用依次返回的单调时间值。

        Returns:
            无。

        Raises:
            ValueError: 时钟序列为空时抛出。
        """

        if not values:
            raise ValueError("scripted monotonic clock requires values")
        self.values = values
        self.index = 0

    def __call__(self) -> float:
        """返回下一项时钟值，耗尽后保持最后值。

        Args:
            无。

        Returns:
            当前 scripted 单调时间值。

        Raises:
            无。
        """

        if self.index >= len(self.values):
            return self.values[-1]
        value = self.values[self.index]
        self.index += 1
        return value


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
        browser_resource_budget: BrowserResourceBudget,
    ) -> web_playwright_backend.WebPayload:
        """启动长生命周期 nested child 后保持 worker 存活。

        :param url: 测试 URL。
        :param timeout_seconds: worker 总预算。
        :param headers: 可选请求头。
        :param playwright_channel: 可选浏览器 channel。
        :param playwright_storage_state_path: 用作 nested child PID 文件路径。
        :param egress_policy: 当前 Web 出站策略。
        :param browser_resource_budget: Browser child 资源预算。
        :returns: 理论成功载荷；测试会在返回前中断 worker。
        :raises RuntimeError: PID 文件路径为空时抛出。
        """

        del (
            url,
            timeout_seconds,
            headers,
            playwright_channel,
            egress_policy,
            browser_resource_budget,
        )
        if not playwright_storage_state_path:
            raise RuntimeError("synthetic nested child pid path is required")
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time\n" "time.sleep(60)\n",
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
        browser_resource_budget: BrowserResourceBudget,
    ) -> web_playwright_backend.WebPayload:
        """启动真实浏览器并保持 worker 存活。

        :param url: 本地 fixture URL。
        :param timeout_seconds: worker 总预算。
        :param headers: 可选请求头。
        :param playwright_channel: 可选浏览器 channel。
        :param playwright_storage_state_path: 用作 ready marker 文件路径。
        :param egress_policy: 当前 Web 出站策略。
        :param browser_resource_budget: Browser child 资源预算。
        :returns: 理论成功载荷；测试会在返回前中断 worker。
        :raises RuntimeError: ready marker 路径为空时抛出。
        """

        del (
            timeout_seconds,
            headers,
            playwright_channel,
            egress_policy,
            browser_resource_budget,
        )
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
        browser_resource_budget: BrowserResourceBudget,
    ) -> web_playwright_backend.WebPayload:
        """抛出 Web fetch owner 的 URL safety 异常。

        :param url: 测试 URL。
        :param timeout_seconds: worker 总预算。
        :param headers: 可选请求头。
        :param playwright_channel: 可选浏览器 channel。
        :param playwright_storage_state_path: storage state 路径。
        :param egress_policy: Web 出站策略。
        :param browser_resource_budget: Browser child 资源预算。
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
            browser_resource_budget,
        )
        raise web_fetch_orchestrator._FetchUrlSafetyError(
            url=self.blocked_url,
            reason=self.blocked_stage,
        )


@dataclass(frozen=True, slots=True)
class _SyntheticProcessPlaywrightWorker:
    """测试 process wrapper 成功与普通失败的可 pickle worker。"""

    failure_message: str | None = None

    def __call__(
        self,
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        browser_resource_budget: BrowserResourceBudget,
    ) -> web_playwright_backend.WebPayload:
        """返回成功 payload 或抛出配置的普通失败。

        Args:
            url: 测试 URL。
            timeout_seconds: worker 总预算。
            headers: 可选请求头。
            playwright_channel: 可选浏览器 channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: Web 出站策略。
            browser_resource_budget: Browser child 资源预算。

        Returns:
            未配置失败时返回确定性成功 payload。

        Raises:
            RuntimeError: 配置了 ``failure_message`` 时抛出。
        """

        del (
            url,
            timeout_seconds,
            headers,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            browser_resource_budget,
        )
        if self.failure_message is not None:
            raise RuntimeError(self.failure_message)
        return {"ok": True, "content": "process success"}


def _stable_owner_warmup(
    session: requests.Session,
    *,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str],
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    egress_policy: WebEgressPolicy,
    transport_policy: web_http_session.WebHttpTransportPolicy,
    browser_resource_budget: BrowserResourceBudget,
    cancellation_token: CancellationToken | None = None,
) -> web_tools.StagePayload:
    """返回不升级 browser 的精确 warmup facts。

    Args:
        session: 当前 HTTP Session。
        url: 目标 URL。
        timeout_seconds: 单次超时秒数。
        headers: 请求头。
        timeout_budget: 可选总超时预算。
        deadline_monotonic: 可选绝对 deadline。
        egress_policy: 当前 Web 出站策略。
        transport_policy: 当前 attempt 的 transport policy。
        browser_resource_budget: Browser child 资源预算。
        cancellation_token: 可选取消令牌。

    Returns:
        表示 warmup 已成功的稳定阶段事实。

    Raises:
        无。
    """

    del (
        session,
        url,
        timeout_seconds,
        headers,
        timeout_budget,
        deadline_monotonic,
        egress_policy,
        transport_policy,
        browser_resource_budget,
        cancellation_token,
    )
    return {"attempted": True, "ok": True}


def _stable_owner_probe(
    session: requests.Session,
    *,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str],
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    egress_policy: WebEgressPolicy,
    transport_policy: web_http_session.WebHttpTransportPolicy,
    cancellation_token: CancellationToken | None = None,
) -> web_tools.ContentProbePayload:
    """返回不升级 browser 的精确 probe facts。

    Args:
        session: 当前 HTTP Session。
        url: 目标 URL。
        timeout_seconds: 单次超时秒数。
        headers: 请求头。
        timeout_budget: 可选总超时预算。
        deadline_monotonic: 可选绝对 deadline。
        egress_policy: 当前 Web 出站策略。
        transport_policy: 当前 attempt 的 transport policy。
        cancellation_token: 可选取消令牌。

    Returns:
        表示 probe 已成功的稳定阶段事实。

    Raises:
        无。
    """

    del (
        session,
        url,
        timeout_seconds,
        headers,
        timeout_budget,
        deadline_monotonic,
        egress_policy,
        transport_policy,
        cancellation_token,
    )
    return {"attempted": True, "ok": True}


def _resolve_private_test_address(hostname: str, port: int) -> tuple[str, ...]:
    """把 custom-port 测试 hostname 固定解析到本地地址。

    Args:
        hostname: 待解析 hostname。
        port: 目标端口。

    Returns:
        单一本地测试地址。

    Raises:
        无。
    """

    del hostname, port
    return ("127.0.0.1",)


def _convert_expected_fetch_html(
    html: str,
    *,
    url: str = "",
) -> web_fetch_orchestrator.HtmlPipelineResult:
    """校验 HTTP owner HTML input 并返回确定性 pipeline result。

    Args:
        html: 已有界物化的 HTML。
        url: final URL。

    Returns:
        确定性 HTML pipeline result。

    Raises:
        AssertionError: HTML 或 URL 偏离测试契约时抛出。
    """

    assert html == "<html><body>Revenue grew.</body></html>"
    assert url == "https://example.com/report"
    return web_fetch_orchestrator.HtmlPipelineResult(
        title="Example",
        html=html,
        markdown="Revenue grew.",
        extractor_source="synthetic",
        renderer_source="synthetic",
        quality_flags=(),
        content_stats={"text_length": 13},
        normalization_applied=False,
    )


def _reject_non_html_conversion(
    raw_bytes: bytes,
    stream_name: str,
) -> tuple[str, str, str]:
    """拒绝 HTML case 意外进入 non-HTML converter。

    Args:
        raw_bytes: 意外传入的原始字节。
        stream_name: 意外传入的流名称。

    Returns:
        不返回。

    Raises:
        AssertionError: 始终抛出，表示调用路径错误。
    """

    del raw_bytes, stream_name
    raise AssertionError("non-HTML conversion must not run")


def _reject_fetch_html_conversion(
    html: str,
    *,
    url: str = "",
) -> web_fetch_orchestrator.HtmlPipelineResult:
    """拒绝 PDF case 意外进入 HTTP HTML converter。

    Args:
        html: 意外传入的 HTML。
        url: 意外传入的 URL。

    Returns:
        不返回。

    Raises:
        AssertionError: 始终抛出，表示调用路径错误。
    """

    del html, url
    raise AssertionError("HTML conversion must not run")


def _convert_expected_pdf(raw_bytes: bytes, stream_name: str) -> tuple[str, str, str]:
    """返回确定性 non-HTML owner conversion 结果。

    Args:
        raw_bytes: 已有界物化的 PDF 字节。
        stream_name: 推断出的流名称。

    Returns:
        固定标题、长度文本与 renderer 来源。

    Raises:
        无。
    """

    return ("PDF", f"{stream_name}:{len(raw_bytes)}", "docling")


def _raise_missing_optional_zstd(module_name: str) -> ModuleType:
    """模拟缺少可执行有界解码的 optional zstd codec。

    Args:
        module_name: 待导入的 optional module 名称。

    Returns:
        不返回。

    Raises:
        ImportError: module 名称正确时始终抛出。
        AssertionError: module 名称偏离测试契约时抛出。
    """

    assert module_name == "zstandard"
    raise ImportError(module_name)


def _import_identity_zstd(module_name: str) -> ModuleType:
    """返回不依赖环境 optional package 的精确 zstd module。

    Args:
        module_name: 待导入的 optional module 名称。

    Returns:
        具有有界 stream-reader API 的 synthetic module。

    Raises:
        AssertionError: module 名称偏离测试契约时抛出。
    """

    assert module_name == "zstandard"
    return _IdentityZstdModule()


def _convert_expected_browser_html(
    html: str,
    *,
    url: str = "",
) -> _SyntheticHtmlPipelineResult:
    """校验完整 browser HTML/final URL 并返回确定性 conversion result。

    Args:
        html: browser 完整 HTML。
        url: browser final URL。

    Returns:
        synthetic HTML conversion result。

    Raises:
        AssertionError: HTML 或 URL 漂移时抛出。
    """

    assert html == "<html><body>Revenue grew.</body></html>"
    assert url == "http://127.0.0.1:43119/report"
    return _SyntheticHtmlPipelineResult()


def _reject_browser_html_conversion(
    html: str,
    *,
    url: str = "",
) -> _SyntheticHtmlPipelineResult:
    """拒绝 non-HTML 或 DOM failure 意外进入 browser HTML converter。

    Args:
        html: 意外传入的 HTML。
        url: 意外传入的 URL。

    Returns:
        不返回。

    Raises:
        AssertionError: 始终抛出，表示调用路径错误。
    """

    del html, url
    raise AssertionError("HTML conversion must not run")


def _convert_oversized_browser_markdown(
    html: str,
    *,
    url: str = "",
) -> _SyntheticHtmlPipelineResult:
    """返回超过 Browser text cap 的 typed Markdown。

    Args:
        html: 已通过 DOM cap 的 HTML。
        url: browser final URL。

    Returns:
        Markdown 长度固定为 17 的 synthetic conversion result。

    Raises:
        无。
    """

    del html, url
    return _SyntheticHtmlPipelineResult(markdown="x" * 17)


def _run_synthetic_playwright_worker(
    page: _SyntheticPlaywrightPage,
    *,
    browser_resource_budget: BrowserResourceBudget,
    convert_html: web_playwright_backend._HtmlConverterProtocol,
) -> web_playwright_backend.WebPayload:
    """用精确 Browser owner 和 converter 执行一个 synthetic worker。

    Args:
        page: 当前 case 的 synthetic Page。
        browser_resource_budget: Browser child 资源预算。
        convert_html: 当前 case 的 HTML converter。

    Returns:
        browser worker 的 typed payload。

    Raises:
        RuntimeError: browser worker 的确定性失败原样透出。
    """

    context = _SyntheticPlaywrightContext(page)
    browser = _SyntheticPlaywrightBrowser(context)

    def get_browser(
        *,
        playwright_channel: str | None = None,
        headless: bool = True,
    ) -> web_playwright_backend._BrowserProtocol | None:
        """返回当前 case 的 synthetic Browser。

        Args:
            playwright_channel: 可选浏览器 channel。
            headless: 是否使用无头模式。

        Returns:
            当前 case 唯一的 synthetic Browser。

        Raises:
            无。
        """

        del playwright_channel, headless
        return cast(web_playwright_backend._BrowserProtocol, browser)

    return web_playwright_backend._playwright_sync_worker(
        url="http://127.0.0.1:43119/report",
        timeout_seconds=5.0,
        get_playwright_browser=get_browser,
        build_domain_home_url=web_tools._build_domain_home_url,
        normalize_url_for_http=web_tools._normalize_url_for_http,
        sanitize_response_headers=web_tools._sanitize_plain_response_headers,
        convert_html_to_markdown=convert_html,
        egress_policy=WebEgressPolicy(
            allow_private_network=True,
            allow_custom_port=True,
        ),
        browser_resource_budget=browser_resource_budget,
    )


def _unavailable_browser(
    *,
    playwright_channel: str | None = None,
    headless: bool = True,
) -> web_playwright_backend._BrowserProtocol | None:
    """返回明确不可用的 Browser owner 结果。

    Args:
        playwright_channel: 可选浏览器 channel。
        headless: 是否使用无头模式。

    Returns:
        始终返回 ``None``。

    Raises:
        无。
    """

    del playwright_channel, headless
    return None


def _accept_picklable_playwright_worker(
    worker: web_playwright_backend._PlaywrightWorkerProtocol,
) -> bool:
    """声明精确 Playwright worker 可进入 synthetic process wrapper。

    Args:
        worker: 待检查的 typed Playwright worker。

    Returns:
        始终返回 ``True``。

    Raises:
        无。
    """

    del worker
    return True


def _exhaust_browser_timeout(
    timeout_seconds: float,
    *,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    reserve_seconds: float = 0.0,
) -> float:
    """模拟 browser 启动前 timeout budget 已耗尽。

    Args:
        timeout_seconds: 原始单次 timeout。
        timeout_budget: 可选总 timeout 预算。
        deadline_monotonic: 可选绝对 deadline。
        reserve_seconds: 预留秒数。

    Returns:
        不返回。

    Raises:
        requests.Timeout: 始终抛出。
    """

    del timeout_seconds, timeout_budget, deadline_monotonic, reserve_seconds
    raise requests.Timeout("synthetic browser budget exhausted")


def _process_entry_success_worker(
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    egress_policy: WebEgressPolicy,
    browser_resource_budget: BrowserResourceBudget,
) -> web_playwright_backend.WebPayload:
    """返回确定性 process-entry worker success。

    Args:
        url: 目标 URL。
        timeout_seconds: browser timeout。
        headers: 请求头。
        playwright_channel: browser channel。
        playwright_storage_state_path: storage state 路径。
        egress_policy: 出站策略。
        browser_resource_budget: browser budget。

    Returns:
        确定性成功 payload。

    Raises:
        无。
    """

    del (
        url,
        timeout_seconds,
        headers,
        playwright_channel,
        playwright_storage_state_path,
        egress_policy,
        browser_resource_budget,
    )
    return {"ok": True, "content": "success"}


def _process_entry_proxy_environment_worker(
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    egress_policy: WebEgressPolicy,
    browser_resource_budget: BrowserResourceBudget,
) -> web_playwright_backend.WebPayload:
    """返回 worker 入口可见的标准 proxy 环境变量名。

    Args:
        url: 目标 URL。
        timeout_seconds: browser timeout。
        headers: 请求头。
        playwright_channel: browser channel。
        playwright_storage_state_path: storage state 路径。
        egress_policy: 出站策略。
        browser_resource_budget: browser budget。

    Returns:
        只含环境变量名、不含 proxy 值的确定性 payload。

    Raises:
        无。
    """

    del (
        url,
        timeout_seconds,
        headers,
        playwright_channel,
        playwright_storage_state_path,
        egress_policy,
        browser_resource_budget,
    )
    proxy_names = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    )
    return {
        "ok": True,
        "visible_proxy_environment": [name for name in proxy_names if name in os.environ],
    }


def _process_entry_blocked_worker(
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    egress_policy: WebEgressPolicy,
    browser_resource_budget: BrowserResourceBudget,
) -> web_playwright_backend.WebPayload:
    """抛出 process-entry typed URL safety error。

    Args:
        url: 目标 URL。
        timeout_seconds: browser timeout。
        headers: 请求头。
        playwright_channel: browser channel。
        playwright_storage_state_path: storage state 路径。
        egress_policy: 出站策略。
        browser_resource_budget: browser budget。

    Returns:
        不返回。

    Raises:
        web_fetch_orchestrator._FetchUrlSafetyError: 始终抛出。
    """

    del (
        url,
        timeout_seconds,
        headers,
        playwright_channel,
        playwright_storage_state_path,
        egress_policy,
        browser_resource_budget,
    )
    raise web_fetch_orchestrator._FetchUrlSafetyError(
        url="http://127.0.0.1/private?secret=value",
        reason="playwright_route",
    )


def _process_entry_failed_worker(
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    egress_policy: WebEgressPolicy,
    browser_resource_budget: BrowserResourceBudget,
) -> web_playwright_backend.WebPayload:
    """抛出 process-entry 普通 worker failure。

    Args:
        url: 目标 URL。
        timeout_seconds: browser timeout。
        headers: 请求头。
        playwright_channel: browser channel。
        playwright_storage_state_path: storage state 路径。
        egress_policy: 出站策略。
        browser_resource_budget: browser budget。

    Returns:
        不返回。

    Raises:
        RuntimeError: 始终抛出。
    """

    del (
        url,
        timeout_seconds,
        headers,
        playwright_channel,
        playwright_storage_state_path,
        egress_policy,
        browser_resource_budget,
    )
    raise RuntimeError("synthetic diagnostic failure")


def _skip_new_process_session() -> bool:
    """在 process-entry 单元测试中跳过真实 POSIX session 切换。

    Args:
        无。

    Returns:
        返回 ``False``，表示未进入新的 process session。

    Raises:
        无。
    """

    return False


def test_web_provider_discovers_search_and_fetch() -> None:
    """ToolsDiscovery 应发现两个 Web tools。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: provider 未精确暴露两个 Web tools 时抛出。
    """

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


def test_egress_custom_port_policy_is_independent_from_private_network_policy() -> None:
    """custom-port 与 private-network 必须由两个独立 typed facts 决策。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 两个 policy fact 未独立生效时抛出。
    """

    custom_port_target = WebEgressPolicy(
        allow_private_network=False,
        allow_custom_port=True,
        resolver=_resolve_public_test_address,
    ).authorize_http_target("https://example.com:8443/report", stage="test_custom_port")

    assert custom_port_target.port == 8443
    with pytest.raises(WebEgressPolicyError, match="custom port is not allowed"):
        WebEgressPolicy(
            allow_private_network=True,
            allow_custom_port=False,
            resolver=_resolve_private_test_address,
        ).authorize_http_target("http://fixture.test:43119/report", stage="test_custom_port")


def test_search_visibility_consumes_same_private_and_custom_port_policy() -> None:
    """search result visibility 必须直接消费与 fetch 同型的 WebEgressPolicy。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: search visibility 与 typed egress policy 不一致时抛出。
    """

    rows: list[web_search_providers.SearchResultRow] = [
        {
            "title": "standard",
            "url": "https://example.com/report",
            "snippet": "standard",
            "published_date": "",
        },
        {
            "title": "custom",
            "url": "https://example.com:8443/report",
            "snippet": "custom",
            "published_date": "",
        },
        {
            "title": "private",
            "url": "http://127.0.0.1/report",
            "snippet": "private",
            "published_date": "",
        },
    ]

    default_visible = web_search_providers._filter_visible_results(
        rows=rows,
        egress_policy=_public_test_policy(),
    )
    custom_visible = web_search_providers._filter_visible_results(
        rows=rows,
        egress_policy=WebEgressPolicy(
            allow_custom_port=True,
            resolver=_resolve_public_test_address,
        ),
    )

    assert [row["title"] for row in default_visible] == ["standard"]
    assert [row["title"] for row in custom_visible] == ["standard", "custom"]


def test_egress_transport_dependency_versions_are_locked() -> None:
    """target-bound 扩展点必须在 plan 锁定的 requests/urllib3 版本上运行。"""

    assert package_version("requests") == "2.33.1"
    assert package_version("urllib3") == "2.6.3"


def test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """proxy allow 必须使用标准 Session 并原样复用一次 merge 的 settings。

    Args:
        monkeypatch: pytest 属性替换夹具。
        caplog: pytest 日志捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: prepare/merge/select/send 未消费同一 settings 时抛出。
    """

    source_session = web_http_session._create_no_retry_session()
    target = AuthorizedHttpTarget(
        normalized_url="https://example.com/report?secret=hidden",
        scheme="https",
        hostname="example.com",
        port=443,
        approved_addresses=("93.184.216.34",),
    )
    prepared_count = 0
    merged_count = 0
    selected_proxy_ids: list[int] = []
    sent_proxy_ids: list[int] = []
    proxy_settings = {"https": "http://user:credential@proxy.invalid:8080"}
    settings: web_http_session._MergedEnvironmentSettings = {
        "proxies": proxy_settings,
        "stream": True,
        "verify": True,
        "cert": None,
    }
    original_prepare = requests.Session.prepare_request

    def record_prepare(
        session: requests.Session,
        request: requests.Request,
    ) -> requests.PreparedRequest:
        """记录唯一 prepare 调用并执行 requests 标准实现。

        Args:
            session: 当前 attempt-local Session。
            request: 待 prepare 的请求。

        Returns:
            标准 requests prepared request。

        Raises:
            requests.RequestException: 标准 prepare 失败时原样抛出。
        """

        nonlocal prepared_count
        prepared_count += 1
        assert session.trust_env is True
        return original_prepare(session, request)

    def record_merge(
        session: requests.Session,
        url: str,
        proxies: Mapping[str, str],
        stream: bool,
        verify: bool | str,
        cert: str | tuple[str, str] | None,
    ) -> web_http_session._MergedEnvironmentSettings:
        """返回唯一 merged settings 对象并记录空 per-call proxy 输入。

        Args:
            session: 当前 attempt-local Session。
            url: 当前 prepared URL。
            proxies: per-call proxy 输入。
            stream: stream 开关。
            verify: TLS verify 设置。
            cert: client certificate 设置。

        Returns:
            供 select 与 send 共同消费的同一个 settings。

        Raises:
            AssertionError: trust_env 或调用参数漂移时抛出。
        """

        nonlocal merged_count
        merged_count += 1
        assert session.trust_env is True
        assert url == target.normalized_url
        assert dict(proxies) == {}
        assert stream is True
        assert verify is True
        assert cert is None
        return settings

    def record_select_proxy(
        url: str,
        proxies: Mapping[str, str] | None,
    ) -> str | None:
        """记录 select_proxy 收到的 merged proxy 对象。

        Args:
            url: 当前 prepared URL。
            proxies: merged proxy 映射。

        Returns:
            确定性 active proxy。

        Raises:
            AssertionError: URL 或 proxy 对象发生复制时抛出。
        """

        assert url == target.normalized_url
        assert proxies is proxy_settings
        selected_proxy_ids.append(id(proxies))
        return proxy_settings["https"]

    def record_send(
        session: requests.Session,
        request: requests.PreparedRequest,
        *,
        timeout: float,
        allow_redirects: bool,
        proxies: dict[str, str],
        stream: bool,
        verify: bool | str,
        cert: str | tuple[str, str] | None,
    ) -> requests.Response:
        """记录 send 收到的原 merged settings 并返回确定性响应。

        Args:
            session: 当前 attempt-local Session。
            request: 唯一 prepared request。
            timeout: 请求 timeout。
            allow_redirects: 自动 redirect 开关。
            proxies: merged proxy 映射。
            stream: stream 开关。
            verify: TLS verify 设置。
            cert: client certificate 设置。

        Returns:
            确定性空响应。

        Raises:
            AssertionError: transport 调用参数漂移时抛出。
        """

        assert session.trust_env is True
        assert request.url == target.normalized_url
        assert timeout == 1.0
        assert allow_redirects is False
        assert proxies is proxy_settings
        assert stream is True
        assert verify is True
        assert cert is None
        sent_proxy_ids.append(id(proxies))
        response = requests.Response()
        response.status_code = 200
        response.url = target.normalized_url
        response.request = request
        return response

    monkeypatch.setattr(requests.Session, "prepare_request", record_prepare)
    monkeypatch.setattr(requests.Session, "merge_environment_settings", record_merge)
    monkeypatch.setattr(requests.utils, "select_proxy", record_select_proxy)
    monkeypatch.setattr(requests.Session, "send", record_send)
    caplog.set_level(logging.WARNING, logger=web_http_session.__name__)
    try:
        lease = web_http_session._send_authorized_request(
            source_session,
            target=target,
            method="GET",
            timeout=1.0,
            headers={},
            stream=True,
            transport_policy=_PROXY_ALLOWED_TRANSPORT_POLICY,
        )
        lease.close()
    finally:
        source_session.close()

    assert prepared_count == 1
    assert merged_count == 1
    assert selected_proxy_ids == sent_proxy_ids
    warning_messages = [record.getMessage() for record in caplog.records if record.name == web_http_session.__name__]
    assert warning_messages == ["environment_proxy_active=true " "reason=environment_proxy_active_without_peer_proof"]
    assert "credential" not in warning_messages[0]
    assert "example.com" not in warning_messages[0]


def test_http_transport_proxy_deny_ignores_environment_and_sends_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """proxy deny 必须令 trust_env=false 且同次 send 收到空 proxies。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: direct transport 读取环境或传入 proxy 时抛出。
    """

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    source_session = web_http_session._create_no_retry_session()
    target = AuthorizedHttpTarget(
        normalized_url="https://example.com/report",
        scheme="https",
        hostname="example.com",
        port=443,
        approved_addresses=("93.184.216.34",),
    )
    observed_proxies: list[dict[str, str]] = []

    def record_direct_send(
        session: requests.Session,
        request: requests.PreparedRequest,
        *,
        timeout: float,
        allow_redirects: bool,
        proxies: dict[str, str],
        stream: bool,
        verify: bool | str,
        cert: str | tuple[str, str] | None,
    ) -> requests.Response:
        """记录 direct send 的 trust_env 与空 proxy settings。

        Args:
            session: 当前 attempt-local Session。
            request: prepared request。
            timeout: 请求 timeout。
            allow_redirects: 自动 redirect 开关。
            proxies: merge 后 proxy 映射。
            stream: stream 开关。
            verify: TLS verify 设置。
            cert: client certificate 设置。

        Returns:
            确定性空响应。

        Raises:
            AssertionError: direct transport 参数漂移时抛出。
        """

        del timeout, allow_redirects, stream, verify, cert
        assert session.trust_env is False
        assert request.url == target.normalized_url
        observed_proxies.append(proxies)
        response = requests.Response()
        response.status_code = 200
        response.url = target.normalized_url
        response.request = request
        return response

    monkeypatch.setattr(requests.Session, "send", record_direct_send)
    try:
        lease = web_http_session._send_authorized_request(
            source_session,
            target=target,
            method="GET",
            timeout=1.0,
            headers={},
            stream=False,
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        )
        lease.close()
    finally:
        source_session.close()

    assert observed_proxies == [{}]


def test_http_transport_proof_with_active_proxy_fails_typed_before_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """proof on 遇到当前 URL active proxy 必须 typed fail 且不得降级发送。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: typed 冲突未在 send 前阻断时抛出。
    """

    source_session = web_http_session._create_no_retry_session()
    target = AuthorizedHttpTarget(
        normalized_url="https://example.com/report",
        scheme="https",
        hostname="example.com",
        port=443,
        approved_addresses=("93.184.216.34",),
    )
    proxy_settings = {"https": "http://proxy.invalid:8080"}
    settings: web_http_session._MergedEnvironmentSettings = {
        "proxies": proxy_settings,
        "stream": False,
        "verify": True,
        "cert": None,
    }
    send_calls: list[str] = []

    def return_proxy_settings(
        session: requests.Session,
        url: str,
        proxies: Mapping[str, str],
        stream: bool,
        verify: bool | str,
        cert: str | tuple[str, str] | None,
    ) -> web_http_session._MergedEnvironmentSettings:
        """为 proof/proxy 冲突返回确定性 active proxy settings。

        Args:
            session: 当前 attempt-local Session。
            url: 当前 prepared URL。
            proxies: per-call proxy 输入。
            stream: stream 开关。
            verify: TLS verify 设置。
            cert: client certificate 设置。

        Returns:
            含 active proxy 的 merged settings。

        Raises:
            AssertionError: proof attempt 未允许读取环境时抛出。
        """

        del url, proxies, stream, verify, cert
        assert session.trust_env is True
        return settings

    def select_active_proxy(
        url: str,
        proxies: Mapping[str, str] | None,
    ) -> str | None:
        """返回当前 URL 的 active proxy。

        Args:
            url: 当前 prepared URL。
            proxies: merged proxy 映射。

        Returns:
            确定性 proxy URI。

        Raises:
            AssertionError: sender 未传同一 proxy 对象时抛出。
        """

        del url
        assert proxies is proxy_settings
        return proxy_settings["https"]

    def reject_send(
        session: requests.Session,
        request: requests.PreparedRequest,
        *,
        timeout: float,
        allow_redirects: bool,
        proxies: dict[str, str],
        stream: bool,
        verify: bool | str,
        cert: str | tuple[str, str] | None,
    ) -> requests.Response:
        """记录任何不应发生的 proof/proxy 降级发送。

        Args:
            session: 当前 Session。
            request: prepared request。
            timeout: 请求 timeout。
            allow_redirects: 自动 redirect 开关。
            proxies: merged proxy 映射。
            stream: stream 开关。
            verify: TLS verify 设置。
            cert: client certificate 设置。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出以暴露静默降级。
        """

        del session, request, timeout, allow_redirects, proxies, stream, verify, cert
        send_calls.append("unexpected")
        raise AssertionError("proof/proxy conflict must fail before send")

    monkeypatch.setattr(
        requests.Session,
        "merge_environment_settings",
        return_proxy_settings,
    )
    monkeypatch.setattr(requests.utils, "select_proxy", select_active_proxy)
    monkeypatch.setattr(requests.Session, "send", reject_send)
    proof_with_proxy = web_http_session.WebHttpTransportPolicy(
        dns_peer_proof_enabled=True,
        allow_environment_proxy=True,
    )
    try:
        with pytest.raises(web_http_session.ProxyPeerProofIncompatibleError) as exc_info:
            web_http_session._send_authorized_request(
                source_session,
                target=target,
                method="GET",
                timeout=1.0,
                headers={},
                stream=False,
                transport_policy=proof_with_proxy,
            )
    finally:
        source_session.close()

    assert exc_info.value.reason == "proxy_peer_proof_incompatible"
    assert str(exc_info.value) == "proxy_peer_proof_incompatible"
    assert send_calls == []


def test_egress_target_bound_http_preserves_host_and_numeric_destination() -> None:
    """真实 adapter/pool/connection 必须只连接授权 IP 并保留 HTTP Host。"""

    server = _SocketWebServer.start(response_body=b"pinned http", max_connections=2)
    resolver_calls: list[tuple[str, int]] = []

    def resolver(hostname: str, port: int) -> tuple[str, ...]:
        """记录 owner DNS 调用并固定到 loopback fixture。"""

        resolver_calls.append((hostname, port))
        return ("127.0.0.1",)

    policy = WebEgressPolicy(
        allow_private_network=True,
        allow_custom_port=True,
        resolver=resolver,
    )
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
            transport_policy=_PEER_PROOF_TRANSPORT_POLICY,
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
        allow_custom_port=True,
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
            transport_policy=_PEER_PROOF_TRANSPORT_POLICY,
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
        allow_custom_port=True,
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
            transport_policy=_PEER_PROOF_TRANSPORT_POLICY,
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

    target = WebEgressPolicy(
        allow_private_network=True,
        allow_custom_port=True,
        resolver=resolver,
    ).authorize_http_target(
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
                transport_policy=_PEER_PROOF_TRANSPORT_POLICY,
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
    assert fetch_definition.schema.function.parameters.properties["url"] == {
        "type": "string",
        "description": (
            "要抓取的完整 http/https URL。"
            "优先使用 search_web 返回的 URL。"
        ),
    }


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

    definition = _definitions_by_name(_discover_definitions({"allow_private_network_url": True}))[tool_name]
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
        definition = _definitions_by_name(_discover_definitions({"allow_private_network_url": True}))["fetch_web_page"]
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
        tool_runtime = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
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
    assert accept_port.candidates[0].governance.policy_decision.reason_code == ("tool_runtime_cancelled")


def test_search_public_web_provider_result_excludes_llm_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search provider 边界只返回结构化事实，不生成 LLM guidance 字段。"""

    observed_budgets: list[HttpResourceBudget] = []

    def fake_search_with_duckduckgo(
        *,
        query: str,
        domains: list[str],
        max_results: int,
        timeout_seconds: float,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        http_resource_budget: HttpResourceBudget,
    ) -> list[web_search_providers.SearchResultRow]:
        """返回确定性 provider 原始结果。

        Args:
            query: 检索关键词。
            domains: 域名过滤。
            max_results: 返回数量。
            timeout_seconds: HTTP 请求超时秒数。
            timeout_budget: 工具调用总预算。
            deadline_monotonic: 工具调用 deadline。
            egress_policy: provider endpoint 出站策略。
            transport_policy: 当前 attempt transport policy。
            normalize_whitespace: 空白规整函数。
            resolve_timeout_budget: timeout 预算解析函数。
            http_resource_budget: Web response 资源预算。

        Returns:
            单条 provider 原始结果。

        Raises:
            无。
        """

        del (
            query,
            domains,
            max_results,
            timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            egress_policy,
            transport_policy,
            normalize_whitespace,
            resolve_timeout_budget,
        )
        observed_budgets.append(http_resource_budget)
        return [
            {
                "title": "10-K",
                "url": "https://www.sec.gov/Archives/example.htm",
                "snippet": "annual report",
                "published_date": "",
            }
        ]

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
        egress_policy=_public_test_policy(),
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        normalize_whitespace=normalize_whitespace,
        resolve_timeout_budget=resolve_timeout_budget,
        http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
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
    assert observed_budgets == [_DEFAULT_HTTP_RESOURCE_BUDGET]


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

    outcome = asyncio.run(definition.callable(_call("search_web", {"query": "revenue"}), _context()))

    assert isinstance(outcome, ToolCompletedOutcome)
    assert calls[0]["provider"] == "serper"
    assert calls[0]["request_timeout_seconds"] == 3.5
    assert calls[0]["max_search_results"] == 4
    assert cast(WebEgressPolicy, calls[0]["egress_policy"]).allows_private_network is True
    assert cast(WebEgressPolicy, calls[0]["egress_policy"]).allows_custom_port is True
    assert calls[0]["http_resource_budget"] == DEFAULT_HTTP_RESOURCE_BUDGET


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
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        http_resource_budget: HttpResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebProviderResult:
        """记录 token identity 并返回确定性搜索结果。

        Args:
            query: 检索关键词。
            domains: 可选域名限制。
            recency_days: 可选最近天数。
            max_results: 请求结果数量。
            max_search_results: 注册配置中的结果上限。
            provider: provider 策略。
            request_timeout_seconds: 单次 provider 请求超时。
            timeout_budget: 当前工具调用预算。
            deadline_monotonic: 当前工具调用 deadline。
            egress_policy: 搜索结果出站策略。
            transport_policy: 当前 attempt transport policy。
            normalize_whitespace: 空白规整函数。
            resolve_timeout_budget: timeout 预算解析函数。
            http_resource_budget: Web response 资源预算。
            cancellation_token: execution context 注入的取消令牌。

        Returns:
            确定性 provider 搜索事实。

        Raises:
            无。
        """

        del (
            domains,
            recency_days,
            max_search_results,
            provider,
            request_timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            egress_policy,
            transport_policy,
            normalize_whitespace,
            resolve_timeout_budget,
            http_resource_budget,
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
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        http_resource_budget: HttpResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebProviderResult:
        """记录非预期 provider 调用。

        Args:
            query: 检索关键词。
            domains: 可选域名限制。
            recency_days: 可选最近天数。
            max_results: 请求结果数量。
            max_search_results: 注册配置中的结果上限。
            provider: provider 策略。
            request_timeout_seconds: 单次 provider 请求超时。
            timeout_budget: 当前工具调用预算。
            deadline_monotonic: 当前工具调用 deadline。
            egress_policy: 搜索结果出站策略。
            transport_policy: 当前 attempt transport policy。
            normalize_whitespace: 空白规整函数。
            resolve_timeout_budget: timeout 预算解析函数。
            http_resource_budget: Web response 资源预算。
            cancellation_token: execution context 注入的取消令牌。

        Returns:
            空 provider 搜索事实。

        Raises:
            无。
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
            egress_policy,
            transport_policy,
            normalize_whitespace,
            resolve_timeout_budget,
            http_resource_budget,
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
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        http_resource_budget: HttpResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebProviderResult:
        """模拟搜索 provider 在深层 checkpoint 抛出携带治理字段的取消。

        Args:
            query: 检索关键词。
            domains: 可选域名限制。
            recency_days: 可选最近天数。
            max_results: 请求结果数量。
            max_search_results: 注册配置中的结果上限。
            provider: provider 策略。
            request_timeout_seconds: 单次 provider 请求超时。
            timeout_budget: 当前工具调用预算。
            deadline_monotonic: 当前工具调用 deadline。
            egress_policy: 搜索结果出站策略。
            transport_policy: 当前 attempt transport policy。
            normalize_whitespace: 空白规整函数。
            resolve_timeout_budget: timeout 预算解析函数。
            http_resource_budget: Web response 资源预算。
            cancellation_token: execution context 注入的取消令牌。

        Returns:
            不返回。

        Raises:
            WebSearchCancelledError: 始终抛出测试取消。
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
            egress_policy,
            transport_policy,
            normalize_whitespace,
            resolve_timeout_budget,
            http_resource_budget,
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
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        http_resource_budget: HttpResourceBudget,
    ) -> list[web_search_providers.SearchResultRow]:
        """模拟首个 provider 失败并同时触发 Host cancel。

        Args:
            query: 检索关键词。
            domains: 域名限制。
            recency_days: 最近天数。
            max_results: 返回数量。
            timeout_seconds: HTTP 请求超时。
            egress_policy: provider endpoint 出站策略。
            transport_policy: 当前 attempt transport policy。
            timeout_budget: 当前工具预算。
            deadline_monotonic: 当前工具 deadline。
            resolve_timeout_budget: timeout 预算解析函数。
            http_resource_budget: Web response 资源预算。

        Returns:
            不返回。

        Raises:
            RuntimeError: 始终抛出 provider 失败。
        """

        del (
            query,
            domains,
            recency_days,
            max_results,
            timeout_seconds,
            egress_policy,
            transport_policy,
            timeout_budget,
            deadline_monotonic,
            resolve_timeout_budget,
            http_resource_budget,
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
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        http_resource_budget: HttpResourceBudget,
    ) -> list[web_search_providers.SearchResultRow]:
        """记录非预期 DuckDuckGo fallback。

        Args:
            query: 检索关键词。
            domains: 域名限制。
            max_results: 返回数量。
            timeout_seconds: HTTP 请求超时。
            egress_policy: provider endpoint 出站策略。
            transport_policy: 当前 attempt transport policy。
            timeout_budget: 当前工具预算。
            deadline_monotonic: 当前工具 deadline。
            normalize_whitespace: 空白规整函数。
            resolve_timeout_budget: timeout 预算解析函数。
            http_resource_budget: Web response 资源预算。

        Returns:
            空结果。

        Raises:
            无。
        """

        del (
            query,
            domains,
            max_results,
            timeout_seconds,
            egress_policy,
            transport_policy,
            timeout_budget,
            deadline_monotonic,
            normalize_whitespace,
            resolve_timeout_budget,
            http_resource_budget,
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


def test_fetch_private_url_fails_closed_with_explicit_false() -> None:
    """显式关闭 private/local URL 时必须由 typed policy 拒绝。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: private URL 未 fail closed 时抛出。
    """

    definition = _definitions_by_name(_discover_definitions({"allow_private_network_url": False}))["fetch_web_page"]

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

    sentinel = "5a" * 32
    raw_final_url = f"https://{sentinel}:{sentinel}@example.com/report" f"?token={sentinel}#{sentinel}"
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
            "final_url": raw_final_url,
            "title": "Internal",
            "content": "local test content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "extraction_source": "mock",
            "renderer_source": "mock",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(web_tools, "_fetch_and_convert_content", fake_fetch_and_convert_content)
    definition = _definitions_by_name(_discover_definitions({"allow_private_network_url": True}))["fetch_web_page"]

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
    assert value["final_url"] == "https://example.com/report"
    assert sentinel not in str(value["final_url"])
    assert "ok" not in value


def test_fetch_redirect_to_private_url_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP redirect 每一跳都必须复用 private-network safety owner。"""

    response = _counting_response(
        url="https://example.com/report",
        status_code=302,
        body=b"",
        headers={"Location": "http://127.0.0.1/internal"},
    )
    session = _QueuedSession([response])

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
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
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
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
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
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
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
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
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
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
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
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
    )

    assert result["ok"] is True
    assert response.close_count == 1


def test_fetch_meta_refresh_to_private_url_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTML meta refresh 目标必须在继续抓取前复用同一 URL safety owner。"""

    html = b'<html><head><meta http-equiv="refresh" ' b'content="0;url=http://127.0.0.1/internal"></head></html>'
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
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
        )

    assert exc_info.value.url == "http://127.0.0.1/internal"
    assert session.calls == [("GET", "https://example.com/report", True)]


def test_fetch_meta_refresh_treats_redirect_hop_as_visited(monkeypatch: pytest.MonkeyPatch) -> None:
    """meta refresh 防环必须消费 HTTP redirect 已访问 URL 记录。"""

    html = b'<html><head><meta http-equiv="refresh" ' b'content="0;url=https://example.com/redirected"></head></html>'
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
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
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
            http_resource_budget=_http_resource_budget(
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
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            http_resource_budget=_http_resource_budget(
                wire_body_bytes=4,
                decoded_body_bytes=4,
            ),
        )


def test_fetch_http_budget_success_paths_keep_html_and_non_html_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP child budget 迁移后 HTML 与 non-HTML conversion 结果必须保持。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: HTML 或 non-HTML owner 语义发生漂移时抛出。
    """

    html_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=b"<html><body>Revenue grew.</body></html>",
        headers={"Content-Type": "text/html; charset=utf-8"},
    )
    pdf_response = _raw_response(
        url="https://example.com/report.pdf",
        status_code=200,
        body=b"%PDF synthetic",
        headers={"Content-Type": "application/pdf"},
    )
    sessions = [_QueuedSession([html_response]), _QueuedSession([pdf_response])]
    monkeypatch.setattr(
        web_fetch_orchestrator,
        "_send_authorized_request",
        _queued_send_authorized_request,
    )

    html_result = web_fetch_orchestrator._fetch_and_convert_content(
        "https://example.com/report",
        timeout_seconds=1.0,
        resolve_timeout_budget=web_tools._resolve_timeout_budget,
        normalize_url_for_http=web_tools._normalize_url_for_http,
        build_referer=web_tools._build_referer,
        convert_html=_convert_expected_fetch_html,
        convert_non_html=_reject_non_html_conversion,
        session=cast(requests.Session, sessions[0]),
        headers={},
        egress_policy=_public_test_policy(),
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        http_resource_budget=_http_resource_budget(),
    )
    pdf_result = web_fetch_orchestrator._fetch_and_convert_content(
        "https://example.com/report.pdf",
        timeout_seconds=1.0,
        resolve_timeout_budget=web_tools._resolve_timeout_budget,
        normalize_url_for_http=web_tools._normalize_url_for_http,
        build_referer=web_tools._build_referer,
        convert_html=_reject_fetch_html_conversion,
        convert_non_html=_convert_expected_pdf,
        session=cast(requests.Session, sessions[1]),
        headers={},
        egress_policy=_public_test_policy(),
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        http_resource_budget=_http_resource_budget(),
    )

    assert html_result["content"] == "Revenue grew."
    assert html_result["renderer_source"] == "synthetic"
    assert pdf_result["title"] == "PDF"
    assert pdf_result["content"] == "page.pdf:14"
    assert pdf_result["renderer_source"] == "docling"


@pytest.mark.parametrize("invalid_value", [True, 0, -1, cast(int, 1.5)])
def test_resource_budget_constructor_rejects_bool_and_non_positive_integer(
    invalid_value: int,
) -> None:
    """三个 child owner 构造期都必须拒绝 bool、非整数与非正整数。"""

    with pytest.raises(ValueError, match="wire_body_bytes"):
        HttpResourceBudget(
            wire_body_bytes=invalid_value,
            decoded_body_bytes=2,
        )
    with pytest.raises(ValueError, match="warmup_body_bytes"):
        BrowserResourceBudget(
            warmup_body_bytes=invalid_value,
            dom_chars=2,
            text_chars=1,
        )
    with pytest.raises(ValueError, match="error_chars"):
        DiagnosticResourceBudget(error_chars=invalid_value, events=1)


def test_resource_budget_provider_config_complete_object_and_default() -> None:
    """完整 nested resource_budget 成功，整个 object 缺失时使用 typed defaults。"""

    parsed = web_provider._parse_config({"resource_budget": _resource_budget_json()})
    defaulted = web_provider._parse_config({})

    assert parsed.resource_budgets == _resource_budgets()
    assert defaulted.resource_budgets == WebResourceBudgets(
        http=DEFAULT_HTTP_RESOURCE_BUDGET,
        browser=DEFAULT_BROWSER_RESOURCE_BUDGET,
        diagnostics=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    )

    with pytest.raises(ValueError, match="must be an object"):
        web_provider._parse_config({"resource_budget": "invalid"})


def test_resource_budget_provider_config_applies_only_local_child_default() -> None:
    """nested 局部 override 只补同 owner sibling，不改写其他 child。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: local default 改写 sibling owner 时抛出。
    """

    parsed = web_provider._parse_config({"resource_budget": {"http": {"wire_body_bytes": 17}}})

    assert parsed.resource_budgets.http == HttpResourceBudget(
        wire_body_bytes=17,
        decoded_body_bytes=DEFAULT_HTTP_RESOURCE_BUDGET.decoded_body_bytes,
    )
    assert parsed.resource_budgets.browser == DEFAULT_BROWSER_RESOURCE_BUDGET
    assert parsed.resource_budgets.diagnostics == DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET


def test_web_provider_config_rejects_unknown_typo_and_keeps_partial_defaults() -> None:
    """Web raw parser 拒绝顶层 typo，同时保留合法 partial record 的局部默认。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 未知字段路径或 partial/default 语义不符合契约时抛出。
    """

    assert web_provider._CONFIG_FIELDS == frozenset(
        {
            "provider",
            "request_timeout_seconds",
            "max_search_results",
            "fetch_truncate_chars",
            "allow_private_network_url",
            "allow_custom_port_url",
            "dns_peer_proof_enabled",
            "allow_environment_proxy",
            "browser_enabled",
            "playwright_channel",
            "playwright_storage_state_dir",
            "resource_budget",
        }
    )
    with pytest.raises(
        ValueError,
        match=r"web provider config\.allow_prvate_network_url",
    ):
        web_provider._parse_config({"allow_prvate_network_url": False})

    parsed = web_provider._parse_config(
        {
            "provider": "duckduckgo",
            "resource_budget": {"http": {"wire_body_bytes": 17}},
        }
    )
    assert parsed.provider == "duckduckgo"
    assert parsed.allow_private_network_url is True
    assert parsed.allow_custom_port_url is True
    assert parsed.browser_enabled is True
    assert parsed.transport_policy == web_http_session.WebHttpTransportPolicy(
        dns_peer_proof_enabled=False,
        allow_environment_proxy=True,
    )
    assert parsed.resource_budgets.http == HttpResourceBudget(
        wire_body_bytes=17,
        decoded_body_bytes=DEFAULT_HTTP_RESOURCE_BUDGET.decoded_body_bytes,
    )
    assert parsed.resource_budgets.browser == DEFAULT_BROWSER_RESOURCE_BUDGET
    assert parsed.resource_budgets.diagnostics == DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET


@pytest.mark.parametrize("invalid_value", [True, 0, -1])
def test_resource_budget_provider_config_rejects_unknown_and_invalid_values(
    invalid_value: int,
) -> None:
    """nested budget 未知 group/field 与非法值必须精确 fail fast。

    Args:
        invalid_value: 当前非法 budget 字段值。

    Returns:
        无。

    Raises:
        AssertionError: 任一非法 nested budget 未被精确拒绝时抛出。
    """

    with pytest.raises(ValueError, match="wire_body_bytes"):
        web_provider._parse_config({"resource_budget": {"http": {"wire_body_bytes": invalid_value}}})

    with pytest.raises(ValueError, match="unknown groups: unexpected"):
        web_provider._parse_config({"resource_budget": {"unexpected": {}}})
    with pytest.raises(ValueError, match="http has unknown fields: unexpected"):
        web_provider._parse_config({"resource_budget": {"http": {"unexpected": 1}}})
    with pytest.raises(ValueError, match="resource_budget.http must be an object"):
        web_provider._parse_config({"resource_budget": {"http": 1}})


def test_packaged_web_config_matches_typed_policy_and_budget_defaults() -> None:
    """packaged Web 五 bool 与三 owner ceilings 必须逐字段等于 typed defaults。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: packaged projection 与 typed defaults 不同源时抛出。
    """

    config_path = Path(__file__).resolve().parents[3] / "dayu" / "config" / "tool_discovery.json"
    document = cast(
        Mapping[str, JsonValue],
        json_module.loads(config_path.read_text(encoding="utf-8")),
    )
    providers = cast(Mapping[str, JsonValue], document["providers"])
    web_record = cast(Mapping[str, JsonValue], providers["web-tools"])
    packaged_config = cast(Mapping[str, JsonValue], web_record["config"])

    parsed = web_provider._parse_config(packaged_config)

    assert parsed.allow_private_network_url is True
    assert parsed.allow_custom_port_url is True
    assert parsed.browser_enabled is True
    assert parsed.transport_policy == web_http_session.WebHttpTransportPolicy(
        dns_peer_proof_enabled=False,
        allow_environment_proxy=True,
    )
    assert parsed.resource_budgets == WebResourceBudgets(
        http=DEFAULT_HTTP_RESOURCE_BUDGET,
        browser=DEFAULT_BROWSER_RESOURCE_BUDGET,
        diagnostics=DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    )


def test_web_policy_config_defaults_and_overrides_are_independent() -> None:
    """五个布尔 policy facts 必须各自采用冻结默认并可独立覆盖。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一 policy fact 的默认或 override 不独立时抛出。
    """

    defaulted = web_provider._parse_config({})
    overridden = web_provider._parse_config(
        {
            "allow_private_network_url": False,
            "allow_custom_port_url": False,
            "dns_peer_proof_enabled": True,
            "allow_environment_proxy": False,
            "browser_enabled": False,
        }
    )

    assert defaulted.allow_private_network_url is True
    assert defaulted.allow_custom_port_url is True
    assert defaulted.transport_policy == web_http_session.WebHttpTransportPolicy(
        dns_peer_proof_enabled=False,
        allow_environment_proxy=True,
    )
    assert defaulted.browser_enabled is True
    assert overridden.allow_private_network_url is False
    assert overridden.allow_custom_port_url is False
    assert overridden.transport_policy == web_http_session.WebHttpTransportPolicy(
        dns_peer_proof_enabled=True,
        allow_environment_proxy=False,
    )
    assert overridden.browser_enabled is False


@pytest.mark.parametrize(
    ("field_name", "override"),
    [
        ("allow_private_network_url", True),
        ("allow_private_network_url", False),
        ("allow_custom_port_url", True),
        ("allow_custom_port_url", False),
        ("dns_peer_proof_enabled", True),
        ("dns_peer_proof_enabled", False),
        ("allow_environment_proxy", True),
        ("allow_environment_proxy", False),
        ("browser_enabled", True),
        ("browser_enabled", False),
    ],
)
def test_web_policy_config_single_override_preserves_four_sibling_defaults(
    field_name: str,
    override: bool,
) -> None:
    """final record 单字段 override 不得改变其余四个 typed defaults。

    Args:
        field_name: 当前覆盖的 policy 字段名。
        override: 当前覆盖值。

    Returns:
        无。

    Raises:
        AssertionError: 单字段 override 改写任一 sibling 时抛出。
    """

    parsed = web_provider._parse_config({field_name: override})
    observed = {
        "allow_private_network_url": parsed.allow_private_network_url,
        "allow_custom_port_url": parsed.allow_custom_port_url,
        "dns_peer_proof_enabled": parsed.transport_policy.dns_peer_proof_enabled,
        "allow_environment_proxy": parsed.transport_policy.allow_environment_proxy,
        "browser_enabled": parsed.browser_enabled,
    }
    expected = {
        "allow_private_network_url": True,
        "allow_custom_port_url": True,
        "dns_peer_proof_enabled": False,
        "allow_environment_proxy": True,
        "browser_enabled": True,
    }
    expected[field_name] = override

    assert observed == expected


@pytest.mark.parametrize(
    "field_name",
    [
        "allow_private_network_url",
        "allow_custom_port_url",
        "dns_peer_proof_enabled",
        "allow_environment_proxy",
        "browser_enabled",
    ],
)
@pytest.mark.parametrize("invalid_value", [1, "true", None])
def test_web_policy_config_rejects_non_boolean_values(
    field_name: str,
    invalid_value: JsonValue,
) -> None:
    """五个布尔 policy 字段都必须拒绝 int、string 与 null。

    Args:
        field_name: 当前校验的 policy 字段名。
        invalid_value: 当前非法 JSON 值。

    Returns:
        无。

    Raises:
        AssertionError: 非布尔输入未被精确拒绝时抛出。
    """

    with pytest.raises(ValueError, match=field_name):
        web_provider._parse_config({field_name: invalid_value})


def test_s2_owner_signatures_and_worker_payload_are_closed() -> None:
    """预算、transport、worker 与 process wrapper 必须满足 S2 owner 边界。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 类型、签名或 payload owner 闭集发生漂移时抛出。
    """

    aggregate_fields = fields(WebResourceBudgets)
    assert tuple(field.name for field in aggregate_fields) == (
        "http",
        "browser",
        "diagnostics",
    )
    assert all(field.default is MISSING for field in aggregate_fields)
    assert "__post_init__" not in WebResourceBudgets.__dict__

    config_fields = fields(web_tools.WebToolsConfig)
    assert all(field.default is MISSING for field in config_fields)
    assert all(field.default_factory is MISSING for field in config_fields)

    probe_parameters = inspect.signature(web_fetch_orchestrator._probe_content_type).parameters
    assert "http_resource_budget" not in probe_parameters
    assert "browser_resource_budget" not in probe_parameters
    assert "diagnostic_resource_budget" not in probe_parameters
    sender_parameters = inspect.signature(web_http_session._send_authorized_request).parameters
    assert sender_parameters["transport_policy"].default is inspect.Parameter.empty
    plain_sender_parameters = inspect.signature(web_http_session._send_authorized_plain_request).parameters
    assert plain_sender_parameters["transport_policy"].default is inspect.Parameter.empty

    worker_parameters = inspect.signature(web_playwright_backend._PlaywrightWorkerProtocol.__call__).parameters
    assert "browser_resource_budget" in worker_parameters
    assert "diagnostic_resource_budget" not in worker_parameters
    assert web_playwright_backend._WorkerKwargs.__required_keys__ == frozenset(
        {
            "url",
            "timeout_seconds",
            "headers",
            "playwright_channel",
            "playwright_storage_state_path",
            "egress_policy",
            "browser_resource_budget",
        }
    )
    process_parameters = inspect.signature(web_playwright_backend._run_playwright_worker_process).parameters
    assert process_parameters["diagnostic_resource_budget"].default is inspect.Parameter.empty
    assert process_parameters["allow_environment_proxy"].default is inspect.Parameter.empty


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
    exact_budget = _http_resource_budget(
        wire_body_bytes=1024,
        decoded_body_bytes=len(exact_body),
    )
    assert (
        web_fetch_orchestrator._read_limited_response_body(
            exact_response,
            http_resource_budget=exact_budget,
        )
        == exact_body
    )

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
            http_resource_budget=exact_budget,
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
    exact_budget = _http_resource_budget(
        wire_body_bytes=1024,
        decoded_body_bytes=len(exact_body),
    )
    exact_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=exact_body,
    )
    assert (
        web_fetch_orchestrator._read_limited_response_body(
            exact_response,
            http_resource_budget=exact_budget,
        )
        == exact_body
    )

    overflow_body = exact_body + b"!"
    overflow_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=overflow_body,
    )
    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded) as exc_info:
        web_fetch_orchestrator._read_limited_response_body(
            overflow_response,
            http_resource_budget=exact_budget,
        )
    assert exc_info.value.limit_kind == "decompressed"
    assert exc_info.value.observed_bytes == len(exact_body) + 1


def test_http_child_budget_owns_declared_length_and_bounded_codec_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP child owner 必须控制声明长度并拒绝无法有界解码的 encoding。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: 声明长度或 codec failure 未由 HTTP owner 控制时抛出。
    """

    declared_overflow = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=b"unused",
        headers={"Content-Length": "5"},
    )
    budget = _http_resource_budget(wire_body_bytes=4, decoded_body_bytes=8)
    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded) as exc_info:
        web_fetch_orchestrator._read_limited_response_body(
            declared_overflow,
            http_resource_budget=budget,
        )
    assert exc_info.value.limit_kind == "wire"
    assert exc_info.value.observed_bytes == 5

    invalid_declared_length = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=b"ok",
        headers={"Content-Length": "invalid"},
    )
    assert (
        web_fetch_orchestrator._read_limited_response_body(
            invalid_declared_length,
            http_resource_budget=_http_resource_budget(
                wire_body_bytes=8,
                decoded_body_bytes=8,
            ),
        )
        == b"ok"
    )

    monkeypatch.setattr(
        web_fetch_orchestrator,
        "_import_optional_module",
        _raise_missing_optional_zstd,
    )
    zstd_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=b"synthetic-zstd",
        headers={"Content-Encoding": "zstd"},
    )
    with pytest.raises(RuntimeError, match="zstd"):
        web_fetch_orchestrator._read_limited_response_body(
            zstd_response,
            http_resource_budget=_http_resource_budget(),
        )

    unknown_encoding = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=b"synthetic",
        headers={"Content-Encoding": "compress"},
    )
    with pytest.raises(RuntimeError, match="compress"):
        web_fetch_orchestrator._read_limited_response_body(
            unknown_encoding,
            http_resource_budget=_http_resource_budget(),
        )


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
    assert (
        web_fetch_orchestrator._read_limited_response_body(
            multi_layer_response,
            http_resource_budget=_http_resource_budget(
                wire_body_bytes=1024,
                decoded_body_bytes=1024,
            ),
        )
        == body
    )

    bomb_response = _raw_response(
        url="https://example.com/bomb",
        status_code=200,
        body=gzip.compress(b"x" * 10_000),
        headers={"Content-Encoding": "gzip"},
    )
    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded) as exc_info:
        web_fetch_orchestrator._read_limited_response_body(
            bomb_response,
            http_resource_budget=_http_resource_budget(
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
            http_resource_budget=_http_resource_budget(),
        )
    assert web_tools._build_fetch_headers("https://example.com/report")["Accept-Encoding"] == "gzip, deflate"


def test_decompress_zstd_streaming_uses_http_child_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """zstd stream-reader 必须按 HTTP child decoded cap 有界消费。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: stream-reader 绕过 HTTP decoded cap 时抛出。
    """

    monkeypatch.setattr(
        web_fetch_orchestrator,
        "_import_optional_module",
        _import_identity_zstd,
    )
    body = b"zstd bounded body"
    response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=body,
        headers={"Content-Encoding": "zstd"},
    )

    assert (
        web_fetch_orchestrator._read_limited_response_body(
            response,
            http_resource_budget=_http_resource_budget(decoded_body_bytes=len(body)),
        )
        == body
    )

    overflow_response = _raw_response(
        url="https://example.com/report",
        status_code=200,
        body=body,
        headers={"Content-Encoding": "zstd"},
    )
    with pytest.raises(web_fetch_orchestrator._FetchBodyLimitExceeded):
        web_fetch_orchestrator._read_limited_response_body(
            overflow_response,
            http_resource_budget=_http_resource_budget(decoded_body_bytes=4),
        )


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
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        browser_resource_budget=_browser_resource_budget(warmup_body_bytes=7),
    )

    assert result["consumed_body_bytes"] == 7
    assert session.calls == [("GET", "https://example.com/", True)]
    assert source.tell() == 7
    assert response.close_count == 1


def test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browser lifecycle owner 必须按 channel/headless key 创建、复用和替换。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: 单例创建、同 key 复用或 key 变化 cleanup/recreate 漂移时抛出。
    """

    browsers = tuple(_LifecyclePlaywrightBrowser() for _ in range(3))
    launchers = tuple(_LifecycleChromiumLauncher(browser) for browser in browsers)
    instances = tuple(_LifecyclePlaywrightInstance(launcher) for launcher in launchers)
    factory = _LifecycleSyncPlaywrightFactory(instances)
    monkeypatch.setattr(playwright_sync_api, "sync_playwright", factory)
    monkeypatch.setattr(web_playwright_backend, "_PW_INSTANCE", None)
    monkeypatch.setattr(web_playwright_backend, "_PW_BROWSER", None)
    monkeypatch.setattr(web_playwright_backend, "_PW_BROWSER_KEY", None)

    first = web_playwright_backend._get_playwright_browser(
        playwright_channel="chrome",
        headless=True,
    )
    reused = web_playwright_backend._get_playwright_browser(
        playwright_channel=" chrome ",
        headless=True,
    )
    channel_changed = web_playwright_backend._get_playwright_browser(
        playwright_channel="chromium",
        headless=True,
    )
    headless_changed = web_playwright_backend._get_playwright_browser(
        playwright_channel="chromium",
        headless=False,
    )

    assert first is browsers[0]
    assert reused is first
    assert channel_changed is browsers[1]
    assert headless_changed is browsers[2]
    assert len(factory.starters) == 3
    assert [starter.start_calls for starter in factory.starters] == [1, 1, 1]
    assert [len(launcher.launch_calls) for launcher in launchers] == [1, 1, 1]
    assert [
        (
            launcher.launch_calls[0]["headless"],
            launcher.launch_calls[0]["channel"],
        )
        for launcher in launchers
    ] == [
        (True, "chrome"),
        (True, "chromium"),
        (False, "chromium"),
    ]
    assert [browser.close_calls for browser in browsers] == [1, 1, 0]
    assert [instance.stop_calls for instance in instances] == [1, 1, 0]
    assert web_playwright_backend._PW_BROWSER is browsers[2]
    assert web_playwright_backend._PW_INSTANCE is instances[2]
    assert web_playwright_backend._PW_BROWSER_KEY == ("chromium", False)


@pytest.mark.parametrize(
    ("runtime_stop_error", "expected_cleanup_failure_diagnostics"),
    (
        (None, 0),
        (
            RuntimeError(
                "sensitive-stop-body "
                "url=https://user:password@example.test/private?token=secret "
                "header=Authorization credential=secret-value "
                "storage_path=/private/browser-state.json"
            ),
            1,
        ),
    ),
)
def test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    runtime_stop_error: RuntimeError | None,
    expected_cleanup_failure_diagnostics: int,
) -> None:
    """Browser launch失败必须停止局部runtime且不得发布singleton半状态。

    Args:
        monkeypatch: pytest 属性替换夹具。
        caplog: pytest 日志捕获夹具。
        runtime_stop_error: 局部runtime stop时需要抛出的可选异常。
        expected_cleanup_failure_diagnostics: 预期脱敏 cleanup-failure 诊断数量。

    Returns:
        无。

    Raises:
        AssertionError: cleanup、脱敏诊断、返回值或global发布契约漂移时抛出。
    """

    caplog.set_level(logging.DEBUG, logger=web_playwright_backend.__name__)
    browser = _LifecyclePlaywrightBrowser()
    launcher = _LifecycleChromiumLauncher(
        browser,
        launch_error=RuntimeError("synthetic launch failure"),
    )
    instance = _LifecyclePlaywrightInstance(
        launcher,
        stop_error=runtime_stop_error,
    )
    factory = _LifecycleSyncPlaywrightFactory((instance,))
    monkeypatch.setattr(playwright_sync_api, "sync_playwright", factory)
    monkeypatch.setattr(web_playwright_backend, "_PW_INSTANCE", None)
    monkeypatch.setattr(web_playwright_backend, "_PW_BROWSER", None)
    monkeypatch.setattr(web_playwright_backend, "_PW_BROWSER_KEY", None)

    result = web_playwright_backend._get_playwright_browser(
        playwright_channel="chrome",
        headless=True,
    )

    assert result is None
    assert len(factory.starters) == 1
    assert factory.starters[0].start_calls == 1
    assert len(launcher.launch_calls) == 1
    assert instance.stop_calls == 1
    assert web_playwright_backend._PW_INSTANCE is None
    assert web_playwright_backend._PW_BROWSER is None
    assert web_playwright_backend._PW_BROWSER_KEY is None
    cleanup_failure_diagnostics = [
        record.getMessage()
        for record in caplog.records
        if record.name == web_playwright_backend.__name__
        and record.levelno == logging.DEBUG
        and "stage=browser_launch_failure_runtime_stop" in record.getMessage()
    ]
    assert len(cleanup_failure_diagnostics) == expected_cleanup_failure_diagnostics
    if cleanup_failure_diagnostics:
        assert cleanup_failure_diagnostics == [
            "[ENGINE.WEB_PLAYWRIGHT] Playwright runtime cleanup failed "
            "stage=browser_launch_failure_runtime_stop exception_type=RuntimeError"
        ]
        for sensitive_fragment in (
            "sensitive-stop-body",
            "https://user:password@example.test/private?token=secret",
            "Authorization",
            "secret-value",
            "/private/browser-state.json",
        ):
            assert sensitive_fragment not in caplog.text


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
    budget = _browser_resource_budget(dom_chars=10, text_chars=10)

    with pytest.raises(
        web_playwright_backend._BrowserResourceBudgetExceeded,
        match="browser_dom_too_large",
    ):
        web_playwright_backend._materialize_bounded_page_projection(
            cast(web_playwright_backend._PageProtocol, page),
            browser_resource_budget=budget,
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


@pytest.mark.parametrize(
    ("preflight_text_exceeded", "expected_content_calls", "expected_evaluate_calls"),
    (
        (True, 0, 1),
        (False, 1, 2),
    ),
)
def test_materialize_bounded_page_projection_owns_text_too_large_reason(
    preflight_text_exceeded: bool,
    expected_content_calls: int,
    expected_evaluate_calls: int,
) -> None:
    """DOM 界内时 text 预检或实际超限都必须产生 typed text-too-large reason。

    Args:
        preflight_text_exceeded: 是否在 bounded text 预检阶段直接超限。
        expected_content_calls: 预期完整 HTML 读取次数。
        expected_evaluate_calls: 预期 page evaluate 总次数。

    Returns:
        无。

    Raises:
        AssertionError: text owner 未产生稳定 typed reason 或调用边界漂移时抛出。
    """

    page = _BudgetProbePage(
        metrics={
            "domChars": 5,
            "textChars": 11 if preflight_text_exceeded else 2,
            "domExceeded": False,
            "textExceeded": preflight_text_exceeded,
        },
        html="short",
        page_text="x" * 11,
    )

    with pytest.raises(web_playwright_backend._BrowserResourceBudgetExceeded) as exc_info:
        web_playwright_backend._materialize_bounded_page_projection(
            cast(web_playwright_backend._PageProtocol, page),
            browser_resource_budget=_browser_resource_budget(
                dom_chars=10,
                text_chars=10,
            ),
        )

    assert exc_info.value.reason == web_playwright_backend._BROWSER_TEXT_TOO_LARGE_REASON
    assert page.content_calls == expected_content_calls
    assert len(page.evaluate_calls) == expected_evaluate_calls


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
    budget = _browser_resource_budget(dom_chars=10, text_chars=10)
    with pytest.raises(
        web_playwright_backend._BrowserResourceBudgetExceeded,
        match="browser_dom_too_large",
    ):
        web_playwright_backend._materialize_bounded_page_projection(
            cast(web_playwright_backend._PageProtocol, dynamic_dom_page),
            browser_resource_budget=budget,
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
            browser_resource_budget=budget,
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
        browser_resource_budget=_browser_resource_budget(
            dom_chars=64,
            text_chars=64,
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


def test_playwright_worker_success_consumes_only_browser_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完整 browser worker 成功路径只消费 BrowserResourceBudget。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: worker 消费错误 owner 或成功语义漂移时抛出。
    """

    page = _SyntheticPlaywrightPage()
    context = _SyntheticPlaywrightContext(page)
    browser = _SyntheticPlaywrightBrowser(context)

    def get_browser(
        *,
        playwright_channel: str | None = None,
        headless: bool = True,
    ) -> web_playwright_backend._BrowserProtocol | None:
        """返回 synthetic Browser 并校验 channel/headless。

        Args:
            playwright_channel: browser channel。
            headless: 是否无头运行。

        Returns:
            synthetic Browser。

        Raises:
            AssertionError: channel/headless 不符合调用契约时抛出。
        """

        assert playwright_channel == "chrome"
        assert headless is True
        return cast(web_playwright_backend._BrowserProtocol, browser)

    monkeypatch.setattr(web_tools, "_get_playwright_browser", get_browser)
    monkeypatch.setattr(
        web_tools,
        "convert_html_to_llm_markdown",
        _convert_expected_browser_html,
    )

    result = web_tools._playwright_sync_worker(
        url="http://127.0.0.1:43119/report",
        timeout_seconds=5.0,
        playwright_channel="chrome",
        playwright_storage_state_path="/tmp/synthetic-state.json",
        egress_policy=WebEgressPolicy(
            allow_private_network=True,
            allow_custom_port=True,
        ),
        browser_resource_budget=_browser_resource_budget(
            warmup_body_bytes=64,
            dom_chars=512,
            text_chars=256,
        ),
    )

    assert result["ok"] is True
    assert result["content"] == "Revenue grew."
    assert context.close_calls == 1
    assert page.route_patterns == ["**/*"]
    assert [call[0] for call in page.goto_calls] == [
        "http://127.0.0.1:43119/",
        "http://127.0.0.1:43119/report",
    ]
    assert page.load_states == [("load", 2500), ("networkidle", 1500)]
    assert page.wait_timeouts == [1000]
    assert browser.context_kwargs is not None
    assert browser.context_kwargs["storage_state"] == "/tmp/synthetic-state.json"


def test_playwright_worker_browser_owner_controls_terminal_resource_paths() -> None:
    """Browser child owner 必须控制 non-HTML、DOM 与 Markdown 终态。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一终态绕过 Browser child owner 时抛出。
    """

    non_html_result = _run_synthetic_playwright_worker(
        _SyntheticPlaywrightPage(content_type="application/pdf"),
        browser_resource_budget=_browser_resource_budget(
            dom_chars=512,
            text_chars=256,
        ),
        convert_html=_reject_browser_html_conversion,
    )
    assert non_html_result["reason"] == "non_html_content_type"

    dom_overflow_page = _SyntheticPlaywrightPage()
    dom_overflow_page.metrics["domExceeded"] = True
    dom_result = _run_synthetic_playwright_worker(
        dom_overflow_page,
        browser_resource_budget=_browser_resource_budget(
            dom_chars=512,
            text_chars=256,
        ),
        convert_html=_reject_browser_html_conversion,
    )
    assert dom_result["reason"] == "browser_dom_too_large"

    markdown_result = _run_synthetic_playwright_worker(
        _SyntheticPlaywrightPage(),
        browser_resource_budget=_browser_resource_budget(
            dom_chars=512,
            text_chars=16,
        ),
        convert_html=_convert_oversized_browser_markdown,
    )
    assert markdown_result["reason"] == "browser_text_too_large"

    with pytest.raises(RuntimeError, match="页面加载超时"):
        _run_synthetic_playwright_worker(
            _SyntheticPlaywrightPage(goto_error=PlaywrightTimeoutError("synthetic timeout")),
            browser_resource_budget=_browser_resource_budget(),
            convert_html=_reject_browser_html_conversion,
        )
    with pytest.raises(RuntimeError, match="未返回 response"):
        _run_synthetic_playwright_worker(
            _SyntheticPlaywrightPage(return_response=False),
            browser_resource_budget=_browser_resource_budget(),
            convert_html=_reject_browser_html_conversion,
        )

    with pytest.raises(RuntimeError, match="Browser 单例不可用"):
        web_playwright_backend._playwright_sync_worker(
            url="http://127.0.0.1:43119/report",
            timeout_seconds=5.0,
            get_playwright_browser=_unavailable_browser,
            build_domain_home_url=web_tools._build_domain_home_url,
            normalize_url_for_http=web_tools._normalize_url_for_http,
            sanitize_response_headers=web_tools._sanitize_plain_response_headers,
            convert_html_to_markdown=_reject_browser_html_conversion,
            egress_policy=WebEgressPolicy(
                allow_private_network=True,
                allow_custom_port=True,
            ),
            browser_resource_budget=_browser_resource_budget(),
        )


@pytest.mark.parametrize(
    ("failure_code", "expected_error_code"),
    (
        ("browser_dom_too_large", "browser_dom_too_large"),
        ("browser_text_too_large", "browser_text_too_large"),
        ("browser_peer_proof_unavailable", "browser_peer_proof_unavailable"),
        ("browser_runtime_unavailable", None),
    ),
)
def test_playwright_budget_failure_projects_stable_tool_error(
    monkeypatch: pytest.MonkeyPatch,
    failure_code: str,
    expected_error_code: str | None,
) -> None:
    """浏览器失败必须按显式 Diagnostic owner 投影或返回无结果。

    Args:
        monkeypatch: pytest 属性替换夹具。
        failure_code: 当前 synthetic browser failure code。
        expected_error_code: 预期工具失败码；``None`` 表示返回无结果。

    Returns:
        无。

    Raises:
        AssertionError: browser failure 未按当前 Diagnostic owner 投影时抛出。
    """

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
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """返回确定性 browser failure。

        Args:
            url: 目标 URL。
            timeout_seconds: browser timeout。
            headers: 请求头。
            timeout_budget: 工具预算。
            deadline_monotonic: 工具 deadline。
            playwright_channel: browser channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: Web 出站策略。
            transport_policy: 当前 attempt 的 transport policy。
            browser_resource_budget: 浏览器资源预算。
            diagnostic_resource_budget: 诊断投影预算。
            cancellation_token: 取消令牌。

        Returns:
            确定性 browser failure payload。

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
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
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

    diagnostic_budget = _diagnostic_resource_budget(error_chars=5, events=2)
    if expected_error_code is None:
        result = web_tools._try_playwright_fallback(
            url="http://127.0.0.1/report",
            timeout_seconds=1.0,
            headers={},
            timeout_budget=None,
            deadline_monotonic=None,
            egress_policy=WebEgressPolicy(allow_private_network=True),
            browser_enabled=True,
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            browser_resource_budget=_DEFAULT_BROWSER_RESOURCE_BUDGET,
            diagnostic_resource_budget=diagnostic_budget,
        )
        assert result is None
        return

    with pytest.raises(web_tools.ToolBusinessError) as exc_info:
        web_tools._try_playwright_fallback(
            url="http://127.0.0.1/report",
            timeout_seconds=1.0,
            headers={},
            timeout_budget=None,
            deadline_monotonic=None,
            egress_policy=WebEgressPolicy(allow_private_network=True),
            browser_enabled=True,
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            browser_resource_budget=_DEFAULT_BROWSER_RESOURCE_BUDGET,
            diagnostic_resource_budget=diagnostic_budget,
        )
    assert exc_info.value.code == expected_error_code
    assert len(exc_info.value.message) <= diagnostic_budget.error_chars


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
    assert web_challenge_detection.BotChallengeEvidenceClass.STRONG_VENDOR_CONTENT in result.evidence_classes


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
    assert (
        web_challenge_detection.challenge_fallback_action(
            decision=two_text_signals.decision,
            browser_available=web_tools._browser_fallback_available(
                browser_enabled=True,
                transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            ),
        )
        is web_challenge_detection.ChallengeFallbackAction.TRY_BROWSER
    )
    assert (
        web_challenge_detection.challenge_fallback_action(
            decision=two_text_signals.decision,
            browser_available=False,
        )
        is web_challenge_detection.ChallengeFallbackAction.FAIL_BLOCKED
    )


@pytest.mark.parametrize("browser_enabled", (True, False))
def test_challenge_confirmed_http_500_uses_current_browser_capability(
    monkeypatch: pytest.MonkeyPatch,
    browser_enabled: bool,
) -> None:
    """confirmed challenge + HTTP 500 必须按当前 browser capability 收口。

    Args:
        monkeypatch: pytest 属性替换夹具。
        browser_enabled: 当前 typed browser capability。

    Returns:
        无。

    Raises:
        AssertionError: challenge fallback 未消费当前 browser capability 时抛出。
    """

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
        browser_enabled: bool,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
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
            browser_enabled: 当前配置是否允许 browser fallback。
            transport_policy: 当前 attempt transport policy。
            browser_resource_budget: 浏览器资源预算。
            diagnostic_resource_budget: 诊断投影预算。
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
            browser_enabled,
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
            cancellation_token,
        )
        fallback_calls.append(url)
        return {"ok": True, "content": "browser result"}

    monkeypatch.setattr(web_tools, "_try_playwright_fallback", fake_playwright_fallback)

    config = web_provider._parse_config(
        {
            "allow_private_network_url": True,
            "browser_enabled": browser_enabled,
        }
    )
    if browser_enabled:
        result = web_tools._fetch_web_page_business(
            url="http://127.0.0.1/report",
            config=config,
            timeout_budget=None,
            cancellation_token=cast(CancellationToken, _OpenCancellationToken()),
        )
        assert result["content"] == "browser result"
        assert fallback_calls == ["http://127.0.0.1/report"]
        return

    with pytest.raises(web_tools.ToolBusinessError) as exc_info:
        web_tools._fetch_web_page_business(
            url="http://127.0.0.1/report",
            config=config,
            timeout_budget=None,
            cancellation_token=cast(CancellationToken, _OpenCancellationToken()),
        )
    assert exc_info.value.code == "blocked"
    assert fallback_calls == []


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
            config=web_provider._parse_config({"provider": "duckduckgo"}),
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

    def fake_send(
        *,
        egress_policy: WebEgressPolicy,
        url: str,
        method: str,
        timeout: float,
        headers: Mapping[str, str],
        stream: bool,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        request_params: Mapping[str, str] | None,
        request_json: Mapping[str, JsonValue] | None,
    ) -> web_http_session.AuthorizedResponseLease:
        """返回确定性 Tavily JSON response。

        Args:
            egress_policy: 当前 endpoint egress policy。
            url: provider URL。
            method: HTTP 方法。
            timeout: 请求 timeout。
            headers: provider headers。
            stream: 是否流式获取 response。
            transport_policy: 当前 attempt transport policy。
            request_params: 可选 query 参数。
            request_json: 可选 JSON body。

        Returns:
            确定性 response lease。

        Raises:
            无。
        """

        del timeout
        assert egress_policy.allows_private_network is False
        assert egress_policy.allows_custom_port is False
        assert url == "https://api.tavily.com/search"
        assert method == "POST"
        assert stream is True
        assert transport_policy is _PROXY_DENIED_TRANSPORT_POLICY
        assert request_params is None
        assert request_json is not None
        assert headers["Accept-Encoding"] == "gzip, deflate"
        captured_payloads.append(dict(request_json))
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
        return _plain_response_lease(response)

    monkeypatch.setattr(
        web_search_providers,
        "_send_authorized_plain_request",
        fake_send,
    )
    rows = web_search_providers._search_with_tavily(
        query="revenue",
        domains=["example.com"],
        recency_days=7,
        max_results=3,
        timeout_seconds=1.0,
        egress_policy=_public_test_policy(),
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        resolve_timeout_budget=web_search_providers._default_resolve_timeout_budget,
        http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
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

    def fake_send(
        *,
        egress_policy: WebEgressPolicy,
        url: str,
        method: str,
        timeout: float,
        headers: Mapping[str, str],
        stream: bool,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        request_params: Mapping[str, str] | None,
        request_json: Mapping[str, JsonValue] | None,
    ) -> web_http_session.AuthorizedResponseLease:
        """返回确定性 Serper JSON response。

        Args:
            egress_policy: 当前 endpoint egress policy。
            url: provider URL。
            method: HTTP 方法。
            timeout: 请求 timeout。
            headers: provider headers。
            stream: 是否流式获取 response。
            transport_policy: 当前 attempt transport policy。
            request_params: 可选 query 参数。
            request_json: 可选 JSON body。

        Returns:
            确定性 response lease。

        Raises:
            无。
        """

        del timeout
        assert egress_policy.allows_private_network is False
        assert egress_policy.allows_custom_port is False
        assert url == "https://google.serper.dev/search"
        assert method == "POST"
        assert stream is True
        assert transport_policy is _PROXY_DENIED_TRANSPORT_POLICY
        assert request_params is None
        assert request_json is not None
        assert headers["Accept-Encoding"] == "gzip, deflate"
        captured_payloads.append(dict(request_json))
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
        return _plain_response_lease(response)

    monkeypatch.setattr(
        web_search_providers,
        "_send_authorized_plain_request",
        fake_send,
    )
    rows = web_search_providers._search_with_serper(
        query="revenue",
        domains=["example.com"],
        recency_days=7,
        max_results=3,
        timeout_seconds=1.0,
        egress_policy=_public_test_policy(),
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        resolve_timeout_budget=web_search_providers._default_resolve_timeout_budget,
        http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
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

    def fake_send(
        *,
        egress_policy: WebEgressPolicy,
        url: str,
        method: str,
        timeout: float,
        headers: Mapping[str, str],
        stream: bool,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        request_params: Mapping[str, str] | None,
        request_json: Mapping[str, JsonValue] | None,
    ) -> web_http_session.AuthorizedResponseLease:
        """返回带关闭计数的流式 DuckDuckGo response。

        Args:
            egress_policy: 当前 endpoint egress policy。
            url: provider URL。
            method: HTTP 方法。
            timeout: 请求 timeout。
            headers: provider headers。
            stream: 是否流式获取 response。
            transport_policy: 当前 attempt transport policy。
            request_params: query 参数。
            request_json: 可选 JSON body。

        Returns:
            可计数关闭的 response lease。

        Raises:
            无。
        """

        del timeout
        assert egress_policy.allows_private_network is False
        assert egress_policy.allows_custom_port is False
        assert url == "https://duckduckgo.com/html/"
        assert method == "GET"
        assert request_params == {"q": "revenue"}
        assert request_json is None
        assert headers["Accept-Encoding"] == "gzip, deflate"
        assert transport_policy is _PROXY_DENIED_TRANSPORT_POLICY
        assert stream is True
        return _plain_response_lease(response)

    monkeypatch.setattr(
        web_search_providers,
        "_send_authorized_plain_request",
        fake_send,
    )
    budget = _http_resource_budget(
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
                egress_policy=_public_test_policy(),
                transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
                normalize_whitespace=web_tools._normalize_whitespace,
                resolve_timeout_budget=web_search_providers._default_resolve_timeout_budget,
                http_resource_budget=budget,
            )
    else:
        assert (
            web_search_providers._search_with_duckduckgo(
                query="revenue",
                domains=[],
                max_results=3,
                timeout_seconds=1.0,
                egress_policy=_public_test_policy(),
                transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
                normalize_whitespace=web_tools._normalize_whitespace,
                resolve_timeout_budget=web_search_providers._default_resolve_timeout_budget,
                http_resource_budget=budget,
            )
            == []
        )

    assert response.close_count == 1


def test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DuckDuckGo plain sender 必须先授权、禁 redirect 并保留 challenge 失败。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: egress、redirect 或 challenge 语义漂移时抛出。
    """

    resolver_calls: list[tuple[str, int]] = []
    send_redirect_flags: list[bool] = []
    detector_calls: list[str] = []
    challenge_body = b"<html>asset from challenges.cloudflare.com</html>"
    original_detector = web_challenge_detection.detect_bot_challenge

    def resolve_provider(hostname: str, port: int) -> tuple[str, ...]:
        """记录 provider endpoint 的唯一 DNS owner 调用。

        Args:
            hostname: provider hostname。
            port: provider 端口。

        Returns:
            确定性公网地址。

        Raises:
            无。
        """

        resolver_calls.append((hostname, port))
        return ("93.184.216.34",)

    def return_challenge_response(
        session: requests.Session,
        request: requests.PreparedRequest,
        *,
        timeout: float,
        allow_redirects: bool,
        proxies: dict[str, str],
        stream: bool,
        verify: bool | str,
        cert: str | tuple[str, str] | None,
    ) -> requests.Response:
        """返回确定性 challenge HTML 并记录 transport 调用事实。

        Args:
            session: attempt-local Session。
            request: prepared provider request。
            timeout: 请求 timeout。
            allow_redirects: 自动 redirect 开关。
            proxies: merged proxy 映射。
            stream: stream 开关。
            verify: TLS verify 设置。
            cert: client certificate 设置。

        Returns:
            确定性 challenge response。

        Raises:
            AssertionError: provider transport 语义漂移时抛出。
        """

        del timeout, verify, cert
        assert session.trust_env is False
        assert request.url == "https://duckduckgo.com/html/?q=revenue"
        assert proxies == {}
        assert stream is True
        send_redirect_flags.append(allow_redirects)
        response = _counting_response(
            url=request.url,
            status_code=200,
            body=challenge_body,
            headers={"Content-Type": "text/html"},
        )
        response.request = request
        return response

    def record_challenge_detection(
        *,
        response: requests.Response | None,
        response_headers: Mapping[str, str] | None = None,
        http_status: int | None = None,
        content_text: str,
    ) -> web_challenge_detection.BotChallengeDetectionResult:
        """记录 provider 复用共享 challenge detector 的输入。

        Args:
            response: provider response。
            response_headers: 可选独立响应头。
            http_status: 可选独立状态码。
            content_text: 待检测 HTML。

        Returns:
            共享 detector 的原始结果。

        Raises:
            无。
        """

        detector_calls.append(content_text)
        return original_detector(
            response=response,
            response_headers=response_headers,
            http_status=http_status,
            content_text=content_text,
        )

    monkeypatch.setattr(requests.Session, "send", return_challenge_response)
    monkeypatch.setattr(
        web_search_providers,
        "detect_bot_challenge",
        record_challenge_detection,
    )
    with pytest.raises(web_search_providers.WebSearchProviderResponseError) as exc_info:
        web_search_providers._search_with_duckduckgo(
            query="revenue",
            domains=[],
            max_results=3,
            timeout_seconds=1.0,
            egress_policy=WebEgressPolicy(resolver=resolve_provider),
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            normalize_whitespace=web_tools._normalize_whitespace,
            resolve_timeout_budget=web_search_providers._default_resolve_timeout_budget,
            http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
        )

    assert resolver_calls == [("duckduckgo.com", 443)]
    assert send_redirect_flags == [False]
    assert detector_calls == [challenge_body.decode("utf-8")]
    assert exc_info.value.reason == "challenge_response"


@pytest.mark.parametrize(
    "transport_policy",
    (
        _PROXY_ALLOWED_TRANSPORT_POLICY,
        _PROXY_DENIED_TRANSPORT_POLICY,
        _PEER_PROOF_TRANSPORT_POLICY,
    ),
)
def test_search_provider_forwards_proxy_and_peer_policy_to_plain_sender(
    monkeypatch: pytest.MonkeyPatch,
    transport_policy: web_http_session.WebHttpTransportPolicy,
) -> None:
    """search provider 必须把每个 typed transport policy 交给共享 plain sender。

    Args:
        monkeypatch: pytest 属性替换夹具。
        transport_policy: 当前参数化的 typed transport policy。

    Returns:
        无。

    Raises:
        AssertionError: provider 未原样传播 transport policy 时抛出。
    """

    observed_policies: list[web_http_session.WebHttpTransportPolicy] = []
    response = _counting_response(
        url="https://duckduckgo.com/html/?q=revenue",
        status_code=200,
        body=b'<div class="no-results">No results.</div>',
    )

    def record_plain_sender(
        *,
        egress_policy: WebEgressPolicy,
        url: str,
        method: str,
        timeout: float,
        headers: Mapping[str, str],
        stream: bool,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        request_params: Mapping[str, str] | None,
        request_json: Mapping[str, JsonValue] | None,
    ) -> web_http_session.AuthorizedResponseLease:
        """记录 provider 交付的 transport policy 并返回空结果响应。

        Args:
            egress_policy: provider endpoint 出站策略。
            url: provider URL。
            method: HTTP 方法。
            timeout: 请求 timeout。
            headers: provider headers。
            stream: stream 开关。
            transport_policy: 当前 attempt transport policy。
            request_params: query 参数。
            request_json: 可选 JSON body。

        Returns:
            确定性空结果 response lease。

        Raises:
            AssertionError: provider 请求语义漂移时抛出。
        """

        del timeout
        assert egress_policy.allows_private_network is False
        assert url == "https://duckduckgo.com/html/"
        assert method == "GET"
        assert headers["Accept-Encoding"] == "gzip, deflate"
        assert stream is True
        assert request_params == {"q": "revenue"}
        assert request_json is None
        observed_policies.append(transport_policy)
        return _plain_response_lease(response)

    monkeypatch.setattr(
        web_search_providers,
        "_send_authorized_plain_request",
        record_plain_sender,
    )
    rows = web_search_providers._search_with_duckduckgo(
        query="revenue",
        domains=[],
        max_results=3,
        timeout_seconds=1.0,
        egress_policy=_public_test_policy(),
        transport_policy=transport_policy,
        normalize_whitespace=web_tools._normalize_whitespace,
        resolve_timeout_budget=web_search_providers._default_resolve_timeout_budget,
        http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
    )

    assert rows == []
    assert observed_policies == [transport_policy]


def test_search_proxy_peer_incompatibility_is_not_provider_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """shared proxy/proof 冲突不得被 search 降级为 provider unavailable。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: typed 冲突被 provider fallback 吞掉时抛出。
    """

    sender_calls: list[str] = []

    def fail_plain_sender(
        *,
        egress_policy: WebEgressPolicy,
        url: str,
        method: str,
        timeout: float,
        headers: Mapping[str, str],
        stream: bool,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        request_params: Mapping[str, str] | None,
        request_json: Mapping[str, JsonValue] | None,
    ) -> web_http_session.AuthorizedResponseLease:
        """模拟共享 sender 产生 typed proxy/proof 冲突。

        Args:
            egress_policy: provider endpoint 出站策略。
            url: provider URL。
            method: HTTP 方法。
            timeout: 请求 timeout。
            headers: provider headers。
            stream: stream 开关。
            transport_policy: 当前 attempt transport policy。
            request_params: query 参数。
            request_json: 可选 JSON body。

        Returns:
            不返回。

        Raises:
            ProxyPeerProofIncompatibleError: 始终抛出 typed 冲突。
        """

        del (
            egress_policy,
            method,
            timeout,
            headers,
            stream,
            transport_policy,
            request_params,
            request_json,
        )
        sender_calls.append(url)
        raise web_http_session.ProxyPeerProofIncompatibleError()

    monkeypatch.setattr(
        web_search_providers,
        "_send_authorized_plain_request",
        fail_plain_sender,
    )
    with pytest.raises(web_http_session.ProxyPeerProofIncompatibleError):
        web_search_providers.search_public_web(
            query="revenue",
            domains=None,
            recency_days=None,
            max_results=3,
            max_search_results=10,
            provider="duckduckgo",
            request_timeout_seconds=1.0,
            timeout_budget=None,
            deadline_monotonic=None,
            egress_policy=_public_test_policy(),
            transport_policy=_PEER_PROOF_TRANSPORT_POLICY,
            normalize_whitespace=web_tools._normalize_whitespace,
            resolve_timeout_budget=web_search_providers._default_resolve_timeout_budget,
            http_resource_budget=_DEFAULT_HTTP_RESOURCE_BUDGET,
        )

    assert sender_calls == ["https://duckduckgo.com/html/"]


def test_search_proxy_peer_incompatibility_projects_safe_tool_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search tool 必须把 typed proxy/proof 冲突投影为安全稳定失败。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: 工具错误码或 LLM-facing 文本泄漏内部语义时抛出。
    """

    def fail_search_business(
        *,
        query: str,
        domains: list[str] | None,
        recency_days: int | None,
        max_results: int,
        config: web_tools.WebToolsConfig,
        timeout_budget: float | None,
        cancellation_token: CancellationToken,
    ) -> web_tools.SearchWebOutput:
        """模拟 search business 透出共享 transport typed 冲突。

        Args:
            query: 检索词。
            domains: 可选域名过滤。
            recency_days: 可选最近天数。
            max_results: 最大结果数。
            config: typed Web 配置。
            timeout_budget: 工具 timeout 预算。
            cancellation_token: 取消令牌。

        Returns:
            不返回。

        Raises:
            ProxyPeerProofIncompatibleError: 始终抛出 typed 冲突。
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
        raise web_http_session.ProxyPeerProofIncompatibleError()

    monkeypatch.setattr(web_tools, "_search_web_business", fail_search_business)
    outcome = asyncio.run(
        web_tools._call_search_web(
            call=_call("search_web", {"query": "revenue"}),
            context=_context(timeout_seconds=1.0),
            config=web_provider._parse_config({"provider": "duckduckgo"}),
            provider_lock=asyncio.Lock(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "proxy_peer_proof_incompatible"
    assert outcome.result.message == "当前连接验证策略与已启用的网络代理不兼容。"
    llm_text = f"{outcome.result.message} {outcome.result.hint}"
    assert "credential" not in llm_text
    assert "proxy.invalid" not in llm_text


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
            config=web_provider._parse_config({"provider": "duckduckgo"}),
            provider_lock=asyncio.Lock(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "response_body_too_large"
    assert outcome.result.hint == (web_tool_projection_text.WEB_SEARCH_RESPONSE_BODY_TOO_LARGE_HINT)


@pytest.mark.parametrize(
    ("resource_type", "url", "expected_action"),
    (
        ("image", "https://example.com/image.png", _ROUTE_ABORT_ACTION),
        ("font", "https://example.com/font.woff2", _ROUTE_ABORT_ACTION),
        ("media", "https://example.com/video.mp4", _ROUTE_ABORT_ACTION),
        ("document", "http://127.0.0.1/internal", _ROUTE_ABORT_ACTION),
        ("document", "https://example.com/report", _ROUTE_CONTINUE_ACTION),
    ),
)
def test_route_handler_owner_selects_resource_policy_or_continue_action(
    resource_type: str,
    url: str,
    expected_action: str,
) -> None:
    """Browser route owner 必须覆盖资源 abort、policy deny 与 allowed continue。

    Args:
        resource_type: Playwright request 资源类型。
        url: Playwright request URL。
        expected_action: owner 应选择的唯一 route action。

    Returns:
        无。

    Raises:
        AssertionError: route owner 选择的 action 不符合 contract 时抛出。
    """

    route = _RecordingPlaywrightRoute(
        resource_type=resource_type,
        url=url,
    )

    web_playwright_backend._route_handler_abort_resources(
        cast(web_playwright_backend._RouteProtocol, route),
        egress_policy=_public_test_policy(),
    )

    assert route.actions == [expected_action]


def test_playwright_public_direct_runs_without_private_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公网 browser fallback 与 private-network permission 必须双向解耦。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: 公网 browser 被 private permission 错误阻断时抛出。
    """

    process_proxy_flags: list[bool] = []

    def run_public_process(
        *,
        playwright_sync_worker: web_playwright_backend._PlaywrightWorkerProtocol,
        worker_kwargs: web_playwright_backend._WorkerKwargs,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        allow_environment_proxy: bool,
        total_timeout: float,
        cancellation_token: CancellationToken | None,
    ) -> web_playwright_backend.WebPayload:
        """记录公网 worker process 已启动并返回确定性成功事实。

        Args:
            playwright_sync_worker: 当前 browser worker。
            worker_kwargs: browser worker 的 typed 参数。
            diagnostic_resource_budget: 独立诊断预算。
            allow_environment_proxy: 是否允许 worker 沿用 proxy 环境。
            total_timeout: process 总 timeout。
            cancellation_token: 可选取消令牌。

        Returns:
            确定性公网成功 payload。

        Raises:
            AssertionError: private permission 或预算 owner 漂移时抛出。
        """

        del playwright_sync_worker, total_timeout, cancellation_token
        worker_policy = worker_kwargs["egress_policy"]
        assert worker_policy.allows_private_network is False
        assert worker_policy.allows_custom_port is False
        assert diagnostic_resource_budget is _DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET
        process_proxy_flags.append(allow_environment_proxy)
        return {
            "ok": True,
            "content": "Revenue grew.",
            "http_status": 200,
            "response_headers": {"content-type": "text/html"},
        }

    monkeypatch.setattr(
        web_playwright_backend,
        "_is_picklable_worker",
        _accept_picklable_playwright_worker,
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_run_playwright_worker_process",
        run_public_process,
    )

    result = web_playwright_backend._fetch_and_convert_with_playwright(
        url="https://example.com/report",
        timeout_seconds=1.0,
        egress_policy=_public_test_policy(),
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        browser_resource_budget=_DEFAULT_BROWSER_RESOURCE_BUDGET,
        diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
        resolve_timeout_budget=web_tools._resolve_timeout_budget,
        playwright_sync_worker=_SyntheticProcessPlaywrightWorker(),
        detect_bot_challenge=web_challenge_detection.detect_bot_challenge,
    )

    assert result["ok"] is True
    assert process_proxy_flags == [False]


def test_browser_disabled_with_private_permission_does_not_start_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """private permission=true 不得反向启用已关闭的 browser capability。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: browser-disabled 路径仍启动 backend 时抛出。
    """

    backend_calls: list[str] = []

    def record_backend_call(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        egress_policy: WebEgressPolicy,
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_playwright_backend.WebPayload:
        """记录任何不应发生的 browser backend 调用。

        Args:
            url: 目标 URL。
            timeout_seconds: browser timeout。
            headers: 请求头。
            timeout_budget: 工具预算。
            deadline_monotonic: 工具 deadline。
            playwright_channel: browser channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: 出站策略。
            transport_policy: 当前 attempt transport policy。
            browser_resource_budget: browser budget。
            diagnostic_resource_budget: diagnostic budget。
            cancellation_token: 可选取消令牌。

        Returns:
            确定性成功 payload，用于暴露错误启动。

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
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
            cancellation_token,
        )
        backend_calls.append(url)
        return {"ok": True, "content": "unexpected"}

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        record_backend_call,
    )
    result = web_tools._try_playwright_fallback(
        url="http://127.0.0.1/report",
        timeout_seconds=1.0,
        headers={},
        timeout_budget=None,
        deadline_monotonic=None,
        egress_policy=WebEgressPolicy(allow_private_network=True),
        browser_enabled=False,
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        browser_resource_budget=_DEFAULT_BROWSER_RESOURCE_BUDGET,
        diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
    )

    assert result is None
    assert backend_calls == []


def test_browser_peer_proof_fails_before_process_with_safe_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 browser fallback 遇到 proof=true 必须在 process 前 typed fail。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: proof-incompatible browser 路径启动 process 或投影泄漏时抛出。
    """

    process_calls: list[str] = []

    def record_process_call(
        *,
        playwright_sync_worker: web_playwright_backend._PlaywrightWorkerProtocol,
        worker_kwargs: web_playwright_backend._WorkerKwargs,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        allow_environment_proxy: bool,
        total_timeout: float,
        cancellation_token: CancellationToken | None,
    ) -> web_playwright_backend.WebPayload:
        """记录任何不应发生的 proof-incompatible process 启动。

        Args:
            playwright_sync_worker: browser worker。
            worker_kwargs: browser worker 参数。
            diagnostic_resource_budget: diagnostic budget。
            allow_environment_proxy: proxy 环境继承开关。
            total_timeout: process 总 timeout。
            cancellation_token: 可选取消令牌。

        Returns:
            确定性成功 payload，用于暴露错误启动。

        Raises:
            无。
        """

        del (
            playwright_sync_worker,
            worker_kwargs,
            diagnostic_resource_budget,
            allow_environment_proxy,
            total_timeout,
            cancellation_token,
        )
        process_calls.append("unexpected")
        return {"ok": True, "content": "unexpected"}

    monkeypatch.setattr(
        web_playwright_backend,
        "_run_playwright_worker_process",
        record_process_call,
    )
    backend_result = web_playwright_backend._fetch_and_convert_with_playwright(
        url="https://example.com/report",
        timeout_seconds=1.0,
        egress_policy=_public_test_policy(),
        transport_policy=_PEER_PROOF_TRANSPORT_POLICY,
        browser_resource_budget=_DEFAULT_BROWSER_RESOURCE_BUDGET,
        diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
        resolve_timeout_budget=web_tools._resolve_timeout_budget,
        playwright_sync_worker=_SyntheticProcessPlaywrightWorker(),
        detect_bot_challenge=web_challenge_detection.detect_bot_challenge,
    )
    assert backend_result == {
        "ok": False,
        "availability": "unprocessable",
        "reason": "browser_peer_proof_unavailable",
    }

    with pytest.raises(web_tools.ToolBusinessError) as exc_info:
        web_tools._try_playwright_fallback(
            url="https://example.com/report",
            timeout_seconds=1.0,
            headers={},
            timeout_budget=None,
            deadline_monotonic=None,
            egress_policy=_public_test_policy(),
            browser_enabled=True,
            transport_policy=_PEER_PROOF_TRANSPORT_POLICY,
            browser_resource_budget=_DEFAULT_BROWSER_RESOURCE_BUDGET,
            diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
        )

    assert exc_info.value.code == "browser_peer_proof_unavailable"
    assert exc_info.value.message == "当前浏览器访问无法验证目标连接。"
    llm_text = f"{exc_info.value.message} {exc_info.value.hint}"
    assert "Playwright" not in llm_text
    assert "socket" not in llm_text
    assert "peer" not in llm_text
    assert "proof" not in llm_text
    assert process_calls == []


def test_playwright_process_wrapper_keeps_diagnostic_budget_out_of_worker_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """browser process wrapper 必须独立持有 Diagnostic budget 并稳定投影失败。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: Diagnostic budget 进入 worker kwargs 或投影漂移时抛出。
    """

    browser_budget = _browser_resource_budget()
    diagnostic_budget = _diagnostic_resource_budget(error_chars=64, events=4)
    observed_worker_kwargs: list[web_playwright_backend._WorkerKwargs] = []
    observed_diagnostic_budgets: list[DiagnosticResourceBudget] = []
    queued_results: list[web_playwright_backend.WebPayload | BaseException] = [
        {
            "ok": True,
            "content": "Revenue grew.",
            "http_status": 200,
            "response_headers": {"content-type": "text/html"},
        },
        TimeoutError("synthetic timeout"),
        RuntimeError("synthetic worker failure"),
    ]

    def fake_run_process(
        *,
        playwright_sync_worker: web_playwright_backend._PlaywrightWorkerProtocol,
        worker_kwargs: web_playwright_backend._WorkerKwargs,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        allow_environment_proxy: bool,
        total_timeout: float,
        cancellation_token: CancellationToken | None,
    ) -> web_playwright_backend.WebPayload:
        """记录两个独立 owner inputs 并按队列返回或抛错。

        Args:
            playwright_sync_worker: browser worker callable。
            worker_kwargs: 只含 Browser budget 的 worker payload。
            diagnostic_resource_budget: process/failure diagnostic budget。
            allow_environment_proxy: 是否允许 worker 沿用 proxy 环境。
            total_timeout: process 总 timeout。
            cancellation_token: 当前取消令牌。

        Returns:
            队列中的成功 payload。

        Raises:
            BaseException: 队列中的测试异常原样抛出。
        """

        del playwright_sync_worker, allow_environment_proxy, cancellation_token
        assert total_timeout > 1.0
        observed_worker_kwargs.append(worker_kwargs)
        observed_diagnostic_budgets.append(diagnostic_resource_budget)
        queued = queued_results.pop(0)
        if isinstance(queued, BaseException):
            raise queued
        return queued

    monkeypatch.setattr(
        web_playwright_backend,
        "_is_picklable_worker",
        _accept_picklable_playwright_worker,
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_run_playwright_worker_process",
        fake_run_process,
    )

    outcomes = [
        web_tools._fetch_and_convert_with_playwright(
            url="http://127.0.0.1/report",
            timeout_seconds=2.0,
            egress_policy=WebEgressPolicy(allow_private_network=True),
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            browser_resource_budget=browser_budget,
            diagnostic_resource_budget=diagnostic_budget,
        )
        for _ in range(3)
    ]

    assert outcomes[0]["ok"] is True
    assert outcomes[1] == {
        "ok": False,
        "availability": "timeout",
        "reason": "playwright_timeout",
    }
    assert outcomes[2] == {
        "ok": False,
        "availability": "unprocessable",
        "reason": "playwright_error",
    }
    assert observed_diagnostic_budgets == [diagnostic_budget] * 3
    assert all(kwargs["browser_resource_budget"] is browser_budget for kwargs in observed_worker_kwargs)
    assert all("diagnostic_resource_budget" not in kwargs for kwargs in observed_worker_kwargs)


def test_playwright_wrapper_retains_timeout_and_challenge_with_split_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browser/Diagnostic 拆分后必须保留 timeout 与 confirmed challenge 终态。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: timeout 或 challenge 终态在 owner 拆分后漂移时抛出。
    """

    browser_budget = _browser_resource_budget()
    diagnostic_budget = _diagnostic_resource_budget(error_chars=64, events=4)

    timeout_result = web_playwright_backend._fetch_and_convert_with_playwright(
        url="http://127.0.0.1/report",
        timeout_seconds=1.0,
        egress_policy=WebEgressPolicy(allow_private_network=True),
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        browser_resource_budget=browser_budget,
        diagnostic_resource_budget=diagnostic_budget,
        resolve_timeout_budget=_exhaust_browser_timeout,
        playwright_sync_worker=_BlockedPlaywrightWorker(
            blocked_url="http://127.0.0.1/private",
            blocked_stage="playwright_goto",
        ),
        detect_bot_challenge=web_challenge_detection.detect_bot_challenge,
    )
    assert timeout_result["reason"] == "playwright_timeout"

    def challenge_process_result(
        *,
        playwright_sync_worker: web_playwright_backend._PlaywrightWorkerProtocol,
        worker_kwargs: web_playwright_backend._WorkerKwargs,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        allow_environment_proxy: bool,
        total_timeout: float,
        cancellation_token: CancellationToken | None,
    ) -> web_playwright_backend.WebPayload:
        """校验拆分 owner 后返回 confirmed challenge 内容。

        Args:
            playwright_sync_worker: 当前 typed browser worker。
            worker_kwargs: 只含 Browser budget 的 worker payload。
            diagnostic_resource_budget: 独立 Diagnostic child budget。
            allow_environment_proxy: 是否允许 worker 沿用 proxy 环境。
            total_timeout: process 总 timeout。
            cancellation_token: 可选取消令牌。

        Returns:
            含稳定 challenge signal 的成功 payload。

        Raises:
            AssertionError: 两个 child owner 未独立传入时抛出。
        """

        del playwright_sync_worker, total_timeout, cancellation_token
        assert worker_kwargs["browser_resource_budget"] is browser_budget
        assert diagnostic_resource_budget is diagnostic_budget
        assert allow_environment_proxy is False
        return {
            "ok": True,
            "content": "asset from challenges.cloudflare.com",
            "http_status": 200,
            "response_headers": {"content-type": "text/html"},
        }

    monkeypatch.setattr(
        web_playwright_backend,
        "_is_picklable_worker",
        _accept_picklable_playwright_worker,
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_run_playwright_worker_process",
        challenge_process_result,
    )
    challenge_result = web_playwright_backend._fetch_and_convert_with_playwright(
        url="http://127.0.0.1/report",
        timeout_seconds=1.0,
        egress_policy=WebEgressPolicy(allow_private_network=True),
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        browser_resource_budget=browser_budget,
        diagnostic_resource_budget=diagnostic_budget,
        resolve_timeout_budget=web_tools._resolve_timeout_budget,
        playwright_sync_worker=_BlockedPlaywrightWorker(
            blocked_url="http://127.0.0.1/private",
            blocked_stage="playwright_goto",
        ),
        detect_bot_challenge=web_challenge_detection.detect_bot_challenge,
    )
    assert challenge_result["reason"] == "bot_challenge"
    assert challenge_result["availability"] == "blocked"


def test_playwright_process_entry_projects_separate_diagnostic_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """process entry 必须用独立 Diagnostic budget 投影成功与两类失败。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: success/safety/failure 未由当前 Diagnostic owner 投影时抛出。
    """

    monkeypatch.setattr(
        web_playwright_backend,
        "enter_new_process_session_if_supported",
        _skip_new_process_session,
    )
    worker_kwargs: web_playwright_backend._WorkerKwargs = {
        "url": "https://example.com/report",
        "timeout_seconds": 1.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": "",
        "egress_policy": _public_test_policy(),
        "browser_resource_budget": _DEFAULT_BROWSER_RESOURCE_BUDGET,
    }
    payloads: list[web_playwright_backend.WebPayload] = []
    for worker in (
        _process_entry_success_worker,
        _process_entry_blocked_worker,
        _process_entry_failed_worker,
    ):
        raw_queue = multiprocessing.get_context("spawn").Queue(maxsize=1)
        result_queue = cast(web_playwright_backend._ResultQueueProtocol, raw_queue)
        web_playwright_backend._playwright_process_entry(
            result_queue,
            worker,
            worker_kwargs,
            _diagnostic_resource_budget(error_chars=32, events=4),
            False,
        )
        payloads.append(result_queue.get(timeout=1.0))
        result_queue.close()
        result_queue.join_thread()

    assert payloads[0] == {"kind": "result", "payload": {"ok": True, "content": "success"}}
    assert payloads[1]["blocked_by_safety_policy"] is True
    assert payloads[1]["blocked_url"] == "http://127.0.0.1/private"
    assert payloads[2]["error_type"] == "RuntimeError"
    assert len(str(payloads[2]["message"])) <= 32


def test_playwright_process_entry_controls_proxy_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """browser worker 必须按 transport policy 沿用或清理标准 proxy 环境。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: worker 可见 proxy 环境与 transport policy 不一致时抛出。
    """

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setattr(
        web_playwright_backend,
        "enter_new_process_session_if_supported",
        _skip_new_process_session,
    )
    worker_kwargs: web_playwright_backend._WorkerKwargs = {
        "url": "https://example.com/report",
        "timeout_seconds": 1.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": "",
        "egress_policy": _public_test_policy(),
        "browser_resource_budget": _DEFAULT_BROWSER_RESOURCE_BUDGET,
    }
    observed_payloads: list[web_playwright_backend.WebPayload] = []
    for allow_environment_proxy in (True, False):
        raw_queue = multiprocessing.get_context("spawn").Queue(maxsize=1)
        result_queue = cast(web_playwright_backend._ResultQueueProtocol, raw_queue)
        web_playwright_backend._playwright_process_entry(
            result_queue,
            _process_entry_proxy_environment_worker,
            worker_kwargs,
            _DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
            allow_environment_proxy,
        )
        envelope = result_queue.get(timeout=1.0)
        observed_payloads.append(cast(web_playwright_backend.WebPayload, envelope["payload"]))
        result_queue.close()
        result_queue.join_thread()

    enabled_names = cast(list[str], observed_payloads[0]["visible_proxy_environment"])
    disabled_names = cast(list[str], observed_payloads[1]["visible_proxy_environment"])
    assert "HTTPS_PROXY" in enabled_names
    assert disabled_names == []


def test_run_playwright_worker_process_cancellation_terminates_and_cleans_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process owner 收到取消后必须 terminate、抛 CancelledError 并清理 queue。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: 取消、终止或 finally cleanup 契约漂移时抛出。
    """

    result_queue = _FakePlaywrightResultQueue()
    process = _FakePlaywrightProcess(alive_after_start=True)
    context = _FakePlaywrightMultiprocessingContext(
        result_queue=result_queue,
        process=process,
    )
    context_factory = _FakePlaywrightContextFactory(context)
    terminator = _RecordingPlaywrightProcessTerminator()
    cancellation_token = _ManualCancellationToken()
    cancellation_token.cancel("controller cancellation")
    monkeypatch.setattr(
        web_playwright_backend.multiprocessing,
        "get_context",
        context_factory,
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_terminate_playwright_process",
        terminator,
    )

    with pytest.raises(web_playwright_backend.CancelledError) as exc_info:
        web_playwright_backend._run_playwright_worker_process(
            playwright_sync_worker=_SyntheticProcessPlaywrightWorker(),
            worker_kwargs=_playwright_worker_process_kwargs(),
            diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
            allow_environment_proxy=False,
            total_timeout=5.0,
            cancellation_token=cancellation_token,
        )

    assert str(exc_info.value) == "controller cancellation"
    assert context_factory.methods == ["spawn"]
    assert context.queue_maxsizes == [1]
    assert context.process_target is web_playwright_backend._playwright_process_entry
    assert process.started is True
    assert process.daemon is True
    assert terminator.processes == [process]
    assert result_queue.close_calls == 1
    assert result_queue.join_thread_calls == 1


def test_run_playwright_worker_process_no_result_exit_cleans_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker 无结果退出后必须抛稳定错误并执行 finally queue cleanup。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: result-drain fencing 或 finally cleanup 契约漂移时抛出。
    """

    result_queue = _FakePlaywrightResultQueue()
    process = _FakePlaywrightProcess(alive_after_start=False)
    context = _FakePlaywrightMultiprocessingContext(
        result_queue=result_queue,
        process=process,
    )
    context_factory = _FakePlaywrightContextFactory(context)
    terminator = _RecordingPlaywrightProcessTerminator()
    clock = _ScriptedMonotonicClock((0.0, 0.0, 0.0, 0.5))
    monkeypatch.setattr(
        web_playwright_backend.multiprocessing,
        "get_context",
        context_factory,
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_terminate_playwright_process",
        terminator,
    )
    monkeypatch.setattr(web_playwright_backend.time, "monotonic", clock)

    with pytest.raises(RuntimeError, match="playwright worker exited without result"):
        web_playwright_backend._run_playwright_worker_process(
            playwright_sync_worker=_SyntheticProcessPlaywrightWorker(),
            worker_kwargs=_playwright_worker_process_kwargs(),
            diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
            allow_environment_proxy=False,
            total_timeout=5.0,
            cancellation_token=None,
        )

    assert process.started is True
    assert process.join_timeouts == [0]
    assert terminator.processes == []
    assert len(result_queue.get_calls) == 1
    assert result_queue.close_calls == 1
    assert result_queue.join_thread_calls == 1


def test_run_playwright_worker_process_timeout_terminates_and_cleans_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker timeout 必须 terminate 并执行 finally queue cleanup。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: timeout fencing、终止或 finally cleanup 契约漂移时抛出。
    """

    result_queue = _FakePlaywrightResultQueue()
    process = _FakePlaywrightProcess(alive_after_start=True)
    context = _FakePlaywrightMultiprocessingContext(
        result_queue=result_queue,
        process=process,
    )
    context_factory = _FakePlaywrightContextFactory(context)
    terminator = _RecordingPlaywrightProcessTerminator()
    clock = _ScriptedMonotonicClock((1.0, 1.0))
    monkeypatch.setattr(
        web_playwright_backend.multiprocessing,
        "get_context",
        context_factory,
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_terminate_playwright_process",
        terminator,
    )
    monkeypatch.setattr(web_playwright_backend.time, "monotonic", clock)

    with pytest.raises(TimeoutError, match="playwright worker timeout"):
        web_playwright_backend._run_playwright_worker_process(
            playwright_sync_worker=_SyntheticProcessPlaywrightWorker(),
            worker_kwargs=_playwright_worker_process_kwargs(),
            diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
            allow_environment_proxy=False,
            total_timeout=0.0,
            cancellation_token=None,
        )

    assert process.started is True
    assert terminator.processes == [process]
    assert result_queue.get_calls == []
    assert result_queue.close_calls == 1
    assert result_queue.join_thread_calls == 1


@pytest.mark.parametrize(
    ("browser_close_error", "runtime_stop_error"),
    (
        (None, None),
        (RuntimeError("synthetic browser close failure"), None),
        (None, RuntimeError("synthetic runtime stop failure")),
    ),
)
def test_close_playwright_browser_clears_singletons_after_success_or_error(
    monkeypatch: pytest.MonkeyPatch,
    browser_close_error: RuntimeError | None,
    runtime_stop_error: RuntimeError | None,
) -> None:
    """Browser/runtime close 成功或抛异常时都必须清空三项 singleton 状态。

    Args:
        monkeypatch: pytest 属性替换夹具。
        browser_close_error: browser close 时需要抛出的可选异常。
        runtime_stop_error: runtime stop 时需要抛出的可选异常。

    Returns:
        无。

    Raises:
        AssertionError: cleanup 调用或 singleton 状态清空契约漂移时抛出。
    """

    browser = _LifecyclePlaywrightBrowser(close_error=browser_close_error)
    instance = _LifecyclePlaywrightInstance(
        _LifecycleChromiumLauncher(browser),
        stop_error=runtime_stop_error,
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_PW_BROWSER",
        cast(web_playwright_backend._BrowserProtocol, browser),
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_PW_INSTANCE",
        cast(web_playwright_backend._PlaywrightInstanceProtocol, instance),
    )
    monkeypatch.setattr(
        web_playwright_backend,
        "_PW_BROWSER_KEY",
        ("chrome", True),
    )

    web_playwright_backend._close_playwright_browser()

    assert browser.close_calls == 1
    assert instance.stop_calls == 1
    assert web_playwright_backend._PW_BROWSER is None
    assert web_playwright_backend._PW_INSTANCE is None
    assert web_playwright_backend._PW_BROWSER_KEY is None


def test_playwright_url_safety_error_survives_worker_process() -> None:
    """Playwright worker 子进程必须保留 Web fetch URL safety 异常语义。"""

    worker_kwargs: web_playwright_backend._WorkerKwargs = {
        "url": "https://example.com/report",
        "timeout_seconds": 1.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": "",
        "egress_policy": _public_test_policy(),
        "browser_resource_budget": _DEFAULT_BROWSER_RESOURCE_BUDGET,
    }

    with pytest.raises(web_fetch_orchestrator._FetchUrlSafetyError) as exc_info:
        web_playwright_backend._run_playwright_worker_process(
            playwright_sync_worker=_BlockedPlaywrightWorker(
                blocked_url="http://127.0.0.1/internal",
                blocked_stage="playwright_goto",
            ),
            worker_kwargs=worker_kwargs,
            diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
            allow_environment_proxy=False,
            total_timeout=5.0,
            cancellation_token=None,
        )

    assert exc_info.value.url == "http://127.0.0.1/internal"
    assert exc_info.value.reason == "playwright_goto"


def test_playwright_process_wrapper_projects_success_and_diagnostic_error() -> None:
    """process wrapper 必须分别投影 Browser success 与 Diagnostic-capped error。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: success 或 capped error 投影不符合 owner 契约时抛出。
    """

    worker_kwargs: web_playwright_backend._WorkerKwargs = {
        "url": "https://example.com/report",
        "timeout_seconds": 1.0,
        "headers": None,
        "playwright_channel": None,
        "playwright_storage_state_path": "",
        "egress_policy": _public_test_policy(),
        "browser_resource_budget": _DEFAULT_BROWSER_RESOURCE_BUDGET,
    }
    result = web_playwright_backend._run_playwright_worker_process(
        playwright_sync_worker=_SyntheticProcessPlaywrightWorker(),
        worker_kwargs=worker_kwargs,
        diagnostic_resource_budget=_diagnostic_resource_budget(
            error_chars=32,
            events=4,
        ),
        allow_environment_proxy=False,
        total_timeout=5.0,
        cancellation_token=None,
    )
    assert result["content"] == "process success"

    with pytest.raises(RuntimeError, match="RuntimeError") as exc_info:
        web_playwright_backend._run_playwright_worker_process(
            playwright_sync_worker=_SyntheticProcessPlaywrightWorker(
                failure_message="synthetic process diagnostic failure",
            ),
            worker_kwargs=worker_kwargs,
            diagnostic_resource_budget=_diagnostic_resource_budget(
                error_chars=32,
                events=4,
            ),
            allow_environment_proxy=False,
            total_timeout=5.0,
            cancellation_token=None,
        )
    assert len(str(exc_info.value)) <= len("RuntimeError: ") + 32


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
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> web_playwright_backend.WebPayload:
        """模拟 Playwright 导航阶段 URL safety 拒绝。

        Args:
            url: 目标 URL。
            timeout_seconds: 浏览器抓取超时。
            headers: 请求头。
            timeout_budget: 工具总预算。
            deadline_monotonic: 工具调用 deadline。
            playwright_channel: 浏览器 channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: Web 出站策略。
            transport_policy: 当前 attempt 的 transport policy。
            browser_resource_budget: Browser child 资源预算。
            diagnostic_resource_budget: Diagnostic child 诊断投影预算。
            cancellation_token: 取消令牌。

        Returns:
            不返回。

        Raises:
            _FetchUrlSafetyError: 始终抛出。
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
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
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
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """模拟 Playwright worker 在 fallback 内部收到取消。

        Args:
            url: 目标 URL。
            timeout_seconds: 浏览器抓取超时。
            headers: 请求头。
            timeout_budget: 工具总预算。
            deadline_monotonic: 工具调用 deadline。
            playwright_channel: 浏览器 channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: Web 出站策略。
            transport_policy: 当前 attempt 的 transport policy。
            browser_resource_budget: Browser child 资源预算。
            diagnostic_resource_budget: Diagnostic child 诊断投影预算。
            cancellation_token: 取消令牌。

        Returns:
            不返回。

        Raises:
            CancelledError: 始终抛出。
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
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
        )
        raise web_playwright_backend.CancelledError("cancelled by host")

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )
    definition = _definitions_by_name(_discover_definitions({"allow_private_network_url": True}))["fetch_web_page"]

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
    definitions = _definitions_by_name(_discover_definitions({"allow_private_network_url": True}))
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
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """记录非预期 Playwright worker 调用。

        Args:
            url: 目标 URL。
            timeout_seconds: 浏览器抓取超时。
            headers: 请求头。
            timeout_budget: 工具总预算。
            deadline_monotonic: 工具调用 deadline。
            playwright_channel: 浏览器 channel。
            playwright_storage_state_path: storage state 路径。
            egress_policy: Web 出站策略。
            transport_policy: 当前 attempt 的 transport policy。
            browser_resource_budget: Browser child 资源预算。
            diagnostic_resource_budget: Diagnostic child 诊断投影预算。
            cancellation_token: 取消令牌。

        Returns:
            成功结果。

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
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
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
            browser_enabled=True,
            transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
            browser_resource_budget=_DEFAULT_BROWSER_RESOURCE_BUDGET,
            diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
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
        browser_resource_budget: BrowserResourceBudget,
    ) -> dict[str, JsonValue]:
        """记录不应发生的同进程 Playwright 调用。

        :param url: 目标 URL。
        :param timeout_seconds: browser timeout。
        :param headers: 可选请求头。
        :param playwright_channel: 可选浏览器 channel。
        :param playwright_storage_state_path: storage state 路径。
        :param egress_policy: 当前 Web 出站策略。
        :param browser_resource_budget: Browser child 资源预算。
        :returns: 确定性成功 payload，用于暴露错误同进程执行。
        :raises Exception: 不主动抛出异常。
        """

        del (
            timeout_seconds,
            headers,
            playwright_channel,
            playwright_storage_state_path,
            egress_policy,
            browser_resource_budget,
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
        transport_policy=_PROXY_DENIED_TRANSPORT_POLICY,
        browser_resource_budget=_DEFAULT_BROWSER_RESOURCE_BUDGET,
        diagnostic_resource_budget=_DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
        cancellation_token=_OpenCancellationToken(),
        resolve_timeout_budget=lambda timeout_seconds, **kwargs: timeout_seconds,
        playwright_sync_worker=fake_worker,
        detect_bot_challenge=lambda **kwargs: web_challenge_detection.BotChallengeDetectionResult(
            decision=web_challenge_detection.BotChallengeDecision.NONE,
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
        "browser_resource_budget": _DEFAULT_BROWSER_RESOURCE_BUDGET,
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
        assert terminate_result.elapsed_seconds <= (web_playwright_backend._PW_PROCESS_TERMINATE_GRACE_SECONDS)
        assert cleanup_elapsed_seconds <= (web_playwright_backend._PW_PROCESS_TERMINATE_GRACE_SECONDS)
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
        "browser_resource_budget": _DEFAULT_BROWSER_RESOURCE_BUDGET,
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
            pytest.skip("process-group cleanup fallback: " f"{terminate_result.cleanup.reason.value}")
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
            b"<html><head><title>Live Browser Cleanup</title></head>" b"<body>browser cleanup fixture</body></html>"
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
        "browser_resource_budget": _DEFAULT_BROWSER_RESOURCE_BUDGET,
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
            pytest.skip("process-group cleanup fallback: " f"{terminate_result.cleanup.reason.value}")
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
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """记录 browser fallback 参数并返回确定性内容。

        Args:
            url: 目标 URL。
            timeout_seconds: 抓取超时。
            headers: 请求 headers。
            timeout_budget: 工具预算。
            deadline_monotonic: 工具 deadline。
            playwright_channel: 浏览器 channel。
            playwright_storage_state_path: storage state 文件路径。
            egress_policy: Web 出站策略。
            transport_policy: 当前 attempt 的 transport policy。
            browser_resource_budget: Browser child 资源预算。
            diagnostic_resource_budget: Diagnostic child 诊断投影预算。
            cancellation_token: 取消令牌。

        Returns:
            确定性抓取内容。

        Raises:
            无。
        """

        del (
            headers,
            timeout_budget,
            deadline_monotonic,
            egress_policy,
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
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
        transport_policy: web_http_session.WebHttpTransportPolicy,
        browser_resource_budget: BrowserResourceBudget,
        diagnostic_resource_budget: DiagnosticResourceBudget,
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """记录空 storage state dir 的 browser fallback 参数。

        Args:
            url: 目标 URL。
            timeout_seconds: 抓取超时。
            headers: 请求 headers。
            timeout_budget: 工具预算。
            deadline_monotonic: 工具 deadline。
            playwright_channel: 浏览器 channel。
            playwright_storage_state_path: storage state 文件路径。
            egress_policy: Web 出站策略。
            transport_policy: 当前 attempt 的 transport policy。
            browser_resource_budget: Browser child 资源预算。
            diagnostic_resource_budget: Diagnostic child 诊断投影预算。
            cancellation_token: 取消令牌。

        Returns:
            确定性抓取内容。

        Raises:
            无。
        """

        del (
            headers,
            timeout_budget,
            deadline_monotonic,
            egress_policy,
            transport_policy,
            browser_resource_budget,
            diagnostic_resource_budget,
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

    outcome = asyncio.run(definition.callable(_call("search_web", {"query": "revenue"}), _context()))

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

    definitions = _definitions_by_name(_discover_definitions({"allow_private_network_url": True}))

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
        args=(
            result_queue,
            worker_callable,
            worker_kwargs,
            _DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET,
            False,
        ),
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
