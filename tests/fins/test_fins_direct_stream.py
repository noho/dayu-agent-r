"""Fins direct stream 唯一终态 owner 的契约测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

import pytest

from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_SUCCESS,
    FinsDirectStreamProtocolError,
    FinsDirectStreamProtocolErrorKind,
    FinsEvent,
    FinsEventType,
    FinsOperationKind,
    FinsProgress,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.direct_stream import ValidatedFinsEventStream

_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE: Final[str] = (
    "Fins direct terminal result is not available before clean stream exhaustion"
)


@dataclass(slots=True)
class _RawStreamObservation:
    """记录真实 async generator 的迭代与终结事实。"""

    next_calls: int = 0
    generator_exit_calls: int = 0
    finally_calls: int = 0


async def _controlled_raw_stream(
    items: tuple[FinsEvent | BaseException, ...],
    *,
    observation: _RawStreamObservation,
    close_error: BaseException | None = None,
) -> AsyncGenerator[FinsEvent, None]:
    """以真实 async generator 依次产出事件并记录终结语义。

    Args:
        items: 依次产出或抛出的事件与异常。
        observation: 独立、严格类型化的 generator 观察状态。
        close_error: ``finally`` 在关闭路径应原样抛出的可选异常。

    Returns:
        真实 ``async def`` Fins raw event generator。

    Raises:
        BaseException: 当前 item 或关闭路径配置的异常原样抛出。
    """

    try:
        for item in items:
            observation.next_calls += 1
            if isinstance(item, BaseException):
                raise item
            try:
                yield item
            except GeneratorExit:
                observation.generator_exit_calls += 1
                raise
        observation.next_calls += 1
    finally:
        observation.finally_calls += 1
        if close_error is not None:
            raise close_error


def _validated_stream(
    source: AsyncGenerator[FinsEvent, None],
    *,
    operation_kind: FinsOperationKind = FinsOperationKind.DOWNLOAD,
) -> ValidatedFinsEventStream:
    """把受控 source 交给 production validator。

    Args:
        source: 受控 raw stream。
        operation_kind: validator 应记录的 direct 操作类型。

    Returns:
        使用 production 状态机的已验证 stream。

    Raises:
        TypeError: operation_kind 非法时由 production validator 抛出。
    """

    return ValidatedFinsEventStream(
        source,
        operation_kind=operation_kind,
    )


def _progress_event() -> FinsEvent:
    """构造安全的下载 progress 事件。

    Args:
        无。

    Returns:
        下载 progress 事件。

    Raises:
        ValueError: 固定测试数据违反事件契约时抛出。
    """

    return FinsEvent(
        event_type=FinsEventType.PROGRESS,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="下载进行中",
        emitted_at=datetime.now(timezone.utc),
        ticker="AAPL",
        filing_kind=None,
        document_label=None,
        progress=FinsProgress(
            stage="download",
            completed_units=1,
            total_units=2,
        ),
        result=None,
    )


def _result_summary() -> FinsResultSummary:
    """构造合法的 success 终态摘要。

    Args:
        无。

    Returns:
        success 终态摘要。

    Raises:
        ValueError: 固定测试数据违反结果契约时抛出。
    """

    return FinsResultSummary(
        status=FinsResultStatus.SUCCESS,
        exit_code=FINS_RESULT_EXIT_SUCCESS,
        title="下载完成",
        details=(),
        error_kind=None,
        error_message=None,
    )


def _result_event(
    result: FinsResultSummary | None = None,
) -> FinsEvent:
    """构造携带指定摘要的下载 RESULT 事件。

    Args:
        result: 可选终态摘要；省略时构造 success 摘要。

    Returns:
        下载 RESULT 事件。

    Raises:
        ValueError: 固定测试数据违反事件契约时抛出。
    """

    summary = result if result is not None else _result_summary()
    return FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="下载完成",
        emitted_at=datetime.now(timezone.utc),
        ticker="AAPL",
        filing_kind=None,
        document_label=None,
        progress=None,
        result=summary,
    )


async def _collect_events(
    stream: ValidatedFinsEventStream,
) -> tuple[FinsEvent, ...]:
    """完整消费 production validated stream。

    Args:
        stream: 待消费的已验证 stream。

    Returns:
        按产出顺序收集的事件。

    Raises:
        BaseException: stream 的 typed 协议错误或 upstream 异常原样传播。
    """

    return tuple([event async for event in stream])


def _assert_terminal_result_unavailable(stream: ValidatedFinsEventStream) -> None:
    """断言 terminal_result 尚不可用且使用 owner 固定安全消息。

    Args:
        stream: 待检查的已验证 stream。

    Returns:
        无。

    Raises:
        AssertionError: exception 类型或消息不符合 owner contract 时抛出。
    """

    with pytest.raises(RuntimeError) as captured:
        _ = stream.terminal_result
    assert str(captured.value) == _TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE


async def _result_then_waiting_source(
    result_event: FinsEvent,
    *,
    waiting: asyncio.Event,
    release: asyncio.Event,
) -> AsyncGenerator[FinsEvent, None]:
    """在 RESULT 后暂停，以便观察 RESULT_BUFFERED 状态。

    Args:
        result_event: 首个 RESULT 事件。
        waiting: source 进入暂停状态时设置的事件。
        release: 允许 source clean exhaustion 的事件。

    Returns:
        异步产出 result_event，随后等待并正常耗尽。

    Raises:
        asyncio.CancelledError: 等待期间 task 被取消时抛出。
    """

    yield result_event
    waiting.set()
    await release.wait()


@pytest.mark.asyncio
async def test_validated_stream_yields_progress_then_buffered_result_only_after_clean_end() -> None:
    """验证 RESULT 只在 raw source clean exhaustion 后产出。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 顺序、drain 或结果实例不符合契约时抛出。
    """

    summary = _result_summary()
    progress = _progress_event()
    result = _result_event(summary)
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream((progress, result), observation=observation)
    )

    events = await _collect_events(stream)

    assert events == (progress, result)
    assert observation.next_calls == 3
    assert observation.generator_exit_calls == 0
    assert observation.finally_calls == 1
    assert stream.terminal_result is summary


@pytest.mark.asyncio
async def test_validated_stream_missing_result_uses_fins_owned_typed_code() -> None:
    """验证 clean EOF 缺少 RESULT 由 Fins owner 产生 typed code。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: typed error 字段或消息不符合契约时抛出。
    """

    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream((), observation=observation)
    )

    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await _collect_events(stream)

    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.MISSING_RESULT
    assert captured.value.operation_kind is FinsOperationKind.DOWNLOAD
    assert captured.value.message == "Fins direct stream ended without RESULT"
    assert observation.next_calls == 1
    assert observation.generator_exit_calls == 0
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_duplicate_result_is_primary_and_closes_source_once() -> None:
    """验证 duplicate typed error 为 primary 且 raw source 只关闭一次。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: primary error 或关闭次数不符合契约时抛出。
    """

    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream(
            (_result_event(), _result_event()),
            observation=observation,
        )
    )

    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await _collect_events(stream)

    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT
    assert captured.value.operation_kind is FinsOperationKind.DOWNLOAD
    assert captured.value.message == "Fins direct stream produced multiple RESULT events"
    assert observation.generator_exit_calls == 1
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_event_after_result_is_primary_and_closes_source_once() -> None:
    """验证 RESULT 后 progress 由 event-after typed error 收口。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: typed error 或关闭次数不符合契约时抛出。
    """

    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream(
            (_result_event(), _progress_event()),
            observation=observation,
        )
    )

    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await _collect_events(stream)

    assert captured.value.reason is FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT
    assert captured.value.operation_kind is FinsOperationKind.DOWNLOAD
    assert captured.value.message == "Fins direct stream produced an event after RESULT"
    assert observation.generator_exit_calls == 1
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_upstream_error_identity_is_primary_and_closes_source_once() -> None:
    """验证 upstream exception 以同一对象传播并关闭 source 一次。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 异常身份或关闭次数不符合契约时抛出。
    """

    primary = RuntimeError("upstream failed")
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream((primary,), observation=observation)
    )

    with pytest.raises(RuntimeError) as captured:
        await _collect_events(stream)

    assert captured.value is primary
    assert observation.generator_exit_calls == 0
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_upstream_cancellation_identity_is_primary_and_closes_source_once() -> None:
    """验证 upstream cancellation 以同一对象传播并关闭 source 一次。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 取消身份或关闭次数不符合契约时抛出。
    """

    primary = asyncio.CancelledError("upstream cancelled")
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream((primary,), observation=observation)
    )

    with pytest.raises(asyncio.CancelledError) as captured:
        await _collect_events(stream)

    assert captured.value is primary
    assert observation.generator_exit_calls == 0
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_duplicate_error_stays_primary_when_cleanup_close_fails() -> None:
    """验证 duplicate error 不被 cleanup close failure 覆盖。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: primary/cause 身份不符合契约时抛出。
    """

    close_error = OSError("close failed")
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream(
            (_result_event(), _result_event()),
            observation=observation,
            close_error=close_error,
        )
    )

    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await _collect_events(stream)
    primary = captured.value

    assert primary.reason is FinsDirectStreamProtocolErrorKind.DUPLICATE_RESULT
    assert primary.operation_kind is FinsOperationKind.DOWNLOAD
    assert primary.message == "Fins direct stream produced multiple RESULT events"
    assert primary.__cause__ is close_error
    assert observation.generator_exit_calls == 1
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_event_after_result_error_stays_primary_when_cleanup_close_fails() -> None:
    """验证 event-after error 不被 cleanup close failure 覆盖。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: primary/cause 身份不符合契约时抛出。
    """

    close_error = OSError("close failed")
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream(
            (_result_event(), _progress_event()),
            observation=observation,
            close_error=close_error,
        )
    )

    with pytest.raises(FinsDirectStreamProtocolError) as captured:
        await _collect_events(stream)
    primary = captured.value

    assert primary.reason is FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT
    assert primary.operation_kind is FinsOperationKind.DOWNLOAD
    assert primary.message == "Fins direct stream produced an event after RESULT"
    assert primary.__cause__ is close_error
    assert observation.generator_exit_calls == 1
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_result_then_error_propagates_same_error_without_result() -> None:
    """验证 RESULT 后 upstream error 丢弃 success 并原样传播异常。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 结果泄漏、异常身份或关闭次数不符合契约时抛出。
    """

    primary = RuntimeError("upstream failed after result")
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream(
            (_result_event(), primary),
            observation=observation,
        )
    )
    observed: list[FinsEvent] = []

    with pytest.raises(RuntimeError) as captured:
        async for event in stream:
            observed.append(event)

    assert captured.value is primary
    assert observed == []
    assert observation.generator_exit_calls == 0
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_explicit_aclose_propagates_same_close_error_without_primary() -> None:
    """验证显式 close 没有 primary 时原样传播底层 close failure。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: close failure 身份或调用次数不符合契约时抛出。
    """

    close_error = OSError("close failed")
    progress = _progress_event()
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream(
            (progress,),
            observation=observation,
            close_error=close_error,
        )
    )

    assert await anext(stream) is progress

    with pytest.raises(OSError) as captured:
        await stream.aclose()

    assert captured.value is close_error
    assert observation.generator_exit_calls == 1
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_repeated_aclose_closes_source_once() -> None:
    """验证成功显式 close 后重复 close 不触发底层重试。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: raw source close 次数不符合契约时抛出。
    """

    progress = _progress_event()
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream((progress,), observation=observation)
    )

    assert await anext(stream) is progress

    await stream.aclose()
    await stream.aclose()

    assert observation.generator_exit_calls == 1
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_repeated_aclose_after_close_failure_does_not_retry_source() -> None:
    """验证首次 close 失败后重复 close 也不触发底层重试。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: close failure 身份或 raw close 次数不符合契约时抛出。
    """

    close_error = OSError("close failed")
    progress = _progress_event()
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream(
            (progress,),
            observation=observation,
            close_error=close_error,
        )
    )

    assert await anext(stream) is progress

    with pytest.raises(OSError) as captured:
        await stream.aclose()
    await stream.aclose()

    assert captured.value is close_error
    assert observation.generator_exit_calls == 1
    assert observation.finally_calls == 1


def test_validated_stream_terminal_result_in_open_raises_owned_runtime_error() -> None:
    """验证 OPEN 状态读取 terminal_result 使用 owner programmer error。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: exception 类型或消息不符合契约时抛出。
    """

    stream = _validated_stream(
        _controlled_raw_stream((), observation=_RawStreamObservation())
    )

    _assert_terminal_result_unavailable(stream)


@pytest.mark.asyncio
async def test_validated_stream_terminal_result_while_result_buffered_raises_owned_runtime_error() -> None:
    """验证 RESULT_BUFFERED 状态不能提前读取 terminal_result。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: availability 或最终结果身份不符合契约时抛出。
    """

    result = _result_event()
    waiting = asyncio.Event()
    release = asyncio.Event()
    stream = ValidatedFinsEventStream(
        _result_then_waiting_source(result, waiting=waiting, release=release),
        operation_kind=FinsOperationKind.DOWNLOAD,
    )
    next_task = asyncio.create_task(anext(stream))
    await waiting.wait()

    try:
        _assert_terminal_result_unavailable(stream)
    finally:
        release.set()
        yielded = await next_task

    assert yielded is result


@pytest.mark.asyncio
async def test_validated_stream_terminal_result_after_abortive_close_raises_owned_runtime_error() -> None:
    """验证 abortive close 后 terminal_result 保持不可用。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: availability 或 close 次数不符合契约时抛出。
    """

    progress = _progress_event()
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream(
            (progress, _result_event()),
            observation=observation,
        )
    )

    assert await anext(stream) is progress

    await stream.aclose()

    _assert_terminal_result_unavailable(stream)
    assert observation.generator_exit_calls == 1
    assert observation.finally_calls == 1


@pytest.mark.asyncio
async def test_validated_stream_terminal_result_after_clean_exhaustion_is_same_object() -> None:
    """验证 clean exhaustion 后返回 buffered result 的同一实例。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: terminal result 身份或事件顺序不符合契约时抛出。
    """

    summary = _result_summary()
    result = _result_event(summary)
    observation = _RawStreamObservation()
    stream = _validated_stream(
        _controlled_raw_stream((result,), observation=observation)
    )

    events = await _collect_events(stream)

    assert events == (result,)
    assert stream.terminal_result is summary
    assert observation.generator_exit_calls == 0
    assert observation.finally_calls == 1
