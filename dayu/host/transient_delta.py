"""Host 当前进程内的瞬态增量发布与订阅基础设施。

本模块拥有 runtime identity、单调发布序列、Session 内 fanout、慢消费者
隔离、terminal fence 与订阅生命周期。它不写 EventLog，不提供 replay，
也不创建每 watcher 后台任务。
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol

from dayu.host.api import (
    HostApiError,
    HostApiErrorCode,
    HostTransientDelta,
    HostTransientDeltaData,
    HostTransientDeltaType,
    HostUnavailableDetail,
)

_TRANSIENT_WATCH_BUFFER_CAPACITY: Final[int] = 256
_LIVE_STREAM_COMPONENT: Final[str] = "session_live_stream"
_SLOW_CONSUMER_REASON_CODE: Final[str] = "slow_consumer"
_SLOW_CONSUMER_MESSAGE: Final[str] = "Session live stream consumer is too slow"
_DEDUPE_KEY_VERSION: Final[str] = "host-transient-delta-v1"


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


def _transient_dedupe_key(*, runtime_id: str, execution_id: str, worker_event_index: int) -> str:
    """生成消费者只能按等值比较的稳定瞬态去重键。

    :param runtime_id: 当前 Host runtime 标识。
    :param execution_id: 已验证 execution 标识。
    :param worker_event_index: execution 内事件序号。
    :returns: 带版本前缀的 SHA-256 opaque 去重键。
    :raises ValueError: 本函数不额外抛出业务异常。
    """

    encoded = "\x00".join((runtime_id, execution_id, str(worker_event_index))).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{_DEDUPE_KEY_VERSION}:{digest}"


def _slow_consumer_error() -> HostApiError:
    """构造瞬态订阅慢消费者 public typed 错误。

    :returns: 独立的 ``HostApiError`` 实例。
    :raises ValueError: 固定错误字段非法时抛出。
    """

    return HostApiError(
        code=HostApiErrorCode.UNAVAILABLE,
        message=_SLOW_CONSUMER_MESSAGE,
        retryable=True,
        detail=HostUnavailableDetail(
            component=_LIVE_STREAM_COMPONENT,
            reason_code=_SLOW_CONSUMER_REASON_CODE,
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
    :param observed_at: Engine event 的 UTC 观测时间。
    :param type: public 瞬态增量类型。
    :param data: 与类型严格对应、已验证的 public payload。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    worker_event_index: int
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


class HostTransientDeltaPublisher(Protocol):
    """Host ingest 使用的同步、non-blocking、non-throwing 发布端口。"""

    def publish(self, candidate: ValidatedTransientDeltaCandidate) -> None:
        """发布一个已验证瞬态候选。

        :param candidate: 已通过 durable identity 与 late-state 校验的候选。
        :returns: ``None``。
        :raises Exception: 端口 contract 要求实现隔离内部异常，不向调用方抛出。
        """

        ...


class HostTransientDeltaSubscription:
    """单个 Session watcher 的有界瞬态订阅与 terminal fence owner。

    :param hub: 拥有本订阅的 hub。
    :param session_id: 目标 Session 标识。
    """

    __slots__ = (
        "_closed",
        "_hub",
        "_overflowed",
        "_queue",
        "_ready",
        "_session_id",
        "_terminal_run_ids",
    )

    def __init__(self, *, hub: HostTransientDeltaHub, session_id: str) -> None:
        """构造有界订阅。

        :param hub: 拥有本订阅的 hub。
        :param session_id: 目标 Session 标识。
        :returns: 无返回值。
        :raises ValueError: Session 标识为空时抛出。
        """

        _require_non_empty(session_id, field_name="subscription.session_id")
        self._hub = hub
        self._session_id = session_id
        self._queue: asyncio.Queue[HostTransientDelta] = asyncio.Queue(maxsize=_TRANSIENT_WATCH_BUFFER_CAPACITY)
        self._ready = asyncio.Event()
        self._terminal_run_ids: set[str] = set()
        self._overflowed = False
        self._closed = False

    @property
    def session_id(self) -> str:
        """返回订阅目标 Session 标识。

        :returns: Session 标识。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._session_id

    @property
    def is_closed(self) -> bool:
        """返回订阅是否已正常关闭。

        :returns: 已关闭返回 ``True``。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._closed

    def drain_nowait(self) -> tuple[HostTransientDelta, ...]:
        """按 runtime sequence 排空当前已接受的连续前缀。

        :returns: 未被 watcher-local terminal fence 拒绝的不可变增量元组。
        :raises asyncio.QueueEmpty: 本方法内部处理空队列，不向调用方抛出。
        """

        drained: list[HostTransientDelta] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item.run_id not in self._terminal_run_ids:
                drained.append(item)
        self._refresh_readiness()
        return tuple(drained)

    async def wait_ready(self, timeout_seconds: float) -> bool:
        """等待队列非空、overflow 或 close 的 level-triggered 状态。

        :param timeout_seconds: 最大等待秒数，必须为正数。
        :returns: owner state ready 时返回 ``True``，超时返回 ``False``。
        :raises TypeError: timeout 不是数字或是布尔值时抛出。
        :raises ValueError: timeout 不是正数时抛出。
        """

        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
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
            await asyncio.wait_for(self._ready.wait(), timeout=float(timeout_seconds))
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
        return _slow_consumer_error()

    def mark_run_terminal(self, run_id: str) -> None:
        """为 watcher 建立同 Run terminal fence。

        :param run_id: 已向该 watcher 交付 terminal 的 Run 标识。
        :returns: ``None``。
        :raises ValueError: Run 标识为空时抛出。
        """

        _require_non_empty(run_id, field_name="subscription.terminal_run_id")
        self._terminal_run_ids.add(run_id)

    def close(self) -> None:
        """幂等 detach 并清空本订阅。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if self._closed:
            return
        self._closed = True
        self._hub._detach(self)
        self._clear_queue()
        self._ready.set()

    def _offer(self, event: HostTransientDelta) -> None:
        """由 hub non-blocking offer 一个共享 public envelope。

        :param event: 待发布 envelope。
        :returns: ``None``。
        :raises asyncio.QueueFull: 本方法内部转为订阅 overflow，不向 hub 抛出。
        """

        if self._closed or self._overflowed or event.run_id in self._terminal_run_ids:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._overflowed = True
            self._hub._detach(self)
        self._ready.set()

    def _close_from_hub(self) -> None:
        """响应 hub close，正常结束并唤醒 watcher。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if self._closed:
            return
        self._closed = True
        self._clear_queue()
        self._ready.set()

    def _is_ready(self) -> bool:
        """返回 level-triggered owner state 是否 ready。

        :returns: queue 非空、overflow 或 close 时返回 ``True``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        return not self._queue.empty() or self._overflowed or self._closed

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

    def _clear_queue(self) -> None:
        """无等待清空 private queue。

        :returns: ``None``。
        :raises asyncio.QueueEmpty: 本方法内部处理空队列，不向调用方抛出。
        """

        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return


class HostTransientDeltaHub(HostTransientDeltaPublisher):
    """单个 ``open_host`` runtime 的瞬态 identity 与 fanout owner。"""

    __slots__ = ("_closed", "_runtime_id", "_runtime_sequence", "_subscriptions")

    def __init__(self) -> None:
        """创建具有独立 opaque runtime identity 的 hub。

        :returns: 无返回值。
        :raises RuntimeError: UUID 创建失败时透传运行期异常。
        """

        self._runtime_id = str(uuid.uuid4())
        self._runtime_sequence = 0
        self._subscriptions: dict[str, set[HostTransientDeltaSubscription]] = {}
        self._closed = False

    @property
    def runtime_id(self) -> str:
        """返回当前 Host runtime opaque identity。

        :returns: UUID 文本。
        :raises RuntimeError: 本属性不抛出异常。
        """

        return self._runtime_id

    def subscribe(self, session_id: str) -> HostTransientDeltaSubscription:
        """同步注册 Session 瞬态订阅。

        :param session_id: 目标 Session 标识。
        :returns: 已在 hub 注册的有界订阅。
        :raises RuntimeError: hub 已关闭时抛出。
        :raises ValueError: Session 标识为空时抛出。
        """

        if self._closed:
            raise RuntimeError("Host transient delta hub is closed")
        _require_non_empty(session_id, field_name="hub.session_id")
        subscription = HostTransientDeltaSubscription(
            hub=self,
            session_id=session_id,
        )
        self._subscriptions.setdefault(session_id, set()).add(subscription)
        return subscription

    def publish(self, candidate: ValidatedTransientDeltaCandidate) -> None:
        """分配一次 runtime identity 并 non-blocking fanout 到当前订阅快照。

        :param candidate: 已通过 Host durable 校验的瞬态候选。
        :returns: ``None``；hub 已关闭时直接返回；无 watcher 时仍推进全局序列。
        :raises Exception: 本实现隔离 queue overflow，正常使用不向调用方抛出。
        """

        if self._closed:
            return
        subscriptions = tuple(self._subscriptions.get(candidate.session_id, ()))
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
            subscription._offer(event)

    def subscription_count(self, session_id: str) -> int:
        """返回指定 Session 当前 attach 的订阅数量。

        :param session_id: 目标 Session 标识。
        :returns: 当前订阅数量。
        :raises ValueError: Session 标识为空时抛出。
        """

        _require_non_empty(session_id, field_name="hub.session_id")
        return len(self._subscriptions.get(session_id, ()))

    def close(self) -> None:
        """关闭 hub，清空所有 buffer 并正常唤醒全部 watcher。

        :returns: ``None``。
        :raises RuntimeError: 本方法不抛出异常。
        """

        if self._closed:
            return
        self._closed = True
        subscriptions = tuple(
            subscription
            for session_subscriptions in self._subscriptions.values()
            for subscription in session_subscriptions
        )
        self._subscriptions.clear()
        for subscription in subscriptions:
            subscription._close_from_hub()

    def _detach(self, subscription: HostTransientDeltaSubscription) -> None:
        """从 Session 索引幂等移除单个订阅。

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


__all__ = [
    "HostTransientDeltaHub",
    "HostTransientDeltaPublisher",
    "HostTransientDeltaSubscription",
    "ValidatedTransientDeltaCandidate",
]
