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
from dayu.engine.contracts.engine_events import IterationStartedData
from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptFencingReason,
    AttemptLeaseBusyReason,
    AttemptLeaseDecision,
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
    GlobalEventPosition,
)
from dayu.host._run_state_store import (
    AttemptLeaseStore,
    AttemptStateStore,
    RunStateStore,
)
from dayu.host.contracts import (
    HostRunFailedData,
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


def _host_failed_draft(*, run_id: str) -> RunEventDraft:
    """构造 Host ``RUN_FAILED`` terminal 草稿。

    :param run_id: Run id。
    :returns: Host 失败 terminal RunEvent 草稿。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.RUN_FAILED,
        occurred_at=datetime.now(tz=timezone.utc),
        data=HostRunFailedData(
            error_code="attempt_lease_lost",
            message="attempt lease lost",
            recoverable=False,
            exception_type="RuntimeError",
        ),
        source_engine_event_id=None,
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
        attempt_state_store = AttemptStateStore(storage=storage, clock=clock)
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
async def test_terminal_override_does_not_overwrite_existing_terminal_truth() -> None:
    """已有 terminal truth 时, LOST override 不得覆盖 attempt / EventLog。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        attempt_state_store = AttemptStateStore(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            first_link = await supervisor.append_terminal_and_close(
                owner_context=owner_context,
                draft=_final_answer_draft(run_id="r1"),
                failure_summary=None,
            )
            with pytest.raises(AttemptFencingError) as excinfo:
                await supervisor.append_terminal_and_close(
                    owner_context=owner_context,
                    draft=_host_failed_draft(run_id="r1"),
                    failure_summary="attempt_lease_lost:fenced",
                    terminal_state_override=AttemptState.LOST,
                )

        assert excinfo.value.reason is AttemptFencingReason.ATTEMPT_TERMINAL
        attempt = attempt_state_store.get(owner_context.attempt_id)
        assert attempt is not None
        assert attempt.state is AttemptState.SUCCEEDED
        assert attempt.terminal_event_position is not None
        assert (
            attempt.terminal_event_position.value
            == first_link.event_position.value
        )
        events = await supervisor.event_store.list_events(
            run_id="r1", after=None
        )
        assert len(events) == 1
        assert events[0].type is RunEventType.FINAL_ANSWER
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
        attempt_state_store = AttemptStateStore(storage=storage, clock=clock)
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
            with pytest.raises(AttemptFencingError) as exc_info:
                await supervisor.append_terminal_and_close(
                    owner_context=owner_context,
                    draft=mismatched,
                    failure_summary=None,
                )
            assert exc_info.value.reason == AttemptFencingReason.RUN_ID_MISMATCH
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


def _engine_event_draft(*, run_id: str, engine_event_id: str) -> RunEventDraft:
    """构造一个非 terminal Engine 来源 RunEvent 草稿用于 scoped append 测试。

    :param run_id: Run id。
    :param engine_event_id: 事件 id, 多次调用必须显式区分以避免 unique 冲突。
    :returns: :class:`RunEventDraft`。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.ITERATION_STARTED,
        occurred_at=datetime.now(tz=timezone.utc),
        data=IterationStartedData(
            iteration_id="iter-0",
            iteration_index=0,
            message_count=1,
        ),
        source_engine_event_id=engine_event_id,
    )


@pytest.mark.asyncio
async def test_scoped_appender_blocks_terminal_drafts() -> None:
    """``AttemptScopedRunEventAppender.append`` 不接受 terminal draft。

    terminal RunEvent 必须走 :meth:`append_terminal_and_close`, 否则 attempt
    close 与 terminal append 失去原子性。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            appender = supervisor.scoped_appender(owner_context)
            with pytest.raises(ValueError):
                await appender.append(_final_answer_draft(run_id="r1"))
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert events == ()
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_scoped_appender_rejects_run_id_mismatch() -> None:
    """draft.run_id 与 owner_context.run_id 不一致时抛 RUN_ID_MISMATCH。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            appender = supervisor.scoped_appender(owner_context)
            mismatch = _engine_event_draft(
                run_id="other_run", engine_event_id="engine_other"
            )
            with pytest.raises(AttemptFencingError) as excinfo:
                await appender.append(mismatch)
            assert excinfo.value.reason == AttemptFencingReason.RUN_ID_MISMATCH
            assert excinfo.value.attempt_id == owner_context.attempt_id
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert events == ()
            other_events = await supervisor.event_store.list_events(
                run_id="other_run", after=None
            )
            assert other_events == ()
            # 错误文本不含 owner secret 明文
            assert owner_context.owner_token.value not in str(excinfo.value)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_scoped_appender_rejects_when_owner_fenced() -> None:
    """owner 被外部替换后, 非 terminal append 也必须 CAS miss + 整事务回滚。

    这是 Engine event / context fact / ToolRuntime fact 共享的 fencing 路径
    总入口 (``AttemptScopedRunEventAppender.append``)。任何 stale owner 试图
    写入都应抛 :class:`AttemptFencingError`, EventLog 不残留 fact。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            appender = supervisor.scoped_appender(owner_context)
            # 外部把 fencing_token 改掉: stale owner 视角下 CAS 必然 miss
            other_owner_token = AttemptOwnerToken.new()
            async with storage.transaction() as tx:
                tx.execute(
                    "UPDATE host_attempts SET owner_token_hash = ?, "
                    "fencing_token = ? WHERE attempt_id = ?",
                    (
                        other_owner_token.digest(),
                        owner_context.fencing_token.value + 5000,
                        owner_context.attempt_id,
                    ),
                )
            with pytest.raises(AttemptFencingError) as excinfo:
                await appender.append(
                    _engine_event_draft(
                        run_id="r1", engine_event_id="engine_preview_late"
                    )
                )
            assert excinfo.value.reason in (
                AttemptFencingReason.OWNER_MISMATCH,
                AttemptFencingReason.FENCING_TOKEN_MISMATCH,
            )
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert events == ()
            # 错误文本不含 owner secret 明文
            assert owner_context.owner_token.value not in str(excinfo.value)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_verify_owner_with_null_owner_hash_returns_typed_fence() -> None:
    """RUNNING 行 owner hash 为 NULL 时返回 typed OWNER_MISMATCH。

    回归 P8 F8：``_diagnose_fence`` 不得把 ``None`` 传给
    ``hmac.compare_digest`` 导致 ``TypeError``，而应按 owner 不匹配收口。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            async with storage.transaction() as tx:
                tx.execute(
                    "UPDATE host_attempts SET owner_token_hash = NULL "
                    "WHERE attempt_id = ?",
                    (owner_context.attempt_id,),
                )
            with pytest.raises(AttemptFencingError) as excinfo:
                async with storage.transaction() as tx:
                    supervisor.lease_store.verify_owner(
                        tx=tx,
                        owner_context=owner_context,
                    )
            assert excinfo.value.reason is AttemptFencingReason.OWNER_MISMATCH
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_busy_acquire_result_includes_current_fencing_token() -> None:
    """attempt_index 冲突的 BUSY 结果必须携带当前 fencing token。

    回归 P8 F22：BUSY 诊断缺少 ``current_fencing_token`` 会丢失并发冲突
    的关键诊断字段。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        lease_store = AttemptLeaseStore(storage=storage, clock=clock)
        owner_token = AttemptOwnerToken.new()
        async with storage.transaction() as tx:
            first = lease_store.acquire_new_attempt(
                tx=tx,
                attempt_id="attempt-busy-1",
                run_id="r1",
                attempt_index=0,
                recovered_from_attempt_id=None,
                owner_id="owner-1",
                owner_token=owner_token,
                lease_expires_at=clock.now() + timedelta(seconds=30),
            )
            assert first.owner_context is not None
            busy = lease_store.acquire_new_attempt(
                tx=tx,
                attempt_id="attempt-busy-2",
                run_id="r1",
                attempt_index=0,
                recovered_from_attempt_id=None,
                owner_id="owner-2",
                owner_token=AttemptOwnerToken.new(),
                lease_expires_at=clock.now() + timedelta(seconds=30),
            )
        assert busy.decision is AttemptLeaseDecision.BUSY
        assert busy.reason is None
        assert busy.busy_reason is AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT
        assert busy.current_fencing_token == first.owner_context.fencing_token
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_scoped_appender_appends_when_owner_active() -> None:
    """owner 仍 active 时, scoped append 在同事务完成 verify_owner + EventLog 写入。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            appender = supervisor.scoped_appender(owner_context)
            event = await appender.append(
                _engine_event_draft(
                    run_id="r1", engine_event_id="engine_preview_ok"
                )
            )
            assert event.type == RunEventType.ITERATION_STARTED
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert len(events) == 1
            assert events[0].source_engine_event_id == "engine_preview_ok"
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_append_in_transaction_appends_within_outer_transaction() -> None:
    """``append_in_transaction``: 外层事务内 owner 仍 active 时正常 append。

    生产路径 ``LocalRunHarness._resolve_attempt_appender`` 在 harness 持
    有外层事务时调用此方法, 测试必须证明 verify_owner +
    append_with_position 在同事务内串联成功。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            appender = supervisor.scoped_appender(owner_context)
            async with storage.transaction() as tx:
                event = appender.append_in_transaction(
                    tx=tx,
                    draft=_engine_event_draft(
                        run_id="r1", engine_event_id="engine_in_tx_ok"
                    ),
                )
            assert event.type == RunEventType.ITERATION_STARTED
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert len(events) == 1
            assert events[0].source_engine_event_id == "engine_in_tx_ok"
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_append_in_transaction_rolls_back_when_owner_fenced() -> None:
    """``append_in_transaction``: owner 被外部替换后 verify_owner 必 CAS miss。

    在外层事务前先把 owner_token_hash + fencing_token 改成不同值, 进入
    外层事务后 ``append_in_transaction`` 调用 ``verify_owner`` 应抛
    :class:`AttemptFencingError`, 整事务回滚: EventLog 不残留 RunEvent。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            appender = supervisor.scoped_appender(owner_context)
            other_owner_token = AttemptOwnerToken.new()
            async with storage.transaction() as tx:
                tx.execute(
                    "UPDATE host_attempts SET owner_token_hash = ?, "
                    "fencing_token = ? WHERE attempt_id = ?",
                    (
                        other_owner_token.digest(),
                        owner_context.fencing_token.value + 7000,
                        owner_context.attempt_id,
                    ),
                )
            with pytest.raises(AttemptFencingError) as excinfo:
                async with storage.transaction() as tx:
                    appender.append_in_transaction(
                        tx=tx,
                        draft=_engine_event_draft(
                            run_id="r1",
                            engine_event_id="engine_in_tx_fenced",
                        ),
                    )
            assert excinfo.value.reason in (
                AttemptFencingReason.OWNER_MISMATCH,
                AttemptFencingReason.FENCING_TOKEN_MISMATCH,
            )
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert events == ()
            assert owner_context.owner_token.value not in str(excinfo.value)
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_append_in_transaction_rejects_run_id_mismatch() -> None:
    """``append_in_transaction``: draft.run_id 与 owner 不一致抛 RUN_ID_MISMATCH。

    与 ``append`` 路径保持一致的 typed reason, 不允许跨 run 借助同事务旁
    路 fencing。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            appender = supervisor.scoped_appender(owner_context)
            mismatch = _engine_event_draft(
                run_id="other_run",
                engine_event_id="engine_in_tx_other_run",
            )
            with pytest.raises(AttemptFencingError) as excinfo:
                async with storage.transaction() as tx:
                    appender.append_in_transaction(tx=tx, draft=mismatch)
            assert excinfo.value.reason == AttemptFencingReason.RUN_ID_MISMATCH
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert events == ()
            other_events = await supervisor.event_store.list_events(
                run_id="other_run", after=None
            )
            assert other_events == ()
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_append_in_transaction_rejects_terminal_drafts() -> None:
    """``append_in_transaction``: terminal RunEventType 必抛 ValueError。

    terminal RunEvent 必须走 ``append_terminal_and_close``, 否则 attempt
    close 与 terminal append 失去原子性。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            appender = supervisor.scoped_appender(owner_context)
            with pytest.raises(ValueError):
                async with storage.transaction() as tx:
                    appender.append_in_transaction(
                        tx=tx,
                        draft=_final_answer_draft(run_id="r1"),
                    )
            events = await supervisor.event_store.list_events(
                run_id="r1", after=None
            )
            assert events == ()
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_update_state_owner_aware_uses_injected_clock_for_finished_at() -> None:
    """F2: ``update_state_owner_aware`` 写入 ``finished_at`` 必使用注入 clock。

    fake clock 推到一个区分系统墙钟的固定时刻, owner-aware 诊断 close 后
    断言 ``finished_at`` 与 ``clock.now()`` 完全一致, 不会落到真实墙钟。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        attempt_state_store = AttemptStateStore(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            clock.advance(timedelta(seconds=7))
            target_finished_at = clock.now()
            async with storage.transaction() as tx:
                updated = supervisor.lease_store.update_state_owner_aware(
                    tx=tx,
                    owner_context=owner_context,
                    state=AttemptState.STALE,
                    failure_summary="diagnostic_close",
                    terminal_event_position=None,
                )
            assert updated is True
        attempt = attempt_state_store.get(owner_context.attempt_id)
        assert attempt is not None
        assert attempt.state is AttemptState.STALE
        assert attempt.finished_at == target_finished_at
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_close_terminal_rejects_stale_state() -> None:
    """``close_terminal`` 拒绝 ``AttemptState.STALE``，STALE 走 ``mark_stale_or_lost``。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            async with storage.transaction() as tx:
                with pytest.raises(ValueError, match="close_terminal requires"):
                    supervisor.lease_store.close_terminal(
                        tx=tx,
                        owner_context=owner_context,
                        state=AttemptState.STALE,
                        terminal_event_position=GlobalEventPosition(value=1),
                        failure_summary="should_fail",
                    )
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_append_terminal_and_close_respects_state_override() -> None:
    """``terminal_state_override`` 覆盖默认按 draft type 推断的 attempt 终态。

    T4: 传 ``terminal_state_override=AttemptState.FAILED`` 时, 即使 draft
    type 为 ``FINAL_ANSWORD`` (默认推断 SUCCEEDED), attempt 终态也必须是
    FAILED。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        attempt_state_store = AttemptStateStore(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            link = await supervisor.append_terminal_and_close(
                owner_context=owner_context,
                draft=_final_answer_draft(run_id="r1"),
                failure_summary="override_test",
                terminal_state_override=AttemptState.FAILED,
            )
        # override 生效: terminal_state 为 FAILED 而非 SUCCEEDED。
        assert link.terminal_state is AttemptState.FAILED
        attempt = attempt_state_store.get(owner_context.attempt_id)
        assert attempt is not None
        assert attempt.state is AttemptState.FAILED
        assert attempt.failure_summary == "override_test"
    finally:
        storage.close()
