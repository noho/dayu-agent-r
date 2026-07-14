#!/usr/bin/env python3
"""网页访问路径诊断脚本。

本模块提供手工 opt-in 的 Web live diagnostics：对同一个 URL 采集 raw
``requests``、当前 ``fetch_web_page`` 工具 callable，以及可选 Playwright
浏览器路径的同源证据。脚本只输出诊断 artifact，不改变 Host、Engine、
ToolRuntime 或生产 Web tools 行为。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import Final, Protocol, TypeAlias, cast, runtime_checkable
from urllib.parse import urlparse

import requests

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.documents.docling_runtime import DoclingRuntimeInitializationError
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscoveryProviderSpec,
)
from dayu.tools.web import web_tools as _web_tools_module
from dayu.tools.web import web_fetch_orchestrator as _web_fetch_orchestrator
from dayu.tools.web import web_playwright_backend as _web_playwright_backend
from dayu.tools.web.provider import _parse_config, discover_tools
from dayu.tools.web.web_challenge_detection import (
    BotChallengeDecision,
    detect_bot_challenge,
)
from dayu.tools.web.web_egress_policy import WebEgressPolicy, WebEgressPolicyError
from dayu.tools.web.web_http_session import WebHttpTransportPolicy
from dayu.tools.web.web_resource_budget import (
    DEFAULT_BROWSER_RESOURCE_BUDGET,
    DEFAULT_HTTP_RESOURCE_BUDGET,
    BrowserResourceBudget,
    HttpResourceBudget,
)
from dayu.tools.web.web_diagnostics import (
    WEB_DIAGNOSTIC_SCHEMA_REVISION,
    WEB_DIAGNOSTIC_SCHEMA_VERSION,
    WebDiagnosticBackend,
    WebDiagnosticOutcome,
    WebDiagnosticProjection,
    completed_bytes_projection,
    completed_text_projection,
    content_diagnostic_from_text,
    failed_projection,
    project_error_message,
    project_network_event,
    project_response_headers,
    project_safe_url_or_empty,
)

JsonObject: TypeAlias = dict[str, JsonValue]
_DoclingConvertCallable: TypeAlias = Callable[[bytes, str], tuple[str, str, str]]

# schema_version 标识 diagnostics artifact schema；diagnostic_schema_version/revision
# 是 F03 smoke 校验同一 artifact 时使用的显式标记。
_SCHEMA_VERSION: Final[str] = WEB_DIAGNOSTIC_SCHEMA_VERSION
_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = WEB_DIAGNOSTIC_SCHEMA_REVISION
_FETCH_TOOL_NAME: Final[str] = "fetch_web_page"
_DEFAULT_BATCH_OUTPUT_ROOT: Final[Path] = Path("workspace/output/web_diagnostics")
_JSONL_SUFFIXES: Final[frozenset[str]] = frozenset({".jsonl", ".jsonlines"})
_DEFAULT_FETCH_TRUNCATE_CHARS: Final[int] = 80_000
_DEFAULT_DIAGNOSTIC_ERROR_CHARS: Final[int] = 1_024
_DEFAULT_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_REQUEST_ACCEPT: Final[str] = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)
_NEXT_ACTION_HINT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\[([a-z_]+)\]\s*(.*)$")
_DOCLING_TARGET_MODULE: Final[str] = "dayu.tools.web.web_tools"
_DOCLING_TARGET_FUNCTION: Final[str] = "_docling_convert_to_markdown"
_OBSERVED_BUCKET_DOCLING_RUNTIME_SKIP: Final[str] = "docling_runtime_initialization_error"
_OBSERVED_BUCKET_CHILD_PROCESS_ERROR: Final[str] = "child_process_error"
_OBSERVED_BUCKET_ALL_SUCCESS: Final[str] = "all_success"
_OBSERVED_BUCKET_PARTIAL_SAMPLE: Final[str] = "partial_sample"
_OBSERVED_BUCKET_REQUESTS_ONLY_SAMPLED: Final[str] = "requests_only_sampled"
_OBSERVED_BUCKET_PLAYWRIGHT_CHALLENGE: Final[str] = "playwright_challenge_detected"
_OBSERVED_BUCKET_BROWSER_ONLY_SUCCESS: Final[str] = "browser_only_success"
_OBSERVED_HINT_NONE: Final[str] = ""
_OBSERVED_REASON_NONE: Final[str] = ""
_PATH_CHILD_PROCESS: Final[str] = "diagnostic_child_process"
_PATH_REQUESTS: Final[str] = "requests"
_PATH_FETCH_WEB_PAGE: Final[str] = "fetch_web_page"
_PATH_PLAYWRIGHT: Final[str] = "playwright"
_PATH_DOCLING_CONVERSION: Final[str] = "docling_conversion"
_DOCLING_DEPENDENCY_EXCEPTION_TYPES: Final[frozenset[str]] = frozenset(
    {"DoclingRuntimeInitializationError", "ModuleNotFoundError", "ImportError"}
)
_STORAGE_STATE_FINAL_PREFIX: Final[str] = "dayu-web-diagnostic-storage-state-"
_STORAGE_STATE_TEMP_PREFIX: Final[str] = ".dayu-web-diagnostic-storage-state-"
_STORAGE_STATE_FINAL_SUFFIX: Final[str] = ".json"
_STORAGE_STATE_TEMP_SUFFIX: Final[str] = ".tmp"
_PRIVATE_DIRECTORY_MODE: Final[int] = 0o700
_PRIVATE_FILE_MODE: Final[int] = 0o600
_DIAGNOSTIC_HTTP_RESOURCE_BUDGET: Final[HttpResourceBudget] = (
    DEFAULT_HTTP_RESOURCE_BUDGET
)
_DIAGNOSTIC_BROWSER_RESOURCE_BUDGET: Final[BrowserResourceBudget] = (
    DEFAULT_BROWSER_RESOURCE_BUDGET
)


class _DiagnosticBrowserBodyLimitExceeded(RuntimeError):
    """Playwright diagnostic response body 超过共享 decoded-body 上限。"""


@dataclass(frozen=True, slots=True)
class DiagnosticUrlEntry:
    """批量诊断的一条 URL 输入样本。

    Args:
        url: 待诊断 URL。
        label: 业务可读标签。
        region: 站点地区标签。
        category: 站点类别标签。
        notes: 输入侧备注。

    Returns:
        无。

    Raises:
        无。
    """

    url: str
    label: str = ""
    region: str = ""
    category: str = ""
    notes: str = ""


@dataclass(frozen=True, slots=True)
class CliOptions:
    """命令行参数的强类型投影。

    Args:
        url: 单 URL 模式输入。
        url_file: 批量模式输入文件。
        output: 单 URL 输出文件。
        batch_output_dir: 批量输出目录。
        run_label: 批量运行标签。
        request_timeout: requests 与 current fetch 基础超时。
        tool_timeout_budget: current tool callable 的批式 timeout budget。
        playwright_timeout: Playwright 导航超时。
        playwright_channel: Playwright Chromium channel。
        headed: 是否以有界面浏览器运行。
        manual_wait_seconds: 导航后人工等待秒数。
        pause_before_snapshot: 采样页面状态前是否等待人工确认。
        storage_state_in: Playwright storage state 输入路径。
        storage_state_out: Playwright storage state 输出路径。
        storage_state_dir: host 级 storage state 目录。
        storage_state_ttl_seconds: 显式输出 storage state 的正 TTL 秒数。
        skip_playwright: 是否跳过浏览器路径。
        skip_requests: 是否跳过 raw requests 路径。
        skip_tool_fetch: 是否跳过 current fetch 工具路径。
        max_network: 最多记录的浏览器网络摘要数。
        fetch_truncate_chars: 传给 current provider 的截断声明字符数。
        allow_private_network_url: 是否允许诊断内网或本地 URL。

    Returns:
        无。

    Raises:
        无。
    """

    url: str
    url_file: str
    output: str
    batch_output_dir: str
    run_label: str
    request_timeout: float
    tool_timeout_budget: float
    playwright_timeout: float
    playwright_channel: str
    headed: bool
    manual_wait_seconds: float
    pause_before_snapshot: bool
    storage_state_in: str
    storage_state_out: str
    storage_state_dir: str
    storage_state_ttl_seconds: int
    skip_playwright: bool
    skip_requests: bool
    skip_tool_fetch: bool
    max_network: int
    fetch_truncate_chars: int
    allow_private_network_url: bool


@dataclass(slots=True)
class _StorageStateLifecycle:
    """单次 diagnostic storage-state 的原子发布生命周期。

    Args:
        input_path: 可选显式或 owner 目录输入文件。
        final_path: 显式 opt-in 的 owner 命名 final path。
        ttl_seconds: 成功 final 的正 TTL 秒数；未启用输出时为零。
        temp_path: 当前 run 创建的同目录临时文件。
        published: final 是否已由当前 run 原子发布。

    Returns:
        无。

    Raises:
        无。
    """

    input_path: Path | None
    final_path: Path | None
    ttl_seconds: int
    temp_path: Path | None = None
    published: bool = False

    @property
    def output_enabled(self) -> bool:
        """返回当前运行是否显式启用 storage-state 输出。

        Args:
            无。

        Returns:
            final path 存在时返回 ``True``。

        Raises:
            无。
        """

        return self.final_path is not None

    def artifact_projection(self) -> JsonObject:
        """构造不暴露绝对路径或登录态内容的 artifact 投影。

        Args:
            无。

        Returns:
            输入是否使用、输出是否启用、sanitized label 与 TTL。

        Raises:
            无。
        """

        return {
            "input_used": self.input_path is not None,
            "output_enabled": self.output_enabled,
            "output_label": self.final_path.name if self.final_path is not None else "",
            "ttl_seconds": self.ttl_seconds if self.output_enabled else None,
            "published": self.published,
        }

    def publish(self, context: _BrowserContextProtocol) -> None:
        """读取 Playwright storage state 并原子发布到 final。

        Args:
            context: 已完成页面采样的浏览器上下文。

        Returns:
            无。

        Raises:
            OSError: 目录、临时文件、flush/fsync、replace 或权限确认失败时抛出。
            TypeError: Playwright 返回值无法 JSON 序列化时抛出。
        """

        final_path = self.final_path
        if final_path is None:
            return
        temp_path = final_path.parent / (
            f"{_STORAGE_STATE_TEMP_PREFIX}{secrets.token_hex(16)}"
            f"{_STORAGE_STATE_TEMP_SUFFIX}"
        )
        self.temp_path = temp_path
        payload = context.storage_state()
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ) + "\n"
        descriptor = os.open(
            temp_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            _PRIVATE_FILE_MODE,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_path, _PRIVATE_FILE_MODE)
            os.replace(temp_path, final_path)
            self.temp_path = None
            self.published = True
            os.chmod(final_path, _PRIVATE_FILE_MODE)
        except BaseException:
            self._unlink_temp()
            raise

    def cleanup_failure(self) -> None:
        """清理普通 failure/cancel 路径的本 run temp 与已发布 final。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 当前 run 文件无法删除时抛出。
        """

        self._unlink_temp()
        if self.published and self.final_path is not None:
            self.final_path.unlink(missing_ok=True)
            self.published = False

    def _unlink_temp(self) -> None:
        """删除当前 run 创建的临时文件。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 临时文件无法删除时抛出。
        """

        if self.temp_path is None:
            return
        self.temp_path.unlink(missing_ok=True)
        self.temp_path = None


@dataclass(slots=True)
class _DoclingInvocationEvidence:
    """Docling 转换 callable 的诊断期调用证据。

    Args:
        diagnostic_url: 当前诊断 URL。
        invoked: wrapper 是否观察到实际调用。
        stream_name: 原始 callable 收到的流名称。
        raw_bytes_length: 原始 callable 收到的字节长度；未调用时为 ``None``。
        original_completed: 原始 callable 是否正常返回。
        original_exception_type: 原始 callable 抛出的异常类型；未抛出时为空。
        docling_runtime_initialization_error: 是否观察到 Docling 运行时初始化或依赖异常。

    Returns:
        无。

    Raises:
        无。
    """

    diagnostic_url: str
    invoked: bool = False
    stream_name: str = ""
    raw_bytes_length: int | None = None
    original_completed: bool = False
    original_exception_type: str = ""
    docling_runtime_initialization_error: bool = False

    def mark_invoked(self, *, stream_name: str, raw_bytes_length: int) -> None:
        """记录原始 Docling callable 已被调用。

        Args:
            stream_name: 原始 callable 收到的流名称。
            raw_bytes_length: 原始 callable 收到的原始字节长度。

        Returns:
            无。

        Raises:
            无。
        """

        self.invoked = True
        self.stream_name = stream_name
        self.raw_bytes_length = raw_bytes_length
        self.original_completed = False
        self.original_exception_type = ""
        self.docling_runtime_initialization_error = False

    def mark_completed(self) -> None:
        """记录原始 Docling callable 已正常返回。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.original_completed = True
        self.original_exception_type = ""
        self.docling_runtime_initialization_error = False

    def mark_exception(self, exc: Exception) -> None:
        """记录原始 Docling callable 抛出的异常。

        Args:
            exc: 原始 callable 抛出的异常。

        Returns:
            无。

        Raises:
            无。
        """

        exception_type = type(exc).__name__
        self.original_completed = False
        self.original_exception_type = exception_type
        self.docling_runtime_initialization_error = (
            isinstance(exc, DoclingRuntimeInitializationError)
            or exception_type in _DOCLING_DEPENDENCY_EXCEPTION_TYPES
        )

    def to_json(self) -> JsonObject:
        """转换为诊断 artifact 使用的 JSON 对象。

        Args:
            无。

        Returns:
            Docling callable 调用证据 JSON 对象。

        Raises:
            无。
        """

        return {
            "invoked": self.invoked,
            "stream_name": self.stream_name,
            "raw_bytes_length": self.raw_bytes_length,
            "target_module": _DOCLING_TARGET_MODULE,
            "target_function": _DOCLING_TARGET_FUNCTION,
            "original_completed": self.original_completed,
            "original_exception_type": self.original_exception_type,
            "docling_runtime_initialization_error": self.docling_runtime_initialization_error,
            "safe_url": project_safe_url_or_empty(self.diagnostic_url),
            "diagnostic_only_reason": (
                "该字段只记录本次诊断是否观察到非 HTML 内容转换 callable 调用；"
                "它不是网页业务事实，也不会写入生产 fetch_web_page 返回给 LLM 的成功 payload。"
            ),
        }


class _DoclingInvocationWrapper:
    """诊断期 Docling callable wrapper。

    wrapper 只负责记录调用证据并委托原始 callable，不替代生产转换逻辑。
    """

    def __init__(
        self,
        *,
        original: _DoclingConvertCallable,
        evidence: _DoclingInvocationEvidence,
    ) -> None:
        """初始化 wrapper。

        Args:
            original: 被包装的原始 Docling callable。
            evidence: 本次诊断的调用证据容器。

        Returns:
            无。

        Raises:
            无。
        """

        self._original = original
        self._evidence = evidence

    def __call__(self, raw_bytes: bytes, stream_name: str) -> tuple[str, str, str]:
        """记录调用证据后委托原始 Docling callable。

        Args:
            raw_bytes: 原始响应字节。
            stream_name: Docling 输入流名称。

        Returns:
            原始 callable 的 ``(title, markdown, extraction_source)`` 返回值。

        Raises:
            Exception: 原始 callable 抛出的异常会原样透传。
        """

        self._evidence.mark_invoked(stream_name=stream_name, raw_bytes_length=len(raw_bytes))
        try:
            result = self._original(raw_bytes, stream_name)
        except Exception as exc:
            self._evidence.mark_exception(exc)
            raise
        self._evidence.mark_completed()
        return result


class _DiagnosticCancellationToken:
    """诊断脚本使用的永不取消 token。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        Args:
            无。

        Returns:
            始终返回 ``False``，表示本诊断 utility 不连接 Host 取消状态。

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


class _PlaywrightContextManagerProtocol(Protocol):
    """Playwright 同步 context manager 的最小协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    def __enter__(self) -> _PlaywrightProtocol:
        """进入 Playwright 上下文。

        Args:
            无。

        Returns:
            Playwright 根对象。

        Raises:
            Exception: Playwright 包内部可抛出启动错误。
        """

        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """退出 Playwright 上下文。

        Args:
            exc_type: 异常类型。
            exc: 异常实例。
            traceback: 异常 traceback。

        Returns:
            是否吞掉异常。

        Raises:
            Exception: Playwright 包内部可抛出清理错误。
        """

        ...


class _PlaywrightProtocol(Protocol):
    """Playwright 根对象的最小协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    @property
    def chromium(self) -> _BrowserTypeProtocol:
        """返回 Chromium 浏览器类型。

        Args:
            无。

        Returns:
            浏览器类型协议对象。

        Raises:
            无。
        """

        ...


class _BrowserTypeProtocol(Protocol):
    """Playwright browser type 的最小协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    def launch(self, **kwargs: JsonValue) -> _BrowserProtocol:
        """启动浏览器。

        Args:
            kwargs: Playwright ``launch`` 参数。

        Returns:
            浏览器实例。

        Raises:
            Exception: 浏览器不可用或启动失败时抛出。
        """

        ...


class _BrowserProtocol(Protocol):
    """Playwright browser 的最小协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    def new_context(self, **kwargs: JsonValue) -> _BrowserContextProtocol:
        """创建浏览器上下文。

        Args:
            kwargs: Playwright ``new_context`` 参数。

        Returns:
            浏览器上下文。

        Raises:
            Exception: 上下文创建失败时抛出。
        """

        ...

    def close(self) -> None:
        """关闭浏览器。

        Args:
            无。

        Returns:
            无。

        Raises:
            Exception: Playwright 内部关闭失败时抛出。
        """

        ...


class _BrowserContextProtocol(Protocol):
    """Playwright browser context 的最小协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    def new_page(self) -> _PageProtocol:
        """创建页面。

        Args:
            无。

        Returns:
            页面对象。

        Raises:
            Exception: 页面创建失败时抛出。
        """

        ...

    def storage_state(self, *, path: str | None = None) -> JsonValue:
        """读取或保存 storage state。

        Args:
            path: 可选输出路径；存在时写入文件。

        Returns:
            Playwright 返回的 storage state JSON 载荷。

        Raises:
            Exception: 读取或写入失败时抛出。
        """

        ...

    def close(self) -> None:
        """关闭浏览器上下文。

        Args:
            无。

        Returns:
            无。

        Raises:
            Exception: Playwright 内部关闭失败时抛出。
        """

        ...


class _RouteRequestProtocol(Protocol):
    """Playwright route request 的最小协议。"""

    @property
    def url(self) -> str:
        """返回 request URL。

        Args:
            无。

        Returns:
            request URL。

        Raises:
            无。
        """

        ...


class _RouteProtocol(Protocol):
    """Playwright route 的最小协议。"""

    @property
    def request(self) -> _RouteRequestProtocol:
        """返回当前 request。

        Args:
            无。

        Returns:
            当前 request。

        Raises:
            无。
        """

        ...

    def abort(self) -> None:
        """中止 request。

        Args:
            无。

        Returns:
            无。

        Raises:
            Exception: 浏览器拒绝中止时抛出。
        """

        ...

    def continue_(self) -> None:
        """继续 request。

        Args:
            无。

        Returns:
            无。

        Raises:
            Exception: 浏览器拒绝继续时抛出。
        """

        ...


class _PageProtocol(Protocol):
    """Playwright page 的最小协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    def on(self, event: str, handler: Callable[[_PlaywrightNetworkEvent], None]) -> None:
        """注册页面事件回调。

        Args:
            event: 事件名。
            handler: 事件处理函数。

        Returns:
            无。

        Raises:
            Exception: Playwright 内部注册失败时抛出。
        """

        ...

    def route(
        self,
        pattern: str,
        handler: Callable[[_RouteProtocol, _RequestProtocol], None],
    ) -> None:
        """注册浏览器 request 路由。

        Args:
            pattern: Playwright URL pattern。
            handler: request route handler。

        Returns:
            无。

        Raises:
            Exception: 路由注册失败时抛出。
        """

        ...

    def goto(self, url: str, *, wait_until: str, timeout: float) -> _ResponseProtocol | None:
        """导航到目标 URL。

        Args:
            url: 目标 URL。
            wait_until: Playwright 等待条件。
            timeout: 超时毫秒数。

        Returns:
            主文档响应；无响应时返回 ``None``。

        Raises:
            Exception: 导航失败时抛出。
        """

        ...

    def title(self) -> str:
        """读取页面标题。

        Args:
            无。

        Returns:
            页面标题。

        Raises:
            Exception: Playwright 内部读取失败时抛出。
        """

        ...

    def content(self) -> str:
        """读取页面 HTML。

        Args:
            无。

        Returns:
            页面 HTML。

        Raises:
            Exception: Playwright 内部读取失败时抛出。
        """

        ...

    def inner_text(self, selector: str, *, timeout: float) -> str:
        """读取选择器对应文本。

        Args:
            selector: CSS 选择器。
            timeout: 超时毫秒数。

        Returns:
            页面文本。

        Raises:
            Exception: 选择器不可用或读取失败时抛出。
        """

        ...

    def evaluate(
        self,
        expression: str,
        arg: Mapping[str, int] | None = None,
    ) -> JsonValue:
        """执行页面脚本并返回字符串结果。

        Args:
            expression: JavaScript 表达式。

        Returns:
            表达式结果的 JSON 值。

        Raises:
            Exception: 脚本执行失败时抛出。
        """

        ...


class _RequestProtocol(Protocol):
    """Playwright request 事件的最小协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    @property
    def url(self) -> str:
        """返回请求 URL。

        Args:
            无。

        Returns:
            请求 URL。

        Raises:
            无。
        """

        ...

    @property
    def method(self) -> str:
        """返回请求方法。

        Args:
            无。

        Returns:
            HTTP 方法。

        Raises:
            无。
        """

        ...

    @property
    def resource_type(self) -> str:
        """返回资源类型。

        Args:
            无。

        Returns:
            Playwright 资源类型。

        Raises:
            无。
        """

        ...

    @property
    def headers(self) -> Mapping[str, str]:
        """返回请求头。

        Args:
            无。

        Returns:
            请求头映射。

        Raises:
            无。
        """

        ...


@runtime_checkable
class _ResponseProtocol(Protocol):
    """Playwright response 事件的最小协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    @property
    def url(self) -> str:
        """返回响应 URL。

        Args:
            无。

        Returns:
            响应 URL。

        Raises:
            无。
        """

        ...

    @property
    def status(self) -> int:
        """返回响应 HTTP 状态码。

        Args:
            无。

        Returns:
            HTTP 状态码。

        Raises:
            无。
        """

        ...

    @property
    def headers(self) -> Mapping[str, str]:
        """返回响应头。

        Args:
            无。

        Returns:
            响应头映射。

        Raises:
            无。
        """

        ...

    @property
    def request(self) -> _RequestProtocol:
        """返回响应对应的请求。

        Args:
            无。

        Returns:
            请求对象。

        Raises:
            无。
        """

        ...

    def body(self) -> bytes:
        """返回当前 response 的原始响应 bytes。

        Args:
            无。

        Returns:
            response body bytes。

        Raises:
            Exception: Playwright 无法读取 body 时抛出。
        """

        ...


_PlaywrightNetworkEvent: TypeAlias = _RequestProtocol | _ResponseProtocol


def _build_argument_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Args:
        无。

    Returns:
        已配置的 ``argparse.ArgumentParser``。

    Raises:
        无。
    """

    parser = argparse.ArgumentParser(description="导出网页访问路径差异诊断信息。")
    parser.add_argument("--url", default="", help="待诊断的单个 URL。")
    parser.add_argument("--url-file", default="", help="批量 URL 文件，支持 JSONL 或 TXT。")
    parser.add_argument("--output", default="", help="单 URL 诊断 JSON 输出路径。")
    parser.add_argument("--batch-output-dir", default="", help="批量诊断输出目录。")
    parser.add_argument("--run-label", default="", help="批量诊断运行标签。")
    parser.add_argument("--request-timeout", type=float, default=12.0, help="requests 与 fetch 基础超时秒数。")
    parser.add_argument("--tool-timeout-budget", type=float, default=60.0, help="current tool callable 超时预算秒数。")
    parser.add_argument("--playwright-timeout", type=float, default=20.0, help="Playwright 导航超时秒数。")
    parser.add_argument("--playwright-channel", default="chrome", help="Playwright Chromium channel；空字符串表示不指定。")
    parser.add_argument("--headed", action="store_true", help="以有界面浏览器运行 Playwright。")
    parser.add_argument("--manual-wait-seconds", type=float, default=0.0, help="导航后额外等待秒数。")
    parser.add_argument("--pause-before-snapshot", action="store_true", help="采样页面前等待人工确认。")
    parser.add_argument("--storage-state-in", default="", help="Playwright storage state 输入文件。")
    parser.add_argument("--storage-state-out", default="", help="Playwright storage state 输出文件。")
    parser.add_argument("--storage-state-dir", default="", help="按 host 查找 owner 命名 storage state 输入的目录；不会自动启用输出。")
    parser.add_argument(
        "--storage-state-ttl-seconds",
        type=int,
        default=0,
        help="显式 --storage-state-out 的正 TTL 秒数；缺省为 0，表示不持久化。",
    )
    parser.add_argument("--skip-playwright", action="store_true", help="跳过 Playwright 浏览器路径。")
    parser.add_argument("--skip-requests", action="store_true", help="跳过 raw requests 对照路径。")
    parser.add_argument("--skip-tool-fetch", action="store_true", help="跳过 current fetch_web_page 工具路径。")
    parser.add_argument("--max-network", type=int, default=80, help="最多记录的 Playwright 网络摘要条数。")
    parser.add_argument(
        "--fetch-truncate-chars",
        type=int,
        default=_DEFAULT_FETCH_TRUNCATE_CHARS,
        help="传给 current provider 的 fetch 内容截断字符数。",
    )
    parser.add_argument("--allow-private-network-url", action="store_true", help="允许诊断内网或本地 URL。")
    return parser


def _parse_options(argv: Sequence[str] | None) -> CliOptions:
    """把命令行参数解析为强类型选项。

    Args:
        argv: 可选命令行参数序列；为 ``None`` 时读取进程参数。

    Returns:
        强类型 CLI 选项。

    Raises:
        SystemExit: argparse 参数错误时抛出。
    """

    namespace = _build_argument_parser().parse_args(argv)
    return CliOptions(
        url=str(namespace.url or "").strip(),
        url_file=str(namespace.url_file or "").strip(),
        output=str(namespace.output or "").strip(),
        batch_output_dir=str(namespace.batch_output_dir or "").strip(),
        run_label=str(namespace.run_label or "").strip(),
        request_timeout=max(float(namespace.request_timeout), 0.001),
        tool_timeout_budget=max(float(namespace.tool_timeout_budget), 0.001),
        playwright_timeout=max(float(namespace.playwright_timeout), 0.001),
        playwright_channel=str(namespace.playwright_channel or "").strip(),
        headed=bool(namespace.headed),
        manual_wait_seconds=max(float(namespace.manual_wait_seconds), 0.0),
        pause_before_snapshot=bool(namespace.pause_before_snapshot),
        storage_state_in=str(namespace.storage_state_in or "").strip(),
        storage_state_out=str(namespace.storage_state_out or "").strip(),
        storage_state_dir=str(namespace.storage_state_dir or "").strip(),
        storage_state_ttl_seconds=int(namespace.storage_state_ttl_seconds),
        skip_playwright=bool(namespace.skip_playwright),
        skip_requests=bool(namespace.skip_requests),
        skip_tool_fetch=bool(namespace.skip_tool_fetch),
        max_network=max(int(namespace.max_network), 1),
        fetch_truncate_chars=max(int(namespace.fetch_truncate_chars), 1),
        allow_private_network_url=bool(namespace.allow_private_network_url),
    )


def _validate_cli_mode(options: CliOptions) -> None:
    """校验 CLI 诊断模式选择。

    Args:
        options: 已解析的 CLI 选项。

    Returns:
        无。

    Raises:
        ValueError: ``--url`` 与 ``--url-file`` 同时提供或同时缺失时抛出。
    """

    has_url = bool(options.url)
    has_url_file = bool(options.url_file)
    if has_url and has_url_file:
        raise ValueError("--url 与 --url-file 不能同时提供；请只选择单 URL 模式或批量 URL 文件模式。")
    if not has_url and not has_url_file:
        raise ValueError("必须提供 --url 或 --url-file 其中一个，以选择单 URL 模式或批量 URL 文件模式。")


def _utc_now_iso() -> str:
    """生成 UTC ISO 时间字符串。

    Args:
        无。

    Returns:
        带 timezone 的 ISO 时间字符串。

    Raises:
        无。
    """

    return datetime.now(timezone.utc).isoformat()


def _default_run_label() -> str:
    """生成默认批量运行标签。

    Args:
        无。

    Returns:
        UTC 时间戳标签。

    Raises:
        无。
    """

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify_for_filename(url: str) -> str:
    """把 URL 转为文件名安全片段。

    Args:
        url: 原始 URL。

    Returns:
        文件名安全 slug。

    Raises:
        无。
    """

    parsed = urlparse(url)
    raw = f"{parsed.hostname or ''}{parsed.path}".strip("/") or "web_diagnostic"
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "web_diagnostic"


def _default_output_path(url: str) -> Path:
    """构造单 URL 默认输出路径。

    Args:
        url: 待诊断 URL。

    Returns:
        默认输出文件路径。

    Raises:
        无。
    """

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _DEFAULT_BATCH_OUTPUT_ROOT / f"{_slugify_for_filename(url)}-{timestamp}.json"


def _default_batch_output_dir(run_label: str) -> Path:
    """构造批量诊断默认输出目录。

    Args:
        run_label: 本轮运行标签。

    Returns:
        默认批量输出目录。

    Raises:
        无。
    """

    return _DEFAULT_BATCH_OUTPUT_ROOT / run_label


def _normalize_url_for_http(url: str) -> str:
    """规范化 HTTP URL。

    Args:
        url: 用户输入 URL。

    Returns:
        带 http/https scheme 的 URL。

    Raises:
        ValueError: URL 为空或 scheme 非 http/https 时抛出。
    """

    raw = url.strip()
    if not raw:
        raise ValueError("URL 不能为空。")
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"只支持 http/https URL: {url}")
    return raw


def _build_diagnostic_headers(url: str) -> Mapping[str, str]:
    """构造 raw requests 诊断路径使用的本地 headers。

    Args:
        url: 已规范化 URL。

    Returns:
        HTTP headers 映射。

    Raises:
        无。
    """

    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    return {
        "User-Agent": _DEFAULT_USER_AGENT,
        "Accept": _REQUEST_ACCEPT,
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": referer,
    }


def _redact_headers(headers: Mapping[str, str]) -> JsonObject:
    """投影 HTTP headers 的最小安全信息。

    Args:
        headers: 原始 header 映射。

    Returns:
        只包含 allowlist values 与敏感 header presence 的 JSON 对象。

    Raises:
        无。
    """

    return project_response_headers(headers).to_json()


def _round_elapsed(started_at: float) -> float:
    """计算四舍五入后的耗时秒数。

    Args:
        started_at: ``time.perf_counter`` 起始值。

    Returns:
        三位小数耗时。

    Raises:
        无。
    """

    return round(time.perf_counter() - started_at, 3)


def _build_requests_profile(
    url: str,
    *,
    timeout_seconds: float,
    egress_policy: WebEgressPolicy,
    transport_policy: WebHttpTransportPolicy,
) -> JsonObject:
    """采集 raw requests 诊断路径证据。

    Args:
        url: 待诊断 URL。
        timeout_seconds: requests 超时秒数。
        egress_policy: 当前 diagnostic 调用共享的 Web 出站策略。
        transport_policy: provider parser 产生的本次 HTTP transport 策略快照。

    Returns:
        raw requests profile JSON 对象。

    Raises:
        无。
    """

    started_at = time.perf_counter()
    try:
        normalized_url = _normalize_url_for_http(url)
    except ValueError as exc:
        return failed_projection(
            stage="requests",
            url=url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="blocked_by_web_egress_policy",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.REQUESTS,
            sampled=False,
        ).to_json()

    session = requests.Session()
    headers = _build_diagnostic_headers(normalized_url)
    try:
        lease, redirect_hops, _visited_urls = _web_fetch_orchestrator._request_with_safe_redirects(
            session,
            method="GET",
            url=normalized_url,
            timeout=timeout_seconds,
            headers=dict(headers),
            normalize_url_for_http=_normalize_url_for_http,
            egress_policy=egress_policy,
            transport_policy=transport_policy,
            stream=True,
            cancellation_token=None,
        )
    except _web_fetch_orchestrator._FetchUrlSafetyError as exc:
        profile = failed_projection(
            stage="requests",
            url=url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="blocked_by_web_egress_policy",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.REQUESTS,
            sampled=False,
        ).to_json()
        session.close()
        return profile
    except (requests.RequestException, RuntimeError) as exc:
        profile = failed_projection(
            stage="requests",
            url=url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="request_exception",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.REQUESTS,
        ).to_json()
        session.close()
        return profile

    try:
        with lease:
            response = lease.response
            _web_fetch_orchestrator._materialize_response_body(
                response,
                http_resource_budget=_DIAGNOSTIC_HTTP_RESOURCE_BUDGET,
            )
            response_text = response.text
            response_bytes = bytes(response.content)
            challenge = detect_bot_challenge(response=response, content_text=response_text)
            profile = completed_bytes_projection(
                stage="requests",
                url=str(response.url or normalized_url),
                elapsed_seconds=_round_elapsed(started_at),
                backend=WebDiagnosticBackend.REQUESTS,
                content=response_bytes,
                http_status=response.status_code,
                response_headers=response.headers,
            ).to_json()
            profile["redirect_hops"] = redirect_hops
            response_header_projection = _nested_object(profile, "response_headers")
            profile["content_type"] = str(
                response_header_projection.get("content_type", "") or ""
            )
            profile["challenge_decision"] = challenge.decision.value
            profile["challenge_signals"] = list(challenge.challenge_signals)
            return profile
    except (requests.RequestException, RuntimeError) as exc:
        return failed_projection(
            stage="requests",
            url=normalized_url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="request_exception",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.REQUESTS,
        ).to_json()
    finally:
        session.close()


def _provider_config(options: CliOptions) -> JsonObject:
    """构造 current Web provider config。

    Args:
        options: CLI 选项。

    Returns:
        传给 current provider 的 JSON config。

    Raises:
        无。
    """

    config: JsonObject = {
        "request_timeout_seconds": options.request_timeout,
        "fetch_truncate_chars": options.fetch_truncate_chars,
    }
    if options.allow_private_network_url:
        config["allow_private_network_url"] = True
    if options.playwright_channel:
        config["playwright_channel"] = options.playwright_channel
    else:
        config["playwright_channel"] = None
    if options.storage_state_dir:
        config["playwright_storage_state_dir"] = str(Path(options.storage_state_dir).expanduser().resolve())
    return config


def _fetch_web_page_definition(
    provider_config: Mapping[str, JsonValue],
) -> ToolDefinition:
    """通过 current provider discovery 取得 ``fetch_web_page`` 定义。

    Args:
        provider_config: single-diagnostic orchestration 生成的 raw provider 配置。

    Returns:
        current ``fetch_web_page`` 的 ``ToolDefinition``。

    Raises:
        RuntimeError: provider 未返回目标工具时抛出。
        ValueError: provider config 非法时由 current provider 抛出。
    """

    spec = ToolsDiscoveryProviderSpec(
        spec_id="diagnose-web-tools",
        location=PythonImportPathProvider("dayu.tools.web.provider:discover_tools"),
        enabled=True,
        config=provider_config,
    )
    output = discover_tools(spec)
    for definition in output.definitions:
        if definition.name == _FETCH_TOOL_NAME:
            return definition
    raise RuntimeError("current Web provider 未返回 fetch_web_page 定义，诊断无法继续。")


def _tool_call_context(options: CliOptions) -> BatchToolExecutionContext:
    """构造 current tool callable 所需的批式上下文。

    Args:
        options: CLI 选项。

    Returns:
        ``BatchToolExecutionContext``。

    Raises:
        ValueError: timeout budget 非法时由契约类型抛出。
    """

    return BatchToolExecutionContext(
        run_id="diagnose-web",
        session_id="diagnose-web",
        iteration_id="diagnose-web-iteration",
        timeout_seconds=options.tool_timeout_budget,
        cancellation_token=_DiagnosticCancellationToken(),
        correlation_id="diagnose-web:diagnose-web-iteration:tool_batch",
    )


async def _call_fetch_tool_async(
    definition: ToolDefinition,
    url: str,
    options: CliOptions,
) -> ToolCompletedOutcome | ToolFailedOutcome | ToolAwaitingOutcome | ToolCancelledOutcome:
    """调用 current ``ToolDefinition.callable``。

    Args:
        definition: current 工具定义。
        url: 待抓取 URL。
        options: CLI 选项。

    Returns:
        current 工具执行 outcome。

    Raises:
        Exception: current callable 边界可透传未被 adapter 捕获的异常。
    """

    call = ToolCallRequest(
        tool_call_id="diagnose-fetch-web-page",
        name=_FETCH_TOOL_NAME,
        arguments={"url": url},
        index_in_iteration=0,
        provider_state=None,
    )
    return await definition.callable(call, _tool_call_context(options))


def _json_object_from_value(value: JsonValue) -> JsonObject:
    """把 JSON 值收口为 JSON 对象。

    Args:
        value: current tool 返回的 JSON 值。

    Returns:
        若输入是对象则复制为 ``dict``，否则返回空对象。

    Raises:
        无。
    """

    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _new_docling_invocation_evidence(diagnostic_url: str) -> _DoclingInvocationEvidence:
    """创建未调用状态的 Docling invocation evidence。

    Args:
        diagnostic_url: 当前诊断 URL。

    Returns:
        未调用状态的证据容器。

    Raises:
        无。
    """

    return _DoclingInvocationEvidence(diagnostic_url=diagnostic_url)


def _docling_evidence_json_from_fetch_profile(
    *,
    diagnostic_url: str,
    fetch_profile: Mapping[str, JsonValue],
) -> JsonObject:
    """从 fetch profile 读取或补齐 Docling 调用证据。

    Args:
        diagnostic_url: 当前诊断 URL。
        fetch_profile: current ``fetch_web_page`` 路径 profile。

    Returns:
        Docling 调用证据 JSON 对象；没有观察到调用时返回 ``invoked=false``。

    Raises:
        无。
    """

    evidence = _nested_object(fetch_profile, "docling_conversion_invocation_evidence")
    if evidence:
        return evidence
    return _new_docling_invocation_evidence(diagnostic_url).to_json()


def _attach_docling_evidence(
    *,
    profile: JsonObject,
    evidence: _DoclingInvocationEvidence,
) -> JsonObject:
    """把 Docling 调用证据附加到 fetch profile。

    Args:
        profile: current fetch 工具 profile。
        evidence: 本次诊断采集到的 Docling 调用证据。

    Returns:
        已追加证据字段的 profile。

    Raises:
        无。
    """

    profile["docling_conversion_invocation_evidence"] = evidence.to_json()
    return profile


def _build_tool_fetch_profile(
    url: str,
    options: CliOptions,
    *,
    provider_config: Mapping[str, JsonValue],
) -> JsonObject:
    """采集 current ``fetch_web_page`` 工具路径证据。

    Args:
        url: 待诊断 URL。
        options: CLI 选项。
        provider_config: 与 raw requests transport snapshot 同源的 provider 配置。

    Returns:
        current fetch 工具 profile JSON 对象。

    Raises:
        无。
    """

    started_at = time.perf_counter()
    evidence = _new_docling_invocation_evidence(url)
    original_docling_callable: _DoclingConvertCallable = _web_tools_module._docling_convert_to_markdown
    wrapper = _DoclingInvocationWrapper(original=original_docling_callable, evidence=evidence)
    _web_tools_module._docling_convert_to_markdown = wrapper
    try:
        definition = _fetch_web_page_definition(provider_config)
        outcome = asyncio.run(_call_fetch_tool_async(definition, url, options))
    except Exception as exc:
        failure = failed_projection(
            stage="fetch_web_page",
            url=url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="callable_exception",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.TOOL,
        ).to_json()
        return _attach_docling_evidence(
            profile=failure,
            evidence=evidence,
        )
    finally:
        _web_tools_module._docling_convert_to_markdown = original_docling_callable

    elapsed = _round_elapsed(started_at)
    if isinstance(outcome, ToolCompletedOutcome):
        payload = _json_object_from_value(outcome.result.value)
        content = str(payload.get("content", "") or "")
        backend_text = str(payload.get("fetch_backend", "") or "")
        backend = (
            WebDiagnosticBackend.PLAYWRIGHT
            if backend_text == WebDiagnosticBackend.PLAYWRIGHT.value
            else WebDiagnosticBackend.REQUESTS
            if backend_text == WebDiagnosticBackend.REQUESTS.value
            else WebDiagnosticBackend.TOOL
        )
        completed = completed_text_projection(
            stage="fetch_web_page",
            url=str(payload.get("final_url", url) or url),
            elapsed_seconds=elapsed,
            backend=backend,
            content=content,
            http_status=None,
        ).to_json()
        projected_content = content_diagnostic_from_text(content)
        response_length = payload.get("response_content_length")
        response_digest = payload.get("response_content_digest")
        if (
            isinstance(response_length, int)
            and not isinstance(response_length, bool)
            and response_length >= 0
            and isinstance(response_digest, str)
        ):
            completed["content_length"] = response_length
            completed["content_digest"] = response_digest
        completed["projected_content_length"] = projected_content.length
        completed["projected_content_digest"] = projected_content.digest
        return _attach_docling_evidence(
            profile=completed,
            evidence=evidence,
        )
    if isinstance(outcome, ToolFailedOutcome):
        hint = outcome.result.hint or ""
        failure = failed_projection(
            stage="fetch_web_page",
            url=url,
            elapsed_seconds=elapsed,
            error_code=outcome.result.error,
            error_message=outcome.result.message,
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.TOOL,
        ).to_json()
        failure["next_action"] = _next_action_from_hint(hint)
        failure["diagnostics"] = _tool_failed_outcome_diagnostics(outcome.result.error)
        return _attach_docling_evidence(
            profile=failure,
            evidence=evidence,
        )
    if isinstance(outcome, ToolCancelledOutcome):
        cancelled = WebDiagnosticProjection(
            stage="fetch_web_page",
            sampled=True,
            outcome=WebDiagnosticOutcome.CANCELLED,
            safe_url=project_safe_url_or_empty(url),
            elapsed_seconds=elapsed,
            backend=WebDiagnosticBackend.TOOL,
            error_code=outcome.reason,
            error_message=project_error_message(
                outcome.message,
                max_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            ),
        ).to_json()
        return _attach_docling_evidence(
            profile=cancelled,
            evidence=evidence,
        )
    if isinstance(outcome, ToolAwaitingOutcome):
        awaiting = failed_projection(
            stage="fetch_web_page",
            url=url,
            elapsed_seconds=elapsed,
            error_code="unexpected_awaiting_outcome",
            error_message="fetch_web_page returned awaiting outcome in diagnostics.",
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.TOOL,
        ).to_json()
        return _attach_docling_evidence(
            profile=awaiting,
            evidence=evidence,
        )
    unknown = failed_projection(
        stage="fetch_web_page",
        url=url,
        elapsed_seconds=elapsed,
        error_code="unknown_outcome",
        error_message="current fetch_web_page returned an unknown outcome.",
        max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
        backend=WebDiagnosticBackend.TOOL,
    ).to_json()
    return _attach_docling_evidence(
        profile=unknown,
        evidence=evidence,
    )


def _next_action_from_hint(hint: str) -> str:
    """从 current Web 工具 hint 中恢复结构化 next action。

    Args:
        hint: current ``ToolFailedOutcome`` 携带的恢复提示。

    Returns:
        hint 以 ``[action]`` 开头时返回 action，否则返回空字符串。

    Raises:
        无。
    """

    match = _NEXT_ACTION_HINT_PATTERN.match(hint.strip())
    if match is None:
        return ""
    return match.group(1)


def _tool_failed_outcome_diagnostics(error_code: str) -> JsonObject:
    """构造 current failed outcome 的诊断字段来源说明。

    current adapter 只把 ``ToolBusinessError`` 的 code/message/hint 投影到
    ``ToolFailedOutcome``；Web 错误里的 http status 与内部诊断不会进入
    outcome。诊断 artifact 必须显式说明这个边界，避免把缺失字段误解为
    站点事实。

    Args:
        error_code: current failed outcome 的错误码。

    Returns:
        业务可读诊断来源说明。

    Raises:
        无。
    """

    return {
        "diagnostic_source": "current_tool_failed_outcome",
        "error_code": error_code,
        "available_fields": ["error_code", "message", "hint", "next_action_from_hint"],
        "note": (
            "current ToolFailedOutcome 不暴露 Web 工具内部 http_status 或 internal_diagnostics；"
            "本诊断只记录 outcome 可见字段，并从 hint 的 [action] 前缀恢复 next_action。"
        ),
    }


def _storage_state_owner_final_name(url: str) -> str:
    """按 URL host 构造 owner 命名的 storage-state final 文件名。

    Args:
        url: 当前诊断 URL。

    Returns:
        只包含 owner prefix、规范化 host 与 ``.json`` 后缀的文件名。

    Raises:
        ValueError: URL 无有效 host 时抛出。
    """

    host = (urlparse(_normalize_url_for_http(url)).hostname or "").strip().lower()
    if not host:
        raise ValueError("storage state URL 缺少 host。")
    label = re.sub(r"[^a-z0-9.-]+", "-", host).strip("-.")
    if not label:
        raise ValueError("storage state URL host 无法形成安全文件名。")
    return f"{_STORAGE_STATE_FINAL_PREFIX}{label}{_STORAGE_STATE_FINAL_SUFFIX}"


def _resolve_storage_state_paths(options: CliOptions, url: str) -> tuple[str, str]:
    """解析单 URL 的 storage state 输入与显式输出路径。

    Args:
        options: CLI 选项。
        url: 当前 URL。

    Returns:
        ``(storage_state_in, storage_state_out)``；目录只会推导输入，不会启用输出。

    Raises:
        ValueError: 输出未同时提供正 TTL，或 final 不是 owner 命名时抛出。
    """

    storage_state_in = options.storage_state_in
    storage_state_out = options.storage_state_out
    if options.storage_state_dir:
        storage_dir = Path(options.storage_state_dir).expanduser().resolve()
        host_path = storage_dir / _storage_state_owner_final_name(url)
        if not storage_state_in and host_path.is_file():
            storage_state_in = str(host_path)
    if storage_state_out:
        final_path = Path(storage_state_out).expanduser().resolve()
        if options.storage_state_ttl_seconds <= 0:
            raise ValueError("--storage-state-out 必须同时提供正的 --storage-state-ttl-seconds。")
        if final_path.name != _storage_state_owner_final_name(url):
            raise ValueError(
                "storage state final 必须使用当前 URL host 对应的 owner 命名。"
            )
        storage_state_out = str(final_path)
    elif options.storage_state_ttl_seconds != 0:
        raise ValueError("--storage-state-ttl-seconds 只能与显式 --storage-state-out 一起使用。")
    return storage_state_in, storage_state_out


def _ensure_private_storage_directory(path: Path) -> None:
    """确保 storage-state 输出父目录为 ``0700``。

    Args:
        path: 输出父目录。

    Returns:
        无。

    Raises:
        OSError: 目录创建、检查或 chmod 失败时抛出。
        ValueError: 已存在父目录不是 ``0700`` 时抛出，避免修改共享目录权限。
    """

    if path.exists():
        if not path.is_dir():
            raise ValueError("storage state 父路径不是目录。")
        if path.stat().st_mode & 0o777 != _PRIVATE_DIRECTORY_MODE:
            raise ValueError("storage state 已存在父目录必须预先设置为 0700。")
        return
    # 中间目录属于调用方路径结构，按普通 umask 创建；只有 storage owner 的
    # 最终目录由本 helper 收紧到 0700。
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
    os.chmod(path, _PRIVATE_DIRECTORY_MODE)


def _reconcile_storage_state_directory(
    directory: Path,
    *,
    ttl_seconds: int,
    now_epoch_seconds: float | None = None,
) -> None:
    """删除本 owner 命名的 orphan temp 与过期 final。

    Args:
        directory: 已明确 opt-in 的目标目录。
        ttl_seconds: 判断 final 过期的正 TTL 秒数。
        now_epoch_seconds: 测试可注入的当前 epoch 秒数。

    Returns:
        无。

    Raises:
        ValueError: TTL 不是正整数时抛出。
        OSError: 目录扫描、stat 或 owner 文件删除失败时抛出。
    """

    if isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
        raise ValueError("storage state TTL must be a positive integer")
    now_value = time.time() if now_epoch_seconds is None else now_epoch_seconds
    for candidate in directory.iterdir():
        name = candidate.name
        if name.startswith(_STORAGE_STATE_TEMP_PREFIX) and name.endswith(
            _STORAGE_STATE_TEMP_SUFFIX
        ):
            candidate.unlink(missing_ok=True)
            continue
        if not (
            name.startswith(_STORAGE_STATE_FINAL_PREFIX)
            and name.endswith(_STORAGE_STATE_FINAL_SUFFIX)
        ):
            continue
        if candidate.stat().st_mtime + ttl_seconds <= now_value:
            candidate.unlink(missing_ok=True)


def _prepare_storage_state_lifecycle(
    options: CliOptions,
    url: str,
) -> _StorageStateLifecycle:
    """解析 opt-in 并在 diagnostic 启动时执行 owner 范围 reconciliation。

    Args:
        options: CLI 选项。
        url: 当前诊断 URL。

    Returns:
        当前 run 的 storage-state lifecycle。

    Raises:
        ValueError: opt-in、owner 命名或目录权限非法时抛出。
        OSError: 目录或 startup cleanup 失败时抛出。
    """

    storage_state_in, storage_state_out = _resolve_storage_state_paths(options, url)
    input_path = (
        Path(storage_state_in).expanduser().resolve() if storage_state_in else None
    )
    final_path = Path(storage_state_out) if storage_state_out else None
    lifecycle = _StorageStateLifecycle(
        input_path=input_path,
        final_path=final_path,
        ttl_seconds=options.storage_state_ttl_seconds if final_path is not None else 0,
    )
    if final_path is not None:
        _ensure_private_storage_directory(final_path.parent)
        _reconcile_storage_state_directory(
            final_path.parent,
            ttl_seconds=options.storage_state_ttl_seconds,
        )
    return lifecycle


def _safe_close_context(context: _BrowserContextProtocol | None) -> None:
    """关闭 Playwright context，忽略清理异常。

    Args:
        context: 可选浏览器上下文。

    Returns:
        无。

    Raises:
        无。
    """

    if context is None:
        return
    try:
        context.close()
    except Exception:
        return


def _safe_close_browser(browser: _BrowserProtocol | None) -> None:
    """关闭 Playwright browser，忽略清理异常。

    Args:
        browser: 可选浏览器实例。

    Returns:
        无。

    Raises:
        无。
    """

    if browser is None:
        return
    try:
        browser.close()
    except Exception:
        return


def _request_event_summary(event: _RequestProtocol) -> JsonObject:
    """构造 Playwright request 事件摘要。

    Args:
        event: Playwright request 事件。

    Returns:
        业务可读 JSON 摘要。

    Raises:
        无。
    """

    return {
        **project_network_event(
            event="request",
            url=event.url,
            method=event.method,
            resource_type=event.resource_type,
            status_code=None,
        )
    }


def _response_event_summary(event: _ResponseProtocol) -> JsonObject:
    """构造 Playwright response 事件摘要。

    Args:
        event: Playwright response 事件。

    Returns:
        业务可读 JSON 摘要。

    Raises:
        无。
    """

    return project_network_event(
        event="response",
        url=event.url,
        method=event.request.method,
        resource_type=event.request.resource_type,
        status_code=event.status,
    )


def _network_event_summary(event: _PlaywrightNetworkEvent) -> JsonObject:
    """把 Playwright 网络事件转成 JSON 摘要。

    Args:
        event: request 或 response 事件。

    Returns:
        业务可读 JSON 摘要。

    Raises:
        无。
    """

    if isinstance(event, _ResponseProtocol):
        return _response_event_summary(event)
    return _request_event_summary(event)


def _append_bounded_network_event(
    events: list[JsonValue],
    event: _PlaywrightNetworkEvent,
    *,
    max_network: int,
) -> None:
    """追加有上限的网络事件摘要。

    Args:
        events: 已收集事件列表。
        event: Playwright 网络事件。
        max_network: 最大事件数。

    Returns:
        无。

    Raises:
        无。
    """

    if len(events) >= max_network:
        return
    try:
        events.append(_network_event_summary(event))
    except Exception as exc:
        events.append(
            {
                "event": "network_summary_error",
                "error_type": type(exc).__name__,
                "error_message": project_error_message(
                    str(exc),
                    max_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
                ),
            }
        )


def _wait_for_manual_confirmation(prompt_text: str) -> None:
    """等待人工确认后继续。

    Args:
        prompt_text: 终端提示文本。

    Returns:
        无。

    Raises:
        无。
    """

    try:
        input(prompt_text)
    except EOFError:
        print("[诊断] stdin 不可交互，跳过人工确认等待。")


def _route_diagnostic_browser_request(
    route: _RouteProtocol,
    request: _RequestProtocol,
    *,
    egress_policy: WebEgressPolicy,
) -> None:
    """按 local/dev policy 裁决 diagnostic browser subrequest。

    Args:
        route: 当前 Playwright route。
        request: Playwright 传入的同一 request 事件；URL 仍从 route owner 读取。
        egress_policy: 当前 diagnostic 调用共享的 Web 出站策略。

    Returns:
        无。

    Raises:
        无。被拒绝 request 会直接 abort。
    """

    del request
    if egress_policy.is_url_allowed(route.request.url):
        route.continue_()
    else:
        route.abort()


def _read_bounded_playwright_response_body(
    response: _ResponseProtocol,
    *,
    http_resource_budget: HttpResourceBudget,
) -> bytes:
    """读取 Playwright 主响应 bytes，并复用共享 decoded-body budget。

    Playwright 不提供 response body 流式迭代接口，因此先用可信度较低的
    Content-Length 做早拒绝，再对实际返回 bytes 做强制后验上限。该 helper
    只用于显式 private/local diagnostic profile；公网 direct browser 默认不可用。

    Args:
        response: Playwright 主导航 response。
        http_resource_budget: HTTP decoded body 预算。

    Returns:
        未超过上限的 response body bytes。

    Raises:
        _DiagnosticBrowserBodyLimitExceeded: 声明值或实读值超过上限时抛出。
        Exception: Playwright body 读取失败时透出。
    """

    raw_content_length = response.headers.get("content-length") or response.headers.get(
        "Content-Length"
    )
    if raw_content_length is not None:
        try:
            declared_length = int(str(raw_content_length).strip())
        except ValueError:
            declared_length = 0
        if declared_length > http_resource_budget.decoded_body_bytes:
            raise _DiagnosticBrowserBodyLimitExceeded(
                "Playwright diagnostic response body exceeds decoded-body limit."
            )
    body = response.body()
    if len(body) > http_resource_budget.decoded_body_bytes:
        raise _DiagnosticBrowserBodyLimitExceeded(
            "Playwright diagnostic response body exceeds decoded-body limit."
        )
    return body


def _build_playwright_profile(
    url: str,
    options: CliOptions,
    *,
    egress_policy: WebEgressPolicy,
) -> JsonObject:
    """采集 Playwright 浏览器路径证据。

    Args:
        url: 待诊断 URL。
        options: CLI 选项。
        egress_policy: 当前 diagnostic 调用共享的 Web 出站策略。

    Returns:
        Playwright profile JSON 对象。

    Raises:
        无。
    """

    storage_lifecycle = _prepare_storage_state_lifecycle(options, url)
    started_at = time.perf_counter()
    if not egress_policy.allows_private_network:
        profile = _skipped_profile(
            "browser_egress_policy_unavailable",
            url=url,
            backend=WebDiagnosticBackend.PLAYWRIGHT,
        )
        profile["storage_state"] = storage_lifecycle.artifact_projection()
        return profile
    try:
        target = egress_policy.authorize_http_target(
            _normalize_url_for_http(url),
            stage="diagnostic_playwright_input",
        )
        normalized_url = target.normalized_url
    except (ValueError, WebEgressPolicyError) as exc:
        profile = failed_projection(
            stage="playwright",
            url=url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="blocked_by_web_egress_policy",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.PLAYWRIGHT,
            sampled=False,
        ).to_json()
        profile["storage_state"] = storage_lifecycle.artifact_projection()
        return profile

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        profile = failed_projection(
            stage="playwright",
            url=url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="playwright_package_missing",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.PLAYWRIGHT,
            sampled=False,
        ).to_json()
        profile["storage_state"] = storage_lifecycle.artifact_projection()
        return profile

    browser: _BrowserProtocol | None = None
    context: _BrowserContextProtocol | None = None
    network_events: list[JsonValue] = []
    launch_options: JsonObject = {"headless": not options.headed}
    if options.playwright_channel:
        launch_options["channel"] = options.playwright_channel
    context_options: JsonObject = {
        "user_agent": _DEFAULT_USER_AGENT,
        "ignore_https_errors": True,
    }
    if storage_lifecycle.input_path is not None:
        context_options["storage_state"] = str(storage_lifecycle.input_path)

    try:
        manager = cast(_PlaywrightContextManagerProtocol, sync_playwright())
        with manager as playwright:
            browser = playwright.chromium.launch(**launch_options)
            context = browser.new_context(**context_options)
            page = context.new_page()
            page.route(
                "**/*",
                partial(_route_diagnostic_browser_request, egress_policy=egress_policy),
            )
            page.on(
                "request",
                lambda event: _append_bounded_network_event(network_events, event, max_network=options.max_network),
            )
            page.on(
                "response",
                lambda event: _append_bounded_network_event(network_events, event, max_network=options.max_network),
            )
            response = page.goto(
                normalized_url,
                wait_until="domcontentloaded",
                timeout=options.playwright_timeout * 1000.0,
            )
            if options.manual_wait_seconds > 0:
                time.sleep(options.manual_wait_seconds)
            if options.pause_before_snapshot:
                _wait_for_manual_confirmation("[诊断] 按 Enter 后采样页面并保存 storage state...")
            page_projection = _web_playwright_backend._materialize_bounded_page_projection(
                cast(_web_playwright_backend._PageProtocol, page),
                browser_resource_budget=_DIAGNOSTIC_BROWSER_RESOURCE_BUDGET,
            )
            html = page_projection.html
            page_text = page_projection.page_text
            status_code = response.status if response is not None else None
            final_url = response.url if response is not None else normalized_url
            response_headers = response.headers if response is not None else {}
            response_body = (
                _read_bounded_playwright_response_body(
                    response,
                    http_resource_budget=_DIAGNOSTIC_HTTP_RESOURCE_BUDGET,
                )
                if response is not None
                else b""
            )
            challenge = detect_bot_challenge(
                response=None,
                response_headers=response_headers,
                http_status=status_code,
                content_text=f"{page_text}\n{html}",
            )
            storage_lifecycle.publish(context)
            profile = completed_bytes_projection(
                stage="playwright",
                url=final_url,
                elapsed_seconds=_round_elapsed(started_at),
                backend=WebDiagnosticBackend.PLAYWRIGHT,
                content=response_body,
                http_status=status_code,
                response_headers=response_headers,
            ).to_json()
            rendered_html_diagnostic = content_diagnostic_from_text(html)
            rendered_text_diagnostic = content_diagnostic_from_text(page_text)
            profile["rendered_html_length"] = rendered_html_diagnostic.length
            profile["rendered_html_digest"] = rendered_html_diagnostic.digest
            profile["rendered_text_length"] = rendered_text_diagnostic.length
            profile["rendered_text_digest"] = rendered_text_diagnostic.digest
            profile["browser_executed"] = True
            profile["challenge_decision"] = challenge.decision.value
            profile["challenge_signals"] = list(challenge.challenge_signals)
            profile["network_events"] = network_events
            profile["network_event_count"] = len(network_events)
            profile["network_event_limit"] = options.max_network
            profile["storage_state"] = storage_lifecycle.artifact_projection()
            return profile
    except _DiagnosticBrowserBodyLimitExceeded as exc:
        storage_lifecycle.cleanup_failure()
        profile = failed_projection(
            stage="playwright",
            url=url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="response_body_too_large",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.PLAYWRIGHT,
        ).to_json()
        profile["browser_executed"] = True
        profile["network_events"] = network_events
        profile["network_event_count"] = len(network_events)
        profile["network_event_limit"] = options.max_network
        profile["storage_state"] = storage_lifecycle.artifact_projection()
        return profile
    except Exception as exc:
        storage_lifecycle.cleanup_failure()
        profile = failed_projection(
            stage="playwright",
            url=url,
            elapsed_seconds=_round_elapsed(started_at),
            error_code="playwright_error",
            error_message=str(exc),
            max_error_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
            backend=WebDiagnosticBackend.PLAYWRIGHT,
        ).to_json()
        profile["browser_executed"] = True
        profile["network_events"] = network_events
        profile["network_event_count"] = len(network_events)
        profile["network_event_limit"] = options.max_network
        profile["storage_state"] = storage_lifecycle.artifact_projection()
        return profile
    except BaseException:
        storage_lifecycle.cleanup_failure()
        raise
    finally:
        _safe_close_context(context)
        _safe_close_browser(browser)


def _skipped_profile(
    reason: str,
    *,
    url: str,
    backend: WebDiagnosticBackend,
) -> JsonObject:
    """构造未采样路径 profile。

    Args:
        reason: 稳定跳过原因。
        url: 原始 URL。
        backend: 被跳过的 backend。

    Returns:
        JSON profile。

    Raises:
        无。
    """

    return WebDiagnosticProjection(
        stage=backend.value,
        sampled=False,
        outcome=WebDiagnosticOutcome.SKIPPED,
        safe_url=project_safe_url_or_empty(url),
        elapsed_seconds=0.0,
        backend=backend,
        error_code=reason,
    ).to_json()


def _bool_from_mapping(mapping: Mapping[str, JsonValue], key: str) -> bool:
    """从 JSON 对象读取布尔值。

    Args:
        mapping: JSON 对象。
        key: 字段名。

    Returns:
        字段为 ``True`` 时返回 ``True``。

    Raises:
        无。
    """

    return mapping.get(key) is True


def _nested_object(mapping: Mapping[str, JsonValue], key: str) -> JsonObject:
    """从 JSON 对象读取子对象。

    Args:
        mapping: JSON 对象。
        key: 字段名。

    Returns:
        子对象副本；不存在或类型不匹配时返回空对象。

    Raises:
        无。
    """

    value = mapping.get(key)
    if isinstance(value, Mapping):
        return {str(nested_key): nested_value for nested_key, nested_value in value.items()}
    return {}


def _string_list(value: JsonValue | None) -> list[JsonValue]:
    """把 JSON 值规整为字符串 JSON 数组。

    Args:
        value: 原始 JSON 值。

    Returns:
        字符串数组。

    Raises:
        无。
    """

    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _classify_diagnostic_bucket(payload: Mapping[str, JsonValue]) -> str:
    """按访问路径结果给单 URL 诊断分桶。

    Args:
        payload: 单 URL 诊断 payload。

    Returns:
        deterministic comparison bucket。

    Raises:
        无。
    """

    playwright_profile = _nested_object(payload, "playwright_profile")
    requests_profile = _nested_object(payload, "requests_profile")
    fetch_profile = _nested_object(payload, "fetch_web_page_profile")

    playwright_sampled = _bool_from_mapping(playwright_profile, "sampled")
    requests_sampled = _bool_from_mapping(requests_profile, "sampled")
    fetch_sampled = _bool_from_mapping(fetch_profile, "sampled")
    playwright_ok = playwright_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value
    requests_ok = requests_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value
    fetch_ok = fetch_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value
    child_process_error = str(payload.get("status", "") or "") == "child_process_error"
    challenge_detected = (
        playwright_profile.get("challenge_decision") == BotChallengeDecision.CONFIRMED.value
    )
    playwright_failed = playwright_sampled and not playwright_ok
    requests_failed = requests_sampled and not requests_ok
    fetch_failed = fetch_sampled and not fetch_ok
    sampled_path_count = int(playwright_sampled) + int(requests_sampled) + int(fetch_sampled)

    if child_process_error:
        return "child_process_error"
    if playwright_sampled and challenge_detected:
        return "playwright_challenge_detected"
    if playwright_sampled and fetch_sampled and requests_sampled and playwright_ok and requests_ok and fetch_ok:
        return "all_success"
    if fetch_sampled and fetch_ok and requests_failed and playwright_failed:
        return "fetch_only_success"
    if fetch_sampled and fetch_ok and requests_failed and (not playwright_sampled or playwright_failed):
        return "fetch_outperforms_requests"
    if requests_sampled and requests_ok and not fetch_sampled and not playwright_sampled:
        return "requests_only_sampled"
    if requests_sampled and requests_ok and fetch_failed and (not playwright_sampled or playwright_failed):
        return "requests_only_success"
    if playwright_sampled and playwright_ok and fetch_failed and requests_failed:
        return "browser_only_success"
    if requests_sampled and requests_ok and fetch_sampled and fetch_ok and playwright_failed:
        return "requests_and_fetch_success_playwright_failed"
    if fetch_failed and (requests_ok or playwright_ok):
        return "fetch_only_failure"
    if sampled_path_count > 0 and (
        (not playwright_sampled or playwright_failed)
        and (not requests_sampled or requests_failed)
        and (not fetch_sampled or fetch_failed)
    ):
        return "all_failed"
    if sampled_path_count > 0:
        return "partial_sample"
    return "mixed"


def _build_single_diagnostic_payload(options: CliOptions) -> JsonObject:
    """构造单 URL 诊断 payload。

    Args:
        options: CLI 选项。

    Returns:
        单 URL 诊断 JSON 对象。

    Raises:
        ValueError: 单 URL 模式缺少 ``--url`` 时抛出。
    """

    if not options.url:
        raise ValueError("单 URL 模式必须提供 --url。")

    provider_config = _provider_config(options)
    transport_policy = _parse_config(provider_config).transport_policy
    egress_policy = WebEgressPolicy(
        allow_private_network=options.allow_private_network_url,
        allow_custom_port=options.allow_private_network_url,
    )
    payload: JsonObject = {
        "schema_version": _SCHEMA_VERSION,
        "diagnostic_schema_version": _SCHEMA_VERSION,
        "diagnostic_schema_revision": _DIAGNOSTIC_SCHEMA_REVISION,
        "generated_at": _utc_now_iso(),
        "safe_url": project_safe_url_or_empty(options.url),
    }
    payload["requests_profile"] = (
        _skipped_profile(
            "user_skipped_requests",
            url=options.url,
            backend=WebDiagnosticBackend.REQUESTS,
        )
        if options.skip_requests
        else _build_requests_profile(
            options.url,
            timeout_seconds=options.request_timeout,
            egress_policy=egress_policy,
            transport_policy=transport_policy,
        )
    )
    payload["fetch_web_page_profile"] = (
        _skipped_profile(
            "user_skipped_tool_fetch",
            url=options.url,
            backend=WebDiagnosticBackend.TOOL,
        )
        if options.skip_tool_fetch
        else _build_tool_fetch_profile(
            options.url,
            options,
            provider_config=provider_config,
        )
    )
    payload["docling_conversion_invocation_evidence"] = _docling_evidence_json_from_fetch_profile(
        diagnostic_url=options.url,
        fetch_profile=_nested_object(payload, "fetch_web_page_profile"),
    )
    if options.skip_playwright:
        storage_lifecycle = _prepare_storage_state_lifecycle(options, options.url)
        playwright_profile = _skipped_profile(
            "user_skipped_playwright",
            url=options.url,
            backend=WebDiagnosticBackend.PLAYWRIGHT,
        )
        playwright_profile["storage_state"] = storage_lifecycle.artifact_projection()
        payload["playwright_profile"] = playwright_profile
    else:
        payload["playwright_profile"] = _build_playwright_profile(
            options.url,
            options,
            egress_policy=egress_policy,
        )
    payload["comparison_bucket"] = _classify_diagnostic_bucket(payload)
    return payload


def _write_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    """写 JSON 文件。

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


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, JsonValue]]) -> None:
    """写 JSONL 文件。

    Args:
        path: 输出路径。
        rows: JSON 对象行序列。

    Returns:
        无。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
    if content:
        content = f"{content}\n"
    path.write_text(content, encoding="utf-8")


def _run_single_diagnose(options: CliOptions) -> int:
    """执行单 URL 诊断。

    Args:
        options: CLI 选项。

    Returns:
        进程退出码。

    Raises:
        ValueError: 参数非法时抛出。
        OSError: 输出文件写入失败时抛出。
    """

    output_path = Path(options.output).expanduser().resolve() if options.output else _default_output_path(options.url)
    payload = _build_single_diagnostic_payload(options)
    _write_json(output_path, payload)
    print(f"诊断结果已写入: {output_path}")
    return 0


def _read_json_line(raw_line: str, line_number: int) -> DiagnosticUrlEntry:
    """解析一行 JSONL URL 样本。

    Args:
        raw_line: 原始行文本。
        line_number: 行号。

    Returns:
        URL 样本。

    Raises:
        ValueError: JSON 或字段非法时抛出。
    """

    try:
        payload = cast(JsonValue, json.loads(raw_line))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSONL 第 {line_number} 行不是合法 JSON: {exc}") from exc
    if isinstance(payload, str):
        url = payload.strip()
        if not url:
            raise ValueError(f"JSONL 第 {line_number} 行 URL 为空。")
        return DiagnosticUrlEntry(url=url)
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSONL 第 {line_number} 行必须是对象或字符串。")
    url_value = payload.get("url")
    url = str(url_value or "").strip()
    if not url:
        raise ValueError(f"JSONL 第 {line_number} 行缺少 url。")
    return DiagnosticUrlEntry(
        url=url,
        label=str(payload.get("label", "") or "").strip(),
        region=str(payload.get("region", "") or "").strip(),
        category=str(payload.get("category", "") or "").strip(),
        notes=str(payload.get("notes", "") or "").strip(),
    )


def _read_jsonl_url_entries(path: Path) -> list[DiagnosticUrlEntry]:
    """读取 JSONL URL 样本。

    Args:
        path: JSONL 文件路径。

    Returns:
        URL 样本列表。

    Raises:
        ValueError: 文件内容非法时抛出。
        OSError: 文件读取失败时抛出。
    """

    entries: list[DiagnosticUrlEntry] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        entries.append(_read_json_line(line, line_number))
    return entries


def _read_txt_url_entries(path: Path) -> list[DiagnosticUrlEntry]:
    """读取 TXT URL 样本。

    Args:
        path: TXT 文件路径。

    Returns:
        URL 样本列表。

    Raises:
        OSError: 文件读取失败时抛出。
    """

    entries: list[DiagnosticUrlEntry] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(DiagnosticUrlEntry(url=line))
    return entries


def _deduplicate_url_entries(entries: Sequence[DiagnosticUrlEntry]) -> list[DiagnosticUrlEntry]:
    """按 URL 去重并保留首次出现的元数据。

    Args:
        entries: 原始 URL 样本序列。

    Returns:
        去重后的 URL 样本列表。

    Raises:
        无。
    """

    deduped: list[DiagnosticUrlEntry] = []
    seen_urls: set[str] = set()
    for entry in entries:
        url = entry.url.strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(
            DiagnosticUrlEntry(
                url=url,
                label=entry.label,
                region=entry.region,
                category=entry.category,
                notes=entry.notes,
            )
        )
    return deduped


def _read_url_entries(path: Path) -> list[DiagnosticUrlEntry]:
    """读取批量 URL 样本文件。

    Args:
        path: URL 文件路径。

    Returns:
        去重后的 URL 样本列表。

    Raises:
        ValueError: 文件内容非法时抛出。
        OSError: 文件读取失败时抛出。
    """

    entries = _read_jsonl_url_entries(path) if path.suffix.lower() in _JSONL_SUFFIXES else _read_txt_url_entries(path)
    return _deduplicate_url_entries(entries)


def _entry_json(entry: DiagnosticUrlEntry) -> JsonObject:
    """把 URL 样本转成 JSON 对象。

    Args:
        entry: URL 样本。

    Returns:
        JSON 对象。

    Raises:
        无。
    """

    payload = cast(JsonObject, asdict(entry))
    payload["url"] = project_safe_url_or_empty(entry.url)
    return payload


def _build_batch_child_command(
    *,
    entry: DiagnosticUrlEntry,
    diagnostic_path: Path,
    options: CliOptions,
) -> list[str]:
    """构造批量模式下的单 URL 子进程命令。

    Args:
        entry: 当前 URL 样本。
        diagnostic_path: 单 URL 诊断输出路径。
        options: CLI 选项。

    Returns:
        子进程命令数组。

    Raises:
        无。
    """

    command = [
        sys.executable,
        "-m",
        "utils.diagnose_web_access",
        "--url",
        entry.url,
        "--output",
        str(diagnostic_path),
        "--request-timeout",
        str(options.request_timeout),
        "--tool-timeout-budget",
        str(options.tool_timeout_budget),
        "--playwright-timeout",
        str(options.playwright_timeout),
        "--playwright-channel",
        options.playwright_channel,
        "--max-network",
        str(options.max_network),
        "--fetch-truncate-chars",
        str(options.fetch_truncate_chars),
    ]
    if options.storage_state_dir:
        command.extend(["--storage-state-dir", options.storage_state_dir])
    if options.storage_state_in:
        command.extend(["--storage-state-in", options.storage_state_in])
    if options.storage_state_out:
        command.extend(["--storage-state-out", options.storage_state_out])
        command.extend(
            ["--storage-state-ttl-seconds", str(options.storage_state_ttl_seconds)]
        )
    if options.headed:
        command.append("--headed")
    if options.manual_wait_seconds > 0:
        command.extend(["--manual-wait-seconds", str(options.manual_wait_seconds)])
    if options.pause_before_snapshot:
        command.append("--pause-before-snapshot")
    if options.skip_playwright:
        command.append("--skip-playwright")
    if options.skip_requests:
        command.append("--skip-requests")
    if options.skip_tool_fetch:
        command.append("--skip-tool-fetch")
    if options.allow_private_network_url:
        command.append("--allow-private-network-url")
    return command


def _load_diagnostic_payload(path: Path) -> JsonObject:
    """读取单 URL 诊断 JSON。

    Args:
        path: 诊断 JSON 路径。

    Returns:
        JSON 对象。

    Raises:
        ValueError: 文件内容不是 JSON 对象时抛出。
        OSError: 文件读取失败时抛出。
    """

    payload = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, Mapping):
        raise ValueError(f"诊断文件不是 JSON 对象: {path}")
    normalized = {str(key): value for key, value in payload.items()}
    if normalized.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(f"诊断文件 schema_version 不是 {_SCHEMA_VERSION}: {path}")
    if normalized.get("diagnostic_schema_version") != _SCHEMA_VERSION:
        raise ValueError(f"诊断文件 diagnostic_schema_version 不是 {_SCHEMA_VERSION}: {path}")
    if normalized.get("diagnostic_schema_revision") != _DIAGNOSTIC_SCHEMA_REVISION:
        raise ValueError(f"诊断文件 revision 不是 {_DIAGNOSTIC_SCHEMA_REVISION}: {path}")
    return normalized


def _status_code_value(mapping: Mapping[str, JsonValue], key: str) -> JsonValue:
    """读取状态码字段。

    Args:
        mapping: JSON 对象。
        key: 字段名。

    Returns:
        状态码或 ``None``。

    Raises:
        无。
    """

    value = mapping.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _docling_runtime_initialization_observed(payload: Mapping[str, JsonValue]) -> bool:
    """判断 payload 是否观察到 Docling 运行时初始化或依赖异常。

    Args:
        payload: 单 URL 诊断 payload 或批量结果行。

    Returns:
        观察到 Docling 初始化或依赖异常时返回 ``True``。

    Raises:
        无。
    """

    evidence = _nested_object(payload, "docling_conversion_invocation_evidence")
    if evidence.get("docling_runtime_initialization_error") is True:
        return True
    if payload.get("docling_runtime_initialization_error") is True:
        return True
    return False


def _observed_bucket_from_payload(
    *,
    payload: Mapping[str, JsonValue],
    comparison_bucket: str,
) -> str:
    """从诊断 payload 得到 observed bucket。

    Args:
        payload: 单 URL 诊断 payload 或批量结果行。
        comparison_bucket: 访问路径 comparison bucket。

    Returns:
        observed bucket。Docling 初始化或依赖异常会被提升为显式 skip 观察项。

    Raises:
        无。
    """

    if _docling_runtime_initialization_observed(payload):
        return _OBSERVED_BUCKET_DOCLING_RUNTIME_SKIP
    return comparison_bucket


def _observed_failing_path_from_payload(
    *,
    payload: Mapping[str, JsonValue],
    comparison_bucket: str,
) -> str:
    """从诊断 payload 推断已观察到的失败路径。

    Args:
        payload: 单 URL 诊断 payload 或批量结果行。
        comparison_bucket: 访问路径 comparison bucket。

    Returns:
        逗号分隔的失败路径名称；没有直接失败路径时返回空字符串。

    Raises:
        无。
    """

    if str(payload.get("status", "") or "") == _OBSERVED_BUCKET_CHILD_PROCESS_ERROR:
        return _PATH_CHILD_PROCESS
    if _docling_runtime_initialization_observed(payload):
        return _PATH_DOCLING_CONVERSION

    failing_paths: list[str] = []
    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    requests_profile = _nested_object(payload, "requests_profile")
    playwright_profile = _nested_object(payload, "playwright_profile")

    fetch_sampled = payload.get("fetch_sampled") is True or _bool_from_mapping(fetch_profile, "sampled")
    fetch_ok = payload.get("fetch_ok") is True or fetch_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value
    requests_sampled = payload.get("requests_sampled") is True or _bool_from_mapping(requests_profile, "sampled")
    requests_ok = payload.get("requests_ok") is True or requests_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value
    playwright_sampled = payload.get("playwright_sampled") is True or _bool_from_mapping(playwright_profile, "sampled")
    playwright_ok = payload.get("playwright_ok") is True or playwright_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value

    if fetch_sampled and not fetch_ok:
        failing_paths.append(_PATH_FETCH_WEB_PAGE)
    if requests_sampled and not requests_ok:
        failing_paths.append(_PATH_REQUESTS)
    if playwright_sampled and not playwright_ok:
        failing_paths.append(_PATH_PLAYWRIGHT)
    if not failing_paths and comparison_bucket not in {
        _OBSERVED_BUCKET_ALL_SUCCESS,
        _OBSERVED_BUCKET_PARTIAL_SAMPLE,
        _OBSERVED_BUCKET_REQUESTS_ONLY_SAMPLED,
    }:
        # 当前 fallback 仅服务既有 comparison bucket；新增 bucket 时需同步确认其是否代表真实失败路径。
        return comparison_bucket
    return ",".join(failing_paths)


def _diagnostic_action_hint_from_payload(
    *,
    payload: Mapping[str, JsonValue],
    comparison_bucket: str,
    observed_failing_path: str,
) -> str:
    """构造诊断动作建议。

    Args:
        payload: 单 URL 诊断 payload 或批量结果行。
        comparison_bucket: 访问路径 comparison bucket。
        observed_failing_path: 已观察到的失败路径。

    Returns:
        诊断动作建议；没有需要动作的事实时返回空字符串。

    Raises:
        无。
    """

    if str(payload.get("status", "") or "") == _OBSERVED_BUCKET_CHILD_PROCESS_ERROR:
        return "重新运行单 URL 诊断子进程，并检查 stdout/stderr length/digest 与诊断脚本参数。"
    if _docling_runtime_initialization_observed(payload):
        return "检查 Docling 运行时依赖、模型初始化与本机设备配置；这是诊断观察到的环境问题。"
    fetch_next_action = str(payload.get("fetch_next_action", "") or "")
    if fetch_next_action:
        return f"current fetch_web_page 提示下一步动作为 {fetch_next_action}。"
    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    nested_fetch_next_action = str(fetch_profile.get("next_action", "") or "")
    if nested_fetch_next_action:
        return f"current fetch_web_page 提示下一步动作为 {nested_fetch_next_action}。"
    if comparison_bucket == _OBSERVED_BUCKET_PLAYWRIGHT_CHALLENGE:
        return "浏览器路径观察到访问门禁或反爬挑战；需要换来源、补充登录态或转为外部诊断残留。"
    if observed_failing_path:
        return f"优先检查已观察失败路径：{observed_failing_path}。"
    return _OBSERVED_HINT_NONE


def _diagnostic_only_reason_from_payload(
    *,
    payload: Mapping[str, JsonValue],
    comparison_bucket: str,
) -> str:
    """构造 diagnostic-only 原因说明。

    Args:
        payload: 单 URL 诊断 payload 或批量结果行。
        comparison_bucket: 访问路径 comparison bucket。

    Returns:
        诊断事实说明；没有 diagnostic-only 原因时返回空字符串。

    Raises:
        无。
    """

    if _docling_runtime_initialization_observed(payload):
        return "Docling 初始化或依赖异常是运行环境事实，可由后续 smoke 作为环境 skip 依据。"
    if comparison_bucket == _OBSERVED_BUCKET_PLAYWRIGHT_CHALLENGE:
        return "观察到浏览器访问门禁或反爬挑战；该事实通常只适合作为外部站点诊断残留。"
    if comparison_bucket == _OBSERVED_BUCKET_BROWSER_ONLY_SUCCESS:
        return "只有浏览器路径成功，说明 raw requests/current fetch 与真实浏览器环境存在差异。"
    if str(payload.get("status", "") or "") == _OBSERVED_BUCKET_CHILD_PROCESS_ERROR:
        return "单 URL 诊断子进程失败；该行没有可信单 URL 诊断 JSON，只能作为诊断基础设施事实。"
    return _OBSERVED_REASON_NONE


def _build_observed_diagnostic_item(row: Mapping[str, JsonValue]) -> JsonObject:
    """把批量结果行投影为 smoke 可消费的 observed fact。

    Args:
        row: 批量结果行。

    Returns:
        observed fact JSON 对象，包含 URL、证据路径、失败路径和诊断动作建议。

    Raises:
        无。
    """

    comparison_bucket = str(row.get("comparison_bucket", "") or "")
    observed_bucket = str(row.get("observed_bucket", "") or comparison_bucket)
    observed_failing_path = str(row.get("observed_failing_path", "") or "")
    diagnostic_action_hint = str(row.get("diagnostic_action_hint", "") or "")
    diagnostic_only_reason = str(row.get("diagnostic_only_reason", "") or "")
    evidence_path = str(row.get("evidence_path", "") or row.get("diagnostic_path", "") or "")
    failure_url = str(row.get("failure_safe_url", "") or "")
    return {
        "input_index": row.get("input_index"),
        "safe_url": str(row.get("safe_url", "") or ""),
        "label": str(row.get("label", "") or ""),
        "observed_bucket": observed_bucket,
        "comparison_bucket": comparison_bucket,
        "observed_failing_path": observed_failing_path,
        "evidence_path": evidence_path,
        "failure_safe_url": failure_url,
        "diagnostic_action_hint": diagnostic_action_hint,
        "diagnostic_only_reason": diagnostic_only_reason,
        "diagnostic_schema_version": str(row.get("diagnostic_schema_version", "")),
        "diagnostic_schema_revision": row.get("diagnostic_schema_revision"),
    }


def _observed_items_with_reason(rows: Sequence[Mapping[str, JsonValue]]) -> list[JsonValue]:
    """筛选带 diagnostic-only reason 的 observed items。

    Args:
        rows: 批量结果行。

    Returns:
        带 diagnostic-only reason 的 observed item 列表。

    Raises:
        无。
    """

    items: list[JsonValue] = []
    for row in rows:
        item = _build_observed_diagnostic_item(row)
        if str(item.get("diagnostic_only_reason", "") or ""):
            items.append(item)
    return items


def _skip_observed_items(rows: Sequence[Mapping[str, JsonValue]]) -> list[JsonValue]:
    """筛选可作为环境 skip 依据的 observed items。

    Args:
        rows: 批量结果行。

    Returns:
        只包含 Docling 初始化或依赖异常等 skip 观察项的列表。

    Raises:
        无。
    """

    items: list[JsonValue] = []
    for row in rows:
        item = _build_observed_diagnostic_item(row)
        if str(item.get("observed_bucket", "") or "") == _OBSERVED_BUCKET_DOCLING_RUNTIME_SKIP:
            items.append(item)
    return items


def _diagnostic_action_hints(rows: Sequence[Mapping[str, JsonValue]]) -> list[JsonValue]:
    """提取批量结果中的诊断动作建议。

    Args:
        rows: 批量结果行。

    Returns:
        含 URL、证据路径和动作建议的列表。

    Raises:
        无。
    """

    hints: list[JsonValue] = []
    for row in rows:
        hint = str(row.get("diagnostic_action_hint", "") or "")
        if not hint:
            continue
        hints.append(
            {
                "safe_url": str(row.get("safe_url", "") or ""),
                "evidence_path": str(row.get("evidence_path", "") or row.get("diagnostic_path", "") or ""),
                "diagnostic_action_hint": hint,
            }
        )
    return hints


def _build_batch_result_row(
    *,
    entry: DiagnosticUrlEntry,
    diagnostic_path: Path | None,
    payload: Mapping[str, JsonValue],
    index: int,
) -> JsonObject:
    """从单 URL 诊断 payload 提炼批量结果行。

    Args:
        entry: 输入 URL 样本。
        diagnostic_path: 单 URL 诊断路径；子进程失败时为 ``None``。
        payload: 单 URL payload 或子进程错误 payload。
        index: 输入序号。

    Returns:
        批量结果行。

    Raises:
        无。
    """

    playwright_profile = _nested_object(payload, "playwright_profile")
    requests_profile = _nested_object(payload, "requests_profile")
    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    docling_evidence = _nested_object(payload, "docling_conversion_invocation_evidence")
    if not docling_evidence:
        docling_evidence = _nested_object(fetch_profile, "docling_conversion_invocation_evidence")
    comparison_bucket = str(payload.get("comparison_bucket", ""))
    if not comparison_bucket:
        comparison_bucket = _classify_diagnostic_bucket(payload)
    observed_bucket = _observed_bucket_from_payload(payload=payload, comparison_bucket=comparison_bucket)
    observed_failing_path = _observed_failing_path_from_payload(
        payload=payload,
        comparison_bucket=comparison_bucket,
    )
    diagnostic_action_hint = _diagnostic_action_hint_from_payload(
        payload=payload,
        comparison_bucket=comparison_bucket,
        observed_failing_path=observed_failing_path,
    )
    diagnostic_only_reason = _diagnostic_only_reason_from_payload(
        payload=payload,
        comparison_bucket=comparison_bucket,
    )
    safe_url = project_safe_url_or_empty(entry.url)
    row: JsonObject = {
        "input_index": index,
        "safe_url": safe_url,
        "label": entry.label,
        "region": entry.region,
        "category": entry.category,
        "notes": entry.notes,
        "status": str(payload.get("status", "completed") or "completed"),
        "diagnostic_path": str(diagnostic_path) if diagnostic_path is not None else None,
        "comparison_bucket": comparison_bucket,
        "playwright_sampled": _bool_from_mapping(playwright_profile, "sampled"),
        "playwright_ok": playwright_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value,
        "playwright_status": str(playwright_profile.get("outcome", "") or ""),
        "playwright_error": str(playwright_profile.get("error_message", "") or ""),
        "playwright_response_status": _status_code_value(playwright_profile, "http_status"),
        "playwright_safe_url": str(playwright_profile.get("safe_url", safe_url) or safe_url),
        "challenge_detected": playwright_profile.get("challenge_decision") == BotChallengeDecision.CONFIRMED.value,
        "challenge_signals": _string_list(playwright_profile.get("challenge_signals")),
        "requests_sampled": _bool_from_mapping(requests_profile, "sampled"),
        "requests_ok": requests_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value,
        "requests_status": str(requests_profile.get("outcome", "") or ""),
        "requests_status_code": _status_code_value(requests_profile, "http_status"),
        "requests_error": str(requests_profile.get("error_message", "") or ""),
        "fetch_sampled": _bool_from_mapping(fetch_profile, "sampled"),
        "fetch_ok": fetch_profile.get("outcome") == WebDiagnosticOutcome.COMPLETED.value,
        "fetch_status": str(fetch_profile.get("outcome", "") or ""),
        "fetch_error_code": str(fetch_profile.get("error_code", "") or ""),
        "fetch_error": str(fetch_profile.get("error_message", "") or ""),
        "fetch_next_action": str(fetch_profile.get("next_action", "") or ""),
        "fetch_safe_url": str(fetch_profile.get("safe_url", safe_url) or safe_url),
        "docling_conversion_invoked": docling_evidence.get("invoked") is True,
        "docling_stream_name": str(docling_evidence.get("stream_name", "") or ""),
        "docling_original_exception_type": str(docling_evidence.get("original_exception_type", "") or ""),
        "docling_runtime_initialization_error": docling_evidence.get("docling_runtime_initialization_error") is True,
        "child_returncode": payload.get("returncode") if str(payload.get("status", "") or "") == "child_process_error" else None,
        "child_stdout_length": payload.get("stdout_length", 0),
        "child_stdout_digest": str(payload.get("stdout_digest", "") or ""),
        "child_stderr_length": payload.get("stderr_length", 0),
        "child_stderr_digest": str(payload.get("stderr_digest", "") or ""),
        "observed_bucket": observed_bucket,
        "observed_failing_path": observed_failing_path,
        "evidence_path": str(diagnostic_path) if diagnostic_path is not None else None,
        "failure_safe_url": safe_url if observed_failing_path else "",
        "diagnostic_action_hint": diagnostic_action_hint,
        "diagnostic_only_reason": diagnostic_only_reason,
        "diagnostic_schema_version": str(payload.get("schema_version", "")),
        "diagnostic_schema_revision": payload.get("diagnostic_schema_revision"),
    }
    return row


def _child_error_payload(
    *,
    completed: subprocess.CompletedProcess[str],
    entry: DiagnosticUrlEntry,
) -> JsonObject:
    """构造批量子进程失败 payload。

    Args:
        completed: 子进程结果。
        entry: 输入 URL 样本。

    Returns:
        子进程失败 JSON 对象。

    Raises:
        无。
    """

    stdout_diagnostic = content_diagnostic_from_text(completed.stdout or "")
    stderr_diagnostic = content_diagnostic_from_text(completed.stderr or "")
    payload: JsonObject = {
        "schema_version": _SCHEMA_VERSION,
        "diagnostic_schema_version": _SCHEMA_VERSION,
        "diagnostic_schema_revision": _DIAGNOSTIC_SCHEMA_REVISION,
        "generated_at": _utc_now_iso(),
        "safe_url": project_safe_url_or_empty(entry.url),
        "status": "child_process_error",
        "comparison_bucket": "child_process_error",
        "returncode": completed.returncode,
        "stdout_length": stdout_diagnostic.length,
        "stdout_digest": stdout_diagnostic.digest,
        "stderr_length": stderr_diagnostic.length,
        "stderr_digest": stderr_diagnostic.digest,
        "diagnostic_path": None,
        "message": "单 URL 诊断子进程异常退出；未生成可信诊断 JSON。",
    }
    return payload


def _count_by_key(rows: Sequence[Mapping[str, JsonValue]], key: str) -> JsonObject:
    """统计字符串字段分布。

    Args:
        rows: 批量结果行。
        key: 待统计字段。

    Returns:
        计数字典。

    Raises:
        无。
    """

    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "") or "").strip() or "<empty>"
        counts[value] = counts.get(value, 0) + 1
    return {key_value: count for key_value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))}


def _build_batch_summary(
    *,
    run_label: str,
    input_path: Path,
    rows: Sequence[Mapping[str, JsonValue]],
) -> JsonObject:
    """构造批量诊断 summary JSON。

    Args:
        run_label: 运行标签。
        input_path: 输入 URL 文件。
        rows: 批量结果行。

    Returns:
        summary JSON 对象。

    Raises:
        无。
    """

    return {
        "schema_version": _SCHEMA_VERSION,
        "diagnostic_schema_version": _SCHEMA_VERSION,
        "diagnostic_schema_revision": _DIAGNOSTIC_SCHEMA_REVISION,
        "generated_at": _utc_now_iso(),
        "run_label": run_label,
        "input_file": str(input_path),
        "input_url_count": len(rows),
        "child_process_error_count": sum(1 for row in rows if row.get("status") == "child_process_error"),
        "playwright_sampled_count": sum(1 for row in rows if row.get("playwright_sampled") is True),
        "playwright_ok_count": sum(1 for row in rows if row.get("playwright_sampled") is True and row.get("playwright_ok") is True),
        "requests_sampled_count": sum(1 for row in rows if row.get("requests_sampled") is True),
        "requests_ok_count": sum(1 for row in rows if row.get("requests_ok") is True),
        "fetch_sampled_count": sum(1 for row in rows if row.get("fetch_sampled") is True),
        "fetch_ok_count": sum(1 for row in rows if row.get("fetch_sampled") is True and row.get("fetch_ok") is True),
        "challenge_detected_count": sum(1 for row in rows if row.get("challenge_detected") is True),
        "comparison_buckets": _count_by_key(rows, "comparison_bucket"),
        "observed_buckets": _count_by_key(rows, "observed_bucket"),
        "observed_items": [_build_observed_diagnostic_item(row) for row in rows],
        "diagnostic_only_observed_items": _observed_items_with_reason(rows),
        "skip_observed_items": _skip_observed_items(rows),
        "diagnostic_action_hints": _diagnostic_action_hints(rows),
        "child_returncodes": _count_by_key(
            [row for row in rows if row.get("status") == "child_process_error"],
            "child_returncode",
        ),
        "playwright_statuses": _count_by_key(rows, "playwright_status"),
        "requests_statuses": _count_by_key(rows, "requests_status"),
        "fetch_statuses": _count_by_key(rows, "fetch_status"),
        "fetch_error_codes": _count_by_key(
            [row for row in rows if row.get("fetch_sampled") is True and row.get("fetch_ok") is not True],
            "fetch_error_code",
        ),
    }


def _markdown_count_section(title: str, values: Mapping[str, JsonValue]) -> list[str]:
    """构造 Markdown 计数章节。

    Args:
        title: 章节标题。
        values: 计数字典。

    Returns:
        Markdown 行列表。

    Raises:
        无。
    """

    lines = ["", f"## {title}", ""]
    if not values:
        lines.append("- 无")
        return lines
    for key, value in values.items():
        lines.append(f"- {key}: {value}")
    return lines


def _build_batch_summary_markdown(summary: Mapping[str, JsonValue]) -> str:
    """构造批量诊断 Markdown 汇总。

    Args:
        summary: summary JSON 对象。

    Returns:
        Markdown 文本。

    Raises:
        无。
    """

    lines = [
        f"# Web Access Diagnostics Batch Summary - {summary.get('run_label', '')}",
        "",
        f"- 生成时间：{summary.get('generated_at', '')}",
        f"- 输入文件：{summary.get('input_file', '')}",
        f"- URL 数量：{summary.get('input_url_count', 0)}",
        f"- 子进程异常：{summary.get('child_process_error_count', 0)}",
        f"- Playwright 已采样：{summary.get('playwright_sampled_count', 0)}",
        f"- Playwright 成功：{summary.get('playwright_ok_count', 0)}",
        f"- requests 已采样：{summary.get('requests_sampled_count', 0)}",
        f"- requests 成功：{summary.get('requests_ok_count', 0)}",
        f"- fetch_web_page 已采样：{summary.get('fetch_sampled_count', 0)}",
        f"- fetch_web_page 成功：{summary.get('fetch_ok_count', 0)}",
        f"- 检测到 challenge：{summary.get('challenge_detected_count', 0)}",
    ]
    lines.extend(_markdown_count_section("Comparison Buckets", _nested_object(summary, "comparison_buckets")))
    lines.extend(_markdown_count_section("Observed Buckets", _nested_object(summary, "observed_buckets")))
    lines.extend(_markdown_count_section("Child Return Codes", _nested_object(summary, "child_returncodes")))
    lines.extend(_markdown_count_section("Playwright Statuses", _nested_object(summary, "playwright_statuses")))
    lines.extend(_markdown_count_section("Requests Statuses", _nested_object(summary, "requests_statuses")))
    lines.extend(_markdown_count_section("Fetch Statuses", _nested_object(summary, "fetch_statuses")))
    lines.extend(_markdown_count_section("Fetch Error Codes", _nested_object(summary, "fetch_error_codes")))
    return "\n".join(lines) + "\n"


def _run_batch_diagnose(options: CliOptions) -> int:
    """执行批量 URL 诊断。

    Args:
        options: CLI 选项。

    Returns:
        进程退出码。

    Raises:
        ValueError: 输入文件缺失或为空时抛出。
        OSError: 文件读写失败时抛出。
    """

    if not options.url_file:
        raise ValueError("批量模式必须提供 --url-file。")
    input_path = Path(options.url_file).expanduser().resolve()
    if not input_path.is_file():
        raise ValueError(f"URL 文件不存在: {input_path}")
    entries = _read_url_entries(input_path)
    if not entries:
        raise ValueError("URL 文件中没有可用样本。")

    run_label = options.run_label or _default_run_label()
    run_dir = (
        Path(options.batch_output_dir).expanduser().resolve()
        if options.batch_output_dir
        else _default_batch_output_dir(run_label).expanduser().resolve()
    )
    diagnostics_dir = run_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(run_dir / "corpus.normalized.jsonl", (_entry_json(entry) for entry in entries))

    rows: list[JsonObject] = []
    interactive_mode = options.headed or options.pause_before_snapshot or options.manual_wait_seconds > 0
    for index, entry in enumerate(entries, start=1):
        diagnostic_path = diagnostics_dir / f"{index:04d}-{_slugify_for_filename(entry.url)}.json"
        print(
            f"[diagnose {index}/{len(entries)}] "
            f"{project_safe_url_or_empty(entry.url)}"
        )
        command = _build_batch_child_command(entry=entry, diagnostic_path=diagnostic_path, options=options)
        completed = subprocess.run(
            command,
            capture_output=not interactive_mode,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            payload = _child_error_payload(completed=completed, entry=entry)
            rows.append(_build_batch_result_row(entry=entry, diagnostic_path=None, payload=payload, index=index))
            continue
        try:
            payload = _load_diagnostic_payload(diagnostic_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            stdout_diagnostic = content_diagnostic_from_text(completed.stdout or "")
            stderr_diagnostic = content_diagnostic_from_text(
                f"{completed.stderr or ''}\n{type(exc).__name__}"
            )
            error_payload: JsonObject = {
                "schema_version": _SCHEMA_VERSION,
                "diagnostic_schema_version": _SCHEMA_VERSION,
                "diagnostic_schema_revision": _DIAGNOSTIC_SCHEMA_REVISION,
                "generated_at": _utc_now_iso(),
                "safe_url": project_safe_url_or_empty(entry.url),
                "status": "child_process_error",
                "comparison_bucket": "child_process_error",
                "returncode": completed.returncode,
                "stdout_length": stdout_diagnostic.length,
                "stdout_digest": stdout_diagnostic.digest,
                "stderr_length": stderr_diagnostic.length,
                "stderr_digest": stderr_diagnostic.digest,
                "diagnostic_path": None,
                "message": "单 URL 子进程退出后无法读取有效诊断 JSON。",
            }
            rows.append(_build_batch_result_row(entry=entry, diagnostic_path=None, payload=error_payload, index=index))
            continue
        rows.append(_build_batch_result_row(entry=entry, diagnostic_path=diagnostic_path, payload=payload, index=index))

    _write_jsonl(run_dir / "results.jsonl", rows)
    summary = _build_batch_summary(run_label=run_label, input_path=input_path, rows=rows)
    _write_json(run_dir / "summary.json", summary)
    (run_dir / "summary.md").write_text(_build_batch_summary_markdown(summary), encoding="utf-8")
    print(f"批量诊断结果已写入: {run_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    Args:
        argv: 可选命令行参数；为 ``None`` 时读取进程参数。

    Returns:
        进程退出码。

    Raises:
        无。
    """

    try:
        options = _parse_options(argv)
        _validate_cli_mode(options)
        if options.url_file:
            return _run_batch_diagnose(options)
        return _run_single_diagnose(options)
    except Exception as exc:
        safe_error = project_error_message(
            str(exc),
            max_chars=_DEFAULT_DIAGNOSTIC_ERROR_CHARS,
        )
        print(f"[诊断失败] {type(exc).__name__}: {safe_error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
