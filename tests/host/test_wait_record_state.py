"""Host wait record durable schema、codec 与 CAS helper 测试。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.host.api import AttemptStatus, RunStatus, SessionStatus, WaitAdapterKey
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError, HostRowDecodeError, HostUniqueConstraintError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_HOST_WAIT_RECORDS
from dayu.host.queue_policy import RunQueuePolicy
from dayu.host.durable.state import (
    AttemptRow,
    ExternalJobRef,
    RunRow,
    SessionRow,
    StateMutationStatus,
    WaitRecordRow,
    WaitRecordStatus,
    WaitPollLastOutcome,
    WaitResumePolicy,
    WaitSnapshotRef,
    cancel_active_wait_records_for_run,
    claim_wait_record_for_poll,
    deserialize_wait_poll_last_outcome,
    deserialize_wait_record_status,
    deserialize_wait_resume_policy,
    deserialize_wait_snapshot_ref,
    insert_attempt,
    insert_run,
    insert_session,
    insert_wait_record,
    mark_wait_record_failed_row,
    mark_wait_record_lost_row,
    mark_wait_record_poll_abandoned,
    mark_wait_record_resolved_row,
    read_active_wait_records_for_run,
    read_wait_record_by_id,
    release_wait_record_poll_claim,
    serialize_wait_poll_last_outcome,
    serialize_wait_record_status,
    serialize_wait_resume_policy,
    wait_record_row_from_host_row,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, SQLiteScalar

_TIMESTAMP = "2026-05-16T00:00:00.000000Z"
_EARLIER_TIMESTAMP = "2026-05-16T00:00:10.000000Z"
_LATER_TIMESTAMP = "2026-05-16T00:01:00.000000Z"
_FUTURE_TIMESTAMP = "2026-05-16T00:05:00.000000Z"
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
            cancel_request_event_id=None,
            current_attempt_id=None,
            source_run_id=None,
            source_run_relation=None,
            execution_target="local-default",
            queue_policy=RunQueuePolicy.QUEUE,
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
            "USER_INPUT_ACCEPTED",
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
        assert row.poll_claim_id is None
        assert row.poll_claim_owner_id is None
        assert row.poll_claimed_at is None
        assert row.poll_claim_expires_at is None
        assert row.poll_next_observe_at is None
        assert row.poll_backoff_attempt == 0
        assert row.poll_last_outcome is None
        assert row.poll_last_error_code is None
        assert row.poll_last_error_message is None
        assert row.poll_abandoned_at is None


def test_wait_snapshot_ref_rejects_invalid_digest() -> None:
    """WaitSnapshotRef 构造阶段拒绝无效 digest，避免把不完整引用推迟到 SQLite 才失败。

    :returns: ``None``。
    """

    with pytest.raises(HostDurableError, match="snapshot_digest must be sha256 digest"):
        WaitSnapshotRef(
            snapshot_id="snapshot-1",
            captured_at=_SNAPSHOT_AT,
            snapshot_digest="not-a-digest",
        )


def test_deserialize_wait_snapshot_ref_rejects_missing_digest() -> None:
    """wait snapshot 三列反序列化阶段拒绝缺失 digest 的不完整引用。

    :returns: ``None``。
    """

    with pytest.raises(HostDurableError, match="snapshot ref columns must be paired"):
        deserialize_wait_snapshot_ref(
            "snapshot-1",
            "2026-05-16T00:00:00.000000Z",
            None,
        )


def test_wait_record_status_and_policy_codecs_are_closed() -> None:
    """wait record status 与 resume policy codec 使用封闭 enum。"""

    assert serialize_wait_record_status(WaitRecordStatus.LOST) == "lost"
    assert deserialize_wait_record_status("lost") == WaitRecordStatus.LOST
    assert serialize_wait_resume_policy(WaitResumePolicy.CALLBACK) == "callback"
    assert deserialize_wait_resume_policy("manual") == WaitResumePolicy.MANUAL
    with pytest.raises(HostDurableError, match="WaitRecordStatus"):
        deserialize_wait_record_status("pending")


def test_wait_poll_terminal_outcome_codecs_roundtrip_new_values() -> None:
    """新增 Host wait poll outcome 使用 StrEnum value roundtrip。"""

    assert (
        serialize_wait_poll_last_outcome(WaitPollLastOutcome.BOUNDARY_REJECTED)
        == "boundary_rejected"
    )
    assert (
        deserialize_wait_poll_last_outcome("boundary_rejected")
        is WaitPollLastOutcome.BOUNDARY_REJECTED
    )
    assert (
        serialize_wait_poll_last_outcome(WaitPollLastOutcome.ABANDON_UNSUPPORTED)
        == "abandon_unsupported"
    )
    assert (
        deserialize_wait_poll_last_outcome("abandon_unsupported")
        is WaitPollLastOutcome.ABANDON_UNSUPPORTED
    )
    assert (
        serialize_wait_poll_last_outcome(WaitPollLastOutcome.ABANDON_NOOP)
        == "abandon_noop"
    )
    assert (
        deserialize_wait_poll_last_outcome("abandon_noop")
        is WaitPollLastOutcome.ABANDON_NOOP
    )


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


def test_wait_record_ddl_rejects_waiting_terminal_at(
    tmp_path: Path,
) -> None:
    """WaitRecord DDL CHECK 拒绝 waiting row 携带 terminal_at。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: DDL CHECK 未拒绝非法形状时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """写入合法 waiting wait 后补入 terminal_at。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            transaction.execute(
                f"UPDATE {TABLE_HOST_WAIT_RECORDS} SET terminal_at = ? WHERE wait_id = ?",
                (_TIMESTAMP, "wait-1"),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


def test_wait_record_ddl_rejects_terminal_missing_terminal_at(
    tmp_path: Path,
) -> None:
    """WaitRecord DDL CHECK 拒绝 terminal row 缺少 terminal_at。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: DDL CHECK 未拒绝非法形状时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """写入合法 waiting wait 后尝试改为缺 terminal_at 的 resolved。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_WAIT_RECORDS}
                SET status = ?,
                    resolve_idempotency_key = ?,
                    resolve_semantic_digest = ?
                WHERE wait_id = ?
                """,
                (
                    serialize_wait_record_status(WaitRecordStatus.RESOLVED),
                    "resolve-1",
                    _RESOLVE_DIGEST,
                    "wait-1",
                ),
            )

        with pytest.raises(HostDurableError, match="CHECK constraint"):
            store.transaction_runner.run_write(operation)


def test_wait_record_python_validation_rejects_terminal_at_shape(
    tmp_path: Path,
) -> None:
    """WaitRecord Python insert validation 与 DDL terminal_at 形状一致。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Python validation 未拒绝非法形状时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def waiting_with_terminal_at(transaction: HostTransaction) -> None:
            """尝试插入携带 terminal_at 的 waiting wait。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _seed_run(transaction)
            insert_wait_record(
                transaction,
                replace(_wait_row(transaction), terminal_at=_TIMESTAMP),
            )

        def terminal_without_terminal_at(transaction: HostTransaction) -> None:
            """尝试插入缺少 terminal_at 的 resolved wait。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _seed_run(transaction, run_id="run-2")
            insert_wait_record(
                transaction,
                replace(
                    _wait_row(
                        transaction,
                        wait_id="wait-2",
                        run_id="run-2",
                        status=WaitRecordStatus.RESOLVED,
                    ),
                    terminal_at=None,
                ),
            )

        with pytest.raises(HostDurableError, match="waiting wait record terminal_at"):
            store.transaction_runner.run_write(waiting_with_terminal_at)
        with pytest.raises(HostDurableError, match="terminal wait record requires terminal_at"):
            store.transaction_runner.run_write(terminal_without_terminal_at)


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


def test_poll_claim_acquires_eligible_waiting_row(tmp_path: Path) -> None:
    """poll claim helper 原子 claim eligible waiting poll row。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> WaitRecordRow:
            """写入 waiting wait 并取得 poll claim。

            :param transaction: Host transaction。
            :returns: claim 后的 wait record。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            result = claim_wait_record_for_poll(
                transaction,
                claim_id="claim-1",
                owner_id="poller-1",
                now=_TIMESTAMP,
                claim_expires_at=_LATER_TIMESTAMP,
            )
            assert result.status is StateMutationStatus.UPDATED
            assert result.row is not None
            return result.row

        row = store.transaction_runner.run_write(operation)
        assert row.poll_claim_id == "claim-1"
        assert row.poll_claim_owner_id == "poller-1"
        assert row.poll_claimed_at == _TIMESTAMP
        assert row.poll_claim_expires_at == _LATER_TIMESTAMP


def test_poll_claim_skips_future_next_observe_and_active_claim(
    tmp_path: Path,
) -> None:
    """poll claim helper 跳过未到期 backoff 与未过期 claim。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> tuple[StateMutationStatus, StateMutationStatus]:
            """构造未来 backoff 与 active claim 后尝试 claim。

            :param transaction: Host transaction。
            :returns: 两次 claim 状态。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_WAIT_RECORDS}
                SET poll_next_observe_at = ?
                WHERE wait_id = ?
                """,
                (_FUTURE_TIMESTAMP, "wait-1"),
            )
            future_backoff = claim_wait_record_for_poll(
                transaction,
                claim_id="claim-future",
                owner_id="poller-1",
                now=_TIMESTAMP,
                claim_expires_at=_LATER_TIMESTAMP,
            )
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_WAIT_RECORDS}
                SET poll_next_observe_at = NULL,
                    poll_claim_id = ?,
                    poll_claim_owner_id = ?,
                    poll_claimed_at = ?,
                    poll_claim_expires_at = ?
                WHERE wait_id = ?
                """,
                ("claim-active", "poller-active", _TIMESTAMP, _FUTURE_TIMESTAMP, "wait-1"),
            )
            active_claim = claim_wait_record_for_poll(
                transaction,
                claim_id="claim-conflict",
                owner_id="poller-2",
                now=_LATER_TIMESTAMP,
                claim_expires_at=_FUTURE_TIMESTAMP,
            )
            return future_backoff.status, active_claim.status

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.NOT_FOUND,
            StateMutationStatus.NOT_FOUND,
        )


def test_poll_claim_acquires_expired_claim(tmp_path: Path) -> None:
    """poll claim helper 可接管已过期 claim。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> WaitRecordRow:
            """构造过期 claim 后重新 claim。

            :param transaction: Host transaction。
            :returns: 接管后的 wait record。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_WAIT_RECORDS}
                SET poll_claim_id = ?,
                    poll_claim_owner_id = ?,
                    poll_claimed_at = ?,
                    poll_claim_expires_at = ?
                WHERE wait_id = ?
                """,
                ("claim-old", "poller-old", _EARLIER_TIMESTAMP, _LATER_TIMESTAMP, "wait-1"),
            )
            result = claim_wait_record_for_poll(
                transaction,
                claim_id="claim-new",
                owner_id="poller-new",
                now=_FUTURE_TIMESTAMP,
                claim_expires_at="2026-05-16T00:06:00.000000Z",
            )
            assert result.status is StateMutationStatus.UPDATED
            assert result.row is not None
            return result.row

        row = store.transaction_runner.run_write(operation)
        assert row.poll_claim_id == "claim-new"
        assert row.poll_claim_owner_id == "poller-new"


def test_stale_poll_release_cannot_clear_newer_claim(tmp_path: Path) -> None:
    """旧 claim release 不能清除新的 poll claim。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> tuple[StateMutationStatus, WaitRecordRow]:
            """构造新 claim 后用旧 claim 尝试 release。

            :param transaction: Host transaction。
            :returns: release 状态与最新 wait row。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_WAIT_RECORDS}
                SET poll_claim_id = ?,
                    poll_claim_owner_id = ?,
                    poll_claimed_at = ?,
                    poll_claim_expires_at = ?
                WHERE wait_id = ?
                """,
                ("claim-new", "poller-new", _TIMESTAMP, _FUTURE_TIMESTAMP, "wait-1"),
            )
            release = release_wait_record_poll_claim(
                transaction,
                wait_id="wait-1",
                claim_id="claim-old",
                next_observe_at=_FUTURE_TIMESTAMP,
                backoff_attempt=1,
                last_outcome=WaitPollLastOutcome.NOT_READY,
                last_error_code=None,
                last_error_message=None,
                updated_at=_TIMESTAMP,
            )
            latest = read_wait_record_by_id(transaction, "wait-1")
            assert latest is not None
            return release.status, latest

        status, row = store.transaction_runner.run_write(operation)
        assert status is StateMutationStatus.CAS_LOST
        assert row.poll_claim_id == "claim-new"
        assert row.poll_next_observe_at is None


def test_cancelled_poll_abandoned_row_is_not_eligible(tmp_path: Path) -> None:
    """已标记 poll_abandoned_at 的 cancelled wait 不再 eligible。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> StateMutationStatus:
            """构造已 abandoned cancelled wait 后尝试 claim。

            :param transaction: Host transaction。
            :returns: claim 状态。
            """

            _seed_run(transaction)
            insert_wait_record(
                transaction,
                _wait_row(
                    transaction,
                    status=WaitRecordStatus.CANCELLED,
                ),
            )
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_WAIT_RECORDS}
                SET poll_abandoned_at = ?
                WHERE wait_id = ?
                """,
                (_TIMESTAMP, "wait-1"),
            )
            result = claim_wait_record_for_poll(
                transaction,
                claim_id="claim-after-abandon",
                owner_id="poller-1",
                now=_LATER_TIMESTAMP,
                claim_expires_at=_FUTURE_TIMESTAMP,
            )
            return result.status

        assert store.transaction_runner.run_write(operation) is StateMutationStatus.NOT_FOUND


def test_cancelled_poll_timeout_release_preserves_claimability_after_due(
    tmp_path: Path,
) -> None:
    """cancelled wait timeout release 后保持非终态并可在到期时再次 claim。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> tuple[WaitRecordRow, WaitRecordRow]:
            """claim、release cancelled wait，再在 due 时重新 claim。

            :param transaction: Host transaction。
            :returns: release 后与重新 claim 后的 wait row。
            """

            _seed_run(transaction)
            insert_wait_record(
                transaction,
                _wait_row(transaction, status=WaitRecordStatus.CANCELLED),
            )
            claimed = claim_wait_record_for_poll(
                transaction,
                claim_id="claim-timeout",
                owner_id="poller-timeout",
                now=_TIMESTAMP,
                claim_expires_at=_LATER_TIMESTAMP,
            )
            assert claimed.status is StateMutationStatus.UPDATED
            released = release_wait_record_poll_claim(
                transaction,
                wait_id="wait-1",
                claim_id="claim-timeout",
                next_observe_at=_LATER_TIMESTAMP,
                backoff_attempt=1,
                last_outcome=WaitPollLastOutcome.ABANDON_ERROR,
                last_error_code="wait_abandon_timeout",
                last_error_message="wait adapter abandon exceeded Host time budget",
                updated_at=_TIMESTAMP,
            )
            assert released.status is StateMutationStatus.UPDATED
            assert released.row is not None
            retry = claim_wait_record_for_poll(
                transaction,
                claim_id="claim-retry",
                owner_id="poller-retry",
                now=_LATER_TIMESTAMP,
                claim_expires_at=_FUTURE_TIMESTAMP,
            )
            assert retry.status is StateMutationStatus.UPDATED
            assert retry.row is not None
            return released.row, retry.row

        released_row, retry_row = store.transaction_runner.run_write(operation)
        assert released_row.status is WaitRecordStatus.CANCELLED
        assert released_row.poll_claim_id is None
        assert released_row.poll_claim_owner_id is None
        assert released_row.poll_claimed_at is None
        assert released_row.poll_claim_expires_at is None
        assert released_row.poll_next_observe_at == _LATER_TIMESTAMP
        assert released_row.poll_backoff_attempt == 1
        assert released_row.poll_last_outcome is WaitPollLastOutcome.ABANDON_ERROR
        assert released_row.poll_last_error_code == "wait_abandon_timeout"
        assert released_row.poll_abandoned_at is None
        assert retry_row.poll_claim_id == "claim-retry"
        assert retry_row.poll_claim_owner_id == "poller-retry"
        assert retry_row.poll_backoff_attempt == 1
        assert retry_row.poll_abandoned_at is None


@pytest.mark.parametrize(
    "last_outcome",
    (
        WaitPollLastOutcome.ABANDONED,
        WaitPollLastOutcome.ABANDON_UNSUPPORTED,
        WaitPollLastOutcome.ABANDON_NOOP,
    ),
)
def test_poll_abandon_success_marks_row_and_clears_claim(
    tmp_path: Path, last_outcome: WaitPollLastOutcome
) -> None:
    """poll abandon success CAS 写入 durable marker 并清理 claim / backoff。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> WaitRecordRow:
            """claim cancelled wait 后标记 abandon success。

            :param transaction: Host transaction。
            :returns: abandon 后 wait row。
            """

            _seed_run(transaction)
            insert_wait_record(
                transaction,
                _wait_row(transaction, status=WaitRecordStatus.CANCELLED),
            )
            claimed = claim_wait_record_for_poll(
                transaction,
                claim_id="claim-abandon",
                owner_id="poller-1",
                now=_TIMESTAMP,
                claim_expires_at=_LATER_TIMESTAMP,
            )
            assert claimed.status is StateMutationStatus.UPDATED
            abandoned = mark_wait_record_poll_abandoned(
                transaction,
                wait_id="wait-1",
                claim_id="claim-abandon",
                abandoned_at=_LATER_TIMESTAMP,
                updated_at=_LATER_TIMESTAMP,
                last_outcome=last_outcome,
            )
            assert abandoned.status is StateMutationStatus.UPDATED
            assert abandoned.row is not None
            return abandoned.row

        row = store.transaction_runner.run_write(operation)
        assert row.poll_abandoned_at == _LATER_TIMESTAMP
        assert row.poll_claim_id is None
        assert row.poll_last_outcome is last_outcome


def test_wait_record_terminal_transition_clears_poll_claim(tmp_path: Path) -> None:
    """wait terminal CAS 清除 poll claim 字段。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> WaitRecordRow:
            """claim waiting wait 后标记 resolved。

            :param transaction: Host transaction。
            :returns: terminal wait row。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            claim_wait_record_for_poll(
                transaction,
                claim_id="claim-terminal",
                owner_id="poller-1",
                now=_TIMESTAMP,
                claim_expires_at=_LATER_TIMESTAMP,
            )
            result = mark_wait_record_resolved_row(
                transaction,
                wait_id="wait-1",
                resolve_idempotency_key="resolve-1",
                resolve_semantic_digest=_RESOLVE_DIGEST,
                updated_event_id="event-wait-updated-wait-1",
                updated_event_sequence=4,
                updated_at=_LATER_TIMESTAMP,
                terminal_at=_LATER_TIMESTAMP,
            )
            assert result.status is StateMutationStatus.UPDATED
            assert result.row is not None
            return result.row

        row = store.transaction_runner.run_write(operation)
        assert row.status is WaitRecordStatus.RESOLVED
        assert row.poll_claim_id is None
        assert row.poll_claim_owner_id is None
        assert row.poll_claimed_at is None
        assert row.poll_claim_expires_at is None


def test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at(
    tmp_path: Path,
) -> None:
    """terminal CAS 拒绝测试专用 corrupted waiting + terminal_at row。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal CAS 未拒绝 corrupted row 时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(transaction: HostTransaction) -> None:
            """绕过 CHECK 构造 corrupted wait row 并执行 terminal CAS。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostRowDecodeError: corrupted wait row 被读取时抛出。
            """

            _seed_run(transaction)
            insert_wait_record(transaction, _wait_row(transaction))
            transaction.execute("PRAGMA ignore_check_constraints=ON")
            transaction.execute(
                f"UPDATE {TABLE_HOST_WAIT_RECORDS} SET terminal_at = ? WHERE wait_id = ?",
                (_TIMESTAMP, "wait-1"),
            )
            transaction.execute("PRAGMA ignore_check_constraints=OFF")
            mark_wait_record_resolved_row(
                transaction,
                wait_id="wait-1",
                resolve_idempotency_key="resolve-1",
                resolve_semantic_digest=_RESOLVE_DIGEST,
                updated_event_id="event-wait-updated-wait-1",
                updated_event_sequence=4,
                updated_at=_TIMESTAMP,
                terminal_at=_TIMESTAMP,
            )

        with pytest.raises(HostRowDecodeError, match="waiting wait record terminal_at") as error_info:
            store.transaction_runner.run_write(operation)
        _assert_host_row_decode_error(
            error_info.value,
            row_name=TABLE_HOST_WAIT_RECORDS,
            field_name=None,
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
    """row codec 拒绝不属于 WaitRecordStatus 的状态文本。

    :returns: ``None``。
    :raises AssertionError: 未抛出 ``HostRowDecodeError`` 或错误属性不符合预期时抛出。
    """

    with pytest.raises(HostRowDecodeError, match="WaitRecordStatus") as error_info:
        wait_record_row_from_host_row(_wait_record_host_row(status="pending"))

    _assert_host_row_decode_error(
        error_info.value,
        row_name=TABLE_HOST_WAIT_RECORDS,
        field_name="status",
    )


def test_wait_record_row_decode_missing_terminal_at_column_raises_row_decode_error() -> None:
    """WaitRecord row decode 缺少 terminal_at 列时抛出稳定 row decode 错误。

    :returns: ``None``。
    :raises AssertionError: 未抛出 ``HostRowDecodeError`` 或错误属性不符合预期时抛出。
    """

    with pytest.raises(HostRowDecodeError) as error_info:
        wait_record_row_from_host_row(_wait_record_host_row(include_terminal_at_column=False))

    _assert_host_row_decode_error(
        error_info.value,
        row_name=TABLE_HOST_WAIT_RECORDS,
        field_name="terminal_at",
    )


def test_wait_record_row_decode_terminal_at_shape_raises_row_decode_error() -> None:
    """WaitRecord row decode 拒绝 waiting/terminal 与 terminal_at 形状不一致。

    :returns: ``None``。
    :raises AssertionError: 未抛出 ``HostRowDecodeError`` 或错误属性不符合预期时抛出。
    """

    with pytest.raises(HostRowDecodeError, match="waiting wait record terminal_at") as waiting_error:
        wait_record_row_from_host_row(
            _wait_record_host_row(
                status=serialize_wait_record_status(WaitRecordStatus.WAITING),
                terminal_at=_TIMESTAMP,
            )
        )
    with pytest.raises(HostRowDecodeError, match="terminal wait record requires terminal_at") as terminal_error:
        wait_record_row_from_host_row(
            _wait_record_host_row(
                status=serialize_wait_record_status(WaitRecordStatus.RESOLVED),
                terminal_at=None,
            )
        )

    _assert_host_row_decode_error(
        waiting_error.value,
        row_name=TABLE_HOST_WAIT_RECORDS,
        field_name=None,
    )
    _assert_host_row_decode_error(
        terminal_error.value,
        row_name=TABLE_HOST_WAIT_RECORDS,
        field_name=None,
    )


def _assert_host_row_decode_error(
    error: HostDurableError,
    *,
    row_name: str,
    field_name: str | None,
) -> None:
    """断言错误保持 durable row decode 边界属性。

    :param error: 捕获到的 durable 错误。
    :param row_name: 期望的 row 名称。
    :param field_name: 期望的字段名；row 级形状错误时为 ``None``。
    :returns: ``None``。
    :raises AssertionError: 错误类型、属性或消息不符合预期时抛出。
    """

    assert isinstance(error, HostDurableError)
    assert isinstance(error, HostRowDecodeError)
    assert error.row_name == row_name
    assert error.field_name == field_name
    assert row_name in str(error)
    if field_name is not None:
        assert field_name in str(error)


def _wait_record_host_row(
    *,
    status: str = "waiting",
    terminal_at: str | None = None,
    include_terminal_at_column: bool = True,
) -> HostRow:
    """构造 WaitRecord row codec 测试用 HostRow。

    :param status: status 列文本。
    :param terminal_at: terminal timestamp。
    :param include_terminal_at_column: 是否包含 terminal_at 列。
    :returns: ``HostRow``。
    :raises AssertionError: 本 helper 不主动触发断言。
    """

    columns: tuple[str, ...] = (
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
        "poll_claim_id",
        "poll_claim_owner_id",
        "poll_claimed_at",
        "poll_claim_expires_at",
        "poll_next_observe_at",
        "poll_backoff_attempt",
        "poll_last_outcome",
        "poll_last_error_code",
        "poll_last_error_message",
        "poll_abandoned_at",
        "status",
        "created_event_id",
        "created_event_sequence",
        "updated_event_id",
        "updated_event_sequence",
        "created_at",
        "updated_at",
        "terminal_at",
    )
    values: tuple[SQLiteScalar, ...] = (
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
        None,
        None,
        None,
        None,
        None,
        0,
        None,
        None,
        None,
        None,
        status,
        "event-created",
        1,
        "event-updated",
        2,
        _TIMESTAMP,
        _TIMESTAMP,
        terminal_at,
    )
    if include_terminal_at_column:
        return HostRow(columns=columns, values=values)
    return HostRow(columns=columns[:-1], values=values[:-1])
