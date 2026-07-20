"""Host LogAuditSink JSONL projection 测试。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.audit import (
    LOG_AUDIT_SINK_CONSUMER_ID,
    LogAuditSink,
    LogAuditSinkOptions,
    PurgeCompletedAuditRecordRequest,
    PurgeFailedAuditRecordRequest,
    PurgeStartedAuditRecordRequest,
    append_purge_completed_audit_record,
    append_purge_failed_audit_record,
    append_purge_started_audit_record,
    audit_json_line_marks_purged_source_eventlog_facts,
    default_log_audit_sink_options,
)
from dayu.host.durable.audit import read_audit_sink_marker
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.purge import (
    PurgeDeleteCounts,
    PurgeTombstoneRow,
    build_deleted_counts_digest,
    build_purge_semantic_digest,
    build_purge_tombstone_digest,
)
from dayu.host.durable.projection import (
    read_projection_checkpoint,
    read_projection_failure,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_AUDIT_SINK_MARKERS,
    TABLE_HOST_RUNS,
)
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.lifecycle_events import (
    HostPreviewEventType,
    serialize_host_event_type,
)
from dayu.host.projection import ProjectionRunner

_EVENT_TYPE_RUN_ACCEPTED = "RUN_ACCEPTED"
_EVENT_TYPE_PREVIEW_DELTA = serialize_host_event_type(
    HostPreviewEventType.REASONING_DELTA
)
_FIXED_NOW = datetime(2026, 5, 29, 1, 2, 3, tzinfo=UTC)
_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_DIGEST_C = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
_PURGE_TOMBSTONE_ID = "purge-tombstone-1"
_PURGE_SESSION_ID = "session-purged-1"
_PURGE_CLIENT_REQUEST_ID = "purge-request-1"
_PURGE_REASON = "retention-request"
_CONFIGURED_SECRET_SENTINEL = "synthetic-local-trust-sentinel-6f2b9d8c"


def _purge_counts() -> PurgeDeleteCounts:
    """构造 purge audit line 测试删除计数。

    :returns: purge 删除矩阵计数。
    """

    return PurgeDeleteCounts(
        event_log_rows=2,
        idempotency_records=1,
        payload_descriptors=0,
        sqlite_payloads=0,
        host_session_slots=1,
        host_sessions=1,
        host_runs=1,
        host_attempts=1,
        host_attempt_dispatch_records=1,
        host_wait_records=0,
        host_run_results=1,
        host_session_timeline_items=1,
        host_memory_snapshots=0,
        host_memory_items=0,
        host_memory_diagnostics=0,
        host_audit_sink_markers=1,
        host_tool_trace_hot=0,
        host_outbox_terminal_items=0,
        host_outbox_drain_idempotency=0,
        host_projection_checkpoints=1,
        host_projection_failures=0,
    )


def _purge_operation_context_refs() -> dict[str, JsonValue]:
    """构造 purge audit 测试 operation context refs。

    :returns: operation context refs JSON object。
    """

    return {"business_object_id": _PURGE_SESSION_ID}


def _purge_request_context() -> dict[str, JsonValue]:
    """构造 purge audit 测试 request context。

    :returns: request context JSON object。
    """

    return {"request_id": "request-1"}


def _purge_semantic_digest() -> str:
    """构造 purge audit 测试 semantic digest。

    :returns: ``sha256:`` semantic digest。
    """

    return build_purge_semantic_digest(
        session_id=_PURGE_SESSION_ID,
        reason=_PURGE_REASON,
        operation_context_digest=_DIGEST_A,
        operation_context_refs=_purge_operation_context_refs(),
        request_context=_purge_request_context(),
    )


def _purge_tombstone(started_line: Mapping[str, JsonValue]) -> PurgeTombstoneRow:
    """构造 purge_completed 测试 tombstone。

    :param started_line: 已构造的 purge_started audit line。
    :returns: purge tombstone row。
    """

    counts = _purge_counts()
    audit_record_ref = started_line.get("audit_record_ref")
    audit_record_digest = started_line.get("line_digest")
    assert isinstance(audit_record_ref, str)
    assert isinstance(audit_record_digest, str)
    return PurgeTombstoneRow(
        tombstone_id=_PURGE_TOMBSTONE_ID,
        session_id=_PURGE_SESSION_ID,
        client_request_id=_PURGE_CLIENT_REQUEST_ID,
        semantic_request_digest=_purge_semantic_digest(),
        actor="user-1",
        source="host-api",
        operation_context_digest=_DIGEST_A,
        operation_context_refs=_purge_operation_context_refs(),
        reason=_PURGE_REASON,
        purged_at="2026-05-29T00:00:00.000000Z",
        precondition_digest=_DIGEST_B,
        deleted_counts=counts,
        deleted_counts_digest=build_deleted_counts_digest(counts),
        deleted_refs_digest=_DIGEST_C,
        audit_record_ref=audit_record_ref,
        audit_record_digest=audit_record_digest,
        request_context=_purge_request_context(),
    )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(),
    )


def _append_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    event_class: EventClass = EventClass.CANONICAL_FACT,
    event_type: str = _EVENT_TYPE_RUN_ACCEPTED,
    payload: JsonValue | None = None,
    actor: str | None = "analyst",
    source: str | None = "unit-test",
    client_request_id: str | None = "client-request-1",
) -> EventLogRow:
    """追加 audit sink 测试 EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param event_class: EventLog class。
    :param event_type: EventLog type。
    :param payload: inline payload；``None`` 时使用空 object。
    :param actor: EventLog actor。
    :param source: EventLog source。
    :param client_request_id: EventLog client request id。
    :returns: 已追加 EventLog row。
    """

    payload_json = payload if payload is not None else {}
    return transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=event_class,
                session_id="session-1",
                run_id="run-1",
                attempt_id="attempt-1",
                execution_id="execution-1",
                event_type=event_type,
                occurred_at=_FIXED_NOW,
                actor=actor,
                source=source,
                client_request_id=client_request_id,
                idempotency_key=client_request_id,
                policy_decision={"decision": "accepted"},
                reason={"reason": "test"},
                payload_json=payload_json,
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
    )


def _run_audit_once(
    transaction_runner: HostTransactionRunner,
    audit_jsonl_path: Path,
    *,
    lock_path: Path | None = None,
) -> None:
    """运行一次 LogAuditSink projection。

    :param transaction_runner: Host durable transaction runner。
    :param audit_jsonl_path: audit JSONL 路径。
    :param lock_path: 显式 runtime file lock 路径；``None`` 时使用默认派生路径。
    :returns: ``None``。
    """

    ProjectionRunner(
        transaction_runner,
        (
            LogAuditSink(
                LogAuditSinkOptions(
                    audit_jsonl_path=audit_jsonl_path,
                    create_parent_dirs=True,
                    lock_path=lock_path,
                )
            ),
        ),
    ).run_once(LOG_AUDIT_SINK_CONSUMER_ID, limit=10)


def _json_lines(path: Path) -> tuple[Mapping[str, JsonValue], ...]:
    """读取 JSONL 文件为 JSON object 元组。

    :param path: JSONL 文件路径。
    :returns: JSON object 元组。
    :raises AssertionError: 行不是 JSON object 时抛出。
    """

    if not path.exists():
        return ()
    rows: list[Mapping[str, JsonValue]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = cast(JsonValue, json.loads(line))
        assert isinstance(value, Mapping)
        rows.append(cast(Mapping[str, JsonValue], value))
    return tuple(rows)


def _table_count(
    transaction_runner: HostTransactionRunner, table_name: str
) -> int:
    """读取表 row 数。

    :param transaction_runner: Host durable transaction runner。
    :param table_name: 目标表名。
    :returns: row 数。
    :raises AssertionError: SQLite 返回值不是整数时抛出。
    """

    row = transaction_runner.run_read(
        lambda transaction: transaction.fetchone(
            f"SELECT count(*) AS n FROM {table_name}"
        )
    )
    assert row is not None
    value = row.get("n")
    assert isinstance(value, int)
    return value


def _reset_audit_checkpoint(transaction_runner: HostTransactionRunner) -> None:
    """删除 audit consumer checkpoint 以模拟 replay。

    :param transaction_runner: Host durable transaction runner。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: transaction.execute(
            "DELETE FROM host_projection_checkpoints WHERE consumer_id = ?",
            (LOG_AUDIT_SINK_CONSUMER_ID.value,),
        )
    )


def test_jsonl_line_contains_required_audit_fields(tmp_path: Path) -> None:
    """audit JSONL 行包含计划要求的最小字段与 line digest。"""

    audit_path = tmp_path / "audit" / "host-audit.jsonl"
    lock_path = tmp_path / "locks" / "host-audit.jsonl.lock"
    payload: JsonValue = {
        "operation_context": {
            "operation_name": "submit_followup",
            "operation_kind": "command",
            "business_domain": "finance",
            "business_object_type": "filing",
            "business_object_id": "10-k-1",
            "scenario": "analysis",
            "correlation_id": "corr-1",
        },
        "authorization_claims": [
            {"name": "principal", "value": "analyst-1"},
        ],
        "policy_decision_ref": "policy-ref-1",
    }
    options = _options(tmp_path)
    marker_line_digest = ""
    with open_host_durable_store(options) as store:
        event = _append_event(
            store.transaction_runner, event_id="event-1", payload=payload
        )
        preview_event = _append_event(
            store.transaction_runner,
            event_id="event-preview",
            event_class=EventClass.PREVIEW,
            event_type=_EVENT_TYPE_PREVIEW_DELTA,
            payload={"delta": "ignored"},
        )
        _run_audit_once(store.transaction_runner, audit_path, lock_path=lock_path)
        marker = store.transaction_runner.run_read(
            lambda transaction: read_audit_sink_marker(transaction, event.event_id)
        )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction, LOG_AUDIT_SINK_CONSUMER_ID.value
            )
        )
        assert marker is not None
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == preview_event.event_sequence
        assert lock_path.exists()
        marker_line_digest = marker.line_digest

    lines = _json_lines(audit_path)
    assert len(lines) == 1
    line = lines[0]
    expected_fields = {
        "schema_version",
        "event_sequence",
        "event_id",
        "event_type",
        "event_class",
        "occurred_at",
        "session_id",
        "run_id",
        "attempt_id",
        "execution_id",
        "actor",
        "principal",
        "source",
        "client_request_id",
        "operation_context_refs",
        "operation_context_digest",
        "policy_decision_ref",
        "policy_decision_summary",
        "reason",
        "payload_ref",
        "payload_digest",
        "line_digest",
    }
    assert set(line) == expected_fields
    assert line["event_id"] == "event-1"
    assert line["event_class"] == EventClass.CANONICAL_FACT.value
    assert line["actor"] == "analyst"
    assert line["principal"] == "analyst-1"
    assert line["source"] == "unit-test"
    assert line["client_request_id"] == "client-request-1"
    assert line["policy_decision_ref"] == "policy-ref-1"
    assert line["policy_decision_summary"] == {"decision": "accepted"}
    assert line["reason"] == {"reason": "test"}
    assert line["payload_ref"] is None
    assert line["payload_digest"] is None
    fields_without_digest = dict(line)
    line_digest = fields_without_digest.pop("line_digest")
    assert line_digest == sha256_digest_json(fields_without_digest)
    assert marker_line_digest == line_digest


def test_audit_projection_excludes_internal_effective_execution_value(
    tmp_path: Path,
) -> None:
    """audit owner 不复制内部 effective execution 配置值。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: audit 行字段契约漂移或包含 synthetic sentinel 时抛出。
    """

    audit_path = tmp_path / "audit" / "effective-execution.jsonl"
    payload: JsonValue = {
        "display_text": "分析本期经营情况",
        "effective_execution_config": {
            "config": {
                "runner_spec": {
                    "headers": {
                        "X-Synthetic-Execution-Value": _CONFIGURED_SECRET_SENTINEL,
                    }
                }
            }
        },
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-effective-execution",
            event_type="USER_INPUT_ACCEPTED",
            payload=payload,
        )
        _run_audit_once(store.transaction_runner, audit_path)

    lines = _json_lines(audit_path)
    assert len(lines) == 1
    line = lines[0]
    assert set(line) == {
        "schema_version",
        "event_sequence",
        "event_id",
        "event_type",
        "event_class",
        "occurred_at",
        "session_id",
        "run_id",
        "attempt_id",
        "execution_id",
        "actor",
        "principal",
        "source",
        "client_request_id",
        "operation_context_refs",
        "operation_context_digest",
        "policy_decision_ref",
        "policy_decision_summary",
        "reason",
        "payload_ref",
        "payload_digest",
        "line_digest",
    }
    assert line["event_type"] == "USER_INPUT_ACCEPTED"
    serialized = canonical_json_dumps(cast(JsonValue, line))
    assert _CONFIGURED_SECRET_SENTINEL not in serialized


def test_marker_prevents_duplicate_append_when_checkpoint_replays(
    tmp_path: Path,
) -> None:
    """checkpoint replay 时 sink-local marker 避免重复 logical audit event。"""

    audit_path = tmp_path / "audit" / "host-audit.jsonl"
    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(store.transaction_runner, event_id="event-1")
        _run_audit_once(store.transaction_runner, audit_path)
        _reset_audit_checkpoint(store.transaction_runner)
        runner = ProjectionRunner(
            store.transaction_runner,
            (
                LogAuditSink(
                    LogAuditSinkOptions(
                        audit_jsonl_path=audit_path,
                        create_parent_dirs=True,
                        lock_path=None,
                    )
                ),
            ),
        )
        result = runner.run_once(LOG_AUDIT_SINK_CONSUMER_ID, limit=1)
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction, LOG_AUDIT_SINK_CONSUMER_ID.value
            )
        )
        assert result.duplicate_events == 1
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == event.event_sequence

    assert [line["event_id"] for line in _json_lines(audit_path)] == ["event-1"]


def test_jsonl_existing_line_prevents_duplicate_when_marker_missing(
    tmp_path: Path,
) -> None:
    """JSONL 已写但 marker 缺失时 replay 只补 marker，不重复追加行。"""

    audit_path = tmp_path / "audit" / "host-audit.jsonl"
    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(store.transaction_runner, event_id="event-1")
        _run_audit_once(store.transaction_runner, audit_path)
        store.transaction_runner.run_write(
            lambda transaction: (
                transaction.execute(
                    f"DELETE FROM {TABLE_HOST_AUDIT_SINK_MARKERS}"
                ),
                transaction.execute(
                    "DELETE FROM host_projection_checkpoints WHERE consumer_id = ?",
                    (LOG_AUDIT_SINK_CONSUMER_ID.value,),
                ),
            )
        )

        _run_audit_once(store.transaction_runner, audit_path)
        marker = store.transaction_runner.run_read(
            lambda transaction: read_audit_sink_marker(transaction, event.event_id)
        )

        assert marker is not None
        assert [line["event_id"] for line in _json_lines(audit_path)] == ["event-1"]


def test_jsonl_source_key_digest_conflict_records_failure_without_marker(
    tmp_path: Path,
) -> None:
    """JSONL 同 event_id 但 digest 不同时记录 failure，且不补 marker。"""

    audit_path = tmp_path / "audit" / "host-audit.jsonl"
    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(store.transaction_runner, event_id="event-1")
        _run_audit_once(store.transaction_runner, audit_path)
        lines = _json_lines(audit_path)
        assert len(lines) == 1
        conflict_line = dict(lines[0])
        conflict_line["line_digest"] = "sha256:conflicting"
        audit_path.write_text(
            json.dumps(conflict_line, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        store.transaction_runner.run_write(
            lambda transaction: (
                transaction.execute(
                    f"DELETE FROM {TABLE_HOST_AUDIT_SINK_MARKERS}"
                ),
                transaction.execute(
                    "DELETE FROM host_projection_checkpoints WHERE consumer_id = ?",
                    (LOG_AUDIT_SINK_CONSUMER_ID.value,),
                ),
            )
        )

        runner = ProjectionRunner(
            store.transaction_runner,
            (
                LogAuditSink(
                    LogAuditSinkOptions(
                        audit_jsonl_path=audit_path,
                        create_parent_dirs=True,
                        lock_path=None,
                    )
                ),
            ),
        )
        result = runner.run_once(LOG_AUDIT_SINK_CONSUMER_ID, limit=1)
        marker = store.transaction_runner.run_read(
            lambda transaction: read_audit_sink_marker(transaction, event.event_id)
        )
        failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction, LOG_AUDIT_SINK_CONSUMER_ID.value
            )
        )

        assert result.failures == 1
        assert marker is None
        assert failure is not None
        assert failure.failed_event_id == event.event_id
        assert _json_lines(audit_path)[0]["line_digest"] == "sha256:conflicting"


def test_file_write_failure_records_projection_failure_without_checkpoint(
    tmp_path: Path,
) -> None:
    """JSONL 文件写失败只记录 projection failure，不推进 checkpoint。"""

    audit_path = tmp_path / "audit-dir"
    audit_path.mkdir()
    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(store.transaction_runner, event_id="event-1")
        runner = ProjectionRunner(
            store.transaction_runner,
            (
                LogAuditSink(
                    LogAuditSinkOptions(
                        audit_jsonl_path=audit_path,
                        create_parent_dirs=False,
                        lock_path=None,
                    )
                ),
            ),
        )
        result = runner.run_once(LOG_AUDIT_SINK_CONSUMER_ID, limit=1)
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction, LOG_AUDIT_SINK_CONSUMER_ID.value
            )
        )
        failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction, LOG_AUDIT_SINK_CONSUMER_ID.value
            )
        )
        marker = store.transaction_runner.run_read(
            lambda transaction: read_audit_sink_marker(transaction, event.event_id)
        )
        assert result.failures == 1
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 0
        assert failure is not None
        assert failure.failed_event_id == event.event_id
        assert marker is None


def test_audit_sink_does_not_modify_governance_or_event_log(
    tmp_path: Path,
) -> None:
    """audit sink 不写 Run / Attempt governance，也不追加 EventLog。"""

    audit_path = tmp_path / "audit" / "host-audit.jsonl"
    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _append_event(store.transaction_runner, event_id="event-1")
        event_count_before = _table_count(store.transaction_runner, TABLE_EVENT_LOG)
        run_count_before = _table_count(store.transaction_runner, TABLE_HOST_RUNS)
        attempt_count_before = _table_count(
            store.transaction_runner, TABLE_HOST_ATTEMPTS
        )
        _run_audit_once(store.transaction_runner, audit_path)
        event_count_after = _table_count(store.transaction_runner, TABLE_EVENT_LOG)
        run_count_after = _table_count(store.transaction_runner, TABLE_HOST_RUNS)
        attempt_count_after = _table_count(
            store.transaction_runner, TABLE_HOST_ATTEMPTS
        )
        assert event_count_after == event_count_before
        assert run_count_after == run_count_before == 0
        assert attempt_count_after == attempt_count_before == 0


def test_purge_audit_lines_are_append_only_and_only_completed_marks_purged(
    tmp_path: Path,
) -> None:
    """purge started/failed/completed audit line 幂等追加且只有 completed 被识别。"""

    audit_path = tmp_path / "audit" / "host-audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        '{"event_id":"event-1","line_digest":"sha256:'
        'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}\n',
        encoding="utf-8",
    )
    options = LogAuditSinkOptions(audit_jsonl_path=audit_path, lock_path=None)
    started_result = append_purge_started_audit_record(
        options,
        PurgeStartedAuditRecordRequest(
            tombstone_id=_PURGE_TOMBSTONE_ID,
            session_id=_PURGE_SESSION_ID,
            client_request_id=_PURGE_CLIENT_REQUEST_ID,
            semantic_request_digest=_purge_semantic_digest(),
            actor="user-1",
            source="host-api",
            operation_context_digest=_DIGEST_A,
            operation_context_refs=_purge_operation_context_refs(),
            reason=_PURGE_REASON,
            request_context=_purge_request_context(),
        ),
    )
    append_purge_started_audit_record(
        options,
        PurgeStartedAuditRecordRequest(
            tombstone_id=_PURGE_TOMBSTONE_ID,
            session_id=_PURGE_SESSION_ID,
            client_request_id=_PURGE_CLIENT_REQUEST_ID,
            semantic_request_digest=_purge_semantic_digest(),
            actor="user-1",
            source="host-api",
            operation_context_digest=_DIGEST_A,
            operation_context_refs=_purge_operation_context_refs(),
            reason=_PURGE_REASON,
            request_context=_purge_request_context(),
        ),
    )
    failed_result = append_purge_failed_audit_record(
        options,
        PurgeFailedAuditRecordRequest(
            tombstone_id=_PURGE_TOMBSTONE_ID,
            session_id=_PURGE_SESSION_ID,
            client_request_id=_PURGE_CLIENT_REQUEST_ID,
            semantic_request_digest=_purge_semantic_digest(),
            actor="user-1",
            source="host-api",
            operation_context_digest=_DIGEST_A,
            operation_context_refs=_purge_operation_context_refs(),
            reason=_PURGE_REASON,
            request_context=_purge_request_context(),
            failure_stage="sqlite_purge_transaction",
            failure_message="test failure",
        ),
    )
    lines_after_failed = _json_lines(audit_path)
    tombstone = _purge_tombstone(lines_after_failed[1])
    completed_result = append_purge_completed_audit_record(
        LogAuditSinkOptions(audit_jsonl_path=audit_path, lock_path=None),
        PurgeCompletedAuditRecordRequest(
            tombstone=tombstone,
            semantic_request_digest=_purge_semantic_digest(),
        ),
    )
    append_purge_completed_audit_record(
        options,
        PurgeCompletedAuditRecordRequest(
            tombstone=tombstone,
            semantic_request_digest=_purge_semantic_digest(),
        ),
    )

    lines = _json_lines(audit_path)
    started_line = lines[1]
    failed_line = lines[2]
    completed_line = lines[3]
    assert len(lines) == 4
    assert lines[0]["event_id"] == "event-1"
    assert started_line["line_kind"] == "purge_started"
    assert started_line["source_eventlog_facts_purged"] is False
    assert started_line["purge_tombstone_ref"] is None
    assert failed_line["line_kind"] == "purge_failed"
    assert failed_line["source_eventlog_facts_purged"] is False
    assert completed_line["line_kind"] == "purge_completed"
    assert completed_line["purge_tombstone_ref"] == _PURGE_TOMBSTONE_ID
    assert completed_line["purge_tombstone_digest"] == build_purge_tombstone_digest(tombstone)
    assert completed_line["deleted_counts_digest"] == build_deleted_counts_digest(_purge_counts())
    assert completed_line["source_eventlog_facts_purged"] is True
    assert audit_json_line_marks_purged_source_eventlog_facts(started_line) is False
    assert audit_json_line_marks_purged_source_eventlog_facts(failed_line) is False
    assert audit_json_line_marks_purged_source_eventlog_facts(completed_line) is True
    assert started_result.audit_record_ref == started_line["audit_record_ref"]
    assert started_result.audit_record_digest == started_line["line_digest"]
    assert failed_result.audit_record_ref == failed_line["audit_record_ref"]
    assert completed_result.audit_record_ref == completed_line["audit_record_ref"]
    assert completed_result.audit_record_digest == completed_line["line_digest"]


def test_default_audit_path_is_derived_from_artifact_root(tmp_path: Path) -> None:
    """open_host 默认 audit JSONL 路径从 artifact_root 派生。"""

    options = default_log_audit_sink_options(
        tmp_path / "artifacts",
        create_parent_dirs=True,
    )

    assert options.audit_jsonl_path == (
        tmp_path / "artifacts" / "audit" / "host-audit.jsonl"
    )
    assert options.lock_path == (
        tmp_path / "artifacts" / "audit" / "host-audit.jsonl.lock"
    )
