"""Host 当前进程内的瞬态增量发布与订阅基础设施。

本模块拥有 runtime identity、单调发布序列、Session 内 fanout、per-Session
attach reservation、单订阅 mailbox 与唯一 in-flight retained item、overflow
和订阅生命周期。它不写 EventLog，不提供 replay，也不创建每 watcher 后台任务。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol

from dayu.host.api import (
    HostApiError,
    HostApiErrorCode,
    HostSessionEventAdmissionDetail,
    HostSessionEventAdmissionReason,
    HostSessionEventDeliveryDetail,
    HostSessionEventDeliveryPolicy,
    HostSessionEventDeliveryReason,
    HostTransientDelta,
    HostTransientDeltaData,
    HostTransientDeltaType,
)

_LOGGER = logging.getLogger(__name__)
_DEDUPE_KEY_VERSION: Final[str] = "host-transient-delta-v1"
_DELIVERY_INTERRUPTED_MESSAGE: Final[str] = (
    "Session event delivery was interrupted"
)
_SUBSCRIPTION_LIMIT_MESSAGE: Final[str] = (
    "Session event subscription limit was reached"
)


class _DeliveryLogEvent(StrEnum):
    """Session Event Delivery 低基数日志事件。"""

    ATTACH = "attach"
    DETACH = "detach"
    OVERFLOW = "overflow"


class _DeliveryLogOutcome(StrEnum):
    """Session Event Delivery 低基数日志结果。"""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RELEASED = "released"
    INTERRUPTED = "interrupted"


class _DeliveryLogReason(StrEnum):
    """Session Event Delivery 低基数日志原因。"""

    ATTACHED = "attached"
    ATTACH_ABORTED = "attach_aborted"
    CALLER_CLOSED = "caller_closed"
    HOST_CLOSED = "host_closed"
    SESSION_SUBSCRIPTION_LIMIT_REACHED = "session_subscription_limit_reached"
    TRANSIENT_MAILBOX_OVERFLOW = "transient_mailbox_overflow"


def _log_delivery(
    *,
    event: _DeliveryLogEvent,
    outcome: _DeliveryLogOutcome,
    reason: _DeliveryLogReason,
) -> None:
    """记录不含 identity、payload、item count 或容量维度的 delivery 事实。

    :param event: 封闭日志事件。
    :param outcome: 封闭日志结果。
    :param reason: 封闭日志原因。
    :returns: ``None``。
    :raises Exception: logging backend 异常由标准库自行隔离。
    """

    _LOGGER.info(
        "host.session_event_delivery event=%s outcome=%s reason=%s",
        event.value,
        outcome.value,
        reason.value,
    )


def _require_non_empty(value: str, *, field_name: str) -> None:
    """校验内部 identity 文本非空。

    :param value: 待校验文本。
    :param field_name: 错误消息使用的字段名。
    :returns: ``None``。
    :raises TypeError: 值不是字符串时抛出。
    :raises ValueError: 值为空或仅含空白时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验内部序号是正整数。

    :param value: 待校验序号。
    :param field_name: 错误消息使用的字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值不是正数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验内部 cursor 是非负整数。

    :param value: 待校验 cursor。
    :param field_name: 错误消息使用的字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值为负数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_utc_datetime(value: datetime, *, field_name: str) -> None:
    """校验内部时间是 UTC aware datetime。

    :param value: 待校验时间。
    :param field_name: 错误消息使用的字段名。
    :returns: ``None``。
    :raises TypeError: 值不是 ``datetime`` 时抛出。
    :raises ValueError: 值不是 UTC aware datetime 时抛出。
    """

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC-aware")


def _transient_dedupe_key(
    *,
    runtime_id: str,
    execution_id: str,
    worker_event_index: int,
) -> str:
    """生成消费者只能按等值比较的稳定瞬态去重键。

    :param runtime_id: 当前 Host runtime 标识。
    :param execution_id: 已验证 execution 标识。
    :param worker_event_index: execution 内事件序号。
    :returns: 带版本前缀的 SHA-256 opaque 去重键。
    :raises ValueError: 本函数不额外抛出业务异常。
    """

    encoded = "\x00".join(
        (runtime_id, execution_id, str(worker_event_index))
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{_DEDUPE_KEY_VERSION}:{digest}"


def _delivery_interrupted_error() -> HostApiError:
    """构造 transient mailbox overflow public typed 错误。

    :returns: 独立的 non-retryable ``HostApiError`` 实例。
    :raises ValueError: 固定错误字段非法时抛出。
    """

    return HostApiError(
        code=HostApiErrorCode.DELIVERY_INTERRUPTED,
        message=_DELIVERY_INTERRUPTED_MESSAGE,
        retryable=False,
        detail=HostSessionEventDeliveryDetail(
            reason=(
                HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW
            ),
        ),
    )


def _subscription_limit_error() -> HostApiError:
    """构造 Session subscription admission cap public typed 错误。

    :returns: 独立的 retryable ``HostApiError`` 实例。
    :raises ValueError: 固定错误字段非法时抛出。
    """

    return HostApiError(
        code=HostApiErrorCode.RESOURCE_EXHAUSTED,
        message=_SUBSCRIPTION_LIMIT_MESSAGE,
        retryable=True,
        detail=HostSessionEventAdmissionDetail(
            reason=(
                HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class ValidatedTransientDeltaCandidate:
    """已通过 Host durable identity 与 late-state 校验的瞬态候选。

    :param session_id: 已验证 Session 标识。
    :param run_id: 已验证 Run 标识。
    :param attempt_id: 已验证 Attempt 标识。
    :param execution_id: 已验证 execution 标识。
    :param worker_event_index: execution 内由 dispatch 分配的正整数序号。
    :param durable_causal_fence_event_sequence: 同一 validation transaction 中
        current Attempt 的 started event sequence。
    :param observed_at: Engine event 的 UTC 观测时间。
    :param type: public 瞬态增量类型。
    :param data: 与类型严格对应、已验证的 public payload。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    worker_event_index: int
    durable_causal_fence_event_sequence: int
    observed_at: datetime
    type: HostTransientDeltaType
    data: HostTransientDeltaData

    def __post_init__(self) -> None:
        """校验已验证瞬态候选的内部 contract。

        :returns: ``None``。
        :raises TypeError: enum、payload、序号或时间类型非法时抛出。
        :raises ValueError: identity 为空、序号非正数、时间非 UTC 或
            discriminator/data 不匹配时抛出。
        """

        _require_non_empty(self.session_id, field_name="candidate.session_id")
        _require_non_empty(self.run_id, field_name="candidate.run_id")
        _require_non_empty(self.attempt_id, field_name="candidate.attempt_id")
        _require_non_empty(self.execution_id, field_name="candidate.execution_id")
        _require_positive_int(
            self.worker_event_index,
            field_name="candidate.worker_event_index",
        )
        _require_positive_int(
            self.durable_causal_fence_event_sequence,
            field_name="candidate.durable_causal_fence_event_sequence",
        )
        _require_utc_datetime(self.observed_at, field_name="candidate.observed_at")
        if not isinstance(self.type, HostTransientDeltaType):
            raise TypeError("candidate.type must be HostTransientDeltaType")
        # 复用 public envelope 的唯一 discriminator/data 校验真源。
        HostTransientDelta(
            runtime_id="candidate-validation",
            runtime_sequence=1,
            session_id=self.session_id,
            run_id=self.run_id,
            attempt_id=self.attempt_id,
            execution_id=self.execution_id,
            worker_event_index=self.worker_event_index,
            observed_at=self.observed_at,
            type=self.type,
            data=self.data,
            dedupe_key="candidate-validation",
        )


@dataclass(frozen=True, slots=True)
class HostTransientDeltaMailboxEntry:
    """单个 subscription 独立持有的瞬态 mailbox retained item。

    :param event: 多订阅共享的 immutable public 瞬态 envelope。
    :param durable_causal_fence_event_sequence: candidate 原样携带的 durable
        Attempt start fence。
    """

    event: HostTransientDelta
    durable_causal_fence_event_sequence: int

    def __post_init__(self) -> None:
        """校验 mailbox entry 内部 contract。

        :returns: ``None``。
        :raises TypeError: event 或 fence 类型非法时抛出。
        :raises ValueError: fence 不是正数时抛出。
        """

        if not isinstance(self.event, HostTransientDelta):
            raise TypeError("mailbox_entry.event must be HostTransientDelta")
        _require_positive_int(
            self.durable_causal_fence_event_sequence,
            field_name=(
                "mailbox_entry.durable_causal_fence_event_sequence"
            ),
        )


class HostTransientDeltaPublisher(Protocol):
    """Host ingest 使用的同步、non-blocking、non-throwing 发布端口。"""

    def publish(self, candidate: ValidatedTransientDeltaCandidate) -> None:
        """发布一个已验证瞬态候选。

        :param candidate: 已通过 durable identity 与 late-state 校验的候选。
        :returns: ``None``。
        :raises Exception: 端口 contract 要求实现隔离内部异常，不向调用方抛出。
        """

        ...


class HostTransientDeltaReservation:
    """一个 Session attach slot 的幂等 reservation token。

    token 只表达 resource ownership，不创建 mailbox、cursor、iterator 或 task。
    """

    __slots__ = ("_hub", "_released", "_session_id")

    def __init__(self, *, hub: HostTransientDeltaHub, session_id: str) -> None:
        """初始化已经由 hub 计入 admission 的 token。

        :param hub: reservation owner。
        :param session_id: 目标 Session 标识。
        :returns: 无返回值。
        :raises ValueError: Session 标识为空时抛出。
        """

        _require_non_empty(session_id, field_name="reservation.session_id")
        self._hub = hub
        self._session_id = session_id
        self._released = False

    @property
    def session_id(self) -> str:
        """返回 reservation 目标 Session 标识。

        :returns: Session 标识。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._session_id

    @property
    def is_released(self) -> bool:
        """返回 token 是否已经释放。

        :returns: 已释放返回 ``True``。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._released

    def release(
        self,
        *,
        reason: _DeliveryLogReason = _DeliveryLogReason.ATTACH_ABORTED,
    ) -> None:
        """幂等释放 reservation。

        :param reason: 低基数 release 原因。
        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if self._released:
            return
        self._released = True
        self._hub._release_reservation(self)
        _log_delivery(
            event=_DeliveryLogEvent.DETACH,
            outcome=_DeliveryLogOutcome.RELEASED,
            reason=reason,
        )


class HostTransientDeltaSubscription:
    """单个 Session watcher 的 item-bound mailbox 与 durable readiness owner。

    :param hub: 拥有本订阅的 hub。
    :param reservation: 已线性化且尚未释放的 reservation。
    """

    __slots__ = (
        "_closed",
        "_committed_terminal_event_sequence_high_watermark",
        "_durable_cursor",
        "_hub",
        "_in_flight",
        "_mailbox",
        "_overflowed",
        "_ready",
        "_reservation",
    )

    def __init__(
        self,
        *,
        hub: HostTransientDeltaHub,
        reservation: HostTransientDeltaReservation,
        durable_cursor: int,
        committed_terminal_event_sequence_high_watermark: int,
    ) -> None:
        """构造尚未注册到 fanout 的订阅资源。

        :param hub: 拥有本订阅的 hub。
        :param reservation: 已线性化 reservation。
        :param durable_cursor: attach transaction 已读取的 durable cursor。
        :param committed_terminal_event_sequence_high_watermark: attach 临界段
            观察到的 opener-local terminal watermark baseline。
        :returns: 无返回值。
        :raises ValueError: reservation Session 标识非法时抛出。
        """

        _require_non_empty(
            reservation.session_id,
            field_name="subscription.session_id",
        )
        _require_non_negative_int(
            durable_cursor,
            field_name="subscription.durable_cursor",
        )
        _require_non_negative_int(
            committed_terminal_event_sequence_high_watermark,
            field_name=(
                "subscription.committed_terminal_event_sequence_high_watermark"
            ),
        )
        self._hub = hub
        self._reservation = reservation
        self._mailbox: deque[HostTransientDeltaMailboxEntry] = deque()
        self._in_flight: HostTransientDeltaMailboxEntry | None = None
        self._durable_cursor = durable_cursor
        self._committed_terminal_event_sequence_high_watermark = (
            committed_terminal_event_sequence_high_watermark
        )
        self._ready = asyncio.Event()
        self._overflowed = False
        self._closed = False
        self._refresh_readiness()

    @property
    def session_id(self) -> str:
        """返回订阅目标 Session 标识。

        :returns: Session 标识。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._reservation.session_id

    @property
    def is_closed(self) -> bool:
        """返回订阅是否已正常关闭。

        :returns: 已关闭返回 ``True``。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._closed

    @property
    def retained_items(self) -> int:
        """返回 mailbox 与唯一 in-flight 的当前 retained item 数。

        :returns: 当前 retained item 数。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return len(self._mailbox) + (1 if self._in_flight is not None else 0)

    def peek_next_nowait(self) -> HostTransientDeltaMailboxEntry | None:
        """读取 mailbox head，但不改变 retained ownership。

        :returns: 当前 mailbox head；mailbox 为空时返回 ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if not self._mailbox:
            return None
        return self._mailbox[0]

    def pop_next_nowait(self) -> HostTransientDeltaMailboxEntry | None:
        """把下一项从 mailbox 转移为唯一 in-flight。

        entry 的 transfer 不降低 retained item 计数。caller 必须在下一次
        ``anext`` resume 或 cleanup 时调用 ``release_in_flight``。

        :returns: 转移后的 entry；mailbox 为空时返回 ``None``。
        :raises RuntimeError: 上一个 in-flight 尚未释放时抛出。
        """

        if self._in_flight is not None:
            raise RuntimeError("subscription in-flight item must be released before pop")
        if self._mailbox:
            entry = self._mailbox.popleft()
            self._in_flight = entry
            self._refresh_readiness()
            return entry
        self._refresh_readiness()
        return None

    def release_in_flight(self) -> None:
        """释放上一轮 yield 后仍由 Host 持有的唯一 in-flight 引用。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        self._in_flight = None
        self._refresh_readiness()

    async def wait_ready(self, timeout_seconds: float) -> bool:
        """等待 mailbox 非空、overflow 或 close 的 level-triggered 状态。

        :param timeout_seconds: 最大等待秒数，必须为正数。
        :returns: owner state ready 时返回 ``True``，超时返回 ``False``。
        :raises TypeError: timeout 不是数字或是布尔值时抛出。
        :raises ValueError: timeout 不是正数时抛出。
        """

        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds,
            int | float,
        ):
            raise TypeError("timeout_seconds must be float")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self._is_ready():
            return True
        self._ready.clear()
        if self._is_ready():
            self._ready.set()
            return True
        try:
            await asyncio.wait_for(
                self._ready.wait(),
                timeout=float(timeout_seconds),
            )
        except TimeoutError:
            return self._is_ready()
        return True

    def overflow_error(self) -> HostApiError | None:
        """返回当前订阅的 typed overflow 错误。

        :returns: overflow 时返回新错误实例，否则返回 ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if not self._overflowed:
            return None
        return _delivery_interrupted_error()

    @property
    def needs_durable_reconciliation(self) -> bool:
        """返回 opener-local terminal watermark 是否领先 durable cursor。

        :returns: 本地 watermark 领先时返回 ``True``。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return (
            self._committed_terminal_event_sequence_high_watermark
            > self._durable_cursor
        )

    def advance_durable_cursor(self, event_sequence: int) -> None:
        """按实际处理进度单调推进 subscription durable cursor。

        :param event_sequence: 已处理的 EventLog 全局序号。
        :returns: ``None``。
        :raises TypeError: sequence 不是严格整数时抛出。
        :raises ValueError: sequence 为负数或倒退时抛出。
        """

        _require_non_negative_int(
            event_sequence,
            field_name="subscription.durable_cursor",
        )
        if event_sequence < self._durable_cursor:
            raise ValueError("subscription durable cursor must not move backward")
        self._durable_cursor = event_sequence
        self._refresh_readiness()

    def _advance_committed_terminal_event_sequence_high_watermark(
        self,
        event_sequence: int,
    ) -> None:
        """响应 hub local terminal hint 并 level-trigger 当前 subscription。

        :param event_sequence: 新提交 terminal EventLog 全局序号。
        :returns: ``None``。
        :raises TypeError: sequence 不是严格整数时抛出。
        :raises ValueError: sequence 不是正数时抛出。
        """

        _require_positive_int(
            event_sequence,
            field_name=(
                "subscription.committed_terminal_event_sequence_high_watermark"
            ),
        )
        if (
            event_sequence
            <= self._committed_terminal_event_sequence_high_watermark
        ):
            return
        self._committed_terminal_event_sequence_high_watermark = event_sequence
        self._ready.set()

    def close(self) -> None:
        """幂等 detach、清空 retained state 并释放 reservation。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if self._closed:
            return
        self._closed = True
        self._hub._detach_from_fanout(self)
        self._clear_retained_state()
        self._reservation.release(reason=_DeliveryLogReason.CALLER_CLOSED)
        self._ready.set()

    def _offer(self, entry: HostTransientDeltaMailboxEntry) -> None:
        """由 hub non-blocking offer 一个 subscription-owned entry。

        :param entry: 待发布 retained item。
        :returns: ``None``。
        :raises RuntimeError: 本方法将容量拒绝转为 subscription overflow。
        """

        if self._closed or self._overflowed:
            return
        prospective_retained_items = self.retained_items + 1
        if (
            prospective_retained_items
            > self._hub.policy.transient_mailbox_max_items
        ):
            self._overflowed = True
            self._hub._detach_from_fanout(self)
            _log_delivery(
                event=_DeliveryLogEvent.OVERFLOW,
                outcome=_DeliveryLogOutcome.INTERRUPTED,
                reason=_DeliveryLogReason.TRANSIENT_MAILBOX_OVERFLOW,
            )
            self._ready.set()
            return
        self._mailbox.append(entry)
        self._ready.set()

    def _close_from_hub(self) -> None:
        """响应 hub close，正常结束并释放全部 retained owner resource。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if self._closed:
            return
        self._closed = True
        self._clear_retained_state()
        self._reservation.release(reason=_DeliveryLogReason.HOST_CLOSED)
        self._ready.set()

    def _is_ready(self) -> bool:
        """返回 level-triggered owner state 是否 ready。

        :returns: mailbox 非空、overflow 或 close 时返回 ``True``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        return (
            bool(self._mailbox)
            or self._overflowed
            or self._closed
            or self.needs_durable_reconciliation
        )

    def _refresh_readiness(self) -> None:
        """按当前 owner state 刷新 readiness，避免丢失唤醒。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if self._is_ready():
            self._ready.set()
            return
        self._ready.clear()
        if self._is_ready():
            self._ready.set()

    def _clear_retained_state(self) -> None:
        """清空 mailbox 与唯一 in-flight retained state。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        self._mailbox.clear()
        self._in_flight = None


class HostTransientDeltaHub(HostTransientDeltaPublisher):
    """单个 ``open_host`` runtime 的瞬态 identity 与 resource owner。"""

    __slots__ = (
        "_closed",
        "_committed_terminal_event_sequence_high_watermarks",
        "_policy",
        "_reservations",
        "_runtime_id",
        "_runtime_sequence",
        "_subscriptions",
    )

    def __init__(self, *, policy: HostSessionEventDeliveryPolicy) -> None:
        """创建具有独立 opaque runtime identity 的 hub。

        :param policy: 当前 opener 所有 subscription 共用的 typed policy。
        :returns: 无返回值。
        :raises TypeError: policy 类型非法时抛出。
        :raises RuntimeError: UUID 创建失败时透传运行期异常。
        """

        if not isinstance(policy, HostSessionEventDeliveryPolicy):
            raise TypeError("policy must be HostSessionEventDeliveryPolicy")
        self._policy = policy
        self._runtime_id = str(uuid.uuid4())
        self._runtime_sequence = 0
        self._committed_terminal_event_sequence_high_watermarks: dict[
            str,
            int,
        ] = {}
        self._subscriptions: dict[
            str,
            set[HostTransientDeltaSubscription],
        ] = {}
        self._reservations: dict[
            str,
            set[HostTransientDeltaReservation],
        ] = {}
        self._closed = False

    @property
    def policy(self) -> HostSessionEventDeliveryPolicy:
        """返回当前 opener 的 immutable delivery policy。

        :returns: delivery policy。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._policy

    @property
    def runtime_id(self) -> str:
        """返回当前 Host runtime opaque identity。

        :returns: UUID 文本。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._runtime_id

    def reserve(self, session_id: str) -> HostTransientDeltaReservation:
        """在分配 watcher resource 前线性化 Session attach reservation。

        :param session_id: 目标 Session 标识。
        :returns: 已计入 per-Session admission 的 reservation token。
        :raises RuntimeError: hub 已关闭时抛出。
        :raises HostApiError: 目标 Session reservation 已达上限时抛出。
        :raises ValueError: Session 标识为空时抛出。
        """

        if self._closed:
            raise RuntimeError("Host transient delta hub is closed")
        _require_non_empty(session_id, field_name="hub.session_id")
        session_reservations = self._reservations.get(session_id)
        if (
            session_reservations is not None
            and len(session_reservations)
            >= self._policy.max_subscriptions_per_session
        ):
            _log_delivery(
                event=_DeliveryLogEvent.ATTACH,
                outcome=_DeliveryLogOutcome.REJECTED,
                reason=(
                    _DeliveryLogReason.SESSION_SUBSCRIPTION_LIMIT_REACHED
                ),
            )
            raise _subscription_limit_error()
        reservation = HostTransientDeltaReservation(
            hub=self,
            session_id=session_id,
        )
        self._reservations.setdefault(session_id, set()).add(reservation)
        return reservation

    def attach(
        self,
        reservation: HostTransientDeltaReservation,
        *,
        durable_cursor: int,
    ) -> HostTransientDeltaSubscription:
        """把已完成 cursor transaction 的 reservation 转成 attached subscription。

        本方法在 owner loop 单一无 ``await`` 临界段内分配 mailbox、注册 fanout
        并返回 subscription；失败时 reservation 仍由 factory owner 释放。

        :param reservation: 当前 hub 已计入 admission 的 reservation。
        :param durable_cursor: attach transaction 已读取的 durable cursor。
        :returns: 已注册的 subscription。
        :raises RuntimeError: hub 已关闭、token 已释放或不属于当前 hub 时抛出。
        """

        if self._closed:
            raise RuntimeError("Host transient delta hub is closed")
        if reservation._hub is not self:
            raise RuntimeError("reservation belongs to another hub")
        if reservation.is_released:
            raise RuntimeError("reservation is already released")
        session_reservations = self._reservations.get(reservation.session_id)
        if (
            session_reservations is None
            or reservation not in session_reservations
        ):
            raise RuntimeError("reservation is not active")
        subscription = HostTransientDeltaSubscription(
            hub=self,
            reservation=reservation,
            durable_cursor=durable_cursor,
            committed_terminal_event_sequence_high_watermark=(
                self._committed_terminal_event_sequence_high_watermarks.get(
                    reservation.session_id,
                    0,
                )
            ),
        )
        self._subscriptions.setdefault(
            reservation.session_id,
            set(),
        ).add(subscription)
        _log_delivery(
            event=_DeliveryLogEvent.ATTACH,
            outcome=_DeliveryLogOutcome.ACCEPTED,
            reason=_DeliveryLogReason.ATTACHED,
        )
        return subscription

    def publish(self, candidate: ValidatedTransientDeltaCandidate) -> None:
        """分配一次 runtime identity 并 non-blocking fanout 到当前订阅快照。

        :param candidate: 已通过 Host durable 校验的瞬态候选。
        :returns: ``None``；hub 已关闭时直接返回；无 watcher 时仍推进全局序列。
        :raises Exception: 本实现隔离 subscription overflow，正常使用不抛出。
        """

        if self._closed:
            return
        subscriptions = tuple(
            self._subscriptions.get(candidate.session_id, ())
        )
        self._runtime_sequence += 1
        event = HostTransientDelta(
            runtime_id=self._runtime_id,
            runtime_sequence=self._runtime_sequence,
            session_id=candidate.session_id,
            run_id=candidate.run_id,
            attempt_id=candidate.attempt_id,
            execution_id=candidate.execution_id,
            worker_event_index=candidate.worker_event_index,
            observed_at=candidate.observed_at,
            type=candidate.type,
            data=candidate.data,
            dedupe_key=_transient_dedupe_key(
                runtime_id=self._runtime_id,
                execution_id=candidate.execution_id,
                worker_event_index=candidate.worker_event_index,
            ),
        )
        for subscription in subscriptions:
            subscription._offer(
                HostTransientDeltaMailboxEntry(
                    event=event,
                    durable_causal_fence_event_sequence=(
                        candidate.durable_causal_fence_event_sequence
                    ),
                )
            )

    def advance_committed_terminal_event_sequence_high_watermark(
        self,
        session_id: str,
        event_sequence: int,
    ) -> bool:
        """推进 opener-local delivery terminal watermark 并唤醒订阅。

        本 hook 只定义 Session Event Delivery owner state；Slice 2 不把任何
        terminal producer 接到这里。后续 coordinator 只能在 commit 后调用。

        :param session_id: terminal 所属 Session 标识。
        :param event_sequence: exact terminal EventLog 全局序号。
        :returns: watermark 实际前移时返回 ``True``，重复或倒序时返回
            ``False``。
        :raises ValueError: Session 标识为空或 sequence 不是正数时抛出。
        :raises TypeError: sequence 不是严格整数时抛出。
        """

        _require_non_empty(session_id, field_name="hub.session_id")
        _require_positive_int(
            event_sequence,
            field_name=(
                "hub.committed_terminal_event_sequence_high_watermark"
            ),
        )
        current = self._committed_terminal_event_sequence_high_watermarks.get(
            session_id,
            0,
        )
        if event_sequence <= current:
            return False
        self._committed_terminal_event_sequence_high_watermarks[session_id] = (
            event_sequence
        )
        for subscription in tuple(self._subscriptions.get(session_id, ())):
            subscription._advance_committed_terminal_event_sequence_high_watermark(
                event_sequence
            )
        return True

    def committed_terminal_event_sequence_high_watermark(
        self,
        session_id: str,
    ) -> int:
        """读取指定 Session 的 opener-local delivery watermark。

        :param session_id: 目标 Session 标识。
        :returns: 尚未见 terminal 时返回 ``0``，否则返回当前正整数 watermark。
        :raises ValueError: Session 标识为空时抛出。
        """

        _require_non_empty(session_id, field_name="hub.session_id")
        return self._committed_terminal_event_sequence_high_watermarks.get(
            session_id,
            0,
        )

    def subscription_count(self, session_id: str) -> int:
        """返回指定 Session 当前仍参与 fanout 的订阅数量。

        :param session_id: 目标 Session 标识。
        :returns: 当前 fanout subscription 数量。
        :raises ValueError: Session 标识为空时抛出。
        """

        _require_non_empty(session_id, field_name="hub.session_id")
        return len(self._subscriptions.get(session_id, ()))

    def reservation_count(self, session_id: str) -> int:
        """返回指定 Session 当前占用 admission 的 reservation 数量。

        :param session_id: 目标 Session 标识。
        :returns: RESERVED、ATTACHED 与 OVERFLOWED token 总数。
        :raises ValueError: Session 标识为空时抛出。
        """

        _require_non_empty(session_id, field_name="hub.session_id")
        return len(self._reservations.get(session_id, ()))

    def close(self) -> None:
        """关闭 hub，清空全部 retained state 并释放所有 reservation。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if self._closed:
            return
        self._closed = True
        self._committed_terminal_event_sequence_high_watermarks.clear()
        subscriptions = tuple(
            subscription
            for session_subscriptions in self._subscriptions.values()
            for subscription in session_subscriptions
        )
        self._subscriptions.clear()
        for subscription in subscriptions:
            subscription._close_from_hub()
        pending_reservations = tuple(
            reservation
            for session_reservations in self._reservations.values()
            for reservation in session_reservations
        )
        for reservation in pending_reservations:
            reservation.release(reason=_DeliveryLogReason.HOST_CLOSED)

    def _detach_from_fanout(
        self,
        subscription: HostTransientDeltaSubscription,
    ) -> None:
        """从 Session fanout 索引幂等移除单个订阅。

        :param subscription: 待移除订阅。
        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        session_subscriptions = self._subscriptions.get(subscription.session_id)
        if session_subscriptions is None:
            return
        session_subscriptions.discard(subscription)
        if not session_subscriptions:
            del self._subscriptions[subscription.session_id]

    def _release_reservation(
        self,
        reservation: HostTransientDeltaReservation,
    ) -> None:
        """从 Session admission 索引幂等移除 reservation。

        :param reservation: 待释放 token。
        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        session_reservations = self._reservations.get(reservation.session_id)
        if session_reservations is None:
            return
        session_reservations.discard(reservation)
        if not session_reservations:
            del self._reservations[reservation.session_id]


__all__ = [
    "HostTransientDeltaHub",
    "HostTransientDeltaMailboxEntry",
    "HostTransientDeltaPublisher",
    "HostTransientDeltaReservation",
    "HostTransientDeltaSubscription",
    "ValidatedTransientDeltaCandidate",
]
