"""``dayu.runtime.lane`` 单进程行为测试。

覆盖配置校验、独立 SQLite runtime lane DB 初始化、claim / heartbeat /
release 生命周期、timeout、协作式 cancellation、外层 task cancellation 和
controller close 语义。
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest

import dayu.runtime.lane as lane_module
from dayu.runtime.lane import (
    LaneAcquireCancelled,
    LaneAcquired,
    LaneClaimToken,
    LaneAcquireTimedOut,
    LaneConfig,
    LaneController,
    LaneOwner,
    RuntimeLaneClaimLostError,
    RuntimeLaneClosedError,
    RuntimeLaneConfigError,
    RuntimeLaneError,
    SQLiteLaneCoordinatorConfig,
    _ClaimAttempt,
    _await_task_after_outer_cancellation,
)

_LANE_NAME = "llm"
_SECOND_LANE_NAME = "tool"
_CLAIMS_TABLE = "runtime_lane_claims"
_FAST_TTL_SECONDS = 0.5
_FAST_HEARTBEAT_SECONDS = 0.05
_FAST_POLL_SECONDS = 0.01
_SHORT_TIMEOUT_SECONDS = 0.04
_SLOW_OPERATION_SECONDS = 5.0
_CANCEL_REASON = "user-stop"
_THREAD_EVENT_TIMEOUT_SECONDS = 1.0
_UNTRACKED_RELEASE_FAILED_LOG_FRAGMENT = "untracked claim release failed"
_REFRESH_FAILED_LOG_FRAGMENT = "runtime lane refresh failed after outer cancellation"
_RELEASE_FAILED_MESSAGE = "release failed"
_REFRESH_FAILED_MESSAGE = "refresh failed"
_CLOSE_RELEASE_FAILED_MESSAGE = "release failed during close"
_MISSING_CLAIM_ID = "claim-missing"


class _FakeCancellationToken:
    """测试用协作式取消 token。"""

    def __init__(self) -> None:
        """初始化为未取消状态。"""

        self._cancelled = False
        self._reason: str | None = None
        self._requested_at: datetime | None = None

    def cancel(self, *, reason: str | None = _CANCEL_REASON) -> None:
        """触发取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self._cancelled = True
        self._reason = reason
        self._requested_at = datetime.now(UTC)

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已取消返回 ``True``。
        """

        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 取消原因；未取消返回 ``None``。
        """

        return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 取消请求时间；未取消返回 ``None``。
        """

        return self._requested_at


def _coordinator(db_path: Path) -> SQLiteLaneCoordinatorConfig:
    """构造测试用 SQLite coordinator 配置。

    :param db_path: runtime lane DB 路径。
    :returns: SQLite coordinator 配置。
    """

    return SQLiteLaneCoordinatorConfig(
        db_path=db_path,
        busy_timeout_seconds=1.0,
        poll_interval_seconds=_FAST_POLL_SECONDS,
    )


def _lane_config(
    *,
    name: str = _LANE_NAME,
    capacity: int = 1,
    default_timeout_seconds: float | None = None,
) -> LaneConfig:
    """构造测试用 lane 配置。

    :param name: lane 名称。
    :param capacity: lane 容量。
    :param default_timeout_seconds: 默认 acquire timeout。
    :returns: lane 配置。
    """

    return LaneConfig(
        name=name,
        capacity=capacity,
        default_timeout_seconds=default_timeout_seconds,
        claim_ttl_seconds=_FAST_TTL_SECONDS,
        heartbeat_interval_seconds=_FAST_HEARTBEAT_SECONDS,
    )


def _claim_count(db_path: Path, lane_name: str = _LANE_NAME) -> int:
    """读取指定 lane 当前 claim row 数。

    :param db_path: runtime lane DB 路径。
    :param lane_name: lane 名称。
    :returns: claim row 数。
    """

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            f"SELECT COUNT(*) FROM {_CLAIMS_TABLE} WHERE lane_name = ?",
            (lane_name,),
        ).fetchone()
        assert row is not None
        return int(row[0])
    finally:
        connection.close()


def _delete_claim(db_path: Path, claim_id: str) -> None:
    """直接删除测试 claim row，用于模拟 claim 丢失。

    :param db_path: runtime lane DB 路径。
    :param claim_id: claim id。
    :returns: ``None``。
    """

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            f"DELETE FROM {_CLAIMS_TABLE} WHERE claim_id = ?",
            (claim_id,),
        )
        connection.commit()
    finally:
        connection.close()


def _table_columns(db_path: Path) -> set[str]:
    """读取 claim table 字段集合。

    :param db_path: runtime lane DB 路径。
    :returns: 字段名集合。
    """

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(f"PRAGMA table_info({_CLAIMS_TABLE})").fetchall()
        return {str(row[1]) for row in rows}
    finally:
        connection.close()


async def _wait_for_thread_event(event: Event) -> None:
    """等待线程事件触发，避免取消竞态测试依赖随机 sleep。

    :param event: 待等待的线程事件。
    :returns: ``None``。
    """

    triggered = await asyncio.to_thread(
        event.wait, _THREAD_EVENT_TIMEOUT_SECONDS
    )
    assert triggered is True


@pytest.mark.asyncio
async def test_config_validation_and_unknown_lane(tmp_path: Path) -> None:
    """配置错误与未知 lane 必须抛结构化 runtime config error。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    with pytest.raises(RuntimeLaneConfigError):
        LaneConfig(name=" ", capacity=1)
    with pytest.raises(RuntimeLaneConfigError):
        LaneConfig(name=_LANE_NAME, capacity=0)
    with pytest.raises(RuntimeLaneConfigError):
        LaneConfig(
            name=_LANE_NAME,
            capacity=1,
            claim_ttl_seconds=0.1,
            heartbeat_interval_seconds=0.1,
        )
    with pytest.raises(RuntimeLaneConfigError):
        await LaneController.open(
            [_lane_config(), _lane_config()],
            coordinator=_coordinator(db_path),
        )

    controller = await LaneController.open(
        [_lane_config()],
        coordinator=_coordinator(db_path),
    )
    with pytest.raises(RuntimeLaneConfigError):
        await controller.acquire(_SECOND_LANE_NAME, timeout_seconds=0)


def test_lane_owner_rejects_empty_owner_id_and_invalid_pid() -> None:
    """LaneOwner 必须拒绝空 owner_id 与非法 pid。"""

    with pytest.raises(RuntimeLaneConfigError, match="owner_id"):
        LaneOwner(owner_id=" ", pid=1)
    with pytest.raises(RuntimeLaneConfigError, match="pid"):
        LaneOwner(owner_id="owner-1", pid=0)


@pytest.mark.asyncio
async def test_acquire_rejects_negative_timeout(tmp_path: Path) -> None:
    """LaneController.acquire 必须拒绝负数 timeout_seconds。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()],
        coordinator=_coordinator(db_path),
    )

    with pytest.raises(RuntimeLaneConfigError, match="timeout"):
        await controller.acquire(_LANE_NAME, timeout_seconds=-1)
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_close_is_idempotent_when_called_twice(tmp_path: Path) -> None:
    """LaneController.close 连续调用两次必须保持幂等。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()],
        coordinator=_coordinator(db_path),
    )

    await controller.close(reason="first-close")
    await controller.close(reason="second-close")


@pytest.mark.asyncio
async def test_parent_directory_creation_policy(tmp_path: Path) -> None:
    """create_parent_dirs=False 且 parent 缺失时必须抛配置错误。"""

    missing_parent = tmp_path / "missing" / "runtime_lanes.sqlite3"
    with pytest.raises(RuntimeLaneConfigError):
        await LaneController.open(
            [_lane_config()],
            coordinator=SQLiteLaneCoordinatorConfig(
                db_path=missing_parent,
                create_parent_dirs=False,
            ),
        )

    created_parent_db = tmp_path / "created" / "runtime_lanes.sqlite3"
    await LaneController.open(
        [_lane_config()],
        coordinator=SQLiteLaneCoordinatorConfig(db_path=created_parent_db),
    )
    assert created_parent_db.exists()


@pytest.mark.asyncio
async def test_parent_directory_creation_oserror_is_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """创建 SQLite parent directory 的 OSError 必须包装为配置错误。"""

    def raise_permission(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        """模拟文件系统拒绝创建目录。

        :param self: 目标路径。
        :param mode: 目录权限。
        :param parents: 是否创建父目录。
        :param exist_ok: 目录存在时是否忽略。
        :returns: 不返回。
        :raises PermissionError: 始终抛出。
        """

        del self, mode, parents, exist_ok
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "mkdir", raise_permission)

    with pytest.raises(RuntimeLaneConfigError) as exc_info:
        await LaneController.open(
            [_lane_config()],
            coordinator=SQLiteLaneCoordinatorConfig(
                db_path=tmp_path / "missing-parent" / "runtime_lanes.sqlite3",
            ),
        )
    assert isinstance(exc_info.value.__cause__, PermissionError)


@pytest.mark.asyncio
async def test_database_init_sets_wal_and_schema_has_no_host_or_fins_fields(
    tmp_path: Path,
) -> None:
    """DB 初始化必须使用独立 runtime schema，且不包含 Host / Fins 字段。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    await LaneController.open([_lane_config()], coordinator=_coordinator(db_path))

    connection = sqlite3.connect(db_path)
    try:
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
    finally:
        connection.close()

    assert journal_mode.lower() == "wal"
    columns = _table_columns(db_path)
    assert {
        "lane_name",
        "claim_id",
        "owner_id",
        "owner_pid",
        "owner_process_start_token",
        "created_at",
        "heartbeat_at",
        "expires_at",
    } <= columns
    forbidden_columns = {
        "session_id",
        "run_id",
        "attempt_id",
        "event_sequence",
        "event_id",
        "tool_name",
        "fins_document_id",
    }
    assert columns.isdisjoint(forbidden_columns)


@pytest.mark.asyncio
async def test_acquire_refresh_and_release(tmp_path: Path) -> None:
    """成功 acquire 后可以 refresh，并可通过 release 释放容量。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )

    outcome = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(outcome, LaneAcquired)
    token = outcome.token
    assert _claim_count(db_path) == 1

    old_expires_at = token.expires_at
    await asyncio.sleep(_FAST_POLL_SECONDS)
    await token.refresh()
    assert token.expires_at > old_expires_at

    await token.release()
    assert token.released is True
    assert _claim_count(db_path) == 0
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_await_task_after_outer_cancellation_yields_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外层取消后等待 shielded task 时必须先退避，避免紧循环。"""

    original_sleep = asyncio.sleep
    sleep_delays: list[float] = []
    complete = asyncio.Event()

    async def fake_sleep(delay: float, result: object | None = None) -> object | None:
        """记录 sleep 调用并让出事件循环。

        :param delay: sleep 秒数。
        :param result: sleep 返回值。
        :returns: ``result``。
        """

        sleep_delays.append(delay)
        return await original_sleep(0, result=result)

    async def pending_task() -> str:
        """等待测试释放后返回结果。

        :returns: 完成标记。
        """

        await complete.wait()
        return "done"

    monkeypatch.setattr(lane_module.asyncio, "sleep", fake_sleep)
    target = asyncio.create_task(pending_task())
    waiter = asyncio.create_task(_await_task_after_outer_cancellation(target))
    await original_sleep(0)

    waiter.cancel()
    await original_sleep(0)
    complete.set()

    assert await waiter == "done"
    assert sleep_delays == [lane_module._OUTER_CANCELLATION_SETTLE_SLEEP_SECONDS]


@pytest.mark.asyncio
async def test_refresh_waits_for_shielded_success_after_outer_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh 被外层取消时必须等待底层成功结果并更新 token 状态。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    outcome = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(outcome, LaneAcquired)
    refresh_started = Event()
    finish_refresh = Event()
    refresh_finished = Event()
    new_expires_at = outcome.token.expires_at + timedelta(seconds=10)

    def slow_successful_refresh(token: LaneClaimToken) -> datetime:
        """阻塞同步 refresh，让测试能稳定取消外层 task。

        :param token: 待刷新的 token，本测试只校验其 claim id。
        :returns: 新的 token 过期时间。
        """

        assert token.claim_id == outcome.token.claim_id
        refresh_started.set()
        assert finish_refresh.wait(_THREAD_EVENT_TIMEOUT_SECONDS) is True
        refresh_finished.set()
        return new_expires_at

    monkeypatch.setattr(controller, "_refresh_token_sync", slow_successful_refresh)

    refresh_task = asyncio.create_task(outcome.token.refresh())
    await _wait_for_thread_event(refresh_started)
    refresh_task.cancel()
    refresh_task.cancel()
    finish_refresh.set()

    with pytest.raises(asyncio.CancelledError):
        await refresh_task
    assert refresh_finished.is_set()
    assert outcome.token.expires_at == new_expires_at
    assert outcome.token.released is False

    await outcome.token.release()
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_refresh_cancel_cleanup_marks_lost_after_claim_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh 取消清理中发现 claim lost 时必须标记 token 丢失。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    outcome = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(outcome, LaneAcquired)
    refresh_started = Event()
    finish_refresh = Event()
    refresh_finished = Event()

    def slow_lost_refresh(token: LaneClaimToken) -> datetime:
        """阻塞同步 refresh，并模拟 claim row 已丢失。

        :param token: 待刷新的 token。
        :returns: 不返回。
        :raises RuntimeLaneClaimLostError: 始终抛出 claim lost。
        """

        refresh_started.set()
        assert finish_refresh.wait(_THREAD_EVENT_TIMEOUT_SECONDS) is True
        _delete_claim(db_path, token.claim_id)
        refresh_finished.set()
        raise RuntimeLaneClaimLostError("lane claim lost during refresh")

    monkeypatch.setattr(controller, "_refresh_token_sync", slow_lost_refresh)

    refresh_task = asyncio.create_task(outcome.token.refresh())
    await _wait_for_thread_event(refresh_started)
    refresh_task.cancel()
    finish_refresh.set()

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await refresh_task
    assert isinstance(exc_info.value.__cause__, RuntimeLaneError)
    assert refresh_finished.is_set()
    assert outcome.token.released is True
    assert _claim_count(db_path) == 0

    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_refresh_cancel_cleanup_logs_runtime_error_and_preserves_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """refresh 取消清理中遇到 runtime error 时必须收口异常并保留取消。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    outcome = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(outcome, LaneAcquired)
    refresh_started = Event()
    finish_refresh = Event()
    refresh_finished = Event()

    def slow_failed_refresh(token: LaneClaimToken) -> datetime:
        """阻塞同步 refresh，并模拟底层 runtime lane 错误。

        :param token: 待刷新的 token，本测试不使用。
        :returns: 不返回。
        :raises RuntimeLaneError: 始终抛出 refresh 失败。
        """

        del token
        refresh_started.set()
        assert finish_refresh.wait(_THREAD_EVENT_TIMEOUT_SECONDS) is True
        refresh_finished.set()
        raise RuntimeLaneError(_REFRESH_FAILED_MESSAGE)

    monkeypatch.setattr(controller, "_refresh_token_sync", slow_failed_refresh)
    caplog.set_level(logging.ERROR, logger="dayu.runtime.lane")

    refresh_task = asyncio.create_task(outcome.token.refresh())
    await _wait_for_thread_event(refresh_started)
    refresh_task.cancel()
    finish_refresh.set()

    with pytest.raises(asyncio.CancelledError):
        await refresh_task
    assert refresh_finished.is_set()
    assert outcome.token.released is False
    assert _claim_count(db_path) == 1
    assert _REFRESH_FAILED_LOG_FRAGMENT in caplog.text

    await outcome.token.release()
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_duplicate_release_is_idempotent_and_isolated(
    tmp_path: Path,
) -> None:
    """重复 release 不影响其它 claim。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config(capacity=2)],
        coordinator=_coordinator(db_path),
    )
    first = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    second = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(first, LaneAcquired)
    assert isinstance(second, LaneAcquired)

    await first.token.release()
    await first.token.release()
    assert _claim_count(db_path) == 1

    await second.token.refresh()
    assert second.token.released is False
    await second.token.release()
    assert _claim_count(db_path) == 0
    await controller.close()


@pytest.mark.asyncio
async def test_nonblocking_and_positive_timeout_do_not_occupy_capacity(
    tmp_path: Path,
) -> None:
    """capacity 满时 non-blocking 与正 timeout 都返回 timed out 且不占容量。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config(default_timeout_seconds=_SHORT_TIMEOUT_SECONDS)],
        coordinator=_coordinator(db_path),
    )
    held = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(held, LaneAcquired)

    nonblocking = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(nonblocking, LaneAcquireTimedOut)
    positive = await controller.acquire(_LANE_NAME)
    assert isinstance(positive, LaneAcquireTimedOut)
    assert _claim_count(db_path) == 1

    await held.token.release()
    after_release = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(after_release, LaneAcquired)
    await after_release.token.release()
    await controller.close()


@pytest.mark.asyncio
async def test_cancellation_token_cancels_waiting_acquire(tmp_path: Path) -> None:
    """等待 acquire 时 cancellation token 命中应返回 cancelled。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    held = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(held, LaneAcquired)
    cancel_token = _FakeCancellationToken()

    async def _cancel_soon() -> None:
        """稍后触发测试取消。

        :returns: ``None``。
        """

        await asyncio.sleep(_FAST_POLL_SECONDS * 2)
        cancel_token.cancel(reason=_CANCEL_REASON)

    trigger = asyncio.create_task(_cancel_soon())
    outcome = await controller.acquire(
        _LANE_NAME,
        token=cancel_token,
        timeout_seconds=_SLOW_OPERATION_SECONDS,
    )
    await trigger
    assert isinstance(outcome, LaneAcquireCancelled)
    assert outcome.reason == _CANCEL_REASON
    assert _claim_count(db_path) == 1
    await held.token.release()
    await controller.close()


@pytest.mark.asyncio
async def test_task_cancel_propagates_without_extra_claim(
    tmp_path: Path,
) -> None:
    """外层 ``Task.cancel`` 必须透传，且不得泄漏额外 claim。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    held = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(held, LaneAcquired)

    task = asyncio.create_task(
        controller.acquire(_LANE_NAME, timeout_seconds=_SLOW_OPERATION_SECONDS)
    )
    await asyncio.sleep(_FAST_POLL_SECONDS * 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _claim_count(db_path) == 1

    await held.token.release()
    await controller.close()


@pytest.mark.asyncio
async def test_repeated_task_cancel_during_claim_cleanup_releases_inserted_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重复外层取消不能打断已插入 claim 的 cleanup release。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    claim_started = Event()
    finish_claim = Event()
    claim_finished = Event()
    original_try_claim_once_sync = controller._try_claim_once_sync

    def slow_claim(lane_config: LaneConfig) -> _ClaimAttempt:
        """阻塞同步 claim，让测试稳定发出两次外层取消。

        :param lane_config: lane 配置。
        :returns: 原始同步 claim 结果。
        """

        claim_started.set()
        assert finish_claim.wait(_THREAD_EVENT_TIMEOUT_SECONDS) is True
        result = original_try_claim_once_sync(lane_config)
        claim_finished.set()
        return result

    monkeypatch.setattr(controller, "_try_claim_once_sync", slow_claim)

    task = asyncio.create_task(
        controller.acquire(_LANE_NAME, timeout_seconds=_SLOW_OPERATION_SECONDS)
    )
    await _wait_for_thread_event(claim_started)
    task.cancel()
    task.cancel()
    finish_claim.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    await _wait_for_thread_event(claim_finished)
    assert _claim_count(db_path) == 0
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_cancel_during_successful_claim_preserves_cancelled_error_when_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """claim 已写入但 cleanup 失败时仍必须向调用方透传 ``CancelledError``。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    claim_started = Event()
    release_claim = Event()
    original_try_claim_once_sync = controller._try_claim_once_sync

    def slow_claim(lane_config: LaneConfig) -> _ClaimAttempt:
        """阻塞同步 claim，让测试能稳定取消外层 task。

        :param lane_config: lane 配置。
        :returns: 原始同步 claim 结果。
        """

        claim_started.set()
        assert release_claim.wait(_THREAD_EVENT_TIMEOUT_SECONDS) is True
        return original_try_claim_once_sync(lane_config)

    def fail_release(lane_name: str, claim_id: str) -> None:
        """模拟取消清理阶段 release 失败。

        :param lane_name: lane 名称。
        :param claim_id: claim id。
        :returns: 不返回。
        :raises RuntimeLaneError: 始终抛出 release 失败。
        """

        del lane_name, claim_id
        raise RuntimeLaneError(_RELEASE_FAILED_MESSAGE)

    monkeypatch.setattr(controller, "_try_claim_once_sync", slow_claim)
    monkeypatch.setattr(controller, "_release_claim_sync", fail_release)
    caplog.set_level(logging.WARNING, logger="dayu.runtime.lane")

    task = asyncio.create_task(
        controller.acquire(_LANE_NAME, timeout_seconds=_SLOW_OPERATION_SECONDS)
    )
    await _wait_for_thread_event(claim_started)
    task.cancel()
    release_claim.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert _UNTRACKED_RELEASE_FAILED_LOG_FRAGMENT in caplog.text
    assert _claim_count(db_path) == 1
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_release_token_waits_for_shielded_release_after_outer_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """release 被外层取消时必须等 DB release 完成后再更新内存状态。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    acquired = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(acquired, LaneAcquired)
    release_started = Event()
    finish_release = Event()
    original_release_claim_sync = controller._release_claim_sync

    def slow_release(lane_name: str, claim_id: str) -> None:
        """阻塞同步 release，让测试能稳定取消外层 task。

        :param lane_name: lane 名称。
        :param claim_id: claim id。
        :returns: ``None``。
        """

        release_started.set()
        assert finish_release.wait(_THREAD_EVENT_TIMEOUT_SECONDS) is True
        original_release_claim_sync(lane_name, claim_id)

    monkeypatch.setattr(controller, "_release_claim_sync", slow_release)

    release_task = asyncio.create_task(acquired.token.release())
    await _wait_for_thread_event(release_started)
    release_task.cancel()
    finish_release.set()

    with pytest.raises(asyncio.CancelledError):
        await release_task
    assert acquired.token.released is True
    assert _claim_count(db_path) == 0

    reacquired = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(reacquired, LaneAcquired)
    await reacquired.token.release()
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """untracked release 在取消后失败时只记录错误并重新抛出取消。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    release_started = Event()
    finish_release = Event()

    def fail_slow_release(lane_name: str, claim_id: str) -> None:
        """模拟 untracked release 慢操作随后失败。

        :param lane_name: lane 名称。
        :param claim_id: claim id。
        :returns: 不返回。
        :raises RuntimeLaneError: 始终抛出 release 失败。
        """

        del lane_name, claim_id
        release_started.set()
        assert finish_release.wait(_THREAD_EVENT_TIMEOUT_SECONDS) is True
        raise RuntimeLaneError(_RELEASE_FAILED_MESSAGE)

    monkeypatch.setattr(controller, "_release_claim_sync", fail_slow_release)
    caplog.set_level(logging.ERROR, logger="dayu.runtime.lane")

    release_task = asyncio.create_task(
        controller._release_untracked_claim(_LANE_NAME, _MISSING_CLAIM_ID)
    )
    await _wait_for_thread_event(release_started)
    release_task.cancel()
    finish_release.set()

    with pytest.raises(asyncio.CancelledError):
        await release_task
    assert _UNTRACKED_RELEASE_FAILED_LOG_FRAGMENT in caplog.text
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_untracked_release_failure_without_outer_cancel_warns_and_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """untracked release 普通失败必须写 warning 并抛 RuntimeLaneError。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )

    def fail_release(lane_name: str, claim_id: str) -> None:
        """模拟 untracked release 普通失败。

        :param lane_name: lane 名称。
        :param claim_id: claim id。
        :returns: 不返回。
        :raises RuntimeLaneError: 始终抛出 release 失败。
        """

        del lane_name, claim_id
        raise RuntimeLaneError(_RELEASE_FAILED_MESSAGE)

    monkeypatch.setattr(controller, "_release_claim_sync", fail_release)
    caplog.set_level(logging.WARNING, logger="dayu.runtime.lane")

    with pytest.raises(RuntimeLaneError, match=_RELEASE_FAILED_MESSAGE):
        await controller._release_untracked_claim(_LANE_NAME, _MISSING_CLAIM_ID)

    assert _UNTRACKED_RELEASE_FAILED_LOG_FRAGMENT in caplog.text
    await controller.close(reason="test-done")


@pytest.mark.asyncio
async def test_close_cancels_pending_and_releases_held_tokens(
    tmp_path: Path,
) -> None:
    """close 会取消 pending acquire、释放 held token，并拒绝新 acquire。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    held = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(held, LaneAcquired)

    pending = asyncio.create_task(
        controller.acquire(_LANE_NAME, timeout_seconds=_SLOW_OPERATION_SECONDS)
    )
    await asyncio.sleep(_FAST_POLL_SECONDS * 2)
    await controller.close(reason="shutdown")
    pending_outcome = await pending

    assert isinstance(pending_outcome, LaneAcquireCancelled)
    assert pending_outcome.reason == "shutdown"
    assert _claim_count(db_path) == 0
    with pytest.raises(RuntimeLaneClosedError):
        await controller.acquire(_LANE_NAME, timeout_seconds=0)


@pytest.mark.asyncio
async def test_close_best_effort_release_continues_after_one_release_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close 遇到单个 release 失败时仍继续释放其它 held token。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config(capacity=2)], coordinator=_coordinator(db_path)
    )
    first = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    second = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(first, LaneAcquired)
    assert isinstance(second, LaneAcquired)
    original_release_claim_sync = controller._release_claim_sync

    def fail_first_release(lane_name: str, claim_id: str) -> None:
        """只让第一枚 token 的 release 失败。

        :param lane_name: lane 名称。
        :param claim_id: claim id。
        :returns: ``None``。
        :raises RuntimeLaneError: 第一枚 token release 时抛出。
        """

        if claim_id == first.token.claim_id:
            raise RuntimeLaneError(_CLOSE_RELEASE_FAILED_MESSAGE)
        original_release_claim_sync(lane_name, claim_id)

    monkeypatch.setattr(controller, "_release_claim_sync", fail_first_release)

    with pytest.raises(RuntimeLaneError, match=_CLOSE_RELEASE_FAILED_MESSAGE):
        await controller.close(reason="shutdown")

    assert _claim_count(db_path) == 1
    assert first.token.released is False
    assert second.token.released is True


@pytest.mark.asyncio
async def test_refresh_reports_lost_claim_and_release_stays_idempotent(
    tmp_path: Path,
) -> None:
    """claim row 丢失时 refresh 抛 lost，release 仍保持幂等。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()], coordinator=_coordinator(db_path)
    )
    outcome = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(outcome, LaneAcquired)

    _delete_claim(db_path, outcome.token.claim_id)
    with pytest.raises(RuntimeLaneClaimLostError):
        await outcome.token.refresh()
    await outcome.token.release()
    assert _claim_count(db_path) == 0
    await controller.close()


@pytest.mark.asyncio
async def test_heartbeat_runtime_error_stops_new_acquire(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """heartbeat 遇到 RuntimeLaneError 后停止新 acquire 并暴露结构化错误。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config()],
        coordinator=_coordinator(db_path),
    )
    held = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(held, LaneAcquired)

    def _raise_heartbeat_error(_token: LaneClaimToken) -> datetime:
        """模拟 heartbeat 中的不可恢复 SQLite runtime 错误。

        :param _token: 待刷新的 token，本测试不使用。
        :returns: 不返回；始终抛出结构化 runtime lane 错误。
        :raises RuntimeLaneError: 始终抛出。
        """

        raise RuntimeLaneError("heartbeat failed")

    monkeypatch.setattr(
        controller,
        "_refresh_token_sync",
        _raise_heartbeat_error,
    )

    observed_error: RuntimeLaneError | None = None
    for _ in range(20):
        await asyncio.sleep(_FAST_HEARTBEAT_SECONDS)
        try:
            await controller.acquire(_LANE_NAME, timeout_seconds=0)
        except RuntimeLaneError as exc:
            observed_error = exc
            break
    assert observed_error is not None
    assert str(observed_error) == "heartbeat failed"

    await controller.close(reason="cleanup")
    assert _claim_count(db_path) == 0


@pytest.mark.asyncio
async def test_heartbeat_lost_claim_does_not_close_controller(
    tmp_path: Path,
) -> None:
    """单个 token lost 只标记该 token，不关闭 controller 或影响其它 token。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config(capacity=2)],
        coordinator=_coordinator(db_path),
    )
    first = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    second = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(first, LaneAcquired)
    assert isinstance(second, LaneAcquired)

    _delete_claim(db_path, first.token.claim_id)
    for _ in range(20):
        if first.token.released:
            break
        await asyncio.sleep(_FAST_HEARTBEAT_SECONDS)

    assert first.token.released is True
    assert second.token.released is False
    await second.token.refresh()

    await second.token.release()
    after_lost = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(after_lost, LaneAcquired)
    await after_lost.token.release()
    assert _claim_count(db_path) == 0
    await controller.close()


@pytest.mark.asyncio
async def test_heartbeat_lost_claim_wakes_waiting_acquire(
    tmp_path: Path,
) -> None:
    """heartbeat 标记 lost token 后应立即唤醒等待中的 acquire。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config(capacity=1)],
        coordinator=SQLiteLaneCoordinatorConfig(
            db_path=db_path,
            busy_timeout_seconds=1.0,
            poll_interval_seconds=10.0,
        ),
    )
    first = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(first, LaneAcquired)

    waiter = asyncio.create_task(
        controller.acquire(_LANE_NAME, timeout_seconds=0.5)
    )
    await asyncio.sleep(_FAST_HEARTBEAT_SECONDS)
    _delete_claim(db_path, first.token.claim_id)
    second = await waiter

    assert isinstance(second, LaneAcquired)
    assert first.token.released is True
    await second.token.release()
    assert _claim_count(db_path) == 0
    await controller.close()


@pytest.mark.asyncio
async def test_concurrent_acquire_keeps_capacity_invariant(
    tmp_path: Path,
) -> None:
    """并发 acquire 不应突破 capacity invariant。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    capacity = 2
    controller = await LaneController.open(
        [_lane_config(capacity=capacity)],
        coordinator=_coordinator(db_path),
    )
    outcomes = await asyncio.gather(
        *[
            controller.acquire(_LANE_NAME, timeout_seconds=0)
            for _ in range(capacity * 3)
        ]
    )
    acquired = [item for item in outcomes if isinstance(item, LaneAcquired)]
    timed_out = [item for item in outcomes if isinstance(item, LaneAcquireTimedOut)]

    assert len(acquired) == capacity
    assert len(timed_out) == capacity * 2
    assert _claim_count(db_path) == capacity
    for outcome in acquired:
        await outcome.token.release()
    await controller.close()


@pytest.mark.asyncio
async def test_close_wakes_pending_acquire_and_rejects_new_claims(
    tmp_path: Path,
) -> None:
    """close 必须唤醒 pending acquire，释放 active claim，并阻止新 claim。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config(capacity=1)],
        coordinator=SQLiteLaneCoordinatorConfig(
            db_path=db_path,
            busy_timeout_seconds=1.0,
            poll_interval_seconds=10.0,
        ),
    )
    first = await controller.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(first, LaneAcquired)

    waiter = asyncio.create_task(controller.acquire(_LANE_NAME))
    await asyncio.sleep(_FAST_POLL_SECONDS)
    await controller.close(reason="close-race")
    outcome = await asyncio.wait_for(waiter, timeout=_SHORT_TIMEOUT_SECONDS)

    assert isinstance(outcome, LaneAcquireCancelled)
    assert outcome.reason == "close-race"
    assert first.token.released is True
    assert _claim_count(db_path) == 0
    with pytest.raises(RuntimeLaneClosedError):
        await controller.acquire(_LANE_NAME, timeout_seconds=0)


@pytest.mark.asyncio
async def test_close_during_slow_acquire_releases_untracked_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close 与 claim 事务并发时不得泄漏 active claim count。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    controller = await LaneController.open(
        [_lane_config(capacity=1)],
        coordinator=_coordinator(db_path),
    )
    claim_started = Event()
    finish_claim = Event()
    original_try_claim_once_sync = controller._try_claim_once_sync

    def slow_try_claim_once_sync(lane_config: LaneConfig) -> _ClaimAttempt:
        """阻塞 claim 线程，稳定制造 close/acquire 并发。

        :param lane_config: lane 配置。
        :returns: claim 尝试结果。
        """

        claim_started.set()
        assert finish_claim.wait(_THREAD_EVENT_TIMEOUT_SECONDS) is True
        return original_try_claim_once_sync(lane_config)

    monkeypatch.setattr(
        controller,
        "_try_claim_once_sync",
        slow_try_claim_once_sync,
    )

    acquire_task = asyncio.create_task(controller.acquire(_LANE_NAME))
    await _wait_for_thread_event(claim_started)
    await controller.close(reason="close-during-claim")
    finish_claim.set()
    outcome = await asyncio.wait_for(acquire_task, timeout=1.0)

    assert isinstance(outcome, LaneAcquireCancelled)
    assert outcome.reason == "close-during-claim"
    assert _claim_count(db_path) == 0
    with pytest.raises(RuntimeLaneClosedError):
        await controller.acquire(_LANE_NAME, timeout_seconds=0)
