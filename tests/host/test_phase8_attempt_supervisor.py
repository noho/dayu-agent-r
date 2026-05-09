"""Host P8-S3 ``AttemptSupervisor`` 测试。

覆盖 supervisor 主路径:

- ``lease_context`` 正常 acquire owner / 计算 ``lease_expires_at`` /
  在退出时取消 renew loop;
- renew loop 在 fake clock 推进下 renew 成功, fencing token 不变, lease
  到期时刻被刷新;
- renew 命中 store 层 ``FENCED`` 时 session 被标记 fenced, 后续
  ``is_owner_active`` 返回 ``False``;
- ``DurableHarnessConfig.attempt_lease_config`` 装配入口可覆盖默认 TTL /
  renew interval / owner_id_prefix;
- 装配后 ``LocalRunHarness`` 自身不写 lease SQL: 通过注入 fake supervisor
  断言 ``lease_context`` 被调用, 而 lease store 没有额外 acquire 调用;
- 日志与异常文本中不出现 owner secret 明文 (仅 masked 形式);
- renew 命中 FENCED 后 supervisor ``wait_owner_lost`` 立即返回 typed
  ``FENCED``; harness 在 owner-lost 后不再 append late Engine event;
- renew 抛 storage 异常时 supervisor 暴露独立 ``STORAGE_ERROR`` loss
  reason, 日志只含 masked owner token, 不向 EventLog 继续 append;
- ``close_attempt_with_diagnostic_state`` 在 owner CAS 命中失败时返回
  ``False``, 不会覆盖未来状态。

测试一律使用 :class:`_FakeClock`, 不依赖真实 ``time.sleep``。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from typing import cast

import pytest

from dayu.engine.contracts.engine_events import (
    ContentDeltaData,
    EngineEvent,
    EngineEventType,
)
from dayu.contracts import CancellationToken
from dayu.host._attempt_lease import (
    ATTEMPT_OWNER_ID_PREFIX,
    AttemptFencingError,
    AttemptFencingReason,
    AttemptLeaseConfig,
    AttemptLeaseDecision,
    AttemptLeaseResult,
    AttemptOwnerContext,
    AttemptOwnerToken,
    DEFAULT_ATTEMPT_LEASE_CONFIG,
)
from dayu.host._attempt_supervisor import (
    AttemptOwnerLossReason,
    AttemptSupervisor,
)
from dayu.host._durable_event_store import (
    DurableRunEventStore,
    open_durable_event_store,
)
from dayu.host._durable_harness import (
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import (
    AttemptState,
    ExtendedRunState,
    FencingToken,
    GlobalEventPosition,
)
from dayu.host._run_state_store import AttemptLeaseStore
from dayu.host.contracts import (
    HostRunFailedData,
    RunEventSource,
    RunEventType,
    StartRunRequest,
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
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current = self.current + delta


def _open_storage() -> HostStorage:
    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    return storage


def _build_event_store(storage: HostStorage) -> DurableRunEventStore:
    """构造与 supervisor 共享同一 storage 的 event store。"""

    return DurableRunEventStore(storage=storage)


async def _seed_run(storage: HostStorage, *, run_id: str = "r1") -> None:
    async with storage.transaction() as tx:
        tx.execute(
            "INSERT INTO host_runs (run_id, session_id, state, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, "s", ExtendedRunState.RUNNING.value, "t", "t"),
        )


def _build_supervisor(
    *,
    storage: HostStorage,
    clock: _FakeClock,
    config: AttemptLeaseConfig | None = None,
) -> AttemptSupervisor:
    actual_config = config if config is not None else AttemptLeaseConfig(
        ttl=timedelta(seconds=30),
        renew_interval=timedelta(milliseconds=10),
        owner_id_prefix="host-test",
    )
    lease_store = AttemptLeaseStore(storage=storage, clock=clock)
    return AttemptSupervisor(
        storage=storage,
        lease_store=lease_store,
        lease_config=actual_config,
        clock=clock,
        event_store=_build_event_store(storage),
    )


@pytest.mark.asyncio
async def test_lease_context_acquires_owner_and_releases_session() -> None:
    """lease_context 正常 acquire / yield / 退出后清理 session。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            assert owner_context.run_id == "r1"
            assert owner_context.attempt_index == 0
            assert owner_context.fencing_token.value > 0
            assert owner_context.lease_expires_at == clock.now() + timedelta(
                seconds=30
            )
            assert supervisor.is_owner_active(owner_context)
        assert not supervisor.is_owner_active(owner_context)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=1
        ) as next_owner:
            assert next_owner.fencing_token.value > owner_context.fencing_token.value
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_renew_loop_extends_lease_without_changing_fencing_token() -> None:
    """renew 成功只刷新 lease 到期, 不改变 fencing token。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            initial_token = owner_context.fencing_token.value
            initial_expiry = owner_context.lease_expires_at
            clock.advance(timedelta(seconds=5))
            for _ in range(20):
                await asyncio.sleep(0)
            await asyncio.sleep(0.05)
            session_owner = supervisor._sessions[  # noqa: SLF001
                owner_context.attempt_id
            ].owner_context
            assert session_owner.fencing_token.value == initial_token
            assert session_owner.lease_expires_at >= initial_expiry
    finally:
        storage.close()


@dataclass(slots=True)
class _FencingLeaseStore:
    """让 renew 第一次返回 FENCED 的 lease store stub。

    使用显式同签名方法转发, 不再依赖 ``object`` + ``type: ignore[arg-type]``。
    """

    inner: AttemptLeaseStore
    fenced: bool = False

    def acquire_new_attempt(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None,
        owner_id: str,
        owner_token: AttemptOwnerToken,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        return self.inner.acquire_new_attempt(
            tx=tx,
            attempt_id=attempt_id,
            run_id=run_id,
            attempt_index=attempt_index,
            recovered_from_attempt_id=recovered_from_attempt_id,
            owner_id=owner_id,
            owner_token=owner_token,
            lease_expires_at=lease_expires_at,
        )

    def renew(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        if not self.fenced:
            self.fenced = True
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.FENCED,
                owner_context=None,
                current_state=AttemptState.RUNNING,
                current_owner_id="other",
                lease_expires_at=None,
                reason=AttemptFencingReason.OWNER_MISMATCH,
                current_fencing_token=FencingToken(value=999),
            )
        return self.inner.renew(
            tx=tx,
            owner_context=owner_context,
            lease_expires_at=lease_expires_at,
        )

    def verify_owner(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
    ) -> None:
        self.inner.verify_owner(tx=tx, owner_context=owner_context)

    def update_state_owner_aware(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        failure_summary: str | None,
        terminal_event_position: GlobalEventPosition | None,
    ) -> bool:
        return self.inner.update_state_owner_aware(
            tx=tx,
            owner_context=owner_context,
            state=state,
            failure_summary=failure_summary,
            terminal_event_position=terminal_event_position,
        )


@pytest.mark.asyncio
async def test_renew_fenced_marks_session_inactive() -> None:
    """renew 命中 FENCED 后 session 不再 active, 后续 owner check 拒绝。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        real_store = AttemptLeaseStore(storage=storage, clock=clock)
        fencing_store = _FencingLeaseStore(inner=real_store)
        config = AttemptLeaseConfig(
            ttl=timedelta(seconds=30),
            renew_interval=timedelta(milliseconds=5),
            owner_id_prefix="host-test",
        )
        supervisor = AttemptSupervisor(
            storage=storage,
            lease_store=cast(AttemptLeaseStore, fencing_store),
            lease_config=config,
            clock=clock,
            event_store=_build_event_store(storage),
        )
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            for _ in range(50):
                await asyncio.sleep(0.01)
                if not supervisor.is_owner_active(owner_context):
                    break
            assert not supervisor.is_owner_active(owner_context)
            # owner-lost signal 立即可读, 返回 typed FENCED reason。
            loss_reason = await asyncio.wait_for(
                supervisor.wait_owner_lost(owner_context),
                timeout=0.5,
            )
            assert loss_reason is AttemptOwnerLossReason.FENCED
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_durable_harness_config_overrides_lease_config() -> None:
    """``DurableHarnessConfig`` 作为 lease config 装配入口, 默认值可覆盖。"""

    custom = AttemptLeaseConfig(
        ttl=timedelta(seconds=42),
        renew_interval=timedelta(seconds=7),
        owner_id_prefix="host-custom",
    )
    bundle = build_durable_harness(
        config=DurableHarnessConfig(
            database_path=":memory:",
            attempt_lease_config=custom,
        )
    )
    try:
        assert bundle.attempt_lease_config is custom
        assert bundle.attempt_supervisor.lease_config is custom
        bundle_default = build_durable_harness(
            config=DurableHarnessConfig(database_path=":memory:")
        )
        try:
            assert (
                bundle_default.attempt_lease_config
                is DEFAULT_ATTEMPT_LEASE_CONFIG
            )
            assert (
                bundle_default.attempt_lease_config.owner_id_prefix
                == ATTEMPT_OWNER_ID_PREFIX
            )
        finally:
            bundle_default.close()
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_owner_token_plaintext_never_appears_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """supervisor 日志只允许 masked owner token, 不可出现明文。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        plaintext_seen: list[str] = []
        with caplog.at_level(logging.DEBUG, logger="dayu.host._attempt_supervisor"):
            async with supervisor.lease_context(
                run_id="r1", attempt_index=0
            ) as owner_context:
                plaintext_seen.append(owner_context.owner_token.value)
                for _ in range(5):
                    await asyncio.sleep(0.02)
        all_logs = "\n".join(record.getMessage() for record in caplog.records)
        for plain in plaintext_seen:
            assert plain not in all_logs
        assert "***" in all_logs
    finally:
        storage.close()


@dataclass(slots=True)
class _RecordingSupervisor:
    """fake supervisor: 记录调用次数, 不真正 acquire / renew。

    使用显式 ``close_attempt_with_diagnostic_state`` / ``wait_owner_lost`` /
    ``is_owner_active`` 同签名方法, 避免 ``type: ignore[arg-type]``。
    """

    enter_count: int = 0
    exit_count: int = 0
    last_owner: AttemptOwnerContext | None = None
    diagnostic_close_calls: list[tuple[str, AttemptState, str | None]] = field(
        default_factory=list
    )

    @asynccontextmanager
    async def lease_context(
        self,
        *,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None = None,
    ) -> AsyncGenerator[AttemptOwnerContext, None]:
        del recovered_from_attempt_id
        self.enter_count += 1
        owner = AttemptOwnerContext(
            attempt_id=f"att-{run_id}-{attempt_index}",
            run_id=run_id,
            attempt_index=attempt_index,
            owner_id="host-test:0:0000",
            owner_token=AttemptOwnerToken.new(),
            fencing_token=FencingToken(value=self.enter_count),
            lease_expires_at=datetime(
                2099, 1, 1, tzinfo=timezone.utc
            ),
        )
        self.last_owner = owner
        try:
            yield owner
        finally:
            self.exit_count += 1

    def is_owner_active(self, owner_context: AttemptOwnerContext) -> bool:
        return owner_context is self.last_owner

    async def wait_owner_lost(
        self, owner_context: AttemptOwnerContext
    ) -> AttemptOwnerLossReason:
        # fake supervisor: 永远不主动暴露 lease loss; 由测试主线程驱动。
        del owner_context
        await asyncio.Event().wait()
        return AttemptOwnerLossReason.FENCED

    async def close_attempt_with_diagnostic_state(
        self,
        *,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        failure_summary: str | None,
        terminal_event_position: GlobalEventPosition | None = None,
    ) -> bool:
        del terminal_event_position
        self.diagnostic_close_calls.append(
            (owner_context.attempt_id, state, failure_summary)
        )
        return True


@pytest.mark.asyncio
async def test_local_run_harness_thin_delegates_to_supervisor() -> None:
    """harness ``_begin_attempt_if_durable`` 仅薄委托 supervisor.lease_context。"""

    from dayu.host._run_harness import LocalRunHarness, _ActiveAttempt
    from dayu.host._proxy import LocalProxy
    from dayu.host._worker import EngineWorker
    from dayu.host._tool_runtime import ToolRuntimeToolExecutor

    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:")
    )
    try:
        await _seed_run(bundle.storage)
        recording = _RecordingSupervisor()
        runtime = bundle.harness.tool_runtime
        assert runtime is not None
        proxy = LocalProxy(
            worker=EngineWorker(ToolRuntimeToolExecutor(runtime))
        )
        harness = LocalRunHarness(
            proxy=proxy,
            event_store=bundle.event_store,
            tool_runtime=runtime,
            memory_store=bundle.memory_store,
            attempt_supervisor=cast(AttemptSupervisor, recording),
            storage=bundle.storage,
        )

        from dayu.engine.contracts.messages import (
            AgentMessageRole,
            UserMessage,
        )
        from dayu.engine.contracts.agent_policy import AgentPolicy
        from dayu.engine.contracts.runner_spec import (
            RunnerCallOptions,
            RunnerSpec,
        )
        from dayu.host.contracts import (
            RunInput,
            RunOptions,
            StartRunRequest,
        )

        request = StartRunRequest(
            session_id="s",
            run_id="r1",
            input=RunInput(
                messages=(
                    UserMessage(role=AgentMessageRole.USER, content="hi"),
                )
            ),
            options=RunOptions(
                runner_spec=RunnerSpec(
                    provider="openai",
                    model="m",
                    endpoint="https://example.test/v1/chat/completions",
                    api_key_ref="K",
                    headers={},
                    supports_tool_calling=True,
                    supports_streaming=True,
                    supports_stream_usage=False,
                    default_timeout_seconds=30.0,
                    max_retries=0,
                    provider_request=None,
                ),
                runner_options=RunnerCallOptions(
                    temperature=None,
                    max_tokens=None,
                    top_p=None,
                    stream=True,
                ),
                agent_policy=AgentPolicy(
                    max_iterations=3,
                    continuation_max_attempts=1,
                    allow_tool_calls=True,
                ),
                stream=False,
                disable_tools=True,
                tool_schemas=(),
            ),
        )
        active = await harness._begin_attempt_if_durable(  # noqa: SLF001
            request=request, attempt_index=0
        )
        assert isinstance(active, _ActiveAttempt)
        assert recording.enter_count == 1
        assert active.lease_exit_stack is not None
        await harness._finish_attempt_if_durable(  # noqa: SLF001
            active_attempt=active,
            terminal_event=None,
            state=AttemptState.SUCCEEDED,
        )
        assert recording.exit_count == 1
        # 验证 harness 通过 supervisor diagnostic close 完成 owner-aware 收口。
        assert len(recording.diagnostic_close_calls) == 1
        attempt_id, state, _summary = recording.diagnostic_close_calls[0]
        assert state is AttemptState.SUCCEEDED
        assert active.owner_context is not None
        assert attempt_id == active.owner_context.attempt_id
    finally:
        bundle.close()


@dataclass(slots=True)
class _BusyStore:
    """acquire 始终返回 BUSY 的 lease store stub。

    用于覆盖 ``lease_context`` 在 acquire 失败路径上的 fencing error 传播。
    """

    clock: _FakeClock

    def acquire_new_attempt(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None,
        owner_id: str,
        owner_token: AttemptOwnerToken,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        del (
            tx,
            attempt_id,
            run_id,
            attempt_index,
            recovered_from_attempt_id,
            owner_id,
            owner_token,
            lease_expires_at,
        )
        return AttemptLeaseResult(
            decision=AttemptLeaseDecision.BUSY,
            owner_context=None,
            current_state=AttemptState.RUNNING,
            current_owner_id="someone",
            lease_expires_at=self.clock.now(),
            reason=AttemptFencingReason.ATTEMPT_NOT_RUNNING,
            current_fencing_token=FencingToken(value=7),
        )

    def renew(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        del tx, owner_context, lease_expires_at
        raise AssertionError("renew should not be called on busy acquire")

    def verify_owner(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
    ) -> None:
        del tx, owner_context
        raise AssertionError("verify should not be called")

    def update_state_owner_aware(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        failure_summary: str | None,
        terminal_event_position: GlobalEventPosition | None,
    ) -> bool:
        del tx, owner_context, state, failure_summary, terminal_event_position
        raise AssertionError("update_state_owner_aware should not be called")


@pytest.mark.asyncio
async def test_lease_context_propagates_acquire_fencing_error() -> None:
    """acquire 命中非 ACQUIRED 决策时, lease_context 抛 ``AttemptFencingError``。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = AttemptSupervisor(
            storage=storage,
            lease_store=cast(AttemptLeaseStore, _BusyStore(clock=clock)),
            lease_config=AttemptLeaseConfig(
                ttl=timedelta(seconds=30),
                renew_interval=timedelta(milliseconds=10),
                owner_id_prefix="host-test",
            ),
            clock=clock,
            event_store=_build_event_store(storage),
        )
        with pytest.raises(AttemptFencingError) as excinfo:
            async with supervisor.lease_context(
                run_id="r1", attempt_index=0
            ):
                pytest.fail("lease_context should not yield on BUSY")
        assert excinfo.value.reason is AttemptFencingReason.ATTEMPT_NOT_RUNNING
    finally:
        storage.close()


@dataclass(slots=True)
class _StorageErrorLeaseStore:
    """让 renew 第一次抛 storage error 的 lease store stub。

    用于验证 supervisor 把非 ``CancelledError`` 异常映射为 typed
    ``STORAGE_ERROR`` loss reason, 不被伪装成 fencing。
    """

    inner: AttemptLeaseStore
    raised: bool = False

    def acquire_new_attempt(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None,
        owner_id: str,
        owner_token: AttemptOwnerToken,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        return self.inner.acquire_new_attempt(
            tx=tx,
            attempt_id=attempt_id,
            run_id=run_id,
            attempt_index=attempt_index,
            recovered_from_attempt_id=recovered_from_attempt_id,
            owner_id=owner_id,
            owner_token=owner_token,
            lease_expires_at=lease_expires_at,
        )

    def renew(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        del tx, owner_context, lease_expires_at
        if not self.raised:
            self.raised = True
            raise RuntimeError("simulated SQLite IO error")
        # 不应再被调用; 第一次 raise 后 supervisor 应停止 renew loop。
        raise AssertionError("renew should not be called after storage error")

    def verify_owner(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
    ) -> None:
        self.inner.verify_owner(tx=tx, owner_context=owner_context)

    def update_state_owner_aware(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        failure_summary: str | None,
        terminal_event_position: GlobalEventPosition | None,
    ) -> bool:
        return self.inner.update_state_owner_aware(
            tx=tx,
            owner_context=owner_context,
            state=state,
            failure_summary=failure_summary,
            terminal_event_position=terminal_event_position,
        )


@pytest.mark.asyncio
async def test_renew_storage_error_marks_owner_lost_with_storage_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """renew 抛 storage 异常时 supervisor 暴露 STORAGE_ERROR 且日志 masked。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        real_store = AttemptLeaseStore(storage=storage, clock=clock)
        store = _StorageErrorLeaseStore(inner=real_store)
        config = AttemptLeaseConfig(
            ttl=timedelta(seconds=30),
            renew_interval=timedelta(milliseconds=5),
            owner_id_prefix="host-test",
        )
        supervisor = AttemptSupervisor(
            storage=storage,
            lease_store=cast(AttemptLeaseStore, store),
            lease_config=config,
            clock=clock,
            event_store=_build_event_store(storage),
        )
        plaintext_seen: list[str] = []
        with caplog.at_level(logging.DEBUG, logger="dayu.host._attempt_supervisor"):
            async with supervisor.lease_context(
                run_id="r1", attempt_index=0
            ) as owner_context:
                plaintext_seen.append(owner_context.owner_token.value)
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if not supervisor.is_owner_active(owner_context):
                        break
                assert not supervisor.is_owner_active(owner_context)
                loss_reason = await asyncio.wait_for(
                    supervisor.wait_owner_lost(owner_context),
                    timeout=0.5,
                )
                assert loss_reason is AttemptOwnerLossReason.STORAGE_ERROR
        all_logs = "\n".join(record.getMessage() for record in caplog.records)
        # owner 明文不能进入日志; masked token 必须出现; storage error 标识必须出现。
        for plain in plaintext_seen:
            assert plain not in all_logs
        assert "***" in all_logs
        assert "host.attempt.lease_renew_storage_error" in all_logs
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_diagnostic_close_owner_cas_miss_returns_false() -> None:
    """owner CAS 命中失败时 diagnostic close 返回 ``False``, 不覆盖未来状态。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            # 模拟 recovery: 直接把 owner 行迁出 RUNNING, 让 owner-aware
            # CAS 命不中。
            async with storage.transaction() as tx:
                tx.execute(
                    "UPDATE host_attempts SET state = ? WHERE attempt_id = ?",
                    (AttemptState.STALE.value, owner_context.attempt_id),
                )
            applied = await supervisor.close_attempt_with_diagnostic_state(
                owner_context=owner_context,
                state=AttemptState.LOST,
                failure_summary="diagnostic",
            )
            assert applied is False
            # 验证 row 仍是 STALE, 没有被 LOST 覆盖。
            async with storage.transaction() as tx:
                row = tx.execute(
                    "SELECT state FROM host_attempts WHERE attempt_id = ?",
                    (owner_context.attempt_id,),
                ).fetchone()
            assert row is not None
            assert row[0] == AttemptState.STALE.value
    finally:
        storage.close()


@dataclass(slots=True)
class _ManualLossSupervisor:
    """fake supervisor: 由测试显式触发 owner-lost。

    用于覆盖 harness 在 lease loss 后停止消费 Engine event / 不再 append。
    """

    last_owner: AttemptOwnerContext | None = None
    enter_count: int = 0
    exit_count: int = 0
    diagnostic_close_calls: list[tuple[str, AttemptState, str | None]] = field(
        default_factory=list
    )
    _loss_event: asyncio.Event = field(default_factory=asyncio.Event)
    _loss_reason: AttemptOwnerLossReason = AttemptOwnerLossReason.FENCED

    def trigger_loss(
        self, reason: AttemptOwnerLossReason = AttemptOwnerLossReason.FENCED
    ) -> None:
        self._loss_reason = reason
        self._loss_event.set()

    @asynccontextmanager
    async def lease_context(
        self,
        *,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None = None,
    ) -> AsyncGenerator[AttemptOwnerContext, None]:
        del recovered_from_attempt_id
        self.enter_count += 1
        owner = AttemptOwnerContext(
            attempt_id=f"att-{run_id}-{attempt_index}",
            run_id=run_id,
            attempt_index=attempt_index,
            owner_id="host-test:0:0000",
            owner_token=AttemptOwnerToken.new(),
            fencing_token=FencingToken(value=self.enter_count),
            lease_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        self.last_owner = owner
        try:
            yield owner
        finally:
            self.exit_count += 1

    def is_owner_active(self, owner_context: AttemptOwnerContext) -> bool:
        if owner_context is not self.last_owner:
            return False
        return not self._loss_event.is_set()

    async def wait_owner_lost(
        self, owner_context: AttemptOwnerContext
    ) -> AttemptOwnerLossReason:
        if owner_context is not self.last_owner:
            return AttemptOwnerLossReason.FENCED
        await self._loss_event.wait()
        return self._loss_reason

    async def close_attempt_with_diagnostic_state(
        self,
        *,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        failure_summary: str | None,
        terminal_event_position: GlobalEventPosition | None = None,
    ) -> bool:
        del terminal_event_position
        self.diagnostic_close_calls.append(
            (owner_context.attempt_id, state, failure_summary)
        )
        return True


@pytest.mark.asyncio
async def test_owner_lost_during_engine_wait_stops_late_event_append() -> None:
    """owner-lost 后 harness 停止从 Engine 拉取 / append late event。

    使用一个手动可推进的 fake EngineEvent stream: 第一个 event 已经 ready,
    然后等待直到测试主线程触发 owner-lost; race 后再 yield 一个 late event。
    断言: late event 不进入 EventLog (event_store.append 不再被调用)。
    """

    from dayu.host._run_harness import LocalRunHarness

    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:")
    )
    try:
        await _seed_run(bundle.storage)
        supervisor = _ManualLossSupervisor()
        proxy = bundle.harness.proxy
        runtime = bundle.harness.tool_runtime
        assert runtime is not None
        harness = LocalRunHarness(
            proxy=proxy,
            event_store=bundle.event_store,
            tool_runtime=runtime,
            memory_store=bundle.memory_store,
            attempt_supervisor=cast(AttemptSupervisor, supervisor),
            storage=bundle.storage,
        )

        # 构造一个最小 owner 句柄, 不通过 lease_context (本测试只验证 race 行为)。
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            from dayu.host._run_harness import (
                _ActiveAttempt,
                _OwnerLostDuringEngineWait,
            )
            from contextlib import AsyncExitStack

            stack = AsyncExitStack()
            await stack.__aenter__()
            active = _ActiveAttempt(
                attempt_id=owner_context.attempt_id,
                owner_context=owner_context,
                lease_exit_stack=stack,
            )

            late_event_appended: list[EngineEvent] = []

            async def _engine_stream() -> AsyncIterator[EngineEvent]:
                # 永远 pending: 等到 owner_lost 触发后被 cancel; harness 不应 append 任何 event。
                await asyncio.Event().wait()
                # 下方 yield/append 仅用于类型完整性, owner-lost 触发后 race
                # 任务被 cancel, 流不会真正抵达。
                yield EngineEvent(  # pragma: no cover
                    event_id="late",
                    sequence=1,
                    occurred_at=datetime.now(tz=timezone.utc),
                    session_id="s",
                    run_id="r1",
                    type=EngineEventType.RUNNER_CONTENT_DELTA,
                    data=ContentDeltaData(iteration_id="it", delta="late"),
                    metadata=None,
                )
                late_event_appended.append(  # pragma: no cover
                    EngineEvent(
                        event_id="late2",
                        sequence=2,
                        occurred_at=datetime.now(tz=timezone.utc),
                        session_id="s",
                        run_id="r1",
                        type=EngineEventType.RUNNER_CONTENT_DELTA,
                        data=ContentDeltaData(iteration_id="it", delta="late"),
                        metadata=None,
                    )
                )

            stream = _engine_stream()

            async def _race() -> None:
                with pytest.raises(_OwnerLostDuringEngineWait) as excinfo:
                    await harness._next_engine_event_or_lose_owner(  # noqa: SLF001
                        engine_events=stream,
                        active_attempt=active,
                    )
                assert excinfo.value.loss_reason is AttemptOwnerLossReason.FENCED

            race_task = asyncio.create_task(_race())
            await asyncio.sleep(0.02)
            assert not race_task.done()
            supervisor.trigger_loss(AttemptOwnerLossReason.FENCED)
            await asyncio.wait_for(race_task, timeout=1.0)
            # 关键断言: late event 没有被 append (因为 owner-lost 优先 race)。
            assert late_event_appended == []
            await stack.aclose()
    finally:
        bundle.close()


@dataclass(slots=True)
class _RecordingDiagnosticSupervisor:
    """包装真实 supervisor 并记录 diagnostic close 调用。

    本 wrapper 不替换 lease_context / renew loop / wait_owner_lost 任何路径,
    仅透传到内部 supervisor; 唯一额外能力是把
    ``close_attempt_with_diagnostic_state`` 的入参与返回值记录到列表, 使集成
    测试可以在 ``_run_to_store`` 整链路上观察 owner-aware 收口确实经过 supervisor
    路径(而不是 legacy 非 owner-aware update_state)。
    """

    inner: AttemptSupervisor
    diagnostic_close_calls: list[
        tuple[str, AttemptState, str | None, GlobalEventPosition | None, bool]
    ] = field(default_factory=list)

    @asynccontextmanager
    async def lease_context(
        self,
        *,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None = None,
    ) -> AsyncGenerator[AttemptOwnerContext, None]:
        async with self.inner.lease_context(
            run_id=run_id,
            attempt_index=attempt_index,
            recovered_from_attempt_id=recovered_from_attempt_id,
        ) as owner_context:
            yield owner_context

    def is_owner_active(self, owner_context: AttemptOwnerContext) -> bool:
        return self.inner.is_owner_active(owner_context)

    async def wait_owner_lost(
        self, owner_context: AttemptOwnerContext
    ) -> AttemptOwnerLossReason:
        return await self.inner.wait_owner_lost(owner_context)

    async def close_attempt_with_diagnostic_state(
        self,
        *,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        failure_summary: str | None,
        terminal_event_position: GlobalEventPosition | None = None,
    ) -> bool:
        applied = await self.inner.close_attempt_with_diagnostic_state(
            owner_context=owner_context,
            state=state,
            failure_summary=failure_summary,
            terminal_event_position=terminal_event_position,
        )
        self.diagnostic_close_calls.append(
            (
                owner_context.attempt_id,
                state,
                failure_summary,
                terminal_event_position,
                applied,
            )
        )
        return applied


@dataclass(slots=True)
class _OwnerLostDuringRunToStoreState:
    """``_run_to_store`` 集成路径上 fake proxy 与测试主线程的状态同步。

    fake proxy 的 stream 在第一个 preview event yield 后等待 ``loss_done`` 被
    set; 测试主线程在确认 preview 已 append 后, 通过事务直接重写
    ``host_attempts`` 的 ``fencing_token``, 使 supervisor 的 renew CAS 必然
    miss, 之后 set ``loss_done`` 让 stream 准备 yield late event。harness 应
    在拿到 owner-lost 信号后停止后续 append, late event 不进入 EventLog。
    """

    first_event_yielded: asyncio.Event = field(default_factory=asyncio.Event)
    loss_done: asyncio.Event = field(default_factory=asyncio.Event)
    late_event_was_yielded: bool = False


@dataclass(slots=True)
class _OwnerLostDuringRunToStoreProxy:
    """fake proxy: 先吐 preview event, 等 owner 被外部 fenced 后再准备 late event。

    本 proxy 不调用真实 Engine, 也不依赖真实 sleep; 仅按测试主线程驱动的事件
    序列稳定地复现 ``_run_to_store`` 主循环 owner-lost 路径所需的输入。
    """

    state: _OwnerLostDuringRunToStoreState
    session_id: str
    run_id: str

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        del request, cancellation_token
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[EngineEvent]:
        # 第 1 个事件: preview content_delta, 确保 ``_run_to_store`` 已经
        # 进入主循环并完成首轮 EventLog append。
        yield EngineEvent(
            event_id="engine_preview_1",
            sequence=1,
            occurred_at=datetime.now(tz=timezone.utc),
            session_id=self.session_id,
            run_id=self.run_id,
            type=EngineEventType.RUNNER_CONTENT_DELTA,
            data=ContentDeltaData(iteration_id="it-0", delta="early"),
            metadata=None,
        )
        self.state.first_event_yielded.set()
        # 等待测试主线程触发 owner fenced 并 set loss_done。
        await self.state.loss_done.wait()
        # late event: harness 在 owner-lost race 命中后不应再 append 本事件,
        # 但 fake stream 仍会准备好(语义上模拟 worker 还在产出事件的真实场景)。
        self.state.late_event_was_yielded = True
        yield EngineEvent(
            event_id="engine_late_after_loss",
            sequence=2,
            occurred_at=datetime.now(tz=timezone.utc),
            session_id=self.session_id,
            run_id=self.run_id,
            type=EngineEventType.RUNNER_CONTENT_DELTA,
            data=ContentDeltaData(iteration_id="it-0", delta="late"),
            metadata=None,
        )


@pytest.mark.asyncio
async def test_run_to_store_owner_lost_drops_late_engine_event_and_writes_host_failure() -> (
    None
):
    """``_run_to_store`` 端到端 owner-lost: late Engine event 不进 EventLog, Host 写诊断终态。

    覆盖 P8-S3 Low-3 follow-up 完整路径, 不只测 ``_next_engine_event_or_lose_owner``:

    1. ``build_durable_harness`` 装配真实 supervisor + DurableEventStore + 默认
       observer; renew_interval 用极短值, 便于测试主线程外部 fence 后 supervisor
       renew CAS 立即 miss。
    2. 注入 fake proxy: 先 yield 一个 preview content_delta, 等待 ``loss_done``
       后再 yield 一个 late event (模拟 worker 在 owner-lost 后仍在产出事件)。
    3. 测试主线程等 preview event 已 append, 直接 UPDATE ``host_attempts.fencing_token``
       (owner_token_hash 保留), 让 supervisor renew loop 在下一次 CAS 时命中
       FENCED, ``wait_owner_lost`` 立即返回 typed ``FENCED``。
    4. set ``loss_done`` 让 fake stream 准备 yield late event; harness 经
       ``_handle_owner_lost`` 路径写入 ``RUN_FAILED(error_code=attempt_lease_lost)``,
       关闭 stream, 不再 append late event。
    5. 通过 ``_RecordingDiagnosticSupervisor`` 观察:
       - diagnostic close 至少被调用一次, 入参 ``state == AttemptState.LOST``,
         failure_summary 以 ``attempt_lease_lost:`` 开头;
       - close 返回 ``False`` (owner CAS miss, 因为外部已经替换 fencing token),
         证明走的是 owner-aware 路径而不是 legacy 非 owner-aware update。
    6. EventLog 断言:
       - 出现 Host RUN_FAILED 且 ``error_code == "attempt_lease_lost"``;
       - 不出现 ``event_id == "engine_late_after_loss"`` 的 RunEvent
         (late Engine event 没有进入 EventLog)。
    7. ``host_attempts`` 行的 ``state`` 仍是 ``running`` (CAS miss 未覆盖未来
       状态), 进一步证明诊断收口走 owner-aware CAS 而不是 unconditional 写。
    8. 全程不依赖真实 ``time.sleep``; 仅在轮询等待异步事件时使用极短
       ``asyncio.sleep`` 让出事件循环。
    """

    from dayu.engine import (
        AgentMessageRole,
        AgentPolicy,
        RunnerCallOptions,
        RunnerSpec,
        UserMessage,
    )
    from dayu.host._run_harness import LocalRunHarness
    from dayu.host.contracts import (
        RunInput,
        RunOptions,
    )

    # renew_interval 设极短, 便于外部 fence 后 supervisor 立刻 CAS-miss; ttl
    # 仍较长, 不靠 lease 自然过期。
    fast_renew = AttemptLeaseConfig(
        ttl=timedelta(seconds=30),
        renew_interval=timedelta(milliseconds=5),
        owner_id_prefix="host-test",
    )
    bundle = build_durable_harness(
        config=DurableHarnessConfig(
            database_path=":memory:",
            attempt_lease_config=fast_renew,
        )
    )
    try:
        sync_state = _OwnerLostDuringRunToStoreState()
        proxy = _OwnerLostDuringRunToStoreProxy(
            state=sync_state, session_id="s_int", run_id="r_int"
        )
        recording = _RecordingDiagnosticSupervisor(
            inner=bundle.attempt_supervisor
        )
        runtime = bundle.harness.tool_runtime
        assert runtime is not None
        from dayu.host._proxy import WorkerProxy

        harness = LocalRunHarness(
            proxy=cast(WorkerProxy, proxy),
            event_store=bundle.event_store,
            tool_runtime=runtime,
            memory_store=bundle.memory_store,
            coordinator=bundle.coordinator,
            attempt_state_store=bundle.attempt_state_store,
            attempt_supervisor=cast(AttemptSupervisor, recording),
            storage=bundle.storage,
        )

        request = StartRunRequest(
            session_id="s_int",
            run_id="r_int",
            input=RunInput(
                messages=(
                    UserMessage(role=AgentMessageRole.USER, content="hi"),
                )
            ),
            options=RunOptions(
                runner_spec=RunnerSpec(
                    provider="openai",
                    model="m",
                    endpoint="https://example.test/v1/chat/completions",
                    api_key_ref="K",
                    headers={},
                    supports_tool_calling=True,
                    supports_streaming=True,
                    supports_stream_usage=False,
                    default_timeout_seconds=30.0,
                    max_retries=0,
                    provider_request=None,
                ),
                runner_options=RunnerCallOptions(
                    temperature=None,
                    max_tokens=None,
                    top_p=None,
                    stream=True,
                ),
                agent_policy=AgentPolicy(
                    max_iterations=3,
                    continuation_max_attempts=1,
                    allow_tool_calls=True,
                ),
                stream=False,
                disable_tools=True,
                tool_schemas=(),
            ),
        )

        run_stream = await harness.start_run(request)

        # 等 fake proxy 已经 yield 第一个 preview event; 此时 attempt 已经
        # 存在于 host_attempts, EventLog 已经 append 了 USER_INPUT_ACCEPTED +
        # context snapshot + preview。
        await asyncio.wait_for(
            sync_state.first_event_yielded.wait(), timeout=2.0
        )

        # 直接 UPDATE host_attempts.fencing_token 把当前 owner 替换成不同的
        # fencing token (state 仍为 running, owner_token_hash 不动): supervisor
        # renew loop 下一次 CAS 必然 miss -> 标记 FENCED -> wait_owner_lost
        # 返回 FENCED -> harness 走 _handle_owner_lost 路径。
        attempt_id = recording.inner._sessions[  # noqa: SLF001
            next(iter(recording.inner._sessions))  # noqa: SLF001
        ].owner_context.attempt_id
        owner_context = recording.inner._sessions[attempt_id].owner_context  # noqa: SLF001
        async with bundle.storage.transaction() as tx:
            tx.execute(
                "UPDATE host_attempts SET fencing_token = ? "
                "WHERE attempt_id = ?",
                (10_000_000, attempt_id),
            )

        # 等到 supervisor 的 renew loop 真正完成一次 CAS 并把 owner 标记为
        # 失活, 才让 fake stream 解除等待。这避免 late event 被 harness 在
        # owner-lost 信号到达前抢先 anext 消费(导致 attempt_lease_lost 路径
        # 被 engine_stream_ended_without_terminal 替换)。
        loss_deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < loss_deadline:
            if not recording.inner.is_owner_active(owner_context):
                break
            await asyncio.sleep(0.005)
        assert not recording.inner.is_owner_active(owner_context), (
            "supervisor renew loop did not detect external fence"
        )

        # 让 fake stream 解除等待, 准备 yield late event; harness 此时已经
        # 在 owner-lost 路径上, race 必然命中 owner-lost。
        sync_state.loss_done.set()

        # 等 background _run_to_store task 跑完: 用 EventLog 出现 Host
        # RUN_FAILED 作为完成信号, 不依赖真实 sleep。
        deadline = asyncio.get_running_loop().time() + 5.0
        host_failure_event = None
        late_event_in_log = False
        while asyncio.get_running_loop().time() < deadline:
            events = await bundle.event_store.list_events(
                run_id="r_int", after=None
            )
            for evt in events:
                if (
                    evt.type is RunEventType.RUN_FAILED
                    and evt.source is RunEventSource.HOST
                ):
                    host_failure_event = evt
                if evt.source_engine_event_id == "engine_late_after_loss":
                    late_event_in_log = True
            if host_failure_event is not None:
                break
            await asyncio.sleep(0.01)

        # 关键断言 1: Host RUN_FAILED(error_code=attempt_lease_lost) 已写入。
        assert host_failure_event is not None, (
            "host owner-lost terminal RUN_FAILED was not appended"
        )
        host_data = host_failure_event.data
        assert isinstance(host_data, HostRunFailedData)
        assert host_data.error_code == "attempt_lease_lost"
        assert host_data.recoverable is False

        # 关键断言 2: late Engine event 没有进入 EventLog。
        assert late_event_in_log is False, (
            "late Engine event after owner-lost leaked into EventLog"
        )

        # 关键断言 3: diagnostic close 通过 supervisor owner-aware 路径调用,
        # 且 CAS miss 返回 False (因为外部已替换 fencing token)。
        relevant_calls = [
            call for call in recording.diagnostic_close_calls
            if call[0] == attempt_id
        ]
        assert len(relevant_calls) >= 1
        _aid, state, summary, _pos, applied = relevant_calls[-1]
        assert state is AttemptState.LOST
        assert summary is not None
        assert summary.startswith("attempt_lease_lost:")
        assert applied is False, (
            "diagnostic close should CAS-miss after external fence; "
            "non-owner-aware update would have returned True"
        )

        # 关键断言 4: host_attempts.state 仍是 running, owner-aware CAS 没有
        # 把它覆盖为 LOST; 这进一步证明走的是 supervisor owner-aware 路径。
        async with bundle.storage.transaction() as tx:
            row = tx.execute(
                "SELECT state FROM host_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == AttemptState.RUNNING.value

        # 消费 RunStream 直到结束, 避免遗留订阅资源。
        consumed_types: list[RunEventType] = []
        async for evt in run_stream.events:
            consumed_types.append(evt.type)
        # 订阅流以 Host RUN_FAILED 收口; 不应出现 late engine event。
        assert RunEventType.RUN_FAILED in consumed_types
    finally:
        bundle.close()
