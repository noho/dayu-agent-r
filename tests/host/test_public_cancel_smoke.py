"""P10.5 Slice 5 public cancel smoke 测试。"""

from __future__ import annotations

import pathlib
import sqlite3
from contextlib import AsyncExitStack
from dataclasses import replace

import pytest

from dayu.host import (
    CancelMode,
    CancelRunRequest,
    CancelSessionRunsRequest,
    HostEventKind,
    RunStatus,
    open_host,
)
from tests.host.public_smoke_support import (
    close_attachment_shielded,
    next_terminal_for_run,
    wait_for_diagnostic_event_type_count,
)
from tests.host.test_public_retry_replay import (
    _BLOCK,
    _SequencedWorkerFactory,
    _context,
    _ensure_request,
    _followup_request,
    _options,
    _wait_for_run_status,
)


@pytest.mark.asyncio
async def test_cancel_accepted_queued_and_active_public_path(
    tmp_path: pathlib.Path,
) -> None:
    """public cancel 覆盖 queued 与 active，并通过 shared registry 可见。"""

    factory = _SequencedWorkerFactory([_BLOCK])
    async with (
        open_host(_options(tmp_path, factory)) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(_ensure_request("cancel"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        active = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "cancel-active"),
        )
        await _wait_for_run_status(host, active.accepted_run_id, RunStatus.RUNNING)
        await wait_for_diagnostic_event_type_count(
            tmp_path / "host.sqlite3", "ATTEMPT_RUNNING", 1
        )
        await _wait_for_handle_count(factory, 1)
        queued = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "cancel-queued"),
        )
        assert queued.accepted_run_status is RunStatus.QUEUED

        cancelled_queued = await host.cancel_run(
            queued.accepted_run_id,
            CancelRunRequest(
                context=_context("cancel-queued"),
                client_request_id="cancel-queued",
                reason="user_cancel_queued",
                mode=CancelMode.GRACEFUL,
            ),
        )
        assert cancelled_queued.status is RunStatus.CANCELLED

        await host.cancel_session_runs(
            session.session_id,
            CancelSessionRunsRequest(
                context=_context("cancel-session"),
                client_request_id="cancel-session",
                reason="user_cancel_session",
                mode=CancelMode.GRACEFUL,
            ),
        )
        cancelling = await host.get_run(active.accepted_run_id)
        assert cancelling.status in (RunStatus.CANCELLING, RunStatus.CANCELLED)
        assert factory.handles[0].cancel_reasons == ["user_cancel_session"]


@pytest.mark.asyncio
async def test_pre_dispatch_cancel_visible_in_watch(
    tmp_path: pathlib.Path,
) -> None:
    """pre-dispatch queued Run 取消后通过 public watch 可见。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: watch 未观察到取消 terminal 时抛出。
    """

    factory = _SequencedWorkerFactory([_BLOCK])
    async with (
        open_host(_options(tmp_path, factory)) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(_ensure_request("cancel-watch"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        watcher = await host.watch_session_events(session.session_id)
        active = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "cancel-watch-active"),
        )
        await _wait_for_run_status(host, active.accepted_run_id, RunStatus.RUNNING)
        queued = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "cancel-watch-queued"),
        )

        cancelled = await host.cancel_run(
            queued.accepted_run_id,
            CancelRunRequest(
                context=_context("cancel-watch-queued"),
                client_request_id="cancel-watch-queued",
                reason="pre_dispatch_visible",
                mode=CancelMode.GRACEFUL,
            ),
        )
        terminal = await next_terminal_for_run(watcher, queued.accepted_run_id)

    assert cancelled.status is RunStatus.CANCELLED
    assert terminal.kind is HostEventKind.CANCELLED
    assert terminal.cancel_reason == "pre_dispatch_visible"


@pytest.mark.asyncio
async def test_active_cancel_emits_public_cancel_event(
    tmp_path: pathlib.Path,
) -> None:
    """active cancel 通过 public watch 暴露取消 terminal。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: active cancel 未传播到 worker 或 watch 时抛出。
    """

    factory = _SequencedWorkerFactory([_BLOCK])
    async with (
        open_host(_options(tmp_path, factory)) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(_ensure_request("active-cancel"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        watcher = await host.watch_session_events(session.session_id)
        active = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "active-cancel-run"),
        )
        await _wait_for_run_status(host, active.accepted_run_id, RunStatus.RUNNING)
        await _wait_for_handle_count(factory, 1)
        await host.cancel_run(
            active.accepted_run_id,
            CancelRunRequest(
                context=_context("active-cancel-run"),
                client_request_id="active-cancel-run",
                reason="active_cancel_visible",
                mode=CancelMode.GRACEFUL,
            ),
        )
        terminal = await next_terminal_for_run(watcher, active.accepted_run_id)

    assert terminal.kind is HostEventKind.CANCELLED
    assert terminal.cancel_reason == "active_cancel_visible"


@pytest.mark.asyncio
async def test_recovering_cancel_does_not_propagate_worker_cancel(
    tmp_path: pathlib.Path,
) -> None:
    """public cancel_run 取消 RECOVERING Run 时不触碰 active WorkerProxy。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: RECOVERING cancel 错误传播到 worker 时抛出。
    """

    factory = _SequencedWorkerFactory([_BLOCK])
    async with (
        open_host(_options(tmp_path, factory)) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(_ensure_request("recovering-cancel"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        active = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "recovering-cancel-run"),
        )
        await _wait_for_run_status(host, active.accepted_run_id, RunStatus.RUNNING)
        await _wait_for_handle_count(factory, 1)
        _mark_run_recovering(tmp_path / "host.sqlite3", active.accepted_run_id)

        cancelled = await host.cancel_run(
            active.accepted_run_id,
            CancelRunRequest(
                context=_context("recovering-cancel-run"),
                client_request_id="recovering-cancel-run",
                reason="recovering_cancel_visible",
                mode=CancelMode.GRACEFUL,
            ),
        )

        assert cancelled.status is RunStatus.CANCELLED
        assert factory.handles[0].cancel_reasons == []


@pytest.mark.asyncio
async def test_cancel_session_runs_scoped_to_session(
    tmp_path: pathlib.Path,
) -> None:
    """cancel_session_runs 只取消目标 Session 下的非终态 Run。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 其它 Session 的 Run 被错误取消时抛出。
    """

    factory = _SequencedWorkerFactory([_BLOCK, _BLOCK])
    options = replace(
        _options(tmp_path, factory),
        lane_capacity=2,
        lane_name="slice5-session-scope",
    )
    async with (
        open_host(options) as host,
        AsyncExitStack() as attachment_stack,
    ):
        first_session = await host.ensure_session(_ensure_request("scope-first"))
        second_session = await host.ensure_session(_ensure_request("scope-second"))
        first_attachment = await host.attach_session(first_session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, first_attachment
        )
        second_attachment = await host.attach_session(second_session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, second_attachment
        )
        first_run = await host.submit_followup(
            first_session.session_id,
            _followup_request(first_session.session_id, "scope-first-run"),
        )
        second_run = await host.submit_followup(
            second_session.session_id,
            _followup_request(second_session.session_id, "scope-second-run"),
        )
        await _wait_for_run_status(host, first_run.accepted_run_id, RunStatus.RUNNING)
        await _wait_for_run_status(host, second_run.accepted_run_id, RunStatus.RUNNING)
        await _wait_for_handle_count(factory, 2)

        await host.cancel_session_runs(
            first_session.session_id,
            CancelSessionRunsRequest(
                context=_context("scope-cancel"),
                client_request_id="scope-cancel",
                reason="session_scope_only",
                mode=CancelMode.GRACEFUL,
            ),
        )
        first_snapshot = await host.get_run(first_run.accepted_run_id)
        second_snapshot = await host.get_run(second_run.accepted_run_id)
        assert factory.handles[1].cancel_reasons == []

    assert first_snapshot.status in (RunStatus.CANCELLING, RunStatus.CANCELLED)
    assert second_snapshot.status is RunStatus.RUNNING
    assert factory.handles[0].cancel_reasons == ["session_scope_only"]


def _mark_run_recovering(db_path: pathlib.Path, run_id: str) -> None:
    """直接把测试 Run 标记为 RECOVERING。

    :param db_path: Host SQLite DB 路径。
    :param run_id: 目标 Run id。
    :returns: ``None``。
    """

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE host_runs SET status = ? WHERE run_id = ?",
            (RunStatus.RECOVERING.value, run_id),
        )


async def _wait_for_handle_count(
    factory: _SequencedWorkerFactory, expected_count: int
) -> None:
    """等待 worker factory 创建指定数量 handle。

    :param factory: sequenced worker factory。
    :param expected_count: 期望 handle 数量。
    :returns: ``None``。
    :raises TimeoutError: 超时未达到数量时抛出。
    """

    for _ in range(200):
        if len(factory.handles) >= expected_count:
            return
        await factory.accepted_event.wait()
        factory.accepted_event.clear()
    raise TimeoutError(f"worker handles did not reach {expected_count}")
