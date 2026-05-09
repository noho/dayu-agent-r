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

    async def process(
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


# ---------------------------------------------------------------------------
# 本轮 PR review 修复回归用例
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_observer_sink_failure_preserves_pending_for_replay() -> None:
    """P0 修复：sink 抛异常时 ``_pending_by_run`` 不被破坏；下一次重放成功投影。

    模拟 ``ConversationMemoryStore.project_run_events`` 第一次失败、第二次成功，
    验证终态 batch 内的 USER_INPUT_ACCEPTED 与 FINAL_ANSWER 都没有丢失。
    """

    from dayu.engine import FinalAnswerData, FinishReason
    from dayu.host._conversation_memory import (
        ConversationMemorySnapshot,
        ConversationMemoryStore,
    )
    from dayu.host._event_observer import ProjectionEventEnvelope
    from dayu.host._internal_contracts import GlobalEventPosition
    from dayu.host._memory_projection import MemoryProjectionObserver
    from dayu.host.contracts import (
        RunEvent,
        RunEventCursor,
        UserInputAcceptedData,
        UserInputScope,
    )

    class _FlakyMemoryStore:
        """前 N 次抛异常的 fake memory store。"""

        def __init__(self, fail_times: int) -> None:
            """构造 fake。

            :param fail_times: 失败次数。
            :returns: 无返回值。
            :raises Exception: 不主动抛出异常。
            """

            self._remaining = fail_times
            self.projected: list[tuple[RunEvent, ...]] = []

        async def project_run_events(
            self, events: tuple[RunEvent, ...]
        ) -> None:
            """模拟 sink。

            :param events: 事件元组。
            :returns: 无返回值。
            :raises RuntimeError: 在剩余失败计数 > 0 时抛出。
            """

            if self._remaining > 0:
                self._remaining -= 1
                raise RuntimeError("sink failure")
            self.projected.append(events)

        async def get_snapshot(
            self, session_id: str
        ) -> ConversationMemorySnapshot:
            """未使用，仅满足协议。

            :param session_id: 会话 id。
            :returns: 永不调用，返回 None 即可。
            :raises NotImplementedError: 始终。
            """

            del session_id
            raise NotImplementedError

    flaky: ConversationMemoryStore = _FlakyMemoryStore(fail_times=1)  # type: ignore[assignment]
    observer = MemoryProjectionObserver(memory_store=flaky)

    user_event = RunEvent(
        run_id="rX",
        session_id="s",
        cursor=RunEventCursor(sequence=0),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.USER_INPUT_ACCEPTED,
        occurred_at=_utc(),
        data=UserInputAcceptedData(
            turn_id="rX", content="hello", scope=UserInputScope.SESSION
        ),
        source_engine_event_id=None,
    )
    final_event = RunEvent(
        run_id="rX",
        session_id="s",
        cursor=RunEventCursor(sequence=1),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=_utc(),
        data=FinalAnswerData(
            content="world",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        source_engine_event_id="engine_rX_final",
    )
    batch = (
        ProjectionEventEnvelope(
            position=GlobalEventPosition(value=1), event=user_event
        ),
        ProjectionEventEnvelope(
            position=GlobalEventPosition(value=2), event=final_event
        ),
    )

    storage = HostStorage(database_path=":memory:")
    storage.open()
    try:
        # 第一次：sink 抛 RuntimeError；observer 不能因失败破坏内部状态，
        # 即使 _pending_by_run 之前已累积过其他 run 的事件，也必须保留。
        observer._pending_by_run["other_run"] = []  # noqa: SLF001
        with pytest.raises(RuntimeError, match="sink failure"):
            async with storage.transaction() as tx:
                await observer.process(tx=tx, batch=batch)
        # 关键不变量：失败后 _pending_by_run 不能被破坏（之前累积的 run 仍在）。
        assert "other_run" in observer._pending_by_run  # noqa: SLF001

        # 第二次重放：sink 成功；coordinator 会用同一 batch 重放，整批应被完整投影。
        async with storage.transaction() as tx:
            await observer.process(tx=tx, batch=batch)
        assert len(flaky.projected) == 1  # type: ignore[attr-defined]
        projected_events = flaky.projected[0]  # type: ignore[attr-defined]
        types = [e.type for e in projected_events]
        assert RunEventType.USER_INPUT_ACCEPTED in types
        assert RunEventType.FINAL_ANSWER in types
        # terminal 投影成功后 pending 必须被清掉，避免无限累积。
        assert "rX" not in observer._pending_by_run  # noqa: SLF001
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_durable_bundle_startup_reconcile_catches_up_after_crash() -> None:
    """P1 修复：模拟崩溃后只剩 EventLog + RunResult，``startup_reconcile`` 追平 read model。"""

    from dayu.host._conversation_memory import InMemoryConversationMemoryStore
    from dayu.host._durable_harness import (
        DurableHarnessConfig,
        build_durable_harness,
    )
    from dayu.host.contracts import UserInputAcceptedData, UserInputScope

    memory = InMemoryConversationMemoryStore()
    bundle_a = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:"),
        memory_store=memory,
    )
    storage = bundle_a.storage
    try:
        # 写入完整 terminal run（用户输入 + final answer）但 *不* 调用 coordinator.drain()。
        user_draft = RunEventDraft(
            run_id="rZ",
            session_id="s",
            kind=RunEventKind.CANONICAL,
            source=RunEventSource.HOST,
            type=RunEventType.USER_INPUT_ACCEPTED,
            occurred_at=_utc(),
            data=UserInputAcceptedData(
                turn_id="rZ", content="hi", scope=UserInputScope.SESSION
            ),
            source_engine_event_id=None,
        )
        await bundle_a.event_store.append(user_draft)
        await bundle_a.event_store.append(_final_draft(run_id="rZ"))
        # memory store 此刻应为空（没有任何 projection 调用过）。
        snapshot = await memory.get_snapshot("s")
        assert snapshot.recent_raw_turns == ()

        # 启动追平：startup_reconcile 必须把 memory 推进到含本轮 raw turns 的状态。
        await bundle_a.startup_reconcile()
        snapshot = await memory.get_snapshot("s")
        assert snapshot.recent_raw_turns != ()
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_finish_attempt_if_durable_rejects_terminal_event_and_state_together() -> None:
    """``_finish_attempt_if_durable`` 同时传 terminal_event 与 state 时抛 ValueError。"""

    from dayu.host._durable_harness import (
        DurableHarnessConfig,
        build_durable_harness,
    )
    from dayu.host._run_harness import _ActiveAttempt
    from dayu.host._run_state_store import AttemptState
    from dayu.host.contracts import RunEvent, RunEventCursor

    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:")
    )
    try:
        harness = bundle.harness
        fake_event = RunEvent(
            run_id="rA",
            session_id="s",
            cursor=RunEventCursor(sequence=0),
            kind=RunEventKind.CANONICAL,
            source=RunEventSource.ENGINE,
            type=RunEventType.RUN_FAILED,
            occurred_at=_utc(),
            data=RunFailedData(
                error_code="x", message="y", recoverable=False
            ),
            source_engine_event_id="engine_rA_failed",
        )
        active = _ActiveAttempt(
            attempt_id="att_1",
            owner_context=None,
            lease_exit_stack=None,
        )
        with pytest.raises(ValueError, match="terminal_event"):
            await harness._finish_attempt_if_durable(  # noqa: SLF001
                active_attempt=active,
                terminal_event=fake_event,
                state=AttemptState.FAILED,
            )
    finally:
        bundle.close()


__all__ = ["_drafts_for"]
