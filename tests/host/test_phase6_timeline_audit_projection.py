"""Host P6 timeline + audit projection observer 行为测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.engine import ContentDeltaData, FinalAnswerData, FinishReason
from dayu.host._audit_projection import AuditProjectionObserver
from dayu.host._durable_event_store import open_durable_event_store
from dayu.host._event_observer import ProjectionCoordinator
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._projection_store import ProjectionStore
from dayu.host._timeline_projection import TimelineProjectionObserver
from dayu.host.contracts import (
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
)


def _utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _content_draft(*, run_id: str, idx: int, kind: RunEventKind) -> RunEventDraft:
    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=kind,
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
async def test_timeline_observer_keeps_canonical_events_only() -> None:
    """timeline 仅累积 canonical 事件，preview 不进入。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(
        _content_draft(run_id="r1", idx=0, kind=RunEventKind.PREVIEW)
    )
    await store.append(_final_draft("r1"))

    observer = TimelineProjectionObserver()
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=ProjectionStore(storage=storage),
        observers=(observer,),
    )
    await coord.drain()

    timeline = observer.get_timeline("r1")
    assert len(timeline) == 1
    assert timeline[0].type is RunEventType.FINAL_ANSWER
    assert observer.list_runs() == ("r1",)
    storage.close()


@pytest.mark.asyncio
async def test_timeline_observer_orders_by_sequence() -> None:
    """timeline 按 cursor sequence 升序排列。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    for idx in range(3):
        await store.append(
            _content_draft(run_id="r1", idx=idx, kind=RunEventKind.CANONICAL)
        )

    observer = TimelineProjectionObserver()
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=ProjectionStore(storage=storage),
        observers=(observer,),
    )
    await coord.drain()

    seqs = [e.cursor.sequence for e in observer.get_timeline("r1")]
    assert seqs == sorted(seqs)
    storage.close()


@pytest.mark.asyncio
async def test_audit_observer_records_metadata_only() -> None:
    """audit 记录元数据，且按 position 升序累积、幂等。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(
        _content_draft(run_id="r1", idx=0, kind=RunEventKind.CANONICAL)
    )
    await store.append(_final_draft("r1"))

    observer = AuditProjectionObserver()
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=ProjectionStore(storage=storage),
        observers=(observer,),
    )
    await coord.drain()

    records = observer.list_records()
    assert len(records) == 2
    positions = [r.position.value for r in records]
    assert positions == sorted(positions)
    assert records[0].run_id == "r1"
    assert records[1].event_type is RunEventType.FINAL_ANSWER
    storage.close()


@pytest.mark.asyncio
async def test_audit_observer_skips_preview_kind() -> None:
    """audit 也仅记录 canonical 事件。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(
        _content_draft(run_id="r1", idx=0, kind=RunEventKind.PREVIEW)
    )

    observer = AuditProjectionObserver()
    coord = ProjectionCoordinator(
        storage=storage,
        event_store=store,
        projection_store=ProjectionStore(storage=storage),
        observers=(observer,),
    )
    await coord.drain()
    assert observer.list_records() == ()
    storage.close()
