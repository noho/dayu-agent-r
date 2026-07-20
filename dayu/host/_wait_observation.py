"""Host 同步 wait adapter 调用的有界观察运行器。

本模块只拥有 adapter invocation 的线程、发布令牌、并发上限与关闭预算。
观察线程不持有 durable store、transaction、command handle 或 scheduler 端口；
超时或关闭后，令牌先失效，迟到结果只能被丢弃。
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeAlias, TypeVar
from uuid import uuid4


T = TypeVar("T")


class WaitObservationTokenState(StrEnum):
    """单次 adapter observation token 的生命周期状态。"""

    ACTIVE = "active"
    INVALIDATED = "invalidated"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True)
class WaitObservationPublished(Generic[T]):
    """adapter 结果在令牌仍有效时成功发布。

    :param value: adapter 返回的 typed 结果。
    """

    value: T


@dataclass(frozen=True, slots=True)
class WaitObservationFailed:
    """adapter 在令牌仍有效时抛出普通异常。

    :param error: adapter 抛出的普通异常。
    """

    error: Exception


@dataclass(frozen=True, slots=True)
class WaitObservationTimedOut:
    """adapter 调用超过单次观察预算。"""


@dataclass(frozen=True, slots=True)
class WaitObservationCapacityExceeded:
    """live adapter invocation 已达到 policy 上限。"""


@dataclass(frozen=True, slots=True)
class WaitObservationClosed:
    """supervisor 已关闭，当前观察不再拥有发布权。"""


WaitObservationResult: TypeAlias = (
    WaitObservationPublished[T]
    | WaitObservationFailed
    | WaitObservationTimedOut
    | WaitObservationCapacityExceeded
    | WaitObservationClosed
)


@dataclass(frozen=True, slots=True)
class WaitObservationDiagnosticsSnapshot:
    """有界观察 registry 的只读诊断快照。

    :param live_count: 尚未从 registry 移除的 invocation 数。
    :param active_count: 仍拥有发布权的 invocation 数。
    :param invalidated_count: 已撤销发布权但线程尚未结束的 invocation 数。
    :param published_count: 成功发布的结果或普通异常数。
    :param dropped_count: 令牌失效后到达而被丢弃的结果或异常数。
    :param capacity_rejections: 因达到上限而未创建线程的调用数。
    :param closed: runner 是否已进入关闭 generation。
    """

    live_count: int
    active_count: int
    invalidated_count: int
    published_count: int
    dropped_count: int
    capacity_rejections: int
    closed: bool


class _ObservationTokenPort(Protocol):
    """异构 token registry 使用的非泛型最小端口。"""

    token_id: str
    generation: int
    state: WaitObservationTokenState
    thread: threading.Thread | None

    def invalidate(self) -> None:
        """撤销发布权并唤醒等待方。

        :returns: ``None``。
        """

        ...


@dataclass(slots=True)
class _ObservationToken(Generic[T]):
    """单次 observation 的发布令牌与单槽结果通道。"""

    token_id: str
    generation: int
    result_queue: queue.Queue[WaitObservationResult[T]]
    state: WaitObservationTokenState = WaitObservationTokenState.ACTIVE
    thread: threading.Thread | None = None

    def invalidate(self) -> None:
        """撤销 token 并用 closed signal 唤醒等待方。

        :returns: ``None``。
        """

        if self.state is not WaitObservationTokenState.ACTIVE:
            return
        self.state = WaitObservationTokenState.INVALIDATED
        try:
            self.result_queue.put_nowait(WaitObservationClosed())
        except queue.Full:
            # result 与 invalidation 在 registry lock 下线性化；槽已满表示
            # 结果先发布，调用方仍会在 lifecycle gate 处拒绝 durable publish。
            return


class WaitObservationRunner:
    """有界执行同步 adapter 调用并治理迟到发布。

    :param max_outstanding_adapter_calls: 同时存活的 adapter invocation 上限。
    :param thread_name_prefix: daemon observation thread 名称前缀。
    :param on_drained: 关闭后最后一个线程结束时的可选通知。
    """

    def __init__(
        self,
        *,
        max_outstanding_adapter_calls: int,
        thread_name_prefix: str,
        on_drained: Callable[[], None] | None = None,
    ) -> None:
        """初始化 observation registry。

        :param max_outstanding_adapter_calls: live invocation 正数上限。
        :param thread_name_prefix: 非空线程名前缀。
        :param on_drained: 关闭 generation 完全 drain 后通知；无则为 ``None``。
        :returns: ``None``。
        :raises ValueError: 上限非正或线程名前缀为空时抛出。
        """

        if not isinstance(max_outstanding_adapter_calls, int) or isinstance(
            max_outstanding_adapter_calls, bool
        ):
            raise TypeError("max_outstanding_adapter_calls must be int")
        if max_outstanding_adapter_calls <= 0:
            raise ValueError("max_outstanding_adapter_calls must be positive")
        if thread_name_prefix.strip() == "":
            raise ValueError("thread_name_prefix must be non-empty")
        self._max_outstanding_adapter_calls = max_outstanding_adapter_calls
        self._thread_name_prefix = thread_name_prefix
        self._on_drained = on_drained
        self._lock = threading.Lock()
        self._tokens: dict[str, _ObservationTokenPort] = {}
        self._generation = 0
        self._closed = False
        self._published_count = 0
        self._dropped_count = 0
        self._capacity_rejections = 0

    def observe(
        self,
        operation: Callable[[], T],
        *,
        timeout_seconds: float,
    ) -> WaitObservationResult[T]:
        """在 daemon thread 执行一次同步 adapter operation。

        :param operation: 只捕获 adapter 与 immutable wait snapshot 的调用。
        :param timeout_seconds: finite-positive 单次等待预算。
        :returns: published、failed、timeout、capacity 或 closed typed 结果。
        :raises ValueError: timeout 非 finite-positive 时抛出。
        """

        if not isinstance(timeout_seconds, (int, float)) or isinstance(
            timeout_seconds, bool
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        if not 0.0 < float(timeout_seconds) < float("inf"):
            raise ValueError("timeout_seconds must be a finite positive number")
        token = self._start_observation(operation)
        if isinstance(token, (WaitObservationClosed, WaitObservationCapacityExceeded)):
            return token
        try:
            return token.result_queue.get(timeout=float(timeout_seconds))
        except queue.Empty:
            if self._invalidate_token(token):
                return WaitObservationTimedOut()
            # provider publish 与 timeout invalidation 使用同一 registry lock。
            # 未能撤销 ACTIVE 表示 provider/close 已先线性化，结果 signal 必须
            # 已经进入单槽 queue，不能把已发布结果重分类为 timeout。
            try:
                return token.result_queue.get_nowait()
            except queue.Empty as exc:
                raise RuntimeError(
                    "finished wait observation has no published signal"
                ) from exc

    def begin_close(self) -> None:
        """进入关闭 generation 并撤销全部 live token 发布权。

        :returns: ``None``。
        """

        with self._lock:
            if not self._closed:
                self._closed = True
                self._generation += 1
            for token in self._tokens.values():
                token.invalidate()

    def drain_until(self, deadline_monotonic: float) -> bool:
        """使用一个 shared monotonic deadline best-effort join live threads。

        :param deadline_monotonic: 全部线程共享的绝对 monotonic deadline。
        :returns: registry 已无 live invocation 时返回 ``True``。
        :raises ValueError: deadline 不是 finite 数值时抛出。
        """

        if not isinstance(deadline_monotonic, (int, float)) or isinstance(
            deadline_monotonic, bool
        ):
            raise ValueError("deadline_monotonic must be finite")
        if not float("-inf") < float(deadline_monotonic) < float("inf"):
            raise ValueError("deadline_monotonic must be finite")
        with self._lock:
            threads = tuple(
                token.thread
                for token in self._tokens.values()
                if token.thread is not None
            )
        for thread in threads:
            remaining = max(0.0, float(deadline_monotonic) - time.monotonic())
            if remaining <= 0.0:
                break
            if thread is not threading.current_thread():
                thread.join(remaining)
        return self.diagnostics_snapshot().live_count == 0

    def diagnostics_snapshot(self) -> WaitObservationDiagnosticsSnapshot:
        """读取 registry 状态与发布统计。

        :returns: immutable diagnostics snapshot。
        """

        with self._lock:
            active_count = sum(
                token.state is WaitObservationTokenState.ACTIVE
                for token in self._tokens.values()
            )
            invalidated_count = sum(
                token.state is WaitObservationTokenState.INVALIDATED
                for token in self._tokens.values()
            )
            return WaitObservationDiagnosticsSnapshot(
                live_count=len(self._tokens),
                active_count=active_count,
                invalidated_count=invalidated_count,
                published_count=self._published_count,
                dropped_count=self._dropped_count,
                capacity_rejections=self._capacity_rejections,
                closed=self._closed,
            )

    def _start_observation(
        self, operation: Callable[[], T]
    ) -> _ObservationToken[T] | WaitObservationClosed | WaitObservationCapacityExceeded:
        """注册并启动一次 observation。

        :param operation: adapter operation。
        :returns: 已启动 token，或未启动原因。
        """

        with self._lock:
            if self._closed:
                return WaitObservationClosed()
            if len(self._tokens) >= self._max_outstanding_adapter_calls:
                self._capacity_rejections += 1
                return WaitObservationCapacityExceeded()
            token = _ObservationToken[T](
                token_id=f"wait-observation-{uuid4()}",
                generation=self._generation,
                result_queue=queue.Queue(maxsize=1),
            )
            thread = threading.Thread(
                target=_run_observation,
                args=(self, token, operation),
                name=f"{self._thread_name_prefix}-{token.token_id}",
                daemon=True,
            )
            token.thread = thread
            self._tokens[token.token_id] = token
            thread.start()
            return token

    def _invalidate_token(self, token: _ObservationTokenPort) -> bool:
        """在 registry lock 下撤销单个 token。

        :param token: 目标 token。
        :returns: 本调用成功把 ACTIVE token 置为 INVALIDATED 时返回 ``True``。
        """

        with self._lock:
            current = self._tokens.get(token.token_id)
            if (
                current is token
                and token.state is WaitObservationTokenState.ACTIVE
            ):
                token.invalidate()
                return True
            return False

    def _publish(
        self,
        token: _ObservationToken[T],
        result: WaitObservationPublished[T] | WaitObservationFailed,
    ) -> bool:
        """在线性化 gate 内发布 adapter 结果。

        :param token: observation token。
        :param result: typed value 或普通异常。
        :returns: 成功发布为 ``True``；迟到结果为 ``False``。
        """

        with self._lock:
            current = self._tokens.get(token.token_id)
            if (
                current is not token
                or token.state is not WaitObservationTokenState.ACTIVE
                or self._closed
                or token.generation != self._generation
            ):
                self._dropped_count += 1
                return False
            token.state = WaitObservationTokenState.FINISHED
            token.result_queue.put_nowait(result)
            self._published_count += 1
            return True

    def _finish(self, token: _ObservationTokenPort) -> None:
        """在线程 finally 中标记 FINISHED 并移除强引用。

        :param token: 已结束 invocation token。
        :returns: ``None``。
        """

        notify_drained = False
        with self._lock:
            current = self._tokens.get(token.token_id)
            if current is token:
                token.state = WaitObservationTokenState.FINISHED
                del self._tokens[token.token_id]
            notify_drained = self._closed and not self._tokens
        if notify_drained and self._on_drained is not None:
            self._on_drained()


def _run_observation(
    runner: WaitObservationRunner,
    token: _ObservationToken[T],
    operation: Callable[[], T],
) -> None:
    """执行 adapter operation 并尝试一次 gated publish。

    :param runner: 不含 durable authority 的 observation registry。
    :param token: 本次 invocation token。
    :param operation: adapter operation。
    :returns: ``None``。
    """

    try:
        try:
            result: WaitObservationPublished[T] | WaitObservationFailed = (
                WaitObservationPublished(operation())
            )
        except Exception as exc:
            result = WaitObservationFailed(exc)
        runner._publish(token, result)
    finally:
        runner._finish(token)


__all__ = [
    "WaitObservationCapacityExceeded",
    "WaitObservationClosed",
    "WaitObservationDiagnosticsSnapshot",
    "WaitObservationFailed",
    "WaitObservationPublished",
    "WaitObservationResult",
    "WaitObservationRunner",
    "WaitObservationTimedOut",
    "WaitObservationTokenState",
]
