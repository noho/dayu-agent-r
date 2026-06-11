"""Host memory projection repair 编排测试。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, TypeVar, cast

import pytest

import dayu.host.memory_repair as memory_repair
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.memory import MemorySnapshotRow, read_latest_memory_snapshot
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.projection import (
    ProjectionCheckpointRow,
    read_projection_checkpoint,
)
from dayu.host.durable.transaction import (
    AfterCommitCallback,
    HostTransaction,
    HostTransactionRunner,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    MemoryProjectionPolicy,
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from dayu.host.projection import (
    ProjectionConsumerId,
    ProjectionRunResult,
    ProjectionRunner as RealProjectionRunner,
)

T = TypeVar("T")


class _FakeTransaction:
    """测试用空 transaction 占位。"""


class _FakeTransactionRunner:
    """记录 write transaction 调用的 fake runner。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.write_calls = 0

    def run_write(
        self,
        operation: Callable[[HostTransaction], T],
        *,
        after_commit: tuple[AfterCommitCallback, ...] = (),
    ) -> T:
        """执行传入 operation 并记录调用次数。

        :param operation: 待执行写事务操作。
        :param after_commit: commit 后回调；fake 中立即执行。
        :returns: operation 返回值。
        """

        self.write_calls += 1
        result = operation(cast(HostTransaction, _FakeTransaction()))
        for callback in after_commit:
            callback()
        return result


class _FakeProjectionRunner:
    """按预置结果返回的 ProjectionRunner fake。"""

    queued_results: ClassVar[list[ProjectionRunResult]] = []
    run_calls: ClassVar[list[tuple[ProjectionConsumerId, int, int | None]]] = []

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
        consumers: tuple[memory_repair.ConversationMemoryProjectionConsumer, ...],
    ) -> None:
        """记录初始化输入。

        :param transaction_runner: Host transaction runner。
        :param consumers: memory projection consumer tuple。
        :returns: ``None``。
        """

        del transaction_runner
        assert len(consumers) == 1

    def run_once(
        self,
        consumer_id: ProjectionConsumerId,
        *,
        limit: int,
        max_event_sequence: int | None = None,
    ) -> ProjectionRunResult:
        """返回下一条预置 projection 结果。

        :param consumer_id: projection consumer id。
        :param limit: batch size。
        :param max_event_sequence: 最大 event sequence。
        :returns: 下一条预置结果。
        :raises AssertionError: 未预置结果时抛出。
        """

        self.run_calls.append((consumer_id, limit, max_event_sequence))
        assert self.queued_results
        return self.queued_results.pop(0)


def _result(
    *,
    consumer_id: ProjectionConsumerId,
    started_cursor: int,
    finished_cursor: int,
    scanned: int,
    matched: int = 0,
    applied: int = 0,
    duplicates: int = 0,
    failures: int = 0,
) -> ProjectionRunResult:
    """构造 projection run result。

    :param consumer_id: consumer id。
    :param started_cursor: 开始 cursor。
    :param finished_cursor: 结束 cursor。
    :param scanned: 扫描事件数。
    :param matched: 命中事件数。
    :param applied: 应用事件数。
    :param duplicates: 重复事件数。
    :param failures: failure 数。
    :returns: projection run result。
    """

    return ProjectionRunResult(
        consumer_id=consumer_id,
        started_cursor=started_cursor,
        finished_cursor=finished_cursor,
        events_scanned=scanned,
        events_matched=matched,
        events_applied=applied,
        events_skipped=0,
        duplicate_events=duplicates,
        failures=failures,
    )


@pytest.fixture(autouse=True)
def _fake_projection_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 memory repair 内部 ProjectionRunner。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    _FakeProjectionRunner.queued_results = []
    _FakeProjectionRunner.run_calls = []
    monkeypatch.setattr(memory_repair, "ProjectionRunner", _FakeProjectionRunner)


def _policy() -> MemoryProjectionPolicy:
    """构造测试用 memory projection policy。

    :returns: memory projection policy。
    """

    return default_memory_projection_policy(context_window_size=8192)


def test_rebuild_resets_projection_and_finishes_empty_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rebuild 先 reset，空 batch 后正常终止。"""

    consumer_id = ProjectionConsumerId("memory.test")
    reset_calls: list[str] = []

    def fake_reset(transaction: HostTransaction, *, consumer_id: str) -> None:
        """记录 reset consumer id。

        :param transaction: Host transaction。
        :param consumer_id: consumer id。
        :returns: ``None``。
        """

        del transaction
        reset_calls.append(consumer_id)

    monkeypatch.setattr(
        memory_repair,
        "reset_conversation_memory_projection",
        fake_reset,
    )
    _FakeProjectionRunner.queued_results = [
        _result(
            consumer_id=consumer_id,
            started_cursor=0,
            finished_cursor=0,
            scanned=0,
        )
    ]
    runner = cast(HostTransactionRunner, _FakeTransactionRunner())

    result = memory_repair.rebuild_conversation_memory_projection(
        runner,
        policy=_policy(),
        batch_size=10,
        max_event_sequence=0,
        budget=memory_repair.MemoryProjectionCatchupBudget(
            max_batches=1,
            max_scanned_events=10,
            purpose=memory_repair.MemoryProjectionRepairPurpose.BEST_EFFORT_AFTER_COMMIT,
        ),
        consumer_id=consumer_id.value,
    )

    assert reset_calls == [consumer_id.value]
    assert result.reset_checkpoint is True
    assert result.started_cursor == 0
    assert result.finished_cursor == 0
    assert result.events_scanned == 0
    assert result.batches_used == 1
    assert result.stop_reason is memory_repair.MemoryProjectionRepairStopReason.TARGET_REACHED
    assert result.target_reached is True
    assert _FakeProjectionRunner.run_calls == [(consumer_id, 10, 0)]


def test_catch_up_accumulates_batches_until_short_batch() -> None:
    """catch-up 聚合多批结果，并在短 batch 后终止。"""

    consumer_id = ProjectionConsumerId("memory.test")
    _FakeProjectionRunner.queued_results = [
        _result(
            consumer_id=consumer_id,
            started_cursor=0,
            finished_cursor=2,
            scanned=2,
            matched=2,
            applied=1,
            duplicates=1,
        ),
        _result(
            consumer_id=consumer_id,
            started_cursor=2,
            finished_cursor=4,
            scanned=2,
            matched=2,
            applied=2,
        ),
        _result(
            consumer_id=consumer_id,
            started_cursor=4,
            finished_cursor=5,
            scanned=1,
            matched=1,
            applied=1,
        ),
    ]

    result = memory_repair.catch_up_conversation_memory_projection(
        cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=_policy(),
        batch_size=2,
        consumer_id=consumer_id.value,
        max_event_sequence=5,
    )

    assert result.reset_checkpoint is False
    assert result.started_cursor == 0
    assert result.finished_cursor == 5
    assert result.events_scanned == 5
    assert result.events_matched == 5
    assert result.events_applied == 4
    assert result.duplicates == 1
    assert result.batches_used == 3
    assert result.stop_reason is memory_repair.MemoryProjectionRepairStopReason.TARGET_REACHED
    assert result.target_reached is True
    assert len(_FakeProjectionRunner.run_calls) == 3
    assert all(call == (consumer_id, 2, 5) for call in _FakeProjectionRunner.run_calls)


def test_catch_up_budget_exhausted_stops_before_idle() -> None:
    """catch-up 总 batch 预算耗尽时停止且不标记 projection failure。"""

    consumer_id = ProjectionConsumerId("memory.test")
    _FakeProjectionRunner.queued_results = [
        _result(
            consumer_id=consumer_id,
            started_cursor=0,
            finished_cursor=2,
            scanned=2,
            matched=2,
            applied=2,
        ),
        _result(
            consumer_id=consumer_id,
            started_cursor=2,
            finished_cursor=4,
            scanned=2,
            matched=2,
            applied=2,
        ),
    ]

    result = memory_repair.catch_up_conversation_memory_projection(
        cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=_policy(),
        batch_size=2,
        consumer_id=consumer_id.value,
        budget=memory_repair.MemoryProjectionCatchupBudget(
            max_batches=1,
            max_scanned_events=2,
            purpose=memory_repair.MemoryProjectionRepairPurpose.BEST_EFFORT_AFTER_COMMIT,
        ),
    )

    assert result.finished_cursor == 2
    assert result.events_scanned == 2
    assert result.batches_used == 1
    assert result.failures == 0
    assert result.budget_exhausted is True
    assert result.target_reached is False
    assert (
        result.stop_reason
        is memory_repair.MemoryProjectionRepairStopReason.BUDGET_EXHAUSTED
    )
    assert len(_FakeProjectionRunner.run_calls) == 1


def test_catch_up_stops_when_target_reached_before_idle() -> None:
    """catch-up 覆盖目标 cursor 后停止，不继续追 EventLog idle。"""

    consumer_id = ProjectionConsumerId("memory.test")
    _FakeProjectionRunner.queued_results = [
        _result(
            consumer_id=consumer_id,
            started_cursor=0,
            finished_cursor=2,
            scanned=2,
            matched=2,
            applied=2,
        ),
        _result(
            consumer_id=consumer_id,
            started_cursor=2,
            finished_cursor=4,
            scanned=2,
            matched=2,
            applied=2,
        ),
    ]

    result = memory_repair.catch_up_conversation_memory_projection(
        cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=_policy(),
        batch_size=2,
        consumer_id=consumer_id.value,
        max_event_sequence=2,
        budget=memory_repair.MemoryProjectionCatchupBudget(
            max_batches=4,
            max_scanned_events=8,
            purpose=memory_repair.MemoryProjectionRepairPurpose.BEST_EFFORT_AFTER_COMMIT,
        ),
    )

    assert result.finished_cursor == 2
    assert result.batches_used == 1
    assert result.budget_exhausted is False
    assert result.target_reached is True
    assert result.stop_reason is memory_repair.MemoryProjectionRepairStopReason.TARGET_REACHED
    assert _FakeProjectionRunner.run_calls == [(consumer_id, 2, 2)]


def test_required_catch_up_without_budget_crosses_old_batch_cap_to_target() -> None:
    """required catch-up 无 correctness batch cap，可跨超过旧 16 批追到目标。"""

    consumer_id = ProjectionConsumerId("memory.test")
    _FakeProjectionRunner.queued_results = [
        _result(
            consumer_id=consumer_id,
            started_cursor=index,
            finished_cursor=index + 1,
            scanned=1,
            matched=1,
            applied=1,
        )
        for index in range(17)
    ]

    result = memory_repair.catch_up_conversation_memory_projection(
        cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=_policy(),
        batch_size=1,
        consumer_id=consumer_id.value,
        max_event_sequence=17,
        budget=None,
    )

    assert result.finished_cursor == 17
    assert result.batches_used == 17
    assert result.events_scanned == 17
    assert result.target_reached is True
    assert result.budget_exhausted is False
    assert result.max_batches is None
    assert result.max_scanned_events is None
    assert len(_FakeProjectionRunner.run_calls) == 17


def test_rebuild_budget_exhausted_reports_target_not_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rebuild 总预算耗尽且未覆盖 required cursor 时返回可诊断结果。"""

    consumer_id = ProjectionConsumerId("memory.test")

    def fake_reset(transaction: HostTransaction, *, consumer_id: str) -> None:
        """忽略 reset projection operation。

        :param transaction: Host transaction。
        :param consumer_id: consumer id。
        :returns: ``None``。
        """

        del transaction, consumer_id

    monkeypatch.setattr(
        memory_repair,
        "reset_conversation_memory_projection",
        fake_reset,
    )
    _FakeProjectionRunner.queued_results = [
        _result(
            consumer_id=consumer_id,
            started_cursor=0,
            finished_cursor=2,
            scanned=2,
            matched=2,
            applied=2,
        )
    ]

    result = memory_repair.rebuild_conversation_memory_projection(
        cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=_policy(),
        batch_size=2,
        max_event_sequence=4,
        budget=memory_repair.MemoryProjectionCatchupBudget(
            max_batches=1,
            max_scanned_events=2,
            purpose=memory_repair.MemoryProjectionRepairPurpose.BEST_EFFORT_AFTER_COMMIT,
        ),
        consumer_id=consumer_id.value,
    )

    assert result.reset_checkpoint is True
    assert result.finished_cursor == 2
    assert result.target_reached is False
    assert result.budget_exhausted is True
    assert (
        result.stop_reason
        is memory_repair.MemoryProjectionRepairStopReason.BUDGET_EXHAUSTED
    )
    assert _FakeProjectionRunner.run_calls == [(consumer_id, 2, 4)]


def test_rebuild_without_budget_crosses_old_batch_cap_to_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rebuild 无 correctness batch cap，可跨超过旧 32 批追到目标。"""

    consumer_id = ProjectionConsumerId("memory.test")

    def fake_reset(transaction: HostTransaction, *, consumer_id: str) -> None:
        """忽略 reset projection operation。

        :param transaction: Host transaction。
        :param consumer_id: consumer id。
        :returns: ``None``。
        """

        del transaction, consumer_id

    monkeypatch.setattr(
        memory_repair,
        "reset_conversation_memory_projection",
        fake_reset,
    )
    _FakeProjectionRunner.queued_results = [
        _result(
            consumer_id=consumer_id,
            started_cursor=index,
            finished_cursor=index + 1,
            scanned=1,
            matched=1,
            applied=1,
        )
        for index in range(33)
    ]

    result = memory_repair.rebuild_conversation_memory_projection(
        cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=_policy(),
        batch_size=1,
        max_event_sequence=33,
        budget=None,
        consumer_id=consumer_id.value,
    )

    assert result.reset_checkpoint is True
    assert result.finished_cursor == 33
    assert result.batches_used == 33
    assert result.target_reached is True
    assert result.budget_exhausted is False
    assert result.max_batches is None
    assert result.max_scanned_events is None
    assert len(_FakeProjectionRunner.run_calls) == 33


def test_catch_up_stops_on_failure_and_counts_failure() -> None:
    """runner 返回 failure 时 catch-up 立即终止并汇总 failure。"""

    consumer_id = ProjectionConsumerId("memory.test")
    _FakeProjectionRunner.queued_results = [
        _result(
            consumer_id=consumer_id,
            started_cursor=7,
            finished_cursor=8,
            scanned=2,
            matched=1,
            failures=1,
        ),
        _result(
            consumer_id=consumer_id,
            started_cursor=8,
            finished_cursor=9,
            scanned=0,
        ),
    ]

    result = memory_repair.catch_up_conversation_memory_projection(
        cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=_policy(),
        batch_size=2,
        consumer_id=consumer_id.value,
    )

    assert result.started_cursor == 7
    assert result.finished_cursor == 8
    assert result.events_scanned == 2
    assert result.failures == 1
    assert result.stop_reason is memory_repair.MemoryProjectionRepairStopReason.FAILURE
    assert result.budget_exhausted is False
    assert len(_FakeProjectionRunner.run_calls) == 1


def test_catchup_port_delegates_to_catch_up_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConversationMemoryProjectionCatchupPort 委托模块级 catch-up 函数。"""

    calls: list[
        tuple[int, str, memory_repair.MemoryProjectionCatchupBudget | None]
    ] = []
    policy = _policy()

    def fake_catch_up(
        transaction_runner: HostTransactionRunner,
        *,
        policy: MemoryProjectionPolicy,
        batch_size: int,
        consumer_id: str,
        max_event_sequence: int | None = None,
        budget: memory_repair.MemoryProjectionCatchupBudget | None = None,
    ) -> memory_repair.ConversationMemoryProjectionRepairResult:
        """记录端口传入参数并返回空结果。

        :param transaction_runner: Host transaction runner。
        :param policy: memory projection policy。
        :param batch_size: batch size。
        :param consumer_id: consumer id。
        :param max_event_sequence: 最大 event sequence。
        :param budget: Host 内部单次总预算。
        :returns: repair result。
        """

        del transaction_runner, policy, max_event_sequence
        calls.append((batch_size, consumer_id, budget))
        projection_consumer_id = ProjectionConsumerId(consumer_id)
        return memory_repair.ConversationMemoryProjectionRepairResult(
            consumer_id=projection_consumer_id,
            reset_checkpoint=False,
            started_cursor=0,
            finished_cursor=0,
            events_scanned=0,
            events_matched=0,
            events_applied=0,
            duplicates=0,
            failures=0,
        )

    monkeypatch.setattr(
        memory_repair,
        "catch_up_conversation_memory_projection",
        fake_catch_up,
    )
    budget = memory_repair.MemoryProjectionCatchupBudget(
        max_batches=1,
        max_scanned_events=4,
        purpose=memory_repair.MemoryProjectionRepairPurpose.BEST_EFFORT_AFTER_COMMIT,
    )
    port = memory_repair.ConversationMemoryProjectionCatchupPort(
        transaction_runner=cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=policy,
        batch_size=4,
        consumer_id="memory.port",
        budget=budget,
    )

    port.catch_up_projection()

    assert calls == [(4, "memory.port", budget)]


def test_catch_up_uses_real_durable_store_and_writes_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """catch-up 在真实 durable store 上写入 memory snapshot 与 checkpoint。"""

    monkeypatch.setattr(memory_repair, "ProjectionRunner", RealProjectionRunner)
    policy = _policy()
    options = _options(tmp_path / "durable.sqlite3", tmp_path / "artifacts")
    with open_host_durable_store(options) as store:
        first_event = store.transaction_runner.run_write(
            _AppendMemoryEventOperation(
                event_id="event-memory-repair-1",
                display_text="第一轮用户问题",
            )
        )
        second_event = store.transaction_runner.run_write(
            _AppendMemoryEventOperation(
                event_id="event-memory-repair-2",
                display_text="第二轮用户问题",
            )
        )

        result = memory_repair.catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=2,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        )
        snapshot_row = store.transaction_runner.run_read(
            _ReadLatestMemorySnapshotOperation(policy)
        )
        checkpoint = store.transaction_runner.run_read(
            _ReadMemoryCheckpointOperation()
        )

        assert first_event.event_sequence < second_event.event_sequence
        assert result.reset_checkpoint is False
        assert result.events_scanned == 2
        assert result.events_matched == 2
        assert result.events_applied == 2
        assert result.failures == 0
        assert result.finished_cursor == second_event.event_sequence
        assert snapshot_row is not None
        assert (
            snapshot_row.snapshot.cursor.checkpoint_event_sequence
            == second_event.event_sequence
        )
        assert tuple(
            item.text
            for item in snapshot_row.snapshot.trace_memory.selected_recent_window
        ) == ("第一轮用户问题", "第二轮用户问题")
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == second_event.event_sequence
        assert checkpoint.checkpoint_event_id == second_event.event_id


def test_catch_up_budget_exhausted_advances_only_processed_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实 durable catch-up 超预算时只推进已处理 row 的 checkpoint。"""

    monkeypatch.setattr(memory_repair, "ProjectionRunner", RealProjectionRunner)
    policy = _policy()
    options = _options(tmp_path / "durable.sqlite3", tmp_path / "artifacts")
    with open_host_durable_store(options) as store:
        first_event = store.transaction_runner.run_write(
            _AppendMemoryEventOperation(
                event_id="event-memory-budget-1",
                display_text="预算内问题",
            )
        )
        store.transaction_runner.run_write(
            _AppendMemoryEventOperation(
                event_id="event-memory-budget-2",
                display_text="预算外问题",
            )
        )

        result = memory_repair.catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=1,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            budget=memory_repair.MemoryProjectionCatchupBudget(
                max_batches=1,
                max_scanned_events=1,
                purpose=(
                    memory_repair.MemoryProjectionRepairPurpose.BEST_EFFORT_AFTER_COMMIT
                ),
            ),
        )
        snapshot_row = store.transaction_runner.run_read(
            _ReadLatestMemorySnapshotOperation(policy)
        )
        checkpoint = store.transaction_runner.run_read(
            _ReadMemoryCheckpointOperation()
        )

        assert result.budget_exhausted is True
        assert result.failures == 0
        assert result.finished_cursor == first_event.event_sequence
        assert snapshot_row is not None
        assert tuple(
            item.text
            for item in snapshot_row.snapshot.trace_memory.selected_recent_window
        ) == ("预算内问题",)
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == first_event.event_sequence
        assert checkpoint.checkpoint_event_id == first_event.event_id


class _AppendMemoryEventOperation:
    """追加 USER_INPUT_ACCEPTED 事件的真实 durable operation。

    :param event_id: EventLog event id。
    :param display_text: memory projection 可读文本。
    """

    def __init__(self, *, event_id: str, display_text: str) -> None:
        """初始化 append operation。

        :param event_id: EventLog event id。
        :param display_text: 用户可见文本。
        :returns: ``None``。
        """

        self._event_id = event_id
        self._display_text = display_text

    def __call__(self, transaction: HostTransaction) -> EventLogRow:
        """追加 canonical memory input event。

        :param transaction: Host durable transaction。
        :returns: 追加后的 EventLog row。
        """

        return append_event(
            transaction,
            EventLogAppendRequest(
                event_id=self._event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id="session-memory-repair",
                run_id="run-memory-repair",
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
                actor="host",
                source="memory-repair-test",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={"display_text": self._display_text},
                payload_ref=None,
                payload_digest=None,
            ),
        ).row


class _ReadLatestMemorySnapshotOperation:
    """读取真实 durable memory 最新 snapshot。

    :param policy: memory projection policy。
    """

    def __init__(self, policy: MemoryProjectionPolicy) -> None:
        """初始化读取 operation。

        :param policy: memory projection policy。
        :returns: ``None``。
        """

        self._policy = policy

    def __call__(self, transaction: HostTransaction) -> MemorySnapshotRow | None:
        """读取测试 session 的最新 memory snapshot row。

        :param transaction: Host durable transaction。
        :returns: snapshot row 或 ``None``。
        """

        return read_latest_memory_snapshot(
            transaction,
            session_id="session-memory-repair",
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            policy_digest=digest_memory_projection_policy(self._policy),
        )


class _ReadMemoryCheckpointOperation:
    """读取 memory projection checkpoint 的 durable operation。"""

    def __call__(self, transaction: HostTransaction) -> ProjectionCheckpointRow | None:
        """读取 memory projection checkpoint。

        :param transaction: Host durable transaction。
        :returns: checkpoint row 或 ``None``。
        """

        return read_projection_checkpoint(
            transaction,
            CONVERSATION_MEMORY_CONSUMER_ID,
        )


def _options(db_path: Path, artifact_root: Path) -> HostDurableStoreOptions:
    """构造真实 durable store options。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=3.0,
            write_busy_retry_count=80,
            write_retry_initial_delay_seconds=0.002,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.03,
        ),
    )
