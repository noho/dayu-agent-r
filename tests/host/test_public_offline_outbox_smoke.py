"""Public Outbox offline terminal delivery smoke 测试。"""

from __future__ import annotations

import pathlib
import sqlite3
from collections.abc import AsyncGenerator, AsyncIterator
from typing import cast

import pytest

from dayu.host import (
    DrainOutboxTerminalItemsRequest,
    HostEvent,
    HostEventKind,
    HostTerminalStatus,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItemState,
    ReadOutboxTerminalItemsRequest,
    open_host,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from tests.host import public_smoke_support as smoke


@pytest.mark.asyncio
async def test_offline_read_and_idempotent_drain_do_not_write_eventlog(
    tmp_path: pathlib.Path,
) -> None:
    """离线 terminal 可由 public read 补读；drain 幂等且不写 EventLog。"""

    factory = smoke.FinalAnswerWorkerFactory()
    options = smoke.open_host_options(
        tmp_path,
        runner_spec=smoke.deterministic_runner_spec(),
        worker_factory=factory,
        allow_tool_calls=False,
    )

    async with open_host(options) as host:
        session = await host.ensure_session(smoke.ensure_request("outbox-offline"))
        followup = await host.submit_followup(
            session.session_id,
            smoke.followup_request(
                session.session_id,
                "outbox-offline-run",
                "请给出最终答案",
            ),
        )
        await smoke.wait_for_status(
            host,
            followup.accepted_run_id,
            HostTerminalStatus.SUCCEEDED,
        )
        read = await host.read_outbox_terminal_items(
            session.session_id,
            ReadOutboxTerminalItemsRequest(
                after=OutboxTerminalCursor(event_sequence=0),
                seen_terminal_event_ids=(),
                limit=10,
            ),
        )
        before_drain_eventlog_count = _eventlog_count(options.db_path)
        drain_request = DrainOutboxTerminalItemsRequest(
            context=smoke.host_context("outbox-offline-drain"),
            after=OutboxTerminalCursor(event_sequence=0),
            seen_terminal_event_ids=(),
            limit=10,
            drain_request_id="outbox-offline-drain",
        )
        drained = await host.drain_outbox_terminal_items(
            session.session_id,
            drain_request,
        )
        replayed = await host.drain_outbox_terminal_items(
            session.session_id,
            drain_request,
        )
        after_drain_eventlog_count = _eventlog_count(options.db_path)

    assert read.projection_status is OutboxProjectionStatus.CAUGHT_UP
    assert len(read.items) == 1
    item = read.items[0]
    assert item.run_id == followup.accepted_run_id
    assert item.terminal_status is HostTerminalStatus.SUCCEEDED
    assert item.terminal_summary_ref is not None
    assert item.terminal_summary_digest is not None
    assert item.dedupe_key == item.terminal_event_id
    assert tuple(drained_item.item_id for drained_item in drained.items) == (
        item.item_id,
    )
    assert tuple(replayed_item.item_id for replayed_item in replayed.items) == (
        item.item_id,
    )
    assert drained.items[0].item_state is OutboxTerminalItemState.DRAINED
    assert after_drain_eventlog_count == before_drain_eventlog_count


@pytest.mark.asyncio
async def test_live_first_seen_ids_filter_outbox_duplicate(
    tmp_path: pathlib.Path,
) -> None:
    """live-first attach 后 Outbox 用 terminal_event_id 过滤已展示 terminal。"""

    factory = smoke.FinalAnswerWorkerFactory()
    options = smoke.open_host_options(
        tmp_path,
        runner_spec=smoke.deterministic_runner_spec(),
        worker_factory=factory,
        allow_tool_calls=False,
    )

    async with open_host(options) as host:
        session = await host.ensure_session(smoke.ensure_request("outbox-live-first"))
        watcher = host.watch_session_events(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                smoke.followup_request(
                    session.session_id,
                    "outbox-live-first-run",
                    "请给出最终答案",
                ),
            )
            terminal = await smoke.next_terminal_for_run(
                watcher,
                followup.accepted_run_id,
            )
            filtered = await host.read_outbox_terminal_items(
                session.session_id,
                ReadOutboxTerminalItemsRequest(
                    after=OutboxTerminalCursor(event_sequence=0),
                    seen_terminal_event_ids=(terminal.event_id,),
                    limit=10,
                ),
            )
            unfiltered = await host.read_outbox_terminal_items(
                session.session_id,
                ReadOutboxTerminalItemsRequest(
                    after=OutboxTerminalCursor(event_sequence=0),
                    seen_terminal_event_ids=(),
                    limit=10,
                ),
            )
        finally:
            await _close_iterator(watcher)

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert filtered.items == ()
    assert filtered.scanned_watermark.event_sequence >= terminal.event_sequence
    assert len(unfiltered.items) == 1
    assert unfiltered.items[0].terminal_event_id == terminal.event_id
    assert unfiltered.items[0].dedupe_key == terminal.dedupe_key


@pytest.mark.asyncio
async def test_drain_first_second_read_covers_live_attach_window(
    tmp_path: pathlib.Path,
) -> None:
    """drain-first 后的 second read 覆盖 live attach 窗口且不重复展示。"""

    factory = smoke.FinalAnswerWorkerFactory()
    options = smoke.open_host_options(
        tmp_path,
        runner_spec=smoke.deterministic_runner_spec(),
        worker_factory=factory,
        allow_tool_calls=False,
    )

    async with open_host(options) as host:
        session = await host.ensure_session(smoke.ensure_request("outbox-drain-first"))
        first_followup = await host.submit_followup(
            session.session_id,
            smoke.followup_request(
                session.session_id,
                "outbox-drain-first-run-1",
                "请给出第一个最终答案",
            ),
        )
        await smoke.wait_for_status(
            host,
            first_followup.accepted_run_id,
            HostTerminalStatus.SUCCEEDED,
        )
        first_batch = await host.drain_outbox_terminal_items(
            session.session_id,
            DrainOutboxTerminalItemsRequest(
                context=smoke.host_context("outbox-drain-first-drain"),
                after=OutboxTerminalCursor(event_sequence=0),
                seen_terminal_event_ids=(),
                limit=10,
                drain_request_id="outbox-drain-first-drain",
            ),
        )
        watcher = host.watch_session_events(session.session_id)
        try:
            second_followup = await host.submit_followup(
                session.session_id,
                smoke.followup_request(
                    session.session_id,
                    "outbox-drain-first-run-2",
                    "请给出第二个最终答案",
                ),
            )
            live_terminal = await smoke.next_terminal_for_run(
                watcher,
                second_followup.accepted_run_id,
            )
            second_read = await host.read_outbox_terminal_items(
                session.session_id,
                ReadOutboxTerminalItemsRequest(
                    after=first_batch.next_cursor,
                    seen_terminal_event_ids=(live_terminal.event_id,),
                    limit=10,
                ),
            )
        finally:
            await _close_iterator(watcher)

    assert len(first_batch.items) == 1
    assert first_batch.items[0].run_id == first_followup.accepted_run_id
    assert live_terminal.kind is HostEventKind.SUCCEEDED
    assert second_read.items == ()
    assert second_read.scanned_watermark.event_sequence >= live_terminal.event_sequence
    assert second_read.next_cursor.event_sequence >= live_terminal.event_sequence
    assert second_read.projection_status is OutboxProjectionStatus.CAUGHT_UP


async def _close_iterator(iterator: AsyncIterator[HostEvent]) -> None:
    """关闭 public HostEvent async iterator。

    :param iterator: HostEvent async iterator。
    :returns: ``None``。
    """

    await cast(AsyncGenerator[HostEvent, None], iterator).aclose()


def _eventlog_count(db_path: pathlib.Path) -> int:
    """读取 EventLog row 数量。

    :param db_path: Host SQLite 路径。
    :returns: EventLog row 数。
    :raises AssertionError: SQLite count 返回值不是整数时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            f"SELECT count(*) FROM {TABLE_EVENT_LOG}"
        ).fetchone()
    assert row is not None
    value = row[0]
    assert isinstance(value, int)
    return value
