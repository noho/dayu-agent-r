"""Web tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
import logging
import multiprocessing
import os
import pickle
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import ParamSpec, TypeVar, cast

import pytest

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
from dayu.tools.web import web_tool_projection_text
from dayu.tools.web import web_search_providers
from dayu.tools.web import web_tools

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
_FORBIDDEN_IMPORTS = (
    "dayu.engine.tool_registry",
    "dayu.engine.truncation_manager",
    "dayu.engine.tools.fetch_more",
    "dayu.web",
    "dayu.tools." + "_legacy" + "_adapter",
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

    @classmethod
    def start(
        cls,
        *,
        response_body: bytes,
        delay_seconds: float = 0.0,
        max_connections: int = 8,
    ) -> "_SocketWebServer":
        """启动本地 HTTP server。

        :param response_body: 响应正文。
        :param delay_seconds: 每个连接发送响应前等待的秒数。
        :param max_connections: 最多处理的连接数。
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
            with connection:
                self._handle_connection(connection)

    def _handle_connection(self, connection: socket.socket) -> None:
        """处理单个 HTTP 连接。

        :param connection: 已接受的 socket 连接。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        try:
            request = connection.recv(4096)
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

        del url, timeout_seconds, headers, playwright_channel
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

        del timeout_seconds, headers, playwright_channel
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


def test_web_provider_discovers_search_and_fetch() -> None:
    """ToolsDiscovery 应发现两个 Web tools。"""

    spec = _spec({})
    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=spec, provider=discover_tools),)
    )

    assert tuple(definition.name for definition in result.tool_bundle.definitions) == _WEB_TOOL_NAMES
    assert result.provider_reports[0].tool_names == _WEB_TOOL_NAMES


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
    ) -> dict[str, JsonValue]:
        """记录不应发生的同进程 Playwright 调用。"""

        del timeout_seconds, headers, playwright_channel, playwright_storage_state_path
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
        cancellation_token=_OpenCancellationToken(),
        resolve_timeout_budget=lambda timeout_seconds, **kwargs: timeout_seconds,
        playwright_sync_worker=fake_worker,
        detect_bot_challenge=lambda **kwargs: web_tools.BotChallengeDetectionResult(
            challenge_detected=False,
            challenge_signals=(),
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
        :param cancellation_token: 取消令牌。
        :returns: 确定性抓取内容。
        """

        del headers, timeout_budget, deadline_monotonic, cancellation_token
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
        :param cancellation_token: 取消令牌。
        :returns: 确定性抓取内容。
        """

        del headers, timeout_budget, deadline_monotonic, cancellation_token
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
