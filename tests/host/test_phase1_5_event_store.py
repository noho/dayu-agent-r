"""Host P1.5 RunEventStore 行为测试。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from _pytest.logging import LogCaptureFixture

from dayu.engine import ContentDeltaData, FinalAnswerData, FinishReason
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
)

_WAIT_SECONDS: float = 0.5


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _content_draft(
    *,
    run_id: str = "run",
    session_id: str = "session",
    delta: str = "hello",
) -> RunEventDraft:
    """构造 content delta preview 事件草稿。

    :param run_id: Run id。
    :param session_id: Session id。
    :param delta: 增量正文。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.PREVIEW,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUNNER_CONTENT_DELTA,
        occurred_at=_utc_now(),
        data=ContentDeltaData(iteration_id="iter", delta=delta),
        source_engine_event_id=f"engine_{delta}",
    )


def _final_draft(
    *,
    run_id: str = "run",
    session_id: str = "session",
    content: str = "done",
) -> RunEventDraft:
    """构造 final answer canonical 事件草稿。

    :param run_id: Run id。
    :param session_id: Session id。
    :param content: 最终回答正文。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=_utc_now(),
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        source_engine_event_id=f"engine_final_{content}",
    )


async def _next_event(events: AsyncIterator[RunEvent]) -> RunEvent:
    """带超时读取下一个 RunEvent。

    :param events: RunEvent 异步流。
    :returns: 下一个 RunEvent。
    :raises TimeoutError: 超时未收到事件时抛出。
    """

    return await asyncio.wait_for(anext(events), timeout=_WAIT_SECONDS)


@pytest.mark.asyncio
async def test_append_assigns_per_run_monotonic_cursor() -> None:
    """append 为每个 run 独立分配严格单调 cursor。"""

    store = InMemoryRunEventStore()

    first = await store.append(_content_draft(run_id="run_a", delta="a"))
    second = await store.append(_content_draft(run_id="run_a", delta="b"))
    other = await store.append(_content_draft(run_id="run_b", delta="c"))

    assert [first.cursor.sequence, second.cursor.sequence] == [0, 1]
    assert other.cursor.sequence == 0


@pytest.mark.asyncio
async def test_list_events_uses_exclusive_cursor() -> None:
    """list_events 只返回 after cursor 之后的事件。"""

    store = InMemoryRunEventStore()
    first = await store.append(_content_draft(delta="a"))
    second = await store.append(_content_draft(delta="b"))
    terminal = await store.append(_final_draft())

    events = await store.list_events(run_id="run", after=first.cursor)

    assert events == (second, terminal)


@pytest.mark.asyncio
async def test_subscribe_replays_then_follows_without_lost_wakeup() -> None:
    """subscribe 先补读已 append 事件，再等待后续 append。"""

    store = InMemoryRunEventStore()
    first = await store.append(_content_draft(delta="a"))
    events = store.subscribe(run_id="run", after=None)

    replayed = await _next_event(events)
    assert replayed == first

    followed_task = asyncio.create_task(_next_event(events))
    await asyncio.sleep(0)
    terminal = await store.append(_final_draft())

    assert await followed_task == terminal


@pytest.mark.asyncio
async def test_subscribe_follow_uses_cursor_predicate_without_waiter() -> None:
    """follow 前已经 append 的事件也必须被 cursor predicate 捕获。"""

    store = InMemoryRunEventStore()
    first = await store.append(_content_draft(delta="a"))
    events = store.subscribe(run_id="run", after=None)

    replayed = await _next_event(events)
    assert replayed == first

    terminal = await store.append(_final_draft())

    assert await _next_event(events) == terminal


@pytest.mark.asyncio
async def test_subscribe_after_terminal_exits_immediately() -> None:
    """after 已越过 terminal cursor 时订阅不会永久等待。"""

    store = InMemoryRunEventStore()
    terminal = await store.append(_final_draft())
    events = store.subscribe(run_id="run", after=terminal.cursor)

    with pytest.raises(StopAsyncIteration):
        await _next_event(events)


@pytest.mark.asyncio
async def test_append_rejects_non_terminal_after_terminal() -> None:
    """store 边界拒绝同一 run 终态后的非终态事件。"""

    store = InMemoryRunEventStore()
    terminal = await store.append(_final_draft())

    with pytest.raises(ValueError, match="after terminal event"):
        await store.append(_content_draft(delta="late"))

    assert await store.list_events(run_id="run", after=None) == (terminal,)
    assert await store.list_events(run_id="run", after=terminal.cursor) == ()
    events = store.subscribe(run_id="run", after=terminal.cursor)
    with pytest.raises(StopAsyncIteration):
        await _next_event(events)


@pytest.mark.asyncio
async def test_append_rejects_second_terminal_after_terminal() -> None:
    """store 边界拒绝同一 run 终态后的第二个终态事件。"""

    store = InMemoryRunEventStore()
    terminal = await store.append(_final_draft(content="first"))

    with pytest.raises(ValueError, match="after terminal event"):
        await store.append(_final_draft(content="second"))

    assert await store.list_events(run_id="run", after=None) == (terminal,)


@pytest.mark.asyncio
async def test_cursor_is_not_bound_to_engine_sequence() -> None:
    """Host cursor 由 store 生成，不从 draft 外部注入。"""

    store = InMemoryRunEventStore()
    first = await store.append(_content_draft(delta="first"))
    replay = await store.list_events(
        run_id="run",
        after=RunEventCursor(sequence=-1),
    )

    assert first.cursor.sequence == 0
    assert replay == (first,)


@pytest.mark.asyncio
async def test_append_rejects_engine_source_without_engine_event_id() -> None:
    """Engine 来源事件必须携带 source_engine_event_id。"""

    store = InMemoryRunEventStore()
    draft = replace(_content_draft(), source_engine_event_id=None)

    with pytest.raises(ValueError, match="requires source_engine_event_id"):
        await store.append(draft)


@pytest.mark.asyncio
async def test_append_rejects_host_source_with_engine_event_id() -> None:
    """Host 来源事件不得携带 source_engine_event_id。"""

    store = InMemoryRunEventStore()
    draft = replace(
        _content_draft(),
        source=RunEventSource.HOST,
        source_engine_event_id="engine_id",
    )

    with pytest.raises(ValueError, match="must not set source_engine_event_id"):
        await store.append(draft)


@pytest.mark.asyncio
async def test_debug_logs_skip_preview_append_and_subscribe_polling(
    caplog: LogCaptureFixture,
) -> None:
    """DEBUG 日志保留存储边界，但不刷 preview append 与 subscribe 轮询。"""

    store = InMemoryRunEventStore()
    caplog.set_level(logging.DEBUG, logger="dayu.host._event_store")

    events = store.subscribe(run_id="run", after=None)
    first_task = asyncio.create_task(_next_event(events))
    await asyncio.sleep(0)

    preview = await store.append(_content_draft(delta="preview-secret"))
    assert await first_task == preview

    terminal_task = asyncio.create_task(_next_event(events))
    await asyncio.sleep(0)
    terminal = await store.append(_final_draft(content="done"))
    assert await terminal_task == terminal
    with pytest.raises(StopAsyncIteration):
        await _next_event(events)

    messages = [record.getMessage() for record in caplog.records]
    log_text = "\n".join(messages)
    assert "host.event_store.subscribe_start" in log_text
    assert "host.event_store.subscribe_complete" in log_text
    assert "host.event_store.appended" in log_text
    assert "type=final_answer" in log_text
    assert "terminal=True" in log_text
    assert "type=runner_content_delta" not in log_text
    assert "preview-secret" not in log_text
    assert "host.event_store.subscribe_wait" not in log_text
    assert "host.event_store.subscribe_batch" not in log_text
