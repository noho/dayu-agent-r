"""Host storage lifecycle artifact orphan proof 测试。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.host.durable.artifact import LocalArtifactRef, LocalArtifactStore
from dayu.host.durable.codec import sha256_digest_bytes
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.storage_lifecycle import (
    artifact_relative_path_is_referenced,
    collect_referenced_artifact_paths,
    physical_artifact_bytes,
    scan_orphan_artifact_files,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.durable.payload import write_payload_descriptor_for_artifact

_OLD_TIMESTAMP_SECONDS = 1_700_000_000
_NOW = datetime(2026, 6, 12, 12, 0, 0, tzinfo=UTC)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
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


def test_artifact_relative_path_reference_uses_descriptor_truth(
    tmp_path: Path,
) -> None:
    """artifact path 引用证明只以 artifact descriptor 为真源。"""

    options = _options(tmp_path)
    store = open_host_durable_store(options)
    artifact_ref = LocalArtifactStore(
        options.payload_policy.artifact_root
    ).write_artifact_bytes(b"referenced")
    try:
        def write_descriptor(transaction: HostTransaction) -> None:
            """写入 artifact descriptor。

            :param transaction: Host write transaction。
            :returns: ``None``。
            """

            write_payload_descriptor_for_artifact(
                transaction,
                "payload-ref",
                artifact_ref,
                "application/octet-stream",
                {},
            )

        store.transaction_runner.run_write(write_descriptor)

        def read_checks(transaction: HostTransaction) -> tuple[bool, bool]:
            """读取 true/false 引用证明。

            :param transaction: Host read transaction。
            :returns: 已引用路径与未引用路径的判定结果。
            """

            return (
                artifact_relative_path_is_referenced(
                    transaction,
                    artifact_ref.artifact_relative_path,
                ),
                artifact_relative_path_is_referenced(
                    transaction,
                    "sha256/ff/not-referenced",
                ),
            )

        referenced, missing = store.transaction_runner.run_read(read_checks)
    finally:
        store.close()

    assert referenced is True
    assert missing is False


def test_collect_referenced_artifact_paths_deduplicates_shared_descriptors(
    tmp_path: Path,
) -> None:
    """多个 descriptor 共享同一内容寻址文件时只收集一个相对路径。"""

    options = _options(tmp_path)
    store = open_host_durable_store(options)
    artifact_ref = LocalArtifactStore(
        options.payload_policy.artifact_root
    ).write_artifact_bytes(b"shared")
    try:
        def write_shared_descriptors(transaction: HostTransaction) -> None:
            """写入两个共享 artifact path 的 descriptor。

            :param transaction: Host write transaction。
            :returns: ``None``。
            """

            write_payload_descriptor_for_artifact(
                transaction,
                "payload-ref-a",
                artifact_ref,
                "application/octet-stream",
                {},
            )
            write_payload_descriptor_for_artifact(
                transaction,
                "payload-ref-b",
                artifact_ref,
                "application/octet-stream",
                {},
            )

        store.transaction_runner.run_write(write_shared_descriptors)
        referenced_paths = store.transaction_runner.run_read(
            collect_referenced_artifact_paths
        )
    finally:
        store.close()

    assert referenced_paths == frozenset({artifact_ref.artifact_relative_path})


def test_descriptor_with_durable_event_reference_keeps_artifact_referenced(
    tmp_path: Path,
) -> None:
    """projection lag 场景下 descriptor 存活即证明 artifact 仍被引用。"""

    options = _options(tmp_path)
    store = open_host_durable_store(options)
    artifact_ref = LocalArtifactStore(
        options.payload_policy.artifact_root
    ).write_artifact_bytes(b"event-referenced")
    try:
        def write_descriptor_and_event(transaction: HostTransaction) -> None:
            """写入 descriptor 与引用该 payload_ref 的 EventLog row。

            :param transaction: Host write transaction。
            :returns: ``None``。
            """

            descriptor = write_payload_descriptor_for_artifact(
                transaction,
                "payload-ref-event",
                artifact_ref,
                "application/octet-stream",
                {},
            )
            append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-payload-ref",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id="session-1",
                    run_id="run-1",
                    attempt_id=None,
                    execution_id=None,
                    event_type="USER_INPUT_ACCEPTED",
                    occurred_at=_NOW,
                    actor="host",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json={"payload_ref": descriptor.payload_ref},
                    payload_ref=descriptor.payload_ref,
                    payload_digest=descriptor.payload_digest,
                ),
            )

        store.transaction_runner.run_write(write_descriptor_and_event)

        def is_referenced(transaction: HostTransaction) -> bool:
            """读取 artifact 引用证明。

            :param transaction: Host read transaction。
            :returns: 引用证明结果。
            """

            return artifact_relative_path_is_referenced(
                transaction,
                artifact_ref.artifact_relative_path,
            )

        referenced = store.transaction_runner.run_read(is_referenced)
    finally:
        store.close()

    assert referenced is True


def test_scan_orphan_artifact_files_filters_namespace_grace_and_sorts(
    tmp_path: Path,
) -> None:
    """orphan 扫描只返回 sha256 namespace 下超过 grace 的排序候选。"""

    artifact_root = tmp_path / "artifacts"
    old_orphan_b = _write_raw_artifact_file(artifact_root, b"old-b")
    referenced = _write_raw_artifact_file(artifact_root, b"referenced")
    old_orphan_a = _write_raw_artifact_file(artifact_root, b"old-a")
    fresh_orphan = _write_raw_artifact_file(artifact_root, b"fresh")
    _set_mtime(artifact_root / old_orphan_a, _OLD_TIMESTAMP_SECONDS)
    _set_mtime(artifact_root / old_orphan_b, _OLD_TIMESTAMP_SECONDS)
    _set_mtime(artifact_root / referenced, _OLD_TIMESTAMP_SECONDS)
    _set_mtime(artifact_root / fresh_orphan, _NOW.timestamp())
    (artifact_root / ".tmp").mkdir()
    (artifact_root / ".tmp" / "temp-file").write_bytes(b"temp")
    (artifact_root / "audit").mkdir()
    (artifact_root / "audit" / "audit.jsonl").write_text("{}", encoding="utf-8")
    (artifact_root / "tool-trace").mkdir()
    (artifact_root / "tool-trace" / "trace.jsonl").write_text(
        "{}",
        encoding="utf-8",
    )

    candidates = scan_orphan_artifact_files(
        artifact_root,
        frozenset({referenced}),
        now=_NOW,
        grace_seconds=3600.0,
    )

    assert candidates == tuple(sorted((old_orphan_a, old_orphan_b)))


def test_scan_orphan_artifact_files_rejects_negative_grace_seconds(
    tmp_path: Path,
) -> None:
    """orphan 扫描拒绝负数 grace window。"""

    with pytest.raises(ValueError, match="grace_seconds must be non-negative"):
        scan_orphan_artifact_files(
            tmp_path / "artifacts",
            frozenset(),
            now=_NOW,
            grace_seconds=-1.0,
        )


def test_scan_orphan_artifact_files_rejects_naive_datetime(
    tmp_path: Path,
) -> None:
    """orphan 扫描拒绝缺少时区的当前时间。"""

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        scan_orphan_artifact_files(
            tmp_path / "artifacts",
            frozenset(),
            now=datetime(2026, 6, 12, 12, 0, 0),
            grace_seconds=0.0,
        )


def test_physical_artifact_bytes_counts_only_published_sha256_files(
    tmp_path: Path,
) -> None:
    """物理 artifact size 排除 tmp、audit 和 tool-trace 文件。"""

    artifact_root = tmp_path / "artifacts"
    artifact_a = _write_raw_artifact_file(artifact_root, b"abc")
    artifact_b = _write_raw_artifact_file(artifact_root, b"defgh")
    (artifact_root / ".tmp").mkdir()
    (artifact_root / ".tmp" / "temp-file").write_bytes(b"temp")
    (artifact_root / "audit").mkdir()
    (artifact_root / "audit" / "audit.jsonl").write_bytes(b"audit")
    (artifact_root / "tool-trace").mkdir()
    (artifact_root / "tool-trace" / "trace.jsonl").write_bytes(b"trace")

    assert physical_artifact_bytes(artifact_root) == (
        (artifact_root / artifact_a).stat().st_size
        + (artifact_root / artifact_b).stat().st_size
    )


def _write_raw_artifact_file(artifact_root: Path, content: bytes) -> str:
    """按内容 digest 写入测试 artifact 文件。

    :param artifact_root: artifact 根目录。
    :param content: 文件内容。
    :returns: artifact POSIX 相对路径。
    """

    digest = sha256_digest_bytes(content)
    artifact_ref = LocalArtifactRef(
        artifact_relative_path=_relative_path_for_digest(digest),
        artifact_digest=digest,
        artifact_size_bytes=len(content),
    )
    artifact_path = artifact_root / artifact_ref.artifact_relative_path
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(content)
    return artifact_ref.artifact_relative_path


def _relative_path_for_digest(digest: str) -> str:
    """生成测试用 artifact 相对路径。

    :param digest: sha256 digest。
    :returns: ``sha256/<shard>/<hex>`` 相对路径。
    """

    digest_hex = digest.removeprefix("sha256:")
    return f"sha256/{digest_hex[:2]}/{digest_hex}"


def _set_mtime(path: Path, timestamp_seconds: float) -> None:
    """设置文件 atime/mtime。

    :param path: 文件路径。
    :param timestamp_seconds: POSIX timestamp 秒数。
    :returns: ``None``。
    """

    os.utime(path, (timestamp_seconds, timestamp_seconds))
