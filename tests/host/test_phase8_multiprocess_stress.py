"""Host P8-S7 真实多进程 + Observer Drain 验证测试。

本文件覆盖 P8-S7 entry 的四类默认可跑场景, 全部基于真实 spawn 子进程
+ 文件落库 SQLite (WAL + ``BEGIN IMMEDIATE``):

1. **跨进程 EventLog append**: N 个独立进程并发 ``append`` 非 terminal
   canonical 事件; 验证 per-run cursor 单调唯一、global ``event_position``
   单调唯一、行数等于 N*M。
2. **Terminal race**: 两个进程持有不同 owner token 同时尝试 terminal
   close; 验证恰好一个胜出, 另一个 fenced; ``host_attempts`` /
   ``host_runs`` terminal snapshot 来自胜出者; EventLog 不残留 stale
   terminal。
3. **跨进程 stale recovery**: 进程 A 拿到 lease 后退出 (不收口);
   测试主进程把 ``lease_expires_at`` 改成过去时刻; 进程 B 调
   ``recover_stale_attempts`` 落地 typed
   ``MARK_RECOVERING_AND_CREATE_ATTEMPT``; 旧 owner late append 必然
   ``AttemptFencingError``; 不写诊断 RunEvent。
4. **Observer drain / startup_reconcile**: 进程 A 写入 terminal facts
   但 **不** drain; 进程 B ``build_durable_harness`` +
   ``coordinator.startup_reconcile`` 把 memory / timeline / audit
   checkpoint 推到 EventLog tail; 第二次 reconcile 幂等。
   本场景 **仅** 验证多进程下 EventLog / projection checkpoint /
   ``startup_reconcile`` 既有语义, **不** 声称 in-memory
   ``ConversationMemoryStore`` 具备生产级崩溃恢复; durable memory store
   与 checkpoint-aware rebuild 已划入 P8-S8 scope。

测试目标是 P8 既有契约在多进程下的真实可重放性, 不引入 multiprocessing
launcher 的生产化, 也不自动接入 ``build_durable_harness`` bootstrap 中。
所有同步通过 :func:`tests.host._multiprocess_platform.run_workers` +
spawn-context Barrier/Queue, 不使用 ``time.sleep`` 做 race 控制, 不
使用 ``:memory:`` 库。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from dayu.engine import ContentDeltaData, FinalAnswerData, FinishReason
from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptLeaseConfig,
    AttemptOwnerContext,
    AttemptOwnerToken,
    DEFAULT_ATTEMPT_LEASE_CONFIG,
)
from dayu.host._attempt_supervisor import AttemptSupervisor
from dayu.host._durable_event_store import (
    DurableRunEventStore,
    open_durable_event_store,
)
from dayu.host._durable_harness import (
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import AttemptState, ExtendedRunState, FencingToken
from dayu.host._run_state_store import AttemptLeaseStore
from dayu.host.contracts import (
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    UserInputAcceptedData,
    UserInputScope,
)
from tests.host._multiprocess_platform import (
    DEFAULT_JOIN_TIMEOUT_SECONDS,
    WorkerContext,
    WorkerSpec,
    assert_clean_exit,
    get_spawn_context,
    make_barrier,
    report_error,
    report_success,
    run_workers,
    temp_database_path,
)

_RUN_ID: str = "r-mp"
_SESSION_ID: str = "s-mp"
_LEASE_TTL_SECONDS: int = 30
_LEASE_RENEW_INTERVAL_SECONDS: int = 10
_OWNER_PREFIX: str = "host-mp-test"
_EVENTS_PER_WORKER: int = 5
_APPEND_WORKER_COUNT: int = 4


# ---------------------------------------------------------------------------
# 通用进程内辅助 (主进程 / 子进程都会用到, 但每个 helper 只允许在其声明
# 进程内调用; 子进程不持有主进程的 HostStorage 实例)。
# ---------------------------------------------------------------------------


def _utc() -> datetime:
    """返回 timezone-aware UTC 当前时间。

    :returns: timezone-aware UTC datetime。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


class _SystemUtcClock:
    """子进程内使用的系统 UTC clock。

    P8-S7 多进程场景下不能跨进程共享 fake clock; 每个子进程内部都装配
    一个独立的实壁钟实例, 喂给 :class:`AttemptLeaseStore` /
    :class:`AttemptSupervisor` 做 lease 时间判断。
    """

    def now(self) -> datetime:
        """返回 timezone-aware UTC 当前时间。

        :returns: timezone-aware UTC datetime。
        :raises Exception: 不主动抛出异常。
        """

        return datetime.now(tz=timezone.utc)


def _content_draft(*, run_id: str, worker: str, idx: int) -> RunEventDraft:
    """构造非 terminal preview content delta draft。

    :param run_id: Run id。
    :param worker: 子进程 name; 用于 engine event id 唯一性。
    :param idx: 子进程内序号。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=_SESSION_ID,
        kind=RunEventKind.PREVIEW,
        source=RunEventSource.ENGINE,
        type=RunEventType.RUNNER_CONTENT_DELTA,
        occurred_at=_utc(),
        data=ContentDeltaData(iteration_id=worker, delta=f"{worker}#{idx}"),
        source_engine_event_id=f"engine-{worker}-{idx}",
    )


def _final_draft(*, run_id: str, worker: str) -> RunEventDraft:
    """构造 terminal final answer canonical draft。

    :param run_id: Run id。
    :param worker: 子进程 name; 用于 engine event id 唯一性。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=_SESSION_ID,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.FINAL_ANSWER,
        occurred_at=_utc(),
        data=FinalAnswerData(
            content=f"final-from-{worker}",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        source_engine_event_id=f"engine-final-{worker}",
    )


def _seed_run_row(storage: HostStorage, *, run_id: str) -> None:
    """同步预置 ``host_runs`` 行 (run state = RUNNING)。

    主进程在多进程 race 之前预置 run 行, 让子进程的 acquire 不会因为
    ``host_runs`` 缺失被 store 层拒绝; 这是 P8-S6 既有约束。

    :param storage: 主进程 HostStorage。
    :param run_id: Run id。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: 写入失败时透传。
    """

    async def _do() -> None:
        timestamp = _utc().isoformat()
        async with storage.transaction() as tx:
            tx.execute(
                "INSERT INTO host_runs (run_id, session_id, state, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    _SESSION_ID,
                    ExtendedRunState.RUNNING.value,
                    timestamp,
                    timestamp,
                ),
            )

    asyncio.run(_do())


def _bootstrap_database(database_path: str) -> None:
    """在主进程内创建文件并完成 schema bootstrap + 预置 run 行。

    :param database_path: 文件 SQLite 路径。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: 失败时透传。
    """

    storage = HostStorage(database_path=database_path)
    try:
        open_durable_event_store(storage)
        _seed_run_row(storage, run_id=_RUN_ID)
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# 场景 1: 跨进程 EventLog append
# ---------------------------------------------------------------------------


def _worker_append_events(
    context: WorkerContext,
    database_path: str,
    run_id: str,
    events_per_worker: int,
) -> None:
    """spawn 子进程: 依序 append N 条 preview content delta 事件。

    每个子进程打开独立 :class:`HostStorage`, 通过文件 SQLite WAL +
    ``BEGIN IMMEDIATE`` 与其它进程并发追加; 不复用主进程连接。barrier
    用于让所有 worker "几乎同时" 进入 append 区段, 放大 race。

    :param context: 子进程上下文, 必须由 helper 注入。
    :param database_path: 文件 SQLite 路径。
    :param run_id: Run id。
    :param events_per_worker: 本 worker 要追加的事件条数。
    :returns: 无返回值。
    :raises Exception: 内部异常由 :func:`report_error` 回报。
    """

    try:
        storage = HostStorage(database_path=database_path)
        try:
            store = DurableRunEventStore(storage=storage)
            if context.barrier is not None:
                context.barrier.wait()
            sequences: list[int] = []
            for idx in range(events_per_worker):
                draft = _content_draft(
                    run_id=run_id, worker=context.name, idx=idx
                )
                event = asyncio.run(store.append(draft))
                sequences.append(event.cursor.sequence)
        finally:
            storage.close()
        report_success(context, payload=sequences)
    except BaseException as exc:  # noqa: BLE001
        report_error(context, exc=exc)


def test_cross_process_append_preserves_cursor_and_position(
    tmp_path: Path,
) -> None:
    """N 个进程并发 append, per-run sequence + global position 严格唯一单调。"""

    database_path = temp_database_path(tmp_path)
    _bootstrap_database(database_path)

    ctx = get_spawn_context()
    barrier = make_barrier(ctx, parties=_APPEND_WORKER_COUNT)
    specs = tuple(
        WorkerSpec(
            name=f"appender-{i}",
            target=_worker_append_events,
            args=(database_path, _RUN_ID, _EVENTS_PER_WORKER),
        )
        for i in range(_APPEND_WORKER_COUNT)
    )
    outcomes = run_workers(specs, barrier=barrier)
    assert_clean_exit(outcomes)

    storage = HostStorage(database_path=database_path)
    try:
        rows = storage.execute_read(
            "SELECT run_id, sequence, event_position FROM host_run_events "
            "ORDER BY event_position ASC"
        )
        # 全部事件总数 = workers * per-worker。
        assert len(rows) == _APPEND_WORKER_COUNT * _EVENTS_PER_WORKER
        # global position 单调严格递增且唯一。
        positions = [int(row["event_position"]) for row in rows]
        assert positions == sorted(set(positions))
        # per-run sequence 严格唯一; 因为只有一个 run, 它们形成 0..N-1 的
        # 完整置换 (无 gap, 无重复)。
        sequences = sorted(int(row["sequence"]) for row in rows if row["run_id"] == _RUN_ID)
        assert sequences == list(range(_APPEND_WORKER_COUNT * _EVENTS_PER_WORKER))
        # 每个 worker 自己回报的 sequence 也必须严格单调递增 (本 worker 内
        # 顺序写入), 即使与其它 worker 的 sequence 交错。
        for outcome in outcomes:
            payload = outcome.result
            assert isinstance(payload, list)
            assert len(payload) == _EVENTS_PER_WORKER
            assert payload == sorted(payload)
            assert len(set(payload)) == _EVENTS_PER_WORKER
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# 场景 2: terminal close race
# ---------------------------------------------------------------------------


def _create_running_attempt_synchronously(
    *, database_path: str, run_id: str
) -> tuple[str, int, str, datetime]:
    """在主进程内为 race 准备一个真实 RUNNING attempt + 第二个 owner。

    流程:

    1. 通过 :class:`AttemptSupervisor` 进入 ``lease_context`` 让 store
       层落地一个 RUNNING attempt 行 (含 fencing token + owner hash);
    2. ``lease_context`` 退出后, attempt 行仍是 RUNNING 但 supervisor 不
       再持有 session;
    3. 直接读出 attempt_id, 然后构造一个新的 owner secret token 并把它
       的 hash 写回库, 同时把 lease 续到未来; 这样我们得到 **两个互不
       信任的 owner secret token**, 它们持有同一个 fencing token / 同一
       个 attempt_id, 但 secret 不同 -- store CAS (``owner_token_hash``)
       会拒绝错误的 secret。

    返回的 ``token_a`` 在主进程内是当前库中真实的 owner secret;
    ``token_b`` 是一个 "竞争 owner secret", 但它的 hash 不在库内, 因此
    一定会 fenced。这恰好模拟了进程 A 真实持有 lease, 进程 B 凭一个过
    期 / 错误 secret 试图终态收口的场景, 所有 CAS 路径 (``verify_owner``
    + ``close_terminal``) 都会按 typed fencing 拒绝。

    :param database_path: 文件 SQLite 路径。
    :param run_id: Run id。
    :returns: ``(attempt_id, fencing_token, token_a_secret, lease_expires_at)``。
    :raises sqlite3.DatabaseError: 失败时透传。
    """

    async def _do() -> tuple[str, int, str, datetime]:
        storage = HostStorage(database_path=database_path)
        try:
            clock = _SystemUtcClock()
            event_store = DurableRunEventStore(storage=storage)
            lease_store = AttemptLeaseStore(storage=storage, clock=clock)
            config = AttemptLeaseConfig(
                ttl=timedelta(seconds=_LEASE_TTL_SECONDS),
                renew_interval=timedelta(seconds=_LEASE_RENEW_INTERVAL_SECONDS),
                owner_id_prefix=_OWNER_PREFIX,
            )
            supervisor = AttemptSupervisor(
                storage=storage,
                lease_store=lease_store,
                lease_config=config,
                clock=clock,
                event_store=event_store,
            )
            captured_attempt_id: str
            captured_token: int
            captured_secret: str
            async with supervisor.lease_context(
                run_id=run_id, attempt_index=0
            ) as owner:
                captured_attempt_id = owner.attempt_id
                captured_token = owner.fencing_token.value
                captured_secret = owner.owner_token.value
            # lease_context 退出后, supervisor 注销 session 但 attempt 行
            # 仍然处于 RUNNING; 我们把 lease 续到未来, 以避免 store 层在
            # ``verify_owner`` 时把 lease_expires_at 视为已过期。
            future_expiry = _utc() + timedelta(seconds=_LEASE_TTL_SECONDS * 4)
            async with storage.transaction() as tx:
                tx.execute(
                    "UPDATE host_attempts SET lease_expires_at = ?, "
                    "lease_renewed_at = ? WHERE attempt_id = ?",
                    (
                        future_expiry.isoformat(),
                        _utc().isoformat(),
                        captured_attempt_id,
                    ),
                )
            return (
                captured_attempt_id,
                captured_token,
                captured_secret,
                future_expiry,
            )
        finally:
            storage.close()

    return asyncio.run(_do())


def _worker_terminal_close(
    context: WorkerContext,
    database_path: str,
    run_id: str,
    attempt_id: str,
    fencing_token: int,
    owner_secret: str,
    lease_expires_at_iso: str,
    attempt_index: int,
) -> None:
    """spawn 子进程: 用给定 owner 凭据尝试 terminal close。

    凭子进程持有的 owner secret 在 ``BEGIN IMMEDIATE`` 事务内调用
    :meth:`AttemptScopedRunEventAppender.append_terminal_and_close`; 命
    中 owner CAS 失败时透传 :class:`AttemptFencingError`, 由 worker 包
    装为 ``ok=True`` + ``payload['fenced']=True``, 而不是子进程崩溃。
    成功胜出时 ``payload['fenced']=False`` 并附带 terminal cursor /
    position。

    :param context: 子进程上下文。
    :param database_path: 文件 SQLite 路径。
    :param run_id: Run id。
    :param attempt_id: 在 race 之前预置的 RUNNING attempt id。
    :param fencing_token: 同上 attempt 的 fencing token。
    :param owner_secret: 本子进程持有的 owner secret 明文。
    :param lease_expires_at_iso: ``host_attempts.lease_expires_at`` 的
        ISO 字符串; 仅用于构造 :class:`AttemptOwnerContext`。
    :param attempt_index: attempt 序号。
    :returns: 无返回值。
    :raises Exception: 内部异常由 :func:`report_error` 回报。
    """

    try:
        if context.barrier is not None:
            context.barrier.wait()
        storage = HostStorage(database_path=database_path)
        payload: dict[str, Any]
        try:
            clock = _SystemUtcClock()
            event_store = DurableRunEventStore(storage=storage)
            lease_store = AttemptLeaseStore(storage=storage, clock=clock)
            config = AttemptLeaseConfig(
                ttl=timedelta(seconds=_LEASE_TTL_SECONDS),
                renew_interval=timedelta(seconds=_LEASE_RENEW_INTERVAL_SECONDS),
                owner_id_prefix=_OWNER_PREFIX,
            )
            supervisor = AttemptSupervisor(
                storage=storage,
                lease_store=lease_store,
                lease_config=config,
                clock=clock,
                event_store=event_store,
            )
            owner_context = AttemptOwnerContext(
                attempt_id=attempt_id,
                run_id=run_id,
                attempt_index=attempt_index,
                owner_id=f"{_OWNER_PREFIX}:{context.name}",
                owner_token=AttemptOwnerToken(value=owner_secret),
                fencing_token=FencingToken(value=fencing_token),
                lease_expires_at=datetime.fromisoformat(lease_expires_at_iso),
            )
            appender = supervisor.scoped_appender(owner_context)
            try:
                link = asyncio.run(
                    appender.append_terminal_and_close(
                        draft=_final_draft(run_id=run_id, worker=context.name),
                        failure_summary=None,
                    )
                )
                payload = {
                    "fenced": False,
                    "fencing_token": fencing_token,
                    "event_position": link.event_position.value,
                    "sequence": link.event_cursor.sequence,
                    "terminal_state": link.terminal_state.value,
                }
            except AttemptFencingError as exc:
                payload = {
                    "fenced": True,
                    "reason": exc.reason.value,
                    "fencing_token": fencing_token,
                }
        finally:
            storage.close()
        report_success(context, payload=payload)
    except BaseException as exc:  # noqa: BLE001
        report_error(context, exc=exc)


def test_terminal_close_race_has_exactly_one_winner(
    tmp_path: Path,
) -> None:
    """两个进程同时 terminal close, 只有 owner secret 命中库中 hash 的胜出。"""

    database_path = temp_database_path(tmp_path)
    _bootstrap_database(database_path)
    (
        attempt_id,
        fencing_token,
        secret_a,
        lease_expires_at,
    ) = _create_running_attempt_synchronously(
        database_path=database_path, run_id=_RUN_ID
    )
    # 第二个 owner secret: 没有写入库 (库内仍是 secret_a 的 hash), 因此
    # 这个 owner 在 ``verify_owner`` 时一定 fenced (OWNER_MISMATCH)。
    secret_b = AttemptOwnerToken.new().value

    ctx = get_spawn_context()
    barrier = make_barrier(ctx, parties=2)
    specs = (
        WorkerSpec(
            name="closer-a",
            target=_worker_terminal_close,
            args=(
                database_path,
                _RUN_ID,
                attempt_id,
                fencing_token,
                secret_a,
                lease_expires_at.isoformat(),
                0,
            ),
        ),
        WorkerSpec(
            name="closer-b",
            target=_worker_terminal_close,
            args=(
                database_path,
                _RUN_ID,
                attempt_id,
                fencing_token,
                secret_b,
                lease_expires_at.isoformat(),
                0,
            ),
        ),
    )
    outcomes = run_workers(specs, barrier=barrier)
    assert_clean_exit(outcomes)

    winners = [o for o in outcomes if not o.result["fenced"]]
    losers = [o for o in outcomes if o.result["fenced"]]
    assert len(winners) == 1
    assert len(losers) == 1
    winner_payload = winners[0].result
    assert winner_payload["terminal_state"] == AttemptState.SUCCEEDED.value

    storage = HostStorage(database_path=database_path)
    try:
        attempt_rows = storage.execute_read(
            "SELECT state, terminal_event_position, fencing_token "
            "FROM host_attempts WHERE attempt_id = ?",
            (attempt_id,),
        )
        assert len(attempt_rows) == 1
        attempt_row = attempt_rows[0]
        assert attempt_row["state"] == AttemptState.SUCCEEDED.value
        assert (
            int(attempt_row["terminal_event_position"])
            == winner_payload["event_position"]
        )
        assert int(attempt_row["fencing_token"]) == fencing_token

        run_rows = storage.execute_read(
            "SELECT state, terminal_event_position FROM host_runs "
            "WHERE run_id = ?",
            (_RUN_ID,),
        )
        assert len(run_rows) == 1
        run_row = run_rows[0]
        assert run_row["state"] == ExtendedRunState.SUCCEEDED.value
        assert (
            int(run_row["terminal_event_position"])
            == winner_payload["event_position"]
        )

        terminal_rows = storage.execute_read(
            "SELECT type, event_position FROM host_run_events "
            "WHERE run_id = ? AND terminal = 1",
            (_RUN_ID,),
        )
        assert len(terminal_rows) == 1
        assert terminal_rows[0]["type"] == RunEventType.FINAL_ANSWER.value
        assert (
            int(terminal_rows[0]["event_position"])
            == winner_payload["event_position"]
        )
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# 场景 3: 跨进程 stale recovery
# ---------------------------------------------------------------------------


def _worker_acquire_and_exit(
    context: WorkerContext,
    database_path: str,
    run_id: str,
) -> None:
    """spawn 子进程: 进入 lease_context, 不写 terminal 直接退出。

    模拟进程 A 在持有 owner lease 时崩溃 / 退出, 留下 RUNNING 但无 owner
    存活的孤儿 attempt 行。回报 ``attempt_id`` / ``fencing_token`` /
    ``owner_secret`` / ``attempt_index`` 让主进程把 ``lease_expires_at``
    改成过去时刻, 让 recovery scan 能命中。

    :param context: 子进程上下文。
    :param database_path: 文件 SQLite 路径。
    :param run_id: Run id。
    :returns: 无返回值。
    :raises Exception: 内部异常由 :func:`report_error` 回报。
    """

    try:
        async def _acquire() -> dict[str, Any]:
            storage = HostStorage(database_path=database_path)
            try:
                clock = _SystemUtcClock()
                event_store = DurableRunEventStore(storage=storage)
                lease_store = AttemptLeaseStore(storage=storage, clock=clock)
                supervisor = AttemptSupervisor(
                    storage=storage,
                    lease_store=lease_store,
                    lease_config=DEFAULT_ATTEMPT_LEASE_CONFIG,
                    clock=clock,
                    event_store=event_store,
                )
                async with supervisor.lease_context(
                    run_id=run_id, attempt_index=0
                ) as owner:
                    captured = {
                        "attempt_id": owner.attempt_id,
                        "fencing_token": owner.fencing_token.value,
                        "owner_secret": owner.owner_token.value,
                        "attempt_index": owner.attempt_index,
                    }
                return captured
            finally:
                storage.close()

        payload = asyncio.run(_acquire())
        report_success(context, payload=payload)
    except BaseException as exc:  # noqa: BLE001
        report_error(context, exc=exc)


def _worker_recover(
    context: WorkerContext,
    database_path: str,
    run_id: str,
) -> None:
    """spawn 子进程: 调用 ``recover_stale_attempts`` 收口候选并回报。

    :param context: 子进程上下文。
    :param database_path: 文件 SQLite 路径。
    :param run_id: Run id。
    :returns: 无返回值。
    :raises Exception: 内部异常由 :func:`report_error` 回报。
    """

    try:
        async def _recover() -> list[dict[str, Any]]:
            storage = HostStorage(database_path=database_path)
            try:
                clock = _SystemUtcClock()
                event_store = DurableRunEventStore(storage=storage)
                lease_store = AttemptLeaseStore(storage=storage, clock=clock)
                supervisor = AttemptSupervisor(
                    storage=storage,
                    lease_store=lease_store,
                    lease_config=DEFAULT_ATTEMPT_LEASE_CONFIG,
                    clock=clock,
                    event_store=event_store,
                )
                decisions = await supervisor.recover_stale_attempts(
                    run_id=run_id
                )
                return [
                    {
                        "action": decision.action.value,
                        "source_attempt_id": decision.source_attempt_id,
                        "recovery_attempt_id": decision.recovery_attempt_id,
                        "recovery_attempt_index": (
                            decision.recovery_attempt_index
                        ),
                        "reason": decision.reason,
                    }
                    for decision in decisions
                ]
            finally:
                storage.close()

        payload = asyncio.run(_recover())
        report_success(context, payload=payload)
    except BaseException as exc:  # noqa: BLE001
        report_error(context, exc=exc)


def _expire_attempt_lease(
    *, database_path: str, attempt_id: str
) -> None:
    """主进程内把 ``lease_expires_at`` 改成过去时刻让 recovery scan 命中。

    采用 ``测试事务内直接 UPDATE`` 方式: 跨进程注入 fake clock 不可行
    (子进程 ``UtcClock`` 是各自实例), 所以 P8-S7 task brief 明确允许在
    测试事务内推进 ``lease_expires_at`` 字段。

    :param database_path: 文件 SQLite 路径。
    :param attempt_id: 待过期的 attempt id。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: 失败时透传。
    """

    async def _do() -> None:
        storage = HostStorage(database_path=database_path)
        try:
            past = (_utc() - timedelta(seconds=_LEASE_TTL_SECONDS * 4)).isoformat()
            async with storage.transaction() as tx:
                tx.execute(
                    "UPDATE host_attempts SET lease_expires_at = ? "
                    "WHERE attempt_id = ?",
                    (past, attempt_id),
                )
        finally:
            storage.close()

    asyncio.run(_do())


def test_cross_process_stale_recovery_preserves_typed_decision(
    tmp_path: Path,
) -> None:
    """进程 A 退出 + 主进程过期 lease + 进程 B recover, typed 决策正确落库。"""

    database_path = temp_database_path(tmp_path)
    _bootstrap_database(database_path)

    # 阶段 1: 进程 A 拿 lease 并退出, 留下 RUNNING 孤儿。
    acquire_outcomes = run_workers(
        (
            WorkerSpec(
                name="acquirer",
                target=_worker_acquire_and_exit,
                args=(database_path, _RUN_ID),
            ),
        )
    )
    assert_clean_exit(acquire_outcomes)
    captured = acquire_outcomes[0].result
    assert isinstance(captured, dict)
    old_attempt_id: str = captured["attempt_id"]
    old_fencing_token: int = captured["fencing_token"]
    old_owner_secret: str = captured["owner_secret"]
    old_attempt_index: int = captured["attempt_index"]

    # 阶段 2: 主进程把 lease 过期。
    _expire_attempt_lease(
        database_path=database_path, attempt_id=old_attempt_id
    )

    # 阶段 3: 进程 B 执行 recovery scan。
    recover_outcomes = run_workers(
        (
            WorkerSpec(
                name="recoverer",
                target=_worker_recover,
                args=(database_path, _RUN_ID),
            ),
        )
    )
    assert_clean_exit(recover_outcomes)
    decisions = recover_outcomes[0].result
    assert isinstance(decisions, list)
    assert len(decisions) == 1
    decision = decisions[0]
    assert (
        decision["action"]
        == "mark_recovering_and_create_attempt"
    )
    assert decision["source_attempt_id"] == old_attempt_id
    new_attempt_id = decision["recovery_attempt_id"]
    new_attempt_index = decision["recovery_attempt_index"]
    assert isinstance(new_attempt_id, str)
    assert new_attempt_index == old_attempt_index + 1
    assert decision["reason"] == "lease_expired_recovery_started"

    storage = HostStorage(database_path=database_path)
    try:
        rows = storage.execute_read(
            "SELECT attempt_id, attempt_index, state, fencing_token, "
            "recovered_from_attempt_id FROM host_attempts WHERE run_id = ? "
            "ORDER BY attempt_index ASC",
            (_RUN_ID,),
        )
        assert len(rows) == 2
        old_row, new_row = rows[0], rows[1]
        assert old_row["attempt_id"] == old_attempt_id
        assert old_row["state"] == AttemptState.RECOVERING.value
        assert new_row["attempt_id"] == new_attempt_id
        assert new_row["state"] == AttemptState.RUNNING.value
        assert new_row["recovered_from_attempt_id"] == old_attempt_id
        assert int(new_row["fencing_token"]) > old_fencing_token

        # recovery scan 不写 EventLog 诊断 RunEvent。
        event_rows = storage.execute_read(
            "SELECT COUNT(*) AS cnt FROM host_run_events WHERE run_id = ?",
            (_RUN_ID,),
        )
        assert int(event_rows[0]["cnt"]) == 0
    finally:
        storage.close()

    # 阶段 4: 旧 owner late append (主进程内构造) 必然 fenced。
    storage = HostStorage(database_path=database_path)
    try:
        clock = _SystemUtcClock()
        event_store = DurableRunEventStore(storage=storage)
        lease_store = AttemptLeaseStore(storage=storage, clock=clock)
        supervisor = AttemptSupervisor(
            storage=storage,
            lease_store=lease_store,
            lease_config=DEFAULT_ATTEMPT_LEASE_CONFIG,
            clock=clock,
            event_store=event_store,
        )
        old_owner = AttemptOwnerContext(
            attempt_id=old_attempt_id,
            run_id=_RUN_ID,
            attempt_index=old_attempt_index,
            owner_id=f"{_OWNER_PREFIX}:late",
            owner_token=AttemptOwnerToken(value=old_owner_secret),
            fencing_token=FencingToken(value=old_fencing_token),
            lease_expires_at=_utc() + timedelta(seconds=_LEASE_TTL_SECONDS),
        )
        appender = supervisor.scoped_appender(old_owner)

        async def _late_append() -> None:
            await appender.append(
                _content_draft(run_id=_RUN_ID, worker="late", idx=0)
            )

        with pytest.raises(AttemptFencingError):
            asyncio.run(_late_append())
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# 场景 4: observer drain / startup_reconcile
# ---------------------------------------------------------------------------


def _worker_write_terminal_no_drain(
    context: WorkerContext,
    database_path: str,
    run_id: str,
) -> None:
    """spawn 子进程: 写入 user input + delta + final answer 但 **不** drain。

    模拟进程 A 在 terminal 落库之后、`drain()` 执行之前崩溃: EventLog 含
    user input + final answer (含 RunResult snapshot), 但 memory /
    timeline / audit checkpoint 都未推进。

    :param context: 子进程上下文。
    :param database_path: 文件 SQLite 路径。
    :param run_id: Run id。
    :returns: 无返回值。
    :raises Exception: 内部异常由 :func:`report_error` 回报。
    """

    try:
        async def _do() -> dict[str, Any]:
            storage = HostStorage(database_path=database_path)
            try:
                store = DurableRunEventStore(storage=storage)
                user_draft = RunEventDraft(
                    run_id=run_id,
                    session_id=_SESSION_ID,
                    kind=RunEventKind.CANONICAL,
                    source=RunEventSource.HOST,
                    type=RunEventType.USER_INPUT_ACCEPTED,
                    occurred_at=_utc(),
                    data=UserInputAcceptedData(
                        turn_id=run_id,
                        content="hello",
                        scope=UserInputScope.SESSION,
                    ),
                    source_engine_event_id=None,
                )
                await store.append(user_draft)
                await store.append(
                    _content_draft(
                        run_id=run_id, worker=context.name, idx=0
                    )
                )
                terminal = await store.append(
                    _final_draft(run_id=run_id, worker=context.name)
                )
                return {
                    "terminal_sequence": terminal.cursor.sequence,
                }
            finally:
                storage.close()

        payload = asyncio.run(_do())
        report_success(context, payload=payload)
    except BaseException as exc:  # noqa: BLE001
        report_error(context, exc=exc)


def _worker_startup_reconcile(
    context: WorkerContext,
    database_path: str,
) -> None:
    """spawn 子进程: 用 ``build_durable_harness`` + ``coordinator.startup_reconcile`` 追平。

    构造 durable bundle 仅为驱动
    :meth:`ProjectionCoordinator.startup_reconcile`; 不会启动 LLM、不会
    消费用户输入, 也不读 ``ConversationMemoryStore`` 内部状态 (本 slice
    的 in-memory memory store 不具备生产级崩溃恢复, durable memory store
    见 P8-S8)。完成后回报每个 observer 的 ``last_success_position``, 让
    主进程断言 checkpoint 已对齐 EventLog tail。

    :param context: 子进程上下文。
    :param database_path: 文件 SQLite 路径。
    :returns: 无返回值。
    :raises Exception: 内部异常由 :func:`report_error` 回报。
    """

    try:
        async def _do() -> dict[str, Any]:
            bundle = build_durable_harness(
                config=DurableHarnessConfig(database_path=database_path),
            )
            try:
                # 第一次 reconcile: 把 checkpoint 推到 tail。
                first = await bundle.coordinator.startup_reconcile()
                # 第二次 reconcile: 必须幂等, 不再变更 last_success_position。
                second = await bundle.coordinator.startup_reconcile()
                return {
                    "first": [
                        {
                            "observer_id": cp.observer_id,
                            "last_success_position": (
                                None
                                if cp.last_success_position is None
                                else cp.last_success_position.value
                            ),
                            "status": cp.status.value,
                        }
                        for cp in first
                    ],
                    "second": [
                        {
                            "observer_id": cp.observer_id,
                            "last_success_position": (
                                None
                                if cp.last_success_position is None
                                else cp.last_success_position.value
                            ),
                            "status": cp.status.value,
                        }
                        for cp in second
                    ],
                }
            finally:
                bundle.close()

        payload = asyncio.run(_do())
        report_success(context, payload=payload)
    except BaseException as exc:  # noqa: BLE001
        report_error(context, exc=exc)


def test_observer_drain_catches_up_after_cross_process_terminal(
    tmp_path: Path,
) -> None:
    """terminal 落库 + 不 drain, 另起进程 startup_reconcile 追平且幂等。

    本测试 **仅** 验证多进程场景下 P8 既有 EventLog / projection
    checkpoint / ``ProjectionCoordinator.startup_reconcile`` 三者之间的
    "崩溃后重启可以把 checkpoint 追到 EventLog tail" 语义, 并断言再次
    调用 ``startup_reconcile`` 幂等不前进 checkpoint。

    本测试 **不** 声称、也不验证以下任何一项 (均归 P8-S8 scope):

    - in-memory ``ConversationMemoryStore`` 在进程崩溃后能从 EventLog
      重建用户消息 / Engine 内存语义;
    - durable ``ConversationMemoryStore`` 实现;
    - checkpoint-aware ``rebuild`` 与启动时回放策略。

    P8-S7 已确认: in-memory memory store 不具备生产级崩溃恢复; 测试只
    取得 ``host_projection_checkpoints`` 表的位点对齐事实, 不读取 / 不
    断言 memory store 内容。
    """

    database_path = temp_database_path(tmp_path)
    _bootstrap_database(database_path)

    write_outcomes = run_workers(
        (
            WorkerSpec(
                name="writer",
                target=_worker_write_terminal_no_drain,
                args=(database_path, _RUN_ID),
            ),
        )
    )
    assert_clean_exit(write_outcomes)

    # EventLog tail 的 global position; 子进程 startup_reconcile 应该把
    # 全部 observer 的 last_success_position 推到这里。
    storage = HostStorage(database_path=database_path)
    try:
        rows = storage.execute_read(
            "SELECT MAX(event_position) AS tail FROM host_run_events"
        )
        tail = int(rows[0]["tail"])
        assert tail >= 1
    finally:
        storage.close()

    reconcile_outcomes = run_workers(
        (
            WorkerSpec(
                name="reconciler",
                target=_worker_startup_reconcile,
                args=(database_path,),
            ),
        ),
        timeout_seconds=DEFAULT_JOIN_TIMEOUT_SECONDS,
    )
    assert_clean_exit(reconcile_outcomes)
    payload = reconcile_outcomes[0].result
    assert isinstance(payload, dict)
    first = payload["first"]
    second = payload["second"]
    assert isinstance(first, list)
    assert isinstance(second, list)

    expected_observer_ids = {
        "host_memory_projection",
        "host_timeline_projection",
        "host_audit_projection",
    }
    first_ids = {item["observer_id"] for item in first}
    assert expected_observer_ids.issubset(first_ids)
    for item in first:
        assert item["last_success_position"] == tail
        assert item["status"] == "caught_up"
    # 幂等: 第二次 reconcile 不再前进 checkpoint。
    first_by_id = {item["observer_id"]: item for item in first}
    second_by_id = {item["observer_id"]: item for item in second}
    for observer_id in expected_observer_ids:
        assert (
            first_by_id[observer_id]["last_success_position"]
            == second_by_id[observer_id]["last_success_position"]
        )
        assert second_by_id[observer_id]["status"] == "caught_up"

    # 主进程内额外断言: SQLite 内 checkpoint 与 worker 回报一致, 防止
    # 子进程序列化遗漏 / 误读。
    storage = HostStorage(database_path=database_path)
    try:
        cp_rows = storage.execute_read(
            "SELECT observer_id, last_success_position, status "
            "FROM host_projection_checkpoints"
        )
        positions = {
            row["observer_id"]: int(row["last_success_position"])
            for row in cp_rows
            if row["last_success_position"] is not None
        }
        for observer_id in expected_observer_ids:
            assert positions[observer_id] == tail
    finally:
        storage.close()
