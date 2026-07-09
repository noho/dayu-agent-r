"""Host Outbox durable helper 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError, HostIdempotencyConflictError
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
from dayu.host.durable.outbox import (
    OutboxTerminalItemRow,
    OutboxTerminalProjectionStatus,
    drain_outbox_terminal_items,
    insert_outbox_terminal_item_if_absent,
    read_outbox_terminal_projection_state,
    read_outbox_terminal_item_by_event_id,
    read_outbox_terminal_items_after,
)
from dayu.host.durable.projection import advance_projection_checkpoint
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.outbox import (
    OUTBOX_TERMINAL_CONSUMER_ID,
    build_outbox_terminal_item_identity,
)

_FIXED_NOW = datetime(2026, 5, 29, 2, 3, 4, tzinfo=UTC)
_NOW_TEXT = "2026-05-29T02:03:04.000000Z"
_DRAINED_AT = "2026-05-29T02:04:05.000000Z"
_SUMMARY_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


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
    run_id: str,
    payload: JsonValue,
    event_type: str = "RUN_SUCCEEDED",
) -> EventLogRow:
    """追加 Outbox durable 测试用 EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param run_id: Run id。
    :param payload: inline payload。
    :param event_type: EventLog type。
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
                attempt_id=None,
                execution_id=None,
                event_type=event_type,
                occurred_at=_FIXED_NOW,
                actor="host",
                source="unit-test",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
    )


def _insert_item(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    run_id: str,
) -> OutboxTerminalItemRow:
    """插入 Outbox terminal item row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: terminal EventLog id。
    :param run_id: Run id。
    :returns: 插入后的 item row。
    """

    event = _append_event(
        transaction_runner,
        event_id=event_id,
        run_id=run_id,
        payload={
            "terminal_summary_ref": f"summary-{event_id}",
            "terminal_summary_digest": _SUMMARY_DIGEST,
        },
    )
    identity = build_outbox_terminal_item_identity(
        terminal_event_id=event.event_id,
        run_id=run_id,
        result_ref=None,
        result_digest=None,
        terminal_summary_ref=f"summary-{event_id}",
        terminal_summary_digest=_SUMMARY_DIGEST,
    )
    row = OutboxTerminalItemRow(
        item_id=identity.item_id,
        idempotency_key=identity.idempotency_key,
        terminal_event_id=event.event_id,
        event_sequence=event.event_sequence,
        session_id=event.session_id,
        run_id=run_id,
        terminal_status="succeeded",
        dedupe_key=event.event_id,
        final_answer_json=None,
        error_message=None,
        cancel_reason=None,
        result_ref=None,
        result_digest=None,
        terminal_summary_ref=f"summary-{event_id}",
        terminal_summary_digest=_SUMMARY_DIGEST,
        item_state="pending",
        projected_at=_NOW_TEXT,
        updated_at=_NOW_TEXT,
        drained_at=None,
        last_drain_request_id=None,
    )
    return transaction_runner.run_write(
        lambda transaction: insert_outbox_terminal_item_if_absent(
            transaction,
            row,
        ).row
    )


def _event_log_count(transaction_runner: HostTransactionRunner) -> int:
    """读取 EventLog row 数。

    :param transaction_runner: Host durable transaction runner。
    :returns: EventLog row 数。
    :raises AssertionError: SQLite 返回值不是整数时抛出。
    """

    row = transaction_runner.run_read(
        lambda transaction: transaction.fetchone(
            f"SELECT count(*) AS n FROM {TABLE_EVENT_LOG}"
        )
    )
    assert row is not None
    value = row.get("n")
    assert isinstance(value, int)
    return value


def test_read_after_filters_seen_ids_and_reports_watermark(
    tmp_path: Path,
) -> None:
    """read helper 按 cursor 读取、过滤 seen ids，并返回 scanned watermark。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        first = _insert_item(
            store.transaction_runner,
            event_id="event-terminal-1",
            run_id="run-1",
        )
        second = _insert_item(
            store.transaction_runner,
            event_id="event-terminal-2",
            run_id="run-2",
        )
        third = _insert_item(
            store.transaction_runner,
            event_id="event-terminal-3",
            run_id="run-3",
        )

        first_page = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_items_after(
                transaction,
                "session-1",
                after_event_sequence=0,
                seen_terminal_event_ids=(second.terminal_event_id,),
                limit=1,
            )
        )
        second_page = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_items_after(
                transaction,
                "session-1",
                after_event_sequence=first.event_sequence,
                seen_terminal_event_ids=(second.terminal_event_id,),
                limit=1,
            )
        )

        assert tuple(row.terminal_event_id for row in first_page.rows) == (
            first.terminal_event_id,
        )
        assert first_page.scanned_watermark == first.event_sequence
        assert first_page.next_event_sequence == first.event_sequence
        assert first_page.has_more is True
        assert tuple(row.terminal_event_id for row in second_page.rows) == (
            third.terminal_event_id,
        )
        assert second_page.scanned_watermark == third.event_sequence
        assert second_page.has_more is False


def test_drain_is_idempotent_and_does_not_write_eventlog(
    tmp_path: Path,
) -> None:
    """drain 只更新 Outbox item state，并按 request id 幂等返回同一 item。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        first = _insert_item(
            store.transaction_runner,
            event_id="event-terminal-1",
            run_id="run-1",
        )
        _insert_item(
            store.transaction_runner,
            event_id="event-terminal-2",
            run_id="run-2",
        )
        before_event_count = _event_log_count(store.transaction_runner)

        drained = store.transaction_runner.run_write(
            lambda transaction: drain_outbox_terminal_items(
                transaction,
                "session-1",
                after_event_sequence=0,
                seen_terminal_event_ids=(),
                limit=1,
                drain_request_id="drain-request-1",
                drained_at=_DRAINED_AT,
            )
        )
        replayed = store.transaction_runner.run_write(
            lambda transaction: drain_outbox_terminal_items(
                transaction,
                "session-1",
                after_event_sequence=0,
                seen_terminal_event_ids=(),
                limit=1,
                drain_request_id="drain-request-1",
                drained_at=_DRAINED_AT,
            )
        )
        stored = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                first.terminal_event_id,
            )
        )

        assert tuple(row.item_id for row in drained.rows) == (first.item_id,)
        assert tuple(row.item_id for row in replayed.rows) == (first.item_id,)
        assert stored is not None
        assert stored.item_state == "drained"
        assert stored.last_drain_request_id == "drain-request-1"
        assert _event_log_count(store.transaction_runner) == before_event_count


def test_projection_state_ignores_non_terminal_eventlog_tail(
    tmp_path: Path,
) -> None:
    """checkpoint 追上 terminal fact 后，后续非 terminal EventLog 不应报告 lag。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        terminal = _append_event(
            store.transaction_runner,
            event_id="event-terminal-1",
            run_id="run-1",
            payload={
                "terminal_summary_ref": "summary-event-terminal-1",
                "terminal_summary_digest": _SUMMARY_DIGEST,
            },
        )
        store.transaction_runner.run_write(
            lambda transaction: advance_projection_checkpoint(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
                event_sequence=terminal.event_sequence,
                event_id=terminal.event_id,
                now=_NOW_TEXT,
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-non-terminal",
            run_id="run-1",
            payload={},
            event_type="RUN_ACCEPTED",
        )

        state = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_projection_state(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
                catchup_error=None,
            )
        )

        assert state.checkpoint_event_sequence == terminal.event_sequence
        assert state.status is OutboxTerminalProjectionStatus.CAUGHT_UP


def test_projection_state_ignores_run_lost_eventlog_tail(
    tmp_path: Path,
) -> None:
    """checkpoint 追上 public terminal 后，后续 RUN_LOST 不应报告 outbox lag。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        terminal = _append_event(
            store.transaction_runner,
            event_id="event-terminal-public",
            run_id="run-1",
            payload={
                "terminal_summary_ref": "summary-event-terminal-public",
                "terminal_summary_digest": _SUMMARY_DIGEST,
            },
        )
        store.transaction_runner.run_write(
            lambda transaction: advance_projection_checkpoint(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
                event_sequence=terminal.event_sequence,
                event_id=terminal.event_id,
                now=_NOW_TEXT,
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-run-lost-tail",
            run_id="run-lost",
            payload={"reason": "startup_orphan_attempt_lost"},
            event_type="RUN_LOST",
        )

        state = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_projection_state(
                transaction,
                OUTBOX_TERMINAL_CONSUMER_ID.value,
                catchup_error=None,
            )
        )

        assert state.checkpoint_event_sequence == terminal.event_sequence
        assert state.status is OutboxTerminalProjectionStatus.CAUGHT_UP


def test_drain_pending_cas_prevents_second_request_metadata_overwrite(
    tmp_path: Path,
) -> None:
    """不同 drain_request_id 不得覆盖已 drained item 的 metadata。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        first = _insert_item(
            store.transaction_runner,
            event_id="event-terminal-1",
            run_id="run-1",
        )
        store.transaction_runner.run_write(
            lambda transaction: drain_outbox_terminal_items(
                transaction,
                "session-1",
                after_event_sequence=0,
                seen_terminal_event_ids=(),
                limit=1,
                drain_request_id="drain-request-1",
                drained_at=_DRAINED_AT,
            )
        )

        with pytest.raises(HostDurableError, match="pending CAS failed"):
            store.transaction_runner.run_write(
                lambda transaction: drain_outbox_terminal_items(
                    transaction,
                    "session-1",
                    after_event_sequence=0,
                    seen_terminal_event_ids=(),
                    limit=1,
                    drain_request_id="drain-request-2",
                    drained_at="2026-05-29T02:05:06.000000Z",
                )
            )
        stored = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_item_by_event_id(
                transaction,
                first.terminal_event_id,
            )
        )

        assert stored is not None
        assert stored.item_state == "drained"
        assert stored.drained_at == _DRAINED_AT
        assert stored.last_drain_request_id == "drain-request-1"


def test_drain_request_idempotency_conflict(tmp_path: Path) -> None:
    """同一 drain_request_id 携带不同 request digest 时抛出结构化冲突。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _insert_item(
            store.transaction_runner,
            event_id="event-terminal-1",
            run_id="run-1",
        )

        store.transaction_runner.run_write(
            lambda transaction: drain_outbox_terminal_items(
                transaction,
                "session-1",
                after_event_sequence=0,
                seen_terminal_event_ids=(),
                limit=1,
                drain_request_id="drain-request-conflict",
                drained_at=_DRAINED_AT,
            )
        )
        with pytest.raises(HostIdempotencyConflictError):
            store.transaction_runner.run_write(
                lambda transaction: drain_outbox_terminal_items(
                    transaction,
                    "session-1",
                    after_event_sequence=1,
                    seen_terminal_event_ids=(),
                    limit=1,
                    drain_request_id="drain-request-conflict",
                    drained_at=_DRAINED_AT,
                )
            )
