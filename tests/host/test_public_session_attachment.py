"""WU-CTX-04 public Session attachment owner-boundary 测试。"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
import sys
import threading
from contextlib import suppress
from datetime import UTC, datetime
from collections.abc import AsyncIterator
from typing import cast

import pytest

import dayu.host.dispatch as host_dispatch
import dayu.host.session_attachment as session_attachment_module
from dayu.host import (
    CancelMode,
    CancelRunRequest,
    CloseSessionRequest,
    DrainOutboxTerminalItemsRequest,
    FollowupSnapshot,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostSessionAccessMode,
    HostSessionAttachment,
    HostSessionAttachmentConflictDetail,
    HostSessionAttachmentConflictReason,
    HostSessionMutationErrorDetail,
    HostSessionMutationRejectionReason,
    HostTerminalStatus,
    AttemptDispatchSnapshot,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    OpenHostOptions,
    OutboxTerminalCursor,
    ReplayRunRequest,
    RetryRunRequest,
    RunStatus,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.command import HostCommandHandle
from dayu.host._execution_health import HostExecutionHealthState
from dayu.host.api import LocalWorkerHandle
from dayu.host.dispatch import HostDispatchScheduler, PendingDispatchRecord
from dayu.host.durable.liveness import (
    HostInstanceStatus,
    read_host_instance,
)
from dayu.host.open_host import _PublicHostHandle, _submit_followup
from dayu.host.recovery import (
    SessionAttachmentRecoveryPolicy,
    SessionAttachmentRecoveryScanResult,
    SessionAttachmentRecoveryScanner,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.host.session_attachment import SessionWorkLease
from dayu.runtime.native_mutex import StrictNativeMutexHandle
from tests.host.public_smoke_support import (
    FinalAnswerWorkerFactory,
    close_attachment_shielded,
    deterministic_runner_spec,
    ensure_request,
    followup_request,
    host_context,
    open_host_options,
    wait_for_status,
)


def _options(
    tmp_path: pathlib.Path,
    factory: LocalEngineWorkerFactory,
) -> OpenHostOptions:
    """构造 public attachment 测试用 opener options。

    :param tmp_path: pytest 临时目录。
    :param factory: deterministic worker factory。
    :returns: public Host opener options。
    :raises Exception: options 构造失败时透传。
    """

    return open_host_options(
        tmp_path,
        runner_spec=deterministic_runner_spec("attachment-public-model"),
        worker_factory=factory,
        allow_tool_calls=False,
    )


def _event_count(db_path: pathlib.Path) -> int:
    """统计 durable EventLog row 数。

    :param db_path: Host SQLite 路径。
    :returns: EventLog row 数。
    :raises Exception: SQLite 查询失败时透传。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            f"SELECT COUNT(*) FROM {TABLE_EVENT_LOG}"
        ).fetchone()
    assert row is not None
    return int(row[0])


def _assert_mutation_rejection(
    error: HostApiError,
    *,
    session_id: str,
    reason: HostSessionMutationRejectionReason,
    actual_mode: HostSessionAccessMode | None,
) -> None:
    """断言 public mutation gate 的精确 typed detail。

    :param error: 捕获到的 public Host 错误。
    :param session_id: 预期 Session id。
    :param reason: 预期拒绝原因。
    :param actual_mode: 当前 attachment mode；缺失时为 ``None``。
    :returns: ``None``。
    :raises AssertionError: public contract 漂移时抛出。
    """

    assert error.code is HostApiErrorCode.PERMISSION_DENIED
    assert error.retryable is False
    assert error.detail == HostSessionMutationErrorDetail(
        kind="session_mutation_access",
        session_id=session_id,
        reason=reason,
        required_mode=HostSessionAccessMode.READ_WRITE,
        actual_mode=actual_mode,
    )


class _FailOnceMandatoryCloseHandle:
    """首次 mandatory close 失败、重试成功的残余 worker handle。"""

    def __init__(self) -> None:
        """初始化 close 计数与关闭状态。

        :returns: ``None``。
        """

        self.close_count = 0
        self.closed = False

    @property
    def local_worker_id(self) -> str:
        """返回稳定测试 worker id。

        :returns: worker id。
        """

        return "attachment-mandatory-close-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """返回空事件流。

        :returns: 空异步迭代器。
        """

        if False:
            yield cast(EngineEvent, None)

    def on_cancel(self, reason: str) -> None:
        """忽略未注册残余 handle 的取消 hook。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason

    async def close(self) -> None:
        """首次模拟 mandatory cleanup 失败，重试成功。

        :returns: ``None``。
        :raises RuntimeError: 首次调用模拟 handle close 失败。
        """

        self.close_count += 1
        if self.close_count == 1:
            raise RuntimeError("public mandatory handle close failed")
        self.closed = True


class _DelayedFinalAnswerHandle:
    """把 deterministic final events 延迟到测试显式放行的 handle。"""

    def __init__(
        self,
        inner: LocalWorkerHandle,
        *,
        factory: "_DelayedFinalAnswerWorkerFactory",
    ) -> None:
        """保存底层 handle 与事件 barrier。

        :param inner: deterministic final-answer handle。
        :param factory: events barrier 与 cleanup 计数 owner。
        :returns: ``None``。
        """

        self._inner = inner
        self._factory = factory

    @property
    def local_worker_id(self) -> str:
        """返回底层 worker id。

        :returns: worker id。
        """

        return self._inner.local_worker_id

    async def events(self) -> AsyncIterator[EngineEvent]:
        """建立 stable Attempt 后等待测试放行 final events。

        :returns: 底层 deterministic event stream。
        """

        self._factory.events_started.set()
        await self._factory.events_release.wait()
        async for event in self._inner.events():
            yield event

    def on_cancel(self, reason: str) -> None:
        """转发 lifecycle cancel hook。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self._factory.cancel_count += 1
        self._inner.on_cancel(reason)

    async def close(self) -> None:
        """关闭底层 handle。

        :returns: ``None``。
        :raises Exception: 底层 close 失败时透传。
        """

        self._factory.handle_close_count += 1
        await self._inner.close()


class _DelayedFinalAnswerWorker:
    """接受 dispatch 后返回 delayed final-answer handle。"""

    def __init__(self, factory: "_DelayedFinalAnswerWorkerFactory") -> None:
        """保存所属 factory。

        :param factory: barrier 与 delegate owner。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """委托 deterministic provider 并包装 event barrier。

        :param snapshot: dispatch snapshot。
        :param request: Engine run request。
        :returns: delayed worker handle。
        :raises Exception: delegate accept 失败时透传。
        """

        delegate = self._factory.delegate.create_worker(snapshot)
        inner = await delegate.accept(snapshot, request)
        return _DelayedFinalAnswerHandle(
            inner,
            factory=self._factory,
        )


class _DelayedFinalAnswerWorkerFactory:
    """构造 stable Attempt barrier 的 deterministic worker factory。"""

    def __init__(self) -> None:
        """初始化 delegate 与 barrier。

        :returns: ``None``。
        """

        self.delegate = FinalAnswerWorkerFactory()
        self.events_started = asyncio.Event()
        self.events_release = asyncio.Event()
        self.cancel_count = 0
        self.handle_close_count = 0

    def create_worker(
        self,
        snapshot: AttemptDispatchSnapshot,
    ) -> LocalEngineWorker:
        """创建 delayed worker。

        :param snapshot: dispatch snapshot。
        :returns: delayed worker。
        """

        del snapshot
        return _DelayedFinalAnswerWorker(self)


class _CancelHookFailureBarrierHandle:
    """on_cancel 失败且 close 可控的 active worker handle。"""

    def __init__(self) -> None:
        """初始化 hook/close/events barrier 与计数。

        :returns: ``None``。
        """

        self.events_started = asyncio.Event()
        self.close_started = asyncio.Event()
        self.close_release = asyncio.Event()
        self.hook_called = asyncio.Event()
        self.cancel_count = 0
        self.close_count = 0
        self.closed = False

    @property
    def local_worker_id(self) -> str:
        """返回稳定 worker id。

        :returns: worker id。
        """

        return "attachment-cancel-hook-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持 active stream，直到 scheduler close 取消 consumer。

        :returns: 不会正常产生事件的异步迭代器。
        """

        self.events_started.set()
        await asyncio.Event().wait()
        if False:
            yield cast(EngineEvent, None)

    def on_cancel(self, reason: str) -> None:
        """记录 hook 后模拟 best-effort 异常。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises RuntimeError: 始终模拟 hook 失败。
        """

        del reason
        self.cancel_count += 1
        self.hook_called.set()
        raise RuntimeError("public cancel hook failed")

    async def close(self) -> None:
        """在测试 barrier 放行后完成 mandatory handle cleanup。

        :returns: ``None``。
        """

        self.close_count += 1
        self.close_started.set()
        await self.close_release.wait()
        self.closed = True


class _CancelHookBarrierWorker:
    """首次返回 cancel-hook barrier，后续委托 final-answer provider。"""

    def __init__(self, factory: "_CancelHookBarrierWorkerFactory") -> None:
        """保存所属 factory。

        :param factory: handle 与 delegate owner。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """首次返回 barrier handle，后续执行 deterministic final answer。

        :param snapshot: dispatch snapshot。
        :param request: Engine run request。
        :returns: worker handle。
        :raises Exception: delegate accept 失败时透传。
        """

        self._factory.accept_count += 1
        if self._factory.accept_count == 1:
            self._factory.first_snapshot = snapshot
            return self._factory.first_handle
        delegate = self._factory.delegate.create_worker(snapshot)
        return await delegate.accept(snapshot, request)


class _CancelHookBarrierWorkerFactory:
    """首次 worker 暴露 cancel hook 与 mandatory close 顺序。"""

    def __init__(self) -> None:
        """初始化首次 handle、delegate 与计数。

        :returns: ``None``。
        """

        self.first_handle = _CancelHookFailureBarrierHandle()
        self.delegate = FinalAnswerWorkerFactory()
        self.accept_count = 0
        self.first_snapshot: AttemptDispatchSnapshot | None = None

    def create_worker(
        self,
        snapshot: AttemptDispatchSnapshot,
    ) -> LocalEngineWorker:
        """创建顺序感知 worker。

        :param snapshot: dispatch snapshot。
        :returns: barrier worker。
        """

        del snapshot
        return _CancelHookBarrierWorker(self)


@pytest.mark.asyncio
async def test_public_mutation_requires_attachment_before_actor_or_provider(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未 attach 的 mutation 必须在 actor operation 与 provider 前 typed 拒绝。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: actor operation 或 provider 被触发时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    actor_operation_calls = 0

    def forbidden_submit(
        handle: HostCommandHandle,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """记录任何越过 attachment gate 的 actor submit。

        :param handle: actor-owned command handle。
        :param session_id: 目标 Session id。
        :param request: public follow-up 请求。
        :returns: 正常路径不会返回。
        :raises AssertionError: 本 helper 被调用即抛出。
        """

        nonlocal actor_operation_calls
        del handle, session_id, request
        actor_operation_calls += 1
        raise AssertionError("actor submit must not run without attachment")

    monkeypatch.setattr(
        sys.modules["dayu.host.open_host"],
        "_submit_followup",
        forbidden_submit,
    )
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(ensure_request("attachment-required"))
        with pytest.raises(HostApiError) as exc_info:
            await host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    "attachment-required-submit",
                    "must fail before actor write",
                ),
            )

    _assert_mutation_rejection(
        exc_info.value,
        session_id=session.session_id,
        reason=HostSessionMutationRejectionReason.ATTACHMENT_REQUIRED,
        actual_mode=None,
    )
    assert actor_operation_calls == 0
    assert factory.requests == []


@pytest.mark.asyncio
async def test_public_read_write_attachment_enables_mutation_and_closes(
    tmp_path: pathlib.Path,
) -> None:
    """显式 RW attachment 允许 mutation，关闭后同 handle 恢复 typed 拒绝。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: mode、dispatch 或 close 后 gate 漂移时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(ensure_request("attachment-rw"))
        attachment = await host.attach_session(session.session_id)
        assert attachment.session_id == session.session_id
        assert attachment.access_mode is HostSessionAccessMode.READ_WRITE
        accepted = await host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "attachment-rw-submit",
                "run with explicit attachment",
            ),
        )
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)
        assert factory.requests[0].run_id == accepted.accepted_run_id

        await close_attachment_shielded(attachment)
        with pytest.raises(HostApiError) as exc_info:
            await host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    "attachment-after-close",
                    "must fail after attachment close",
                ),
            )

    _assert_mutation_rejection(
        exc_info.value,
        session_id=session.session_id,
        reason=HostSessionMutationRejectionReason.ATTACHMENT_REQUIRED,
        actual_mode=None,
    )


@pytest.mark.asyncio
async def test_cross_opener_read_only_is_frozen_until_fresh_reacquire(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实双 opener 的 RO 七类 mutation 零副作用，fresh attach 才升级。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: access、零副作用、read/watch 或 fresh mode 漂移时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    owner_manager = open_host(options)
    observer_manager = open_host(options)
    owner_host = await owner_manager.__aenter__()
    owner_attachment: HostSessionAttachment | None = None
    observer_attachment: HostSessionAttachment | None = None
    fresh_attachment: HostSessionAttachment | None = None
    watcher = None
    scan_calls = 0
    original_scan = SessionAttachmentRecoveryScanner.scan

    def record_scan(
        scanner: SessionAttachmentRecoveryScanner,
        policy: SessionAttachmentRecoveryPolicy | None = None,
    ) -> SessionAttachmentRecoveryScanResult:
        """记录 target recovery 并调用真实 scanner。

        :param scanner: target recovery scanner。
        :param policy: fixed-now recovery policy。
        :returns: 真实 recovery result。
        :raises Exception: production recovery 异常透传。
        """

        nonlocal scan_calls
        scan_calls += 1
        return original_scan(scanner, policy)

    monkeypatch.setattr(SessionAttachmentRecoveryScanner, "scan", record_scan)
    try:
        session = await owner_host.ensure_session(ensure_request("attachment-ro"))
        owner_attachment = await owner_host.attach_session(session.session_id)
        assert scan_calls == 1

        event_count_before_observer_open = _event_count(options.db_path)
        observer_host = await observer_manager.__aenter__()
        assert _event_count(options.db_path) == event_count_before_observer_open
        observer_attachment = await observer_host.attach_session(session.session_id)
        assert owner_attachment.access_mode is HostSessionAccessMode.READ_WRITE
        assert observer_attachment.access_mode is HostSessionAccessMode.READ_ONLY
        assert scan_calls == 1
        assert _event_count(options.db_path) == event_count_before_observer_open

        watcher = await observer_host.watch_session_events(session.session_id)
        source = await owner_host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "attachment-ro-source",
                "create source run for read-only mutation gates",
            ),
        )
        observed = await asyncio.wait_for(anext(watcher), timeout=2.0)
        assert observed.session_id == session.session_id
        await wait_for_status(
            observer_host,
            source.accepted_run_id,
            HostTerminalStatus.SUCCEEDED,
        )
        readable = await observer_host.get_run(source.accepted_run_id)
        assert readable.session_id == session.session_id

        wake_calls: list[str] = []

        def record_dispatch_wake(
            scheduler: HostDispatchScheduler,
            record: PendingDispatchRecord,
        ) -> None:
            """记录任何越过 RO gate 的 dispatch wake。

            :param scheduler: scheduler 实例。
            :param record: pending dispatch record；测试只记录调用。
            :returns: ``None``。
            :raises Exception: 不主动抛出异常。
            """

            del scheduler, record
            wake_calls.append("dispatch")

        def record_promotion_wake(
            scheduler: HostDispatchScheduler,
            session_id: str,
        ) -> None:
            """记录任何越过 RO gate 的 promotion wake。

            :param scheduler: scheduler 实例。
            :param session_id: wake 目标 Session id。
            :returns: ``None``。
            :raises Exception: 不主动抛出异常。
            """

            del scheduler, session_id
            wake_calls.append("promotion")

        monkeypatch.setattr(
            HostDispatchScheduler,
            "wake_dispatch",
            record_dispatch_wake,
        )
        monkeypatch.setattr(
            HostDispatchScheduler,
            "wake_queue_promotion",
            record_promotion_wake,
        )
        event_count_before_rejections = _event_count(options.db_path)
        provider_count_before_rejections = len(factory.requests)

        with pytest.raises(HostApiError) as submit_error:
            await observer_host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    "attachment-ro-submit",
                    "read-only submit must reject",
                ),
            )
        _assert_mutation_rejection(
            submit_error.value,
            session_id=session.session_id,
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )

        with pytest.raises(HostApiError) as steer_error:
            await observer_host.submit_followup(
                session.session_id,
                SubmitFollowupRequest(
                    context=host_context("attachment-ro-steer"),
                    session_id=session.session_id,
                    client_request_id="attachment-ro-steer",
                    system_prompt=None,
                    user_prompt="read-only steer must reject",
                    tool_names=None,
                    runner_spec=None,
                    runner_options=None,
                    agent_policy=None,
                    behavior=FollowupBehavior.STEER,
                    target_run_id=source.accepted_run_id,
                ),
            )
        _assert_mutation_rejection(
            steer_error.value,
            session_id=session.session_id,
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )

        with pytest.raises(HostApiError) as cancel_error:
            await observer_host.cancel_run(
                source.accepted_run_id,
                CancelRunRequest(
                    context=host_context("attachment-ro-cancel"),
                    client_request_id="attachment-ro-cancel",
                    reason="read_only_cancel",
                    mode=CancelMode.GRACEFUL,
                ),
            )
        _assert_mutation_rejection(
            cancel_error.value,
            session_id=session.session_id,
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )

        with pytest.raises(HostApiError) as retry_error:
            await observer_host.retry_run(
                source.accepted_run_id,
                RetryRunRequest(
                    context=host_context("attachment-ro-retry"),
                    client_request_id="attachment-ro-retry",
                    reason="read_only_retry",
                ),
            )
        _assert_mutation_rejection(
            retry_error.value,
            session_id=session.session_id,
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )

        with pytest.raises(HostApiError) as replay_error:
            await observer_host.replay_run(
                source.accepted_run_id,
                ReplayRunRequest(
                    context=host_context("attachment-ro-replay"),
                    client_request_id="attachment-ro-replay",
                    reason="read_only_replay",
                    repair_instruction="must reject before replay semantics",
                ),
            )
        _assert_mutation_rejection(
            replay_error.value,
            session_id=session.session_id,
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )

        with pytest.raises(HostApiError) as close_error:
            await observer_host.close_session(
                session.session_id,
                CloseSessionRequest(
                    context=host_context("attachment-ro-close"),
                    client_request_id="attachment-ro-close",
                    reason="read_only_close",
                ),
            )
        _assert_mutation_rejection(
            close_error.value,
            session_id=session.session_id,
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )

        with pytest.raises(HostApiError) as drain_error:
            await observer_host.drain_outbox_terminal_items(
                session.session_id,
                DrainOutboxTerminalItemsRequest(
                    context=host_context("attachment-ro-drain"),
                    after=OutboxTerminalCursor(event_sequence=0),
                    seen_terminal_event_ids=(),
                    limit=10,
                    drain_request_id="attachment-ro-drain",
                ),
            )
        _assert_mutation_rejection(
            drain_error.value,
            session_id=session.session_id,
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )

        assert _event_count(options.db_path) == event_count_before_rejections
        assert len(factory.requests) == provider_count_before_rejections
        assert wake_calls == []

        await close_attachment_shielded(owner_attachment)
        owner_attachment = None
        assert observer_attachment.access_mode is HostSessionAccessMode.READ_ONLY
        await close_attachment_shielded(observer_attachment)
        observer_attachment = None

        fresh_attachment = await observer_host.attach_session(session.session_id)
        assert fresh_attachment.access_mode is HostSessionAccessMode.READ_WRITE
    finally:
        if watcher is not None:
            await watcher.aclose()
        if fresh_attachment is not None:
            await close_attachment_shielded(fresh_attachment)
        if observer_attachment is not None:
            await close_attachment_shielded(observer_attachment)
        if owner_attachment is not None:
            await close_attachment_shielded(owner_attachment)
        await observer_manager.__aexit__(None, None, None)
        await owner_manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_same_workspace_different_sessions_allow_parallel_read_write(
    tmp_path: pathlib.Path,
) -> None:
    """同 workspace 不同 Session 的独立 opener 可同时持有 RW attachment。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: mutex 错误退化为 workspace 级或 dispatch 丢失时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    async with open_host(options) as first_host, open_host(options) as second_host:
        first_session = await first_host.ensure_session(
            ensure_request("attachment-parallel-first")
        )
        second_session = await second_host.ensure_session(
            ensure_request("attachment-parallel-second")
        )
        first_attachment = await first_host.attach_session(first_session.session_id)
        second_attachment = await second_host.attach_session(second_session.session_id)
        try:
            assert first_attachment.access_mode is HostSessionAccessMode.READ_WRITE
            assert second_attachment.access_mode is HostSessionAccessMode.READ_WRITE
            first_followup, second_followup = await asyncio.gather(
                first_host.submit_followup(
                    first_session.session_id,
                    followup_request(
                        first_session.session_id,
                        "attachment-parallel-first-run",
                        "first independent session",
                    ),
                ),
                second_host.submit_followup(
                    second_session.session_id,
                    followup_request(
                        second_session.session_id,
                        "attachment-parallel-second-run",
                        "second independent session",
                    ),
                ),
            )
            await asyncio.gather(
                wait_for_status(
                    first_host,
                    first_followup.accepted_run_id,
                    HostTerminalStatus.SUCCEEDED,
                ),
                wait_for_status(
                    second_host,
                    second_followup.accepted_run_id,
                    HostTerminalStatus.SUCCEEDED,
                ),
            )
            assert len(factory.requests) == 2
        finally:
            await close_attachment_shielded(second_attachment)
            await close_attachment_shielded(first_attachment)


@pytest.mark.asyncio
async def test_concurrent_fresh_cross_opener_attach_has_single_read_write_owner(
    tmp_path: pathlib.Path,
) -> None:
    """两个 fresh opener 并发 attach 时必须恰有一个 RW owner。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: native mutex 产生双 RW 或双 RO 时抛出。
    """

    options = _options(tmp_path, FinalAnswerWorkerFactory())
    async with open_host(options) as first_host, open_host(options) as second_host:
        session = await first_host.ensure_session(
            ensure_request("attachment-concurrent-fresh")
        )
        first_attachment, second_attachment = await asyncio.gather(
            first_host.attach_session(session.session_id),
            second_host.attach_session(session.session_id),
        )
        try:
            modes = sorted(
                (
                    first_attachment.access_mode.value,
                    second_attachment.access_mode.value,
                )
            )
            assert modes == [
                HostSessionAccessMode.READ_ONLY.value,
                HostSessionAccessMode.READ_WRITE.value,
            ]
        finally:
            await close_attachment_shielded(second_attachment)
            await close_attachment_shielded(first_attachment)


@pytest.mark.asyncio
async def test_recovery_failure_releases_mutex_for_fresh_attachment(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """target recovery 失败后先 drain allocation，再允许 fresh RW attach。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: recovery failure 泄漏 mutex 或 fresh mode 漂移时抛出。
    """

    scan_calls = 0
    original_scan = SessionAttachmentRecoveryScanner.scan

    def fail_once(
        scanner: SessionAttachmentRecoveryScanner,
        policy: SessionAttachmentRecoveryPolicy | None = None,
    ) -> SessionAttachmentRecoveryScanResult:
        """首次 recovery 失败，之后委托 production scanner。

        :param scanner: target recovery scanner。
        :param policy: fixed-now recovery policy。
        :returns: 第二次起的真实 scan result。
        :raises RuntimeError: 首次调用模拟 recovery failure。
        """

        nonlocal scan_calls
        scan_calls += 1
        if scan_calls == 1:
            raise RuntimeError("forced target recovery failure")
        return original_scan(scanner, policy)

    monkeypatch.setattr(SessionAttachmentRecoveryScanner, "scan", fail_once)
    async with open_host(
        _options(tmp_path, FinalAnswerWorkerFactory())
    ) as host:
        session = await host.ensure_session(
            ensure_request("attachment-recovery-failure-fresh")
        )
        with pytest.raises(RuntimeError, match="forced target recovery failure"):
            await host.attach_session(session.session_id)
        fresh = await host.attach_session(session.session_id)
        try:
            assert fresh.access_mode is HostSessionAccessMode.READ_WRITE
            assert scan_calls == 2
        finally:
            await close_attachment_shielded(fresh)


@pytest.mark.asyncio
async def test_cancelled_recovery_waits_for_drain_before_fresh_attachment(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """attach caller 取消时 recovery 继续收口，随后 fresh attach 可取得 RW。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: cancellation 提前释放或泄漏 mutex 时抛出。
    """

    scan_started = threading.Event()
    scan_release = threading.Event()
    original_scan = SessionAttachmentRecoveryScanner.scan

    def blocked_scan(
        scanner: SessionAttachmentRecoveryScanner,
        policy: SessionAttachmentRecoveryPolicy | None = None,
    ) -> SessionAttachmentRecoveryScanResult:
        """在 actor thread 上阻塞 target recovery。

        :param scanner: target recovery scanner。
        :param policy: fixed-now recovery policy。
        :returns: barrier 释放后的真实 scan result。
        :raises RuntimeError: barrier 未在测试预算内释放时抛出。
        """

        scan_started.set()
        if not scan_release.wait(timeout=2.0):
            raise RuntimeError("target recovery release barrier timed out")
        return original_scan(scanner, policy)

    monkeypatch.setattr(SessionAttachmentRecoveryScanner, "scan", blocked_scan)
    async with open_host(
        _options(tmp_path, FinalAnswerWorkerFactory())
    ) as host:
        session = await host.ensure_session(
            ensure_request("attachment-recovery-cancel-fresh")
        )
        attach_task = asyncio.create_task(host.attach_session(session.session_id))
        assert await asyncio.to_thread(scan_started.wait, 1.0)
        attach_task.cancel()
        await asyncio.sleep(0)
        assert attach_task.done() is False
        scan_release.set()
        with pytest.raises(asyncio.CancelledError):
            await attach_task

        fresh = await host.attach_session(session.session_id)
        try:
            assert fresh.access_mode is HostSessionAccessMode.READ_WRITE
        finally:
            await close_attachment_shielded(fresh)


@pytest.mark.asyncio
async def test_periodic_reconcile_one_shot_targets_only_active_read_write(
    tmp_path: pathlib.Path,
) -> None:
    """one-shot reconcile 只租用 owner opener 的 ACTIVE RW Session。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: RO opener 被扫描或 owner work lease 缺失时抛出。
    """

    options = _options(tmp_path, FinalAnswerWorkerFactory())
    async with open_host(options) as owner_host, open_host(options) as observer_host:
        session = await owner_host.ensure_session(
            ensure_request("attachment-periodic-target")
        )
        owner_attachment = await owner_host.attach_session(session.session_id)
        observer_attachment = await observer_host.attach_session(session.session_id)
        try:
            owner_scheduler = cast(_PublicHostHandle, owner_host)._scheduler
            observer_scheduler = cast(_PublicHostHandle, observer_host)._scheduler
            fixed_now = datetime(2026, 7, 22, 4, 5, 6, tzinfo=UTC)
            owner_result = await owner_scheduler.reconcile_owned_sessions_once(
                fixed_now=fixed_now
            )
            observer_result = await observer_scheduler.reconcile_owned_sessions_once(
                fixed_now=fixed_now
            )

            assert owner_result.owned_session_count == 1
            assert owner_result.leased_session_count == 1
            assert owner_result.dispatched_session_count == 0
            assert owner_result.skipped_session_count == 1
            assert observer_result.owned_session_count == 0
            assert observer_result.leased_session_count == 0
            assert observer_result.dispatched_session_count == 0
            assert observer_result.skipped_session_count == 0
        finally:
            await close_attachment_shielded(observer_attachment)
            await close_attachment_shielded(owner_attachment)


@pytest.mark.asyncio
async def test_host_close_keeps_mutex_through_scheduler_barrier(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host close 在 scheduler barrier 前后保持 mutex，完成后才允许 fresh RW。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: scheduler close 前 mutex 提前释放时抛出。
    """

    options = _options(tmp_path, FinalAnswerWorkerFactory())
    owner_manager = open_host(options)
    observer_manager = open_host(options)
    owner_host = await owner_manager.__aenter__()
    observer_host = await observer_manager.__aenter__()
    owner_public = cast(_PublicHostHandle, owner_host)
    owner_scheduler = owner_public._scheduler
    original_scheduler_close = HostDispatchScheduler.close
    scheduler_close_entered = asyncio.Event()
    scheduler_close_release = asyncio.Event()
    owner_attachment: HostSessionAttachment | None = None
    observer_attachment: HostSessionAttachment | None = None
    fresh_attachment: HostSessionAttachment | None = None

    async def blocked_scheduler_close(scheduler: HostDispatchScheduler) -> None:
        """只在 owner scheduler close 上建立测试 barrier。

        :param scheduler: 待关闭 scheduler。
        :returns: ``None``。
        :raises Exception: production scheduler close 异常透传。
        """

        if scheduler is owner_scheduler:
            scheduler_close_entered.set()
            await scheduler_close_release.wait()
        await original_scheduler_close(scheduler)

    try:
        session = await owner_host.ensure_session(
            ensure_request("attachment-host-close-barrier")
        )
        owner_attachment = await owner_host.attach_session(session.session_id)
        monkeypatch.setattr(
            HostDispatchScheduler,
            "close",
            blocked_scheduler_close,
        )
        close_task = asyncio.create_task(owner_public.close())
        await asyncio.wait_for(scheduler_close_entered.wait(), timeout=2.0)

        observer_attachment = await observer_host.attach_session(session.session_id)
        assert observer_attachment.access_mode is HostSessionAccessMode.READ_ONLY
        await close_attachment_shielded(observer_attachment)
        observer_attachment = None

        scheduler_close_release.set()
        await close_task
        owner_attachment = None
        fresh_attachment = await observer_host.attach_session(session.session_id)
        assert fresh_attachment.access_mode is HostSessionAccessMode.READ_WRITE
    finally:
        scheduler_close_release.set()
        monkeypatch.setattr(
            HostDispatchScheduler,
            "close",
            original_scheduler_close,
        )
        if fresh_attachment is not None:
            await close_attachment_shielded(fresh_attachment)
        if observer_attachment is not None:
            await close_attachment_shielded(observer_attachment)
        if owner_attachment is not None:
            await close_attachment_shielded(owner_attachment)
        await observer_manager.__aexit__(None, None, None)
        await owner_manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_scheduler_close_failure_keeps_mutex_until_successful_retry(
    tmp_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """真实 mandatory handle cleanup 失败时 Host 保持 CLOSING 与 mutex。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    :raises AssertionError: owner 阶段提前完成、force unlock 或无法重试时抛出。
    """

    options = _options(tmp_path, FinalAnswerWorkerFactory())
    owner_manager = open_host(options)
    observer_manager = open_host(options)
    owner_host = await owner_manager.__aenter__()
    observer_host = await observer_manager.__aenter__()
    owner_public = cast(_PublicHostHandle, owner_host)
    owner_scheduler = owner_public._scheduler
    failing_handle = _FailOnceMandatoryCloseHandle()
    owner_attachment: HostSessionAttachment | None = None
    observer_attachment: HostSessionAttachment | None = None
    fresh_attachment: HostSessionAttachment | None = None

    try:
        session = await owner_host.ensure_session(
            ensure_request("attachment-host-close-retry")
        )
        owner_attachment = await owner_host.attach_session(session.session_id)
        owner_scheduler._active_handles.add(
            cast(LocalWorkerHandle, failing_handle)
        )
        with caplog.at_level("INFO"):
            with pytest.raises(
                RuntimeError,
                match="public mandatory handle close failed",
            ):
                await owner_public.close()

        assert owner_public._health_gate.state is HostExecutionHealthState.CLOSING
        with pytest.raises(HostApiError) as attachment_error:
            owner_public._session_attachment_registry.acquire_mutation_lease(
                session.session_id
            )
        _assert_mutation_rejection(
            attachment_error.value,
            session_id=session.session_id,
            reason=HostSessionMutationRejectionReason.ATTACHMENT_CLOSING,
            actual_mode=HostSessionAccessMode.READ_WRITE,
        )
        assert owner_scheduler._close_cleanup_done is False
        assert owner_scheduler._lane_close_done is False
        assert owner_scheduler._host_instance_stopped_marked is False
        assert failing_handle in owner_scheduler._active_handles
        assert failing_handle.close_count == 1
        assert failing_handle.closed is False
        assert owner_public._terminal_post_commit_coordinator._closed is False
        assert "dispatch.scheduler.close_done" not in caplog.text
        assert "host.public_handle.close_done" not in caplog.text
        failed_instance = owner_public._scheduler_store.transaction_runner.run_read(
            lambda transaction: read_host_instance(
                transaction,
                owner_scheduler.host_instance_id,
            )
        )
        assert failed_instance is not None
        assert failed_instance.status is HostInstanceStatus.STOPPING

        observer_attachment = await observer_host.attach_session(session.session_id)
        assert observer_attachment.access_mode is HostSessionAccessMode.READ_ONLY
        await close_attachment_shielded(observer_attachment)
        observer_attachment = None

        await owner_public.close()
        owner_attachment = None
        assert failing_handle.close_count == 2
        assert failing_handle.closed is True
        assert owner_scheduler._close_cleanup_done is True
        assert owner_scheduler._host_instance_stopped_marked is True
        assert owner_public._health_gate.state is HostExecutionHealthState.CLOSED
        fresh_attachment = await observer_host.attach_session(session.session_id)
        assert fresh_attachment.access_mode is HostSessionAccessMode.READ_WRITE
    finally:
        if fresh_attachment is not None:
            await close_attachment_shielded(fresh_attachment)
        if observer_attachment is not None:
            await close_attachment_shielded(observer_attachment)
        if owner_attachment is not None:
            await close_attachment_shielded(owner_attachment)
        await observer_manager.__aexit__(None, None, None)
        await owner_manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_same_handle_duplicate_conflicts_before_second_native_acquire(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 handle duplicate attach 在第二次 native acquire 前 typed conflict。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: conflict detail 或 native acquire 次数漂移时抛出。
    """

    native_acquire_calls = 0
    original_acquire = session_attachment_module.try_acquire_strict_native_mutex

    def counting_acquire(path: pathlib.Path) -> StrictNativeMutexHandle | None:
        """记录 strict native mutex acquire 调用。

        :param path: 派生后的 opaque mutex 路径。
        :returns: production acquire 结果。
        :raises Exception: production native mutex 错误透传。
        """

        nonlocal native_acquire_calls
        native_acquire_calls += 1
        return original_acquire(path)

    monkeypatch.setattr(
        session_attachment_module,
        "try_acquire_strict_native_mutex",
        counting_acquire,
    )
    async with open_host(_options(tmp_path, FinalAnswerWorkerFactory())) as host:
        session = await host.ensure_session(ensure_request("attachment-duplicate"))
        attachment = await host.attach_session(session.session_id)
        try:
            with pytest.raises(HostApiError) as exc_info:
                await host.attach_session(session.session_id)
        finally:
            await close_attachment_shielded(attachment)

    assert native_acquire_calls == 1
    assert exc_info.value.code is HostApiErrorCode.CONFLICT
    assert exc_info.value.retryable is False
    assert exc_info.value.detail == HostSessionAttachmentConflictDetail(
        kind="session_attachment_conflict",
        session_id=session.session_id,
        reason=HostSessionAttachmentConflictReason.ALREADY_ATTACHED,
    )


@pytest.mark.asyncio
async def test_attachment_close_waits_for_cancelled_caller_actor_future(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """caller cancellation 后 attachment close 仍等待底层 actor mutation 收口。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: close 越过未完成 actor Future 时抛出。
    """

    actor_started = threading.Event()
    actor_release = threading.Event()
    original_submit = _submit_followup

    def blocked_submit(
        handle: HostCommandHandle,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """在 actor thread 阻塞真实 mutation commit。

        :param handle: actor-owned command handle。
        :param session_id: 目标 Session id。
        :param request: public follow-up 请求。
        :returns: production follow-up snapshot。
        :raises RuntimeError: test barrier 未释放时抛出。
        :raises Exception: production submit 错误透传。
        """

        actor_started.set()
        if not actor_release.wait(timeout=2.0):
            raise RuntimeError("actor mutation release barrier timed out")
        return original_submit(handle, session_id, request)

    monkeypatch.setattr(
        sys.modules["dayu.host.open_host"],
        "_submit_followup",
        blocked_submit,
    )
    async with open_host(_options(tmp_path, FinalAnswerWorkerFactory())) as host:
        session = await host.ensure_session(ensure_request("attachment-cancel"))
        attachment = await host.attach_session(session.session_id)
        submit_task = asyncio.create_task(
            host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    "attachment-cancel-submit",
                    "caller cancellation must not release lease",
                ),
            )
        )
        assert await asyncio.to_thread(actor_started.wait, 1.0)
        submit_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await submit_task

        close_task = asyncio.create_task(attachment.aclose())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert close_task.done() is False

        actor_release.set()
        await close_task
    actor_release.set()
    with suppress(asyncio.CancelledError):
        await submit_task


@pytest.mark.asyncio
async def test_attachment_close_holds_mutex_through_real_pre_start_wake_lease(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """accepted wake 已取得的 pre-start lease 阻止 mutex 提前释放。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: actor/lease barrier、mutex 或 attempt 唯一性漂移时抛出。
    """

    factory = FinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    owner_manager = open_host(options)
    observer_manager = open_host(options)
    owner_host = await owner_manager.__aenter__()
    observer_host = await observer_manager.__aenter__()
    owner_public = cast(_PublicHostHandle, owner_host)
    owner_scheduler = owner_public._scheduler
    original_governance = HostDispatchScheduler._run_pre_start_governance
    pre_start_entered = asyncio.Event()
    pre_start_release = asyncio.Event()
    owner_attachment: HostSessionAttachment | None = None
    observer_attachment: HostSessionAttachment | None = None
    fresh_attachment: HostSessionAttachment | None = None

    async def block_owner_pre_start(
        scheduler: HostDispatchScheduler,
        session_id: str,
        *,
        work_lease: SessionWorkLease,
    ) -> host_dispatch._GovernanceStageResult:
        """在 production work lease 已取得后阻塞 owner governance。

        :param scheduler: 当前 scheduler。
        :param session_id: 目标 Session id。
        :param work_lease: production new-work lease。
        :returns: production governance 结果。
        :raises Exception: production governance 失败时透传。
        """

        if scheduler is owner_scheduler:
            pre_start_entered.set()
            await pre_start_release.wait()
        return await original_governance(
            scheduler,
            session_id,
            work_lease=work_lease,
        )

    try:
        session = await owner_host.ensure_session(
            ensure_request("attachment-pre-start-lease-barrier")
        )
        owner_attachment = await owner_host.attach_session(session.session_id)
        monkeypatch.setattr(
            HostDispatchScheduler,
            "_run_pre_start_governance",
            block_owner_pre_start,
        )
        submitted = await owner_host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "attachment-pre-start-lease",
                "hold the accepted wake before its first stable attempt",
            ),
        )
        await asyncio.wait_for(pre_start_entered.wait(), timeout=2.0)
        accepted_before = await owner_host.get_run(submitted.accepted_run_id)
        assert accepted_before.status is RunStatus.ACCEPTED
        assert accepted_before.current_attempt_id is None
        close_task = asyncio.create_task(owner_attachment.aclose())
        await asyncio.sleep(0)
        assert close_task.done() is False

        observer_attachment = await observer_host.attach_session(session.session_id)
        assert observer_attachment.access_mode is HostSessionAccessMode.READ_ONLY
        await close_attachment_shielded(observer_attachment)
        observer_attachment = None
        assert close_task.done() is False
        assert owner_scheduler._closed is False

        pre_start_release.set()
        await close_task
        owner_attachment = None
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)
        assert len(factory.snapshots) == 1
        assert len(factory.requests) == 1
        fresh_attachment = await observer_host.attach_session(session.session_id)
        assert fresh_attachment.access_mode is HostSessionAccessMode.READ_WRITE
        assert owner_scheduler._closed is False
        await wait_for_status(
            observer_host,
            submitted.accepted_run_id,
            HostTerminalStatus.SUCCEEDED,
        )
    finally:
        pre_start_release.set()
        if fresh_attachment is not None:
            await close_attachment_shielded(fresh_attachment)
        if observer_attachment is not None:
            await close_attachment_shielded(observer_attachment)
        if owner_attachment is not None:
            await close_attachment_shielded(owner_attachment)
        await observer_manager.__aexit__(None, None, None)
        await owner_manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_single_attachment_close_leaves_stable_attempt_running(
    tmp_path: pathlib.Path,
) -> None:
    """单 attachment close 不等 terminal、不关 scheduler、不取消 stable Attempt。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: attachment close 错误接管 execution lifecycle 时抛出。
    """

    factory = _DelayedFinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    owner_manager = open_host(options)
    observer_manager = open_host(options)
    owner_host = await owner_manager.__aenter__()
    observer_host = await observer_manager.__aenter__()
    owner_public = cast(_PublicHostHandle, owner_host)
    owner_attachment: HostSessionAttachment | None = None
    fresh_attachment: HostSessionAttachment | None = None

    try:
        session = await owner_host.ensure_session(
            ensure_request("attachment-stable-attempt-close")
        )
        owner_attachment = await owner_host.attach_session(session.session_id)
        submitted = await owner_host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "attachment-stable-attempt-close",
                "keep the stable attempt running while attachment closes",
            ),
        )
        await asyncio.wait_for(factory.events_started.wait(), timeout=2.0)
        stable_before = await owner_host.get_run(submitted.accepted_run_id)
        assert stable_before.status is RunStatus.RUNNING
        assert stable_before.current_attempt_id is not None

        await asyncio.wait_for(owner_attachment.aclose(), timeout=1.0)
        owner_attachment = None
        stable_after = await observer_host.get_run(submitted.accepted_run_id)
        assert stable_after.status is RunStatus.RUNNING
        assert stable_after.current_attempt_id == stable_before.current_attempt_id
        assert owner_public._scheduler._closed is False
        assert factory.cancel_count == 0
        assert factory.handle_close_count == 0

        fresh_attachment = await observer_host.attach_session(session.session_id)
        assert fresh_attachment.access_mode is HostSessionAccessMode.READ_WRITE
        factory.events_release.set()
        await wait_for_status(
            observer_host,
            submitted.accepted_run_id,
            HostTerminalStatus.SUCCEEDED,
        )
        assert factory.cancel_count == 0
        assert factory.handle_close_count == 1
    finally:
        factory.events_release.set()
        if fresh_attachment is not None:
            await close_attachment_shielded(fresh_attachment)
        if owner_attachment is not None:
            await close_attachment_shielded(owner_attachment)
        await observer_manager.__aexit__(None, None, None)
        await owner_manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_host_close_cancel_hook_failure_precedes_unlock_and_keeps_cleanup(
    tmp_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """best-effort on_cancel 失败不阻断 token 与 mandatory close，且先于 unlock。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    :raises AssertionError: hook、token、cleanup 与 mutex 顺序漂移时抛出。
    """

    factory = _CancelHookBarrierWorkerFactory()
    options = _options(tmp_path, factory)
    owner_manager = open_host(options)
    observer_manager = open_host(options)
    owner_host = await owner_manager.__aenter__()
    observer_host = await observer_manager.__aenter__()
    owner_public = cast(_PublicHostHandle, owner_host)
    owner_attachment: HostSessionAttachment | None = None
    observer_attachment: HostSessionAttachment | None = None
    fresh_attachment: HostSessionAttachment | None = None

    try:
        session = await owner_host.ensure_session(
            ensure_request("attachment-cancel-hook-close")
        )
        owner_attachment = await owner_host.attach_session(session.session_id)
        submitted = await owner_host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "attachment-cancel-hook-close",
                "hold active cleanup while proving cancel hook ordering",
            ),
        )
        await asyncio.wait_for(
            factory.first_handle.events_started.wait(),
            timeout=2.0,
        )
        stable = await owner_host.get_run(submitted.accepted_run_id)
        assert stable.status is RunStatus.RUNNING
        assert factory.first_snapshot is not None

        with caplog.at_level("WARNING", logger="dayu.host.dispatch"):
            close_task = asyncio.create_task(owner_public.close())
            await asyncio.wait_for(
                factory.first_handle.hook_called.wait(),
                timeout=2.0,
            )
            await asyncio.wait_for(
                factory.first_handle.close_started.wait(),
                timeout=2.0,
            )
            assert close_task.done() is False
            assert factory.first_snapshot.cancellation_token.is_cancelled()
            assert factory.first_snapshot.cancellation_token.cancel_reason() == (
                "scheduler_close"
            )
            assert factory.first_handle.cancel_count == 1
            assert factory.first_handle.close_count == 1
            assert factory.first_handle.closed is False
            assert owner_public._health_gate.state is (
                HostExecutionHealthState.CLOSING
            )
            assert owner_public._scheduler._close_cleanup_done is False

            observer_attachment = await observer_host.attach_session(
                session.session_id
            )
            assert observer_attachment.access_mode is HostSessionAccessMode.READ_ONLY
            factory.first_handle.close_release.set()
            await close_task
            owner_attachment = None

        assert "active worker cancel hook failed; continuing" in caplog.text
        assert factory.first_handle.closed is True
        assert owner_public._scheduler._close_cleanup_done is True
        assert owner_public._health_gate.state is HostExecutionHealthState.CLOSED
        await close_attachment_shielded(observer_attachment)
        observer_attachment = None
        fresh_attachment = await observer_host.attach_session(session.session_id)
        assert fresh_attachment.access_mode is HostSessionAccessMode.READ_WRITE
    finally:
        factory.first_handle.close_release.set()
        if fresh_attachment is not None:
            await close_attachment_shielded(fresh_attachment)
        if observer_attachment is not None:
            await close_attachment_shielded(observer_attachment)
        if owner_attachment is not None:
            await close_attachment_shielded(owner_attachment)
        await observer_manager.__aexit__(None, None, None)
        await owner_manager.__aexit__(None, None, None)
