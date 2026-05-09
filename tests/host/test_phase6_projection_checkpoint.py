"""Host P6 ProjectionStore + ProjectionCoordinator 行为测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.engine import ContentDeltaData, FinalAnswerData, FinishReason
from dayu.host._audit_projection import AuditProjectionObserver
from dayu.host._durable_event_store import open_durable_event_store
from dayu.host._event_observer import (
    ObserverDescriptor,
    ProjectionCoordinator,
    ProjectionEventEnvelope,
    RetryableProjectionError,
)
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import GlobalEventPosition, ObserverStatus
from dayu.host._projection_store import ProjectionStore
from dayu.host.contracts import (
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
)


def _utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _content_draft(*, run_id: str, idx: int) -> RunEventDraft:
    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUNNER_CONTENT_DELTA,
        occurred_at=_utc(),
        data=ContentDeltaData(iteration_id="iter", delta=f"d{idx}"),
        source_engine_event_id=f"engine_{run_id}_{idx}",
    )


def _final_draft(run_id: str) -> RunEventDraft:
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


@pytest.mark.asyncio
async def test_projection_checkpoint_advances_after_drain() -> None:
    """observer drain 完成后 checkpoint 应该推进到 latest position。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))
    await store.append(_final_draft("r1"))

    observer = AuditProjectionObserver()
    proj_store = ProjectionStore(storage=storage)
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(observer,),
    )
    snapshots = await coord.drain()
    assert len(snapshots) == 1
    cp = snapshots[0]
    assert cp.last_success_position is not None
    assert cp.last_success_position.value == 2
    assert cp.status in {ObserverStatus.RUNNING, ObserverStatus.CAUGHT_UP}
    assert len(observer.list_records()) == 2
    storage.close()


class _RetryOnceObserver:
    """测试用 observer，第一次抛 retryable，第二次成功。"""

    def __init__(self) -> None:
        self._calls = 0
        self.processed_positions: list[int] = []

    @property
    def descriptor(self) -> ObserverDescriptor:
        return ObserverDescriptor(
            observer_id="retry_once",
            projection_name="retry_test",
            schema_version=1,
            required=False,
        )

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        del tx
        self._calls += 1
        if self._calls == 1:
            raise RetryableProjectionError("transient")
        for env in batch:
            self.processed_positions.append(env.position.value)


@pytest.mark.asyncio
async def test_observer_retryable_failure_does_not_advance() -> None:
    """RetryableProjectionError 必须只标 RETRYABLE_FAILED，不前进。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))

    observer = _RetryOnceObserver()
    proj_store = ProjectionStore(storage=storage)
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(observer,),
    )
    await coord.initialize()
    snap1 = await coord.run_once(observer=observer)
    assert snap1.status is ObserverStatus.RETRYABLE_FAILED
    assert snap1.last_success_position is None
    assert snap1.retry_count >= 1

    snap2 = await coord.run_once(observer=observer)
    assert snap2.status in {ObserverStatus.RUNNING, ObserverStatus.CAUGHT_UP}
    assert snap2.last_success_position is not None
    assert observer.processed_positions == [1]
    storage.close()


class _BlockingObserver:
    """非 retryable 异常 observer，验证 BLOCKED_FAILED 路径。"""

    @property
    def descriptor(self) -> ObserverDescriptor:
        return ObserverDescriptor(
            observer_id="blocking",
            projection_name="blocking_test",
            schema_version=1,
            required=True,
        )

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        del tx, batch
        raise RuntimeError("blocked")


@pytest.mark.asyncio
async def test_observer_non_retryable_failure_marks_blocked() -> None:
    """普通异常进入 BLOCKED_FAILED，不前进 success position。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))

    observer = _BlockingObserver()
    proj_store = ProjectionStore(storage=storage)
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=proj_store,
        observers=(observer,),
    )
    await coord.initialize()
    snap = await coord.run_once(observer=observer)
    assert snap.status is ObserverStatus.BLOCKED_FAILED
    assert snap.last_success_position is None
    assert snap.last_error_code == "RuntimeError"
    storage.close()


@pytest.mark.asyncio
async def test_projection_store_advance_regression_rejected() -> None:
    """checkpoint 倒退必须被 ProjectionStore 拒绝。"""

    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    proj = ProjectionStore(storage=storage)
    async with storage.transaction() as tx:
        proj.ensure(
            tx=tx,
            observer_id="x",
            projection_name="y",
            schema_version=1,
        )
        proj.advance_success(
            tx=tx,
            observer_id="x",
            projection_name="y",
            schema_version=1,
            position=GlobalEventPosition(value=10),
            status=ObserverStatus.RUNNING,
        )
    with pytest.raises(ValueError):
        async with storage.transaction() as tx:
            proj.advance_success(
                tx=tx,
                observer_id="x",
                projection_name="y",
                schema_version=1,
                position=GlobalEventPosition(value=5),
                status=ObserverStatus.RUNNING,
            )
    storage.close()


@pytest.mark.asyncio
async def test_projection_lag_events_reflects_remaining_events() -> None:
    """checkpoint 报告的 lag = MAX(position) - last_success_position。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    for idx in range(3):
        await store.append(_content_draft(run_id="r1", idx=idx))

    proj = ProjectionStore(storage=storage)
    async with storage.transaction() as tx:
        proj.ensure(
            tx=tx,
            observer_id="x",
            projection_name="y",
            schema_version=1,
        )
        proj.advance_success(
            tx=tx,
            observer_id="x",
            projection_name="y",
            schema_version=1,
            position=GlobalEventPosition(value=1),
            status=ObserverStatus.RUNNING,
        )
    cp = proj.get(observer_id="x", projection_name="y", schema_version=1)
    assert cp is not None
    assert cp.lag_events == 2
    storage.close()
