"""``dayu.runtime.cancellation`` helper 测试。

覆盖 :func:`await_or_cancel`、:func:`wait_for_or_cancel` 与
:func:`await_or_cancel_or_timeout` 的关键分支：正常完成、token 命中、
timeout、cancellation 与 timeout 同时命中（cancel 优先）、外层
``Task.cancel()`` 透传、target task ownership 语义。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pytest

from dayu.runtime.cancellation import (
    WaitCancelled,
    WaitCompleted,
    WaitTimedOut,
    await_or_cancel,
    await_or_cancel_or_timeout,
    wait_for_or_cancel,
    _cancel_task_and_wait,
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


_FAST_POLL: float = 0.005
_FAST_TIMEOUT_SECONDS: float = _FAST_POLL * 4
_SLOW_OPERATION_SECONDS: float = 5.0
_EXPECTED_INT_VALUE: int = 42
_EXPECTED_TEXT_VALUE: str = "value"
_CANCEL_REASON: str = "user-stop"


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", (0.0, -0.1))
async def test_await_or_cancel_rejects_non_positive_poll_interval(
    interval: float,
) -> None:
    """await_or_cancel 必须拒绝非正轮询间隔。"""

    token = _FakeToken()

    async def _target() -> None:
        """返回空结果，供非法 interval 拒绝路径测试使用。"""

        return None

    with pytest.raises(ValueError, match="poll_interval_seconds"):
        await await_or_cancel(
            _target(),
            token=token,
            poll_interval_seconds=interval,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", (0.0, -0.1))
async def test_wait_for_or_cancel_rejects_non_positive_poll_interval(
    interval: float,
) -> None:
    """wait_for_or_cancel 必须拒绝非正轮询间隔。"""

    token = _FakeToken()
    task = asyncio.ensure_future(asyncio.sleep(_SLOW_OPERATION_SECONDS))
    try:
        with pytest.raises(ValueError, match="poll_interval_seconds"):
            await wait_for_or_cancel(
                task,
                token=token,
                timeout_seconds=_FAST_TIMEOUT_SECONDS,
                poll_interval_seconds=interval,
            )
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", (0.0, -0.1))
async def test_await_or_cancel_or_timeout_rejects_non_positive_poll_interval(
    interval: float,
) -> None:
    """await_or_cancel_or_timeout 必须拒绝非正轮询间隔。"""

    token = _FakeToken()

    async def _target() -> None:
        """返回空结果，供非法 interval 拒绝路径测试使用。"""

        return None

    with pytest.raises(ValueError, match="poll_interval_seconds"):
        await await_or_cancel_or_timeout(
            _target(),
            token=token,
            timeout_seconds=_FAST_TIMEOUT_SECONDS,
            poll_interval_seconds=interval,
        )


@pytest.mark.asyncio
async def test_cancel_task_and_wait_logs_non_cancel_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """取消 cleanup 读取到普通异常时必须写 warning 诊断。"""

    async def _raise_after_cancel() -> None:
        """被取消后模拟 cleanup 编程错误。"""

        try:
            await asyncio.sleep(_SLOW_OPERATION_SECONDS)
        except asyncio.CancelledError as exc:
            raise ValueError("cleanup failed") from exc

    caplog.set_level(logging.WARNING, logger="dayu.runtime.cancellation")
    task = asyncio.create_task(_raise_after_cancel())
    await asyncio.sleep(0)

    await _cancel_task_and_wait(task)

    assert any(
        "runtime.cancellation.cancelled_task_failed" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_await_or_cancel_returns_completed_on_success() -> None:
    """awaitable 正常完成时返回 :class:`WaitCompleted`。"""

    async def _ok() -> int:
        await asyncio.sleep(0)
        return _EXPECTED_INT_VALUE

    token = _FakeToken()
    outcome = await await_or_cancel(
        _ok(), token=token, poll_interval_seconds=_FAST_POLL
    )
    assert isinstance(outcome, WaitCompleted)
    assert outcome.value == _EXPECTED_INT_VALUE


@pytest.mark.asyncio
async def test_await_or_cancel_returns_cancelled_when_token_hits() -> None:
    """token 在 awaitable 完成前命中时返回 :class:`WaitCancelled`。"""

    token = _FakeToken()

    async def _slow() -> int:
        await asyncio.sleep(_SLOW_OPERATION_SECONDS)
        return 0

    async def _trigger() -> None:
        await asyncio.sleep(_FAST_POLL * 2)
        token.cancel(reason=_CANCEL_REASON)

    trigger_task = asyncio.ensure_future(_trigger())
    try:
        outcome = await await_or_cancel(
            _slow(), token=token, poll_interval_seconds=_FAST_POLL
        )
    finally:
        await trigger_task
    assert isinstance(outcome, WaitCancelled)
    assert outcome.reason == _CANCEL_REASON


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
async def test_await_or_cancel_closes_task_when_already_cancelled() -> None:
    """入口已取消且传入 task 时，helper 必须取消并等待 target 收口。"""

    token = _FakeToken()
    target_done = asyncio.Event()

    async def _target() -> None:
        try:
            await asyncio.sleep(_SLOW_OPERATION_SECONDS)
        finally:
            target_done.set()

    task = asyncio.ensure_future(_target())
    await asyncio.sleep(0)
    token.cancel(reason=_CANCEL_REASON)

    outcome = await await_or_cancel(
        task, token=token, poll_interval_seconds=_FAST_POLL
    )
    assert isinstance(outcome, WaitCancelled)
    assert outcome.reason == _CANCEL_REASON
    assert task.done()
    assert task.cancelled()
    assert target_done.is_set()


@pytest.mark.asyncio
async def test_await_or_cancel_owns_target_and_cancels_on_token_hit() -> None:
    """token 命中时 helper 必须取消并等待 target task done，不留后台任务。"""

    token = _FakeToken()
    target_done = asyncio.Event()
    target_was_cancelled = False

    async def _target() -> None:
        nonlocal target_was_cancelled
        try:
            await asyncio.sleep(_SLOW_OPERATION_SECONDS)
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
        await asyncio.sleep(_SLOW_OPERATION_SECONDS)

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
async def test_await_or_cancel_outer_cancel_closes_target() -> None:
    """外层取消时 helper 必须取消并等待 target task 收口，不留孤儿协程。"""

    token = _FakeToken()
    target_done = asyncio.Event()
    target_received_cancel = False

    async def _slow() -> None:
        nonlocal target_received_cancel
        try:
            await asyncio.sleep(_SLOW_OPERATION_SECONDS)
        except asyncio.CancelledError:
            target_received_cancel = True
            raise
        finally:
            target_done.set()

    async def _outer() -> None:
        await await_or_cancel(
            _slow(), token=token, poll_interval_seconds=_FAST_POLL
        )

    outer = asyncio.ensure_future(_outer())
    await asyncio.sleep(_FAST_POLL * 2)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer
    # 外层取消透传后，target task 必须已经被 helper 取消并收口。
    assert target_done.is_set()
    assert target_received_cancel is True


@pytest.mark.asyncio
async def test_wait_for_or_cancel_returns_completed_on_pending_done() -> None:
    """pending 完成时返回 :class:`WaitCompleted` 并保留调用方所有权。"""

    async def _ok() -> str:
        await asyncio.sleep(0)
        return _EXPECTED_TEXT_VALUE

    pending = asyncio.ensure_future(_ok())
    token = _FakeToken()
    outcome = await wait_for_or_cancel(
        pending,
        token=token,
        timeout_seconds=_SLOW_OPERATION_SECONDS,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitCompleted)
    assert outcome.value == _EXPECTED_TEXT_VALUE
    assert pending.done()


@pytest.mark.asyncio
async def test_wait_for_or_cancel_returns_timed_out() -> None:
    """timeout 命中时返回 :class:`WaitTimedOut`，pending 不被取消。"""

    async def _slow() -> None:
        await asyncio.sleep(_SLOW_OPERATION_SECONDS)

    pending = asyncio.ensure_future(_slow())
    token = _FakeToken()
    try:
        outcome = await wait_for_or_cancel(
            pending,
            token=token,
            timeout_seconds=_FAST_TIMEOUT_SECONDS,
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
        await asyncio.sleep(_SLOW_OPERATION_SECONDS)

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
        await asyncio.sleep(_SLOW_OPERATION_SECONDS)

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
        await asyncio.sleep(_SLOW_OPERATION_SECONDS)

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


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_returns_completed() -> None:
    """awaitable 正常完成时返回 :class:`WaitCompleted`。"""

    async def _ok() -> str:
        await asyncio.sleep(0)
        return _EXPECTED_TEXT_VALUE

    token = _FakeToken()
    outcome = await await_or_cancel_or_timeout(
        _ok(),
        token=token,
        timeout_seconds=_SLOW_OPERATION_SECONDS,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitCompleted)
    assert outcome.value == _EXPECTED_TEXT_VALUE


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_returns_cancelled() -> None:
    """token 命中时取消 target task 并返回 :class:`WaitCancelled`。"""

    token = _FakeToken()

    async def _slow() -> None:
        await asyncio.sleep(_SLOW_OPERATION_SECONDS)

    async def _trigger() -> None:
        await asyncio.sleep(_FAST_POLL * 2)
        token.cancel(reason=_CANCEL_REASON)

    trigger_task = asyncio.ensure_future(_trigger())
    try:
        outcome = await await_or_cancel_or_timeout(
            _slow(),
            token=token,
            timeout_seconds=_SLOW_OPERATION_SECONDS,
            poll_interval_seconds=_FAST_POLL,
        )
    finally:
        await trigger_task
    assert isinstance(outcome, WaitCancelled)
    assert outcome.reason == _CANCEL_REASON


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_returns_timed_out() -> None:
    """timeout 命中时取消 target task 并返回 :class:`WaitTimedOut`。"""

    token = _FakeToken()
    target_done = asyncio.Event()

    async def _slow() -> None:
        try:
            await asyncio.sleep(_SLOW_OPERATION_SECONDS)
        finally:
            target_done.set()

    outcome = await await_or_cancel_or_timeout(
        _slow(),
        token=token,
        timeout_seconds=_FAST_TIMEOUT_SECONDS,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitTimedOut)
    assert outcome.elapsed_seconds >= 0
    assert target_done.is_set()


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_cancel_priority_over_timeout() -> None:
    """cancellation 与 timeout 同时命中时返回 :class:`WaitCancelled`。"""

    token = _FakeToken()
    token.cancel(reason="prio")

    async def _slow() -> None:
        await asyncio.sleep(_SLOW_OPERATION_SECONDS)

    outcome = await await_or_cancel_or_timeout(
        _slow(),
        token=token,
        timeout_seconds=0.0,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitCancelled)
    assert outcome.reason == "prio"


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_short_circuits_when_cancelled() -> None:
    """入口已取消时不启动 target awaitable。"""

    token = _FakeToken()
    token.cancel(reason=_CANCEL_REASON)
    started = False

    async def _target() -> None:
        nonlocal started
        started = True

    outcome = await await_or_cancel_or_timeout(
        _target(),
        token=token,
        timeout_seconds=_SLOW_OPERATION_SECONDS,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitCancelled)
    assert outcome.reason == _CANCEL_REASON
    assert started is False


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_closes_task_when_cancelled() -> None:
    """入口已取消且传入 task 时，helper 仍取消并等待 target 收口。"""

    token = _FakeToken()
    target_done = asyncio.Event()

    async def _target() -> None:
        try:
            await asyncio.sleep(_SLOW_OPERATION_SECONDS)
        finally:
            target_done.set()

    task = asyncio.ensure_future(_target())
    await asyncio.sleep(0)
    token.cancel(reason=_CANCEL_REASON)

    outcome = await await_or_cancel_or_timeout(
        task,
        token=token,
        timeout_seconds=_SLOW_OPERATION_SECONDS,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitCancelled)
    assert outcome.reason == _CANCEL_REASON
    assert task.done()
    assert task.cancelled()
    assert target_done.is_set()


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_propagates_awaitable_exception() -> None:
    """awaitable 自身异常应原样透传。"""

    class _Boom(RuntimeError):
        pass

    async def _raises() -> None:
        raise _Boom("kaboom")

    token = _FakeToken()
    with pytest.raises(_Boom, match="kaboom"):
        await await_or_cancel_or_timeout(
            _raises(),
            token=token,
            timeout_seconds=_SLOW_OPERATION_SECONDS,
            poll_interval_seconds=_FAST_POLL,
        )


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_outer_cancel_closes_target() -> None:
    """外层取消时 helper 必须取消 target task 并透传 ``CancelledError``。"""

    token = _FakeToken()
    target_done = asyncio.Event()

    async def _slow() -> None:
        try:
            await asyncio.sleep(_SLOW_OPERATION_SECONDS)
        finally:
            target_done.set()

    async def _outer() -> None:
        await await_or_cancel_or_timeout(
            _slow(),
            token=token,
            timeout_seconds=_SLOW_OPERATION_SECONDS,
            poll_interval_seconds=_FAST_POLL,
        )

    outer = asyncio.ensure_future(_outer())
    await asyncio.sleep(_FAST_POLL * 2)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer
    assert target_done.is_set()


@pytest.mark.asyncio
async def test_await_or_cancel_or_timeout_target_receives_cancelled_error() -> None:
    """timeout 路径必须让 target 收到 ``asyncio.CancelledError``。"""

    token = _FakeToken()
    target_received_cancel = False

    async def _slow() -> None:
        nonlocal target_received_cancel
        try:
            await asyncio.sleep(_SLOW_OPERATION_SECONDS)
        except asyncio.CancelledError:
            target_received_cancel = True
            raise

    outcome = await await_or_cancel_or_timeout(
        _slow(),
        token=token,
        timeout_seconds=_FAST_TIMEOUT_SECONDS,
        poll_interval_seconds=_FAST_POLL,
    )
    assert isinstance(outcome, WaitTimedOut)
    assert target_received_cancel is True
