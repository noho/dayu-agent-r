"""Host Outbox terminal projection 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import canonical_json_dumps
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
from dayu.host.durable.outbox import read_outbox_terminal_item_by_event_id
from dayu.host.durable.payload import (
    PayloadDescriptor,
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.projection import (
    read_projection_checkpoint,
    read_projection_failure,
)
from dayu.host.durable.schema import (
    TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
)
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.outbox import (
    OUTBOX_TERMINAL_CONSUMER_ID,
    OutboxTerminalProjectionConsumer,
    build_outbox_terminal_item_identity,
    catch_up_outbox_terminal_projection,
)
from dayu.host.projection import (
    ProjectionApplyStatus,
    ProjectionRunner,
    projection_event_view_from_row,
)

_FIXED_NOW = datetime(2026, 5, 29, 2, 3, 4, tzinfo=UTC)
_SUMMARY_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_RESULT_DIGEST = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


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


def _append_terminal_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    event_type: str,
    run_id: str,
    payload: JsonValue,
) -> EventLogRow:
    """追加 Outbox projection 测试 terminal EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param run_id: Run id。
    :param payload: inline payload。
    :returns: 已追加 EventLog row。
    """

    return transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id="session-1",
                run_id=run_id,
                attempt_id="attempt-1",
                execution_id="execution-1",
                event_type=event_type,
                occurred_at=_FIXED_NOW,
                actor="host",
                source="unit-test",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"reason": "test"},
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
    )


def _append_diagnostic_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    event_type: str,
    run_id: str,
    payload: JsonValue,
) -> EventLogRow:
    """追加 Outbox projection 测试 diagnostic EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param run_id: Run id。
    :param payload: inline payload。
    :returns: 已追加 EventLog row。
    """

    return transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.DIAGNOSTIC,
                session_id="session-1",
                run_id=run_id,
                attempt_id="attempt-1",
                execution_id="execution-1",
                event_type=event_type,
                occurred_at=_FIXED_NOW,
                actor="host",
                source="unit-test",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"reason": "test"},
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
    )


def _run_outbox_once(
    transaction_runner: HostTransactionRunner,
    *,
    limit: int = 10,
) -> None:
    """运行一次 Outbox terminal projection。

    :param transaction_runner: Host durable transaction runner。
    :param limit: ProjectionRunner 单次扫描上限。
    :returns: ``None``。
    """

    ProjectionRunner(
        transaction_runner,
        (OutboxTerminalProjectionConsumer(),),
    ).run_once(OUTBOX_TERMINAL_CONSUMER_ID, limit=limit)


def _write_terminal_payload(
    transaction_runner: HostTransactionRunner,
    *,
    payload_ref: str,
    payload_id: str,
    content: str,
) -> PayloadDescriptor:
    """写入 Outbox projection 测试用 terminal payload。

    :param transaction_runner: Host durable transaction runner。
    :param payload_ref: descriptor ref。
    :param payload_id: SQLite payload id。
    :param content: terminal final answer content。
    :returns: 已持久化 descriptor。
    :raises HostDurableError: payload 无法写入时抛出。
    """

    return transaction_runner.run_write(
        lambda transaction: PayloadStore().write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref=payload_ref,
                payload_id=payload_id,
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json={"content": content},
            ),
        )
    )


def _table_count(
    transaction_runner: HostTransactionRunner,
    table_name: str,
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


def _reset_outbox_checkpoint(transaction_runner: HostTransactionRunner) -> None:
    """清理 Outbox checkpoint 以模拟 EventLog replay。

    :param transaction_runner: Host durable transaction runner。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: (
            transaction.execute(
                f"DELETE FROM {TABLE_HOST_PROJECTION_CHECKPOINTS} WHERE consumer_id = ?",
                (OUTBOX_TERMINAL_CONSUMER_ID.value,),
            ),
            transaction.execute(
                f"DELETE FROM {TABLE_HOST_PROJECTION_FAILURES} WHERE consumer_id = ?",
                (OUTBOX_TERMINAL_CONSUMER_ID.value,),
            ),
        )
    )


def test_terminal_item_idempotency_key_is_stable(tmp_path: Path) -> None:
    """Outbox item identity 只由 terminal identity 与结果 refs 稳定派生。"""

    first = build_outbox_terminal_item_identity(
        terminal_event_id="event-terminal",
        run_id="run-1",
        result_ref="result-ref",
        result_digest=_RESULT_DIGEST,
        terminal_summary_ref="summary-ref",
        terminal_summary_digest=_SUMMARY_DIGEST,
    )
    second = build_outbox_terminal_item_identity(
        terminal_event_id="event-terminal",
        run_id="run-1",
        result_ref="result-ref",
        result_digest=_RESULT_DIGEST,
        terminal_summary_ref="summary-ref",
        terminal_summary_digest=_SUMMARY_DIGEST,
    )

    assert first == second
    assert first.item_id.startswith("outbox-terminal-")
    assert first.idempotency_key.startswith("sha256:")


def test_provider_diagnostic_is_excluded_from_outbox_terminal_projection(
    tmp_path: Path,
) -> None:
    """PROVIDER_DIAGNOSTIC 是 diagnostic，不进入 Outbox terminal queue。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        diagnostic = _append_diagnostic_event(
            store.transaction_runner,
            event_id="event-provider-diagnostic",
            event_type="PROVIDER_DIAGNOSTIC",
            run_id="run-1",
            payload={
                "diagnostic_code": "usage_field_malformed",
                "severity": "warning",
                "message": "usage ignored",
            },
        )

        result = store.transaction_runner.run_write(
            lambda transaction: OutboxTerminalProjectionConsumer().apply_event(
                transaction,
                projection_event_view_from_row(transaction, diagnostic),
            )
        )
        item = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                diagnostic.event_id,
            )
        )

        assert result.status is ProjectionApplyStatus.SKIPPED
        assert item is None


def test_same_terminal_event_replay_does_not_duplicate(tmp_path: Path) -> None:
    """同一 terminal EventLog replay 返回 duplicate，不创建第二条 Outbox item。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        terminal = _append_terminal_event(
            store.transaction_runner,
            event_id="event-terminal-success",
            event_type="RUN_SUCCEEDED",
            run_id="run-1",
            payload={
                "final_answer": "assistant conclusion",
                "filtered": False,
                "degraded": False,
                "finish_reason": "stop",
                "result_ref": "result-ref",
                "result_digest": _RESULT_DIGEST,
                "terminal_summary_ref": "summary-ref",
                "terminal_summary_digest": _SUMMARY_DIGEST,
            },
        )

        _run_outbox_once(store.transaction_runner)
        first_row = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                terminal.event_id,
            )
        )
        _reset_outbox_checkpoint(store.transaction_runner)
        result = catch_up_outbox_terminal_projection(
            store.transaction_runner,
            batch_size=10,
        )

        second_row = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                terminal.event_id,
            )
        )
        assert first_row is not None
        assert second_row is not None
        assert second_row.item_id == first_row.item_id
        assert result.duplicates == 1
        assert _table_count(
            store.transaction_runner,
            TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
        ) == 1


def test_descriptor_only_and_inline_precedence_materialize_complete_answer(
    tmp_path: Path,
) -> None:
    """Outbox 从统一 resolver 投影 descriptor-only，并保持 inline precedence。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: content source 或 canonical metadata 漂移时抛出。
    """

    result = None
    descriptor_row = None
    inline_row = None
    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = _write_terminal_payload(
            store.transaction_runner,
            payload_ref="summary-descriptor-source",
            payload_id="sqlite-descriptor-source",
            content="descriptor answer",
        )
        descriptor_only = _append_terminal_event(
            store.transaction_runner,
            event_id="event-descriptor-only",
            event_type="RUN_SUCCEEDED",
            run_id="run-descriptor-only",
            payload={
                "terminal_summary_ref": descriptor.payload_ref,
                "terminal_summary_digest": descriptor.payload_digest,
                "filtered": False,
                "degraded": True,
                "finish_reason": "length",
            },
        )
        inline = _append_terminal_event(
            store.transaction_runner,
            event_id="event-inline-precedence",
            event_type="RUN_SUCCEEDED",
            run_id="run-inline-precedence",
            payload={
                "final_answer": "inline answer",
                "terminal_summary_ref": descriptor.payload_ref,
                "terminal_summary_digest": descriptor.payload_digest,
                "filtered": True,
                "degraded": False,
                "finish_reason": "stop",
            },
        )
        result = catch_up_outbox_terminal_projection(
            store.transaction_runner,
            batch_size=10,
        )
        descriptor_row = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                descriptor_only.event_id,
            )
        )
        inline_row = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                inline.event_id,
            )
        )

    assert result is not None
    assert result.events_applied == 2
    assert descriptor_row is not None
    assert descriptor_row.final_answer_json == canonical_json_dumps(
        {
            "content": "descriptor answer",
            "filtered": False,
            "degraded": True,
            "finish_reason": "length",
            "terminal_status": "succeeded",
        }
    )
    assert inline_row is not None
    assert inline_row.final_answer_json == canonical_json_dumps(
        {
            "content": "inline answer",
            "filtered": True,
            "degraded": False,
            "finish_reason": "stop",
            "terminal_status": "succeeded",
        }
    )


def test_failed_and_cancelled_ignore_forged_final_answer_sources(
    tmp_path: Path,
) -> None:
    """非成功 Outbox projection 不读取或提升伪造 answer/descriptor content。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: failed/cancelled row 携带 final answer 时抛出。
    """

    result = None
    failed_row = None
    cancelled_row = None
    with open_host_durable_store(_options(tmp_path)) as store:
        failed = _append_terminal_event(
            store.transaction_runner,
            event_id="event-failed-forged-answer",
            event_type="RUN_FAILED",
            run_id="run-failed-forged-answer",
            payload={
                "message": "failed",
                "final_answer": "forged",
                "content": "forged",
                "terminal_summary_ref": "missing-ref",
                "terminal_summary_digest": _SUMMARY_DIGEST,
            },
        )
        cancelled = _append_terminal_event(
            store.transaction_runner,
            event_id="event-cancelled-forged-answer",
            event_type="RUN_CANCELLED",
            run_id="run-cancelled-forged-answer",
            payload={
                "reason": "user_stop",
                "final_answer": "forged",
                "content": "forged",
                "terminal_summary_ref": "missing-ref",
                "terminal_summary_digest": _SUMMARY_DIGEST,
            },
        )
        result = catch_up_outbox_terminal_projection(
            store.transaction_runner,
            batch_size=10,
        )
        failed_row = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                failed.event_id,
            )
        )
        cancelled_row = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                cancelled.event_id,
            )
        )

    assert result is not None
    assert result.events_applied == 2
    assert failed_row is not None
    assert failed_row.final_answer_json is None
    assert cancelled_row is not None
    assert cancelled_row.final_answer_json is None


def test_descriptor_failure_rolls_back_and_same_descriptor_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    """descriptor test-only 原样恢复后完成 rollback/retry/idempotency 闭环。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: item/checkpoint 原子性或同 identity retry 失效时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = _write_terminal_payload(
            store.transaction_runner,
            payload_ref="summary-retry-same-ref",
            payload_id="sqlite-retry-same-id",
            content="retry answer",
        )
        terminal = _append_terminal_event(
            store.transaction_runner,
            event_id="event-descriptor-retry",
            event_type="RUN_SUCCEEDED",
            run_id="run-descriptor-retry",
            payload={
                "terminal_summary_ref": descriptor.payload_ref,
                "terminal_summary_digest": descriptor.payload_digest,
                "filtered": False,
                "degraded": False,
                "finish_reason": "stop",
            },
        )
        descriptor_row = store.transaction_runner.run_read(
            lambda transaction: transaction.fetchone(
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
                (descriptor.payload_ref,),
            )
        )
        assert descriptor_row is not None
        original_descriptor_values = descriptor_row.values
        original_sqlite_payload = store.transaction_runner.run_read(
            lambda transaction: transaction.fetchone(
                f"SELECT payload_json FROM {TABLE_SQLITE_PAYLOADS} WHERE payload_id = ?",
                (descriptor.sqlite_payload_id,),
            )
        )
        assert original_sqlite_payload is not None

        store.transaction_runner.run_write(
            lambda transaction: transaction.execute(
                f"DELETE FROM {TABLE_PAYLOAD_DESCRIPTORS} WHERE payload_ref = ?",
                (descriptor.payload_ref,),
            )
        )
        failed_result = catch_up_outbox_terminal_projection(
            store.transaction_runner,
            batch_size=10,
        )
        item_after_failure = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                terminal.event_id,
            )
        )
        checkpoint_after_failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
            )
        )
        failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
            )
        )

        assert failed_result.failures == 1
        assert item_after_failure is None
        assert checkpoint_after_failure is not None
        assert checkpoint_after_failure.checkpoint_event_sequence == 0
        assert failure is not None
        assert failure.failed_event_sequence == terminal.event_sequence
        assert failure.failed_event_id == terminal.event_id
        assert failure.last_error_code == "HostDurableError"
        assert "descriptor is missing" in failure.last_error_message

        store.transaction_runner.run_write(
            lambda transaction: transaction.execute(
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
                original_descriptor_values,
            )
        )
        restored_descriptor_row = store.transaction_runner.run_read(
            lambda transaction: transaction.fetchone(
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
                (descriptor.payload_ref,),
            )
        )
        restored_sqlite_payload = store.transaction_runner.run_read(
            lambda transaction: transaction.fetchone(
                f"SELECT payload_json FROM {TABLE_SQLITE_PAYLOADS} WHERE payload_id = ?",
                (descriptor.sqlite_payload_id,),
            )
        )
        assert restored_descriptor_row is not None
        assert restored_descriptor_row.values == original_descriptor_values
        assert restored_sqlite_payload == original_sqlite_payload

        retry_result = catch_up_outbox_terminal_projection(
            store.transaction_runner,
            batch_size=10,
        )
        restored_item = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                terminal.event_id,
            )
        )
        checkpoint_after_retry = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
            )
        )
        failure_after_retry = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
            )
        )
        duplicate = store.transaction_runner.run_write(
            lambda transaction: OutboxTerminalProjectionConsumer().apply_event(
                transaction,
                projection_event_view_from_row(transaction, terminal),
            )
        )
        identity_counts = store.transaction_runner.run_read(
            lambda transaction: transaction.fetchone(
                f"""
                SELECT
                  SUM(CASE WHEN terminal_event_id = ? THEN 1 ELSE 0 END)
                    AS event_count,
                  SUM(CASE WHEN item_id = ? THEN 1 ELSE 0 END)
                    AS item_count
                FROM {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}
                """,
                (terminal.event_id, restored_item.item_id if restored_item else ""),
            )
        )

        assert retry_result.events_applied == 1
        assert restored_item is not None
        assert restored_item.terminal_summary_ref == descriptor.payload_ref
        assert restored_item.terminal_summary_digest == descriptor.payload_digest
        assert checkpoint_after_retry is not None
        assert checkpoint_after_retry.checkpoint_event_sequence == terminal.event_sequence
        assert failure_after_retry is None
        assert duplicate.status is ProjectionApplyStatus.DUPLICATE
        assert identity_counts is not None
        assert identity_counts.get("event_count") == 1
        assert identity_counts.get("item_count") == 1
        assert _table_count(
            store.transaction_runner,
            TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
        ) == 1


def test_missing_required_answer_records_actionable_projection_failure(
    tmp_path: Path,
) -> None:
    """required resolver taxonomy 进入 Outbox failure row 而不写半成品。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: failure code/message 或 rollback 不符合契约时抛出。
    """

    result = None
    failure = None
    item = None
    with open_host_durable_store(_options(tmp_path)) as store:
        terminal = _append_terminal_event(
            store.transaction_runner,
            event_id="event-answer-source-missing",
            event_type="RUN_SUCCEEDED",
            run_id="run-answer-source-missing",
            payload={
                "filtered": False,
                "degraded": False,
                "finish_reason": "stop",
            },
        )
        result = catch_up_outbox_terminal_projection(
            store.transaction_runner,
            batch_size=10,
        )
        failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
            )
        )
        item = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                terminal.event_id,
            )
        )

    assert result is not None
    assert result.failures == 1
    assert item is None
    assert failure is not None
    assert failure.last_error_code == "HostDurableError"
    assert "inline answer and descriptor pair are missing" in (
        failure.last_error_message
    )


@pytest.mark.parametrize(
    ("payload", "expected_fragment"),
    (
        (
            {
                "final_answer": "answer",
                "degraded": False,
                "finish_reason": "stop",
            },
            "filtered must be bool",
        ),
        (
            {
                "final_answer": "answer",
                "filtered": 1,
                "degraded": False,
                "finish_reason": "stop",
            },
            "filtered must be bool",
        ),
        (
            {
                "final_answer": "answer",
                "filtered": False,
                "finish_reason": "stop",
            },
            "degraded must be bool",
        ),
        (
            {
                "final_answer": "answer",
                "filtered": False,
                "degraded": "false",
                "finish_reason": "stop",
            },
            "degraded must be bool",
        ),
        (
            {
                "final_answer": "answer",
                "filtered": False,
                "degraded": False,
                "finish_reason": 123,
            },
            "finish_reason",
        ),
        (
            {
                "final_answer": "answer",
                "filtered": False,
                "degraded": False,
                "finish_reason": "stop",
                "terminal_summary_ref": "one-sided-ref",
            },
            "must pair",
        ),
    ),
)
def test_succeeded_projection_rejects_invalid_metadata_or_summary_pair(
    tmp_path: Path,
    payload: JsonValue,
    expected_fragment: str,
) -> None:
    """Outbox success 对 canonical metadata 与 summary pair fail closed。

    :param tmp_path: pytest 临时目录。
    :param payload: malformed success payload。
    :param expected_fragment: failure row 期望错误片段。
    :returns: ``None``。
    :raises AssertionError: malformed success 产生半成品或推进 checkpoint 时抛出。
    """

    result = None
    failure = None
    item = None
    with open_host_durable_store(_options(tmp_path)) as store:
        terminal = _append_terminal_event(
            store.transaction_runner,
            event_id="event-invalid-success-metadata",
            event_type="RUN_SUCCEEDED",
            run_id="run-invalid-success-metadata",
            payload=payload,
        )
        result = catch_up_outbox_terminal_projection(
            store.transaction_runner,
            batch_size=10,
        )
        failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
            )
        )
        item = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                terminal.event_id,
            )
        )

    assert result is not None
    assert result.failures == 1
    assert item is None
    assert failure is not None
    assert failure.last_error_code == "HostDurableError"
    assert expected_fragment in failure.last_error_message


def test_run_lost_is_skipped_without_public_outbox_item(tmp_path: Path) -> None:
    """RUN_LOST 只返回 skipped detail，不创建 public terminal Outbox item。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        lost = _append_terminal_event(
            store.transaction_runner,
            event_id="event-terminal-lost",
            event_type="RUN_LOST",
            run_id="run-lost",
            payload={
                "reason": "worker_lost_before_terminal",
                "final_answer": "forged",
                "content": "forged",
                "terminal_summary_ref": "missing-ref",
                "terminal_summary_digest": _SUMMARY_DIGEST,
            },
        )

        result = ProjectionRunner(
            store.transaction_runner,
            (OutboxTerminalProjectionConsumer(),),
        ).run_once(OUTBOX_TERMINAL_CONSUMER_ID, limit=10)

        row = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                lost.event_id,
            )
        )
        assert row is None
        assert result.events_skipped == 1
        assert _table_count(
            store.transaction_runner,
            TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
        ) == 0
