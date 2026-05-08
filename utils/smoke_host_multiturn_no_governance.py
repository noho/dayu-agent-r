"""Host P5 no-full-governance 多轮 smoke。

本脚本服务人工验证 P5 纵向路径：真实 provider 主路径必须使用
与 utils 下其它 provider smoke 一致的脚本内 ``ProviderCase``，固定运行
``mimo-v2.5-pro-plan``。该路径由模型通过 LLM tool calling 调用公共
``@tool`` 声明的 ``huge_echo``，并经
``ToolExecutor.execute -> ToolRuntimeToolExecutor -> InMemoryToolRuntime``
产生截断、cursor 与补读事实。缺少 API key 或 provider case 能力不满足时
返回清晰失败，不能把 fake case 当作真实 provider 成功。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypeAlias, TypeVar, cast

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

from dayu.contracts import (  # noqa: E402
    CancellationToken,
    FRAMEWORK_FETCH_MORE_TOOL_NAME,
    JsonValue,
    ToolBundle,
    ToolCallRequest,
    ToolCompletedOutcome,
    ToolExecutionRequest,
    ToolExecutor,
    ToolExecutionOutcome,
    ToolParametersSchema,
    ToolResultSuccess,
    ToolSchema,
    ToolTruncateSpec,
    framework_fetch_more_tool_schema,
    tool,
)
import dayu.engine.agent as agent_module  # noqa: E402
from dayu.engine import (  # noqa: E402
    AgentMessage,
    AgentMessageRole,
    AgentPolicy,
    AgentRunRequest,
    AssistantMessage,
    ContentCompleteData,
    AsyncRunner,
    ContextBudgetSnapshot,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventData,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    MimoThinkingExtension,
    ProviderRequestExtension,
    ReasoningDeltaData,
    RunFailedData,
    RunnerCallOptions,
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerSpec,
    RunnerToolCallsCompletedData,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dayu.host import (  # noqa: E402
    RunEvent,
    RunEventType,
    RunInput,
    RunOptions,
    RunSucceededResult,
    StartRunRequest,
    ToolFetchMoreFailedResult,
    ToolFetchMoreHandleRequest,
    ToolFetchMoreHandleSucceededResult,
    ToolFetchMoreRequest,
    ToolFetchMoreSucceededResult,
)
from dayu.host._conversation_memory import (  # noqa: E402
    ConversationMemoryPatch,
    ConversationMemorySnapshot,
    ConversationMemoryStore,
    ConversationPinnedState,
    InMemoryConversationMemoryStore,
    TaskFrame,
)
from dayu.host._event_store import InMemoryRunEventStore  # noqa: E402
from dayu.host._proxy import LocalProxy, WorkerProxy  # noqa: E402
from dayu.host._run_harness import LocalRunHarness  # noqa: E402
from dayu.host._tool_runtime import (  # noqa: E402
    InMemoryToolRuntime,
    ToolRuntimeToolExecutor,
)
from dayu.host._worker import EngineWorker  # noqa: E402
from dayu.host.contracts import (  # noqa: E402
    HostContextCompactCompletedData,
    HostContextOverflowObservedData,
    ToolCursorIssuedData,
    ToolFetchMoreCompletedData,
    ToolResultTruncatedData,
)
from dayu.runtime.log import LogLevel, configure  # noqa: E402

_LOGGER: logging.Logger = logging.getLogger("smoke.host.phase5")
_MODEL_CASE_NAME: str = "mimo-v2.5-pro-plan"
_MIMO_PROVIDER: str = "mimo"
_MIMO_ENV_VAR: str = "MIMO_PLAN_API_KEY"
_MIMO_ENDPOINT: str = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
_MIMO_MODEL: str = "mimo-v2.5-pro"
_DEFAULT_TIMEOUT_SECONDS: float = 3600.0
_DEFAULT_MAX_RETRIES: int = 0
_DEFAULT_MAX_TOKENS: int = 512
_STREAM_IDLE_TIMEOUT_SECONDS: float = 120.0
_STREAM_IDLE_HEARTBEAT_SECONDS: float = 10.0
_PROVIDER_CASE_SOURCE: str = "hardcoded_provider_case"
_MIMO_THINKING_SOURCE: str = (
    "intentional_hardcoded_provider_case_not_llm_models_json"
)
_HUGE_ECHO_TOOL_CALL_ID: str = "huge_echo_call_1"
_FETCH_MORE_TOOL_CALL_ID: str = "fetch_more_call_1"
_HUGE_ECHO_DEFAULT_REPEAT: int = 96
_HUGE_ECHO_MAX_REPEAT: int = 256
_HUGE_ECHO_TRUNCATE_CHARS: int = 240
_HUGE_ECHO_FETCH_LIMIT: int = 120
_WAIT_SPIN_LIMIT: int = 100
_WAIT_SLEEP_SECONDS: float = 0.01
_SMOKE_PREFIX: str = "SMOKE"
_REAL_PROVIDER_CASE_NAME: str = "real-provider"
_THINKING_SOURCE_AGGREGATE: Literal["aggregate"] = "aggregate"
_THINKING_SOURCE_DELTA: Literal["delta"] = "delta"
_FINAL_ANSWER_PREVIEW_CHARS: int = 320
_TEXT_TRUNCATED_SUFFIX: str = "...[truncated]"
_PROMPT: str = (
    "这是工具调用能力测试，不要直接回答。你必须调用且只调用 huge_echo 工具，"
    "参数 text 使用 phase5-host-smoke，repeat 使用 96。拿到工具结果后，"
    "如果工具结果里的 truncation.next_action 是 fetch_more，你必须再调用 "
    "fetch_more，并原样使用 truncation.fetch_more_args。拿到 fetch_more 返回的"
    "下一段后，用一句中文说明你已经调用了 huge_echo 和 fetch_more。"
)
_T = TypeVar("_T")
_RunnerFactory = Callable[[AgentRunRequest], AsyncRunner]
_RunnerScriptFactory: TypeAlias = Callable[
    [Sequence[AgentMessage], Sequence[ToolSchema]], tuple[RunnerEvent, ...]
]
_RunnerScript: TypeAlias = tuple[RunnerEvent, ...] | _RunnerScriptFactory


@dataclass(frozen=True, slots=True)
class ProviderCase:
    """真实 provider smoke case。

    :param name: 模型 case 名。
    :param provider: provider 名称。
    :param endpoint: endpoint URL。
    :param model: 模型名。
    :param env_var: API key 环境变量名。
    :param supports_stream: 是否支持流式。
    :param supports_tool_calling: 是否支持工具调用。
    :param supports_stream_usage: 是否支持 stream usage。
    :param timeout_seconds: 默认超时秒数。
    :param stream_idle_timeout_seconds: 流空闲超时秒数。
    :param stream_idle_heartbeat_seconds: 流空闲心跳秒数。
    :param provider_request: provider 请求扩展。
    """

    name: str
    provider: str
    endpoint: str
    model: str
    env_var: str
    supports_stream: bool
    supports_tool_calling: bool
    supports_stream_usage: bool
    timeout_seconds: float
    stream_idle_timeout_seconds: float | None
    stream_idle_heartbeat_seconds: float | None
    provider_request: ProviderRequestExtension | None


# P5 smoke 沿用 utils/smoke_async_agent_providers.py 的硬编码 ProviderCase
# 范式：MimoThinkingExtension(enabled=True) 是本 smoke case 的有意选择，
# 不读取 dayu/config/llm_models.json 或 workspace/config 作为真源。
MIMO_PLAN_PROVIDER_CASE: ProviderCase = ProviderCase(
    name=_MODEL_CASE_NAME,
    provider=_MIMO_PROVIDER,
    endpoint=_MIMO_ENDPOINT,
    model=_MIMO_MODEL,
    env_var=_MIMO_ENV_VAR,
    supports_stream=True,
    supports_tool_calling=True,
    supports_stream_usage=False,
    timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
    stream_idle_timeout_seconds=_STREAM_IDLE_TIMEOUT_SECONDS,
    stream_idle_heartbeat_seconds=_STREAM_IDLE_HEARTBEAT_SECONDS,
    provider_request=MimoThinkingExtension(enabled=True),
)


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """命令行参数。

    :param case: smoke case。
    :param log_level: 日志级别。
    :param timeout_seconds: provider 请求超时秒数。
    :param thinking: 是否在终端回显 real-provider 返回的 thinking / reasoning。
    """

    case: Literal["all", "real-provider", "compact-retry"]
    log_level: str
    timeout_seconds: float
    thinking: bool


@dataclass(slots=True)
class ToolExecutionProbe:
    """P5 工具执行链路观测器。

    :param gate_after_runtime: 是否在 ToolRuntime 产生 facts 后暂停。
    :param gate_tool_name: 只暂停指定工具名；为 ``None`` 表示所有工具。
    :param execute_called: Engine 是否调用过外层 ToolExecutor。
    :param runtime_completed: ToolRuntimeToolExecutor 是否完成调用。
    :param tool_names: 实际工具名序列。
    :param after_runtime_event: ToolRuntime 完成后触发的事件。
    :param release_event: 释放 Engine 后续 LLM final 的事件。
    """

    gate_after_runtime: bool
    gate_tool_name: str | None = None
    execute_called: bool = False
    runtime_completed: bool = False
    tool_names: list[str] = field(default_factory=list)
    after_runtime_event: asyncio.Event = field(default_factory=asyncio.Event)
    release_event: asyncio.Event = field(default_factory=asyncio.Event)

    async def wait_after_runtime(self) -> None:
        """等待 ToolRuntime 产生截断 / cursor facts。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        await self.after_runtime_event.wait()

    def release(self) -> None:
        """释放 gated executor。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.release_event.set()


@dataclass(slots=True)
class _RealProviderRunOutput:
    """real-provider 单 Run 人工观察输出器。

    :param run_index: smoke 中的 run 序号，从 1 开始。
    :param emitted_delta: 是否已输出 reasoning delta。
    :param emitted_aggregate: 是否已输出 aggregate fallback。
    :param thinking_block_open: thinking delta 文本块是否已打开。
    """

    run_index: int
    emitted_delta: bool = False
    emitted_aggregate: bool = False
    thinking_block_open: bool = False

    def observe(self, event: RunEvent) -> None:
        """按事件到达顺序输出可人工观察的 provider 文本。

        :param event: Host ``RunEvent``。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        data = event.data
        if (
            event.type is RunEventType.RUNNER_REASONING_DELTA
            and isinstance(data, ReasoningDeltaData)
            and data.delta
        ):
            self._print_delta(
                text=data.delta,
            )
            return
        if (
            event.type is RunEventType.RUNNER_CONTENT_COMPLETED
            and isinstance(data, ContentCompleteData)
            and data.reasoning_content
            and not self.emitted_delta
            and not self.emitted_aggregate
        ):
            self._print_aggregate(
                cursor=event.cursor.sequence,
                text=data.reasoning_content,
            )
            return
        if event.type is RunEventType.FINAL_ANSWER and isinstance(
            data, FinalAnswerData
        ):
            self._print_final_answer(
                cursor=event.cursor.sequence,
                text=data.content,
            )

    def finish(self) -> None:
        """结束当前 run 的人工观察输出块。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._close_thinking_block()

    def _print_delta(self, *, text: str) -> None:
        """输出一个 provider reasoning delta。

        :param text: reasoning delta 文本。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        if not self.thinking_block_open:
            print()
            print(
                f"thinking_delta run_index={self.run_index} "
                f"source={_THINKING_SOURCE_DELTA}"
            )
            self.thinking_block_open = True
        print(text, end="", flush=True)
        self.emitted_delta = True

    def _print_aggregate(self, *, cursor: int, text: str) -> None:
        """输出没有 delta 时的 aggregate reasoning fallback。

        :param cursor: Host ``RunEvent`` cursor sequence。
        :param text: aggregate reasoning 文本。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        print()
        print(
            f"thinking_delta run_index={self.run_index} "
            f"source={_THINKING_SOURCE_AGGREGATE} "
            f"fallback=no_delta cursor={cursor} chars={len(text)}"
        )
        print(text)
        print()
        self.emitted_aggregate = True

    def _print_final_answer(self, *, cursor: int, text: str) -> None:
        """输出 final answer 前缀预览。

        :param cursor: Host ``RunEvent`` cursor sequence。
        :param text: final answer 完整文本。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._close_thinking_block()
        preview = _preview_text(text, _FINAL_ANSWER_PREVIEW_CHARS)
        print()
        print(
            f"final_answer run_index={self.run_index} cursor={cursor} "
            f"chars={len(text)} preview_chars={len(preview)}"
        )
        print(preview)
        print()

    def _close_thinking_block(self) -> None:
        """关闭已打开的 delta 输出块。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        if self.thinking_block_open:
            print()
            print()
            self.thinking_block_open = False


@dataclass(slots=True)
class GatedToolExecutor:
    """包裹 ToolRuntimeToolExecutor 的 smoke/test executor。

    :param delegate: 真实 ToolRuntimeToolExecutor。
    :param probe: 调用链路观测器。
    """

    delegate: ToolExecutor
    probe: ToolExecutionProbe

    async def execute(
        self, request: ToolExecutionRequest
    ) -> ToolExecutionOutcome:
        """执行工具并在 ToolRuntime facts 产生后按需暂停。

        :param request: 工具执行请求。
        :returns: 工具执行 outcome。
        :raises Exception: 透传 delegate 异常。
        """

        self.probe.execute_called = True
        self.probe.tool_names.append(request.call.name)
        outcome = await self.delegate.execute(request)
        self.probe.runtime_completed = True
        self.probe.after_runtime_event.set()
        should_gate = self.probe.gate_after_runtime and (
            self.probe.gate_tool_name is None
            or self.probe.gate_tool_name == request.call.name
        )
        if should_gate:
            await self.probe.release_event.wait()
        return outcome


@dataclass(slots=True)
class SeededMemoryStore:
    """带 P5 stable layer 种子的内存 memory store。

    :param pinned_state: 测试 / smoke 预置 pinned state。
    :param task_frame: 测试 / smoke 预置 task frame。
    :param delegate: 真实内存投影 store。
    """

    pinned_state: ConversationPinnedState
    task_frame: TaskFrame
    delegate: InMemoryConversationMemoryStore = field(
        default_factory=InMemoryConversationMemoryStore
    )

    async def project_run_events(self, events: tuple[RunEvent, ...]) -> None:
        """投影 RunEvent 到 delegate。

        :param events: 同一 run 的事件。
        :returns: 无返回值。
        :raises Exception: delegate 投影失败时透传。
        """

        await self.delegate.project_run_events(events)

    async def get_snapshot(self, session_id: str) -> ConversationMemorySnapshot:
        """读取带 stable layer 的 snapshot。

        :param session_id: 会话 id。
        :returns: memory snapshot。
        :raises Exception: delegate 读取失败时透传。
        """

        snapshot = await self.delegate.get_snapshot(session_id)
        return replace(
            snapshot,
            pinned_state=self.pinned_state,
            task_frame=self.task_frame,
        )

    async def apply_patch(self, patch: ConversationMemoryPatch) -> None:
        """应用 internal memory patch。

        :param patch: memory patch。
        :returns: 无返回值。
        :raises ValueError: patch 非 delegate 支持范围时透传。
        """

        await self.delegate.apply_patch(patch)


@dataclass(slots=True)
class _OverflowThenSuccessProxy:
    """compact retry 辅助 case 使用的 scripted WorkerProxy。"""

    requests: list[StartRunRequest] = field(default_factory=list)

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """第一次 attempt 产出 overflow，第二次 attempt 产出 final。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.requests.append(request)
        _ = cancellation_token
        if len(self.requests) == 1:
            return _iter_engine_events(
                (
                    _engine_event(
                        sequence=0,
                        session_id=request.session_id,
                        run_id=request.run_id,
                        event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
                        data=ContextCompactionRequestedData(
                            iteration_id="iter-0",
                            budget_state=ContextBudgetSnapshot(
                                prompt_tokens=0,
                                completion_tokens=0,
                                total_tokens=0,
                            ),
                            reason="context_compaction_required",
                        ),
                    ),
                    _engine_event(
                        sequence=1,
                        session_id=request.session_id,
                        run_id=request.run_id,
                        event_type=EngineEventType.RUN_FAILED,
                        data=RunFailedData(
                            error_code="context_compaction_required",
                            message="provider context overflow",
                            recoverable=True,
                        ),
                    ),
                )
            )
        return _iter_engine_events(
            (
                _engine_event(
                    sequence=2,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=FinalAnswerData(
                        content="compact retry completed",
                        filtered=False,
                        degraded=False,
                        finish_reason=FinishReason.STOP,
                    ),
                ),
            )
        )


@dataclass(slots=True)
class _ScriptedRunner:
    """fake provider runner，仅模拟 provider 输出。"""

    scripts: tuple[_RunnerScript, ...]
    requests: list[AgentRunRequest] = field(default_factory=list)
    call_count: int = 0
    messages_seen: list[tuple[AgentMessage, ...]] = field(default_factory=list)
    tools_seen: list[tuple[ToolSchema, ...]] = field(default_factory=list)

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
    ) -> AsyncIterator[RunnerEvent]:
        """返回脚本化 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用选项。
        :param tools: LLM-facing 工具 schema。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        _ = options
        self.messages_seen.append(tuple(messages))
        self.tools_seen.append(tuple(tools))
        index = self.call_count
        self.call_count += 1
        if index >= len(self.scripts):
            return _iter_runner_events(())
        script = self.scripts[index]
        if callable(script):
            return _iter_runner_events(script(messages, tools))
        return _iter_runner_events(script)

    def is_supports_tool_calling(self) -> bool:
        """返回是否支持工具调用。

        :returns: 始终返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    async def close(self) -> None:
        """关闭 fake runner。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        return None


@contextmanager
def _patch_agent_runner_factory(factory: _RunnerFactory) -> Iterator[None]:
    """临时替换 Engine Agent 的 runner 构造函数并集中恢复。

    :param factory: 测试 / smoke 注入的 runner factory。
    :returns: 上下文管理器迭代器。
    :raises Exception: 上下文内异常会在恢复后透传。
    """

    original_build_runner = agent_module._build_runner
    agent_module._build_runner = factory
    try:
        yield
    finally:
        agent_module._build_runner = original_build_runner


async def _huge_echo_execute(
    request: ToolExecutionRequest,
) -> ToolExecutionOutcome:
    """执行 P5 huge_echo smoke 工具。

    :param request: 工具执行请求。
    :returns: 成功 outcome，值为足够触发截断的长文本。
    :raises Exception: 不主动抛出异常。
    """

    text_value = request.call.arguments.get("text")
    repeat_value = request.call.arguments.get("repeat")
    text = text_value if isinstance(text_value, str) else "phase5-host-smoke"
    repeat = repeat_value if isinstance(repeat_value, int) else _HUGE_ECHO_DEFAULT_REPEAT
    repeat = max(1, min(repeat, _HUGE_ECHO_MAX_REPEAT))
    lines = tuple(f"{index:03d}:{text}" for index in range(repeat))
    return ToolCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value="\n".join(lines),
            truncation=None,
            meta=None,
        )
    )


HUGE_ECHO_DEFINITION = tool(
    name="huge_echo",
    description=(
        "Return a deliberately large echo string for Host P5 smoke truncation."
    ),
    parameters=ToolParametersSchema(
        type="object",
        properties={
            "text": {"type": "string"},
            "repeat": {"type": "integer", "minimum": 1},
        },
        required=("text",),
        additional_properties=False,
    ),
    truncate=ToolTruncateSpec(
        enabled=True,
        strategy="text_chars",
        limits={"max_chars": _HUGE_ECHO_TRUNCATE_CHARS},
        target_field=None,
        field_path=None,
        ttl_seconds=300,
    ),
    display_name="Huge Echo",
    tags=("phase5", "smoke"),
)(_huge_echo_execute)


def huge_echo_bundle() -> ToolBundle:
    """返回 P5 huge_echo 工具 bundle。

    :returns: 只包含 huge_echo 的工具 bundle。
    :raises Exception: 不主动抛出异常。
    """

    return ToolBundle(definitions=(HUGE_ECHO_DEFINITION,))


def phase5_tool_schemas() -> tuple[ToolSchema, ...]:
    """返回 P5 主路径暴露给模型的业务工具与 framework 工具 schema。

    :returns: ``huge_echo`` 与 framework ``fetch_more`` schema。
    :raises Exception: 不主动抛出异常。
    """

    return (
        *huge_echo_bundle().to_tool_schemas(),
        framework_fetch_more_tool_schema(),
    )


def build_huge_echo_harness(
    *,
    probe: ToolExecutionProbe,
    memory_store: ConversationMemoryStore | None = None,
    proxy: WorkerProxy | None = None,
) -> LocalRunHarness:
    """构造使用真实 ToolRuntime 的 P5 harness。

    :param probe: 工具执行观测器。
    :param memory_store: 可选 memory store。
    :param proxy: 可选 WorkerProxy；未提供时使用真实 EngineWorker。
    :returns: LocalRunHarness。
    :raises Exception: 不主动抛出异常。
    """

    bundle = huge_echo_bundle()
    event_store = InMemoryRunEventStore()
    business_executor = HUGE_ECHO_DEFINITION.executor
    runtime = InMemoryToolRuntime(
        executor=business_executor,
        event_store=event_store,
        truncate_specs=bundle.truncate_specs(),
    )
    runtime_executor = ToolRuntimeToolExecutor(runtime)
    gated_executor = GatedToolExecutor(
        delegate=runtime_executor,
        probe=probe,
    )
    resolved_proxy = proxy
    if resolved_proxy is None:
        resolved_proxy = LocalProxy(worker=EngineWorker(gated_executor))
    return LocalRunHarness(
        proxy=resolved_proxy,
        event_store=event_store,
        tool_runtime=runtime,
        memory_store=memory_store or _seeded_memory_store(),
    )


def build_start_request(
    *,
    session_id: str,
    run_id: str,
    prompt: str,
    runner_spec: RunnerSpec,
    stream: bool,
    tool_schemas: tuple[ToolSchema, ...],
    caller_system_messages: tuple[SystemMessage, ...] = (),
) -> StartRunRequest:
    """构造 Host StartRunRequest。

    :param session_id: session id。
    :param run_id: run id。
    :param prompt: 当前用户问题。
    :param runner_spec: Runner 规约。
    :param stream: 是否流式。
    :param tool_schemas: Engine / Runner 可见工具 schema。
    :param caller_system_messages: 调用方 system prompt。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id=session_id,
        run_id=run_id,
        input=RunInput(
            messages=(
                *caller_system_messages,
                UserMessage(role=AgentMessageRole.USER, content=prompt),
            )
        ),
        options=RunOptions(
            runner_spec=runner_spec,
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=_DEFAULT_MAX_TOKENS,
                top_p=None,
                stream=stream,
            ),
            agent_policy=AgentPolicy(
                max_iterations=6,
                continuation_max_attempts=1,
                allow_tool_calls=True,
            ),
            stream=stream,
            disable_tools=False,
            tool_schemas=tool_schemas,
        ),
    )


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的参数。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run Host P5 no-full-governance smoke."
    )
    parser.add_argument(
        "--case",
        choices=("all", "real-provider", "compact-retry"),
        default="all",
    )
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=_DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        default=False,
        help=(
            "Stream real-provider reasoning deltas while consuming RunEvents, "
            "falling back to aggregate reasoning when no delta exists. "
            "Thinking and final answer are printed as separated observation "
            "blocks. Disabled by default."
        ),
    )
    namespace = parser.parse_args(list(argv))
    case: Literal["all", "real-provider", "compact-retry"] = namespace.case
    return SmokeArgs(
        case=case,
        log_level=str(namespace.log_level),
        timeout_seconds=float(namespace.timeout_seconds),
        thinking=bool(namespace.thinking),
    )


def build_runner_spec_from_case(
    *, case: ProviderCase, api_key: str
) -> RunnerSpec:
    """根据 provider case 构造 RunnerSpec。

    :param case: provider smoke case。
    :param api_key: API key 明文，只进入请求头。
    :returns: RunnerSpec。
    :raises Exception: RunnerSpec 字段非法时透传。
    """

    return RunnerSpec(
        provider=case.provider,
        model=case.model,
        endpoint=case.endpoint,
        api_key_ref=case.env_var,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        supports_tool_calling=case.supports_tool_calling,
        supports_streaming=case.supports_stream,
        supports_stream_usage=case.supports_stream_usage,
        default_timeout_seconds=case.timeout_seconds,
        max_retries=_DEFAULT_MAX_RETRIES,
        provider_request=case.provider_request,
        stream_idle_timeout_seconds=case.stream_idle_timeout_seconds,
        stream_idle_heartbeat_seconds=case.stream_idle_heartbeat_seconds,
    )


async def run_real_provider_case(args: SmokeArgs) -> bool:
    """运行真实 provider 主 smoke。

    :param args: smoke 参数。
    :returns: 成功返回 ``True``，失败返回 ``False``。
    :raises Exception: 未预期异常由调用方处理。
    """

    case = MIMO_PLAN_PROVIDER_CASE
    api_key = os.environ.get(case.env_var)
    if not api_key:
        _print_provider_summary(case=case, request_sent=False)
        print(
            f"{_SMOKE_PREFIX} real_provider=failed reason=missing_api_key "
            f"env={case.env_var}"
        )
        return False
    if not case.supports_tool_calling or case.endpoint == "" or case.model == "":
        _print_provider_summary(case=case, request_sent=False)
        print(f"{_SMOKE_PREFIX} real_provider=failed reason=missing_capability")
        return False
    _print_provider_summary(case=case, request_sent=True)
    runner_spec = build_runner_spec_from_case(case=case, api_key=api_key)
    return await _run_tool_multiturn_case(
        runner_spec=runner_spec,
        stream=case.supports_stream,
        case_name="real-provider",
        prompt=_PROMPT,
        timeout_seconds=args.timeout_seconds,
        thinking=args.thinking,
    )


async def run_compact_retry_case() -> bool:
    """运行 compact retry 辅助 smoke。

    :returns: 成功返回 ``True``。
    :raises Exception: 未预期异常由调用方处理。
    """

    memory_store = _seeded_memory_store()
    fake_spec = _fake_runner_spec()
    fake_runner = _ScriptedRunner(
        scripts=(
            _tool_call_script(),
            _fetch_more_script_from_hint,
            _final_script("fake provider observed huge_echo"),
            _final_script("run 2 observed memory"),
        )
    )
    def _fake_build_runner(request: AgentRunRequest) -> AsyncRunner:
        """返回 fake provider runner。

        :param request: Engine AgentRunRequest。
        :returns: fake runner。
        :raises Exception: 不主动抛出异常。
        """

        _ = request
        return fake_runner

    with _patch_agent_runner_factory(_fake_build_runner):
        ok = await _run_tool_multiturn_case(
            runner_spec=fake_spec,
            stream=True,
            case_name="fake-provider",
            prompt="请调用 huge_echo。",
            timeout_seconds=30.0,
            memory_store=memory_store,
            thinking=False,
        )
    if not ok:
        return False
    proxy = _OverflowThenSuccessProxy()
    compact_harness = LocalRunHarness(proxy=proxy, memory_store=memory_store)
    request = build_start_request(
        session_id="phase5-session",
        run_id="phase5-compact-run",
        prompt="请基于已有工具事实回答，并触发 compact retry。",
        runner_spec=fake_spec,
        stream=True,
        tool_schemas=(),
        caller_system_messages=(
            SystemMessage(
                role=AgentMessageRole.SYSTEM,
                content="caller system prompt for compact",
            ),
        ),
    )
    stream = await compact_harness.start_run(request)
    events = await _collect_events(stream.events)
    user_count = sum(
        1 for event in events if event.type is RunEventType.USER_INPUT_ACCEPTED
    )
    completed = _first_data(events, HostContextCompactCompletedData)
    overflow = _first_data(events, HostContextOverflowObservedData)
    retry_input = proxy.requests[1].input.messages if len(proxy.requests) > 1 else ()
    retry_text = _messages_to_text(retry_input)
    terminal = await compact_harness.get_run_result("phase5-compact-run")
    terminal_type = type(terminal).__name__ if terminal is not None else "none"
    print(
        f"{_SMOKE_PREFIX} case=compact-retry run_id=phase5-compact-run "
        f"user_input_accepted_count={user_count} attempts={len(proxy.requests)}"
    )
    if overflow is not None:
        print(
            f"{_SMOKE_PREFIX} compact overflow_observed "
            f"recoverable={overflow.recoverable}"
        )
    if completed is not None:
        print(
            f"{_SMOKE_PREFIX} compact completed "
            f"before_tokens={completed.before_token_estimate} "
            f"after_tokens={completed.after_token_estimate} "
            f"dropped={completed.dropped_item_count}"
        )
    print(
        f"{_SMOKE_PREFIX} compact retry_input contains_system="
        f"{'caller system prompt' in retry_text} contains_current_user="
        f"{'触发 compact retry' in retry_text} contains_pinned_state="
        f"{'phase5 pinned goal' in retry_text} contains_tool_fact="
        f"{HUGE_ECHO_DEFINITION.name in retry_text} contains_source_cursor="
        f"{'source_event_cursor=' in retry_text}"
    )
    print(f"{_SMOKE_PREFIX} compact terminal type={terminal_type}")
    return (
        user_count == 1
        and len(proxy.requests) == 2
        and completed is not None
        and "phase5 pinned goal" in retry_text
        and HUGE_ECHO_DEFINITION.name in retry_text
    )


async def _run_tool_multiturn_case(
    *,
    runner_spec: RunnerSpec,
    stream: bool,
    case_name: str,
    prompt: str,
    timeout_seconds: float,
    memory_store: ConversationMemoryStore | None = None,
    thinking: bool = False,
) -> bool:
    """运行两个顺序 Run 的工具截断 / 补读 / memory 接续 case。

    :param runner_spec: RunnerSpec。
    :param stream: 是否启用流式。
    :param case_name: 输出 case 名。
    :param prompt: run 1 prompt。
    :param timeout_seconds: 超时秒数；当前只用于摘要占位。
    :param memory_store: 可选 memory store。
    :param thinking: 是否输出 real-provider thinking / reasoning 诊断。
    :returns: 成功返回 ``True``。
    :raises Exception: 未预期异常透传。
    """

    _ = timeout_seconds
    probe = ToolExecutionProbe(gate_after_runtime=False)
    harness = build_huge_echo_harness(
        probe=probe,
        memory_store=memory_store or _seeded_memory_store(),
    )
    request = build_start_request(
        session_id="phase5-session",
        run_id=f"phase5-{case_name}-run-1",
        prompt=prompt,
        runner_spec=runner_spec,
        stream=stream,
        tool_schemas=phase5_tool_schemas(),
    )
    stream_result = await harness.start_run(request)
    event_iter = stream_result.events
    first_output = _real_provider_run_output(
        run_index=1,
        enabled=thinking and case_name == _REAL_PROVIDER_CASE_NAME,
    )
    try:
        first_events = await _collect_events(event_iter, output=first_output)
    except RuntimeError as exc:
        print(
            f"{_SMOKE_PREFIX} case={case_name} failed "
            f"reason=model_did_not_call_huge_echo detail={str(exc)}"
        )
        probe.release()
        return False
    cursor_event = _last_data(first_events, ToolCursorIssuedData)
    truncated = _last_data(first_events, ToolResultTruncatedData)
    if cursor_event is None or truncated is None:
        print(
            f"{_SMOKE_PREFIX} case={case_name} failed "
            f"reason=model_did_not_call_huge_echo"
        )
        return False
    fetch_completed = _last_data(first_events, ToolFetchMoreCompletedData)
    if fetch_completed is None:
        print(
            f"{_SMOKE_PREFIX} case={case_name} failed "
            f"reason=model_did_not_call_fetch_more"
        )
        return False
    _finish_real_provider_run_output(first_output)
    terminal = await _wait_for_result(
        harness=harness,
        run_id=f"phase5-{case_name}-run-1",
    )
    await _wait_for_memory_projection(
        harness=harness,
        session_id="phase5-session",
    )
    second_request = build_start_request(
        session_id="phase5-session",
        run_id=f"phase5-{case_name}-run-2",
        prompt="Run 2：请说明 previous run 是否调用了 huge_echo。",
        runner_spec=runner_spec,
        stream=stream,
        tool_schemas=(),
    )
    second_stream = await harness.start_run(second_request)
    second_output = _real_provider_run_output(
        run_index=2,
        enabled=thinking and case_name == _REAL_PROVIDER_CASE_NAME,
    )
    second_events = await _collect_events(
        second_stream.events,
        output=second_output,
    )
    _finish_real_provider_run_output(second_output)
    await _wait_for_result(
        harness=harness,
        run_id=f"phase5-{case_name}-run-2",
    )
    trace = harness.last_run_input_build_trace_by_run[
        f"phase5-{case_name}-run-2"
    ]
    actual_second_input = _messages_to_text(
        _last_built_messages_from_trace_source(harness, f"phase5-{case_name}-run-2")
    )
    terminal_cursor = terminal.terminal_event_cursor.sequence
    print(
        f"{_SMOKE_PREFIX} case={case_name} run_index=1 "
        f"user_input_accepted.cursor=0 terminal_cursor={terminal_cursor}"
    )
    print(
        f"{_SMOKE_PREFIX} case={case_name} run_index=1 llm_tool_call "
        f"tool={HUGE_ECHO_DEFINITION.name} via_engine_tool_loop="
        f"{RunEventType.TOOL_CALL_REQUESTED in {event.type for event in first_events}} "
        f"executor_execute_called={probe.execute_called} "
        f"tool_runtime_completed={probe.runtime_completed} "
        f"observed_tools={','.join(probe.tool_names)}"
    )
    print(
        f"{_SMOKE_PREFIX} case={case_name} run_index=1 tool_truncated "
        f"event_cursor={_event_cursor_for_data(first_events, truncated)} "
        f"cursor_issued={cursor_event.cursor_fingerprint}"
    )
    fetch_event_cursor = _event_cursor_for_data(first_events, fetch_completed)
    print(
        f"{_SMOKE_PREFIX} case={case_name} fetch_more pre_terminal "
        f"completed has_more={fetch_completed.has_more} "
        f"event_cursor={fetch_event_cursor} "
        f"before_terminal={fetch_event_cursor is not None and fetch_event_cursor < terminal_cursor}"
    )
    print(
        f"{_SMOKE_PREFIX} case={case_name} run_index=2 "
        f"user_input_accepted.cursor={second_events[0].cursor.sequence}"
    )
    print(
        f"{_SMOKE_PREFIX} case={case_name} run_index=2 run_input "
        f"contains_previous_user={'phase5-host-smoke' in actual_second_input} "
        f"contains_previous_final={'huge_echo' in actual_second_input} "
        f"contains_tool_fact={HUGE_ECHO_DEFINITION.name in actual_second_input} "
        f"contains_source_cursor={'source_event_cursor=' in actual_second_input} "
        f"contains_pinned_state={'phase5 pinned goal' in actual_second_input} "
        f"contains_task_frame={'phase5-topic' in actual_second_input} "
        f"trace_items={len(trace.items)}"
    )
    return (
        isinstance(terminal, RunSucceededResult)
        and probe.execute_called
        and probe.runtime_completed
        and HUGE_ECHO_DEFINITION.name in probe.tool_names
        and FRAMEWORK_FETCH_MORE_TOOL_NAME in probe.tool_names
        and fetch_completed is not None
        and fetch_event_cursor is not None
        and fetch_event_cursor < terminal_cursor
        and HUGE_ECHO_DEFINITION.name in actual_second_input
        and "source_event_cursor=" in actual_second_input
    )


def _seeded_memory_store() -> SeededMemoryStore:
    """构造带 stable layer 的 memory store。

    :returns: SeededMemoryStore。
    :raises Exception: 不主动抛出异常。
    """

    return SeededMemoryStore(
        pinned_state=ConversationPinnedState(
            current_goal="phase5 pinned goal",
            confirmed_subjects=("phase5 subject",),
            user_constraints=("keep source cursor",),
            open_questions=("none",),
        ),
        task_frame=TaskFrame(
            topic_ref="phase5-topic",
            entity_refs=("phase5-entity",),
            period_refs=("2025",),
            basis_refs=("smoke",),
            unit_ref="text",
        ),
    )


def _fake_runner_spec() -> RunnerSpec:
    """构造 fake provider / scripted proxy 用 RunnerSpec。

    :returns: RunnerSpec。
    :raises Exception: 不主动抛出异常。
    """

    return RunnerSpec(
        provider="openai",
        model="fake-model",
        endpoint="https://example.test/v1/chat/completions",
        api_key_ref="TEST_KEY",
        headers={},
        supports_tool_calling=True,
        supports_streaming=True,
        supports_stream_usage=False,
        default_timeout_seconds=30.0,
        max_retries=0,
        provider_request=None,
    )


def _engine_event(
    *,
    sequence: int,
    session_id: str,
    run_id: str,
    event_type: EngineEventType,
    data: EngineEventData,
) -> EngineEvent:
    """构造 EngineEvent。

    :param sequence: Engine event sequence。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param event_type: 事件类型。
    :param data: 事件 data。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"phase5-engine-{sequence}",
        sequence=sequence,
        session_id=session_id,
        run_id=run_id,
        occurred_at=datetime.now(tz=timezone.utc),
        type=event_type,
        data=data,
        metadata=None,
    )


def _runner_event(
    event_type: RunnerEventType,
    data: RunnerEventData,
) -> RunnerEvent:
    """构造 RunnerEvent。

    :param event_type: Runner event 类型。
    :param data: Runner event data。
    :returns: RunnerEvent。
    :raises Exception: 不主动抛出异常。
    """

    return RunnerEvent(
        type=event_type,
        data=data,
        occurred_at=datetime.now(tz=timezone.utc),
    )


def _fake_tool_call() -> ToolCallRequest:
    """构造 fake provider 产出的 huge_echo tool call。

    :returns: ToolCallRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id=_HUGE_ECHO_TOOL_CALL_ID,
        name=HUGE_ECHO_DEFINITION.name,
        arguments={"text": "phase5-host-smoke", "repeat": 96},
        index_in_iteration=0,
        provider_state=None,
    )


def _fake_fetch_more_tool_call(
    *, arguments: Mapping[str, JsonValue]
) -> ToolCallRequest:
    """构造 fake provider 根据截断 hint 发出的 ``fetch_more`` tool call。

    :param arguments: ``truncation.fetch_more_args``。
    :returns: ToolCallRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id=_FETCH_MORE_TOOL_CALL_ID,
        name=FRAMEWORK_FETCH_MORE_TOOL_NAME,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _tool_call_script() -> tuple[RunnerEvent, ...]:
    """构造工具调用 Runner 脚本。

    :returns: RunnerEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        _runner_event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=None,
                reasoning_content="fake reasoning must stay preview",
                finish_reason=FinishReason.TOOL_CALLS,
            ),
        ),
        _runner_event(
            RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
            RunnerToolCallsCompletedData(tool_calls=(_fake_tool_call(),)),
        ),
        _runner_event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=FinishReason.TOOL_CALLS),
        ),
    )


def _fetch_more_script_from_hint(
    messages: Sequence[AgentMessage],
    tools: Sequence[ToolSchema],
) -> tuple[RunnerEvent, ...]:
    """从 previous run 的 ToolMessage 截断 hint 中构造 ``fetch_more`` 调用脚本。

    :param messages: 当前 Runner 输入消息。
    :param tools: 当前暴露给 Runner 的工具 schema。
    :returns: RunnerEvent 元组。
    :raises AssertionError: 未看到合法截断 hint 或 schema 时抛出。
    """

    tool_names = {schema.function.name for schema in tools}
    assert FRAMEWORK_FETCH_MORE_TOOL_NAME in tool_names
    payload = _latest_tool_message_payload(messages)
    truncation = _json_object_field(payload, "truncation")
    assert truncation.get("next_action") == FRAMEWORK_FETCH_MORE_TOOL_NAME
    fetch_more_args = _json_object_field(truncation, "fetch_more_args")
    assert isinstance(fetch_more_args.get("cursor"), str)
    assert isinstance(fetch_more_args.get("scope_token"), str)
    return (
        _runner_event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=None,
                reasoning_content=None,
                finish_reason=FinishReason.TOOL_CALLS,
            ),
        ),
        _runner_event(
            RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
            RunnerToolCallsCompletedData(
                tool_calls=(
                    _fake_fetch_more_tool_call(arguments=fetch_more_args),
                )
            ),
        ),
        _runner_event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=FinishReason.TOOL_CALLS),
        ),
    )


def _final_script(content: str) -> tuple[RunnerEvent, ...]:
    """构造 final answer Runner 脚本。

    :param content: final answer 正文。
    :returns: RunnerEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        _runner_event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=content,
                reasoning_content=None,
                finish_reason=FinishReason.STOP,
            ),
        ),
        _runner_event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=FinishReason.STOP),
        ),
    )


async def _iter_runner_events(
    events: tuple[RunnerEvent, ...]
) -> AsyncIterator[RunnerEvent]:
    """产出 RunnerEvent 序列。

    :param events: RunnerEvent 元组。
    :returns: RunnerEvent 异步流。
    :raises Exception: 不主动抛出异常。
    """

    for event in events:
        yield event


async def _iter_engine_events(
    events: tuple[EngineEvent, ...]
) -> AsyncIterator[EngineEvent]:
    """产出 EngineEvent 序列。

    :param events: 事件元组。
    :returns: EngineEvent 异步流。
    :raises Exception: 不主动抛出异常。
    """

    for event in events:
        yield event


async def _collect_until_cursor_issued(
    events: AsyncIterator[RunEvent],
    *,
    output: _RealProviderRunOutput | None = None,
) -> tuple[RunEvent, ...]:
    """收集事件直到观察到 ToolRuntime cursor issued。

    :param events: RunEvent 流。
    :param output: 可选的 real-provider 人工观察输出器。
    :returns: 已收集事件。
    :raises RuntimeError: 提前终态时抛出。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
        _observe_real_provider_run_event(output, event)
        if isinstance(event.data, ToolCursorIssuedData):
            return tuple(collected)
        if _is_terminal(event):
            raise RuntimeError("terminal before cursor issued")
    raise RuntimeError("stream ended before cursor issued")


async def _collect_events(
    events: AsyncIterator[RunEvent],
    *,
    output: _RealProviderRunOutput | None = None,
) -> tuple[RunEvent, ...]:
    """收集完整 RunEvent 流。

    :param events: RunEvent 流。
    :param output: 可选的 real-provider 人工观察输出器。
    :returns: 事件元组。
    :raises Exception: 透传事件流异常。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
        _observe_real_provider_run_event(output, event)
    return tuple(collected)


def _real_provider_run_output(
    *, run_index: int, enabled: bool
) -> _RealProviderRunOutput | None:
    """按开关构造 real-provider run 观察输出器。

    :param run_index: smoke 中的 run 序号，从 1 开始。
    :param enabled: 是否启用人工观察输出。
    :returns: 输出器；未启用时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if not enabled:
        return None
    return _RealProviderRunOutput(run_index=run_index)


def _observe_real_provider_run_event(
    output: _RealProviderRunOutput | None, event: RunEvent
) -> None:
    """把单个 RunEvent 交给可选的 real-provider 输出器。

    :param output: real-provider 人工观察输出器；未启用时为 ``None``。
    :param event: Host ``RunEvent``。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if output is None:
        return
    output.observe(event)


def _finish_real_provider_run_output(
    output: _RealProviderRunOutput | None,
) -> None:
    """结束可选的 real-provider run 输出器。

    :param output: real-provider 人工观察输出器；未启用时为 ``None``。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if output is None:
        return
    output.finish()


async def _wait_for_result(
    *, harness: LocalRunHarness, run_id: str
) -> RunSucceededResult:
    """等待 run 成功终态与 memory projection。

    :param harness: LocalRunHarness。
    :param run_id: run id。
    :returns: 成功结果。
    :raises AssertionError: 超时或非成功终态时抛出。
    """

    for _ in range(_WAIT_SPIN_LIMIT):
        result = await harness.get_run_result(run_id)
        if isinstance(result, RunSucceededResult):
            return result
        await asyncio.sleep(_WAIT_SLEEP_SECONDS)
    raise AssertionError(f"run did not succeed: {run_id}")


async def _wait_for_memory_projection(
    *, harness: LocalRunHarness, session_id: str
) -> None:
    """等待 memory projection 完成。

    :param harness: LocalRunHarness。
    :param session_id: session id。
    :returns: 无返回值。
    :raises AssertionError: 超时后仍未投影时抛出。
    """

    for _ in range(_WAIT_SPIN_LIMIT):
        snapshot = await harness.memory_store.get_snapshot(session_id)
        if snapshot.recent_raw_turns:
            return
        await asyncio.sleep(_WAIT_SLEEP_SECONDS)
    raise AssertionError("memory projection was not completed")


def _is_terminal(event: RunEvent) -> bool:
    """判断 RunEvent 是否为终态。

    :param event: RunEvent。
    :returns: 终态返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return event.type in {
        RunEventType.FINAL_ANSWER,
        RunEventType.RUN_FAILED,
        RunEventType.RUN_CANCELLED,
        RunEventType.RUN_SUSPENDED,
    }


def _last_data(
    events: Sequence[RunEvent], data_type: type[_T]
) -> _T | None:
    """按类型返回最后一个事件 data。

    :param events: 事件序列。
    :param data_type: data 类型。
    :returns: 匹配 data 或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for event in reversed(events):
        if isinstance(event.data, data_type):
            return event.data
    return None


def _first_data(
    events: Sequence[RunEvent], data_type: type[_T]
) -> _T | None:
    """按类型返回第一个事件 data。

    :param events: 事件序列。
    :param data_type: data 类型。
    :returns: 匹配 data 或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for event in events:
        if isinstance(event.data, data_type):
            return event.data
    return None


def _event_cursor_for_data(
    events: Sequence[RunEvent],
    data: ToolResultTruncatedData | ToolFetchMoreCompletedData,
) -> int | None:
    """返回指定工具事实 data 对应事件 cursor。

    :param events: 事件序列。
    :param data: 工具事实 data。
    :returns: cursor sequence 或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for event in events:
        if event.data == data:
            return event.cursor.sequence
    return None


def _preview_text(text: str, max_chars: int) -> str:
    """返回固定长度文本预览。

    :param text: 已格式化为单行的文本。
    :param max_chars: 最大保留字符数。
    :returns: 不超过最大长度的文本预览；截断时附加截断标记。
    :raises ValueError: ``max_chars`` 小于截断标记长度时抛出。
    """

    if max_chars < len(_TEXT_TRUNCATED_SUFFIX):
        raise ValueError("max_chars must fit truncation suffix")
    if len(text) <= max_chars:
        return text
    keep_chars = max_chars - len(_TEXT_TRUNCATED_SUFFIX)
    return text[:keep_chars] + _TEXT_TRUNCATED_SUFFIX


def _messages_to_text(messages: Sequence[AgentMessage]) -> str:
    """拼接消息正文。

    :param messages: Agent 消息序列。
    :returns: 拼接后的文本。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    for message in messages:
        if isinstance(message, (SystemMessage, UserMessage)):
            parts.append(message.content)
        if isinstance(message, AssistantMessage) and message.content is not None:
            parts.append(message.content)
    return "\n".join(parts)


def _latest_tool_message_payload(
    messages: Sequence[AgentMessage],
) -> Mapping[str, JsonValue]:
    """读取最近一条 ToolMessage 的 JSON object 内容。

    :param messages: Agent 消息序列。
    :returns: ToolMessage content 反序列化后的 JSON object。
    :raises AssertionError: 缺少 ToolMessage 或 content 不是 JSON object 时抛出。
    """

    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            loaded = json.loads(message.content)
            assert isinstance(loaded, Mapping)
            return cast(Mapping[str, JsonValue], loaded)
    raise AssertionError("missing tool message")


def _json_object_field(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> Mapping[str, JsonValue]:
    """读取 JSON object 字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 字段值。
    :raises AssertionError: 字段不存在或不是 JSON object 时抛出。
    """

    value = payload.get(field_name)
    assert isinstance(value, Mapping)
    return value


def _last_built_messages_from_trace_source(
    harness: LocalRunHarness, run_id: str
) -> tuple[AgentMessage, ...]:
    """读取 harness 内部最近 RunInput 消息缓存。

    :param harness: LocalRunHarness。
    :param run_id: run id。
    :returns: 已缓存的 RunInput 消息；缺失时为空元组。
    :raises Exception: 不主动抛出异常。
    """

    return harness.last_run_input_messages_by_run.get(run_id, ())


def _print_provider_summary(*, case: ProviderCase, request_sent: bool) -> None:
    """输出 provider 中性摘要。

    :param case: provider case。
    :param request_sent: 是否将发送真实请求。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    print(
        f"{_SMOKE_PREFIX} case=real-provider provider={case.provider} "
        f"model={case.model} endpoint={_endpoint_summary(case.endpoint)} "
        f"request_sent={request_sent} supports_tool_calling="
        f"{case.supports_tool_calling} supports_stream_usage="
        f"{case.supports_stream_usage} provider_request="
        f"{_provider_request_summary(case.provider_request)} "
        f"case_source={_PROVIDER_CASE_SOURCE} "
        f"thinking_extension_source={_MIMO_THINKING_SOURCE}"
    )


def _endpoint_summary(endpoint: str) -> str:
    """返回 endpoint 摘要。

    :param endpoint: endpoint URL。
    :returns: 去掉路径细节的摘要。
    :raises Exception: 不主动抛出异常。
    """

    if "/v1/" in endpoint:
        return endpoint.split("/v1/", maxsplit=1)[0] + "/v1/..."
    return endpoint


def _provider_request_summary(
    provider_request: ProviderRequestExtension | None,
) -> str:
    """生成 provider_request 摘要。

    :param provider_request: provider request。
    :returns: 摘要。
    :raises Exception: 不主动抛出异常。
    """

    if provider_request is None:
        return "none"
    if isinstance(provider_request, MimoThinkingExtension):
        return f"mimo_thinking enabled={provider_request.enabled}"
    return type(provider_request).__name__


async def _async_main(args: SmokeArgs) -> int:
    """执行 smoke。

    :param args: smoke 参数。
    :returns: 进程退出码。
    :raises Exception: 未预期异常透传。
    """

    ok = True
    if args.case in ("all", "real-provider"):
        ok = await run_real_provider_case(args) and ok
    if args.case in ("all", "compact-retry"):
        ok = await run_compact_retry_case() and ok
    return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 可选参数序列；为 ``None`` 时使用 ``sys.argv``。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出异常。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    configure(level=LogLevel[args.log_level.upper()])
    logging.basicConfig(
        level=int(LogLevel[args.log_level.upper()]),
        format="%(levelname)s %(name)s %(message)s",
    )
    try:
        return asyncio.run(_async_main(args))
    except Exception as exc:
        _LOGGER.exception("phase5 smoke failed")
        print(
            f"{_SMOKE_PREFIX} failed reason=unexpected "
            f"detail={type(exc).__name__}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
