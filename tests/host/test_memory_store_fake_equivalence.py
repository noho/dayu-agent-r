"""tests-only ``FakeInMemoryConversationMemoryStore`` 与 durable store
behavior 等价性最小验证 (P8 S9 R5)。

R5 关注: ``tests/host/_memory_store_fake`` 与生产 durable store 不能在
canonical 投影 / patch / get_snapshot 行为上偏离。本文件仅做最小行为对齐
断言, 覆盖 fake 的 reset / scope clear / canonical event 投影路径与
durable 实现一致; 更深的 fuzz / 随机 trace 覆盖不在本 P8 范围, 见 plan
R5 owner: P9。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayu.host._conversation_memory import (
    MemoryResetPatch,
    MemoryScope,
    ScopeClearPatch,
    _empty_snapshot,
    _project_canonical_events,
)
from dayu.host._durable_harness import (
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host._event_translation import user_input_accepted_draft

from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore


_SESSION_ID: str = "fake-equiv-session"
_RUN_ID: str = "fake-equiv-run"


@pytest.mark.asyncio
async def test_fake_reset_clears_session_like_durable() -> None:
    """``MemoryResetPatch`` 在 fake 与 durable store 上行为一致。"""

    fake = FakeInMemoryConversationMemoryStore()
    await fake.apply_patch(
        MemoryResetPatch(
            session_id=_SESSION_ID,
            scope=MemoryScope.SESSION,
            reason="test_reset",
        )
    )
    fake_snapshot = await fake.get_snapshot(_SESSION_ID)

    config = DurableHarnessConfig(database_path=":memory:")
    bundle = build_durable_harness(config=config)
    try:
        await bundle.memory_store.apply_patch(
            MemoryResetPatch(
                session_id=_SESSION_ID,
                scope=MemoryScope.SESSION,
                reason="test_reset",
            )
        )
        durable_snapshot = await bundle.memory_store.get_snapshot(
            _SESSION_ID
        )
    finally:
        bundle.close()

    assert fake_snapshot == durable_snapshot


@pytest.mark.asyncio
async def test_fake_session_scope_clear_matches_durable() -> None:
    """``ScopeClearPatch(SESSION)`` 在 fake 与 durable store 上行为一致。"""

    fake = FakeInMemoryConversationMemoryStore()
    await fake.apply_patch(
        ScopeClearPatch(
            session_id=_SESSION_ID,
            scope=MemoryScope.SESSION,
            reason="test_clear",
        )
    )
    fake_snapshot = await fake.get_snapshot(_SESSION_ID)

    config = DurableHarnessConfig(database_path=":memory:")
    bundle = build_durable_harness(config=config)
    try:
        await bundle.memory_store.apply_patch(
            ScopeClearPatch(
                session_id=_SESSION_ID,
                scope=MemoryScope.SESSION,
                reason="test_clear",
            )
        )
        durable_snapshot = await bundle.memory_store.get_snapshot(
            _SESSION_ID
        )
    finally:
        bundle.close()

    assert fake_snapshot == durable_snapshot


@pytest.mark.asyncio
async def test_fake_non_session_scope_clear_raises_value_error() -> None:
    """非 SESSION scope clear 必须抛 ValueError, 与 durable 实现一致。"""

    fake = FakeInMemoryConversationMemoryStore()
    with pytest.raises(ValueError):
        await fake.apply_patch(
            ScopeClearPatch(
                session_id=_SESSION_ID,
                scope=MemoryScope.GROUP,
                reason="test_clear_invalid",
            )
        )


@pytest.mark.asyncio
async def test_fake_canonical_event_projection_matches_helper() -> None:
    """USER_INPUT_ACCEPTED canonical event 投影到 fake 后, snapshot
    与 ``_project_canonical_events`` helper 直接产物一致。

    Fake 与 durable store 都委托同一份 ``_project_canonical_events``
    helper 做 canonical 事件 -> snapshot 的语义投影; 本测试通过对齐 fake
    与 helper 来锚定 fake 不会在 helper 之外引入额外语义偏离, 间接保证
    fake 与 durable store 在投影语义上一致。
    """

    occurred_at = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    user_text = "fake equivalence question"

    config = DurableHarnessConfig(database_path=":memory:")
    bundle = build_durable_harness(config=config)
    try:
        async with bundle.attempt_supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ) as owner:
            draft = user_input_accepted_draft(
                run_id=_RUN_ID,
                session_id=_SESSION_ID,
                occurred_at=occurred_at,
                turn_id=_RUN_ID,
                content=user_text,
            )
            appender = bundle.attempt_supervisor.scoped_appender(owner)
            event = await appender.append(draft)
    finally:
        bundle.close()

    fake = FakeInMemoryConversationMemoryStore()
    await fake.project_run_events((event,))
    fake_snapshot = await fake.get_snapshot(_SESSION_ID)

    expected = _project_canonical_events(
        snapshot=_empty_snapshot(_SESSION_ID),
        events=(event,),
        recent_turn_limit=fake.recent_turn_limit,
    )
    assert fake_snapshot == expected
