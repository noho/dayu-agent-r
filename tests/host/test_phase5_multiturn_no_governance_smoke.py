"""Host P5 no-full-governance 纵向 smoke 测试。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from typing import Final, TypeVar

import dayu.engine.agent as agent_module
from dayu.contracts import FRAMEWORK_FETCH_MORE_TOOL_NAME, ToolSchema
from dayu.engine import (
    AgentMessage,
    AgentMessageRole,
    AgentRunRequest,
    AssistantMessage,
    ContentCompleteData,
    ContentDeltaData,
    FinalAnswerData,
    FinishReason,
    MimoThinkingExtension,
    ReasoningDeltaData,
    RunnerContentDeltaData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    SystemMessage,
    ToolCallRequestedData,
    ToolMessage,
)
from dayu.host import (
    RunEvent,
    RunEventCursor,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunSucceededResult,
    ToolFetchMoreFailedResult,
    ToolFetchMoreHandleRequest,
    ToolFetchMoreHandleSucceededResult,
    ToolFetchMoreRequest,
    ToolFetchMoreSucceededResult,
)
from dayu.host.contracts import (
    HostContextCompactCompletedData,
    ToolCursorIssuedData,
    ToolFetchMoreCompletedData,
    ToolResultTruncatedData,
)
from dayu.host._run_harness import LocalRunHarness
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL
from utils.smoke_host_multiturn_no_governance import (
    HUGE_ECHO_DEFINITION,
    MIMO_PLAN_PROVIDER_CASE,
    ToolExecutionProbe,
    _OverflowThenSuccessProxy,
    _RealProviderRunOutput,
    _ScriptedRunner,
    _collect_events,
    _fake_runner_spec,
    _fetch_more_script_from_hint,
    _final_script,
    _messages_to_text,
    _seeded_memory_store,
    _tool_call_script,
    build_runner_spec_from_case,
    build_huge_echo_harness,
    build_start_request,
    huge_echo_bundle,
    main as smoke_main,
    phase5_tool_schemas,
    parse_args as smoke_parse_args,
)

_SESSION_ID: str = "phase5-test-session"
_RUN_1: str = "phase5-test-run-1"
_RUN_2: str = "phase5-test-run-2"
_COMPACT_RUN: str = "phase5-test-compact"
_T = TypeVar("_T")
_ROOT_LOGGER_NAME: Final[str] = ""
_DAYU_LOGGER_NAME: Final[str] = "dayu"
_ENGINE_AGENT_LOGGER_NAME: Final[str] = "dayu.engine.agent"
_ENGINE_WARNING_PROBE_MESSAGE: Final[str] = (
    "phase5-smoke-after-warning-caplog-probe"
)
_ENGINE_VERBOSE_PROBE_MESSAGE: Final[str] = (
    "phase5-smoke-after-verbose-caplog-probe"
)
_SMOKE_CONFIGURE_THIRD_PARTY_LOGGER_NAMES: Final[tuple[str, ...]] = (
    "aiohttp",
    "aiohttp.access",
    "aiohttp.client",
    "aiohttp.internal",
    "aiohttp.server",
    "aiohttp.web",
    "aiohttp.websocket",
    "asyncio",
    "urllib3",
    "httpx",
    "httpcore",
)
_SMOKE_LOGGING_STATE_LOGGER_NAMES: Final[tuple[str, ...]] = (
    _ROOT_LOGGER_NAME,
    _DAYU_LOGGER_NAME,
    *_SMOKE_CONFIGURE_THIRD_PARTY_LOGGER_NAMES,
)


@dataclass(frozen=True, slots=True)
class _LoggerState:
    """logger 可变状态快照，用于隔离会主动装配日志的 smoke 入口。"""

    level: int
    propagate: bool
    handlers: tuple[logging.Handler, ...]
    disabled: bool


def _target_logger(name: str) -> logging.Logger:
    """按约定名称返回目标 logger。

    :param name: logger 名称；空字符串表示 root logger。
    :returns: 对应的 ``logging.Logger`` 实例。
    :raises Exception: 不主动抛出异常。
    """

    if name == _ROOT_LOGGER_NAME:
        return logging.getLogger()
    return logging.getLogger(name)


def _snapshot_logging_state(
    logger_names: tuple[str, ...],
) -> dict[str, _LoggerState]:
    """保存一组 logger 的关键可变状态。

    :param logger_names: 需要保存状态的 logger 名称集合。
    :returns: 以 logger 名称为键的状态快照。
    :raises Exception: 不主动抛出异常。
    """

    snapshots: dict[str, _LoggerState] = {}
    for name in logger_names:
        logger = _target_logger(name)
        snapshots[name] = _LoggerState(
            level=logger.level,
            propagate=logger.propagate,
            handlers=tuple(logger.handlers),
            disabled=logger.disabled,
        )
    return snapshots


def _restore_logging_state(
    snapshots: dict[str, _LoggerState],
) -> None:
    """恢复 logger 的关键可变状态。

    :param snapshots: ``_snapshot_logging_state`` 返回的状态快照。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    for name, state in snapshots.items():
        logger = _target_logger(name)
        logger.handlers = list(state.handlers)
        logger.setLevel(state.level)
        logger.propagate = state.propagate
        logger.disabled = state.disabled


@contextmanager
def _preserve_smoke_logging_state() -> Iterator[None]:
    """隔离 ``smoke_main`` 的全局 logging 装配副作用。

    :returns: 上下文管理器迭代器。
    :raises Exception: 上下文内异常会在恢复日志状态后透传。
    """

    snapshots = _snapshot_logging_state(_SMOKE_LOGGING_STATE_LOGGER_NAMES)
    try:
        yield
    finally:
        _restore_logging_state(snapshots)


def _assert_engine_caplog_still_captures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """确认 smoke 后 Engine logger 仍能通过 pytest caplog 捕获。

    :param caplog: pytest 日志捕获 fixture。
    :returns: 无返回值。
    :raises AssertionError: 当 WARNING 或 VERBOSE 探针日志未被捕获时抛出。
    """

    engine_logger = logging.getLogger(_ENGINE_AGENT_LOGGER_NAME)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_ENGINE_AGENT_LOGGER_NAME):
        engine_logger.warning(_ENGINE_WARNING_PROBE_MESSAGE)
    assert _ENGINE_WARNING_PROBE_MESSAGE in caplog.text

    caplog.clear()
    with caplog.at_level(VERBOSE_LOG_LEVEL, logger=_ENGINE_AGENT_LOGGER_NAME):
        engine_logger.log(
            VERBOSE_LOG_LEVEL,
            _ENGINE_VERBOSE_PROBE_MESSAGE,
        )
    assert _ENGINE_VERBOSE_PROBE_MESSAGE in caplog.text


def _runner_event(
    event_type: RunnerEventType, data: RunnerEventData
) -> RunnerEvent:
    """构造 RunnerEvent。

    :param event_type: runner event 类型。
    :param data: runner event data。
    :returns: RunnerEvent。
    :raises Exception: 不主动抛出异常。
    """

    return RunnerEvent(
        type=event_type,
        data=data,
        occurred_at=datetime.now(tz=timezone.utc),
    )


def _run_event(
    *,
    sequence: int,
    event_type: RunEventType,
    data: (
        ContentDeltaData
        | ReasoningDeltaData
        | ContentCompleteData
        | FinalAnswerData
    ),
) -> RunEvent:
    """构造已 append 的 Host RunEvent。

    :param sequence: Host event cursor sequence。
    :param event_type: RunEvent 类型。
    :param data: Engine preview data。
    :returns: RunEvent。
    :raises Exception: 不主动抛出异常。
    """

    return RunEvent(
        run_id=_RUN_1,
        session_id=_SESSION_ID,
        cursor=RunEventCursor(sequence=sequence),
        kind=(
            RunEventKind.CANONICAL
            if event_type is RunEventType.FINAL_ANSWER
            else RunEventKind.PREVIEW
        ),
        source=RunEventSource.ENGINE,
        type=event_type,
        occurred_at=datetime.now(tz=timezone.utc),
        data=data,
        source_engine_event_id=f"phase5-test-engine-{sequence}",
    )


def _preview_tool_call_script() -> tuple[RunnerEvent, ...]:
    """构造带 preview delta 与 reasoning 的工具调用脚本。

    :returns: RunnerEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        _runner_event(
            RunnerEventType.RUNNER_CONTENT_DELTA,
            RunnerContentDeltaData(delta="preview delta should not persist"),
        ),
        *_tool_call_script(),
    )


async def _collect(events: AsyncIterator[RunEvent]) -> tuple[RunEvent, ...]:
    """收集 RunEvent。

    :param events: RunEvent 流。
    :returns: RunEvent 元组。
    :raises Exception: 透传事件流异常。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
    return tuple(collected)


async def _streaming_reasoning_then_final_events(
    capsys: pytest.CaptureFixture[str],
    observed: list[str],
) -> AsyncIterator[RunEvent]:
    """产出 reasoning delta 后在 final 前观测 stdout。

    :param capsys: pytest stdout 捕获器。
    :param observed: 保存 final 事件产出前的 stdout 快照。
    :returns: RunEvent 异步流。
    :raises Exception: 不主动抛出异常。
    """

    yield _run_event(
        sequence=2,
        event_type=RunEventType.RUNNER_REASONING_DELTA,
        data=ReasoningDeltaData(
            iteration_id="iter-0",
            delta="live delta",
        ),
    )
    observed.append(capsys.readouterr().out)
    yield _run_event(
        sequence=6,
        event_type=RunEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content="最终回答",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
    )


async def _collect_until_cursor(
    events: AsyncIterator[RunEvent],
) -> tuple[RunEvent, ...]:
    """收集到 cursor issued 为止。

    :param events: RunEvent 流。
    :returns: 已收集事件。
    :raises AssertionError: 提前终态或流结束时抛出。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
        if isinstance(event.data, ToolCursorIssuedData):
            return tuple(collected)
        assert event.type not in {
            RunEventType.FINAL_ANSWER,
            RunEventType.RUN_FAILED,
            RunEventType.RUN_CANCELLED,
            RunEventType.RUN_SUSPENDED,
        }
    raise AssertionError("cursor was not issued")


async def _collect_until_fetch_more_completed(
    events: AsyncIterator[RunEvent],
) -> tuple[RunEvent, ...]:
    """收集到 framework ``fetch_more`` 完成事实为止。

    :param events: RunEvent 流。
    :returns: 已收集事件。
    :raises AssertionError: 提前终态或流结束时抛出。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
        if isinstance(event.data, ToolFetchMoreCompletedData):
            return tuple(collected)
        assert event.type not in {
            RunEventType.FINAL_ANSWER,
            RunEventType.RUN_FAILED,
            RunEventType.RUN_CANCELLED,
            RunEventType.RUN_SUSPENDED,
        }
    raise AssertionError("fetch_more was not completed")


def _last_data(events: tuple[RunEvent, ...], data_type: type[_T]) -> _T:
    """读取最后一个指定类型 data。

    :param events: RunEvent 元组。
    :param data_type: data 类型。
    :returns: data。
    :raises AssertionError: 未找到时抛出。
    """

    for event in reversed(events):
        if isinstance(event.data, data_type):
            return event.data
    raise AssertionError(f"missing data: {data_type.__name__}")


def _event_count(events: tuple[RunEvent, ...], event_type: RunEventType) -> int:
    """统计事件数量。

    :param events: RunEvent 元组。
    :param event_type: 事件类型。
    :returns: 数量。
    :raises Exception: 不主动抛出异常。
    """

    return sum(1 for event in events if event.type is event_type)


def _event_cursor_for_data(
    events: tuple[RunEvent, ...],
    data: ToolFetchMoreCompletedData,
) -> int:
    """读取指定 data 对应事件 cursor。

    :param events: 事件元组。
    :param data: 事件 data。
    :returns: cursor sequence。
    :raises AssertionError: 未找到时抛出。
    """

    for event in events:
        if event.data == data:
            return event.cursor.sequence
    raise AssertionError("missing event cursor for data")


def _latest_tool_message_content(messages: tuple[AgentMessage, ...]) -> str:
    """读取最近一条 ToolMessage content。

    :param messages: Runner 输入消息。
    :returns: ToolMessage content。
    :raises AssertionError: 未找到 ToolMessage 时抛出。
    """

    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            return message.content
    raise AssertionError("missing tool message")


async def _wait_succeeded(
    harness: LocalRunHarness, run_id: str
) -> RunSucceededResult:
    """等待成功终态。

    :param harness: LocalRunHarness 兼容对象。
    :param run_id: run id。
    :returns: 成功结果。
    :raises AssertionError: 未成功时抛出。
    """

    result = await harness.get_run_result(run_id)
    assert isinstance(result, RunSucceededResult)
    return result


async def _wait_memory_projected(
    harness: LocalRunHarness, session_id: str
) -> None:
    """等待 terminal 后 memory projection 完成。

    :param harness: LocalRunHarness。
    :param session_id: session id。
    :returns: 无返回值。
    :raises AssertionError: projection 未完成时抛出。
    """

    for _ in range(20):
        snapshot = await harness.memory_store.get_snapshot(session_id)
        if snapshot.recent_raw_turns:
            return
        await asyncio.sleep(0.0)
    raise AssertionError("memory projection was not completed")


@pytest.mark.asyncio
async def test_phase5_sequential_multiturn_stitches_eventlog_toolruntime_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """顺序多轮串起 Engine tool loop、ToolRuntime、fetch_more 与 memory。"""

    runner = _ScriptedRunner(
        scripts=(
            _preview_tool_call_script(),
            _fetch_more_script_from_hint,
            _final_script("final mentions huge_echo"),
            _final_script("run 2 final"),
        )
    )

    def _fake_build_runner(request: AgentRunRequest) -> _ScriptedRunner:
        """返回 fake provider runner。"""

        runner.requests.append(request)
        return runner

    monkeypatch.setattr(agent_module, "_build_runner", _fake_build_runner)
    probe = ToolExecutionProbe(
        gate_after_runtime=True,
        gate_tool_name=FRAMEWORK_FETCH_MORE_TOOL_NAME,
    )
    memory_store = _seeded_memory_store()
    harness = build_huge_echo_harness(probe=probe, memory_store=memory_store)
    schemas = phase5_tool_schemas()
    request = build_start_request(
        session_id=_SESSION_ID,
        run_id=_RUN_1,
        prompt="请调用 huge_echo，text=phase5-host-smoke。",
        runner_spec=_fake_runner_spec(),
        stream=True,
        tool_schemas=schemas,
    )

    stream = await harness.start_run(request)
    first_events = await _collect_until_fetch_more_completed(stream.events)
    cursor = _last_data(first_events, ToolCursorIssuedData)
    truncated = _last_data(first_events, ToolResultTruncatedData)
    fetch_completed = _last_data(first_events, ToolFetchMoreCompletedData)

    assert fetch_completed.next_cursor_fingerprint is not None
    next_handle = await harness.get_tool_fetch_more_handle(
        ToolFetchMoreHandleRequest(
            iteration_id="iter-0",
            session_id=_SESSION_ID,
            run_id=_RUN_1,
            tool_call_id=cursor.tool_call_id,
            cursor_fingerprint=fetch_completed.next_cursor_fingerprint,
        )
    )
    assert isinstance(next_handle, ToolFetchMoreHandleSucceededResult)
    probe.release()
    first_events = first_events + await _collect(stream.events)
    terminal = await _wait_succeeded(harness, _RUN_1)
    await _wait_memory_projected(harness, _SESSION_ID)
    event_count_before = len(await harness.event_store.list_events(_RUN_1, after=None))
    post_terminal = await harness.fetch_more_tool_result(
        ToolFetchMoreRequest(
            iteration_id="iter-0",
            session_id=_SESSION_ID,
            run_id=_RUN_1,
            tool_call_id=cursor.tool_call_id,
            cursor=next_handle.handle.cursor,
            scope_token=next_handle.handle.scope_token,
            limit=None,
        )
    )
    event_count_after = len(await harness.event_store.list_events(_RUN_1, after=None))

    second = await harness.start_run(
        build_start_request(
            session_id=_SESSION_ID,
            run_id=_RUN_2,
            prompt="Run 2：请说明 previous run 调用了什么工具？",
            runner_spec=_fake_runner_spec(),
            stream=True,
            tool_schemas=(),
        )
    )
    second_events = await _collect(second.events)
    second_input_text = _messages_to_text(
        harness.last_run_input_messages_by_run[_RUN_2]
    )

    first_schema_names = {
        schema.function.name for schema in runner.requests[0].tool_schemas
    }
    assert runner.requests[0].tool_schemas == schemas
    assert first_schema_names == {"huge_echo", FRAMEWORK_FETCH_MORE_TOOL_NAME}
    assert all(isinstance(schema, ToolSchema) for schema in runner.requests[0].tool_schemas)
    second_iteration_tool_message = _latest_tool_message_content(
        runner.messages_seen[1]
    )
    second_payload = json.loads(second_iteration_tool_message)
    assert second_payload["truncation"]["next_action"] == "fetch_more"
    assert "cursor" in second_payload["truncation"]["fetch_more_args"]
    assert "scope_token" in second_payload["truncation"]["fetch_more_args"]
    assert "scope_token" not in repr(first_events)
    fetch_more_requested = [
        event
        for event in first_events
        if event.type is RunEventType.TOOL_CALL_REQUESTED
        and isinstance(event.data, ToolCallRequestedData)
        and event.data.name == FRAMEWORK_FETCH_MORE_TOOL_NAME
    ]
    assert fetch_more_requested
    assert "scope_token" not in repr(fetch_more_requested)
    assert RunEventType.TOOL_CALL_REQUESTED in {event.type for event in first_events}
    assert _event_count(first_events, RunEventType.USER_INPUT_ACCEPTED) == 1
    assert probe.execute_called
    assert probe.runtime_completed
    assert probe.tool_names == ["huge_echo", FRAMEWORK_FETCH_MORE_TOOL_NAME]
    assert truncated.tool_name == "huge_echo"
    assert _last_data(first_events, ToolFetchMoreCompletedData).tool_name == "huge_echo"
    assert _event_cursor_for_data(first_events, fetch_completed) < terminal.terminal_event_cursor.sequence
    assert isinstance(post_terminal, ToolFetchMoreFailedResult)
    assert post_terminal.error_code == "run_terminal"
    assert not post_terminal.denied
    assert post_terminal.event_cursor is None
    assert event_count_before == event_count_after
    assert _event_count(second_events, RunEventType.USER_INPUT_ACCEPTED) == 1
    assert "phase5-host-smoke" in second_input_text
    assert "final mentions huge_echo" in second_input_text
    assert "tool_name=huge_echo" in second_input_text
    assert "source_event_cursor=" in second_input_text
    assert "phase5 pinned goal" in second_input_text
    assert "phase5-topic" in second_input_text


def test_phase5_engine_and_worker_requests_only_receive_tool_schema_tuple() -> None:
    """ToolDefinition / truncate / display metadata 不进入 Engine request。"""

    bundle = huge_echo_bundle()
    schemas = bundle.to_tool_schemas()
    request = build_start_request(
        session_id=_SESSION_ID,
        run_id="phase5-boundary-run",
        prompt="hello",
        runner_spec=_fake_runner_spec(),
        stream=True,
        tool_schemas=schemas,
    )
    field_names = set(AgentRunRequest.__dataclass_fields__)

    assert request.options.tool_schemas == schemas
    assert all(isinstance(schema, ToolSchema) for schema in request.options.tool_schemas)
    assert HUGE_ECHO_DEFINITION not in request.options.tool_schemas
    assert "truncate" not in field_names
    assert "display" not in field_names
    assert "display_name" not in field_names
    assert "tags" not in field_names
    assert "callable" not in field_names
    assert "executor" not in field_names


def test_real_provider_case_is_hardcoded_mimo_plan() -> None:
    """真实 provider smoke 使用脚本内写死的 Mimo ProviderCase。"""

    case = MIMO_PLAN_PROVIDER_CASE
    spec = build_runner_spec_from_case(case=case, api_key="secret-key")

    assert case.name == "mimo-v2.5-pro-plan"
    assert case.env_var == "MIMO_PLAN_API_KEY"
    assert case.provider == "mimo"
    assert case.endpoint == (
        "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    )
    assert case.model == "mimo-v2.5-pro"
    assert case.supports_stream
    assert case.supports_tool_calling
    assert not case.supports_stream_usage
    assert case.timeout_seconds == 3600.0
    assert case.stream_idle_timeout_seconds == 120.0
    assert case.stream_idle_heartbeat_seconds == 10.0
    assert case.provider_request == MimoThinkingExtension(enabled=True)
    assert spec.provider == case.provider
    assert spec.model == case.model
    assert spec.endpoint == case.endpoint
    assert spec.api_key_ref == case.env_var
    assert spec.headers["Authorization"] == "Bearer secret-key"
    assert spec.supports_tool_calling
    assert spec.supports_streaming
    assert not spec.supports_stream_usage
    assert spec.default_timeout_seconds == case.timeout_seconds
    assert spec.stream_idle_timeout_seconds == case.stream_idle_timeout_seconds
    assert spec.stream_idle_heartbeat_seconds == case.stream_idle_heartbeat_seconds
    assert spec.provider_request == case.provider_request


def test_messages_to_text_includes_assistant_content() -> None:
    """消息文本观察 helper 显式覆盖 assistant content。"""

    text = _messages_to_text(
        (
            AssistantMessage(
                role=AgentMessageRole.ASSISTANT,
                content="assistant final answer",
                reasoning_content="reasoning should stay out",
                tool_calls=(),
            ),
        )
    )

    assert "assistant final answer" in text
    assert "reasoning should stay out" not in text


@pytest.mark.asyncio
async def test_phase5_compact_retry_is_internal_attempt_and_preserves_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compact retry 不重复用户输入，并保留 stable layer / tool fact。"""

    runner = _ScriptedRunner(
        scripts=(
            _tool_call_script(),
            _fetch_more_script_from_hint,
            _final_script("final mentions huge_echo"),
        )
    )

    def _fake_build_runner(request: AgentRunRequest) -> _ScriptedRunner:
        """返回 fake provider runner。"""

        runner.requests.append(request)
        return runner

    monkeypatch.setattr(agent_module, "_build_runner", _fake_build_runner)
    probe = ToolExecutionProbe(gate_after_runtime=False)
    memory_store = _seeded_memory_store()
    harness = build_huge_echo_harness(probe=probe, memory_store=memory_store)
    first = await harness.start_run(
        build_start_request(
            session_id=_SESSION_ID,
            run_id=_RUN_1,
            prompt="请调用 huge_echo，text=phase5-host-smoke。",
            runner_spec=_fake_runner_spec(),
            stream=True,
            tool_schemas=phase5_tool_schemas(),
        )
    )
    first_events = await _collect(first.events)
    assert _last_data(first_events, ToolFetchMoreCompletedData).tool_name == "huge_echo"
    await _wait_succeeded(harness, _RUN_1)
    await _wait_memory_projected(harness, _SESSION_ID)

    proxy = _OverflowThenSuccessProxy()
    compact_harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        memory_store=memory_store,
    )
    compact = await compact_harness.start_run(
        build_start_request(
            session_id=_SESSION_ID,
            run_id=_COMPACT_RUN,
            prompt="当前用户问题触发 compact。",
            runner_spec=_fake_runner_spec(),
            stream=True,
            tool_schemas=(),
            caller_system_messages=(
                SystemMessage(
                    role=AgentMessageRole.SYSTEM,
                    content="caller system prompt",
                ),
            ),
        )
    )
    compact_events = await _collect(compact.events)
    retry_text = _messages_to_text(proxy.requests[1].input.messages)

    assert _event_count(compact_events, RunEventType.USER_INPUT_ACCEPTED) == 1
    assert len(proxy.requests) == 2
    assert _last_data(compact_events, HostContextCompactCompletedData).reduced
    assert "caller system prompt" in retry_text
    assert "当前用户问题触发 compact" in retry_text
    assert "phase5 pinned goal" in retry_text
    assert "tool_name=huge_echo" in retry_text
    assert "source_event_cursor=" in retry_text


@pytest.mark.asyncio
async def test_phase5_preview_and_reasoning_do_not_enter_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preview delta / reasoning 不进入后续 Run 的运行态输入。"""

    runner = _ScriptedRunner(
        scripts=(
            _preview_tool_call_script(),
            _fetch_more_script_from_hint,
            _final_script("final mentions huge_echo"),
            _final_script("run 2 final"),
        )
    )

    def _fake_build_runner(request: AgentRunRequest) -> _ScriptedRunner:
        """返回 fake provider runner。"""

        runner.requests.append(request)
        return runner

    monkeypatch.setattr(agent_module, "_build_runner", _fake_build_runner)
    probe = ToolExecutionProbe(gate_after_runtime=False)
    harness = build_huge_echo_harness(
        probe=probe,
        memory_store=_seeded_memory_store(),
    )
    first = await harness.start_run(
        build_start_request(
            session_id=_SESSION_ID,
            run_id=_RUN_1,
            prompt="请调用 huge_echo，text=phase5-host-smoke。",
            runner_spec=_fake_runner_spec(),
            stream=True,
            tool_schemas=phase5_tool_schemas(),
        )
    )
    await _collect(first.events)
    await _wait_succeeded(harness, _RUN_1)
    await _wait_memory_projected(harness, _SESSION_ID)
    second = await harness.start_run(
        build_start_request(
            session_id=_SESSION_ID,
            run_id=_RUN_2,
            prompt="Run 2 问题。",
            runner_spec=_fake_runner_spec(),
            stream=True,
            tool_schemas=(),
        )
    )
    await _collect(second.events)
    second_text = _messages_to_text(harness.last_run_input_messages_by_run[_RUN_2])

    assert "fake reasoning must stay preview" not in second_text
    assert "preview delta should not persist" not in second_text


def test_phase5_smoke_script_reports_clear_missing_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """真实 provider 缺 key 时 clear failure，且不输出敏感材料。

    :param monkeypatch: pytest 环境变量 patch fixture。
    :param capsys: pytest stdout / stderr 捕获 fixture。
    :param caplog: pytest 日志捕获 fixture。
    :returns: 无返回值。
    :raises AssertionError: 当失败输出、敏感信息过滤或日志隔离断言不满足时抛出。
    """

    monkeypatch.delenv("MIMO_PLAN_API_KEY", raising=False)

    with _preserve_smoke_logging_state():
        exit_code = smoke_main(["--case", "real-provider", "--log-level", "INFO"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "reason=missing_api_key" in output
    assert "case_source=hardcoded_provider_case" in output
    assert (
        "thinking_extension_source="
        "intentional_hardcoded_provider_case_not_llm_models_json"
    ) in output
    assert "case=real-provider thinking " not in output
    assert "case=real-provider final_answer " not in output
    assert "scope_token" not in output
    assert "Bearer " not in output
    _assert_engine_caplog_still_captures(caplog)


def test_phase5_smoke_thinking_flag_defaults_to_false() -> None:
    """smoke thinking 开关默认关闭，参数名与 OLD prompt 对齐。"""

    args = smoke_parse_args(["--case", "real-provider", "--log-level", "INFO"])
    enabled_args = smoke_parse_args(
        ["--case", "real-provider", "--log-level", "INFO", "--thinking"]
    )

    assert not args.thinking
    assert enabled_args.thinking


def test_phase5_real_provider_thinking_output_is_reasoning_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """thinking 诊断有 delta 时只输出 provider reasoning delta。"""

    events = (
        _run_event(
            sequence=2,
            event_type=RunEventType.RUNNER_REASONING_DELTA,
            data=ReasoningDeltaData(
                iteration_id="iter-0",
                delta="delta reasoning ",
            ),
        ),
        _run_event(
            sequence=3,
            event_type=RunEventType.RUNNER_CONTENT_DELTA,
            data=ContentDeltaData(
                iteration_id="iter-0",
                delta="preview delta should not persist",
            ),
        ),
        _run_event(
            sequence=4,
            event_type=RunEventType.RUNNER_REASONING_DELTA,
            data=ReasoningDeltaData(
                iteration_id="iter-0",
                delta="second delta",
            ),
        ),
        _run_event(
            sequence=5,
            event_type=RunEventType.RUNNER_CONTENT_COMPLETED,
            data=ContentCompleteData(
                iteration_id="iter-0",
                content="completed preview should not persist",
                reasoning_content="provider reasoning\nsecond line",
                finish_reason=FinishReason.STOP,
            ),
        ),
    )

    outputter = _RealProviderRunOutput(run_index=1)
    for event in events:
        outputter.observe(event)
    outputter.finish()
    output = capsys.readouterr().out

    assert "SMOKE case=real-provider thinking" not in output
    assert "thinking_delta run_index=1" in output
    assert "source=delta" in output
    assert "delta reasoning second delta" in output
    assert "source=aggregate" not in output
    assert "provider reasoning" not in output
    assert "preview delta should not persist" not in output
    assert "completed preview should not persist" not in output
    assert output.startswith("\n")
    assert output.endswith("\n\n")


def test_phase5_real_provider_thinking_falls_back_to_aggregate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """没有 reasoning delta 时，thinking 诊断才回退聚合 reasoning。"""

    events = (
        _run_event(
            sequence=3,
            event_type=RunEventType.RUNNER_CONTENT_COMPLETED,
            data=ContentCompleteData(
                iteration_id="iter-0",
                content="completed preview should not persist",
                reasoning_content="provider reasoning\nsecond line",
                finish_reason=FinishReason.STOP,
            ),
        ),
    )

    outputter = _RealProviderRunOutput(run_index=1)
    for event in events:
        outputter.observe(event)
    output = capsys.readouterr().out

    assert "SMOKE case=real-provider thinking" not in output
    assert "thinking_delta run_index=1" in output
    assert "source=aggregate" in output
    assert "fallback=no_delta" in output
    assert "provider reasoning\nsecond line" in output
    assert "completed preview should not persist" not in output


def test_phase5_real_provider_thinking_absent_is_explicit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """开启 thinking 但无 reasoning 事件时不制造空 thinking 日志。"""

    outputter = _RealProviderRunOutput(run_index=2)
    outputter.finish()
    output = capsys.readouterr().out

    assert output == ""


def test_phase5_real_provider_final_answer_outputs_short_preview(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """thinking 开启时 final answer 只输出前缀预览。"""

    long_answer = "最终回答：" + ("很长" * 180)
    events = (
        _run_event(
            sequence=7,
            event_type=RunEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=long_answer,
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
        ),
    )

    outputter = _RealProviderRunOutput(run_index=1)
    for event in events:
        outputter.observe(event)
    output = capsys.readouterr().out

    assert "SMOKE case=real-provider final_answer" not in output
    assert "final_answer run_index=1" in output
    assert "cursor=7" in output
    assert "最终回答：" in output
    assert "preview_chars=320" in output
    assert "...[truncated]" in output
    assert len(output.strip().splitlines()[-1]) == 320


def test_phase5_real_provider_final_answer_is_printed_after_thinking(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """同一 run 中 final answer 必须在 reasoning delta 之后输出。"""

    events = (
        _run_event(
            sequence=2,
            event_type=RunEventType.RUNNER_REASONING_DELTA,
            data=ReasoningDeltaData(
                iteration_id="iter-0",
                delta="delta reasoning",
            ),
        ),
        _run_event(
            sequence=6,
            event_type=RunEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content="最终回答",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
        ),
    )

    outputter = _RealProviderRunOutput(run_index=1)
    for event in events:
        outputter.observe(event)
    output = capsys.readouterr().out

    assert output.index("thinking_delta run_index=1 source=delta") < output.index(
        "final_answer run_index=1"
    )


@pytest.mark.asyncio
async def test_phase5_real_provider_thinking_delta_prints_while_streaming(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """reasoning delta 必须在 final event 到达前随 RunEvent 流即时输出。"""

    observed: list[str] = []
    outputter = _RealProviderRunOutput(run_index=1)

    await _collect_events(
        _streaming_reasoning_then_final_events(capsys, observed),
        output=outputter,
    )
    outputter.finish()
    final_output = capsys.readouterr().out

    assert len(observed) == 1
    assert "thinking_delta run_index=1 source=delta" in observed[0]
    assert "live delta" in observed[0]
    assert "final_answer run_index=1" not in observed[0]
    assert "final_answer run_index=1" in final_output
