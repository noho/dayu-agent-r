"""Host durable JSON payload descriptor/content 完整性 owner 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_bytes
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    BoundedJsonPayloadWriteRequest,
    PayloadDescriptor,
    PayloadKind,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
    write_bounded_json_payload,
    write_sqlite_payload,
)
from dayu.host.durable.payload_resolution import resolve_json_payload
from dayu.host.durable.schema import (
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
)
from dayu.host.durable.transaction import HostTransaction


class _SQLiteTamperKind(StrEnum):
    """SQLite payload tamper matrix 的封闭测试分类。"""

    PAYLOAD_JSON = "payload_json"
    ROW_DIGEST = "row_digest"
    ROW_SIZE = "row_size"
    DESCRIPTOR_DIGEST = "descriptor_digest"
    DESCRIPTOR_SIZE = "descriptor_size"
    DESCRIPTOR_REF = "descriptor_ref"
    SQLITE_PAYLOAD_ID = "sqlite_payload_id"


class _ArtifactTamperKind(StrEnum):
    """artifact-backed payload tamper matrix 的封闭测试分类。"""

    CONTAINMENT = "containment"
    DIGEST = "digest"
    SIZE = "size"


def _options(
    tmp_path: Path,
    *,
    payload_inline_threshold_bytes: int = 65536,
) -> HostDurableStoreOptions:
    """构造 durable payload integrity 测试 options。

    :param tmp_path: pytest 临时目录。
    :param payload_inline_threshold_bytes: SQLite/artifact 冷热分界。
    :returns: Host durable store options。
    :raises ValueError: 阈值非法时由 production policy 抛出。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts",
            payload_inline_threshold_bytes=payload_inline_threshold_bytes,
        ),
        sqlite_policy=HostSQLiteStoragePolicy(),
    )


def _write_sqlite_object(
    transaction: HostTransaction,
    *,
    payload_ref: str = "payload-integrity",
    payload_id: str = "sqlite-payload-integrity",
    payload: Mapping[str, JsonValue] | None = None,
) -> PayloadDescriptor:
    """写入测试用 SQLite canonical JSON object。

    :param transaction: 当前 Host write transaction。
    :param payload_ref: descriptor ref。
    :param payload_id: SQLite payload id。
    :param payload: JSON object；``None`` 时使用标准 payload。
    :returns: 已持久化 descriptor。
    :raises HostDurableError: 写入请求非法时由 production owner 抛出。
    """

    actual_payload: Mapping[str, JsonValue] = (
        {"value": "verified", "count": 2} if payload is None else payload
    )
    return write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=payload_id,
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=actual_payload,
            media_type="application/json",
            metadata={},
        ),
    )


def _tamper_sqlite_payload(
    transaction: HostTransaction,
    *,
    descriptor: PayloadDescriptor,
    tamper_kind: _SQLiteTamperKind,
) -> None:
    """对 SQLite row/descriptor 的单一 integrity atom 注入篡改。

    :param transaction: 当前 Host write transaction。
    :param descriptor: 目标 descriptor。
    :param tamper_kind: 篡改分类。
    :returns: ``None``。
    :raises AssertionError: descriptor 不是 SQLite payload 时抛出。
    :raises HostDurableError: secondary payload 写入失败时由 production owner 抛出。
    """

    payload_id = descriptor.sqlite_payload_id
    if payload_id is None:
        raise AssertionError("sqlite payload id must exist")
    wrong_digest = sha256_digest_bytes(b"tampered")
    if tamper_kind is _SQLiteTamperKind.PAYLOAD_JSON:
        transaction.execute(
            f"UPDATE {TABLE_SQLITE_PAYLOADS} SET payload_json = ? WHERE payload_id = ?",
            (canonical_json_dumps({"value": "tampered"}), payload_id),
        )
        return
    if tamper_kind is _SQLiteTamperKind.ROW_DIGEST:
        transaction.execute(
            f"UPDATE {TABLE_SQLITE_PAYLOADS} SET payload_digest = ? WHERE payload_id = ?",
            (wrong_digest, payload_id),
        )
        return
    if tamper_kind is _SQLiteTamperKind.ROW_SIZE:
        transaction.execute(
            f"UPDATE {TABLE_SQLITE_PAYLOADS} SET payload_size_bytes = payload_size_bytes + 1 WHERE payload_id = ?",
            (payload_id,),
        )
        return
    if tamper_kind is _SQLiteTamperKind.DESCRIPTOR_DIGEST:
        transaction.execute(
            f"UPDATE {TABLE_PAYLOAD_DESCRIPTORS} SET payload_digest = ? WHERE payload_ref = ?",
            (wrong_digest, descriptor.payload_ref),
        )
        return
    if tamper_kind is _SQLiteTamperKind.DESCRIPTOR_SIZE:
        transaction.execute(
            f"UPDATE {TABLE_PAYLOAD_DESCRIPTORS} SET payload_size_bytes = payload_size_bytes + 1 WHERE payload_ref = ?",
            (descriptor.payload_ref,),
        )
        return
    if tamper_kind is _SQLiteTamperKind.DESCRIPTOR_REF:
        transaction.execute(
            f"UPDATE {TABLE_PAYLOAD_DESCRIPTORS} SET payload_ref = ? WHERE payload_ref = ?",
            ("payload-integrity-moved", descriptor.payload_ref),
        )
        return
    secondary = _write_sqlite_object(
        transaction,
        payload_ref="payload-integrity-secondary",
        payload_id="sqlite-payload-integrity-secondary",
        payload={"value": "different"},
    )
    if secondary.sqlite_payload_id is None:
        raise AssertionError("secondary sqlite payload id must exist")
    transaction.execute(
        f"UPDATE {TABLE_PAYLOAD_DESCRIPTORS} SET sqlite_payload_id = ? WHERE payload_ref = ?",
        (secondary.sqlite_payload_id, descriptor.payload_ref),
    )


def _rewrite_noncanonical_json_with_consistent_metadata(
    transaction: HostTransaction,
    *,
    descriptor: PayloadDescriptor,
) -> str:
    """写入语义有效但非 canonical 的 JSON，并同步全部 digest/size metadata。

    :param transaction: 当前 Host write transaction。
    :param descriptor: 目标 SQLite descriptor。
    :returns: 非 canonical bytes digest，供 caller digest 使用。
    :raises AssertionError: descriptor 没有 SQLite payload id 时抛出。
    """

    payload_id = descriptor.sqlite_payload_id
    if payload_id is None:
        raise AssertionError("sqlite payload id must exist")
    payload_json = '{"b": 2, "a": 1}'
    payload_bytes = payload_json.encode("utf-8")
    payload_digest = sha256_digest_bytes(payload_bytes)
    payload_size_bytes = len(payload_bytes)
    transaction.execute(
        f"""
        UPDATE {TABLE_SQLITE_PAYLOADS}
        SET payload_json = ?, payload_size_bytes = ?, payload_digest = ?
        WHERE payload_id = ?
        """,
        (payload_json, payload_size_bytes, payload_digest, payload_id),
    )
    transaction.execute(
        f"""
        UPDATE {TABLE_PAYLOAD_DESCRIPTORS}
        SET payload_size_bytes = ?, payload_digest = ?
        WHERE payload_ref = ?
        """,
        (payload_size_bytes, payload_digest, descriptor.payload_ref),
    )
    return payload_digest


def test_sqlite_json_payload_integrity_owner_accepts_valid_object(
    tmp_path: Path,
) -> None:
    """共享 resolver 接受 ref/digest/row/bytes 全部同源的 SQLite object。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolver 未返回同源 descriptor 或 payload 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(_write_sqlite_object)
        resolved = store.transaction_runner.run_read(
            lambda transaction: resolve_json_payload(
                transaction,
                payload_ref=descriptor.payload_ref,
                expected_digest=descriptor.payload_digest,
            )
        )
        assert resolved.descriptor == descriptor
        assert resolved.payload == {"value": "verified", "count": 2}


@pytest.mark.parametrize("tamper_kind", tuple(_SQLiteTamperKind))
def test_sqlite_json_payload_integrity_owner_rejects_each_split_atom(
    tmp_path: Path,
    tamper_kind: _SQLiteTamperKind,
) -> None:
    """caller/descriptor/row/content identity 任一分裂均 fail closed。

    :param tmp_path: pytest 临时目录。
    :param tamper_kind: 单一 tamper 分类。
    :returns: ``None``。
    :raises AssertionError: 任一损坏 payload 被接受时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(_write_sqlite_object)
        store.transaction_runner.run_write(
            lambda transaction: _tamper_sqlite_payload(
                transaction,
                descriptor=descriptor,
                tamper_kind=tamper_kind,
            )
        )
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_read(
                lambda transaction: resolve_json_payload(
                    transaction,
                    payload_ref=descriptor.payload_ref,
                    expected_digest=descriptor.payload_digest,
                )
            )


def test_sqlite_json_payload_rejects_noncanonical_bytes_even_if_metadata_matches(
    tmp_path: Path,
) -> None:
    """row/descriptor/caller 全部跟随篡改时仍拒绝非 canonical JSON bytes。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 非 canonical bytes 未触发 durable error 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(_write_sqlite_object)
        tampered_digest = store.transaction_runner.run_write(
            lambda transaction: _rewrite_noncanonical_json_with_consistent_metadata(
                transaction,
                descriptor=descriptor,
            )
        )
        with pytest.raises(HostDurableError, match="not canonical JSON"):
            store.transaction_runner.run_read(
                lambda transaction: resolve_json_payload(
                    transaction,
                    payload_ref=descriptor.payload_ref,
                    expected_digest=tampered_digest,
                )
            )


def test_sqlite_json_payload_rejects_non_object_canonical_json(
    tmp_path: Path,
) -> None:
    """descriptor 内容即使 canonical 且 digest 自洽，也必须是 JSON object。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: canonical JSON list 被当作 object 接受时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(
            lambda transaction: write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-list",
                    payload_id="sqlite-payload-list",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json=["not", "object"],
                ),
            )
        )
        with pytest.raises(HostDurableError, match="must be object"):
            store.transaction_runner.run_read(
                lambda transaction: resolve_json_payload(
                    transaction,
                    payload_ref=descriptor.payload_ref,
                    expected_digest=descriptor.payload_digest,
                )
            )


@pytest.mark.parametrize("tamper_kind", tuple(_ArtifactTamperKind))
def test_artifact_json_payload_verifies_containment_digest_and_size(
    tmp_path: Path,
    tamper_kind: _ArtifactTamperKind,
) -> None:
    """artifact-backed JSON 先成功解析，物理 bytes 篡改后 fail closed。

    :param tmp_path: pytest 临时目录。
    :param tamper_kind: containment、实际 digest 或实际 size 篡改分类。
    :returns: ``None``。
    :raises AssertionError: artifact identity/内容断言或篡改拒绝不成立时抛出。
    """

    with open_host_durable_store(
        _options(tmp_path, payload_inline_threshold_bytes=1)
    ) as store:
        descriptor = store.transaction_runner.run_write(
            lambda transaction: write_bounded_json_payload(
                transaction,
                BoundedJsonPayloadWriteRequest(
                    payload_ref="payload-artifact-integrity",
                    sqlite_payload_id="sqlite-artifact-integrity-unused",
                    payload_json={"artifact": "verified"},
                    media_type="application/json",
                    metadata={},
                ),
            )
        )
        assert descriptor.payload_kind is PayloadKind.ARTIFACT_REF
        resolved = store.transaction_runner.run_read(
            lambda transaction: resolve_json_payload(
                transaction,
                payload_ref=descriptor.payload_ref,
                expected_digest=descriptor.payload_digest,
            )
        )
        assert resolved.payload == {"artifact": "verified"}
        if descriptor.artifact_relative_path is None:
            raise AssertionError("artifact path must exist")
        if tamper_kind is _ArtifactTamperKind.CONTAINMENT:
            store.transaction_runner.run_write(
                lambda transaction: transaction.execute(
                    f"""
                    UPDATE {TABLE_PAYLOAD_DESCRIPTORS}
                    SET artifact_relative_path = ?
                    WHERE payload_ref = ?
                    """,
                    ("../outside.json", descriptor.payload_ref),
                )
            )
        else:
            artifact_path = (
                store.options.payload_policy.artifact_root
                / descriptor.artifact_relative_path
            )
            tampered_size = descriptor.payload_size_bytes
            if tamper_kind is _ArtifactTamperKind.SIZE:
                tampered_size += 1
            artifact_path.write_bytes(b"x" * tampered_size)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_read(
                lambda transaction: resolve_json_payload(
                    transaction,
                    payload_ref=descriptor.payload_ref,
                    expected_digest=descriptor.payload_digest,
                )
            )


def test_json_payload_integrity_owner_rejects_caller_digest_split(
    tmp_path: Path,
) -> None:
    """caller digest 与 descriptor 分裂时在读取 content 前 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 错误 caller digest 未被拒绝时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(_write_sqlite_object)
        with pytest.raises(HostDurableError, match="descriptor digest mismatch"):
            store.transaction_runner.run_read(
                lambda transaction: resolve_json_payload(
                    transaction,
                    payload_ref=descriptor.payload_ref,
                    expected_digest=sha256_digest_bytes(b"wrong-caller-digest"),
                )
            )
