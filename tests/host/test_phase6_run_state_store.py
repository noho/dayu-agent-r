"""Host P6 RunStateStore / AttemptStateStore 测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.engine import FinalAnswerData, FinishReason
from dayu.host._durable_event_store import open_durable_event_store
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import (
    AttemptState,
    ExtendedRunState,
)
from dayu.host._run_state_store import AttemptStateStore, RunStateStore
from dayu.host.contracts import (
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunSucceededResult,
)


def _utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _final_draft(run_id: str = "r1") -> RunEventDraft:
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
async def test_run_state_transitions_to_terminal_on_final_answer() -> None:
    """final answer append 后 run state 必须切到 SUCCEEDED 并记录 cursor。"""

    storage = HostStorage(database_path=":memory:")
    store = open_durable_event_store(storage)
    run_state = RunStateStore(storage=storage)

    event = await store.append(_final_draft())
    record = run_state.get("r1")
    assert record is not None
    assert record.state is ExtendedRunState.SUCCEEDED
    assert record.terminal_event_cursor is not None
    assert record.terminal_event_cursor.sequence == event.cursor.sequence
    storage.close()


@pytest.mark.asyncio
async def test_run_state_terminal_result_round_trip() -> None:
    """terminal RunResult snapshot JSON encode/decode round trip。"""

    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    run_state = RunStateStore(storage=storage)
    async with storage.transaction() as tx:
        tx.execute(
            "INSERT INTO host_runs (run_id, session_id, state, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            ("r2", "s", ExtendedRunState.SUCCEEDED.value, "t", "t"),
        )
        run_state.write_terminal_result(
            tx=tx,
            run_id="r2",
            result=RunSucceededResult(
                run_id="r2",
                session_id="s",
                content="hello",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
                terminal_event_cursor=RunEventCursor(sequence=3),
            ),
        )
    decoded = run_state.get_terminal_result("r2")
    assert isinstance(decoded, RunSucceededResult)
    assert decoded.content == "hello"
    assert decoded.terminal_event_cursor.sequence == 3
    storage.close()


@pytest.mark.asyncio
async def test_attempt_state_create_and_update() -> None:
    """attempt 创建 + 状态推进与 terminal 字段写入。"""

    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    attempt_store = AttemptStateStore(storage=storage)
    async with storage.transaction() as tx:
        tx.execute(
            "INSERT INTO host_runs (run_id, session_id, state, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            ("r1", "s", ExtendedRunState.RUNNING.value, "t", "t"),
        )
        record = attempt_store.create(
            tx=tx, attempt_id="a1", run_id="r1", attempt_index=0
        )
    assert record.state is AttemptState.CREATED

    async with storage.transaction() as tx:
        attempt_store.update_state(
            tx=tx, attempt_id="a1", state=AttemptState.SUCCEEDED
        )
    fetched = attempt_store.get("a1")
    assert fetched is not None
    assert fetched.state is AttemptState.SUCCEEDED
    assert fetched.finished_at is not None
    storage.close()
