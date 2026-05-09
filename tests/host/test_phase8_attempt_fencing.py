"""Host P8-S4 ``AttemptSupervisor.append_terminal_and_close`` 原子语义测试。

覆盖 P8-S4 关键不变量:

- 正常 owner: terminal RunEvent append + ``host_attempts`` 终态 close 在
  同一 ``BEGIN IMMEDIATE`` 事务内原子完成; ``host_attempts.terminal_event_position``
  非空且与刚 append 的 terminal RunEvent 全局 position 完全一致;
  ``host_runs`` 终态推进与 RunResult snapshot 与 EventLog 同事务写入。
- owner 已被替换 / fencing token 不一致 / lease 过期 / attempt 已不再
  RUNNING 时, ``append_terminal_and_close`` 必须抛
  :class:`AttemptFencingError`, 整事务回滚: EventLog 不残留 stale terminal
  RunEvent (该 run 的 ``terminal_sequence`` 仍为 ``None``),
  ``host_attempts.state`` 保持原值 (RUNNING 或被外部修改后的状态), 不被
  旧 owner 覆盖未来状态。

测试一律使用 fake clock, 不依赖真实 ``time.sleep``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from dayu.engine import FinalAnswerData, FinishReason
from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptFencingReason,
    AttemptLeaseConfig,
    AttemptOwnerToken,
)
from dayu.host._attempt_supervisor import AttemptSupervisor
from dayu.host._durable_event_store import (
    DurableRunEventStore,
    open_durable_event_store,
)
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import (
    AttemptState,
    ExtendedRunState,
)
from dayu.host._run_state_store import (
    AttemptLeaseStore,
    AttemptStateStore,
    RunStateStore,
)
from dayu.host.contracts import (
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunSucceededResult,
)


@dataclass(slots=True)
class _FakeClock:
    """fake UTC clock; 测试用 ``advance`` 显式推进时间。"""

    current: datetime = field(
        default_factory=lambda: datetime(
            2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc
        )
    )

    def now(self) -> datetime:
        """返回当前 fake UTC 时间。

        :returns: timezone-aware UTC datetime。
        :raises Exception: 不主动抛出异常。
        """

        return self.current

    def advance(self, delta: timedelta) -> None:
        """按 ``delta`` 前推 fake 时间。

        :param delta: 待推进的 timedelta。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.current = self.current + delta


def _open_storage() -> HostStorage:
    """构造一个内存 SQLite storage 并完成 P6 schema 初始化。

    :returns: 已 open 的 :class:`HostStorage`。
    :raises sqlite3.DatabaseError: schema bootstrap 失败时抛出。
    """

    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    return storage


async def _seed_run(storage: HostStorage, *, run_id: str = "r1") -> None:
    """在 ``host_runs`` 中预置一行 RUNNING run。

    :param storage: 共享 storage。
    :param run_id: Run id, 默认 ``r1``。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: 写入失败时抛出。
    """

    timestamp = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    async with storage.transaction() as tx:
        tx.execute(
            "INSERT INTO host_runs (run_id, session_id, state, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, "s", ExtendedRunState.RUNNING.value, timestamp, timestamp),
        )


def _build_supervisor(
    *,
    storage: HostStorage,
    clock: _FakeClock,
) -> AttemptSupervisor:
    """构造测试用 supervisor + lease_store + event_store, 共享同一 storage。

    :param storage: 共享 storage。
    :param clock: fake clock。
    :returns: 已装配完成的 :class:`AttemptSupervisor`。
    :raises Exception: 不主动抛出异常。
    """

    config = AttemptLeaseConfig(
        ttl=timedelta(seconds=30),
        renew_interval=timedelta(seconds=10),
        owner_id_prefix="host-test",
    )
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    event_store = DurableRunEventStore(storage=storage)
    return AttemptSupervisor(
        storage=storage,
        lease_store=lease_store,
        lease_config=config,
        clock=clock,
        event_store=event_store,
    )


def _final_answer_draft(
    *, run_id: str, engine_event_id: str = "engine_final"
) -> RunEventDraft:
    """构造一个 terminal ``FINAL_ANSWER`` RunEvent 草稿。

    :param run_id: Run id。
    :param engine_event_id: 事件 id, 默认 ``engine_final``; 多次调用必须
        显式区分以避免 unique 冲突。
    :returns: :class:`RunEventDraft`。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=datetime.now(tz=timezone.utc),
        data=FinalAnswerData(
            content="ok",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        source_engine_event_id=engine_event_id,
    )


@pytest.mark.asyncio
async def test_append_terminal_and_close_writes_position_atomically() -> None:
    """正常 owner: terminal append + close 同事务原子写入。

    断言:

    - ``AttemptTerminalLink`` 的 ``terminal_state == SUCCEEDED``;
    - ``host_attempts.terminal_event_position`` 与 EventLog 终态 RunEvent
      全局 position 完全一致;
    - EventLog 终态 RunEvent 的 cursor 与 link 一致;
    - ``host_runs`` 终态推进 (``ExtendedRunState.SUCCEEDED``) 与 RunResult
      snapshot 由 EventLog 同事务写入;
    - attempt state == SUCCEEDED, finished_at 非空, failure_summary 为
      ``None``。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        attempt_state_store = AttemptStateStore(storage=storage)
        run_state_store = RunStateStore(storage=storage)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            link = await supervisor.append_terminal_and_close(
                owner_context=owner_context,
                draft=_final_answer_draft(run_id="r1"),
                failure_summary=None,
            )
        assert link.terminal_state is AttemptState.SUCCEEDED
        assert link.run_id == "r1"
        assert link.attempt_id == owner_context.attempt_id
        # attempt 终态写入 + terminal_event_position 与 link.event_position
        # 一致
        attempt = attempt_state_store.get(owner_context.attempt_id)
        assert attempt is not None
        assert attempt.state is AttemptState.SUCCEEDED
        assert attempt.finished_at is not None
        assert attempt.failure_summary is None
        assert attempt.terminal_event_position is not None
        assert (
            attempt.terminal_event_position.value == link.event_position.value
        )
        # EventLog terminal RunEvent 与 link 完全对齐
        events = await supervisor.event_store.list_events(
            run_id="r1", after=None
        )
        assert len(events) == 1
        terminal_event = events[0]
        assert terminal_event.type is RunEventType.FINAL_ANSWER
        assert terminal_event.cursor.sequence == link.event_cursor.sequence
        # global position: fetch_events_by_position 应返回与 link 一致的
        # global position
        positions = supervisor.event_store.fetch_events_by_position(
            after=None, limit=10
        )
        assert len(positions) == 1
        assert positions[0][0].value == link.event_position.value
        # Run state snapshot 已同事务写入 SUCCEEDED + RunResult
        run_record = run_state_store.get("r1")
        assert run_record is not None
        assert run_record.state is ExtendedRunState.SUCCEEDED
        assert run_record.terminal_event_cursor is not None
        assert (
            run_record.terminal_event_cursor.sequence
            == link.event_cursor.sequence
        )
        assert isinstance(run_record.result, RunSucceededResult)
        assert run_record.result.content == "ok"
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_append_terminal_and_close_rolls_back_when_owner_fenced() -> None:
    """owner 失效时 append_terminal_and_close 必须整事务回滚。

    场景: lease_context 内 owner 仍 active, 但测试外部已经把
    ``host_attempts.fencing_token`` 改成不同的 token (模拟 recovery 替换
    了当前 owner)。``append_terminal_and_close`` 在事务内 ``verify_owner``
    必然 CAS miss, 抛 :class:`AttemptFencingError`。事务整体回滚:

    - EventLog 不残留 terminal RunEvent (该 run 的 events 列表为空,
      ``host_runs.terminal_sequence`` 仍为 NULL);
    - ``host_attempts.state`` 不被覆盖 (仍是被外部修改后的值);
    - 抛出的错误带 typed reason, 不暴露 owner 明文 token。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        attempt_state_store = AttemptStateStore(storage=storage)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            # 模拟 recovery 替换: 把 owner_token_hash + fencing_token 改成
            # 不同值。owner_context 视角下 store 已是 stale owner。
            other_owner_token = AttemptOwnerToken.new()
            async with storage.transaction() as tx:
                tx.execute(
                    "UPDATE host_attempts SET owner_token_hash = ?, "
                    "fencing_token = ? WHERE attempt_id = ?",
                    (
                        other_owner_token.digest(),
                        owner_context.fencing_token.value + 1000,
                        owner_context.attempt_id,
                    ),
                )
            with pytest.raises(AttemptFencingError) as excinfo:
                await supervisor.append_terminal_and_close(
                    owner_context=owner_context,
                    draft=_final_answer_draft(run_id="r1"),
                    failure_summary=None,
                )
            assert excinfo.value.attempt_id == owner_context.attempt_id
            assert excinfo.value.reason in (
                AttemptFencingReason.OWNER_MISMATCH,
                AttemptFencingReason.FENCING_TOKEN_MISMATCH,
            )
            # EventLog 不残留 terminal RunEvent
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert events == ()
            # host_runs 仍未推进到终态: terminal_event_position 为 None
            run_terminal = supervisor.event_store.latest_event_position()
            assert run_terminal is None
            # owner CAS 没有覆盖 attempt 行: 行仍持有外部写入的新 token
            attempt = attempt_state_store.get(owner_context.attempt_id)
            assert attempt is not None
            assert attempt.state is AttemptState.RUNNING
            assert attempt.fencing_token is not None
            assert (
                attempt.fencing_token.value
                == owner_context.fencing_token.value + 1000
            )
            assert attempt.terminal_event_position is None
            # 错误文本不含 owner secret 明文
            assert owner_context.owner_token.value not in str(excinfo.value)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_append_terminal_and_close_rejects_lease_expired() -> None:
    """lease 已过期但 fake supervisor 仍持有 session 时, 终态 close 必回滚。

    使用 fake clock 把当前时间推到 lease_expires_at 之后, 即便 owner_token
    与 fencing_token 仍然匹配, ``close_terminal`` CAS 也因 ``lease_expires_at
    > now`` 失败抛 :class:`AttemptFencingError`, 事务回滚, EventLog 不残留
    terminal RunEvent。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        # 直接构造 owner_context: 旁路 lease_context, 避免 supervisor 的
        # session-level race (lease 过期时 verify_owner 也会失败)。
        owner_token = AttemptOwnerToken.new()
        attempt_id = "attempt-r1-0-deadbeef"
        lease_expires_at = clock.now() + timedelta(seconds=30)
        async with storage.transaction() as tx:
            result = supervisor.lease_store.acquire_new_attempt(
                tx=tx,
                attempt_id=attempt_id,
                run_id="r1",
                attempt_index=0,
                recovered_from_attempt_id=None,
                owner_id="host-test:1:abcd",
                owner_token=owner_token,
                lease_expires_at=lease_expires_at,
            )
        owner_context = result.owner_context
        assert owner_context is not None
        # 推进 fake clock 至 lease 过期之后
        clock.advance(timedelta(seconds=60))
        with pytest.raises(AttemptFencingError) as excinfo:
            await supervisor.append_terminal_and_close(
                owner_context=owner_context,
                draft=_final_answer_draft(run_id="r1"),
                failure_summary=None,
            )
        assert excinfo.value.reason is AttemptFencingReason.LEASE_EXPIRED
        events = await supervisor.event_store.list_events(
            run_id="r1", after=None
        )
        assert events == ()
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_append_terminal_and_close_validates_run_id_and_type() -> None:
    """draft 与 owner_context 不一致 / 非 terminal type 时抛 ValueError 不写入。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            mismatched = RunEventDraft(
                run_id="other_run",
                session_id="s",
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.ENGINE,
                type=RunEventType.FINAL_ANSWER,
                occurred_at=datetime.now(tz=timezone.utc),
                data=FinalAnswerData(
                    content="x",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                source_engine_event_id="engine_final_other",
            )
            with pytest.raises(ValueError):
                await supervisor.append_terminal_and_close(
                    owner_context=owner_context,
                    draft=mismatched,
                    failure_summary=None,
                )
            non_terminal = RunEventDraft(
                run_id="r1",
                session_id="s",
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT,
                occurred_at=datetime.now(tz=timezone.utc),
                data=None,  # type: ignore[arg-type]
                source_engine_event_id=None,
            )
            with pytest.raises(ValueError):
                await supervisor.append_terminal_and_close(
                    owner_context=owner_context,
                    draft=non_terminal,
                    failure_summary=None,
                )
            # 任一异常路径都不应留下 RunEvent
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert events == ()
            events_other = await supervisor.event_store.list_events(
                run_id="other_run", after=None
            )
            assert events_other == ()
    finally:
        storage.close()
