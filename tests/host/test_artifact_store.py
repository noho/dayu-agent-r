"""Host durable local artifact helper 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.host.durable.artifact import (
    LocalArtifactRef,
    LocalArtifactStore,
    validate_artifact_ref,
)
from dayu.host.durable.codec import sha256_digest_bytes
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
    read_event_by_id,
)
from dayu.host.durable.errors import (
    HostArtifactWriteError,
    HostDigestMismatchError,
    HostDurableError,
    HostPayloadReferenceError,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadKind,
    read_payload_descriptor,
    write_payload_descriptor_for_artifact,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_PAYLOAD_DESCRIPTORS,
)
from dayu.host.durable.transaction import HostTransaction


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
    """构造引用 artifact descriptor 的 EventLog 请求。

    :param payload_ref: payload descriptor 引用。
    :param payload_digest: payload digest。
    :returns: EventLog append 请求。
    """

    return EventLogAppendRequest(
        event_id="event-artifact",
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-1",
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        event_type="host.artifact.accepted",
        occurred_at=datetime(2026, 5, 14, 1, 2, 3, 123456, tzinfo=UTC),
        actor="host",
        source="artifact-test",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={"ref": payload_ref},
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )


def _count_event_rows(transaction: HostTransaction) -> int:
    """读取 EventLog row count。

    :param transaction: Host transaction。
    :returns: EventLog row count。
    :raises AssertionError: SQLite 未返回 count row 时抛出。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {TABLE_EVENT_LOG}")
    assert row is not None
    total = row.get("total")
    assert isinstance(total, int)
    return total


def test_artifact_helper_writes_under_injected_root(tmp_path: Path) -> None:
    """artifact helper 只写入显式注入的 artifact root。"""

    artifact_root = tmp_path / "configured-artifacts"
    artifact_ref = LocalArtifactStore(artifact_root).write_artifact_bytes(b"content")
    final_path = artifact_root / artifact_ref.artifact_relative_path

    assert final_path.is_file()
    assert final_path.read_bytes() == b"content"
    assert artifact_ref.artifact_relative_path.startswith("sha256/")
    assert Path("sha256").exists() is False


def test_artifact_ref_rejects_invalid_relative_paths() -> None:
    """artifact ref 拒绝绝对路径、空字节、目录穿越与 temp 路径。"""

    digest = sha256_digest_bytes(b"content")
    invalid_paths = (
        "/abs/path",
        "sha256/\x00/path",
        "../escape",
        "sha256/../escape",
        ".tmp/artifact-temp",
    )
    for relative_path in invalid_paths:
        with pytest.raises(HostDurableError):
            validate_artifact_ref(
                LocalArtifactRef(
                    artifact_relative_path=relative_path,
                    artifact_digest=digest,
                    artifact_size_bytes=7,
                )
            )


def test_artifact_ref_rejects_negative_size() -> None:
    """artifact ref 拒绝负数 artifact_size_bytes。"""

    with pytest.raises(HostDurableError, match="Artifact size must be non-negative"):
        validate_artifact_ref(
            LocalArtifactRef(
                artifact_relative_path="sha256/ab/value",
                artifact_digest=sha256_digest_bytes(b"content"),
                artifact_size_bytes=-1,
            )
        )


def test_artifact_helper_rejects_symlink_escape(tmp_path: Path) -> None:
    """artifact helper 不会通过已存在 symlink 逃逸 artifact root。"""

    artifact_root = tmp_path / "artifacts"
    outside_root = tmp_path / "outside"
    artifact_root.mkdir()
    outside_root.mkdir()
    (artifact_root / "sha256").symlink_to(outside_root, target_is_directory=True)

    with pytest.raises(HostArtifactWriteError):
        LocalArtifactStore(artifact_root).write_artifact_bytes(b"content")


def test_temp_area_is_under_artifact_root_and_concurrent_writes_do_not_collide(
    tmp_path: Path,
) -> None:
    """temp 文件目录固定在 artifact_root/.tmp 且多次写入不会路径碰撞。"""

    artifact_root = tmp_path / "artifacts"
    store = LocalArtifactStore(artifact_root)
    first = store.write_artifact_bytes(b"first")
    second = store.write_artifact_bytes(b"second")

    assert (artifact_root / ".tmp").is_dir()
    assert first.artifact_relative_path != second.artifact_relative_path
    assert (artifact_root / first.artifact_relative_path).is_file()
    assert (artifact_root / second.artifact_relative_path).is_file()


def test_digest_verify_happens_before_descriptor_write(tmp_path: Path) -> None:
    """artifact digest mismatch 会阻止后续 descriptor 写入。"""

    options = _options(tmp_path)
    wrong_digest = sha256_digest_bytes(b"wrong")
    with pytest.raises(HostDigestMismatchError):
        LocalArtifactStore(options.payload_policy.artifact_root).write_artifact_bytes(
            b"content",
            expected_digest=wrong_digest,
        )
    with open_host_durable_store(options) as durable_store:

        def operation(transaction: HostTransaction) -> int:
            """确认没有 descriptor row。

            :param transaction: Host transaction。
            :returns: descriptor row count。
            """

            row = transaction.fetchone(
                f"SELECT COUNT(*) AS total FROM {TABLE_PAYLOAD_DESCRIPTORS}"
            )
            assert row is not None
            total = row.get("total")
            assert isinstance(total, int)
            return total

        assert durable_store.transaction_runner.run_write(operation) == 0


def test_final_artifact_is_published_and_digest_matches(tmp_path: Path) -> None:
    """artifact 最终文件发布后内容 digest 与返回 ref 一致。"""

    content = b"durable artifact"
    expected_digest = sha256_digest_bytes(content)
    artifact_root = tmp_path / "artifacts"
    artifact_ref = LocalArtifactStore(artifact_root).write_artifact_bytes(
        content,
        expected_digest=expected_digest,
    )
    final_path = artifact_root / artifact_ref.artifact_relative_path

    assert final_path.is_file()
    assert sha256_digest_bytes(final_path.read_bytes()) == artifact_ref.artifact_digest
    assert artifact_ref.artifact_digest == expected_digest
    assert artifact_ref.artifact_size_bytes == len(content)


def test_event_log_references_descriptor_not_artifact_temp_path(
    tmp_path: Path,
) -> None:
    """EventLog row 只引用 descriptor payload_ref，不引用 artifact temp 路径。"""

    options = _options(tmp_path)
    artifact_ref = LocalArtifactStore(
        options.payload_policy.artifact_root
    ).write_artifact_bytes(b"artifact")
    with open_host_durable_store(options) as durable_store:

        def operation(transaction: HostTransaction) -> tuple[str | None, str | None]:
            """写 artifact descriptor 并 append EventLog。

            :param transaction: Host transaction。
            :returns: EventLog payload_ref 与 descriptor artifact_relative_path。
            """

            descriptor = write_payload_descriptor_for_artifact(
                transaction,
                "payload-artifact",
                artifact_ref,
                "application/octet-stream",
                {"kind": "artifact"},
            )
            event = append_event(
                transaction,
                _event_request(
                    descriptor.payload_ref,
                    descriptor.payload_digest,
                ),
            )
            return event.row.payload_ref, descriptor.artifact_relative_path

        event_payload_ref, artifact_relative_path = (
            durable_store.transaction_runner.run_write(operation)
        )
        assert event_payload_ref == "payload-artifact"
        assert artifact_relative_path is not None
        assert ".tmp" not in event_payload_ref
        assert not artifact_relative_path.startswith(".tmp/")


def test_sqlite_failure_after_artifact_publish_leaves_orphan_not_fact(
    tmp_path: Path,
) -> None:
    """artifact 发布后 SQLite rollback 只留下 orphan 文件，不留下 accepted fact。"""

    options = _options(tmp_path)
    artifact_ref = LocalArtifactStore(
        options.payload_policy.artifact_root
    ).write_artifact_bytes(b"orphan")
    final_path = options.payload_policy.artifact_root / artifact_ref.artifact_relative_path
    with open_host_durable_store(options) as durable_store:

        def operation(transaction: HostTransaction) -> None:
            """写 descriptor 与 EventLog 后强制失败。

            :param transaction: Host transaction。
            :returns: 永不返回。
            :raises RuntimeError: 始终抛出，用于验证 rollback。
            """

            descriptor = write_payload_descriptor_for_artifact(
                transaction,
                "payload-orphan",
                artifact_ref,
                None,
                {"kind": "orphan-window"},
            )
            append_event(
                transaction,
                _event_request(descriptor.payload_ref, descriptor.payload_digest),
            )
            raise RuntimeError("force rollback")

        with pytest.raises(RuntimeError):
            durable_store.transaction_runner.run_write(operation)

        def read_after_rollback(transaction: HostTransaction) -> tuple[bool, int]:
            """读取 rollback 后的 descriptor 与 EventLog row。

            :param transaction: Host transaction。
            :returns: descriptor 是否存在与 EventLog row count。
            """

            return (
                read_payload_descriptor(transaction, "payload-orphan") is not None,
                _count_event_rows(transaction),
            )

        assert durable_store.transaction_runner.run_write(read_after_rollback) == (
            False,
            0,
        )
    assert final_path.is_file()


def test_event_log_rejects_descriptor_with_artifact_temp_path(
    tmp_path: Path,
) -> None:
    """EventLog 不接受指向 artifact temp path 的 descriptor。"""

    digest = sha256_digest_bytes(b"temp")
    with open_host_durable_store(_options(tmp_path)) as durable_store:

        def setup(transaction: HostTransaction) -> None:
            """直接插入 temp path artifact descriptor。

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
                    "payload-temp",
                    PayloadKind.ARTIFACT_REF.value,
                    digest,
                    4,
                    None,
                    None,
                    ".tmp/artifact-temp",
                    "{}",
                    "2026-05-14T01:02:03.123456Z",
                ),
            )

        durable_store.transaction_runner.run_write(setup)

        def operation(transaction: HostTransaction) -> None:
            """尝试 append 引用 temp descriptor 的 EventLog。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            append_event(transaction, _event_request("payload-temp", digest))

        with pytest.raises(HostPayloadReferenceError):
            durable_store.transaction_runner.run_write(operation)
        assert (
            durable_store.transaction_runner.run_write(
                lambda transaction: read_event_by_id(transaction, "event-artifact")
            )
            is None
        )
