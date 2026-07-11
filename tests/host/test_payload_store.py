"""Host durable payload descriptor primitive 测试。"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_bytes
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.errors import (
    HostDigestMismatchError,
    HostDurableError,
    HostForeignKeyError,
    HostPayloadReferenceError,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadKind,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
    read_payload_descriptor,
    write_sqlite_payload,
)
from dayu.host.durable.schema import (
    PayloadDescriptorKind,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
    payload_descriptor_metadata,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.payload_resolution import event_payload_object


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.05,
            write_busy_retry_count=2,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.0,
            write_retry_max_delay_seconds=0.001,
        ),
    )


def _event_request(payload_ref: str, payload_digest: str) -> EventLogAppendRequest:
    """构造引用 payload descriptor 的 EventLog 请求。

    :param payload_ref: payload descriptor 引用。
    :param payload_digest: payload digest。
    :returns: EventLog append 请求。
    """

    return EventLogAppendRequest(
        event_id="event-with-payload",
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-1",
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        event_type="USER_INPUT_ACCEPTED",
        occurred_at=datetime(2026, 5, 14, 1, 2, 3, 123456, tzinfo=UTC),
        actor="host",
        source="payload-test",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={"ref": payload_ref},
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )


def _count_rows(transaction: HostTransaction, table_name: str) -> int:
    """读取表 row count。

    :param transaction: Host transaction。
    :param table_name: 表名。
    :returns: row count。
    :raises AssertionError: SQLite 未返回 count row 时抛出。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {table_name}")
    assert row is not None
    total = row.get("total")
    assert isinstance(total, int)
    return total


def test_default_payload_inline_threshold_can_be_overridden(tmp_path: Path) -> None:
    """payload inline threshold 默认值为 65536，且可通过 policy 覆盖。"""

    default_policy = PayloadStoragePolicy(artifact_root=tmp_path / "default")
    override_policy = PayloadStoragePolicy(
        artifact_root=tmp_path / "override",
        payload_inline_threshold_bytes=128,
    )

    assert default_policy.payload_inline_threshold_bytes == 65536
    assert override_policy.payload_inline_threshold_bytes == 128


def test_canonical_json_payload_writes_payload_and_descriptor(
    tmp_path: Path,
) -> None:
    """canonical JSON payload 会在一个 transaction 内写入 payload row 与 descriptor。"""

    payload_json = {"b": 2, "a": 1}
    expected_bytes = canonical_json_dumps(payload_json).encode("utf-8")
    expected_digest = sha256_digest_bytes(expected_bytes)
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[str, str, int, int]:
            """写入 JSON payload 并读取底层 row。

            :param transaction: Host transaction。
            :returns: descriptor digest、JSON 文本、payload row 数、descriptor row 数。
            """

            descriptor = write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-json",
                    payload_id="sqlite-json",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json=payload_json,
                    media_type="application/json",
                    metadata={"source": "test"},
                ),
            )
            row = transaction.fetchone(
                f"""
                SELECT payload_json, payload_digest
                FROM {TABLE_SQLITE_PAYLOADS}
                WHERE payload_id = ?
                """,
                ("sqlite-json",),
            )
            assert row is not None
            payload_text = row.get("payload_json")
            assert isinstance(payload_text, str)
            assert row.get("payload_digest") == expected_digest
            assert descriptor.payload_kind is PayloadKind.SQLITE_PAYLOAD
            assert descriptor.payload_ref == "payload-json"
            assert descriptor.sqlite_payload_id == "sqlite-json"
            assert descriptor.artifact_relative_path is None
            assert descriptor.payload_size_bytes == len(expected_bytes)
            assert descriptor.metadata_json == '{"source":"test"}'
            return (
                descriptor.payload_digest,
                payload_text,
                _count_rows(transaction, TABLE_SQLITE_PAYLOADS),
                _count_rows(transaction, TABLE_PAYLOAD_DESCRIPTORS),
            )

        assert store.transaction_runner.run_write(operation) == (
            expected_digest,
            '{"a":1,"b":2}',
            1,
            1,
        )


def test_descriptor_metadata_helper_rejects_descriptor_kind_override() -> None:
    """descriptor metadata helper 不允许调用方覆盖 owner 写入的 kind。"""

    with pytest.raises(
        HostDurableError, match="must not override descriptor_kind"
    ):
        payload_descriptor_metadata(
            PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON,
            {"descriptor_kind": "other"},
        )


def test_payload_descriptor_rejects_unknown_descriptor_kind_before_write(
    tmp_path: Path,
) -> None:
    """payload 写入边界拒绝未知 descriptor kind 且不落 durable row。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """尝试写入未知 descriptor kind。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-json",
                    payload_id="sqlite-json",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={"ok": True},
                    metadata={"descriptor_kind": "unknown_descriptor_kind"},
                ),
            )

        with pytest.raises(
            HostDurableError, match="payload descriptor kind is invalid"
        ):
            store.transaction_runner.run_write(operation)

        def count_operation(transaction: HostTransaction) -> tuple[int, int]:
            """统计 payload 与 descriptor rows。

            :param transaction: Host transaction。
            :returns: payload row 数与 descriptor row 数。
            """

            return (
                _count_rows(transaction, TABLE_SQLITE_PAYLOADS),
                _count_rows(transaction, TABLE_PAYLOAD_DESCRIPTORS),
            )

        assert store.transaction_runner.run_read(count_operation) == (0, 0)


def test_bytes_payload_writes_bytes_descriptor_and_digest(
    tmp_path: Path,
) -> None:
    """bytes payload 会按原始 bytes 计算 digest 与 size。"""

    content = b"\x00\x01payload"
    expected_digest = sha256_digest_bytes(content)
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[str, int, bytes]:
            """写入 bytes payload 并读取 row。

            :param transaction: Host transaction。
            :returns: descriptor digest、size 与 payload bytes。
            """

            descriptor = write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-bytes",
                    payload_id="sqlite-bytes",
                    payload_format=SQLitePayloadFormat.BYTES,
                    payload_bytes=content,
                    media_type="application/octet-stream",
                    expected_digest=expected_digest,
                ),
            )
            row = transaction.fetchone(
                f"""
                SELECT payload_bytes
                FROM {TABLE_SQLITE_PAYLOADS}
                WHERE payload_id = ?
                """,
                ("sqlite-bytes",),
            )
            assert row is not None
            payload_bytes = row.get("payload_bytes")
            assert isinstance(payload_bytes, bytes)
            return (
                descriptor.payload_digest,
                descriptor.payload_size_bytes,
                payload_bytes,
            )

        assert store.transaction_runner.run_write(operation) == (
            expected_digest,
            len(content),
            content,
        )


def test_bytes_payload_rejects_payload_json(tmp_path: Path) -> None:
    """bytes payload 显式携带 payload_json 时会结构化拒绝。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """尝试写入同时携带 bytes 与 JSON 的 bytes payload。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-bytes-with-json",
                    payload_id="sqlite-bytes-with-json",
                    payload_format=SQLitePayloadFormat.BYTES,
                    payload_json={"ignored": False},
                    payload_bytes=b"bytes",
                ),
            )

        with pytest.raises(
            HostDurableError, match="bytes payload must not include payload_json"
        ):
            store.transaction_runner.run_write(operation)


def test_read_payload_descriptor_returns_typed_descriptor(tmp_path: Path) -> None:
    """descriptor read 会返回 typed PayloadDescriptor。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[PayloadKind, str | None]:
            """写入并读取 descriptor。

            :param transaction: Host transaction。
            :returns: descriptor kind 与 sqlite payload id。
            """

            write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-json",
                    payload_id="sqlite-json",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={"ok": True},
                ),
            )
            descriptor = read_payload_descriptor(transaction, "payload-json")
            assert descriptor is not None
            return descriptor.payload_kind, descriptor.sqlite_payload_id

        assert store.transaction_runner.run_write(operation) == (
            PayloadKind.SQLITE_PAYLOAD,
            "sqlite-json",
        )


def test_descriptor_with_missing_sqlite_payload_fk_fails(
    tmp_path: Path,
) -> None:
    """缺失 sqlite payload row 的 descriptor 会触发 foreign-key 结构化错误。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """直接插入缺失 FK 的 descriptor。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

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
                    "payload-missing",
                    PayloadKind.SQLITE_PAYLOAD.value,
                    sha256_digest_bytes(b"missing"),
                    7,
                    None,
                    "missing-sqlite-payload",
                    None,
                    "{}",
                    "2026-05-14T01:02:03.123456Z",
                ),
            )

        with pytest.raises(HostForeignKeyError):
            store.transaction_runner.run_write(operation)


def test_event_payload_object_raises_when_descriptor_missing(
    tmp_path: Path,
) -> None:
    """EventLog 指向缺失 descriptor 时 fail closed。"""

    event = _event_row(
        payload_ref="payload-missing-descriptor",
        payload_digest=sha256_digest_bytes(b"missing-descriptor"),
    )
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """触发 descriptor 缺失读取。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            event_payload_object(
                transaction, event, payload_label="USER_INPUT_ACCEPTED"
            )

        with pytest.raises(
            HostDurableError, match="USER_INPUT_ACCEPTED payload descriptor is missing"
        ):
            store.transaction_runner.run_read(operation)


def test_event_payload_object_raises_when_sqlite_payload_row_missing(
    tmp_path: Path,
) -> None:
    """descriptor 存在但 sqlite payload row 缺失时 fail closed。"""

    payload_ref = "payload-missing-sqlite-row"
    payload_id = "sqlite-missing-row"
    payload_digest: str | None = None
    with open_host_durable_store(_options(tmp_path)) as store:

        def write_descriptor(transaction: HostTransaction) -> str:
            """写入完整 payload row 与 descriptor。

            :param transaction: Host transaction。
            :returns: descriptor payload digest。
            """

            descriptor = write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref=payload_ref,
                    payload_id=payload_id,
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={"display_text": "full prompt"},
                    media_type="application/json",
                ),
            )
            return descriptor.payload_digest

        payload_digest = store.transaction_runner.run_write(write_descriptor)

    _delete_sqlite_payload_row_without_fk(tmp_path / "durable.sqlite3", payload_id)
    if payload_digest is None:
        raise AssertionError("payload digest must exist")
    event = _event_row(payload_ref=payload_ref, payload_digest=payload_digest)
    with open_host_durable_store(_options(tmp_path)) as store:

        def read_missing_payload(transaction: HostTransaction) -> None:
            """读取已损坏 descriptor 指向的 payload row。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            event_payload_object(
                transaction, event, payload_label="USER_INPUT_ACCEPTED"
            )

        with pytest.raises(
            HostDurableError,
            match="USER_INPUT_ACCEPTED sqlite payload row is missing",
        ):
            store.transaction_runner.run_read(read_missing_payload)


def test_payload_digest_mismatch_raises_without_writing_rows(
    tmp_path: Path,
) -> None:
    """payload expected_digest 不匹配会抛出 HostDigestMismatchError 且不写 row。"""

    wrong_digest = sha256_digest_bytes(b"wrong")
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """触发 payload digest mismatch。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-json",
                    payload_id="sqlite-json",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={"ok": True},
                    expected_digest=wrong_digest,
                ),
            )

        with pytest.raises(HostDigestMismatchError):
            store.transaction_runner.run_write(operation)

        def count_operation(transaction: HostTransaction) -> tuple[int, int]:
            """统计 payload 与 descriptor rows。

            :param transaction: Host transaction。
            :returns: payload row 数与 descriptor row 数。
            """

            return (
                _count_rows(transaction, TABLE_SQLITE_PAYLOADS),
                _count_rows(transaction, TABLE_PAYLOAD_DESCRIPTORS),
            )

        assert store.transaction_runner.run_write(count_operation) == (0, 0)


def _event_row(*, payload_ref: str, payload_digest: str) -> EventLogRow:
    """构造引用 payload descriptor 的 EventLog row。

    :param payload_ref: payload descriptor ref。
    :param payload_digest: payload digest。
    :returns: EventLogRow。
    """

    return EventLogRow(
        event_sequence=1,
        event_id="event-user-input-payload",
        event_body_digest=sha256_digest_bytes(b"event-body"),
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-1",
        run_id="run-1",
        attempt_id=None,
        execution_id=None,
        event_type="USER_INPUT_ACCEPTED",
        occurred_at="2026-05-14T01:02:03.123456Z",
        actor="pytest",
        source="pytest",
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json='{"payload_ref":null}',
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        appended_at="2026-05-14T01:02:03.123456Z",
    )


def _delete_sqlite_payload_row_without_fk(db_path: Path, payload_id: str) -> None:
    """绕过 FK 删除 sqlite payload row 以构造损坏 durable 状态。

    :param db_path: SQLite DB 路径。
    :param payload_id: 待删除 payload row id。
    :returns: ``None``。
    """

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            f"DELETE FROM {TABLE_SQLITE_PAYLOADS} WHERE payload_id = ?",
            (payload_id,),
        )
        connection.commit()
    finally:
        connection.close()


def test_event_log_can_reference_existing_descriptor_and_digest(
    tmp_path: Path,
) -> None:
    """EventLog 可以引用已存在 descriptor 及其 payload digest。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(
            transaction: HostTransaction,
        ) -> tuple[str | None, str | None, str]:
            """写 payload descriptor 并 append EventLog。

            :param transaction: Host transaction。
            :returns: EventLog row 中的 payload ref、digest 与 descriptor digest。
            """

            descriptor = write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-json",
                    payload_id="sqlite-json",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={"accepted": True},
                ),
            )
            event = append_event(
                transaction,
                _event_request(
                    descriptor.payload_ref,
                    descriptor.payload_digest,
                ),
            )
            return (
                event.row.payload_ref,
                event.row.payload_digest,
                descriptor.payload_digest,
            )

        event_payload_ref, event_payload_digest, descriptor_digest = (
            store.transaction_runner.run_write(operation)
        )
        assert event_payload_ref == "payload-json"
        assert event_payload_digest == descriptor_digest


def test_event_log_payload_digest_mismatch_raises_reference_error(
    tmp_path: Path,
) -> None:
    """EventLog 引用已存在 descriptor 但 digest 不一致时结构化失败。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def setup(transaction: HostTransaction) -> None:
            """写入 descriptor。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-json",
                    payload_id="sqlite-json",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={"accepted": True},
                ),
            )

        store.transaction_runner.run_write(setup)

        def operation(transaction: HostTransaction) -> None:
            """用错误 digest append EventLog。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(
                transaction,
                _event_request("payload-json", sha256_digest_bytes(b"wrong")),
            )

        with pytest.raises(HostPayloadReferenceError):
            store.transaction_runner.run_write(operation)
