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
import hashlib
import html
import http.server
import importlib.util
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Final, Iterator, TypeAlias, cast
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig
from dayu.runtime.log import LogLevel, configure
from dayu.tools.web.web_diagnostics import (
    WEB_DIAGNOSTIC_SCHEMA_REVISION,
    WEB_DIAGNOSTIC_SCHEMA_VERSION,
    WebDiagnosticOutcome,
    content_diagnostic_from_bytes,
    content_diagnostic_from_text,
    project_error_message,
    project_safe_url_or_empty,
)
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
_DIAGNOSTIC_SCHEMA_VERSION: Final[str] = WEB_DIAGNOSTIC_SCHEMA_VERSION
_MIN_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = WEB_DIAGNOSTIC_SCHEMA_REVISION
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
_CASE_LOCAL_CHALLENGE_CONTROL: Final[str] = "local_challenge_control"
_CASE_LOCAL_ASSEMBLY_CONFIG: Final[str] = "local_assembly_config"
_CASE_LOCAL_FILING: Final[str] = "local_filing"
_CASE_LOCAL_PRIVATE_DENY: Final[str] = "local_private_deny"
_CASE_LOCAL_CUSTOM_PORT_DENY: Final[str] = "local_custom_port_deny"
_CASE_EXTERNAL: Final[str] = "external"
_CASE_SEARCH_PROVIDER: Final[str] = "search_provider"
_JSONL_SUFFIXES: Final[frozenset[str]] = frozenset({".jsonl", ".jsonlines"})
_EXTERNAL_URL_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})
_LOCAL_FIXTURE_HOST: Final[str] = "127.0.0.1"
_LOCAL_HTML_PATH: Final[str] = "/index.html"
_LOCAL_PDF_PATH: Final[str] = "/fixture.pdf"
_LOCAL_BROWSER_PATH: Final[str] = "/client-rendered.html"
_LOCAL_CHALLENGE_PATH: Final[str] = "/challenge-control.html"
_LOCAL_FILING_PATH: Final[str] = "/aapl-20240928.htm"
_LOCAL_NEGATIVE_PATH: Final[str] = "/negative-control"
_FIXTURE_TOKEN_QUERY_KEY: Final[str] = "dayu_smoke_token"
_LOCAL_HTML_CONTENT_TYPE: Final[str] = "text/html; charset=utf-8"
_LOCAL_PDF_CONTENT_TYPE: Final[str] = "application/pdf"
_HTTP_GET_METHOD: Final[str] = "GET"
_HTTP_HEAD_METHOD: Final[str] = "HEAD"
_HTTP_HEADER_CONTENT_TYPE: Final[str] = "Content-Type"
_HTTP_HEADER_CONTENT_LENGTH: Final[str] = "Content-Length"
_HTTP_HEADER_CACHE_CONTROL: Final[str] = "Cache-Control"
_HTTP_CACHE_CONTROL_NO_STORE: Final[str] = "no-store"
_HTTP_STATUS_OK: Final[int] = 200
_HTTP_STATUS_NOT_FOUND: Final[int] = 404
_HTTP_STATUS_METHOD_NOT_ALLOWED: Final[int] = 405
_HTTP_STATUS_FORBIDDEN: Final[int] = 403
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
_BUCKET_FIXTURE_LEDGER_GAP: Final[str] = "fixture_ledger_gap"
_BUCKET_CONTENT_ORACLE_MISMATCH: Final[str] = "content_oracle_mismatch"
_BUCKET_NEGATIVE_CONTROL_FAILED: Final[str] = "negative_control_failed"
_BUCKET_CHALLENGE_CONTROL_FAILED: Final[str] = "challenge_control_failed"
_BUCKET_WEB_CONFIG_LOADER_FAILURE: Final[str] = "web_config_loader_failure"
_BUCKET_WEB_ASSEMBLY_DISCOVERY_FAILURE: Final[str] = "web_assembly_discovery_failure"
_BUCKET_WEB_TOOL_MISSING: Final[str] = "web_tool_missing"
_BUCKET_WEB_ASSEMBLY_FETCH_FAILURE: Final[str] = "web_assembly_fetch_failure"
_BUCKET_WEB_ASSEMBLY_FETCH_CONTENT_FAILURE: Final[str] = "web_assembly_fetch_content_failure"
_BUCKET_WEB_ASSEMBLY_CONFIG_MISMATCH: Final[str] = "web_assembly_config_mismatch"
_BUCKET_TYPED_EGRESS_DENY_FAILED: Final[str] = "typed_egress_deny_failed"
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
_VERSIONED_FILING_FIXTURE: Final[Path] = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fins"
    / "fixtures"
    / "aapl_xbrl"
    / "fil_0000320193-24-000123"
    / "aapl-20240928.htm"
)
_NOISY_DEBUG_LOGGER_NAMES: Final[tuple[str, ...]] = (
    "dayu.fins",
    "dayu.tools.web",
    "filelock",
    "htmldate",
    "readability",
    "trafilatura",
)
_ASSEMBLY_FETCH_TRUNCATE_CHARS: Final[int] = 3210
_ASSEMBLY_PROVIDER_CONFIG: Final[JsonObject] = {
    "provider": "duckduckgo",
    "request_timeout_seconds": 6.0,
    "max_search_results": 3,
    "fetch_truncate_chars": _ASSEMBLY_FETCH_TRUNCATE_CHARS,
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
_FIXTURE_LEDGER_MAX_OBSERVATIONS: Final[int] = 256
_NEGATIVE_CONTROL_TIMEOUT_SECONDS: Final[float] = 2.0
_CHALLENGE_FIXTURE_BYTES: Final[bytes] = (
    b"<!doctype html><html><body>verify you are human bot challenge</body></html>"
)


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


class FixtureResponseKind(StrEnum):
    """本地 fixture 响应或负控的封闭类型。"""

    HTML = "html"
    PDF = "pdf"
    BROWSER = "browser"
    CHALLENGE = "challenge"
    NEGATIVE_MISSING_TOKEN = "negative_missing_token"
    NEGATIVE_WRONG_TOKEN = "negative_wrong_token"
    NEGATIVE_REPLAY_TOKEN = "negative_replay_token"
    NEGATIVE_METHOD = "negative_method"
    NEGATIVE_UNKNOWN_PATH = "negative_unknown_path"


@dataclass(frozen=True, slots=True)
class LocalFixtureCase:
    """父进程注册的单个 local smoke case。

    Args:
        case_name: 稳定 case 名称。
        case_kind: smoke 分类类型。
        path: 规范化 fixture path。
        url: 含一次性 256-bit token 的 child URL。
        token: 只保留在父进程活跃 session 的 raw token。
        token_digest: ledger 使用的 token SHA-256。
        response_kind: fixture 响应类型。
        response_body: 父进程实际注册的 exact response bytes。
        response_digest: exact response bytes 的 SHA-256。
        expected_backend: artifact 必须证明的 backend。
        sample_playwright: diagnostics 是否执行 Playwright profile。
        skip_requests: diagnostics 是否跳过 raw requests profile。
        skip_tool_fetch: diagnostics 是否跳过 tool profile。

    Returns:
        无。

    Raises:
        无。
    """

    case_name: str
    case_kind: str
    path: str
    url: str
    token: str
    token_digest: str
    response_kind: FixtureResponseKind
    response_body: bytes
    response_digest: str
    expected_backend: str
    sample_playwright: bool
    skip_requests: bool
    skip_tool_fetch: bool

    @property
    def response_length(self) -> int:
        """返回父进程注册的 exact response bytes 长度。

        Args:
            无。

        Returns:
            response bytes 长度。

        Raises:
            无。
        """

        return len(self.response_body)


@dataclass(frozen=True, slots=True)
class FixtureRequestObservation:
    """handler 追加到父进程内存 ledger 的有界观察项。

    Args:
        token_digest: 请求 token 的 SHA-256；缺失 token 使用空字符串摘要。
        method: HTTP method。
        normalized_path: 删除 query 后的 path。
        response_kind: 响应或拒绝类型。
        response_digest: 实际响应 bytes 的 SHA-256。
        accepted: token/path/method 是否被接受。

    Returns:
        无。

    Raises:
        无。
    """

    token_digest: str
    method: str
    normalized_path: str
    response_kind: FixtureResponseKind
    response_digest: str
    accepted: bool


@dataclass(frozen=True, slots=True)
class FrozenFixtureLedger:
    """server 停止后冻结的 local fixture ledger 快照。

    Args:
        observations: 有界 typed request observations。
        dropped_count: 超出 ledger 上限的观察项数量。
        lifecycle: 父进程记录的生命周期顺序。

    Returns:
        无。

    Raises:
        无。
    """

    observations: tuple[FixtureRequestObservation, ...]
    dropped_count: int
    lifecycle: tuple[str, ...]


class ParentFixtureLedger:
    """父进程拥有、handler 只追加的内存 ledger。"""

    def __init__(self, *, max_observations: int) -> None:
        """初始化可变 ledger。

        Args:
            max_observations: 最大 request observation 数。

        Returns:
            无。

        Raises:
            ValueError: 上限不是正整数时抛出。
        """

        if isinstance(max_observations, bool) or max_observations <= 0:
            raise ValueError("fixture ledger max_observations must be positive")
        self._max_observations = max_observations
        self._observations: list[FixtureRequestObservation] = []
        self._dropped_count = 0
        self._lifecycle: list[str] = ["created"]
        self._frozen = False
        self._lock = threading.Lock()

    def record_lifecycle(self, stage: str) -> None:
        """由父进程记录 lifecycle stage。

        Args:
            stage: 稳定 lifecycle 标签。

        Returns:
            无。

        Raises:
            RuntimeError: ledger 已冻结时抛出。
        """

        with self._lock:
            if self._frozen:
                raise RuntimeError("fixture ledger is frozen")
            self._lifecycle.append(stage)

    def append(self, observation: FixtureRequestObservation) -> None:
        """由 fixture handler 追加一条 typed observation。

        Args:
            observation: 不含 raw token/header/body 的观察项。

        Returns:
            无。

        Raises:
            RuntimeError: ledger 已冻结时抛出。
        """

        with self._lock:
            if self._frozen:
                raise RuntimeError("fixture ledger is frozen")
            if len(self._observations) >= self._max_observations:
                self._dropped_count += 1
                return
            self._observations.append(observation)

    def freeze(self) -> FrozenFixtureLedger:
        """在 server 停止后冻结 ledger。

        Args:
            无。

        Returns:
            不可变 ledger 快照。

        Raises:
            RuntimeError: 重复冻结时抛出。
        """

        with self._lock:
            if self._frozen:
                raise RuntimeError("fixture ledger already frozen")
            self._lifecycle.append("frozen")
            self._frozen = True
            return FrozenFixtureLedger(
                observations=tuple(self._observations),
                dropped_count=self._dropped_count,
                lifecycle=tuple(self._lifecycle),
            )


@dataclass(slots=True)
class LocalFixtureSession:
    """local fixture server 与父进程 ledger 的共生 session。

    Args:
        urls: 旧 direct assembly consumer 使用的基础 URL 集合。
        cases: 已注册 local cases。
        ledger: 活跃父进程 ledger。
        frozen_ledger: server 停止后由 context manager 写入的冻结快照。

    Returns:
        无。

    Raises:
        无。
    """

    urls: LocalFixtureUrls
    cases: tuple[LocalFixtureCase, ...]
    ledger: ParentFixtureLedger
    frozen_ledger: FrozenFixtureLedger | None = None


class _LocalFixtureServer(http.server.ThreadingHTTPServer):
    """携带父进程 registrations 与 ledger 的 typed HTTP server。"""

    def __init__(
        self,
        server_address: tuple[str, int],
        cases: tuple[LocalFixtureCase, ...],
        ledger: ParentFixtureLedger,
    ) -> None:
        """初始化 typed fixture server。

        Args:
            server_address: host/port 监听地址。
            cases: 父进程预注册 cases。
            ledger: 父进程内存 ledger。

        Returns:
            无。

        Raises:
            OSError: server 绑定失败时抛出。
        """

        self.fixture_cases = cases
        self.fixture_ledger = ledger
        self.accepted_token_digests: set[str] = set()
        self.fixture_lock = threading.Lock()
        super().__init__(server_address, _LocalFixtureRequestHandler)


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


@dataclass(frozen=True, slots=True)
class PendingLocalDiagnostic:
    """server 活跃期间暂存、freeze 后才能分类的 local child 结果。

    Args:
        fixture_case: 父进程注册 case。
        artifact_path: child 诊断 artifact 路径。
        child_result: child 进程退出事实。

    Returns:
        无。

    Raises:
        无。
    """

    fixture_case: LocalFixtureCase
    artifact_path: Path
    child_result: DiagnosticChildResult


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


def _token_digest(token: str) -> str:
    """计算 fixture token 的 SHA-256 hex。

    Args:
        token: 父进程生成的 raw token。

    Returns:
        64 位小写 SHA-256 hex。

    Raises:
        无。
    """

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fixture_url(*, port: int, path: str, token: str) -> str:
    """构造携带一次性 query token 的 local fixture URL。

    Args:
        port: local server 端口。
        path: normalized fixture path。
        token: 256-bit hex token。

    Returns:
        仅供 child 调用的 tokenized URL。

    Raises:
        ValueError: port 非正时抛出。
    """

    if port <= 0:
        raise ValueError("local fixture server 端口必须大于 0。")
    query = urlencode({_FIXTURE_TOKEN_QUERY_KEY: token})
    return f"http://{_LOCAL_FIXTURE_HOST}:{port}{path}?{query}"


def _new_fixture_case(
    *,
    port: int,
    case_name: str,
    case_kind: str,
    path: str,
    response_kind: FixtureResponseKind,
    response_body: bytes,
    expected_backend: str,
    sample_playwright: bool,
    skip_requests: bool,
    skip_tool_fetch: bool,
) -> LocalFixtureCase:
    """创建带唯一 256-bit sentinel 的父进程 fixture case。

    Args:
        port: local server 端口。
        case_name: 稳定 case 名称。
        case_kind: smoke case 类型。
        path: fixture path。
        response_kind: 响应类型。
        response_body: exact registered bytes。
        expected_backend: artifact 必须证明的 backend。
        sample_playwright: 是否执行 Playwright。
        skip_requests: 是否跳过 raw requests。
        skip_tool_fetch: 是否跳过 tool fetch。

    Returns:
        raw token 仅存在父进程 session 的 typed case。

    Raises:
        ValueError: port 非正时抛出。
    """

    token = secrets.token_hex(32)
    response = content_diagnostic_from_bytes(response_body)
    return LocalFixtureCase(
        case_name=case_name,
        case_kind=case_kind,
        path=path,
        url=_fixture_url(port=port, path=path, token=token),
        token=token,
        token_digest=_token_digest(token),
        response_kind=response_kind,
        response_body=response_body,
        response_digest=response.digest,
        expected_backend=expected_backend,
        sample_playwright=sample_playwright,
        skip_requests=skip_requests,
        skip_tool_fetch=skip_tool_fetch,
    )


def _build_local_fixture_cases(port: int) -> tuple[LocalFixtureCase, ...]:
    """为每个 local smoke case 注册唯一 sentinel 与 exact response bytes。

    Args:
        port: local server 端口。

    Returns:
        HTML、PDF、browser、challenge、版本化 filing 与 assembly cases。

    Raises:
        OSError: 版本化 filing fixture 读取失败时抛出。
        ValueError: port 非正或版本化 fixture 不是常规文件时抛出。
    """

    html_bytes = _html_fixture_bytes()
    pdf_bytes = _pdf_fixture_bytes()
    browser_bytes = _browser_fixture_bytes()
    if not _VERSIONED_FILING_FIXTURE.is_file():
        raise ValueError("版本化 AAPL filing fixture 缺失或不是常规文件。")
    filing_bytes = _VERSIONED_FILING_FIXTURE.read_bytes()
    return (
        _new_fixture_case(
            port=port,
            case_name="local-html-requests",
            case_kind=_CASE_LOCAL_HTML,
            path=_LOCAL_HTML_PATH,
            response_kind=FixtureResponseKind.HTML,
            response_body=html_bytes,
            expected_backend="requests",
            sample_playwright=False,
            skip_requests=False,
            skip_tool_fetch=True,
        ),
        _new_fixture_case(
            port=port,
            case_name="local-html-tool",
            case_kind=_CASE_LOCAL_HTML,
            path=_LOCAL_HTML_PATH,
            response_kind=FixtureResponseKind.HTML,
            response_body=html_bytes,
            expected_backend="requests",
            sample_playwright=False,
            skip_requests=True,
            skip_tool_fetch=False,
        ),
        _new_fixture_case(
            port=port,
            case_name="local-pdf-requests",
            case_kind=_CASE_LOCAL_PDF,
            path=_LOCAL_PDF_PATH,
            response_kind=FixtureResponseKind.PDF,
            response_body=pdf_bytes,
            expected_backend="requests",
            sample_playwright=False,
            skip_requests=False,
            skip_tool_fetch=True,
        ),
        _new_fixture_case(
            port=port,
            case_name="local-pdf-tool",
            case_kind=_CASE_LOCAL_PDF,
            path=_LOCAL_PDF_PATH,
            response_kind=FixtureResponseKind.PDF,
            response_body=pdf_bytes,
            expected_backend="requests",
            sample_playwright=False,
            skip_requests=True,
            skip_tool_fetch=False,
        ),
        _new_fixture_case(
            port=port,
            case_name="local-browser-playwright",
            case_kind=_CASE_LOCAL_BROWSER,
            path=_LOCAL_BROWSER_PATH,
            response_kind=FixtureResponseKind.BROWSER,
            response_body=browser_bytes,
            expected_backend="playwright",
            sample_playwright=True,
            skip_requests=True,
            skip_tool_fetch=True,
        ),
        _new_fixture_case(
            port=port,
            case_name="local-challenge-control",
            case_kind=_CASE_LOCAL_CHALLENGE_CONTROL,
            path=_LOCAL_CHALLENGE_PATH,
            response_kind=FixtureResponseKind.CHALLENGE,
            response_body=_CHALLENGE_FIXTURE_BYTES,
            expected_backend="requests",
            sample_playwright=False,
            skip_requests=False,
            skip_tool_fetch=True,
        ),
        _new_fixture_case(
            port=port,
            case_name="local-filing-http",
            case_kind=_CASE_LOCAL_FILING,
            path=_LOCAL_FILING_PATH,
            response_kind=FixtureResponseKind.HTML,
            response_body=filing_bytes,
            expected_backend="requests",
            sample_playwright=False,
            skip_requests=False,
            skip_tool_fetch=True,
        ),
        _new_fixture_case(
            port=port,
            case_name="local-filing-playwright",
            case_kind=_CASE_LOCAL_FILING,
            path=_LOCAL_FILING_PATH,
            response_kind=FixtureResponseKind.HTML,
            response_body=filing_bytes,
            expected_backend="playwright",
            sample_playwright=True,
            skip_requests=True,
            skip_tool_fetch=True,
        ),
        _new_fixture_case(
            port=port,
            case_name="local-assembly-config",
            case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
            path=_LOCAL_HTML_PATH,
            response_kind=FixtureResponseKind.HTML,
            response_body=html_bytes,
            expected_backend="requests",
            sample_playwright=False,
            skip_requests=True,
            skip_tool_fetch=False,
        ),
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

        _handle_fixture_request(self)

    def do_HEAD(self) -> None:
        """拒绝非 smoke 必需的 HEAD 请求。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        _handle_fixture_request(self)

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


def _fixture_content_type(case: LocalFixtureCase) -> str:
    """返回注册 case 的稳定 Content-Type。

    Args:
        case: 父进程注册 case。

    Returns:
        PDF 使用 application/pdf，其余使用 HTML UTF-8。

    Raises:
        无。
    """

    if case.response_kind is FixtureResponseKind.PDF:
        return _LOCAL_PDF_CONTENT_TYPE
    return _LOCAL_HTML_CONTENT_TYPE


def _negative_response_body(kind: FixtureResponseKind) -> bytes:
    """构造不含 raw token 的负控响应体。

    Args:
        kind: 负控类型。

    Returns:
        稳定 ASCII response bytes。

    Raises:
        ValueError: kind 不是负控类型时抛出。
    """

    if kind not in {
        FixtureResponseKind.NEGATIVE_MISSING_TOKEN,
        FixtureResponseKind.NEGATIVE_WRONG_TOKEN,
        FixtureResponseKind.NEGATIVE_REPLAY_TOKEN,
        FixtureResponseKind.NEGATIVE_METHOD,
        FixtureResponseKind.NEGATIVE_UNKNOWN_PATH,
    }:
        raise ValueError("fixture response kind is not negative")
    return f"rejected:{kind.value}\n".encode("ascii")


def _append_fixture_observation(
    *,
    server: _LocalFixtureServer,
    token: str,
    method: str,
    path: str,
    response_kind: FixtureResponseKind,
    body: bytes,
    accepted: bool,
) -> None:
    """向父进程 ledger 追加不含 raw token/body 的 typed observation。

    Args:
        server: typed local fixture server。
        token: 请求携带 token；只在追加前计算摘要。
        method: HTTP method。
        path: normalized path。
        response_kind: 响应或拒绝类型。
        body: 实际响应 bytes；只计算摘要。
        accepted: 请求是否接受。

    Returns:
        无。

    Raises:
        RuntimeError: ledger 已冻结时抛出。
    """

    body_diagnostic = content_diagnostic_from_bytes(body)
    server.fixture_ledger.append(
        FixtureRequestObservation(
            token_digest=_token_digest(token),
            method=method,
            normalized_path=path,
            response_kind=response_kind,
            response_digest=body_diagnostic.digest,
            accepted=accepted,
        )
    )


def _handle_fixture_request(handler: _LocalFixtureRequestHandler) -> None:
    """校验一次性 token、记录 ledger 并发送 fixture 响应。

    Args:
        handler: 当前 typed request handler。

    Returns:
        无。

    Raises:
        OSError: HTTP response 写入失败时由 stdlib 透出。
    """

    server = cast(_LocalFixtureServer, handler.server)
    parsed = urlparse(handler.path)
    path = parsed.path or "/"
    token_values = parse_qs(parsed.query, keep_blank_values=True).get(
        _FIXTURE_TOKEN_QUERY_KEY,
        [],
    )
    token = token_values[0] if len(token_values) == 1 else ""
    path_cases = tuple(case for case in server.fixture_cases if case.path == path)
    matched_case = next((case for case in path_cases if case.token == token), None)
    if not path_cases:
        kind = FixtureResponseKind.NEGATIVE_UNKNOWN_PATH
    elif not token:
        kind = FixtureResponseKind.NEGATIVE_MISSING_TOKEN
    elif matched_case is None:
        kind = FixtureResponseKind.NEGATIVE_WRONG_TOKEN
    elif handler.command != _HTTP_GET_METHOD:
        kind = FixtureResponseKind.NEGATIVE_METHOD
    else:
        with server.fixture_lock:
            if matched_case.token_digest in server.accepted_token_digests:
                kind = FixtureResponseKind.NEGATIVE_REPLAY_TOKEN
            else:
                server.accepted_token_digests.add(matched_case.token_digest)
                kind = matched_case.response_kind
    if matched_case is not None and kind is matched_case.response_kind:
        body = matched_case.response_body
        _append_fixture_observation(
            server=server,
            token=token,
            method=handler.command,
            path=path,
            response_kind=kind,
            body=body,
            accepted=True,
        )
        _send_fixture_response(
            handler,
            status_code=_HTTP_STATUS_OK,
            content_type=_fixture_content_type(matched_case),
            body=body,
        )
        return
    body = _negative_response_body(kind)
    observed_body = body if handler.command == _HTTP_GET_METHOD else b""
    _append_fixture_observation(
        server=server,
        token=token,
        method=handler.command,
        path=path,
        response_kind=kind,
        body=observed_body,
        accepted=False,
    )
    status_code = (
        _HTTP_STATUS_NOT_FOUND
        if kind is FixtureResponseKind.NEGATIVE_UNKNOWN_PATH
        else _HTTP_STATUS_METHOD_NOT_ALLOWED
        if kind is FixtureResponseKind.NEGATIVE_METHOD
        else _HTTP_STATUS_FORBIDDEN
    )
    _send_fixture_response(
        handler,
        status_code=status_code,
        content_type="text/plain; charset=utf-8",
        body=body,
    )


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
def _running_local_fixture_server() -> Iterator[LocalFixtureSession]:
    """启动本地 loopback fixture server。

    Args:
        无。

    Returns:
        context manager 期间可访问的 fixture session；退出后含 frozen ledger。

    Raises:
        OSError: server 绑定或启动失败时抛出。
    """

    ledger = ParentFixtureLedger(
        max_observations=_FIXTURE_LEDGER_MAX_OBSERVATIONS
    )
    server = _LocalFixtureServer((_LOCAL_FIXTURE_HOST, 0), (), ledger)
    port = int(server.server_address[1])
    cases = _build_local_fixture_cases(port)
    server.fixture_cases = cases
    assembly_case = next(
        case for case in cases if case.case_kind == _CASE_LOCAL_ASSEMBLY_CONFIG
    )
    pdf_case = next(
        case for case in cases if case.case_name == "local-pdf-requests"
    )
    browser_case = next(
        case for case in cases if case.case_name == "local-browser-playwright"
    )
    session = LocalFixtureSession(
        urls=LocalFixtureUrls(
            html_url=assembly_case.url,
            pdf_url=pdf_case.url,
            browser_url=browser_case.url,
        ),
        cases=cases,
        ledger=ledger,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        name="dayu-web-smoke-local-fixture",
        daemon=True,
    )
    thread.start()
    ledger.record_lifecycle("server_started")
    try:
        yield session
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)
        ledger.record_lifecycle("server_stopped")
        session.frozen_ledger = ledger.freeze()


def _replace_fixture_query_token(url: str, token: str) -> str:
    """替换 fixture URL 的 query token。

    Args:
        url: 原始 tokenized URL。
        token: 新 token；空字符串表示删除 query。

    Returns:
        替换后的 URL。

    Raises:
        无。
    """

    parsed = urlparse(url)
    query = urlencode({_FIXTURE_TOKEN_QUERY_KEY: token}) if token else ""
    return urlunparse(parsed._replace(query=query))


def _send_negative_control_request(
    url: str,
    *,
    method: str = _HTTP_GET_METHOD,
) -> None:
    """由父进程发送一次应被 fixture 拒绝的负控请求。

    Args:
        url: 负控 URL。
        method: 封闭的 GET 或 HEAD method。

    Returns:
        无；HTTP 结果只由 ledger classifier 判断，不由此函数签发结论。

    Raises:
        ValueError: method 不是 GET/HEAD 时抛出。
        requests.RequestException: local fixture 请求失败时抛出。
    """

    if method not in {_HTTP_GET_METHOD, _HTTP_HEAD_METHOD}:
        raise ValueError("fixture negative control method must be GET or HEAD")
    response = requests.request(
        method,
        url,
        timeout=_NEGATIVE_CONTROL_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.close()


def _exercise_pre_child_negative_controls(case: LocalFixtureCase) -> None:
    """在 child 启动前发送 missing/wrong/method/unknown-path 负控。

    Args:
        case: 当前父进程 fixture case。

    Returns:
        无。

    Raises:
        requests.RequestException: local fixture 请求失败时抛出。
    """

    _send_negative_control_request(_replace_fixture_query_token(case.url, ""))
    _send_negative_control_request(
        _replace_fixture_query_token(case.url, secrets.token_hex(32))
    )
    _send_negative_control_request(case.url, method=_HTTP_HEAD_METHOD)
    parsed = urlparse(case.url)
    unknown_url = urlunparse(parsed._replace(path=_LOCAL_NEGATIVE_PATH))
    _send_negative_control_request(unknown_url)


def _exercise_post_child_replay_control(case: LocalFixtureCase) -> None:
    """在 child 返回后重放同一 token，证明一次性 token 拒绝语义。

    Args:
        case: 当前父进程 fixture case。

    Returns:
        无。

    Raises:
        requests.RequestException: local fixture 请求失败时抛出。
    """

    _send_negative_control_request(case.url)


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


def _suppress_noisy_debug_loggers() -> None:
    """压低默认 debug 下与 Web smoke 判断无关的 logger。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for logger_name in _NOISY_DEBUG_LOGGER_NAMES:
        logging.getLogger(logger_name).setLevel(int(LogLevel.INFO))


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

    del case_kind
    version = _string_field(payload, "diagnostic_schema_version")
    schema_version = _string_field(payload, "schema_version")
    revision = _int_field(payload, "diagnostic_schema_revision")
    if version != _DIAGNOSTIC_SCHEMA_VERSION or schema_version != _DIAGNOSTIC_SCHEMA_VERSION:
        return "diagnostics artifact 必须精确使用 web-diagnostics-v2，旧 schema 不兼容。"
    if revision != _MIN_DIAGNOSTIC_SCHEMA_REVISION:
        return "diagnostics artifact 必须精确使用 diagnostic_schema_revision=2。"
    legacy_field = _legacy_diagnostic_field(payload)
    if legacy_field:
        return f"diagnostics artifact 包含禁止的旧 schema 字段：{legacy_field}。"
    for profile_name in (
        "requests_profile",
        "fetch_web_page_profile",
        "playwright_profile",
    ):
        profile = _nested_object(payload, profile_name)
        gap = _profile_schema_gap(profile, profile_name=profile_name)
        if gap:
            return gap
    return ""


def _legacy_diagnostic_field(value: JsonValue) -> str:
    """递归查找 schema v2 禁止的可逆前缀或旧 URL 字段。

    Args:
        value: diagnostics JSON 值。

    Returns:
        首个禁止字段名；不存在时返回空字符串。

    Raises:
        无。
    """

    forbidden = {
        "content_prefix",
        "html_prefix",
        "page_text_prefix",
        "stderr_prefix",
        "stdout_prefix",
        "text_prefix",
    }
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in forbidden:
                return key
            nested = _legacy_diagnostic_field(item)
            if nested:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = _legacy_diagnostic_field(item)
            if nested:
                return nested
    return ""


def _profile_schema_gap(
    profile: Mapping[str, JsonValue],
    *,
    profile_name: str,
) -> str:
    """校验一个 schema v2 path profile 的自足字段。

    Args:
        profile: path profile。
        profile_name: 错误信息使用的字段名。

    Returns:
        空字符串表示通过；否则返回 gap。

    Raises:
        无。
    """

    if not isinstance(profile.get("sampled"), bool):
        return f"{profile_name}.sampled 必须是 bool。"
    outcome = profile.get("outcome")
    if outcome not in {item.value for item in WebDiagnosticOutcome}:
        return f"{profile_name}.outcome 不是 schema v2 封闭值。"
    if not isinstance(profile.get("safe_url"), str):
        return f"{profile_name}.safe_url 必须是字符串。"
    elapsed = profile.get("elapsed_seconds")
    if (
        not isinstance(elapsed, (int, float))
        or isinstance(elapsed, bool)
        or elapsed < 0
    ):
        return f"{profile_name}.elapsed_seconds 必须是非负数。"
    if outcome == WebDiagnosticOutcome.COMPLETED.value:
        backend = profile.get("backend")
        if backend not in {"requests", "playwright", "tool"}:
            return f"{profile_name}.backend 缺失或非法。"
        content_length = profile.get("content_length")
        if (
            not isinstance(content_length, int)
            or isinstance(content_length, bool)
            or content_length < 0
        ):
            return f"{profile_name}.content_length 必须是非负整数。"
        content_digest = profile.get("content_digest")
        if not isinstance(content_digest, str) or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            content_digest,
        ) is None:
            return f"{profile_name}.content_digest 必须是 SHA-256 摘要。"
        if "http_status" not in profile:
            return f"{profile_name}.http_status 缺失。"
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

    return _diagnostic_schema_gap(payload, case_kind=_CASE_LOCAL_HTML)


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
    response_headers = _nested_object(requests_profile, "response_headers")
    projected_content_type = _string_field(response_headers, "content_type")
    if projected_content_type:
        return projected_content_type
    return _string_field(requests_profile, "content_type")


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
    return _int_field(requests_profile, "content_length")


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
    return _string_field(fetch_profile, "backend")


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
    return (
        _bool_field(requests_profile, "sampled")
        and _string_field(requests_profile, "outcome")
        == WebDiagnosticOutcome.COMPLETED.value
    )


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
    return (
        _bool_field(fetch_profile, "sampled")
        and _string_field(fetch_profile, "outcome")
        == WebDiagnosticOutcome.COMPLETED.value
    )


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

    return _string_field(payload, "safe_url") or project_safe_url_or_empty(fallback_url)


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


def _fixture_ledger_gap(
    *,
    case: LocalFixtureCase,
    ledger: FrozenFixtureLedger,
) -> str:
    """用冻结 ledger 独立证明 token/path/response 与负控事实。

    Args:
        case: 当前父进程注册 case。
        ledger: server 停止后冻结的 ledger。

    Returns:
        空字符串表示独立 oracle 通过；否则返回 gap。

    Raises:
        无。
    """

    if len(ledger.lifecycle) < 4 or ledger.lifecycle[-2:] != (
        "server_stopped",
        "frozen",
    ):
        return "fixture ledger 必须在 server 停止后 freeze，并在 classify 前保持冻结。"
    if ledger.dropped_count != 0:
        return "fixture ledger observation 超过有界上限，无法完整分类。"
    accepted = tuple(
        observation
        for observation in ledger.observations
        if observation.accepted
        and observation.token_digest == case.token_digest
        and observation.normalized_path == case.path
    )
    if len(accepted) != 1:
        return "fixture ledger 缺少当前 token/path 的唯一 accepted request。"
    accepted_observation = accepted[0]
    if accepted_observation.method != _HTTP_GET_METHOD:
        return "fixture ledger accepted request method 不是 GET。"
    if accepted_observation.response_kind is not case.response_kind:
        return "fixture ledger response kind 与父进程注册事实不一致。"
    if accepted_observation.response_digest != case.response_digest:
        return "fixture ledger response digest 与父进程注册 bytes 不一致。"
    rejected_kinds = {
        observation.response_kind
        for observation in ledger.observations
        if not observation.accepted
        and observation.normalized_path in {case.path, _LOCAL_NEGATIVE_PATH}
    }
    required_negative_kinds = {
        FixtureResponseKind.NEGATIVE_MISSING_TOKEN,
        FixtureResponseKind.NEGATIVE_WRONG_TOKEN,
        FixtureResponseKind.NEGATIVE_REPLAY_TOKEN,
        FixtureResponseKind.NEGATIVE_METHOD,
        FixtureResponseKind.NEGATIVE_UNKNOWN_PATH,
    }
    missing_negative_kinds = required_negative_kinds - rejected_kinds
    if missing_negative_kinds:
        missing = ",".join(sorted(item.value for item in missing_negative_kinds))
        return f"fixture negative controls 未全部失败：{missing}。"
    return ""


def _exact_response_artifact_gap(
    *,
    profile: Mapping[str, JsonValue],
    case: LocalFixtureCase,
) -> str:
    """比较 artifact content length/digest 与父进程 exact response bytes。

    Args:
        profile: 对应 requests path profile。
        case: 父进程注册 case。

    Returns:
        空字符串表示匹配；否则返回 gap。

    Raises:
        无。
    """

    if _int_field(profile, "content_length") != case.response_length:
        return "artifact content_length 与父进程 expected bytes 不一致。"
    if _string_field(profile, "content_digest") != case.response_digest:
        return "artifact content_digest 与父进程 expected bytes 不一致。"
    return ""


def _playwright_package_missing_independently() -> bool:
    """由 smoke 父进程独立判断 Playwright Python package 是否缺失。

    Args:
        无。

    Returns:
        package spec 缺失时返回 ``True``。

    Raises:
        无。
    """

    return importlib.util.find_spec("playwright") is None


def _docling_package_missing_independently() -> bool:
    """由 smoke 父进程独立判断 Docling package 是否缺失。

    Args:
        无。

    Returns:
        package spec 缺失时返回 ``True``。

    Raises:
        无。
    """

    return importlib.util.find_spec("docling") is None


def _classify_loaded_artifact(
    *,
    case_name: str,
    case_kind: str,
    fallback_url: str,
    artifact_path: Path,
    payload: Mapping[str, JsonValue],
    child_returncode: int,
    fixture_case: LocalFixtureCase | None = None,
    frozen_ledger: FrozenFixtureLedger | None = None,
) -> SmokeCaseResult:
    """根据已加载 artifact 分类 smoke case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        fallback_url: artifact 缺少 URL 时的后备 URL。
        artifact_path: artifact 路径。
        payload: diagnostics artifact。
        child_returncode: diagnostics 子进程退出码。
        fixture_case: local case 的父进程注册事实；external 为空。
        frozen_ledger: server 停止后冻结的父进程 ledger；external 为空。

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

    if fixture_case is None or frozen_ledger is None:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_FIXTURE_LEDGER_GAP,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step="local PASS 必须由父进程 fixture registration 与 frozen ledger 证明。",
        )

    if (
        child_returncode != _EXIT_OK
        and _docling_init_skip(payload)
        and case_kind == _CASE_LOCAL_PDF
        and _docling_package_missing_independently()
    ):
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
    if (
        case_kind == _CASE_LOCAL_PDF
        and _docling_init_skip(payload)
        and _docling_package_missing_independently()
    ):
        return _case_skip(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_DOCLING_INIT_SKIP,
            reason="diagnostics 观察到 Docling 初始化或依赖缺失，PDF local smoke 本轮跳过。",
        )
    if case_kind == _CASE_LOCAL_BROWSER:
        playwright_profile = _nested_object(payload, "playwright_profile")
        if (
            _string_field(playwright_profile, "error_code")
            == "playwright_package_missing"
            and _playwright_package_missing_independently()
        ):
            return SmokeCaseResult(
                case_name=case_name,
                case_kind=case_kind,
                url=url,
                status=_STATUS_SKIPPED,
                bucket=_BUCKET_BROWSER_PROFILE_NOT_SAMPLED,
                evidence_path=evidence_path,
                suggested_next_step="安装 Playwright Python package 后重跑 browser smoke。",
                reason="父进程独立确认 Playwright Python package 缺失。",
                exit_code=_EXIT_OK,
            )

    ledger_gap = _fixture_ledger_gap(case=fixture_case, ledger=frozen_ledger)
    if ledger_gap:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_FIXTURE_LEDGER_GAP,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step=ledger_gap,
        )

    profile_name = (
        "playwright_profile"
        if case_kind == _CASE_LOCAL_BROWSER
        or (
            case_kind == _CASE_LOCAL_FILING
            and case_name == "local-filing-playwright"
        )
        else "fetch_web_page_profile"
        if case_name.endswith("-tool")
        else "requests_profile"
    )
    profile = _nested_object(payload, profile_name)
    if _string_field(profile, "outcome") != WebDiagnosticOutcome.COMPLETED.value:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=(
                _BUCKET_BROWSER_FETCH_FAILURE
                if profile_name == "playwright_profile"
                else _BUCKET_LOCAL_FETCH_FAILURE
                if profile_name == "fetch_web_page_profile"
                else _BUCKET_LOCAL_REQUESTS_FAILURE
            ),
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step=f"{profile_name} 未证明 completed execution。",
        )

    content_gap = _exact_response_artifact_gap(profile=profile, case=fixture_case)
    if content_gap:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_CONTENT_ORACLE_MISMATCH,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step=content_gap,
        )
    if _string_field(profile, "backend") != fixture_case.expected_backend:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=(
                _BUCKET_BROWSER_BACKEND_NOT_OBSERVED
                if profile_name == "playwright_profile"
                else _BUCKET_LOCAL_FETCH_FAILURE
            ),
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="artifact backend execution evidence 与父进程 case contract 不一致。",
        )

    if case_kind == _CASE_LOCAL_CHALLENGE_CONTROL:
        if _string_field(profile, "challenge_decision") != "confirmed":
            return _case_failure(
                case_name=case_name,
                case_kind=case_kind,
                url=url,
                evidence_path=evidence_path,
                bucket=_BUCKET_CHALLENGE_CONTROL_FAILED,
                exit_code=_EXIT_LOCAL_FAILURE,
                suggested_next_step="challenge negative control 必须观察到 confirmed decision。",
            )
    elif _string_field(profile, "challenge_decision") == "confirmed":
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_CHALLENGE_CONTROL_FAILED,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="普通 local fixture 不得被分类为 confirmed challenge。",
        )

    if case_kind == _CASE_LOCAL_FILING:
        filing_gap = _filing_artifact_gap(
            payload=payload,
            profile_name=profile_name,
        )
        if filing_gap:
            return _case_failure(
                case_name=case_name,
                case_kind=case_kind,
                url=url,
                evidence_path=evidence_path,
                bucket=_BUCKET_BROWSER_BACKEND_NOT_OBSERVED,
                exit_code=_EXIT_LOCAL_FAILURE,
                suggested_next_step=filing_gap,
            )

    if case_kind == _CASE_LOCAL_PDF and profile_name == "fetch_web_page_profile":
        pdf_failure = _classify_pdf_tool_loaded_artifact(
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
        url=project_safe_url_or_empty(url),
        status=_STATUS_PASSED,
        bucket=_BUCKET_PASSED,
        evidence_path=evidence_path,
        suggested_next_step="",
        reason="",
        exit_code=_EXIT_OK,
    )


def _classify_pdf_tool_loaded_artifact(
    *,
    case_name: str,
    url: str,
    evidence_path: str,
    payload: Mapping[str, JsonValue],
) -> SmokeCaseResult | None:
    """校验 PDF tool case 的转换正文与 Docling execution evidence。

    PDF 原始 response kind/length/digest 已由父进程 registration、ledger 与
    通用 exact-content oracle 证明；本 helper 只校验工具转换这一独立事实，
    不从已跳过的 requests profile 反推 content-type。

    Args:
        case_name: case 名称。
        url: safe URL 输入。
        evidence_path: 诊断 artifact 路径。
        payload: schema v2 diagnostics artifact。

    Returns:
        tool 转换证据失败结果；全部满足时返回 ``None``。

    Raises:
        无。
    """

    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    projected_length = _int_field(fetch_profile, "projected_content_length")
    if projected_length is None or projected_length < PDF_FETCH_MIN_CHARS:
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_CONTENT_LENGTH_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step=(
                f"PDF tool projected content 必须至少 {PDF_FETCH_MIN_CHARS} 个字符。"
            ),
        )
    evidence = _docling_evidence(payload)
    if (
        not _bool_field(evidence, "invoked")
        or _string_field(evidence, "stream_name") != _PDF_EXPECTED_STREAM_NAME
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
                "PDF tool case 必须观察到 Docling callable 实际调用、"
                f"stream_name={_PDF_EXPECTED_STREAM_NAME} 且原始 callable 正常返回。"
            ),
        )
    return None


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
        browser 必需证据失败结果；全部满足时返回 ``None``。

    Raises:
        无。
    """

    if not _playwright_profile_sampled(payload):
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_BROWSER,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_BROWSER_PROFILE_NOT_SAMPLED,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="确认 smoke 默认 browser case 未被 --skip-playwright 或旧 diagnostics 命令绕过。",
        )
    playwright_profile = _nested_object(payload, "playwright_profile")
    if not _bool_field(playwright_profile, "browser_executed"):
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_BROWSER,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_BROWSER_BACKEND_NOT_OBSERVED,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="Playwright profile 未提供 browser_executed=true 的执行证据。",
        )
    return None


def _filing_artifact_gap(
    *,
    payload: Mapping[str, JsonValue],
    profile_name: str,
) -> str:
    """校验版本化 filing 的 HTTP 或真实 Playwright 执行事实。

    Args:
        payload: diagnostics artifact。
        profile_name: 当前 filing case 的执行 profile 名称。

    Returns:
        空字符串表示 filing 执行证据完整；否则返回 gap 说明。

    Raises:
        无。
    """

    if profile_name != "playwright_profile":
        return ""
    profile = _nested_object(payload, profile_name)
    if not _playwright_profile_sampled(payload):
        return "版本化 filing 未执行 Playwright profile。"
    if not _bool_field(profile, "browser_executed"):
        return "版本化 filing 缺少 browser_executed=true。"
    storage_state = _nested_object(profile, "storage_state")
    if not _bool_field(storage_state, "input_used"):
        return "版本化 filing 未证明显式 storage state 输入已被 raw Playwright 消费。"
    if _int_field(profile, "rendered_html_length") is None:
        return "版本化 filing 缺少 rendered HTML length metric。"
    if _int_field(profile, "rendered_text_length") is None:
        return "版本化 filing 缺少 rendered text length metric。"
    if _int_field(profile, "network_event_count") is None:
        return "版本化 filing 缺少 network event count metric。"
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden_field in (
        "output_enabled",
        "output_label",
        "ttl_seconds",
        "published",
        "reconcile",
        "cleanup",
    ):
        if forbidden_field in serialized:
            return f"版本化 filing artifact 残留 credential lifecycle 字段：{forbidden_field}。"
    return ""


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
        url=project_safe_url_or_empty(url),
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
        url=project_safe_url_or_empty(url),
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
        url=project_safe_url_or_empty(url),
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
    fixture_case: LocalFixtureCase | None = None,
    frozen_ledger: FrozenFixtureLedger | None = None,
) -> SmokeCaseResult:
    """按子进程结果与 artifact 分类 smoke case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        fallback_url: artifact 缺少 URL 时的后备 URL。
        artifact_path: artifact 路径。
        child_result: diagnostics 子进程结果。
        fixture_case: local case 的父进程注册事实；external 为空。
        frozen_ledger: server 停止后冻结的 ledger；external 为空。

    Returns:
        smoke case 结果。

    Raises:
        无。
    """

    if case_kind == _CASE_EXTERNAL and child_result.returncode != _EXIT_OK:
        return _case_diagnostic_only(
            case_name=case_name,
            case_kind=case_kind,
            url=project_safe_url_or_empty(fallback_url),
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
                url=project_safe_url_or_empty(fallback_url),
                evidence_path=str(artifact_path),
                bucket=_BUCKET_ARTIFACT_MISSING,
                reason="外部 diagnostics 未生成 artifact；不影响 local smoke gate。",
                suggested_next_step="检查 external URL 文件、网络和 diagnostics 子进程 stderr。",
            )
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=project_safe_url_or_empty(fallback_url),
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
                url=project_safe_url_or_empty(fallback_url),
                evidence_path=str(artifact_path),
                bucket=_BUCKET_ARTIFACT_PARSE_FAILURE,
                reason=f"外部 diagnostics artifact 无法解析：{exc}",
                suggested_next_step="检查外部 diagnostics artifact 是否完整写入。",
            )
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=project_safe_url_or_empty(fallback_url),
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
        fixture_case=fixture_case,
        frozen_ledger=frozen_ledger,
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
    """只记录 diagnostics 子进程输出的不可逆 length/digest。

    Args:
        case_name: smoke case 名称。
        child_result: diagnostics 子进程结果。

    Returns:
        无。

    Raises:
        无。
    """

    stdout_diagnostic = content_diagnostic_from_text(child_result.stdout)
    stderr_diagnostic = content_diagnostic_from_text(child_result.stderr)
    _LOGGER.debug(
        "diagnostics child finished: case=%s returncode=%s "
        "stdout_length=%s stdout_digest=%s stderr_length=%s stderr_digest=%s",
        case_name,
        child_result.returncode,
        stdout_diagnostic.length,
        stdout_diagnostic.digest,
        stderr_diagnostic.length,
        stderr_diagnostic.digest,
    )


def _diagnostic_command(
    *,
    url: str,
    artifact_path: Path,
    options: SmokeOptions,
    sample_playwright: bool,
    skip_requests: bool = False,
    skip_tool_fetch: bool = False,
    storage_state_input: Path | None = None,
) -> list[str]:
    """构造单 URL diagnostics 命令。

    Args:
        url: 待诊断 URL。
        artifact_path: diagnostics 输出 artifact。
        options: smoke 选项。
        sample_playwright: 是否让 diagnostics 采样 Playwright。
        skip_requests: 是否跳过 raw requests profile。
        skip_tool_fetch: 是否跳过 tool fetch profile。
        storage_state_input: 可选的显式 Playwright storage state 输入文件。

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
    if not sample_playwright:
        command.append("--skip-playwright")
    if skip_requests:
        command.append("--skip-requests")
    if skip_tool_fetch:
        command.append("--skip-tool-fetch")
    if storage_state_input is not None:
        command.extend(["--storage-state-in", str(storage_state_input)])
    return command


def _run_local_typed_egress_deny_case(
    *,
    case_name: str,
    case_kind: str,
    fixture_url: str,
    diagnostics_dir: Path,
    provider_config: Mapping[str, JsonValue],
) -> SmokeCaseResult:
    """通过正式 config assembly 与工具 callable 验证一个 typed egress deny。

    Args:
        case_name: 稳定 smoke case 名称。
        case_kind: private 或 custom-port deny case 类型。
        fixture_url: 本地 custom-port fixture URL。
        diagnostics_dir: local diagnostics 输出目录。
        provider_config: 含单一显式 deny 的 Web provider overlay。

    Returns:
        typed deny 的 smoke 分类结果。

    Raises:
        OSError: overlay 或 artifact 写入失败时抛出。
    """

    artifact_path = diagnostics_dir / f"{case_name}.json"
    workspace_config_dir = diagnostics_dir / f"{case_name}-workspace-config"
    _write_web_tool_discovery_overlay(
        workspace_config_dir,
        provider_config=provider_config,
    )
    error_type = ""
    observed_error_code = ""
    try:
        config = _load_runtime_config_for_overlay(workspace_config_dir)
        definitions = _discover_tools_by_name(config, workspace_root=diagnostics_dir)
        fetch_definition = definitions.get("fetch_web_page")
        if fetch_definition is None:
            error_type = "MissingFetchWebPage"
        else:
            outcome = asyncio.run(
                fetch_definition.callable(
                    _tool_call("fetch_web_page", {"url": fixture_url}),
                    _tool_context(),
                )
            )
            if isinstance(outcome, ToolFailedOutcome):
                observed_error_code = outcome.result.error
            else:
                error_type = type(outcome).__name__
    except Exception as exc:
        error_type = type(exc).__name__

    passed = observed_error_code == "permission_denied"
    _write_json(
        artifact_path,
        {
            "schema_version": "web-smoke-typed-egress-v1",
            "case_kind": case_kind,
            "safe_url": project_safe_url_or_empty(fixture_url),
            "provider_config": dict(provider_config),
            "expected_error_code": "permission_denied",
            "observed_error_code": observed_error_code,
            "error_type": error_type,
            "passed": passed,
        },
    )
    if not passed:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=fixture_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_TYPED_EGRESS_DENY_FAILED,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step=(
                "显式 typed provider deny 必须在正式 fetch_web_page callable 中投影为 permission_denied。"
            ),
        )
    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=project_safe_url_or_empty(fixture_url),
        status=_STATUS_PASSED,
        bucket=_BUCKET_PASSED,
        evidence_path=str(artifact_path),
        suggested_next_step="",
        reason="",
        exit_code=_EXIT_OK,
    )


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
    projected_content_length = len(content)
    response_content_length = _int_field(value, "response_content_length")
    response_content_digest = _string_field(value, "response_content_digest")
    artifact_content_length = (
        response_content_length if response_content_length is not None else 0
    )
    if not content_contains_fixture_text:
        _write_assembly_artifact(
            artifact_path=artifact_path,
            url=fixture_urls.html_url,
            tool_names=tool_names,
            provider_config=provider_config,
            fetch_ok=True,
            content_length=artifact_content_length,
            content_contains_fixture_text=False,
            truncate_max_chars=truncate_max_chars,
            bucket=_BUCKET_WEB_ASSEMBLY_FETCH_CONTENT_FAILURE,
            suggested_next_step="fetch_web_page 成功但未返回 local HTML fixture 正文，检查内容抽取或 URL 路径。",
            content_digest=response_content_digest,
            projected_content_length=projected_content_length,
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
        content_length=artifact_content_length,
        content_contains_fixture_text=True,
        truncate_max_chars=truncate_max_chars,
        bucket=_BUCKET_PASSED,
        suggested_next_step="",
        content_digest=response_content_digest,
        projected_content_length=projected_content_length,
    )
    return SmokeCaseResult(
        case_name=case_name,
        case_kind=_CASE_LOCAL_ASSEMBLY_CONFIG,
        url=project_safe_url_or_empty(fixture_urls.html_url),
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
        error_summary=project_error_message(str(error), max_chars=512),
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
    content_digest: str = "",
    projected_content_length: int = 0,
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
        content_digest: 原始响应 bytes 的 SHA-256。
        projected_content_length: 工具转换后正文长度。

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
            "url": project_safe_url_or_empty(url),
            "tool_names": list(tool_names),
            "provider_config": dict(provider_config),
            "called_tool": "fetch_web_page",
            "fetch_ok": fetch_ok,
            "content_length": content_length,
            "content_digest": content_digest,
            "projected_content_length": projected_content_length,
            "content_contains_fixture_text": content_contains_fixture_text,
            "truncate_max_chars": truncate_max_chars,
            "assembly_path": _ASSEMBLY_PATH_LABEL,
            "bucket": bucket,
            "suggested_next_step": suggested_next_step,
            "error_type": error_type,
            "error_summary": error_summary,
        },
    )


def _classify_assembly_with_ledger(
    *,
    preliminary_result: SmokeCaseResult,
    fixture_case: LocalFixtureCase,
    frozen_ledger: FrozenFixtureLedger,
) -> SmokeCaseResult:
    """用 frozen ledger 与 exact digest 为 assembly PASS 追加独立证明。

    Args:
        preliminary_result: assembly callable 的初步执行结果。
        fixture_case: 父进程注册 assembly case。
        frozen_ledger: server 停止后冻结的 ledger。

    Returns:
        独立 oracle 分类后的 assembly 结果。

    Raises:
        无。artifact 读取错误投影为 failure。
    """

    if preliminary_result.status != _STATUS_PASSED:
        return preliminary_result
    ledger_gap = _fixture_ledger_gap(case=fixture_case, ledger=frozen_ledger)
    if ledger_gap:
        return _case_failure(
            case_name=preliminary_result.case_name,
            case_kind=preliminary_result.case_kind,
            url=preliminary_result.url,
            evidence_path=preliminary_result.evidence_path,
            bucket=_BUCKET_FIXTURE_LEDGER_GAP,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step=ledger_gap,
        )
    try:
        payload = _load_json_artifact(Path(preliminary_result.evidence_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _case_failure(
            case_name=preliminary_result.case_name,
            case_kind=preliminary_result.case_kind,
            url=preliminary_result.url,
            evidence_path=preliminary_result.evidence_path,
            bucket=_BUCKET_ARTIFACT_PARSE_FAILURE,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step=f"assembly artifact 无法解析：{type(exc).__name__}。",
        )
    if (
        _int_field(payload, "content_length") != fixture_case.response_length
        or _string_field(payload, "content_digest")
        != fixture_case.response_digest
    ):
        return _case_failure(
            case_name=preliminary_result.case_name,
            case_kind=preliminary_result.case_kind,
            url=preliminary_result.url,
            evidence_path=preliminary_result.evidence_path,
            bucket=_BUCKET_CONTENT_ORACLE_MISMATCH,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="assembly artifact 的原始响应 length/digest 与父进程 expected bytes 不一致。",
        )
    return preliminary_result


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
    filing_diagnostics_dir = options.output_dir / "diagnostics" / "filing"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    filing_diagnostics_dir.mkdir(parents=True, exist_ok=True)
    filing_storage_state_input = filing_diagnostics_dir / "explicit-storage-state-input.json"
    _write_json(
        filing_storage_state_input,
        {"cookies": [], "origins": []},
    )
    pending_diagnostics: list[PendingLocalDiagnostic] = []
    typed_deny_results: list[SmokeCaseResult] = []
    assembly_pending: tuple[LocalFixtureCase, SmokeCaseResult] | None = None
    with _running_local_fixture_server() as session:
        _LOGGER.info(
            "local fixture server started: origin=%s registered_cases=%s",
            project_safe_url_or_empty(session.urls.html_url),
            len(session.cases),
        )
        diagnostic_cases = tuple(
            case
            for case in session.cases
            if case.case_kind != _CASE_LOCAL_ASSEMBLY_CONFIG
        )
        for case in diagnostic_cases:
            artifact_dir = (
                filing_diagnostics_dir
                if case.case_kind == _CASE_LOCAL_FILING
                else diagnostics_dir
            )
            artifact_path = artifact_dir / f"{case.case_name}.json"
            _LOGGER.debug(
                "running local smoke case: case=%s kind=%s sample_playwright=%s artifact=%s",
                case.case_name,
                case.case_kind,
                case.sample_playwright,
                artifact_path,
            )
            session.ledger.record_lifecycle(
                f"negative_controls_started:{case.case_name}"
            )
            _exercise_pre_child_negative_controls(case)
            session.ledger.record_lifecycle(f"child_started:{case.case_name}")
            command = _diagnostic_command(
                url=case.url,
                artifact_path=artifact_path,
                options=options,
                sample_playwright=case.sample_playwright,
                skip_requests=case.skip_requests,
                skip_tool_fetch=case.skip_tool_fetch,
                storage_state_input=(
                    filing_storage_state_input
                    if case.case_name == "local-filing-playwright"
                    else None
                ),
            )
            child_result = runner(command)
            _log_diagnostic_child_result(
                case_name=case.case_name,
                child_result=child_result,
            )
            _exercise_post_child_replay_control(case)
            pending_diagnostics.append(
                PendingLocalDiagnostic(
                    fixture_case=case,
                    artifact_path=artifact_path,
                    child_result=child_result,
                )
            )
        private_deny_config = dict(_ASSEMBLY_PROVIDER_CONFIG)
        private_deny_config["allow_private_network_url"] = False
        private_deny_config["allow_custom_port_url"] = True
        typed_deny_results.append(
            _run_local_typed_egress_deny_case(
                case_name="local-private-deny",
                case_kind=_CASE_LOCAL_PRIVATE_DENY,
                fixture_url=session.urls.html_url,
                diagnostics_dir=diagnostics_dir,
                provider_config=private_deny_config,
            )
        )
        custom_port_deny_config = dict(_ASSEMBLY_PROVIDER_CONFIG)
        custom_port_deny_config["allow_private_network_url"] = True
        custom_port_deny_config["allow_custom_port_url"] = False
        typed_deny_results.append(
            _run_local_typed_egress_deny_case(
                case_name="local-custom-port-deny",
                case_kind=_CASE_LOCAL_CUSTOM_PORT_DENY,
                fixture_url=session.urls.html_url,
                diagnostics_dir=diagnostics_dir,
                provider_config=custom_port_deny_config,
            )
        )
        assembly_fixture_case = next(
            case
            for case in session.cases
            if case.case_kind == _CASE_LOCAL_ASSEMBLY_CONFIG
        )
        session.ledger.record_lifecycle(
            f"negative_controls_started:{assembly_fixture_case.case_name}"
        )
        _exercise_pre_child_negative_controls(assembly_fixture_case)
        session.ledger.record_lifecycle(
            f"child_started:{assembly_fixture_case.case_name}"
        )
        assembly_result = _run_local_assembly_config_case(
            fixture_urls=session.urls,
            diagnostics_dir=diagnostics_dir,
        )
        _exercise_post_child_replay_control(assembly_fixture_case)
        assembly_pending = (assembly_fixture_case, assembly_result)

    frozen_ledger = session.frozen_ledger
    if frozen_ledger is None:
        raise RuntimeError("local fixture ledger 未在 server shutdown 后冻结。")
    results = [
        _classify_child_result(
            case_name=pending.fixture_case.case_name,
            case_kind=pending.fixture_case.case_kind,
            fallback_url=pending.fixture_case.url,
            artifact_path=pending.artifact_path,
            child_result=pending.child_result,
            fixture_case=pending.fixture_case,
            frozen_ledger=frozen_ledger,
        )
        for pending in pending_diagnostics
    ]
    results.extend(typed_deny_results)
    if assembly_pending is None:
        raise RuntimeError("local assembly case 未执行。")
    assembly_fixture_case, preliminary_assembly_result = assembly_pending
    results.append(
        _classify_assembly_with_ledger(
            preliminary_result=preliminary_assembly_result,
            fixture_case=assembly_fixture_case,
            frozen_ledger=frozen_ledger,
        )
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
    _suppress_noisy_debug_loggers()
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
