"""Host durable payload descriptor 与 SQLite payload primitive。

本模块只实现 Phase 2 durable foundation 的 payload row、descriptor row 写入与
读取。它不访问 Fins 仓储、不实现 ToolRuntime、不创建 trace / cleanup 表，也不
解释 payload 的业务语义。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.artifact import LocalArtifactRef, validate_artifact_ref
from dayu.host.durable._validation import (
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_optional_sha256_digest as _require_optional_digest,
    require_text as _require_text,
)
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    sha256_digest_bytes,
)
from dayu.host.durable.errors import (
    HostDigestMismatchError,
    HostDurableError,
)
from dayu.host.durable.schema import (
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
)
from dayu.host.durable.transaction import HostRow, HostTransaction


class PayloadKind(StrEnum):
    """payload descriptor 类型。"""

    SQLITE_PAYLOAD = "sqlite_payload"
    ARTIFACT_REF = "artifact_ref"


class SQLitePayloadFormat(StrEnum):
    """SQLite payload 存储格式。"""

    CANONICAL_JSON = "canonical_json"
    BYTES = "bytes"


def _empty_metadata() -> Mapping[str, JsonValue]:
    """返回空 metadata JSON object。

    :returns: 空 metadata 映射。
    """

    return {}


@dataclass(frozen=True, slots=True, kw_only=True)
class SQLitePayloadWriteRequest:
    """SQLite payload 写入请求。

    :param payload_ref: descriptor 主键引用。
    :param payload_id: SQLite payload row 主键。
    :param payload_format: payload 存储格式。
    :param payload_json: ``canonical_json`` 格式时待写入的 JSON 值。
    :param payload_bytes: ``bytes`` 格式时待写入的原始 bytes。
    :param media_type: descriptor media type；未知时为 ``None``。
    :param metadata: descriptor metadata JSON object。
    :param expected_digest: 调用方预期 payload digest；无预期时为 ``None``。
    """

    payload_ref: str
    payload_id: str
    payload_format: SQLitePayloadFormat
    payload_json: JsonValue = None
    payload_bytes: bytes | None = None
    media_type: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=_empty_metadata)
    expected_digest: str | None = None


@dataclass(frozen=True, slots=True)
class PayloadDescriptor:
    """已持久化 payload descriptor。

    :param payload_ref: descriptor 主键引用。
    :param payload_kind: descriptor 类型。
    :param payload_digest: payload digest。
    :param payload_size_bytes: payload 原始字节长度。
    :param media_type: media type；未知时为 ``None``。
    :param sqlite_payload_id: SQLite payload row 引用。
    :param artifact_relative_path: artifact root 下的相对路径。
    :param metadata_json: canonical metadata JSON 文本。
    :param created_at: 固定 UTC 微秒精度 ``Z`` timestamp 文本。
    """

    payload_ref: str
    payload_kind: PayloadKind
    payload_digest: str
    payload_size_bytes: int
    media_type: str | None
    sqlite_payload_id: str | None
    artifact_relative_path: str | None
    metadata_json: str
    created_at: str


@dataclass(frozen=True, slots=True)
class _EncodedSQLitePayload:
    """SQLite payload 写入前的 canonical 编码结果。

    :param payload_json: canonical JSON 文本。
    :param payload_bytes: 原始 bytes。
    :param payload_size_bytes: payload 字节长度。
    :param payload_digest: payload digest。
    """

    payload_json: str | None
    payload_bytes: bytes | None
    payload_size_bytes: int
    payload_digest: str


class PayloadStore:
    """Payload primitive 的轻量方法集合。

    该类不持有连接、不创建 transaction；所有 mutation 都必须发生在调用方
    传入的 ``HostTransaction`` 中。
    """

    def write_sqlite_payload(
        self, transaction: HostTransaction, request: SQLitePayloadWriteRequest
    ) -> PayloadDescriptor:
        """写入 SQLite payload row 与 descriptor row。

        :param transaction: 调用方提供的 Host durable transaction。
        :param request: SQLite payload 写入请求。
        :returns: 已持久化 descriptor。
        :raises HostDurableError: 请求字段或 JSON 编码无效时抛出。
        :raises HostDigestMismatchError: ``expected_digest`` 与实际 digest 不一致时抛出。
        :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
        """

        return write_sqlite_payload(transaction, request)

    def write_payload_descriptor_for_artifact(
        self,
        transaction: HostTransaction,
        payload_ref: str,
        artifact_ref: LocalArtifactRef,
        media_type: str | None,
        metadata: Mapping[str, JsonValue],
    ) -> PayloadDescriptor:
        """为已发布 artifact 写入 payload descriptor。

        :param transaction: 调用方提供的 Host durable transaction。
        :param payload_ref: descriptor 主键引用。
        :param artifact_ref: 已发布且校验过 digest 的本地 artifact 引用。
        :param media_type: media type；未知时为 ``None``。
        :param metadata: descriptor metadata JSON object。
        :returns: 已持久化 descriptor。
        :raises HostDurableError: descriptor 字段或 metadata 编码无效时抛出。
        :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
        """

        return write_payload_descriptor_for_artifact(
            transaction, payload_ref, artifact_ref, media_type, metadata
        )

    def read_payload_descriptor(
        self, transaction: HostTransaction, payload_ref: str
    ) -> PayloadDescriptor | None:
        """读取 payload descriptor。

        :param transaction: 调用方提供的 Host durable transaction。
        :param payload_ref: descriptor 主键引用。
        :returns: 找到时返回 descriptor，否则返回 ``None``。
        :raises HostDurableError: ``payload_ref`` 为空时抛出。
        """

        return read_payload_descriptor(transaction, payload_ref)


def write_sqlite_payload(
    transaction: HostTransaction, request: SQLitePayloadWriteRequest
) -> PayloadDescriptor:
    """在调用方 transaction 内写入 SQLite payload row 与 descriptor row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param request: SQLite payload 写入请求。
    :returns: 已持久化 descriptor。
    :raises HostDurableError: 请求字段或 JSON 编码无效时抛出。
    :raises HostDigestMismatchError: ``expected_digest`` 与实际 digest 不一致时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_sqlite_payload_request(request)
    encoded = _encode_sqlite_payload(request)
    _validate_expected_digest(
        encoded.payload_digest,
        request.expected_digest,
        field_name="expected_digest",
    )
    created_at = format_utc_timestamp(datetime.now(UTC))
    transaction.execute(
        f"""
        INSERT INTO {TABLE_SQLITE_PAYLOADS} (
          payload_id,
          payload_format,
          payload_json,
          payload_bytes,
          payload_size_bytes,
          payload_digest,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request.payload_id,
            request.payload_format.value,
            encoded.payload_json,
            encoded.payload_bytes,
            encoded.payload_size_bytes,
            encoded.payload_digest,
            created_at,
        ),
    )
    _insert_payload_descriptor(
        transaction,
        payload_ref=request.payload_ref,
        payload_kind=PayloadKind.SQLITE_PAYLOAD,
        payload_digest=encoded.payload_digest,
        payload_size_bytes=encoded.payload_size_bytes,
        media_type=request.media_type,
        sqlite_payload_id=request.payload_id,
        artifact_relative_path=None,
        metadata=request.metadata,
        created_at=created_at,
    )
    descriptor = read_payload_descriptor(transaction, request.payload_ref)
    if descriptor is None:
        raise HostDurableError("Payload descriptor insert did not return inserted row")
    return descriptor


def write_payload_descriptor_for_artifact(
    transaction: HostTransaction,
    payload_ref: str,
    artifact_ref: LocalArtifactRef,
    media_type: str | None,
    metadata: Mapping[str, JsonValue],
) -> PayloadDescriptor:
    """在调用方 transaction 内为已发布 artifact 写入 descriptor。

    :param transaction: 调用方提供的 Host durable transaction。
    :param payload_ref: descriptor 主键引用。
    :param artifact_ref: 已发布且校验过 digest 的本地 artifact 引用。
    :param media_type: media type；未知时为 ``None``。
    :param metadata: descriptor metadata JSON object。
    :returns: 已持久化 descriptor。
    :raises HostDurableError: descriptor 字段或 metadata 编码无效时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _require_non_empty_text(payload_ref, field_name="payload_ref")
    _require_optional_non_empty_text(media_type, field_name="media_type")
    validate_artifact_ref(artifact_ref)
    created_at = format_utc_timestamp(datetime.now(UTC))
    _insert_payload_descriptor(
        transaction,
        payload_ref=payload_ref,
        payload_kind=PayloadKind.ARTIFACT_REF,
        payload_digest=artifact_ref.artifact_digest,
        payload_size_bytes=artifact_ref.artifact_size_bytes,
        media_type=media_type,
        sqlite_payload_id=None,
        artifact_relative_path=artifact_ref.artifact_relative_path,
        metadata=metadata,
        created_at=created_at,
    )
    descriptor = read_payload_descriptor(transaction, payload_ref)
    if descriptor is None:
        raise HostDurableError("Payload descriptor insert did not return inserted row")
    return descriptor


def read_payload_descriptor(
    transaction: HostTransaction, payload_ref: str
) -> PayloadDescriptor | None:
    """按 ``payload_ref`` 读取 payload descriptor。

    :param transaction: 调用方提供的 Host durable transaction。
    :param payload_ref: descriptor 主键引用。
    :returns: 找到时返回 descriptor，否则返回 ``None``。
    :raises HostDurableError: ``payload_ref`` 为空时抛出。
    """

    _require_non_empty_text(payload_ref, field_name="payload_ref")
    row = transaction.fetchone(
        f"""
        SELECT
          payload_ref,
          payload_kind,
          payload_digest,
          payload_size_bytes,
          media_type,
          sqlite_payload_id,
          artifact_relative_path,
          metadata_json,
          created_at
        FROM {TABLE_PAYLOAD_DESCRIPTORS}
        WHERE payload_ref = ?
        """,
        (payload_ref,),
    )
    if row is None:
        return None
    return _payload_descriptor_from_host_row(row)


def _insert_payload_descriptor(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    payload_kind: PayloadKind,
    payload_digest: str,
    payload_size_bytes: int,
    media_type: str | None,
    sqlite_payload_id: str | None,
    artifact_relative_path: str | None,
    metadata: Mapping[str, JsonValue],
    created_at: str,
) -> None:
    """插入 payload descriptor row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param payload_ref: descriptor 主键引用。
    :param payload_kind: descriptor 类型。
    :param payload_digest: payload digest。
    :param payload_size_bytes: payload 原始字节长度。
    :param media_type: media type；未知时为 ``None``。
    :param sqlite_payload_id: SQLite payload row 引用。
    :param artifact_relative_path: artifact root 下的相对路径。
    :param metadata: metadata JSON object。
    :param created_at: descriptor 创建时间。
    :returns: ``None``。
    :raises HostDurableError: metadata JSON 编码失败时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    try:
        metadata_json = canonical_json_dumps(metadata)
    except (TypeError, ValueError) as exc:
        raise HostDurableError("Payload descriptor metadata encoding failed") from exc
    transaction.execute(
        f"""
        INSERT INTO {TABLE_PAYLOAD_DESCRIPTORS} (
          payload_ref,
          payload_kind,
          payload_digest,
          payload_size_bytes,
          media_type,
          sqlite_payload_id,
          artifact_relative_path,
          metadata_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload_ref,
            payload_kind.value,
            payload_digest,
            payload_size_bytes,
            media_type,
            sqlite_payload_id,
            artifact_relative_path,
            metadata_json,
            created_at,
        ),
    )


def _validate_sqlite_payload_request(request: SQLitePayloadWriteRequest) -> None:
    """校验 SQLite payload 写入请求。

    :param request: SQLite payload 写入请求。
    :returns: ``None``。
    :raises HostDurableError: 字段无效时抛出。
    """

    _require_non_empty_text(request.payload_ref, field_name="payload_ref")
    _require_non_empty_text(request.payload_id, field_name="payload_id")
    if not isinstance(request.payload_format, SQLitePayloadFormat):
        raise HostDurableError("SQLite payload format is invalid")
    _require_optional_non_empty_text(request.media_type, field_name="media_type")
    _require_optional_digest(request.expected_digest, field_name="expected_digest")
    if (
        request.payload_format is SQLitePayloadFormat.CANONICAL_JSON
        and request.payload_bytes is not None
    ):
        raise HostDurableError("canonical_json payload must not include payload_bytes")
    if (
        request.payload_format is SQLitePayloadFormat.BYTES
        and request.payload_bytes is None
    ):
        raise HostDurableError("bytes payload must include payload_bytes")
    if (
        request.payload_format is SQLitePayloadFormat.BYTES
        and request.payload_json is not None
    ):
        raise HostDurableError("bytes payload must not include payload_json")


def _encode_sqlite_payload(
    request: SQLitePayloadWriteRequest,
) -> _EncodedSQLitePayload:
    """编码 SQLite payload 并计算 digest。

    :param request: SQLite payload 写入请求。
    :returns: canonical 编码结果。
    :raises HostDurableError: JSON 编码失败时抛出。
    """

    if request.payload_format is SQLitePayloadFormat.CANONICAL_JSON:
        try:
            payload_json = canonical_json_dumps(request.payload_json)
        except (TypeError, ValueError) as exc:
            raise HostDurableError("SQLite payload JSON encoding failed") from exc
        payload_bytes = payload_json.encode("utf-8")
        return _EncodedSQLitePayload(
            payload_json=payload_json,
            payload_bytes=None,
            payload_size_bytes=len(payload_bytes),
            payload_digest=sha256_digest_bytes(payload_bytes),
        )
    if request.payload_bytes is None:
        raise HostDurableError("bytes payload must include payload_bytes")
    return _EncodedSQLitePayload(
        payload_json=None,
        payload_bytes=request.payload_bytes,
        payload_size_bytes=len(request.payload_bytes),
        payload_digest=sha256_digest_bytes(request.payload_bytes),
    )


def _validate_expected_digest(
    actual_digest: str, expected_digest: str | None, *, field_name: str
) -> None:
    """校验调用方预期 digest。

    :param actual_digest: 实际 digest。
    :param expected_digest: 预期 digest；无预期时为 ``None``。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDigestMismatchError: 预期 digest 与实际 digest 不一致时抛出。
    :raises HostDurableError: 预期 digest 格式无效时抛出。
    """

    _require_optional_digest(expected_digest, field_name=field_name)
    if expected_digest is not None and expected_digest != actual_digest:
        raise HostDigestMismatchError("Payload digest does not match expected digest")


def _payload_descriptor_from_host_row(row: HostRow) -> PayloadDescriptor:
    """把通用 HostRow 转换为 PayloadDescriptor。

    :param row: HostTransaction 查询返回的 row。
    :returns: PayloadDescriptor。
    :raises HostDurableError: durable row 类型或 enum 值不符合 schema 预期时抛出。
    """

    payload_kind_text = _require_text(row.get("payload_kind"), field_name="payload_kind")
    try:
        payload_kind = PayloadKind(payload_kind_text)
    except ValueError as exc:
        raise HostDurableError("Payload descriptor row has invalid payload_kind") from exc
    return PayloadDescriptor(
        payload_ref=_require_text(row.get("payload_ref"), field_name="payload_ref"),
        payload_kind=payload_kind,
        payload_digest=_require_text(
            row.get("payload_digest"), field_name="payload_digest"
        ),
        payload_size_bytes=_require_int(
            row.get("payload_size_bytes"), field_name="payload_size_bytes"
        ),
        media_type=_optional_text(row.get("media_type"), field_name="media_type"),
        sqlite_payload_id=_optional_text(
            row.get("sqlite_payload_id"), field_name="sqlite_payload_id"
        ),
        artifact_relative_path=_optional_text(
            row.get("artifact_relative_path"), field_name="artifact_relative_path"
        ),
        metadata_json=_require_text(
            row.get("metadata_json"), field_name="metadata_json"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
    )
