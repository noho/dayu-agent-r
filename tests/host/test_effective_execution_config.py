"""P10.5 Slice 3 per-run effective execution config 测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessageRole
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    EnsureSessionRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    SubmitFollowupRequest,
    ensure_session as command_ensure_session,
    open_host,
    submit_followup as command_submit_followup,
)
from dayu.host.api import HostCommandHandleOptions
from dayu.host.command import create_host_command_handle
from dayu.host._event_payload import payload_object as _payload_object
from dayu.host._execution_config_projection import (
    required_json_mapping as _required_json_mapping,
)
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventLogRow, EventLogStore
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import default_memory_projection_policy


@dataclass(frozen=True, slots=True)
class _ReadEventById:
    """测试用 EventLog 单事件读取 operation。

    :param event_id: 目标 EventLog id。
    """

    event_id: str

    def __call__(self, transaction: HostTransaction) -> EventLogRow | None:
        """读取目标事件。

        :param transaction: Host durable transaction。
        :returns: EventLog row；缺失时返回 ``None``。
        :raises HostDurableError: durable 读取事件失败时由底层抛出。
        """

        return EventLogStore().read_event_by_id(transaction, self.event_id)


class _FinalHandle:
    """测试用成功终态 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: dispatch snapshot。
        :returns: ``None``。
        :raises: 无主动抛出。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises: 无主动抛出。
        """

        return "slice3-effective-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出 final answer。

        :returns: EngineEvent 异步迭代器。
        :raises: 无主动抛出。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 3, 0, 0, tzinfo=UTC),
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
        :raises: 无主动抛出。
        """

        return None

    def cancel(self, reason: str) -> None:
        """忽略取消。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises: 无主动抛出。
        """

        del reason


class _RecordingWorker:
    """记录 Engine request 与 snapshot 的 worker。"""

    def __init__(self, factory: "_RecordingWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 记录 factory。
        :returns: ``None``。
        :raises: 无主动抛出。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受并记录 request。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: final handle。
        :raises: 无主动抛出。
        """

        self._factory.snapshots.append(snapshot)
        self._factory.requests.append(request)
        self._factory.accepted.set()
        return _FinalHandle(snapshot)


class _RecordingWorkerFactory:
    """记录 worker accept 输入的 factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        :raises: 无主动抛出。
        """

        self.accepted = asyncio.Event()
        self.snapshots: list[AttemptDispatchSnapshot] = []
        self.requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建记录 worker。

        :param snapshot: dispatch snapshot。
        :returns: 记录 worker。
        :raises: 无主动抛出。
        """

        del snapshot
        return _RecordingWorker(self)


@pytest.mark.asyncio
async def test_field_level_partial_merge_uses_baseline_for_omitted_fields(
    tmp_path: pathlib.Path,
) -> None:
    """只传 runner_options 时 runner_spec 与 agent_policy 仍来自 opener baseline。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: effective request 不符合预期时由断言抛出。
    """

    factory = _RecordingWorkerFactory()
    override_options = RunnerCallOptions(
        temperature=0.2,
        max_tokens=321,
        top_p=0.9,
        stream=False,
    )
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request())
        await host.submit_followup(
            session.session_id,
            _followup(
                session.session_id,
                runner_options=override_options,
                system_prompt="system slice3",
            ),
        )
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)

    request = factory.requests[0]
    assert request.runner_spec.model == "baseline-model"
    assert request.runner_options == override_options
    assert request.agent_policy.max_iterations == 2
    assert request.messages[0].role == AgentMessageRole.SYSTEM
    assert request.messages[0].content == "system slice3"


@pytest.mark.asyncio
async def test_effective_config_freezes_override_and_idempotent_replay(
    tmp_path: pathlib.Path,
) -> None:
    """per-run override 冻结到 dispatch snapshot，幂等重放不创建第二次 dispatch。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 冻结配置或幂等行为不符合预期时由断言抛出。
    """

    factory = _RecordingWorkerFactory()
    override_spec = _runner_spec("override-model")
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request())
        request = _followup(session.session_id, runner_spec=override_spec)

        first = await host.submit_followup(session.session_id, request)
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)
        second = await host.submit_followup(session.session_id, request)

    assert first.accepted_run_id == second.accepted_run_id
    assert len(factory.requests) == 1
    assert factory.requests[0].runner_spec.model == "override-model"
    assert factory.snapshots[0].policy_snapshot_ref.startswith("policy:sha256:")


@pytest.mark.asyncio
async def test_agent_policy_override_freezes_payload_and_dispatch_snapshot_ref(
    tmp_path: pathlib.Path,
) -> None:
    """agent_policy override 会冻结进输入 payload，并驱动 dispatch snapshot ref。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: payload 或 dispatch snapshot ref 不符合预期时由断言抛出。
    """

    factory = _RecordingWorkerFactory()
    options = _options(tmp_path, factory)
    override_policy = AgentPolicy(
        max_iterations=7,
        continuation_max_attempts=1,
        allow_tool_calls=False,
        tool_execution_timeout_seconds=3.5,
        max_consecutive_failed_tool_batches=4,
    )
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        accepted = await host.submit_followup(
            session.session_id,
            _followup(
                session.session_id,
                agent_policy=override_policy,
                system_prompt="policy override",
            ),
        )
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)

    payload = _read_event_payload(options, accepted.accepted_input_ref)
    effective_execution = _required_json_mapping(
        payload.get("effective_execution_config"),
        field_name="effective_execution_config",
    )
    config = _required_json_mapping(
        effective_execution.get("config"), field_name="config"
    )
    agent_policy = _required_json_mapping(
        config.get("agent_policy"), field_name="agent_policy"
    )
    sources = _required_json_mapping(config.get("sources"), field_name="sources")

    assert agent_policy["max_iterations"] == 7
    assert agent_policy["continuation_max_attempts"] == 1
    assert agent_policy["tool_execution_timeout_seconds"] == 3.5
    assert agent_policy["max_consecutive_failed_tool_batches"] == 4
    assert sources["agent_policy"] == "request"
    assert sources["runner_spec"] == "opener_baseline"
    assert factory.requests[0].agent_policy == override_policy
    assert (
        factory.snapshots[0].policy_snapshot_ref
        == effective_execution["policy_snapshot_ref"]
    )


@pytest.mark.asyncio
async def test_submit_followup_without_ordinary_baseline_fails_before_dispatch(
    tmp_path: pathlib.Path,
) -> None:
    """低层 command handle 无 ordinary_run_baseline 时 submit_followup 早失败。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 错误码或错误消息不符合预期时由断言抛出。
    """

    handle = create_host_command_handle(_command_options(tmp_path))
    try:
        session = command_ensure_session(handle, _ensure_request())

        with pytest.raises(HostApiError) as exc_info:
            command_submit_followup(
                handle, session.session_id, _followup(session.session_id)
            )
    finally:
        handle.close()

    assert exc_info.value.code == HostApiErrorCode.INVALID_STATE
    assert "ordinary Run baseline" in exc_info.value.message


def _followup(
    session_id: str,
    *,
    runner_spec: RunnerSpec | None = None,
    runner_options: RunnerCallOptions | None = None,
    agent_policy: AgentPolicy | None = None,
    system_prompt: str | None = None,
) -> SubmitFollowupRequest:
    """构造 submit follow-up 请求。

    :param session_id: Session id。
    :param runner_spec: 可选 RunnerSpec override。
    :param runner_options: 可选 RunnerCallOptions override。
    :param agent_policy: 可选 AgentPolicy override。
    :param system_prompt: 可选 system prompt。
    :returns: SubmitFollowupRequest。
    :raises ValueError: 请求字段不满足 SubmitFollowupRequest 契约时抛出。
    """

    return SubmitFollowupRequest(
        context=_context("client-effective"),
        session_id=session_id,
        client_request_id="client-effective",
        system_prompt=system_prompt,
        user_prompt="effective prompt",
        tool_names=None,
        runner_spec=runner_spec,
        runner_options=runner_options,
        agent_policy=agent_policy,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _options(
    tmp_path: pathlib.Path,
    worker_factory: _RecordingWorkerFactory,
) -> OpenHostOptions:
    """构造 OpenHostOptions。

    :param tmp_path: 临时目录。
    :param worker_factory: worker factory。
    :returns: OpenHostOptions。
    :raises TypeError: options typed 字段类型非法时抛出。
    :raises ValueError: options 字段语义非法时抛出。
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
        ordinary_run_baseline=_ordinary_run_baseline(),
        worker_factory=worker_factory,
        tooling_options=None,
        context_budget_policy=None,
        compactor_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
    )


def _command_options(tmp_path: pathlib.Path) -> HostCommandHandleOptions:
    """构造不含 local execution baseline 的低层 command handle options。

    :param tmp_path: 临时目录。
    :returns: HostCommandHandleOptions。
    :raises TypeError: options typed 字段类型非法时抛出。
    :raises ValueError: options 字段语义非法时抛出。
    """

    return HostCommandHandleOptions(
        host_handle_id="slice3-effective-command",
        db_path=tmp_path / "command-host.sqlite3",
        artifact_root=tmp_path / "command-artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        context_window_size=4096,
        reserved_output_tokens=512,
        context_budget_hard_threshold_tokens=None,
        context_budget_minimum_protection_tokens=None,
        local_execution=None,
    )


def _ordinary_run_baseline() -> OrdinaryRunExecutionBaseline:
    """构造测试用 ordinary run baseline。

    :returns: OrdinaryRunExecutionBaseline。
    :raises ValueError: baseline 字段不满足契约时抛出。
    """

    return OrdinaryRunExecutionBaseline(
        runner_spec=_runner_spec("baseline-model"),
        runner_options=RunnerCallOptions(
            temperature=None, max_tokens=None, top_p=None, stream=False
        ),
        agent_policy=AgentPolicy(
            max_iterations=2,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
        ),
    )


def _read_event_payload(
    options: OpenHostOptions, event_id: str
) -> Mapping[str, JsonValue]:
    """读取指定 EventLog row 的 payload object。

    :param options: 打开 Host 时使用的 options。
    :param event_id: 目标 EventLog id。
    :returns: payload JSON mapping。
    :raises AssertionError: 事件缺失时抛出。
    """

    event: EventLogRow | None = None
    with open_host_durable_store(_durable_options(options)) as durable_store:
        event = durable_store.transaction_runner.run_read(_ReadEventById(event_id))
    if event is None:
        raise AssertionError("event must exist")
    return _payload_object(event)


def _durable_options(options: OpenHostOptions) -> HostDurableStoreOptions:
    """从 OpenHostOptions 构造测试读取用 durable options。

    :param options: OpenHostOptions。
    :returns: HostDurableStoreOptions。
    :raises HostDurableConfigError: durable options 字段非法时由底层抛出。
    """

    return HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(
            artifact_root=options.artifact_root,
            payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
            create_artifact_root=options.create_parent_dirs,
        ),
        create_parent_dirs=options.create_parent_dirs,
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


def _ensure_request() -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :returns: EnsureSessionRequest。
    :raises ValueError: ensure session 字段不满足契约时抛出。
    """

    return EnsureSessionRequest(scope="scope", slot_key="slot", metadata=())


def _context(request_id: str) -> HostCallContext:
    """构造 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises ValueError: context 字段不满足契约时抛出。
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


def _runner_spec(model: str) -> RunnerSpec:
    """构造 RunnerSpec。

    :param model: 模型名。
    :returns: RunnerSpec。
    :raises ValueError: RunnerSpec 字段不满足契约时抛出。
    """

    return RunnerSpec(
        provider="test",
        model=model,
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )
