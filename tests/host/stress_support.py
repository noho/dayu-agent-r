"""WU-STRESS-01 Host production stress 测试支撑。

本模块只服务 ``tests/host`` 下的 Host stress suite。它提供结构化
summary、terminal 去重诊断、watch lag 估算和 deterministic worker
基础设施；这些 helper 不进入生产代码，不作为 Host durable truth，
也不替代 public Host snapshot、HostEvent 或 EventLog 的事实来源。
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sqlite3
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from multiprocessing import Process
from typing import Literal, TypeAlias, cast

from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunFailedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.host import (
    AttemptDispatchSnapshot,
    Host,
    HostEvent,
    HostEventKind,
    HostTerminalStatus,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OpenHostOptions,
    RunSnapshot,
    RunStatus,
)
from dayu.host.durable.codec import parse_utc_timestamp
from dayu.host.durable.liveness import HostInstanceStatus
from dayu.runtime.lane import (
    LaneAcquired,
    LaneConfig,
    LaneController,
    LaneOwner,
    SQLiteLaneCoordinatorConfig,
)
from tests.host.public_smoke_support import (
    deterministic_runner_spec,
    open_host_options,
)
from tests.host.recovery_support import (
    AcceptedAttemptMarker,
    attempt_count_for_run as recovery_attempt_count_for_run,
    event_type_count as recovery_event_type_count,
    force_owner_pid_missing_and_heartbeat_stale,
    run_blocking_owner_process,
    run_open_probe_process,
    terminate_process,
    wait_for_accepted_marker,
    wait_for_runtime_lane_claim_ttl_to_expire,
)

StressFailureBoundary: TypeAlias = Literal[
    "durable",
    "scheduler",
    "watch",
    "watch_reconnect",
    "liveness",
    "recovery",
    "projection",
    "active_cleanup",
    "scheduler_close",
    "worker_accept",
    "unknown",
]
"""Host stress 失败边界的封闭诊断集合。"""

StressSummaryJsonValue: TypeAlias = str | int | bool | tuple[int, ...] | None
"""``HostStressSummary`` JSON payload 中允许出现的值类型。"""

_RUNNER_SPEC_NAME = "wu-stress-01"
_LANE_NAME = "wu-stress-01-host"
_LANE_CLAIM_TTL_SECONDS = 3.0
_LANE_HEARTBEAT_INTERVAL_SECONDS = 0.2
_WORKER_STARTUP_TIMEOUT_SECONDS = 3.0
_DISPATCH_POLL_INTERVAL_SECONDS = 0.01
_DEFAULT_MAX_TOKENS = 96
_DEFAULT_CONTENT_PREFIX = "stress-final"
_FAILED_ERROR_CODE = "stress_worker_failed"
_FAILED_MESSAGE = "deterministic stress worker failed"
_STREAM_EXCEPTION_MESSAGE = "deterministic stress worker stream exception"
_WORKER_ID = "wu-stress-01-worker"
_NOW = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
_HOST_DB_FILENAME = "host.sqlite3"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_EVENT_TYPE_RUN_LOST = "RUN_LOST"
_EVENT_REASON_JSON_PATH = "$.reason"
_TERMINAL_EVENT_TYPES = (
    _EVENT_TYPE_RUN_SUCCEEDED,
    _EVENT_TYPE_RUN_FAILED,
    _EVENT_TYPE_RUN_CANCELLED,
)
_ALL_RUN_TERMINAL_EVENT_TYPES = _TERMINAL_EVENT_TYPES + (_EVENT_TYPE_RUN_LOST,)
_PROCESS_START_TIMEOUT_SECONDS = 5.0
_POLL_INTERVAL_SECONDS = 0.01
# 该阈值只用于 stress diagnostic 解释已被测试 helper 主动改旧的 heartbeat；
# Host recovery stale policy 仍以生产 recovery scanner 为准。
_HOST_INSTANCE_STALE_AFTER_SECONDS = 1.0
_LANE_VERIFY_TIMEOUT_SECONDS = 0.0
_LANE_VERIFY_OWNER_ID = "wu-stress-lane-verifier"


@dataclass(frozen=True, slots=True)
class HostStressSummary:
    """Host stress 场景的结构化诊断摘要。

    :param scenario_name: stress 场景名称。
    :param session_count: 场景涉及的 Session 数量。
    :param run_count: 场景提交或检查的 Run 数量。
    :param crash_count: 场景内主动制造的 crash 次数。
    :param recovery_count: 场景观测到的 recovery 次数。
    :param watch_lag_max: watch lag 样本的最大值。
    :param watch_lag_samples: watch lag 估算样本。
    :param scheduler_drained: scheduler 是否完成 drain。
    :param liveness_stale_detected: 是否观测到预期 stale liveness。
    :param terminal_duplicate_count: terminal 事件重复计数。
    :param terminal_dedupe_ok: terminal 去重断言是否通过。
    :param failure_boundary: 失败边界；成功时为 ``None``。
    :returns: 不适用；dataclass 初始化返回 ``HostStressSummary`` 实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    scenario_name: str
    session_count: int
    run_count: int
    crash_count: int
    recovery_count: int
    watch_lag_max: int
    watch_lag_samples: tuple[int, ...]
    scheduler_drained: bool
    liveness_stale_detected: bool
    terminal_duplicate_count: int
    terminal_dedupe_ok: bool
    failure_boundary: StressFailureBoundary | None


@dataclass(frozen=True, slots=True)
class HostStressScenario:
    """Host mixed stress 场景参数。

    本 dataclass 只服务 WU-STRESS-01 测试层 deterministic scenario，避免
    mixed stress 的规模、watch 速度和 lane 容量散落在测试主体中。它不进入
    生产代码，不作为 Host public contract，也不表达 durable truth。

    :param session_count: 场景涉及的 Session 数量。
    :param runs_per_session: 每个 Session 期望覆盖的 Run 数量。
    :param crash_cycles: 场景内主动制造的 owner crash 次数。
    :param watch_delay: primary watcher 每条 terminal 后的消费延迟秒数。
    :param lane_capacity: Host dispatch runtime lane 容量。
    :returns: 不适用；dataclass 初始化返回 ``HostStressScenario`` 实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    session_count: int
    runs_per_session: int
    crash_cycles: int
    watch_delay: float
    lane_capacity: int


@dataclass(frozen=True, slots=True)
class StressTerminalObservation:
    """stress helper 记录的 terminal 观测。

    :param run_id: terminal 对应的 Run id。
    :param event_id: terminal HostEvent 或 durable event id。
    :param event_sequence: terminal 事件序号。
    :param terminal_kind: Host terminal event kind。
    :param terminal_status: Host terminal status。
    :returns: 不适用；dataclass 初始化返回 ``StressTerminalObservation`` 实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    run_id: str
    event_id: str
    event_sequence: int
    terminal_kind: HostEventKind
    terminal_status: HostTerminalStatus


@dataclass(frozen=True, slots=True)
class StressHostInstanceDiagnostic:
    """Host instance liveness row 的测试诊断视图。

    :param host_instance_id: Host instance id。
    :param pid: owner 进程 pid。
    :param heartbeat_at: 最近 heartbeat 时间文本。
    :param status: Host instance lifecycle 状态。
    :param heartbeat_stale: 相对读取时刻与测试阈值是否 stale。
    :returns: 不适用；dataclass 初始化返回
        ``StressHostInstanceDiagnostic`` 实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    host_instance_id: str
    pid: int
    heartbeat_at: str
    status: HostInstanceStatus
    heartbeat_stale: bool


class StressWorkerBehavior(StrEnum):
    """deterministic stress worker 的封闭行为集合。

    :param value: 枚举成员字符串值，由 ``StrEnum`` 管理，调用方不直接传入。
    :returns: 不适用；枚举成员由 Python 枚举机制创建。
    :raises Exception: 本类型不主动抛出异常。
    """

    FINAL = "final"
    FAILED = "failed"
    BLOCKING_FINAL = "blocking_final"
    STREAM_EXCEPTION = "stream_exception"
    CLEAN_EOF = "clean_eof"


class DeterministicStressWorkerHandle:
    """stress suite 使用的 deterministic worker handle。

    :param snapshot: 当前 dispatch snapshot。
    :param behavior: 本次 run 的脚本行为。
    :param release_event: blocking final 行为的释放事件。
    :param content_prefix: final answer 内容前缀。
    :param owner: 记录 close/cancel 诊断的 factory。
    :returns: 不适用；初始化返回 ``DeterministicStressWorkerHandle`` 实例。
    :raises Exception: 本类型初始化不主动抛出异常。
    """

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        behavior: StressWorkerBehavior,
        release_event: asyncio.Event,
        content_prefix: str,
        owner: "DeterministicStressWorkerFactory",
    ) -> None:
        """初始化 deterministic worker handle。

        :param snapshot: 当前 dispatch snapshot。
        :param behavior: 本次 run 的脚本行为。
        :param release_event: blocking final 行为的释放事件。
        :param content_prefix: final answer 内容前缀。
        :param owner: 记录 close/cancel 诊断的 factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._snapshot = snapshot
        self._behavior = behavior
        self._release_event = release_event
        self._content_prefix = content_prefix
        self._owner = owner

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        :raises Exception: 不主动抛出异常。
        """

        return _WORKER_ID

    async def events(self) -> AsyncIterator[EngineEvent]:
        """按脚本行为产出 Engine event stream。

        :returns: EngineEvent 异步迭代器；``CLEAN_EOF`` 行为不产出事件，
            由 Host scheduler 显式 closeout。
        :raises RuntimeError: 行为为 ``STREAM_EXCEPTION`` 时抛出。
        """

        if self._behavior is StressWorkerBehavior.BLOCKING_FINAL:
            await self._release_event.wait()
            yield self._final_answer_event()
            return
        if self._behavior is StressWorkerBehavior.FINAL:
            yield self._final_answer_event()
            return
        if self._behavior is StressWorkerBehavior.FAILED:
            yield self._failed_event()
            return
        if self._behavior is StressWorkerBehavior.STREAM_EXCEPTION:
            raise RuntimeError(_STREAM_EXCEPTION_MESSAGE)
        if self._behavior is StressWorkerBehavior.CLEAN_EOF:
            return
        return

    async def close(self) -> None:
        """记录 handle close 诊断。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._owner.record_handle_close()

    def on_cancel(self, reason: str) -> None:
        """记录 Host 下发的取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._owner.record_cancel(reason)

    def _final_answer_event(self) -> EngineEvent:
        """构造成功终态 EngineEvent。

        :returns: 成功 final answer EngineEvent。
        :raises Exception: 不主动抛出异常。
        """

        return EngineEvent(
            occurred_at=_NOW,
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=f"{self._content_prefix}:{self._snapshot.run_id}",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    def _failed_event(self) -> EngineEvent:
        """构造失败终态 EngineEvent。

        :returns: failed EngineEvent。
        :raises Exception: 不主动抛出异常。
        """

        return EngineEvent(
            occurred_at=_NOW,
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.RUN_FAILED,
            data=RunFailedData(
                error_code=_FAILED_ERROR_CODE,
                message=_FAILED_MESSAGE,
                provider_request_id=None,
                recoverable=False,
            ),
            metadata=None,
        )


class DeterministicStressWorker:
    """创建 deterministic stress handle 的 worker。

    :param factory: 持有脚本与诊断状态的 factory。
    :returns: 不适用；初始化返回 ``DeterministicStressWorker`` 实例。
    :raises Exception: 本类型初始化不主动抛出异常。
    """

    def __init__(self, factory: "DeterministicStressWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 持有脚本与诊断状态的 factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受一次 dispatch 并返回脚本化 handle。

        :param snapshot: durable dispatch snapshot。
        :param request: Engine run request；本 worker 不读取请求内容。
        :returns: deterministic local worker handle。
        :raises Exception: 不主动抛出异常。
        """

        del request
        self._factory.record_accepted(snapshot)
        return DeterministicStressWorkerHandle(
            snapshot=snapshot,
            behavior=self._factory.behavior_for_run(snapshot.run_id),
            release_event=self._factory.release_event_for_run(snapshot.run_id),
            content_prefix=self._factory.content_prefix,
            owner=self._factory,
        )


class DeterministicStressWorkerFactory:
    """Host stress suite 使用的 deterministic worker factory。

    :param default_behavior: 未设置 per-run 脚本时使用的默认行为。
    :param content_prefix: final answer 内容前缀。
    :returns: 不适用；初始化返回 ``DeterministicStressWorkerFactory`` 实例。
    :raises Exception: 本类型初始化不主动抛出异常。
    """

    def __init__(
        self,
        default_behavior: StressWorkerBehavior = StressWorkerBehavior.FINAL,
        content_prefix: str = _DEFAULT_CONTENT_PREFIX,
    ) -> None:
        """初始化 deterministic stress worker factory。

        :param default_behavior: 未设置 per-run 脚本时使用的默认行为。
        :param content_prefix: final answer 内容前缀。
        :returns: ``None``。
        :raises ValueError: ``content_prefix`` 为空时抛出。
        """

        if content_prefix.strip() == "":
            raise ValueError("content_prefix must be non-empty")
        self._default_behavior = default_behavior
        self.content_prefix = content_prefix
        self._run_behaviors: dict[str, StressWorkerBehavior] = {}
        self._queued_behaviors: list[StressWorkerBehavior] = []
        self._release_events: dict[str, asyncio.Event] = {}
        self._accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self._cancel_reasons: list[str] = []
        self._accepted_event = asyncio.Event()
        self._handle_close_count = 0

    @property
    def accepted_snapshots(self) -> tuple[AttemptDispatchSnapshot, ...]:
        """返回已 accepted 的 dispatch snapshot。

        :returns: accepted snapshot 元组。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._accepted_snapshots)

    @property
    def cancel_reasons(self) -> tuple[str, ...]:
        """返回 worker 收到的取消原因。

        :returns: 取消原因元组。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._cancel_reasons)

    @property
    def handle_close_count(self) -> int:
        """返回 handle close 调用次数。

        :returns: close 调用次数。
        :raises Exception: 不主动抛出异常。
        """

        return self._handle_close_count

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 deterministic stress worker。

        :param snapshot: durable dispatch snapshot；本 factory 不直接读取。
        :returns: deterministic stress worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return DeterministicStressWorker(self)

    def set_run_behavior(
        self,
        run_id: str,
        behavior: StressWorkerBehavior,
    ) -> None:
        """设置指定 Run 的脚本行为。

        :param run_id: Run id。
        :param behavior: 该 Run 的脚本行为。
        :returns: ``None``。
        :raises ValueError: ``run_id`` 为空时抛出。
        """

        if run_id.strip() == "":
            raise ValueError("run_id must be non-empty")
        self._run_behaviors[run_id] = behavior

    def enqueue_run_behavior(self, behavior: StressWorkerBehavior) -> None:
        """为下一次 worker accept 入队脚本行为。

        该队列只服务 stress 测试中“先提交、后获得 run_id”的 public API
        路径。调用方仍应在单线程 deterministic 调度点使用它，避免并发
        accept 让行为分配变得不可诊断；本 helper 不进入生产代码。

        :param behavior: 下一次 worker accept 使用的脚本行为。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._queued_behaviors.append(behavior)

    def behavior_for_run(self, run_id: str) -> StressWorkerBehavior:
        """读取指定 Run 的脚本行为。

        查找顺序固定为：显式 ``run_id`` 行为、预提交的下一次 accept 队列
        行为、factory 默认行为。后续 stress 测试必须优先使用预提交队列
        路径绑定故障脚本，避免 public submit 返回后再按 run_id 设置行为
        造成调度竞态；显式 run 行为仅保留给已知 run_id 的受控场景。

        :param run_id: Run id。
        :returns: 该 Run 的脚本行为；未显式配置时依次尝试下一次 accept
            队列和默认行为。
        :raises Exception: 不主动抛出异常。
        """

        configured = self._run_behaviors.get(run_id)
        if configured is not None:
            return configured
        if len(self._queued_behaviors) > 0:
            return self._queued_behaviors.pop(0)
        return self._default_behavior

    def release_run(self, run_id: str) -> None:
        """释放 blocking final 行为的指定 Run。

        :param run_id: Run id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.release_event_for_run(run_id).set()

    def release_event_for_run(self, run_id: str) -> asyncio.Event:
        """返回指定 Run 的释放事件。

        :param run_id: Run id。
        :returns: blocking final 释放事件。
        :raises Exception: 不主动抛出异常。
        """

        event = self._release_events.get(run_id)
        if event is None:
            event = asyncio.Event()
            self._release_events[run_id] = event
        return event

    def record_accepted(self, snapshot: AttemptDispatchSnapshot) -> None:
        """记录 worker accepted snapshot。

        :param snapshot: durable dispatch snapshot。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._accepted_snapshots.append(snapshot)
        self._accepted_event.set()

    def record_handle_close(self) -> None:
        """记录 handle close 调用。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._handle_close_count += 1

    def record_cancel(self, reason: str) -> None:
        """记录 Host cancel 通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._cancel_reasons.append(reason)

    async def wait_accepted(self, timeout_seconds: float) -> None:
        """等待至少一次 worker accept。

        :param timeout_seconds: 等待超时秒数。
        :returns: ``None``。
        :raises TimeoutError: 超时未发生 accepted 时由 ``asyncio`` 抛出。
        """

        await asyncio.wait_for(self._accepted_event.wait(), timeout_seconds)


class InspectableStressWorkerFactory(DeterministicStressWorkerFactory):
    """Slice 4 使用的可检查 deterministic worker factory。

    本类型在 ``DeterministicStressWorkerFactory`` 的脚本化 worker 能力之上，
    增加 accepted handle 总数、worker cancel 总数和 handle close 总数的
    聚合诊断入口。它只服务 WU-STRESS-01 public opener stress，不暴露
    production scheduler internals，也不作为 Host durable truth。

    :param default_behavior: 未设置 per-run 脚本时使用的默认行为。
    :param content_prefix: final answer 内容前缀。
    :returns: 不适用；初始化返回 ``InspectableStressWorkerFactory`` 实例。
    :raises ValueError: ``content_prefix`` 为空时由父类抛出。
    """

    @property
    def accepted_handle_count(self) -> int:
        """返回已 accepted handle 数量。

        :returns: accepted snapshot 数量。
        :raises Exception: 不主动抛出异常。
        """

        return len(self.accepted_snapshots)

    @property
    def total_cancel_count(self) -> int:
        """返回 worker handle 收到的取消通知数量。

        :returns: 取消通知数量。
        :raises Exception: 不主动抛出异常。
        """

        return len(self.cancel_reasons)

    @property
    def total_close_count(self) -> int:
        """返回 worker handle close 数量。

        :returns: close 调用数量。
        :raises Exception: 不主动抛出异常。
        """

        return self.handle_close_count


async def consume_terminals(
    iterator: AsyncIterator[HostEvent],
    *,
    expected_count: int,
    delay_seconds: float,
    timeout_seconds: float,
    observed_events: asyncio.Queue[HostEvent] | None = None,
) -> tuple[HostEvent, ...]:
    """消费指定数量的 terminal HostEvent。

    本 helper 只服务 WU-STRESS-01 watch stress。调用方可通过
    ``delay_seconds`` 模拟慢消费者，并可通过 ``observed_events`` 获得
    逐条观测用于 watch lag 诊断；这些观测只表达 live watcher 已读事实，
    不表达 replay cursor truth，也不替代 EventLog / Run canonical facts。

    :param iterator: public ``watch_session_events`` 返回的异步迭代器。
    :param expected_count: 需要消费的 terminal 事件数量。
    :param delay_seconds: 每条 terminal 后的人为消费延迟秒数。
    :param timeout_seconds: 总超时秒数。
    :param observed_events: 可选观测队列；传入时每条 terminal 会写入队列。
    :returns: 按消费顺序返回的 terminal HostEvent 元组。
    :raises ValueError: ``expected_count`` 或延迟参数非法时抛出。
    :raises TimeoutError: 超时未消费到足够 terminal 时由 ``asyncio`` 抛出。
    :raises StopAsyncIteration: iterator 提前结束时由底层透传。
    """

    if expected_count < 0:
        raise ValueError("expected_count must be non-negative")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    observed: list[HostEvent] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while len(observed) < expected_count:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("timed out while consuming terminal HostEvents")
        event = await asyncio.wait_for(anext(iterator), timeout=remaining)
        if event.kind not in {
            HostEventKind.SUCCEEDED,
            HostEventKind.FAILED,
            HostEventKind.CANCELLED,
            HostEventKind.LOST,
        }:
            continue
        observed.append(event)
        if observed_events is not None:
            observed_events.put_nowait(event)
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
    return tuple(observed)


async def close_host_event_iterator(iterator: AsyncIterator[HostEvent]) -> None:
    """关闭测试持有的 HostEvent async generator。

    本 helper 镜像 recovery 测试中的 watch iterator 清理语义，但归属
    WU-STRESS-01 stress helper：它不是兼容 wrapper，不是生产生命周期抽象，
    也不表达 Host close 治理。它只关闭 public watch iterator，不写
    EventLog、不取消 Run，只服务测试清理。

    :param iterator: HostEvent iterator。
    :returns: ``None``。
    :raises Exception: 底层 async generator close 失败时透传。
    """

    await cast(AsyncGenerator[HostEvent, None], iterator).aclose()


def read_latest_event_sequence(root_path: pathlib.Path) -> int:
    """读取 EventLog 当前最新全局序号。

    每次调用都会打开新的短连接并执行 fresh short read transaction，得到
    point-in-time diagnostic。该读取只用于测试诊断和 watch lag 估算，
    不表达 watcher replay truth，不替代 EventLog / Run / Attempt
    canonical facts，也不得复用长事务快照计算最终 lag。

    :param root_path: pytest 临时根目录。
    :returns: 当前最新 EventLog sequence；空 EventLog 返回 0。
    :raises TypeError: durable row 字段类型不符合预期时抛出。
    """

    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        row = connection.execute("SELECT COALESCE(MAX(event_sequence), 0) FROM event_log").fetchone()
    if row is None:
        return 0
    value = row[0]
    if not isinstance(value, int):
        raise TypeError("latest event_sequence must be int")
    return value


def read_event_log_count(root_path: pathlib.Path) -> int:
    """读取 EventLog row 数量。

    每次调用都会打开新的短连接并执行 fresh short read transaction，得到
    point-in-time diagnostic。该读取只用于 consumer cancel 测试断言和
    失败定位，不替代 EventLog canonical fact。

    :param root_path: pytest 临时根目录。
    :returns: EventLog row 数量。
    :raises TypeError: durable row 字段类型不符合预期时抛出。
    """

    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        row = connection.execute("SELECT COUNT(*) FROM event_log").fetchone()
    if row is None:
        return 0
    value = row[0]
    if not isinstance(value, int):
        raise TypeError("event log count must be int")
    return value


def read_session_terminal_sequences(
    root_path: pathlib.Path,
    session_id: str,
) -> tuple[int, ...]:
    """读取指定 Session 的 terminal EventLog sequence。

    每次调用都会打开新的短连接并执行一次短读，得到 point-in-time
    diagnostic。该读取只用于 watch lag drain、terminal 覆盖和断开窗口
    durable 诊断，不表达 watcher replay truth，不替代 EventLog / Run /
    Attempt canonical facts，也不复用长事务快照。

    :param root_path: pytest 临时根目录。
    :param session_id: 目标 Session id。
    :returns: 按 EventLog sequence 升序排列的 terminal sequence 元组。
    :raises ValueError: ``session_id`` 为空时抛出。
    :raises TypeError: durable row 字段类型不符合预期时抛出。
    """

    if session_id.strip() == "":
        raise ValueError("session_id must be non-empty")
    terminal_type_placeholders = ",".join("?" for _ in _TERMINAL_EVENT_TYPES)
    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        rows = connection.execute(
            f"""
            SELECT event_sequence
            FROM event_log
            WHERE session_id = ?
              AND event_type IN ({terminal_type_placeholders})
            ORDER BY event_sequence ASC
            """,
            (session_id,) + _TERMINAL_EVENT_TYPES,
        ).fetchall()

    sequences: list[int] = []
    for row in rows:
        value = row[0]
        if not isinstance(value, int):
            raise TypeError("terminal event_sequence must be int")
        sequences.append(value)
    return tuple(sequences)


def summary_to_json(summary: HostStressSummary) -> str:
    """把 Host stress summary 转成排序 JSON 文本。

    :param summary: Host stress summary。
    :returns: 排序后的 JSON 文本，可用于 assertion message 或
        ``record_property``。
    :raises TypeError: JSON 序列化失败时由 ``json.dumps`` 透传。
    """

    payload: Mapping[str, StressSummaryJsonValue] = {
        "crash_count": summary.crash_count,
        "failure_boundary": summary.failure_boundary,
        "liveness_stale_detected": summary.liveness_stale_detected,
        "recovery_count": summary.recovery_count,
        "run_count": summary.run_count,
        "scenario_name": summary.scenario_name,
        "scheduler_drained": summary.scheduler_drained,
        "session_count": summary.session_count,
        "terminal_dedupe_ok": summary.terminal_dedupe_ok,
        "terminal_duplicate_count": summary.terminal_duplicate_count,
        "watch_lag_max": summary.watch_lag_max,
        "watch_lag_samples": summary.watch_lag_samples,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def assert_summary_ok(summary: HostStressSummary) -> None:
    """断言 stress summary 没有暴露基础失败信号。

    :param summary: Host stress summary。
    :returns: ``None``。
    :raises AssertionError: summary 显示 terminal 去重失败或存在失败边界时抛出。
    """

    summary_json = summary_to_json(summary)
    assert summary.failure_boundary is None, summary_json
    assert summary.terminal_dedupe_ok, summary_json
    assert summary.terminal_duplicate_count == 0, summary_json


def terminal_duplicate_count(
    observations: Sequence[StressTerminalObservation],
) -> int:
    """计算 terminal 观测中的重复数量。

    同一 ``run_id`` 或同一 ``event_id`` 再次出现，都计为一条重复观测。

    :param observations: terminal 观测序列。
    :returns: 重复 terminal 观测数量。
    :raises Exception: 不主动抛出异常。
    """

    seen_run_ids: set[str] = set()
    seen_event_ids: set[str] = set()
    duplicate_count = 0
    for observation in observations:
        run_seen = observation.run_id in seen_run_ids
        event_seen = observation.event_id in seen_event_ids
        if run_seen or event_seen:
            duplicate_count += 1
        seen_run_ids.add(observation.run_id)
        seen_event_ids.add(observation.event_id)
    return duplicate_count


def terminal_dedupe_ok(
    observations: Sequence[StressTerminalObservation],
) -> bool:
    """判断 terminal 观测是否满足去重要求。

    :param observations: terminal 观测序列。
    :returns: 没有重复 terminal 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return terminal_duplicate_count(observations) == 0


def compute_watch_lag(latest_sequence: int, last_seen_sequence: int) -> int:
    """计算 watch lag 诊断值。

    调用方读取 ``latest_sequence`` 与 ``last_seen_sequence`` 时，必须通过
    fresh short read transaction 取得 point-in-time diagnostic；本 helper
    只做测试诊断和 lag 估算，不表达 watcher replay truth，不替代
    EventLog / Run / Attempt canonical facts，也不得复用长事务快照计算最终
    lag。

    :param latest_sequence: 诊断读取时 EventLog 最新序号。
    :param last_seen_sequence: watcher 已观测到的最后序号。
    :returns: 非负 lag。
    :raises ValueError: 任一序号小于 0 时抛出。
    """

    if latest_sequence < 0 or last_seen_sequence < 0:
        raise ValueError("sequence must be non-negative")
    return max(0, latest_sequence - last_seen_sequence)


def build_stress_open_host_options(
    root_path: pathlib.Path,
    worker_factory: LocalEngineWorkerFactory,
    *,
    lane_capacity: int,
    lane_timeout_seconds: float,
) -> OpenHostOptions:
    """构造 Host stress suite 使用的 public ``OpenHostOptions``。

    :param root_path: pytest 临时根目录。
    :param worker_factory: deterministic stress worker factory。
    :param lane_capacity: runtime lane 容量。
    :param lane_timeout_seconds: lane acquire 默认超时秒数。
    :returns: public Host opener options。
    :raises TypeError: typed options 字段非法时由底层抛出。
    :raises ValueError: options 语义非法时由底层抛出。
    """

    options = open_host_options(
        root_path,
        runner_spec=deterministic_runner_spec(_RUNNER_SPEC_NAME),
        worker_factory=worker_factory,
        allow_tool_calls=False,
        max_tokens=_DEFAULT_MAX_TOKENS,
    )
    return replace(
        options,
        lane_name=_LANE_NAME,
        lane_capacity=lane_capacity,
        lane_default_timeout_seconds=lane_timeout_seconds,
        lane_claim_ttl_seconds=_LANE_CLAIM_TTL_SECONDS,
        lane_heartbeat_interval_seconds=_LANE_HEARTBEAT_INTERVAL_SECONDS,
        worker_startup_timeout_seconds=_WORKER_STARTUP_TIMEOUT_SECONDS,
        dispatch_poll_interval_seconds=_DISPATCH_POLL_INTERVAL_SECONDS,
    )


async def wait_all_runs_terminal(
    host: Host,
    run_ids: Sequence[str],
    timeout_seconds: float,
) -> tuple[RunSnapshot, ...]:
    """等待一组 Run 全部进入 Host public 终态。

    本 helper 通过 public ``Host.get_run`` 轮询，不读取 scheduler private
    registry，也不把 durable diagnostic 当作成功路径。``LOST`` 是 Host
    public Run 终态，因此也视为 terminal。

    :param host: public Host handle。
    :param run_ids: 需要等待的 Run id 序列。
    :param timeout_seconds: 总超时秒数。
    :returns: 按 ``run_ids`` 顺序返回的 terminal Run snapshot。
    :raises ValueError: 任一 Run id 为空或 timeout 非正时抛出。
    :raises TimeoutError: 超时仍存在非终态 Run 时抛出。
    :raises Exception: Host public API 失败时透传。
    """

    for run_id in run_ids:
        if run_id.strip() == "":
            raise ValueError("run_id must be non-empty")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    terminal_by_run_id: dict[str, RunSnapshot] = {}
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        for run_id in run_ids:
            if run_id in terminal_by_run_id:
                continue
            snapshot = await host.get_run(run_id)
            if _is_public_run_terminal(snapshot.status):
                terminal_by_run_id[run_id] = snapshot
        if len(terminal_by_run_id) == len(run_ids):
            return tuple(terminal_by_run_id[run_id] for run_id in run_ids)
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    open_run_ids = tuple(run_id for run_id in run_ids if run_id not in terminal_by_run_id)
    raise TimeoutError(f"runs did not reach terminal status: {open_run_ids}")


def read_host_instances(root_path: pathlib.Path) -> tuple[StressHostInstanceDiagnostic, ...]:
    """读取 Host instance liveness 诊断视图。

    每次调用都会打开新的 SQLite 短连接读取 ``host_instances``，只用于
    WU-STRESS-01 判断 running / stopping / stopped 与 stale heartbeat
    诊断；它不替代 recovery orphan proof，不暴露生产 scheduler internals，
    也不作为 Host durable truth 之外的新真源。stale 阈值只解释
    ``force_owner_pid_missing_and_heartbeat_stale()`` 已经制造出的测试证据，
    不替代 Host recovery policy，也不参与生产 orphan 判断。

    :param root_path: pytest 临时根目录。
    :returns: 按 ``host_instance_id`` 排序的 liveness 诊断元组。
    :raises TypeError: durable row 字段类型不符合预期时抛出。
    :raises ValueError: heartbeat timestamp 或 status 无法解析时抛出。
    """

    now = datetime.now(UTC)
    stale_after = timedelta(seconds=_HOST_INSTANCE_STALE_AFTER_SECONDS)
    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        rows = connection.execute(
            """
            SELECT host_instance_id, pid, heartbeat_at, status
            FROM host_instances
            ORDER BY host_instance_id ASC
            """
        ).fetchall()

    diagnostics: list[StressHostInstanceDiagnostic] = []
    for row in rows:
        host_instance_id = row[0]
        pid = row[1]
        heartbeat_at = row[2]
        status_text = row[3]
        if not isinstance(host_instance_id, str):
            raise TypeError("host_instance_id must be str")
        if not isinstance(pid, int):
            raise TypeError("host instance pid must be int")
        if not isinstance(heartbeat_at, str):
            raise TypeError("host instance heartbeat_at must be str")
        if not isinstance(status_text, str):
            raise TypeError("host instance status must be str")
        heartbeat = parse_utc_timestamp(heartbeat_at)
        diagnostics.append(
            StressHostInstanceDiagnostic(
                host_instance_id=host_instance_id,
                pid=pid,
                heartbeat_at=heartbeat_at,
                status=HostInstanceStatus(status_text),
                heartbeat_stale=(now - heartbeat > stale_after),
            )
        )
    return tuple(diagnostics)


async def verify_lane_released(lane_db_path: pathlib.Path, lane_name: str) -> bool:
    """通过 runtime lane public acquire 验证 lane capacity 已释放。

    本 diagnostic 打开一个独立 ``LaneController``，对同一 lane 立即
    acquire 一次并立刻释放。它只证明 runtime lane capacity 没有被遗留
    claim 阻塞，不读取 scheduler internals，不表达 Host durable truth，
    也不构成 recovery proof。

    :param lane_db_path: Host options 使用的 runtime lane SQLite DB 路径。
    :param lane_name: 需要验证的 lane 名称。
    :returns: 立即 acquire 成功时返回 ``True``，容量被占用时返回 ``False``。
        如果调用方传入的不是同一个 Host lane DB，本证明无效。
    :raises ValueError: ``lane_name`` 为空时抛出。
    :raises Exception: runtime lane 打开或 SQLite 操作失败时透传。
    """

    if lane_name.strip() == "":
        raise ValueError("lane_name must be non-empty")
    controller = await LaneController.open(
        [
            LaneConfig(
                name=lane_name,
                capacity=1,
                default_timeout_seconds=_LANE_VERIFY_TIMEOUT_SECONDS,
                claim_ttl_seconds=_LANE_CLAIM_TTL_SECONDS,
                heartbeat_interval_seconds=_LANE_HEARTBEAT_INTERVAL_SECONDS,
            )
        ],
        coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
        owner=LaneOwner(
            owner_id=_LANE_VERIFY_OWNER_ID,
            pid=os.getpid(),
            process_start_token=None,
        ),
    )
    try:
        outcome = await controller.acquire(
            lane_name,
            timeout_seconds=_LANE_VERIFY_TIMEOUT_SECONDS,
        )
        if not isinstance(outcome, LaneAcquired):
            return False
        await outcome.token.release()
        return True
    finally:
        await controller.close()


def run_blocking_stress_owner_process(
    root_path_text: str,
    accepted_marker_text: str,
    release_marker_text: str,
    result_marker_text: str,
    slot_key: str,
    client_request_id: str,
    user_prompt: str,
) -> None:
    """运行 stress crash 场景的阻塞 owner 子进程。

    本函数是 ``tests.host.recovery_support.run_blocking_owner_process`` 的
    薄封装，只为 WU-STRESS-01 暴露 multiprocessing 顶层 target；进程内
    仍通过既有 recovery helper 打开 Host、提交 Run、写 accepted marker，
    不复制多进程 owner 实现，也不进入生产代码。

    :param root_path_text: 测试根目录文本路径。
    :param accepted_marker_text: accepted marker 文本路径。
    :param release_marker_text: release marker 文本路径。
    :param result_marker_text: result marker 文本路径。
    :param slot_key: ensure_session slot key。
    :param client_request_id: follow-up 幂等 id。
    :param user_prompt: 用户输入。
    :returns: ``None``。
    :raises Exception: 底层 recovery helper 的异常会在子进程内透传。
    """

    run_blocking_owner_process(
        root_path_text,
        accepted_marker_text,
        release_marker_text,
        result_marker_text,
        slot_key,
        client_request_id,
        user_prompt,
    )


def run_open_probe_for_stress(root_path_text: str, result_marker_text: str) -> None:
    """运行 stress live owner probe 子进程。

    本函数是 ``tests.host.recovery_support.run_open_probe_process`` 的薄封装，
    只服务 WU-STRESS-01 live owner 防误恢复探针；它不表达 Host durable
    truth，也不修改生产 recovery 策略。

    :param root_path_text: 测试根目录文本路径。
    :param result_marker_text: probe result marker 文本路径。
    :returns: ``None``。
    :raises Exception: 底层 recovery helper 的异常会在子进程内透传。
    """

    run_open_probe_process(root_path_text, result_marker_text)


def start_and_crash_owner_for_stress(
    root_path: pathlib.Path,
    *,
    slot_key: str,
    client_request_id: str,
    user_prompt: str,
    timeout_seconds: float = _PROCESS_START_TIMEOUT_SECONDS,
) -> AcceptedAttemptMarker:
    """启动阻塞 owner，等待 accepted 后 crash 并制造 stale owner 证据。

    本 helper 复用 recovery multiprocess helper 的 process target、accepted
    marker、进程终止、lane TTL 等待和 stale owner fault injection；新增职责
    仅是把这些步骤组合为 WU-STRESS-01 可复用的 crash/reopen stress 步骤。
    它只服务测试层 deterministic fault injection，不进入生产代码，不作为
    Host recovery truth。

    :param root_path: pytest 临时根目录。
    :param slot_key: ensure_session slot key。
    :param client_request_id: follow-up 幂等 id。
    :param user_prompt: 用户输入。
    :param timeout_seconds: 等待 accepted marker 的超时秒数。
    :returns: 被 crash 中断的 accepted attempt marker。
    :raises TimeoutError: 超时未等到 accepted marker 时抛出。
    :raises AssertionError: 子进程无法终止、owner row 不存在或 crash 前
        attempt 数不为 1 时抛出。
    """

    accepted_marker = root_path / f"{client_request_id}-accepted"
    release_marker = root_path / f"{client_request_id}-release"
    result_marker = root_path / f"{client_request_id}-result"
    owner_process = Process(
        target=run_blocking_stress_owner_process,
        args=(
            str(root_path),
            str(accepted_marker),
            str(release_marker),
            str(result_marker),
            slot_key,
            client_request_id,
            user_prompt,
        ),
    )
    owner_process.start()
    try:
        accepted = wait_for_accepted_marker(accepted_marker, timeout_seconds)
        terminate_process(owner_process)
        wait_for_runtime_lane_claim_ttl_to_expire()
        force_owner_pid_missing_and_heartbeat_stale(root_path, accepted.run_id)
        observed_attempt_count = recovery_attempt_count_for_run(root_path, accepted.run_id)
        if observed_attempt_count != 1:
            raise AssertionError("crashed owner run must have exactly one attempt")
        return accepted
    except BaseException as original_error:
        if owner_process.is_alive():
            try:
                terminate_process(owner_process)
            except BaseException as cleanup_error:
                raise cleanup_error from original_error
        raise


def count_event_type(root_path: pathlib.Path, event_type: str) -> int:
    """统计 EventLog 中指定 event type 的数量。

    本函数复用 ``tests.host.recovery_support.event_type_count``，只为 stress
    summary 提供命名一致的诊断入口；读取结果只用于测试断言和失败定位，
    不替代 EventLog canonical fact。

    :param root_path: pytest 临时根目录。
    :param event_type: EventLog event type。
    :returns: 指定类型事件数量。
    :raises ValueError: ``event_type`` 为空时抛出。
    :raises TypeError: 底层读取到非整数 count 时透传。
    """

    if event_type.strip() == "":
        raise ValueError("event_type must be non-empty")
    return recovery_event_type_count(root_path, event_type)


def attempt_count_for_run(root_path: pathlib.Path, run_id: str) -> int:
    """统计指定 Run 的 Attempt 数量。

    本函数复用 ``tests.host.recovery_support.attempt_count_for_run``，只服务
    WU-STRESS-01 诊断；它读取 durable row count 作为测试核对，不绕过 Host
    状态机制造成功路径。

    :param root_path: pytest 临时根目录。
    :param run_id: Run id。
    :returns: 该 Run 的 Attempt 数量。
    :raises ValueError: ``run_id`` 为空时抛出。
    :raises TypeError: 底层读取到非整数 count 时透传。
    """

    if run_id.strip() == "":
        raise ValueError("run_id must be non-empty")
    return recovery_attempt_count_for_run(root_path, run_id)


def terminal_events_for_runs(
    root_path: pathlib.Path,
    run_ids: Sequence[str],
) -> tuple[StressTerminalObservation, ...]:
    """读取指定 Run 的 durable terminal event 诊断。

    每次调用都会打开新的短连接并执行一次短读，得到 point-in-time
    diagnostic。该读取只用于 terminal 去重诊断和 stress assertion message，
    不表达 watcher replay truth，不替代 EventLog / Run / Attempt canonical
    facts，也不复用长事务快照。

    :param root_path: pytest 临时根目录。
    :param run_ids: 需要读取 terminal event 的 Run id 序列。
    :returns: 按 ``event_sequence`` 排序的 terminal 观测元组。
    :raises ValueError: 任一 Run id 为空时抛出。
    :raises TypeError: durable row 字段类型不符合预期时抛出。
    """

    if len(run_ids) == 0:
        return ()
    for run_id in run_ids:
        if run_id.strip() == "":
            raise ValueError("run_id must be non-empty")

    placeholders = ",".join("?" for _ in run_ids)
    terminal_type_placeholders = ",".join("?" for _ in _TERMINAL_EVENT_TYPES)
    parameters = tuple(run_ids) + _TERMINAL_EVENT_TYPES
    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        rows = connection.execute(
            f"""
            SELECT event_id, event_sequence, run_id, event_type
            FROM event_log
            WHERE run_id IN ({placeholders})
              AND event_type IN ({terminal_type_placeholders})
            ORDER BY event_sequence ASC
            """,
            parameters,
        ).fetchall()

    observations: list[StressTerminalObservation] = []
    for row in rows:
        event_id = row[0]
        event_sequence = row[1]
        run_id = row[2]
        event_type = row[3]
        if not isinstance(event_id, str):
            raise TypeError("terminal event_id must be str")
        if not isinstance(event_sequence, int):
            raise TypeError("terminal event_sequence must be int")
        if not isinstance(run_id, str):
            raise TypeError("terminal run_id must be str")
        if not isinstance(event_type, str):
            raise TypeError("terminal event_type must be str")
        observations.append(
            StressTerminalObservation(
                run_id=run_id,
                event_id=event_id,
                event_sequence=event_sequence,
                terminal_kind=_terminal_kind_for_event_type(event_type),
                terminal_status=_terminal_status_for_event_type(event_type),
            )
        )
    return tuple(observations)


def terminal_event_count_for_runs(
    root_path: pathlib.Path,
    run_ids: Sequence[str],
) -> int:
    """读取指定 Run 的 Host-wide terminal EventLog 总数。

    本 helper 在 EventLog count 层显式纳入 ``RUN_LOST``，用于和 public
    terminal observation 交叉证明 Host-wide terminal closeout 不重复。

    每次调用都会打开新的短连接并执行一次短读，得到 point-in-time
    diagnostic；读取结果只用于 stress assertion message，不表达 watcher
    replay truth，也不替代 EventLog canonical fact。

    :param root_path: pytest 临时根目录。
    :param run_ids: 需要读取 terminal event 数量的 Run id 序列。
    :returns: 包含 ``RUN_LOST`` 的 terminal EventLog 总数。
    :raises ValueError: 任一 Run id 为空时抛出。
    :raises TypeError: durable row 字段类型不符合预期时抛出。
    """

    if len(run_ids) == 0:
        return 0
    for run_id in run_ids:
        if run_id.strip() == "":
            raise ValueError("run_id must be non-empty")

    placeholders = ",".join("?" for _run_id in run_ids)
    terminal_type_placeholders = ",".join("?" for _event_type in _ALL_RUN_TERMINAL_EVENT_TYPES)
    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        row = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM event_log
            WHERE run_id IN ({placeholders})
              AND event_type IN ({terminal_type_placeholders})
            """,
            tuple(run_ids) + _ALL_RUN_TERMINAL_EVENT_TYPES,
        ).fetchone()
    if row is None:
        return 0
    value = row[0]
    if not isinstance(value, int):
        raise TypeError("terminal event count must be int")
    return value


def run_lost_event_count(root_path: pathlib.Path) -> int:
    """统计 EventLog 中 ``RUN_LOST`` 事件数量。

    本函数只服务 Slice 4 stream exception closeout 诊断，避免测试文件复制
    durable event type 常量；读取结果不是生产 API，不替代 EventLog
    canonical fact。

    :param root_path: pytest 临时根目录。
    :returns: ``RUN_LOST`` 事件数量。
    :raises TypeError: 底层读取到非整数 count 时透传。
    """

    return recovery_event_type_count(root_path, _EVENT_TYPE_RUN_LOST)


def run_failed_reason_for_run(root_path: pathlib.Path, run_id: str) -> str | None:
    """读取指定 Run 的 ``RUN_FAILED`` reason。

    本 helper 只服务 stress 测试对 scheduler failed closeout 的直接证明；
    它读取 EventLog canonical fact 的 ``reason_json.reason``，不替代 public
    Host API，也不暴露 scheduler private state。

    :param root_path: pytest 临时根目录。
    :param run_id: 目标 Run id。
    :returns: 最近一条 ``RUN_FAILED`` 的 reason；不存在 reason 时返回
        ``None``。
    :raises ValueError: ``run_id`` 为空时抛出。
    :raises TypeError: durable reason 不是文本时抛出。
    """

    if run_id.strip() == "":
        raise ValueError("run_id must be non-empty")

    with sqlite3.connect(root_path / _HOST_DB_FILENAME) as connection:
        row = connection.execute(
            """
            SELECT json_extract(reason_json, ?)
            FROM event_log
            WHERE run_id = ?
              AND event_type = ?
            ORDER BY event_sequence DESC
            LIMIT 1
            """,
            (_EVENT_REASON_JSON_PATH, run_id, _EVENT_TYPE_RUN_FAILED),
        ).fetchone()
    if row is None:
        return None
    value = row[0]
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("RUN_FAILED reason must be text")
    return value


def _terminal_kind_for_event_type(event_type: str) -> HostEventKind:
    """把 durable terminal event type 映射为 public HostEvent kind。

    :param event_type: durable terminal event type。
    :returns: 对应的 ``HostEventKind``。
    :raises ValueError: ``event_type`` 不是 terminal event type 时抛出。
    """

    if event_type == _EVENT_TYPE_RUN_SUCCEEDED:
        return HostEventKind.SUCCEEDED
    if event_type == _EVENT_TYPE_RUN_FAILED:
        return HostEventKind.FAILED
    if event_type == _EVENT_TYPE_RUN_CANCELLED:
        return HostEventKind.CANCELLED
    if event_type == _EVENT_TYPE_RUN_LOST:
        return HostEventKind.LOST
    raise ValueError(f"unsupported terminal event type: {event_type}")


def _terminal_status_for_event_type(event_type: str) -> HostTerminalStatus:
    """把 durable terminal event type 映射为 public terminal status。

    :param event_type: durable terminal event type。
    :returns: 对应的 ``HostTerminalStatus``。
    :raises ValueError: ``event_type`` 不是 terminal event type 时抛出。
    """

    if event_type == _EVENT_TYPE_RUN_SUCCEEDED:
        return HostTerminalStatus.SUCCEEDED
    if event_type == _EVENT_TYPE_RUN_FAILED:
        return HostTerminalStatus.FAILED
    if event_type == _EVENT_TYPE_RUN_CANCELLED:
        return HostTerminalStatus.CANCELLED
    if event_type == _EVENT_TYPE_RUN_LOST:
        return HostTerminalStatus.LOST
    raise ValueError(f"unsupported terminal event type: {event_type}")


def _is_public_run_terminal(status: RunStatus) -> bool:
    """判断 public Run 状态是否为终态。

    :param status: Run 状态。
    :returns: succeeded/failed/cancelled/lost 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return status in {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.LOST,
    }
