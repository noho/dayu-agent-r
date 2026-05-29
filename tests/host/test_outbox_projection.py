"""Host Outbox terminal projection 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dayu.contracts.json_value import JsonValue
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
from dayu.host.durable.schema import (
    TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
)
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.outbox import (
    OUTBOX_TERMINAL_CONSUMER_ID,
    OutboxTerminalProjectionConsumer,
    build_outbox_terminal_item_identity,
    catch_up_outbox_terminal_projection,
)
from dayu.host.projection import ProjectionRunner

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


def test_run_lost_is_skipped_without_public_outbox_item(tmp_path: Path) -> None:
    """RUN_LOST 只返回 skipped detail，不创建 public terminal Outbox item。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        lost = _append_terminal_event(
            store.transaction_runner,
            event_id="event-terminal-lost",
            event_type="RUN_LOST",
            run_id="run-lost",
            payload={"reason": "worker_lost_before_terminal"},
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
