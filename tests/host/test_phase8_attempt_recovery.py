"""Host P8-S6 Stale / Orphan Recovery 主路径测试。

覆盖 :meth:`AttemptSupervisor.recover_stale_attempts` 的全部 typed 决策:

- ``MARK_RECOVERING_AND_CREATE_ATTEMPT``: ``RUNNING`` 旧 attempt lease 过
  期, 旧 attempt 被 CAS 推到 ``RECOVERING`` 并写入 ``stale_marked_at`` /
  ``failure_summary``; 同事务内 INSERT 新 attempt, 新 attempt 持有严格
  更大的 fencing token、独立 owner secret hash, 并通过
  ``recovered_from_attempt_id`` 链接回旧 attempt; 旧 owner 之后再试图
  ``verify_owner`` 必然 fenced。
- ``MARK_LOST`` (run terminal): run 已 terminal 时旧 attempt 被标记为
  ``LOST``, 不创建 recovery attempt; ``host_attempts`` 不新增行。
- ``MARK_LOST`` (orphan ``CREATED``): ``CREATED`` 孤儿行 (无 owner / 无
  fencing token) 被标记为 ``LOST``, 不创建 recovery attempt。
- ``NOOP_TERMINAL``: 候选行 fencing token 在 scan 与短事务之间被其它进
  程改写时, CAS miss 应返回 NOOP, 不创建 recovery attempt, 不覆盖该行。

附加断言: recovery scan 不修改 ``host_projection_checkpoints``, 不写
EventLog 诊断 RunEvent (``list_events`` 仍为空)。

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
    AttemptOwnerToken,
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
    AttemptIndexCollisionError,
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


@pytest.mark.asyncio
async def test_recover_stale_running_attempt_creates_recovery_attempt() -> None:
    """``RUNNING`` lease 过期 -> ``MARK_RECOVERING_AND_CREATE_ATTEMPT``。"""

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        # 进入 lease_context, acquire owner; 退出 ctx 不会自动收口 attempt,
        # 旧行仍处于 RUNNING 状态, 但 lease 在 clock.advance 后过期。
        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ) as old_owner:
            old_attempt_id = old_owner.attempt_id
            old_token = old_owner.fencing_token.value
        # 强制清空 supervisor sessions, 模拟进程崩溃后旧 owner 不可达。
        # 推进时钟超过 lease TTL 让旧行 lease_expires_at <= now。
        clock.advance(timedelta(seconds=120))

        decisions = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(decisions) == 1
        decision = decisions[0]
        assert (
            decision.action
            is AttemptRecoveryAction.MARK_RECOVERING_AND_CREATE_ATTEMPT
        )
        assert decision.source_attempt_id == old_attempt_id
        assert decision.recovery_attempt_id is not None
        assert decision.recovery_attempt_index == 1

        # 验证旧 attempt 已被 CAS 推到 RECOVERING; 新 attempt RUNNING +
        # recovered_from_attempt_id 链接 + 严格更大 fencing token。
        # 通过 SQL 直接验证事实, 避免依赖未公开 helper。
        async with storage.transaction() as tx:
            rows = tx.execute(
                "SELECT attempt_id, attempt_index, state, fencing_token, "
                "recovered_from_attempt_id, stale_marked_at, "
                "failure_summary FROM host_attempts WHERE run_id = ? "
                "ORDER BY attempt_index ASC",
                (_RUN_ID,),
            ).fetchall()
        assert len(rows) == 2
        old_row, new_row = rows[0], rows[1]
        assert old_row["attempt_id"] == old_attempt_id
        assert old_row["state"] == AttemptState.RECOVERING.value
        assert old_row["stale_marked_at"] is not None
        assert old_row["failure_summary"] == "lease_expired_recovery_started"
        assert new_row["attempt_id"] == decision.recovery_attempt_id
        assert new_row["state"] == AttemptState.RUNNING.value
        assert new_row["recovered_from_attempt_id"] == old_attempt_id
        assert int(new_row["fencing_token"]) > old_token

        # recovery scan 不写诊断 RunEvent。
        assert await _events_for(
            supervisor.event_store, run_id=_RUN_ID
        ) == 0

        # 旧 owner 再次 verify 必然 fenced (state 不再 running)。
        with pytest.raises(AttemptFencingError):
            async with storage.transaction() as tx:
                supervisor.lease_store.verify_owner(
                    tx=tx, owner_context=old_owner
                )
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_skips_when_run_is_terminal() -> None:
    """run 已 terminal -> ``MARK_LOST``, 不创建 recovery attempt。"""

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ) as old_owner:
            old_attempt_id = old_owner.attempt_id

        # 把 run 推到 terminal (例如 SUCCEEDED) 后再 scan。
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
        assert decisions[0].recovery_attempt_id is None

        async with storage.transaction() as tx:
            rows = tx.execute(
                "SELECT state FROM host_attempts WHERE run_id = ? "
                "ORDER BY attempt_index ASC",
                (_RUN_ID,),
            ).fetchall()
        # 仅旧 attempt, 无 recovery attempt 行。
        assert len(rows) == 1
        assert rows[0]["state"] == AttemptState.LOST.value
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_marks_orphan_created_attempt_lost() -> None:
    """``CREATED`` 孤儿行 -> ``MARK_LOST``, 不创建 recovery attempt。"""

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        # 直接构造一个 CREATED 行: 无 owner / 无 fencing token, 但带过期
        # lease_expires_at 让它进入 candidate scan 集合。
        expired = (clock.now() - timedelta(seconds=10)).isoformat()
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
                    NULL, NULL, NULL, ?, NULL, NULL, NULL)
                """,
                (
                    "attempt-orphan",
                    _RUN_ID,
                    0,
                    AttemptState.CREATED.value,
                    started,
                    expired,
                ),
            )
        supervisor = _build_supervisor(storage=storage, clock=clock)

        decisions = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(decisions) == 1
        assert decisions[0].action is AttemptRecoveryAction.MARK_LOST
        assert decisions[0].source_attempt_id == "attempt-orphan"
        assert decisions[0].recovery_attempt_id is None

        async with storage.transaction() as tx:
            rows = tx.execute(
                "SELECT attempt_id, state FROM host_attempts WHERE run_id = ?",
                (_RUN_ID,),
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["state"] == AttemptState.LOST.value
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_recover_returns_noop_when_cas_misses() -> None:
    """fencing token 在 scan 与短事务之间改写 -> ``NOOP_TERMINAL``。

    通过直接调用 store 层 CAS 入口模拟该 race: scan 拿到的候选携带 token
    ``T``, 在本进程进入 recovery 短事务之前另一个进程已把该行 fencing_token
    替换为 ``T'``, 因此 CAS ``state='running' AND fencing_token=T`` rowcount
    为 0, store 返回 ``NOOP_TERMINAL`` (``cas_failed_noop`` reason)。

    F1 review fix 断言: supervisor 必须保留 store 返回的 reason
    ``cas_failed_noop``, 不允许被覆盖为 supervisor 自建的常量。
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

        # 模拟另一个进程在 scan 之后, 本进程 CAS 之前覆盖了 fencing_token,
        # 让 mark_recovering CAS rowcount=0 命中 NOOP_TERMINAL 分支。
        async with storage.transaction() as tx:
            tx.execute(
                "UPDATE host_attempts SET fencing_token = ? "
                "WHERE attempt_id = ?",
                (stale_token + 999, old_attempt_id),
            )

        # 直接调用 store CAS 入口, 用 scan 时已记录的 stale token 作为
        # source_fencing_token; 这等价于 supervisor 在拿到候选后被另一个
        # 进程抢先覆写。
        async with storage.transaction() as tx:
            decision = (
                supervisor.lease_store.mark_recovering_and_create_attempt(
                    tx=tx,
                    source_attempt_id=old_attempt_id,
                    source_fencing_token=stale_token,
                    run_id=_RUN_ID,
                    recovery_attempt_id="attempt-recovery-mismatch",
                    recovery_attempt_index=1,
                    owner_id="host-recovery-test",
                    owner_token=AttemptOwnerToken.new(),
                    lease_expires_at=clock.now() + timedelta(seconds=30),
                )
            )
        assert decision.action is AttemptRecoveryAction.NOOP_TERMINAL
        assert decision.source_attempt_id == old_attempt_id
        assert decision.recovery_attempt_id is None
        # F1: store 返回的 reason 必须是 ``cas_failed_noop`` 而不是被
        # supervisor 替换为 ``attempt_already_terminal``。
        assert decision.reason == "cas_failed_noop"
        # CAS miss: 没有创建 recovery 行, 旧行也未被改 state。
        async with storage.transaction() as tx:
            rows = tx.execute(
                "SELECT attempt_id, state FROM host_attempts WHERE run_id = ?",
                (_RUN_ID,),
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["state"] == AttemptState.RUNNING.value
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_supervisor_preserves_store_reason_on_cas_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F1: ``recover_stale_attempts`` 必须透传 store 层返回的 reason。

    构造 fencing token race 让 ``mark_recovering_and_create_attempt`` 返回
    ``NOOP_TERMINAL(reason="cas_failed_noop")``, 之后 supervisor
    ``recover_stale_attempts`` 必须把该 reason 原样带回, 不允许把它静默
    替换为 supervisor 自建的 ``attempt_already_terminal``; 同时也不允许
    替换为本 slice 新增的 ``unique_index_collision``。

    用 monkeypatch 改写 ``list_recovery_candidates`` 行为以模拟"scan 时
    候选携带 stale fencing token, 短事务内 CAS rowcount=0"的真实并发
    race; 这是 store 层 typed decision 真正会被触发的路径。
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

        # 让 scan 看到的候选携带 stale_token; 然后在它真正进入短事务 CAS
        # 之前, 由"另一个进程"改写 fencing_token 让 CAS rowcount=0。
        original_list = AttemptLeaseStore.list_recovery_candidates

        def _patched_list(  # type: ignore[no-untyped-def]
            self, *, tx, run_id, now
        ):
            candidates = original_list(self, tx=tx, run_id=run_id, now=now)
            # scan 后立刻覆写 fencing_token, 模拟其它进程抢先一步; 候选
            # 元组里仍然持有 stale_token, supervisor 后续 CAS 必然 miss。
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
        assert decision.recovery_attempt_id is None
        # F1 核心断言: store reason 必须被原样带回, 不能被 supervisor 覆盖。
        assert decision.reason == "cas_failed_noop"
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_mark_recovering_unique_index_collision_rolls_back_atomically() -> (
    None
):
    """F2 store 层断言: ``UNIQUE(run_id, attempt_index)`` 冲突应抛 typed 异常。

    预置一个已经占用 ``attempt_index=1`` 的 attempt 行, 然后调用
    ``mark_recovering_and_create_attempt`` 让它去插入 ``attempt_index=1``
    的新 recovery attempt, 必须抛 :class:`AttemptIndexCollisionError`,
    而不是裸 ``sqlite3.IntegrityError``; 旧 attempt 的 ``RECOVERING`` CAS
    必须随外层事务回滚, 旧行仍处于 ``RUNNING``, 不留半状态。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id=_RUN_ID)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        # 先 acquire 旧 attempt (attempt_index=0) 让它处于 RUNNING。
        async with supervisor.lease_context(
            run_id=_RUN_ID, attempt_index=0
        ) as old_owner:
            old_attempt_id = old_owner.attempt_id
            stale_token = old_owner.fencing_token.value
        # 预置一个 attempt_index=1 的"占位"行, 模拟另一进程已经成功完成
        # recovery 的场景。
        async with storage.transaction() as tx:
            now_iso = clock.now().isoformat()
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
                    "attempt-other-recovery",
                    _RUN_ID,
                    1,
                    AttemptState.RUNNING.value,
                    now_iso,
                ),
            )
        clock.advance(timedelta(seconds=120))

        # 直接驱动 store 层接口: 让 lease 过期的旧 attempt 试图把新
        # recovery attempt 也写到 attempt_index=1, 必须抛 typed 冲突。
        with pytest.raises(AttemptIndexCollisionError) as excinfo:
            async with storage.transaction() as tx:
                supervisor.lease_store.mark_recovering_and_create_attempt(
                    tx=tx,
                    source_attempt_id=old_attempt_id,
                    source_fencing_token=stale_token,
                    run_id=_RUN_ID,
                    recovery_attempt_id="attempt-recovery-collision",
                    recovery_attempt_index=1,
                    owner_id="host-recovery-test",
                    owner_token=AttemptOwnerToken.new(),
                    lease_expires_at=clock.now() + timedelta(seconds=30),
                )
        assert excinfo.value.run_id == _RUN_ID
        assert excinfo.value.attempt_index == 1
        assert excinfo.value.source_attempt_id == old_attempt_id

        # 关键断言: 整事务已被回滚, 旧 attempt 仍 RUNNING, 没有进入
        # RECOVERING 半状态; ``attempt_index=1`` 占位行未被改写; 也没有
        # 多余的 recovery attempt 行被落库。
        async with storage.transaction() as tx:
            rows = tx.execute(
                "SELECT attempt_id, attempt_index, state FROM host_attempts "
                "WHERE run_id = ? ORDER BY attempt_index ASC",
                (_RUN_ID,),
            ).fetchall()
        assert len(rows) == 2
        assert rows[0]["attempt_id"] == old_attempt_id
        assert rows[0]["state"] == AttemptState.RUNNING.value
        assert rows[1]["attempt_id"] == "attempt-other-recovery"
        assert rows[1]["state"] == AttemptState.RUNNING.value
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_supervisor_unique_index_collision_returns_typed_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F2 supervisor 层断言: 冲突收口为 typed ``NOOP_TERMINAL``, 不抛裸异常。

    通过 monkeypatch ``next_attempt_index`` 强制返回已被占用的 index,
    模拟两个并发进程在独立短事务中算出相同 ``attempt_index`` 的真实并发
    race; supervisor 必须在事务外捕获 :class:`AttemptIndexCollisionError`,
    返回 ``AttemptRecoveryDecision(action=NOOP_TERMINAL,
    reason="unique_index_collision")``, 旧 attempt 不被改成 RECOVERING。
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

        # 预置 attempt_index=1 占位行, 模拟其它进程已经 race 成功。
        async with storage.transaction() as tx:
            now_iso = clock.now().isoformat()
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
                    "attempt-winner",
                    _RUN_ID,
                    1,
                    AttemptState.SUCCEEDED.value,
                    now_iso,
                ),
            )
        clock.advance(timedelta(seconds=120))

        # monkeypatch next_attempt_index: 在并发场景中, 本进程读到的
        # MAX(attempt_index) 可能在 race 中过期; 这里强制让 supervisor
        # 试图占用与"其它进程"相同的 attempt_index=1, 必然 UNIQUE 冲突。
        def _force_collision_index(  # type: ignore[no-untyped-def]
            *_args, **_kwargs
        ) -> int:
            return 1

        monkeypatch.setattr(
            AttemptLeaseStore,
            "next_attempt_index",
            _force_collision_index,
        )

        decisions = await supervisor.recover_stale_attempts(run_id=_RUN_ID)
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.action is AttemptRecoveryAction.NOOP_TERMINAL
        assert decision.source_attempt_id == old_attempt_id
        assert decision.recovery_attempt_id is None
        assert decision.recovery_attempt_index is None
        assert decision.reason == "unique_index_collision"

        # 原子性核心断言: 旧 attempt 没有被改成 RECOVERING; 占位行未被
        # 触碰; 没有任何残留 recovery 行。
        async with storage.transaction() as tx:
            rows = tx.execute(
                "SELECT attempt_id, attempt_index, state FROM host_attempts "
                "WHERE run_id = ? ORDER BY attempt_index ASC",
                (_RUN_ID,),
            ).fetchall()
        assert len(rows) == 2
        assert rows[0]["attempt_id"] == old_attempt_id
        assert rows[0]["state"] == AttemptState.RUNNING.value
        assert rows[1]["attempt_id"] == "attempt-winner"
        assert rows[1]["state"] == AttemptState.SUCCEEDED.value
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
        # ensure 一个 checkpoint 行作为 baseline。
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
