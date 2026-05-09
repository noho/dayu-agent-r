"""Host P8-S5 ToolRuntime owner fencing 测试。

本测试覆盖 P8-S5 引入的 ToolRuntime fencing 入口:

- :class:`ToolRuntimeOwnerScope` 安装 / 恢复 ContextVar 行为对称, 异常路径
  仍恢复旧值;
- :func:`active_tool_runtime_appender` 在没有 scope 时返回 ``None``,
  ``InMemoryToolRuntime._resolve_appender`` 在该路径下退化为
  :class:`PlainRunEventAppender`;
- 在 scope 内 ``_resolve_appender`` 返回安装的
  :class:`AttemptScopedRunEventAppender`;
- :class:`AttemptScopedRunEventAppender` 在 scope 中接收非 owner run 的 draft
  时, 抛 :class:`AttemptFencingError(reason=OWNER_MISMATCH)`,
  EventLog 不残留 fact, 与 P8-S5 attempt-scoped 写入契约一致。

测试只用真实 supervisor + storage, 不 mock fencing 路径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptFencingReason,
    AttemptLeaseConfig,
)
from dayu.host._attempt_supervisor import (
    AttemptScopedRunEventAppender,
    AttemptSupervisor,
)
from dayu.host._durable_event_store import (
    DurableRunEventStore,
    open_durable_event_store,
)
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._internal_contracts import ExtendedRunState
from dayu.host._run_state_store import AttemptLeaseStore
from dayu.host._tool_runtime import (
    InMemoryToolRuntime,
    PlainRunEventAppender,
    ToolRuntimeOwnerScope,
    active_tool_runtime_appender,
)
from dayu.host.contracts import (
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
)


@dataclass(slots=True)
class _FakeClock:
    """fake UTC clock, 测试主线程显式推进。"""

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


def _open_storage() -> HostStorage:
    """构造内存 SQLite storage 并完成 schema bootstrap。

    :returns: 已 open 的 :class:`HostStorage`。
    :raises sqlite3.DatabaseError: bootstrap 失败时抛出。
    """

    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    return storage


async def _seed_run(storage: HostStorage, *, run_id: str) -> None:
    """预置一行 RUNNING run。

    :param storage: 共享 storage。
    :param run_id: Run id。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: 写入失败透传。
    """

    timestamp = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    async with storage.transaction() as tx:
        tx.execute(
            "INSERT INTO host_runs (run_id, session_id, state, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, "s", ExtendedRunState.RUNNING.value, timestamp, timestamp),
        )


def _build_supervisor(
    *, storage: HostStorage, clock: _FakeClock
) -> AttemptSupervisor:
    """装配真实 supervisor + lease store + event store, 共享同一 storage。

    :param storage: 共享 storage。
    :param clock: fake clock。
    :returns: 已装配的 :class:`AttemptSupervisor`。
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


def _tool_truncated_draft(*, run_id: str) -> RunEventDraft:
    """构造一个 Host-owned ``TOOL_RESULT_TRUNCATED`` draft 用于 scope 测试。

    本测试只关注 owner 校验路径, 因此使用 ``data=None``: scoped append 在
    ``run_id`` 不一致时早早抛 :class:`AttemptFencingError`, 不会进入序列化路径。

    :param run_id: draft 的 run id。
    :returns: :class:`RunEventDraft`。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id="s",
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.TOOL_RESULT_TRUNCATED,
        occurred_at=datetime.now(tz=timezone.utc),
        data=None,  # type: ignore[arg-type]
        source_engine_event_id=None,
    )


@pytest.mark.asyncio
async def test_active_appender_none_outside_scope() -> None:
    """没有 scope 时 ``active_tool_runtime_appender`` 必须返回 ``None``。

    保证 ToolRuntime 在非 durable 路径下不会误把上一个 attempt 的 appender
    当作 active scope。
    """

    assert active_tool_runtime_appender() is None


@pytest.mark.asyncio
async def test_owner_scope_installs_and_restores_appender() -> None:
    """``ToolRuntimeOwnerScope`` 进入时安装, 退出时恢复, 异常路径仍恢复。"""

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            scoped = supervisor.scoped_appender(owner_context)
            assert active_tool_runtime_appender() is None
            async with ToolRuntimeOwnerScope(scoped):
                assert active_tool_runtime_appender() is scoped
            assert active_tool_runtime_appender() is None
            # 异常路径下也应当恢复
            with pytest.raises(RuntimeError):
                async with ToolRuntimeOwnerScope(scoped):
                    assert active_tool_runtime_appender() is scoped
                    raise RuntimeError("boom")
            assert active_tool_runtime_appender() is None
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_inmemory_tool_runtime_resolves_to_plain_outside_scope() -> None:
    """没有安装 scope 时, ToolRuntime helper 退化为 :class:`PlainRunEventAppender`。"""

    storage = _open_storage()
    try:
        clock = _FakeClock()
        del clock
        event_store = DurableRunEventStore(storage=storage)

        async def _noop_executor(*args: object, **kwargs: object) -> object:
            del args, kwargs
            return None

        runtime = InMemoryToolRuntime(
            executor=_noop_executor,  # type: ignore[arg-type]
            event_store=event_store,
        )
        appender = runtime._resolve_appender()  # noqa: SLF001
        assert isinstance(appender, PlainRunEventAppender)
        assert appender.event_store is event_store
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_inmemory_tool_runtime_resolves_to_scoped_inside_scope() -> None:
    """安装 :class:`ToolRuntimeOwnerScope` 后, ToolRuntime helper 拿到 fencing-aware appender。"""

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)

        async def _noop_executor(*args: object, **kwargs: object) -> object:
            del args, kwargs
            return None

        runtime = InMemoryToolRuntime(
            executor=_noop_executor,  # type: ignore[arg-type]
            event_store=supervisor.event_store,
        )
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            scoped = supervisor.scoped_appender(owner_context)
            async with ToolRuntimeOwnerScope(scoped):
                resolved = runtime._resolve_appender()  # noqa: SLF001
                assert isinstance(resolved, AttemptScopedRunEventAppender)
                assert resolved is scoped
            # 退出 scope 后回退
            assert isinstance(
                runtime._resolve_appender(),  # noqa: SLF001
                PlainRunEventAppender,
            )
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_scoped_appender_run_id_mismatch_blocks_tool_runtime_fact() -> None:
    """ToolRuntime fact append 命中 ``run_id`` mismatch 时抛 OWNER_MISMATCH。

    模拟 framework ``fetch_more`` 在 attempt 边界 race 期间想把上一个 cursor
    的 fact 写到错误 run: scoped appender 必须在 ``verify_owner`` 之前先做
    ``run_id`` 校验, EventLog 不残留 stale fact。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        await _seed_run(storage, run_id="r_other")
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)
        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            scoped = supervisor.scoped_appender(owner_context)
            async with ToolRuntimeOwnerScope(scoped):
                with pytest.raises(AttemptFencingError) as excinfo:
                    await scoped.append(_tool_truncated_draft(run_id="r_other"))
                assert (
                    excinfo.value.reason
                    == AttemptFencingReason.OWNER_MISMATCH
                )
                assert (
                    excinfo.value.attempt_id == owner_context.attempt_id
                )
                # 任一 run 都不应残留 fact
                events_r1 = await supervisor.event_store.list_events(
                    run_id="r1", after=None
                )
                assert events_r1 == ()
                events_other = await supervisor.event_store.list_events(
                    run_id="r_other", after=None
                )
                assert events_other == ()
                # 错误文本不含 owner secret 明文
                assert (
                    owner_context.owner_token.value not in str(excinfo.value)
                )
    finally:
        storage.close()
