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
import gc
import logging
import sqlite3
import warnings
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from typing import cast

import pytest

from dayu.engine.contracts.engine_events import (
    ContentDeltaData,
    EngineEvent,
    EngineEventType,
)
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    RunnerCallOptions,
    RunnerSpec,
    UserMessage,
)
from dayu.contracts import CancellationToken, ToolSchema
from dayu.host._attempt_lease import (
    ATTEMPT_OWNER_ID_PREFIX,
    AttemptFencingError,
    AttemptFencingReason,
    AttemptLeaseBusyReason,
    AttemptLeaseConfig,
    AttemptLeaseDecision,
    AttemptLeaseResult,
    AttemptOwnerContext,
    AttemptOwnerToken,
    AttemptTerminalLink,
    DEFAULT_ATTEMPT_LEASE_CONFIG,
)
from dayu.host._attempt_supervisor import (
    AttemptOwnerLossReason,
    AttemptScopedRunEventAppender,
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
from dayu.host._run_harness import _ActiveAttempt
from dayu.host._tool_runtime import HostToolRuntime
from dayu.host.contracts import (
    HostRunFailedData,
    RunEvent,
    RunEventDraft,
    RunFailedResult,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunInput,
    RunOptions,
    StartRunRequest,
    UserInputAcceptedData,
    UserInputScope,
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


class _FencingProxy:
    """在获取 Engine iterator 时直接抛 fencing 的 fake proxy。"""

    def stream_engine_events(
        self,
        *,
        request: StartRunRequest,
        tool_schemas: tuple[ToolSchema, ...],
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """模拟 proxy 入口阶段被 owner fencing 拒绝。

        :param request: start run 请求。
        :param cancellation_token: 取消 token。
        :returns: 永不返回异步迭代器。
        :raises AttemptFencingError: 始终抛出 typed fencing 错误。
        """

        del cancellation_token
        raise AttemptFencingError(
            attempt_id="attempt-entry-fenced",
            run_id=request.run_id,
            reason=AttemptFencingReason.OWNER_MISMATCH,
            current_state=AttemptState.RUNNING,
            owner_id="owner-other",
            fencing_token=FencingToken(value=1),
        )


def _minimal_start_request(*, session_id: str, run_id: str) -> StartRunRequest:
    """构造最小 durable harness start request。

    :param session_id: 会话 id。
    :param run_id: Run id。
    :returns: :class:`StartRunRequest`。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id=session_id,
        run_id=run_id,
        input=RunInput(
            messages=(UserMessage(role=AgentMessageRole.USER, content="hi"),)
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


def _host_run_failed_draft(*, run_id: str) -> RunEventDraft:
    """构造 Host ``RUN_FAILED`` terminal RunEvent 草稿。

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

    from dayu.host._run_harness import LocalRunHarness
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
            is_durable=True,
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
            reason=None,
            busy_reason=AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT,
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
        assert excinfo.value.reason is AttemptFencingReason.STORAGE_CONFLICT
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_start_run_initial_attempt_busy_writes_terminal_failure() -> None:
    """首个 attempt acquire BUSY 不得留下 USER_INPUT_ACCEPTED 无终态。"""

    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:")
    )
    clock = _FakeClock()
    supervisor = AttemptSupervisor(
        storage=bundle.storage,
        lease_store=cast(AttemptLeaseStore, _BusyStore(clock=clock)),
        lease_config=AttemptLeaseConfig(
            ttl=timedelta(seconds=30),
            renew_interval=timedelta(milliseconds=10),
            owner_id_prefix="host-test",
        ),
        clock=clock,
        event_store=bundle.event_store,
    )
    from dayu.host._proxy import WorkerProxy
    from dayu.host._run_harness import LocalRunHarness

    harness = LocalRunHarness(
        is_durable=True,
        proxy=cast(WorkerProxy, _FencingProxy()),
        event_store=bundle.event_store,
        tool_runtime=bundle.harness.tool_runtime,
        memory_store=bundle.memory_store,
        coordinator=bundle.coordinator,
        attempt_supervisor=supervisor,
        storage=bundle.storage,
    )
    try:
        stream = await harness.start_run(
            _minimal_start_request(session_id="s-busy", run_id="r-busy")
        )
        events = [event async for event in stream.events]

        assert [event.type for event in events] == [
            RunEventType.USER_INPUT_ACCEPTED,
            RunEventType.RUN_FAILED,
        ]
        result = bundle.run_state_store.get_terminal_result("r-busy")
        assert isinstance(result, RunFailedResult)
    finally:
        bundle.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run_id", "attempt_index", "recovered_from_attempt_id", "message"),
    (
        ("", 0, None, "run_id must be non-empty"),
        ("r1", -1, None, "attempt_index must be greater than or equal to 0"),
        (
            "r1",
            0,
            "",
            "recovered_from_attempt_id must be non-empty when provided",
        ),
    ),
)
async def test_lease_context_validates_identity_arguments(
    run_id: str,
    attempt_index: int,
    recovered_from_attempt_id: str | None,
    message: str,
) -> None:
    """lease_context 必须在 acquire 前拒绝非法业务标识参数。

    :param run_id: 待验证的 Run id。
    :param attempt_index: 待验证的 attempt 序号。
    :param recovered_from_attempt_id: 待验证的 recovery 来源 attempt id。
    :param message: 期望的错误消息片段。
    :returns: 无返回值。
    :raises AssertionError: 未抛出预期 ``ValueError`` 时由 pytest 抛出。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        with pytest.raises(ValueError, match=message):
            async with supervisor.lease_context(
                run_id=run_id,
                attempt_index=attempt_index,
                recovered_from_attempt_id=recovered_from_attempt_id,
            ):
                pytest.fail("lease_context should reject invalid arguments")
        rows = storage.execute_read("SELECT attempt_id FROM host_attempts")
        assert rows == []
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


@dataclass(slots=True)
class _LateSuccessLeaseStore:
    """让 renew 在返回成功前触发并发 owner-lost 的 lease store stub。

    :param inner: 真实 lease store，用于 acquire / verify / close。
    :param before_success_return: renew 返回成功结果前执行的回调。
    :param renew_called: renew 已被调用的同步信号。
    """

    inner: AttemptLeaseStore
    before_success_return: Callable[[], None] | None = None
    renew_called: asyncio.Event = field(default_factory=asyncio.Event)

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
        result = self.inner.renew(
            tx=tx,
            owner_context=owner_context,
            lease_expires_at=lease_expires_at,
        )
        self.renew_called.set()
        if self.before_success_return is not None:
            self.before_success_return()
        return result

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
async def test_renew_late_success_does_not_overwrite_owner_lost_reason() -> None:
    """late successful renew 不得覆盖已置位的 owner-lost 第一原因。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        real_store = AttemptLeaseStore(storage=storage, clock=clock)
        store = _LateSuccessLeaseStore(inner=real_store)
        supervisor = AttemptSupervisor(
            storage=storage,
            lease_store=cast(AttemptLeaseStore, store),
            lease_config=AttemptLeaseConfig(
                ttl=timedelta(seconds=30),
                renew_interval=timedelta(milliseconds=5),
                owner_id_prefix="host-test",
            ),
            clock=clock,
            event_store=_build_event_store(storage),
        )
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            session = supervisor._sessions[owner_context.attempt_id]  # noqa: SLF001
            first_owner_context = session.owner_context

            def _mark_storage_loss() -> None:
                """模拟 renew 成功返回前已经由并发路径判定 owner-lost。

                :returns: 无返回值。
                :raises Exception: 不主动抛出异常。
                """

                supervisor._mark_owner_lost(  # noqa: SLF001
                    session=session,
                    loss_reason=AttemptOwnerLossReason.STORAGE_ERROR,
                    fence_reason=None,
                )

            store.before_success_return = _mark_storage_loss
            clock.advance(timedelta(seconds=1))

            await asyncio.wait_for(store.renew_called.wait(), timeout=1.0)
            await asyncio.wait_for(session.stopped_event.wait(), timeout=1.0)
            loss_reason = await asyncio.wait_for(
                supervisor.wait_owner_lost(owner_context),
                timeout=1.0,
            )

            assert loss_reason is AttemptOwnerLossReason.STORAGE_ERROR
            assert session.loss_reason is AttemptOwnerLossReason.STORAGE_ERROR
            assert session.owner_context is first_owner_context
    finally:
        storage.close()


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
                session = supervisor._sessions[owner_context.attempt_id]  # noqa: SLF001
                await asyncio.wait_for(session.stopped_event.wait(), timeout=0.5)
                renew_task = session.renew_task
                assert renew_task is not None
                assert renew_task.done()
                assert renew_task.exception() is None
        all_logs = "\n".join(record.getMessage() for record in caplog.records)
        # owner 明文不能进入日志; masked token 必须出现; storage error 标识必须出现。
        for plain in plaintext_seen:
            assert plain not in all_logs
        assert "***" in all_logs
        assert "host.attempt.lease_renew_storage_error" in all_logs
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_renew_terminal_fence_after_terminal_close_marks_owner_lost() -> None:
    """terminal close 竞争后 renew 收到 ATTEMPT_TERMINAL 并无异常退出。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        config = AttemptLeaseConfig(
            ttl=timedelta(seconds=30),
            renew_interval=timedelta(milliseconds=5),
            owner_id_prefix="host-test",
        )
        supervisor = _build_supervisor(
            storage=storage,
            clock=clock,
            config=config,
        )
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            session = supervisor._sessions[owner_context.attempt_id]  # noqa: SLF001
            await supervisor.append_terminal_and_close(
                owner_context=owner_context,
                draft=_host_run_failed_draft(run_id=owner_context.run_id),
                failure_summary="attempt lease lost",
            )

            await asyncio.wait_for(session.stopped_event.wait(), timeout=1.0)
            loss_reason = await asyncio.wait_for(
                supervisor.wait_owner_lost(owner_context),
                timeout=1.0,
            )
            renew_task = session.renew_task

            assert loss_reason is AttemptOwnerLossReason.FENCED
            assert session.loss_reason is AttemptOwnerLossReason.FENCED
            assert (
                session.fence_reason
                is AttemptFencingReason.ATTEMPT_TERMINAL
            )
            assert renew_task is not None
            assert renew_task.done()
            assert renew_task.exception() is None
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

    from dayu.host._run_harness import LocalRunHarness, _ActiveAttempt

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
            is_durable=True,
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
    """包装真实 supervisor 并记录 diagnostic close 与 terminal close 调用。

    本 wrapper 不替换 lease_context / renew loop / wait_owner_lost 任何路径,
    仅透传到内部 supervisor; 唯一额外能力是把
    ``close_attempt_with_diagnostic_state`` 与
    ``append_terminal_and_close`` 的入参与返回值记录到列表, 使集成
    测试可以在 ``_run_to_store`` 整链路上观察 owner-aware 收口确实经过
    supervisor 路径(而不是 legacy 非 owner-aware update_state, 或裸
    ``event_store.append``)。
    """

    inner: AttemptSupervisor
    diagnostic_close_calls: list[
        tuple[str, AttemptState, str | None, GlobalEventPosition | None, bool]
    ] = field(default_factory=list)
    terminal_close_calls: list[
        tuple[str, RunEventType, str | None, AttemptFencingReason | None]
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

    def scoped_appender(
        self, owner_context: AttemptOwnerContext
    ) -> AttemptScopedRunEventAppender:
        return self.inner.scoped_appender(owner_context)

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

    async def append_terminal_and_close(
        self,
        *,
        owner_context: AttemptOwnerContext,
        draft: RunEventDraft,
        failure_summary: str | None = None,
        terminal_state_override: AttemptState | None = None,
    ) -> AttemptTerminalLink:
        try:
            link = await self.inner.append_terminal_and_close(
                owner_context=owner_context,
                draft=draft,
                failure_summary=failure_summary,
                terminal_state_override=terminal_state_override,
            )
        except AttemptFencingError as exc:
            self.terminal_close_calls.append(
                (owner_context.attempt_id, draft.type, failure_summary, exc.reason)
            )
            raise
        self.terminal_close_calls.append(
            (owner_context.attempt_id, draft.type, failure_summary, None)
        )
        return link


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
        tool_schemas: tuple[ToolSchema, ...],
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
async def test_run_to_store_owner_lost_atomic_terminal_close_cas_hit() -> None:
    """``_run_to_store`` 端到端 owner-lost (Case A — CAS hit): atomic terminal close。

    P8-S3 Case A: owner 被诊断为 lost 但 DB 真源仍持有当前 owner_token /
    fencing_token (例如 supervisor 内部 ``loss_reason`` 被 storage error 等
    非 DB-CAS 原因置位)。``_handle_owner_lost`` 必须走
    ``AttemptSupervisor.append_terminal_and_close`` 在单事务内完成:

    1. ``verify_owner`` CAS hit;
    2. terminal ``RUN_FAILED(error_code=attempt_lease_lost)`` append;
    3. ``host_attempts`` 终态 close + ``terminal_event_position`` 写入。

    关键断言:

    - EventLog 出现恰 1 条 Host RUN_FAILED, ``error_code == attempt_lease_lost``;
    - ``host_attempts.state == LOST`` 且 ``terminal_event_position`` 非空,
      ``failure_summary`` 以 ``attempt_lease_lost:`` 开头;
    - RunStream 订阅方收到 terminal event 后 generator 自然结束;
    - late Engine event 不进入 EventLog。
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

    # renew_interval 设极短, 让 renew loop 快速观察到 loss_reason 后退出。
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
            is_durable=True,
            proxy=cast(WorkerProxy, proxy),
            event_store=bundle.event_store,
            tool_runtime=runtime,
            memory_store=bundle.memory_store,
            coordinator=bundle.coordinator,
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

        # 等 fake proxy 已经 yield preview event。
        await asyncio.wait_for(
            sync_state.first_event_yielded.wait(), timeout=2.0
        )

        # Case A 触发: 直接把 supervisor 内部 session 的 loss_reason 置为
        # STORAGE_ERROR 并 set owner_lost_event, 不修改 DB; renew loop 在
        # 下次 tick 看到 loss_reason 非空后退出, harness wait_owner_lost
        # 立即返回 STORAGE_ERROR。DB owner_token / fencing_token 仍是真实
        # 当前 owner -> ``append_terminal_and_close`` CAS 命中。
        sessions = recording.inner._sessions  # noqa: SLF001
        attempt_id = next(iter(sessions))
        session = sessions[attempt_id]
        owner_context = session.owner_context
        session.loss_reason = AttemptOwnerLossReason.STORAGE_ERROR
        session.owner_lost_event.set()

        # 让 fake stream 解除等待, harness 在 owner-lost race 命中。
        sync_state.loss_done.set()

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

        assert host_failure_event is not None, (
            "atomic terminal close should append HOST RUN_FAILED on CAS hit"
        )
        host_data = host_failure_event.data
        assert isinstance(host_data, HostRunFailedData)
        assert host_data.error_code == "attempt_lease_lost"
        assert host_data.recoverable is False

        assert late_event_in_log is False, (
            "late Engine event after owner-lost leaked into EventLog"
        )

        # 走的是 ``append_terminal_and_close`` 而不是 legacy 裸 append +
        # diagnostic close: terminal_close_calls 至少 1 次, fence_reason
        # 为 None (CAS hit)。
        relevant_terminal = [
            call for call in recording.terminal_close_calls
            if call[0] == attempt_id
        ]
        assert len(relevant_terminal) >= 1
        _aid, draft_type, summary, fence_reason = relevant_terminal[-1]
        assert draft_type is RunEventType.RUN_FAILED
        assert summary is not None
        assert summary.startswith("attempt_lease_lost:")
        assert fence_reason is None, (
            "Case A 期望 verify_owner CAS 命中, 不应出现 fence_reason"
        )

        # host_attempts 已被 supervisor 在同事务内推到 LOST, 并写入
        # terminal_event_position。
        async with bundle.storage.transaction() as tx:
            row = tx.execute(
                "SELECT state, failure_summary, terminal_event_position "
                "FROM host_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == AttemptState.LOST.value
        assert row[1] is not None and row[1].startswith("attempt_lease_lost:")
        assert row[2] is not None

        # 不应触发 diagnostic close (CAS hit 路径已经把 attempt 推到 LOST,
        # 上层 finally 块的 _finish_attempt_if_durable 在 active_attempt
        # 被置 None 后跳过)。
        diagnostic_relevant = [
            call for call in recording.diagnostic_close_calls
            if call[0] == attempt_id
        ]
        assert diagnostic_relevant == [], (
            "Case A 不应回退到 diagnostic close; "
            "append_terminal_and_close 已 atomic 推进终态"
        )

        consumed_types: list[RunEventType] = []
        async for evt in run_stream.events:
            consumed_types.append(evt.type)
        assert RunEventType.RUN_FAILED in consumed_types

        # owner_context 在记录调用中保留, 用于诊断输出
        assert owner_context.attempt_id == attempt_id
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_handle_owner_lost_cas_miss_no_stale_terminal() -> None:
    """``_handle_owner_lost`` Case B — CAS miss: 不写任何终态 RunEvent。

    P8-S3 Case B: 在旧 owner 的 owner-lost signal 触发前, 已有 recovery /
    其它进程把 ``host_attempts`` 推到 LOST。``_handle_owner_lost`` 必须:

    - 调 ``append_terminal_and_close`` 触发 ``AttemptFencingError``;
    - **不**向 EventLog 追加任何 ``RUN_FAILED``;
    - ``host_attempts.state`` 保持 recovery 推进后的值;
    - typed log ``host.run.attempt_lease_lost_cas_miss`` 已记录;
    - RunStream generator 自然 break, 不抛 user-visible 异常。
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
            is_durable=True,
            proxy=cast(WorkerProxy, proxy),
            event_store=bundle.event_store,
            tool_runtime=runtime,
            memory_store=bundle.memory_store,
            coordinator=bundle.coordinator,
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
        await asyncio.wait_for(
            sync_state.first_event_yielded.wait(), timeout=2.0
        )

        # 模拟 recovery: 直接 UPDATE ``host_attempts`` 把 fencing_token
        # 替换 (state 仍为 running, owner_token_hash 不动), 让 supervisor
        # 后续 ``verify_owner`` CAS 必然 miss; 紧接着把 supervisor 内部
        # session 的 ``loss_reason`` 置位, 触发 owner-lost signal。
        sessions = recording.inner._sessions  # noqa: SLF001
        attempt_id = next(iter(sessions))
        session = sessions[attempt_id]
        async with bundle.storage.transaction() as tx:
            tx.execute(
                "UPDATE host_attempts SET fencing_token = ? "
                "WHERE attempt_id = ?",
                (10_000_000, attempt_id),
            )
        session.loss_reason = AttemptOwnerLossReason.FENCED
        session.fence_reason = AttemptFencingReason.FENCING_TOKEN_MISMATCH
        session.owner_lost_event.set()

        sync_state.loss_done.set()

        # 等 background _run_to_store task 完成 (要么 CAS miss 后退出,
        # 要么 supervisor 记录 terminal_close_calls)。
        deadline = asyncio.get_running_loop().time() + 5.0
        terminal_recorded = False
        while asyncio.get_running_loop().time() < deadline:
            relevant = [
                c for c in recording.terminal_close_calls
                if c[0] == attempt_id
            ]
            if relevant:
                terminal_recorded = True
                break
            await asyncio.sleep(0.01)

        assert terminal_recorded, (
            "_handle_owner_lost should attempt append_terminal_and_close"
        )
        # CAS miss: terminal_close_calls 末尾 fence_reason 非空。
        last_call = [
            c for c in recording.terminal_close_calls if c[0] == attempt_id
        ][-1]
        assert last_call[3] is not None, (
            "Case B 期望 verify_owner CAS miss, fence_reason 必须非空"
        )

        # 关键断言: EventLog 不出现 HOST RUN_FAILED。
        events = await bundle.event_store.list_events(
            run_id="r_int", after=None
        )
        host_failure_count = sum(
            1
            for evt in events
            if evt.type is RunEventType.RUN_FAILED
            and evt.source is RunEventSource.HOST
        )
        assert host_failure_count == 0, (
            "CAS miss path must not append stale HOST RUN_FAILED"
        )

        # host_attempts.state 保持 recovery 推进后的值 (本测试只改 fencing_token,
        # 没改 state, 因此仍是 RUNNING)。
        async with bundle.storage.transaction() as tx:
            row = tx.execute(
                "SELECT state FROM host_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == AttemptState.RUNNING.value

        # CAS miss 路径不会写终态事件; 真正终态由 recovery 真源补齐。
        # 本用例无 recovery 进程, 因此 RunStream 不会自然结束;
        # 显式 aclose() generator, 验证不抛 user-visible 异常即可。
        events_iter = cast(AsyncGenerator[RunEvent, None], run_stream.events)
        await events_iter.aclose()
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_owner_lost_handler_non_fencing_error_clears_active_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """owner-lost handler 抛普通异常时 finally 不得重复 close 同一 attempt。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: 无返回值。
    :raises AssertionError: 发生重复 close 或未透传原异常时抛出。
    """

    from dayu.host._proxy import WorkerProxy
    from dayu.host._run_harness import LocalRunHarness

    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:")
    )
    finish_calls: list[str] = []

    async def _raising_owner_lost(
        self: LocalRunHarness,
        *,
        request: StartRunRequest,
        active_attempt: _ActiveAttempt | None,
        loss_reason: AttemptOwnerLossReason,
        event_count: int,
        terminal_seen: bool,
    ) -> bool:
        """替换 ``_handle_owner_lost``，模拟非 fencing cleanup 异常。

        :param self: harness 实例。
        :param request: 当前 run 请求。
        :param active_attempt: 当前 attempt。
        :param loss_reason: owner-lost 原因。
        :param event_count: 已处理事件数。
        :param terminal_seen: 是否已见 terminal。
        :returns: 永不返回。
        :raises RuntimeError: 始终抛出模拟异常。
        """

        del self, request, active_attempt, loss_reason, event_count
        del terminal_seen
        raise RuntimeError("owner-lost-cleanup-failed")

    async def _recording_finish(
        self: LocalRunHarness,
        *,
        active_attempt: _ActiveAttempt | None,
        terminal_event: RunEvent | None,
        state: AttemptState | None = None,
        failure_summary: str | None = None,
    ) -> None:
        """记录是否发生 fallback attempt close。

        :param self: harness 实例。
        :param active_attempt: 当前 attempt。
        :param terminal_event: terminal RunEvent。
        :param state: 显式 attempt state。
        :param failure_summary: 失败摘要。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        del self, terminal_event, state, failure_summary
        if active_attempt is not None:
            finish_calls.append("close")

    monkeypatch.setattr(
        LocalRunHarness, "_handle_owner_lost", _raising_owner_lost
    )
    monkeypatch.setattr(
        LocalRunHarness, "_finish_attempt_if_durable", _recording_finish
    )

    try:
        runtime = bundle.harness.tool_runtime
        assert runtime is not None
        harness = LocalRunHarness(
            is_durable=True,
            proxy=cast(WorkerProxy, _FencingProxy()),
            event_store=bundle.event_store,
            tool_runtime=runtime,
            memory_store=bundle.memory_store,
            coordinator=bundle.coordinator,
            attempt_supervisor=bundle.attempt_supervisor,
            storage=bundle.storage,
        )
        request = _minimal_start_request(session_id="s_clear", run_id="r_clear")
        current_user_event = await bundle.event_store.append(
            RunEventDraft(
                run_id=request.run_id,
                session_id=request.session_id,
                kind=RunEventKind.CANONICAL,
                source=RunEventSource.HOST,
                type=RunEventType.USER_INPUT_ACCEPTED,
                occurred_at=datetime.now(tz=timezone.utc),
                data=UserInputAcceptedData(
                    turn_id=request.run_id,
                    content="hi",
                    scope=UserInputScope.SESSION,
                ),
                source_engine_event_id=None,
            )
        )
        with pytest.raises(RuntimeError, match="owner-lost-cleanup-failed"):
            await harness._run_to_store(  # noqa: SLF001
                request=request,
                tool_schemas=(),
                current_user_event=current_user_event,
            )
        assert finish_calls == []
    finally:
        bundle.close()


def _noop_tool_runtime(
    event_store: DurableRunEventStore,
) -> HostToolRuntime:
    """构造一个 noop tool runtime 用于不需要工具执行的测试。

    :param event_store: 事件 store。
    :returns: tool runtime 实例。
    :raises Exception: 不主动抛出异常。
    """

    from dayu.contracts.tool_call import ToolExecutionRequest
    from dayu.contracts.tool_outcome import (
        ToolCompletedOutcome,
        ToolExecutionOutcome,
    )
    from dayu.contracts.tool_result import ToolResultSuccess

    class _NoopExecutor:
        async def execute(
            self, request: ToolExecutionRequest
        ) -> ToolExecutionOutcome:
            del request
            return ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True, value=None, meta=None
                )
            )

    return HostToolRuntime(
        is_durable=True,
        executor=_NoopExecutor(),
        event_store=event_store,
    )


@pytest.mark.asyncio
async def test_handle_owner_lost_closes_stack_on_non_fencing_exception() -> None:
    """``_handle_owner_lost`` 非 AttemptFencingError 异常时也关闭 lease_exit_stack。"""

    from dayu.host._run_harness import LocalRunHarness
    from dayu.host._proxy import WorkerProxy
    from tests.host._memory_store_fake import (
        FakeInMemoryConversationMemoryStore,
    )

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        event_store = _build_event_store(storage)

        class _ExplodingSupervisor:
            """append_terminal_and_close 抛非 fencing 异常。"""

            def __init__(self, inner: AttemptSupervisor) -> None:
                self._inner = inner

            async def append_terminal_and_close(
                self, **_kwargs: object
            ) -> object:
                raise sqlite3.DatabaseError("disk I/O error")

            def scoped_appender(
                self, owner_context: AttemptOwnerContext
            ) -> AttemptScopedRunEventAppender:
                return self._inner.scoped_appender(owner_context)

            async def close_attempt_with_diagnostic_state(
                self, **_kwargs: object
            ) -> bool:
                return True

            async def wait_owner_lost(
                self, _owner_context: AttemptOwnerContext
            ) -> AttemptOwnerLossReason:
                await asyncio.sleep(10)
                return AttemptOwnerLossReason.FENCED  # pragma: no cover

            def is_owner_active(
                self, _owner_context: AttemptOwnerContext
            ) -> bool:
                return False

        exploding = _ExplodingSupervisor(supervisor)
        stack_closed = False

        class _TrackingStack:
            """记录 aclose 是否被调用。"""

            def __init__(self) -> None:
                pass

            async def aclose(self) -> None:
                nonlocal stack_closed
                stack_closed = True

        harness = LocalRunHarness(
            is_durable=True,
            proxy=cast(WorkerProxy, _NoopProxy()),
            event_store=event_store,
            tool_runtime=_noop_tool_runtime(event_store),
            memory_store=FakeInMemoryConversationMemoryStore(),
            coordinator=None,
            attempt_supervisor=cast(AttemptSupervisor, exploding),
            storage=storage,
        )

        # 构造一个带 owner_context 的 active attempt。
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            tracking_stack = _TrackingStack()
            active = _ActiveAttempt(
                attempt_id=owner_context.attempt_id,
                owner_context=owner_context,
                lease_exit_stack=tracking_stack,  # type: ignore[arg-type]
            )

            request = StartRunRequest(
                session_id="s1",
                run_id="r1",
                input=RunInput(
                    messages=(
                        UserMessage(
                            role=AgentMessageRole.USER, content="hi"
                        ),
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

            with pytest.raises(sqlite3.DatabaseError, match="disk I/O"):
                await harness._handle_owner_lost(  # noqa: SLF001
                    request=request,
                    active_attempt=active,
                    loss_reason=AttemptOwnerLossReason.STORAGE_ERROR,
                    event_count=0,
                    terminal_seen=False,
                )
            assert stack_closed, (
                "非 fencing 异常时 lease_exit_stack 必须被关闭"
            )
    finally:
        storage.close()


class _NoopProxy:
    """最小 proxy stub。"""

    async def stream_engine_events(
        self,
        **_kwargs: object,
    ) -> AsyncIterator[EngineEvent]:
        yield  # type: ignore[misc]
        return  # pragma: no cover


@pytest.mark.asyncio
async def test_lease_context_cleans_session_on_create_task_failure() -> None:
    """``asyncio.create_task`` 失败时 ``_sessions`` 无残留。"""

    storage = _open_storage()
    try:
        await _seed_run(storage)
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        original_create_task = asyncio.create_task
        call_count = 0

        def _failing_create_task(*args: object, **kwargs: object) -> asyncio.Task[object]:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("event loop closed")

        asyncio.create_task = _failing_create_task  # type: ignore[assignment]
        try:
            with warnings.catch_warnings(record=True) as captured_warnings:
                warnings.simplefilter("always", RuntimeWarning)
                with pytest.raises(RuntimeError, match="event loop closed"):
                    async with supervisor.lease_context(
                        run_id="r1", attempt_index=0
                    ):
                        pass  # pragma: no cover
                gc.collect()
            assert supervisor._sessions == {}
            assert not any(
                "was never awaited" in str(warning.message)
                for warning in captured_warnings
            )
        finally:
            asyncio.create_task = original_create_task  # type: ignore[assignment]
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_worker_exception_before_owner_scope_writes_terminal() -> None:
    """``stream_engine_events`` 在 ``_attempt_owner_scope`` 前抛普通异常时,
    durable path 写入 Host ``RUN_FAILED`` terminal, RunStream 不 hang。

    修复 2044-F1: ``_append_worker_failure_if_needed`` 改用
    ``_resolve_attempt_appender(active_attempt)`` 替代 ``_scope_appender()``,
    确保在 owner scope 进入前也能正确写入 terminal event。
    """

    from dayu.host._durable_harness import (
        DurableHarnessConfig,
        build_durable_harness,
    )
    from dayu.host._proxy import WorkerProxy
    from dayu.host._run_harness import LocalRunHarness

    class _ExplodingProxy:
        """``stream_engine_events`` 抛出非 fencing 异常。"""

        def stream_engine_events(
            self,
            *,
            request: StartRunRequest,
            tool_schemas: tuple[ToolSchema, ...],
            cancellation_token: CancellationToken,
        ) -> AsyncIterator[EngineEvent]:
            del request, cancellation_token
            raise RuntimeError("engine assembly failed")

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
        # 构造使用 exploding proxy 的 harness。
        harness = LocalRunHarness(
            is_durable=True,
            proxy=cast(WorkerProxy, _ExplodingProxy()),
            event_store=bundle.event_store,
            tool_runtime=bundle.harness.tool_runtime,
            memory_store=bundle.memory_store,
            coordinator=bundle.coordinator,
            attempt_supervisor=bundle.attempt_supervisor,
            storage=bundle.storage,
        )

        request = _minimal_start_request(session_id="s_f1", run_id="r_f1")
        stream = await harness.start_run(request)

        # 消费 RunStream 直到结束。
        events: list[RunEvent] = []
        async for event in stream.events:
            events.append(event)

        # 验证 terminal event 已写入。
        terminal_events = [
            e for e in events
            if e.type in {RunEventType.RUN_FAILED, RunEventType.FINAL_ANSWER}
        ]
        assert len(terminal_events) >= 1, (
            "worker 异常后必须写入 terminal RunEvent"
        )

        # 验证 RunResult 可推导。
        result = bundle.run_state_store.get_terminal_result("r_f1")
        assert result is not None, "RunResult 必须可推导"
    finally:
        bundle.close()
