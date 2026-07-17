"""Fins direct 事件流的唯一终态协议校验器。

本模块独占 direct stream 恰好包含一个且最后一个 ``RESULT`` 的判定，
并负责 raw async generator 的关闭生命周期。Service 与 CLI 只消费这里
产出的已验证 typed stream，不再重复推断终态协议。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from enum import Enum
from typing import Final, NoReturn

from dayu.fins.direct_events import (
    FinsDirectStreamProtocolError,
    FinsDirectStreamProtocolErrorKind,
    FinsEvent,
    FinsEventType,
    FinsOperationKind,
    FinsResultSummary,
)

_MISSING_RESULT_MESSAGE: Final[str] = "Fins direct stream ended without RESULT"
_DUPLICATE_RESULT_MESSAGE: Final[str] = (
    "Fins direct stream produced multiple RESULT events"
)
_EVENT_AFTER_RESULT_MESSAGE: Final[str] = (
    "Fins direct stream produced an event after RESULT"
)
_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE: Final[str] = (
    "Fins direct terminal result is not available before clean stream exhaustion"
)


class _ValidatedStreamState(str, Enum):
    """已验证 direct stream 的私有状态。"""

    OPEN = "open"
    RESULT_BUFFERED = "result_buffered"
    RESULT_YIELDED = "result_yielded"
    CLOSED = "closed"


class ValidatedFinsEventStream(AsyncIterator[FinsEvent]):
    """校验 Fins direct stream 终态协议并拥有 raw source 生命周期。

    Args:
        source: Fins runtime 创建的 raw 事件 async generator。
        operation_kind: 当前 direct 操作类型，用于 typed 协议错误来源。

    Raises:
        TypeError: operation_kind 类型非法时抛出。
    """

    def __init__(
        self,
        source: AsyncGenerator[FinsEvent, None],
        *,
        operation_kind: FinsOperationKind,
    ) -> None:
        """初始化唯一 direct stream validator。

        Args:
            source: Fins runtime 创建的 raw 事件 async generator。
            operation_kind: 当前 direct 操作类型。

        Returns:
            无。

        Raises:
            TypeError: operation_kind 类型非法时抛出。
        """

        if not isinstance(operation_kind, FinsOperationKind):
            raise TypeError("operation_kind must be FinsOperationKind")
        self._source = source
        self._operation_kind = operation_kind
        self._state = _ValidatedStreamState.OPEN
        self._buffered_result_event: FinsEvent | None = None
        self._terminal_result_value: FinsResultSummary | None = None
        self._clean_exhaustion = False
        self._source_close_attempted = False

    def __aiter__(self) -> ValidatedFinsEventStream:
        """返回当前已验证事件流。

        Args:
            无。

        Returns:
            当前已验证事件流实例。

        Raises:
            无。
        """

        return self

    async def __anext__(self) -> FinsEvent:
        """返回下一个已验证事件。

        首个 ``RESULT`` 会被缓存，只有 raw source clean exhaustion 后才会
        返回；其后的任意事件都会由本 owner 产生 typed 协议错误。

        Args:
            无。

        Returns:
            下一个 progress 事件或已证明唯一且最后的 result 事件。

        Raises:
            StopAsyncIteration: 已验证事件流耗尽时抛出。
            FinsDirectStreamProtocolError: 缺少、重复或 RESULT 后仍有事件时抛出。
            BaseException: raw source 的原始异常或取消以同一对象传播。
        """

        while True:
            if self._state is _ValidatedStreamState.CLOSED:
                raise StopAsyncIteration
            if self._state is _ValidatedStreamState.RESULT_YIELDED:
                self._state = _ValidatedStreamState.CLOSED
                raise StopAsyncIteration

            try:
                event = await self._source.__anext__()
            except StopAsyncIteration:
                return self._finish_clean_exhaustion()
            except BaseException as primary_error:
                await self._raise_primary_after_close(primary_error)

            if self._state is _ValidatedStreamState.OPEN:
                if event.event_type is FinsEventType.RESULT:
                    result = event.result
                    assert result is not None
                    self._buffered_result_event = event
                    self._terminal_result_value = result
                    self._state = _ValidatedStreamState.RESULT_BUFFERED
                    continue
                return event

            if event.event_type is FinsEventType.RESULT:
                protocol_error = FinsDirectStreamProtocolError(
                    FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT,
                    self._operation_kind,
                    _DUPLICATE_RESULT_MESSAGE,
                )
            else:
                protocol_error = FinsDirectStreamProtocolError(
                    FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT,
                    self._operation_kind,
                    _EVENT_AFTER_RESULT_MESSAGE,
                )
            await self._raise_primary_after_close(protocol_error)

    async def aclose(self) -> None:
        """中止消费并关闭 raw source，底层关闭最多尝试一次。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: 没有既存语义错误时，raw source 关闭失败以同一对象传播。
        """

        if self._state is _ValidatedStreamState.CLOSED:
            return
        self._state = _ValidatedStreamState.CLOSED
        if not self._clean_exhaustion:
            self._buffered_result_event = None
            self._terminal_result_value = None
        await self._close_source_once()

    @property
    def terminal_result(self) -> FinsResultSummary:
        """返回 clean exhaustion 已证明的同一终态结果实例。

        Args:
            无。

        Returns:
            已证明唯一且最后的 ``FinsResultSummary`` 实例。

        Raises:
            RuntimeError: stream 尚未 clean exhaustion 或已中止时抛出。
        """

        if not self._clean_exhaustion or self._terminal_result_value is None:
            raise RuntimeError(_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE)
        return self._terminal_result_value

    def _finish_clean_exhaustion(self) -> FinsEvent:
        """在 raw source clean exhaustion 时完成 terminal 判定。

        Args:
            无。

        Returns:
            已缓存且证明唯一、最后的 result 事件。

        Raises:
            FinsDirectStreamProtocolError: raw source 未产生 RESULT 时抛出。
        """

        if self._state is _ValidatedStreamState.OPEN:
            self._state = _ValidatedStreamState.CLOSED
            raise FinsDirectStreamProtocolError(
                FinsDirectStreamProtocolErrorKind.MISSING_RESULT,
                self._operation_kind,
                _MISSING_RESULT_MESSAGE,
            )
        buffered_event = self._buffered_result_event
        assert buffered_event is not None
        self._clean_exhaustion = True
        self._state = _ValidatedStreamState.RESULT_YIELDED
        return buffered_event

    async def _raise_primary_after_close(self, primary_error: BaseException) -> NoReturn:
        """关闭 raw source 后保持 primary semantic error 身份并重抛。

        Args:
            primary_error: upstream/cancellation 原异常或 validator typed 协议错误。

        Returns:
            不返回。

        Raises:
            BaseException: 始终重抛同一个 primary_error；关闭失败作为显式 cause。
        """

        self._state = _ValidatedStreamState.CLOSED
        self._buffered_result_event = None
        self._terminal_result_value = None
        try:
            await self._close_source_once()
        except BaseException as close_error:
            raise primary_error from close_error
        raise primary_error

    async def _close_source_once(self) -> None:
        """至多一次调用 raw source 的 ``aclose``。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: raw source 关闭失败时原样传播。
        """

        if self._source_close_attempted:
            return
        self._source_close_attempted = True
        await self._source.aclose()


__all__: tuple[str, ...] = ("ValidatedFinsEventStream",)
