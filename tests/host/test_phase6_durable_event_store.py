"""Host P6 DurableRunEventStore append/replay/terminal/global-position 测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.engine import ContentDeltaData, FinalAnswerData, FinishReason
from dayu.host._durable_event_store import open_durable_event_store
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import GlobalEventPosition
from dayu.host.contracts import (
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
)


def _utc() -> datetime:
    """返回当前 UTC 时间。"""

    return datetime.now(tz=timezone.utc)


def _content_draft(*, run_id: str, idx: int) -> RunEventDraft:
    """构造 content delta preview draft。"""

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
    """构造 final answer canonical draft。"""

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
async def test_append_assigns_per_run_sequence_and_global_position() -> None:
    """同一 run 内 sequence 单调递增，跨 run global position 单调递增。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    e1 = await store.append(_content_draft(run_id="r1", idx=0))
    e2 = await store.append(_content_draft(run_id="r1", idx=1))
    e3 = await store.append(_content_draft(run_id="r2", idx=0))
    assert e1.cursor.sequence == 0
    assert e2.cursor.sequence == 1
    assert e3.cursor.sequence == 0

    rows = store.fetch_events_by_position(after=None, limit=10)
    assert tuple(p.value for p, _ in rows) == (1, 2, 3)
    storage.close()


@pytest.mark.asyncio
async def test_append_after_terminal_raises() -> None:
    """terminal 之后再 append 必须报错。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_final_draft(run_id="r1"))
    with pytest.raises(ValueError):
        await store.append(_content_draft(run_id="r1", idx=99))
    storage.close()


@pytest.mark.asyncio
async def test_subscribe_replays_then_completes_on_terminal() -> None:
    """先 replay 已有事件再阻塞，看到 terminal 后自动结束。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    await store.append(_content_draft(run_id="r1", idx=0))
    await store.append(_final_draft(run_id="r1"))
    seen: list[RunEventType] = []
    async for event in store.subscribe(run_id="r1", after=None):
        seen.append(event.type)
    assert seen == [RunEventType.RUNNER_CONTENT_DELTA, RunEventType.FINAL_ANSWER]
    storage.close()


@pytest.mark.asyncio
async def test_fetch_events_by_position_supports_pagination() -> None:
    """observer 可以按 global position 分页消费。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    for idx in range(5):
        await store.append(_content_draft(run_id="r1", idx=idx))
    page1 = store.fetch_events_by_position(after=None, limit=2)
    assert len(page1) == 2
    last_pos = page1[-1][0]
    page2 = store.fetch_events_by_position(after=last_pos, limit=10)
    assert len(page2) == 3
    assert page2[0][0].value > last_pos.value
    storage.close()


@pytest.mark.asyncio
async def test_engine_draft_requires_engine_event_id() -> None:
    """engine 来源必须携带 engine event id。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    bad = RunEventDraft(
        run_id="r",
        session_id="s",
        kind=RunEventKind.PREVIEW,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUNNER_CONTENT_DELTA,
        occurred_at=_utc(),
        data=ContentDeltaData(iteration_id="iter", delta="x"),
        source_engine_event_id=None,
    )
    with pytest.raises(ValueError):
        await store.append(bad)
    storage.close()


@pytest.mark.asyncio
async def test_latest_event_position_tracks_max() -> None:
    """latest_event_position 始终返回最大 position。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    assert store.latest_event_position() is None
    await store.append(_content_draft(run_id="r1", idx=0))
    pos = store.latest_event_position()
    assert isinstance(pos, GlobalEventPosition)
    assert pos.value == 1
    storage.close()
