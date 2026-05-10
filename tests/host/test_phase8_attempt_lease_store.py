"""Host P8-S1 Attempt lease store CAS 测试。

覆盖 :class:`AttemptLeaseStore` 的 acquire / renew / verify_owner 三个
CAS 入口，以及 :class:`AttemptOwnerToken` / :class:`AttemptLeaseConfig`
等强类型契约的关键边界。

P8-S1 不接入 :class:`LocalRunHarness` 主路径，本测试只覆盖 store 层。

fencing 真源是全局 :class:`FencingToken`（``host_fencing_tokens``
``INTEGER PRIMARY KEY AUTOINCREMENT``）：跨 attempt / 跨 run 严格单调
递增，允许 gap，禁止倒退或复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from dayu.host._attempt_lease import (
    ATTEMPT_OWNER_ID_PREFIX,
    DEFAULT_ATTEMPT_LEASE_CONFIG,
    AttemptFencingError,
    AttemptFencingReason,
    AttemptLeaseConfig,
    AttemptLeaseDecision,
    AttemptOwnerContext,
    AttemptOwnerToken,
)
from dayu.host._durable_event_store import open_durable_event_store
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import (
    AttemptState,
    ExtendedRunState,
    FencingToken,
)
from dayu.host._run_state_store import (
    AttemptLeaseStore,
    AttemptStateStore,
)


@dataclass(slots=True)
class _FakeClock:
    """可控 UTC clock，单元测试推进 lease 过期。"""

    current: datetime = field(
        default_factory=lambda: datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    )

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current = self.current + delta


def _open_storage() -> HostStorage:
    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    return storage


async def _seed_run(storage: HostStorage, *, run_id: str = "r1") -> None:
    async with storage.transaction() as tx:
        tx.execute(
            "INSERT INTO host_runs (run_id, session_id, state, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, "s", ExtendedRunState.RUNNING.value, "t", "t"),
        )


def _expires_at(clock: _FakeClock, *, ttl: timedelta = timedelta(seconds=30)) -> datetime:
    return clock.now() + ttl


def test_owner_token_digest_and_masked() -> None:
    """token 明文唯一映射到 digest；masked 不暴露明文核心。"""

    token = AttemptOwnerToken.new()
    assert len(token.value) == 64  # 32 bytes -> 64 hex chars
    assert token.digest() == AttemptOwnerToken(value=token.value).digest()
    assert token.masked().startswith("***")
    assert token.value not in token.masked()


def test_attempt_lease_config_validates() -> None:
    """非法配置必须立即报错，不允许通过装配层渗到 store。"""

    with pytest.raises(ValueError):
        AttemptLeaseConfig(
            ttl=timedelta(0),
            renew_interval=timedelta(seconds=1),
            owner_id_prefix="x",
        )
    with pytest.raises(ValueError):
        AttemptLeaseConfig(
            ttl=timedelta(seconds=10),
            renew_interval=timedelta(seconds=10),
            owner_id_prefix="x",
        )
    with pytest.raises(ValueError):
        AttemptLeaseConfig(
            ttl=timedelta(seconds=10),
            renew_interval=timedelta(seconds=1),
            owner_id_prefix="",
        )
    assert DEFAULT_ATTEMPT_LEASE_CONFIG.owner_id_prefix == ATTEMPT_OWNER_ID_PREFIX
    assert DEFAULT_ATTEMPT_LEASE_CONFIG.renew_interval < DEFAULT_ATTEMPT_LEASE_CONFIG.ttl


def test_fencing_token_rejects_non_positive() -> None:
    """``FencingToken`` 必须是正整数，0 / 负值不允许构造。"""

    with pytest.raises(ValueError):
        FencingToken(value=0)
    with pytest.raises(ValueError):
        FencingToken(value=-1)


@pytest.mark.asyncio
async def test_acquire_inserts_running_attempt_with_owner_lease() -> None:
    """acquire 成功必须落地 RUNNING + fencing_token + owner_token_hash。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    state_store = AttemptStateStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()
    expires = _expires_at(clock)

    async with storage.transaction() as tx:
        result = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token,
            lease_expires_at=expires,
        )

    assert result.decision is AttemptLeaseDecision.ACQUIRED
    assert result.owner_context is not None
    assert result.owner_context.fencing_token.value >= 1
    assert result.owner_context.lease_expires_at == expires
    assert result.current_fencing_token == result.owner_context.fencing_token

    record = state_store.get("a1")
    assert record is not None
    assert record.state is AttemptState.RUNNING
    assert record.owner_id == "host:1"
    assert record.owner_token_hash == token.digest()
    assert record.fencing_token == result.owner_context.fencing_token
    assert record.lease_expires_at == expires
    assert record.lease_renewed_at == clock.now()
    assert record.recovered_from_attempt_id is None
    token_rows = storage.execute_read(
        "SELECT resource_type, resource_id FROM host_fencing_tokens "
        "WHERE fencing_token = ?",
        (result.owner_context.fencing_token.value,),
    )
    assert len(token_rows) == 1
    assert token_rows[0]["resource_type"] == "attempt"
    assert token_rows[0]["resource_id"] == "a1"
    storage.close()


@pytest.mark.asyncio
async def test_acquire_returns_busy_on_attempt_index_conflict() -> None:
    """``UNIQUE(run_id, attempt_index)`` 冲突必须映射成 BUSY，不抛裸 SQLite。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token_a = AttemptOwnerToken.new()
    token_b = AttemptOwnerToken.new()
    expires = _expires_at(clock)

    async with storage.transaction() as tx:
        first = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token_a,
            lease_expires_at=expires,
        )
    assert first.decision is AttemptLeaseDecision.ACQUIRED
    assert first.owner_context is not None
    first_token = first.owner_context.fencing_token

    async with storage.transaction() as tx:
        second = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a2",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:2",
            owner_token=token_b,
            lease_expires_at=expires,
        )
    assert second.decision is AttemptLeaseDecision.BUSY
    assert second.current_state is AttemptState.RUNNING
    assert second.current_owner_id == "host:1"

    # 即使 BUSY 失败，下一次成功 acquire 必须取得严格更大的 token，
    # 不复用、不倒退。
    await _seed_run(storage, run_id="r2")
    async with storage.transaction() as tx:
        third = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a3",
            run_id="r2",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:3",
            owner_token=AttemptOwnerToken.new(),
            lease_expires_at=expires,
        )
    assert third.decision is AttemptLeaseDecision.ACQUIRED
    assert third.owner_context is not None
    assert third.owner_context.fencing_token.value > first_token.value
    storage.close()


@pytest.mark.asyncio
async def test_renew_extends_lease_without_changing_fencing_token() -> None:
    """合法 owner renew 只延长 lease_expires_at；fencing_token 不变。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    state_store = AttemptStateStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        result = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token,
            lease_expires_at=_expires_at(clock),
        )
    assert result.owner_context is not None
    owner_ctx = result.owner_context
    original_token = owner_ctx.fencing_token

    clock.advance(timedelta(seconds=5))
    new_expires = _expires_at(clock)
    async with storage.transaction() as tx:
        renewed = lease_store.renew(
            tx=tx,
            owner_context=owner_ctx,
            lease_expires_at=new_expires,
        )
    assert renewed.decision is AttemptLeaseDecision.ACQUIRED
    assert renewed.owner_context is not None
    assert renewed.owner_context.fencing_token == original_token
    assert renewed.owner_context.lease_expires_at == new_expires

    record = state_store.get("a1")
    assert record is not None
    assert record.lease_expires_at == new_expires
    assert record.lease_renewed_at == clock.now()
    assert record.fencing_token == original_token
    storage.close()


@pytest.mark.asyncio
async def test_renew_fenced_when_lease_expired() -> None:
    """lease 过期后 renew 必须返回 FENCED+LEASE_EXPIRED。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        acquired = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token,
            lease_expires_at=_expires_at(clock, ttl=timedelta(seconds=10)),
        )
    assert acquired.owner_context is not None

    clock.advance(timedelta(seconds=20))
    async with storage.transaction() as tx:
        result = lease_store.renew(
            tx=tx,
            owner_context=acquired.owner_context,
            lease_expires_at=_expires_at(clock),
        )
    assert result.decision is AttemptLeaseDecision.FENCED
    assert result.reason is AttemptFencingReason.LEASE_EXPIRED
    storage.close()


@pytest.mark.asyncio
async def test_renew_fenced_on_owner_mismatch() -> None:
    """另一个 owner 用错误 token renew 必须 FENCED+OWNER_MISMATCH。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        acquired = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token,
            lease_expires_at=_expires_at(clock),
        )
    assert acquired.owner_context is not None

    other_token = AttemptOwnerToken.new()
    spoofed = AttemptOwnerContext(
        attempt_id=acquired.owner_context.attempt_id,
        run_id=acquired.owner_context.run_id,
        attempt_index=acquired.owner_context.attempt_index,
        owner_id="host:other",
        owner_token=other_token,
        fencing_token=acquired.owner_context.fencing_token,
        lease_expires_at=acquired.owner_context.lease_expires_at,
    )

    async with storage.transaction() as tx:
        result = lease_store.renew(
            tx=tx,
            owner_context=spoofed,
            lease_expires_at=_expires_at(clock),
        )
    assert result.decision is AttemptLeaseDecision.FENCED
    assert result.reason is AttemptFencingReason.OWNER_MISMATCH
    storage.close()


@pytest.mark.asyncio
async def test_renew_fenced_on_fencing_token_mismatch() -> None:
    """fencing_token 不一致必须 FENCED+FENCING_TOKEN_MISMATCH。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        acquired = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token,
            lease_expires_at=_expires_at(clock),
        )
    assert acquired.owner_context is not None

    bumped = AttemptOwnerContext(
        attempt_id=acquired.owner_context.attempt_id,
        run_id=acquired.owner_context.run_id,
        attempt_index=acquired.owner_context.attempt_index,
        owner_id=acquired.owner_context.owner_id,
        owner_token=acquired.owner_context.owner_token,
        fencing_token=FencingToken(
            value=acquired.owner_context.fencing_token.value + 1
        ),
        lease_expires_at=acquired.owner_context.lease_expires_at,
    )
    async with storage.transaction() as tx:
        result = lease_store.renew(
            tx=tx,
            owner_context=bumped,
            lease_expires_at=_expires_at(clock),
        )
    assert result.decision is AttemptLeaseDecision.FENCED
    assert result.reason is AttemptFencingReason.FENCING_TOKEN_MISMATCH
    storage.close()


@pytest.mark.asyncio
async def test_renew_terminal_when_attempt_terminal_state() -> None:
    """旧 owner 在 attempt terminal 后 renew 必须 TERMINAL+ATTEMPT_TERMINAL。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    state_store = AttemptStateStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        acquired = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token,
            lease_expires_at=_expires_at(clock),
        )
    assert acquired.owner_context is not None

    async with storage.transaction() as tx:
        state_store.update_state(
            tx=tx,
            attempt_id="a1",
            state=AttemptState.SUCCEEDED,
        )

    async with storage.transaction() as tx:
        result = lease_store.renew(
            tx=tx,
            owner_context=acquired.owner_context,
            lease_expires_at=_expires_at(clock),
        )
    assert result.decision is AttemptLeaseDecision.TERMINAL
    assert result.reason is AttemptFencingReason.ATTEMPT_TERMINAL
    assert result.current_state is AttemptState.SUCCEEDED
    storage.close()


@pytest.mark.asyncio
async def test_verify_owner_passes_for_valid_lease() -> None:
    """合法 owner 通过 verify_owner，不抛异常。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        result = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token,
            lease_expires_at=_expires_at(clock),
        )
    assert result.owner_context is not None

    async with storage.transaction() as tx:
        lease_store.verify_owner(tx=tx, owner_context=result.owner_context)
    storage.close()


@pytest.mark.asyncio
async def test_verify_owner_raises_typed_fencing_when_expired() -> None:
    """lease 过期后 verify_owner 抛 typed AttemptFencingError。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        result = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token,
            lease_expires_at=_expires_at(clock, ttl=timedelta(seconds=10)),
        )
    assert result.owner_context is not None
    expected_token = result.owner_context.fencing_token
    clock.advance(timedelta(seconds=20))

    async with storage.transaction() as tx:
        with pytest.raises(AttemptFencingError) as excinfo:
            lease_store.verify_owner(tx=tx, owner_context=result.owner_context)
    err = excinfo.value
    assert err.reason is AttemptFencingReason.LEASE_EXPIRED
    assert err.attempt_id == "a1"
    assert err.fencing_token == expected_token
    assert token.value not in str(err)
    storage.close()


@pytest.mark.asyncio
async def test_verify_owner_raises_owner_missing_for_unknown_attempt() -> None:
    """库内不存在该 attempt 行时 verify_owner 抛 OWNER_MISSING。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    ghost = AttemptOwnerContext(
        attempt_id="missing",
        run_id="r1",
        attempt_index=0,
        owner_id="host:ghost",
        owner_token=token,
        fencing_token=FencingToken(value=1),
        lease_expires_at=_expires_at(clock),
    )
    async with storage.transaction() as tx:
        with pytest.raises(AttemptFencingError) as excinfo:
            lease_store.verify_owner(tx=tx, owner_context=ghost)
    assert excinfo.value.reason is AttemptFencingReason.OWNER_MISSING
    storage.close()


@pytest.mark.asyncio
async def test_acquire_records_recovered_from_attempt_id() -> None:
    """recovery attempt 路径必须落地 recovered_from_attempt_id 并分配新 token。"""

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    state_store = AttemptStateStore(storage=storage, clock=clock)
    token_a = AttemptOwnerToken.new()
    token_b = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        first = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token_a,
            lease_expires_at=_expires_at(clock),
        )
    assert first.owner_context is not None
    first_token = first.owner_context.fencing_token

    async with storage.transaction() as tx:
        result = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a2",
            run_id="r1",
            attempt_index=1,
            recovered_from_attempt_id="a1",
            owner_id="host:2",
            owner_token=token_b,
            lease_expires_at=_expires_at(clock),
        )
    assert result.decision is AttemptLeaseDecision.ACQUIRED
    assert result.owner_context is not None
    assert result.owner_context.fencing_token.value > first_token.value

    record = state_store.get("a2")
    assert record is not None
    assert record.recovered_from_attempt_id == "a1"
    assert record.owner_token_hash == token_b.digest()
    assert record.fencing_token == result.owner_context.fencing_token
    storage.close()


@pytest.mark.asyncio
async def test_fencing_token_strictly_monotonic_across_runs() -> None:
    """fencing token 跨 attempt / 跨 run 全局严格单调递增。"""

    storage = _open_storage()
    await _seed_run(storage, run_id="r1")
    await _seed_run(storage, run_id="r2")
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)

    issued: list[int] = []
    for idx, (run_id, attempt_id) in enumerate(
        [("r1", "a1"), ("r2", "b1"), ("r1", "a2"), ("r2", "b2")]
    ):
        attempt_index = 0 if attempt_id in {"a1", "b1"} else 1
        async with storage.transaction() as tx:
            res = lease_store.acquire_new_attempt(
                tx=tx,
                attempt_id=attempt_id,
                run_id=run_id,
                attempt_index=attempt_index,
                recovered_from_attempt_id=None,
                owner_id=f"host:{idx}",
                owner_token=AttemptOwnerToken.new(),
                lease_expires_at=_expires_at(clock),
            )
        assert res.owner_context is not None
        issued.append(res.owner_context.fencing_token.value)

    assert issued == sorted(issued)
    assert len(set(issued)) == len(issued)  # 不复用
    for prev, nxt in zip(issued, issued[1:]):
        assert nxt > prev
    storage.close()


def test_acquire_rejects_naive_lease_expires_at() -> None:
    """``lease_expires_at`` 必须 timezone-aware；naive 时 store 拒绝。"""

    storage = _open_storage()
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token = AttemptOwnerToken.new()

    async def _go() -> None:
        await _seed_run(storage)
        async with storage.transaction() as tx:
            with pytest.raises(ValueError):
                lease_store.acquire_new_attempt(
                    tx=tx,
                    attempt_id="a1",
                    run_id="r1",
                    attempt_index=0,
                    recovered_from_attempt_id=None,
                    owner_id="host:1",
                    owner_token=token,
                    lease_expires_at=datetime(2026, 5, 9, 12, 0, 30),
                )

    import asyncio

    asyncio.run(_go())
    storage.close()


@pytest.mark.asyncio
async def test_allocate_fencing_token_fail_fast_when_lastrowid_invalid() -> None:
    """``host_fencing_tokens`` INSERT 未拿到正 ``lastrowid`` 时必须 fail-fast。

    SQLite ``INTEGER PRIMARY KEY AUTOINCREMENT`` 在正常路径下保证严格单调
    递增的 ``lastrowid``; 一旦缺失或非正, 表示 fencing 单调递增不变量被
    破坏, 必须立即抛 :class:`RuntimeError`, 禁止退化为 ``FencingToken(0)``
    / 静默继续这种"局部止血"。
    """

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)

    @dataclass(slots=True)
    class _NullLastRowidCursor:
        """``lastrowid`` 缺失的 cursor stub。"""

        lastrowid: int | None = None

    @dataclass(slots=True)
    class _StubTx:
        """只暴露 ``execute`` 的 tx stub, 始终返回 ``lastrowid=None``。"""

        captured_sql: list[str] = field(default_factory=list)

        def execute(
            self, sql: str, params: object = ()
        ) -> _NullLastRowidCursor:
            del params
            self.captured_sql.append(sql)
            return _NullLastRowidCursor()

    stub = _StubTx()
    with pytest.raises(RuntimeError, match="fencing token monotonic"):
        lease_store._allocate_fencing_token(  # type: ignore[arg-type]
            tx=stub,  # type: ignore[arg-type]
            resource_id="a-fail",
            owner_id="host:1",
            now=clock.now(),
        )
    assert any("host_fencing_tokens" in sql for sql in stub.captured_sql)
    storage.close()


@pytest.mark.asyncio
async def test_acquire_new_attempt_busy_when_attempt_index_unique_violation() -> None:
    """F4: ``UNIQUE(run_id, attempt_index)`` 冲突仍映射为 BUSY。

    第二次 acquire 复用同一 ``(run_id, attempt_index)``, store 应返回
    ``decision=BUSY`` 而不是抛 IntegrityError; 业务级 BUSY 路径必须保留。
    """

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token_a = AttemptOwnerToken.new()
    token_b = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        first = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a1",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token_a,
            lease_expires_at=_expires_at(clock),
        )
    assert first.decision is AttemptLeaseDecision.ACQUIRED

    async with storage.transaction() as tx:
        second = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="a2",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:2",
            owner_token=token_b,
            lease_expires_at=_expires_at(clock),
        )
    assert second.decision is AttemptLeaseDecision.BUSY
    storage.close()


@pytest.mark.asyncio
async def test_acquire_new_attempt_propagates_other_integrity_errors() -> None:
    """F4: 非 ``(run_id, attempt_index)`` 的 IntegrityError 不能伪装成 BUSY。

    通过 PRIMARY KEY ``attempt_id`` 碰撞触发 IntegrityError: 第一次 acquire
    成功写入 ``a1``, 第二次以新 ``attempt_index`` 但相同 ``attempt_id`` 再
    次 acquire, 应直接透传 IntegrityError, 不被 ``_is_attempt_index_unique_violation``
    误判为 BUSY。
    """

    import sqlite3 as _sqlite3

    storage = _open_storage()
    await _seed_run(storage)
    clock = _FakeClock()
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    token_a = AttemptOwnerToken.new()
    token_b = AttemptOwnerToken.new()

    async with storage.transaction() as tx:
        first = lease_store.acquire_new_attempt(
            tx=tx,
            attempt_id="dup-pk",
            run_id="r1",
            attempt_index=0,
            recovered_from_attempt_id=None,
            owner_id="host:1",
            owner_token=token_a,
            lease_expires_at=_expires_at(clock),
        )
    assert first.decision is AttemptLeaseDecision.ACQUIRED

    with pytest.raises(_sqlite3.IntegrityError):
        async with storage.transaction() as tx:
            lease_store.acquire_new_attempt(
                tx=tx,
                attempt_id="dup-pk",
                run_id="r1",
                attempt_index=1,
                recovered_from_attempt_id=None,
                owner_id="host:2",
                owner_token=token_b,
                lease_expires_at=_expires_at(clock),
            )
    storage.close()
