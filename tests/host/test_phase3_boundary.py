"""Host P3 public / internal 边界测试。"""

from __future__ import annotations

import ast
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture

import dayu.engine as engine
import dayu.host as host
from dayu.contracts import CancellationToken, ToolSchema
from dayu.engine import (
    AgentMessage,
    AgentPolicy,
    AssistantMessage,
    ContentCompleteData,
    EngineEvent,
    FinishReason,
    ReasoningDeltaData,
    RunnerCallOptions,
    RunnerSpec,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._event_translation import user_input_accepted_draft
from dayu.host._run_harness import LocalRunHarness
from dayu.host._run_input_builder import DefaultRunInputBuilder
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
    StartRunRequest,
)
from dayu.engine import AgentMessageRole

_ERROR_APPEND_FAILED: str = "append failed"


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _FailingAppendStore:
    """append 始终失败的测试 RunEventStore。"""

    append_count: int = 0

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """模拟 append 失败。

        :param draft: 待追加事件草稿。
        :returns: 永不返回。
        :raises RuntimeError: 始终抛出 append 失败。
        """

        self.append_count += 1
        raise RuntimeError(_ERROR_APPEND_FAILED)

    async def list_events(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> tuple[RunEvent, ...]:
        """返回空事件。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor。
        :returns: 空元组。
        :raises Exception: 不主动抛出异常。
        """

        return ()

    def subscribe(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncIterator[RunEvent]:
        """返回空订阅。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor。
        :returns: 空异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        return self._empty()

    async def _empty(self) -> AsyncIterator[RunEvent]:
        """空异步生成器。

        :returns: 空异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        empty_events: tuple[RunEvent, ...] = ()
        for event in empty_events:
            yield event


@dataclass(slots=True)
class _CountingProxy:
    """记录 Engine 是否被启动的测试 proxy。"""

    call_count: int = 0

    def stream_engine_events(
        self,
        request: StartRunRequest,
        tool_schemas: tuple[ToolSchema, ...],
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """记录调用并返回空事件流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入取消 token。
        :returns: 空 EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.call_count += 1
        return self._empty()

    async def _empty(self) -> AsyncIterator[EngineEvent]:
        """空 EngineEvent 异步生成器。

        :returns: 空异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        empty_events: tuple[EngineEvent, ...] = ()
        for event in empty_events:
            yield event


@dataclass(slots=True)
class _SynchronousFailingProxy:
    """启动 worker stream 时同步失败的测试 proxy。"""

    call_count: int = 0

    def stream_engine_events(
        self,
        request: StartRunRequest,
        tool_schemas: tuple[ToolSchema, ...],
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """模拟 proxy / worker 启动失败。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入取消 token。
        :returns: 永不返回。
        :raises RuntimeError: 始终抛出 worker 失败。
        """

        self.call_count += 1
        raise RuntimeError("worker failed")


async def _collect(events: AsyncIterator[RunEvent]) -> tuple[RunEvent, ...]:
    """收集 RunEvent。

    :param events: RunEvent 异步流。
    :returns: RunEvent 元组。
    :raises Exception: 透传事件流异常。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
    return tuple(collected)


def _request() -> StartRunRequest:
    """构造 StartRunRequest。

    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id="session-boundary",
        run_id="run-boundary",
        input=RunInput(
            messages=(
                UserMessage(role=AgentMessageRole.USER, content="用户输入"),
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


def _request_with_messages(
    messages: tuple[AgentMessage, ...],
) -> StartRunRequest:
    """构造指定消息的 StartRunRequest。

    :param messages: 入口消息元组。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    request = _request()
    return StartRunRequest(
        session_id=request.session_id,
        run_id=request.run_id,
        input=RunInput(messages=messages),
        options=request.options,
    )


def _engine_root() -> Path:
    """返回 Engine 源码根目录。

    :returns: Engine 包根目录。
    :raises AssertionError: 包文件缺失时抛出。
    """

    package_file = engine.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _imported_module_names(source: str) -> list[str]:
    """从源码中提取 import 模块名。

    :param source: Python 源码。
    :returns: 模块名列表。
    :raises SyntaxError: 源码无法解析时抛出。
    """

    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                names.append(node.module)
    return names


@pytest.mark.asyncio
async def test_append_user_input_failure_does_not_start_engine() -> None:
    """USER_INPUT_ACCEPTED append 失败不得启动 Engine。"""

    store = _FailingAppendStore()
    proxy = _CountingProxy()
    harness = LocalRunHarness(is_durable=False, proxy=proxy, event_store=store, memory_store=FakeInMemoryConversationMemoryStore())

    with pytest.raises(RuntimeError, match=_ERROR_APPEND_FAILED):
        await harness.start_run(_request())

    assert store.append_count == 1
    assert proxy.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "messages",
    (
        (),
        (
            UserMessage(role=AgentMessageRole.USER, content=""),
        ),
        (
            SystemMessage(role=AgentMessageRole.SYSTEM, content="历史 system"),
        ),
        (
            AssistantMessage(
                role=AgentMessageRole.ASSISTANT,
                content="历史 assistant",
                reasoning_content=None,
                tool_calls=(),
            ),
        ),
        (
            ToolMessage(
                role=AgentMessageRole.TOOL,
                tool_call_id="tool-call",
                content="历史 tool",
            ),
        ),
        (
            UserMessage(role=AgentMessageRole.USER, content="第一条"),
            UserMessage(role=AgentMessageRole.USER, content="第二条"),
        ),
        (
            UserMessage(role=AgentMessageRole.USER, content="当前输入"),
            AssistantMessage(
                role=AgentMessageRole.ASSISTANT,
                content="历史回答",
                reasoning_content=None,
                tool_calls=(),
            ),
        ),
    ),
)
async def test_invalid_ingress_transcript_does_not_start_engine_or_pollute_memory(
    messages: tuple[AgentMessage, ...],
) -> None:
    """入口 input 不是单条非空 UserMessage 时 fail fast。"""

    event_store = InMemoryRunEventStore()
    memory_store = FakeInMemoryConversationMemoryStore()
    proxy = _CountingProxy()
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        event_store=event_store,
        memory_store=memory_store,
    )

    with pytest.raises(ValueError):
        await harness.start_run(_request_with_messages(messages))

    assert proxy.call_count == 0
    assert await event_store.list_events("run-boundary", after=None) == ()
    snapshot = await memory_store.get_snapshot("session-boundary")
    assert snapshot.recent_raw_turns == ()
    assert snapshot.older_raw_turns == ()


@pytest.mark.asyncio
async def test_host_owned_worker_failure_projects_user_input_to_memory() -> None:
    """Host-owned failure 终态也会触发 memory projection。"""

    event_store = InMemoryRunEventStore()
    memory_store = FakeInMemoryConversationMemoryStore()
    proxy = _SynchronousFailingProxy()
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        event_store=event_store,
        memory_store=memory_store,
    )

    stream = await harness.start_run(_request())
    events = await _collect(stream.events)
    snapshot = await memory_store.get_snapshot("session-boundary")

    assert proxy.call_count == 1
    assert events[0].type is RunEventType.USER_INPUT_ACCEPTED
    assert events[-1].type is RunEventType.RUN_FAILED
    assert len(snapshot.recent_raw_turns) == 1
    assert snapshot.recent_raw_turns[0].user_text == "用户输入"


@pytest.mark.asyncio
async def test_engine_stream_without_terminal_fails_and_projects_memory(
    caplog: LogCaptureFixture,
) -> None:
    """Engine stream 正常结束但无终态时追加 Host-owned failure 并投影。"""

    caplog.set_level(logging.CRITICAL, logger="dayu.host._run_harness")
    event_store = InMemoryRunEventStore()
    memory_store = FakeInMemoryConversationMemoryStore()
    proxy = _CountingProxy()
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        event_store=event_store,
        memory_store=memory_store,
    )

    stream = await harness.start_run(_request())
    events = await _collect(stream.events)
    result = await harness.get_run_result("run-boundary")
    snapshot = await memory_store.get_snapshot("session-boundary")

    assert proxy.call_count == 1
    assert events[0].type is RunEventType.USER_INPUT_ACCEPTED
    assert events[-1].type is RunEventType.RUN_FAILED
    assert events[-1].source is RunEventSource.HOST
    assert isinstance(events[-1].data, HostRunFailedData)
    assert events[-1].data.error_code == "engine_stream_ended_without_terminal"
    assert events[-1].data.exception_type == "RuntimeError"
    assert isinstance(result, RunFailedResult)
    assert result.error_code == "engine_stream_ended_without_terminal"
    assert len(snapshot.recent_raw_turns) == 1
    assert snapshot.recent_raw_turns[0].user_text == "用户输入"
    assert snapshot.recent_raw_turns[0].terminal_summary is not None
    assert (
        "engine_stream_ended_without_terminal"
        in snapshot.recent_raw_turns[0].terminal_summary
    )
    assert any(
        record.levelno == logging.CRITICAL
        and "host.run.engine_stream_ended_without_terminal"
        in record.getMessage()
        for record in caplog.records
    )


def test_host_public_api_does_not_export_internal_memory_builder() -> None:
    """Host public API 不导出 internal store / builder / projection。"""

    forbidden = frozenset(
        {
            "ConversationMemoryStore",
            "InMemoryConversationMemoryStore",
            "RunInputBuilder",
            "DefaultRunInputBuilder",
            "RunInputBuildTrace",
        }
    )

    assert forbidden.isdisjoint(frozenset(host.__all__))
    for name in forbidden:
        assert not hasattr(host, name)


def test_engine_production_code_does_not_import_host_memory() -> None:
    """Engine 生产代码不得反向导入 Host memory / builder。"""

    violations: list[tuple[str, str]] = []
    for file_path in sorted(_engine_root().rglob("*.py")):
        if "__pycache__" in file_path.parts:
            continue
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if module.startswith("dayu.host"):
                violations.append((str(file_path), module))
    assert not violations


@pytest.mark.asyncio
async def test_run_input_replay_excludes_display_reasoning() -> None:
    """RunInputBuilder replay 不包含 preview reasoning。"""

    event_store = InMemoryRunEventStore()
    memory_store = FakeInMemoryConversationMemoryStore()
    await event_store.append(
        user_input_accepted_draft(
            run_id="run-reasoning",
            session_id="session-reasoning",
            occurred_at=_utc_now(),
            turn_id="run-reasoning",
            content="上一轮问题",
        )
    )
    await event_store.append(
        RunEventDraft(
            run_id="run-reasoning",
            session_id="session-reasoning",
            kind=RunEventKind.PREVIEW,
            source=RunEventSource.ENGINE,
            type=RunEventType.RUNNER_REASONING_DELTA,
            occurred_at=_utc_now(),
            data=ReasoningDeltaData(iteration_id="iter", delta="secret reasoning"),
            source_engine_event_id="reasoning",
        )
    )
    await event_store.append(
        RunEventDraft(
            run_id="run-reasoning",
            session_id="session-reasoning",
            kind=RunEventKind.PREVIEW,
            source=RunEventSource.ENGINE,
            type=RunEventType.RUNNER_CONTENT_COMPLETED,
            occurred_at=_utc_now(),
            data=ContentCompleteData(
                iteration_id="iter",
                content="display completed",
                reasoning_content="completed reasoning",
                finish_reason=FinishReason.STOP,
            ),
            source_engine_event_id="completed",
        )
    )
    await memory_store.project_run_events(
        await event_store.list_events("run-reasoning", after=None)
    )
    current_event = await event_store.append(
        user_input_accepted_draft(
            run_id="run-current",
            session_id="session-reasoning",
            occurred_at=_utc_now(),
            turn_id="run-current",
            content="当前问题",
        )
    )

    result = DefaultRunInputBuilder().build(
        snapshot=await memory_store.get_snapshot("session-reasoning"),
        current_user_event=current_event,
    )
    system_message = result.run_input.messages[0]

    assert isinstance(system_message, SystemMessage)
    assert "secret reasoning" not in system_message.content
    assert "completed reasoning" not in system_message.content
    assert "display completed" not in system_message.content
