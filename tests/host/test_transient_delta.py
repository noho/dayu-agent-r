"""Host transient delta public contract 与 runtime hub owner tests。"""

from __future__ import annotations

import asyncio
from dataclasses import fields
from datetime import UTC, datetime
from typing import Literal

import pytest

import dayu.host.transient_delta as transient_delta_module
from dayu.host import (
    HOST_TRANSIENT_DELTA_TYPE_TO_DATA,
    HostApiErrorCode,
    HostContentDelta,
    HostEvent,
    HostReasoningDelta,
    HostToolCallDelta,
    HostTransientDelta,
    HostTransientDeltaType,
    HostUnavailableDetail,
)
from dayu.host.transient_delta import (
    HostTransientDeltaHub,
    ValidatedTransientDeltaCandidate,
)

_OBSERVED_AT = datetime(2026, 7, 20, 1, 2, 3, tzinfo=UTC)


class _WaitEnteredEvent(asyncio.Event):
    """暴露 ``wait`` 已开始的 deterministic asyncio.Event barrier。"""

    def __init__(self) -> None:
        """初始化 wait-entry barrier。

        :returns: 无返回值。
        :raises Exception: ``asyncio.Event`` 构造失败时透传。
        """

        super().__init__()
        self.wait_entered = asyncio.Event()

    async def wait(self) -> Literal[True]:
        """记录 wait 已进入，再等待真实 Event state。

        :returns: Event 被 set 后返回 ``True``。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        self.wait_entered.set()
        return await super().wait()


class _PublishOnClearEvent(asyncio.Event):
    """在首次 ``clear`` 线性化点同步发布的 deterministic barrier。"""

    def __init__(
        self,
        *,
        hub: HostTransientDeltaHub,
        candidate: ValidatedTransientDeltaCandidate,
    ) -> None:
        """初始化 clear/publish 交界 barrier。

        :param hub: 首次 clear 时调用的真实 transient hub。
        :param candidate: 首次 clear 时发布的候选。
        :returns: 无返回值。
        :raises Exception: ``asyncio.Event`` 构造失败时透传。
        """

        super().__init__()
        self._hub = hub
        self._candidate = candidate
        self._armed = True

    def clear(self) -> None:
        """首次 clear 时先发布，再执行真实 clear。

        该顺序覆盖最不利交错：publish 的 ``set`` 会被随后 ``clear`` 清除，
        subscription 必须依靠 owner state recheck 恢复 readiness。

        :returns: ``None``。
        :raises Exception: 注入的发布动作失败时透传。
        """

        if self._armed:
            self._armed = False
            self._hub.publish(self._candidate)
        super().clear()


def test_public_payload_mapping_is_closed_and_strict() -> None:
    """public discriminator/data mapping 只允许三类精确 payload。

    :returns: ``None``。
    :raises AssertionError: closed mapping 或构造校验漂移时报告。
    """

    assert dict(HOST_TRANSIENT_DELTA_TYPE_TO_DATA) == {
        HostTransientDeltaType.CONTENT_DELTA: HostContentDelta,
        HostTransientDeltaType.REASONING_DELTA: HostReasoningDelta,
        HostTransientDeltaType.TOOL_CALL_DELTA: HostToolCallDelta,
    }
    content = HostContentDelta(iteration_id="iteration-1", text_delta="")
    reasoning = HostReasoningDelta(iteration_id="iteration-1", text_delta="  ")
    tool_call = HostToolCallDelta(
        iteration_id="iteration-1",
        tool_call_index=0,
        tool_call_id="",
        name_delta=None,
        arguments_delta=" ",
    )
    assert content.text_delta == ""
    assert reasoning.text_delta == "  "
    assert tool_call.tool_call_id == ""

    with pytest.raises(ValueError, match="does not match data"):
        _public_delta(
            transient_type=HostTransientDeltaType.CONTENT_DELTA,
            data=reasoning,
        )
    with pytest.raises(ValueError, match="must be positive"):
        _public_delta(runtime_sequence=0)
    with pytest.raises(ValueError, match="timezone.utc aware"):
        _public_delta(observed_at=datetime(2026, 7, 20, 1, 2, 3))
    with pytest.raises(TypeError, match="must be int"):
        HostToolCallDelta(
            iteration_id="iteration-1",
            tool_call_index=True,
            tool_call_id=None,
            name_delta=None,
            arguments_delta=None,
        )


def test_durable_and_transient_public_envelopes_have_separate_identity_fields() -> None:
    """durable 与 transient envelope 不共享 cursor/terminal 字段。

    :returns: ``None``。
    :raises AssertionError: public field boundary 漂移时报告。
    """

    durable_fields = {field.name for field in fields(HostEvent)}
    transient_fields = {field.name for field in fields(HostTransientDelta)}

    assert "thinking" not in durable_fields
    assert "runtime_id" not in durable_fields
    assert "runtime_sequence" not in durable_fields
    assert "event_id" not in transient_fields
    assert "event_sequence" not in transient_fields
    assert "terminal_status" not in transient_fields
    assert "activity" not in transient_fields


def test_hub_fanout_reuses_envelope_and_late_attach_has_no_replay() -> None:
    """hub 每次 publish 只分配一次 identity，且 attach 前增量不 replay。

    :returns: ``None``。
    :raises AssertionError: fanout identity、sequence 或 live-only 边界漂移时报告。
    """

    hub = HostTransientDeltaHub()
    first = hub.subscribe("session-1")
    hub.publish(_candidate(worker_event_index=1))
    second = hub.subscribe("session-1")
    hub.publish(_candidate(worker_event_index=2))

    first_events = first.drain_nowait()
    second_events = second.drain_nowait()

    assert [event.runtime_sequence for event in first_events] == [1, 2]
    assert [event.runtime_sequence for event in second_events] == [2]
    assert first_events[1] is second_events[0]
    assert first_events[0].runtime_id == hub.runtime_id
    assert first_events[0].dedupe_key != first_events[1].dedupe_key

    other_runtime = HostTransientDeltaHub()
    other_subscription = other_runtime.subscribe("session-1")
    other_runtime.publish(_candidate(worker_event_index=1))
    other_event = other_subscription.drain_nowait()[0]
    assert other_event.runtime_sequence == 1
    assert other_event.dedupe_key != first_events[0].dedupe_key

    unwatched_runtime = HostTransientDeltaHub()
    unwatched_runtime.publish(_candidate(worker_event_index=1))
    attached_after_publish = unwatched_runtime.subscribe("session-1")
    unwatched_runtime.publish(_candidate(worker_event_index=2))
    assert attached_after_publish.drain_nowait()[0].runtime_sequence == 2


def test_subscription_terminal_fence_detach_and_hub_close_are_local() -> None:
    """terminal fence、detach 与 hub close 只改变各自 owner state。

    :returns: ``None``。
    :raises AssertionError: fence、注册计数或 close 清理语义漂移时报告。
    """

    hub = HostTransientDeltaHub()
    detached = hub.subscribe("session-1")
    active = hub.subscribe("session-1")
    detached.close()
    assert hub.subscription_count("session-1") == 1

    active.mark_run_terminal("run-1")
    hub.publish(_candidate(worker_event_index=1, run_id="run-1"))
    hub.publish(_candidate(worker_event_index=2, run_id="run-2"))
    assert [event.run_id for event in active.drain_nowait()] == ["run-2"]

    hub.publish(_candidate(worker_event_index=3, run_id="run-2"))
    hub.close()
    assert active.is_closed is True
    assert active.drain_nowait() == ()
    assert hub.subscription_count("session-1") == 0
    hub.publish(_candidate(worker_event_index=4, run_id="run-2"))


@pytest.mark.asyncio
async def test_subscription_publish_before_wait_is_level_triggered() -> None:
    """publish-before-wait 必须从 queue owner state 立即观察 readiness。

    :returns: ``None``。
    :raises AssertionError: publish 后 readiness 或排空状态错误时报告。
    """

    hub = HostTransientDeltaHub()
    subscription = hub.subscribe("session-1")
    hub.publish(_candidate(worker_event_index=1))
    assert await subscription.wait_ready(0.1) is True
    assert len(subscription.drain_nowait()) == 1
    assert await subscription.wait_ready(0.001) is False


@pytest.mark.asyncio
async def test_subscription_wait_before_publish_wakes_at_barrier() -> None:
    """wait-before-publish 必须在真实 Event wait 已进入后可靠唤醒。

    :returns: ``None``。
    :raises AssertionError: publish 未在 timeout 内唤醒 waiter 时报告。
    """

    hub = HostTransientDeltaHub()
    subscription = hub.subscribe("session-1")
    controlled_event = _WaitEnteredEvent()
    subscription._ready = controlled_event
    waiter = asyncio.create_task(subscription.wait_ready(1.0))

    await asyncio.wait_for(controlled_event.wait_entered.wait(), timeout=0.5)
    hub.publish(_candidate(worker_event_index=1))

    assert await asyncio.wait_for(waiter, timeout=0.5) is True
    assert [event.worker_event_index for event in subscription.drain_nowait()] == [1]


@pytest.mark.asyncio
async def test_subscription_drain_clear_publish_intersection_rechecks_owner_state() -> None:
    """排空最后一项并 clear 时同步 publish 不得丢失 level-trigger wakeup。

    :returns: ``None``。
    :raises AssertionError: clear 覆盖 publish set 后未由 state recheck 修复时报告。
    """

    hub = HostTransientDeltaHub()
    subscription = hub.subscribe("session-1")
    hub.publish(_candidate(worker_event_index=1))
    controlled_event = _PublishOnClearEvent(
        hub=hub,
        candidate=_candidate(worker_event_index=2),
    )
    controlled_event.set()
    subscription._ready = controlled_event

    first = subscription.drain_nowait()

    assert [event.worker_event_index for event in first] == [1]
    assert await subscription.wait_ready(0.1) is True
    assert [event.worker_event_index for event in subscription.drain_nowait()] == [2]


@pytest.mark.asyncio
async def test_subscription_overflow_and_close_states_remain_ready() -> None:
    """overflow 与 close 都必须在 queue prefix 清空后保持 ready 并唤醒 waiter。

    :returns: ``None``。
    :raises AssertionError: overflow/close owner state 或 wakeup 丢失时报告。
    """

    overflow_hub = HostTransientDeltaHub()
    overflowed = overflow_hub.subscribe("session-1")
    for worker_event_index in range(
        1,
        transient_delta_module._TRANSIENT_WATCH_BUFFER_CAPACITY + 2,
    ):
        overflow_hub.publish(_candidate(worker_event_index=worker_event_index))
    assert len(overflowed.drain_nowait()) == transient_delta_module._TRANSIENT_WATCH_BUFFER_CAPACITY
    assert overflowed.overflow_error() is not None
    assert await overflowed.wait_ready(0.1) is True

    close_hub = HostTransientDeltaHub()
    closed = close_hub.subscribe("session-1")
    controlled_event = _WaitEnteredEvent()
    closed._ready = controlled_event
    close_waiter = asyncio.create_task(closed.wait_ready(1.0))
    await asyncio.wait_for(controlled_event.wait_entered.wait(), timeout=0.5)
    close_hub.close()
    assert await asyncio.wait_for(close_waiter, timeout=0.5) is True
    assert closed.is_closed is True


def test_slow_subscription_overflow_preserves_prefix_and_fast_watcher() -> None:
    """单个慢 watcher overflow 后保留连续前缀且不影响快 watcher。

    :returns: ``None``。
    :raises AssertionError: bounded overflow、typed error 或隔离语义漂移时报告。
    """

    hub = HostTransientDeltaHub()
    slow = hub.subscribe("session-1")
    fast = hub.subscribe("session-1")
    fast_events: list[HostTransientDelta] = []
    publish_count = transient_delta_module._TRANSIENT_WATCH_BUFFER_CAPACITY + 1

    for worker_event_index in range(1, publish_count + 1):
        hub.publish(_candidate(worker_event_index=worker_event_index))
        fast_events.extend(fast.drain_nowait())

    slow_prefix = slow.drain_nowait()
    overflow = slow.overflow_error()
    assert len(slow_prefix) == transient_delta_module._TRANSIENT_WATCH_BUFFER_CAPACITY
    assert [event.runtime_sequence for event in slow_prefix] == list(
        range(1, transient_delta_module._TRANSIENT_WATCH_BUFFER_CAPACITY + 1)
    )
    assert overflow is not None
    assert overflow.code is HostApiErrorCode.UNAVAILABLE
    assert overflow.retryable is True
    assert overflow.detail == HostUnavailableDetail(
        component="session_live_stream",
        reason_code="slow_consumer",
    )
    assert len(fast_events) == publish_count
    assert hub.subscription_count("session-1") == 1

    hub.publish(_candidate(worker_event_index=publish_count + 1))
    assert fast.drain_nowait()[0].worker_event_index == publish_count + 1
    assert slow.drain_nowait() == ()


def _candidate(
    *,
    worker_event_index: int,
    run_id: str = "run-1",
) -> ValidatedTransientDeltaCandidate:
    """构造有效 reasoning 瞬态候选。

    :param worker_event_index: execution 内事件序号。
    :param run_id: 关联 Run 标识。
    :returns: 有效候选。
    :raises ValueError: 输入违反 candidate contract 时抛出。
    """

    return ValidatedTransientDeltaCandidate(
        session_id="session-1",
        run_id=run_id,
        attempt_id="attempt-1",
        execution_id="execution-1",
        worker_event_index=worker_event_index,
        observed_at=_OBSERVED_AT,
        type=HostTransientDeltaType.REASONING_DELTA,
        data=HostReasoningDelta(
            iteration_id="iteration-1",
            text_delta=f"delta-{worker_event_index}",
        ),
    )


def _public_delta(
    *,
    transient_type: HostTransientDeltaType = HostTransientDeltaType.CONTENT_DELTA,
    data: HostContentDelta | HostReasoningDelta | HostToolCallDelta | None = None,
    runtime_sequence: int = 1,
    observed_at: datetime = _OBSERVED_AT,
) -> HostTransientDelta:
    """构造 public 瞬态 envelope。

    :param transient_type: public discriminator。
    :param data: public payload；``None`` 时构造 content payload。
    :param runtime_sequence: 当前 runtime 序列。
    :param observed_at: UTC 观测时间。
    :returns: public 瞬态 envelope。
    :raises ValueError: discriminator、identity、sequence 或时间非法时抛出。
    """

    public_data = HostContentDelta(iteration_id="iteration-1", text_delta="delta") if data is None else data
    return HostTransientDelta(
        runtime_id="runtime-1",
        runtime_sequence=runtime_sequence,
        session_id="session-1",
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        worker_event_index=1,
        observed_at=observed_at,
        type=transient_type,
        data=public_data,
        dedupe_key="dedupe-1",
    )
