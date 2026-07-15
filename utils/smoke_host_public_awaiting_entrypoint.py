"""Host public entrypoint 等待态 smoke 脚本。"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dayu.contracts import (
    AsyncDirectToolExecutionCapability,
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolAwaitKind,
    ToolAwaitSpec,
    ToolAwaitingOutcome,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    ToolCallRequest,
    ToolDefinition,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolResultSuccess,
    ToolSchema,
)
from dayu.engine import (
    AgentRunRequest,
    AssistantToolCallBatchSnapshot,
    AwaitingToolExecutionRecord,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    RunSuspendedData,
    ToolAwaitingData,
)
from dayu.host import (
    AttemptDispatchSnapshot,
    AuthorizationClaim,
    EnsureSessionRequest,
    FollowupBehavior,
    HostCallContext,
    Host,
    HostTerminalStatus,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OutboxTerminalCursor,
    ReadOutboxTerminalItemsRequest,
    ResolveWaitCompletedOutcome,
    RunStatus,
    open_host,
)
from dayu.host.durable.codec import parse_utc_timestamp
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import project_host_durable_store_options
from dayu.host.durable.state import (
    WaitPollLastOutcome,
    WaitRecordRow,
    WaitRecordStatus,
    read_active_wait_records_for_run,
    read_wait_record_by_id,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.wait_adapter import (
    WaitAdapterSnapshot,
    WaitExternalJobLifecycleResult,
    WaitExternalJobLifecycleUnsupported,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollReady,
    WaitPollResult,
    WaitPollerRuntimePolicy,
    WaitResumePolicy,
)
from dayu.fins.tools._ingestion_tool_helpers import AwaitingResolutionMode
from dayu.runtime.config_loader import (
    HostRuntimeConfig,
    RuntimeConfig,
    ToolDiscoveryProviderConfig,
)
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    SceneSourceKind,
    SceneSourceRef,
    SceneToolSelectionMode,
    SceneToolSelectionResult,
)
from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityStatus,
    EntrypointTerminalSource,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointRunTerminalResult,
    EntrypointTurnRequest,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.fins_wait_adapter import (
    FINS_DOWNLOAD_AWAITING_TOOL_NAME,
    FINS_INGESTION_WAIT_ADAPTER_KEY,
    FINS_PREPROCESS_AWAITING_TOOL_NAME,
    FINS_UPLOAD_AWAITING_TOOL_NAME,
)
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceOpenHostAssemblyRequest,
    ServiceOpenHostAssemblyResult,
    ServiceRunOverrides,
    assemble_effective_tool_provider_configs,
    compose_open_host_options,
    discover_service_tools,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_CONFIG_ROOT = _PROJECT_ROOT / "dayu" / "config"
_AWAITING_TOOL_NAME = FINS_PREPROCESS_AWAITING_TOOL_NAME
_ADAPTER_KEY = FINS_INGESTION_WAIT_ADAPTER_KEY
_FINS_AWAITING_PROVIDER_IDS = frozenset(
    {
        "financial-download-tools",
        "financial-preprocess-tools",
        "financial-upload-tools",
    }
)
_FINS_AWAITING_TOOL_NAMES = (
    FINS_DOWNLOAD_AWAITING_TOOL_NAME,
    FINS_PREPROCESS_AWAITING_TOOL_NAME,
    FINS_UPLOAD_AWAITING_TOOL_NAME,
)
_LOCAL_PROVIDER_ENV = {
    "DEEPSEEK_API_KEY": "local-smoke-placeholder",
    "MIMO_PLAN_API_KEY": "local-smoke-placeholder",
}
_NOW = datetime(2026, 7, 5, 0, 0, 0, tzinfo=UTC)
_FINAL_ANSWER = "等待任务已完成，已收到轮询恢复结果。"
_RESUME_TOKEN = "service-awaiting-smoke-token"
_SOURCE_REF = ToolBundleSourceRef(
    source_kind=ToolBundleSourceKind.SERVICE_COMPOSITION,
    source_id="utils.smoke_host_public_awaiting_entrypoint",
    version_ref=None,
)
_DEFAULT_WORKSPACE_PARENT = Path("workspace/tmp")
_DEFAULT_WORKSPACE_PREFIX = "host-public-awaiting-entrypoint-smoke"
_DEFAULT_SLOT_KEY_PREFIX = "manual-smoke-awaiting-entrypoint"
_TEST_HANDSHAKE_BUDGET_SECONDS = 0.05
_TEST_ADAPTER_TIMEOUT_SECONDS = 0.15
_TEST_INITIAL_BACKOFF_SECONDS = 0.6
_TEST_EXTERNAL_OPERATION_DURATION_SECONDS = 0.3
_TEST_STATE_POLL_QUANTUM_SECONDS = 0.005
_TEST_RELATIVE_MARGIN_SECONDS = 0.03
_TEST_OVERALL_DEADLINE_SECONDS = 15.0
_TEST_CI_DURATION_CAP_SECONDS = 20.0
_TEST_POLLER_INTERVAL_SECONDS = 0.01
_TEST_CLOSE_DRAIN_SECONDS = 1.0
_TEST_BACKOFF_TOLERANCE_SECONDS = 0.01
_PACKAGED_WAIT_POLICY_SNAPSHOT = (
    True,
    1.0,
    60.0,
    100,
    30.0,
    2.0,
    300.0,
    1.0,
    5.0,
    30.0,
    5.0,
    8,
)
_SMOKE_PHASES = (
    "run_accepted",
    "operation_started",
    "handshake_accepted",
    "durable_waiting",
    "first_observation_entered",
    "first_observation_timeout_released",
    "operation_finished",
    "late_result_released",
    "second_observation_entered",
    "late_publication_dropped",
    "public_terminal_outbox",
)


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """解析后的 smoke 参数。"""

    workspace_root: Path
    keep_workspace: bool


@dataclass(frozen=True, slots=True)
class _CompositionSmokeMatrix:
    """packaged composition smoke 的无网络分支结果。

    :param poll: packaged poll + enabled policy 结果。
    :param manual: active manual providers 结果。
    :param no_provider: 不包含 awaiting provider 的结果。
    :param provider_disabled: awaiting providers 全部 disabled 的结果。
    :param runtime_disabled: active poll + disabled runtime policy 结果。
    """

    poll: ServiceOpenHostAssemblyResult
    manual: ServiceOpenHostAssemblyResult
    no_provider: ServiceOpenHostAssemblyResult
    provider_disabled: ServiceOpenHostAssemblyResult
    runtime_disabled: ServiceOpenHostAssemblyResult


@dataclass(frozen=True, slots=True)
class _SmokeStateSnapshot:
    """phase failure 与状态断言共用的当前 Host 快照。"""

    run_status: RunStatus | None
    wait: WaitRecordRow | None
    terminal_outbox: tuple[str, ...]


@dataclass(slots=True)
class _SmokePhaseContext:
    """单一 overall deadline、phase ledger 与诊断读取上下文。"""

    started_at: float
    deadline: float
    options: OpenHostOptions | None = None
    host: Host | None = None
    session_id: str | None = None
    run_id: str | None = None
    wait_id: str | None = None
    completed_phases: list[str] = field(default_factory=list)
    last_snapshot: _SmokeStateSnapshot | None = None

    def complete(self, phase: str) -> None:
        """把一个具名 phase 记录为已完成。

        :param phase: ``_SMOKE_PHASES`` 中的 phase 名称。
        :returns: ``None``。
        :raises RuntimeError: phase 未登记或发生重复完成时抛出。
        """

        if phase not in _SMOKE_PHASES:
            raise RuntimeError(f"unknown smoke phase: {phase}")
        if phase in self.completed_phases:
            raise RuntimeError(f"smoke phase completed twice: {phase}")
        self.completed_phases.append(phase)


@dataclass(frozen=True, slots=True)
class _ReadWaitRecordOperation:
    """按 cached wait id 或 active Run 读取 smoke wait record。"""

    run_id: str
    wait_id: str | None

    def __call__(self, transaction: HostTransaction) -> WaitRecordRow | None:
        """执行只读 wait record 查询。

        :param transaction: Host durable read transaction。
        :returns: 当前 wait record；尚未创建时返回 ``None``。
        :raises Exception: durable row 损坏或读取失败时透出。
        """

        if self.wait_id is not None:
            return read_wait_record_by_id(transaction, self.wait_id)
        active = read_active_wait_records_for_run(transaction, self.run_id)
        if len(active) > 1:
            raise RuntimeError("smoke run has more than one active wait record")
        if len(active) == 0:
            return None
        return active[0]


class _ExternalOperationController:
    """协调独立 operation、迟到首轮 Ready 与第二轮 authoritative Ready。"""

    def __init__(self) -> None:
        """初始化所有 event、计数与 monotonic timing 字段。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.operation_started = threading.Event()
        self.operation_finished = threading.Event()
        self.first_observation_entered = threading.Event()
        self.late_result_release = threading.Event()
        self.late_result_released = threading.Event()
        self.second_observation_entered = threading.Event()
        self.second_observation_release = threading.Event()
        self.operation_started_at: float | None = None
        self.operation_finished_at: float | None = None
        self.operation_task: asyncio.Task[None] | None = None
        self.poll_call_count = 0
        self._poll_lock = threading.Lock()

    def start_external_operation(self) -> None:
        """在当前 event loop 启动唯一独立 operation task。

        :returns: ``None``。
        :raises RuntimeError: operation 已启动时抛出。
        """

        if self.operation_task is not None:
            raise RuntimeError("external operation started more than once")
        self.operation_task = asyncio.create_task(self._run_external_operation())

    def release_late_result(self) -> None:
        """允许首次 observation 在 operation 完成后返回迟到 Ready。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.late_result_release.set()

    def release_second_observation(self) -> None:
        """允许第二轮 observation 返回 authoritative Ready。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.second_observation_release.set()

    async def finish(self) -> None:
        """等待成功路径 operation task 完成。

        :returns: ``None``。
        :raises Exception: operation task 失败时透出。
        """

        if self.operation_task is None:
            raise RuntimeError("external operation was not started")
        await self.operation_task

    async def abort(self) -> None:
        """解除 provider thread gate 并取消尚未完成的 operation task。

        :returns: ``None``。
        :raises Exception: operation task 的非取消失败透出。
        """

        self.late_result_release.set()
        self.second_observation_release.set()
        self.operation_finished.set()
        task = self.operation_task
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def begin_poll_observation(self) -> int:
        """原子分配当前 poll observation 序号。

        :returns: 从一开始的 observation 序号。
        :raises Exception: 不主动抛出异常。
        """

        with self._poll_lock:
            self.poll_call_count += 1
            return self.poll_call_count

    async def _run_external_operation(self) -> None:
        """运行具名时长的本地独立 operation。

        :returns: ``None``。
        :raises asyncio.CancelledError: smoke cleanup 取消 operation 时透传。
        """

        self.operation_started_at = time.monotonic()
        self.operation_started.set()
        await asyncio.sleep(_TEST_EXTERNAL_OPERATION_DURATION_SECONDS)
        self.operation_finished_at = time.monotonic()
        self.operation_finished.set()


async def run_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int:
    """运行 public entrypoint awaiting smoke。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises RuntimeError: public 行为不符合预期时抛出。
    """

    del env
    started_at = time.monotonic()
    phases = _SmokePhaseContext(
        started_at=started_at,
        deadline=started_at + _TEST_OVERALL_DEADLINE_SECONDS,
    )
    _assert_static_timing_contract()
    interactive_runtime = await _prepare_packaged_entrypoint_runtime(
        workspace_root=args.workspace_root,
        scene_id="interactive",
    )
    prompt_runtime = await _prepare_packaged_entrypoint_runtime(
        workspace_root=args.workspace_root,
        scene_id="prompt",
    )
    composition_matrix = _packaged_composition_matrix(
        workspace_root=args.workspace_root,
        interactive_runtime=interactive_runtime,
        prompt_runtime=prompt_runtime,
    )
    await _open_non_poll_composition_cases(composition_matrix)
    packaged_policy = composition_matrix.poll.options.wait_poller_policy
    if packaged_policy is None:
        raise RuntimeError("packaged poll policy missing")
    _assert_packaged_policy_snapshot(packaged_policy)
    operation = _ExternalOperationController()
    poll_adapter = _TimedLateReadyPollAdapter(operation)
    worker_factory = _AwaitingThenAnswerWorkerFactory(operation)
    options = _deterministic_public_poll_options(
        composition_matrix.poll.options,
        worker_factory=worker_factory,
        poll_adapter=poll_adapter,
    )
    effective_policy = options.wait_poller_policy
    if effective_policy is None:
        raise RuntimeError("test-effective poll policy missing")
    phases.options = options
    scene_inputs = _scene_inputs()
    host_assembly = replace(
        composition_matrix.poll,
        options=options,
        effective_tool_bundle=_tool_bundle(operation),
    )
    accepted_run_ids: list[str] = []
    activities: list[EntrypointActivity] = []
    run_accepted = asyncio.Event()

    print("SMOKE START packaged composition -> Host public awaiting entrypoint")
    print(f"SMOKE WORKSPACE_ROOT {args.workspace_root}")
    print(
        "SMOKE TYPED_PROVIDER_MODES "
        f"poll={AwaitingResolutionMode.POLL.value} "
        f"manual={AwaitingResolutionMode.MANUAL.value} "
        f"callback={AwaitingResolutionMode.CALLBACK.value}"
    )
    print(
        "SMOKE PACKAGED_RUNTIME_POLICY "
        f"{_wait_poller_policy_summary(packaged_policy)}"
    )
    print(
        "SMOKE TEST_EFFECTIVE_RUNTIME_POLICY "
        f"{_wait_poller_policy_summary(effective_policy)}"
    )
    print(
        "SMOKE TEST_TIMING_CONSTANTS "
        f"handshake_budget={_TEST_HANDSHAKE_BUDGET_SECONDS} "
        f"observation_timeout={_TEST_ADAPTER_TIMEOUT_SECONDS} "
        f"operation_target={_TEST_EXTERNAL_OPERATION_DURATION_SECONDS} "
        f"initial_backoff={_TEST_INITIAL_BACKOFF_SECONDS} "
        f"state_poll_quantum={_TEST_STATE_POLL_QUANTUM_SECONDS} "
        f"relative_margin={_TEST_RELATIVE_MARGIN_SECONDS} "
        f"overall_deadline={_TEST_OVERALL_DEADLINE_SECONDS} "
        f"ci_duration_cap={_TEST_CI_DURATION_CAP_SECONDS}"
    )
    print(
        "SMOKE COMPOSITION "
        "poll_registry=true poll_policy=true manual_poller=false "
        "callback_pre_open_failure=true no_provider_poller=false "
        "provider_disabled_poller=false runtime_disabled_poller=false "
        "prompt_interactive_same=true"
    )
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_entrypoint_turn_and_wait")
    print("SMOKE WAIT_RECOVERY production poller via public wait poll adapter registry")

    async with open_host(options) as host:
        phases.host = host
        session = await host.ensure_session(
            EnsureSessionRequest(
                scope="workspace",
                slot_key=f"{_DEFAULT_SLOT_KEY_PREFIX}-{uuid4().hex[:12]}",
                metadata=(),
            )
        )
        phases.session_id = session.session_id
        print(f"SMOKE SESSION_ID {session.session_id}")

        def on_activity(activity: EntrypointActivity) -> None:
            """记录 Service activity。

            :param activity: Service 投影后的 activity。
            :returns: ``None``。
            :raises Exception: 不主动抛出异常。
            """

            activities.append(activity)

        def on_run_accepted(run_id: str) -> None:
            """记录 public accepted Run 并释放 phase wait。

            :param run_id: Host 接受的 Run id。
            :returns: ``None``。
            :raises RuntimeError: public helper 重复回调不同 Run 时抛出。
            """

            if accepted_run_ids and accepted_run_ids[0] != run_id:
                raise RuntimeError("entrypoint accepted more than one Run")
            accepted_run_ids.append(run_id)
            phases.run_id = run_id
            run_accepted.set()

        submit_task = asyncio.create_task(
            submit_entrypoint_turn_and_wait(
                host,
                request=_turn_request(session_id=session.session_id),
                scene_inputs=scene_inputs,
                host_assembly=host_assembly,
                on_run_accepted=on_run_accepted,
                on_activity=on_activity,
                poll_interval_seconds=_TEST_STATE_POLL_QUANTUM_SECONDS,
            )
        )
        try:
            await _wait_for_async_event(
                phases,
                phase="run_accepted",
                event=run_accepted,
            )
            _require(len(accepted_run_ids) == 1, message="run acceptance count mismatch")
            accepted_run_id = accepted_run_ids[0]
            print(f"SMOKE ACCEPTED_RUN_ID {accepted_run_id}")
            await _wait_for_thread_event(
                phases,
                phase="operation_started",
                event=operation.operation_started,
            )
            await _wait_for_async_event(
                phases,
                phase="handshake_accepted",
                event=worker_factory.handshake_accepted,
            )
            _assert_handshake_timing(worker_factory)
            print(
                "SMOKE HANDSHAKE_ACCEPTED "
                f"elapsed={worker_factory.handshake_elapsed_seconds:.6f} "
                f"budget={_TEST_HANDSHAKE_BUDGET_SECONDS}"
            )

            waiting_state = await _wait_for_state(
                phases,
                phase="durable_waiting",
                predicate=_is_durable_waiting,
            )
            _require(
                waiting_state.wait is not None,
                message="durable WAITING state omitted wait record",
            )
            print("SMOKE OBSERVED_WAITING true")

            await _wait_for_thread_event(
                phases,
                phase="first_observation_entered",
                event=operation.first_observation_entered,
            )
            timeout_state = await _wait_for_state(
                phases,
                phase="first_observation_timeout_released",
                predicate=_is_first_timeout_release,
            )
            _assert_timeout_release_state(timeout_state)
            timeout_wait = timeout_state.wait
            if timeout_wait is None:
                raise RuntimeError("timeout state omitted wait record")
            print(
                "SMOKE FIRST_OBSERVATION_TIMEOUT "
                "run=WAITING wait=WAITING claim_released=true "
                "diagnostic=ADAPTER_ERROR/wait_observation_timeout "
                f"next_observe_at={timeout_wait.poll_next_observe_at} "
                "terminal_outbox=0"
            )

            operation.release_late_result()
            await _wait_for_thread_event(
                phases,
                phase="operation_finished",
                event=operation.operation_finished,
            )
            await operation.finish()
            measured_operation_duration = _measured_operation_duration(operation)
            _assert_measured_timing_contract(measured_operation_duration)
            print(
                "SMOKE OPERATION_DURATION "
                f"measured={measured_operation_duration:.6f} "
                f"handshake_budget={_TEST_HANDSHAKE_BUDGET_SECONDS}"
            )
            print(
                "SMOKE TIMING_INEQUALITIES "
                "handshake_plus_margin_lt_observation=true "
                "observation_plus_margin_lt_operation=true "
                "operation_plus_margin_lt_observation_plus_backoff=true "
                "margin_ge_five_state_quanta=true"
            )
            await _wait_for_thread_event(
                phases,
                phase="late_result_released",
                event=operation.late_result_released,
            )
            await _wait_for_thread_event(
                phases,
                phase="second_observation_entered",
                event=operation.second_observation_entered,
            )
            _require(
                not operation.second_observation_release.is_set(),
                message="second observation was released before evidence capture",
            )
            await _wait_for_state(
                phases,
                phase="late_publication_dropped",
                predicate=(
                    _is_late_ready_rejected_at_second_observation_boundary
                ),
            )
            print(
                "SMOKE LATE_READY_REJECTED "
                "second_observation_blocked=true second_claim_active=true "
                "run=WAITING wait=WAITING terminal_outbox=0"
            )
            operation.release_second_observation()
            result = await _wait_for_submit_result(phases, submit_task)

            _require(
                result.source is EntrypointTerminalSource.LIVE_EVENT,
                message=f"terminal source mismatch: {result.source}",
            )
            _require(
                result.run_id == accepted_run_id,
                message=f"terminal run id mismatch: {result.run_id}",
            )
            _require(
                result.terminal_status is HostTerminalStatus.SUCCEEDED,
                message=f"terminal status mismatch: {result.terminal_status}",
            )
            terminal_snapshot = await host.get_run(accepted_run_id)
            _require(
                terminal_snapshot.status is RunStatus.SUCCEEDED,
                message=(
                    "public Run snapshot terminal mismatch: "
                    f"{terminal_snapshot.status}"
                ),
            )
            final_answer = result.final_answer
            if final_answer is None:
                raise RuntimeError("missing final answer")
            _require(final_answer.content.strip() != "", message="blank final answer")
            _require(
                worker_factory.accept_count == 2,
                message=f"worker accept count mismatch: {worker_factory.accept_count}",
            )
            _require(
                operation.poll_call_count == 2,
                message=f"poll observation count mismatch: {operation.poll_call_count}",
            )
            _require(
                any(
                    activity.status is EntrypointActivityStatus.WAITING
                    for activity in activities
                ),
                message="WAITING activity was not recorded",
            )
            print(f"SMOKE TERMINAL_EVENT_ID {result.terminal_event_id}")
            print("SMOKE TERMINAL_STATUS SUCCEEDED")

            batch = await host.read_outbox_terminal_items(
                session.session_id,
                ReadOutboxTerminalItemsRequest(
                    after=OutboxTerminalCursor(event_sequence=0),
                    seen_terminal_event_ids=(),
                    limit=50,
                ),
            )
            matching_items = tuple(
                item
                for item in batch.items
                if item.run_id == accepted_run_id
                and item.terminal_status is HostTerminalStatus.SUCCEEDED
            )
            _require(
                len(matching_items) == 1,
                message=f"terminal outbox match count mismatch: {len(matching_items)}",
            )
            _require(
                matching_items[0].terminal_event_id == result.terminal_event_id,
                message="terminal outbox event id mismatch",
            )
            phases.complete("public_terminal_outbox")
            print("SMOKE OUTBOX_TERMINAL_MATCH true")
            print(f"SMOKE WORKER_ACCEPT_COUNT {worker_factory.accept_count}")
            print(f"SMOKE POLL_OBSERVATION_COUNT {operation.poll_call_count}")
            print(
                "SMOKE PHASES_COMPLETED "
                + ",".join(phases.completed_phases)
            )
            print("SMOKE PASS Host public awaiting entrypoint")
            if args.keep_workspace:
                print("SMOKE WORKSPACE_KEPT true  # smoke never deletes Host artifacts")
            return 0
        finally:
            await operation.abort()
            if not submit_task.done():
                submit_task.cancel()
                try:
                    await submit_task
                except asyncio.CancelledError:
                    pass


async def _prepare_packaged_entrypoint_runtime(
    *, workspace_root: Path, scene_id: str
) -> EntrypointRuntimeResult:
    """通过 packaged ConfigLoader 与共享 Service 路径准备 entrypoint runtime。

    :param workspace_root: smoke workspace 根目录。
    :param scene_id: ``prompt`` 或 ``interactive`` scene id。
    :returns: packaged entrypoint runtime 结果。
    :raises Exception: config、provider discovery、scene 或 composition 失败时透出。
    """

    return await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            explicit_config_dir=None,
            scene_id=scene_id,
            context_slot_values={
                "fins_default_subject": "DAYU",
                "current_time": "2026-07-15 12:00:00 +08:00",
            },
            assembly_overrides=ServiceAssemblyOverrides(),
            env=_LOCAL_PROVIDER_ENV,
        )
    )


def _packaged_composition_matrix(
    *,
    workspace_root: Path,
    interactive_runtime: EntrypointRuntimeResult,
    prompt_runtime: EntrypointRuntimeResult,
) -> _CompositionSmokeMatrix:
    """验证 packaged provider modes 与 runtime policy 的完整装配分支。

    :param workspace_root: smoke workspace 根目录。
    :param interactive_runtime: packaged interactive runtime。
    :param prompt_runtime: packaged prompt runtime。
    :returns: 可用于 public Host open 的 composition matrix。
    :raises RuntimeError: 任一 registry、binding、policy 或 fail-closed 断言不成立。
    """

    poll = interactive_runtime.host_assembly
    prompt_policy = prompt_runtime.host_assembly.options.wait_poller_policy
    _require(poll.options.wait_poller_policy is not None, message="poll policy missing")
    _require(prompt_policy == poll.options.wait_poller_policy, message="prompt/interactive policy diverged")
    _require_poll_bindings(poll, expected_policy=WaitResumePolicy.POLL)

    config = interactive_runtime.runtime_config
    providers = tuple(config.tool_discovery.providers.values())
    manual = _compose_provider_case(
        workspace_root=workspace_root,
        runtime=interactive_runtime,
        config=config,
        provider_configs=_fins_provider_configs(
            providers,
            mode=AwaitingResolutionMode.MANUAL,
            enabled=True,
            include=True,
        ),
    )
    _require(manual.options.wait_poller_policy is None, message="manual policy must be absent")
    _require_poll_bindings(manual, expected_policy=WaitResumePolicy.MANUAL)
    manual_tooling = manual.options.tooling_options
    if manual_tooling is None:
        raise RuntimeError("manual tooling missing")
    _require(
        manual_tooling.wait_poll_adapter_registry is None,
        message="manual poll registry must be absent",
    )

    no_provider = _compose_provider_case(
        workspace_root=workspace_root,
        runtime=interactive_runtime,
        config=config,
        provider_configs=_fins_provider_configs(
            providers,
            mode=AwaitingResolutionMode.POLL,
            enabled=True,
            include=False,
        ),
    )
    _require(
        no_provider.options.wait_poller_policy is None,
        message="no-provider policy must be absent",
    )

    provider_disabled = _compose_provider_case(
        workspace_root=workspace_root,
        runtime=interactive_runtime,
        config=config,
        provider_configs=_fins_provider_configs(
            providers,
            mode=AwaitingResolutionMode.POLL,
            enabled=False,
            include=True,
        ),
    )
    _require(
        provider_disabled.options.wait_poller_policy is None,
        message="provider-disabled policy must be absent",
    )

    runtime_disabled = _compose_provider_case(
        workspace_root=workspace_root,
        runtime=interactive_runtime,
        config=_runtime_config_with_wait_poller_enabled(config, enabled=False),
        provider_configs=_fins_provider_configs(
            providers,
            mode=AwaitingResolutionMode.POLL,
            enabled=True,
            include=True,
        ),
    )
    disabled_policy = runtime_disabled.options.wait_poller_policy
    if disabled_policy is None:
        raise RuntimeError("runtime-disabled policy missing")
    _require(not disabled_policy.enabled, message="runtime-disabled policy was enabled")
    _require_poll_bindings(runtime_disabled, expected_policy=WaitResumePolicy.POLL)

    callback_configs = _fins_provider_configs(
        providers,
        mode=AwaitingResolutionMode.CALLBACK,
        enabled=True,
        include=True,
    )
    try:
        _compose_provider_case(
            workspace_root=workspace_root,
            runtime=interactive_runtime,
            config=config,
            provider_configs=callback_configs,
        )
    except ValueError as exc:
        _require(
            "authenticated callback transport" in str(exc),
            message=f"callback failure mismatch: {exc}",
        )
    else:
        raise RuntimeError("callback composition did not fail before open_host")

    return _CompositionSmokeMatrix(
        poll=poll,
        manual=manual,
        no_provider=no_provider,
        provider_disabled=provider_disabled,
        runtime_disabled=runtime_disabled,
    )


def _compose_provider_case(
    *,
    workspace_root: Path,
    runtime: EntrypointRuntimeResult,
    config: RuntimeConfig,
    provider_configs: tuple[ToolDiscoveryProviderConfig, ...],
) -> ServiceOpenHostAssemblyResult:
    """通过真实 provider discovery 与 Service composition 构造一个矩阵分支。

    :param workspace_root: smoke workspace 根目录。
    :param runtime: packaged entrypoint runtime，复用其 location 与 scene input。
    :param config: 当前分支的 typed runtime config。
    :param provider_configs: 当前分支的 provider owner inputs。
    :returns: Service Host assembly 结果。
    :raises Exception: provider discovery 或 composition 失败时透出。
    """

    discovered = discover_service_tools(
        assemble_effective_tool_provider_configs(
            provider_configs,
            workspace_root=workspace_root,
        )
    )
    return compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=workspace_root,
            config=config,
            locations=runtime.locations,
            scene_inputs=runtime.scene_inputs,
            discovered_tools=discovered,
            overrides=ServiceAssemblyOverrides(),
            env=_LOCAL_PROVIDER_ENV,
        )
    )


def _fins_provider_configs(
    provider_configs: Sequence[ToolDiscoveryProviderConfig],
    *,
    mode: AwaitingResolutionMode,
    enabled: bool,
    include: bool,
) -> tuple[ToolDiscoveryProviderConfig, ...]:
    """构造 smoke 分支的 Fins provider owner inputs。

    :param provider_configs: packaged provider configs。
    :param mode: 写入 owner config 的 closed typed mode。
    :param enabled: awaiting providers 是否启用。
    :param include: 是否保留 awaiting providers；``False`` 表示 no-provider。
    :returns: 只在 Fins awaiting provider owner input 上变化的 configs。
    :raises Exception: 不主动抛出异常。
    """

    resolved: list[ToolDiscoveryProviderConfig] = []
    for provider in provider_configs:
        if provider.provider_id not in _FINS_AWAITING_PROVIDER_IDS:
            resolved.append(provider)
            continue
        if not include:
            continue
        provider_config = dict(provider.config)
        provider_config["awaiting_resolution_mode"] = mode.value
        resolved.append(replace(provider, enabled=enabled, config=provider_config))
    return tuple(resolved)


def _runtime_config_with_wait_poller_enabled(
    config: RuntimeConfig, *, enabled: bool
) -> RuntimeConfig:
    """为 smoke 分支替换选中 runtime 的 typed policy enabled 值。

    :param config: ConfigLoader 产出的完整 runtime config。
    :param enabled: 分支期望的 runtime policy 开关。
    :returns: 除 typed enabled 字段外保持不变的 runtime config。
    :raises Exception: packaged 默认 runtime 缺失时由映射访问抛出。
    """

    runtime_id = config.host_runtime.default_host_runtime_id
    profile = config.host_runtime.runtimes[runtime_id]
    runtimes = dict(config.host_runtime.runtimes)
    runtimes[runtime_id] = replace(
        profile,
        wait_poller_policy=replace(profile.wait_poller_policy, enabled=enabled),
    )
    return replace(
        config,
        host_runtime=HostRuntimeConfig(
            default_host_runtime_id=runtime_id,
            runtimes=runtimes,
        ),
    )


def _require_poll_bindings(
    assembly: ServiceOpenHostAssemblyResult,
    *,
    expected_policy: WaitResumePolicy,
) -> None:
    """断言三个 packaged Fins awaiting binding 的精确 resume policy。

    :param assembly: Service assembly 结果。
    :param expected_policy: 当前分支期望的 Host resume policy。
    :returns: ``None``。
    :raises RuntimeError: tooling、registry 或任一 binding 不符合预期。
    """

    tooling = assembly.options.tooling_options
    if tooling is None:
        raise RuntimeError("Fins tooling missing")
    registry = tooling.wait_adapter_registry
    if registry is None:
        raise RuntimeError("Fins wait binding registry missing")
    for tool_name in _FINS_AWAITING_TOOL_NAMES:
        binding = registry.resolve_binding(
            tool_name=tool_name,
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
        )
        if binding is None:
            raise RuntimeError(f"binding missing: {tool_name}")
        _require(
            binding.resume_policy is expected_policy,
            message=f"binding policy mismatch: {tool_name}",
        )


async def _open_non_poll_composition_cases(
    matrix: _CompositionSmokeMatrix,
) -> None:
    """通过 public Host opener 验证无 poller 与 disabled 分支均可安全打开关闭。

    :param matrix: 已验证的 packaged composition matrix。
    :returns: ``None``。
    :raises Exception: 任一 public Host open/close 失败时透出。
    """

    for assembly in (
        matrix.manual,
        matrix.no_provider,
        matrix.provider_disabled,
        matrix.runtime_disabled,
    ):
        async with open_host(assembly.options):
            pass


def _deterministic_public_poll_options(
    options: OpenHostOptions,
    *,
    worker_factory: _AwaitingThenAnswerWorkerFactory,
    poll_adapter: _TimedLateReadyPollAdapter,
) -> OpenHostOptions:
    """在真实 composition 结果上替换无网络 deterministic execution driver。

    :param options: packaged Service composition 产出的 public Host options。
    :param worker_factory: deterministic local worker factory。
    :param poll_adapter: deterministic timeout/late-ready observation driver。
    :returns: 仅替换测试所需 timing 与无网络 driver 的 public Host options。
    :raises RuntimeError: packaged tooling、poll registry 或 policy 缺失时抛出。
    """

    tooling = options.tooling_options
    if tooling is None:
        raise RuntimeError("packaged poll tooling missing")
    packaged_poll_registry = tooling.wait_poll_adapter_registry
    if packaged_poll_registry is None:
        raise RuntimeError("packaged poll registry missing")
    packaged_policy = options.wait_poller_policy
    if packaged_policy is None:
        raise RuntimeError("packaged poll policy missing")
    _require(
        packaged_poll_registry.resolve_adapter(_ADAPTER_KEY) is not None,
        message="packaged Fins poll adapter missing",
    )
    deterministic_tooling = replace(
        tooling,
        business_tool_bundle=_tool_bundle(worker_factory.operation),
        wait_activation_registry=None,
        wait_poll_adapter_registry=WaitPollAdapterRegistry(
            (
                WaitPollAdapterRegistration(
                    adapter_key=_ADAPTER_KEY,
                    adapter=poll_adapter,
                ),
            )
        ),
    )
    return replace(
        options,
        worker_factory=worker_factory,
        tooling_options=deterministic_tooling,
        wait_poller_policy=replace(
            packaged_policy,
            poll_interval_seconds=_TEST_POLLER_INTERVAL_SECONDS,
            backoff_initial_delay_seconds=_TEST_INITIAL_BACKOFF_SECONDS,
            backoff_max_delay_seconds=_TEST_INITIAL_BACKOFF_SECONDS,
            not_ready_observe_interval_seconds=_TEST_POLLER_INTERVAL_SECONDS,
            idle_poll_interval_seconds=_TEST_POLLER_INTERVAL_SECONDS,
            adapter_call_timeout_seconds=_TEST_ADAPTER_TIMEOUT_SECONDS,
            close_drain_timeout_seconds=_TEST_CLOSE_DRAIN_SECONDS,
        ),
    )


def _wait_poller_policy_summary(policy: WaitPollerRuntimePolicy) -> str:
    """格式化不含凭证的完整 wait poller policy snapshot。

    :param policy: Service composition 产出的 typed policy。
    :returns: 十二字段紧凑摘要。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"enabled={policy.enabled} poll={policy.poll_interval_seconds} "
        f"claim_ttl={policy.claim_ttl_seconds} claim_batch={policy.claim_batch_size} "
        f"backoff_initial={policy.backoff_initial_delay_seconds} "
        f"backoff_multiplier={policy.backoff_multiplier} "
        f"backoff_max={policy.backoff_max_delay_seconds} "
        f"not_ready={policy.not_ready_observe_interval_seconds} "
        f"idle={policy.idle_poll_interval_seconds} "
        f"adapter_timeout={policy.adapter_call_timeout_seconds} "
        f"close_drain={policy.close_drain_timeout_seconds} "
        f"max_outstanding={policy.max_outstanding_adapter_calls}"
    )


def _assert_packaged_policy_snapshot(policy: WaitPollerRuntimePolicy) -> None:
    """断言 ConfigLoader 产出的 packaged policy 精确十二字段快照。

    :param policy: 未施加 smoke timing override 的 packaged policy。
    :returns: ``None``。
    :raises RuntimeError: 任一字段偏离已发布默认值时抛出。
    """

    actual = (
        policy.enabled,
        policy.poll_interval_seconds,
        policy.claim_ttl_seconds,
        policy.claim_batch_size,
        policy.backoff_initial_delay_seconds,
        policy.backoff_multiplier,
        policy.backoff_max_delay_seconds,
        policy.not_ready_observe_interval_seconds,
        policy.idle_poll_interval_seconds,
        policy.adapter_call_timeout_seconds,
        policy.close_drain_timeout_seconds,
        policy.max_outstanding_adapter_calls,
    )
    _require(
        actual == _PACKAGED_WAIT_POLICY_SNAPSHOT,
        message=(
            "packaged wait policy snapshot mismatch: "
            f"actual={actual!r} expected={_PACKAGED_WAIT_POLICY_SNAPSHOT!r}"
        ),
    )


def _assert_static_timing_contract() -> None:
    """在启动 Host 前校验所有静态 timing 常量的相对关系。

    :returns: ``None``。
    :raises RuntimeError: 任一预算关系不足以区分 phase 时抛出。
    """

    _require(
        _TEST_OVERALL_DEADLINE_SECONDS <= _TEST_CI_DURATION_CAP_SECONDS,
        message="overall deadline exceeds CI duration cap",
    )
    _require(
        _TEST_HANDSHAKE_BUDGET_SECONDS + _TEST_RELATIVE_MARGIN_SECONDS
        < _TEST_ADAPTER_TIMEOUT_SECONDS,
        message="handshake budget is not separated from observation timeout",
    )
    _require(
        _TEST_ADAPTER_TIMEOUT_SECONDS + _TEST_RELATIVE_MARGIN_SECONDS
        < _TEST_EXTERNAL_OPERATION_DURATION_SECONDS,
        message="target operation does not outlive observation timeout",
    )
    _require(
        _TEST_EXTERNAL_OPERATION_DURATION_SECONDS + _TEST_RELATIVE_MARGIN_SECONDS
        < _TEST_ADAPTER_TIMEOUT_SECONDS + _TEST_INITIAL_BACKOFF_SECONDS,
        message="target operation does not finish before the real retry due time",
    )
    _require(
        _TEST_RELATIVE_MARGIN_SECONDS
        >= 5 * _TEST_STATE_POLL_QUANTUM_SECONDS,
        message="relative timing margin is smaller than five state quanta",
    )


def _assert_handshake_timing(
    factory: _AwaitingThenAnswerWorkerFactory,
) -> None:
    """断言 worker 收到命名预算且 awaiting 握手在预算内完成。

    :param factory: 记录握手 timing 的 worker factory。
    :returns: ``None``。
    :raises RuntimeError: 缺少 timing 或耗时越过握手预算时抛出。
    """

    elapsed = factory.handshake_elapsed_seconds
    if elapsed is None:
        raise RuntimeError("awaiting handshake timing was not recorded")
    _require(
        elapsed < _TEST_HANDSHAKE_BUDGET_SECONDS,
        message=(
            "accepted awaiting exceeded handshake budget: "
            f"elapsed={elapsed:.6f} "
            f"budget={_TEST_HANDSHAKE_BUDGET_SECONDS:.6f}"
        ),
    )


def _measured_operation_duration(
    operation: _ExternalOperationController,
) -> float:
    """读取独立 operation 的 monotonic 实测时长。

    :param operation: 独立 operation controller。
    :returns: operation 实测秒数。
    :raises RuntimeError: 起止 timing 缺失时抛出。
    """

    started_at = operation.operation_started_at
    finished_at = operation.operation_finished_at
    if started_at is None or finished_at is None:
        raise RuntimeError("external operation timing is incomplete")
    return finished_at - started_at


def _assert_measured_timing_contract(operation_duration_seconds: float) -> None:
    """用 operation 实测时长断言 smoke 的关键相对 timing 关系。

    :param operation_duration_seconds: monotonic 实测 operation 秒数。
    :returns: ``None``。
    :raises RuntimeError: operation 未跨过握手/观察预算或越过 retry due 时抛出。
    """

    _require(
        operation_duration_seconds > _TEST_HANDSHAKE_BUDGET_SECONDS,
        message="external operation did not outlive handshake budget",
    )
    _require(
        _TEST_ADAPTER_TIMEOUT_SECONDS + _TEST_RELATIVE_MARGIN_SECONDS
        < operation_duration_seconds,
        message="external operation did not outlive observation timeout margin",
    )
    _require(
        operation_duration_seconds + _TEST_RELATIVE_MARGIN_SECONDS
        < _TEST_ADAPTER_TIMEOUT_SECONDS + _TEST_INITIAL_BACKOFF_SECONDS,
        message="external operation crossed the first real retry due boundary",
    )


async def _wait_for_async_event(
    phases: _SmokePhaseContext,
    *,
    phase: str,
    event: asyncio.Event,
) -> None:
    """在单一 overall deadline 内等待 asyncio phase event。

    :param phases: deadline、ledger 与诊断上下文。
    :param phase: event 对应 phase 名称。
    :param event: phase owner 发布的 asyncio event。
    :returns: ``None``。
    :raises RuntimeError: overall deadline 耗尽时携带完整 phase 诊断抛出。
    """

    remaining = _remaining_seconds(phases)
    if remaining <= 0.0:
        raise await _phase_failure(phases, phase=phase)
    try:
        await asyncio.wait_for(event.wait(), timeout=remaining)
    except TimeoutError:
        raise await _phase_failure(phases, phase=phase) from None
    phases.complete(phase)


async def _wait_for_thread_event(
    phases: _SmokePhaseContext,
    *,
    phase: str,
    event: threading.Event,
) -> None:
    """在单一 overall deadline 内等待 provider thread phase event。

    :param phases: deadline、ledger 与诊断上下文。
    :param phase: event 对应 phase 名称。
    :param event: provider/operation thread event。
    :returns: ``None``。
    :raises RuntimeError: overall deadline 耗尽时携带完整 phase 诊断抛出。
    """

    remaining = _remaining_seconds(phases)
    if remaining <= 0.0:
        raise await _phase_failure(phases, phase=phase)
    observed = await asyncio.to_thread(event.wait, remaining)
    if not observed:
        raise await _phase_failure(phases, phase=phase)
    phases.complete(phase)


async def _wait_for_state(
    phases: _SmokePhaseContext,
    *,
    phase: str,
    predicate: Callable[[_SmokeStateSnapshot], bool],
) -> _SmokeStateSnapshot:
    """轮询 owner/public state，直到目标谓词成立或 overall deadline 耗尽。

    :param phases: deadline、ledger 与诊断上下文。
    :param phase: 状态谓词对应 phase 名称。
    :param predicate: 只读取 typed snapshot 的目标状态判断。
    :returns: 首个满足谓词的状态快照。
    :raises RuntimeError: overall deadline 耗尽时携带完整 phase 诊断抛出。
    """

    while True:
        snapshot = await _capture_smoke_state(phases)
        phases.last_snapshot = snapshot
        if snapshot.wait is not None:
            phases.wait_id = snapshot.wait.wait_id
        if predicate(snapshot):
            phases.complete(phase)
            return snapshot
        remaining = _remaining_seconds(phases)
        if remaining <= 0.0:
            raise await _phase_failure(phases, phase=phase)
        await asyncio.sleep(
            min(_TEST_STATE_POLL_QUANTUM_SECONDS, remaining)
        )


async def _wait_for_submit_result(
    phases: _SmokePhaseContext,
    submit_task: asyncio.Task[EntrypointRunTerminalResult],
) -> EntrypointRunTerminalResult:
    """在 overall deadline 内等待 public entrypoint terminal 结果。

    :param phases: deadline、ledger 与诊断上下文。
    :param submit_task: public submit-and-wait task。
    :returns: public terminal 结果。
    :raises RuntimeError: overall deadline 耗尽时携带完整 phase 诊断抛出。
    :raises Exception: public submit task 的失败异常透出。
    """

    remaining = _remaining_seconds(phases)
    if remaining <= 0.0:
        raise await _phase_failure(phases, phase="public_terminal_outbox")
    try:
        return await asyncio.wait_for(asyncio.shield(submit_task), timeout=remaining)
    except TimeoutError:
        raise await _phase_failure(
            phases, phase="public_terminal_outbox"
        ) from None


def _remaining_seconds(phases: _SmokePhaseContext) -> float:
    """返回 smoke 单一 overall deadline 的剩余秒数。

    :param phases: deadline 上下文。
    :returns: 可为负数的剩余 monotonic 秒数。
    :raises Exception: 不主动抛出异常。
    """

    return phases.deadline - time.monotonic()


async def _capture_smoke_state(
    phases: _SmokePhaseContext,
) -> _SmokeStateSnapshot:
    """读取 public Run/outbox 与 durable Wait owner state。

    :param phases: 已绑定 Host、storage 与 Run identifiers 的上下文。
    :returns: 当前 smoke state snapshot。
    :raises RuntimeError: 捕获所需上下文缺失时抛出。
    :raises Exception: public/durable read 失败时透出。
    """

    host = phases.host
    options = phases.options
    session_id = phases.session_id
    run_id = phases.run_id
    if host is None or options is None or session_id is None or run_id is None:
        raise RuntimeError("smoke state context is incomplete")
    run = await host.get_run(run_id)
    wait = await asyncio.to_thread(
        _read_wait_record,
        options,
        run_id,
        phases.wait_id,
    )
    outbox = await host.read_outbox_terminal_items(
        session_id,
        ReadOutboxTerminalItemsRequest(
            after=OutboxTerminalCursor(event_sequence=0),
            seen_terminal_event_ids=(),
            limit=50,
        ),
    )
    terminal_outbox = tuple(
        f"{item.run_id}:{item.terminal_status.value}:{item.terminal_event_id}"
        for item in outbox.items
        if item.run_id == run_id
    )
    return _SmokeStateSnapshot(
        run_status=run.status,
        wait=wait,
        terminal_outbox=terminal_outbox,
    )


def _read_wait_record(
    options: OpenHostOptions,
    run_id: str,
    wait_id: str | None,
) -> WaitRecordRow | None:
    """通过独立只读 durable transaction 读取 wait owner state。

    :param options: public Host storage options。
    :param run_id: 当前 public Run id。
    :param wait_id: 已缓存的 wait id；尚未知时为 ``None``。
    :returns: 当前 wait record 或 ``None``。
    :raises Exception: durable store 打开、schema 校验或读取失败时透出。
    """

    with open_host_durable_store(
        project_host_durable_store_options(options)
    ) as store:
        return store.transaction_runner.run_read(
            _ReadWaitRecordOperation(run_id=run_id, wait_id=wait_id)
        )


def _is_durable_waiting(snapshot: _SmokeStateSnapshot) -> bool:
    """判断 public Run 与 durable Wait 是否共同进入 WAITING。

    :param snapshot: 当前 state snapshot。
    :returns: 两个 owner projection 均为 WAITING 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return (
        snapshot.run_status is RunStatus.WAITING
        and snapshot.wait is not None
        and snapshot.wait.status is WaitRecordStatus.WAITING
    )


def _is_first_timeout_release(snapshot: _SmokeStateSnapshot) -> bool:
    """判断首轮 observation timeout 的 durable release 已完整提交。

    :param snapshot: 当前 state snapshot。
    :returns: retryable timeout owner state 已完整可见时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    wait = snapshot.wait
    return (
        snapshot.run_status is RunStatus.WAITING
        and wait is not None
        and wait.status is WaitRecordStatus.WAITING
        and wait.poll_claim_id is None
        and wait.poll_claim_owner_id is None
        and wait.poll_claimed_at is None
        and wait.poll_claim_expires_at is None
        and wait.poll_backoff_attempt == 1
        and wait.poll_last_outcome is WaitPollLastOutcome.ADAPTER_ERROR
        and wait.poll_last_error_code == "wait_observation_timeout"
    )


def _is_late_ready_rejected_at_second_observation_boundary(
    snapshot: _SmokeStateSnapshot,
) -> bool:
    """判断第二轮尚未返回时首轮迟到 Ready 未改写 durable truth。

    :param snapshot: 当前 state snapshot。
    :returns: Run/Wait 仍在等待、第二轮 claim active 且无终态 outbox 时返回
        ``True``。
    :raises Exception: 不主动抛出异常。
    """

    wait = snapshot.wait
    return (
        _is_durable_waiting(snapshot)
        and wait is not None
        and wait.poll_claim_id is not None
        and wait.poll_claim_owner_id is not None
        and wait.poll_claimed_at is not None
        and wait.poll_claim_expires_at is not None
        and wait.poll_backoff_attempt == 1
        and wait.poll_last_outcome is WaitPollLastOutcome.ADAPTER_ERROR
        and wait.poll_last_error_code == "wait_observation_timeout"
        and len(snapshot.terminal_outbox) == 0
    )


def _assert_timeout_release_state(snapshot: _SmokeStateSnapshot) -> None:
    """断言 observation timeout 只写 retry diagnostic，不写 terminal truth。

    :param snapshot: 首轮 timeout release 后的状态快照。
    :returns: ``None``。
    :raises RuntimeError: claim、backoff、diagnostic、abandon 或 outbox 不符时抛出。
    """

    wait = snapshot.wait
    if wait is None:
        raise RuntimeError("timeout release snapshot omitted wait record")
    _require(
        wait.poll_claim_id is None
        and wait.poll_claim_owner_id is None
        and wait.poll_claimed_at is None
        and wait.poll_claim_expires_at is None,
        message="timeout release retained one or more poll claim fields",
    )
    _require(
        wait.poll_backoff_attempt == 1,
        message=f"timeout backoff attempt mismatch: {wait.poll_backoff_attempt}",
    )
    _require(
        wait.poll_last_outcome is WaitPollLastOutcome.ADAPTER_ERROR,
        message=f"timeout last outcome mismatch: {wait.poll_last_outcome}",
    )
    _require(
        wait.poll_last_error_code == "wait_observation_timeout",
        message=f"timeout error code mismatch: {wait.poll_last_error_code}",
    )
    _require(
        wait.poll_last_error_message is not None,
        message="timeout error message was not persisted",
    )
    _require(
        wait.poll_abandoned_at is None,
        message="poll timeout incorrectly wrote poll_abandoned_at",
    )
    _require(
        len(snapshot.terminal_outbox) == 0,
        message=f"poll timeout emitted terminal outbox: {snapshot.terminal_outbox!r}",
    )
    next_observe_at = wait.poll_next_observe_at
    if next_observe_at is None:
        raise RuntimeError("poll timeout omitted next observe time")
    scheduled_delay = (
        parse_utc_timestamp(next_observe_at)
        - parse_utc_timestamp(wait.updated_at)
    ).total_seconds()
    _require(
        abs(scheduled_delay - _TEST_INITIAL_BACKOFF_SECONDS)
        <= _TEST_BACKOFF_TOLERANCE_SECONDS,
        message=(
            "timeout backoff delay mismatch: "
            f"actual={scheduled_delay:.6f} "
            f"expected={_TEST_INITIAL_BACKOFF_SECONDS:.6f}"
        ),
    )


async def _phase_failure(
    phases: _SmokePhaseContext,
    *,
    phase: str,
) -> RuntimeError:
    """构造包含 phase ledger 与 owner state 的 deadline 失败异常。

    :param phases: deadline、ledger 与状态读取上下文。
    :param phase: deadline 命中的目标 phase。
    :returns: 可直接抛出的 RuntimeError。
    :raises Exception: 不主动抛出；诊断读取失败会转成文本。
    """

    snapshot = phases.last_snapshot
    if (
        phases.host is not None
        and phases.options is not None
        and phases.session_id is not None
        and phases.run_id is not None
    ):
        try:
            snapshot = await _capture_smoke_state(phases)
        except Exception as exc:
            capture_error = f"{type(exc).__name__}:{exc}"
        else:
            capture_error = "none"
    else:
        capture_error = "context-incomplete"
    elapsed = time.monotonic() - phases.started_at
    completed = ",".join(phases.completed_phases) or "none"
    pending = ",".join(
        name for name in _SMOKE_PHASES if name not in phases.completed_phases
    )
    if snapshot is None:
        state_text = "run=unknown wait=unknown outbox=unknown"
    else:
        wait = snapshot.wait
        state_text = (
            f"run={snapshot.run_status} "
            f"wait_status={None if wait is None else wait.status} "
            f"claim_id={None if wait is None else wait.poll_claim_id} "
            f"claim_owner={None if wait is None else wait.poll_claim_owner_id} "
            f"claimed_at={None if wait is None else wait.poll_claimed_at} "
            f"claim_expires={None if wait is None else wait.poll_claim_expires_at} "
            f"next_observe={None if wait is None else wait.poll_next_observe_at} "
            f"backoff_attempt={None if wait is None else wait.poll_backoff_attempt} "
            f"last_outcome={None if wait is None else wait.poll_last_outcome} "
            f"last_error_code={None if wait is None else wait.poll_last_error_code} "
            f"poll_abandoned_at={None if wait is None else wait.poll_abandoned_at} "
            f"terminal_outbox={snapshot.terminal_outbox!r}"
        )
    return RuntimeError(
        "smoke overall deadline exhausted "
        f"phase={phase} elapsed={elapsed:.6f} completed={completed} "
        f"pending={pending} capture_error={capture_error} {state_text}"
    )


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: argparse 在参数非法时抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run Host public awaiting entrypoint smoke."
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help=(
            "workspace / project root；默认使用 workspace/tmp 下的 fresh smoke "
            "workspace，避免历史 durable DB schema 污染。"
        ),
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="输出中标记保留 workspace；脚本不会删除 Host/runtime artifacts。",
    )
    namespace = parser.parse_args(list(argv))
    workspace_root_text: str | None = namespace.workspace_root
    keep_workspace: bool = namespace.keep_workspace
    return SmokeArgs(
        workspace_root=_resolve_workspace_root(workspace_root_text),
        keep_workspace=keep_workspace,
    )


def _resolve_workspace_root(workspace_root_text: str | None) -> Path:
    """解析 smoke workspace root。

    :param workspace_root_text: CLI 显式传入的 workspace root；为 ``None`` 时
        生成 fresh smoke workspace root。
    :returns: 归一化后的 workspace root。
    :raises Exception: 不主动抛出异常。
    """

    if workspace_root_text is not None:
        return Path(workspace_root_text).resolve()
    return (
        _DEFAULT_WORKSPACE_PARENT
        / f"{_DEFAULT_WORKSPACE_PREFIX}-{uuid4().hex[:12]}"
    ).resolve()


def _require(condition: bool, *, message: str) -> None:
    """校验 smoke 条件成立。

    :param condition: 待校验条件。
    :param message: 条件不成立时的错误消息。
    :returns: ``None``。
    :raises RuntimeError: 条件不成立时抛出。
    """

    if not condition:
        raise RuntimeError(message)


def _wait_for_poll_adapter_gate(
    event: threading.Event,
    *,
    gate_name: str,
) -> None:
    """在具名有限预算内等待 fake poll adapter 同步门。

    :param event: 由 operation 或 smoke 主流程发布的同步事件。
    :param gate_name: 失败诊断使用的稳定 phase 名称。
    :returns: 事件在预算内发布时返回 ``None``。
    :raises RuntimeError: 等待达到 smoke overall deadline 预算仍未发布时抛出。
    """

    observed = event.wait(timeout=_TEST_OVERALL_DEADLINE_SECONDS)
    if not observed:
        raise RuntimeError(
            "poll adapter gate timed out "
            f"gate={gate_name} "
            f"timeout_seconds={_TEST_OVERALL_DEADLINE_SECONDS}"
        )


class _TimedLateReadyPollAdapter:
    """首轮超时后返回迟到 Ready，第二轮经证据边界释放后返回 Ready。"""

    def __init__(self, operation: _ExternalOperationController) -> None:
        """初始化 adapter。

        :param operation: 独立 operation 与 observation phase controller。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._operation = operation

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """按 observation 序号返回迟到或 authoritative Ready。

        :param snapshot: Host 传入的等待快照；本 smoke 不读取其字段。
        :returns: poll 结果。
        :raises RuntimeError: observation 次数越界、同步门超时或第二轮早于
            operation 完成时抛出。
        """

        del snapshot
        observation_index = self._operation.begin_poll_observation()
        if observation_index == 1:
            self._operation.first_observation_entered.set()
            _wait_for_poll_adapter_gate(
                self._operation.operation_finished,
                gate_name="operation_finished",
            )
            _wait_for_poll_adapter_gate(
                self._operation.late_result_release,
                gate_name="late_result_release",
            )
            self._operation.late_result_released.set()
        elif observation_index == 2:
            self._operation.second_observation_entered.set()
            if not self._operation.operation_finished.is_set():
                raise RuntimeError("second observation preceded operation completion")
            _wait_for_poll_adapter_gate(
                self._operation.second_observation_release,
                gate_name="second_observation_release",
            )
        else:
            raise RuntimeError(
                f"unexpected poll observation index: {observation_index}"
            )
        return WaitPollReady(
            ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"message": "ready"},
                    meta=None,
                ),
                payload_ref=None,
            )
        )

    def abandon_wait(
        self, snapshot: WaitAdapterSnapshot
    ) -> WaitExternalJobLifecycleResult:
        """返回当前 smoke 不支持外部放弃动作。

        :param snapshot: Host 传入的等待快照；本 smoke 不读取其字段。
        :returns: unsupported 结果。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return WaitExternalJobLifecycleUnsupported(reason="not-supported-in-smoke")


class _AwaitingThenAnswerWorkerFactory:
    """第一次运行进入等待态，恢复运行返回最终回答的 worker factory。"""

    def __init__(self, operation: _ExternalOperationController) -> None:
        """初始化 factory。

        :param operation: 独立 operation controller。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.accept_count = 0
        self.operation = operation
        self.handshake_accepted = asyncio.Event()
        self.handshake_elapsed_seconds: float | None = None

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 deterministic worker。

        :param snapshot: 当前运行快照。
        :returns: worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return _AwaitingThenAnswerWorker(self)


class _AwaitingThenAnswerWorker:
    """按运行顺序切换脚本行为的 worker。"""

    _factory: _AwaitingThenAnswerWorkerFactory

    def __init__(self, factory: _AwaitingThenAnswerWorkerFactory) -> None:
        """初始化 worker。

        :param factory: 共享状态。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受一次运行并返回脚本 handle。

        :param snapshot: 当前运行快照。
        :param request: Engine agent 请求。
        :returns: worker handle。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.accept_count += 1
        if self._factory.accept_count == 1:
            return _AwaitingHandle(request=request, factory=self._factory)
        del snapshot
        return _AnswerHandle(request=request)


class _AwaitingHandle:
    """通过 public ToolExecutor 协议产生等待结果的 worker handle。"""

    _request: AgentRunRequest

    def __init__(
        self,
        *,
        request: AgentRunRequest,
        factory: _AwaitingThenAnswerWorkerFactory,
    ) -> None:
        """初始化 handle。

        :param request: Engine agent 请求。
        :param factory: 握手 timing 与 phase signal owner。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._request = request
        self._factory = factory

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "service-awaiting-agent-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """执行 public 工具协议并返回等待事件流。

        :returns: public Engine 事件流。
        :raises Exception: 底层运行失败时透传。
        """

        iteration_id = "awaiting-smoke-iteration"
        tool_call = _awaiting_tool_call()
        batch_snapshot = AssistantToolCallBatchSnapshot(
            iteration_id=iteration_id,
            tool_calls=(tool_call,),
            content=None,
            reasoning_content=None,
            provider_request_id=None,
        )
        request_timeout = (
            self._request.agent_policy.tool_execution_timeout_seconds
        )
        _require(
            request_timeout == _TEST_HANDSHAKE_BUDGET_SECONDS,
            message=f"worker handshake budget mismatch: {request_timeout}",
        )
        handshake_started_at = time.monotonic()
        outcome = await self._request.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(tool_call,),
                context=BatchToolExecutionContext(
                    run_id=self._request.run_id,
                    session_id=self._request.session_id,
                    iteration_id=iteration_id,
                    timeout_seconds=(
                        self._request.agent_policy.tool_execution_timeout_seconds
                    ),
                    cancellation_token=self._request.cancellation_token,
                    correlation_id=f"{self._request.run_id}:{iteration_id}:tool_batch",
                ),
            )
        )
        handshake_elapsed_seconds = time.monotonic() - handshake_started_at
        if len(outcome.records) != 1:
            raise RuntimeError(f"tool execution record count mismatch: {len(outcome.records)}")
        record = outcome.records[0]
        if record.tool_call_id != tool_call.tool_call_id:
            raise RuntimeError(f"tool call id mismatch: {record.tool_call_id}")
        record_outcome = record.outcome
        if not isinstance(record_outcome, ToolAwaitingOutcome):
            raise RuntimeError(
                f"tool outcome type mismatch: {type(record_outcome).__name__}"
            )
        self._factory.handshake_elapsed_seconds = handshake_elapsed_seconds
        self._factory.handshake_accepted.set()
        awaiting_record = AwaitingToolExecutionRecord(
            batch_snapshot=batch_snapshot,
            call=tool_call,
            await_spec=record_outcome.await_spec,
            snapshot=record_outcome.snapshot,
        )
        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.TOOL_AWAITING,
            data=ToolAwaitingData(
                iteration_id=iteration_id,
                record=awaiting_record,
            ),
            metadata=None,
        )
        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.RUN_SUSPENDED,
            data=RunSuspendedData(
                reason=RUN_SUSPENDED_REASON_TOOL_AWAITING,
                resume_hint=None,
                accepted_records=(),
                awaiting_records=(awaiting_record,),
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
        """忽略取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class _AnswerHandle:
    """返回最终回答的 worker handle。"""

    _request: AgentRunRequest

    def __init__(self, *, request: AgentRunRequest) -> None:
        """初始化 handle。

        :param request: Engine agent 请求。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._request = request

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "service-awaiting-answer-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """返回最终回答事件流。

        :returns: public Engine 事件流。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=_FINAL_ANSWER,
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
        """忽略取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class _AwaitingTool:
    """返回等待 outcome 的业务工具。"""

    def __init__(self, operation: _ExternalOperationController) -> None:
        """初始化工具。

        :param operation: 独立 operation controller。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._operation = operation

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行等待型业务工具。

        :param call: 工具调用。
        :param context: 执行上下文。
        :returns: 等待型 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del call, context
        self._operation.start_external_operation()
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token=_RESUME_TOKEN,
            ),
            snapshot=None,
        )


def _awaiting_tool_call() -> ToolCallRequest:
    """构造等待型工具调用请求。

    :returns: 工具调用请求。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id="awaiting-smoke-tool-call",
        name=_AWAITING_TOOL_NAME,
        arguments={"subject": "DAYU"},
        index_in_iteration=0,
        provider_state=None,
    )


def _tool_bundle(operation: _ExternalOperationController) -> ToolBundle:
    """构造等待型业务工具 bundle。

    :param operation: 独立 operation controller。
    :returns: Tool bundle。
    :raises Exception: typed schema 字段非法时由底层抛出。
    """

    return ToolBundle(
        definitions=(
            ToolDefinition(
                name=_AWAITING_TOOL_NAME,
                schema=ToolSchema(
                    type="function",
                    function=ToolFunctionSchema(
                        name=_AWAITING_TOOL_NAME,
                        description="提交一个测试财报观察任务，返回等待态。",
                        parameters=ToolParametersSchema(
                            type="object",
                            properties={
                                "subject": {
                                    "type": "string",
                                    "description": "财报主体名称。",
                                }
                            },
                            required=("subject",),
                            additional_properties=False,
                        ),
                    ),
                ),
                callable=_AwaitingTool(operation),
                truncate=None,
                display=None,
                tags=(),
                execution=AsyncDirectToolExecutionCapability(),
            ),
        )
    )


def _scene_inputs() -> PreparedSceneInputs:
    """构造 Service submit 所需 scene 输入。

    :returns: scene 输入。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return PreparedSceneInputs(
        system_messages=("你是财报分析助手。",),
        system_prompt="你是财报分析助手。",
        tool_selection=SceneToolSelectionResult(
            mode=SceneToolSelectionMode.SELECT,
            tool_names=frozenset({_AWAITING_TOOL_NAME}),
        ),
        model_hints=None,
        agent_policy_override=None,
        fragment_refs=(),
        source_refs=(
            SceneSourceRef(
                source_kind=SceneSourceKind.ASSEMBLY_INPUT,
                source_id="service-awaiting-smoke",
                version_ref=None,
                content_digest="sha256:" + "0" * 64,
            ),
        ),
        content_digest="sha256:" + "1" * 64,
        capability_tags=(),
    )


def _turn_request(*, session_id: str) -> EntrypointTurnRequest:
    """构造 entrypoint turn 请求。

    :param session_id: Host session id。
    :returns: turn 请求。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return EntrypointTurnRequest(
        context=_host_context("awaiting-smoke-submit"),
        session_id=session_id,
        client_request_id="awaiting-smoke-submit",
        user_prompt="请观察测试财报任务。",
        tool_names=frozenset({_AWAITING_TOOL_NAME}),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
        run_overrides=ServiceRunOverrides(
            tool_execution_timeout_seconds=_TEST_HANDSHAKE_BUDGET_SECONDS
        ),
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造 Host 调用上下文。

    :param request_id: 请求 id。
    :returns: Host call context。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor="analyst",
        source="utils.smoke_host_public_awaiting_entrypoint",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="tester"),),
        operation_context=OperationContext(
            operation_name="service_entrypoint_awaiting_smoke",
            operation_kind="manual_smoke",
            business_domain="service",
            business_object_type=None,
            business_object_id=None,
            scenario="wu_semantic_ownership_r05_s2",
            correlation_id=None,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 命令行参数；为 ``None`` 时读取 ``sys.argv[1:]``。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出；异常会被转换为退出码 1。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(run_smoke(args, os.environ))
    except Exception as exc:
        print(f"SMOKE FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
