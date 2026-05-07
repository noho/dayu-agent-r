"""Host P1.5 Run harness 与 RunEventStore 集成测试。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest
from _pytest.logging import LogCaptureFixture

from dayu.contracts import CancellationToken
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    ContentCompleteData,
    ContentDeltaData,
    EngineEvent,
    EngineEventData,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    ReasoningDeltaData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
    RunnerCallOptions,
    RunnerSpec,
    ToolCallRequestedData,
    ToolResultAcceptedData,
    UserMessage,
)
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._event_translation import translate_engine_event
from dayu.host._run_harness import LocalRunHarness
from dayu.host.contracts import (
    HostRunFailedData,
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunFailedResult,
    RunInput,
    RunOptions,
    RunSucceededResult,
    StartRunRequest,
)

_WAIT_SECONDS: float = 0.5
_POLL_LIMIT: int = 20
_INITIAL_CURSOR_SEQUENCE: int = -1


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _AsyncReleaseGate:
    """测试用异步释放门。"""

    event: asyncio.Event = field(default_factory=asyncio.Event)

    async def wait(self) -> None:
        """等待释放。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        await self.event.wait()

    def release(self) -> None:
        """释放等待方。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.event.set()


@dataclass(slots=True)
class _ScriptedProxy:
    """按脚本产出 EngineEvent 的 fake WorkerProxy。"""

    events: tuple[EngineEvent, ...]
    release_after_first_event: _AsyncReleaseGate | None = None
    yielded_count: int = 0

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回脚本化 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        return self._iter_events()

    async def _iter_events(self) -> AsyncIterator[EngineEvent]:
        """产出脚本事件。

        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        for index, event in enumerate(self.events):
            self.yielded_count += 1
            yield event
            if index == 0 and self.release_after_first_event is not None:
                await self.release_after_first_event.wait()


@dataclass(frozen=True, slots=True)
class _FailingProxy:
    """启动后立即抛出异常的 fake WorkerProxy。"""

    error: Exception

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回会失败的 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 迭代时抛出配置的异常。
        """

        return self._fail()

    async def _fail(self) -> AsyncIterator[EngineEvent]:
        """抛出配置的异常。

        :returns: EngineEvent 异步流。
        :raises Exception: 始终抛出配置的异常。
        """

        empty_events: tuple[EngineEvent, ...] = ()
        for event in empty_events:
            yield event
        raise self.error


@dataclass(slots=True)
class _ClosingFailureEngineEvents:
    """关闭时失败的测试用 EngineEvent 异步流。"""

    events: tuple[EngineEvent, ...]
    close_error: Exception
    iteration_error: Exception | None = None
    _next_index: int = 0

    def __aiter__(self) -> AsyncIterator[EngineEvent]:
        """返回自身作为异步迭代器。

        :returns: EngineEvent 异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> EngineEvent:
        """按顺序产出事件，并在事件耗尽后按配置失败或结束。

        :returns: 下一个 EngineEvent。
        :raises Exception: 事件耗尽且配置 ``iteration_error`` 时抛出。
        :raises StopAsyncIteration: 事件耗尽且未配置异常时抛出。
        """

        if self._next_index < len(self.events):
            event = self.events[self._next_index]
            self._next_index += 1
            return event
        if self.iteration_error is not None:
            raise self.iteration_error
        raise StopAsyncIteration

    async def aclose(self) -> None:
        """模拟底层 stream 关闭失败。

        :returns: 无返回值。
        :raises Exception: 始终抛出配置的关闭异常。
        """

        raise self.close_error


@dataclass(frozen=True, slots=True)
class _ClosingFailureProxy:
    """返回关闭失败 EngineEvent 流的 fake WorkerProxy。"""

    engine_events: _ClosingFailureEngineEvents

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回配置好的 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        return self.engine_events


@dataclass(slots=True)
class _RecordingRunEventStore:
    """记录 append 返回事件的测试用 RunEventStore。"""

    inner: InMemoryRunEventStore = field(default_factory=InMemoryRunEventStore)
    appended_events: list[RunEvent] = field(default_factory=list)

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """追加事件并记录 store 返回的 RunEvent。

        :param draft: 待追加的 RunEvent 草稿。
        :returns: 已 append 的 RunEvent。
        :raises Exception: 透传内部 store append 异常。
        """

        event = await self.inner.append(draft)
        self.appended_events.append(event)
        return event

    async def list_events(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> tuple[RunEvent, ...]:
        """补读内部 store 事件。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor。
        :returns: RunEvent 元组。
        :raises Exception: 透传内部 store 读取异常。
        """

        return await self.inner.list_events(run_id=run_id, after=after)

    def subscribe(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncIterator[RunEvent]:
        """订阅内部 store 事件流。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor。
        :returns: RunEvent 异步流。
        :raises Exception: 透传内部 store 订阅异常。
        """

        return self.inner.subscribe(run_id=run_id, after=after)


def _request(run_id: str) -> StartRunRequest:
    """构造 Host StartRunRequest。

    :param run_id: Run id。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id="session",
        run_id=run_id,
        input=RunInput(
            messages=(
                UserMessage(role=AgentMessageRole.USER, content="hello"),
            )
        ),
        options=RunOptions(
            runner_spec=RunnerSpec(
                provider="openai",
                model="model",
                endpoint="https://example.test/v1/chat/completions",
                api_key_ref="TEST_KEY",
                headers={},
                supports_tool_calling=True,
                supports_streaming=True,
                supports_stream_usage=False,
                default_timeout_seconds=30.0,
                max_retries=0,
                provider_request=None,
            ),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=True,
            ),
            agent_policy=AgentPolicy(
                max_iterations=3,
                continuation_max_attempts=1,
                allow_tool_calls=True,
            ),
            stream=True,
            disable_tools=True,
            tool_schemas=(),
        ),
    )


def _engine_content_delta(run_id: str) -> EngineEvent:
    """构造 Engine content delta 事件。

    :param run_id: Run id。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"{run_id}_engine_delta",
        sequence=10,
        occurred_at=_utc_now(),
        session_id="session",
        run_id=run_id,
        type=EngineEventType.RUNNER_CONTENT_DELTA,
        data=ContentDeltaData(iteration_id="iter", delta="partial"),
        metadata=None,
    )


def _engine_final(run_id: str, content: str) -> EngineEvent:
    """构造 Engine final answer 事件。

    :param run_id: Run id。
    :param content: 最终回答正文。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"{run_id}_engine_final",
        sequence=11,
        occurred_at=_utc_now(),
        session_id="session",
        run_id=run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )


def _engine_event(
    *,
    run_id: str,
    event_type: EngineEventType,
    data: EngineEventData,
) -> EngineEvent:
    """构造指定类型的 EngineEvent。

    :param run_id: Run id。
    :param event_type: EngineEventType。
    :param data: EngineEvent data。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"{run_id}_{event_type.value}",
        sequence=1,
        occurred_at=_utc_now(),
        session_id="session",
        run_id=run_id,
        type=event_type,
        data=data,
        metadata=None,
    )


async def _collect(events: AsyncIterator[RunEvent]) -> list[RunEvent]:
    """收集 RunEvent 流。

    :param events: RunEvent 异步流。
    :returns: RunEvent 列表。
    :raises Exception: 透传事件流异常。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
    return collected


async def _next_event(events: AsyncIterator[RunEvent]) -> RunEvent:
    """带超时读取下一个 RunEvent。

    :param events: RunEvent 异步流。
    :returns: 下一个 RunEvent。
    :raises TimeoutError: 超时未收到事件时抛出。
    """

    return await asyncio.wait_for(anext(events), timeout=_WAIT_SECONDS)


async def _wait_for_store_count(
    store: InMemoryRunEventStore,
    *,
    run_id: str,
    expected_count: int,
) -> tuple[RunEvent, ...]:
    """等待 store 中某个 run 至少拥有指定数量事件。

    :param store: 内存 RunEventStore。
    :param run_id: Run id。
    :param expected_count: 期望最小事件数。
    :returns: 当前已 append 的事件元组。
    :raises AssertionError: 等待后事件数仍不足时抛出。
    """

    for _ in range(_POLL_LIMIT):
        events = await store.list_events(run_id=run_id, after=None)
        if len(events) >= expected_count:
            return events
        await asyncio.sleep(0)
    raise AssertionError("events were not appended")


async def _wait_for_background_error_log(
    records: Sequence[logging.LogRecord],
    *,
    run_id: str,
) -> logging.LogRecord:
    """等待后台 task ERROR 日志被 caplog 捕获。

    :param records: caplog 捕获的日志记录序列。
    :param run_id: 期望出现的 Run id。
    :returns: 匹配的日志记录。
    :raises AssertionError: 等待后仍未捕获到日志时抛出。
    """

    for _ in range(_POLL_LIMIT):
        for record in records:
            if (
                record.levelno == logging.ERROR
                and "host.run.background_task_failed" in record.getMessage()
                and run_id in record.getMessage()
            ):
                return record
        await asyncio.sleep(0)
    raise AssertionError("background task error log was not captured")


@pytest.mark.asyncio
async def test_run_stream_reads_events_after_store_append() -> None:
    """RunStream.events 只能观察到已 append 的 RunEvent。"""

    run_id = "eventlog_append_before_stream"
    gate = _AsyncReleaseGate()
    store = _RecordingRunEventStore()
    harness = LocalRunHarness(
        proxy=_ScriptedProxy(
            events=(
                _engine_content_delta(run_id=run_id),
                _engine_final(run_id=run_id, content="done"),
            ),
            release_after_first_event=gate,
        ),
        event_store=store,
    )

    stream = await harness.start_run(_request(run_id))

    assert stream.handle.event_cursor.sequence == _INITIAL_CURSOR_SEQUENCE
    first_from_stream = await _next_event(stream.events)
    assert store.appended_events
    assert first_from_stream == store.appended_events[0]
    assert first_from_stream.kind is RunEventKind.CANONICAL
    assert first_from_stream.type is RunEventType.USER_INPUT_ACCEPTED
    second_from_stream = await _next_event(stream.events)
    assert second_from_stream == store.appended_events[1]
    assert second_from_stream.kind is RunEventKind.PREVIEW

    gate.release()
    remaining = await _collect(stream.events)
    assert remaining[-1].type is RunEventType.FINAL_ANSWER


@pytest.mark.asyncio
async def test_result_snapshot_only_uses_appended_terminal_event() -> None:
    """get_run_result 不从 preview 片段推导结果，只读已 append 终态事件。"""

    run_id = "eventlog_result_from_terminal"
    gate = _AsyncReleaseGate()
    store = InMemoryRunEventStore()
    harness = LocalRunHarness(
        proxy=_ScriptedProxy(
            events=(
                _engine_content_delta(run_id=run_id),
                _engine_final(run_id=run_id, content="stable answer"),
            ),
            release_after_first_event=gate,
        ),
        event_store=store,
    )

    stream = await harness.start_run(_request(run_id))
    await _wait_for_store_count(store, run_id=run_id, expected_count=2)

    assert await harness.get_run_result(run_id) is None

    gate.release()
    events = await _collect(stream.events)
    result = await harness.get_run_result(run_id)

    assert isinstance(result, RunSucceededResult)
    assert result.content == "stable answer"
    assert result.terminal_event_cursor == events[-1].cursor


@pytest.mark.asyncio
async def test_proxy_exception_appends_host_owned_failure_event() -> None:
    """worker / proxy 异常会落 Host-owned canonical failure 事件。"""

    run_id = "eventlog_host_failure"
    store = InMemoryRunEventStore()
    harness = LocalRunHarness(
        proxy=_FailingProxy(error=RuntimeError("boom")),
        event_store=store,
    )

    stream = await harness.start_run(_request(run_id))
    events = await _collect(stream.events)
    result = await harness.get_run_result(run_id)

    assert len(events) == 2
    assert events[0].type is RunEventType.USER_INPUT_ACCEPTED
    failure = events[-1]
    assert failure.kind is RunEventKind.CANONICAL
    assert failure.source is RunEventSource.HOST
    assert failure.source_engine_event_id is None
    assert failure.type is RunEventType.RUN_FAILED
    assert isinstance(failure.data, HostRunFailedData)
    assert failure.data.exception_type == "RuntimeError"
    assert isinstance(result, RunFailedResult)
    assert result.error_code == "host_worker_failed"
    assert result.terminal_event_cursor == failure.cursor


@pytest.mark.asyncio
async def test_run_input_build_trace_cache_evicts_old_runs_fifo() -> None:
    """RunInput 构造 trace 缓存按容量 FIFO 淘汰，避免无界增长。"""

    store = InMemoryRunEventStore()
    harness = LocalRunHarness(
        proxy=_ScriptedProxy(events=()),
        event_store=store,
        run_input_trace_cache_limit=2,
    )

    for run_id in ("trace-run-1", "trace-run-2", "trace-run-3"):
        stream = await harness.start_run(_request(run_id))
        await _collect(stream.events)

    assert tuple(harness.last_run_input_build_trace_by_run) == (
        "trace-run-2",
        "trace-run-3",
    )


@pytest.mark.asyncio
async def test_harness_stops_after_terminal_and_keeps_views_consistent() -> None:
    """harness 看到首个终态后停止消费，三种读取视图保持同源。"""

    run_id = "eventlog_terminal_then_preview"
    store = InMemoryRunEventStore()
    proxy = _ScriptedProxy(
        events=(
            _engine_final(run_id=run_id, content="first terminal"),
            _engine_content_delta(run_id=run_id),
        )
    )
    harness = LocalRunHarness(proxy=proxy, event_store=store)

    stream = await harness.start_run(_request(run_id))
    events = await _collect(stream.events)
    listed = await store.list_events(run_id=run_id, after=None)
    after_terminal = await _collect(
        harness.stream_run_events(run_id=run_id, after=events[-1].cursor)
    )
    result = await harness.get_run_result(run_id)

    assert proxy.yielded_count == 1
    assert events == list(listed)
    assert len(events) == 2
    assert events[0].type is RunEventType.USER_INPUT_ACCEPTED
    assert events[-1].type is RunEventType.FINAL_ANSWER
    assert after_terminal == []
    assert isinstance(result, RunSucceededResult)
    assert result.content == "first terminal"
    assert result.terminal_event_cursor == events[-1].cursor


@pytest.mark.asyncio
async def test_harness_ignores_second_terminal_after_first_terminal() -> None:
    """harness 不消费首个终态后的第二个终态事件。"""

    run_id = "eventlog_terminal_then_terminal"
    store = InMemoryRunEventStore()
    proxy = _ScriptedProxy(
        events=(
            _engine_final(run_id=run_id, content="first terminal"),
            _engine_final(run_id=run_id, content="second terminal"),
        )
    )
    harness = LocalRunHarness(proxy=proxy, event_store=store)

    stream = await harness.start_run(_request(run_id))
    events = await _collect(stream.events)
    listed = await store.list_events(run_id=run_id, after=None)
    result = await harness.get_run_result(run_id)

    assert proxy.yielded_count == 1
    assert events == list(listed)
    assert len(events) == 2
    assert events[0].type is RunEventType.USER_INPUT_ACCEPTED
    assert isinstance(result, RunSucceededResult)
    assert result.content == "first terminal"
    assert result.terminal_event_cursor == events[-1].cursor


@pytest.mark.asyncio
async def test_terminal_result_error_does_not_append_host_failure() -> None:
    """Host 契约错误不得伪装成 Host-owned failure terminal。"""

    run_id = "eventlog_mismatch_terminal"
    store = InMemoryRunEventStore()
    harness = LocalRunHarness(
        proxy=_ScriptedProxy(
            events=(
                _engine_event(
                    run_id=run_id,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=RunFailedData(
                        error_code="bad_contract",
                        message="bad",
                        recoverable=False,
                    ),
                ),
            )
        ),
        event_store=store,
    )

    with pytest.raises(TypeError, match="FinalAnswerData"):
        await harness._run_to_store(_request(run_id))

    events = await store.list_events(run_id=run_id, after=None)
    assert len(events) == 1
    assert events[0].type is RunEventType.FINAL_ANSWER
    assert events[0].source is RunEventSource.ENGINE
    assert events[0].source_engine_event_id == (
        f"{run_id}_{EngineEventType.FINAL_ANSWER.value}"
    )
    with pytest.raises(TypeError, match="FinalAnswerData"):
        await harness.get_run_result(run_id)


@pytest.mark.asyncio
async def test_stream_close_error_does_not_mask_terminal_contract_error(
    caplog: LogCaptureFixture,
) -> None:
    """关闭 stream 失败不得掩盖 Host 自身契约错误。"""

    run_id = "eventlog_close_error_with_contract_error"
    store = InMemoryRunEventStore()
    harness = LocalRunHarness(
        proxy=_ClosingFailureProxy(
            engine_events=_ClosingFailureEngineEvents(
                events=(
                    _engine_event(
                        run_id=run_id,
                        event_type=EngineEventType.FINAL_ANSWER,
                        data=RunFailedData(
                            error_code="bad_contract",
                            message="bad",
                            recoverable=False,
                        ),
                    ),
                ),
                close_error=RuntimeError("close failed"),
            )
        ),
        event_store=store,
    )

    caplog.set_level(logging.WARNING, logger="dayu.host._run_harness")

    with pytest.raises(TypeError, match="FinalAnswerData"):
        await harness._run_to_store(_request(run_id))

    events = await store.list_events(run_id=run_id, after=None)
    close_logs = [
        record
        for record in caplog.records
        if "host.run.stream_close_failed" in record.getMessage()
    ]

    assert len(events) == 1
    assert events[0].source is RunEventSource.ENGINE
    assert events[0].type is RunEventType.FINAL_ANSWER
    assert all(event.source is not RunEventSource.HOST for event in events)
    assert len(close_logs) == 1
    assert close_logs[0].exc_info is not None
    assert close_logs[0].exc_info[0] is RuntimeError


@pytest.mark.asyncio
async def test_stream_close_error_does_not_change_worker_failure_fact(
    caplog: LogCaptureFixture,
) -> None:
    """关闭 stream 失败不得替换 worker/proxy 异常对应的事实事件。"""

    run_id = "eventlog_close_error_with_worker_error"
    store = InMemoryRunEventStore()
    harness = LocalRunHarness(
        proxy=_ClosingFailureProxy(
            engine_events=_ClosingFailureEngineEvents(
                events=(),
                close_error=RuntimeError("close failed"),
                iteration_error=ValueError("worker failed"),
            )
        ),
        event_store=store,
    )

    caplog.set_level(logging.WARNING, logger="dayu.host._run_harness")

    await harness._run_to_store(_request(run_id))

    events = await store.list_events(run_id=run_id, after=None)
    close_logs = [
        record
        for record in caplog.records
        if "host.run.stream_close_failed" in record.getMessage()
    ]
    result = await harness.get_run_result(run_id)

    assert len(events) == 1
    assert events[0].source is RunEventSource.HOST
    assert events[0].type is RunEventType.RUN_FAILED
    assert isinstance(events[0].data, HostRunFailedData)
    assert events[0].data.exception_type == "ValueError"
    assert isinstance(result, RunFailedResult)
    assert result.terminal_event_cursor == events[0].cursor
    assert len(close_logs) == 1
    assert close_logs[0].exc_info is not None
    assert close_logs[0].exc_info[0] is RuntimeError


@pytest.mark.asyncio
async def test_stream_close_error_after_success_does_not_append_host_failure(
    caplog: LogCaptureFixture,
) -> None:
    """成功终态后的关闭失败只记录日志，不生成 Host-owned failure。"""

    run_id = "eventlog_close_error_after_success"
    store = InMemoryRunEventStore()
    harness = LocalRunHarness(
        proxy=_ClosingFailureProxy(
            engine_events=_ClosingFailureEngineEvents(
                events=(_engine_final(run_id=run_id, content="done"),),
                close_error=RuntimeError("close failed"),
            )
        ),
        event_store=store,
    )

    caplog.set_level(logging.WARNING, logger="dayu.host._run_harness")

    await harness._run_to_store(_request(run_id))

    events = await store.list_events(run_id=run_id, after=None)
    result = await harness.get_run_result(run_id)

    assert len(events) == 1
    assert events[0].source is RunEventSource.ENGINE
    assert events[0].type is RunEventType.FINAL_ANSWER
    assert isinstance(result, RunSucceededResult)
    assert result.content == "done"
    assert all(event.source is not RunEventSource.HOST for event in events)
    assert any(
        "host.run.stream_close_failed" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_start_run_logs_background_contract_error(
    caplog: LogCaptureFixture,
) -> None:
    """public start_run 路径会记录后台 Host 契约错误并取回异常。"""

    run_id = "eventlog_public_mismatch_terminal"
    store = InMemoryRunEventStore()
    harness = LocalRunHarness(
        proxy=_ScriptedProxy(
            events=(
                _engine_event(
                    run_id=run_id,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=RunFailedData(
                        error_code="bad_contract",
                        message="bad",
                        recoverable=False,
                    ),
                ),
            )
        ),
        event_store=store,
    )

    caplog.set_level(logging.ERROR, logger="dayu.host._run_harness")
    stream = await harness.start_run(_request(run_id))
    events = await _collect(stream.events)
    record = await _wait_for_background_error_log(
        caplog.records,
        run_id=run_id,
    )
    stored_events = await store.list_events(run_id=run_id, after=None)

    assert len(events) == 2
    assert stored_events == tuple(events)
    assert events[0].type is RunEventType.USER_INPUT_ACCEPTED
    assert events[-1].source is RunEventSource.ENGINE
    assert events[-1].type is RunEventType.FINAL_ANSWER
    assert record.exc_info is not None
    assert record.exc_info[0] is TypeError
    assert "FinalAnswerData" in str(record.exc_info[1])
    engine_events = [
        event for event in stored_events if event.type is not RunEventType.USER_INPUT_ACCEPTED
    ]
    assert all(event.source is not RunEventSource.HOST for event in engine_events)


def test_engine_event_kind_classification_matrix() -> None:
    """EngineEvent 到 RunEventDraft 的 canonical / preview 分类完整覆盖。"""

    now = _utc_now()
    cancelled_data = RunCancelledData(
        reason="cancelled",
        requested_at=now,
        accepted_at=now,
        finished_at=now,
    )
    cases: tuple[tuple[EngineEventType, EngineEventData, RunEventKind], ...] = (
        (
            EngineEventType.FINAL_ANSWER,
            FinalAnswerData(
                content="done",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            RunEventKind.CANONICAL,
        ),
        (
            EngineEventType.RUN_FAILED,
            RunFailedData(
                error_code="failed",
                message="failed",
                recoverable=False,
            ),
            RunEventKind.CANONICAL,
        ),
        (
            EngineEventType.RUN_CANCELLED,
            cancelled_data,
            RunEventKind.CANONICAL,
        ),
        (
            EngineEventType.RUN_SUSPENDED,
            RunSuspendedData(reason="awaiting", resume_hint=None),
            RunEventKind.CANONICAL,
        ),
        (
            EngineEventType.RUNNER_CONTENT_DELTA,
            ContentDeltaData(iteration_id="iter", delta="content"),
            RunEventKind.PREVIEW,
        ),
        (
            EngineEventType.RUNNER_REASONING_DELTA,
            ReasoningDeltaData(iteration_id="iter", delta="reason"),
            RunEventKind.PREVIEW,
        ),
        (
            EngineEventType.RUNNER_CONTENT_COMPLETED,
            ContentCompleteData(
                iteration_id="iter",
                content="complete",
                reasoning_content=None,
                finish_reason=FinishReason.STOP,
            ),
            RunEventKind.PREVIEW,
        ),
        (
            EngineEventType.TOOL_CALL_REQUESTED,
            ToolCallRequestedData(
                iteration_id="iter",
                tool_call_id="tool_1",
                name="lookup",
                arguments={},
                index_in_iteration=0,
                provider_state=None,
            ),
            RunEventKind.CANONICAL,
        ),
        (
            EngineEventType.TOOL_RESULT_ACCEPTED,
            ToolResultAcceptedData(
                iteration_id="iter",
                tool_call_id="tool_1",
                name="lookup",
                index_in_iteration=0,
                outcome=ToolCompletedOutcome(
                    result=ToolResultSuccess(
                        ok=True,
                        value={"ok": True},
                        truncation=None,
                        meta=None,
                    )
                ),
            ),
            RunEventKind.CANONICAL,
        ),
    )

    for event_type, data, expected_kind in cases:
        draft = translate_engine_event(
            _engine_event(
                run_id=f"classify_{event_type.value}",
                event_type=event_type,
                data=data,
            )
        )
        assert draft.kind is expected_kind
