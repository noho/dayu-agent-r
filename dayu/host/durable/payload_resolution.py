"""Host durable JSON payload descriptor 的完整性解析 owner。

本模块在调用方当前 transaction 中统一校验 descriptor、SQLite payload row
或本地 artifact 与实际 canonical JSON bytes。所有 JSON descriptor consumer
必须复用该边界，不能各自只比较部分 digest 或 size 字段。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.artifact import LocalArtifactRef, read_artifact_bytes
from dayu.host.durable.codec import (
    canonical_json_dumps,
    is_sha256_digest,
    sha256_digest_bytes,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.payload import (
    PayloadDescriptor,
    PayloadKind,
    SQLitePayloadFormat,
    read_payload_descriptor,
)
from dayu.host.durable.schema import TABLE_SQLITE_PAYLOADS
from dayu.host.durable.transaction import HostRow, HostTransaction


@dataclass(frozen=True, slots=True)
class ResolvedJsonPayload:
    """已完成 descriptor/content 完整性校验的 JSON object。

    :param descriptor: 已校验 payload descriptor。
    :param payload: 从 canonical bytes 解析出的 JSON object。
    """

    descriptor: PayloadDescriptor
    payload: Mapping[str, JsonValue]


def resolve_json_payload(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    expected_digest: str,
) -> ResolvedJsonPayload:
    """解析并完整校验 durable JSON payload descriptor。

    SQLite payload 同时校验 requested ref、caller/descriptor/row digest、
    descriptor/row/实际 size、row identity/format 与 canonical JSON bytes。
    artifact payload 复用 containment-guarded reader 校验 path、digest 与 size，
    并继续校验 UTF-8 与 canonical JSON object。

    :param transaction: 调用方当前 Host durable transaction。
    :param payload_ref: 调用方持有的 descriptor ref。
    :param expected_digest: 调用方持有的标准 Host sha256 digest。
    :returns: 已校验 descriptor 与 JSON object。
    :raises HostDurableError: ref、digest、size、identity、format、artifact 或 JSON
        canonicality 任一不一致时抛出。
    """

    _require_non_empty_text(payload_ref, field_name="payload_ref")
    _require_digest(expected_digest, field_name="expected_digest")
    descriptor = read_payload_descriptor(transaction, payload_ref)
    if descriptor is None:
        raise HostDurableError("JSON payload descriptor is missing")
    _validate_descriptor_identity(
        descriptor,
        payload_ref=payload_ref,
        expected_digest=expected_digest,
    )
    if descriptor.payload_kind is PayloadKind.SQLITE_PAYLOAD:
        payload_bytes = _read_verified_sqlite_json_bytes(transaction, descriptor)
    elif descriptor.payload_kind is PayloadKind.ARTIFACT_REF:
        payload_bytes = _read_verified_artifact_json_bytes(transaction, descriptor)
    else:
        raise HostDurableError("JSON payload descriptor kind is unsupported")
    payload = _canonical_json_object_from_bytes(payload_bytes)
    return ResolvedJsonPayload(descriptor=descriptor, payload=payload)


def _validate_descriptor_identity(
    descriptor: PayloadDescriptor,
    *,
    payload_ref: str,
    expected_digest: str,
) -> None:
    """校验 descriptor 与调用方 ref/digest 身份一致。

    :param descriptor: durable descriptor row。
    :param payload_ref: 调用方请求 ref。
    :param expected_digest: 调用方预期 digest。
    :returns: ``None``。
    :raises HostDurableError: ref、digest、size 或 kind-specific identity 非法时抛出。
    """

    if descriptor.payload_ref != payload_ref:
        raise HostDurableError("JSON payload descriptor ref mismatch")
    _require_digest(descriptor.payload_digest, field_name="descriptor.payload_digest")
    if descriptor.payload_digest != expected_digest:
        raise HostDurableError("JSON payload descriptor digest mismatch")
    _require_non_negative_int(
        descriptor.payload_size_bytes,
        field_name="descriptor.payload_size_bytes",
    )
    if descriptor.payload_kind is PayloadKind.SQLITE_PAYLOAD:
        if descriptor.sqlite_payload_id is None:
            raise HostDurableError("JSON sqlite payload id is missing")
        if descriptor.artifact_relative_path is not None:
            raise HostDurableError("JSON sqlite descriptor carries artifact path")
    elif descriptor.payload_kind is PayloadKind.ARTIFACT_REF:
        if descriptor.artifact_relative_path is None:
            raise HostDurableError("JSON artifact path is missing")
        if descriptor.sqlite_payload_id is not None:
            raise HostDurableError("JSON artifact descriptor carries sqlite payload id")


def _read_verified_sqlite_json_bytes(
    transaction: HostTransaction,
    descriptor: PayloadDescriptor,
) -> bytes:
    """读取并校验 SQLite canonical JSON row bytes。

    :param transaction: 调用方当前 transaction。
    :param descriptor: 已校验 SQLite payload descriptor。
    :returns: canonical JSON UTF-8 bytes。
    :raises HostDurableError: row 缺失或 identity/format/digest/size 不一致时抛出。
    """

    payload_id = descriptor.sqlite_payload_id
    if payload_id is None:
        raise HostDurableError("JSON sqlite payload id is missing")
    row = transaction.fetchone(
        f"""
        SELECT
          payload_id,
          payload_format,
          payload_json,
          payload_bytes,
          payload_size_bytes,
          payload_digest
        FROM {TABLE_SQLITE_PAYLOADS}
        WHERE payload_id = ?
        """,
        (payload_id,),
    )
    if row is None:
        raise HostDurableError("JSON sqlite payload row is missing")
    _validate_sqlite_row_identity(row, descriptor=descriptor, payload_id=payload_id)
    payload_json = row.get("payload_json")
    if not isinstance(payload_json, str):
        raise HostDurableError("JSON sqlite payload text is invalid")
    if row.get("payload_bytes") is not None:
        raise HostDurableError("JSON sqlite payload unexpectedly carries bytes")
    payload_bytes = payload_json.encode("utf-8")
    _validate_actual_bytes(
        payload_bytes,
        expected_digest=descriptor.payload_digest,
        expected_size_bytes=descriptor.payload_size_bytes,
    )
    return payload_bytes


def _validate_sqlite_row_identity(
    row: HostRow,
    *,
    descriptor: PayloadDescriptor,
    payload_id: str,
) -> None:
    """校验 SQLite payload row 与 descriptor 的同源 identity。

    :param row: SQLite payload row。
    :param descriptor: 对应 payload descriptor。
    :param payload_id: descriptor 声明的 SQLite payload id。
    :returns: ``None``。
    :raises HostDurableError: id、format、digest 或 size 不一致时抛出。
    """

    row_payload_id = _required_text(row, field_name="payload_id")
    if row_payload_id != payload_id:
        raise HostDurableError("JSON sqlite payload row id mismatch")
    payload_format = _required_text(row, field_name="payload_format")
    if payload_format != SQLitePayloadFormat.CANONICAL_JSON.value:
        raise HostDurableError("JSON sqlite payload format mismatch")
    row_digest = _required_text(row, field_name="payload_digest")
    _require_digest(row_digest, field_name="row.payload_digest")
    if row_digest != descriptor.payload_digest:
        raise HostDurableError("JSON sqlite row digest mismatch")
    row_size = _required_non_negative_int(row, field_name="payload_size_bytes")
    if row_size != descriptor.payload_size_bytes:
        raise HostDurableError("JSON sqlite row size mismatch")


def _read_verified_artifact_json_bytes(
    transaction: HostTransaction,
    descriptor: PayloadDescriptor,
) -> bytes:
    """读取 containment-guarded artifact JSON bytes。

    :param transaction: 调用方当前 transaction。
    :param descriptor: 已校验 artifact payload descriptor。
    :returns: 已校验 digest/size 的 artifact bytes。
    :raises HostDurableError: path 缺失、越界、文件缺失、digest 或 size 不一致时抛出。
    """

    artifact_relative_path = descriptor.artifact_relative_path
    if artifact_relative_path is None:
        raise HostDurableError("JSON artifact path is missing")
    content = read_artifact_bytes(
        transaction.artifact_root,
        LocalArtifactRef(
            artifact_relative_path=artifact_relative_path,
            artifact_digest=descriptor.payload_digest,
            artifact_size_bytes=descriptor.payload_size_bytes,
        ),
    )
    _validate_actual_bytes(
        content,
        expected_digest=descriptor.payload_digest,
        expected_size_bytes=descriptor.payload_size_bytes,
    )
    return content


def _validate_actual_bytes(
    content: bytes,
    *,
    expected_digest: str,
    expected_size_bytes: int,
) -> None:
    """校验实际 bytes 的 digest 与 size。

    :param content: 实际 payload bytes。
    :param expected_digest: descriptor/row 已声明 digest。
    :param expected_size_bytes: descriptor/row 已声明 size。
    :returns: ``None``。
    :raises HostDurableError: digest 或 size 不一致时抛出。
    """

    if len(content) != expected_size_bytes:
        raise HostDurableError("JSON payload canonical byte size mismatch")
    if sha256_digest_bytes(content) != expected_digest:
        raise HostDurableError("JSON payload canonical byte digest mismatch")


def _canonical_json_object_from_bytes(
    content: bytes,
) -> Mapping[str, JsonValue]:
    """解析并验证 canonical UTF-8 JSON object bytes。

    :param content: 已校验 digest/size 的 payload bytes。
    :returns: JSON object mapping。
    :raises HostDurableError: UTF-8、JSON、object shape 或 canonical encoding 非法时抛出。
    """

    try:
        payload_json = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HostDurableError("JSON payload is not UTF-8") from exc
    try:
        value = cast(JsonValue, json.loads(payload_json))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HostDurableError("JSON payload text is invalid") from exc
    if not isinstance(value, Mapping):
        raise HostDurableError("JSON payload must be object")
    payload = cast(Mapping[str, JsonValue], value)
    try:
        canonical_payload_json = canonical_json_dumps(payload)
    except (TypeError, ValueError) as exc:
        raise HostDurableError("JSON payload object is not canonicalizable") from exc
    if canonical_payload_json.encode("utf-8") != content:
        raise HostDurableError("JSON payload bytes are not canonical JSON")
    return payload


def _required_text(row: HostRow, *, field_name: str) -> str:
    """读取 Host row 必填非空文本。

    :param row: Host transaction row。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises HostDurableError: 字段缺失、非文本或为空时抛出。
    """

    value = row.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")
    return value


def _required_non_negative_int(row: HostRow, *, field_name: str) -> int:
    """读取 Host row 必填非负整数。

    :param row: Host transaction row。
    :param field_name: 字段名。
    :returns: 非负整数。
    :raises HostDurableError: 字段不是严格非负整数时抛出。
    """

    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"{field_name} must be non-negative integer")
    return value


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验必填非空文本。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 值非文本或为空时抛出。
    """

    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"{field_name} must be non-empty text")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验严格非负整数。

    :param value: 待校验整数。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 值不是严格非负整数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"{field_name} must be non-negative integer")


def _require_digest(value: str, *, field_name: str) -> None:
    """校验标准 Host sha256 digest。

    :param value: 待校验 digest。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: digest 格式非法时抛出。
    """

    if not isinstance(value, str) or not is_sha256_digest(value):
        raise HostDurableError(f"{field_name} must be sha256 digest")


__all__ = ["resolve_json_payload", "ResolvedJsonPayload"]
