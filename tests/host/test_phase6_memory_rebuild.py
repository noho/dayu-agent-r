"""Host P6 memory rebuild 行为测试。

覆盖 P6 memory required projection 必须满足的事实：

- USER_INPUT_ACCEPTED 永不丢失。
- 成功终态写 assistant final answer raw turn。
- Engine RUN_FAILED 写中性 terminal summary。
- Host-owned RUN_FAILED 写中性 terminal summary。
- cancelled / suspended 不写 assistant terminal summary，仍保留用户输入。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.engine import (
    FinalAnswerData,
    FinishReason,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
)
from tests.host._memory_store_fake import (
    FakeInMemoryConversationMemoryStore,
)
from dayu.host._memory_projection import MemoryProjectionObserver
from dayu.host.contracts import (
    HostRunFailedData,
    RunEvent,
    RunEventCursor,
    RunEventKind,
    RunEventSource,
    RunEventType,
    UserInputAcceptedData,
    UserInputScope,
)


def _utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _user_input_event(*, run_id: str, content: str, sequence: int = 0) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        session_id="s",
        cursor=RunEventCursor(sequence=sequence),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.USER_INPUT_ACCEPTED,
        occurred_at=_utc(),
        data=UserInputAcceptedData(
            turn_id=run_id, content=content, scope=UserInputScope.SESSION
        ),
        source_engine_event_id=None,
    )


def _final_event(*, run_id: str, content: str, sequence: int = 1) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        session_id="s",
        cursor=RunEventCursor(sequence=sequence),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=_utc(),
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        source_engine_event_id=f"engine_{run_id}_final",
    )


def _engine_failed_event(*, run_id: str, sequence: int = 1) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        session_id="s",
        cursor=RunEventCursor(sequence=sequence),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUN_FAILED,
        occurred_at=_utc(),
        data=RunFailedData(
            error_code="model_unavailable",
            message="model is offline",
            recoverable=False,
        ),
        source_engine_event_id=f"engine_{run_id}_failed",
    )


def _host_failed_event(*, run_id: str, sequence: int = 1) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        session_id="s",
        cursor=RunEventCursor(sequence=sequence),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.RUN_FAILED,
        occurred_at=_utc(),
        data=HostRunFailedData(
            error_code="worker_internal_error",
            message="worker exited",
            recoverable=False,
            exception_type="RuntimeError",
        ),
        source_engine_event_id=None,
    )


def _cancelled_event(*, run_id: str, sequence: int = 1) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        session_id="s",
        cursor=RunEventCursor(sequence=sequence),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUN_CANCELLED,
        occurred_at=_utc(),
        data=RunCancelledData(
            reason="user_cancel",
            requested_at=_utc(),
            accepted_at=_utc(),
            finished_at=_utc(),
        ),
        source_engine_event_id=f"engine_{run_id}_cancelled",
    )


def _suspended_event(*, run_id: str, sequence: int = 1) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        session_id="s",
        cursor=RunEventCursor(sequence=sequence),
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUN_SUSPENDED,
        occurred_at=_utc(),
        data=RunSuspendedData(reason="awaiting_input", resume_hint=None),
        source_engine_event_id=f"engine_{run_id}_suspended",
    )


@pytest.mark.asyncio
async def test_memory_rebuild_keeps_user_input_on_success() -> None:
    """成功终态：user input + assistant raw turn 都进入 memory。"""

    memory = FakeInMemoryConversationMemoryStore()
    observer = MemoryProjectionObserver(memory_store=memory)
    await observer.rebuild_from_events(
        events=(
            _user_input_event(run_id="r1", content="问题1"),
            _final_event(run_id="r1", content="答案1"),
        )
    )
    snapshot = await memory.get_snapshot("s")
    user_texts = [t.user_text for t in snapshot.recent_raw_turns]
    assistant_finals = [t.assistant_final for t in snapshot.recent_raw_turns]
    assert "问题1" in user_texts
    assert any("答案1" in (text or "") for text in assistant_finals)


@pytest.mark.asyncio
async def test_memory_rebuild_engine_failure_writes_neutral_terminal() -> None:
    """Engine RUN_FAILED 必须写中性 terminal，user input 不丢。"""

    memory = FakeInMemoryConversationMemoryStore()
    observer = MemoryProjectionObserver(memory_store=memory)
    await observer.rebuild_from_events(
        events=(
            _user_input_event(run_id="r1", content="问题"),
            _engine_failed_event(run_id="r1"),
        )
    )
    snapshot = await memory.get_snapshot("s")
    assert any(
        t.user_text == "问题" for t in snapshot.recent_raw_turns
    )
    summaries = [t.terminal_summary or "" for t in snapshot.recent_raw_turns]
    assert any(
        "model_unavailable" in text for text in summaries
    )


@pytest.mark.asyncio
async def test_memory_rebuild_host_failure_writes_neutral_terminal() -> None:
    """Host-owned failure 也写中性 terminal summary。"""

    memory = FakeInMemoryConversationMemoryStore()
    observer = MemoryProjectionObserver(memory_store=memory)
    await observer.rebuild_from_events(
        events=(
            _user_input_event(run_id="r1", content="hi"),
            _host_failed_event(run_id="r1"),
        )
    )
    snapshot = await memory.get_snapshot("s")
    assert any(t.user_text == "hi" for t in snapshot.recent_raw_turns)


@pytest.mark.asyncio
async def test_memory_rebuild_cancelled_keeps_user_input_no_assistant() -> None:
    """cancelled 仅保留用户输入，不写 assistant terminal。"""

    memory = FakeInMemoryConversationMemoryStore()
    observer = MemoryProjectionObserver(memory_store=memory)
    await observer.rebuild_from_events(
        events=(
            _user_input_event(run_id="r1", content="cancel-me"),
            _cancelled_event(run_id="r1"),
        )
    )
    snapshot = await memory.get_snapshot("s")
    user_texts = [t.user_text for t in snapshot.recent_raw_turns]
    assert "cancel-me" in user_texts
    # cancelled 路径不写 assistant terminal（assistant_final 必须为空）。
    matching = [
        t for t in snapshot.recent_raw_turns if t.user_text == "cancel-me"
    ]
    assert matching
    assert all(
        t.assistant_final is None or t.assistant_final == "" for t in matching
    )


@pytest.mark.asyncio
async def test_memory_rebuild_suspended_keeps_user_input_no_assistant() -> None:
    """suspended 也只保留用户输入，不写 assistant terminal。"""

    memory = FakeInMemoryConversationMemoryStore()
    observer = MemoryProjectionObserver(memory_store=memory)
    await observer.rebuild_from_events(
        events=(
            _user_input_event(run_id="r1", content="pause"),
            _suspended_event(run_id="r1"),
        )
    )
    snapshot = await memory.get_snapshot("s")
    matching = [
        t for t in snapshot.recent_raw_turns if t.user_text == "pause"
    ]
    assert matching
    assert all(
        t.assistant_final is None or t.assistant_final == "" for t in matching
    )
