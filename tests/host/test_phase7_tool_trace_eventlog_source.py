"""P7 S2 EventLog 作为 trace 唯一来源的端到端测试。

覆盖：

- 启用 ``tool_trace_path`` 后，``start_run`` 在 EventLog 中实际写入
  ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` canonical 事实。
- 该事实经 ``ProjectionCoordinator.drain`` 后由 :class:`ToolTraceObserver`
  派生为 JSONL ``iteration_context_snapshot`` record + ``raw_payloads/``
  blob 文件。
- 未配置 ``tool_trace_path`` 时不写入该 fact（保持 P6 行为）。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dayu.contracts import CancellationToken
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RunnerCallOptions,
    RunnerSpec,
    UserMessage,
)
from dayu.host._durable_harness import (
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host.contracts import (
    RunEventType,
    RunInput,
    RunOptions,
    StartRunRequest,
)


_RUN_ID: str = "r1"
_SESSION_ID: str = "s1"
_TERMINAL_TIMEOUT: float = 5.0


@dataclass(frozen=True, slots=True)
class _StubEvents:
    """预定义 EngineEvent 异步流。"""

    events: tuple[EngineEvent, ...]

    def __aiter__(self) -> "_StubIter":
        """返回迭代器。

        :returns: 迭代器实例。
        :raises Exception: 不主动抛出异常。
        """

        return _StubIter(events=self.events)


@dataclass(slots=True)
class _StubIter:
    """``_StubEvents`` 的迭代器。"""

    events: tuple[EngineEvent, ...]
    index: int = 0

    def __aiter__(self) -> "_StubIter":
        """返回自身。

        :returns: 自身。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> EngineEvent:
        """逐条产出事件。

        :returns: 下一个事件。
        :raises StopAsyncIteration: 序列耗尽时抛出。
        """

        if self.index >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self.index]
        self.index += 1
        return event


@dataclass(frozen=True, slots=True)
class _StubProxy:
    """注入预定义 EngineEvent 的 stub WorkerProxy。"""

    events: tuple[EngineEvent, ...]

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回预定义事件流。

        :param request: start_run 请求。
        :param cancellation_token: 取消 token。
        :returns: 异步事件迭代器。
        :raises Exception: 不主动抛出异常。
        """

        _ = request
        _ = cancellation_token
        return _StubEvents(events=self.events).__aiter__()


def _final_event() -> tuple[EngineEvent, ...]:
    """构造单条 final answer engine event。

    :returns: 事件元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        EngineEvent(
            event_id="e1",
            sequence=1,
            occurred_at=datetime.now(tz=timezone.utc),
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content="ok",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        ),
    )


def _build_request() -> StartRunRequest:
    """构造最小 StartRunRequest。

    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        input=RunInput(
            messages=(
                UserMessage(role=AgentMessageRole.USER, content="hi"),
            )
        ),
        options=RunOptions(
            runner_spec=RunnerSpec(
                provider="openai",
                model="m",
                endpoint="https://example.test/v1/chat",
                api_key_ref="K",
                headers={},
                supports_tool_calling=True,
                supports_streaming=True,
                supports_stream_usage=False,
                default_timeout_seconds=10.0,
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
                max_iterations=2,
                continuation_max_attempts=1,
                allow_tool_calls=True,
            ),
            stream=True,
            disable_tools=True,
            tool_schemas=(),
        ),
    )


async def _wait_terminal(bundle: object, run_id: str) -> None:
    """轮询等待 RunResult 出现。

    :param bundle: durable harness bundle。
    :param run_id: Run id。
    :returns: 无返回值。
    :raises RuntimeError: 等待超时时抛出。
    """

    harness = getattr(bundle, "harness")
    deadline = asyncio.get_running_loop().time() + _TERMINAL_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        result = await harness.get_run_result(run_id)
        if result is not None:
            return
        await asyncio.sleep(0.02)
    raise RuntimeError("timeout waiting for terminal")


@pytest.mark.asyncio
async def test_eventlog_records_context_snapshot_when_trace_enabled(
    tmp_path: Path,
) -> None:
    """启用 trace 后 EventLog 出现 ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` 事实。"""

    bundle = build_durable_harness(
        config=DurableHarnessConfig(
            database_path=":memory:",
            tool_trace_path=str(tmp_path / "trace"),
        ),
        proxy=_StubProxy(events=_final_event()),
    )
    try:
        request = _build_request()
        await bundle.harness.start_run(request)
        await _wait_terminal(bundle, _RUN_ID)
        events = await bundle.event_store.list_events(
            run_id=_RUN_ID, after=None
        )
        types = [e.type for e in events]
        assert RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT in types
        # drain 让 trace observer 把 fact 派发为 JSONL + blob。
        await bundle.coordinator.drain()
        trace_root = tmp_path / "trace"
        session_dir = trace_root / "sessions" / _SESSION_ID
        jsonl_files = list(session_dir.glob("tool_calls_*.jsonl"))
        assert len(jsonl_files) >= 1
        all_lines: list[dict[str, object]] = []
        for fp in jsonl_files:
            for line in fp.read_text(encoding="utf-8").splitlines():
                if line:
                    all_lines.append(json.loads(line))
        snapshot_lines = [
            ln for ln in all_lines
            if ln.get("trace_type") == "iteration_context_snapshot"
        ]
        assert len(snapshot_lines) == 1
        # raw_payloads 文件落盘。
        raw_dir = trace_root / "raw_payloads"
        assert raw_dir.exists()
        nested = list(raw_dir.iterdir())
        assert len(nested) == 1
        files = list(nested[0].iterdir())
        assert len(files) == 2
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_eventlog_skips_context_snapshot_when_trace_disabled() -> None:
    """未启用 trace 时 EventLog 不写入 ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT``。"""

    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:"),
        proxy=_StubProxy(events=_final_event()),
    )
    try:
        request = _build_request()
        await bundle.harness.start_run(request)
        await _wait_terminal(bundle, _RUN_ID)
        events = await bundle.event_store.list_events(
            run_id=_RUN_ID, after=None
        )
        types = [e.type for e in events]
        assert RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT not in types
    finally:
        bundle.close()


def test_engine_does_not_import_host_trace_modules() -> None:
    """Engine 包不允许 import Host trace 模块（边界保护）。"""

    import importlib
    import pkgutil

    import dayu.engine as engine_pkg

    forbidden = {
        "dayu.host._tool_trace_projection",
        "dayu.host._tool_trace_jsonl_sink",
        "dayu.host._run_input_context_fact",
    }
    offenders: list[str] = []
    for module_info in pkgutil.walk_packages(
        engine_pkg.__path__, prefix="dayu.engine."
    ):
        module = importlib.import_module(module_info.name)
        for forbidden_name in forbidden:
            if forbidden_name in getattr(module, "__dict__", {}):
                offenders.append(f"{module_info.name} imports {forbidden_name}")
    assert offenders == []
