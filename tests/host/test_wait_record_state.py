"""Host wait record durable schema、codec 与 CAS helper 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.host.api import AttemptStatus, RunStatus, SessionStatus, WaitAdapterKey
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError, HostUniqueConstraintError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_HOST_WAIT_RECORDS
from dayu.host.durable.state import (
    AttemptRow,
    ExternalJobRef,
    RunRow,
    SessionRow,
    StateMutationStatus,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    WaitSnapshotRef,
    cancel_active_wait_records_for_run,
    deserialize_wait_record_status,
    deserialize_wait_resume_policy,
    insert_attempt,
    insert_run,
    insert_session,
    insert_wait_record,
    mark_wait_record_failed_row,
    mark_wait_record_lost_row,
    mark_wait_record_resolved_row,
    read_active_wait_records_for_run,
    read_wait_record_by_id,
    serialize_wait_record_status,
    serialize_wait_resume_policy,
    wait_record_row_from_host_row,
)
from dayu.host.durable.transaction import HostRow, HostTransaction

_TIMESTAMP = "2026-05-16T00:00:00.000000Z"
_EVENT_DIGEST = "0" * 64
_SNAPSHOT_AT = datetime(2026, 5, 16, tzinfo=UTC)
_SNAPSHOT_DIGEST = "sha256:" + "1" * 64
_RESOLVE_DIGEST = "sha256:" + "2" * 64


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def _seed_run(transaction: HostTransaction, *, run_id: str = "run-1") -> None:
    """写入 wait record 测试所需 Session、Run 与 Attempt。

    :param transaction: Host transaction。
    :param run_id: Run id。
    :returns: ``None``。
    """

    session_event_sequence = _insert_event(
        transaction, event_id="event-session-created", session_id="session-1"
    )
    insert_session(
        transaction,
        SessionRow(
            session_id="session-1",
            status=SessionStatus.OPEN,
            metadata_json="{}",
            created_event_id="event-session-created",
            created_event_sequence=session_event_sequence,
            closed_event_id=None,
            closed_event_sequence=None,
            created_at=_TIMESTAMP,
            closed_at=None,
        ),
    )
    input_sequence = _insert_event(
        transaction,
        event_id=f"event-input-{run_id}",
        session_id="session-1",
        run_id=run_id,
    )
    accepted_sequence = _insert_event(
        transaction,
        event_id=f"event-accepted-{run_id}",
        session_id="session-1",
        run_id=run_id,
    )
    started_sequence = _insert_event(
        transaction,
        event_id=f"event-started-{run_id}",
        session_id="session-1",
        run_id=run_id,
    )
    insert_run(
        transaction,
        RunRow(
            run_id=run_id,
            session_id="session-1",
            status=RunStatus.WAITING,
            client_request_id=f"client-{run_id}",
            input_event_id=f"event-input-{run_id}",
            input_event_sequence=input_sequence,
            accepted_event_id=f"event-accepted-{run_id}",
            accepted_event_sequence=accepted_sequence,
            queued_event_id=None,
            queued_event_sequence=None,
            started_event_id=f"event-started-{run_id}",
            started_event_sequence=started_sequence,
            terminal_event_id=None,
            terminal_event_sequence=None,
            current_attempt_id=None,
            source_run_id=None,
            source_run_relation=None,
            execution_target="local-default",
            queue_policy="queue",
            created_at=_TIMESTAMP,
            updated_at=_TIMESTAMP,
            terminal_at=None,
        ),
    )
    attempt_sequence = _insert_event(
        transaction,
        event_id=f"event-attempt-started-{run_id}",
        session_id="session-1",
        run_id=run_id,
        attempt_id=f"attempt-{run_id}",
        execution_id=f"execution-{run_id}",
    )
    insert_attempt(
        transaction,
        AttemptRow(
            attempt_id=f"attempt-{run_id}",
            run_id=run_id,
            execution_id=f"execution-{run_id}",
            status=AttemptStatus.STARTING,
            started_event_id=f"event-attempt-started-{run_id}",
            started_event_sequence=attempt_sequence,
            terminal_event_id=None,
            terminal_event_sequence=None,
            created_at=_TIMESTAMP,
            updated_at=_TIMESTAMP,
            terminal_at=None,
        ),
    )


def _insert_event(
    transaction: HostTransaction,
    *,
    event_id: str,
    session_id: str,
    run_id: str | None = None,
    attempt_id: str | None = None,
    execution_id: str | None = None,
) -> int:
    """插入测试用 EventLog row 并返回 sequence。

    :param transaction: Host transaction。
    :param event_id: EventLog event id。
    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :returns: 插入事件的 ``event_sequence``。
    """

    result = transaction.execute(
        """
        INSERT INTO event_log (
          event_id,
          event_body_digest,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          event_type,
          occurred_at,
          actor,
          source,
          client_request_id,
          idempotency_key,
          policy_decision_json,
          reason_json,
          payload_json,
          payload_ref,
          payload_digest,
          appended_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            _EVENT_DIGEST,
            "canonical_fact",
            session_id,
            run_id,
            attempt_id,
            execution_id,
            "TEST_EVENT",
            _TIMESTAMP,
            None,
            None,
            None,
            None,
            None,
            None,
            "{}",
            None,
            None,
            _TIMESTAMP,
        ),
    )
    assert result.lastrowid is not None
    return result.lastrowid


def _wait_row(
    transaction: HostTransaction,
    *,
    wait_id: str = "wait-1",
    run_id: str = "run-1",
    status: WaitRecordStatus = WaitRecordStatus.WAITING,
) -> WaitRecordRow:
    """构造测试用 wait record row，并补齐事件引用。

    :param transaction: Host transaction。
    :param wait_id: wait record id。
    :param run_id: Run id。
    :param status: wait record 状态。
    :returns: ``WaitRecordRow``。
    """

    created_event_id = f"event-wait-created-{wait_id}"
    updated_event_id = f"event-wait-updated-{wait_id}"
    created_sequence = _insert_event(
        transaction,
        event_id=created_event_id,
        session_id="session-1",
        run_id=run_id,
        attempt_id=f"attempt-{run_id}",
        execution_id=f"execution-{run_id}",
    )
    updated_sequence = _insert_event(
        transaction,
        event_id=updated_event_id,
        session_id="session-1",
        run_id=run_id,
        attempt_id=f"attempt-{run_id}",
        execution_id=f"execution-{run_id}",
    )
    adapter_key = WaitAdapterKey("poll.primary")
    resolve_key = None
    resolve_digest = None
    terminal_at = None
    if status in (
        WaitRecordStatus.RESOLVED,
        WaitRecordStatus.FAILED,
        WaitRecordStatus.LOST,
    ):
        resolve_key = f"resolve-{wait_id}"
        resolve_digest = _RESOLVE_DIGEST
        terminal_at = _TIMESTAMP
    if status == WaitRecordStatus.CANCELLED:
        terminal_at = _TIMESTAMP
    return WaitRecordRow(
        wait_id=wait_id,
        session_id="session-1",
        run_id=run_id,
        attempt_id=f"attempt-{run_id}",
        execution_id=f"execution-{run_id}",
        tool_call_id=f"tool-call-{wait_id}",
        tool_name="earnings_lookup",
        adapter_key=adapter_key,
        await_kind="external_job",
        resume_policy=WaitResumePolicy.POLL,
        resume_token=f"resume-token-{wait_id}",
        snapshot_ref=WaitSnapshotRef(
            snapshot_id=f"snapshot-{wait_id}",
            captured_at=_SNAPSHOT_AT,
            snapshot_digest=_SNAPSHOT_DIGEST,
        ),
        external_job_ref=ExternalJobRef(
            adapter_key=adapter_key,
            external_job_id=f"external-job-{wait_id}",
        ),
        accept_idempotency_key=f"accept-{wait_id}",
        resolve_idempotency_key=resolve_key,
        resolve_semantic_digest=resolve_digest,
        deadline_at=None,
        expires_at=None,
        status=status,
        created_event_id=created_event_id,
        created_event_sequence=created_sequence,
        updated_event_id=updated_event_id,
        updated_event_sequence=updated_sequence,
        created_at=_TIMESTAMP,
        updated_at=_TIMESTAMP,
        terminal_at=terminal_at,
    )


def test_wait_record_codecs_round_trip_all_typed_fields(tmp_path: Path) -> None:
    """insert/read wait record 能 round-trip typed refs、status 与 policy。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> WaitRecordRow:
            """写入并读取 wait record。

            :param transaction: Host transaction。
            :returns: 读取回来的 wait record row。
            """

            _seed_run(transaction)
            expected = _wait_row(transaction)
            insert_wait_record(transaction, expected)
            actual = read_wait_record_by_id(transaction, "wait-1")
            assert actual is not None
            return actual

        row = store.transaction_runner.run_write(operation)
        assert row.wait_id == "wait-1"
        assert row.adapter_key == WaitAdapterKey("poll.primary")
        assert row.resume_policy == WaitResumePolicy.POLL
        assert row.status == WaitRecordStatus.WAITING
        assert row.snapshot_ref == WaitSnapshotRef(
            snapshot_id="snapshot-wait-1",
            captured_at=_SNAPSHOT_AT,
            snapshot_digest=_SNAPSHOT_DIGEST,
        )
        assert row.external_job_ref == ExternalJobRef(
            adapter_key=WaitAdapterKey("poll.primary"),
            external_job_id="external-job-wait-1",
        )


def test_wait_record_status_and_policy_codecs_are_closed() -> None:
    """wait record status 与 resume policy codec 使用封闭 enum。"""

    assert serialize_wait_record_status(WaitRecordStatus.LOST) == "lost"
    assert deserialize_wait_record_status("lost") == WaitRecordStatus.LOST
    assert serialize_wait_resume_policy(WaitResumePolicy.CALLBACK) == "callback"
    assert deserialize_wait_resume_policy("manual") == WaitResumePolicy.MANUAL
    with pytest.raises(HostDurableError, match="WaitRecordStatus"):
        deserialize_wait_record_status("pending")


def test_unique_active_wait_per_run_allows_terminal_history(
    tmp_path: Path,
) -> None:
    """同一 Run 只能有一个 waiting wait，但允许 terminal 历史 wait。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def seed(transaction: HostTransaction) -> None:
            """写入一个 active wait 和一个 terminal wait。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction, wait_id="wait-1"))
            insert_wait_record(
                transaction,
                _wait_row(
                    transaction,
                    wait_id="wait-terminal",
                    status=WaitRecordStatus.RESOLVED,
                ),
            )

        def duplicate_waiting(transaction: HostTransaction) -> None:
            """尝试写入第二个 active wait。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            insert_wait_record(transaction, _wait_row(transaction, wait_id="wait-2"))

        store.transaction_runner.run_write(seed)
        with pytest.raises(HostUniqueConstraintError):
            store.transaction_runner.run_write(duplicate_waiting)


def test_wait_record_ddl_length_checks_reject_overlong_refs(
    tmp_path: Path,
) -> None:
    """SQLite DDL CHECK 拒绝超长 adapter、snapshot、external job 与 key。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """绕过 dataclass 直接触发 DDL CHECK。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _seed_run(transaction)
            row = _wait_row(transaction)
            transaction.execute(
                f"""
                INSERT INTO {TABLE_HOST_WAIT_RECORDS} (
                  wait_id,
                  session_id,
                  run_id,
                  attempt_id,
                  execution_id,
                  tool_call_id,
                  tool_name,
                  adapter_key,
                  await_kind,
                  resume_policy,
                  resume_token,
                  snapshot_ref,
                  snapshot_captured_at,
                  snapshot_digest,
                  external_job_id,
                  accept_idempotency_key,
                  resolve_idempotency_key,
                  resolve_semantic_digest,
                  deadline_at,
                  expires_at,
                  status,
                  created_event_id,
                  created_event_sequence,
                  updated_event_id,
                  updated_event_sequence,
                  created_at,
                  updated_at,
                  terminal_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.wait_id,
                    row.session_id,
                    row.run_id,
                    row.attempt_id,
                    row.execution_id,
                    row.tool_call_id,
                    row.tool_name,
                    "a" * 129,
                    row.await_kind,
                    serialize_wait_resume_policy(row.resume_policy),
                    row.resume_token,
                    "s" * 257,
                    _TIMESTAMP,
                    row.snapshot_ref.snapshot_digest if row.snapshot_ref else None,
                    "j" * 513,
                    "i" * 257,
                    None,
                    None,
                    None,
                    None,
                    serialize_wait_record_status(row.status),
                    row.created_event_id,
                    row.created_event_sequence,
                    row.updated_event_id,
                    row.updated_event_sequence,
                    row.created_at,
                    row.updated_at,
                    row.terminal_at,
                ),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


def test_wait_record_ddl_rejects_orphan_snapshot_digest(
    tmp_path: Path,
) -> None:
    """SQLite DDL CHECK 拒绝无 snapshot ref 的 orphan snapshot digest。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """绕过 dataclass 写入 orphan snapshot digest。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _seed_run(transaction)
            row = _wait_row(transaction)
            transaction.execute(
                f"""
                INSERT INTO {TABLE_HOST_WAIT_RECORDS} (
                  wait_id,
                  session_id,
                  run_id,
                  attempt_id,
                  execution_id,
                  tool_call_id,
                  tool_name,
                  adapter_key,
                  await_kind,
                  resume_policy,
                  resume_token,
                  snapshot_ref,
                  snapshot_captured_at,
                  snapshot_digest,
                  external_job_id,
                  accept_idempotency_key,
                  resolve_idempotency_key,
                  resolve_semantic_digest,
                  deadline_at,
                  expires_at,
                  status,
                  created_event_id,
                  created_event_sequence,
                  updated_event_id,
                  updated_event_sequence,
                  created_at,
                  updated_at,
                  terminal_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "wait-orphan-digest",
                    row.session_id,
                    row.run_id,
                    row.attempt_id,
                    row.execution_id,
                    row.tool_call_id,
                    row.tool_name,
                    row.adapter_key.value,
                    row.await_kind,
                    serialize_wait_resume_policy(row.resume_policy),
                    row.resume_token,
                    None,
                    None,
                    _SNAPSHOT_DIGEST,
                    row.external_job_ref.external_job_id
                    if row.external_job_ref
                    else None,
                    row.accept_idempotency_key,
                    None,
                    None,
                    None,
                    None,
                    serialize_wait_record_status(row.status),
                    row.created_event_id,
                    row.created_event_sequence,
                    row.updated_event_id,
                    row.updated_event_sequence,
                    row.created_at,
                    row.updated_at,
                    row.terminal_at,
                ),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


def test_wait_record_cas_helpers_update_waiting_only(tmp_path: Path) -> None:
    """CAS helper 只更新 waiting wait，并区分 updated/not_found/invalid_state。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(
            transaction: HostTransaction,
        ) -> tuple[StateMutationStatus, StateMutationStatus, StateMutationStatus]:
            """执行单条 wait record CAS helper。

            :param transaction: Host transaction。
            :returns: 三次 mutation 状态。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            updated = mark_wait_record_resolved_row(
                transaction,
                wait_id="wait-1",
                resolve_idempotency_key="resolve-1",
                resolve_semantic_digest=_RESOLVE_DIGEST,
                updated_event_id="event-wait-updated-wait-1",
                updated_event_sequence=4,
                updated_at=_TIMESTAMP,
                terminal_at=_TIMESTAMP,
            )
            invalid = mark_wait_record_failed_row(
                transaction,
                wait_id="wait-1",
                resolve_idempotency_key="resolve-2",
                resolve_semantic_digest=_RESOLVE_DIGEST,
                updated_event_id="event-wait-updated-wait-1",
                updated_event_sequence=4,
                updated_at=_TIMESTAMP,
                terminal_at=_TIMESTAMP,
            )
            missing = mark_wait_record_lost_row(
                transaction,
                wait_id="wait-missing",
                resolve_idempotency_key="resolve-missing",
                resolve_semantic_digest=_RESOLVE_DIGEST,
                updated_event_id="event-wait-updated-wait-1",
                updated_event_sequence=4,
                updated_at=_TIMESTAMP,
                terminal_at=_TIMESTAMP,
            )
            return updated.status, invalid.status, missing.status

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED,
            StateMutationStatus.INVALID_STATE,
            StateMutationStatus.NOT_FOUND,
        )


def test_cancel_active_wait_records_for_run_updates_waiting_rows(
    tmp_path: Path,
) -> None:
    """批量 cancel helper 只取消 Run 下 active waiting wait records。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> tuple[StateMutationStatus, int]:
            """执行批量 cancel helper。

            :param transaction: Host transaction。
            :returns: mutation 状态与 active wait 数量。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            result = cancel_active_wait_records_for_run(
                transaction,
                run_id="run-1",
                updated_event_id="event-wait-updated-wait-1",
                updated_event_sequence=4,
                updated_at=_TIMESTAMP,
                terminal_at=_TIMESTAMP,
            )
            active_after = read_active_wait_records_for_run(transaction, "run-1")
            return result.status, len(active_after)

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED,
            0,
        )


def test_wait_record_row_from_host_row_rejects_invalid_status() -> None:
    """row codec 拒绝不属于 WaitRecordStatus 的状态文本。"""

    row = HostRow(
        columns=(
            "wait_id",
            "session_id",
            "run_id",
            "attempt_id",
            "execution_id",
            "tool_call_id",
            "tool_name",
            "adapter_key",
            "await_kind",
            "resume_policy",
            "resume_token",
            "snapshot_ref",
            "snapshot_captured_at",
            "snapshot_digest",
            "external_job_id",
            "accept_idempotency_key",
            "resolve_idempotency_key",
            "resolve_semantic_digest",
            "deadline_at",
            "expires_at",
            "status",
            "created_event_id",
            "created_event_sequence",
            "updated_event_id",
            "updated_event_sequence",
            "created_at",
            "updated_at",
            "terminal_at",
        ),
        values=(
            "wait-1",
            "session-1",
            "run-1",
            "attempt-1",
            "execution-1",
            "tool-call-1",
            "tool",
            "manual",
            "external_job",
            "manual",
            "resume-token",
            None,
            None,
            None,
            None,
            "accept-1",
            None,
            None,
            None,
            None,
            "pending",
            "event-created",
            1,
            "event-updated",
            2,
            _TIMESTAMP,
            _TIMESTAMP,
            None,
        ),
    )

    with pytest.raises(HostDurableError, match="WaitRecordStatus"):
        wait_record_row_from_host_row(row)
