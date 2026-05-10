"""Host P8-S8 Durable Conversation Memory recovery 测试。

覆盖目标：

- ``build_durable_harness`` 默认装配使用 :class:`DurableConversationMemoryStore`。
- terminal run + drain + 重新装配后 memory snapshot 仍可读出。
- checkpoint 已 caught up + memory 仍空时（模拟崩溃后 read model 丢失），
  ``startup_reconcile()`` 通过同事务投影把 snapshot 写回。
- 重复 ``startup_reconcile()`` 不会破坏已恢复 snapshot。
- ``apply_patch``（reset / SESSION clear / claim correction）持久化生效。
- snapshot JSON encode/decode roundtrip 无损。
- 仓库内不再残留 production ``InMemoryConversationMemoryStore``。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dayu.engine import FinalAnswerData, FinishReason
from dayu.host._conversation_memory import (
    AssumptionRegister,
    ClaimCorrectionPatch,
    ClaimStatus,
    ConversationMemorySnapshot,
    ConversationPinnedState,
    EvidenceAnchor,
    MemoryClaim,
    MemoryIngestionPolicy,
    MemoryProducerKind,
    MemoryProvenance,
    MemoryResetPatch,
    MemoryScope,
    MemoryTrustLevel,
    ScopeClearPatch,
    TaskFrame,
    UserPreferenceProfileRef,
)
from dayu.host._conversation_memory_durable import (
    DurableConversationMemoryStore,
    _decode_snapshot_text,
    _encode_snapshot_text,
    open_durable_conversation_memory_store,
)
from dayu.host._durable_harness import (
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host._host_storage_transaction import HostStorage
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    UserInputAcceptedData,
    UserInputScope,
)


@dataclass(slots=True)
class _FakeClock:
    """durable memory 测试使用的可控 UTC clock。"""

    current: datetime

    def now(self) -> datetime:
        """返回当前 fake UTC 时间。

        :returns: timezone-aware UTC datetime。
        :raises Exception: 不主动抛出异常。
        """

        return self.current


def _utc() -> datetime:
    """返回当前 UTC 时间。

    :returns: 时区感知 UTC datetime。
    """

    return datetime.now(tz=timezone.utc)


def _user_input_draft(
    *, run_id: str, session_id: str, content: str
) -> RunEventDraft:
    """构造 USER_INPUT_ACCEPTED 草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param content: 用户输入文本。
    :returns: :class:`RunEventDraft`。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.USER_INPUT_ACCEPTED,
        occurred_at=_utc(),
        data=UserInputAcceptedData(
            turn_id=run_id, content=content, scope=UserInputScope.SESSION
        ),
        source_engine_event_id=None,
    )


def _final_draft(
    *, run_id: str, session_id: str, content: str
) -> RunEventDraft:
    """构造 FINAL_ANSWER 草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param content: assistant final answer 文本。
    :returns: :class:`RunEventDraft`。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
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


def _snapshot_updated_at(storage: HostStorage, *, session_id: str) -> str:
    """读取 durable memory snapshot 的 ``updated_at``。

    :param storage: Host storage。
    :param session_id: 会话 id。
    :returns: ``updated_at`` ISO 文本。
    :raises AssertionError: snapshot row 不存在或字段类型错误时抛出。
    """

    rows = storage.execute_read(
        "SELECT updated_at FROM host_conversation_memory_snapshots "
        "WHERE session_id = ?",
        (session_id,),
    )
    assert rows
    updated_at = rows[0]["updated_at"]
    assert isinstance(updated_at, str)
    return updated_at


@pytest.mark.asyncio
async def test_build_durable_harness_default_uses_durable_memory_store(
    tmp_path: Path,
) -> None:
    """默认装配必须使用 :class:`DurableConversationMemoryStore`。"""

    db_path = tmp_path / "durable_memory.sqlite"
    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=str(db_path))
    )
    try:
        assert isinstance(
            bundle.memory_store, DurableConversationMemoryStore
        )
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_durable_memory_persists_across_reopen(
    tmp_path: Path,
) -> None:
    """terminal run + drain 后重新装配仍可读出 memory snapshot。"""

    db_path = tmp_path / "memory_persist.sqlite"
    config = DurableHarnessConfig(database_path=str(db_path))
    session_id = "session_reopen"
    run_id = "run_reopen_1"
    user_text = "请生成 2025 年财报摘要。"
    final_text = "已生成 2025 年财报摘要。"

    bundle_a = build_durable_harness(config=config)
    try:
        await bundle_a.event_store.append(
            _user_input_draft(
                run_id=run_id, session_id=session_id, content=user_text
            )
        )
        await bundle_a.event_store.append(
            _final_draft(
                run_id=run_id, session_id=session_id, content=final_text
            )
        )
        await bundle_a.coordinator.drain()
        snapshot = await bundle_a.memory_store.get_snapshot(session_id)
        assert any(
            turn.user_text == user_text for turn in snapshot.recent_raw_turns
        )
    finally:
        bundle_a.close()

    bundle_b = build_durable_harness(config=config)
    try:
        snapshot = await bundle_b.memory_store.get_snapshot(session_id)
        assert any(
            turn.user_text == user_text for turn in snapshot.recent_raw_turns
        )
        assert any(
            turn.assistant_final == final_text
            for turn in snapshot.recent_raw_turns
        )
    finally:
        bundle_b.close()


@pytest.mark.asyncio
async def test_startup_reconcile_recovers_snapshot_after_crash_before_projection(
    tmp_path: Path,
) -> None:
    """模拟 EventLog 已落库但崩溃前 projection 未持久化，启动追平必须把 snapshot 写回。"""

    db_path = tmp_path / "memory_crash.sqlite"
    config = DurableHarnessConfig(database_path=str(db_path))
    session_id = "session_crash"
    run_id = "run_crash_1"
    user_text = "请记录关键事实。"
    final_text = "已记录关键事实。"

    bundle = build_durable_harness(config=config)
    try:
        await bundle.event_store.append(
            _user_input_draft(
                run_id=run_id, session_id=session_id, content=user_text
            )
        )
        await bundle.event_store.append(
            _final_draft(
                run_id=run_id, session_id=session_id, content=final_text
            )
        )
        # 故意不调用 drain：模拟进程在 terminal append 之后、coordinator
        # drain 之前崩溃。memory snapshot 此时仍为空。
        snapshot = await bundle.memory_store.get_snapshot(session_id)
        assert snapshot.recent_raw_turns == ()

        # startup_reconcile 必须把 snapshot 推进到含本轮 raw turn 的状态。
        await bundle.startup_reconcile()
        snapshot = await bundle.memory_store.get_snapshot(session_id)
        assert any(
            turn.user_text == user_text for turn in snapshot.recent_raw_turns
        )

        # 重复 reconcile 不破坏已恢复 snapshot。
        await bundle.startup_reconcile()
        snapshot_again = await bundle.memory_store.get_snapshot(session_id)
        assert snapshot_again.recent_raw_turns == snapshot.recent_raw_turns
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_terminal_projection_rereads_run_events_after_pending_checkpoint_restart(
    tmp_path: Path,
) -> None:
    """非终态 checkpoint 后重启，terminal 投影必须从 EventLog 重读完整 run。

    回归 PR #40 1943-F1：``USER_INPUT_ACCEPTED`` 已被 memory observer
    checkpoint 越过但尚未写 snapshot，进程重启后进程内 pending 丢失；
    terminal 到达时 snapshot 仍必须包含 user input 和 final answer。
    """

    db_path = tmp_path / "memory_pending_restart.sqlite"
    config = DurableHarnessConfig(database_path=str(db_path))
    session_id = "session_pending_restart"
    run_id = "run_pending_restart_1"
    user_text = "请保留这条非终态事实。"
    final_text = "已保留非终态事实。"

    bundle_a = build_durable_harness(config=config)
    try:
        await bundle_a.event_store.append(
            _user_input_draft(
                run_id=run_id, session_id=session_id, content=user_text
            )
        )
        await bundle_a.coordinator.drain()
        snapshot = await bundle_a.memory_store.get_snapshot(session_id)
        assert snapshot.recent_raw_turns == ()
    finally:
        bundle_a.close()

    bundle_b = build_durable_harness(config=config)
    try:
        await bundle_b.event_store.append(
            _final_draft(
                run_id=run_id, session_id=session_id, content=final_text
            )
        )
        await bundle_b.startup_reconcile()
        recovered = await bundle_b.memory_store.get_snapshot(session_id)
        assert any(
            turn.user_text == user_text for turn in recovered.recent_raw_turns
        )
        assert any(
            turn.assistant_final == final_text
            for turn in recovered.recent_raw_turns
        )
        checkpoint = bundle_b.coordinator.projection_store.get(
            observer_id="host_memory_projection",
            projection_name="conversation_memory",
            schema_version=1,
        )
        latest_position = bundle_b.event_store.latest_event_position()
        assert checkpoint is not None
        assert latest_position is not None
        assert checkpoint.last_success_position == latest_position

        assert isinstance(
            bundle_b.memory_store, DurableConversationMemoryStore
        )
        repaired = await bundle_b.memory_store.repair_missing_session_snapshots(
            event_store=bundle_b.event_store
        )
        assert repaired == ()
    finally:
        bundle_b.close()


@pytest.mark.asyncio
async def test_durable_memory_snapshot_updated_at_uses_injected_clock(
    tmp_path: Path,
) -> None:
    """snapshot ``updated_at`` 必须使用注入 clock，便于确定性验证。"""

    db_path = tmp_path / "memory_clock.sqlite"
    config = DurableHarnessConfig(database_path=str(db_path))
    session_id = "session_clock"
    run_id = "run_clock_1"
    clock = _FakeClock(
        current=datetime(2026, 5, 10, 8, 30, 0, tzinfo=timezone.utc)
    )

    bundle = build_durable_harness(config=config, clock=clock)
    try:
        await bundle.event_store.append(
            _user_input_draft(
                run_id=run_id, session_id=session_id, content="hello"
            )
        )
        await bundle.event_store.append(
            _final_draft(
                run_id=run_id, session_id=session_id, content="world"
            )
        )
        await bundle.coordinator.drain()
        assert _snapshot_updated_at(
            bundle.storage, session_id=session_id
        ) == clock.current.isoformat()
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_durable_memory_apply_patch_persists_reset_clear_and_claim(
    tmp_path: Path,
) -> None:
    """``apply_patch``（reset / SESSION clear / claim correction）持久化生效。"""

    db_path = tmp_path / "memory_patch.sqlite"
    storage = HostStorage(database_path=str(db_path))
    store = open_durable_conversation_memory_store(storage)
    session_id = "session_patch"
    try:
        # 先写入一些 raw turn 以便 reset 可以观察到差异。
        await store.project_run_events(
            (
                _build_user_event(
                    run_id="r1",
                    session_id=session_id,
                    content="hello",
                    sequence=0,
                ),
            )
        )
        snapshot = await store.get_snapshot(session_id)
        assert snapshot.recent_raw_turns != ()

        # MemoryResetPatch -> 清空 snapshot。
        await store.apply_patch(
            MemoryResetPatch(
                session_id=session_id,
                scope=MemoryScope.SESSION,
                reason="test_reset",
            )
        )
        snapshot = await store.get_snapshot(session_id)
        assert snapshot.recent_raw_turns == ()

        # ScopeClearPatch(SESSION) -> 同样清空 snapshot。
        await store.project_run_events(
            (
                _build_user_event(
                    run_id="r2",
                    session_id=session_id,
                    content="again",
                    sequence=1,
                ),
            )
        )
        await store.apply_patch(
            ScopeClearPatch(
                session_id=session_id,
                scope=MemoryScope.SESSION,
                reason="test_clear",
            )
        )
        snapshot = await store.get_snapshot(session_id)
        assert snapshot.recent_raw_turns == ()

        # ScopeClearPatch(非 SESSION) -> ValueError。
        with pytest.raises(ValueError):
            await store.apply_patch(
                ScopeClearPatch(
                    session_id=session_id,
                    scope=MemoryScope.DIRECT_USER,
                    reason="test_bad_scope",
                )
            )

        # ClaimCorrectionPatch -> verified_claims 追加。
        claim = MemoryClaim(
            claim_id="claim-1",
            status=ClaimStatus.VERIFIED,
            text="2025 年收入同比增长 12%。",
            source_run_id="r1",
            source_event_cursor=RunEventCursor(sequence=0),
            evidence_anchor_id=None,
            scope=MemoryScope.SESSION,
            created_at=_utc(),
            supersedes=(),
            provenance=MemoryProvenance(
                source_run_id="r1",
                source_event_cursor=RunEventCursor(sequence=0),
                producer_kind=MemoryProducerKind.USER_CORRECTION,
                ingestion_policy=MemoryIngestionPolicy.USER_CONFIRMED_CORRECTION,
                scope=MemoryScope.SESSION,
                trust_level=MemoryTrustLevel.USER_PROVIDED,
            ),
        )
        await store.apply_patch(
            ClaimCorrectionPatch(
                session_id=session_id,
                corrected_claim=claim,
                reason="test_correction",
            )
        )
        snapshot = await store.get_snapshot(session_id)
        assert snapshot.verified_claims == (claim,)
    finally:
        storage.close()


def _build_user_event(
    *, run_id: str, session_id: str, content: str, sequence: int
) -> RunEvent:
    """构造已落库 USER_INPUT_ACCEPTED RunEvent，绕过 store append。"""

    return RunEvent(
        run_id=run_id,
        session_id=session_id,
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


def _build_full_snapshot() -> ConversationMemorySnapshot:
    """构造一个包含全部字段的 snapshot 用于 roundtrip。"""

    cursor = RunEventCursor(sequence=42)
    provenance = MemoryProvenance(
        source_run_id="run-roundtrip",
        source_event_cursor=cursor,
        producer_kind=MemoryProducerKind.HOST_USER_INPUT,
        ingestion_policy=MemoryIngestionPolicy.PRIMARY_SESSION_CANONICAL,
        scope=MemoryScope.SESSION,
        trust_level=MemoryTrustLevel.USER_PROVIDED,
    )
    claim = MemoryClaim(
        claim_id="claim-roundtrip",
        status=ClaimStatus.VERIFIED,
        text="财务事实摘要。",
        source_run_id="run-roundtrip",
        source_event_cursor=cursor,
        evidence_anchor_id="anchor-1",
        scope=MemoryScope.SESSION,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        supersedes=("claim-old",),
        provenance=provenance,
    )
    anchor = EvidenceAnchor(
        anchor_id="anchor-1",
        origin_event_cursor=cursor,
        tool_call_id="tool-call-1",
        source_ref="report-2025",
        chunk_ref="chunk-7",
        fingerprint="abc123",
        summary="Net revenue 2025 摘要。",
        provenance=provenance,
    )
    return ConversationMemorySnapshot(
        session_id="session-roundtrip",
        pinned_state=ConversationPinnedState(
            current_goal="生成摘要",
            confirmed_subjects=("ACME",),
            user_constraints=("中文回答",),
            open_questions=("毛利率？",),
        ),
        task_frame=TaskFrame(
            topic_ref="topic-1",
            entity_refs=("ACME",),
            period_refs=("FY2025",),
            basis_refs=("GAAP",),
            unit_ref="USD",
        ),
        verified_claims=(claim,),
        assumptions=AssumptionRegister(claims=(claim,)),
        evidence_anchors=(anchor,),
        recent_raw_turns=(),
        older_raw_turns=(),
        tool_facts=(),
        user_preference_ref=UserPreferenceProfileRef(
            profile_id="profile-1",
            scope=MemoryScope.USER,
        ),
    )


def test_snapshot_json_encode_decode_roundtrip() -> None:
    """snapshot JSON encode/decode 必须无损 roundtrip。"""

    snapshot = _build_full_snapshot()
    text = _encode_snapshot_text(snapshot=snapshot)
    decoded = _decode_snapshot_text(payload_text=text)
    assert decoded == snapshot


def test_decode_snapshot_rejects_missing_schema_version() -> None:
    """payload 缺少 ``schema_version`` 时必须抛 ValueError。

    Snapshot 是 durable read model, 跨版本 / 缺字段时静默放过会污染
    durable repair 路径。本测试断言 fail-fast。
    """

    bad_payload = json.dumps({"session_id": "s1"})
    with pytest.raises(ValueError, match="schema_version"):
        _decode_snapshot_text(payload_text=bad_payload)


def test_decode_snapshot_rejects_unknown_schema_version() -> None:
    """payload ``schema_version`` 与当前不匹配时必须抛 ValueError。"""

    bad_payload = json.dumps(
        {"schema_version": 999, "session_id": "s1"}
    )
    with pytest.raises(ValueError, match="schema_version"):
        _decode_snapshot_text(payload_text=bad_payload)


def _iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    """遍历 Python 源文件。"""

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            yield path


def test_production_inmemory_conversation_store_no_longer_exists() -> None:
    """生产 ``InMemoryConversationMemoryStore`` 必须已下线。"""

    repo_root = Path(__file__).resolve().parents[2]
    production_dirs = (repo_root / "dayu",)
    forbidden_token = "InMemoryConversationMemoryStore"
    # 仅在 Python 代码用法（class / import / 调用）中视为残留；docstring /
    # 注释里以反引号包裹的历史说明允许保留。
    code_use_prefixes = ("class ", "from ", "import ")
    violations: list[str] = []
    for path in _iter_python_files(production_dirs):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if forbidden_token not in line:
                continue
            stripped = line.strip()
            # docstring / 注释内引用：以反引号包裹或位于注释行。
            if f"``{forbidden_token}``" in line:
                continue
            if stripped.startswith("#"):
                continue
            if any(stripped.startswith(prefix) for prefix in code_use_prefixes):
                violations.append(f"{path}:{line_no}:{stripped}")
                continue
            # 出现在赋值 / 调用 / 类型注解上下文。
            if "(" in line or "=" in line or ":" in line.split(forbidden_token)[1][:5]:
                # 排除 docstring 中带 ``: 的描述行（已在反引号过滤）。
                if forbidden_token + "(" in line or "= " + forbidden_token in line:
                    violations.append(f"{path}:{line_no}:{stripped}")
    assert not violations, "production InMemory 残留:\n" + "\n".join(violations)


def test_replace_keeps_dataclass_immutability() -> None:
    """sanity：snapshot dataclass 应支持 ``replace`` 用于事务内更新。"""

    snapshot = _build_full_snapshot()
    updated = replace(snapshot, session_id="session-replaced")
    assert updated.session_id == "session-replaced"
    assert snapshot.session_id == "session-roundtrip"


@pytest.mark.asyncio
async def test_startup_reconcile_repairs_snapshot_when_checkpoint_caught_up_and_row_missing(
    tmp_path: Path,
) -> None:
    """checkpoint 已 CAUGHT_UP + snapshot row 被外部删除 → repair 必须重建。

    复现 P8-S8 gap：``ProjectionCoordinator`` 的 checkpoint 已推进至最新
    EventLog position 后，普通 drain 不会再驱动 observer 重投。本测试构造
    “checkpoint CAUGHT_UP，``host_conversation_memory_snapshots`` 行被
    外部删除”的 read model 丢失场景，调用 :meth:`startup_reconcile` 必须
    通过 durable memory repair 路径从 EventLog 重建缺失 snapshot。
    """

    db_path = tmp_path / "memory_repair.sqlite"
    config = DurableHarnessConfig(database_path=str(db_path))
    session_id = "session_repair"
    run_id = "run_repair_1"
    user_text = "请记录关键事实。"
    final_text = "已记录关键事实。"

    bundle_a = build_durable_harness(config=config)
    try:
        await bundle_a.event_store.append(
            _user_input_draft(
                run_id=run_id, session_id=session_id, content=user_text
            )
        )
        await bundle_a.event_store.append(
            _final_draft(
                run_id=run_id, session_id=session_id, content=final_text
            )
        )
        # 推进到 CAUGHT_UP，snapshot 此时已写入。
        await bundle_a.coordinator.drain()
        snapshot = await bundle_a.memory_store.get_snapshot(session_id)
        assert any(
            turn.user_text == user_text for turn in snapshot.recent_raw_turns
        )

        # 模拟 read model 丢失：直接删除 snapshot 行，但保留 EventLog 与
        # observer checkpoint。
        async with bundle_a.storage.transaction() as tx:
            tx.execute(
                "DELETE FROM host_conversation_memory_snapshots "
                "WHERE session_id = ?",
                (session_id,),
            )
        empty = await bundle_a.memory_store.get_snapshot(session_id)
        assert empty.recent_raw_turns == ()
    finally:
        bundle_a.close()

    # 重新装配并触发 startup_reconcile：checkpoint 已 CAUGHT_UP 不会再
    # drain，但 repair 路径必须从 EventLog 重建缺失 snapshot。
    bundle_b = build_durable_harness(config=config)
    try:
        await bundle_b.startup_reconcile()
        recovered = await bundle_b.memory_store.get_snapshot(session_id)
        assert any(
            turn.user_text == user_text for turn in recovered.recent_raw_turns
        )
        assert any(
            turn.assistant_final == final_text
            for turn in recovered.recent_raw_turns
        )

        # 重复 reconcile 不破坏已恢复 snapshot。
        await bundle_b.startup_reconcile()
        again = await bundle_b.memory_store.get_snapshot(session_id)
        assert again.recent_raw_turns == recovered.recent_raw_turns
    finally:
        bundle_b.close()


@pytest.mark.asyncio
async def test_startup_reconcile_does_not_overwrite_intentional_empty_snapshot(
    tmp_path: Path,
) -> None:
    """``MemoryResetPatch`` / ``ScopeClearPatch(SESSION)`` 写入的空 snapshot
    必须区别于“缺失 row”，repair 路径不得误恢复旧内容。"""

    db_path = tmp_path / "memory_intentional_empty.sqlite"
    config = DurableHarnessConfig(database_path=str(db_path))
    session_id = "session_intentional_empty"
    run_id = "run_intentional_1"
    user_text = "需要被 reset 清掉的旧事实。"
    final_text = "旧 final answer。"

    bundle = build_durable_harness(config=config)
    try:
        await bundle.event_store.append(
            _user_input_draft(
                run_id=run_id, session_id=session_id, content=user_text
            )
        )
        await bundle.event_store.append(
            _final_draft(
                run_id=run_id, session_id=session_id, content=final_text
            )
        )
        await bundle.coordinator.drain()

        # 走 MemoryResetPatch：snapshot 写入空内容，但 row 仍存在。
        await bundle.memory_store.apply_patch(
            MemoryResetPatch(
                session_id=session_id,
                scope=MemoryScope.SESSION,
                reason="user_requested_reset",
            )
        )
        empty = await bundle.memory_store.get_snapshot(session_id)
        assert empty.recent_raw_turns == ()

        # startup_reconcile 不得把 EventLog 的旧事实重新投回。
        await bundle.startup_reconcile()
        still_empty = await bundle.memory_store.get_snapshot(session_id)
        assert still_empty.recent_raw_turns == ()

        # ScopeClearPatch(SESSION) 同样不应被 repair 误恢复。
        await bundle.event_store.append(
            _user_input_draft(
                run_id="run_intentional_2",
                session_id=session_id,
                content="再次写入然后被 clear。",
            )
        )
        await bundle.event_store.append(
            _final_draft(
                run_id="run_intentional_2",
                session_id=session_id,
                content="再次的 final。",
            )
        )
        await bundle.coordinator.drain()
        await bundle.memory_store.apply_patch(
            ScopeClearPatch(
                session_id=session_id,
                scope=MemoryScope.SESSION,
                reason="user_requested_clear",
            )
        )
        await bundle.startup_reconcile()
        still_empty_2 = await bundle.memory_store.get_snapshot(session_id)
        assert still_empty_2.recent_raw_turns == ()
    finally:
        bundle.close()
