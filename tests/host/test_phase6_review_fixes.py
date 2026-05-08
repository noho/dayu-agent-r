"""Host P6 修复验证测试。

覆盖本轮 P6 review 修复点:

- 终态 RunResult 快照与 terminal event 同事务持久化(全四种终态)。
- ``source_engine_event_id`` 唯一约束违反映射为 ``ValueError``。
- ``ProjectionStore.advance_success`` 在相同 position 重放下幂等。
- ``ProjectionCoordinator._drain_lock`` 防止并发 drain 重入。
- 多 run 并发 append 顺序与 global position 单调。
- post-commit hook 抛异常不污染事务语义。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable  # noqa: F401
from datetime import datetime, timezone

import pytest

from dayu.engine import (
    ContentDeltaData,
    FinalAnswerData,
    FinishReason,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
)
from dayu.host._durable_event_store import open_durable_event_store
from dayu.host._event_observer import (
    ObserverDescriptor,
    ProjectionCoordinator,
    ProjectionEventEnvelope,
)
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import (
    GlobalEventPosition,
    ObserverStatus,
)
from dayu.host._projection_store import ProjectionStore
from dayu.host._run_state_store import RunStateStore
from dayu.host.contracts import (
    RunCancelledResult,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunFailedResult,
    RunSucceededResult,
    RunSuspendedResult,
)


def _utc() -> datetime:
    """返回当前 UTC 时间。

    :returns: 时区感知 UTC datetime。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _content_draft(*, run_id: str, idx: int) -> RunEventDraft:
    """构造 content delta preview 草稿。

    :param run_id: Run id。
    :param idx: 序号,用于 source_engine_event_id 唯一性。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.PREVIEW,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUNNER_CONTENT_DELTA,
        occurred_at=_utc(),
        data=ContentDeltaData(iteration_id="iter", delta=f"d{idx}"),
        source_engine_event_id=f"engine_{run_id}_{idx}",
    )


def _final_draft(*, run_id: str) -> RunEventDraft:
    """构造 FINAL_ANSWER canonical 草稿。

    :param run_id: Run id。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=_utc(),
        data=FinalAnswerData(
            content="ok",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        source_engine_event_id=f"engine_final_{run_id}",
    )


def _failed_draft(*, run_id: str) -> RunEventDraft:
    """构造 RUN_FAILED canonical 草稿。

    :param run_id: Run id。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUN_FAILED,
        occurred_at=_utc(),
        data=RunFailedData(
            error_code="boom",
            message="explosion",
            recoverable=False,
        ),
        source_engine_event_id=f"engine_failed_{run_id}",
    )


def _cancelled_draft(*, run_id: str) -> RunEventDraft:
    """构造 RUN_CANCELLED canonical 草稿。

    :param run_id: Run id。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    now = _utc()
    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUN_CANCELLED,
        occurred_at=now,
        data=RunCancelledData(
            reason="user_cancelled",
            requested_at=now,
            accepted_at=now,
            finished_at=now,
        ),
        source_engine_event_id=f"engine_cancelled_{run_id}",
    )


def _suspended_draft(*, run_id: str) -> RunEventDraft:
    """构造 RUN_SUSPENDED canonical 草稿。

    :param run_id: Run id。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUN_SUSPENDED,
        occurred_at=_utc(),
        data=RunSuspendedData(reason="awaiting_user", resume_hint=None),
        source_engine_event_id=f"engine_suspended_{run_id}",
    )


@pytest.mark.asyncio
async def test_terminal_persists_run_result_succeeded() -> None:
    """FINAL_ANSWER 终态在同事务写入 RunSucceededResult 快照。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)
        await store.append(_final_draft(run_id="r1"))
        run_state_store = RunStateStore(storage=storage)
        snapshot = run_state_store.get_terminal_result("r1")
        assert isinstance(snapshot, RunSucceededResult)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_terminal_persists_run_result_failed() -> None:
    """RUN_FAILED 终态写入 RunFailedResult 快照。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)
        await store.append(_failed_draft(run_id="r2"))
        snapshot = RunStateStore(storage=storage).get_terminal_result("r2")
        assert isinstance(snapshot, RunFailedResult)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_terminal_persists_run_result_cancelled() -> None:
    """RUN_CANCELLED 终态写入 RunCancelledResult 快照。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)
        await store.append(_cancelled_draft(run_id="r3"))
        snapshot = RunStateStore(storage=storage).get_terminal_result("r3")
        assert isinstance(snapshot, RunCancelledResult)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_terminal_persists_run_result_suspended() -> None:
    """RUN_SUSPENDED 终态写入 RunSuspendedResult 快照。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)
        await store.append(_suspended_draft(run_id="r4"))
        snapshot = RunStateStore(storage=storage).get_terminal_result("r4")
        assert isinstance(snapshot, RunSuspendedResult)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_duplicate_engine_event_id_raises_value_error() -> None:
    """同一 run 复用 ``source_engine_event_id`` 抛 ValueError。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)
        await store.append(_content_draft(run_id="r1", idx=0))
        with pytest.raises(ValueError, match="duplicate source_engine_event_id"):
            await store.append(_content_draft(run_id="r1", idx=0))
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_advance_success_idempotent_replay() -> None:
    """同一 position 重复 advance_success 不抛 regression。"""

    storage = HostStorage(database_path=":memory:")
    try:
        ProjectionStore(storage=storage)
        # 先 ensure schema 通过 event store 触发。
        store = open_durable_event_store(storage)
        await store.append(_content_draft(run_id="r1", idx=0))
        ps = ProjectionStore(storage=storage)
        async with storage.transaction() as tx:
            ps.ensure(
                tx=tx,
                observer_id="obs",
                projection_name="proj",
                schema_version=1,
            )
        async with storage.transaction() as tx:
            ps.advance_success(
                tx=tx,
                observer_id="obs",
                projection_name="proj",
                schema_version=1,
                position=GlobalEventPosition(value=1),
                status=ObserverStatus.RUNNING,
            )
        # 再次写入同一 position 必须成功(幂等重放语义)。
        async with storage.transaction() as tx:
            ps.advance_success(
                tx=tx,
                observer_id="obs",
                projection_name="proj",
                schema_version=1,
                position=GlobalEventPosition(value=1),
                status=ObserverStatus.CAUGHT_UP,
            )
        cp = ps.get(observer_id="obs", projection_name="proj", schema_version=1)
        assert cp is not None
        assert cp.status is ObserverStatus.CAUGHT_UP
        assert cp.last_success_position == GlobalEventPosition(value=1)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_advance_success_regression_raises() -> None:
    """checkpoint 严格不能倒退。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)
        await store.append(_content_draft(run_id="r1", idx=0))
        await store.append(_content_draft(run_id="r1", idx=1))
        ps = ProjectionStore(storage=storage)
        async with storage.transaction() as tx:
            ps.ensure(
                tx=tx,
                observer_id="obs",
                projection_name="proj",
                schema_version=1,
            )
            ps.advance_success(
                tx=tx,
                observer_id="obs",
                projection_name="proj",
                schema_version=1,
                position=GlobalEventPosition(value=2),
                status=ObserverStatus.RUNNING,
            )
        with pytest.raises(ValueError, match="regress"):
            async with storage.transaction() as tx:
                ps.advance_success(
                    tx=tx,
                    observer_id="obs",
                    projection_name="proj",
                    schema_version=1,
                    position=GlobalEventPosition(value=1),
                    status=ObserverStatus.RUNNING,
                )
    finally:
        storage.close()


class _RecordingObserver:
    """记录每次 process 调用的 observer。"""

    def __init__(self, observer_id: str = "obs1") -> None:
        """构造 observer。

        :param observer_id: observer id。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._descriptor = ObserverDescriptor(
            observer_id=observer_id,
            projection_name="proj",
            schema_version=1,
            required=False,
        )
        self.calls: list[tuple[ProjectionEventEnvelope, ...]] = []
        self.gate: asyncio.Event | None = None

    @property
    def descriptor(self) -> ObserverDescriptor:
        """返回 observer 描述符。

        :returns: ObserverDescriptor。
        :raises Exception: 不主动抛出异常。
        """

        return self._descriptor

    def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """记录 batch。

        :param tx: 当前事务。
        :param batch: 事件 envelope。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        del tx
        self.calls.append(batch)


@pytest.mark.asyncio
async def test_coordinator_drain_lock_serializes_concurrent_drains() -> None:
    """``_drain_lock`` 防止并发 drain 重入,事件不被重复消费。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)
        for idx in range(3):
            await store.append(_content_draft(run_id="r1", idx=idx))
        ps = ProjectionStore(storage=storage)
        observer = _RecordingObserver()
        coord = ProjectionCoordinator(
            storage=storage,
            event_store=store,
            projection_store=ps,
            observers=(observer,),
            batch_limit=1,
        )
        results = await asyncio.gather(coord.drain(), coord.drain())
        # 两次 drain 都应 caught_up。
        for snapshots in results:
            assert all(
                cp.status is ObserverStatus.CAUGHT_UP for cp in snapshots
            )
        # 只能被消费一遍 + 第二次 drain 在 caught_up 后 fast path 不再 process。
        total_envelopes = sum(len(batch) for batch in observer.calls)
        assert total_envelopes == 3
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_concurrent_multi_run_append_assigns_monotonic_global_position() -> None:
    """多 run 并发 append 的 global position 严格单调。"""

    storage = HostStorage(database_path=":memory:")
    try:
        store = open_durable_event_store(storage)

        async def _append_run(run_id: str, count: int) -> None:
            """串行 append 一组事件。

            :param run_id: Run id。
            :param count: 事件数。
            :returns: 无返回值。
            :raises Exception: 不主动抛出异常。
            """

            for idx in range(count):
                await store.append(_content_draft(run_id=run_id, idx=idx))

        await asyncio.gather(
            _append_run("rA", 5),
            _append_run("rB", 5),
            _append_run("rC", 5),
        )
        rows = store.fetch_events_by_position(after=None, limit=100)
        positions = [pos.value for pos, _ in rows]
        assert positions == sorted(positions)
        assert positions == list(range(1, 16))
        # 同一 run 内部 sequence 也应严格递增。
        per_run: dict[str, list[int]] = {}
        for _, event in rows:
            per_run.setdefault(event.run_id, []).append(event.cursor.sequence)
        for seqs in per_run.values():
            assert seqs == list(range(len(seqs)))
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_post_commit_hook_failure_does_not_break_transaction() -> None:
    """post-commit hook 抛异常被吞掉,后续 hook 仍执行,事务仍 committed。"""

    storage = HostStorage(database_path=":memory:")
    try:
        storage.open()
        called: list[str] = []

        def _bad_hook() -> None:
            """模拟 hook 抛异常。

            :returns: 无返回值。
            :raises RuntimeError: 始终抛出。
            """

            called.append("bad")
            raise RuntimeError("hook explode")

        def _good_hook() -> None:
            """模拟正常 hook。

            :returns: 无返回值。
            :raises Exception: 不主动抛出异常。
            """

            called.append("good")

        async with storage.transaction() as tx:
            tx.execute(
                "CREATE TABLE IF NOT EXISTS sentinel (k INTEGER PRIMARY KEY)"
            )
            tx.execute("INSERT INTO sentinel(k) VALUES (1)")
            tx.add_post_commit_hook(_bad_hook)
            tx.add_post_commit_hook(_good_hook)
        assert called == ["bad", "good"]
        rows = storage.execute_read("SELECT k FROM sentinel")
        assert [row[0] for row in rows] == [1]
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_transaction_rollback_on_exception_preserves_state() -> None:
    """事务体抛异常时 ROLLBACK,已写入数据应被回滚。"""

    storage = HostStorage(database_path=":memory:")
    try:
        storage.open()
        async with storage.transaction() as tx:
            tx.execute(
                "CREATE TABLE IF NOT EXISTS sentinel (k INTEGER PRIMARY KEY)"
            )
        with pytest.raises(RuntimeError, match="boom"):
            async with storage.transaction() as tx:
                tx.execute("INSERT INTO sentinel(k) VALUES (42)")
                raise RuntimeError("boom")
        rows = storage.execute_read("SELECT k FROM sentinel")
        assert rows == []
    finally:
        storage.close()


def _drafts_for(*, run_id: str, n: int) -> Iterable[RunEventDraft]:
    """生成 n 条 content drafts(诊断辅助,留给后续测试扩展)。

    :param run_id: Run id。
    :param n: 数量。
    :returns: 草稿迭代器。
    :raises Exception: 不主动抛出异常。
    """

    for idx in range(n):
        yield _content_draft(run_id=run_id, idx=idx)


__all__ = ["_drafts_for"]
