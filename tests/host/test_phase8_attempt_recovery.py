"""Host P8 Stale / Orphan Recovery 诊断收口测试 (P8 D2 后)。

P8 D2 后 recovery scan 仅做诊断收口, 不再创建 recovery attempt。
``AttemptSupervisor.recover_stale_attempts`` 的全部 typed 决策:

- ``MARK_LOST`` (run terminal): run 已 terminal -> 旧 attempt 标记为
  ``LOST``, reason = ``recovery_run_terminal``;
- ``MARK_LOST`` (orphan ``CREATED``): ``CREATED`` 孤儿行 (lease 字段为
  ``NULL`` 或 fencing_token 为 ``None``) -> ``MARK_LOST``, reason =
  ``recovery_created_orphan``;
- ``MARK_LOST`` (lease 过期): ``RUNNING`` lease 过期 -> ``MARK_LOST``,
  reason = ``recovery_lease_expired``;
- ``NOOP_TERMINAL``: CAS miss (其它进程已推进) -> store 层 typed
  decision 原样透传, reason = ``cas_failed_noop``。

附加断言:

- recovery scan **不**修改 ``host_projection_checkpoints``;
- recovery scan **不**写 EventLog 诊断 RunEvent;
- recovery scan **不**新增 ``host_attempts`` 行 (无 recovery attempt);
- 二次 scan 幂等: 旧 attempt 已 LOST, 二次扫描候选集为空。

测试一律使用真实 ``AttemptSupervisor`` + 真实 storage + ``_FakeClock``,
不 mock fencing 路径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptLeaseConfig,
    AttemptRecoveryAction,
)
from dayu.host._attempt_supervisor import AttemptSupervisor
from dayu.host._durable_event_store import (
    DurableRunEventStore,
    open_durable_event_store,
)
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import AttemptState, ExtendedRunState
from dayu.host._projection_store import ProjectionStore
from dayu.host._run_state_store import (
    AttemptLeaseStore,
)


_RUN_ID: str = "r-recovery"


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

        :returns: timezone-aware datetime。
        :raises Exception: 不主动抛出异常。
        """

        return self.current

    def advance(self, delta: timedelta) -> None:
        """推进 fake 时间。

        :param delta: 推进步长。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.current = self.current + delta


def _open_storage() -> HostStorage:
    """构造内存 SQLite storage 并完成 schema bootstrap。

    :returns: 已 open 的 :class:`HostStorage`。
    :raises sqlite3.DatabaseError: bootstrap 失败时透传。
    """

    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    return storage


async def _seed_run(
    storage: HostStorage,
    *,
    run_id: str,
    state: ExtendedRunState = ExtendedRunState.RUNNING,
) -> None:
    """预置 host_runs 行。

    :param storage: 共享 storage。
    :param run_id: Run id。
    :param state: 期望的 run 状态。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: 写入失败透传。
    """

    timestamp = datetime(
        2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc
    ).isoformat()
    async with storage.transaction() as tx:
        tx.execute(
            "INSERT INTO host_runs (run_id, session_id, state, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, "s", state.value, timestamp, timestamp),
        )


def _build_supervisor(
    *, storage: HostStorage, clock: _FakeClock
) -> AttemptSupervisor:
    """装配真实 supervisor + lease store + event store。

    :param storage: 共享 storage。
    :param clock: fake clock。
    :returns: 已装配 :class:`AttemptSupervisor`。
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


async def _events_for(
    event_store: DurableRunEventStore, *, run_id: str
) -> int:
    """统计某 run 当前 EventLog 行数。

    :param event_store: 事件 store。
    :param run_id: Run id。
    :returns: 事件数。
    :raises sqlite3.DatabaseError: 读取失败透传。
    """

    events = await event_store.list_events(run_id=run_id, after=None)
    return len(events)


async def _attempt_count(
    storage: HostStorage, *, run_id: str
) -> int:
    """统计 ``host_attempts`` 当前行数。

    :param storage: 共享 storage。
    :param run_id: Run id。
    :returns: 行数。
    :raises sqlite3.DatabaseError: 读取失败透传。
    """

    async with storage.transaction() as tx:
        row = tx.execute(
            "SELECT COUNT(*) AS n FROM host_attempts WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return int(row["n"])


@pytest.mark.asyncio
async def test_recover_running_lease_expired_marks_lost_no_new_attempt() -> None:
    """``RUNNING`` lease 过期 -> ``MARK_LOST`` + ``recovery_lease_expired``。

    P8 D2: recovery 不再创建 recovery attempt; 旧 attempt 直接 LOST,
    ``host_attempts`` 不新增行。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ) as old_owner:
            old_attempt_id = old_owner.attempt_id
            old_token = old_owner.fencing_token.value
        clock.advance(timedelta(seconds=120))

        decisions = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.action is AttemptRecoveryAction.MARK_LOST
        assert decision.source_attempt_id == old_attempt_id
        assert decision.reason == "recovery_lease_expired"

        # 关键断言: scan 后 host_attempts 不出现新行 (无 recovery attempt)。
        assert await _attempt_count(storage, run_id=_RUN_ID) == 1

        # 旧 attempt state == LOST; fencing_token 不被改写 (CAS 用 token 匹配)。
        async with storage.transaction() as tx:
            row = tx.execute(
                "SELECT state, fencing_token, failure_summary "
                "FROM host_attempts WHERE attempt_id = ?",
                (old_attempt_id,),
            ).fetchone()
        assert row["state"] == AttemptState.LOST.value
        assert int(row["fencing_token"]) == old_token
        assert row["failure_summary"] == "recovery_lease_expired"

        # recovery scan 不写诊断 RunEvent。
        assert await _events_for(
            supervisor.event_store, run_id=_RUN_ID
        ) == 0

        # 旧 owner 再次 verify 必然 fenced。
        with pytest.raises(AttemptFencingError):
            async with storage.transaction() as tx:
                supervisor.lease_store.verify_owner(
                    tx=tx, owner_context=old_owner
                )
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_skips_when_run_is_terminal() -> None:
    """run 已 terminal -> ``MARK_LOST`` + ``recovery_run_terminal``。"""

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ) as old_owner:
            old_attempt_id = old_owner.attempt_id

        async with storage.transaction() as tx:
            tx.execute(
                "UPDATE host_runs SET state = ? WHERE run_id = ?",
                (ExtendedRunState.SUCCEEDED.value, _RUN_ID),
            )
        clock.advance(timedelta(seconds=120))

        decisions = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(decisions) == 1
        assert decisions[0].action is AttemptRecoveryAction.MARK_LOST
        assert decisions[0].source_attempt_id == old_attempt_id
        assert decisions[0].reason == "recovery_run_terminal"

        # 仍只有旧 attempt, 无 recovery attempt 行。
        assert await _attempt_count(storage, run_id=_RUN_ID) == 1
        async with storage.transaction() as tx:
            row = tx.execute(
                "SELECT state FROM host_attempts WHERE run_id = ?",
                (_RUN_ID,),
            ).fetchone()
        assert row["state"] == AttemptState.LOST.value
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_marks_orphan_created_attempt_lost() -> None:
    """``CREATED`` 孤儿行 -> ``MARK_LOST`` + ``recovery_created_orphan``。

    S6: ``state='created' AND lease_expires_at IS NULL`` 也必须进入候选集。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        # CREATED 孤儿行: owner / fencing_token / lease 字段全为 NULL。
        started = clock.now().isoformat()
        async with storage.transaction() as tx:
            tx.execute(
                """
                INSERT INTO host_attempts (
                    attempt_id, run_id, attempt_index, state, started_at,
                    finished_at, terminal_event_position, failure_summary,
                    owner_id, owner_token_hash, fencing_token,
                    lease_expires_at, lease_renewed_at,
                    recovered_from_attempt_id, stale_marked_at
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL,
                    NULL, NULL, NULL, NULL, NULL, NULL, NULL)
                """,
                (
                    "attempt-orphan",
                    _RUN_ID,
                    0,
                    AttemptState.CREATED.value,
                    started,
                ),
            )
        supervisor = _build_supervisor(storage=storage, clock=clock)

        decisions = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(decisions) == 1
        assert decisions[0].action is AttemptRecoveryAction.MARK_LOST
        assert decisions[0].source_attempt_id == "attempt-orphan"
        assert decisions[0].reason == "recovery_created_orphan"

        assert await _attempt_count(storage, run_id=_RUN_ID) == 1
        async with storage.transaction() as tx:
            row = tx.execute(
                "SELECT attempt_id, state FROM host_attempts WHERE run_id = ?",
                (_RUN_ID,),
            ).fetchone()
        assert row["state"] == AttemptState.LOST.value
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_idempotent_second_scan_finds_no_candidates() -> None:
    """recovery scan 幂等: 旧 attempt 已 LOST 后, 二次扫描候选集为空。"""

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ):
            pass
        clock.advance(timedelta(seconds=120))

        first = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(first) == 1
        assert first[0].action is AttemptRecoveryAction.MARK_LOST

        # 二次扫描不应再返回候选, 也不应再次推进任何状态。
        second = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert second == ()
        assert await _attempt_count(storage, run_id=_RUN_ID) == 1
        assert await _events_for(
            supervisor.event_store, run_id=_RUN_ID
        ) == 0
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_returns_noop_when_cas_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fencing token 在 scan 与 CAS 之间被改写 -> ``NOOP_TERMINAL``。

    通过 monkeypatch ``list_recovery_candidates`` 模拟"scan 拿到 stale
    fencing token, 进入短事务前另一进程已抢先覆写 fencing_token"的
    并发 race; supervisor 必须把 store 层 ``NOOP_TERMINAL(reason=
    cas_failed_noop)`` 决策原样带回, 不允许覆写 reason。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ) as old_owner:
            old_attempt_id = old_owner.attempt_id
            stale_token = old_owner.fencing_token.value
        clock.advance(timedelta(seconds=120))

        original_list = AttemptLeaseStore.list_recovery_candidates

        def _patched_list(  # type: ignore[no-untyped-def]
            self, *, tx, run_id, now
        ):
            candidates = original_list(self, tx=tx, run_id=run_id, now=now)
            tx.execute(
                "UPDATE host_attempts SET fencing_token = ? "
                "WHERE attempt_id = ?",
                (stale_token + 999, old_attempt_id),
            )
            return candidates

        monkeypatch.setattr(
            AttemptLeaseStore, "list_recovery_candidates", _patched_list
        )

        decisions = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.action is AttemptRecoveryAction.NOOP_TERMINAL
        assert decision.source_attempt_id == old_attempt_id
        assert decision.reason == "cas_failed_noop"

        # CAS miss: 旧行 state 仍 RUNNING, 没有新 attempt 行。
        assert await _attempt_count(storage, run_id=_RUN_ID) == 1
        async with storage.transaction() as tx:
            row = tx.execute(
                "SELECT state FROM host_attempts WHERE attempt_id = ?",
                (old_attempt_id,),
            ).fetchone()
        assert row["state"] == AttemptState.RUNNING.value
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_noop_when_candidate_lease_is_renewed_before_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """scan 后、mark 前 lease 变为有效 -> ``NOOP_TERMINAL``，不误标 LOST。

    回归 P8 F14：``mark_stale_or_lost`` 的非 orphan CAS 必须重新检查
    ``lease_expires_at <= now``。否则 recovery scan 读到旧候选后，合法
    owner 已把 lease 刷新到未来时，mark 阶段仍会仅凭 fencing token 命中
    并错误收口 active attempt。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ) as owner:
            attempt_id = owner.attempt_id
        clock.advance(timedelta(seconds=120))

        original_list = AttemptLeaseStore.list_recovery_candidates

        def _patched_list(  # type: ignore[no-untyped-def]
            self, *, tx, run_id, now
        ):
            candidates = original_list(self, tx=tx, run_id=run_id, now=now)
            tx.execute(
                "UPDATE host_attempts SET lease_expires_at = ?, "
                "lease_renewed_at = ? WHERE attempt_id = ?",
                (
                    (now + timedelta(seconds=30)).isoformat(),
                    now.isoformat(),
                    attempt_id,
                ),
            )
            return candidates

        monkeypatch.setattr(
            AttemptLeaseStore, "list_recovery_candidates", _patched_list
        )

        decisions = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(decisions) == 1
        assert decisions[0].action is AttemptRecoveryAction.NOOP_TERMINAL
        assert decisions[0].reason == "cas_failed_noop"

        async with storage.transaction() as tx:
            row = tx.execute(
                "SELECT state, lease_expires_at FROM host_attempts "
                "WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        assert row["state"] == AttemptState.RUNNING.value
        assert datetime.fromisoformat(row["lease_expires_at"]) > clock.now()
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_does_not_advance_projection_checkpoint() -> None:
    """recovery scan 必须不修改 ``host_projection_checkpoints``。"""

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        projections = ProjectionStore(storage=storage)
        async with storage.transaction() as tx:
            projections.ensure(
                tx=tx,
                observer_id="obs",
                projection_name="proj",
                schema_version=1,
            )
        before = projections.get(
            observer_id="obs",
            projection_name="proj",
            schema_version=1,
        )
        assert before is not None

        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ):
            pass
        clock.advance(timedelta(seconds=120))
        await supervisor.recover_stale_attempts(run_id=_RUN_ID)

        after = projections.get(
            observer_id="obs",
            projection_name="proj",
            schema_version=1,
        )
        assert after is not None
        assert (
            after.last_success_position == before.last_success_position
        )
        assert (
            after.last_attempted_position == before.last_attempted_position
        )
        assert after.status == before.status
        assert after.retry_count == before.retry_count
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_stale_attempts_full_scan_run_id_none() -> None:
    """``run_id=None`` 全库扫描: 跨多个 run 的过期 attempt 独立收口。

    T2: 验证全库扫描路径的候选排序与跨 run 独立事务回滚行为。
    """

    storage = _open_storage()
    try:
        run_a, run_b, run_c = "r-full-a", "r-full-b", "r-full-c"
        await _seed_run(storage, run_id=run_a)
        await _seed_run(storage, run_id=run_b)
        # run_c 为 terminal run。
        await _seed_run(
            storage, run_id=run_c, state=ExtendedRunState.SUCCEEDED
        )
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)

        # 为每个 run 创建一个 attempt。
        async with supervisor.lease_context(
            run_id=run_a, attempt_index=0
        ) as ctx_a:
            attempt_a = ctx_a.attempt_id
        async with supervisor.lease_context(
            run_id=run_b, attempt_index=0
        ) as ctx_b:
            attempt_b = ctx_b.attempt_id
        async with supervisor.lease_context(
            run_id=run_c, attempt_index=0
        ) as ctx_c:
            attempt_c = ctx_c.attempt_id

        # 推进时间使所有 lease 过期。
        clock.advance(timedelta(seconds=120))

        # 全库扫描。
        decisions = await supervisor.recover_stale_attempts(run_id=None)
        assert len(decisions) == 3

        decision_map = {d.source_attempt_id: d for d in decisions}

        # run_a: lease 过期 -> MARK_LOST。
        da = decision_map[attempt_a]
        assert da.action is AttemptRecoveryAction.MARK_LOST
        assert da.reason == "recovery_lease_expired"

        # run_b: lease 过期 -> MARK_LOST。
        db = decision_map[attempt_b]
        assert db.action is AttemptRecoveryAction.MARK_LOST
        assert db.reason == "recovery_lease_expired"

        # run_c: run 已 terminal -> MARK_LOST。
        dc = decision_map[attempt_c]
        assert dc.action is AttemptRecoveryAction.MARK_LOST
        assert dc.reason == "recovery_run_terminal"

        # 每个 run 仍只有旧 attempt, 无 recovery attempt 行。
        assert await _attempt_count(storage, run_id=run_a) == 1
        assert await _attempt_count(storage, run_id=run_b) == 1
        assert await _attempt_count(storage, run_id=run_c) == 1

        # 所有 attempt 均为 LOST。
        async with storage.transaction() as tx:
            for attempt_id in (attempt_a, attempt_b, attempt_c):
                row = tx.execute(
                    "SELECT state FROM host_attempts WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchone()
                assert row["state"] == AttemptState.LOST.value

        # EventLog 无诊断 RunEvent。
        for run_id in (run_a, run_b, run_c):
            assert await _events_for(supervisor.event_store, run_id=run_id) == 0

        # 二次扫描幂等: 所有 attempt 已 LOST, 候选集为空。
        second = await supervisor.recover_stale_attempts(run_id=None)
        assert len(second) == 0
    finally:
        storage.close()
