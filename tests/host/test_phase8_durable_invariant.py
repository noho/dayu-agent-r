"""Host P8-S1 ``LocalRunHarness`` durable invariant 测试。

本模块验证 P8-S1 引入的显式 ``is_durable`` 装配契约:

- ``is_durable=True`` 装配必须满足 supervisor / event_store /
  attempt_state_store / storage 的强约束;违反时 ``__post_init__``
  立即 ``RuntimeError``;
- ``is_durable=False`` 装配为 test-only 路径,禁止注入 supervisor;
- ``is_durable`` 是 keyword-only 必填参数,缺省即 ``TypeError``;
- ``_resolve_attempt_appender`` 在 ``is_durable=True`` 且无 owner_context
  时立即 ``RuntimeError``,绝不退化为 ``PlainRunEventAppender``。

测试只装配真实 storage / event_store / supervisor,不 mock invariant 路径。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host._attempt_lease import AttemptLeaseConfig
from dayu.host._attempt_supervisor import AttemptSupervisor
from dayu.host._durable_event_store import (
    DurableRunEventStore,
    open_durable_event_store,
)
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._proxy import LocalProxy
from dayu.host._run_harness import LocalRunHarness
from dayu.host._run_state_store import AttemptLeaseStore, AttemptStateStore
from dayu.host._tool_runtime import HostToolRuntime
from dayu.host._tool_runtime import PlainRunEventAppender
from dayu.host._worker import EngineWorker
from dayu.host._tool_runtime import ToolRuntimeToolExecutor
from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore


class _FakeClock:
    """fake UTC clock。"""

    def now(self) -> datetime:
        """返回固定 UTC 时间。

        :returns: timezone-aware datetime。
        :raises Exception: 不主动抛出异常。
        """

        return datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)


def _open_durable_storage() -> HostStorage:
    """构造 in-memory durable storage 并完成 schema bootstrap。

    :returns: 已 open 的 :class:`HostStorage`。
    :raises sqlite3.DatabaseError: bootstrap 失败时透传。
    """

    storage = HostStorage(database_path=":memory:")
    open_durable_event_store(storage)
    return storage


def _build_supervisor(storage: HostStorage) -> AttemptSupervisor:
    """构造与 storage 共享的真实 supervisor。

    :param storage: 共享 storage。
    :returns: :class:`AttemptSupervisor`。
    :raises Exception: 不主动抛出异常。
    """

    clock = _FakeClock()
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


def _make_proxy() -> LocalProxy:
    """构造最小 LocalProxy(不真实跑 Engine)。

    :returns: :class:`LocalProxy`。
    :raises Exception: 不主动抛出异常。
    """

    runtime = HostToolRuntime(
        is_durable=False,
        executor=_NoopExec(),  # type: ignore[arg-type]
        event_store=InMemoryRunEventStore(),
    )
    return LocalProxy(worker=EngineWorker(ToolRuntimeToolExecutor(runtime)))


def _make_non_durable_runtime() -> HostToolRuntime:
    """构造非 durable ToolRuntime,与 harness ``is_durable=False`` 同源。

    :returns: ``is_durable=False`` 的 :class:`HostToolRuntime`。
    :raises Exception: 不主动抛出异常。
    """

    return HostToolRuntime(
        is_durable=False,
        executor=_NoopExec(),  # type: ignore[arg-type]
        event_store=InMemoryRunEventStore(),
    )


def _make_durable_runtime(storage: HostStorage) -> HostToolRuntime:
    """构造 durable ToolRuntime,与 harness ``is_durable=True`` 同源。

    :param storage: 共享 storage(传给 :class:`DurableRunEventStore`)。
    :returns: ``is_durable=True`` 的 :class:`HostToolRuntime`。
    :raises Exception: 不主动抛出异常。
    """

    return HostToolRuntime(
        is_durable=True,
        executor=_NoopExec(),  # type: ignore[arg-type]
        event_store=DurableRunEventStore(storage=storage),
    )


class _NoopExec:
    """no-op tool executor 占位。"""

    async def execute(
        self, request: ToolExecutionRequest
    ) -> ToolExecutionOutcome:
        """忽略 request，返回空成功工具结果。

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


def test_durable_requires_supervisor() -> None:
    """``is_durable=True`` 缺 supervisor 时立即 RuntimeError。"""

    storage = _open_durable_storage()
    try:
        with pytest.raises(RuntimeError, match="attempt_supervisor"):
            LocalRunHarness(
                is_durable=True,
                proxy=_make_proxy(),
                event_store=DurableRunEventStore(storage=storage),
                memory_store=FakeInMemoryConversationMemoryStore(),
                attempt_supervisor=None,
                storage=storage,
                tool_runtime=_make_durable_runtime(storage),
            )
    finally:
        storage.close()


def test_durable_rejects_legacy_attempt_state_store() -> None:
    """``is_durable=True`` 注入 P6 legacy attempt_state_store 时 RuntimeError。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        legacy_store = AttemptStateStore(storage=storage, clock=_FakeClock())
        with pytest.raises(RuntimeError, match="attempt_state_store"):
            LocalRunHarness(
                is_durable=True,
                proxy=_make_proxy(),
                event_store=DurableRunEventStore(storage=storage),
                memory_store=FakeInMemoryConversationMemoryStore(),
                attempt_supervisor=supervisor,
                attempt_state_store=legacy_store,
                storage=storage,
                tool_runtime=_make_durable_runtime(storage),
            )
    finally:
        storage.close()


def test_durable_rejects_inmemory_event_store() -> None:
    """``is_durable=True`` 必须使用 :class:`DurableRunEventStore`。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        with pytest.raises(RuntimeError, match="DurableRunEventStore"):
            LocalRunHarness(
                is_durable=True,
                proxy=_make_proxy(),
                event_store=InMemoryRunEventStore(),
                memory_store=FakeInMemoryConversationMemoryStore(),
                attempt_supervisor=supervisor,
                storage=storage,
                tool_runtime=_make_durable_runtime(storage),
            )
    finally:
        storage.close()


def test_durable_requires_storage() -> None:
    """``is_durable=True`` 缺 storage 时 RuntimeError。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        with pytest.raises(RuntimeError, match="storage"):
            LocalRunHarness(
                is_durable=True,
                proxy=_make_proxy(),
                event_store=DurableRunEventStore(storage=storage),
                memory_store=FakeInMemoryConversationMemoryStore(),
                attempt_supervisor=supervisor,
                storage=None,
                tool_runtime=_make_durable_runtime(storage),
            )
    finally:
        storage.close()


def test_durable_requires_tool_runtime() -> None:
    """``is_durable=True`` 缺 tool_runtime 时 RuntimeError。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        with pytest.raises(RuntimeError, match="tool_runtime"):
            LocalRunHarness(
                is_durable=True,
                proxy=_make_proxy(),
                event_store=DurableRunEventStore(storage=storage),
                memory_store=FakeInMemoryConversationMemoryStore(),
                attempt_supervisor=supervisor,
                storage=storage,
                tool_runtime=None,
            )
    finally:
        storage.close()


def test_durable_rejects_non_durable_tool_runtime() -> None:
    """``is_durable=True`` 与 non-durable ToolRuntime 装配冲突时 RuntimeError。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        with pytest.raises(RuntimeError, match="tool_runtime.is_durable"):
            LocalRunHarness(
                is_durable=True,
                proxy=_make_proxy(),
                event_store=DurableRunEventStore(storage=storage),
                memory_store=FakeInMemoryConversationMemoryStore(),
                attempt_supervisor=supervisor,
                storage=storage,
                tool_runtime=_make_non_durable_runtime(),
            )
    finally:
        storage.close()


def test_non_durable_rejects_supervisor() -> None:
    """``is_durable=False`` 装配禁止注入 supervisor。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        with pytest.raises(RuntimeError, match="non-durable"):
            LocalRunHarness(
                is_durable=False,
                proxy=_make_proxy(),
                memory_store=FakeInMemoryConversationMemoryStore(),
                attempt_supervisor=supervisor,
            )
    finally:
        storage.close()


def test_non_durable_rejects_durable_tool_runtime() -> None:
    """``is_durable=False`` 与 durable ToolRuntime 装配冲突时 RuntimeError。"""

    storage = _open_durable_storage()
    try:
        with pytest.raises(RuntimeError, match="tool_runtime.is_durable"):
            LocalRunHarness(
                is_durable=False,
                proxy=_make_proxy(),
                memory_store=FakeInMemoryConversationMemoryStore(),
                tool_runtime=_make_durable_runtime(storage),
            )
    finally:
        storage.close()


def test_durable_valid_construction() -> None:
    """完整 durable invariant 全部满足时构造成功。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        harness = LocalRunHarness(
            is_durable=True,
            proxy=_make_proxy(),
            event_store=DurableRunEventStore(storage=storage),
            memory_store=FakeInMemoryConversationMemoryStore(),
            attempt_supervisor=supervisor,
            storage=storage,
            tool_runtime=_make_durable_runtime(storage),
        )
        assert harness.is_durable is True
    finally:
        storage.close()


def test_non_durable_valid_construction() -> None:
    """非 durable 路径最小装配构造成功。"""

    harness = LocalRunHarness(
        is_durable=False,
        proxy=_make_proxy(),
        memory_store=FakeInMemoryConversationMemoryStore(),
        tool_runtime=_make_non_durable_runtime(),
    )
    assert harness.is_durable is False


def test_is_durable_is_keyword_only_required() -> None:
    """缺省 ``is_durable`` 必须 ``TypeError`` (keyword-only required)。"""

    with pytest.raises(TypeError):
        LocalRunHarness(  # type: ignore[call-arg]
            proxy=_make_proxy(),
            memory_store=FakeInMemoryConversationMemoryStore(),
        )


@pytest.mark.asyncio
async def test_resolve_attempt_appender_durable_no_owner_raises() -> None:
    """``is_durable=True`` 且无 owner_context 时 ``_resolve_attempt_appender`` RuntimeError。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        harness = LocalRunHarness(
            is_durable=True,
            proxy=_make_proxy(),
            event_store=DurableRunEventStore(storage=storage),
            memory_store=FakeInMemoryConversationMemoryStore(),
            attempt_supervisor=supervisor,
            storage=storage,
            tool_runtime=_make_durable_runtime(storage),
        )
        with pytest.raises(RuntimeError, match="AttemptOwnerContext"):
            harness._resolve_attempt_appender(None)  # noqa: SLF001
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_scope_appender_durable_without_owner_scope_raises() -> None:
    """durable harness 无 owner scope 时 ``_scope_appender`` 必须 fail fast。"""

    storage = _open_durable_storage()
    try:
        supervisor = _build_supervisor(storage)
        harness = LocalRunHarness(
            is_durable=True,
            proxy=_make_proxy(),
            event_store=DurableRunEventStore(storage=storage),
            memory_store=FakeInMemoryConversationMemoryStore(),
            attempt_supervisor=supervisor,
            storage=storage,
            tool_runtime=_make_durable_runtime(storage),
        )
        with pytest.raises(RuntimeError, match="ToolRuntimeOwnerScope"):
            harness._scope_appender()  # noqa: SLF001
    finally:
        storage.close()


@pytest.mark.asyncio
async def test_scope_appender_non_durable_without_owner_scope_uses_plain_fallback() -> None:
    """非 durable test-only 路径无 owner scope 时仍返回 plain appender。"""

    harness = LocalRunHarness(
        is_durable=False,
        proxy=_make_proxy(),
        memory_store=FakeInMemoryConversationMemoryStore(),
        tool_runtime=_make_non_durable_runtime(),
    )

    appender = harness._scope_appender()  # noqa: SLF001
    assert isinstance(appender, PlainRunEventAppender)
