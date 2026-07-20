"""Host execution health 与 admission lease owner-level 测试。"""

from __future__ import annotations

import asyncio

import pytest

from dayu.host import (
    HostApiError,
    HostApiErrorCode,
    HostClosedError,
    HostUnavailableDetail,
)
from dayu.host._execution_health import (
    HostExecutionHealthGate,
    HostExecutionHealthState,
)


@pytest.mark.asyncio
async def test_health_gate_starting_ready_unavailable_and_close_contract() -> None:
    """gate 只在 READY 接受 new work，fatal detail 保持首个真源。

    :returns: ``None``。
    """

    gate = HostExecutionHealthGate()
    assert gate.state is HostExecutionHealthState.STARTING

    with pytest.raises(HostApiError) as starting_error:
        await gate.acquire_admission()
    assert starting_error.value.code is HostApiErrorCode.UNAVAILABLE
    assert starting_error.value.retryable is True
    assert starting_error.value.detail == HostUnavailableDetail(
        component="host",
        reason_code="execution_starting",
    )

    gate.mark_ready()
    assert gate.state is HostExecutionHealthState.READY
    assert await gate.report_fatal(
        component="dispatch",
        reason_code="injected_critical_exit",
    )
    assert gate.state is HostExecutionHealthState.UNAVAILABLE
    assert not await gate.report_fatal(
        component="heartbeat",
        reason_code="later_exit",
    )

    with pytest.raises(HostApiError) as unavailable_error:
        await gate.acquire_admission()
    assert unavailable_error.value.code is HostApiErrorCode.UNAVAILABLE
    assert unavailable_error.value.detail == HostUnavailableDetail(
        component="dispatch",
        reason_code="injected_critical_exit",
    )

    await gate.begin_closing()
    assert gate.state is HostExecutionHealthState.CLOSING
    with pytest.raises(HostClosedError):
        gate.raise_if_public_closed()
    gate.mark_closed()
    assert gate.state is HostExecutionHealthState.CLOSED


@pytest.mark.asyncio
async def test_admission_first_future_settles_before_fatal_transition() -> None:
    """admission 先持 lease 时 actor future 收口后 fatal 才能提交。

    :returns: ``None``。
    """

    gate = HostExecutionHealthGate()
    gate.mark_ready()
    lease = await gate.acquire_admission()
    actor_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    lease.release_when_done(actor_future)
    fatal_started = asyncio.Event()

    async def report_fatal() -> bool:
        """记录 fatal 已开始并调用真实 health owner。

        :returns: fatal 是否提交 transition。
        :raises Exception: health owner 异常时透传。
        """

        fatal_started.set()
        return await gate.report_fatal(
            component="dispatch",
            reason_code="injected_critical_exit",
        )

    fatal_task = asyncio.create_task(report_fatal())
    await fatal_started.wait()
    assert gate.state is HostExecutionHealthState.READY

    actor_future.set_result("committed-and-woken")
    assert await fatal_task is True
    assert actor_future.result() == "committed-and-woken"
    assert gate.state is HostExecutionHealthState.UNAVAILABLE


@pytest.mark.asyncio
async def test_caller_cancellation_does_not_release_admission_future_lease() -> None:
    """caller awaiter 取消后 lease 仍覆盖底层 actor future 与 fatal 排序。

    :returns: ``None``。
    """

    gate = HostExecutionHealthGate()
    gate.mark_ready()
    actor_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    actor_submitted = asyncio.Event()
    fatal_started = asyncio.Event()

    async def invoke_actor() -> str:
        """模拟 public new-work 对 actor future 的 shield 等待。

        :returns: actor future 的结果。
        :raises asyncio.CancelledError: caller task 被取消时抛出。
        """

        lease = await gate.acquire_admission()
        lease.release_when_done(actor_future)
        actor_submitted.set()
        return await asyncio.shield(actor_future)

    async def report_fatal() -> bool:
        """记录 fatal 开始并提交真实 health transition。

        :returns: fatal 是否提交 transition。
        :raises Exception: health owner 异常时透传。
        """

        fatal_started.set()
        return await gate.report_fatal(
            component="promotion",
            reason_code="injected_critical_exit",
        )

    caller_task = asyncio.create_task(invoke_actor())
    await actor_submitted.wait()
    caller_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller_task

    fatal_task = asyncio.create_task(report_fatal())
    await fatal_started.wait()
    assert gate.state is HostExecutionHealthState.READY
    actor_future.set_result("committed-and-woken")
    assert await fatal_task is True
    assert gate.state is HostExecutionHealthState.UNAVAILABLE


@pytest.mark.asyncio
async def test_fatal_first_rejects_admission_without_operation_submission() -> None:
    """fatal 先提交后 new-work 在 operation submission 前返回 typed unavailable。

    :returns: ``None``。
    """

    gate = HostExecutionHealthGate()
    gate.mark_ready()
    assert await gate.report_fatal(
        component="heartbeat",
        reason_code="critical_task_unexpected_exit",
    )
    operation_submitted = False

    with pytest.raises(HostApiError) as exc_info:
        await gate.acquire_admission()
        operation_submitted = True

    assert operation_submitted is False
    assert exc_info.value.code is HostApiErrorCode.UNAVAILABLE
    assert exc_info.value.retryable is True
    assert exc_info.value.detail == HostUnavailableDetail(
        component="heartbeat",
        reason_code="critical_task_unexpected_exit",
    )
