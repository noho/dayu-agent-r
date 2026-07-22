"""P10.5 public ``open_host`` options 与 typed event 契约测试。"""

from __future__ import annotations

import inspect
import pathlib
from collections.abc import AsyncIterator
from dataclasses import fields, is_dataclass, replace
from typing import Protocol, cast, get_type_hints

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host import (
    AttemptDispatchSnapshot,
    CompactorRunnerBaseline,
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostFinalAnswerView,
    EnsureSessionRequest,
    HostTerminalStatus,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    HostSessionEventDeliveryPolicy,
    OrdinaryRunExecutionBaseline,
    open_host,
)
from dayu.host.api import WaitPollerRuntimePolicy
from dayu.host.memory import default_memory_projection_policy


class _InvalidWaitPollerPolicy:
    """测试用结构完整但字段类型非法的 wait poller policy。"""

    enabled: str = "yes"
    poll_interval_seconds: float = 1.0
    claim_ttl_seconds: float = 60.0
    claim_batch_size: int = 100
    backoff_initial_delay_seconds: float = 30.0
    backoff_multiplier: float = 2.0
    backoff_max_delay_seconds: float = 300.0
    not_ready_observe_interval_seconds: float = 1.0
    idle_poll_interval_seconds: float = 5.0
    adapter_call_timeout_seconds: float = 30.0
    close_drain_timeout_seconds: float = 5.0
    max_outstanding_adapter_calls: int = 8


class _FrozenSlotsDataclassClass(Protocol):
    """测试读取 frozen slots dataclass 参数所需的最小协议。"""

    __dataclass_params__: "_DataclassParams"
    __slots__: tuple[str, ...]


class _DataclassParams(Protocol):
    """测试读取 dataclass frozen 标记所需的最小协议。"""

    frozen: bool


class _WorkerHandle:
    """测试用 worker handle。"""

    @property
    def local_worker_id(self) -> str:
        """返回测试 worker id。

        :returns: 测试 worker id。
        :raises RuntimeError: 测试实现不会抛出。
        """

        return "worker-1"

    def events(self) -> AsyncIterator[EngineEvent]:
        """返回空 EngineEvent 流。

        :returns: 空 EngineEvent async iterator。
        :raises RuntimeError: 测试实现不会抛出。
        """

        return _empty_engine_events()

    async def close(self) -> None:
        """关闭测试 worker handle。

        :returns: ``None``。
        :raises RuntimeError: 测试实现不会抛出。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """取消测试 worker。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises RuntimeError: 测试实现不会抛出。
        """

        return None


async def _empty_engine_events() -> AsyncIterator[EngineEvent]:
    """构造空 EngineEvent 异步迭代器。

    :returns: 空 EngineEvent async iterator。
    :raises RuntimeError: 测试实现不会抛出。
    """

    if False:
        yield cast(EngineEvent, "unreachable")


class _Worker:
    """测试用本地 worker。"""

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受测试 dispatch。

        :param snapshot: dispatch 快照。
        :param request: Engine run 请求。
        :returns: 测试 worker handle。
        :raises RuntimeError: 测试实现不会抛出。
        """

        return _WorkerHandle()


class _WorkerFactory:
    """测试用 worker factory。"""

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建测试 worker。

        :param snapshot: dispatch 快照。
        :returns: 测试 worker。
        :raises RuntimeError: 测试实现不会抛出。
        """

        return _Worker()


def _runner_spec() -> RunnerSpec:
    """构造测试 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _runner_options() -> RunnerCallOptions:
    """构造测试 RunnerCallOptions。

    :returns: RunnerCallOptions。
    """

    return RunnerCallOptions(
        temperature=None,
        max_tokens=None,
        top_p=None,
        stream=False,
    )


def _agent_policy() -> AgentPolicy:
    """构造测试 AgentPolicy。

    :returns: AgentPolicy。
    """

    return AgentPolicy(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=False,
        tool_execution_timeout_seconds=1.0,
        fallback_prompt="test fallback prompt",
        continuation_prompt="test continuation prompt",
    )


def _ordinary_baseline() -> OrdinaryRunExecutionBaseline:
    """构造普通 Run 执行基线。

    :returns: OrdinaryRunExecutionBaseline。
    """

    return OrdinaryRunExecutionBaseline(
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
        agent_policy=_agent_policy(),
    )


def _options(tmp_path: pathlib.Path) -> OpenHostOptions:
    """构造测试 OpenHostOptions。

    :param tmp_path: pytest 临时目录。
    :returns: OpenHostOptions。
    """

    return OpenHostOptions(
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=5.0,
        sqlite_write_busy_retry_count=3,
        sqlite_write_retry_initial_delay_seconds=0.01,
        sqlite_write_retry_backoff_multiplier=2.0,
        sqlite_write_retry_max_delay_seconds=1.0,
        payload_inline_threshold_bytes=4096,
        lane_db_path=tmp_path / "lane.sqlite3",
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.1,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        ordinary_run_baseline=_ordinary_baseline(),
        worker_factory=_WorkerFactory(),
        tooling_options=None,
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


def test_open_host_option_types_are_frozen_slots_dataclasses() -> None:
    """opener options 与 baseline 类型保持 frozen slots dataclass。"""

    for dataclass_type in (
        cast(_FrozenSlotsDataclassClass, OrdinaryRunExecutionBaseline),
        cast(_FrozenSlotsDataclassClass, CompactorRunnerBaseline),
        cast(_FrozenSlotsDataclassClass, HostSessionEventDeliveryPolicy),
        cast(_FrozenSlotsDataclassClass, OpenHostOptions),
        cast(_FrozenSlotsDataclassClass, HostFinalAnswerView),
        cast(_FrozenSlotsDataclassClass, HostEvent),
    ):
        assert is_dataclass(dataclass_type)
        assert dataclass_type.__dataclass_params__.frozen
        assert dataclass_type.__slots__ == tuple(
            field.name for field in fields(dataclass_type)
        )


def test_open_host_options_do_not_accept_removed_active_cancel_budget() -> None:
    """OpenHostOptions 不再暴露或接受已删除的 active cancel 等待预算字段。"""

    field_names = {field.name for field in fields(OpenHostOptions)}
    constructor_parameters = inspect.signature(OpenHostOptions).parameters
    removed_field_name = "active_cancel" + "_timeout_seconds"

    assert removed_field_name not in field_names
    assert removed_field_name not in constructor_parameters


def test_open_host_options_do_not_expose_process_capsule_policy_directly() -> None:
    """process capsule cleanup policy 只能通过 HostToolingOptions 进入。"""

    field_names = {field.name for field in fields(OpenHostOptions)}
    constructor_parameters = inspect.signature(OpenHostOptions).parameters

    assert "process_capsule_interrupt_policy" not in field_names
    assert "process_capsule_interrupt_policy" not in constructor_parameters


def test_open_host_options_type_hints_resolve_wait_poller_policy() -> None:
    """OpenHostOptions runtime type hints 必须能解析 wait poller policy。"""

    hints = get_type_hints(OpenHostOptions)

    assert hints["wait_poller_policy"] == WaitPollerRuntimePolicy | None
    assert (
        hints["session_event_delivery_policy"]
        is HostSessionEventDeliveryPolicy
    )


def test_session_event_delivery_policy_is_required_and_strict(
    tmp_path: pathlib.Path,
) -> None:
    """OpenHostOptions 必须显式接收双字段 typed delivery policy。"""

    parameter = inspect.signature(OpenHostOptions).parameters[
        "session_event_delivery_policy"
    ]
    assert parameter.default is inspect.Parameter.empty
    valid = _options(tmp_path)
    with pytest.raises(TypeError, match="session_event_delivery_policy"):
        replace(
            valid,
            session_event_delivery_policy=cast(
                HostSessionEventDeliveryPolicy,
                "bad",
            ),
        )


def test_open_host_options_reject_invalid_wait_poller_policy(
    tmp_path: pathlib.Path,
) -> None:
    """OpenHostOptions 构造期拒绝非法 wait poller policy。"""

    valid = _options(tmp_path)
    with pytest.raises(TypeError, match="enabled"):
        replace(
            valid,
            wait_poller_policy=cast(
                WaitPollerRuntimePolicy,
                _InvalidWaitPollerPolicy(),
            ),
        )
    with pytest.raises(TypeError, match="wait_poller_policy"):
        replace(
            valid,
            wait_poller_policy=cast(WaitPollerRuntimePolicy, "bad"),
        )


def test_open_host_options_validate_lane_and_baseline(
    tmp_path: pathlib.Path,
) -> None:
    """OpenHostOptions 拒绝非法 lane 与 baseline 输入。"""

    valid = _options(tmp_path)
    with pytest.raises(ValueError, match="lane_claim_ttl_seconds"):
        replace(
            valid,
            lane_claim_ttl_seconds=0.1,
            lane_heartbeat_interval_seconds=0.1,
        )
    with pytest.raises(TypeError, match="ordinary_run_baseline"):
        replace(
            valid,
            ordinary_run_baseline=cast(OrdinaryRunExecutionBaseline, "bad"),
        )


def test_compactor_runner_baseline_validates_typed_fields(
    tmp_path: pathlib.Path,
) -> None:
    """CompactorRunnerBaseline 拒绝错误 Runner、路径与 bool 类型。"""

    baseline = CompactorRunnerBaseline(
        compactor_runner_spec=_runner_spec(),
        compactor_runner_options=_runner_options(),
        compactor_agent_policy=_agent_policy(),
        compactor_system_prompt="test compactor system prompt",
        compactor_user_prompt_template=(
            "test compactor user prompt <<compaction_request>>"
        ),
        compact_artifact_root=tmp_path / "compact",
    )
    assert baseline.compact_artifact_create_parent_dirs
    with pytest.raises(TypeError, match="compactor_runner_spec"):
        replace(baseline, compactor_runner_spec=cast(RunnerSpec, "bad"))
    with pytest.raises(TypeError, match="compactor_agent_policy"):
        replace(baseline, compactor_agent_policy=cast(AgentPolicy, "bad"))
    with pytest.raises(TypeError, match="compact_artifact_root"):
        replace(baseline, compact_artifact_root=cast(pathlib.Path, "bad"))
    with pytest.raises(TypeError, match="compact_artifact_create_parent_dirs"):
        replace(baseline, compact_artifact_create_parent_dirs=cast(bool, 1))
    with pytest.raises(ValueError, match="compactor_system_prompt"):
        replace(baseline, compactor_system_prompt="")
    with pytest.raises(ValueError, match="compactor_user_prompt_template"):
        replace(baseline, compactor_user_prompt_template="")
    assert "compactor_policy_ref" not in {
        field.name for field in fields(CompactorRunnerBaseline)
    }


def test_host_event_terminal_final_answer_contract() -> None:
    """成功 terminal HostEvent 必须内联最终回答视图。"""

    final_answer = HostFinalAnswerView(
        content="完成",
        filtered=False,
        degraded=False,
        finish_reason="stop",
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )
    event = HostEvent(
        event_id="event-1",
        event_sequence=1,
        session_id="session-1",
        run_id="run-1",
        event_class=HostEventClass.CANONICAL_FACT,
        event_type="RUN_SUCCEEDED",
        kind=HostEventKind.SUCCEEDED,
        activity=None,
        dedupe_key="event-1",
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=final_answer,
        error_message=None,
        cancel_reason=None,
    )
    assert event.final_answer is final_answer

    with pytest.raises(ValueError, match="HostFinalAnswerView.content"):
        HostFinalAnswerView(
            content=" \n\t",
            filtered=False,
            degraded=False,
            finish_reason="stop",
            terminal_status=HostTerminalStatus.SUCCEEDED,
        )

    with pytest.raises(ValueError, match="requires final_answer"):
        HostEvent(
            event_id="event-2",
            event_sequence=2,
            session_id="session-1",
            run_id="run-2",
            event_class=HostEventClass.CANONICAL_FACT,
            event_type="RUN_SUCCEEDED",
            kind=HostEventKind.SUCCEEDED,
            activity=None,
            dedupe_key="event-2",
            terminal_status=HostTerminalStatus.SUCCEEDED,
            final_answer=None,
            error_message=None,
            cancel_reason=None,
        )


def test_open_host_rejects_untyped_options() -> None:
    """open_host 入口拒绝非 OpenHostOptions 参数。"""

    with pytest.raises(TypeError, match="OpenHostOptions"):
        open_host(cast(OpenHostOptions, "bad"))


@pytest.mark.asyncio
async def test_open_host_slice1_context_body_is_deferred(
    tmp_path: pathlib.Path,
) -> None:
    """open_host 可作为 async context manager 打开当前公共 runtime。"""

    async with open_host(_options(tmp_path)) as host:
        session = await host.ensure_session(
            EnsureSessionRequest(
                scope="workspace",
                slot_key="open-host-options",
                metadata=(),
            )
        )
        assert session.slot is not None
        assert session.slot.scope == "workspace"
