"""Host Phase 6 ToolRuntime 本地 Engine 集成测试。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultMeta, ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.engine.agent import _AsyncAgent
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.engine_events import EngineEvent, EngineEventType
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import (
    AgentMessage,
    ToolMessage,
)
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerToolCallsCompletedData,
)
from dayu.engine.contracts.runner_identity import RunnerRequestIdentity
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host.api import EnsureSessionRequest, AttemptStatus, RunStatus
from dayu.host.api import AttemptDispatchSnapshot
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.liveness import HostInstanceIdentity, register_current_instance
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CreateRunningRunInput,
    accept_worker_running_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    RunStartReason,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.tool_runtime import (
    DefaultHostToolFactAcceptPort,
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
)
from dayu.host.run_input import PolicySnapshot, create_tool_enabled_run_input_builder
from dayu.host.tooling import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    default_framework_tool_policy_view,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_ITERATION_ID = "iteration-phase6-toolruntime"
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "phase6-toolruntime"})
_POLICY_DIGEST = "sha256:3333333333333333333333333333333333333333333333333333333333333333"


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 active Run 引用。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终为 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        """

        return None


class _FakeBusinessTool:
    """返回固定 JSON 的 fake business tool。"""

    def __init__(self, meta: ToolResultMeta | None = None) -> None:
        """初始化 fake business tool。

        :param meta: 可选工具结果 meta。
        :returns: ``None``。
        """

        self._meta = meta

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 fake 工具。

        :param call: 单次工具调用请求。
        :param context: 批式工具上下文。
        :returns: 成功工具 outcome。
        """

        del call, context
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"accepted_value": "from-host-toolruntime"},
                meta=self._meta,
            )
        )


@dataclass(slots=True)
class _ScriptedRunner:
    """按调用次数产出 RunnerEvent 的 fake Runner。"""

    scripts: tuple[tuple[RunnerEvent, ...], ...]
    call_count: int = 0
    messages_seen: list[tuple[AgentMessage, ...]] = field(default_factory=list)

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
        *,
        request_identity: RunnerRequestIdentity | None,
    ) -> AsyncIterator[RunnerEvent]:
        """返回脚本化 RunnerEvent 流。

        :param messages: Agent messages。
        :param options: Runner options。
        :param tools: 当前暴露的工具 schemas。
        :param request_identity: 本次逻辑 Runner 调用的请求身份。
        :returns: RunnerEvent 异步迭代器。
        """

        del options, tools, request_identity
        self.messages_seen.append(tuple(messages))
        index = self.call_count
        self.call_count += 1
        if index >= len(self.scripts):
            return self._iter_events(())
        return self._iter_events(self.scripts[index])

    def is_supports_tool_calling(self) -> bool:
        """返回 Runner 支持工具调用。

        :returns: 始终为 ``True``。
        """

        return True

    async def close(self) -> None:
        """关闭 fake runner。

        :returns: ``None``。
        """

    async def _iter_events(
        self, events: tuple[RunnerEvent, ...]
    ) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件。

        :param events: 事件元组。
        :returns: RunnerEvent 异步迭代器。
        """

        for event in events:
            yield event


@pytest.mark.asyncio
async def test_engine_continues_only_after_toolruntime_host_accept(
    tmp_path: Path,
) -> None:
    """Engine 通过 ToolRuntime 获取 accepted 工具结果后继续第二轮。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        tool_runtime = DefaultToolRuntimeFactory(
            EffectiveToolBundleBuilder()
        ).create_tool_runtime(
            ToolRuntimeBuildRequest(
                effective_bundle_request=EffectiveToolBundleBuildRequest(
                    business_tool_bundle=ToolBundle(
                        definitions=(_definition(_FakeBusinessTool()),)
                    ),
                    source_refs=(_source_ref(),),
                    framework_tool_policy=default_framework_tool_policy_view(),
                    policy_snapshot_digest=_POLICY_DIGEST,
                ),
                execution_scope=ToolRuntimeExecutionScope(
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    allow_tool_calls=True,
                ),
                accept_port=DefaultHostToolFactAcceptPort(
                    transaction_runner=store.transaction_runner
                ),
            )
        )
        runner = _ScriptedRunner(
            scripts=(
                _tool_script(_tool_call("tool-call-1")),
                _final_script("done after tool"),
            )
        )
        request = create_tool_enabled_run_input_builder(
            transaction_runner=store.transaction_runner,
            policy_snapshot=_policy_snapshot(),
            tool_runtime_handle=tool_runtime,
        ).build(_snapshot(seeded))
        _accept_worker_running(store.transaction_runner, seeded)
        events = await _collect(
            _AsyncAgent(
                request=request,
                runner=runner,
            )
        )

        assert any(event.type is EngineEventType.FINAL_ANSWER for event in events)
        continuation_messages = runner.messages_seen[1]
        tool_message = continuation_messages[-1]
        assert isinstance(tool_message, ToolMessage)
        assert json.loads(tool_message.content) == {
            "accepted_value": "from-host-toolruntime"
        }
        tool_events = _tool_events(store.transaction_runner)
        assert [row.event_type for row in tool_events] == [
            "TOOL_CALL_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
        ]
        result_payload = json.loads(tool_events[1].payload_json)
        assert result_payload["tool_timing"] == {
            "schema_version": 1,
            "status": "missing_tool_result_meta",
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "duration_source": None,
        }
        run_status, attempt_status = _run_attempt_status(
            store.transaction_runner, seeded
        )
        assert run_status is RunStatus.RUNNING
        assert attempt_status is AttemptStatus.RUNNING


@pytest.mark.asyncio
async def test_toolruntime_result_payload_carries_duration_from_result_meta(
    tmp_path: Path,
) -> None:
    """TOOL_RESULT_ACCEPTED 从 ToolResultMeta 投影稳定 tool_timing。"""

    started_at = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
    finished_at = datetime(2026, 5, 15, 1, 2, 4, 250000, tzinfo=UTC)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        tool_runtime = DefaultToolRuntimeFactory(
            EffectiveToolBundleBuilder()
        ).create_tool_runtime(
            ToolRuntimeBuildRequest(
                effective_bundle_request=EffectiveToolBundleBuildRequest(
                    business_tool_bundle=ToolBundle(
                        definitions=(
                            _definition(
                                _FakeBusinessTool(
                                    ToolResultMeta(
                                        tool_name="fake_tool",
                                        started_at=started_at,
                                        finished_at=finished_at,
                                    )
                                )
                            ),
                        )
                    ),
                    source_refs=(_source_ref(),),
                    framework_tool_policy=default_framework_tool_policy_view(),
                    policy_snapshot_digest=_POLICY_DIGEST,
                ),
                execution_scope=ToolRuntimeExecutionScope(
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    allow_tool_calls=True,
                ),
                accept_port=DefaultHostToolFactAcceptPort(
                    transaction_runner=store.transaction_runner
                ),
            )
        )
        _accept_worker_running(store.transaction_runner, seeded)

        outcome = await tool_runtime.tool_executor.execute(
            _tool_request(seeded, _tool_call("tool-call-duration"))
        )
        tool_events = _tool_events(store.transaction_runner)
        result_payload = json.loads(tool_events[1].payload_json)

        assert isinstance(outcome.records[0].outcome, ToolCompletedOutcome)
        assert [row.event_type for row in tool_events] == [
            "TOOL_CALL_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
        ]
        assert result_payload["tool_timing"] == {
            "schema_version": 1,
            "status": "available",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": 1250,
            "duration_source": "tool_result_meta",
        }


@pytest.mark.asyncio
async def test_fetch_more_uses_same_toolruntime_accept_eventlog_path(
    tmp_path: Path,
) -> None:
    """fetch_more 作为普通工具通过 ToolExecutor 与 accept barrier 写 EventLog。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        tool_runtime = DefaultToolRuntimeFactory(
            EffectiveToolBundleBuilder()
        ).create_tool_runtime(
            ToolRuntimeBuildRequest(
                effective_bundle_request=EffectiveToolBundleBuildRequest(
                    business_tool_bundle=ToolBundle(
                        definitions=(
                            _definition(
                                _FakeBusinessTool(),
                                truncate=_truncate_spec(),
                            ),
                        )
                    ),
                    source_refs=(_source_ref(),),
                    framework_tool_policy=FrameworkToolPolicyView(
                        reserved_framework_tool_names=frozenset(
                            {FrameworkToolName.FETCH_MORE}
                        ),
                        enabled_framework_tools=frozenset(
                            {FrameworkToolName.FETCH_MORE}
                        ),
                    ),
                    policy_snapshot_digest=_POLICY_DIGEST,
                    enable_truncation_manager=True,
                ),
                execution_scope=ToolRuntimeExecutionScope(
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    allow_tool_calls=True,
                ),
                accept_port=DefaultHostToolFactAcceptPort(
                    transaction_runner=store.transaction_runner
                ),
            )
        )
        _accept_worker_running(store.transaction_runner, seeded)

        first = await tool_runtime.tool_executor.execute(
            _tool_request(seeded, _tool_call("tool-call-1"))
        )
        first_outcome = first.records[0].outcome
        assert isinstance(first_outcome, ToolCompletedOutcome)
        first_value = first_outcome.result.value
        assert isinstance(first_value, dict)
        fetch_more_ref = first_value["accepted_value"]
        assert isinstance(fetch_more_ref, dict)
        fetch_more_args = fetch_more_ref["fetch_more"]
        assert isinstance(fetch_more_args, dict)
        cursor = fetch_more_args["cursor"]
        scope_token = fetch_more_args["scope_token"]
        assert isinstance(cursor, str)
        assert isinstance(scope_token, str)

        second = await tool_runtime.tool_executor.execute(
            _tool_request(
                seeded,
                _fetch_more_call("fetch-call-1", cursor, scope_token),
            )
        )

        second_outcome = second.records[0].outcome
        assert isinstance(second_outcome, ToolCompletedOutcome)
        assert second_outcome.result.value == "-toolruntime"
        tool_events = _tool_events(store.transaction_runner)
        assert [row.event_type for row in tool_events] == [
            "TOOL_CALL_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
            "TOOL_CALL_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
        ]
        payloads = [json.loads(row.payload_json) for row in tool_events]
        assert payloads[0]["tool_name"] == "fake_tool"
        assert payloads[2]["tool_name"] == "fetch_more"


async def _collect(agent: _AsyncAgent) -> list[EngineEvent]:
    """收集 Engine events。

    :param agent: Engine Agent。
    :returns: EngineEvent 列表。
    """

    events: list[EngineEvent] = []
    async for event in agent.run_messages():
        events.append(event)
    return events


def _tool_script(*tool_calls: ToolCallRequest) -> tuple[RunnerEvent, ...]:
    """构造工具调用脚本。

    :param tool_calls: 工具调用请求。
    :returns: Runner events。
    """

    return (
        _event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=None,
                reasoning_content=None,
            ),
        ),
        _event(
            RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
            RunnerToolCallsCompletedData(tool_calls=tool_calls),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(
                finish_reason=FinishReason.TOOL_CALLS,
                provider_request_id=None,
            ),
        ),
    )


def _final_script(content: str) -> tuple[RunnerEvent, ...]:
    """构造最终回答脚本。

    :param content: 最终回答。
    :returns: Runner events。
    """

    return (
        _event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=content,
                reasoning_content=None,
            ),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
        ),
    )


def _event(event_type: RunnerEventType, data: RunnerEventData) -> RunnerEvent:
    """构造 RunnerEvent。

    :param event_type: 事件类型。
    :param data: 事件数据。
    :returns: RunnerEvent。
    """

    return RunnerEvent(type=event_type, data=data, occurred_at=_NOW)


def _tool_call(tool_call_id: str) -> ToolCallRequest:
    """构造工具调用请求。

    :param tool_call_id: 工具调用 id。
    :returns: ToolCallRequest。
    """

    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name="fake_tool",
        arguments={"ticker": "DAYU"},
        index_in_iteration=0,
        provider_state=None,
    )


def _definition(
    callable_: _FakeBusinessTool,
    truncate: ToolTruncateSpec | None = None,
) -> ToolDefinition:
    """构造 fake tool definition。

    :param callable_: fake business tool。
    :param truncate: 可选截断声明。
    :returns: ToolDefinition。
    """

    return ToolDefinition(
        name="fake_tool",
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name="fake_tool",
                description="fake business tool",
                parameters=_parameters(),
            ),
        ),
        callable=callable_,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=truncate,
        display=None,
        tags=("test",),
    )


def _truncate_spec() -> ToolTruncateSpec:
    """构造 integration test 用截断声明。

    :returns: text_chars 截断声明。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": 9},
        target_field="accepted_value",
        field_path=None,
        ttl_seconds=None,
    )


def _tool_request(
    seeded: _SeededRun, call: ToolCallRequest
) -> BatchToolExecutionRequest:
    """构造 ToolRuntime 直接执行请求。

    :param seeded: active Run refs。
    :param call: 工具调用。
    :returns: 批式工具请求。
    """

    return BatchToolExecutionRequest(
        calls=(call,),
        context=BatchToolExecutionContext(
            run_id=seeded.run_id,
            session_id=seeded.session_id,
            iteration_id=_ITERATION_ID,
            timeout_seconds=10.0,
            cancellation_token=_OpenCancellationToken(),
            correlation_id="correlation-fetch-more",
        ),
    )


def _fetch_more_call(
    tool_call_id: str, cursor: str, scope_token: str
) -> ToolCallRequest:
    """构造 fetch_more 工具调用。

    :param tool_call_id: 工具调用 id。
    :param cursor: cursor。
    :param scope_token: scope token。
    :returns: ToolCallRequest。
    """

    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name=FrameworkToolName.FETCH_MORE.value,
        arguments={"cursor": cursor, "scope_token": scope_token},
        index_in_iteration=0,
        provider_state=None,
    )


def _parameters() -> ToolParametersSchema:
    """构造工具参数 schema。

    :returns: 参数 schema。
    """

    return ToolParametersSchema(
        type="object",
        properties={"ticker": {"type": "string"}},
        required=("ticker",),
        additional_properties=False,
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造工具来源引用。

    :returns: ToolBundleSourceRef。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="phase6-integration",
    )


def _policy_snapshot() -> PolicySnapshot:
    """构造 tool-enabled RunInputBuilder policy snapshot。

    :returns: PolicySnapshot。
    """

    return PolicySnapshot(
        runner_spec=RunnerSpec(
            provider="openai",
            model="model",
            endpoint="https://example.test/v1/chat/completions",
            api_key_ref="TEST_KEY",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
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
            max_iterations=2,
            continuation_max_attempts=1,
            allow_tool_calls=True,
            tool_execution_timeout_seconds=10.0,
        ),
        policy_snapshot_ref="phase6-policy",
    )


def _snapshot(seeded: _SeededRun) -> AttemptDispatchSnapshot:
    """构造 RunInputBuilder dispatch snapshot。

    :param seeded: active Run refs。
    :returns: AttemptDispatchSnapshot。
    """

    return AttemptDispatchSnapshot(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        dispatch_record_id=seeded.dispatch_record_id,
        execution_target="target-phase6",
        policy_snapshot_ref="phase6-policy",
        cancellation_token=_OpenCancellationToken(),
    )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: HostDurableStoreOptions。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        create_parent_dirs=True,
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=1.0,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _seed_active_run(transaction_runner: HostTransactionRunner) -> _SeededRun:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :returns: seeded run。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="phase6", metadata=()),
    ).snapshot.session_id
    seeded = _SeededRun(
        session_id=session_id,
        run_id="run-phase6-toolruntime",
        attempt_id="attempt-phase6-toolruntime",
        execution_id="execution-phase6-toolruntime",
        dispatch_record_id="dispatch-phase6-toolruntime",
    )

    def _operation(transaction: HostTransaction) -> None:
        """写入 active Run 所需 durable rows。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-phase6-test",
                pid=1,
                process_start_token="test-process",
                boot_id=None,
            ),
        )
        input_event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-input-phase6",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-phase6",
                idempotency_key="idem-phase6-input",
                policy_decision=None,
                reason=None,
                payload_json={
                    "display_text": "hello",
                    "operation_kind": "analyze",
                    "execution_target": "target-phase6",
                },
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id=seeded.run_id,
                client_request_id="client-phase6",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-phase6",
                run_started_event_id="event-run-started-phase6",
                attempt_started_event_id="event-attempt-started-phase6",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-phase6",
                execution_target="target-phase6",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-phase6-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-phase6-test",
            lane_name="llm",
            lane_claim_id="claim-phase6",
            lane_owner_id="owner-phase6",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )

    transaction_runner.run_write(_operation)
    return seeded


def _accept_worker_running(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> None:
    """把 seeded Attempt 推进到 worker accepted / RUNNING。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run refs。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """写入 worker accepted transition。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                attempt_running_event_id="event-attempt-running-phase6",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
                local_worker_id="local-worker-phase6",
            ),
        )

    transaction_runner.run_write(_operation)


def _tool_events(transaction_runner: HostTransactionRunner) -> tuple[EventLogRow, ...]:
    """读取工具 canonical EventLog rows。

    :param transaction_runner: Host transaction runner。
    :returns: 工具事件 rows。
    """

    def _operation(transaction: HostTransaction) -> tuple[EventLogRow, ...]:
        """读取工具事件。

        :param transaction: Host transaction。
        :returns: 工具事件 rows。
        """

        return tuple(
            row
            for row in EventLogStore().read_events_after(transaction, 0, limit=100)
            if row.event_type.startswith("TOOL_")
        )

    return transaction_runner.run_read(_operation)


def _run_attempt_status(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> tuple[RunStatus, AttemptStatus]:
    """读取 Run / Attempt 状态。

    :param transaction_runner: Host transaction runner。
    :param seeded: active Run refs。
    :returns: RunStatus 与 AttemptStatus。
    """

    def _operation(transaction: HostTransaction) -> tuple[RunStatus, AttemptStatus]:
        """读取状态。

        :param transaction: Host transaction。
        :returns: RunStatus 与 AttemptStatus。
        :raises AssertionError: row 缺失时抛出。
        """

        run = read_run_by_id(transaction, seeded.run_id)
        attempt = read_attempt_by_id(transaction, seeded.attempt_id)
        assert run is not None
        assert attempt is not None
        return run.status, attempt.status

    return transaction_runner.run_read(_operation)
