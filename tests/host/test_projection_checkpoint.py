"""Host projection checkpoint / failure durable store 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
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
from dayu.host.durable.projection import (
    advance_projection_checkpoint,
    clear_projection_failure,
    ensure_projection_checkpoint,
    ProjectionCheckpointRow,
    ProjectionFailureRow,
    ProjectionResetResult,
    read_projection_checkpoint,
    read_projection_failure,
    reset_projection_refs_for_deleted_events,
    write_projection_failure,
)
from dayu.host.durable.transaction import HostTransactionRunner

_NOW = "2026-05-16T00:00:00.000000Z"
_LATER = "2026-05-16T00:00:01.000000Z"


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
    transaction_runner: HostTransactionRunner, event_id: str, event_type: str
) -> EventLogRow:
    """追加一条测试 EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :returns: 已追加的 EventLog row。
    """

    return transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id="session-1",
                run_id="run-1",
                attempt_id=None,
                execution_id=None,
                event_type=event_type,
                occurred_at=datetime(2026, 5, 16, tzinfo=UTC),
                actor=None,
                source=None,
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={"event_id": event_id},
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
    )


def test_missing_checkpoint_initializes_to_cursor_zero(tmp_path: Path) -> None:
    """缺失 checkpoint 时初始化为 cursor 0。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: ensure_projection_checkpoint(
                transaction, "consumer", now=_NOW
            )
        )
        assert checkpoint.consumer_id == "consumer"
        assert checkpoint.checkpoint_event_sequence == 0
        assert checkpoint.checkpoint_event_id is None
        assert checkpoint.last_success_at is None
        assert checkpoint.updated_at == _NOW


def test_advance_checkpoint_persists_event_identity_and_timestamp(
    tmp_path: Path,
) -> None:
    """checkpoint 推进后持久化 event sequence、event id 与成功时间。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(
            store.transaction_runner, "event-1", "USER_INPUT_ACCEPTED"
        )
        checkpoint = store.transaction_runner.run_write(
            lambda transaction: advance_projection_checkpoint(
                transaction,
                "consumer",
                event_sequence=event.event_sequence,
                event_id=event.event_id,
                now=_LATER,
            )
        )
        assert checkpoint.checkpoint_event_sequence == event.event_sequence
        assert checkpoint.checkpoint_event_id == event.event_id
        assert checkpoint.last_success_at == _LATER
        assert checkpoint.updated_at == _LATER


def test_advancing_checkpoint_backwards_is_rejected(tmp_path: Path) -> None:
    """checkpoint 不允许倒退。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        first_event = _append_event(store.transaction_runner, "event-1", "TYPE_A")
        second_event = _append_event(store.transaction_runner, "event-2", "TYPE_B")
        store.transaction_runner.run_write(
            lambda transaction: advance_projection_checkpoint(
                transaction,
                "consumer",
                event_sequence=second_event.event_sequence,
                event_id=second_event.event_id,
                now=_NOW,
            )
        )
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(
                lambda transaction: advance_projection_checkpoint(
                    transaction,
                    "consumer",
                    event_sequence=first_event.event_sequence,
                    event_id=first_event.event_id,
                    now=_LATER,
                )
            )


def test_advancing_checkpoint_to_same_event_sequence_is_rejected(
    tmp_path: Path,
) -> None:
    """checkpoint 不允许重复推进到相同 event_sequence。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(store.transaction_runner, "event-1", "TYPE_A")
        store.transaction_runner.run_write(
            lambda transaction: advance_projection_checkpoint(
                transaction,
                "consumer",
                event_sequence=event.event_sequence,
                event_id=event.event_id,
                now=_NOW,
            )
        )
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(
                lambda transaction: advance_projection_checkpoint(
                    transaction,
                    "consumer",
                    event_sequence=event.event_sequence,
                    event_id=event.event_id,
                    now=_LATER,
                )
            )


@pytest.mark.parametrize("event_sequence", (0, -1))
def test_advance_checkpoint_rejects_non_positive_event_sequence(
    tmp_path: Path, event_sequence: int
) -> None:
    """checkpoint 推进拒绝非正 event_sequence。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(
                lambda transaction: advance_projection_checkpoint(
                    transaction,
                    "consumer",
                    event_sequence=event_sequence,
                    event_id="event-1",
                    now=_NOW,
                )
            )


def test_failure_row_increments_and_clear_removes_it(tmp_path: Path) -> None:
    """failure row 可记录、累加 failure_count，并在成功后删除。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        event = _append_event(store.transaction_runner, "event-1", "TYPE_A")
        first = store.transaction_runner.run_write(
            lambda transaction: write_projection_failure(
                transaction,
                "consumer",
                failed_event_sequence=event.event_sequence,
                failed_event_id=event.event_id,
                error_code="ProjectionError",
                error_message="failed",
                now=_NOW,
            )
        )
        second = store.transaction_runner.run_write(
            lambda transaction: write_projection_failure(
                transaction,
                "consumer",
                failed_event_sequence=event.event_sequence,
                failed_event_id=event.event_id,
                error_code="ProjectionError",
                error_message="failed again",
                now=_LATER,
            )
        )
        store.transaction_runner.run_write(
            lambda transaction: clear_projection_failure(transaction, "consumer")
        )
        cleared = store.transaction_runner.run_write(
            lambda transaction: read_projection_failure(transaction, "consumer")
        )
        assert first.failure_count == 1
        assert first.first_failed_at == _NOW
        assert second.failure_count == 2
        assert second.first_failed_at == _NOW
        assert second.last_failed_at == _LATER
        assert cleared is None


def test_reset_refs_for_deleted_events_deletes_only_rebuildable_consumers(
    tmp_path: Path,
) -> None:
    """验证 projection reset 只删除引用目标 EventLog 的白名单 consumer rows。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: reset 计数或保留 row 不符合预期时由断言抛出。
    """

    options = _options(tmp_path)
    result: ProjectionResetResult | None = None
    target_checkpoint: ProjectionCheckpointRow | None = None
    other_checkpoint: ProjectionCheckpointRow | None = None
    target_failure: ProjectionFailureRow | None = None
    other_event_id = ""
    with open_host_durable_store(options) as store:
        target = _append_event(store.transaction_runner, "event-target", "TYPE_A")
        other = _append_event(store.transaction_runner, "event-other", "TYPE_B")
        other_event_id = other.event_id
        store.transaction_runner.run_write(
            lambda transaction: (
                advance_projection_checkpoint(
                    transaction,
                    "host.minimal-read-model",
                    event_sequence=target.event_sequence,
                    event_id=target.event_id,
                    now=_NOW,
                ),
                advance_projection_checkpoint(
                    transaction,
                    "host.outbox-terminal",
                    event_sequence=other.event_sequence,
                    event_id=other.event_id,
                    now=_NOW,
                ),
                write_projection_failure(
                    transaction,
                    "host.audit-log-jsonl",
                    failed_event_sequence=target.event_sequence,
                    failed_event_id=target.event_id,
                    error_code="ProjectionError",
                    error_message="failed",
                    now=_NOW,
                ),
            )
        )

        result = store.transaction_runner.run_write(
            lambda transaction: reset_projection_refs_for_deleted_events(
                transaction,
                event_ids=(target.event_id,),
                rebuildable_consumer_ids=(
                    "host.minimal-read-model",
                    "host.audit-log-jsonl",
                    "host.outbox-terminal",
                ),
            )
        )
        target_checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction, "host.minimal-read-model"
            )
        )
        other_checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction, "host.outbox-terminal"
            )
        )
        target_failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction, "host.audit-log-jsonl"
            )
        )

    assert result is not None
    assert result.deleted_checkpoints == 1
    assert result.deleted_failures == 1
    assert target_checkpoint is None
    assert other_checkpoint is not None
    assert other_checkpoint.checkpoint_event_id == other_event_id
    assert target_failure is None


def test_reset_refs_for_deleted_events_rejects_non_rebuildable_consumer(
    tmp_path: Path,
) -> None:
    """验证 projection reset 遇到非白名单 consumer 引用目标 EventLog 时拒绝。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 非白名单 consumer 未被拒绝或 checkpoint 被删除时由断言抛出。
    """

    options = _options(tmp_path)
    checkpoint: ProjectionCheckpointRow | None = None
    target_event_id = ""
    with open_host_durable_store(options) as store:
        target = _append_event(store.transaction_runner, "event-target", "TYPE_A")
        target_event_id = target.event_id
        store.transaction_runner.run_write(
            lambda transaction: advance_projection_checkpoint(
                transaction,
                "host.recovery-governance",
                event_sequence=target.event_sequence,
                event_id=target.event_id,
                now=_NOW,
            )
        )

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(
                lambda transaction: reset_projection_refs_for_deleted_events(
                    transaction,
                    event_ids=(target.event_id,),
                    rebuildable_consumer_ids=("host.minimal-read-model",),
                )
            )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction, "host.recovery-governance"
            )
        )

    assert checkpoint is not None
    assert checkpoint.checkpoint_event_id == target_event_id
