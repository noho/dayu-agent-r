"""P10.5 public ``open_host`` options 与 typed event 契约测试。"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from dataclasses import fields, is_dataclass, replace
from typing import Protocol, cast

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    CompactorExecutionBaseline,
    HostEvent,
    HostEventKind,
    HostFinalAnswerView,
    HostTerminalStatus,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OrdinaryRunExecutionBaseline,
    open_host,
)
from dayu.host.memory import default_memory_projection_policy


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

    def cancel(self, reason: str) -> None:
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
        host_handle_id="host-1",
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
        compactor_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
    )


def test_open_host_option_types_are_frozen_slots_dataclasses() -> None:
    """opener options 与 baseline 类型保持 frozen slots dataclass。"""

    for dataclass_type in (
        cast(_FrozenSlotsDataclassClass, OrdinaryRunExecutionBaseline),
        cast(_FrozenSlotsDataclassClass, CompactorExecutionBaseline),
        cast(_FrozenSlotsDataclassClass, OpenHostOptions),
        cast(_FrozenSlotsDataclassClass, HostFinalAnswerView),
        cast(_FrozenSlotsDataclassClass, HostEvent),
    ):
        assert is_dataclass(dataclass_type)
        assert dataclass_type.__dataclass_params__.frozen
        assert dataclass_type.__slots__ == tuple(
            field.name for field in fields(dataclass_type)
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


def test_compactor_baseline_validates_typed_fields(
    tmp_path: pathlib.Path,
) -> None:
    """CompactorExecutionBaseline 拒绝空 policy ref 与错误 Runner 类型。"""

    baseline = CompactorExecutionBaseline(
        context_compactor=None,
        compactor_runner_spec=None,
        compactor_runner_options=None,
        compactor_policy_ref=None,
        compact_artifact_root=tmp_path / "compact",
    )
    assert baseline.compact_artifact_create_parent_dirs
    with pytest.raises(ValueError, match="compactor_policy_ref"):
        replace(baseline, compactor_policy_ref="")
    with pytest.raises(TypeError, match="compactor_runner_spec"):
        replace(baseline, compactor_runner_spec=cast(RunnerSpec, "bad"))


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
        kind=HostEventKind.SUCCEEDED,
        dedupe_key="event-1",
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=final_answer,
        error_message=None,
        cancel_reason=None,
    )
    assert event.final_answer is final_answer

    with pytest.raises(ValueError, match="requires final_answer"):
        HostEvent(
            event_id="event-2",
            event_sequence=2,
            session_id="session-1",
            run_id="run-2",
            kind=HostEventKind.SUCCEEDED,
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
    """Slice 1 opener 可作为 async context manager 导入但不提前接线 runtime。"""

    with pytest.raises(NotImplementedError, match="later P10.5 slice"):
        async with open_host(_options(tmp_path)):
            raise AssertionError("open_host Slice 1 must not yield a runtime handle")
