"""Host memory projection repair 编排测试。"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, TypeVar, cast

import pytest

import dayu.host.memory_repair as memory_repair
from dayu.host.durable.transaction import (
    AfterCommitCallback,
    HostTransaction,
    HostTransactionRunner,
)
from dayu.host.memory import MemoryProjectionPolicy, default_memory_projection_policy
from dayu.host.projection import ProjectionConsumerId, ProjectionRunResult

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
        consumer_id=consumer_id.value,
    )

    assert reset_calls == [consumer_id.value]
    assert result.reset_checkpoint is True
    assert result.started_cursor == 0
    assert result.finished_cursor == 0
    assert result.events_scanned == 0
    assert _FakeProjectionRunner.run_calls == [(consumer_id, 10, None)]


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
    assert len(_FakeProjectionRunner.run_calls) == 3
    assert all(call == (consumer_id, 2, 5) for call in _FakeProjectionRunner.run_calls)


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
    assert len(_FakeProjectionRunner.run_calls) == 1


def test_catchup_port_delegates_to_catch_up_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConversationMemoryProjectionCatchupPort 委托模块级 catch-up 函数。"""

    calls: list[tuple[int, str]] = []
    policy = _policy()

    def fake_catch_up(
        transaction_runner: HostTransactionRunner,
        *,
        policy: MemoryProjectionPolicy,
        batch_size: int,
        consumer_id: str,
        max_event_sequence: int | None = None,
    ) -> memory_repair.ConversationMemoryProjectionRepairResult:
        """记录端口传入参数并返回空结果。

        :param transaction_runner: Host transaction runner。
        :param policy: memory projection policy。
        :param batch_size: batch size。
        :param consumer_id: consumer id。
        :param max_event_sequence: 最大 event sequence。
        :returns: repair result。
        """

        del transaction_runner, policy, max_event_sequence
        calls.append((batch_size, consumer_id))
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
    port = memory_repair.ConversationMemoryProjectionCatchupPort(
        transaction_runner=cast(HostTransactionRunner, _FakeTransactionRunner()),
        policy=policy,
        batch_size=4,
        consumer_id="memory.port",
    )

    port.catch_up_projection()

    assert calls == [(4, "memory.port")]
