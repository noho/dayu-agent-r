"""P10.5 Slice 3 per-run 业务工具选择测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from datetime import UTC, datetime

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    EnsureSessionRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostToolingOptions,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    HostSessionEventDeliveryPolicy,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    SubmitFollowupRequest,
    open_host,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.host.memory import default_memory_projection_policy
from tests.host.public_smoke_support import close_attachment_shielded


class _FinalHandle:
    """测试用 final answer handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: dispatch snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        """

        return "slice3-tool-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出成功终态事件。

        :returns: EngineEvent 异步迭代器。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 2, 0, 0, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content="ok",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _RecordingWorker:
    """记录 Engine request 的 worker。"""

    def __init__(self, factory: "_RecordingWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 记录 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受并记录 Engine request。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: final handle。
        """

        self._factory.requests.append(request)
        self._factory.accepted.set()
        return _FinalHandle(snapshot)


class _RecordingWorkerFactory:
    """记录 worker accept 的 factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.accepted = asyncio.Event()
        self.requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 worker。

        :param snapshot: dispatch snapshot。
        :returns: 记录 worker。
        """

        del snapshot
        return _RecordingWorker(self)


@pytest.mark.asyncio
async def test_none_tool_names_uses_all_business_tools(tmp_path: pathlib.Path) -> None:
    """tool_names=None 使用 construction-time 全量业务工具。"""

    request = await _accepted_request(tmp_path, tool_names=None)

    assert _schema_names(request) == ("lookup_filing", "search_note")


@pytest.mark.asyncio
async def test_empty_tool_names_disables_business_tools(
    tmp_path: pathlib.Path,
) -> None:
    """空 frozenset 禁用本次 Run 的业务工具。"""

    request = await _accepted_request(tmp_path, tool_names=frozenset())

    assert _schema_names(request) == ()


@pytest.mark.asyncio
async def test_subset_tool_names_filters_tool_schema(tmp_path: pathlib.Path) -> None:
    """非空 tool_names 只暴露请求选择的业务工具 schema。"""

    request = await _accepted_request(
        tmp_path, tool_names=frozenset({"search_note"})
    )

    assert _schema_names(request) == ("search_note",)


@pytest.mark.asyncio
async def test_unknown_tool_name_is_rejected_before_dispatch(
    tmp_path: pathlib.Path,
) -> None:
    """admission 必须在 durable dispatch 前拒绝未知业务工具名。"""

    factory = _RecordingWorkerFactory()
    async with (
        open_host(_options(tmp_path, factory)) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        with pytest.raises(HostApiError) as error:
            await host.submit_followup(
                session.session_id,
                _followup(
                    session.session_id,
                    client_request_id="unknown-tool",
                    tool_names=frozenset({"missing_tool"}),
                ),
            )

    assert error.value.code == HostApiErrorCode.INVALID_STATE
    assert factory.requests == []


async def _accepted_request(
    tmp_path: pathlib.Path, *, tool_names: frozenset[str] | None
) -> AgentRunRequest:
    """提交一次 follow-up 并返回 worker 收到的 Engine request。

    :param tmp_path: 临时目录。
    :param tool_names: per-run 工具选择器。
    :returns: AgentRunRequest。
    """

    factory = _RecordingWorkerFactory()
    async with (
        open_host(_options(tmp_path, factory)) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        await host.submit_followup(
            session.session_id,
            _followup(
                session.session_id,
                client_request_id="client-tools",
                tool_names=tool_names,
            ),
        )
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)
    return factory.requests[0]


def _schema_names(request: AgentRunRequest) -> tuple[str, ...]:
    """返回 Engine request 暴露的工具 schema 名称。

    :param request: Engine request。
    :returns: 工具名元组。
    """

    return tuple(schema.function.name for schema in request.tool_schemas)


def _followup(
    session_id: str,
    *,
    client_request_id: str,
    tool_names: frozenset[str] | None,
) -> SubmitFollowupRequest:
    """构造 follow-up 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等 id。
    :param tool_names: per-run 工具选择器。
    :returns: SubmitFollowupRequest。
    """

    return SubmitFollowupRequest(
        context=_context(client_request_id),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=None,
        user_prompt="use tools",
        tool_names=tool_names,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _options(
    tmp_path: pathlib.Path, worker_factory: _RecordingWorkerFactory
) -> OpenHostOptions:
    """构造带业务工具的 OpenHostOptions。

    :param tmp_path: 临时目录。
    :param worker_factory: worker factory。
    :returns: OpenHostOptions。
    """

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
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.2,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None, max_tokens=None, top_p=None, stream=False
            ),
            agent_policy=AgentPolicy(
                max_iterations=1,
                continuation_max_attempts=0,
                allow_tool_calls=True,
                tool_execution_timeout_seconds=1.0,
                fallback_prompt="test fallback prompt",
                continuation_prompt="test continuation prompt",
            ),
        ),
        worker_factory=worker_factory,
        tooling_options=HostToolingOptions(
            business_tool_bundle=ToolBundle(
                definitions=(
                    _definition("lookup_filing"),
                    _definition("search_note"),
                )
            ),
            source_refs=(_source_ref(),),
        ),
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
        session_event_delivery_policy=HostSessionEventDeliveryPolicy(
            transient_mailbox_max_items=512,
            max_subscriptions_per_session=4,
        ),
    )


def _ensure_request() -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :returns: EnsureSessionRequest。
    """

    return EnsureSessionRequest(scope="scope", slot_key="slot", metadata=())


def _context(request_id: str) -> HostCallContext:
    """构造 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="tester",
        source="pytest",
        request_id=request_id,
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name="submit_followup",
            operation_kind="interactive",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario=None,
            correlation_id=None,
        ),
    )


def _runner_spec() -> RunnerSpec:
    """构造支持工具调用的 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="tool-model",
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
    )


async def _noop_tool(
    call: ToolCallRequest, context: BatchToolExecutionContext
) -> ToolExecutionOutcome:
    """测试用工具 callable。

    :param call: 工具调用请求。
    :param context: 批式上下文。
    :returns: 取消 outcome。
    """

    del call, context
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message="not executed",
        hint=None,
        meta=None,
    )


def _definition(name: str) -> ToolDefinition:
    """构造工具声明。

    :param name: 工具名。
    :returns: ToolDefinition。
    """

    properties: dict[str, JsonValue] = {}
    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=f"{name} tool",
                parameters=ToolParametersSchema(
                    type="object",
                    properties=properties,
                    required=(),
                    additional_properties=False,
                ),
            ),
        ),
        callable=_noop_tool,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=(),
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造工具来源引用。

    :returns: ToolBundleSourceRef。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="pytest",
    )
