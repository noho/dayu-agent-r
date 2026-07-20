"""三类 Host transient delta 的独立高量 production-runtime stress 测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator
from typing import Protocol, cast

import pytest

from dayu.engine.contracts.engine_events import EngineEventType
from dayu.host import (
    HostEvent,
    HostEventKind,
    HostSessionEvent,
    HostTransientDelta,
    HostTransientDeltaType,
    OutboxTerminalCursor,
    ReadOutboxTerminalItemsRequest,
    RunStatus,
    open_host,
)
from tests.host.public_smoke_support import (
    ensure_request,
    followup_request,
)
from tests.host.transient_stream_support import (
    TransientStreamCounts,
    TransientStreamWorkerFactory,
    event_log_type_count,
    read_transient_durable_snapshot,
    transient_stream_open_host_options,
)

pytestmark = pytest.mark.stress

_DELTA_COUNT_PER_TYPE = 1_000
_STRESS_TIMEOUT_SECONDS = 120.0
_FINAL_ANSWER = "transient-stress-final"


class _ClosableSessionEventIterator(Protocol):
    """stress 测试使用的可关闭 Session event iterator 窄协议。"""

    async def aclose(self) -> None:
        """关闭 iterator。

        :returns: ``None``。
        :raises Exception: Host iterator cleanup 失败时透传。
        """

        ...


@pytest.mark.asyncio
async def test_three_thousand_transient_deltas_leave_zero_rows_and_durable_terminal(
    tmp_path: pathlib.Path,
) -> None:
    """三类 delta 各 1000 条仍为零 row，Run/Attempt/final durable facts 完整。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 数量、zero-row 或 durable 同源 contract 漂移时抛出。
    """

    expected_counts = TransientStreamCounts(
        content=_DELTA_COUNT_PER_TYPE,
        reasoning=_DELTA_COUNT_PER_TYPE,
        tool_call=_DELTA_COUNT_PER_TYPE,
    )
    factory = TransientStreamWorkerFactory(
        counts=expected_counts,
        final_answer=_FINAL_ANSWER,
    )
    options = transient_stream_open_host_options(tmp_path, factory)

    async with open_host(options) as host:
        session = await host.ensure_session(ensure_request("transient-stress"))
        watcher = host.watch_session_events(session.session_id)
        observation_task = asyncio.create_task(_collect_until_terminal(watcher))
        followup = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "transient-stress-followup",
                "run transient delta stress",
            ),
        )
        observed_counts, terminal = await asyncio.wait_for(
            observation_task,
            timeout=_STRESS_TIMEOUT_SECONDS,
        )
        run = await host.get_run(followup.accepted_run_id)
        outbox = await host.read_outbox_terminal_items(
            session.session_id,
            ReadOutboxTerminalItemsRequest(
                after=OutboxTerminalCursor(event_sequence=0),
                limit=50,
                seen_terminal_event_ids=(),
            ),
        )
        await cast(_ClosableSessionEventIterator, watcher).aclose()

    assert observed_counts == expected_counts
    assert terminal.kind is HostEventKind.SUCCEEDED
    assert terminal.final_answer is not None
    assert terminal.final_answer.content == _FINAL_ANSWER
    assert run.status is RunStatus.SUCCEEDED
    assert run.current_attempt_id is not None
    assert factory.cancel_reasons == []

    matching_outbox = tuple(
        item for item in outbox.items if item.run_id == followup.accepted_run_id
    )
    assert len(matching_outbox) == 1
    assert matching_outbox[0].terminal_event_id == terminal.event_id
    assert matching_outbox[0].dedupe_key == terminal.dedupe_key
    assert matching_outbox[0].final_answer == terminal.final_answer

    assert event_log_type_count(options.db_path, EngineEventType.CONTENT_DELTA.value) == 0
    assert event_log_type_count(options.db_path, EngineEventType.REASONING_DELTA.value) == 0
    assert event_log_type_count(options.db_path, EngineEventType.TOOL_CALL_DELTA.value) == 0
    assert event_log_type_count(options.db_path, "RUN_SUCCEEDED") == 1

    durable = read_transient_durable_snapshot(
        options.db_path,
        run_id=followup.accepted_run_id,
    )
    assert durable.run_status == "succeeded"
    assert durable.run_attempt_id == run.current_attempt_id
    assert durable.attempt_count == 1
    assert durable.attempt_status == "succeeded"
    assert durable.terminal_event_type == "RUN_SUCCEEDED"
    assert durable.run_terminal_event_id == terminal.event_id
    assert durable.run_terminal_event_sequence == terminal.event_sequence
    assert durable.terminal_event_id == terminal.event_id
    assert durable.terminal_event_sequence == terminal.event_sequence
    assert durable.attempt_terminal_event_id != terminal.event_id
    assert durable.attempt_terminal_event_sequence < terminal.event_sequence


async def _collect_until_terminal(
    watcher: AsyncIterator[HostSessionEvent],
) -> tuple[TransientStreamCounts, HostEvent]:
    """快速消费真实 Host watcher，统计三类 delta 并返回成功 terminal。

    :param watcher: 已同步 attach 的 Host Session event iterator。
    :returns: 三类观测计数与 terminal HostEvent。
    :raises AssertionError: 收到非成功 terminal 或 iterator 提前结束时抛出。
    """

    content_count = 0
    reasoning_count = 0
    tool_call_count = 0
    async for event in watcher:
        if isinstance(event, HostTransientDelta):
            if event.type is HostTransientDeltaType.CONTENT_DELTA:
                content_count += 1
            elif event.type is HostTransientDeltaType.REASONING_DELTA:
                reasoning_count += 1
            elif event.type is HostTransientDeltaType.TOOL_CALL_DELTA:
                tool_call_count += 1
            else:
                raise AssertionError(f"unexpected transient type: {event.type}")
            continue
        if event.kind is HostEventKind.SUCCEEDED:
            return (
                TransientStreamCounts(
                    content=content_count,
                    reasoning=reasoning_count,
                    tool_call=tool_call_count,
                ),
                event,
            )
        if event.terminal_status is not None:
            raise AssertionError(f"unexpected terminal kind: {event.kind}")
    raise AssertionError("Host watcher ended before terminal")
