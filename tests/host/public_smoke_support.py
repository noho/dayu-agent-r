"""P10.5 public-path smoke 测试支撑。

本模块只服务 ``tests/host`` 下的 public smoke。它提供真实 provider case、
公共 opener options、watch terminal helper 与少量 deterministic worker，
不读取 Host durable truth 作为 smoke correctness assertion。
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sqlite3
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.agent import _AsyncAgent
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessage
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerToolCallsCompletedData,
)
from dayu.engine.contracts.runner_identity import RunnerRequestIdentity
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    DeepSeekThinkingExtension,
    GeminiThinkingExtension,
    MimoThinkingExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host import (
    AttemptDispatchSnapshot,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostCallContext,
    HostEvent,
    HostEventKind,
    HostTerminalStatus,
    HostToolingOptions,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    ResolveWaitCompletedOutcome,
    ResolveWaitRequest,
    RunStatus,
    SubmitFollowupRequest,
    WaitAdapterKey,
    WaitResolutionSource,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.host.api import AuthorizationClaim
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.state import (
    WaitRecordRow,
    WaitResumePolicy,
    read_active_wait_records_for_run,
)
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.host.memory import default_memory_projection_policy
from dayu.host.wait_adapter import (
    WaitAdapterBinding,
    WaitAdapterRegistry,
    WaitExternalJobRefSource,
)

_NOW = datetime(2026, 5, 18, 8, 0, 0, tzinfo=UTC)
_DEFAULT_TIMEOUT_SECONDS = 45.0
_DEFAULT_MAX_RETRIES = 0
_DEFAULT_MAX_TOKENS = 96
_TOOL_EXECUTION_TIMEOUT_SECONDS = 5.0
_PROVIDER_TEST_TIMEOUT_SECONDS = 120.0
_AWAITING_TOOL_NAME = "awaiting_mock_fact"
_AWAITING_RESUME_TOKEN = "public-smoke-external-job"
_NETWORK_FAILURE_MARKERS: tuple[str, ...] = (
    "clientconnectorerror",
    "clientconnectionerror",
    "clientoserror",
    "serverdisconnectederror",
    "timeout",
    "timed out",
    "temporary failure",
    "name or service not known",
    "nodename nor servname",
    "network is unreachable",
    "connection reset",
    "connection refused",
)
_TEMPORARY_PROVIDER_UNAVAILABLE_MARKERS: tuple[str, ...] = (
    "503",
    "http 503",
    "status 503",
    "http_status=503",
    "server_error",
    "server error",
    "server overloaded",
    "model is overloaded",
    "overloaded",
    "transient unavailable",
    "transiently unavailable",
    "temporarily unavailable",
    "temporary unavailable",
    "transient server",
    "try again later",
)
_TEMPORARY_PROVIDER_RATE_LIMIT_MARKERS: tuple[str, ...] = (
    "429",
    "http 429",
    "status 429",
    "http_status=429",
    "resource_exhausted",
    "quota_exceeded",
    "quotafailure",
    "quota failure",
    "rate_limit_exceeded",
    "rate limit",
    "ratelimit",
    "retryinfo",
    "retry info",
    "retrydelay",
    "retry delay",
)
_EXPLICIT_UNAVAILABLE_MARKERS: tuple[str, ...] = (
    "status': 'unavailable'",
    '"status": "unavailable"',
    "status=unavailable",
    "code=unavailable",
    "grpc_status=unavailable",
    "error code: 503",
)


@dataclass(frozen=True, slots=True)
class ProviderSmokeCase:
    """真实 provider smoke case。

    :param name: case 名称。
    :param provider: RunnerSpec provider 字段。
    :param env_var: API key 环境变量名。
    :param endpoint: OpenAI-compatible endpoint。
    :param model: provider 模型名。
    :param supports_stream_usage: 是否支持 stream usage。
    :param provider_request: provider thinking 扩展。
    """

    name: str
    provider: str
    env_var: str
    endpoint: str
    model: str
    supports_stream_usage: bool
    provider_request: ProviderRequestExtension


@dataclass(frozen=True, slots=True)
class PublicWaitingRun:
    """public smoke 中由 public opener 生成的 WAITING Run 引用。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: 进入 WAITING 的 Attempt id。
    :param wait_id: Host wait record id，供 public ``resolve_wait`` 输入使用。
    """

    session_id: str
    run_id: str
    attempt_id: str
    wait_id: str


class FinalAnswerHandle:
    """立即产出 final answer 的 deterministic worker handle。

    :param snapshot: dispatch snapshot。
    :param content: final answer 文本。
    """

    def __init__(self, snapshot: AttemptDispatchSnapshot, content: str) -> None:
        """初始化 handle。

        :param snapshot: dispatch snapshot。
        :param content: final answer 文本。
        :returns: ``None``。
        :raises ValueError: content 为空时抛出。
        """

        if content.strip() == "":
            raise ValueError("content must be non-empty")
        self._snapshot = snapshot
        self._content = content

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "slice6-final-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出成功终态事件。

        :returns: EngineEvent 异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=self._content,
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class FinalAnswerWorker:
    """立即成功的 deterministic worker。

    :param factory: 所属 factory。
    """

    def __init__(self, factory: "FinalAnswerWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受 dispatch 并记录 Engine request。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: worker handle。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.requests.append(request)
        self._factory.snapshots.append(snapshot)
        self._factory.accepted.set()
        content = f"final:{len(self._factory.requests)}:{snapshot.run_id}"
        return FinalAnswerHandle(snapshot, content)


class FinalAnswerWorkerFactory:
    """记录请求并立即成功的 worker factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.requests: list[AgentRunRequest] = []
        self.snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted = asyncio.Event()

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 worker。

        :param snapshot: dispatch snapshot。
        :returns: deterministic worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return FinalAnswerWorker(self)


class ToolCallingWorkerFactory:
    """通过 Engine Agent 触发 ToolRuntime 的 deterministic worker factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.requests: list[AgentRunRequest] = []
        self.messages_seen: list[tuple[AgentMessage, ...]] = []
        self.accepted = asyncio.Event()

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 tool-calling worker。

        :param snapshot: dispatch snapshot。
        :returns: tool-calling worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return _ToolCallingWorker(self)


class AwaitingThenFinalWorkerFactory:
    """首个 dispatch 进入 WAITING，后续 dispatch 立即成功的 worker factory。"""

    def __init__(self) -> None:
        """初始化 worker factory。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.requests: list[AgentRunRequest] = []
        self.snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted = asyncio.Event()

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建等待型或成功型 worker。

        :param snapshot: dispatch snapshot。
        :returns: 测试 worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return _AwaitingThenFinalWorker(self)


class _AwaitingThenFinalWorker:
    """按 dispatch 顺序切换 awaiting / final 行为的 worker。"""

    def __init__(self, factory: AwaitingThenFinalWorkerFactory) -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受 dispatch 并返回对应 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 第一次为 awaiting handle，后续为 final answer handle。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.requests.append(request)
        self._factory.snapshots.append(snapshot)
        self._factory.accepted.set()
        if len(self._factory.requests) == 1:
            return _AgentBackedHandle(snapshot, request, _AwaitingToolRunner())
        return FinalAnswerHandle(snapshot, f"resolved:{snapshot.run_id}")


class _ToolCallingWorker:
    """通过 scripted runner 驱动 Engine 工具循环的 worker。

    :param factory: 所属 factory。
    """

    def __init__(self, factory: ToolCallingWorkerFactory) -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受 dispatch 并返回 Engine Agent backed handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: worker handle。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.requests.append(request)
        self._factory.accepted.set()
        runner = _ScriptedToolRunner(self._factory)
        return _AgentBackedHandle(snapshot, request, runner)


class _AgentBackedHandle:
    """用指定 Runner 执行 Engine Agent 的 worker handle。

    :param snapshot: dispatch snapshot。
    :param request: Engine request。
    :param runner: scripted runner。
    """

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
        runner: AsyncRunner,
    ) -> None:
        """初始化 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :param runner: scripted runner。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._snapshot = snapshot
        self._request = request
        self._runner = runner

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "slice6-tool-agent-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出 Engine Agent 事件流。

        :returns: EngineEvent 异步迭代器。
        :raises Exception: Engine Agent 执行失败时透传。
        """

        del self._snapshot
        agent = _AsyncAgent(request=self._request, runner=self._runner)
        async for event in agent.run_messages():
            yield event

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        await self._runner.close()

    def on_cancel(self, reason: str) -> None:
        """忽略取消。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class _ScriptedToolRunner:
    """第一轮请求工具、第二轮返回最终答案的 Runner。

    :param factory: 用于记录 messages 的 factory。
    """

    def __init__(self, factory: ToolCallingWorkerFactory) -> None:
        """初始化 runner。

        :param factory: 用于记录 messages 的 factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory
        self._call_count = 0

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
        *,
        request_identity: RunnerRequestIdentity | None,
    ) -> AsyncIterator[RunnerEvent]:
        """返回脚本化 RunnerEvent 流。

        :param messages: 当前 Agent messages。
        :param options: Runner call options。
        :param tools: 当前暴露的 tool schemas。
        :param request_identity: 本次逻辑 Runner 调用的请求身份。
        :returns: RunnerEvent 异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        del options, tools, request_identity
        self._factory.messages_seen.append(tuple(messages))
        self._call_count += 1
        if self._call_count == 1:
            return self._iter_events(_tool_script(_tool_call()))
        return self._iter_events(_final_script("tool fact accepted"))

    def is_supports_tool_calling(self) -> bool:
        """返回支持工具调用。

        :returns: 始终为 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    async def close(self) -> None:
        """关闭 runner。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    async def _iter_events(
        self, events: tuple[RunnerEvent, ...]
    ) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件。

        :param events: 待产出的事件。
        :returns: RunnerEvent 异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        for event in events:
            yield event


class _AwaitingToolRunner:
    """第一轮请求等待型工具的 Runner。"""

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
        *,
        request_identity: RunnerRequestIdentity | None,
    ) -> AsyncIterator[RunnerEvent]:
        """返回等待型工具调用脚本。

        :param messages: 当前 Agent messages。
        :param options: Runner call options。
        :param tools: 当前暴露的 tool schemas。
        :param request_identity: 本次逻辑 Runner 调用的请求身份。
        :returns: RunnerEvent 异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        del messages, options, tools, request_identity
        return self._iter_events(_tool_script(_awaiting_tool_call()))

    def is_supports_tool_calling(self) -> bool:
        """返回支持工具调用。

        :returns: 始终为 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    async def close(self) -> None:
        """关闭 runner。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    async def _iter_events(
        self, events: tuple[RunnerEvent, ...]
    ) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件。

        :param events: 待产出的事件。
        :returns: RunnerEvent 异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        for event in events:
            yield event


class MockFactTool:
    """机械返回固定工具事实的 mock business tool。"""

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 mock 工具。

        :param call: 工具调用请求。
        :param context: 批式执行上下文。
        :returns: 成功工具 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del context
        ticker_value = call.arguments.get("ticker")
        ticker = ticker_value if isinstance(ticker_value, str) else "DAYU"
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "ticker": ticker,
                    "fact": "mock-tool-fact-enters-memory",
                },
                meta=None,
            )
        )


class AwaitingMockTool:
    """返回 awaiting outcome 的 mock business tool。"""

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行等待型 mock 工具。

        :param call: 工具调用请求。
        :param context: 批式执行上下文。
        :returns: awaiting 工具 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del call, context
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token=_AWAITING_RESUME_TOKEN,
            ),
            snapshot=None,
        )


PROVIDER_CASES: tuple[ProviderSmokeCase, ...] = (
    ProviderSmokeCase(
        name="mimo",
        provider="mimo",
        env_var="MIMO_PLAN_API_KEY",
        endpoint="https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
        model="mimo-v2.5-pro",
        supports_stream_usage=False,
        provider_request=MimoThinkingExtension(enabled=True),
    ),
    ProviderSmokeCase(
        name="deepseek",
        provider="deepseek",
        env_var="DEEPSEEK_API_KEY",
        endpoint="https://api.deepseek.com/chat/completions",
        model="deepseek-v4-flash",
        supports_stream_usage=True,
        provider_request=DeepSeekThinkingExtension(enabled=True),
    ),
    ProviderSmokeCase(
        name="gemini",
        provider="gemini",
        env_var="GEMINI_API_KEY",
        endpoint=(
            "https://generativelanguage.googleapis.com/v1beta/openai/"
            "chat/completions"
        ),
        model="gemini-2.5-flash",
        supports_stream_usage=False,
        provider_request=GeminiThinkingExtension(
            thinking_budget=-1,
            include_thoughts=True,
        ),
    ),
    ProviderSmokeCase(
        name="qwen",
        provider="qwen",
        env_var="QWEN_API_KEY",
        endpoint=(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/"
            "chat/completions"
        ),
        model="qwen3.6-plus",
        supports_stream_usage=True,
        provider_request=QwenThinkingExtension(enable_thinking=True),
    ),
)


def first_available_provider_case() -> tuple[ProviderSmokeCase, str]:
    """返回第一个可用真实 provider case。

    :returns: provider case 与 API key。
    :raises pytest.skip.Exception: 所有 provider secret 都缺失时跳过。
    """

    for case in PROVIDER_CASES:
        api_key = os.environ.get(case.env_var)
        if api_key is not None and api_key.strip() != "":
            return case, api_key
    pytest.skip(_all_provider_missing_reason())


def api_key_or_skip(case: ProviderSmokeCase) -> str:
    """读取 provider API key，缺失时精确 skip。

    :param case: provider case。
    :returns: API key。
    :raises pytest.skip.Exception: 环境变量缺失或为空时跳过。
    """

    api_key = os.environ.get(case.env_var)
    if api_key is None or api_key.strip() == "":
        pytest.skip(f"provider={case.name} missing_env={case.env_var}")
    return api_key


def runner_spec_for_case(case: ProviderSmokeCase, api_key: str) -> RunnerSpec:
    """构造真实 provider RunnerSpec。

    :param case: provider case。
    :param api_key: API key 明文，只进入请求头。
    :returns: RunnerSpec。
    :raises ValueError: RunnerSpec 字段不合法时由底层抛出。
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
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=False,
        supports_streaming=True,
        supports_stream_usage=case.supports_stream_usage,
        default_timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
        max_retries=_DEFAULT_MAX_RETRIES,
        provider_request=None,
        stream_idle_timeout_seconds=None,
        stream_idle_heartbeat_seconds=None,
    )


def open_host_options(
    tmp_path: pathlib.Path,
    *,
    runner_spec: RunnerSpec,
    worker_factory: LocalEngineWorkerFactory | None,
    allow_tool_calls: bool,
    tooling_options: HostToolingOptions | None = None,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> OpenHostOptions:
    """构造 public smoke 用 OpenHostOptions。

    :param tmp_path: pytest 临时目录。
    :param runner_spec: ordinary Run baseline RunnerSpec。
    :param worker_factory: worker factory；为 ``None`` 时使用真实 LocalProxy。
    :param allow_tool_calls: AgentPolicy 是否允许工具调用。
    :param tooling_options: 可选 construction-time 工具选项。
    :param max_tokens: ordinary runner 最大输出 token。
    :returns: OpenHostOptions。
    :raises TypeError: typed options 字段非法时由底层抛出。
    :raises ValueError: options 语义非法时由底层抛出。
    """

    resolved_worker_factory = (
        DefaultLocalEngineWorkerFactory()
        if worker_factory is None
        else worker_factory
    )
    return OpenHostOptions(
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        lane_db_path=tmp_path / "lane.sqlite3",
        lane_name="slice6-public-smoke",
        lane_capacity=1,
        lane_default_timeout_seconds=1.0,
        lane_claim_ttl_seconds=3.0,
        lane_heartbeat_interval_seconds=0.2,
        worker_startup_timeout_seconds=3.0,
        dispatch_poll_interval_seconds=0.01,
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
            runner_spec=runner_spec,
            runner_options=RunnerCallOptions(
                temperature=0.0,
                max_tokens=max_tokens,
                top_p=None,
                stream=False,
            ),
            agent_policy=AgentPolicy(
                max_iterations=2 if allow_tool_calls else 1,
                continuation_max_attempts=0,
                allow_tool_calls=allow_tool_calls,
                tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
            ),
        ),
        worker_factory=resolved_worker_factory,
        tooling_options=tooling_options,
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
    )


def deterministic_runner_spec(model: str = "slice6-test-model") -> RunnerSpec:
    """构造 deterministic smoke 用 RunnerSpec。

    :param model: 模型名。
    :returns: RunnerSpec。
    :raises ValueError: RunnerSpec 字段不合法时由底层抛出。
    """

    return RunnerSpec(
        provider="test",
        model=model,
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=True,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
        stream_idle_timeout_seconds=None,
        stream_idle_heartbeat_seconds=None,
    )


def ensure_request(slot_key: str) -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :param slot_key: slot key。
    :returns: EnsureSessionRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return EnsureSessionRequest(scope="workspace", slot_key=slot_key, metadata=())


def followup_request(
    session_id: str,
    client_request_id: str,
    user_prompt: str,
    *,
    tool_names: frozenset[str] | None = None,
    runner_spec: RunnerSpec | None = None,
    runner_options: RunnerCallOptions | None = None,
) -> SubmitFollowupRequest:
    """构造 queue follow-up 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param user_prompt: 用户输入。
    :param tool_names: 可选工具选择器。
    :param runner_spec: 可选 per-run runner spec override。
    :param runner_options: 可选 per-run runner options override。
    :returns: SubmitFollowupRequest。
    :raises ValueError: 请求字段非法时由底层抛出。
    """

    return SubmitFollowupRequest(
        context=host_context(client_request_id),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=None,
        user_prompt=user_prompt,
        tool_names=tool_names,
        runner_spec=runner_spec,
        runner_options=runner_options,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def host_context(request_id: str) -> HostCallContext:
    """构造 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises ValueError: context 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="tester"),),
        operation_context=OperationContext(
            operation_name="slice6_public_smoke",
            operation_kind="test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="p10_5_slice6",
            correlation_id=None,
        ),
    )


async def next_terminal_for_run(
    iterator: AsyncIterator[HostEvent], run_id: str
) -> HostEvent:
    """读取指定 Run 的下一条 terminal HostEvent。

    :param iterator: HostEvent async iterator。
    :param run_id: 目标 Run id。
    :returns: terminal HostEvent。
    :raises AssertionError: 超时或读到失败 / 取消事件时由调用方断言抛出。
    """

    return await asyncio.wait_for(
        _read_next_terminal_for_run(iterator, run_id),
        timeout=_PROVIDER_TEST_TIMEOUT_SECONDS,
    )


async def wait_for_status(
    host: Host,
    run_id: str,
    terminal_status: HostTerminalStatus | None,
) -> HostEvent | None:
    """轮询 public get_run 等待指定 terminal status。

    :param host: public Host handle。
    :param run_id: Run id。
    :param terminal_status: 目标 terminal status；为 ``None`` 时等待非终态。
    :returns: 当前 helper 不返回事件，保留为 ``None``。
    :raises TimeoutError: 超时未达到状态时抛出。
    """

    del terminal_status
    for _ in range(200):
        snapshot = await host.get_run(run_id)
        if snapshot.status.value in {"succeeded", "failed", "cancelled"}:
            return None
        await asyncio.sleep(0.01)
    raise TimeoutError(f"run {run_id} did not reach terminal")


async def wait_for_public_waiting_run(
    host: Host,
    options: OpenHostOptions,
    run_id: str,
) -> PublicWaitingRun:
    """等待 public opener 产生 WAITING Run 并返回 resolve 所需引用。

    本 helper 先用 public ``get_run`` 观察 WAITING 状态；随后只为测试桥接
    public ``resolve_wait(wait_id, ...)`` 的输入，从 durable wait record 读取
    ``wait_id``。该读取集中在 public smoke support，不能作为 smoke
    correctness assertion；测试结论仍必须断言 public snapshot / HostEvent。

    :param host: public Host handle。
    :param options: 当前 open_host options。
    :param run_id: 目标 Run id。
    :returns: WAITING Run 引用。
    :raises TimeoutError: 超时未进入 WAITING 或未写入 wait record 时抛出。
    :raises AssertionError: WAITING snapshot 缺少 current attempt 时抛出。
    """

    for _ in range(200):
        snapshot = await host.get_run(run_id)
        if snapshot.status is RunStatus.WAITING:
            if snapshot.current_attempt_id is None:
                raise AssertionError("WAITING run must have current attempt")
            wait_id = _active_wait_id(options, run_id)
            if wait_id is not None:
                return PublicWaitingRun(
                    session_id=snapshot.session_id,
                    run_id=snapshot.run_id,
                    attempt_id=snapshot.current_attempt_id,
                    wait_id=wait_id,
                )
        await asyncio.sleep(0.01)
    raise TimeoutError(f"run {run_id} did not reach WAITING")


async def wait_for_diagnostic_event_type_count(
    db_path: pathlib.Path, event_type: str, expected_count: int
) -> None:
    """等待指定 diagnostic EventLog 类型达到期望数量。

    本 helper 只用于 public smoke 中等待非 public-display 的调度诊断事件，
    例如 ``ATTEMPT_RUNNING``。它不是 correctness assertion；调用方必须继续
    用 public ``get_run``、``watch_session_events`` 或 worker observable
    断言 cancel / steer / retry / replay 等结果。

    :param db_path: Host SQLite 路径。
    :param event_type: 等待的 EventLog event type。
    :param expected_count: 期望最小数量。
    :returns: ``None``。
    :raises TimeoutError: 超时未达到期望数量时抛出。
    """

    for _ in range(200):
        if _diagnostic_event_type_count(db_path, event_type) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"Event {event_type} did not reach {expected_count}")


def completed_wait_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造 public resolve_wait completed request。

    :param idempotency_key: resolve wait 幂等键。
    :returns: ResolveWaitRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return ResolveWaitRequest(
        context=host_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"answer": "public-wait-resolved"},
                meta=None,
            ),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=_NOW,
    )


def skip_if_provider_terminal_failed(
    case: ProviderSmokeCase, event: HostEvent
) -> None:
    """按精确 provider 环境失败原因跳过真实 provider terminal。

    :param case: provider case。
    :param event: terminal HostEvent。
    :returns: ``None``。
    :raises pytest.skip.Exception: provider endpoint/network、临时不可用、quota 或
        rate-limit 时跳过。
    """

    if event.terminal_status is not HostTerminalStatus.FAILED:
        return
    message = event.error_message or ""
    _skip_if_provider_failure_message(case, message)


def skip_if_provider_exception(case: ProviderSmokeCase, exc: BaseException) -> None:
    """按精确 provider 环境失败原因跳过真实 provider smoke 异常。

    :param case: provider case。
    :param exc: provider 调用路径抛出的异常。
    :returns: ``None``。
    :raises pytest.skip.Exception: provider endpoint/network、临时不可用、quota 或
        rate-limit 时跳过。
    """

    _skip_if_provider_failure_message(case, str(exc))


def _skip_if_provider_failure_message(
    case: ProviderSmokeCase, message: str
) -> None:
    """按原始错误消息精确识别可跳过的 provider 环境失败。

    :param case: provider case。
    :param message: 原始错误消息。
    :returns: ``None``。
    :raises pytest.skip.Exception: 匹配 provider 环境失败时跳过。
    """

    lowered = message.lower()
    if any(marker in lowered for marker in _NETWORK_FAILURE_MARKERS):
        pytest.skip(
            f"provider={case.name} endpoint={case.endpoint} "
            f"provider_availability=network_unavailable message={message}"
        )
    if any(
        marker in lowered
        for marker in _TEMPORARY_PROVIDER_UNAVAILABLE_MARKERS
    ):
        pytest.skip(
            f"provider={case.name} endpoint={case.endpoint} "
            f"provider_availability=server_overloaded_or_transient "
            f"message={message}"
        )
    if any(marker in lowered for marker in _EXPLICIT_UNAVAILABLE_MARKERS):
        pytest.skip(
            f"provider={case.name} endpoint={case.endpoint} "
            f"provider_availability=explicit_unavailable message={message}"
        )
    if any(marker in lowered for marker in _TEMPORARY_PROVIDER_RATE_LIMIT_MARKERS):
        pytest.skip(
            f"provider={case.name} endpoint={case.endpoint} "
            f"provider_quota_or_rate_limit=resource_exhausted message={message}"
        )


def mock_tooling_options() -> HostToolingOptions:
    """构造 mock business tool options。

    :returns: HostToolingOptions。
    :raises ValueError: 工具声明字段非法时由底层抛出。
    """

    return HostToolingOptions(
        business_tool_bundle=ToolBundle(definitions=(_mock_tool_definition(),)),
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="slice6-mock-tool",
            ),
        ),
    )


def awaiting_tooling_options() -> HostToolingOptions:
    """构造等待型 mock business tool options。

    :returns: HostToolingOptions。
    :raises ValueError: 工具声明字段非法时由底层抛出。
    """

    return HostToolingOptions(
        business_tool_bundle=ToolBundle(definitions=(_awaiting_tool_definition(),)),
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="public-smoke-awaiting-tool",
            ),
        ),
        wait_adapter_registry=_awaiting_wait_adapter_registry(),
    )


async def _read_next_terminal_for_run(
    iterator: AsyncIterator[HostEvent], run_id: str
) -> HostEvent:
    """顺序读取指定 Run terminal 事件。

    :param iterator: HostEvent async iterator。
    :param run_id: 目标 Run id。
    :returns: terminal HostEvent。
    :raises AssertionError: iterator 意外结束时抛出。
    """

    async for event in iterator:
        if event.run_id != run_id:
            continue
        if event.kind in (
            HostEventKind.SUCCEEDED,
            HostEventKind.FAILED,
            HostEventKind.CANCELLED,
            HostEventKind.LOST,
        ):
            return event
    raise AssertionError("watch iterator ended before terminal event")


def _tool_script(tool_call: ToolCallRequest) -> tuple[RunnerEvent, ...]:
    """构造工具调用 Runner 脚本。

    :param tool_call: 工具调用请求。
    :returns: RunnerEvent tuple。
    :raises ValueError: RunnerEvent 字段非法时由底层抛出。
    """

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
            RunnerToolCallsCompletedData(tool_calls=(tool_call,)),
        ),
        _runner_event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(
                finish_reason=FinishReason.TOOL_CALLS,
                provider_request_id=None,
            ),
        ),
    )


def _final_script(content: str) -> tuple[RunnerEvent, ...]:
    """构造最终回答 Runner 脚本。

    :param content: 最终回答。
    :returns: RunnerEvent tuple。
    :raises ValueError: RunnerEvent 字段非法时由底层抛出。
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
            RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
        ),
    )


def _runner_event(event_type: RunnerEventType, data: RunnerEventData) -> RunnerEvent:
    """构造 RunnerEvent。

    :param event_type: runner event type。
    :param data: runner event data。
    :returns: RunnerEvent。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return RunnerEvent(type=event_type, data=data, occurred_at=_NOW)


def _tool_call() -> ToolCallRequest:
    """构造 mock tool call。

    :returns: ToolCallRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return ToolCallRequest(
        tool_call_id="slice6-tool-call-1",
        name="lookup_mock_fact",
        arguments={"ticker": "DAYU"},
        index_in_iteration=0,
        provider_state=None,
    )


def _awaiting_tool_call() -> ToolCallRequest:
    """构造等待型 mock tool call。

    :returns: ToolCallRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return ToolCallRequest(
        tool_call_id="public-smoke-awaiting-call-1",
        name=_AWAITING_TOOL_NAME,
        arguments={"ticker": "DAYU"},
        index_in_iteration=0,
        provider_state=None,
    )


def _mock_tool_definition() -> ToolDefinition:
    """构造 mock tool definition。

    :returns: ToolDefinition。
    :raises ValueError: 字段非法时由底层抛出。
    """

    properties = {
        "ticker": {
            "type": "string",
            "description": "ticker symbol",
        }
    }
    return ToolDefinition(
        name="lookup_mock_fact",
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name="lookup_mock_fact",
                description="Return deterministic mock filing fact.",
                parameters=ToolParametersSchema(
                    type="object",
                    properties=properties,
                    required=("ticker",),
                    additional_properties=False,
                ),
            ),
        ),
        callable=MockFactTool(),
        truncate=None,
        display=None,
        tags=("slice6",),
    )


def _awaiting_tool_definition() -> ToolDefinition:
    """构造等待型 mock tool definition。

    :returns: ToolDefinition。
    :raises ValueError: 字段非法时由底层抛出。
    """

    properties = {
        "ticker": {
            "type": "string",
            "description": "ticker symbol",
        }
    }
    return ToolDefinition(
        name=_AWAITING_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=_AWAITING_TOOL_NAME,
                description="Return an awaiting mock filing fact.",
                parameters=ToolParametersSchema(
                    type="object",
                    properties=properties,
                    required=("ticker",),
                    additional_properties=False,
                ),
            ),
        ),
        callable=AwaitingMockTool(),
        truncate=None,
        display=None,
        tags=("slice6",),
    )


def _awaiting_wait_adapter_registry() -> WaitAdapterRegistry:
    """构造等待型 mock tool 的 wait adapter registry。

    :returns: WaitAdapterRegistry。
    :raises ValueError: binding 字段非法时由底层抛出。
    """

    return WaitAdapterRegistry(
        (
            WaitAdapterBinding(
                tool_name=_AWAITING_TOOL_NAME,
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                adapter_key=WaitAdapterKey("poll:public-smoke-awaiting-tool"),
                resume_policy=WaitResumePolicy.POLL,
                external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
            ),
        )
    )


def _active_wait_id(options: OpenHostOptions, run_id: str) -> str | None:
    """读取指定 Run 的 active wait id。

    :param options: 当前 open_host options。
    :param run_id: 目标 Run id。
    :returns: active wait id；尚未写入时为 ``None``。
    :raises RuntimeError: 同一 Run 出现多个 active wait record 时抛出。
    """

    durable_options = HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=options.artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=(
                options.sqlite_write_retry_initial_delay_seconds
            ),
            write_retry_backoff_multiplier=(
                options.sqlite_write_retry_backoff_multiplier
            ),
            write_retry_max_delay_seconds=options.sqlite_write_retry_max_delay_seconds,
        ),
    )
    rows: tuple[WaitRecordRow, ...] = ()
    with open_host_durable_store(durable_options) as store:
        rows = store.transaction_runner.run_read(
            lambda transaction: read_active_wait_records_for_run(transaction, run_id)
        )
    if len(rows) == 0:
        return None
    if len(rows) > 1:
        raise RuntimeError("public smoke waiting run must have one active wait")
    return rows[0].wait_id


def _diagnostic_event_type_count(db_path: pathlib.Path, event_type: str) -> int:
    """统计测试同步所需的 diagnostic event type 数量。

    :param db_path: Host SQLite 路径。
    :param event_type: 目标事件类型。
    :returns: 匹配事件数量。
    :raises TypeError: SQLite COUNT 结果类型不符合预期时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM event_log WHERE event_type = ?",
            (event_type,),
        ).fetchone()
    if row is None:
        return 0
    value = row[0]
    if not isinstance(value, int):
        raise TypeError("diagnostic event count must be int")
    return value


def _all_provider_missing_reason() -> str:
    """构造全部 provider secret 缺失的 skip reason。

    :returns: skip reason。
    :raises Exception: 不主动抛出异常。
    """

    return "; ".join(
        f"provider={case.name} missing_env={case.env_var}"
        for case in PROVIDER_CASES
    )
