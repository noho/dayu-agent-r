"""Host public Outbox read / drain API 测试。"""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

import pytest

from dayu.host import (
    DrainOutboxTerminalItemsRequest,
    HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT,
    HostApiError,
    HostApiErrorCode,
    HostClosedError,
    HostFinalAnswerView,
    HostTerminalStatus,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItem,
    OutboxTerminalItemState,
    ReadOutboxTerminalItemsRequest,
    open_host,
)
from dayu.host.durable.codec import canonical_json_dumps
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.schema import TABLE_HOST_OUTBOX_TERMINAL_ITEMS
from dayu.host.durable.transaction import HostTransactionRunner
from tests.host import public_smoke_support as smoke


def _public_outbox_item(
    *,
    terminal_status: HostTerminalStatus,
    final_answer: HostFinalAnswerView | None,
) -> OutboxTerminalItem:
    """构造 public Outbox 条件不变量测试 item。

    :param terminal_status: terminal 状态。
    :param final_answer: 可选 final answer view。
    :returns: 构造完成的 public item。
    :raises ValueError: terminal status 与 final answer 组合非法时抛出。
    """

    return OutboxTerminalItem(
        item_id="outbox-item",
        idempotency_key="sha256:item",
        terminal_event_id="terminal-event",
        event_sequence=1,
        session_id="session-1",
        run_id="run-1",
        terminal_status=terminal_status,
        dedupe_key="terminal-event",
        final_answer=final_answer,
        error_message=None,
        cancel_reason=None,
        result_ref=None,
        result_digest=None,
        terminal_summary_ref=None,
        terminal_summary_digest=None,
        projected_at=datetime(2026, 7, 10, tzinfo=UTC),
        item_state=OutboxTerminalItemState.PENDING,
    )


def test_public_outbox_terminal_final_answer_invariants() -> None:
    """public Outbox succeeded 必填，非成功三类禁止 final answer。

    :returns: ``None``。
    :raises AssertionError: conditional invariant 未生效时抛出。
    """

    final_answer = HostFinalAnswerView(
        content="answer",
        filtered=False,
        degraded=False,
        finish_reason="stop",
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )
    assert (
        _public_outbox_item(
            terminal_status=HostTerminalStatus.SUCCEEDED,
            final_answer=final_answer,
        ).final_answer
        is final_answer
    )
    with pytest.raises(ValueError, match="succeeded item requires final_answer"):
        _public_outbox_item(
            terminal_status=HostTerminalStatus.SUCCEEDED,
            final_answer=None,
        )
    for terminal_status in (
        HostTerminalStatus.FAILED,
        HostTerminalStatus.CANCELLED,
        HostTerminalStatus.LOST,
    ):
        with pytest.raises(ValueError, match="failed, cancelled or lost"):
            _public_outbox_item(
                terminal_status=terminal_status,
                final_answer=final_answer,
            )


@pytest.mark.parametrize("content", ("", " \t\n"))
@pytest.mark.asyncio
async def test_public_outbox_read_rejects_raw_blank_final_answer_content(
    tmp_path: pathlib.Path,
    content: str,
) -> None:
    """public read 对 raw Outbox row 的空白 content fail closed。

    :param tmp_path: pytest 临时目录。
    :param content: 直接写入 durable row 的空白回答文本。
    :returns: ``None``。
    :raises AssertionError: public read 未保留 Outbox field 诊断时抛出。
    """

    factory = smoke.FinalAnswerWorkerFactory()
    options = smoke.open_host_options(
        tmp_path,
        runner_spec=smoke.deterministic_runner_spec(),
        worker_factory=factory,
        allow_tool_calls=False,
    )

    async with open_host(options) as host:
        session = await host.ensure_session(smoke.ensure_request("outbox-raw-blank"))
        followup = await host.submit_followup(
            session.session_id,
            smoke.followup_request(
                session.session_id,
                "outbox-raw-blank-run",
                "请给出最终答案",
            ),
        )
        await smoke.wait_for_status(
            host,
            followup.accepted_run_id,
            HostTerminalStatus.SUCCEEDED,
        )
        materialized = await host.read_outbox_terminal_items(
            session.session_id,
            ReadOutboxTerminalItemsRequest(
                after=OutboxTerminalCursor(event_sequence=0),
                seen_terminal_event_ids=(),
                limit=10,
            ),
        )
        assert len(materialized.items) == 1
        terminal_event_id = materialized.items[0].terminal_event_id
        corrupted_json = canonical_json_dumps(
            {
                "content": content,
                "filtered": False,
                "degraded": False,
                "finish_reason": "stop",
                "terminal_status": "succeeded",
            }
        )
        with sqlite3.connect(options.db_path) as connection:
            connection.execute(
                f"""
                UPDATE {TABLE_HOST_OUTBOX_TERMINAL_ITEMS}
                SET final_answer_json = ?
                WHERE terminal_event_id = ?
                """,
                (corrupted_json, terminal_event_id),
            )

        with pytest.raises(HostApiError) as public_error:
            await host.read_outbox_terminal_items(
                session.session_id,
                ReadOutboxTerminalItemsRequest(
                    after=OutboxTerminalCursor(event_sequence=0),
                    seen_terminal_event_ids=(),
                    limit=10,
                ),
            )

    durable_error = public_error.value.__cause__
    assert public_error.value.code is HostApiErrorCode.INTERNAL_ERROR
    assert isinstance(durable_error, HostDurableError)
    diagnostic = str(durable_error)
    assert "Outbox" in diagnostic
    assert "field" in diagnostic
    assert "content" in diagnostic


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
