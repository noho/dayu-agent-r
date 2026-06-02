"""OpenAI runner 诊断载荷摘要工具。

本模块为 OpenAI-compatible runner 内部协议错误提供统一的有界、
脱敏、摘要化诊断载荷。调用方传入 provider JSON object 或非法
UTF-8 chunk 后，本模块只返回可用于排障的有限结构，不保存完整
provider 原始载荷。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue

_LOGGER: logging.Logger = logging.getLogger(__name__)

_DIAGNOSTIC_PAYLOAD_VERSION: int = 1
_DIAGNOSTIC_PAYLOAD_MAX_BYTES: int = 4096
_DIAGNOSTIC_KEYS_MAX_ITEMS: int = 24
_DIAGNOSTIC_SCALAR_MAX_CHARS: int = 160
_DIAGNOSTIC_CHUNK_PREFIX_MAX_BYTES: int = 96
_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "api_key",
    "secret",
    "token",
    "password",
    "authorization",
    "credential",
)

_VERSION_FIELD: str = "version"
_SOURCE_FIELD: str = "source"
_KIND_FIELD: str = "kind"
_CANONICAL_BYTE_SIZE_FIELD: str = "canonical_byte_size"
_SHA256_DIGEST_FIELD: str = "sha256_digest"
_TOP_LEVEL_KEYS_FIELD: str = "top_level_keys"
_PREVIEW_FIELD: str = "preview"
_PROVIDER_ERROR_FIELD: str = "provider_error"
_REDACTED_MARKER: str = "<redacted>"
_ERROR_FIELD: str = "error"
_INVALID_UTF8_SOURCE: str = "invalid_utf8_chunk"
_HTTP_ERROR_SOURCE: str = "http_error_body"
_PROVIDER_ERROR_KIND: str = "provider_error"
_PROTOCOL_OBJECT_KIND: str = "protocol_object"
_INVALID_UTF8_KIND: str = "invalid_utf8"
_HTTP_ERROR_KIND: str = "http_error"
_REASON_FIELD: str = "reason"
_CHUNK_BYTE_SIZE_FIELD: str = "chunk_byte_size"
_CHUNK_SHA256_DIGEST_FIELD: str = "chunk_sha256_digest"
_CHUNK_PREFIX_BASE64_FIELD: str = "chunk_prefix_base64"
_FINAL_DECODE_FIELD: str = "final_decode"
_SUMMARY_TYPE_FIELD: str = "type"
_SUMMARY_KEYS_FIELD: str = "keys"
_SUMMARY_ITEMS_FIELD: str = "items"
_OBJECT_SUMMARY_TYPE: str = "object"
_ARRAY_SUMMARY_TYPE: str = "array"
_PROVIDER_ERROR_SUMMARY_FIELDS: tuple[str, ...] = ("code", "type", "param")
_FALLBACK_SCALAR_MAX_CHARS: int = 32
_CANONICAL_JSON_SEPARATORS: tuple[str, str] = (",", ":")


def provider_error_diagnostic_payload(
    payload: dict[str, JsonValue], *, source: str
) -> JsonValue:
    """生成 provider error object 的有界诊断载荷。

    本函数固定检查 ``payload["error"]`` 子对象；仅当该值是 JSON object
    时提取 ``code`` / ``type`` / ``param`` 等低风险短字段。完整 ``error``
    子对象不会进入返回值。

    :param payload: provider 返回的顶层 JSON object。
    :param source: 调用路径的模块级错误码或来源标识。
    :returns: 有界、脱敏、摘要化的 JSON 诊断对象。
    :raises Exception: 不主动抛出异常。
    """

    canonical = _canonical_payload_metadata(payload)
    diagnostic: dict[str, JsonValue] = _base_diagnostic_payload(
        source=source,
        kind=_PROVIDER_ERROR_KIND,
        canonical=canonical,
    )
    diagnostic[_TOP_LEVEL_KEYS_FIELD] = _bounded_keys(payload)
    diagnostic[_PREVIEW_FIELD] = _top_level_preview(payload)
    error_value = payload.get(_ERROR_FIELD)
    if isinstance(error_value, dict):
        diagnostic[_PROVIDER_ERROR_FIELD] = _provider_error_summary(error_value)
    return _bounded_payload(diagnostic)


def protocol_object_diagnostic_payload(
    payload: dict[str, JsonValue], *, source: str, reason: str
) -> JsonValue:
    """生成通用协议对象错误的有界诊断载荷。

    :param payload: provider 返回的顶层 JSON object。
    :param source: 调用路径的模块级错误码或来源标识。
    :param reason: 调用路径的模块级协议错误原因。
    :returns: 有界、脱敏、摘要化的 JSON 诊断对象。
    :raises Exception: 不主动抛出异常。
    """

    canonical = _canonical_payload_metadata(payload)
    diagnostic: dict[str, JsonValue] = _base_diagnostic_payload(
        source=source,
        kind=_PROTOCOL_OBJECT_KIND,
        canonical=canonical,
    )
    diagnostic[_REASON_FIELD] = reason
    diagnostic[_TOP_LEVEL_KEYS_FIELD] = _bounded_keys(payload)
    diagnostic[_PREVIEW_FIELD] = _top_level_preview(payload)
    return _bounded_payload(diagnostic)


def invalid_utf8_diagnostic_payload(
    chunk: bytes, *, final_decode: bool
) -> JsonValue:
    """生成非法 UTF-8 chunk 的有界诊断载荷。

    :param chunk: 触发解码失败的原始字节片段；流尾 flush 失败时可为空。
    :param final_decode: 是否发生在流尾 flush 阶段。
    :returns: 有界、摘要化的 JSON 诊断对象，包含 chunk 大小、chunk 摘要与
        有界前缀。
    :raises Exception: 不主动抛出异常。
    """

    chunk_digest = hashlib.sha256(chunk).hexdigest()
    diagnostic: dict[str, JsonValue] = _base_diagnostic_payload(
        source=_INVALID_UTF8_SOURCE,
        kind=_INVALID_UTF8_KIND,
        canonical=(len(chunk), chunk_digest),
    )
    diagnostic[_CHUNK_BYTE_SIZE_FIELD] = len(chunk)
    diagnostic[_CHUNK_SHA256_DIGEST_FIELD] = chunk_digest
    diagnostic[_CHUNK_PREFIX_BASE64_FIELD] = base64.b64encode(
        chunk[:_DIAGNOSTIC_CHUNK_PREFIX_MAX_BYTES]
    ).decode("ascii")
    diagnostic[_FINAL_DECODE_FIELD] = final_decode
    return _bounded_payload(diagnostic)


def http_error_diagnostic_payload(payload: dict[str, JsonValue]) -> JsonValue:
    """生成 HTTP JSON error body 的有界诊断载荷。

    HTTP 错误体在调用本函数前已由 Runner 按字节上限读取；本函数只从
    JSON object 中派生脱敏、摘要化诊断结构，不保存完整 provider JSON。

    :param payload: HTTP error body 解析得到的 JSON object。
    :returns: 有界、脱敏、摘要化的 JSON 诊断对象。
    :raises Exception: 不主动抛出异常。
    """

    canonical = _canonical_payload_metadata(payload)
    diagnostic: dict[str, JsonValue] = _base_diagnostic_payload(
        source=_HTTP_ERROR_SOURCE,
        kind=_HTTP_ERROR_KIND,
        canonical=canonical,
    )
    diagnostic[_TOP_LEVEL_KEYS_FIELD] = _bounded_keys(payload)
    diagnostic[_PREVIEW_FIELD] = _top_level_preview(payload)
    error_value = payload.get(_ERROR_FIELD)
    if isinstance(error_value, dict):
        diagnostic[_PROVIDER_ERROR_FIELD] = _provider_error_summary(error_value)
    return _bounded_payload(diagnostic)


def _canonical_payload_metadata(
    payload: dict[str, JsonValue],
) -> tuple[int, str]:
    """计算诊断对象对应原始 JSON object 的 canonical 大小与摘要。

    :param payload: 要摘要的 JSON object。
    :returns: ``(canonical_byte_size, sha256_digest)``。
    :raises Exception: 不主动抛出异常。
    """

    canonical_text = json.dumps(
        _json_native_value(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=_CANONICAL_JSON_SEPARATORS,
    )
    canonical_bytes = canonical_text.encode("utf-8")
    return len(canonical_bytes), hashlib.sha256(canonical_bytes).hexdigest()


def _base_diagnostic_payload(
    *, source: str, kind: str, canonical: tuple[int, str]
) -> dict[str, JsonValue]:
    """构造所有诊断载荷共享的基础字段。

    :param source: 调用路径来源标识。
    :param kind: 诊断载荷类别。
    :param canonical: 被诊断对象大小与摘要；JSON object 路径使用
        canonical JSON bytes，非法 UTF-8 路径使用 raw chunk bytes。
    :returns: 基础诊断 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    canonical_byte_size, sha256_digest = canonical
    return {
        _VERSION_FIELD: _DIAGNOSTIC_PAYLOAD_VERSION,
        _SOURCE_FIELD: source,
        _KIND_FIELD: kind,
        _CANONICAL_BYTE_SIZE_FIELD: canonical_byte_size,
        _SHA256_DIGEST_FIELD: sha256_digest,
    }


def _bounded_payload(payload: dict[str, JsonValue]) -> JsonValue:
    """按固定 fallback 顺序把诊断载荷压到大小上限内。

    :param payload: 初始诊断载荷。
    :returns: 不超过大小上限的诊断载荷；理论最小结构超限时返回最小结构。
    :raises Exception: 不主动抛出异常。
    """

    if _json_byte_size(payload) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES:
        return payload

    truncated = _truncate_preview_fields(payload)
    if _json_byte_size(truncated) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES:
        return truncated

    minimal = _minimal_payload(payload)
    if _json_byte_size(minimal) > _DIAGNOSTIC_PAYLOAD_MAX_BYTES:
        _LOGGER.warning(
            "openai_runner.diagnostic_payload_minimal_over_limit kind=%s",
            minimal[_KIND_FIELD],
        )
    return minimal


def _json_byte_size(value: JsonValue) -> int:
    """计算 JSON 值的 UTF-8 序列化大小。

    :param value: JSON 值。
    :returns: 使用本模块紧凑分隔符序列化后的字节数。
    :raises Exception: 不主动抛出异常。
    """

    encoded = json.dumps(
        _json_native_value(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=_CANONICAL_JSON_SEPARATORS,
    ).encode("utf-8")
    return len(encoded)


def _json_native_value(value: JsonValue) -> JsonValue:
    """把 ``Mapping`` 归一为标准 ``dict`` 以便稳定 JSON 序列化。

    :param value: JSON 值。
    :returns: 只包含标准 ``dict`` / ``list`` / 标量的 JSON 值。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, Mapping):
        return {
            key: _json_native_value(child_value)
            for key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_json_native_value(child_value) for child_value in value]
    return value


def _bounded_keys(payload: dict[str, JsonValue]) -> list[JsonValue]:
    """返回有界 top-level key 列表。

    :param payload: provider 顶层 JSON object。
    :returns: 排序后截断的 key 列表。
    :raises Exception: 不主动抛出异常。
    """

    keys: list[JsonValue] = []
    for key in sorted(payload.keys())[:_DIAGNOSTIC_KEYS_MAX_ITEMS]:
        keys.append(key)
    return keys


def _top_level_preview(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """生成顶层字段的有界预览。

    :param payload: provider 顶层 JSON object。
    :returns: 仅包含有限 key 与有界标量摘要的 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    preview: dict[str, JsonValue] = {}
    for key in sorted(payload.keys())[:_DIAGNOSTIC_KEYS_MAX_ITEMS]:
        if _is_sensitive_key(key):
            preview[key] = _REDACTED_MARKER
            continue
        value = payload[key]
        if isinstance(value, dict) or isinstance(value, list):
            preview[key] = _container_summary(value)
            continue
        preview[key] = _scalar_preview(value, max_chars=_DIAGNOSTIC_SCALAR_MAX_CHARS)
    return preview


def _provider_error_summary(
    error_payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """提取 provider ``error`` 子对象中的低风险字段。

    :param error_payload: provider ``error`` 子对象。
    :returns: 只包含低风险字段与脱敏标记的摘要。
    :raises Exception: 不主动抛出异常。
    """

    summary: dict[str, JsonValue] = {}
    for key in _PROVIDER_ERROR_SUMMARY_FIELDS:
        if key not in error_payload:
            continue
        if _is_sensitive_key(key):
            summary[key] = _REDACTED_MARKER
            continue
        value = error_payload[key]
        keep_value, preview = _provider_error_scalar_preview(value)
        if keep_value:
            summary[key] = preview
    return summary


def _provider_error_scalar_preview(value: JsonValue) -> tuple[bool, JsonValue]:
    """生成 provider error 低风险字段的标量预览。

    :param value: provider ``error`` 子对象中的候选字段值。
    :returns: ``(是否保留, 预览值)``；空字符串与容器值不保留。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, str):
        if value.strip() == "":
            return False, ""
        return True, _scalar_preview(
            value,
            max_chars=_DIAGNOSTIC_SCALAR_MAX_CHARS,
        )
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return True, value
    if value is None:
        return True, None
    return False, ""


def _container_summary(value: JsonValue) -> JsonValue:
    """生成容器值的结构摘要。

    :param value: JSON 值。
    :returns: ``dict`` / ``list`` 的有界结构摘要；标量值原样摘要。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, Mapping):
        return {
            _SUMMARY_TYPE_FIELD: _OBJECT_SUMMARY_TYPE,
            _SUMMARY_KEYS_FIELD: _bounded_keys(dict(value)),
        }
    if isinstance(value, list):
        return {
            _SUMMARY_TYPE_FIELD: _ARRAY_SUMMARY_TYPE,
            _SUMMARY_ITEMS_FIELD: len(value),
        }
    return _scalar_preview(value, max_chars=_DIAGNOSTIC_SCALAR_MAX_CHARS)


def _scalar_preview(value: JsonValue, *, max_chars: int) -> JsonValue:
    """生成标量值的有界预览。

    :param value: JSON 值。
    :param max_chars: 字符串最大保留长度。
    :returns: 有界标量预览；容器值返回结构摘要。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, str):
        return value[:max_chars]
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value
    if value is None:
        return None
    return _container_summary(value)


def _truncate_preview_fields(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """第一阶段 fallback：进一步截断 preview 类字段。

    :param payload: 初始诊断载荷。
    :returns: preview 字段被缩短后的诊断载荷。
    :raises Exception: 不主动抛出异常。
    """

    truncated = dict(payload)
    preview = truncated.get(_PREVIEW_FIELD)
    if isinstance(preview, dict):
        truncated[_PREVIEW_FIELD] = {
            key: _scalar_preview(value, max_chars=_FALLBACK_SCALAR_MAX_CHARS)
            for key, value in preview.items()
        }
    provider_error = truncated.get(_PROVIDER_ERROR_FIELD)
    if isinstance(provider_error, dict):
        truncated[_PROVIDER_ERROR_FIELD] = {
            key: _scalar_preview(value, max_chars=_FALLBACK_SCALAR_MAX_CHARS)
            for key, value in provider_error.items()
        }
    chunk_prefix = truncated.get(_CHUNK_PREFIX_BASE64_FIELD)
    if isinstance(chunk_prefix, str):
        truncated[_CHUNK_PREFIX_BASE64_FIELD] = chunk_prefix[
            :_FALLBACK_SCALAR_MAX_CHARS
        ]
    return truncated


def _minimal_payload(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """第二阶段 fallback：删除 preview 与 top-level keys 后保留最小结构。

    :param payload: 诊断载荷。
    :returns: 最小诊断结构。
    :raises Exception: 不主动抛出异常。
    """

    return {
        _VERSION_FIELD: payload[_VERSION_FIELD],
        _SOURCE_FIELD: payload[_SOURCE_FIELD],
        _KIND_FIELD: payload[_KIND_FIELD],
        _CANONICAL_BYTE_SIZE_FIELD: payload[_CANONICAL_BYTE_SIZE_FIELD],
        _SHA256_DIGEST_FIELD: payload[_SHA256_DIGEST_FIELD],
    }


def _is_sensitive_key(key: str) -> bool:
    """判断字段名是否命中敏感片段。

    :param key: JSON object 字段名。
    :returns: 命中敏感片段时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    normalized = _normalized_sensitive_key(key)
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _normalized_sensitive_key(key: str) -> str:
    """规范化字段名以便敏感片段匹配。

    :param key: JSON object 字段名。
    :returns: 小写且将破折号规范化为下划线后的字段名。
    :raises Exception: 不主动抛出异常。
    """

    return key.lower().replace("-", "_")


__all__ = [
    "http_error_diagnostic_payload",
    "invalid_utf8_diagnostic_payload",
    "protocol_object_diagnostic_payload",
    "provider_error_diagnostic_payload",
]
