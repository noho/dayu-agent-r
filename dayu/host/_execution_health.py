"""Host execution health 与 new-work admission 排序真源。

本模块用 opener event loop 拥有的单一 gate 串行化 new-work admission 与
scheduler fatal transition。admission lease 覆盖 actor transaction、commit 后
wake 和 actor future 收口；调用方取消不会提前释放 lease。
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TypeVar

from dayu.host.api import (
    HostApiError,
    HostApiErrorCode,
    HostClosedError,
    HostUnavailableDetail,
)

T = TypeVar("T")

_STARTING_COMPONENT = "host"
_STARTING_REASON_CODE = "execution_starting"
_UNAVAILABLE_MESSAGE = "Host execution is unavailable"


class HostExecutionHealthState(StrEnum):
    """execution Host lifecycle health 状态。"""

    STARTING = "starting"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    CLOSING = "closing"
    CLOSED = "closed"


class HostExecutionAdmissionLease:
    """持有 health gate admission 排序权的单次 lease。

    :param gate: 创建并拥有本 lease 的 health gate。
    """

    __slots__ = ("_gate", "_released")

    def __init__(self, gate: "HostExecutionHealthGate") -> None:
        """初始化 admission lease。

        :param gate: 创建本 lease 的 health gate。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._gate = gate
        self._released = False

    def release(self) -> None:
        """幂等释放 admission 排序权。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._released:
            return
        self._released = True
        self._gate._release_admission()

    def release_when_done(self, future: asyncio.Future[T]) -> None:
        """把 lease 生命周期绑定到 actor future 的真实收口。

        :param future: 已提交的 actor operation future。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        future.add_done_callback(self._release_after_future)

    def _release_after_future(self, future: asyncio.Future[T]) -> None:
        """在 actor future 完成后释放 lease。

        :param future: 已完成的 actor operation future。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if not future.cancelled():
            # caller 已取消时仍需观察底层 operation 异常；这不会改变其他
            # awaiter 读取同一 future result/exception 的语义。
            future.exception()
        self.release()


class HostExecutionHealthGate:
    """execution health 与 new-work admission 的唯一 lifecycle owner。"""

    __slots__ = ("_admission_lock", "_state", "_unavailable_detail")

    def __init__(self) -> None:
        """创建 STARTING 状态的 health gate。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._admission_lock = asyncio.Lock()
        self._state = HostExecutionHealthState.STARTING
        self._unavailable_detail: HostUnavailableDetail | None = None

    @property
    def state(self) -> HostExecutionHealthState:
        """返回当前 lifecycle health 状态。

        :returns: 当前 health 状态。
        :raises Exception: 不主动抛出异常。
        """

        return self._state

    def mark_ready(self) -> None:
        """在全部 startup critical component 成功后进入 READY。

        :returns: ``None``。
        :raises HostApiError: startup 期间已经报告 fatal 时抛出。
        :raises RuntimeError: 当前状态不允许进入 READY 时抛出。
        """

        if self._state is HostExecutionHealthState.UNAVAILABLE:
            raise self._unavailable_error()
        if self._state is not HostExecutionHealthState.STARTING:
            raise RuntimeError("Host execution health can only become ready from starting")
        self._state = HostExecutionHealthState.READY

    async def acquire_admission(self) -> HostExecutionAdmissionLease:
        """取得 new-work admission lease 并原子校验 READY。

        :returns: 覆盖 actor transaction 与 after-commit wake 的 lease。
        :raises HostApiError: execution 尚未 READY 或已经 UNAVAILABLE 时抛出。
        :raises HostClosedError: execution 正在关闭或已经关闭时抛出。
        """

        await self._admission_lock.acquire()
        if self._state is HostExecutionHealthState.READY:
            return HostExecutionAdmissionLease(self)
        self._admission_lock.release()
        if self._state in (
            HostExecutionHealthState.CLOSING,
            HostExecutionHealthState.CLOSED,
        ):
            raise HostClosedError()
        raise self._unavailable_error()

    async def report_fatal(self, *, component: str, reason_code: str) -> bool:
        """在 admission 排序边界提交 scheduler fatal transition。

        首个 fatal detail 保持真源。若 admission 已先取得 lease，本方法等待其
        actor transaction 与 matching wake 收口后才进入 UNAVAILABLE。

        :param component: 发生 fatal 的稳定组件标识。
        :param reason_code: 不含原始异常文本的稳定原因码。
        :returns: 本次调用实际提交 UNAVAILABLE transition 时返回 ``True``。
        :raises ValueError: component 或 reason_code 为空时抛出。
        """

        _require_non_empty(component, field_name="component")
        _require_non_empty(reason_code, field_name="reason_code")
        async with self._admission_lock:
            if self._state in (
                HostExecutionHealthState.CLOSING,
                HostExecutionHealthState.CLOSED,
                HostExecutionHealthState.UNAVAILABLE,
            ):
                return False
            self._unavailable_detail = HostUnavailableDetail(
                component=component,
                reason_code=reason_code,
            )
            self._state = HostExecutionHealthState.UNAVAILABLE
            return True

    async def begin_closing(self) -> None:
        """拒绝新调用并等待已取得的 admission lease 收口。

        状态在等待 active lease 前先进入 CLOSING，因此后续 admission 即使排队
        取得 lock，也只能得到 ``HostClosedError``。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._state is HostExecutionHealthState.CLOSED:
            return
        self._state = HostExecutionHealthState.CLOSING
        async with self._admission_lock:
            return

    def mark_closed(self) -> None:
        """在 execution owner cleanup 全部尝试后提交 CLOSED。

        :returns: ``None``。
        :raises RuntimeError: 未先进入 CLOSING 时抛出。
        """

        if self._state is HostExecutionHealthState.CLOSED:
            return
        if self._state is not HostExecutionHealthState.CLOSING:
            raise RuntimeError("Host execution health must be closing before closed")
        self._state = HostExecutionHealthState.CLOSED

    def raise_if_public_closed(self) -> None:
        """拒绝 CLOSING/CLOSED 状态的 public 调用。

        UNAVAILABLE 不阻断 read/cancel；new-work 必须调用
        ``acquire_admission()``。

        :returns: ``None``。
        :raises HostClosedError: Host 正在关闭或已经关闭时抛出。
        """

        if self._state in (
            HostExecutionHealthState.CLOSING,
            HostExecutionHealthState.CLOSED,
        ):
            raise HostClosedError()

    def raise_if_scheduler_unavailable(
        self,
        *,
        component: str,
        reason_code: str,
        force: bool = False,
    ) -> None:
        """让 scheduler wake 在 unavailable/closing/closed 时 fail closed。

        STARTING 允许 startup recovery 投递既有 durable work；READY 允许正常
        admission wake；CLOSING 允许 close gate 前已经提交的 actor command 完成
        matching wake，scheduler 私有 close gate 提交后由 ``force`` 拒绝。

        :param component: 当前 scheduler wake 组件。
        :param reason_code: lifecycle 不可用原因码。
        :param force: scheduler 私有 close gate 已提交时强制抛出。
        :returns: ``None``。
        :raises HostApiError: scheduler 已不可接收 wake 时抛出。
        """

        if not force and self._state in (
            HostExecutionHealthState.STARTING,
            HostExecutionHealthState.READY,
            HostExecutionHealthState.CLOSING,
        ):
            return
        detail = self._unavailable_detail
        if detail is None:
            detail = HostUnavailableDetail(
                component=component,
                reason_code=reason_code,
            )
        raise HostApiError(
            code=HostApiErrorCode.UNAVAILABLE,
            message=_UNAVAILABLE_MESSAGE,
            retryable=True,
            detail=detail,
        )

    def _release_admission(self) -> None:
        """释放当前 admission lock。

        :returns: ``None``。
        :raises RuntimeError: admission lock 未持有时由 asyncio 抛出。
        """

        self._admission_lock.release()

    def _unavailable_error(self) -> HostApiError:
        """构造不泄漏原始异常文本的 public unavailable error。

        :returns: retryable typed unavailable error。
        :raises Exception: 不主动抛出异常。
        """

        detail = self._unavailable_detail
        if detail is None:
            detail = HostUnavailableDetail(
                component=_STARTING_COMPONENT,
                reason_code=_STARTING_REASON_CODE,
            )
        return HostApiError(
            code=HostApiErrorCode.UNAVAILABLE,
            message=_UNAVAILABLE_MESSAGE,
            retryable=True,
            detail=detail,
        )


def _require_non_empty(value: str, *, field_name: str) -> None:
    """校验 health diagnostic 字段非空。

    :param value: 待校验文本。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises ValueError: value 为空或仅空白时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


__all__ = [
    "HostExecutionAdmissionLease",
    "HostExecutionHealthGate",
    "HostExecutionHealthState",
]
