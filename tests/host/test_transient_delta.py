"""Host transient delta public contract 与 bounded resource owner tests。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import fields
from datetime import UTC, datetime
from typing import Literal

import pytest

from dayu.host import (
    HOST_TRANSIENT_DELTA_TYPE_TO_DATA,
    HostApiError,
    HostApiErrorCode,
    HostContentDelta,
    HostEvent,
    HostReasoningDelta,
    HostSessionEventAdmissionDetail,
    HostSessionEventAdmissionReason,
    HostSessionEventDeliveryDetail,
    HostSessionEventDeliveryPolicy,
    HostSessionEventDeliveryReason,
    HostToolCallDelta,
    HostTransientDelta,
    HostTransientDeltaType,
)
from dayu.host.transient_delta import (
    HostTransientDeltaHub,
    HostTransientDeltaSubscription,
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
        :raises Exception: 注入的发布动作失败时透传。
        """

        super().__init__()
        self._hub = hub
        self._candidate = candidate
        self._armed = True

    def clear(self) -> None:
        """首次 clear 时先发布，再执行真实 clear。

        :returns: ``None``。
        :raises Exception: 注入的发布动作失败时透传。
        """

        if self._armed:
            self._armed = False
            self._hub.publish(self._candidate)
        super().clear()


def test_public_payload_mapping_is_closed_and_strict() -> None:
    """public discriminator/data mapping 只允许三类精确 payload。"""

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
    """durable 与 transient envelope 不共享 cursor/terminal 字段。"""

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
    """hub 每次 publish 只分配一次 identity，且 attach 前增量不 replay。"""

    hub = _hub()
    first = _attach(hub, "session-1")
    hub.publish(_candidate(worker_event_index=1))
    second = _attach(hub, "session-1")
    hub.publish(_candidate(worker_event_index=2))

    first_event = first.pop_next_nowait()
    first.release_in_flight()
    shared_first_event = first.pop_next_nowait()
    shared_second_event = second.pop_next_nowait()

    assert first_event is not None
    assert shared_first_event is not None
    assert shared_second_event is not None
    assert [first_event.runtime_sequence, shared_first_event.runtime_sequence] == [1, 2]
    assert shared_second_event.runtime_sequence == 2
    assert shared_first_event is shared_second_event
    assert first_event.runtime_id == hub.runtime_id
    assert first_event.dedupe_key != shared_first_event.dedupe_key

    other_runtime = _hub()
    other_subscription = _attach(other_runtime, "session-1")
    other_runtime.publish(_candidate(worker_event_index=1))
    other_event = other_subscription.pop_next_nowait()
    assert other_event is not None
    assert other_event.runtime_sequence == 1
    assert other_event.dedupe_key != first_event.dedupe_key

    unwatched_runtime = _hub()
    unwatched_runtime.publish(_candidate(worker_event_index=1))
    attached_after_publish = _attach(unwatched_runtime, "session-1")
    unwatched_runtime.publish(_candidate(worker_event_index=2))
    late_event = attached_after_publish.pop_next_nowait()
    assert late_event is not None
    assert late_event.runtime_sequence == 2


def test_subscription_terminal_fence_detach_and_hub_close_are_local() -> None:
    """terminal fence、detach 与 hub close 只改变各自 owner state。"""

    hub = _hub()
    detached = _attach(hub, "session-1")
    active = _attach(hub, "session-1")
    detached.close()
    assert hub.subscription_count("session-1") == 1
    assert hub.reservation_count("session-1") == 1

    active.mark_run_terminal("run-1")
    hub.publish(_candidate(worker_event_index=1, run_id="run-1"))
    hub.publish(_candidate(worker_event_index=2, run_id="run-2"))
    event = active.pop_next_nowait()
    assert event is not None
    assert event.run_id == "run-2"

    hub.publish(_candidate(worker_event_index=3, run_id="run-2"))
    hub.close()
    assert active.is_closed is True
    assert active.retained_items == 0
    assert hub.subscription_count("session-1") == 0
    assert hub.reservation_count("session-1") == 0
    hub.publish(_candidate(worker_event_index=4, run_id="run-2"))


def test_single_pop_filters_prequeued_terminal_stale_item() -> None:
    """single-pop 跳过预存 terminal stale item 并维持 retained/readiness。

    :returns: ``None``。
    :raises AssertionError: stale 进入 in-flight 或 owner accounting 漂移时抛出。
    """

    hub = _hub()
    with_followup = _attach(hub, "session-1")
    hub.publish(_candidate(worker_event_index=1, run_id="run-1"))
    hub.publish(_candidate(worker_event_index=2, run_id="run-2"))
    assert with_followup.retained_items == 2

    with_followup.mark_run_terminal("run-1")
    assert with_followup._ready.is_set() is True
    followup = with_followup.pop_next_nowait()

    assert followup is not None
    assert followup.run_id == "run-2"
    assert with_followup.retained_items == 1
    assert with_followup._ready.is_set() is False
    with_followup.release_in_flight()
    assert with_followup.retained_items == 0

    stale_only = _attach(hub, "session-2")
    hub.publish(
        _candidate(
            worker_event_index=3,
            session_id="session-2",
            run_id="run-3",
        )
    )
    assert stale_only.retained_items == 1

    stale_only.mark_run_terminal("run-3")
    assert stale_only._ready.is_set() is True
    assert stale_only.pop_next_nowait() is None
    assert stale_only.retained_items == 0
    assert stale_only._ready.is_set() is False


@pytest.mark.asyncio
async def test_subscription_publish_before_wait_is_level_triggered() -> None:
    """publish-before-wait 必须从 mailbox owner state 立即观察 readiness。"""

    hub = _hub()
    subscription = _attach(hub, "session-1")
    hub.publish(_candidate(worker_event_index=1))
    assert await subscription.wait_ready(0.1) is True
    assert subscription.pop_next_nowait() is not None
    subscription.release_in_flight()
    assert await subscription.wait_ready(0.001) is False


@pytest.mark.asyncio
async def test_subscription_wait_before_publish_wakes_at_barrier() -> None:
    """wait-before-publish 必须在真实 Event wait 已进入后可靠唤醒。"""

    hub = _hub()
    subscription = _attach(hub, "session-1")
    controlled_event = _WaitEnteredEvent()
    subscription._ready = controlled_event
    waiter = asyncio.create_task(subscription.wait_ready(1.0))

    await asyncio.wait_for(controlled_event.wait_entered.wait(), timeout=0.5)
    hub.publish(_candidate(worker_event_index=1))

    assert await asyncio.wait_for(waiter, timeout=0.5) is True
    event = subscription.pop_next_nowait()
    assert event is not None
    assert event.worker_event_index == 1


@pytest.mark.asyncio
async def test_single_pop_clear_publish_intersection_rechecks_owner_state() -> None:
    """转移最后一项并 clear 时同步 publish 不得丢失 level-trigger wakeup。"""

    hub = _hub()
    subscription = _attach(hub, "session-1")
    hub.publish(_candidate(worker_event_index=1))
    controlled_event = _PublishOnClearEvent(
        hub=hub,
        candidate=_candidate(worker_event_index=2),
    )
    controlled_event.set()
    subscription._ready = controlled_event

    first = subscription.pop_next_nowait()
    assert first is not None
    assert first.worker_event_index == 1
    subscription.release_in_flight()
    assert await subscription.wait_ready(0.1) is True
    second = subscription.pop_next_nowait()
    assert second is not None
    assert second.worker_event_index == 2


@pytest.mark.asyncio
async def test_subscription_overflow_and_close_states_remain_ready() -> None:
    """overflow 与 close 都必须在 prefix 清空后保持 ready 并唤醒 waiter。"""

    overflow_hub = _hub(mailbox_max_items=2)
    overflowed = _attach(overflow_hub, "session-1")
    for worker_event_index in range(1, 4):
        overflow_hub.publish(_candidate(worker_event_index=worker_event_index))
    assert overflowed.pop_next_nowait() is not None
    overflowed.release_in_flight()
    assert overflowed.pop_next_nowait() is not None
    overflowed.release_in_flight()
    assert overflowed.overflow_error() is not None
    assert await overflowed.wait_ready(0.1) is True

    close_hub = _hub()
    closed = _attach(close_hub, "session-1")
    controlled_event = _WaitEnteredEvent()
    closed._ready = controlled_event
    close_waiter = asyncio.create_task(closed.wait_ready(1.0))
    await asyncio.wait_for(controlled_event.wait_entered.wait(), timeout=0.5)
    close_hub.close()
    assert await asyncio.wait_for(close_waiter, timeout=0.5) is True
    assert closed.is_closed is True


def test_retained_item_prospective_check_counts_unique_in_flight() -> None:
    """511→512 可接受，唯一 in-flight 保持计数，下一项被拒绝且不入队。"""

    hub = _hub(mailbox_max_items=512)
    subscription = _attach(hub, "session-1")
    for worker_event_index in range(1, 512):
        hub.publish(_candidate(worker_event_index=worker_event_index))
    assert subscription.retained_items == 511

    first = subscription.pop_next_nowait()
    assert first is not None
    assert subscription.retained_items == 511
    hub.publish(_candidate(worker_event_index=512))
    assert subscription.retained_items == 512
    hub.publish(_candidate(worker_event_index=513))

    assert subscription.retained_items == 512
    overflow = subscription.overflow_error()
    assert overflow is not None
    _assert_delivery_overflow(overflow)


def test_slow_subscription_overflow_preserves_prefix_and_fast_watcher() -> None:
    """单个慢 watcher overflow 后保留连续前缀且不影响快 watcher。"""

    hub = _hub(mailbox_max_items=3)
    slow = _attach(hub, "session-1")
    fast = _attach(hub, "session-1")
    fast_events: list[HostTransientDelta] = []

    for worker_event_index in range(1, 5):
        hub.publish(_candidate(worker_event_index=worker_event_index))
        fast_event = fast.pop_next_nowait()
        assert fast_event is not None
        fast_events.append(fast_event)
        fast.release_in_flight()

    slow_prefix: list[HostTransientDelta] = []
    for _index in range(3):
        slow_event = slow.pop_next_nowait()
        assert slow_event is not None
        slow_prefix.append(slow_event)
        slow.release_in_flight()
    overflow = slow.overflow_error()
    assert [event.runtime_sequence for event in slow_prefix] == [1, 2, 3]
    assert overflow is not None
    _assert_delivery_overflow(overflow)
    assert len(fast_events) == 4
    assert hub.subscription_count("session-1") == 1
    assert hub.reservation_count("session-1") == 2

    hub.publish(_candidate(worker_event_index=5))
    fast_event = fast.pop_next_nowait()
    assert fast_event is not None
    assert fast_event.worker_event_index == 5
    assert slow.pop_next_nowait() is None
    slow.close()
    assert hub.reservation_count("session-1") == 1


def test_session_reservation_cap_rejects_before_subscription_and_readmits() -> None:
    """cap+1 拒绝不分配 subscription，detach 后 readmit 且 Session 隔离。"""

    hub = _hub(max_subscriptions_per_session=2)
    first_reservation = hub.reserve("session-1")
    second_reservation = hub.reserve("session-1")
    assert hub.reservation_count("session-1") == 2
    assert hub.subscription_count("session-1") == 0

    with pytest.raises(HostApiError) as exc_info:
        hub.reserve("session-1")
    error = exc_info.value
    assert error.code is HostApiErrorCode.RESOURCE_EXHAUSTED
    assert error.retryable is True
    assert error.detail == HostSessionEventAdmissionDetail(
        reason=(
            HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED
        ),
    )
    assert hub.reservation_count("session-1") == 2
    assert hub.subscription_count("session-1") == 0

    other_session = hub.reserve("session-2")
    assert hub.reservation_count("session-2") == 1
    first = hub.attach(first_reservation)
    second = hub.attach(second_reservation)
    first.close()
    replacement = hub.reserve("session-1")
    replacement_subscription = hub.attach(replacement)
    assert hub.subscription_count("session-1") == 2
    assert second.is_closed is False

    replacement_subscription.close()
    second.close()
    other_session.release()
    assert hub.reservation_count("session-1") == 0
    assert hub.reservation_count("session-2") == 0


def test_owner_exposes_no_batch_pop_or_byte_accounting_shape() -> None:
    """subscription owner 只提供单项 transfer，且没有 byte 容量维度。"""

    source = inspect.getsource(HostTransientDeltaSubscription)
    assert not hasattr(HostTransientDeltaSubscription, "drain_nowait")
    assert "list[HostTransientDelta]" not in source
    assert "tuple[HostTransientDelta" not in source
    assert "max_bytes" not in source
    assert "size_bytes" not in source


def test_delivery_observability_is_low_cardinality(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """delivery owner 日志不得记录 identity、payload、item count 或容量维度。"""

    caplog.set_level(logging.INFO, logger="dayu.host.transient_delta")
    hub = _hub(mailbox_max_items=1, max_subscriptions_per_session=1)
    subscription = _attach(hub, "session-sensitive")
    hub.publish(
        _candidate(
            worker_event_index=1,
            session_id="session-sensitive",
            run_id="run-sensitive",
        )
    )
    hub.publish(
        _candidate(
            worker_event_index=2,
            session_id="session-sensitive",
            run_id="run-sensitive",
        )
    )
    with pytest.raises(HostApiError):
        hub.reserve("session-sensitive")
    subscription.close()

    messages = [record.getMessage() for record in caplog.records]
    assert messages
    assert all("event=" in message for message in messages)
    assert all("outcome=" in message for message in messages)
    assert all("reason=" in message for message in messages)
    forbidden_fragments = (
        "session-sensitive",
        "run-sensitive",
        "delta-",
        "worker_event_index",
        "item_count",
        "capacity",
        "max_items",
    )
    assert all(
        fragment not in message
        for message in messages
        for fragment in forbidden_fragments
    )


def _hub(
    *,
    mailbox_max_items: int = 512,
    max_subscriptions_per_session: int = 4,
) -> HostTransientDeltaHub:
    """构造显式 typed policy 的 transient hub。

    :param mailbox_max_items: 单订阅 retained item 上限。
    :param max_subscriptions_per_session: 单 Session reservation 上限。
    :returns: 测试 hub。
    :raises ValueError: policy 字段非法时抛出。
    """

    return HostTransientDeltaHub(
        policy=HostSessionEventDeliveryPolicy(
            transient_mailbox_max_items=mailbox_max_items,
            max_subscriptions_per_session=max_subscriptions_per_session,
        ),
    )


def _attach(
    hub: HostTransientDeltaHub,
    session_id: str,
) -> HostTransientDeltaSubscription:
    """在线性化 reservation 后 attach 测试 subscription。

    :param hub: transient hub。
    :param session_id: 目标 Session 标识。
    :returns: attached subscription。
    :raises HostApiError: admission cap 满时抛出。
    """

    return hub.attach(hub.reserve(session_id))


def _assert_delivery_overflow(error: HostApiError) -> None:
    """断言 delivery overflow 的精确 public identity。

    :param error: public Host API error。
    :returns: ``None``。
    :raises AssertionError: code、retryable 或 detail 漂移时抛出。
    """

    assert error.code is HostApiErrorCode.DELIVERY_INTERRUPTED
    assert error.retryable is False
    assert error.detail == HostSessionEventDeliveryDetail(
        reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW,
    )


def _candidate(
    *,
    worker_event_index: int,
    session_id: str = "session-1",
    run_id: str = "run-1",
) -> ValidatedTransientDeltaCandidate:
    """构造有效 reasoning 瞬态候选。

    :param worker_event_index: execution 内事件序号。
    :param session_id: 关联 Session 标识。
    :param run_id: 关联 Run 标识。
    :returns: 有效候选。
    :raises ValueError: 输入违反 candidate contract 时抛出。
    """

    return ValidatedTransientDeltaCandidate(
        session_id=session_id,
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

    public_data = (
        HostContentDelta(iteration_id="iteration-1", text_delta="delta")
        if data is None
        else data
    )
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
