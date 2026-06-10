#!/usr/bin/env python3
"""Web CI smoke 汇总脚本。

本模块负责 smoke 级别的 diagnostics artifact schema 校验、pass/fail/skip/
diagnostic-only 分类和 Codex 可读 summary 输出。网页访问、``requests``、
``fetch_web_page``、Playwright 与 Docling 事实均来自 ``utils.diagnose_web_access``
输出的 artifact；本脚本不重新诊断网页内容。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import html
import http.server
import json
import logging
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Iterator, TypeAlias, cast
from urllib.parse import urlparse

import requests

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig
from dayu.runtime.log import LogLevel, configure
from dayu.service.host_assembly import (
    assemble_effective_tool_provider_configs,
    discover_service_tools,
)

JsonObject: TypeAlias = dict[str, JsonValue]
DiagnosticRunner: TypeAlias = Callable[[Sequence[str]], "DiagnosticChildResult"]

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)
_DEFAULT_OUTPUT_ROOT: Final[Path] = Path("workspace/output/web_smoke")
_DEFAULT_EXTERNAL_URL_FILE: Final[Path] = Path(__file__).resolve().with_name("web_ci_urls.jsonl")
_DEFAULT_EXTERNAL_LIMIT: Final[int] = 2
_DIAGNOSTIC_SCHEMA_VERSION: Final[str] = "web-diagnostics-v1"
_MIN_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = 1
_STATUS_PASSED: Final[str] = "passed"
_STATUS_FAILED: Final[str] = "failed"
_STATUS_SKIPPED: Final[str] = "skipped"
_STATUS_DIAGNOSTIC_ONLY: Final[str] = "diagnostic_only"
_EXIT_OK: Final[int] = 0
_EXIT_LOCAL_FAILURE: Final[int] = 1
_EXIT_SCHEMA_OR_INFRA_FAILURE: Final[int] = 2
_CASE_LOCAL_HTML: Final[str] = "local_html"
_CASE_LOCAL_PDF: Final[str] = "local_pdf"
_CASE_LOCAL_BROWSER: Final[str] = "local_browser"
_CASE_LOCAL_ASSEMBLY_CONFIG: Final[str] = "local_assembly_config"
_CASE_EXTERNAL: Final[str] = "external"
_CASE_SEARCH_PROVIDER: Final[str] = "search_provider"
_JSONL_SUFFIXES: Final[frozenset[str]] = frozenset({".jsonl", ".jsonlines"})
_EXTERNAL_URL_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})
_LOCAL_FIXTURE_HOST: Final[str] = "127.0.0.1"
_LOCAL_HTML_PATH: Final[str] = "/index.html"
_LOCAL_PDF_PATH: Final[str] = "/fixture.pdf"
_LOCAL_BROWSER_PATH: Final[str] = "/client-rendered.html"
_LOCAL_HTML_CONTENT_TYPE: Final[str] = "text/html; charset=utf-8"
_LOCAL_PDF_CONTENT_TYPE: Final[str] = "application/pdf"
_HTTP_GET_METHOD: Final[str] = "GET"
_HTTP_HEADER_CONTENT_TYPE: Final[str] = "Content-Type"
_HTTP_HEADER_CONTENT_LENGTH: Final[str] = "Content-Length"
_HTTP_HEADER_CACHE_CONTROL: Final[str] = "Cache-Control"
_HTTP_CACHE_CONTROL_NO_STORE: Final[str] = "no-store"
_HTTP_STATUS_OK: Final[int] = 200
_HTTP_STATUS_NOT_FOUND: Final[int] = 404
_HTTP_STATUS_METHOD_NOT_ALLOWED: Final[int] = 405
_SERVER_JOIN_TIMEOUT_SECONDS: Final[float] = 2.0
_DOCLING_INVOCATION_BLOCKER_FILE: Final[str] = "local-pdf-docling-invocation-blocker.md"
_BUCKET_PASSED: Final[str] = "passed"
_BUCKET_DIAGNOSTIC_SCHEMA_GAP: Final[str] = "diagnostic_schema_gap"
_BUCKET_CHILD_PROCESS_ERROR: Final[str] = "child_process_error"
_BUCKET_ARTIFACT_PARSE_FAILURE: Final[str] = "artifact_parse_failure"
_BUCKET_ARTIFACT_MISSING: Final[str] = "artifact_missing"
_BUCKET_LOCAL_REQUESTS_FAILURE: Final[str] = "local_requests_failure"
_BUCKET_LOCAL_FETCH_FAILURE: Final[str] = "local_fetch_failure"
_BUCKET_PDF_CONTENT_TYPE_FAILURE: Final[str] = "pdf_content_type_failure"
_BUCKET_PDF_CONTENT_LENGTH_FAILURE: Final[str] = "pdf_content_length_failure"
_BUCKET_PDF_DOCLING_INVOCATION_FAILURE: Final[str] = "pdf_docling_invocation_failure"
_BUCKET_DOCLING_INIT_SKIP: Final[str] = "docling_runtime_initialization_error"
_BUCKET_BROWSER_BACKEND_NOT_OBSERVED: Final[str] = "browser_backend_not_observed"
_BUCKET_BROWSER_FETCH_FAILURE: Final[str] = "browser_fetch_failure"
_BUCKET_BROWSER_PROFILE_NOT_SAMPLED: Final[str] = "browser_profile_not_sampled"
_BUCKET_WEB_CONFIG_LOADER_FAILURE: Final[str] = "web_config_loader_failure"
_BUCKET_WEB_ASSEMBLY_DISCOVERY_FAILURE: Final[str] = "web_assembly_discovery_failure"
_BUCKET_WEB_TOOL_MISSING: Final[str] = "web_tool_missing"
_BUCKET_WEB_ASSEMBLY_FETCH_FAILURE: Final[str] = "web_assembly_fetch_failure"
_BUCKET_WEB_ASSEMBLY_FETCH_CONTENT_FAILURE: Final[str] = "web_assembly_fetch_content_failure"
_BUCKET_WEB_ASSEMBLY_CONFIG_MISMATCH: Final[str] = "web_assembly_config_mismatch"
_BUCKET_SEARCH_PROVIDER_PASSED: Final[str] = "search_provider_passed"
_BUCKET_PROVIDER_KEY_MISSING: Final[str] = "provider_key_missing"
_BUCKET_PROVIDER_AUTH_FAILURE: Final[str] = "provider_auth_failure"
_BUCKET_PROVIDER_QUOTA_OR_RATE_LIMITED: Final[str] = "provider_quota_or_rate_limited"
_BUCKET_PROVIDER_NETWORK_FAILURE: Final[str] = "provider_network_failure"
_BUCKET_PROVIDER_RESPONSE_PARSE_FAILURE: Final[str] = "provider_response_parse_failure"
_BUCKET_PROVIDER_NO_RESULTS: Final[str] = "provider_no_results"
_BUCKET_PROVIDER_UNAVAILABLE: Final[str] = "provider_unavailable"
_BUCKET_SEARCH_TOOL_EXECUTION_ERROR: Final[str] = "search_tool_execution_error"
_PDF_EXPECTED_STREAM_NAME: Final[str] = "page.pdf"
_BROWSER_EXPECTED_FETCH_BACKEND: Final[str] = "playwright"
_ASSEMBLY_SCHEMA_VERSION: Final[str] = "web-smoke-assembly-v1"
_SEARCH_SCHEMA_VERSION: Final[str] = "web-smoke-search-v1"
_ASSEMBLY_PATH_LABEL: Final[str] = (
    "ConfigLoader -> assemble_effective_tool_provider_configs -> "
    "discover_service_tools -> ToolDefinition.callable"
)
_PACKAGE_CONFIG_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "dayu" / "config"
_ASSEMBLY_FETCH_TRUNCATE_CHARS: Final[int] = 3210
_ASSEMBLY_PROVIDER_CONFIG: Final[JsonObject] = {
    "provider": "duckduckgo",
    "request_timeout_seconds": 6.0,
    "max_search_results": 3,
    "fetch_truncate_chars": _ASSEMBLY_FETCH_TRUNCATE_CHARS,
    "allow_private_network_url": True,
    "playwright_channel": "chrome",
    "playwright_storage_state_dir": "",
}
_SEARCH_PROVIDERS: Final[tuple[str, ...]] = ("auto", "tavily", "serper", "duckduckgo")
_SEARCH_PROVIDER_QUERY: Final[str] = "OpenAI investor relations"
_SEARCH_FETCH_TRUNCATE_CHARS: Final[int] = 4096
_SEARCH_API_KEY_ENVS: Final[Mapping[str, str]] = {
    "tavily": "TAVILY_API_KEY",
    "serper": "SERPER_API_KEY",
}
PDF_FETCH_MIN_CHARS: Final[int] = 20
_HTML_FIXTURE_TITLE: Final[str] = "Dayu Web Smoke HTML"
_HTML_FIXTURE_BODY: Final[str] = "Dayu Web Smoke HTML fixture verifies local fetch_web_page access."
_BROWSER_FIXTURE_TITLE: Final[str] = "Dayu Web Smoke Browser Rendered"
_BROWSER_FIXTURE_TEXT: Final[str] = (
    "Playwright fallback rendered this client-side page for fetch_web_page smoke evidence."
)
_PDF_FIXTURE_TEXT_LINE_1: Final[str] = "Dayu Web Smoke PDF"
_PDF_FIXTURE_TEXT_LINE_2: Final[str] = "This PDF verifies Docling conversion."
_PDF_STREAM_FONT_SIZE: Final[int] = 18
_PDF_STREAM_X: Final[int] = 72
_PDF_STREAM_Y: Final[int] = 720
_PDF_STREAM_LINE_STEP: Final[int] = 28
_PDF_PAGE_WIDTH: Final[int] = 612
_PDF_PAGE_HEIGHT: Final[int] = 792
_PDF_OBJECT_COUNT: Final[int] = 5
_CHILD_STDIO_LOG_CHARS: Final[int] = 1_000


@dataclass(frozen=True, slots=True)
class SmokeOptions:
    """Smoke CLI 选项的强类型投影。

    Args:
        output_dir: summary 与子 artifact 输出目录。
        request_timeout: 传给 diagnostics 的 requests timeout。
        tool_timeout_budget: 传给 diagnostics 的工具调用 timeout budget。
        include_playwright: 是否让 diagnostics 采样 Playwright。
        external_url_file: 外部 URL 样本文件。
        external_limit: 外部 URL 最多采样数量。
        diagnostic_only_external: 外部 URL 是否只作为 diagnostic-only。
        run_label: 本次 smoke 运行标签。
        log_level: Dayu 诊断日志级别。

    Returns:
        无。

    Raises:
        无。
    """

    output_dir: Path
    request_timeout: float
    tool_timeout_budget: float
    include_playwright: bool
    external_url_file: Path | None
    external_limit: int
    diagnostic_only_external: bool
    run_label: str
    log_level: LogLevel


@dataclass(frozen=True, slots=True)
class LocalFixtureUrls:
    """本地 HTTP fixture 的 URL 集合。

    Args:
        html_url: HTML fixture URL。
        pdf_url: PDF fixture URL。
        browser_url: client-rendered browser fixture URL。

    Returns:
        无。

    Raises:
        无。
    """

    html_url: str
    pdf_url: str
    browser_url: str


@dataclass(frozen=True, slots=True)
class DiagnosticChildResult:
    """diagnostics 子进程执行结果。

    Args:
        returncode: 子进程退出码。
        stdout: 子进程标准输出。
        stderr: 子进程标准错误。

    Returns:
        无。

    Raises:
        无。
    """

    returncode: int
    stdout: str
    stderr: str


class _OpenCancellationToken:
    """Smoke 直接调用工具时使用的未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回当前取消状态。

        Args:
            无。

        Returns:
            始终返回 ``False``。

        Raises:
            无。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Args:
            无。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Args:
            无。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        return None


@dataclass(frozen=True, slots=True)
class SmokeItem:
    """summary 中的一条失败、跳过或 diagnostic-only 记录。

    Args:
        bucket: smoke 分类 bucket。
        evidence_path: 证据 artifact 路径。
        url: 相关 URL。
        suggested_next_step: 建议下一步；failure/diagnostic-only 使用。
        reason: 跳过原因；skip 使用。

    Returns:
        无。

    Raises:
        无。
    """

    bucket: str
    evidence_path: str
    url: str
    suggested_next_step: str
    reason: str

    def to_json(self) -> JsonObject:
        """转换为 summary JSON 对象。

        Args:
            无。

        Returns:
            summary item JSON 对象。

        Raises:
            无。
        """

        return {
            "bucket": self.bucket,
            "evidence_path": self.evidence_path,
            "url": self.url,
            "suggested_next_step": self.suggested_next_step,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SmokeCaseResult:
    """单个 smoke case 的分类结果。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        url: 相关 URL。
        status: ``passed``、``failed``、``skipped`` 或 ``diagnostic_only``。
        bucket: smoke 分类 bucket。
        evidence_path: 证据 artifact 路径。
        suggested_next_step: 建议下一步。
        reason: 跳过或 diagnostic-only 原因。
        exit_code: 该 case 对本地 gate 的退出码贡献。

    Returns:
        无。

    Raises:
        无。
    """

    case_name: str
    case_kind: str
    url: str
    status: str
    bucket: str
    evidence_path: str
    suggested_next_step: str
    reason: str
    exit_code: int

    def to_json(self) -> JsonObject:
        """转换为 summary JSON 对象。

        Args:
            无。

        Returns:
            case result JSON 对象。

        Raises:
            无。
        """

        return {
            "case_name": self.case_name,
            "case_kind": self.case_kind,
            "url": self.url,
            "status": self.status,
            "bucket": self.bucket,
            "evidence_path": self.evidence_path,
            "suggested_next_step": self.suggested_next_step,
            "reason": self.reason,
            "exit_code": self.exit_code,
        }

    def to_item(self) -> SmokeItem:
        """转换为 failure/skip/diagnostic-only 列表项。

        Args:
            无。

        Returns:
            summary item。

        Raises:
            无。
        """

        return SmokeItem(
            bucket=self.bucket,
            evidence_path=self.evidence_path,
            url=self.url,
            suggested_next_step=self.suggested_next_step,
            reason=self.reason,
        )


@dataclass(frozen=True, slots=True)
class SmokeSummary:
    """Web smoke summary 契约。

    Args:
        status: 总体状态。
        exit_code: 脚本退出码。
        run_label: 运行标签。
        output_dir: 输出目录。
        failures: local gate failure 或 schema gap。
        skips: 已跳过的 case。
        diagnostic_only: diagnostic-only 记录。
        local_cases: local case 结果。
        external_cases: external case 结果。
        search_cases: search provider diagnostic case 结果。

    Returns:
        无。

    Raises:
        无。
    """

    status: str
    exit_code: int
    run_label: str
    output_dir: str
    failures: tuple[SmokeItem, ...]
    skips: tuple[SmokeItem, ...]
    diagnostic_only: tuple[SmokeItem, ...]
    local_cases: tuple[SmokeCaseResult, ...]
    external_cases: tuple[SmokeCaseResult, ...]
    search_cases: tuple[SmokeCaseResult, ...]

    def to_json(self) -> JsonObject:
        """转换为 summary JSON 对象。

        Args:
            无。

        Returns:
            summary JSON 对象。

        Raises:
            无。
        """

        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "run_label": self.run_label,
            "output_dir": self.output_dir,
            "failures": [item.to_json() for item in self.failures],
            "skips": [item.to_json() for item in self.skips],
            "diagnostic_only": [item.to_json() for item in self.diagnostic_only],
            "local_cases": [case.to_json() for case in self.local_cases],
            "external_cases": [case.to_json() for case in self.external_cases],
            "search_cases": [case.to_json() for case in self.search_cases],
        }


def _local_fixture_urls(port: int) -> LocalFixtureUrls:
    """按端口构造本地 fixture URL。

    Args:
        port: 本地 HTTP server 监听端口。

    Returns:
        HTML 与 PDF fixture URL。

    Raises:
        ValueError: 端口非法时抛出。
    """

    if port <= 0:
        raise ValueError("local fixture server 端口必须大于 0。")
    origin = f"http://{_LOCAL_FIXTURE_HOST}:{port}"
    return LocalFixtureUrls(
        html_url=f"{origin}{_LOCAL_HTML_PATH}",
        pdf_url=f"{origin}{_LOCAL_PDF_PATH}",
        browser_url=f"{origin}{_LOCAL_BROWSER_PATH}",
    )


def _html_fixture_bytes() -> bytes:
    """构造本地 HTML fixture 响应体。

    Args:
        无。

    Returns:
        UTF-8 HTML bytes。

    Raises:
        无。
    """

    title = html.escape(_HTML_FIXTURE_TITLE)
    body = html.escape(_HTML_FIXTURE_BODY)
    document = (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head><meta charset=\"utf-8\"><title>"
        f"{title}</title></head>\n"
        f"<body><main><h1>{title}</h1><p>{body}</p></main></body>\n"
        "</html>\n"
    )
    return document.encode("utf-8")


def _pdf_text_stream() -> bytes:
    """构造 PDF 页面文本 stream。

    Args:
        无。

    Returns:
        PDF content stream bytes。

    Raises:
        无。
    """

    stream = (
        "BT\n"
        f"/F1 {_PDF_STREAM_FONT_SIZE} Tf\n"
        f"{_PDF_STREAM_X} {_PDF_STREAM_Y} Td\n"
        f"({_PDF_FIXTURE_TEXT_LINE_1}) Tj\n"
        f"0 -{_PDF_STREAM_LINE_STEP} Td\n"
        f"({_PDF_FIXTURE_TEXT_LINE_2}) Tj\n"
        "ET\n"
    )
    return stream.encode("ascii")


def _browser_fixture_bytes() -> bytes:
    """构造需要浏览器执行脚本后才产出正文的 HTML fixture。

    Args:
        无。

    Returns:
        UTF-8 HTML bytes。

    Raises:
        无。
    """

    title = html.escape(_BROWSER_FIXTURE_TITLE)
    rendered_text = html.escape(_BROWSER_FIXTURE_TEXT)
    rendered_html = json.dumps(f"<main><h1>{title}</h1><p>{rendered_text}</p></main>")
    document = (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        f"<head><meta charset=\"utf-8\"><title>{title}</title></head>\n"
        "<body><div id=\"app\"></div><script>\n"
        f"document.getElementById('app').innerHTML = {rendered_html};\n"
        "</script></body>\n"
        "</html>\n"
    )
    return document.encode("utf-8")


def _pdf_fixture_bytes() -> bytes:
    """构造包含稳定可抽取文本的小型 PDF fixture。

    Args:
        无。

    Returns:
        PDF 文件 bytes。

    Raises:
        无。
    """

    content_stream = _pdf_text_stream()
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PDF_PAGE_WIDTH} {_PDF_PAGE_HEIGHT}] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ).encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content_stream)).encode("ascii") + b" >>\nstream\n" + content_stream + b"endstream",
    )
    chunks: list[bytes] = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets: list[int] = []
    for object_index, body in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{object_index} 0 obj\n".encode("ascii"))
        chunks.append(body)
        chunks.append(b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {_PDF_OBJECT_COUNT + 1}\n".encode("ascii"))
    chunks.append(b"0000000000 65535 f \n")
    for offset in offsets:
        chunks.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    chunks.append(
        (
            f"trailer\n<< /Size {_PDF_OBJECT_COUNT + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return b"".join(chunks)


class _LocalFixtureRequestHandler(http.server.BaseHTTPRequestHandler):
    """本地 Web smoke fixture HTTP handler。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        """处理 fixture GET 请求。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        path = urlparse(self.path).path
        if path == _LOCAL_HTML_PATH:
            _send_fixture_response(
                self,
                status_code=_HTTP_STATUS_OK,
                content_type=_LOCAL_HTML_CONTENT_TYPE,
                body=_html_fixture_bytes(),
            )
            return
        if path == _LOCAL_PDF_PATH:
            _send_fixture_response(
                self,
                status_code=_HTTP_STATUS_OK,
                content_type=_LOCAL_PDF_CONTENT_TYPE,
                body=_pdf_fixture_bytes(),
            )
            return
        if path == _LOCAL_BROWSER_PATH:
            _send_fixture_response(
                self,
                status_code=_HTTP_STATUS_OK,
                content_type=_LOCAL_HTML_CONTENT_TYPE,
                body=_browser_fixture_bytes(),
            )
            return
        _send_fixture_response(
            self,
            status_code=_HTTP_STATUS_NOT_FOUND,
            content_type="text/plain; charset=utf-8",
            body=b"not found\n",
        )

    def do_HEAD(self) -> None:
        """拒绝非 smoke 必需的 HEAD 请求。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        _send_fixture_response(
            self,
            status_code=_HTTP_STATUS_METHOD_NOT_ALLOWED,
            content_type="text/plain; charset=utf-8",
            body=b"",
        )

    def log_message(self, format: str, *args: str) -> None:
        """关闭默认 stderr 访问日志。

        Args:
            format: BaseHTTPRequestHandler 的格式字符串。
            args: 格式参数。

        Returns:
            无。

        Raises:
            无。
        """

        return


def _send_fixture_response(
    handler: http.server.BaseHTTPRequestHandler,
    *,
    status_code: int,
    content_type: str,
    body: bytes,
) -> None:
    """发送 fixture HTTP 响应。

    Args:
        handler: 当前请求 handler。
        status_code: HTTP 状态码。
        content_type: 响应 Content-Type。
        body: 响应 body bytes。

    Returns:
        无。

    Raises:
        无。
    """

    handler.send_response(status_code)
    handler.send_header(_HTTP_HEADER_CONTENT_TYPE, content_type)
    handler.send_header(_HTTP_HEADER_CONTENT_LENGTH, str(len(body)))
    handler.send_header(_HTTP_HEADER_CACHE_CONTROL, _HTTP_CACHE_CONTROL_NO_STORE)
    handler.end_headers()
    if handler.command == _HTTP_GET_METHOD and body:
        handler.wfile.write(body)


@contextlib.contextmanager
def _running_local_fixture_server() -> Iterator[LocalFixtureUrls]:
    """启动本地 loopback fixture server。

    Args:
        无。

    Returns:
        context manager 期间可访问的 fixture URLs。

    Raises:
        OSError: server 绑定或启动失败时抛出。
    """

    server = http.server.ThreadingHTTPServer((_LOCAL_FIXTURE_HOST, 0), _LocalFixtureRequestHandler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="dayu-web-smoke-local-fixture",
        daemon=True,
    )
    thread.start()
    try:
        yield _local_fixture_urls(int(server.server_address[1]))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)


def _utc_run_label() -> str:
    """生成默认运行标签。

    Args:
        无。

    Returns:
        UTC 时间戳运行标签。

    Raises:
        无。
    """

    return datetime.now(timezone.utc).strftime("web-smoke-%Y%m%dT%H%M%SZ")


def _default_output_dir(run_label: str) -> Path:
    """生成默认输出目录。

    Args:
        run_label: 运行标签。

    Returns:
        默认输出目录。

    Raises:
        无。
    """

    return (_DEFAULT_OUTPUT_ROOT / run_label).resolve()


def _log_level_from_text(log_level_text: str) -> LogLevel:
    """解析 CLI 日志级别文本。

    Args:
        log_level_text: CLI 传入的日志级别，不区分大小写。

    Returns:
        Dayu 日志级别。

    Raises:
        ValueError: 日志级别不属于 :class:`LogLevel` 时抛出。
    """

    normalized = log_level_text.strip().upper()
    try:
        return LogLevel[normalized]
    except KeyError as exc:
        allowed_values = ", ".join(level.name.lower() for level in LogLevel)
        raise ValueError(f"--log-level 必须是以下之一: {allowed_values}") from exc


def _json_object(value: JsonValue, *, field_name: str) -> JsonObject:
    """校验并复制 JSON 对象。

    Args:
        value: 待校验 JSON 值。
        field_name: 字段名，用于错误信息。

    Returns:
        JSON 对象副本。

    Raises:
        ValueError: 输入不是 JSON 对象时抛出。
    """

    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} 必须是 JSON 对象。")
    return {str(key): item for key, item in value.items()}


def _nested_object(payload: Mapping[str, JsonValue], key: str) -> JsonObject:
    """读取嵌套 JSON 对象。

    Args:
        payload: JSON 对象。
        key: 字段名。

    Returns:
        嵌套 JSON 对象副本；缺失或类型不符时返回空对象。

    Raises:
        无。
    """

    value = payload.get(key)
    if isinstance(value, Mapping):
        return {str(nested_key): nested_value for nested_key, nested_value in value.items()}
    return {}


def _bool_field(payload: Mapping[str, JsonValue], key: str) -> bool:
    """读取布尔字段。

    Args:
        payload: JSON 对象。
        key: 字段名。

    Returns:
        字段严格为 ``True`` 时返回 ``True``。

    Raises:
        无。
    """

    return payload.get(key) is True


def _int_field(payload: Mapping[str, JsonValue], key: str) -> int | None:
    """读取整数字段。

    Args:
        payload: JSON 对象。
        key: 字段名。

    Returns:
        整数字段；缺失或类型不符时返回 ``None``。

    Raises:
        无。
    """

    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _string_field(payload: Mapping[str, JsonValue], key: str) -> str:
    """读取字符串字段。

    Args:
        payload: JSON 对象。
        key: 字段名。

    Returns:
        字符串值；缺失或非字符串时返回空字符串。

    Raises:
        无。
    """

    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _load_json_artifact(path: Path) -> JsonObject:
    """读取 diagnostics JSON artifact。

    Args:
        path: artifact 路径。

    Returns:
        artifact JSON 对象。

    Raises:
        OSError: 文件读取失败时抛出。
        ValueError: 文件不是 JSON 对象时抛出。
        json.JSONDecodeError: JSON 解析失败时抛出。
    """

    payload = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    return _json_object(payload, field_name=str(path))


def _write_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    """写入 JSON 文件。

    Args:
        path: 输出路径。
        payload: JSON 对象。

    Returns:
        无。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_web_tool_discovery_overlay(
    workspace_config_dir: Path,
    *,
    provider_config: Mapping[str, JsonValue],
) -> None:
    """写入只启用 Web tools 的 workspace overlay。

    Args:
        workspace_config_dir: workspace config 目录。
        provider_config: Web provider config。

    Returns:
        无。

    Raises:
        OSError: overlay 写入失败时抛出。
    """

    _write_json(
        workspace_config_dir / "tool_discovery.json",
        {
            "providers": {
                "web-tools": {
                    "import_path": "dayu.tools.web:discover_tools",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "dayu.tools.web",
                    "enabled": True,
                    "allow_empty": False,
                    "config": dict(provider_config),
                }
            }
        },
    )


def _load_runtime_config_for_overlay(workspace_config_dir: Path) -> RuntimeConfig:
    """通过完整 ConfigLoader.load 读取 runtime config。

    Args:
        workspace_config_dir: workspace config overlay 目录。

    Returns:
        ConfigLoader 产出的 runtime config。

    Raises:
        Exception: 配置加载失败时向上抛出。
    """

    return ConfigLoader(package_config_dir=_PACKAGE_CONFIG_DIR).load(
        workspace_config_dir=workspace_config_dir,
    )


def _discover_tools_by_name(
    config: RuntimeConfig,
    *,
    workspace_root: Path,
) -> Mapping[str, ToolDefinition]:
    """通过 Service assembly 装配 effective configs 并发现工具。

    Args:
        config: ConfigLoader.load 产出的 runtime config。
        workspace_root: 当前 smoke 的 workspace root。

    Returns:
        工具定义映射。

    Raises:
        Exception: 工具发现失败时向上抛出。
    """

    effective_provider_configs = assemble_effective_tool_provider_configs(
        tuple(config.tool_discovery.providers.values()),
        workspace_root=workspace_root,
    )
    discovered = discover_service_tools(effective_provider_configs)
    return {definition.name: definition for definition in discovered.tool_bundle.definitions}


def _tool_call(name: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造 smoke 直接工具调用请求。

    Args:
        name: 工具名。
        arguments: 工具参数。

    Returns:
        工具调用请求。

    Raises:
        无。
    """

    return ToolCallRequest(
        tool_call_id=f"smoke-{name}",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _tool_context() -> BatchToolExecutionContext:
    """构造 smoke 直接工具调用上下文。

    Args:
        无。

    Returns:
        批式工具执行上下文。

    Raises:
        无。
    """

    return BatchToolExecutionContext(
        run_id="web-smoke-run",
        session_id="web-smoke-session",
        iteration_id="web-smoke-iteration",
        timeout_seconds=30.0,
        cancellation_token=_OpenCancellationToken(),
        correlation_id="web-smoke-run:web-smoke-iteration:tool_batch",
    )


def _truncate_max_chars(definition: ToolDefinition) -> int | None:
    """读取工具定义中的 text max chars truncate 声明。

    Args:
        definition: 工具定义。

    Returns:
        ``max_chars`` 值；缺失或类型不符时返回 ``None``。

    Raises:
        无。
    """

    if definition.truncate is None:
        return None
    value = definition.truncate.limits.get("max_chars")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _mapping_or_empty(value: JsonValue) -> JsonObject:
    """把 JSON 值收窄为对象。

    Args:
        value: JSON 值。

    Returns:
        JSON object；非对象时返回空对象。

    Raises:
        无。
    """

    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _stdio_log_prefix(value: str) -> str:
    """生成可写入 DEBUG 日志的子进程输出前缀。

    Args:
        value: 子进程 stdout 或 stderr。

    Returns:
        有界且单行化的输出前缀；空输入返回空字符串。

    Raises:
        无。
    """

    normalized = " ".join(value.split())
    if len(normalized) <= _CHILD_STDIO_LOG_CHARS:
        return normalized
    return normalized[:_CHILD_STDIO_LOG_CHARS] + "...<truncated>"


def _diagnostic_schema_gap(payload: Mapping[str, JsonValue], *, case_kind: str) -> str:
    """返回 diagnostics artifact schema gap 描述。

    Args:
        payload: diagnostics artifact。
        case_kind: case 类型。

    Returns:
        空字符串表示 schema 满足当前 smoke；非空字符串为 gap 说明。

    Raises:
        无。
    """

    version = _string_field(payload, "diagnostic_schema_version") or _string_field(payload, "schema_version")
    revision = _int_field(payload, "diagnostic_schema_revision")
    if version != _DIAGNOSTIC_SCHEMA_VERSION:
        return "diagnostics artifact 缺少当前 smoke 需要的 diagnostic_schema_version。"
    if revision is None or revision < _MIN_DIAGNOSTIC_SCHEMA_REVISION:
        return "diagnostics artifact 的 diagnostic_schema_revision 低于当前 smoke 要求。"

    required_gap = _required_fetch_fact_gap(payload)
    if required_gap:
        return required_gap
    if case_kind == _CASE_LOCAL_PDF:
        return _required_pdf_fact_gap(payload)
    return ""


def _external_diagnostic_schema_gap(payload: Mapping[str, JsonValue]) -> str:
    """校验 external diagnostic-only artifact 的最低 schema 事实。

    外部 URL 在 Slice 2 只用于 diagnostic-only 汇总，只需要 HTML 级别的
    requests/fetch 事实；这里刻意不要求 PDF content-type、内容长度或 Docling
    invocation evidence，避免把外部样本误提升为 local PDF gate。

    Args:
        payload: diagnostics artifact。

    Returns:
        空字符串表示 schema 满足 external diagnostic-only 汇总；非空字符串为
        gap 说明。

    Raises:
        无。
    """

    return _diagnostic_schema_gap(payload, case_kind=_CASE_LOCAL_HTML)


def _required_fetch_fact_gap(payload: Mapping[str, JsonValue]) -> str:
    """校验 HTML/PDF local gate 共用的 requests/fetch 必需事实。

    Args:
        payload: diagnostics artifact。

    Returns:
        空字符串表示必需字段存在；非空字符串为 gap 说明。

    Raises:
        无。
    """

    requests_profile = _nested_object(payload, "requests_profile")
    requests_result = _nested_object(requests_profile, "result")
    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    if "sampled" not in requests_profile:
        return "diagnostics artifact 缺少 requests_profile.sampled。"
    if "ok" not in requests_result:
        return "diagnostics artifact 缺少 requests_profile.result.ok。"
    if "sampled" not in fetch_profile:
        return "diagnostics artifact 缺少 fetch_web_page_profile.sampled。"
    if "ok" not in fetch_profile:
        return "diagnostics artifact 缺少 fetch_web_page_profile.ok。"
    return ""


def _required_pdf_fact_gap(payload: Mapping[str, JsonValue]) -> str:
    """校验 PDF local gate 必需事实。

    Args:
        payload: diagnostics artifact。

    Returns:
        空字符串表示必需字段存在；非空字符串为 gap 说明。

    Raises:
        无。
    """

    if not _raw_content_type(payload):
        return "diagnostics artifact 缺少 local PDF raw response content-type。"
    if _raw_content_length(payload) is None:
        return "diagnostics artifact 缺少 local PDF raw response content length。"
    if _fetch_content_length(payload) is None:
        return "diagnostics artifact 缺少 fetch_web_page content length。"
    evidence = _docling_evidence(payload)
    if not evidence:
        return "diagnostics artifact 缺少 docling_conversion_invocation_evidence。"
    return ""


def _raw_content_type(payload: Mapping[str, JsonValue]) -> str:
    """读取 raw requests 响应 content-type。

    Args:
        payload: diagnostics artifact。

    Returns:
        content-type 字符串；缺失时返回空字符串。

    Raises:
        无。
    """

    requests_profile = _nested_object(payload, "requests_profile")
    requests_result = _nested_object(requests_profile, "result")
    headers = _nested_object(requests_result, "response_headers")
    for key, value in headers.items():
        if key.lower() == "content-type" and isinstance(value, str):
            return value
    return _string_field(requests_result, "content_type") or _string_field(requests_profile, "content_type")


def _raw_content_length(payload: Mapping[str, JsonValue]) -> int | None:
    """读取 raw requests 响应内容长度。

    Args:
        payload: diagnostics artifact。

    Returns:
        内容长度；缺失时返回 ``None``。

    Raises:
        无。
    """

    requests_profile = _nested_object(payload, "requests_profile")
    requests_result = _nested_object(requests_profile, "result")
    direct = _int_field(requests_result, "content_length")
    if direct is not None:
        return direct
    return _int_field(requests_result, "text_length")


def _fetch_content_length(payload: Mapping[str, JsonValue]) -> int | None:
    """读取 fetch_web_page 返回内容长度。

    Args:
        payload: diagnostics artifact。

    Returns:
        内容长度；缺失时返回 ``None``。

    Raises:
        无。
    """

    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    return _int_field(fetch_profile, "content_length")


def _fetch_backend(payload: Mapping[str, JsonValue]) -> str:
    """读取 fetch_web_page 实际使用的 backend。

    Args:
        payload: diagnostics artifact。

    Returns:
        backend 字符串；缺失时返回空字符串。

    Raises:
        无。
    """

    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    return _string_field(fetch_profile, "fetch_backend")


def _playwright_profile_sampled(payload: Mapping[str, JsonValue]) -> bool:
    """判断 diagnostics 是否采样了 Playwright profile。

    Args:
        payload: diagnostics artifact。

    Returns:
        已采样时返回 ``True``。

    Raises:
        无。
    """

    playwright_profile = _nested_object(payload, "playwright_profile")
    return _bool_field(playwright_profile, "sampled")


def _docling_evidence(payload: Mapping[str, JsonValue]) -> JsonObject:
    """读取 Docling invocation evidence。

    Args:
        payload: diagnostics artifact。

    Returns:
        evidence JSON 对象；缺失时返回空对象。

    Raises:
        无。
    """

    evidence = _nested_object(payload, "docling_conversion_invocation_evidence")
    if evidence:
        return evidence
    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    return _nested_object(fetch_profile, "docling_conversion_invocation_evidence")


def _docling_init_skip(payload: Mapping[str, JsonValue]) -> bool:
    """判断 artifact 是否清楚表明 Docling 初始化或依赖缺失。

    Args:
        payload: diagnostics artifact。

    Returns:
        观察到 Docling 初始化或依赖错误时返回 ``True``。

    Raises:
        无。
    """

    evidence = _docling_evidence(payload)
    if _bool_field(evidence, "docling_runtime_initialization_error"):
        return True
    exception_type = _string_field(evidence, "original_exception_type")
    return exception_type in {"DoclingRuntimeInitializationError", "ModuleNotFoundError", "ImportError"}


def _requests_ok(payload: Mapping[str, JsonValue]) -> bool:
    """判断 raw requests 是否成功。

    Args:
        payload: diagnostics artifact。

    Returns:
        requests sampled 且 ok 时返回 ``True``。

    Raises:
        无。
    """

    requests_profile = _nested_object(payload, "requests_profile")
    requests_result = _nested_object(requests_profile, "result")
    return _bool_field(requests_profile, "sampled") and _bool_field(requests_result, "ok")


def _fetch_ok(payload: Mapping[str, JsonValue]) -> bool:
    """判断 current fetch_web_page 是否成功。

    Args:
        payload: diagnostics artifact。

    Returns:
        fetch sampled 且 ok 时返回 ``True``。

    Raises:
        无。
    """

    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    return _bool_field(fetch_profile, "sampled") and _bool_field(fetch_profile, "ok")


def _url_from_payload(payload: Mapping[str, JsonValue], fallback_url: str) -> str:
    """读取 artifact URL。

    Args:
        payload: diagnostics artifact。
        fallback_url: 缺失时使用的 URL。

    Returns:
        URL。

    Raises:
        无。
    """

    return _string_field(payload, "url") or fallback_url


def _observed_bucket(payload: Mapping[str, JsonValue], default_bucket: str) -> str:
    """读取 diagnostics observed bucket。

    Args:
        payload: diagnostics artifact。
        default_bucket: 缺失时使用的 bucket。

    Returns:
        bucket 字符串。

    Raises:
        无。
    """

    return (
        _string_field(payload, "observed_bucket")
        or _string_field(payload, "comparison_bucket")
        or default_bucket
    )


def _suggested_next_step(payload: Mapping[str, JsonValue], default_step: str) -> str:
    """读取 diagnostics action hint。

    Args:
        payload: diagnostics artifact。
        default_step: 缺失时使用的建议。

    Returns:
        建议下一步。

    Raises:
        无。
    """

    return _string_field(payload, "diagnostic_action_hint") or default_step


def _classify_loaded_artifact(
    *,
    case_name: str,
    case_kind: str,
    fallback_url: str,
    artifact_path: Path,
    payload: Mapping[str, JsonValue],
    child_returncode: int,
) -> SmokeCaseResult:
    """根据已加载 artifact 分类 smoke case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        fallback_url: artifact 缺少 URL 时的后备 URL。
        artifact_path: artifact 路径。
        payload: diagnostics artifact。
        child_returncode: diagnostics 子进程退出码。

    Returns:
        smoke case 结果。

    Raises:
        无。
    """

    url = _url_from_payload(payload, fallback_url)
    evidence_path = str(artifact_path)
    if case_kind == _CASE_EXTERNAL:
        if child_returncode != _EXIT_OK:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=url,
                evidence_path=evidence_path,
                bucket=_BUCKET_CHILD_PROCESS_ERROR,
                reason="外部 URL diagnostics 子进程失败；外部站点行为不作为 local smoke gate。",
                suggested_next_step="查看 diagnostics stdout/stderr 和站点可达性；必要时缩小外部样本。",
            )
        schema_gap = _external_diagnostic_schema_gap(payload)
        if schema_gap:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=url,
                evidence_path=evidence_path,
                bucket=_BUCKET_DIAGNOSTIC_SCHEMA_GAP,
                reason=schema_gap,
                suggested_next_step="先升级或修复 diagnostics artifact schema，再使用该外部样本做人工判断。",
            )
        return _case_diagnostic_only(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_observed_bucket(payload, _STATUS_DIAGNOSTIC_ONLY),
            reason="外部 URL 只作为 diagnostic-only，不影响 local smoke exit code。",
            suggested_next_step=_suggested_next_step(payload, "查看外部诊断证据；不要把站点不稳定直接判为生产 regression。"),
        )

    if child_returncode != _EXIT_OK and _docling_init_skip(payload) and case_kind == _CASE_LOCAL_PDF:
        return _case_skip(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_DOCLING_INIT_SKIP,
            reason="diagnostics 观察到 Docling 初始化或依赖缺失，PDF local smoke 本轮跳过。",
        )
    if child_returncode != _EXIT_OK:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_CHILD_PROCESS_ERROR,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="检查 diagnostics 子进程错误；local fixture 子进程失败是 smoke failure。",
        )

    schema_gap = _diagnostic_schema_gap(payload, case_kind=case_kind)
    if schema_gap:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_DIAGNOSTIC_SCHEMA_GAP,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step=schema_gap,
        )
    if case_kind == _CASE_LOCAL_PDF and _docling_init_skip(payload):
        return _case_skip(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_DOCLING_INIT_SKIP,
            reason="diagnostics 观察到 Docling 初始化或依赖缺失，PDF local smoke 本轮跳过。",
        )
    if not _requests_ok(payload):
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_LOCAL_REQUESTS_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="先检查 local fixture raw requests 路径；requests 失败不能由 fetch 成功掩盖。",
        )
    if not _fetch_ok(payload):
        if case_kind == _CASE_LOCAL_BROWSER:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=url,
                evidence_path=evidence_path,
                bucket=_BUCKET_BROWSER_FETCH_FAILURE,
                reason="client-rendered fixture 未观察到 fetch_web_page 成功；该 browser path 结果交给 Agent 结合 artifact 判断。",
                suggested_next_step="查看 fetch_web_page_profile 的 error/message/hint，确认是 Playwright 环境缺失、浏览器回退未触发还是工具回归。",
            )
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_LOCAL_FETCH_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="检查 current fetch_web_page callable 路径；local fixture fetch 失败是 smoke failure。",
        )
    if case_kind == _CASE_LOCAL_PDF:
        pdf_failure = _classify_pdf_loaded_artifact(
            case_name=case_name,
            url=url,
            evidence_path=evidence_path,
            payload=payload,
        )
        if pdf_failure is not None:
            return pdf_failure
    if case_kind == _CASE_LOCAL_BROWSER:
        browser_gap = _classify_browser_loaded_artifact(
            case_name=case_name,
            url=url,
            evidence_path=evidence_path,
            payload=payload,
        )
        if browser_gap is not None:
            return browser_gap
    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=url,
        status=_STATUS_PASSED,
        bucket=_BUCKET_PASSED,
        evidence_path=evidence_path,
        suggested_next_step="",
        reason="",
        exit_code=_EXIT_OK,
    )


def _classify_pdf_loaded_artifact(
    *,
    case_name: str,
    url: str,
    evidence_path: str,
    payload: Mapping[str, JsonValue],
) -> SmokeCaseResult | None:
    """分类 PDF local gate 的额外必需事实。

    Args:
        case_name: case 名称。
        url: URL。
        evidence_path: 证据路径。
        payload: diagnostics artifact。

    Returns:
        PDF 失败结果；全部通过时返回 ``None``。

    Raises:
        无。
    """

    content_type = _raw_content_type(payload).lower()
    if "pdf" not in content_type:
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_CONTENT_TYPE_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="local PDF fixture 必须返回 application/pdf content-type。",
        )
    raw_length = _raw_content_length(payload)
    if raw_length is None or raw_length <= 0:
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_CONTENT_LENGTH_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="local PDF raw response 必须包含非空 PDF bytes。",
        )
    fetch_length = _fetch_content_length(payload)
    if fetch_length is None or fetch_length < PDF_FETCH_MIN_CHARS:
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_CONTENT_LENGTH_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step=f"fetch_web_page 返回内容长度必须至少 {PDF_FETCH_MIN_CHARS} 个字符。",
        )
    evidence = _docling_evidence(payload)
    stream_name = _string_field(evidence, "stream_name")
    if (
        not _bool_field(evidence, "invoked")
        or stream_name != _PDF_EXPECTED_STREAM_NAME
        or not _bool_field(evidence, "original_completed")
    ):
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_DOCLING_INVOCATION_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step=(
                "PDF local smoke 必须观察到 Docling conversion callable 实际调用、"
                f"stream_name={_PDF_EXPECTED_STREAM_NAME} 且原始 callable 正常返回。"
            ),
        )
    return None


def _classify_browser_loaded_artifact(
    *,
    case_name: str,
    url: str,
    evidence_path: str,
    payload: Mapping[str, JsonValue],
) -> SmokeCaseResult | None:
    """分类 browser-rendered local case 的额外诊断事实。

    Args:
        case_name: case 名称。
        url: URL。
        evidence_path: 证据路径。
        payload: diagnostics artifact。

    Returns:
        diagnostic-only 结果；browser backend 被观察到时返回 ``None``。

    Raises:
        无。
    """

    if not _playwright_profile_sampled(payload):
        return _case_diagnostic_only(
            case_name=case_name,
            case_kind=_CASE_LOCAL_BROWSER,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_BROWSER_PROFILE_NOT_SAMPLED,
            reason="client-rendered fixture 未采样 Playwright profile，无法用本次 artifact 证明 browser path 环境。",
            suggested_next_step="确认 smoke 默认 browser case 未被 --skip-playwright 或旧 diagnostics 命令绕过。",
        )
    fetch_backend = _fetch_backend(payload)
    if fetch_backend != _BROWSER_EXPECTED_FETCH_BACKEND:
        return _case_diagnostic_only(
            case_name=case_name,
            case_kind=_CASE_LOCAL_BROWSER,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_BROWSER_BACKEND_NOT_OBSERVED,
            reason=(
                "client-rendered fixture 未观察到 fetch_web_page 使用 Playwright backend；"
                f"实际 backend={fetch_backend or '<missing>'}。"
            ),
            suggested_next_step="查看 raw HTML、fetch_web_page_profile 与 playwright_profile，判断是否浏览器回退未触发或 fixture 已被 requests 路径直接处理。",
        )
    return None


def _case_failure(
    *,
    case_name: str,
    case_kind: str,
    url: str,
    evidence_path: str,
    bucket: str,
    exit_code: int,
    suggested_next_step: str,
) -> SmokeCaseResult:
    """构造 failure case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        url: URL。
        evidence_path: 证据路径。
        bucket: failure bucket。
        exit_code: 退出码贡献。
        suggested_next_step: 建议下一步。

    Returns:
        failure case result。

    Raises:
        无。
    """

    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=url,
        status=_STATUS_FAILED,
        bucket=bucket,
        evidence_path=evidence_path,
        suggested_next_step=suggested_next_step,
        reason="",
        exit_code=exit_code,
    )


def _case_skip(
    *,
    case_name: str,
    case_kind: str,
    url: str,
    evidence_path: str,
    bucket: str,
    reason: str,
) -> SmokeCaseResult:
    """构造 skipped case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        url: URL。
        evidence_path: 证据路径。
        bucket: skip bucket。
        reason: 跳过原因。

    Returns:
        skipped case result。

    Raises:
        无。
    """

    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=url,
        status=_STATUS_SKIPPED,
        bucket=bucket,
        evidence_path=evidence_path,
        suggested_next_step="安装或修复 Docling runtime 后重跑 smoke。",
        reason=reason,
        exit_code=_EXIT_OK,
    )


def _case_diagnostic_only(
    *,
    case_name: str,
    case_kind: str,
    url: str,
    evidence_path: str,
    bucket: str,
    reason: str,
    suggested_next_step: str,
) -> SmokeCaseResult:
    """构造 diagnostic-only case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        url: URL。
        evidence_path: 证据路径。
        bucket: diagnostic-only bucket。
        reason: diagnostic-only 原因。
        suggested_next_step: 建议下一步。

    Returns:
        diagnostic-only case result。

    Raises:
        无。
    """

    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=url,
        status=_STATUS_DIAGNOSTIC_ONLY,
        bucket=bucket,
        evidence_path=evidence_path,
        suggested_next_step=suggested_next_step,
        reason=reason,
        exit_code=_EXIT_OK,
    )


def _classify_child_result(
    *,
    case_name: str,
    case_kind: str,
    fallback_url: str,
    artifact_path: Path,
    child_result: DiagnosticChildResult,
) -> SmokeCaseResult:
    """按子进程结果与 artifact 分类 smoke case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        fallback_url: artifact 缺少 URL 时的后备 URL。
        artifact_path: artifact 路径。
        child_result: diagnostics 子进程结果。

    Returns:
        smoke case 结果。

    Raises:
        无。
    """

    if case_kind == _CASE_EXTERNAL and child_result.returncode != _EXIT_OK:
        return _case_diagnostic_only(
            case_name=case_name,
            case_kind=case_kind,
            url=fallback_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_CHILD_PROCESS_ERROR,
            reason="外部 URL diagnostics 子进程失败；外部站点行为不作为 local smoke gate。",
            suggested_next_step="查看 diagnostics stdout/stderr 和站点可达性；必要时缩小外部样本。",
        )
    if not artifact_path.is_file():
        if case_kind == _CASE_EXTERNAL:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=fallback_url,
                evidence_path=str(artifact_path),
                bucket=_BUCKET_ARTIFACT_MISSING,
                reason="外部 diagnostics 未生成 artifact；不影响 local smoke gate。",
                suggested_next_step="检查 external URL 文件、网络和 diagnostics 子进程 stderr。",
            )
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=fallback_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_ARTIFACT_MISSING,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step="local diagnostics artifact 缺失，无法进行 smoke 判定。",
        )
    try:
        payload = _load_json_artifact(artifact_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if case_kind == _CASE_EXTERNAL:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=fallback_url,
                evidence_path=str(artifact_path),
                bucket=_BUCKET_ARTIFACT_PARSE_FAILURE,
                reason=f"外部 diagnostics artifact 无法解析：{exc}",
                suggested_next_step="检查外部 diagnostics artifact 是否完整写入。",
            )
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=fallback_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_ARTIFACT_PARSE_FAILURE,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step=f"local diagnostics artifact 无法解析：{exc}",
        )
    return _classify_loaded_artifact(
        case_name=case_name,
        case_kind=case_kind,
        fallback_url=fallback_url,
        artifact_path=artifact_path,
        payload=payload,
        child_returncode=child_result.returncode,
    )


def _summary_from_cases(
    *,
    run_label: str,
    output_dir: Path,
    local_cases: Sequence[SmokeCaseResult],
    external_cases: Sequence[SmokeCaseResult],
    search_cases: Sequence[SmokeCaseResult] = (),
    extra_skips: Sequence[SmokeItem] = (),
) -> SmokeSummary:
    """按 case 结果构造 smoke summary。

    Args:
        run_label: 运行标签。
        output_dir: 输出目录。
        local_cases: local case 列表。
        external_cases: external case 列表。
        search_cases: search provider case 列表。
        extra_skips: 不属于具体 case、但需要进入 summary 的 skip 信号。

    Returns:
        smoke summary。

    Raises:
        无。
    """

    all_cases = tuple(local_cases) + tuple(external_cases) + tuple(search_cases)
    failures = tuple(case.to_item() for case in all_cases if case.status == _STATUS_FAILED)
    skips = tuple(case.to_item() for case in all_cases if case.status == _STATUS_SKIPPED) + tuple(extra_skips)
    diagnostic_only = tuple(case.to_item() for case in all_cases if case.status == _STATUS_DIAGNOSTIC_ONLY)
    local_exit_code = _EXIT_OK
    hard_gate_cases = tuple(local_cases) + tuple(search_cases)
    if any(case.exit_code == _EXIT_SCHEMA_OR_INFRA_FAILURE for case in hard_gate_cases):
        local_exit_code = _EXIT_SCHEMA_OR_INFRA_FAILURE
    elif any(case.exit_code == _EXIT_LOCAL_FAILURE for case in hard_gate_cases):
        local_exit_code = _EXIT_LOCAL_FAILURE

    if local_exit_code != _EXIT_OK:
        status = _STATUS_FAILED
    elif any(case.status == _STATUS_PASSED for case in local_cases):
        status = _STATUS_PASSED
    elif diagnostic_only:
        status = _STATUS_DIAGNOSTIC_ONLY
    else:
        status = _STATUS_SKIPPED

    return SmokeSummary(
        status=status,
        exit_code=local_exit_code,
        run_label=run_label,
        output_dir=str(output_dir),
        failures=failures,
        skips=skips,
        diagnostic_only=diagnostic_only,
        local_cases=tuple(local_cases),
        external_cases=tuple(external_cases),
        search_cases=tuple(search_cases),
    )


def _summary_markdown(summary: SmokeSummary) -> str:
    """构造 Codex 可读 Markdown summary。

    Args:
        summary: smoke summary。

    Returns:
        Markdown 文本。

    Raises:
        无。
    """

    lines = [
        f"# Web CI Smoke Summary - {summary.run_label}",
        "",
        f"- status: {summary.status}",
        f"- exit_code: {summary.exit_code}",
        f"- output_dir: {summary.output_dir}",
        f"- local_cases: {len(summary.local_cases)}",
        f"- external_cases: {len(summary.external_cases)}",
        f"- search_cases: {len(summary.search_cases)}",
    ]
    lines.extend(_markdown_items("Failures", summary.failures))
    lines.extend(_markdown_items("Skips", summary.skips))
    lines.extend(_markdown_items("Diagnostic Only", summary.diagnostic_only))
    return "\n".join(lines) + "\n"


def _markdown_items(title: str, items: Sequence[SmokeItem]) -> list[str]:
    """构造 Markdown item 章节。

    Args:
        title: 章节标题。
        items: summary item 列表。

    Returns:
        Markdown 行列表。

    Raises:
        无。
    """

    lines = ["", f"## {title}", ""]
    if not items:
        lines.append("- 无")
        return lines
    for item in items:
        detail = item.reason or item.suggested_next_step
        lines.append(f"- bucket={item.bucket} url={item.url} evidence={item.evidence_path} detail={detail}")
    return lines


def _write_summary(summary: SmokeSummary) -> None:
    """写 summary.json 与 summary.md。

    Args:
        summary: smoke summary。

    Returns:
        无。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    output_dir = Path(summary.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "summary.json", summary.to_json())
    (output_dir / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")


def _read_external_urls(path: Path, *, limit: int) -> list[str]:
    """读取外部 URL 样本并应用上限。

    Args:
        path: URL 文件路径，支持 JSONL 对象/字符串或纯文本。
        limit: 最多返回数量；``0`` 表示不返回样本。

    Returns:
        URL 字符串列表。

    Raises:
        ValueError: 输入文件不存在、JSONL 非法或 URL 为空时抛出。
        OSError: 文件读取失败时抛出。
    """

    if not path.is_file():
        raise ValueError(f"external URL 文件不存在: {path}")
    urls: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if limit >= 0 and len(urls) >= limit:
            break
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if path.suffix.lower() in _JSONL_SUFFIXES:
            urls.append(_url_from_jsonl_line(line, line_number))
        else:
            urls.append(line)
    return urls


def _validate_external_url_file(path: Path) -> None:
    """校验 external URL 文件内容，不做采样截断。

    Args:
        path: URL 文件路径，支持 JSONL 对象/字符串或纯文本。

    Returns:
        无。

    Raises:
        ValueError: 输入文件不存在、JSONL 非法或 URL 字符串非法时抛出。
        OSError: 文件读取失败时抛出。
    """

    if not path.is_file():
        raise ValueError(f"external URL 文件不存在: {path}")
    is_jsonl = path.suffix.lower() in _JSONL_SUFFIXES
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        url = _url_from_jsonl_line(line, line_number) if is_jsonl else line
        _validate_external_url_text(url, line_number)


def _validate_external_url_text(url: str, line_number: int) -> None:
    """校验 external URL 字符串可交给 diagnostics 处理。

    Args:
        url: URL 字符串；允许省略 scheme，此时 diagnostics 会按 HTTPS 处理。
        line_number: URL 文件中的行号。

    Returns:
        无。

    Raises:
        ValueError: URL 为空或不是 HTTP/HTTPS 目标时抛出。
    """

    raw_url = url.strip()
    normalized_url = raw_url if "://" in raw_url else f"https://{raw_url}"
    parsed = urlparse(normalized_url)
    if parsed.scheme.lower() not in _EXTERNAL_URL_SCHEMES or not parsed.netloc:
        raise ValueError(f"external URL 文件第 {line_number} 行不是 http/https URL: {url}")


def _url_from_jsonl_line(line: str, line_number: int) -> str:
    """从 JSONL 行读取 URL。

    Args:
        line: JSONL 原始行。
        line_number: 行号。

    Returns:
        URL 字符串。

    Raises:
        ValueError: JSON 或 URL 字段非法时抛出。
    """

    try:
        value = cast(JsonValue, json.loads(line))
    except json.JSONDecodeError as exc:
        raise ValueError(f"external URL JSONL 第 {line_number} 行非法: {exc}") from exc
    if isinstance(value, str):
        url = value.strip()
    elif isinstance(value, Mapping):
        raw_url = value.get("url")
        url = raw_url.strip() if isinstance(raw_url, str) else ""
    else:
        url = ""
    if not url:
        raise ValueError(f"external URL JSONL 第 {line_number} 行缺少 url。")
    return url


def _run_diagnostic_command(command: Sequence[str]) -> DiagnosticChildResult:
    """执行 diagnostics 子进程。

    Args:
        command: 子进程命令。

    Returns:
        子进程结果。

    Raises:
        OSError: 进程启动失败时抛出。
    """

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return DiagnosticChildResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _log_diagnostic_child_result(*, case_name: str, child_result: DiagnosticChildResult) -> None:
    """记录 diagnostics 子进程的有界输出前缀。

    Args:
        case_name: smoke case 名称。
        child_result: diagnostics 子进程结果。

    Returns:
        无。

    Raises:
        无。
    """

    _LOGGER.debug(
        "diagnostics child finished: case=%s returncode=%s stdout_prefix=%s stderr_prefix=%s",
        case_name,
        child_result.returncode,
        _stdio_log_prefix(child_result.stdout),
        _stdio_log_prefix(child_result.stderr),
    )


def _diagnostic_command(
    *,
    url: str,
    artifact_path: Path,
    options: SmokeOptions,
    allow_private_network_url: bool,
    sample_playwright: bool,
) -> list[str]:
    """构造单 URL diagnostics 命令。

    Args:
        url: 待诊断 URL。
        artifact_path: diagnostics 输出 artifact。
        options: smoke 选项。
        allow_private_network_url: 是否允许 diagnostics 访问内网或本地 URL。
        sample_playwright: 是否让 diagnostics 采样 Playwright。

    Returns:
        子进程命令参数列表。

    Raises:
        无。
    """

    command = [
        sys.executable,
        "-m",
        "utils.diagnose_web_access",
        "--url",
        url,
        "--output",
        str(artifact_path),
        "--request-timeout",
        str(options.request_timeout),
        "--tool-timeout-budget",
        str(options.tool_timeout_budget),
    ]
    if allow_private_network_url:
        command.append("--allow-private-network-url")
    if not sample_playwright:
        command.append("--skip-playwright")
    return command


def _run_local_assembly_config_case(
    *,
    fixture_urls: LocalFixtureUrls,
    diagnostics_dir: Path,
) -> SmokeCaseResult:
    """运行本地 Web config assembly hard gate。

    Args:
        fixture_urls: 本地 fixture URL 集合。
        diagnostics_dir: local diagnostics 输出目录。

    Returns:
        assembly config case 结果。

    Raises:
        OSError: overlay 或 artifact 写入失败时抛出。
    """

    case_name = "local-assembly-config"
    artifact_path = diagnostics_dir / "local-assembly-config.json"
    workspace_config_dir = diagnostics_dir / "assembly-workspace-config"
    provider_config = dict(_ASSEMBLY_PROVIDER_CONFIG)
    _write_web_tool_discovery_overlay(
        workspace_config_dir,
        provider_config=provider_config,
    )
    try:
        config = _load_runtime_config_for_overlay(workspace_config_dir)
    except Exception as exc:
        return _assembly_failure_result(
            case_name=case_name,
            url=fixture_urls.html_url,
            artifact_path=artifact_path,
            provider_config=provider_config,
            bucket=_BUCKET_WEB_CONFIG_LOADER_FAILURE,
            error=exc,
            suggested_next_step="检查 ConfigLoader.load 是否能读取包内默认配置与 workspace tool_discovery overlay。",
        )
    try:
        definitions = _discover_tools_by_name(config, workspace_root=diagnostics_dir)
    except Exception as exc:
        return _assembly_failure_result(
            case_name=case_name,
            url=fixture_urls.html_url,
            artifact_path=artifact_path,
            provider_config=provider_config,
            bucket=_BUCKET_WEB_ASSEMBLY_DISCOVERY_FAILURE,
            error=exc,
            suggested_next_step="检查 discover_service_tools 是否能通过 web-tools provider 完成工具发现。",
        )

    tool_names = tuple(definitions)
    fetch_definition = definitions.get("fetch_web_page")
    if fetch_definition is None:
        _write_assembly_artifact(
            artifact_path=artifact_path,
            url=fixture_urls.html_url,
            tool_names=tool_names,
            provider_config=provider_config,
            fetch_ok=False,
            content_length=0,
            content_contains_fixture_text=False,
            truncate_max_chars=None,
            bucket=_BUCKET_WEB_TOOL_MISSING,
            suggested_next_step="检查 web-tools provider 是否仍发现 fetch_web_page。",
        )
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
            url=fixture_urls.html_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_WEB_TOOL_MISSING,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step="检查 web-tools provider 是否仍发现 fetch_web_page。",
        )

    truncate_max_chars = _truncate_max_chars(fetch_definition)
    if truncate_max_chars != _ASSEMBLY_FETCH_TRUNCATE_CHARS:
        _write_assembly_artifact(
            artifact_path=artifact_path,
            url=fixture_urls.html_url,
            tool_names=tool_names,
            provider_config=provider_config,
            fetch_ok=False,
            content_length=0,
            content_contains_fixture_text=False,
            truncate_max_chars=truncate_max_chars,
            bucket=_BUCKET_WEB_ASSEMBLY_CONFIG_MISMATCH,
            suggested_next_step="检查 fetch_truncate_chars 是否从 provider config 闭进 fetch_web_page truncate spec。",
        )
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
            url=fixture_urls.html_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_WEB_ASSEMBLY_CONFIG_MISMATCH,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="检查 fetch_truncate_chars 是否从 provider config 闭进 fetch_web_page truncate spec。",
        )

    outcome = asyncio.run(
        fetch_definition.callable(
            _tool_call("fetch_web_page", {"url": fixture_urls.html_url}),
            _tool_context(),
        )
    )
    if isinstance(outcome, ToolFailedOutcome):
        _write_assembly_artifact(
            artifact_path=artifact_path,
            url=fixture_urls.html_url,
            tool_names=tool_names,
            provider_config=provider_config,
            fetch_ok=False,
            content_length=0,
            content_contains_fixture_text=False,
            truncate_max_chars=truncate_max_chars,
            bucket=_BUCKET_WEB_ASSEMBLY_FETCH_FAILURE,
            suggested_next_step=outcome.result.hint or "检查 fetch_web_page callable 的本地 fixture 抓取路径。",
        )
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
            url=fixture_urls.html_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_WEB_ASSEMBLY_FETCH_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step=outcome.result.hint or "检查 fetch_web_page callable 的本地 fixture 抓取路径。",
        )
    if not isinstance(outcome, ToolCompletedOutcome):
        _write_assembly_artifact(
            artifact_path=artifact_path,
            url=fixture_urls.html_url,
            tool_names=tool_names,
            provider_config=provider_config,
            fetch_ok=False,
            content_length=0,
            content_contains_fixture_text=False,
            truncate_max_chars=truncate_max_chars,
            bucket=_BUCKET_WEB_ASSEMBLY_FETCH_FAILURE,
            suggested_next_step="fetch_web_page callable 返回未知 outcome 类型。",
        )
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
            url=fixture_urls.html_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_WEB_ASSEMBLY_FETCH_FAILURE,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step="fetch_web_page callable 返回未知 outcome 类型。",
        )

    value = _mapping_or_empty(outcome.result.value)
    content = _string_field(value, "content")
    content_contains_fixture_text = _HTML_FIXTURE_BODY in content
    content_length = len(content)
    if not content_contains_fixture_text:
        _write_assembly_artifact(
            artifact_path=artifact_path,
            url=fixture_urls.html_url,
            tool_names=tool_names,
            provider_config=provider_config,
            fetch_ok=True,
            content_length=content_length,
            content_contains_fixture_text=False,
            truncate_max_chars=truncate_max_chars,
            bucket=_BUCKET_WEB_ASSEMBLY_FETCH_CONTENT_FAILURE,
            suggested_next_step="fetch_web_page 成功但未返回 local HTML fixture 正文，检查内容抽取或 URL 路径。",
        )
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
            url=fixture_urls.html_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_WEB_ASSEMBLY_FETCH_CONTENT_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="fetch_web_page 成功但未返回 local HTML fixture 正文，检查内容抽取或 URL 路径。",
        )

    _write_assembly_artifact(
        artifact_path=artifact_path,
        url=fixture_urls.html_url,
        tool_names=tool_names,
        provider_config=provider_config,
        fetch_ok=True,
        content_length=content_length,
        content_contains_fixture_text=True,
        truncate_max_chars=truncate_max_chars,
        bucket=_BUCKET_PASSED,
        suggested_next_step="",
    )
    return SmokeCaseResult(
        case_name=case_name,
        case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
        url=fixture_urls.html_url,
        status=_STATUS_PASSED,
        bucket=_BUCKET_PASSED,
        evidence_path=str(artifact_path),
        suggested_next_step="",
        reason="",
        exit_code=_EXIT_OK,
    )


def _assembly_failure_result(
    *,
    case_name: str,
    url: str,
    artifact_path: Path,
    provider_config: Mapping[str, JsonValue],
    bucket: str,
    error: Exception,
    suggested_next_step: str,
) -> SmokeCaseResult:
    """构造 assembly 失败结果并写入 artifact。

    Args:
        case_name: case 名称。
        url: 目标 URL。
        artifact_path: artifact 路径。
        provider_config: Web provider config。
        bucket: failure bucket。
        error: 捕获到的异常。
        suggested_next_step: 建议下一步。

    Returns:
        failure case result。

    Raises:
        OSError: artifact 写入失败时抛出。
    """

    _write_assembly_artifact(
        artifact_path=artifact_path,
        url=url,
        tool_names=(),
        provider_config=provider_config,
        fetch_ok=False,
        content_length=0,
        content_contains_fixture_text=False,
        truncate_max_chars=None,
        bucket=bucket,
        suggested_next_step=suggested_next_step,
        error_type=type(error).__name__,
        error_summary=str(error),
    )
    return _case_failure(
        case_name=case_name,
        case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
        url=url,
        evidence_path=str(artifact_path),
        bucket=bucket,
        exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
        suggested_next_step=suggested_next_step,
    )


def _write_assembly_artifact(
    *,
    artifact_path: Path,
    url: str,
    tool_names: Sequence[str],
    provider_config: Mapping[str, JsonValue],
    fetch_ok: bool,
    content_length: int,
    content_contains_fixture_text: bool,
    truncate_max_chars: int | None,
    bucket: str,
    suggested_next_step: str,
    error_type: str = "",
    error_summary: str = "",
) -> None:
    """写入 local assembly config artifact。

    Args:
        artifact_path: artifact 路径。
        url: 抓取 URL。
        tool_names: 发现到的工具名。
        provider_config: Web provider config。
        fetch_ok: fetch_web_page 是否成功。
        content_length: 返回正文长度。
        content_contains_fixture_text: 正文是否包含 fixture 文本。
        truncate_max_chars: 观察到的 truncate max chars。
        bucket: 分类 bucket。
        suggested_next_step: 建议下一步。
        error_type: 可选错误类型。
        error_summary: 可选错误摘要。

    Returns:
        无。

    Raises:
        OSError: artifact 写入失败时抛出。
    """

    _write_json(
        artifact_path,
        {
            "schema_version": _ASSEMBLY_SCHEMA_VERSION,
            "case_kind": _CASE_LOCAL_ASSEMBLY_CONFIG,
            "url": url,
            "tool_names": list(tool_names),
            "provider_config": dict(provider_config),
            "called_tool": "fetch_web_page",
            "fetch_ok": fetch_ok,
            "content_length": content_length,
            "content_contains_fixture_text": content_contains_fixture_text,
            "truncate_max_chars": truncate_max_chars,
            "assembly_path": _ASSEMBLY_PATH_LABEL,
            "bucket": bucket,
            "suggested_next_step": suggested_next_step,
            "error_type": error_type,
            "error_summary": error_summary,
        },
    )


def _run_local_cases(*, options: SmokeOptions, runner: DiagnosticRunner) -> list[SmokeCaseResult]:
    """运行本地 fetch_web_page path matrix smoke cases。

    Args:
        options: smoke 选项。
        runner: diagnostics 子进程 runner。

    Returns:
        local case 结果列表。

    Raises:
        OSError: local server、artifact 目录或子进程启动失败时抛出。
    """

    diagnostics_dir = options.output_dir / "diagnostics" / "local"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    results: list[SmokeCaseResult] = []
    with _running_local_fixture_server() as fixture_urls:
        _LOGGER.info(
            "local fixture server started: html=%s pdf=%s browser=%s",
            fixture_urls.html_url,
            fixture_urls.pdf_url,
            fixture_urls.browser_url,
        )
        local_cases = (
            (
                "local-html",
                _CASE_LOCAL_HTML,
                fixture_urls.html_url,
                diagnostics_dir / "local-html.json",
                False,
            ),
            (
                "local-pdf",
                _CASE_LOCAL_PDF,
                fixture_urls.pdf_url,
                diagnostics_dir / "local-pdf.json",
                False,
            ),
            (
                "local-browser",
                _CASE_LOCAL_BROWSER,
                fixture_urls.browser_url,
                diagnostics_dir / "local-browser.json",
                True,
            ),
        )
        for case_name, case_kind, url, artifact_path, sample_playwright in local_cases:
            _LOGGER.debug(
                "running local smoke case: case=%s kind=%s sample_playwright=%s artifact=%s",
                case_name,
                case_kind,
                sample_playwright,
                artifact_path,
            )
            command = _diagnostic_command(
                url=url,
                artifact_path=artifact_path,
                options=options,
                allow_private_network_url=True,
                sample_playwright=sample_playwright,
            )
            child_result = runner(command)
            _log_diagnostic_child_result(case_name=case_name, child_result=child_result)
            case_result = _classify_child_result(
                case_name=case_name,
                case_kind=case_kind,
                fallback_url=url,
                artifact_path=artifact_path,
                child_result=child_result,
            )
            results.append(case_result)
            _LOGGER.debug(
                "classified local smoke case: case=%s status=%s bucket=%s exit_code=%s evidence=%s",
                case_result.case_name,
                case_result.status,
                case_result.bucket,
                case_result.exit_code,
                case_result.evidence_path,
            )
            if (
                case_result.case_kind == _CASE_LOCAL_PDF
                and case_result.status == _STATUS_FAILED
                and case_result.bucket == _BUCKET_PDF_DOCLING_INVOCATION_FAILURE
            ):
                _LOGGER.warning(
                    "stopping local matrix after Docling invocation blocker: evidence=%s",
                    case_result.evidence_path,
                )
                break
        if not _has_docling_invocation_blocker(results):
            assembly_case = _run_local_assembly_config_case(
                fixture_urls=fixture_urls,
                diagnostics_dir=diagnostics_dir,
            )
            results.append(assembly_case)
            _LOGGER.debug(
                "classified local assembly config case: case=%s status=%s bucket=%s exit_code=%s evidence=%s",
                assembly_case.case_name,
                assembly_case.status,
                assembly_case.bucket,
                assembly_case.exit_code,
                assembly_case.evidence_path,
            )
    return results


def _run_external_cases(*, options: SmokeOptions, runner: DiagnosticRunner) -> list[SmokeCaseResult]:
    """运行 external diagnostic-only cases。

    Args:
        options: smoke 选项。
        runner: diagnostics 子进程 runner。

    Returns:
        external case 结果列表。

    Raises:
        ValueError: external URL 输入非法时抛出。
        OSError: 文件读写或子进程启动失败时抛出。
    """

    if options.external_url_file is None:
        _LOGGER.info("external diagnostic-only cases disabled")
        return []
    urls = _read_external_urls(options.external_url_file, limit=options.external_limit)
    _LOGGER.info("external diagnostic-only cases loaded: file=%s count=%s", options.external_url_file, len(urls))
    diagnostics_dir = options.output_dir / "diagnostics" / "external"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    results: list[SmokeCaseResult] = []
    for index, url in enumerate(urls, start=1):
        artifact_path = diagnostics_dir / f"external-{index:04d}.json"
        _LOGGER.debug("running external diagnostic case: index=%s artifact=%s", index, artifact_path)
        command = _diagnostic_command(
            url=url,
            artifact_path=artifact_path,
            options=options,
            allow_private_network_url=False,
            sample_playwright=options.include_playwright,
        )
        child_result = runner(command)
        _log_diagnostic_child_result(case_name=f"external-{index:04d}", child_result=child_result)
        case_result = _classify_child_result(
            case_name=f"external-{index:04d}",
            case_kind=_CASE_EXTERNAL,
            fallback_url=url,
            artifact_path=artifact_path,
            child_result=child_result,
        )
        results.append(case_result)
        _LOGGER.debug(
            "classified external diagnostic case: case=%s status=%s bucket=%s evidence=%s",
            case_result.case_name,
            case_result.status,
            case_result.bucket,
            case_result.evidence_path,
        )
    return results


def _run_search_provider_cases(*, options: SmokeOptions) -> list[SmokeCaseResult]:
    """运行 search_web provider diagnostic-only cases。

    Args:
        options: smoke 选项。

    Returns:
        search provider case 结果列表。

    Raises:
        OSError: overlay 或 artifact 写入失败时抛出。
    """

    diagnostics_dir = options.output_dir / "diagnostics" / "search"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    results: list[SmokeCaseResult] = []
    for provider in _SEARCH_PROVIDERS:
        case_name = f"search-provider-{provider}"
        artifact_path = diagnostics_dir / f"{case_name}.json"
        workspace_config_dir = diagnostics_dir / f"{case_name}-workspace-config"
        provider_config: JsonObject = {
            "provider": provider,
            "request_timeout_seconds": options.request_timeout,
            "max_search_results": 3,
            "fetch_truncate_chars": _SEARCH_FETCH_TRUNCATE_CHARS,
            "allow_private_network_url": False,
            "playwright_channel": "chrome",
            "playwright_storage_state_dir": "",
        }
        _write_web_tool_discovery_overlay(
            workspace_config_dir,
            provider_config=provider_config,
        )
        result = _run_single_search_provider_case(
            case_name=case_name,
            provider=provider,
            provider_config=provider_config,
            workspace_config_dir=workspace_config_dir,
            artifact_path=artifact_path,
            workspace_root=options.output_dir,
        )
        results.append(result)
        _LOGGER.debug(
            "classified search provider diagnostic case: case=%s status=%s bucket=%s evidence=%s",
            result.case_name,
            result.status,
            result.bucket,
            result.evidence_path,
        )
    return results


def _run_single_search_provider_case(
    *,
    case_name: str,
    provider: str,
    provider_config: Mapping[str, JsonValue],
    workspace_config_dir: Path,
    artifact_path: Path,
    workspace_root: Path,
) -> SmokeCaseResult:
    """运行单个 search provider diagnostic case。

    Args:
        case_name: case 名称。
        provider: search provider 策略。
        provider_config: Web provider config。
        workspace_config_dir: workspace config overlay 目录。
        artifact_path: artifact 路径。
        workspace_root: 当前 smoke 的 workspace root。

    Returns:
        smoke case 结果。

    Raises:
        OSError: artifact 写入失败时抛出。
    """

    api_key_env = _SEARCH_API_KEY_ENVS.get(provider, "")
    api_key_present = bool(api_key_env and os.environ.get(api_key_env, "").strip())
    try:
        config = _load_runtime_config_for_overlay(workspace_config_dir)
    except Exception as exc:
        return _search_failure_case(
            case_name=case_name,
            provider=provider,
            artifact_path=artifact_path,
            provider_config=provider_config,
            bucket=_BUCKET_WEB_CONFIG_LOADER_FAILURE,
            status=_STATUS_FAILED,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            api_key_env=api_key_env,
            api_key_present=api_key_present,
            error_type=type(exc).__name__,
            error_summary=str(exc),
            suggested_next_step="检查 search provider overlay 是否能由 ConfigLoader.load 完整加载。",
        )
    try:
        definitions = _discover_tools_by_name(config, workspace_root=workspace_root)
    except Exception as exc:
        return _search_failure_case(
            case_name=case_name,
            provider=provider,
            artifact_path=artifact_path,
            provider_config=provider_config,
            bucket=_BUCKET_WEB_ASSEMBLY_DISCOVERY_FAILURE,
            status=_STATUS_FAILED,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            api_key_env=api_key_env,
            api_key_present=api_key_present,
            error_type=type(exc).__name__,
            error_summary=str(exc),
            suggested_next_step="检查 discover_service_tools 是否能装配 search_web。",
        )

    definition = definitions.get("search_web")
    if definition is None:
        return _search_failure_case(
            case_name=case_name,
            provider=provider,
            artifact_path=artifact_path,
            provider_config=provider_config,
            bucket=_BUCKET_WEB_TOOL_MISSING,
            status=_STATUS_FAILED,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            api_key_env=api_key_env,
            api_key_present=api_key_present,
            error_type="ToolMissing",
            error_summary="search_web not discovered",
            suggested_next_step="检查 web-tools provider 是否仍发现 search_web。",
        )

    try:
        outcome = asyncio.run(
            definition.callable(
                _tool_call("search_web", {"query": _SEARCH_PROVIDER_QUERY}),
                _tool_context(),
            )
        )
    except Exception as exc:
        bucket = _classify_search_exception(provider=provider, error=exc)
        return _search_failure_case(
            case_name=case_name,
            provider=provider,
            artifact_path=artifact_path,
            provider_config=provider_config,
            bucket=bucket,
            status=_STATUS_DIAGNOSTIC_ONLY,
            exit_code=_EXIT_OK,
            api_key_env=api_key_env,
            api_key_present=api_key_present,
            error_type=type(exc).__name__,
            error_summary=str(exc),
            suggested_next_step=_search_suggested_next_step(bucket=bucket, provider=provider),
        )

    if isinstance(outcome, ToolFailedOutcome):
        error_summary = " ".join(
            item
            for item in (
                outcome.result.error,
                outcome.result.message,
                outcome.result.hint or "",
            )
            if item
        )
        bucket = _classify_search_error_text(
            provider=provider,
            error_text=error_summary,
            api_key_present=api_key_present,
        )
        return _search_failure_case(
            case_name=case_name,
            provider=provider,
            artifact_path=artifact_path,
            provider_config=provider_config,
            bucket=bucket,
            status=_STATUS_DIAGNOSTIC_ONLY,
            exit_code=_EXIT_OK,
            api_key_env=api_key_env,
            api_key_present=api_key_present,
            error_type=outcome.result.error,
            error_summary=error_summary,
            suggested_next_step=_search_suggested_next_step(bucket=bucket, provider=provider),
        )
    if not isinstance(outcome, ToolCompletedOutcome):
        return _search_failure_case(
            case_name=case_name,
            provider=provider,
            artifact_path=artifact_path,
            provider_config=provider_config,
            bucket=_BUCKET_SEARCH_TOOL_EXECUTION_ERROR,
            status=_STATUS_DIAGNOSTIC_ONLY,
            exit_code=_EXIT_OK,
            api_key_env=api_key_env,
            api_key_present=api_key_present,
            error_type="UnknownOutcome",
            error_summary=f"unknown outcome type: {type(outcome).__name__}",
            suggested_next_step="检查 search_web adapter outcome 投影。",
        )

    value = _mapping_or_empty(outcome.result.value)
    result_total = _int_field(value, "total") or 0
    preferred_result = _nested_object(value, "preferred_result")
    preferred_result_url = _string_field(preferred_result, "url")
    if provider in _SEARCH_API_KEY_ENVS and not api_key_present:
        bucket = _BUCKET_PROVIDER_KEY_MISSING
    elif result_total > 0:
        bucket = _BUCKET_SEARCH_PROVIDER_PASSED
    else:
        bucket = _BUCKET_PROVIDER_NO_RESULTS
    _write_search_artifact(
        artifact_path=artifact_path,
        provider=provider,
        provider_config=provider_config,
        bucket=bucket,
        status=_STATUS_DIAGNOSTIC_ONLY,
        api_key_env=api_key_env,
        api_key_present=api_key_present,
        result_total=result_total,
        preferred_result_url=preferred_result_url,
        error_type="",
        error_summary="",
        suggested_next_step=_search_suggested_next_step(bucket=bucket, provider=provider),
    )
    return _case_diagnostic_only(
        case_name=case_name,
        case_kind=_CASE_SEARCH_PROVIDER,
        url="",
        evidence_path=str(artifact_path),
        bucket=bucket,
        reason="search provider case 只作为 diagnostic-only，不影响 local fetch hard gate。",
        suggested_next_step=_search_suggested_next_step(bucket=bucket, provider=provider),
    )


def _search_failure_case(
    *,
    case_name: str,
    provider: str,
    artifact_path: Path,
    provider_config: Mapping[str, JsonValue],
    bucket: str,
    status: str,
    exit_code: int,
    api_key_env: str,
    api_key_present: bool,
    error_type: str,
    error_summary: str,
    suggested_next_step: str,
) -> SmokeCaseResult:
    """构造 search provider case 失败或诊断结果。

    Args:
        case_name: case 名称。
        provider: search provider 策略。
        artifact_path: artifact 路径。
        provider_config: Web provider config。
        bucket: 分类 bucket。
        status: case 状态。
        exit_code: 退出码贡献。
        api_key_env: API key 环境变量名。
        api_key_present: API key 是否存在。
        error_type: 错误类型。
        error_summary: 错误摘要。
        suggested_next_step: 建议下一步。

    Returns:
        smoke case result。

    Raises:
        OSError: artifact 写入失败时抛出。
    """

    _write_search_artifact(
        artifact_path=artifact_path,
        provider=provider,
        provider_config=provider_config,
        bucket=bucket,
        status=status,
        api_key_env=api_key_env,
        api_key_present=api_key_present,
        result_total=0,
        preferred_result_url="",
        error_type=error_type,
        error_summary=error_summary,
        suggested_next_step=suggested_next_step,
    )
    if status == _STATUS_FAILED:
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_SEARCH_PROVIDER,
            url="",
            evidence_path=str(artifact_path),
            bucket=bucket,
            exit_code=exit_code,
            suggested_next_step=suggested_next_step,
        )
    return _case_diagnostic_only(
        case_name=case_name,
        case_kind=_CASE_SEARCH_PROVIDER,
        url="",
        evidence_path=str(artifact_path),
        bucket=bucket,
        reason="search provider case 只作为 diagnostic-only，不影响 local fetch hard gate。",
        suggested_next_step=suggested_next_step,
    )


def _write_search_artifact(
    *,
    artifact_path: Path,
    provider: str,
    provider_config: Mapping[str, JsonValue],
    bucket: str,
    status: str,
    api_key_env: str,
    api_key_present: bool,
    result_total: int,
    preferred_result_url: str,
    error_type: str,
    error_summary: str,
    suggested_next_step: str,
) -> None:
    """写入 search provider diagnostic artifact。

    Args:
        artifact_path: artifact 路径。
        provider: search provider 策略。
        provider_config: Web provider config。
        bucket: 分类 bucket。
        status: case 状态。
        api_key_env: API key 环境变量名。
        api_key_present: API key 是否存在。
        result_total: 搜索结果数量。
        preferred_result_url: 首选结果 URL。
        error_type: 错误类型。
        error_summary: 错误摘要。
        suggested_next_step: 建议下一步。

    Returns:
        无。

    Raises:
        OSError: artifact 写入失败时抛出。
    """

    _write_json(
        artifact_path,
        {
            "schema_version": _SEARCH_SCHEMA_VERSION,
            "case_kind": _CASE_SEARCH_PROVIDER,
            "provider": provider,
            "query": _SEARCH_PROVIDER_QUERY,
            "status": status,
            "bucket": bucket,
            "api_key_env": api_key_env,
            "api_key_present": api_key_present,
            "provider_config": dict(provider_config),
            "tool_name": "search_web",
            "assembly_path": _ASSEMBLY_PATH_LABEL,
            "result_total": result_total,
            "preferred_result_url": preferred_result_url,
            "error_type": error_type,
            "error_summary": error_summary,
            "suggested_next_step": suggested_next_step,
        },
    )


def _classify_search_exception(*, provider: str, error: Exception) -> str:
    """按异常类型分类 search provider diagnostic bucket。

    Args:
        provider: search provider 策略。
        error: 捕获到的异常。

    Returns:
        search diagnostic bucket。

    Raises:
        无。
    """

    if isinstance(error, requests.HTTPError):
        response = error.response
        status_code = response.status_code if response is not None else 0
        return _classify_search_http_status(status_code)
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return _BUCKET_PROVIDER_NETWORK_FAILURE
    if isinstance(error, json.JSONDecodeError):
        return _BUCKET_PROVIDER_RESPONSE_PARSE_FAILURE
    return _classify_search_error_text(
        provider=provider,
        error_text=str(error),
        api_key_present=_provider_api_key_present(provider),
    )


def _classify_search_http_status(status_code: int) -> str:
    """按 HTTP 状态码分类 search provider diagnostic bucket。

    Args:
        status_code: HTTP 状态码。

    Returns:
        search diagnostic bucket。

    Raises:
        无。
    """

    if status_code in {401, 403}:
        return _BUCKET_PROVIDER_AUTH_FAILURE
    if status_code == 429:
        return _BUCKET_PROVIDER_QUOTA_OR_RATE_LIMITED
    return _BUCKET_PROVIDER_UNAVAILABLE


def _classify_search_error_text(
    *,
    provider: str,
    error_text: str,
    api_key_present: bool,
) -> str:
    """按错误文本分类 search provider diagnostic bucket。

    Args:
        provider: search provider 策略。
        error_text: 错误摘要。
        api_key_present: API key 是否存在。

    Returns:
        search diagnostic bucket。

    Raises:
        无。
    """

    normalized = error_text.lower()
    if provider in _SEARCH_API_KEY_ENVS and not api_key_present:
        return _BUCKET_PROVIDER_KEY_MISSING
    if "api_key" in normalized and "未配置" in normalized:
        return _BUCKET_PROVIDER_KEY_MISSING
    if "unauthorized" in normalized or "forbidden" in normalized or "invalid key" in normalized:
        return _BUCKET_PROVIDER_AUTH_FAILURE
    if "quota" in normalized or "rate limit" in normalized or "too many requests" in normalized:
        return _BUCKET_PROVIDER_QUOTA_OR_RATE_LIMITED
    if "timeout" in normalized or "connection" in normalized or "dns" in normalized or "tls" in normalized:
        return _BUCKET_PROVIDER_NETWORK_FAILURE
    if "json" in normalized or "parse" in normalized or "unexpected response" in normalized:
        return _BUCKET_PROVIDER_RESPONSE_PARSE_FAILURE
    if "所有 provider 均不可用" in error_text:
        return _BUCKET_PROVIDER_UNAVAILABLE
    return _BUCKET_SEARCH_TOOL_EXECUTION_ERROR


def _provider_api_key_present(provider: str) -> bool:
    """判断 provider 对应 API key 是否存在。

    Args:
        provider: search provider 策略。

    Returns:
        依赖 key 且环境变量非空时返回 ``True``；无 key provider 返回 ``False``。

    Raises:
        无。
    """

    env_name = _SEARCH_API_KEY_ENVS.get(provider, "")
    return bool(env_name and os.environ.get(env_name, "").strip())


def _search_suggested_next_step(*, bucket: str, provider: str) -> str:
    """为 search provider diagnostic bucket 生成建议。

    Args:
        bucket: 分类 bucket。
        provider: search provider 策略。

    Returns:
        建议下一步。

    Raises:
        无。
    """

    if bucket == _BUCKET_SEARCH_PROVIDER_PASSED:
        return "search_web provider path 已产生结果；该 case 仍只作为 diagnostic-only。"
    if bucket == _BUCKET_PROVIDER_KEY_MISSING:
        env_name = _SEARCH_API_KEY_ENVS.get(provider, "对应 provider API key")
        return f"配置 {env_name} 后重跑；默认不影响 local smoke gate。"
    if bucket == _BUCKET_PROVIDER_NO_RESULTS:
        return "provider callable 成功但没有返回结果；检查 query、provider 可用性或站点索引。"
    if bucket == _BUCKET_PROVIDER_AUTH_FAILURE:
        return "检查 provider API key 权限或鉴权配置；不要把 secret 写入 artifact。"
    if bucket == _BUCKET_PROVIDER_QUOTA_OR_RATE_LIMITED:
        return "provider quota 或 rate limit 命中；等待额度恢复后重跑。"
    if bucket == _BUCKET_PROVIDER_NETWORK_FAILURE:
        return "检查外部网络、DNS、TLS 或 provider 服务可达性。"
    if bucket == _BUCKET_PROVIDER_RESPONSE_PARSE_FAILURE:
        return "检查 provider 响应格式是否变化。"
    return "查看 search provider artifact；外部 provider 失败默认不影响 local smoke gate。"


def _has_docling_invocation_blocker(local_cases: Sequence[SmokeCaseResult]) -> bool:
    """判断 local cases 是否命中 Docling invocation blocker。

    Args:
        local_cases: local smoke case 结果。

    Returns:
        命中 PDF fetch 成功但 Docling invocation evidence 不成立时返回 ``True``。

    Raises:
        无。
    """

    return any(
        case.case_kind == _CASE_LOCAL_PDF
        and case.status == _STATUS_FAILED
        and case.bucket == _BUCKET_PDF_DOCLING_INVOCATION_FAILURE
        for case in local_cases
    )


def _write_docling_invocation_blocker_artifact(
    *,
    output_dir: Path,
    local_cases: Sequence[SmokeCaseResult],
) -> Path:
    """写入 Docling invocation blocker artifact。

    Args:
        output_dir: smoke 输出目录。
        local_cases: local smoke case 结果。

    Returns:
        blocker artifact 路径。

    Raises:
        OSError: artifact 写入失败时抛出。
    """

    blocker_dir = output_dir / "blockers"
    blocker_dir.mkdir(parents=True, exist_ok=True)
    blocker_path = blocker_dir / _DOCLING_INVOCATION_BLOCKER_FILE
    pdf_cases = [case for case in local_cases if case.bucket == _BUCKET_PDF_DOCLING_INVOCATION_FAILURE]
    lines = [
        "# Local PDF Docling Invocation Blocker",
        "",
        "local PDF fetch_web_page 成功后，smoke 无法从 diagnostics artifact 证明 Docling conversion callable 实际调用。",
        "该情况不能用 content-type、fetch success、静态代码推断或生产 LLM-facing payload 字段替代。",
        "",
    ]
    for case in pdf_cases:
        lines.extend(
            [
                f"- case_name: {case.case_name}",
                f"- url: {case.url}",
                f"- evidence_path: {case.evidence_path}",
                f"- bucket: {case.bucket}",
                f"- suggested_next_step: {case.suggested_next_step}",
                "",
            ]
        )
    blocker_path.write_text("\n".join(lines), encoding="utf-8")
    _LOGGER.warning("wrote Docling invocation blocker artifact: path=%s", blocker_path)
    return blocker_path


def _execute_smoke(*, options: SmokeOptions, runner: DiagnosticRunner) -> SmokeSummary:
    """执行 Web smoke 流程。

    Args:
        options: smoke 选项。
        runner: diagnostics 子进程 runner。

    Returns:
        smoke summary。

    Raises:
        ValueError: operator 输入非法时抛出。
        OSError: 文件读写或子进程启动失败时抛出。
    """

    _LOGGER.info(
        "web smoke execution started: run_label=%s output_dir=%s external_limit=%s",
        options.run_label,
        options.output_dir,
        options.external_limit,
    )
    local_cases = _run_local_cases(options=options, runner=runner)
    search_cases = _run_search_provider_cases(options=options)
    if _has_docling_invocation_blocker(local_cases):
        _write_docling_invocation_blocker_artifact(output_dir=options.output_dir, local_cases=local_cases)
        summary = _summary_from_cases(
            run_label=options.run_label,
            output_dir=options.output_dir,
            local_cases=local_cases,
            external_cases=(),
            search_cases=search_cases,
        )
        _LOGGER.info(
            "web smoke execution finished: status=%s exit_code=%s local_cases=%s external_cases=0 search_cases=%s",
            summary.status,
            summary.exit_code,
            len(summary.local_cases),
            len(summary.search_cases),
        )
        return summary
    external_cases = _run_external_cases(options=options, runner=runner)
    summary = _summary_from_cases(
        run_label=options.run_label,
        output_dir=options.output_dir,
        local_cases=local_cases,
        external_cases=external_cases,
        search_cases=search_cases,
    )
    _LOGGER.info(
        "web smoke execution finished: status=%s exit_code=%s local_cases=%s external_cases=%s search_cases=%s diagnostic_only=%s",
        summary.status,
        summary.exit_code,
        len(summary.local_cases),
        len(summary.external_cases),
        len(summary.search_cases),
        len(summary.diagnostic_only),
    )
    return summary


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """解析 CLI 参数。

    Args:
        argv: 可选命令行参数；``None`` 表示读取进程参数。

    Returns:
        argparse namespace。

    Raises:
        SystemExit: argparse 在参数非法时抛出。
    """

    parser = argparse.ArgumentParser(description="Web CI smoke summary 生成器。")
    parser.add_argument("--output-dir", default="", help="summary 输出目录；缺省为 workspace/output/web_smoke/<run_label>。")
    parser.add_argument("--request-timeout", type=float, default=15.0, help="diagnostics requests timeout 秒数。")
    parser.add_argument("--tool-timeout-budget", type=float, default=30.0, help="diagnostics 工具调用 timeout budget 秒数。")
    parser.add_argument("--include-playwright", action="store_true", help="让 diagnostics 采样 Playwright；默认跳过。")
    parser.add_argument(
        "--external-url-file",
        default="",
        help="外部 URL 文件；缺省使用 utils/web_ci_urls.jsonl，结果只作为 diagnostic-only。",
    )
    parser.add_argument(
        "--external-limit",
        type=int,
        default=_DEFAULT_EXTERNAL_LIMIT,
        help="外部 URL 最多采样数量；传 0 可只运行本地 matrix。",
    )
    parser.add_argument(
        "--diagnostic-only-external",
        action="store_true",
        help="显式确认外部 URL 只作为 diagnostic-only；提供 external-url-file 时自动按此语义处理。",
    )
    parser.add_argument(
        "--log-level",
        default=LogLevel.DEBUG.name.lower(),
        help="诊断日志级别，不区分大小写；默认 debug。",
    )
    parser.add_argument("--run-label", default="", help="可选运行标签，主要供 deterministic 测试或人工复现使用。")
    return parser.parse_args(argv)


def _options_from_namespace(namespace: argparse.Namespace) -> SmokeOptions:
    """从 argparse namespace 构造 SmokeOptions。

    Args:
        namespace: argparse namespace。

    Returns:
        smoke 选项。

    Raises:
        ValueError: 参数非法时抛出。
    """

    run_label_value = namespace.run_label
    run_label = run_label_value if isinstance(run_label_value, str) and run_label_value else _utc_run_label()
    output_dir_value = namespace.output_dir
    output_dir = (
        Path(output_dir_value).expanduser().resolve()
        if isinstance(output_dir_value, str) and output_dir_value
        else _default_output_dir(run_label)
    )
    request_timeout_value = namespace.request_timeout
    tool_timeout_budget_value = namespace.tool_timeout_budget
    external_limit_value = namespace.external_limit
    external_file_value = namespace.external_url_file
    log_level_value = namespace.log_level
    if not isinstance(request_timeout_value, float) or request_timeout_value <= 0:
        raise ValueError("--request-timeout 必须大于 0。")
    if not isinstance(tool_timeout_budget_value, float) or tool_timeout_budget_value <= 0:
        raise ValueError("--tool-timeout-budget 必须大于 0。")
    if not isinstance(external_limit_value, int) or external_limit_value < 0:
        raise ValueError("--external-limit 必须大于等于 0。")
    if not isinstance(log_level_value, str):
        raise ValueError("--log-level 必须是字符串。")
    log_level = _log_level_from_text(log_level_value)
    external_url_file = (
        Path(external_file_value).expanduser().resolve()
        if isinstance(external_file_value, str) and external_file_value
        else _DEFAULT_EXTERNAL_URL_FILE
    )
    if external_url_file is not None and not external_url_file.is_file():
        raise ValueError(f"external URL 文件不存在: {external_url_file}")
    if external_url_file is not None:
        _validate_external_url_file(external_url_file)
    return SmokeOptions(
        output_dir=output_dir,
        request_timeout=request_timeout_value,
        tool_timeout_budget=tool_timeout_budget_value,
        include_playwright=bool(namespace.include_playwright),
        external_url_file=external_url_file,
        external_limit=external_limit_value,
        diagnostic_only_external=bool(namespace.diagnostic_only_external) or external_url_file is not None,
        run_label=run_label,
        log_level=log_level,
    )


def _print_start_ui(options: SmokeOptions) -> None:
    """打印人类可读的 smoke 启动信息。

    这些 ``SMOKE`` 行是 CLI UI 输出，不作为审计真源；稳定事实仍写入
    summary artifact。

    Args:
        options: smoke 选项。

    Returns:
        无。

    Raises:
        无。
    """

    external_url_file = str(options.external_url_file) if options.external_url_file is not None else "<disabled>"
    print("SMOKE START Web CI smoke")
    print(f"SMOKE RUN_LABEL {options.run_label}")
    print(f"SMOKE LOG_LEVEL {options.log_level.name}")
    print(f"SMOKE OUTPUT_DIR {options.output_dir}")
    print(f"SMOKE EXTERNAL_URL_FILE {external_url_file}")
    print(f"SMOKE EXTERNAL_LIMIT {options.external_limit}")


def _print_summary_ui(summary: SmokeSummary) -> None:
    """打印人类可读的 smoke 结果摘要。

    Args:
        summary: smoke summary。

    Returns:
        无。

    Raises:
        无。
    """

    output_dir = Path(summary.output_dir)
    print(f"SMOKE STATUS {summary.status}")
    print(f"SMOKE EXIT_CODE {summary.exit_code}")
    print(f"SMOKE LOCAL_CASES {len(summary.local_cases)}")
    print(f"SMOKE EXTERNAL_CASES {len(summary.external_cases)}")
    print(f"SMOKE SEARCH_CASES {len(summary.search_cases)}")
    print(f"SMOKE FAILURES {len(summary.failures)}")
    print(f"SMOKE SKIPS {len(summary.skips)}")
    print(f"SMOKE DIAGNOSTIC_ONLY {len(summary.diagnostic_only)}")
    print(f"SMOKE SUMMARY_JSON {output_dir / 'summary.json'}")
    print(f"SMOKE SUMMARY_MD {output_dir / 'summary.md'}")


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    Args:
        argv: 可选命令行参数；``None`` 表示读取进程参数。

    Returns:
        进程退出码。

    Raises:
        无。
    """

    try:
        namespace = _parse_args(argv)
        options = _options_from_namespace(namespace)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else _EXIT_SCHEMA_OR_INFRA_FAILURE
    except ValueError as exc:
        print(f"smoke 参数错误: {exc}", file=sys.stderr)
        return _EXIT_SCHEMA_OR_INFRA_FAILURE

    configure(level=options.log_level, configure_root=True)
    _print_start_ui(options)
    try:
        summary = _execute_smoke(options=options, runner=_run_diagnostic_command)
        _write_summary(summary)
    except (OSError, ValueError) as exc:
        _LOGGER.error("web smoke execution failed before summary output: %s", exc)
        print(f"smoke 执行失败: {exc}", file=sys.stderr)
        return _EXIT_SCHEMA_OR_INFRA_FAILURE
    _print_summary_ui(summary)
    print(f"Web CI smoke summary 已写入: {options.output_dir}")
    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
