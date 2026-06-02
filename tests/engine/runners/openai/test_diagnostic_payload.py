"""OpenAI runner 诊断载荷 helper 测试。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping

from dayu.contracts.json_value import JsonValue
from dayu.engine.runners.openai.diagnostic_payload import (
    _CANONICAL_BYTE_SIZE_FIELD,
    _DIAGNOSTIC_PAYLOAD_MAX_BYTES,
    _KIND_FIELD,
    _PREVIEW_FIELD,
    _PROVIDER_ERROR_FIELD,
    _SHA256_DIGEST_FIELD,
    _SOURCE_FIELD,
    _TOP_LEVEL_KEYS_FIELD,
    _VERSION_FIELD,
    invalid_utf8_diagnostic_payload,
    protocol_object_diagnostic_payload,
    provider_error_diagnostic_payload,
)

_SOURCE: str = "unit_source"
_REASON: str = "unit_reason"


def _serialized_size(value: JsonValue) -> int:
    """计算 JSON 值序列化后的 UTF-8 字节数。

    :param value: JSON 值。
    :returns: 紧凑 JSON 序列化后的字节数。
    :raises Exception: 不主动抛出异常。
    """

    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _leaf_strings(value: JsonValue) -> Iterator[str]:
    """遍历 JSON 值中的字符串叶子。

    :param value: JSON 值。
    :returns: 字符串叶子迭代器。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for child_value in value.values():
            yield from _leaf_strings(child_value)
        return
    if isinstance(value, list):
        for child_value in value:
            yield from _leaf_strings(child_value)


def _canonical_metadata(payload: dict[str, JsonValue]) -> tuple[int, str]:
    """按 helper 约定计算 canonical byte size 与 digest。

    :param payload: JSON object。
    :returns: ``(byte_size, sha256_digest)``。
    :raises Exception: 不主动抛出异常。
    """

    canonical_text = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    canonical_bytes = canonical_text.encode("utf-8")
    return len(canonical_bytes), hashlib.sha256(canonical_bytes).hexdigest()


def test_provider_error_diagnostic_payload_structure_and_digest() -> None:
    """provider error 摘要包含稳定结构与 canonical 元数据。"""

    payload: dict[str, JsonValue] = {
        "id": "chatcmpl_1",
        "error": {
            "code": "context_length_exceeded",
            "type": "invalid_request_error",
            "param": "messages",
            "message": "too long",
        },
    }

    diagnostic = provider_error_diagnostic_payload(payload, source=_SOURCE)

    assert isinstance(diagnostic, dict)
    expected_size, expected_digest = _canonical_metadata(payload)
    assert diagnostic[_VERSION_FIELD] == 1
    assert diagnostic[_SOURCE_FIELD] == _SOURCE
    assert diagnostic[_KIND_FIELD] == "provider_error"
    assert diagnostic[_CANONICAL_BYTE_SIZE_FIELD] == expected_size
    assert diagnostic[_SHA256_DIGEST_FIELD] == expected_digest
    assert diagnostic[_PROVIDER_ERROR_FIELD] == {
        "code": "context_length_exceeded",
        "type": "invalid_request_error",
        "param": "messages",
    }
    assert _serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES


def test_diagnostic_payload_redacts_sensitive_values() -> None:
    """敏感 key 的值不得进入诊断摘要。"""

    payload: dict[str, JsonValue] = {
        "api_key": "sk-secret-api-key",
        "client_secret": "client-secret-value",
        "access_token": "token-value",
        "user_password": "password-value",
        "Authorization": "Bearer auth-value",
        "credential_id": "credential-value",
        "error": {
            "code": "bad_request",
            "type": "invalid_request_error",
        },
    }

    diagnostic = provider_error_diagnostic_payload(payload, source=_SOURCE)

    assert isinstance(diagnostic, dict)
    leaves = tuple(_leaf_strings(diagnostic))
    forbidden_values = (
        "sk-secret-api-key",
        "client-secret-value",
        "token-value",
        "password-value",
        "Bearer auth-value",
        "credential-value",
    )
    for forbidden_value in forbidden_values:
        assert forbidden_value not in leaves


def test_large_payload_falls_back_to_minimal_structure() -> None:
    """超大诊断摘要按固定顺序回退到最小结构。"""

    payload: dict[str, JsonValue] = {
        f"key_{index}_{'x' * 512}": "value"
        for index in range(32)
    }
    payload["error"] = {
        "code": "bad_request",
        "type": "invalid_request_error",
    }

    diagnostic = provider_error_diagnostic_payload(payload, source=_SOURCE)

    assert isinstance(diagnostic, dict)
    assert _serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES
    assert set(diagnostic.keys()) == {
        _VERSION_FIELD,
        _SOURCE_FIELD,
        _KIND_FIELD,
        _CANONICAL_BYTE_SIZE_FIELD,
        _SHA256_DIGEST_FIELD,
    }
    assert _TOP_LEVEL_KEYS_FIELD not in diagnostic
    assert _PREVIEW_FIELD not in diagnostic


def test_protocol_object_diagnostic_payload_records_reason() -> None:
    """通用协议对象错误摘要必须记录 reason。"""

    payload: dict[str, JsonValue] = {"id": "chunk_1", "choices": []}

    diagnostic = protocol_object_diagnostic_payload(
        payload,
        source=_SOURCE,
        reason=_REASON,
    )

    assert isinstance(diagnostic, dict)
    assert diagnostic["reason"] == _REASON
    assert diagnostic[_SOURCE_FIELD] == _SOURCE
    assert diagnostic[_KIND_FIELD] == "protocol_object"
    assert _serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES


def test_protocol_object_diagnostic_payload_redacts_sensitive_values() -> None:
    """通用协议对象错误摘要不得泄漏敏感字段值。"""

    payload: dict[str, JsonValue] = {
        "id": "chunk_1",
        "authorization": "Bearer protocol-secret",
        "metadata": {
            "token": "nested-token-value",
        },
        "choices": [],
    }

    diagnostic = protocol_object_diagnostic_payload(
        payload,
        source=_SOURCE,
        reason=_REASON,
    )

    assert isinstance(diagnostic, dict)
    leaves = tuple(_leaf_strings(diagnostic))
    assert "Bearer protocol-secret" not in leaves
    assert "nested-token-value" not in leaves


def test_invalid_utf8_diagnostic_payload_is_bounded() -> None:
    """非法 UTF-8 摘要只保留 chunk 大小、摘要与有界前缀。"""

    chunk = b"\xff" * (_DIAGNOSTIC_PAYLOAD_MAX_BYTES * 2)

    diagnostic = invalid_utf8_diagnostic_payload(chunk, final_decode=False)

    assert isinstance(diagnostic, dict)
    assert diagnostic[_KIND_FIELD] == "invalid_utf8"
    assert diagnostic[_CANONICAL_BYTE_SIZE_FIELD] == len(chunk)
    assert diagnostic[_SHA256_DIGEST_FIELD] == hashlib.sha256(chunk).hexdigest()
    assert diagnostic["chunk_byte_size"] == len(chunk)
    assert diagnostic["chunk_sha256_digest"] == hashlib.sha256(chunk).hexdigest()
    assert "chunk_prefix_base64" in diagnostic
    assert diagnostic["final_decode"] is False
    assert _serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES


def test_invalid_utf8_diagnostic_payload_final_decode_empty_chunk() -> None:
    """流尾 UTF-8 flush 失败的空 chunk 摘要必须保留 final_decode 事实。"""

    chunk = b""

    diagnostic = invalid_utf8_diagnostic_payload(chunk, final_decode=True)

    assert isinstance(diagnostic, dict)
    expected_digest = hashlib.sha256(chunk).hexdigest()
    assert diagnostic[_CANONICAL_BYTE_SIZE_FIELD] == 0
    assert diagnostic[_SHA256_DIGEST_FIELD] == expected_digest
    assert diagnostic["chunk_byte_size"] == 0
    assert diagnostic["chunk_sha256_digest"] == expected_digest
    assert diagnostic["chunk_prefix_base64"] == ""
    assert diagnostic["final_decode"] is True
