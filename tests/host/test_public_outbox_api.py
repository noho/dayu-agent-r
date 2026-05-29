"""Host public Outbox read / drain API 测试。"""

from __future__ import annotations

import pathlib

import pytest

from dayu.host import (
    DrainOutboxTerminalItemsRequest,
    HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT,
    HostApiError,
    HostApiErrorCode,
    HostClosedError,
    HostTerminalStatus,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    ReadOutboxTerminalItemsRequest,
    open_host,
)
from dayu.host.durable.transaction import HostTransactionRunner
from tests.host import public_smoke_support as smoke


@pytest.mark.asyncio
async def test_public_outbox_validation_and_closed_handle(
    tmp_path: pathlib.Path,
) -> None:
    """public request 校验参数越界，closed handle 抛 HostClosedError。"""

    with pytest.raises(ValueError):
        OutboxTerminalCursor(event_sequence=-1)
    with pytest.raises(ValueError):
        ReadOutboxTerminalItemsRequest(
            after=OutboxTerminalCursor(event_sequence=0),
            seen_terminal_event_ids=(),
            limit=0,
        )
    with pytest.raises(ValueError):
        ReadOutboxTerminalItemsRequest(
            after=OutboxTerminalCursor(event_sequence=0),
            seen_terminal_event_ids=(),
            limit=HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT + 1,
        )
    with pytest.raises(ValueError):
        ReadOutboxTerminalItemsRequest(
            after=OutboxTerminalCursor(event_sequence=0),
            seen_terminal_event_ids=("terminal-1", "terminal-1"),
            limit=1,
        )

    factory = smoke.FinalAnswerWorkerFactory()
    options = smoke.open_host_options(
        tmp_path,
        runner_spec=smoke.deterministic_runner_spec(),
        worker_factory=factory,
        allow_tool_calls=False,
    )
    manager = open_host(options)
    host = await manager.__aenter__()
    session = await host.ensure_session(smoke.ensure_request("outbox-closed"))
    await host.close()

    with pytest.raises(HostClosedError):
        await host.read_outbox_terminal_items(
            session.session_id,
            ReadOutboxTerminalItemsRequest(
                after=OutboxTerminalCursor(event_sequence=0),
                seen_terminal_event_ids=(),
                limit=1,
            ),
        )


@pytest.mark.asyncio
async def test_public_outbox_session_not_found_and_drain_conflict(
    tmp_path: pathlib.Path,
) -> None:
    """Session 缺失返回 not_found，drain request id 语义冲突返回 public 幂等错误。"""

    factory = smoke.FinalAnswerWorkerFactory()
    options = smoke.open_host_options(
        tmp_path,
        runner_spec=smoke.deterministic_runner_spec(),
        worker_factory=factory,
        allow_tool_calls=False,
    )

    async with open_host(options) as host:
        with pytest.raises(HostApiError) as missing:
            await host.read_outbox_terminal_items(
                "missing-session",
                ReadOutboxTerminalItemsRequest(
                    after=OutboxTerminalCursor(event_sequence=0),
                    seen_terminal_event_ids=(),
                    limit=1,
                ),
            )
        assert missing.value.code is HostApiErrorCode.NOT_FOUND

        session = await host.ensure_session(
            smoke.ensure_request("outbox-drain-conflict")
        )
        followup = await host.submit_followup(
            session.session_id,
            smoke.followup_request(
                session.session_id,
                "outbox-drain-conflict-run",
                "请给出最终答案",
            ),
        )
        await smoke.wait_for_status(
            host,
            followup.accepted_run_id,
            HostTerminalStatus.SUCCEEDED,
        )
        request = DrainOutboxTerminalItemsRequest(
            context=smoke.host_context("drain-conflict-1"),
            after=OutboxTerminalCursor(event_sequence=0),
            seen_terminal_event_ids=(),
            limit=1,
            drain_request_id="drain-conflict",
        )
        drained = await host.drain_outbox_terminal_items(
            session.session_id,
            request,
        )
        with pytest.raises(HostApiError) as conflict:
            await host.drain_outbox_terminal_items(
                session.session_id,
                DrainOutboxTerminalItemsRequest(
                    context=smoke.host_context("drain-conflict-2"),
                    after=drained.next_cursor,
                    seen_terminal_event_ids=(),
                    limit=1,
                    drain_request_id="drain-conflict",
                ),
            )

    assert conflict.value.code is HostApiErrorCode.IDEMPOTENCY_CONFLICT


@pytest.mark.asyncio
async def test_public_outbox_reports_lagged_then_catches_up(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """catch-up 未运行时返回 LAGGED，后续正常 read 可补到 terminal item。"""

    factory = smoke.FinalAnswerWorkerFactory()
    options = smoke.open_host_options(
        tmp_path,
        runner_spec=smoke.deterministic_runner_spec(),
        worker_factory=factory,
        allow_tool_calls=False,
    )

    async with open_host(options) as host:
        session = await host.ensure_session(smoke.ensure_request("outbox-lagged"))
        followup = await host.submit_followup(
            session.session_id,
            smoke.followup_request(
                session.session_id,
                "outbox-lagged-run",
                "请给出最终答案",
            ),
        )
        await smoke.wait_for_status(
            host,
            followup.accepted_run_id,
            HostTerminalStatus.SUCCEEDED,
        )
        monkeypatch.setattr(
            "dayu.host.read_api.catch_up_outbox_terminal_projection",
            _noop_outbox_catchup,
        )
        lagged = await host.read_outbox_terminal_items(
            session.session_id,
            ReadOutboxTerminalItemsRequest(
                after=OutboxTerminalCursor(event_sequence=0),
                seen_terminal_event_ids=(),
                limit=10,
            ),
        )
        monkeypatch.undo()
        caught_up = await host.read_outbox_terminal_items(
            session.session_id,
            ReadOutboxTerminalItemsRequest(
                after=OutboxTerminalCursor(event_sequence=0),
                seen_terminal_event_ids=(),
                limit=10,
            ),
        )

    assert lagged.projection_status is OutboxProjectionStatus.LAGGED
    assert lagged.items == ()
    assert caught_up.projection_status is OutboxProjectionStatus.CAUGHT_UP
    assert tuple(item.run_id for item in caught_up.items) == (
        followup.accepted_run_id,
    )


def _noop_outbox_catchup(
    transaction_runner: HostTransactionRunner,
) -> None:
    """测试用跳过 Outbox projection catch-up。

    :param transaction_runner: public API 传入的 transaction runner。
    :returns: ``None``。
    """

    del transaction_runner
    return None
