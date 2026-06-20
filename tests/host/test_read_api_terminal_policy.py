"""Host read API terminal text policy 投影测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dayu.contracts.json_value import JsonValue
from dayu.host.api import HostEvent, HostEventKind, HostTerminalStatus
from dayu.host.durable.codec import canonical_json_dumps, format_utc_timestamp
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventClass, EventLogRow
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.outbox import build_outbox_terminal_item_row
from dayu.host.projection import projection_event_view_from_row
from dayu.host.read_api import _host_event_from_row

_SESSION_ID = "session-terminal-policy"
_RUN_ID = "run-terminal-policy"
_ATTEMPT_ID = "attempt-terminal-policy"
_EXECUTION_ID = "execution-terminal-policy"
_TIMESTAMP = format_utc_timestamp(datetime(2026, 6, 12, tzinfo=UTC))


def test_failed_terminal_projection_never_builds_final_answer(tmp_path: Path) -> None:
    """RUN_FAILED 投影不把 diagnostic payload 当成 final answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: FAILED HostEvent 携带 final answer 时抛出。
    """

    event = _project_terminal_event(
        tmp_path,
        event_type="RUN_FAILED",
        payload={
            "message": "provider failed",
            "final_answer": "must not be displayed",
            "content": "must not be displayed",
        },
    )

    assert event.kind is HostEventKind.FAILED
    assert event.terminal_status is HostTerminalStatus.FAILED
    assert event.final_answer is None
    assert event.error_message == "provider failed"
    assert event.cancel_reason is None


def test_failed_terminal_projection_appends_correlation_suffix(
    tmp_path: Path,
) -> None:
    """live watcher 与 outbox fallback 使用相同 terminal 诊断后缀。"""

    payload: dict[str, JsonValue] = {
        "message": "provider failed",
        "provider_request_id": None,
        "client_correlation_id": "client-fallback",
    }
    row = _row("RUN_FAILED", payload)
    original_payload_json = row.payload_json

    event = _project_terminal_row(tmp_path, row)
    outbox_row = build_outbox_terminal_item_row(
        projection_event_view_from_row(row)
    )

    assert event.error_message == (
        "provider failed\nclient_correlation_id=client-fallback"
    )
    assert outbox_row.error_message == event.error_message
    assert row.payload_json == original_payload_json
    assert payload["message"] == "provider failed"


def test_cancelled_terminal_projection_never_builds_final_answer(tmp_path: Path) -> None:
    """RUN_CANCELLED 投影不把 cancellation reason 当成 final answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: CANCELLED HostEvent 携带 final answer 时抛出。
    """

    event = _project_terminal_event(
        tmp_path,
        event_type="RUN_CANCELLED",
        payload={
            "reason": "user_stop",
            "final_answer": "must not be displayed",
            "content": "must not be displayed",
        },
    )

    assert event.kind is HostEventKind.CANCELLED
    assert event.terminal_status is HostTerminalStatus.CANCELLED
    assert event.final_answer is None
    assert event.error_message is None
    assert event.cancel_reason == "user_stop"


def test_lost_terminal_projection_never_builds_final_answer(tmp_path: Path) -> None:
    """RUN_LOST 投影不把 lifecycle diagnostic 当成 final answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: LOST HostEvent 携带 final answer 时抛出。
    """

    event = _project_terminal_event(
        tmp_path,
        event_type="RUN_LOST",
        payload={
            "message": "worker lost",
            "final_answer": "must not be displayed",
            "content": "must not be displayed",
        },
    )

    assert event.kind is HostEventKind.LOST
    assert event.terminal_status is HostTerminalStatus.LOST
    assert event.final_answer is None
    assert event.error_message == "worker lost"
    assert event.cancel_reason is None


def _project_terminal_event(
    tmp_path: Path, *, event_type: str, payload: dict[str, JsonValue]
) -> HostEvent:
    """投影测试用 terminal EventLog row。

    :param tmp_path: pytest 临时目录。
    :param event_type: terminal event type。
    :param payload: terminal payload。
    :returns: 投影后的 HostEvent。
    """

    return _project_terminal_row(tmp_path, _row(event_type, payload))


def _project_terminal_row(tmp_path: Path, row: EventLogRow) -> HostEvent:
    """投影测试用 terminal EventLog row。

    :param tmp_path: pytest 临时目录。
    :param row: terminal EventLog row。
    :returns: 投影后的 HostEvent。
    """

    event: HostEvent | None = None
    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> HostEvent:
            """执行 read API terminal 投影。

            :param transaction: Host transaction。
            :returns: 投影后的 HostEvent。
            """

            return _host_event_from_row(transaction, row)

        event = store.transaction_runner.run_read(operation)
    assert event is not None
    return event


def _row(event_type: str, payload: dict[str, JsonValue]) -> EventLogRow:
    """构造 terminal EventLog row。

    :param event_type: terminal event type。
    :param payload: terminal payload。
    :returns: EventLog row。
    """

    return EventLogRow(
        event_sequence=1,
        event_id=f"event-{event_type.lower()}",
        event_body_digest="sha256:terminal-policy",
        event_class=EventClass.CANONICAL_FACT,
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        execution_id=_EXECUTION_ID,
        event_type=event_type,
        occurred_at=_TIMESTAMP,
        actor="pytest",
        source="pytest",
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json=canonical_json_dumps(payload),
        payload_ref=None,
        payload_digest=None,
        appended_at=_TIMESTAMP,
    )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )
