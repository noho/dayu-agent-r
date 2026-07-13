"""网页抓取编排辅助模块。

本模块聚合 requests 主路径中的 warmup、content-type probe、
HTML/Docling 路由与浏览器升级判定，避免这些编排细节继续膨胀在
``web_tools.py`` 中。
"""

from __future__ import annotations

import importlib
import re
import zlib
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from io import BytesIO
from types import ModuleType
from typing import Protocol, cast
from threading import Lock
from urllib.parse import urljoin, urlparse

import requests
from requests.structures import CaseInsensitiveDict
from dayu.contracts.cancellation import CancellationToken
from dayu.documents.docling_runtime import (
    DoclingRuntimeInitializationError,
    convert_pdf_bytes_with_docling,
)
from bs4 import BeautifulSoup

from dayu.documents.processors.html_pipeline import HtmlPipelineResult, HtmlPipelineStageError
from dayu.documents.processors.text_utils import infer_suffix_from_uri

from .web_challenge_detection import BotChallengeDecision, detect_bot_challenge
from .web_diagnostics import (
    WebContentDiagnostic,
    WebResponseHeaderProjection,
    content_diagnostic_from_bytes,
    project_response_headers,
    project_safe_url_or_empty,
)
from .web_http_encoding import (
    _decode_response_text,
    _extract_content_encoding_tokens,
    _find_unsupported_content_encodings,
)
from .web_egress_policy import (
    AuthorizedHttpTarget,
    WebEgressPolicy,
    WebEgressPolicyError,
)
from .web_http_session import AuthorizedResponseLease, _send_authorized_request
from .web_resource_budget import WebResourceBudget

_WARMUP_TIMEOUT_SECONDS = 6.0
_EMPTY_CONTENT_MIN_CHARS = 5
_MAX_META_REFRESH_HOPS = 3
_META_REFRESH_IMMEDIATE_MAX_SECONDS = 1.0
_FETCH_BODY_CHUNK_BYTES = 64 * 1024
_FETCH_LIMIT_CONTEXT_EXCERPT_BYTES = 4096
_MAX_HTTP_REDIRECT_HOPS = 30
_HTTP_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_PLAYWRIGHT_HTTP_ESCALATION_STATUSES = frozenset(
    {
        412,
        421,
        422,
        423,
        425,
        426,
        428,
        431,
        440,
        444,
        449,
        450,
        451,
        495,
        496,
        497,
        498,
        499,
        520,
        521,
        522,
        523,
        524,
        525,
        526,
        530,
    }
)
_WARMED_HOSTS_LOCK = Lock()


class _BoundedBinaryReader(Protocol):
    """支持有界 ``read(size)`` 的二进制 reader。"""

    def read(self, size: int = -1) -> bytes:
        """读取不超过 ``size`` 的解码字节。"""
        ...

    def close(self) -> None:
        """关闭 reader。"""
        ...


class _ZstandardDecompressor(Protocol):
    """zstandard 增量解压器协议。"""

    def stream_reader(self, source: BytesIO) -> _BoundedBinaryReader:
        """创建支持有界读取的增量解码 reader。"""
        ...


class _ZstandardModule(Protocol):
    """zstandard 模块协议。"""

    def ZstdDecompressor(self) -> _ZstandardDecompressor:
        """创建 zstd 解压器。"""
        ...


def _import_optional_module(module_name: str) -> ModuleType:
    """按名称导入可选模块。

    Args:
        module_name: 模块名。

    Returns:
        导入的模块对象。

    Raises:
        ImportError: 模块不存在或导入失败时抛出。
    """

    return importlib.import_module(module_name)


@dataclass(frozen=True)
class _FetchContentRuntimeContext:
    """抓取转换失败时保留的不可逆响应证据。"""

    http_status: int | None
    safe_final_url: str
    response_headers: WebResponseHeaderProjection
    content: WebContentDiagnostic
    challenge_decision: BotChallengeDecision
    challenge_signals: tuple[str, ...]
    has_client_rendering_markers: bool


@dataclass(frozen=True)
class _MetaRefreshDirective:
    """HTML meta refresh 指令。"""

    target_url: str
    raw_target: str
    delay_seconds: float | None
    raw_content: str


class _FetchContentConversionError(RuntimeError):
    """抓取转换阶段的包装异常。"""

    def __init__(
        self,
        message: str,
        *,
        response_context: _FetchContentRuntimeContext,
        original_error: RuntimeError,
        failure_reason: str = "",
    ) -> None:
        """初始化包装异常。

        Args:
            message: 对外暴露的错误信息。
            response_context: 原始响应上下文。
            original_error: 原始运行时异常。
            failure_reason: 供上层判定是否升级浏览器的失败类型。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(message)
        self.response_context = response_context
        self.original_error = original_error
        self.failure_reason = str(failure_reason or "").strip()


class _UnsupportedBoundedContentEncoding(RuntimeError):
    """当前 encoding 缺少可在输出物化前执行 cap 的 streaming API。"""

    def __init__(self, encoding: str) -> None:
        """初始化 unsupported encoding 错误。

        Args:
            encoding: 无法有界增量解码的 Content-Encoding token。

        Returns:
            无。

        Raises:
            无。
        """

        normalized_encoding = encoding.strip().lower()
        super().__init__(
            f"当前运行时不支持有界 {normalized_encoding} 增量解码。"
        )
        self.encoding = normalized_encoding


class _FetchBodyLimitExceeded(RuntimeError):
    """响应 body 超过 Web fetch owner 允许的读取上限。"""

    def __init__(
        self,
        message: str,
        *,
        final_url: str,
        limit_kind: str,
        limit_bytes: int,
        observed_bytes: int,
        response_context: _FetchContentRuntimeContext,
    ) -> None:
        """初始化 body 上限异常。

        Args:
            message: 错误消息。
            final_url: 当前响应 URL。
            limit_kind: 命中的限制类型。
            limit_bytes: 对应上限字节数。
            observed_bytes: 已观察到的字节数。
            response_context: 原始响应上下文。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(message)
        self.final_url = final_url
        self.limit_kind = limit_kind
        self.limit_bytes = limit_bytes
        self.observed_bytes = observed_bytes
        self.response_context = response_context


class _FetchUrlSafetyError(RuntimeError):
    """网络跳转目标被 Web URL safety owner 拒绝。"""

    def __init__(self, *, url: str, reason: str) -> None:
        """初始化 URL safety 异常。

        Args:
            url: 被拒绝的 URL。
            reason: 被拒绝的网络阶段。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(f"URL is blocked by fetch safety policy during {reason}: {url}")
        self.url = url
        self.reason = reason


def _raise_if_cancelled(cancellation_token: CancellationToken | None) -> None:
    """在进入下一网络阶段前执行协作式取消检查。

    Args:
        cancellation_token: 当前工具调用的取消令牌。

    Returns:
        无。

    Raises:
        CancelledError: 调用已被取消时抛出。
    """

    if cancellation_token is not None:
        if cancellation_token.is_cancelled():
            raise RuntimeError(cancellation_token.cancel_reason() or "工具调用已取消")


def _sanitize_response_headers(
    headers: CaseInsensitiveDict[str] | dict[str, str] | None,
) -> dict[str, str]:
    """筛选仅供抓取状态机内部判断的关键响应头。

    Args:
        headers: 原始响应头映射。

    Returns:
        内部有界响应头字典；进入日志/artifact 前仍必须经过 diagnostic projection。

    Raises:
        无。
    """

    if not headers:
        return {}
    selected_keys = (
        "content-type",
        "content-length",
        "server",
        "cf-ray",
        "x-datadome",
        "x-datadome-cid",
        "x-dd-b",
        "retry-after",
        "location",
        "set-cookie",
    )
    normalized: dict[str, str] = {}
    for key in selected_keys:
        value = headers.get(key) or headers.get(key.title())
        if value is None:
            continue
        text = str(value)
        if key == "set-cookie":
            cookie_names = [
                chunk.split("=", 1)[0].strip()
                for chunk in text.split(";")
                if "=" in chunk
            ]
            text = ",".join(sorted(set(filter(None, cookie_names))))
        normalized[key] = text[:200]
    return normalized


def _is_redirect_response(response: requests.Response) -> bool:
    """判断响应是否为需要 Web fetch owner 手动处理的 HTTP redirect。

    Args:
        response: HTTP 响应。

    Returns:
        需要继续跳转时返回 ``True``。

    Raises:
        无。
    """

    return int(response.status_code) in _HTTP_REDIRECT_STATUSES


def _resolve_redirect_target(
    *,
    response: requests.Response,
    current_url: str,
    normalize_url_for_http: Callable[[str], str],
) -> str:
    """解析 HTTP redirect 的下一跳 URL。

    Args:
        response: 当前 redirect 响应。
        current_url: 当前请求 URL。
        normalize_url_for_http: URL 规范化函数。

    Returns:
        已规范化的下一跳 URL。

    Raises:
        RuntimeError: redirect 响应缺少或包含非法 ``Location`` 时抛出。
    """

    location = str(response.headers.get("Location", "") or response.headers.get("location", "") or "").strip()
    if not location:
        raise RuntimeError("HTTP redirect 响应缺少 Location 头。")
    try:
        return normalize_url_for_http(urljoin(str(getattr(response, "url", "") or current_url), location))
    except ValueError as exc:
        raise RuntimeError(f"HTTP redirect Location 无法解析: {location}") from exc


def _authorize_http_target(
    egress_policy: WebEgressPolicy,
    *,
    url: str,
    reason: str,
) -> AuthorizedHttpTarget:
    """把 policy 拒绝投影为 fetch 编排层的稳定异常。

    Args:
        egress_policy: 当前 Web 调用唯一的出站策略。
        url: 待授权 URL。
        reason: 当前网络阶段。

    Returns:
        当前 hop 的不可变授权目标。

    Raises:
        _FetchUrlSafetyError: policy 拒绝 URL 时抛出。
    """

    try:
        return egress_policy.authorize_http_target(url, stage=reason)
    except WebEgressPolicyError as exc:
        raise _FetchUrlSafetyError(url=exc.url, reason=reason) from exc


def _validate_response_target(
    egress_policy: WebEgressPolicy,
    *,
    url: str,
    target: AuthorizedHttpTarget,
    reason: str,
) -> str:
    """验证 response URL 未离开已授权 origin。

    Args:
        egress_policy: 当前 Web 调用唯一的出站策略。
        url: response 报告的 URL。
        target: 发送该请求的已授权目标。
        reason: 当前响应阶段。

    Returns:
        规范化后的 response URL。

    Raises:
        _FetchUrlSafetyError: response origin 被偷换时抛出。
    """

    try:
        return egress_policy.validate_response_url(url, target=target, stage=reason)
    except WebEgressPolicyError as exc:
        raise _FetchUrlSafetyError(url=exc.url, reason=reason) from exc


def _append_limited_body_chunk(
    *,
    chunks: list[bytes],
    chunk: bytes,
    observed_bytes: int,
    limit_bytes: int,
    limit_kind: str,
    response: requests.Response,
) -> int:
    """累计 body chunk 并在超过上限时失败。

    Args:
        chunks: 已读取 chunk 列表。
        chunk: 当前 chunk。
        observed_bytes: 此前已观察字节数。
        limit_bytes: 字节上限。
        limit_kind: 限制类型。
        response: 当前 HTTP 响应。

    Returns:
        新的已观察字节数。

    Raises:
        _FetchBodyLimitExceeded: body 超过上限时抛出。
    """

    if not chunk:
        return observed_bytes
    next_size = observed_bytes + len(chunk)
    if next_size > limit_bytes:
        raise _FetchBodyLimitExceeded(
            f"HTTP response {limit_kind} body exceeded fetch limit.",
            final_url=str(getattr(response, "url", "") or ""),
            limit_kind=limit_kind,
            limit_bytes=limit_bytes,
            observed_bytes=next_size,
            response_context=_build_fetch_body_limit_runtime_context(response),
        )
    chunks.append(chunk)
    return next_size


def _iter_raw_response_chunks(response: requests.Response) -> Iterable[bytes]:
    """按 wire bytes 读取 ``requests`` 响应。

    Args:
        response: 使用 ``stream=True`` 创建的响应。

    Returns:
        原始 wire chunk 迭代器。

    Raises:
        requests.RequestException: 底层读取失败时由 requests/urllib3 抛出。
    """

    return response.raw.stream(_FETCH_BODY_CHUNK_BYTES, decode_content=False)


def _zlib_wrapped_deflate(data: bytes) -> bool:
    """判断 deflate body 是否带 RFC 1950 zlib wrapper。

    Args:
        data: deflate 压缩字节。

    Returns:
        header 满足 zlib wrapper 约束时返回 ``True``。

    Raises:
        无。
    """

    if len(data) < 2:
        return False
    compression_method_and_flags = data[0]
    additional_flags = data[1]
    return (
        compression_method_and_flags & 0x0F == 8
        and (compression_method_and_flags << 8 | additional_flags) % 31 == 0
    )


def _decode_zlib_layer(
    response: requests.Response,
    encoded: bytes,
    *,
    window_bits: int,
    limit_bytes: int,
) -> bytes:
    """用 ``decompressobj`` 增量解码单个 zlib/gzip 层。

    每次 decoder 调用的最大输出固定为当前剩余预算加一字节，使超限在
    完整输出物化前可判定。

    Args:
        response: 当前 HTTP 响应，用于构造 typed limit context。
        encoded: 当前编码层输入。
        window_bits: zlib window bits；可表达 gzip、zlib 或 raw deflate。
        limit_bytes: 当前解码层输出上限。

    Returns:
        解码后的有界字节。

    Raises:
        _FetchBodyLimitExceeded: 当前层输出超过上限时抛出。
        RuntimeError: 压缩流不完整或 decoder 无法前进时抛出。
        zlib.error: 压缩流非法时抛出。
    """

    decoder = zlib.decompressobj(window_bits)
    decoded_chunks: list[bytes] = []
    observed_bytes = 0
    for offset in range(0, len(encoded), _FETCH_BODY_CHUNK_BYTES):
        pending = encoded[offset : offset + _FETCH_BODY_CHUNK_BYTES]
        while pending:
            remaining_bytes = limit_bytes - observed_bytes
            decoded_chunk = decoder.decompress(pending, remaining_bytes + 1)
            observed_bytes = _append_limited_body_chunk(
                chunks=decoded_chunks,
                chunk=decoded_chunk,
                observed_bytes=observed_bytes,
                limit_bytes=limit_bytes,
                limit_kind="decompressed",
                response=response,
            )
            next_pending = decoder.unconsumed_tail
            if not next_pending:
                break
            if next_pending == pending and not decoded_chunk:
                raise RuntimeError("HTTP content decoder made no progress")
            pending = next_pending
    if not decoder.eof:
        raise RuntimeError("HTTP compressed response ended before decoder reached EOF")
    if decoder.unused_data:
        raise RuntimeError("HTTP compressed response contains trailing encoded data")
    return b"".join(decoded_chunks)


def _decode_zstd_layer(
    response: requests.Response,
    encoded: bytes,
    *,
    limit_bytes: int,
) -> bytes:
    """用 zstandard ``stream_reader`` 有界解码单层 zstd。

    Args:
        response: 当前 HTTP 响应，用于构造 typed limit context。
        encoded: 当前编码层输入。
        limit_bytes: 当前解码层输出上限。

    Returns:
        解码后的有界字节。

    Raises:
        _FetchBodyLimitExceeded: 当前层输出超过上限时抛出。
        RuntimeError: 缺少带有界 streaming API 的 zstandard 依赖时抛出。
    """

    try:
        zstandard = cast(_ZstandardModule, _import_optional_module("zstandard"))
    except ImportError as exc:
        raise _UnsupportedBoundedContentEncoding("zstd") from exc

    reader = zstandard.ZstdDecompressor().stream_reader(BytesIO(encoded))
    decoded_chunks: list[bytes] = []
    observed_bytes = 0
    try:
        while True:
            remaining_bytes = limit_bytes - observed_bytes
            decoded_chunk = reader.read(
                min(_FETCH_BODY_CHUNK_BYTES, remaining_bytes + 1)
            )
            if not decoded_chunk:
                break
            observed_bytes = _append_limited_body_chunk(
                chunks=decoded_chunks,
                chunk=decoded_chunk,
                observed_bytes=observed_bytes,
                limit_bytes=limit_bytes,
                limit_kind="decompressed",
                response=response,
            )
    finally:
        reader.close()
    return b"".join(decoded_chunks)


def _bounded_identity_layer(
    response: requests.Response,
    body: bytes,
    *,
    limit_bytes: int,
) -> bytes:
    """校验未编码 body 也受 decoded cap 约束。

    Args:
        response: 当前 HTTP 响应。
        body: 未编码 body。
        limit_bytes: decoded body 上限。

    Returns:
        未超限的原 body。

    Raises:
        _FetchBodyLimitExceeded: body 超过 decoded cap 时抛出。
    """

    if len(body) <= limit_bytes:
        return body
    raise _FetchBodyLimitExceeded(
        "HTTP response decompressed body exceeded fetch limit.",
        final_url=str(response.url or ""),
        limit_kind="decompressed",
        limit_bytes=limit_bytes,
        observed_bytes=limit_bytes + 1,
        response_context=_build_fetch_body_limit_runtime_context(
            response,
            body_excerpt=body[:_FETCH_LIMIT_CONTEXT_EXCERPT_BYTES],
        ),
    )


def _decompress_limited_response_body(
    response: requests.Response,
    wire_body: bytes,
    *,
    resource_budget: WebResourceBudget,
) -> bytes:
    """按 ``Content-Encoding`` 解压并限制 decompressed body 大小。

    Args:
        response: 当前 HTTP 响应。
        wire_body: 已按 wire 上限读取的原始字节。

    Returns:
        解压后的 body 字节。

    Raises:
        _FetchBodyLimitExceeded: 解压后字节数超过上限时抛出。
        RuntimeError: 内容编码声明存在但当前运行时无法有界解码时抛出。
    """

    decoded = wire_body
    for encoding in reversed(_extract_content_encoding_tokens(getattr(response, "headers", {}))):
        if encoding == "identity":
            continue
        if encoding == "gzip":
            decoded = _decode_zlib_layer(
                response,
                decoded,
                window_bits=zlib.MAX_WBITS | 16,
                limit_bytes=resource_budget.decoded_body_bytes,
            )
        elif encoding == "deflate":
            decoded = _decode_zlib_layer(
                response,
                decoded,
                window_bits=(
                    zlib.MAX_WBITS
                    if _zlib_wrapped_deflate(decoded)
                    else -zlib.MAX_WBITS
                ),
                limit_bytes=resource_budget.decoded_body_bytes,
            )
        elif encoding == "br":
            raise _UnsupportedBoundedContentEncoding("brotli")
        elif encoding == "zstd":
            decoded = _decode_zstd_layer(
                response,
                decoded,
                limit_bytes=resource_budget.decoded_body_bytes,
            )
        else:
            raise _UnsupportedBoundedContentEncoding(encoding)
    return _bounded_identity_layer(
        response,
        decoded,
        limit_bytes=resource_budget.decoded_body_bytes,
    )


def _read_limited_response_body(
    response: requests.Response,
    *,
    resource_budget: WebResourceBudget,
) -> bytes:
    """读取响应 body，并同时执行 wire/decompressed 上限。

    Args:
        response: 使用 ``stream=True`` 创建的 HTTP 响应。

    Returns:
        已解压、可供后续 HTML/Docling 转换消费的 body 字节。

    Raises:
        _FetchBodyLimitExceeded: wire 或 decompressed body 超过上限时抛出。
        RuntimeError: 内容编码声明存在但当前运行时无法解码时抛出。
    """

    content_length = str(response.headers.get("Content-Length", "") or response.headers.get("content-length", ""))
    if content_length.strip():
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = 0
        if declared_length > resource_budget.wire_body_bytes:
            raise _FetchBodyLimitExceeded(
                "HTTP response declared body exceeded fetch wire limit.",
                final_url=str(getattr(response, "url", "") or ""),
                limit_kind="wire",
                limit_bytes=resource_budget.wire_body_bytes,
                observed_bytes=declared_length,
                response_context=_build_fetch_body_limit_runtime_context(response),
            )

    chunks: list[bytes] = []
    observed_bytes = 0
    for chunk in _iter_raw_response_chunks(response):
        observed_bytes = _append_limited_body_chunk(
            chunks=chunks,
            chunk=chunk,
            observed_bytes=observed_bytes,
            limit_bytes=resource_budget.wire_body_bytes,
            limit_kind="wire",
            response=response,
        )
    return _decompress_limited_response_body(
        response,
        b"".join(chunks),
        resource_budget=resource_budget,
    )


def _materialize_response_body(
    response: requests.Response,
    *,
    resource_budget: WebResourceBudget,
) -> None:
    """把有界读取后的响应 body 写回 ``requests.Response``。

    Args:
        response: 当前 HTTP 响应。

    Returns:
        无。

    Raises:
        _FetchBodyLimitExceeded: body 超过上限时抛出。
        RuntimeError: body 解码失败时抛出。
    """

    decoded_body = _read_limited_response_body(
        response,
        resource_budget=resource_budget,
    )
    setattr(response, "_content", decoded_body)
    response.raw.decode_content = False


def _request_with_safe_redirects(
    session: requests.Session,
    *,
    method: str,
    url: str,
    timeout: float,
    headers: dict[str, str],
    normalize_url_for_http: Callable[[str], str],
    egress_policy: WebEgressPolicy,
    stream: bool,
    cancellation_token: CancellationToken | None,
) -> tuple[AuthorizedResponseLease, int, tuple[str, ...]]:
    """执行带逐跳安全校验的 HTTP 请求。

    Args:
        session: requests Session。
        method: HTTP 方法。
        url: 初始 URL。
        timeout: 请求超时。
        headers: 请求头。
        normalize_url_for_http: URL 规范化函数。
        egress_policy: 当前 Web 调用唯一的出站策略。
        stream: 是否以 stream 模式读取响应。
        cancellation_token: 取消令牌。

    Returns:
        ``(最终 response lease, HTTP redirect 跳数, 已访问 URL 记录)``。

    Raises:
        requests.TooManyRedirects: redirect 超过上限时抛出。
        RuntimeError: redirect 目标被安全策略拒绝时抛出。
    """

    current_target = _authorize_http_target(egress_policy, url=url, reason="http_request")
    current_url = current_target.normalized_url
    current_headers = dict(headers)
    redirect_hops = 0
    visited_urls = [current_url]
    while True:
        _raise_if_cancelled(cancellation_token)
        lease = _send_authorized_request(
            session,
            target=current_target,
            method=method,
            timeout=timeout,
            headers=current_headers,
            stream=stream,
        )
        transferred = False
        try:
            response = lease.response
            _raise_if_cancelled(cancellation_token)
            response_url = _validate_response_target(
                egress_policy,
                url=str(response.url or current_url),
                target=current_target,
                reason="http_response",
            )
            visited_urls.append(response_url)
            if not _is_redirect_response(response):
                transferred = True
                return lease, redirect_hops, tuple(dict.fromkeys(visited_urls))
            if redirect_hops >= _MAX_HTTP_REDIRECT_HOPS:
                raise requests.TooManyRedirects(
                    "HTTP redirect chain exceeded fetch limit",
                    response=response,
                )
            next_url = _resolve_redirect_target(
                response=response,
                current_url=current_url,
                normalize_url_for_http=normalize_url_for_http,
            )
            next_target = _authorize_http_target(
                egress_policy,
                url=next_url,
                reason="http_redirect",
            )
            visited_urls.append(next_target.normalized_url)
            current_headers = dict(headers)
            current_headers["Referer"] = response_url
            current_target = next_target
            current_url = next_target.normalized_url
            redirect_hops += 1
        finally:
            if not transferred:
                lease.close()


def _build_fetch_content_runtime_context(response: requests.Response) -> _FetchContentRuntimeContext:
    """从响应对象构造不可逆抓取转换失败上下文。

    Args:
        response: 原始 HTTP 响应。

    Returns:
        供上层异常处理使用的响应上下文。

    Raises:
        无。
    """

    response_bytes = bytes(response.content)
    try:
        response_text = _decode_response_text(response)
    except Exception:
        response_text = ""
    challenge = detect_bot_challenge(response=response, content_text=response_text)
    return _FetchContentRuntimeContext(
        http_status=response.status_code,
        safe_final_url=project_safe_url_or_empty(str(response.url or "")),
        response_headers=project_response_headers(response.headers),
        content=content_diagnostic_from_bytes(response_bytes),
        challenge_decision=challenge.decision,
        challenge_signals=challenge.challenge_signals,
        has_client_rendering_markers=_html_text_has_client_rendering_markers(response_text),
    )


def _build_fetch_body_limit_runtime_context(
    response: requests.Response,
    *,
    body_excerpt: bytes = b"",
) -> _FetchContentRuntimeContext:
    """为 body 上限异常构造不会读取响应剩余 body 的上下文。

    Args:
        response: 当前 HTTP 响应。
        body_excerpt: 已读取且已裁剪的 body 前缀。

    Returns:
        body-limit 专用响应上下文。

    Raises:
        无。
    """

    bounded_excerpt = body_excerpt[:_FETCH_LIMIT_CONTEXT_EXCERPT_BYTES]
    return _FetchContentRuntimeContext(
        http_status=response.status_code,
        safe_final_url=project_safe_url_or_empty(str(response.url or "")),
        response_headers=project_response_headers(response.headers),
        content=content_diagnostic_from_bytes(bounded_excerpt),
        challenge_decision=BotChallengeDecision.NONE,
        challenge_signals=(),
        has_client_rendering_markers=False,
    )


def _extract_html_response_text(response: requests.Response) -> str:
    """提取已确认走 HTML 管线的响应文本。

    Args:
        response: 原始 HTTP 响应。

    Returns:
        可供 HTML 抽取器消费的文本。

    Raises:
        _FetchContentConversionError: 当响应使用了当前运行时不支持的内容编码时抛出。
    """

    unsupported_encodings = _find_unsupported_content_encodings(getattr(response, "headers", {}))
    if unsupported_encodings:
        raise _FetchContentConversionError(
            f"HTML 响应使用当前运行时不支持的内容编码: {', '.join(unsupported_encodings)}",
            response_context=_build_fetch_content_runtime_context(response),
            original_error=RuntimeError("unsupported_content_encoding"),
            failure_reason="unsupported_content_encoding",
        )
    return _decode_response_text(response)


def _extract_meta_refresh_directive(
    html_text: str,
    *,
    base_url: str,
    normalize_url_for_http: Callable[[str], str],
) -> _MetaRefreshDirective | None:
    """从 HTML 中解析 meta refresh 指令。

    Args:
        html_text: HTML 文本。
        base_url: 当前页面 URL，用于解析相对跳转目标。
        normalize_url_for_http: URL 规范化函数。

    Returns:
        若存在 meta refresh 则返回解析结果，否则返回 `None`。

    Raises:
        无。
    """

    if not html_text.strip():
        return None

    soup = BeautifulSoup(html_text, "lxml")
    for meta_tag in soup.find_all("meta"):
        http_equiv = str(meta_tag.get("http-equiv", "") or "").strip().lower()
        if http_equiv != "refresh":
            continue

        raw_content = str(meta_tag.get("content", "") or "").strip()
        if not raw_content:
            return _MetaRefreshDirective(target_url="", raw_target="", delay_seconds=None, raw_content="")

        match = re.match(
            r"^\s*(?P<delay>\d+(?:\.\d+)?)\s*(?:;\s*url\s*=\s*(?P<target>.+?)\s*)?$",
            raw_content,
            flags=re.IGNORECASE,
        )
        if match is None:
            return _MetaRefreshDirective(target_url="", raw_target="", delay_seconds=None, raw_content=raw_content)

        delay_text = str(match.group("delay") or "").strip()
        raw_target = str(match.group("target") or "").strip().strip("\"'")
        delay_seconds: float | None = None
        if delay_text:
            try:
                delay_seconds = float(delay_text)
            except ValueError:
                delay_seconds = None

        target_url = ""
        if raw_target:
            try:
                target_url = normalize_url_for_http(urljoin(base_url, raw_target))
            except ValueError:
                target_url = ""
        return _MetaRefreshDirective(
            target_url=target_url,
            raw_target=raw_target,
            delay_seconds=delay_seconds,
            raw_content=raw_content,
        )
    return None


def _resolve_meta_refresh_follow_target(
    *,
    response: requests.Response,
    html_text: str,
    visited_urls: Collection[str],
    meta_refresh_hops: int,
    normalize_url_for_http: Callable[[str], str],
) -> str | None:
    """判断当前 HTML 是否需要按 meta refresh 继续抓取。

    Args:
        response: 当前响应对象。
        html_text: 当前 HTML 文本。
        visited_urls: 已访问 URL 集合，用于防环。
        meta_refresh_hops: 已发生的 meta refresh 跳数。
        normalize_url_for_http: URL 规范化函数。

    Returns:
        若需要继续抓取则返回下一跳 URL；否则返回 `None`。

    Raises:
        _FetchContentConversionError: 当 meta refresh 需要浏览器执行或出现循环时抛出。
    """

    directive = _extract_meta_refresh_directive(
        html_text,
        base_url=str(getattr(response, "url", "") or ""),
        normalize_url_for_http=normalize_url_for_http,
    )
    if directive is None:
        return None

    if directive.delay_seconds is None or directive.delay_seconds > _META_REFRESH_IMMEDIATE_MAX_SECONDS:
        raise _FetchContentConversionError(
            "HTML 页面包含需要浏览器执行的 meta refresh 跳转。",
            response_context=_build_fetch_content_runtime_context(response),
            original_error=RuntimeError("meta_refresh_requires_browser"),
            failure_reason="meta_refresh_requires_browser",
        )

    if not directive.target_url:
        raise _FetchContentConversionError(
            "HTML 页面包含无法解析目标的 meta refresh 跳转。",
            response_context=_build_fetch_content_runtime_context(response),
            original_error=RuntimeError("meta_refresh_requires_browser"),
            failure_reason="meta_refresh_requires_browser",
        )

    if meta_refresh_hops >= _MAX_META_REFRESH_HOPS or directive.target_url in visited_urls:
        raise _FetchContentConversionError(
            "HTML 页面 meta refresh 跳转出现循环或超过上限。",
            response_context=_build_fetch_content_runtime_context(response),
            original_error=RuntimeError("meta_refresh_requires_browser"),
            failure_reason="meta_refresh_requires_browser",
        )
    return directive.target_url


def _html_text_has_client_rendering_markers(raw_text: str) -> bool:
    """判断 HTML 文本是否更像需要真实浏览器渲染的前端壳页。

    Args:
        raw_text: 原始 HTML 或其文本摘录。

    Returns:
        命中典型客户端渲染壳页特征时返回 `True`。

    Raises:
        无。
    """

    normalized_text = str(raw_text or "").lower()
    if not normalized_text:
        return False
    return any(
        marker in normalized_text
        for marker in (
            "<script",
            'id="app"',
            "id='app'",
            'id="root"',
            "id='root'",
            "__next",
            "chunk-vendors",
            "webpack",
            "hydrate",
            "render(",
            "#/",
        )
    )


def _should_escalate_http_status_to_browser(http_status: int | None) -> bool:
    """判断 HTTP 错误状态是否值得优先升级到浏览器回退。"""

    return http_status in _PLAYWRIGHT_HTTP_ESCALATION_STATUSES


def _should_escalate_conversion_failure_to_browser(
    *,
    error_message: str,
    response_context: _FetchContentRuntimeContext | None,
) -> bool:
    """判断未类型化的 HTML 转换失败是否应升级到浏览器。"""

    if response_context is None:
        return False

    http_status = response_context.http_status
    if http_status is not None and not 200 <= http_status < 300:
        return False

    normalized_message = str(error_message or "").lower()
    if not any(
        token in normalized_message
        for token in (
            "主体抽取失败",
            "正文为空",
            "未产出结果",
            "empty",
            "no content",
        )
    ):
        return False

    return response_context.has_client_rendering_markers


def _should_escalate_stage_result_to_browser(stage_result: dict[str, str | bool | int | float | None] | None) -> bool:
    """判断阶段性 requests 结果是否应立即升级到浏览器回退。"""

    if not isinstance(stage_result, dict):
        return False
    if not bool(stage_result.get("attempted", True)):
        return False
    return bool(stage_result.get("timeout_like"))


def _should_escalate_pipeline_failure_to_browser(
    *,
    pipeline_error: HtmlPipelineStageError | None,
    response_context: _FetchContentRuntimeContext | None,
) -> bool:
    """判断 HTML 抽取失败是否值得升级到浏览器回退。"""

    if pipeline_error is None or response_context is None:
        return False
    if pipeline_error.stage != "extract":
        return False

    http_status = response_context.http_status
    if http_status is not None and not 200 <= http_status < 300:
        return False

    content_stats = pipeline_error.content_stats if isinstance(pipeline_error.content_stats, dict) else {}
    try:
        text_length = int(content_stats.get("text_length", 0) or 0)
    except (TypeError, ValueError):
        text_length = 0
    try:
        paragraph_count = int(content_stats.get("paragraph_count", 0) or 0)
    except (TypeError, ValueError):
        paragraph_count = 0

    quality_flags = {str(flag).strip().lower() for flag in pipeline_error.quality_flags}
    extractor_found_no_body = text_length <= _EMPTY_CONTENT_MIN_CHARS or paragraph_count <= 0
    quality_indicates_empty_shell = bool({"too_short", "too_few_blocks"} & quality_flags)
    return (
        extractor_found_no_body or quality_indicates_empty_shell
    ) and response_context.has_client_rendering_markers


def _get_session_warmed_hosts(session: requests.Session) -> set[str]:
    """返回与当前 Session 同源的 warmup host 集合。"""

    warmed_hosts = getattr(session, "__dayu_warmed_hosts__", None)
    if isinstance(warmed_hosts, set):
        return warmed_hosts
    warmed_hosts = set()
    setattr(session, "__dayu_warmed_hosts__", warmed_hosts)
    return warmed_hosts


def _consume_warmup_response_body(
    response: requests.Response,
    *,
    max_bytes: int,
) -> int:
    """最多消费 warmup 预算允许的 wire body。

    Args:
        response: 使用 ``stream=True`` 创建的 warmup 响应。
        max_bytes: 本次 warmup 最多消费的 wire bytes。

    Returns:
        实际消费的 wire bytes。

    Raises:
        requests.RequestException: 底层 response stream 读取失败时透出。
    """

    consumed_bytes = 0
    while consumed_bytes < max_bytes:
        remaining_bytes = max_bytes - consumed_bytes
        chunk = response.raw.read(min(_FETCH_BODY_CHUNK_BYTES, remaining_bytes))
        if not chunk:
            break
        consumed_bytes += len(chunk)
    return consumed_bytes


def _warmup_domain(
    session: requests.Session,
    *,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str],
    resolve_timeout_budget: Callable[..., float],
    build_domain_home_url: Callable[[str], str],
    normalize_url_for_http: Callable[[str], str],
    is_timeout_like_exception: Callable[[BaseException], bool],
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    cancellation_token: CancellationToken | None = None,
) -> dict[str, str | bool | int | float | None]:
    """对目标域做一次预热请求以建立 Cookie。"""

    host = (urlparse(url).hostname or "").lower().strip()
    if not host:
        return {"attempted": False, "success": False, "reason": "invalid_host"}

    with _WARMED_HOSTS_LOCK:
        warmed_hosts = _get_session_warmed_hosts(session)
        if host in warmed_hosts:
            return {"attempted": False, "success": True, "reason": "already_warmed"}

    warmup_url = build_domain_home_url(url)
    _raise_if_cancelled(cancellation_token)
    warmup_timeout = min(
        resolve_timeout_budget(
            timeout_seconds,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
        ),
        _WARMUP_TIMEOUT_SECONDS,
    )
    try:
        _raise_if_cancelled(cancellation_token)
        lease, redirect_hops, _redirect_visited_urls = _request_with_safe_redirects(
            session,
            method="GET",
            url=warmup_url,
            timeout=warmup_timeout,
            headers=headers,
            normalize_url_for_http=normalize_url_for_http,
            egress_policy=egress_policy,
            stream=True,
            cancellation_token=cancellation_token,
        )
        with lease:
            response = lease.response
            _raise_if_cancelled(cancellation_token)
            consumed_body_bytes = _consume_warmup_response_body(
                response,
                max_bytes=resource_budget.warmup_body_bytes,
            )
            result: dict[str, str | bool | int | float | None] = {
                "attempted": True,
                "success": True,
                "http_status": response.status_code,
                "final_url": response.url,
                "redirect_hops": redirect_hops,
                "consumed_body_bytes": consumed_body_bytes,
            }
        with _WARMED_HOSTS_LOCK:
            _get_session_warmed_hosts(session).add(host)
        return result
    except Exception as exc:
        _raise_if_cancelled(cancellation_token)
        return {
            "attempted": True,
            "success": False,
            "reason": type(exc).__name__,
            "detail": str(exc),
            "timeout_like": is_timeout_like_exception(exc),
        }


def _probe_content_type(
    session: requests.Session,
    *,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str],
    resolve_timeout_budget: Callable[..., float],
    normalize_url_for_http: Callable[[str], str],
    is_timeout_like_exception: Callable[[BaseException], bool],
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    cancellation_token: CancellationToken | None = None,
) -> dict[str, str | bool | int | None]:
    """探测目标资源类型（HEAD 优先，失败降级到零 body GET）。

    ``resource_budget`` 由与 main/warmup 相同的 owner 显式传入；probe 只读
    response headers 并立即关闭 lease，因此不消费其 body budget。
    """

    timeout = min(
        resolve_timeout_budget(
            timeout_seconds,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
        ),
        _WARMUP_TIMEOUT_SECONDS,
    )
    try:
        _raise_if_cancelled(cancellation_token)
        lease, redirect_hops, _redirect_visited_urls = _request_with_safe_redirects(
            session,
            method="HEAD",
            url=url,
            timeout=timeout,
            headers=headers,
            normalize_url_for_http=normalize_url_for_http,
            egress_policy=egress_policy,
            stream=False,
            cancellation_token=cancellation_token,
        )
        with lease:
            response = lease.response
            _raise_if_cancelled(cancellation_token)
            content_type = str(response.headers.get("Content-Type", "")).lower()
            return {
                "method": "HEAD",
                "content_type": content_type,
                "http_status": response.status_code,
                "final_url": response.url,
                "redirect_hops": redirect_hops,
                "ok": True,
            }
    except Exception as head_exc:
        try:
            _raise_if_cancelled(cancellation_token)
            lease, redirect_hops, _redirect_visited_urls = _request_with_safe_redirects(
                session,
                method="GET",
                url=url,
                timeout=timeout,
                headers=headers,
                normalize_url_for_http=normalize_url_for_http,
                egress_policy=egress_policy,
                stream=True,
                cancellation_token=cancellation_token,
            )
            with lease:
                response = lease.response
                _raise_if_cancelled(cancellation_token)
                content_type = str(response.headers.get("Content-Type", "")).lower()
                return {
                    "method": "GET",
                    "content_type": content_type,
                    "http_status": response.status_code,
                    "final_url": response.url,
                    "redirect_hops": redirect_hops,
                    "ok": True,
                    "head_error": type(head_exc).__name__,
                }
        except Exception as get_exc:
            _raise_if_cancelled(cancellation_token)
            return {
                "method": "UNKNOWN",
                "content_type": "",
                "ok": False,
                "head_error": type(head_exc).__name__,
                "get_error": type(get_exc).__name__,
                "head_timeout_like": is_timeout_like_exception(head_exc),
                "get_timeout_like": is_timeout_like_exception(get_exc),
                "timeout_like": is_timeout_like_exception(head_exc) or is_timeout_like_exception(get_exc),
            }


def _should_route_response_to_html_pipeline(
    *,
    url: str,
    content_type: str,
    response_text: str,
    response_content: bytes,
) -> bool:
    """判断响应是否应进入 HTML 四段式流水线。"""

    normalized_content_type = str(content_type or "").lower()
    if "html" in normalized_content_type:
        return True

    uri_suffix = infer_suffix_from_uri(urlparse(url).path)
    if uri_suffix in {".html", ".htm", ".xhtml"}:
        return True

    candidate_text = str(response_text or "").lstrip()
    if not candidate_text and response_content:
        candidate_text = response_content.decode("utf-8", errors="replace").lstrip()

    lowered_prefix = candidate_text[:256].lower()
    return lowered_prefix.startswith("<!doctype html") or "<html" in lowered_prefix


def _infer_docling_stream_name(*, url: str, content_type: str) -> str:
    """为 Docling 推断更稳定的输入流名称。"""

    normalized_content_type = str(content_type or "").lower()
    uri_suffix = infer_suffix_from_uri(urlparse(url).path)

    if "pdf" in normalized_content_type or uri_suffix == ".pdf":
        return "page.pdf"
    if "xml" in normalized_content_type or uri_suffix in {".xml", ".xbrl"}:
        return "page.xml"
    if "json" in normalized_content_type or uri_suffix == ".json":
        return "page.json"
    if uri_suffix:
        return f"page{uri_suffix}"
    if normalized_content_type.startswith("text/"):
        return "page.txt"
    return "page.bin"


def _docling_convert_to_markdown(raw_bytes: bytes, stream_name: str) -> tuple[str, str, str]:
    """使用 Docling 将非 HTML 原始字节转换为 Markdown。

    Args:
        raw_bytes: 页面原始内容字节。
        stream_name: 流名称，决定 Docling 解析模式。

    Returns:
        ``(title, markdown, extraction_source)`` 三元组。

    Raises:
        DoclingRuntimeInitializationError: Docling 装配失败时抛出。
        RuntimeError: Docling 转换失败时抛出。
    """

    try:
        result = convert_pdf_bytes_with_docling(
            raw_bytes,
            stream_name=stream_name,
            do_ocr=True,
            do_table_structure=True,
            table_mode="accurate",
            do_cell_matching=True,
        )
    except DoclingRuntimeInitializationError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Docling 转换失败: {exc}") from exc

    markdown = result.document.export_to_markdown().strip()
    title = ""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            break
    return title, markdown, "docling"


def _fetch_and_convert_content(
    url: str,
    *,
    timeout_seconds: float,
    resolve_timeout_budget: Callable[..., float],
    normalize_url_for_http: Callable[[str], str],
    build_referer: Callable[[str], str],
    convert_html: Callable[..., HtmlPipelineResult],
    convert_non_html: Callable[[bytes, str], tuple[str, str, str]],
    session: requests.Session | None = None,
    get_web_session: Callable[[], requests.Session] | None = None,
    headers: dict[str, str] | None = None,
    build_fetch_headers: Callable[[str], dict[str, str]] | None = None,
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
    content_type_probe: dict[str, str | bool | int | None] | None = None,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    cancellation_token: CancellationToken | None = None,
) -> dict[str, str | int | bool | list[str] | dict[str, int] | dict[str, str]]:
    """先下载页面内容，再按内容类型转换为低噪音 Markdown。

    Args:
        url: 已通过安全校验的网页链接。
        timeout_seconds: HTTP 请求超时秒数。
        resolve_timeout_budget: timeout 预算解析函数。
        normalize_url_for_http: URL 规范化函数。
        build_referer: Referer 构造函数。
        convert_html: HTML 四段式转换器。
        convert_non_html: 非 HTML 内容转换器。
        session: 可选复用 Session。
        get_web_session: 默认 Session 提供器。
        headers: 可选请求头。
        build_fetch_headers: 默认请求头构造器。
        egress_policy: 当前 Web 调用唯一的出站策略。
        content_type_probe: 可选内容类型探测结果。
        timeout_budget: Runner 注入的单次 tool call 总预算。
        deadline_monotonic: 当前工具调用的单调时钟 deadline。

    Returns:
        抓取和转换结果，包含 ``title/content/http_status/final_url`` 等字段。

    Raises:
        RuntimeError: HTTP 请求失败或内容转换失败时抛出。
        ValueError: 当缺少默认 Session 或请求头构造器时抛出。
    """

    resolved_session = session
    if resolved_session is None:
        if get_web_session is None:
            raise ValueError("缺少默认 requests Session 提供器")
        resolved_session = get_web_session()

    resolved_headers = headers
    if resolved_headers is None:
        if build_fetch_headers is None:
            raise ValueError("缺少默认请求头构造器")
        resolved_headers = build_fetch_headers(url)

    current_url = url
    current_headers = dict(resolved_headers)
    visited_urls = {url}
    meta_refresh_hops = 0
    http_redirect_hops = 0

    while True:
        _raise_if_cancelled(cancellation_token)
        timeout = resolve_timeout_budget(
            timeout_seconds,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
        )
        _raise_if_cancelled(cancellation_token)
        lease, current_redirect_hops, redirect_visited_urls = _request_with_safe_redirects(
            resolved_session,
            method="GET",
            url=current_url,
            timeout=timeout,
            headers=current_headers,
            normalize_url_for_http=normalize_url_for_http,
            egress_policy=egress_policy,
            stream=True,
            cancellation_token=cancellation_token,
        )
        with lease:
            response = lease.response
            http_redirect_hops += current_redirect_hops
            visited_urls.update(redirect_visited_urls)
            _raise_if_cancelled(cancellation_token)
            try:
                _materialize_response_body(
                    response,
                    resource_budget=resource_budget,
                )
            except _UnsupportedBoundedContentEncoding as exc:
                raise _FetchContentConversionError(
                    str(exc),
                    response_context=_build_fetch_body_limit_runtime_context(response),
                    original_error=exc,
                    failure_reason="unsupported_content_encoding",
                ) from exc
            _raise_if_cancelled(cancellation_token)
            response.raise_for_status()

            probe = (
                content_type_probe or {"ok": False, "content_type": ""}
                if meta_refresh_hops == 0
                else {"ok": False, "content_type": ""}
            )
            content_type = str(probe.get("content_type", "") or response.headers.get("Content-Type", "")).lower()
            response_text = _decode_response_text(response)
            response_content = content_diagnostic_from_bytes(bytes(response.content))
            response_url = str(response.url or current_url)
            if _should_route_response_to_html_pipeline(
                url=response_url,
                content_type=content_type,
                response_text=response_text,
                response_content=response.content,
            ):
                html_text = _extract_html_response_text(response)
                next_meta_refresh_url = _resolve_meta_refresh_follow_target(
                    response=response,
                    html_text=html_text,
                    visited_urls=visited_urls,
                    meta_refresh_hops=meta_refresh_hops,
                    normalize_url_for_http=normalize_url_for_http,
                )
                if next_meta_refresh_url is not None:
                    _raise_if_cancelled(cancellation_token)
                    current_headers = dict(resolved_headers)
                    current_headers["Referer"] = build_referer(response_url)
                    current_url = next_meta_refresh_url
                    visited_urls.add(next_meta_refresh_url)
                    meta_refresh_hops += 1
                    continue

                raw_challenge = detect_bot_challenge(
                    response=response,
                    content_text=html_text,
                )
                if raw_challenge.decision is BotChallengeDecision.CONFIRMED:
                    raise _FetchContentConversionError(
                        "HTML 原始响应疑似反爬挑战页或访问门禁。",
                        response_context=_build_fetch_content_runtime_context(response),
                        original_error=RuntimeError("raw_html_bot_challenge"),
                    )
                try:
                    _raise_if_cancelled(cancellation_token)
                    pipeline_result = convert_html(html_text, url=response_url)
                except RuntimeError as exc:
                    raise _FetchContentConversionError(
                        str(exc),
                        response_context=_build_fetch_content_runtime_context(response),
                        original_error=exc,
                    ) from exc
                title = pipeline_result.title
                markdown = pipeline_result.markdown
                extraction_source = pipeline_result.extractor_source
                renderer_source = pipeline_result.renderer_source
                normalization_applied = pipeline_result.normalization_applied
                quality_flags = list(pipeline_result.quality_flags)
                content_stats = dict(pipeline_result.content_stats)
            else:
                _raise_if_cancelled(cancellation_token)
                title, markdown, extraction_source = convert_non_html(
                    response.content,
                    _infer_docling_stream_name(url=response_url, content_type=content_type),
                )
                renderer_source = "docling"
                normalization_applied = False
                quality_flags = []
                content_stats = {
                    "text_length": len(markdown),
                    "markdown_length": len(markdown),
                }
            return {
                "title": title,
                "content": markdown,
                "extraction_source": extraction_source,
                "renderer_source": renderer_source,
                "normalization_applied": normalization_applied,
                "quality_flags": quality_flags,
                "content_stats": content_stats,
                "http_status": response.status_code,
                "final_url": response_url,
                "redirect_hops": http_redirect_hops + meta_refresh_hops,
                "response_headers": _sanitize_response_headers(response.headers),
                "response_content_length": response_content.length,
                "response_content_digest": response_content.digest,
            }
