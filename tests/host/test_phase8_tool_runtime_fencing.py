"""Host P8-S5 ToolRuntime owner fencing 测试。

本测试覆盖 P8-S5 引入的 ToolRuntime fencing 入口:

- :class:`ToolRuntimeOwnerScope` 安装 / 恢复 ContextVar 行为对称, 异常路径
  仍恢复旧值;
- :func:`active_tool_runtime_appender` 在没有 scope 时返回 ``None``,
  ``HostToolRuntime._resolve_appender`` 在该路径下退化为
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

from dayu.contracts import JsonValue, ToolTruncateSpec
from dayu.contracts.tool_call import (
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
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
from dayu.host._internal_contracts import (
    AttemptState,
    ExtendedRunState,
    FencingToken,
)
from dayu.host._run_state_store import AttemptLeaseStore
from dayu.host._tool_runtime import (
    HostToolRuntime,
    PlainRunEventAppender,
    ToolRuntimeOwnerScope,
    ToolRuntimeEventAppender,
    active_tool_runtime_appender,
    _CursorRecord,
)
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    ToolFetchMoreRequest,
    ToolFetchMoreSucceededResult,
    ToolRuntimeCursor,
)


@dataclass(frozen=True, slots=True)
class _Token:
    """测试用永不取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已经取消。

        :returns: 始终为 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


@dataclass(slots=True)
class _CompletedExecutor:
    """返回固定工具结果的 fake executor。"""

    value: JsonValue

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """返回成功工具结果。

        :param request: 工具执行请求。
        :returns: 成功 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del request
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=self.value,
                truncation=None,
                meta=None,
            )
        )


class _NoopExecutor:
    """返回空成功结果的 fake executor。"""

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """返回空成功工具结果。

        :param request: 工具执行请求。
        :returns: 空成功 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del request
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=None,
                truncation=None,
                meta=None,
            )
        )


class _FencingAppender:
    """始终抛 :class:`AttemptFencingError` 的 appender。"""

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """模拟 owner CAS 在 ToolRuntime fact append path 被 fenced。

        :param draft: 待写入的 RunEvent 草稿。
        :returns: 永不返回。
        :raises AttemptFencingError: 始终抛出 typed fencing 错误。
        """

        raise AttemptFencingError(
            attempt_id="attempt-fenced",
            run_id=draft.run_id,
            reason=AttemptFencingReason.OWNER_MISMATCH,
            current_state=AttemptState.RUNNING,
            owner_id="owner-other",
            fencing_token=FencingToken(value=1),
        )


class _FencingOnCompletedAppender:
    """仅在 ``TOOL_FETCH_MORE_COMPLETED`` 时抛 :class:`AttemptFencingError` 的 appender。

    允许 ``TOOL_FETCH_MORE_REQUESTED`` 正常通过, 模拟 completed fact
    append 路径被 fenced 的场景。
    """

    def __init__(self) -> None:
        """初始化。"""
        self.appended_types: list[RunEventType] = []

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """按 draft type 决定通过或 fenced。

        :param draft: 待写入的 RunEvent 草稿。
        :returns: ``TOOL_FETCH_MORE_REQUESTED`` 时返回 fake event。
        :raises AttemptFencingError: ``TOOL_FETCH_MORE_COMPLETED`` 时抛出。
        """

        self.appended_types.append(draft.type)
        if draft.type is RunEventType.TOOL_FETCH_MORE_COMPLETED:
            raise AttemptFencingError(
                attempt_id="attempt-fenced-on-completed",
                run_id=draft.run_id,
                reason=AttemptFencingReason.OWNER_MISMATCH,
                current_state=AttemptState.RUNNING,
                owner_id="owner-other",
                fencing_token=FencingToken(value=1),
            )
        return RunEvent(
            cursor=RunEventCursor(sequence=0),
            run_id=draft.run_id,
            session_id=draft.session_id,
            kind=draft.kind,
            source=draft.source,
            type=draft.type,
            occurred_at=draft.occurred_at,
            data=draft.data,
            source_engine_event_id=draft.source_engine_event_id,
        )


class _FencingOnIssuedAppender:
    """仅在 ``TOOL_CURSOR_ISSUED`` 时抛 :class:`AttemptFencingError` 的 appender。

    允许 REQUESTED 和 COMPLETED 通过, 模拟 issued fact append 路径被
    fenced 的场景。注意: COMPLETED fact 已写入 EventLog, ISSUED 未写入,
    属于 partial fact 风险。
    """

    def __init__(self) -> None:
        """初始化。"""
        self.appended_types: list[RunEventType] = []

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """按 draft type 决定通过或 fenced。

        :param draft: 待写入的 RunEvent 草稿。
        :returns: 非 ISSUED 时返回 fake event。
        :raises AttemptFencingError: ``TOOL_CURSOR_ISSUED`` 时抛出。
        """

        self.appended_types.append(draft.type)
        if draft.type is RunEventType.TOOL_CURSOR_ISSUED:
            raise AttemptFencingError(
                attempt_id="attempt-fenced-on-issued",
                run_id=draft.run_id,
                reason=AttemptFencingReason.OWNER_MISMATCH,
                current_state=AttemptState.RUNNING,
                owner_id="owner-other",
                fencing_token=FencingToken(value=1),
            )
        return RunEvent(
            cursor=RunEventCursor(sequence=0),
            run_id=draft.run_id,
            session_id=draft.session_id,
            kind=draft.kind,
            source=draft.source,
            type=draft.type,
            occurred_at=draft.occurred_at,
            data=draft.data,
            source_engine_event_id=draft.source_engine_event_id,
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


def _tool_request() -> ToolExecutionRequest:
    """构造会触发截断 fact append 的工具执行请求。

    :returns: :class:`ToolExecutionRequest`。
    :raises Exception: 不主动抛出异常。
    """

    return ToolExecutionRequest(
        call=ToolCallRequest(
            tool_call_id="tc-fenced",
            name="demo",
            arguments={},
            index_in_iteration=0,
            provider_state=None,
        ),
        context=ToolExecutionContext(
            run_id="r1",
            session_id="s",
            iteration_id="iter-1",
            tool_call_id="tc-fenced",
            index_in_iteration=0,
            timeout_seconds=None,
            cancellation_token=_Token(),
            correlation_id=None,
        ),
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

        runtime = HostToolRuntime(
            is_durable=False,
            executor=_NoopExecutor(),
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

        runtime = HostToolRuntime(
            is_durable=False,
            executor=_NoopExecutor(),
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
async def test_execute_tool_call_propagates_attempt_fencing_error_from_append_path() -> None:
    """ToolRuntime append path 的 fencing 必须透传，不能转成普通工具失败。

    回归 PR #40 1939-F1：``execute_tool_call`` 的 catch-all 曾把
    ``AttemptFencingError`` 吞成 ``ToolFailedOutcome``，导致 Host harness
    看不到 owner-lost 信号。本测试让截断成功后的 fact append 抛 fencing，
    断言异常原样透传。
    """

    storage = _open_storage()
    try:
        runtime = HostToolRuntime(
            is_durable=False,
            executor=_CompletedExecutor(value=[1, 2, 3]),
            event_store=DurableRunEventStore(storage=storage),
            truncate_specs={
                "demo": ToolTruncateSpec(
                    enabled=True,
                    strategy="list_items",
                    limits={"max_items": 1},
                    target_field=None,
                    field_path=None,
                    ttl_seconds=30,
                )
            },
            token_generator=lambda: "cursor-fenced",
        )
        appender: ToolRuntimeEventAppender = _FencingAppender()
        async with ToolRuntimeOwnerScope(appender):
            with pytest.raises(AttemptFencingError) as excinfo:
                await runtime.execute_tool_call(_tool_request())
        assert excinfo.value.reason is AttemptFencingReason.OWNER_MISMATCH
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


def _build_cursor_record(
    *,
    cursor_value: str,
    run_id: str,
    session_id: str,
    tool_call_id: str,
) -> _CursorRecord:
    """构造一个最小可用的 ``_CursorRecord`` 用于 fetch_more 端到端 fencing 测试。

    本工厂仅用于 P8-S5 deferred 端到端 fenced 复现; 数据载荷选用足以让
    framework ``fetch_more`` 进入 ``_append_fetch_requested`` append 路径
    的最小集合 (列表数据 + offset, 仍有剩余)。

    :param cursor_value: cursor 原文。
    :param run_id: cursor 绑定 run id。
    :param session_id: cursor 绑定 session id。
    :param tool_call_id: cursor 绑定 tool_call_id。
    :returns: 内存态 :class:`_CursorRecord`。
    :raises Exception: 不主动抛出异常。
    """

    return _CursorRecord(
        cursor=cursor_value,
        cursor_fingerprint=f"fp-{cursor_value}",
        scope_token="scope-token",
        scope_hash="scope-hash",
        session_id=session_id,
        run_id=run_id,
        tool_call_id=tool_call_id,
        tool_name="my_tool",
        strategy="length",
        unit="char",
        limit=4,
        total=10,
        data="abcdefghij",
        offset=4,
        template=None,
        field_path=None,
        created_at_monotonic=0.0,
        expires_at_monotonic=1e9,
        ttl_seconds=600,
        parent_cursor_fingerprint=None,
    )


@pytest.mark.asyncio
async def test_fetch_more_under_owner_scope_appends_facts_normally() -> None:
    """合法 owner: ``fetch_more`` 通过 scoped appender 写入 facts。

    cursor 绑定与 owner scope 同一 ``run_id`` 时, ``_append_fetch_requested``
    / ``_append_fetch_completed`` 走 :class:`AttemptScopedRunEventAppender`,
    EventLog 命中 ``TOOL_FETCH_MORE_REQUESTED`` / ``TOOL_FETCH_MORE_COMPLETED``
    并可附带派生 cursor 的 ``TOOL_CURSOR_ISSUED`` fact。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)

        runtime = HostToolRuntime(
            is_durable=False,
            executor=_NoopExecutor(),
            event_store=supervisor.event_store,
        )
        # 构造一个 cursor 绑定到 run_id=r1, 与 owner scope 一致。
        record = _build_cursor_record(
            cursor_value="cursor-legal",
            run_id="r1",
            session_id="s",
            tool_call_id="tc-1",
        )
        runtime._records_by_cursor[record.cursor] = record  # noqa: SLF001

        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            scoped = supervisor.scoped_appender(owner_context)
            async with ToolRuntimeOwnerScope(scoped):
                request = ToolFetchMoreRequest(
                    session_id="s",
                    run_id="r1",
                    iteration_id="iter-1",
                    tool_call_id="tc-1",
                    cursor=ToolRuntimeCursor(
                        value=record.cursor,
                        fingerprint=record.cursor_fingerprint,
                    ),
                    scope_token=record.scope_token,
                    limit=2,
                )
                result = await runtime._fetch_more(request)  # noqa: SLF001
        # 期望: 至少出现 TOOL_FETCH_MORE_REQUESTED 与 TOOL_FETCH_MORE_COMPLETED;
        # 仍有剩余时还会出现 TOOL_CURSOR_ISSUED。
        events = await supervisor.event_store.list_events(
            run_id="r1", after=None
        )
        types = {event.type for event in events}
        assert RunEventType.TOOL_FETCH_MORE_REQUESTED in types
        assert RunEventType.TOOL_FETCH_MORE_COMPLETED in types
        # 无 fencing 异常: result 不应是 failed (binding / fencing 都 OK)。
        assert result is not None
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_fetch_more_run_id_mismatch_is_fenced_end_to_end() -> None:
    """旧 cursor 跨 run race: ``fetch_more`` 必须在 fact append 时被 fencing 拒绝。

    cursor 绑定到 ``r_other``, owner scope 绑定到 ``r1``;
    ``request.run_id == r_other`` 通过 cursor binding 校验后,
    ``_append_fetch_requested`` 的 draft.run_id == r_other != owner.run_id == r1,
    :class:`AttemptScopedRunEventAppender._verify_run_id_matches` 抛
    :class:`AttemptFencingError(reason=OWNER_MISMATCH)`, EventLog 不残留任何
    fetch_more fact。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        await _seed_run(storage, run_id="r_other")
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)

        runtime = HostToolRuntime(
            is_durable=False,
            executor=_NoopExecutor(),
            event_store=supervisor.event_store,
        )
        # 旧 cursor 绑定到 r_other (上一个 attempt 留下的); request 也指向
        # r_other, 因此 cursor binding 不会拒绝, 但 owner scope 仍是 r1。
        record = _build_cursor_record(
            cursor_value="cursor-stale",
            run_id="r_other",
            session_id="s",
            tool_call_id="tc-stale",
        )
        runtime._records_by_cursor[record.cursor] = record  # noqa: SLF001

        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            scoped = supervisor.scoped_appender(owner_context)
            async with ToolRuntimeOwnerScope(scoped):
                request = ToolFetchMoreRequest(
                    session_id="s",
                    run_id="r_other",
                    iteration_id="iter-stale",
                    tool_call_id="tc-stale",
                    cursor=ToolRuntimeCursor(
                        value=record.cursor,
                        fingerprint=record.cursor_fingerprint,
                    ),
                    scope_token=record.scope_token,
                    limit=2,
                )
                with pytest.raises(AttemptFencingError) as excinfo:
                    await runtime._fetch_more(request)  # noqa: SLF001
                assert (
                    excinfo.value.reason
                    is AttemptFencingReason.OWNER_MISMATCH
                )
                assert (
                    owner_context.owner_token.value
                    not in str(excinfo.value)
                )
        # 端到端断言: 任一 run 都不应残留 fetch_more fact。
        events_r1 = await supervisor.event_store.list_events(
            run_id="r1", after=None
        )
        assert events_r1 == ()
        events_other = await supervisor.event_store.list_events(
            run_id="r_other", after=None
        )
        assert events_other == ()
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_durable_runtime_without_owner_scope_fails_fast() -> None:
    """P8-S1: durable runtime 在 ContextVar 缺 owner scope 时立即 RuntimeError。

    durable 装配 (``is_durable=True``) 显式禁止 ToolRuntime 退化为
    :class:`PlainRunEventAppender`; 任何工具调用走到 ``_resolve_appender``
    时缺失 :class:`ToolRuntimeOwnerScope` 必须立即 ``RuntimeError`` fail
    fast, 杜绝 owner-less attempt-scoped fact append 的可能。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        event_store = DurableRunEventStore(storage=storage)

        runtime = HostToolRuntime(
            is_durable=True,
            executor=_NoopExecutor(),
            event_store=event_store,
        )
        with pytest.raises(RuntimeError, match="ToolRuntimeOwnerScope"):
            runtime._resolve_appender()  # noqa: SLF001

        # execute_tool_call 路径下也必须 fail fast: 构造一个最小 cursor 让
        # 流程进入 fact append, 没有 owner scope 时 _resolve_appender
        # 立即抛 RuntimeError。
        record = _build_cursor_record(
            cursor_value="cursor-no-scope",
            run_id="r1",
            session_id="s",
            tool_call_id="tc-no-scope",
        )
        runtime._records_by_cursor[record.cursor] = record  # noqa: SLF001
        request = ToolFetchMoreRequest(
            session_id="s",
            run_id="r1",
            iteration_id="iter-no-scope",
            tool_call_id="tc-no-scope",
            cursor=ToolRuntimeCursor(
                value=record.cursor,
                fingerprint=record.cursor_fingerprint,
            ),
            scope_token=record.scope_token,
            limit=2,
        )
        with pytest.raises(RuntimeError, match="ToolRuntimeOwnerScope"):
            await runtime._fetch_more(request)  # noqa: SLF001
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_fetch_more_completed_fencing_preserves_old_cursor() -> None:
    """``_append_fetch_completed`` 抛 :class:`AttemptFencingError` 时旧 cursor 必须保留。

    回归 PR #40 2044-F4: ``_fetch_more`` 使用纯构建 + 延迟 commit 模式,
    completed fact append 被 fenced 时内存 maps 未变更 — 旧 cursor 仍可
    再次 fetch, next cursor 不存在, EventLog 无 completed / issued 残留。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)

        # 使用仅在 completed 时 fenced 的 appender。
        fencing_appender = _FencingOnCompletedAppender()

        runtime = HostToolRuntime(
            is_durable=False,
            executor=_NoopExecutor(),
            event_store=supervisor.event_store,
        )
        # 构造 offset=4, total=10, limit=4 → new_offset=8, has_more=True。
        record = _build_cursor_record(
            cursor_value="cursor-rollback",
            run_id="r1",
            session_id="s",
            tool_call_id="tc-rollback",
        )
        runtime._records_by_cursor[record.cursor] = record  # noqa: SLF001
        runtime._cursor_by_fingerprint[record.cursor_fingerprint] = record.cursor  # noqa: SLF001

        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            del owner_context
            async with ToolRuntimeOwnerScope(fencing_appender):
                request = ToolFetchMoreRequest(
                    session_id="s",
                    run_id="r1",
                    iteration_id="iter-rollback",
                    tool_call_id="tc-rollback",
                    cursor=ToolRuntimeCursor(
                        value=record.cursor,
                        fingerprint=record.cursor_fingerprint,
                    ),
                    scope_token=record.scope_token,
                    limit=4,
                )
                with pytest.raises(AttemptFencingError):
                    await runtime._fetch_more(request)  # noqa: SLF001

        # 断言: 旧 cursor 仍保留在内存中, 可再次 fetch。
        assert record.cursor in runtime._records_by_cursor  # noqa: SLF001
        assert (
            runtime._cursor_by_fingerprint.get(record.cursor_fingerprint)  # noqa: SLF001
            == record.cursor
        )
        # 断言: next cursor 不存在 (纯构建未注册到 maps)。
        assert len(runtime._records_by_cursor) == 1  # noqa: SLF001
        # 断言: 旧 cursor 仍可再次 fetch (模拟重试)。
        async with supervisor.lease_context(
            run_id="r1", attempt_index=1
        ) as owner_context2:
            del owner_context2
            async with ToolRuntimeOwnerScope(fencing_appender):
                request2 = ToolFetchMoreRequest(
                    session_id="s",
                    run_id="r1",
                    iteration_id="iter-retry",
                    tool_call_id="tc-rollback",
                    cursor=ToolRuntimeCursor(
                        value=record.cursor,
                        fingerprint=record.cursor_fingerprint,
                    ),
                    scope_token=record.scope_token,
                    limit=4,
                )
                # 重试也会在 completed 时被 fenced (同一个 fake appender)。
                with pytest.raises(AttemptFencingError):
                    await runtime._fetch_more(request2)  # noqa: SLF001
        # 重试后旧 cursor 仍然保留。
        assert record.cursor in runtime._records_by_cursor  # noqa: SLF001
        # 断言: EventLog 无任何 fetch_more fact 残留。
        events = await supervisor.event_store.list_events(
            run_id="r1", after=None
        )
        fetch_types = {e.type for e in events}
        assert RunEventType.TOOL_FETCH_MORE_COMPLETED not in fetch_types
        assert RunEventType.TOOL_CURSOR_ISSUED not in fetch_types
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_fetch_more_issued_fencing_preserves_old_cursor() -> None:
    """``_append_cursor_issued`` 抛 :class:`AttemptFencingError` 时旧 cursor 仍保留。

    已知 partial fact 风险: COMPLETED fact 已写入 EventLog, ISSUED fact 未
    写入。这是现有 EventLog 多 fact append 非原子的固有限制，归入
    migration residual risk。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)

        # 使用仅在 issued 时 fenced 的 appender。
        fencing_appender = _FencingOnIssuedAppender()

        runtime = HostToolRuntime(
            is_durable=False,
            executor=_NoopExecutor(),
            event_store=supervisor.event_store,
        )
        record = _build_cursor_record(
            cursor_value="cursor-issued-fence",
            run_id="r1",
            session_id="s",
            tool_call_id="tc-issued-fence",
        )
        runtime._records_by_cursor[record.cursor] = record  # noqa: SLF001
        runtime._cursor_by_fingerprint[record.cursor_fingerprint] = record.cursor  # noqa: SLF001

        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            del owner_context
            async with ToolRuntimeOwnerScope(fencing_appender):
                request = ToolFetchMoreRequest(
                    session_id="s",
                    run_id="r1",
                    iteration_id="iter-issued-fence",
                    tool_call_id="tc-issued-fence",
                    cursor=ToolRuntimeCursor(
                        value=record.cursor,
                        fingerprint=record.cursor_fingerprint,
                    ),
                    scope_token=record.scope_token,
                    limit=4,
                )
                with pytest.raises(AttemptFencingError):
                    await runtime._fetch_more(request)  # noqa: SLF001

        # 断言: 旧 cursor 仍保留, next cursor 未注册。
        assert record.cursor in runtime._records_by_cursor  # noqa: SLF001
        assert len(runtime._records_by_cursor) == 1  # noqa: SLF001
        # 断言: appender 看到了 COMPLETED 和 ISSUED (ISSUED 被拒绝)。
        assert RunEventType.TOOL_FETCH_MORE_COMPLETED in fencing_appender.appended_types
        assert RunEventType.TOOL_CURSOR_ISSUED in fencing_appender.appended_types
        # 已知 partial fact: COMPLETED 已写入, ISSUED 未写入。
        # 这是 EventLog 多 fact append 非原子的固有限制。
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_fetch_more_success_path_old_removed_next_registered() -> None:
    """成功路径: 旧 cursor 删除, next cursor 注册, 可继续 fetch。

    验证纯构建 + 延迟 commit 模式在正常路径下行为正确。
    """

    storage = _open_storage()
    try:
        await _seed_run(storage, run_id="r1")
        clock = _FakeClock()
        supervisor = _build_supervisor(storage=storage, clock=clock)

        runtime = HostToolRuntime(
            is_durable=False,
            executor=_NoopExecutor(),
            event_store=supervisor.event_store,
        )
        # 使用 list_items 策略 + list 数据，确保 _build_chunk 返回非零 chunk。
        # offset=2, total=6, limit=2 → chunk=[3,4], chunk_size=2,
        # new_offset=4, has_more=True。
        record = _CursorRecord(
            cursor="cursor-success",
            cursor_fingerprint="fp-cursor-success",
            scope_token="scope-token",
            scope_hash="scope-hash",
            session_id="s",
            run_id="r1",
            tool_call_id="tc-success",
            tool_name="my_tool",
            strategy="list_items",
            unit="item",
            limit=2,
            total=6,
            data=[1, 2, 3, 4, 5, 6],
            offset=2,
            template=None,
            field_path=None,
            created_at_monotonic=0.0,
            expires_at_monotonic=1e9,
            ttl_seconds=600,
            parent_cursor_fingerprint=None,
        )
        runtime._records_by_cursor[record.cursor] = record  # noqa: SLF001
        runtime._cursor_by_fingerprint[record.cursor_fingerprint] = record.cursor  # noqa: SLF001

        async with supervisor.lease_context(
            run_id="r1", attempt_index=0
        ) as owner_context:
            scoped = supervisor.scoped_appender(owner_context)
            async with ToolRuntimeOwnerScope(scoped):
                request = ToolFetchMoreRequest(
                    session_id="s",
                    run_id="r1",
                    iteration_id="iter-success",
                    tool_call_id="tc-success",
                    cursor=ToolRuntimeCursor(
                        value=record.cursor,
                        fingerprint=record.cursor_fingerprint,
                    ),
                    scope_token=record.scope_token,
                    limit=2,
                )
                result = await runtime._fetch_more(request)  # noqa: SLF001

        # 断言: 旧 cursor 已删除。
        assert record.cursor not in runtime._records_by_cursor  # noqa: SLF001
        # 断言: next cursor 已注册 (has_more=True → 有 next cursor)。
        assert isinstance(result, ToolFetchMoreSucceededResult)
        assert result.truncation is not None
        next_cursor_value = result.truncation.value
        assert next_cursor_value in runtime._records_by_cursor  # noqa: SLF001
        # 断言: next cursor offset 正确推进。
        next_record = runtime._records_by_cursor[next_cursor_value]  # noqa: SLF001
        assert next_record.offset == 4
        assert next_record.total == 6
        # 断言: EventLog 有 COMPLETED 和 ISSUED。
        events = await supervisor.event_store.list_events(
            run_id="r1", after=None
        )
        types = {e.type for e in events}
        assert RunEventType.TOOL_FETCH_MORE_COMPLETED in types
        assert RunEventType.TOOL_CURSOR_ISSUED in types
    finally:
        storage.close()
