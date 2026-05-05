"""``dayu.runtime.cancellation`` helper 测试。

覆盖 :func:`await_or_cancel` / :func:`wait_for_or_cancel` 的所有分支：
正常完成、token 命中、timeout、cancellation 与 timeout 同时命中（cancel
优先）、外层 ``Task.cancel()`` 透传、target task ownership 语义。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from dayu.runtime.cancellation import (
    WaitCancelled,
    WaitCompleted,
    WaitTimedOut,
    await_or_cancel,
    wait_for_or_cancel,
)


class _FakeToken:
    """轻量 :class:`CancellationToken` 实现，仅供测试。"""

    def __init__(self) -> None:
        """初始化为未取消状态。"""

        self._cancelled: bool = False
        self._reason: str | None = None
        self._requested_at: datetime | None = None

    def cancel(self, *, reason: str | None = "test-cancel") -> None:
        """触发取消。"""

        self._cancelled = True
        self._reason = reason
        self._requested_at = datetime.now(timezone.utc)

    def is_cancelled(self) -> bool:
        """返回是否已取消。"""

        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。"""

        return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。"""

        return self._requested_at


_FAST_POLL = 0.005


@pytest.mark.asyncio
async def test_await_or_cancel_returns_completed_on_success() -> None:
    """awaitable 正常完成时返回 :class:`WaitCompleted`。"""

    async def _ok() -> int:
        await asyncio.sleep(0)
        return 42

    token = _FakeToken()
    outcome = await await_or_cancel(
        _ok(), token=token, poll_interval_seconds=_FAST_POLL
    )
    assert isinstance(outcome, WaitCompleted)
    assert outcome.value == 42


@pytest.mark.asyncio
async def test_await_or_cancel_returns_cancelled_when_token_hits() -> None:
    """token 在 awaitable 完成前命中时返回 :class:`WaitCancelled`。"""

    token = _FakeToken()

    async def _slow() -> int:
        await asyncio.sleep(5)
        return 0

    async def _trigger() -> None:
        await asyncio.sleep(_FAST_POLL * 2)
        token.cancel(reason="user-stop")

    trigger_task = asyncio.ensure_future(_trigger())
    try:
        outcome = await await_or_cancel(
            _slow(), token=token, poll_interval_seconds=_FAST_POLL
        )
    finally:
        await trigger_task
    assert isinstance(outcome, WaitCancelled)
    assert outcome.reason == "user-stop"


@pytest.mark.asyncio
async def test_await_or_cancel_short_circuits_when_already_cancelled() -> None:
    """token 在调用前已取消时直接返回 cancelled，不启动 awaitable。"""

    token = _FakeToken()
    token.cancel(reason="pre-cancelled")

    started = False

    async def _never_started() -> None:
        nonlocal started
        started = True

    coro = _never_started()
    outcome = await await_or_cancel(
        coro, token=token, poll_interval_seconds=_FAST_POLL
    )
    assert isinstance(outcome, WaitCancelled)
    assert outcome.reason == "pre-cancelled"
    assert started is False


@pytest.mark.asyncio
async def test_await_or_cancel_owns_target_and_cancels_on_token_hit() -> None:
    """token 命中时 helper 必须取消并等待 target task done，不留后台任务。"""

    token = _FakeToken()
    target_done = asyncio.Event()
    target_was_cancelled = False

    async def _target() -> None:
        nonlocal target_was_cancelled
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            target_was_cancelled = True
            raise
        finally:
            target_done.set()

    async def _trigger() -> None:
        await asyncio.sleep(_FAST_POLL * 2)
        token.cancel()

    trigger_task = asyncio.ensure_future(_trigger())
    try:
        outcome = await await_or_cancel(
            _target(), token=token, poll_interval_seconds=_FAST_POLL
        )
    finally:
        await trigger_task
    assert isinstance(outcome, WaitCancelled)
    # helper 返回时 target 必须已经 done（被 cancel + await 收口）。
    assert target_done.is_set()
    assert target_was_cancelled is True


@pytest.mark.asyncio
async def test_await_or_cancel_propagates_awaitable_exception() -> None:
    """awaitable 自身异常应原样透传。"""

    class _Boom(RuntimeError):
        pass

    async def _raises() -> None:
        raise _Boom("kaboom")

    token = _FakeToken()
    with pytest.raises(_Boom, match="kaboom"):
        await await_or_cancel(
            _raises(), token=token, poll_interval_seconds=_FAST_POLL
        )


@pytest.mark.asyncio
async def test_await_or_cancel_propagates_outer_cancel() -> None:
    """外层 ``Task.cancel()`` 必须透传，helper 不吞 ``CancelledError``。"""

    token = _FakeToken()

    async def _slow() -> None:
        await asyncio.sleep(5)

    async def _outer() -> None:
        await await_or_cancel(
            _slow(), token=token, poll_interval_seconds=_FAST_POLL
        )

    outer = asyncio.ensure_future(_outer())
    await asyncio.sleep(_FAST_POLL * 2)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer


@pytest.mark.asyncio
async def test_wait_for_or_cancel_returns_completed_on_pending_done() -> None:
    """pending 完成时返回 :class:`WaitCompleted` 并保留调用方所有权。"""

    async def _ok() -> str:
        await asyncio.sleep(0)
        return "value"

    pending = asyncio.ensure_future(_ok())
    token = _FakeToken()
    outcome = await wait_for_or_cancel(
        pending,
        token=token,
        timeout_seconds=1.0,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitCompleted)
    assert outcome.value == "value"
    assert pending.done()


@pytest.mark.asyncio
async def test_wait_for_or_cancel_returns_timed_out() -> None:
    """timeout 命中时返回 :class:`WaitTimedOut`，pending 不被取消。"""

    async def _slow() -> None:
        await asyncio.sleep(5)

    pending = asyncio.ensure_future(_slow())
    token = _FakeToken()
    try:
        outcome = await wait_for_or_cancel(
            pending,
            token=token,
            timeout_seconds=_FAST_POLL * 4,
            poll_interval_seconds=_FAST_POLL,
        )
        assert isinstance(outcome, WaitTimedOut)
        assert outcome.elapsed_seconds >= 0
        # helper 不拥有 pending，pending 仍由调用方持有。
        assert not pending.done()
    finally:
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_wait_for_or_cancel_no_timeout_returns_completed() -> None:
    """``timeout_seconds=None`` 仅做 pending vs cancel 二方 race。"""

    async def _ok() -> int:
        await asyncio.sleep(_FAST_POLL)
        return 7

    pending = asyncio.ensure_future(_ok())
    token = _FakeToken()
    outcome = await wait_for_or_cancel(
        pending,
        token=token,
        timeout_seconds=None,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitCompleted)
    assert outcome.value == 7


@pytest.mark.asyncio
async def test_wait_for_or_cancel_token_priority_over_timeout() -> None:
    """token 与 timeout 同时命中时优先返回 :class:`WaitCancelled`。"""

    async def _slow() -> None:
        await asyncio.sleep(5)

    pending = asyncio.ensure_future(_slow())
    token = _FakeToken()
    token.cancel(reason="prio")
    try:
        outcome = await wait_for_or_cancel(
            pending,
            token=token,
            timeout_seconds=0.0,
            poll_interval_seconds=_FAST_POLL,
        )
        assert isinstance(outcome, WaitCancelled)
        assert outcome.reason == "prio"
        # 不拥有 pending：不取消。
        assert not pending.done()
    finally:
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_wait_for_or_cancel_does_not_cancel_pending_on_token_hit() -> None:
    """token 命中时 helper 不主动取消 pending，由调用方自行决定。"""

    async def _slow() -> None:
        await asyncio.sleep(5)

    pending = asyncio.ensure_future(_slow())
    token = _FakeToken()

    async def _trigger() -> None:
        await asyncio.sleep(_FAST_POLL * 2)
        token.cancel()

    trigger_task = asyncio.ensure_future(_trigger())
    try:
        outcome = await wait_for_or_cancel(
            pending,
            token=token,
            timeout_seconds=None,
            poll_interval_seconds=_FAST_POLL,
        )
        assert isinstance(outcome, WaitCancelled)
        assert not pending.done()
        assert not pending.cancelled()
    finally:
        await trigger_task
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_wait_for_or_cancel_propagates_outer_cancel() -> None:
    """外层 ``Task.cancel()`` 必须透传到等待协程。"""

    async def _slow() -> None:
        await asyncio.sleep(5)

    pending = asyncio.ensure_future(_slow())
    token = _FakeToken()

    async def _outer() -> None:
        await wait_for_or_cancel(
            pending,
            token=token,
            timeout_seconds=None,
            poll_interval_seconds=_FAST_POLL,
        )

    outer = asyncio.ensure_future(_outer())
    await asyncio.sleep(_FAST_POLL * 2)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer
    pending.cancel()
    try:
        await pending
    except asyncio.CancelledError:
        pass
