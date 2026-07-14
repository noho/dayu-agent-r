"""Web 专属诊断投影契约。

本模块是 Web URL、正文、响应头、错误与网络事件进入日志或诊断 artifact
前的唯一投影 owner。它复用层中立的文本摘要、敏感值脱敏与有界截断
primitive，但不把 URL/HTTP 业务规则下沉到 ``dayu.runtime``。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import parse_qsl, urlsplit

from dayu.contracts.json_value import JsonValue
from dayu.runtime._digest import text_digest
from dayu.runtime.diagnostic_text import (
    redact_sensitive_diagnostic_values,
    truncate_diagnostic_text,
)

WEB_DIAGNOSTIC_SCHEMA_VERSION: Final[str] = "web-diagnostics-v2"
"""Web diagnostics artifact schema 的固定版本。"""

WEB_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = 2
"""Web diagnostics artifact schema 的固定修订号。"""

_CONTENT_DIGEST_PREFIX: Final[str] = "sha256:"
_ERROR_REDACTION_MARKER: Final[str] = "<redacted>"
_ERROR_TRUNCATION_SUFFIX: Final[str] = "...<truncated>"
_MINIMAL_ERROR_TRUNCATION_MARKER: Final[str] = "…"
_OBSERVABLE_RESPONSE_HEADER_NAMES: Final[frozenset[str]] = frozenset(
    {"cache-control", "content-length", "content-type", "retry-after"}
)
_SENSITIVE_HEADER_FRAGMENTS: Final[tuple[str, ...]] = (
    "api-key",
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
)
_HIGH_ENTROPY_HEX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32,}(?![0-9A-Fa-f])"
)


class WebDiagnosticOutcome(StrEnum):
    """Web 诊断路径的封闭 outcome。"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class WebDiagnosticBackend(StrEnum):
    """Web 诊断路径的封闭 backend。"""

    REQUESTS = "requests"
    PLAYWRIGHT = "playwright"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class WebContentDiagnostic:
    """不可逆的 Web 正文统计投影。

    Args:
        length: 原始正文长度；bytes 使用字节数，str 使用字符数。
        digest: ``sha256:<hex>`` 形式的稳定摘要。

    Returns:
        无。

    Raises:
        ValueError: 长度为负或摘要格式非法时抛出。
    """

    length: int
    digest: str

    def __post_init__(self) -> None:
        """校验正文统计投影。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 长度为负或摘要格式非法时抛出。
        """

        if isinstance(self.length, bool) or self.length < 0:
            raise ValueError("Web content diagnostic length must be a non-negative integer")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.digest):
            raise ValueError("Web content diagnostic digest must be sha256 lowercase hex")


@dataclass(frozen=True, slots=True)
class WebResponseHeaderProjection:
    """响应头的最小披露投影。

    Args:
        present_names: 可观察 header 的小写名称，仅表示存在性。
        sensitive_names: 已观察到但不保存 value 的敏感 header 名称。
        content_type: 从 Content-Type 投影出的规范化 media type。
        content_length: 从 Content-Length 投影出的非负整数。

    Returns:
        无。

    Raises:
        无。
    """

    present_names: tuple[str, ...]
    sensitive_names: tuple[str, ...]
    content_type: str = ""
    content_length: int | None = None

    def to_json(self) -> dict[str, JsonValue]:
        """转换为可写入 artifact 的 JSON 对象。

        Args:
            无。

        Returns:
            只包含 header presence 与受限语义值的对象。

        Raises:
            无。
        """

        return {
            "present_names": list(self.present_names),
            "sensitive_names": list(self.sensitive_names),
            "content_type": self.content_type,
            "content_length": self.content_length,
        }


@dataclass(frozen=True, slots=True)
class WebDiagnosticProjection:
    """单条 Web 路径诊断的强类型安全投影。

    Args:
        stage: 产生诊断的稳定阶段标签。
        sampled: 该路径是否实际采样。
        outcome: 路径 outcome。
        safe_url: 已删除 userinfo/query/fragment 的安全 URL。
        elapsed_seconds: 非负耗时秒数。
        backend: 成功路径或已执行路径使用的 backend。
        content: 可选正文长度与摘要。
        http_status: 可选 HTTP 状态码。
        error_code: 可选稳定错误码。
        error_message: 可选已脱敏且有界错误文本。
        challenge_decision: challenge owner 产生的封闭判定字符串。
        response_headers: 可选最小响应头投影。

    Returns:
        无。

    Raises:
        ValueError: 耗时为负，或 completed outcome 缺少 backend/content 时抛出。
    """

    stage: str
    sampled: bool
    outcome: WebDiagnosticOutcome
    safe_url: str
    elapsed_seconds: float
    backend: WebDiagnosticBackend | None = None
    content: WebContentDiagnostic | None = None
    http_status: int | None = None
    error_code: str = ""
    error_message: str = ""
    challenge_decision: str = "none"
    response_headers: WebResponseHeaderProjection | None = None

    def __post_init__(self) -> None:
        """校验 Web 诊断投影不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 字段违反封闭 schema 时抛出。
        """

        if self.elapsed_seconds < 0:
            raise ValueError("Web diagnostic elapsed_seconds must be non-negative")
        if self.outcome is WebDiagnosticOutcome.COMPLETED:
            if self.backend is None or self.content is None:
                raise ValueError("completed Web diagnostic requires backend and content")
        if self.challenge_decision not in {"none", "suspected", "confirmed"}:
            raise ValueError("unsupported Web diagnostic challenge decision")

    def to_json(self) -> dict[str, JsonValue]:
        """转换为 schema v2 路径对象。

        ``ok`` 只是 producer observation；consumer 不得用它单独签发 PASS。

        Args:
            无。

        Returns:
            不含正文、HTML、query、userinfo 或敏感 header value 的 JSON 对象。

        Raises:
            无。
        """

        payload: dict[str, JsonValue] = {
            "stage": self.stage,
            "sampled": self.sampled,
            "outcome": self.outcome.value,
            "ok": self.outcome is WebDiagnosticOutcome.COMPLETED,
            "safe_url": self.safe_url,
            "elapsed_seconds": self.elapsed_seconds,
        }
        if self.backend is not None:
            payload["backend"] = self.backend.value
        if self.content is not None:
            payload["content_length"] = self.content.length
            payload["content_digest"] = self.content.digest
        if self.http_status is not None:
            payload["http_status"] = self.http_status
        elif self.outcome is WebDiagnosticOutcome.COMPLETED:
            payload["http_status"] = None
        if self.error_code:
            payload["error_code"] = self.error_code
        if self.error_message:
            payload["error_message"] = self.error_message
        if self.challenge_decision != "none":
            payload["challenge_decision"] = self.challenge_decision
        if self.response_headers is not None:
            payload["response_headers"] = self.response_headers.to_json()
        return payload


def project_safe_url(url: str) -> str:
    """把 URL 投影为不含 userinfo、query 与 fragment 的安全形式。

    Args:
        url: 原始 HTTP(S) URL。

    Returns:
        ``scheme + IDNA host + explicit port + path`` 安全 URL。

    Raises:
        ValueError: URL 缺少 HTTP(S) scheme/host，IDNA 非法或端口非法时抛出。
    """

    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Web diagnostic URL must use http or https")
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("Web diagnostic URL must include a host")
    try:
        normalized_host = hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Web diagnostic URL host or port is invalid") from exc
    rendered_host = f"[{normalized_host}]" if ":" in normalized_host else normalized_host
    authority = rendered_host if port is None else f"{rendered_host}:{port}"
    path = parsed.path or "/"
    return f"{scheme}://{authority}{path}"


def project_safe_url_or_empty(url: str) -> str:
    """尽力生成安全 URL，非法输入返回空字符串且不回显原文。

    Args:
        url: 原始 URL。

    Returns:
        安全 URL；非法时返回空字符串。

    Raises:
        无。
    """

    try:
        return project_safe_url(url)
    except ValueError:
        return ""


def content_diagnostic_from_text(value: str) -> WebContentDiagnostic:
    """从文本产生不可逆正文统计。

    Args:
        value: 原始文本。

    Returns:
        字符长度与 SHA-256 摘要。

    Raises:
        无。
    """

    return WebContentDiagnostic(length=len(value), digest=text_digest(value))


def content_diagnostic_from_bytes(value: bytes) -> WebContentDiagnostic:
    """从原始 bytes 产生不可逆正文统计。

    Args:
        value: 原始 bytes。

    Returns:
        字节长度与对 exact bytes 计算的 SHA-256 摘要。

    Raises:
        无。
    """

    return WebContentDiagnostic(
        length=len(value),
        digest=_CONTENT_DIGEST_PREFIX + hashlib.sha256(value).hexdigest(),
    )


def project_response_headers(
    headers: Mapping[str, str],
) -> WebResponseHeaderProjection:
    """把响应头投影为最小 allowlist value 与敏感字段 presence。

    Args:
        headers: 原始响应头。

    Returns:
        不含 Cookie、authorization 或未知 header value 的投影。

    Raises:
        无。
    """

    present_names: set[str] = set()
    sensitive_names: set[str] = set()
    content_type = ""
    content_length: int | None = None
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().lower()
        if any(fragment in name for fragment in _SENSITIVE_HEADER_FRAGMENTS):
            sensitive_names.add(name)
            continue
        if name not in _OBSERVABLE_RESPONSE_HEADER_NAMES:
            continue
        present_names.add(name)
        if name == "content-type":
            candidate = str(raw_value).split(";", 1)[0].strip().lower()
            if re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", candidate):
                content_type = candidate
        elif name == "content-length":
            candidate = str(raw_value).strip()
            if candidate.isascii() and candidate.isdecimal():
                parsed_length = int(candidate)
                if parsed_length >= 0:
                    content_length = parsed_length
    return WebResponseHeaderProjection(
        present_names=tuple(sorted(present_names)),
        sensitive_names=tuple(sorted(sensitive_names)),
        content_type=content_type,
        content_length=content_length,
    )


def sensitive_url_values(url: str) -> tuple[str, ...]:
    """提取 URL 中必须从错误文本删除的 userinfo/query values。

    Args:
        url: 原始 URL。

    Returns:
        去重后的非空敏感值元组。

    Raises:
        无。非法 URL 返回可安全提取到的子集或空元组。
    """

    parsed = urlsplit(url)
    values: list[str] = []
    if parsed.username:
        values.append(parsed.username)
    if parsed.password:
        values.append(parsed.password)
    try:
        values.extend(value for _key, value in parse_qsl(parsed.query, keep_blank_values=False))
    except ValueError:
        pass
    return tuple(dict.fromkeys(value for value in values if value))


def project_error_message(
    message: str,
    *,
    max_chars: int,
    sensitive_values: Sequence[str] = (),
) -> str:
    """把异常或失败文本脱敏并限制长度。

    Args:
        message: 原始错误文本。
        max_chars: 投影最大字符数，必须为正整数。
        sensitive_values: caller 已知的 query、userinfo、header 或 sentinel value。

    Returns:
        已删除已知敏感值、高熵十六进制 token，并经 runtime primitive 脱敏和截断的文本。

    Raises:
        ValueError: ``max_chars`` 不是正整数时抛出。
    """

    projected = message
    for value in sorted(set(sensitive_values), key=len, reverse=True):
        if value:
            projected = projected.replace(value, _ERROR_REDACTION_MARKER)
    projected = _HIGH_ENTROPY_HEX_PATTERN.sub(_ERROR_REDACTION_MARKER, projected)
    projected = redact_sensitive_diagnostic_values(
        projected,
        redaction_marker=_ERROR_REDACTION_MARKER,
    )
    if max_chars == 1:
        single_char_projection = truncate_diagnostic_text(
            projected,
            max_chars=max_chars,
            truncated_suffix="",
        )
        if single_char_projection == projected:
            return single_char_projection
        return _MINIMAL_ERROR_TRUNCATION_MARKER
    truncated_suffix = (
        _ERROR_TRUNCATION_SUFFIX
        if max_chars > len(_ERROR_TRUNCATION_SUFFIX)
        else _MINIMAL_ERROR_TRUNCATION_MARKER
    )
    return truncate_diagnostic_text(
        projected,
        max_chars=max_chars,
        truncated_suffix=truncated_suffix,
    )


def completed_text_projection(
    *,
    stage: str,
    url: str,
    elapsed_seconds: float,
    backend: WebDiagnosticBackend,
    content: str,
    http_status: int | None,
    response_headers: Mapping[str, str] | None = None,
) -> WebDiagnosticProjection:
    """构造文本成功路径投影。

    Args:
        stage: 稳定阶段标签。
        url: 原始 URL。
        elapsed_seconds: 非负耗时。
        backend: 实际执行 backend。
        content: 成功正文；只计算长度和摘要。
        http_status: 可选 HTTP 状态码。
        response_headers: 可选原始响应头。

    Returns:
        不含可逆正文的成功投影。

    Raises:
        ValueError: 投影字段非法时抛出。
    """

    return WebDiagnosticProjection(
        stage=stage,
        sampled=True,
        outcome=WebDiagnosticOutcome.COMPLETED,
        safe_url=project_safe_url_or_empty(url),
        elapsed_seconds=elapsed_seconds,
        backend=backend,
        content=content_diagnostic_from_text(content),
        http_status=http_status,
        response_headers=(
            project_response_headers(response_headers)
            if response_headers is not None
            else None
        ),
    )


def completed_bytes_projection(
    *,
    stage: str,
    url: str,
    elapsed_seconds: float,
    backend: WebDiagnosticBackend,
    content: bytes,
    http_status: int | None,
    response_headers: Mapping[str, str] | None = None,
) -> WebDiagnosticProjection:
    """构造 bytes 成功路径投影。

    Args:
        stage: 稳定阶段标签。
        url: 原始 URL。
        elapsed_seconds: 非负耗时。
        backend: 实际执行 backend。
        content: exact response bytes；只计算长度和摘要。
        http_status: 可选 HTTP 状态码。
        response_headers: 可选原始响应头。

    Returns:
        不含可逆 bytes 的成功投影。

    Raises:
        ValueError: 投影字段非法时抛出。
    """

    return WebDiagnosticProjection(
        stage=stage,
        sampled=True,
        outcome=WebDiagnosticOutcome.COMPLETED,
        safe_url=project_safe_url_or_empty(url),
        elapsed_seconds=elapsed_seconds,
        backend=backend,
        content=content_diagnostic_from_bytes(content),
        http_status=http_status,
        response_headers=(
            project_response_headers(response_headers)
            if response_headers is not None
            else None
        ),
    )


def failed_projection(
    *,
    stage: str,
    url: str,
    elapsed_seconds: float,
    error_code: str,
    error_message: str,
    max_error_chars: int,
    backend: WebDiagnosticBackend | None = None,
    http_status: int | None = None,
    challenge_decision: str = "none",
    response_headers: Mapping[str, str] | None = None,
    sensitive_values: Sequence[str] = (),
    sampled: bool = True,
) -> WebDiagnosticProjection:
    """构造失败路径的安全投影。

    Args:
        stage: 稳定阶段标签。
        url: 原始 URL。
        elapsed_seconds: 非负耗时。
        error_code: 稳定错误码。
        error_message: 原始错误文本。
        max_error_chars: 脱敏后最大字符数。
        backend: 已实际执行的可选 backend。
        http_status: 可选 HTTP 状态码。
        challenge_decision: challenge owner 的封闭判定。
        response_headers: 可选原始响应头。
        sensitive_values: caller 已知的额外敏感值。
        sampled: 是否实际采样。

    Returns:
        已脱敏、有界且不含 raw URL secret 的失败投影。

    Raises:
        ValueError: 投影字段非法时抛出。
    """

    secrets = (*sensitive_url_values(url), *sensitive_values)
    safe_url = project_safe_url_or_empty(url)
    sanitized_message = error_message.replace(url, safe_url) if url else error_message
    return WebDiagnosticProjection(
        stage=stage,
        sampled=sampled,
        outcome=WebDiagnosticOutcome.FAILED,
        safe_url=safe_url,
        elapsed_seconds=elapsed_seconds,
        backend=backend,
        http_status=http_status,
        error_code=error_code,
        error_message=project_error_message(
            sanitized_message,
            max_chars=max_error_chars,
            sensitive_values=secrets,
        ),
        challenge_decision=challenge_decision,
        response_headers=(
            project_response_headers(response_headers)
            if response_headers is not None
            else None
        ),
    )


def project_network_event(
    *,
    event: str,
    url: str,
    method: str,
    resource_type: str,
    status_code: int | None,
) -> dict[str, JsonValue]:
    """构造不含 query/header/body 的 Playwright 网络事件摘要。

    Args:
        event: ``request`` 或 ``response`` 事件标签。
        url: 原始网络事件 URL。
        method: HTTP method。
        resource_type: Playwright resource type。
        status_code: response 状态码；request 使用 ``None``。

    Returns:
        安全 URL、method、resource type 与可选状态码对象。

    Raises:
        ValueError: event 不是封闭值时抛出。
    """

    if event not in {"request", "response"}:
        raise ValueError("unsupported Web network diagnostic event")
    payload: dict[str, JsonValue] = {
        "event": event,
        "safe_url": project_safe_url_or_empty(url),
        "method": method.upper(),
        "resource_type": resource_type,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    return payload
