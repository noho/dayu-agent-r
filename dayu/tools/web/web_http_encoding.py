"""网页抓取的内容编码与字符集处理工具。

本模块只承载 HTTP 内容编码声明、响应字符集解析与文本解码规则，
不包含抓取编排、错误信封或 HTML/Docling 路由决策。
"""

from __future__ import annotations

import codecs
import importlib.util
import re
from collections.abc import Collection, Mapping

import requests

_BASE_ACCEPT_ENCODINGS = ("gzip", "deflate")
_DEFAULT_TEXT_FALLBACK_ENCODING = "iso-8859-1"


def _is_optional_module_available(module_names: Collection[str]) -> bool:
    """判断可选解码依赖是否可用。

    Args:
        module_names: 可选模块名集合。

    Returns:
        只要任一模块可导入则返回 `True`。

    Raises:
        无。
    """

    return any(importlib.util.find_spec(name) is not None for name in module_names)


def _resolve_supported_accept_encodings() -> tuple[str, ...]:
    """解析当前运行时真正支持的内容编码声明。

    Args:
        无。

    Returns:
        可安全声明给服务端的编码元组。

    Raises:
        无。
    """

    supported: list[str] = list(_BASE_ACCEPT_ENCODINGS)
    if _is_optional_module_available(("brotli", "brotlicffi")):
        supported.append("br")
    if _is_optional_module_available(("zstandard", "zstd")):
        supported.append("zstd")
    return tuple(supported)


def _build_accept_encoding_value() -> str:
    """构建当前运行时的 Accept-Encoding 头值。

    Args:
        无。

    Returns:
        逗号分隔的内容编码声明。

    Raises:
        无。
    """

    return ", ".join(_resolve_supported_accept_encodings())


def _extract_content_encoding_tokens(headers: Mapping[str, str] | None) -> tuple[str, ...]:
    """从响应头提取 Content-Encoding token。

    Args:
        headers: 响应头映射。

    Returns:
        小写去空白后的编码 token 元组。

    Raises:
        无。
    """

    if headers is None:
        return ()
    header_value = str(headers.get("Content-Encoding") or headers.get("content-encoding") or "")
    if not header_value:
        return ()
    return tuple(token.strip().lower() for token in header_value.split(",") if token.strip())


def _find_unsupported_content_encodings(headers: Mapping[str, str] | None) -> tuple[str, ...]:
    """识别当前运行时无法处理的 Content-Encoding。

    Args:
        headers: 响应头映射。

    Returns:
        不受支持的编码 token 元组。

    Raises:
        无。
    """

    supported = set(_resolve_supported_accept_encodings()) | {"identity"}
    return tuple(token for token in _extract_content_encoding_tokens(headers) if token not in supported)


def _normalize_charset_name(charset: str) -> str | None:
    """规范化字符集名称并校验当前解释器是否支持。

    Args:
        charset: 原始字符集名称。

    Returns:
        规范化后的字符集名称；无法识别时返回 `None`。

    Raises:
        无。
    """

    normalized = str(charset or "").strip().strip("\"'").split(";", 1)[0].strip().lower()
    if not normalized:
        return None
    alias_map = {
        "utf8": "utf-8",
        "gb2312": "gb18030",
        "gbk": "gb18030",
        "gb_2312-80": "gb18030",
    }
    resolved = alias_map.get(normalized, normalized)
    try:
        codecs.lookup(resolved)
    except LookupError:
        return None
    return resolved


def _extract_charset_from_content_type(content_type: str) -> str | None:
    """从 Content-Type 中提取字符集。

    Args:
        content_type: Content-Type 响应头值。

    Returns:
        规范化后的字符集名称；缺失时返回 `None`。

    Raises:
        无。
    """

    match = re.search(r"charset\s*=\s*['\"]?([a-zA-Z0-9._-]+)", str(content_type or ""), flags=re.IGNORECASE)
    if match is None:
        return None
    return _normalize_charset_name(match.group(1))


def _extract_charset_from_html_bytes(content: bytes) -> str | None:
    """从 HTML 原始字节前缀里的 meta 标签提取字符集。

    Args:
        content: HTML 原始字节。

    Returns:
        规范化后的字符集名称；缺失时返回 `None`。

    Raises:
        无。
    """

    if not content:
        return None
    prefix_text = content[:4096].decode("latin-1", errors="ignore")
    patterns = (
        r"<meta[^>]+charset\s*=\s*['\"]?\s*([a-zA-Z0-9._-]+)",
        r"<meta[^>]+content\s*=\s*['\"][^>]*?charset\s*=\s*([a-zA-Z0-9._-]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, prefix_text, flags=re.IGNORECASE)
        if match is None:
            continue
        resolved = _normalize_charset_name(match.group(1))
        if resolved:
            return resolved
    return None


def _resolve_response_text_encoding(response: requests.Response) -> str | None:
    """解析响应文本应使用的解码字符集。

    优先级：HTTP header charset -> HTML meta charset -> apparent_encoding -> requests 默认 encoding。

    Args:
        response: 原始 HTTP 响应。

    Returns:
        规范化后的字符集名称；无法确定时返回 `None`。

    Raises:
        无。
    """

    headers = getattr(response, "headers", {})
    header_encoding = _extract_charset_from_content_type(
        str(headers.get("Content-Type", "") or headers.get("content-type", "") or "")
    )
    if header_encoding:
        return header_encoding

    content = getattr(response, "content", b"") or b""
    meta_encoding = _extract_charset_from_html_bytes(content)
    if meta_encoding:
        return meta_encoding

    apparent_encoding = _normalize_charset_name(str(getattr(response, "apparent_encoding", "") or ""))
    if apparent_encoding:
        return apparent_encoding

    response_encoding = _normalize_charset_name(str(getattr(response, "encoding", "") or ""))
    if response_encoding:
        return response_encoding
    return None


def _decode_response_text(response: requests.Response) -> str:
    """统一解码响应文本，优先纠正 HTML 旧站字符集。

    Args:
        response: 原始 HTTP 响应。

    Returns:
        解码后的文本；失败时尽力回退到 requests 原始 text。

    Raises:
        无。
    """

    content = getattr(response, "content", b"") or b""
    resolved_encoding = _resolve_response_text_encoding(response)
    if content and resolved_encoding:
        try:
            return content.decode(resolved_encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            pass

    if content:
        try:
            return content.decode(_DEFAULT_TEXT_FALLBACK_ENCODING, errors="replace")
        except UnicodeDecodeError:
            pass

    try:
        return str(getattr(response, "text", "") or "")
    except Exception:
        return ""