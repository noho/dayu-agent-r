"""人工验证 Host P3 Conversation Memory / RunInputBuilder 路径。

本脚本不访问真实 provider，只使用 fake ``WorkerProxy`` 产出少量
``EngineEvent``。Host 侧仍走真实 ``LocalRunHarness``、
``InMemoryRunEventStore``、``SmokeInMemoryConversationMemoryStore`` 与默认
``RunInputBuilder`` 路径，用于观察：

- 首轮 ``USER_INPUT_ACCEPTED`` 是否先落 EventLog。
- 首轮 canonical final answer / tool fact 是否投影进 memory。
- 第二轮 Engine 实际收到的 ``RunInput`` 是否包含上一轮 memory block。
- Engine stream 正常结束但无 terminal 时，Host 是否追加 owned failure。

默认不打印 delta 流，避免 smoke 输出刷屏。需要观察 Host 关键日志时可用
``--log-level DEBUG``。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

_REPO_ROOT_PARENT_INDEX: int = 1


def _ensure_repo_root_on_path() -> None:
    """确保按文件路径运行脚本时也能导入仓库顶层包。

    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if __package__ not in (None, ""):
        return
    repo_root = Path(__file__).resolve().parents[_REPO_ROOT_PARENT_INDEX]
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


_ensure_repo_root_on_path()

from dayu.contracts import CancellationToken, JsonValue
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RunnerCallOptions,
    RunnerSpec,
    SystemMessage,
    ToolResultAcceptedData,
    UserMessage,
)
from utils._smoke_memory_store import SmokeInMemoryConversationMemoryStore
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._run_harness import LocalRunHarness
from dayu.host._run_input_builder import (
    RunInputBuildTrace,
    RunInputTraceItemKind,
    RunInputTraceStatus,
)
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunEventType,
    RunInput,
    RunOptions,
    RunResult,
    StartRunRequest,
)
from dayu.runtime.log import LogLevel, configure

SmokeCaseName = Literal["conversation", "missing-terminal", "all"]
"""smoke case 名称。"""

_DEFAULT_TIMEOUT_SECONDS: float = 30.0
_DEFAULT_MAX_RETRIES: int = 0
_DEFAULT_MAX_ITERATIONS: int = 2
_SESSION_ID: str = "smoke_host_conversation_memory_session"
_RUN_ID_FIRST: str = "smoke_host_memory_turn_1"
_RUN_ID_SECOND: str = "smoke_host_memory_turn_2"
_RUN_ID_MISSING_TERMINAL: str = "smoke_host_memory_missing_terminal"
_FIRST_USER_TEXT: str = "第一轮：请记录 2025 年收入事实。"
_SECOND_USER_TEXT: str = "第二轮：请基于上一轮继续回答。"
_MISSING_TERMINAL_USER_TEXT: str = "请触发缺失终态 smoke。"
_FIRST_FINAL_TEXT: str = "第一轮最终回答：2025 年收入同比增长。"
_SECOND_FINAL_TEXT: str = "第二轮最终回答：已看见上一轮上下文。"
_TOOL_NAME: str = "financial_fact_lookup"
_TOOL_CALL_ID: str = "tool-call-smoke-memory-1"
_TOOL_FACT_SOURCE_TEXT: str = "FY2025 revenue grew 12%"
_SMOKE_PREFIX: str = "SMOKE"


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """解析后的 smoke 参数。

    :param case_name: smoke case 名称。
    :param log_level: 日志级别。
    """

    case_name: SmokeCaseName
    log_level: LogLevel


@dataclass(slots=True)
class _ScriptedProxy:
    """按 run id 产出 EngineEvent，并捕获 Host 交给 Engine 的请求。

    :param include_tool_fact: 首轮是否产出工具事实事件。
    :param requests: 捕获到的 Engine 请求列表。
    """

    include_tool_fact: bool
    requests: list[StartRunRequest] = field(default_factory=list)

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回脚本化 EngineEvent 流。

        :param request: Host 构造后的 Engine 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.requests.append(request)
        return self._iter_events(request)

    async def _iter_events(
        self,
        request: StartRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """按 run id 异步产出事件。

        :param request: Host 构造后的 Engine 请求。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        events = _success_events(
            request=request,
            include_tool_fact=self.include_tool_fact,
        )
        for event in events:
            await asyncio.sleep(0)
            yield event


@dataclass(slots=True)
class _MissingTerminalProxy:
    """正常结束但不产出 terminal 的 fake WorkerProxy。

    :param requests: 捕获到的 Engine 请求列表。
    """

    requests: list[StartRunRequest] = field(default_factory=list)

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回无 terminal 的空 EngineEvent 流。

        :param request: Host 构造后的 Engine 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 空 EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.requests.append(request)
        return self._empty()

    async def _empty(self) -> AsyncIterator[EngineEvent]:
        """产出空 EngineEvent 流。

        :returns: 空 EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        empty_events: tuple[EngineEvent, ...] = ()
        for event in empty_events:
            yield event


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run manual Host P3 conversation memory smoke checks."
    )
    parser.add_argument(
        "--case",
        choices=("conversation", "missing-terminal", "all"),
        default="all",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=LogLevel.INFO.name,
    )
    namespace = parser.parse_args(list(argv))
    case_name: SmokeCaseName = namespace.case
    log_level_name: str = namespace.log_level
    return SmokeArgs(
        case_name=case_name,
        log_level=LogLevel[log_level_name],
    )


def _utc_now() -> datetime:
    """返回当前 UTC 时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _request(*, run_id: str, user_text: str) -> StartRunRequest:
    """构造 Host StartRunRequest。

    :param run_id: Run id。
    :param user_text: 当前用户输入。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id=_SESSION_ID,
        run_id=run_id,
        input=RunInput(
            messages=(UserMessage(role=AgentMessageRole.USER, content=user_text),)
        ),
        options=RunOptions(
            runner_spec=RunnerSpec(
                provider="smoke",
                model="fake",
                endpoint="https://example.invalid/v1/chat/completions",
                api_key_ref="SMOKE_ONLY",
                headers={},
                supports_tool_calling=True,
                supports_streaming=True,
                supports_stream_usage=False,
                default_timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
                max_retries=_DEFAULT_MAX_RETRIES,
                provider_request=None,
            ),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=True,
            ),
            agent_policy=AgentPolicy(
                max_iterations=_DEFAULT_MAX_ITERATIONS,
                continuation_max_attempts=0,
                allow_tool_calls=True,
            ),
            stream=True,
            disable_tools=False,
            tool_schemas=(),
        ),
    )


def _success_events(
    *,
    request: StartRunRequest,
    include_tool_fact: bool,
) -> tuple[EngineEvent, ...]:
    """构造成功路径 EngineEvent 脚本。

    :param request: Host 构造后的 Engine 请求。
    :param include_tool_fact: 是否在第一轮产出工具事实。
    :returns: EngineEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    if request.run_id == _RUN_ID_FIRST:
        final_text = _FIRST_FINAL_TEXT
        if include_tool_fact:
            return (
                _tool_result_event(request),
                _final_event(request=request, content=final_text, sequence=102),
            )
        return (_final_event(request=request, content=final_text, sequence=101),)
    return (
        _final_event(
            request=request,
            content=_SECOND_FINAL_TEXT,
            sequence=201,
        ),
    )


def _tool_result_event(request: StartRunRequest) -> EngineEvent:
    """构造工具结果已接纳 EngineEvent。

    :param request: Host 构造后的 Engine 请求。
    :returns: 工具结果 EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    value: dict[str, JsonValue] = {
        "metric": "revenue",
        "period": "FY2025",
        "fact": _TOOL_FACT_SOURCE_TEXT,
        "source": "smoke filing page 42",
    }
    return EngineEvent(
        event_id=f"{request.run_id}_engine_tool_result",
        sequence=101,
        occurred_at=_utc_now(),
        session_id=request.session_id,
        run_id=request.run_id,
        type=EngineEventType.TOOL_RESULT_ACCEPTED,
        data=ToolResultAcceptedData(
            iteration_id="iteration-smoke-1",
            tool_call_id=_TOOL_CALL_ID,
            name=_TOOL_NAME,
            index_in_iteration=0,
            outcome=ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value=value,
                    truncation=None,
                    meta=None,
                )
            ),
        ),
        metadata=None,
    )


def _final_event(
    *,
    request: StartRunRequest,
    content: str,
    sequence: int,
) -> EngineEvent:
    """构造 final answer EngineEvent。

    :param request: Host 构造后的 Engine 请求。
    :param content: 最终回答正文。
    :param sequence: Engine event sequence。
    :returns: final answer EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"{request.run_id}_engine_final",
        sequence=sequence,
        occurred_at=_utc_now(),
        session_id=request.session_id,
        run_id=request.run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )


async def _collect_events(events: AsyncIterator[RunEvent]) -> tuple[RunEvent, ...]:
    """收集 RunEvent 流。

    :param events: RunEvent 异步流。
    :returns: RunEvent 元组。
    :raises Exception: 透传事件流异常。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
    return tuple(collected)


async def _run_conversation_case() -> None:
    """运行双轮 conversation memory smoke。

    :returns: 无返回值。
    :raises RuntimeError: smoke 关键观测点缺失时抛出。
    """

    event_store = InMemoryRunEventStore()
    memory_store = SmokeInMemoryConversationMemoryStore()
    proxy = _ScriptedProxy(include_tool_fact=True)
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        event_store=event_store,
        memory_store=memory_store,
    )

    print(f"{_SMOKE_PREFIX} case=conversation session_id={_SESSION_ID}")
    first_events = await _start_and_collect(
        harness=harness,
        request=_request(run_id=_RUN_ID_FIRST, user_text=_FIRST_USER_TEXT),
    )
    first_user_event = _event_of_type(
        events=first_events,
        event_type=RunEventType.USER_INPUT_ACCEPTED,
    )
    first_terminal = _terminal_event(first_events)
    first_tool_event = _event_of_type(
        events=first_events,
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
    )
    first_result = await harness.get_run_result(_RUN_ID_FIRST)
    first_snapshot = await memory_store.get_snapshot(_SESSION_ID)

    print(
        f"{_SMOKE_PREFIX} first.user_input_accepted.cursor="
        f"{first_user_event.cursor.sequence}"
    )
    print(
        f"{_SMOKE_PREFIX} first.terminal type={first_terminal.type.value} "
        f"cursor={first_terminal.cursor.sequence} result={_result_name(first_result)}"
    )
    print(
        f"{_SMOKE_PREFIX} memory.snapshot recent_raw_turns="
        f"{len(first_snapshot.recent_raw_turns)} tool_facts="
        f"{len(first_snapshot.tool_facts)}"
    )

    second_events = await _start_and_collect(
        harness=harness,
        request=_request(run_id=_RUN_ID_SECOND, user_text=_SECOND_USER_TEXT),
    )
    second_user_event = _event_of_type(
        events=second_events,
        event_type=RunEventType.USER_INPUT_ACCEPTED,
    )
    second_request = _captured_request(proxy.requests, index=1)
    second_memory_block = _system_memory_block(second_request)
    second_trace = _trace_for_run(harness, _RUN_ID_SECOND)
    source_cursor_text = f"source_event_cursor={first_tool_event.cursor.sequence}"

    print(
        f"{_SMOKE_PREFIX} second.user_input_accepted.cursor="
        f"{second_user_event.cursor.sequence}"
    )
    print(
        f"{_SMOKE_PREFIX} second.run_input messages="
        f"{len(second_request.input.messages)} roles="
        f"{_message_roles(second_request)}"
    )
    print(
        f"{_SMOKE_PREFIX} second.memory_block_contains "
        f"previous_user={_FIRST_USER_TEXT in second_memory_block} "
        f"previous_final={_FIRST_FINAL_TEXT in second_memory_block} "
        f"tool_fact={_TOOL_FACT_SOURCE_TEXT in second_memory_block} "
        f"source_cursor={source_cursor_text in second_memory_block}"
    )
    print(
        f"{_SMOKE_PREFIX} second.trace total_chars="
        f"{second_trace.total_char_size} total_tokens="
        f"{second_trace.total_token_estimate} items={len(second_trace.items)}"
    )
    for summary in _trace_item_summaries(second_trace):
        print(f"{_SMOKE_PREFIX} second.trace.item_count {summary}")


async def _run_missing_terminal_case() -> None:
    """运行 Engine stream 无 terminal 的 Host-owned failure smoke。

    :returns: 无返回值。
    :raises RuntimeError: smoke 关键观测点缺失时抛出。
    """

    event_store = InMemoryRunEventStore()
    memory_store = SmokeInMemoryConversationMemoryStore()
    proxy = _MissingTerminalProxy()
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        event_store=event_store,
        memory_store=memory_store,
    )

    print(f"{_SMOKE_PREFIX} case=missing-terminal run_id={_RUN_ID_MISSING_TERMINAL}")
    events = await _start_and_collect(
        harness=harness,
        request=_request(
            run_id=_RUN_ID_MISSING_TERMINAL,
            user_text=_MISSING_TERMINAL_USER_TEXT,
        ),
    )
    user_event = _event_of_type(
        events=events,
        event_type=RunEventType.USER_INPUT_ACCEPTED,
    )
    terminal = _terminal_event(events)
    result = await harness.get_run_result(_RUN_ID_MISSING_TERMINAL)
    snapshot = await memory_store.get_snapshot(_SESSION_ID)

    print(
        f"{_SMOKE_PREFIX} missing_terminal.user_input_accepted.cursor="
        f"{user_event.cursor.sequence}"
    )
    print(
        f"{_SMOKE_PREFIX} missing_terminal.terminal type={terminal.type.value} "
        f"cursor={terminal.cursor.sequence} source={terminal.source.value} "
        f"result={_result_name(result)}"
    )
    print(
        f"{_SMOKE_PREFIX} missing_terminal.memory recent_raw_turns="
        f"{len(snapshot.recent_raw_turns)} tool_facts={len(snapshot.tool_facts)} "
        f"terminal_summary_present="
        f"{snapshot.recent_raw_turns[-1].terminal_summary is not None}"
    )


async def _start_and_collect(
    *,
    harness: LocalRunHarness,
    request: StartRunRequest,
) -> tuple[RunEvent, ...]:
    """启动 run 并收集事件。

    :param harness: LocalRunHarness。
    :param request: Host start_run 请求。
    :returns: 收集到的 RunEvent 元组。
    :raises Exception: 透传 start_run 或事件流异常。
    """

    stream = await harness.start_run(request)
    return await _collect_events(stream.events)


def _event_of_type(
    *,
    events: tuple[RunEvent, ...],
    event_type: RunEventType,
) -> RunEvent:
    """从事件序列中取第一条指定类型事件。

    :param events: RunEvent 元组。
    :param event_type: 目标事件类型。
    :returns: 匹配的 RunEvent。
    :raises RuntimeError: 未找到目标事件时抛出。
    """

    for event in events:
        if event.type is event_type:
            return event
    raise RuntimeError(f"event not found: {event_type.value}")


def _terminal_event(events: tuple[RunEvent, ...]) -> RunEvent:
    """返回 smoke 事件序列中的终态事件。

    :param events: RunEvent 元组。
    :returns: 终态 RunEvent。
    :raises RuntimeError: 未找到终态事件时抛出。
    """

    for event in reversed(events):
        if event.type in (
            RunEventType.FINAL_ANSWER,
            RunEventType.RUN_FAILED,
            RunEventType.RUN_CANCELLED,
            RunEventType.RUN_SUSPENDED,
        ):
            return event
    raise RuntimeError("terminal event not found")


def _captured_request(
    requests: Sequence[StartRunRequest],
    *,
    index: int,
) -> StartRunRequest:
    """读取 fake proxy 捕获到的 Engine 请求。

    :param requests: 捕获请求序列。
    :param index: 请求下标。
    :returns: 捕获到的 StartRunRequest。
    :raises RuntimeError: 请求数量不足时抛出。
    """

    if len(requests) <= index:
        raise RuntimeError(f"captured request missing: index={index}")
    return requests[index]


def _system_memory_block(request: StartRunRequest) -> str:
    """读取 Engine 实际收到的 system memory block。

    :param request: fake proxy 捕获到的 Engine 请求。
    :returns: system memory block 文本。
    :raises RuntimeError: 首条消息不是 SystemMessage 时抛出。
    """

    first = request.input.messages[0]
    if not isinstance(first, SystemMessage):
        raise RuntimeError("first RunInput message is not SystemMessage")
    return first.content


def _trace_for_run(
    harness: LocalRunHarness,
    run_id: str,
) -> RunInputBuildTrace:
    """读取 harness 最近缓存的 RunInputBuildTrace。

    :param harness: LocalRunHarness。
    :param run_id: Run id。
    :returns: RunInputBuildTrace。
    :raises RuntimeError: trace 不存在时抛出。
    """

    trace = harness.last_run_input_build_trace_by_run.get(run_id)
    if trace is None:
        raise RuntimeError(f"trace not found: {run_id}")
    return trace


def _trace_item_summaries(trace: RunInputBuildTrace) -> tuple[str, ...]:
    """按 item kind / status 统计 trace item。

    :param trace: RunInput 构造 trace。
    :returns: 统计摘要元组。
    :raises Exception: 不主动抛出异常。
    """

    counts: dict[tuple[RunInputTraceItemKind, RunInputTraceStatus], int] = {}
    for item in trace.items:
        key = (item.item_kind, item.status)
        counts[key] = counts.get(key, 0) + 1
    return tuple(
        f"kind={kind.value} status={status.value} count={count}"
        for (kind, status), count in sorted(
            counts.items(),
            key=lambda entry: (entry[0][0].value, entry[0][1].value),
        )
    )


def _message_roles(request: StartRunRequest) -> str:
    """返回 Engine RunInput 消息角色摘要。

    :param request: fake proxy 捕获到的 Engine 请求。
    :returns: 逗号分隔的消息角色。
    :raises Exception: 不主动抛出异常。
    """

    return ",".join(message.role.value for message in request.input.messages)


def _result_name(result: RunResult | None) -> str:
    """返回 RunResult 类型摘要。

    :param result: RunResult 或 ``None``。
    :returns: 结果类型名。
    :raises Exception: 不主动抛出异常。
    """

    if result is None:
        return "None"
    return type(result).__name__


async def run_smoke(args: SmokeArgs) -> int:
    """运行 Host P3 conversation memory smoke。

    :param args: smoke 参数。
    :returns: 进程退出码。
    :raises Exception: smoke 运行失败时透传异常。
    """

    configure(level=args.log_level)
    print(f"{_SMOKE_PREFIX} log_level={args.log_level.name} case={args.case_name}")
    if args.case_name in ("conversation", "all"):
        await _run_conversation_case()
    if args.case_name in ("missing-terminal", "all"):
        await _run_missing_terminal_case()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """smoke 入口。

    :param argv: 可选参数序列；为 ``None`` 时读取 ``sys.argv``。
    :returns: 进程退出码。
    :raises Exception: smoke 运行失败时透传异常。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(run_smoke(args))


if __name__ == "__main__":
    raise SystemExit(main())
