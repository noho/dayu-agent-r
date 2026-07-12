"""WU-STRESS-01 Host production stress suite 哨兵测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from multiprocessing import Process

import pytest

from dayu.host import (
    CancelMode,
    CancelRunRequest,
    Host,
    HostEvent,
    HostEventKind,
    HostTerminalStatus,
    OutboxTerminalCursor,
    ReadOutboxTerminalItemsRequest,
    RunSnapshot,
    RunStatus,
    open_host,
)
from tests.host.public_smoke_support import (
    ensure_request,
    followup_request,
    host_context,
)
from tests.host.public_smoke_support import next_terminal_for_run
from tests.host.recovery_support import (
    AcceptedAttemptMarker,
    AsyncControlledFinalAnswerWorkerFactory,
    assert_process_exited_successfully,
    recovery_open_host_options,
    terminate_process,
    wait_for_accepted_marker,
    write_result_marker,
)
from tests.host.stress_support import (
    HostStressScenario,
    HostStressSummary,
    InspectableStressWorkerFactory,
    StressFailureBoundary,
    StressTerminalObservation,
    StressWorkerBehavior,
    assert_summary_ok,
    attempt_count_for_run,
    build_stress_open_host_options,
    close_host_event_iterator,
    compute_watch_lag,
    consume_terminals,
    count_event_type,
    DeterministicStressWorkerFactory,
    read_event_log_count,
    read_host_instances,
    read_session_terminal_sequences,
    run_failed_reason_for_run,
    run_blocking_stress_owner_process,
    run_open_probe_for_stress,
    start_and_crash_owner_for_stress,
    summary_to_json,
    run_lost_event_count,
    terminal_dedupe_ok,
    terminal_event_count_for_runs,
    terminal_events_for_runs,
    terminal_duplicate_count,
    verify_lane_released,
    wait_all_runs_terminal,
)

pytestmark = pytest.mark.stress

_SUMMARY_JSON_PROPERTY = "host_stress_summary"
_SCENARIO_NAME = "slice1-sentinel"
_SLICE2_SCENARIO_NAME = "repeated-startup-recovery-crash"
_CRASH_CYCLE_COUNT = 3
_EXPECTED_CRASH_ATTEMPT_COUNT = 2
_EXPECTED_LIVE_ATTEMPT_COUNT = 1
_EVENT_TYPE_ATTEMPT_LOST = "ATTEMPT_LOST"
_EVENT_TYPE_RUN_RECOVERING = "RUN_RECOVERING"
_PROCESS_START_TIMEOUT_SECONDS = 5.0
_PROCESS_JOIN_TIMEOUT_SECONDS = 5.0
_SLICE2_WATCH_LAG_PLACEHOLDER: int = 0
_SLICE2_WATCH_LAG_SAMPLES_PLACEHOLDER: tuple[int, ...] = (0,)
_SLICE3_SCENARIO_NAME = "sustained-watch-slow-consumer-reconnect"
_SLICE3_SESSION_COUNT = 3
_SLICE3_RUNS_PER_SESSION = 6
_SLICE3_RUN_COUNT = _SLICE3_SESSION_COUNT * _SLICE3_RUNS_PER_SESSION
_SLICE3_LANE_CAPACITY = 3
_SLICE3_LANE_TIMEOUT_SECONDS = 1.0
_SLICE3_PRIMARY_DELAY_SECONDS = 0.035
_SLICE3_CONSUME_TIMEOUT_SECONDS = 20.0
_SLICE3_WAIT_TIMEOUT_SECONDS = 5.0
_SLICE3_FINAL_WATCH_LAG_TOLERANCE = 0
_SLICE3_OUTBOX_LIMIT = 50
_SLICE3_SECONDARY_FIRST_TERMINAL_COUNT = 2
_SLICE3_SECONDARY_RECONNECT_TERMINAL_COUNT = 1
_SLICE3_DISCONNECT_GAP_RUN_COUNT = 3
_SLICE3_WATCH_LAG_PER_SESSION_LIMIT = _SLICE3_RUNS_PER_SESSION
_SLICE3_DR006_ACCEPTED_COUNT = 12
_SLICE4_SCENARIO_NAME = "scheduler-liveness-long-run-mixed-flow"
_SLICE4_SESSION_COUNT = 4
_SLICE4_LANE_CAPACITY = 1
_SLICE4_LANE_TIMEOUT_SECONDS = 1.0
_SLICE4_WAIT_TIMEOUT_SECONDS = 20.0
_SLICE4_CRASH_COUNT = 1
_SLICE4_EXPECTED_RECOVERY_COUNT = 1
_SLICE4_EXPECTED_LOST_COUNT = 1
_CLEAN_EOF_FAILED_REASON = "stream_ended_without_terminal"
_SLICE5_SCENARIO_NAME = "mixed-host-deterministic-fault-injection"
_SLICE5_SCENARIO = HostStressScenario(
    session_count=3,
    runs_per_session=5,
    crash_cycles=1,
    watch_delay=0.02,
    lane_capacity=1,
)
_SLICE5_RUN_COUNT = _SLICE5_SCENARIO.session_count * _SLICE5_SCENARIO.runs_per_session
_SLICE5_LANE_TIMEOUT_SECONDS = 1.0
_SLICE5_WAIT_TIMEOUT_SECONDS = 25.0
_SLICE5_CONSUME_TIMEOUT_SECONDS = 40.0
# session0 有 5 个 Run，但 crash/recovery 的 RUN_LOST 只进入 durable/public
# snapshot，不作为 HostEvent 发给 watcher；session1 无 lost，session2 的
# stream exception 同理不发 HostEvent，因此 primary 期望为 (4, 5, 4)。
_SLICE5_PRIMARY_TERMINAL_COUNTS: tuple[int, ...] = (4, 5, 4)
_SLICE5_SECONDARY_FIRST_TERMINAL_COUNT = 1
_SLICE5_SECONDARY_RECONNECT_TERMINAL_COUNT = 1
_SLICE5_EXPECTED_LOST_COUNT = 1
_SUMMARY_JSON_FIELDS: tuple[str, ...] = (
    "crash_count",
    "failure_boundary",
    "liveness_stale_detected",
    "recovery_count",
    "run_count",
    "scenario_name",
    "scheduler_drained",
    "session_count",
    "terminal_dedupe_ok",
    "terminal_duplicate_count",
    "watch_lag_max",
    "watch_lag_samples",
)


@dataclass(frozen=True, slots=True)
class Slice2LiveOwnerDiagnostics:
    """Slice 2 live owner probe 诊断。

    :param attempt_lost_delta: probe 期间 ATTEMPT_LOST 增量。
    :param recovery_delta: probe 期间 RUN_RECOVERING 增量。
    :param attempt_count: live owner run 的 Attempt 数。
    :returns: 不适用；dataclass 初始化返回实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    attempt_lost_delta: int
    recovery_delta: int
    attempt_count: int

    @property
    def probe_ok(self) -> bool:
        """返回 live owner probe 是否未产生误恢复事件。

        :returns: 两个增量均为 0 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.attempt_lost_delta == 0 and self.recovery_delta == 0

    @property
    def attempt_count_ok(self) -> bool:
        """返回 live owner run attempt 数是否保持为 1。

        :returns: attempt 数符合 Slice 2 期望时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.attempt_count == _EXPECTED_LIVE_ATTEMPT_COUNT


@dataclass(frozen=True, slots=True)
class Slice2RecoveryDiagnostics:
    """Slice 2 recovery 事件和 worker accept 诊断。

    :param recovery_count: 全场景 RUN_RECOVERING 数量。
    :param attempt_lost_count: 全场景 ATTEMPT_LOST 数量。
    :param recovery_accept_counts: 每轮 recovery worker accepted 数量。
    :param recovery_attempt_changed: 每轮 recovery attempt 是否换新。
    :returns: 不适用；dataclass 初始化返回实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    recovery_count: int
    attempt_lost_count: int
    recovery_accept_counts: tuple[int, ...]
    recovery_attempt_changed: tuple[bool, ...]

    @property
    def event_counts_ok(self) -> bool:
        """返回 recovery / lost 事件数量是否匹配 crash 次数。

        :returns: 两类事件数量均等于 crash 次数时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.recovery_count == _CRASH_CYCLE_COUNT and self.attempt_lost_count == _CRASH_CYCLE_COUNT

    @property
    def liveness_stale_detected(self) -> bool:
        """返回是否观测到预期 stale owner closeout。

        :returns: ``ATTEMPT_LOST`` 数量等于 crash 次数时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.attempt_lost_count == _CRASH_CYCLE_COUNT

    @property
    def worker_accepted_once(self) -> bool:
        """返回每轮 recovery worker 是否仅 accepted 一次。

        :returns: 每个计数均为 1 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return all(count == 1 for count in self.recovery_accept_counts)

    @property
    def attempts_changed(self) -> bool:
        """返回每轮 recovery 是否切换到新 attempt。

        :returns: 每轮 recovery attempt 均换新时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return all(self.recovery_attempt_changed)


@dataclass(frozen=True, slots=True)
class Slice2TerminalDiagnostics:
    """Slice 2 terminal observation 诊断。

    :param duplicate_count: terminal duplicate 数量。
    :param dedupe_ok: terminal 去重是否通过。
    :param observation_count: durable terminal 观测数量。
    :param run_count: 场景 Run 数量。
    :param crashed_statuses: crash run 的 public snapshot 状态。
    :param crashed_terminal_kinds: crash run 的 public terminal event kind。
    :param terminal_statuses: durable terminal observation 状态。
    :returns: 不适用；dataclass 初始化返回实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    duplicate_count: int
    dedupe_ok: bool
    observation_count: int
    run_count: int
    crashed_statuses: tuple[RunStatus, ...]
    crashed_terminal_kinds: tuple[HostEventKind, ...]
    terminal_statuses: tuple[HostTerminalStatus, ...]

    @property
    def terminal_dedupe_ok(self) -> bool:
        """返回 terminal 去重 predicate。

        :returns: duplicate 为 0 且 dedupe helper 通过时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.duplicate_count == 0 and self.dedupe_ok

    @property
    def count_ok(self) -> bool:
        """返回 terminal observation 数量是否覆盖所有 Run。

        :returns: terminal observation 数量等于 run 数量时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.observation_count == self.run_count

    @property
    def crashed_public_terminals_succeeded(self) -> bool:
        """返回 crashed runs 的 public 终态是否均成功。

        :returns: public snapshot 和 terminal event 均成功时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return all(status is RunStatus.SUCCEEDED for status in self.crashed_statuses) and all(
            kind is HostEventKind.SUCCEEDED for kind in self.crashed_terminal_kinds
        )

    @property
    def terminal_statuses_succeeded(self) -> bool:
        """返回 durable terminal observations 是否均为成功状态。

        :returns: 全部 terminal status 为 ``SUCCEEDED`` 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return all(status is HostTerminalStatus.SUCCEEDED for status in self.terminal_statuses)


@dataclass(frozen=True, slots=True)
class Slice2AttemptDiagnostics:
    """Slice 2 crashed run attempt 计数诊断。

    :param crashed_attempt_counts: 每个 crashed run 的 attempt 数。
    :returns: 不适用；dataclass 初始化返回实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    crashed_attempt_counts: tuple[int, ...]

    @property
    def crashed_attempt_counts_ok(self) -> bool:
        """返回 crashed run attempt 数是否符合 recovery 期望。

        :returns: 每个 crashed run attempt 数均为 2 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return all(count == _EXPECTED_CRASH_ATTEMPT_COUNT for count in self.crashed_attempt_counts)


@dataclass(frozen=True, slots=True)
class Slice2StressDiagnostics:
    """Slice 2 typed diagnostics 聚合。

    :param live_owner: live owner probe 诊断。
    :param recovery: recovery 事件和 worker accept 诊断。
    :param terminal: terminal observation 诊断。
    :param attempts: crashed run attempt 诊断。
    :returns: 不适用；dataclass 初始化返回实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    live_owner: Slice2LiveOwnerDiagnostics
    recovery: Slice2RecoveryDiagnostics
    terminal: Slice2TerminalDiagnostics
    attempts: Slice2AttemptDiagnostics

    @property
    def terminal_duplicate_count(self) -> int:
        """返回 terminal duplicate 数量。

        :returns: terminal duplicate 数量。
        :raises Exception: 不主动抛出异常。
        """

        return self.terminal.duplicate_count

    @property
    def terminal_dedupe_ok(self) -> bool:
        """返回 terminal 去重诊断是否通过。

        :returns: terminal 去重通过时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.terminal.terminal_dedupe_ok

    @property
    def liveness_stale_detected(self) -> bool:
        """返回 Slice 2 是否观测到预期 stale owner closeout。

        :returns: ``ATTEMPT_LOST`` 数量等于 crash 次数时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.recovery.liveness_stale_detected

    @property
    def scheduler_drained(self) -> bool:
        """返回 Slice 2 recovery/terminal drain 诊断是否收口。

        Slice 2 不做 Slice 4 的 scheduler long-run cleanup 证明；这里的
        ``scheduler_drained`` 仅表示本场景提交的 live/crashed runs 都已有
        terminal observation，crashed runs 均 public succeeded，recovery
        worker 每轮只 accepted 一次，且 attempt 计数收口。

        :returns: 本 Slice 2 drain 观测收口时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            self.terminal.count_ok
            and self.terminal.crashed_public_terminals_succeeded
            and self.terminal.terminal_statuses_succeeded
            and self.recovery.worker_accepted_once
            and self.recovery.attempts_changed
            and self.attempts.crashed_attempt_counts_ok
            and self.live_owner.attempt_count_ok
        )

    @property
    def failure_boundary(self) -> StressFailureBoundary | None:
        """基于同一组 Slice 2 predicate 返回失败边界。

        :returns: 成功时返回 ``None``，否则返回封闭失败边界。
        :raises Exception: 不主动抛出异常。
        """

        if not self.live_owner.probe_ok or not self.live_owner.attempt_count_ok:
            return "liveness"
        if not self.recovery.event_counts_ok:
            return "recovery"
        if not self.terminal.terminal_dedupe_ok or not self.terminal.count_ok:
            return "durable"
        if not self.terminal.crashed_public_terminals_succeeded:
            return "recovery"
        if not self.terminal.terminal_statuses_succeeded:
            return "durable"
        if not self.recovery.worker_accepted_once:
            return "worker_accept"
        if not self.recovery.attempts_changed:
            return "recovery"
        if not self.attempts.crashed_attempt_counts_ok:
            return "durable"
        return None


@dataclass(frozen=True, slots=True)
class Slice3WatchDiagnostics:
    """Slice 3 watch / reconnect 诊断。

    :param primary_events: primary watcher 观测到的 terminal 事件。
    :param secondary_first_events: secondary watcher 首次 attach 观测事件。
    :param secondary_reconnect_events: secondary watcher 重连后观测事件。
    :param expected_reconnect_run_id: secondary reconnect 后提交并期待观测的
        Run id。
    :param durable_observations: durable terminal 诊断观测。
    :param public_snapshots: 全部 Run 的 public snapshot。
    :param watch_lag_samples_by_session: 每个 primary watcher 的 watch lag 样本。
    :param final_watch_lags_by_session: 每个 primary watcher drain 后的最终 lag。
    :param event_log_count_before_consumer_cancel: consumer cancel 前 EventLog 计数。
    :param event_log_count_after_consumer_cancel: consumer cancel 后 EventLog 计数。
    :param worker_cancel_count_after_consumer_cancel: consumer cancel 后 worker cancel
        通知计数。
    :param gap_run_ids: secondary 断开窗口内提交的 Run id。
    :param outbox_gap_run_count: secondary 断开窗口内 Run 的 outbox 覆盖数量。
    :returns: 不适用；dataclass 初始化返回实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    primary_events: tuple[HostEvent, ...]
    secondary_first_events: tuple[HostEvent, ...]
    secondary_reconnect_events: tuple[HostEvent, ...]
    expected_reconnect_run_id: str
    durable_observations: tuple[StressTerminalObservation, ...]
    public_snapshots: tuple[RunSnapshot, ...]
    watch_lag_samples_by_session: tuple[tuple[int, ...], ...]
    final_watch_lags_by_session: tuple[int, ...]
    event_log_count_before_consumer_cancel: int
    event_log_count_after_consumer_cancel: int
    worker_cancel_count_after_consumer_cancel: int
    gap_run_ids: tuple[str, ...]
    outbox_gap_run_count: int

    @property
    def terminal_duplicate_count(self) -> int:
        """返回 durable terminal duplicate 数量。

        :returns: terminal duplicate 数量。
        :raises Exception: 不主动抛出异常。
        """

        return terminal_duplicate_count(self.durable_observations)

    @property
    def terminal_dedupe_ok(self) -> bool:
        """返回 durable terminal 去重是否通过。

        :returns: 去重通过时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.terminal_duplicate_count == 0 and terminal_dedupe_ok(self.durable_observations)

    @property
    def primary_observed_all_terminals(self) -> bool:
        """返回 primary watcher 是否覆盖所有 Run terminal。

        :returns: primary 观测 run_id 集合覆盖 durable 观测时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return _run_ids_from_events(self.primary_events) == _run_ids_from_observations(self.durable_observations)

    @property
    def public_snapshots_terminal(self) -> bool:
        """返回 public get_run snapshot 是否全部进入终态。

        :returns: 全部 snapshot 为 succeeded/failed/cancelled 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return all(_is_terminal_status(snapshot.status) for snapshot in self.public_snapshots)

    @property
    def consumer_cancel_ok(self) -> bool:
        """返回 consumer cancel 后 EventLog 与 worker cancel 诊断是否通过。

        测试主体单独执行四步验证中的 public ``get_run`` 非终态检查和释放
        worker 后正常 terminal 检查；本 predicate 只覆盖 diagnostics 中的
        两个结构化字段：EventLog count 不变、worker 未收到 cancel。

        :returns: EventLog count 不变且 worker 未收到 cancel 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            self.event_log_count_before_consumer_cancel == self.event_log_count_after_consumer_cancel
            and self.worker_cancel_count_after_consumer_cancel == 0
        )

    @property
    def reconnect_ok(self) -> bool:
        """返回 secondary watcher 重连后是否观察到指定 Run terminal。

        :returns: 重连后观察数量达标，且事件 run id 包含
            ``expected_reconnect_run_id`` 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            len(self.secondary_first_events) >= _SLICE3_SECONDARY_FIRST_TERMINAL_COUNT
            and len(self.secondary_reconnect_events) >= _SLICE3_SECONDARY_RECONNECT_TERMINAL_COUNT
            and self.expected_reconnect_run_id in _run_ids_from_events(self.secondary_reconnect_events)
        )

    @property
    def watch_lag_ok(self) -> bool:
        """返回 watch lag 是否满足 Slice 3 约束。

        :returns: 最大 lag 小于最终 EventLog 总量，且最终 drain 到容忍值内时
            返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        if len(self.watch_lag_samples_by_session) != _SLICE3_SESSION_COUNT:
            return False
        flattened = _flatten_int_groups(self.watch_lag_samples_by_session)
        if len(flattened) == 0:
            return False
        return (
            all(len(samples) > 0 for samples in self.watch_lag_samples_by_session)
            and max(flattened) < _SLICE3_WATCH_LAG_PER_SESSION_LIMIT
            and len(self.final_watch_lags_by_session) == _SLICE3_SESSION_COUNT
            and all(lag <= _SLICE3_FINAL_WATCH_LAG_TOLERANCE for lag in self.final_watch_lags_by_session)
        )

    @property
    def outbox_gap_coverage_ok(self) -> bool:
        """返回 Outbox 是否覆盖 secondary 断开窗口 terminal。

        :returns: Outbox 覆盖全部断开窗口 Run 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.outbox_gap_run_count == len(self.gap_run_ids)

    @property
    def disconnect_gap_terminal_truth_ok(self) -> bool:
        """返回断开窗口 terminal 是否有 primary/public/outbox/durable 证明。

        :returns: primary watcher、public snapshot、durable terminal observation
            与 Outbox 均覆盖断开窗口 Run 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        gap_run_ids = frozenset(self.gap_run_ids)
        public_gap_run_ids = frozenset(
            snapshot.run_id
            for snapshot in self.public_snapshots
            if snapshot.run_id in gap_run_ids and _is_terminal_status(snapshot.status)
        )
        return (
            len(self.gap_run_ids) == _SLICE3_DISCONNECT_GAP_RUN_COUNT
            and gap_run_ids <= _run_ids_from_events(self.primary_events)
            and gap_run_ids <= _run_ids_from_observations(self.durable_observations)
            and gap_run_ids <= public_gap_run_ids
            and self.outbox_gap_coverage_ok
        )

    @property
    def scheduler_drained(self) -> bool:
        """返回 Slice 3 提交 Run 是否全部收口。

        :returns: public snapshot、primary watcher 与 durable observation 均覆盖
            全部 Run 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            len(self.public_snapshots) == _SLICE3_RUN_COUNT
            and len(self.durable_observations) == _SLICE3_RUN_COUNT
            and len(self.primary_events) == _SLICE3_RUN_COUNT
            and self.public_snapshots_terminal
            and self.primary_observed_all_terminals
        )

    @property
    def failure_boundary(self) -> StressFailureBoundary | None:
        """返回 Slice 3 失败边界。

        :returns: 成功时返回 ``None``，否则返回封闭失败边界。
        :raises Exception: 不主动抛出异常。
        """

        if not self.consumer_cancel_ok:
            return "watch"
        if not self.reconnect_ok:
            return "watch_reconnect"
        if not self.scheduler_drained:
            return "scheduler"
        if not self.terminal_dedupe_ok:
            return "durable"
        if not self.watch_lag_ok:
            return "watch"
        if not self.outbox_gap_coverage_ok:
            return "projection"
        if not self.disconnect_gap_terminal_truth_ok:
            return "watch"
        return None


@dataclass(frozen=True, slots=True)
class Slice4SchedulerLivenessDiagnostics:
    """Slice 4 scheduler / liveness long-run 诊断。

    :param public_snapshots: 全部 Run 的 public terminal snapshot。
    :param durable_observations: public terminal EventLog 观测。
    :param all_terminal_event_count: 包含 ``RUN_LOST`` 的 terminal EventLog 数；
        该计数字段来自 ``terminal_event_count_for_runs()``，用于补足
        ``terminal_events_for_runs()`` 不建模 lost terminal observation 的
        去重证明边界。
    :param recovery_count: ``RUN_RECOVERING`` 事件数量。
    :param attempt_lost_count: ``ATTEMPT_LOST`` 事件数量。
    :param run_lost_count: ``RUN_LOST`` 事件数量。
    :param accepted_handle_count: worker accepted handle 数量。
    :param total_close_count: worker handle close 数量。
    :param total_cancel_count: worker handle cancel 通知数量。
    :param lane_released: Host close 后 lane 是否可立即 acquire。
    :param stale_instance_count: stale Host instance 诊断数量。
    :param clean_close_recovery_delta: clean close 后 reopen 的 recovery 事件增量。
    :param clean_close_attempt_lost_delta: clean close 后 reopen 的 lost 事件增量。
    :param clean_eof_run_id: clean EOF closeout 目标 Run id。
    :param clean_eof_failed_reason: clean EOF Run 对应的 ``RUN_FAILED`` reason。
    :returns: 不适用；dataclass 初始化返回实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    public_snapshots: tuple[RunSnapshot, ...]
    durable_observations: tuple[StressTerminalObservation, ...]
    all_terminal_event_count: int
    recovery_count: int
    attempt_lost_count: int
    run_lost_count: int
    accepted_handle_count: int
    total_close_count: int
    total_cancel_count: int
    lane_released: bool
    stale_instance_count: int
    clean_close_recovery_delta: int
    clean_close_attempt_lost_delta: int
    clean_eof_run_id: str
    clean_eof_failed_reason: str | None

    @property
    def terminal_duplicate_count(self) -> int:
        """返回 public terminal durable observation duplicate 数量。

        :returns: duplicate 数量。
        :raises Exception: 不主动抛出异常。
        """

        return terminal_duplicate_count(self.durable_observations)

    @property
    def terminal_dedupe_ok(self) -> bool:
        """返回 terminal 去重是否通过。

        ``terminal_events_for_runs()`` 只覆盖 HostEventKind /
        HostTerminalStatus 可表达的 succeeded/failed/cancelled terminal；
        ``RUN_LOST`` 当前没有对应 public terminal observation。因此 Slice 4
        的去重证明分两层：先证明可表达 terminal observation 没有重复，再
        用包含 ``RUN_LOST`` 的 EventLog terminal 总数等于 public terminal
        snapshot 数，显式证明 lost closeout 没有额外重复 terminal fact。

        :returns: 两层 terminal 去重证明均成立时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            self.terminal_duplicate_count == 0
            and terminal_dedupe_ok(self.durable_observations)
            and self.all_terminal_event_count == len(self.public_snapshots)
        )

    @property
    def scheduler_drained(self) -> bool:
        """返回 scheduler 是否已 drain 全部混合 Run。

        :returns: 所有 public snapshot 终态、handle 全 close 且 close 后没有
            clean recovery 增量时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            len(self.public_snapshots) == self.all_terminal_event_count
            and all(_is_terminal_status(snapshot.status) for snapshot in self.public_snapshots)
            and self.total_close_count == self.accepted_handle_count
            and self.clean_close_recovery_delta == 0
            and self.clean_close_attempt_lost_delta == 0
        )

    @property
    def liveness_stale_detected(self) -> bool:
        """返回是否只在 intentional crash/recovery 子流观测 stale。

        :returns: recovery / lost 计数等于 intentional crash 数且存在 stale
            instance diagnostic 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            self.recovery_count == _SLICE4_EXPECTED_RECOVERY_COUNT
            and self.attempt_lost_count >= _SLICE4_EXPECTED_RECOVERY_COUNT
            and self.stale_instance_count >= 1
            and self.clean_close_recovery_delta == 0
            and self.clean_close_attempt_lost_delta == 0
        )

    @property
    def handle_cleanup_ok(self) -> bool:
        """返回 handle close/cancel 诊断是否通过。

        :returns: 所有 accepted handle 均 close，且至少一次 active cancel
            传播到 worker 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.accepted_handle_count > 0 and self.total_close_count == self.accepted_handle_count and self.total_cancel_count >= 1

    @property
    def stream_exception_closeout_ok(self) -> bool:
        """返回 stream exception lost closeout 是否符合预期。

        :returns: ``RUN_LOST`` 数量符合 Slice 4 预期时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.run_lost_count == _SLICE4_EXPECTED_LOST_COUNT

    @property
    def clean_eof_failed_closeout_ok(self) -> bool:
        """返回 clean EOF scheduler failed closeout 是否符合预期。

        :returns: clean EOF Run 的 public snapshot 为 ``FAILED``，且 durable
            ``RUN_FAILED`` reason 为 stream EOF without terminal 时返回
            ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            any(
                snapshot.run_id == self.clean_eof_run_id and snapshot.status is RunStatus.FAILED
                for snapshot in self.public_snapshots
            )
            and self.clean_eof_failed_reason == _CLEAN_EOF_FAILED_REASON
        )

    @property
    def failure_boundary(self) -> StressFailureBoundary | None:
        """返回 Slice 4 失败边界。

        :returns: 成功时返回 ``None``，否则返回封闭失败边界。
        :raises Exception: 不主动抛出异常。
        """

        if not self.scheduler_drained:
            return "scheduler"
        if not self.liveness_stale_detected:
            return "liveness"
        if not self.handle_cleanup_ok:
            return "active_cleanup"
        if not self.lane_released:
            return "scheduler_close"
        if not self.stream_exception_closeout_ok:
            return "scheduler"
        if not self.clean_eof_failed_closeout_ok:
            return "scheduler_close"
        if not self.terminal_dedupe_ok:
            return "durable"
        return None


@dataclass(frozen=True, slots=True)
class Slice5MixedHostDiagnostics:
    """Slice 5 mixed Host stress 诊断。

    :param public_snapshots: 全部 Run 的 public terminal snapshot。
    :param primary_events: primary watchers 全程观测到的 public terminal 事件。
    :param secondary_first_events: secondary watcher 首次连接观测到的 terminal。
    :param secondary_reconnect_events: secondary watcher 重连后观测到的 terminal。
    :param expected_reconnect_run_id: secondary reconnect 后应观测到的 Run id。
    :param durable_observations: 可表达 public terminal 的 durable observation。
    :param all_terminal_event_count: 包含 ``RUN_LOST`` 的 terminal EventLog 数。
    :param watch_lag_samples_by_session: primary watcher 的 per-session lag 样本。
    :param final_watch_lags_by_session: primary watcher drain 后的最终 lag。
    :param recovery_count: ``RUN_RECOVERING`` 事件数量。
    :param attempt_lost_count: ``ATTEMPT_LOST`` 事件数量。
    :param run_lost_count: ``RUN_LOST`` 事件数量。
    :param accepted_handle_count: worker accepted handle 数量。
    :param total_close_count: worker handle close 数量。
    :param total_cancel_count: worker handle cancel 通知数量。
    :param lane_released: Host close 后 lane 是否可立即 acquire。
    :param stale_instance_count: stale Host instance 诊断数量。
    :param clean_close_recovery_delta: clean close 后 reopen 的 recovery 增量。
    :param clean_close_attempt_lost_delta: clean close 后 reopen 的 lost 增量。
    :returns: 不适用；dataclass 初始化返回实例。
    :raises Exception: 本类型不主动抛出异常。
    """

    public_snapshots: tuple[RunSnapshot, ...]
    primary_events: tuple[HostEvent, ...]
    secondary_first_events: tuple[HostEvent, ...]
    secondary_reconnect_events: tuple[HostEvent, ...]
    expected_reconnect_run_id: str
    durable_observations: tuple[StressTerminalObservation, ...]
    all_terminal_event_count: int
    watch_lag_samples_by_session: tuple[tuple[int, ...], ...]
    final_watch_lags_by_session: tuple[int, ...]
    recovery_count: int
    attempt_lost_count: int
    run_lost_count: int
    accepted_handle_count: int
    total_close_count: int
    total_cancel_count: int
    lane_released: bool
    stale_instance_count: int
    clean_close_recovery_delta: int
    clean_close_attempt_lost_delta: int

    @property
    def terminal_duplicate_count(self) -> int:
        """返回 public terminal durable observation duplicate 数量。

        :returns: duplicate 数量。
        :raises Exception: 不主动抛出异常。
        """

        return terminal_duplicate_count(self.durable_observations)

    @property
    def terminal_dedupe_ok(self) -> bool:
        """返回 mixed terminal 去重证明是否通过。

        :returns: public terminal observation 无重复且包含 ``RUN_LOST`` 的
            terminal EventLog 总数等于全部 public terminal snapshot 时返回
            ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            self.terminal_duplicate_count == 0
            and terminal_dedupe_ok(self.durable_observations)
            and self.all_terminal_event_count == len(self.public_snapshots)
        )

    @property
    def scheduler_drained(self) -> bool:
        """返回 mixed scheduler 是否完成 drain。

        :returns: 全部 Run 进入 public 终态、handle 均 close 且 clean reopen
            没有额外 recovery/lost 增量时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            len(self.public_snapshots) == _SLICE5_RUN_COUNT
            and self.all_terminal_event_count == _SLICE5_RUN_COUNT
            and all(_is_terminal_status(snapshot.status) for snapshot in self.public_snapshots)
            and self.total_close_count == self.accepted_handle_count
            and self.clean_close_recovery_delta == 0
            and self.clean_close_attempt_lost_delta == 0
        )

    @property
    def liveness_stale_detected(self) -> bool:
        """返回 intentional owner crash/recovery 是否被观测。

        :returns: recovery 数等于 crash 数、lost attempt 至少覆盖 crash 数，
            且存在 stale host instance diagnostic 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            self.recovery_count == _SLICE5_SCENARIO.crash_cycles
            and self.attempt_lost_count >= _SLICE5_SCENARIO.crash_cycles
            and self.stale_instance_count >= 1
        )

    @property
    def watch_lag_drained(self) -> bool:
        """返回 primary watcher lag 是否最终 drain。

        :returns: 每个 primary watcher 都有样本，且最终 lag 全部为 0 时返回
            ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            len(self.watch_lag_samples_by_session) == _SLICE5_SCENARIO.session_count
            and all(len(samples) > 0 for samples in self.watch_lag_samples_by_session)
            and len(self.final_watch_lags_by_session) == _SLICE5_SCENARIO.session_count
            and all(lag == 0 for lag in self.final_watch_lags_by_session)
        )

    @property
    def reconnect_ok(self) -> bool:
        """返回 secondary watcher 重连后是否观测到后续 terminal。

        :returns: 首次连接和重连后均达到期望 terminal 数，且重连事件包含
            指定 Run id 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            len(self.secondary_first_events) >= _SLICE5_SECONDARY_FIRST_TERMINAL_COUNT
            and len(self.secondary_reconnect_events) >= _SLICE5_SECONDARY_RECONNECT_TERMINAL_COUNT
            and self.expected_reconnect_run_id in _run_ids_from_events(self.secondary_reconnect_events)
        )

    @property
    def mixed_statuses_ok(self) -> bool:
        """返回 mixed fault script 是否覆盖全部目标终态。

        :returns: public snapshots 同时包含 succeeded、failed、cancelled 和
            lost 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        statuses = _snapshot_statuses(self.public_snapshots)
        return (
            RunStatus.SUCCEEDED in statuses
            and RunStatus.FAILED in statuses
            and RunStatus.CANCELLED in statuses
            and RunStatus.LOST in statuses
        )

    @property
    def cleanup_ok(self) -> bool:
        """返回 active cancel 与 lane cleanup 诊断是否通过。

        :returns: 至少一次 cancel 传播到 worker，全部 handle close，且 Host
            close 后 lane 可立即 acquire 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            self.accepted_handle_count > 0
            and self.total_close_count == self.accepted_handle_count
            and self.total_cancel_count >= 1
            and self.lane_released
        )

    @property
    def stream_exception_ok(self) -> bool:
        """返回 stream exception closeout 是否符合预期。

        :returns: ``RUN_LOST`` 数量等于 Slice 5 期望时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.run_lost_count == _SLICE5_EXPECTED_LOST_COUNT

    @property
    def failure_boundary(self) -> StressFailureBoundary | None:
        """返回 mixed stress 失败边界。

        :returns: 成功时返回 ``None``，否则返回封闭失败边界。
        :raises Exception: 不主动抛出异常。
        """

        if not self.scheduler_drained:
            return "scheduler"
        if not self.liveness_stale_detected:
            return "liveness"
        if not self.reconnect_ok:
            return "watch_reconnect"
        if not self.watch_lag_drained:
            return "watch"
        if not self.cleanup_ok:
            return "active_cleanup"
        if not self.stream_exception_ok:
            return "scheduler"
        if not self.terminal_dedupe_ok:
            return "durable"
        if not self.mixed_statuses_ok:
            return "unknown"
        return None


@pytest.mark.timeout(5)
def test_stress_marker_summary_contract(
    record_property: Callable[[str, str], None],
) -> None:
    """验证 stress summary JSON 字段和 terminal 去重 helper 基础契约。

    :param record_property: pytest 属性记录 fixture。
    :returns: ``None``。
    :raises AssertionError: summary 字段缺失或 terminal helper 行为不符时抛出。
    """

    duplicate_observations = (
        StressTerminalObservation(
            run_id="run-1",
            event_id="event-1",
            event_sequence=1,
            terminal_kind=HostEventKind.SUCCEEDED,
            terminal_status=HostTerminalStatus.SUCCEEDED,
        ),
        StressTerminalObservation(
            run_id="run-1",
            event_id="event-2",
            event_sequence=2,
            terminal_kind=HostEventKind.SUCCEEDED,
            terminal_status=HostTerminalStatus.SUCCEEDED,
        ),
    )
    assert terminal_duplicate_count(duplicate_observations) == 1
    assert not terminal_dedupe_ok(duplicate_observations)

    summary = HostStressSummary(
        scenario_name=_SCENARIO_NAME,
        session_count=1,
        run_count=1,
        crash_count=0,
        recovery_count=0,
        watch_lag_max=0,
        watch_lag_samples=(0,),
        scheduler_drained=True,
        liveness_stale_detected=False,
        terminal_duplicate_count=0,
        terminal_dedupe_ok=True,
        failure_boundary=None,
    )
    summary_json = summary_to_json(summary)
    record_property(_SUMMARY_JSON_PROPERTY, summary_json)

    for field_name in _SUMMARY_JSON_FIELDS:
        assert f'"{field_name}"' in summary_json
    assert f'"scenario_name": "{_SCENARIO_NAME}"' in summary_json
    assert_summary_ok(summary)


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_mixed_host_stress_deterministic_fault_injection(
    tmp_path: pathlib.Path,
    record_property: Callable[[str, str], None],
) -> None:
    """验证 deterministic fault injection 下的最终 mixed Host stress。

    :param tmp_path: pytest 临时目录。
    :param record_property: pytest 属性记录 fixture。
    :returns: ``None``。
    :raises AssertionError: mixed summary 任一验收字段不满足时抛出，message
        包含 summary JSON。
    """

    scenario = _SLICE5_SCENARIO
    run_ids: list[str] = []
    public_snapshots: tuple[RunSnapshot, ...] = ()
    primary_event_groups: tuple[tuple[HostEvent, ...], ...] = ()
    secondary_first_events: tuple[HostEvent, ...] = ()
    secondary_reconnect_events: tuple[HostEvent, ...] = ()
    reconnect_run_id = ""
    watch_lag_samples_by_session: list[list[int]] = [[] for _index in range(scenario.session_count)]
    last_primary_terminal_counts: list[int] = [0 for _index in range(scenario.session_count)]
    final_watch_lags_by_session: tuple[int, ...] = ()
    recovery_count_before_clean_reopen = 0
    attempt_lost_before_clean_reopen = 0
    factory = InspectableStressWorkerFactory()
    lane_released = False

    try:
        crashed = start_and_crash_owner_for_stress(
            tmp_path,
            slot_key="wu-stress-s5-session-0",
            client_request_id="wu-stress-s5-owner-crash",
            user_prompt="slice5 intentional owner crash",
        )
        run_ids.append(crashed.run_id)
        options = build_stress_open_host_options(
            tmp_path,
            factory,
            lane_capacity=scenario.lane_capacity,
            lane_timeout_seconds=_SLICE5_LANE_TIMEOUT_SECONDS,
        )

        async with open_host(options) as host:
            await wait_all_runs_terminal(
                host,
                (crashed.run_id,),
                _SLICE5_WAIT_TIMEOUT_SECONDS,
            )
            sessions = (
                await host.ensure_session(ensure_request("wu-stress-s5-session-0")),
                await host.ensure_session(ensure_request("wu-stress-s5-session-1")),
                await host.ensure_session(ensure_request("wu-stress-s5-session-2")),
            )
            session_ids = tuple(session.session_id for session in sessions)
            last_primary_terminal_counts = [
                len(read_session_terminal_sequences(tmp_path, session_id)) for session_id in session_ids
            ]
            primary_watchers = tuple(host.watch_session_events(session_id) for session_id in session_ids)
            primary_watchers_closed = [False for _index in range(scenario.session_count)]
            primary_observed_events = tuple(asyncio.Queue[HostEvent]() for _index in range(scenario.session_count))
            primary_tasks = tuple(
                asyncio.create_task(
                    consume_terminals(
                        watcher,
                        expected_count=_SLICE5_PRIMARY_TERMINAL_COUNTS[index],
                        delay_seconds=scenario.watch_delay,
                        timeout_seconds=_SLICE5_CONSUME_TIMEOUT_SECONDS,
                        observed_events=primary_observed_events[index],
                    )
                )
                for index, watcher in enumerate(primary_watchers)
            )
            secondary_watcher = host.watch_session_events(sessions[0].session_id)
            secondary_watcher_closed = False
            secondary_first_task = asyncio.create_task(
                consume_terminals(
                    secondary_watcher,
                    expected_count=_SLICE5_SECONDARY_FIRST_TERMINAL_COUNT,
                    delay_seconds=0,
                    timeout_seconds=_SLICE5_CONSUME_TIMEOUT_SECONDS,
                )
            )

            try:
                session0_initial_run_id = await _submit_followup_waiting_for_accept(
                    host,
                    factory,
                    sessions[0].session_id,
                    "wu-stress-s5-s0-initial-final",
                )
                run_ids.append(session0_initial_run_id)
                secondary_first_events = await secondary_first_task
                await close_host_event_iterator(secondary_watcher)
                secondary_watcher_closed = True
                last_primary_terminal_counts = _record_all_watch_lag_samples(
                    tmp_path,
                    session_ids,
                    primary_observed_events,
                    last_primary_terminal_counts,
                    watch_lag_samples_by_session,
                )

                session0_active_run_id = await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[0].session_id,
                    "wu-stress-s5-s0-active-final",
                    StressWorkerBehavior.BLOCKING_FINAL,
                )
                run_ids.append(session0_active_run_id)
                await _wait_run_status(host, session0_active_run_id, RunStatus.RUNNING)
                session0_queued_cancel_run_id = await _submit_followup(
                    host,
                    sessions[0].session_id,
                    "wu-stress-s5-s0-queued-cancel",
                )
                run_ids.append(session0_queued_cancel_run_id)
                await _cancel_run(host, session0_queued_cancel_run_id)
                factory.release_run(session0_active_run_id)
                await wait_all_runs_terminal(
                    host,
                    (session0_active_run_id, session0_queued_cancel_run_id),
                    _SLICE5_WAIT_TIMEOUT_SECONDS,
                )
                last_primary_terminal_counts = _record_all_watch_lag_samples(
                    tmp_path,
                    session_ids,
                    primary_observed_events,
                    last_primary_terminal_counts,
                    watch_lag_samples_by_session,
                )

                secondary_reconnect_watcher = host.watch_session_events(sessions[0].session_id)
                secondary_reconnect_task = asyncio.create_task(
                    consume_terminals(
                        secondary_reconnect_watcher,
                        expected_count=_SLICE5_SECONDARY_RECONNECT_TERMINAL_COUNT,
                        delay_seconds=0,
                        timeout_seconds=_SLICE5_CONSUME_TIMEOUT_SECONDS,
                    )
                )
                reconnect_run_id = await _submit_followup_waiting_for_accept(
                    host,
                    factory,
                    sessions[0].session_id,
                    "wu-stress-s5-s0-reconnect-final",
                )
                run_ids.append(reconnect_run_id)
                secondary_reconnect_events = await secondary_reconnect_task
                await close_host_event_iterator(secondary_reconnect_watcher)

                session1_active_cancel_run_id = await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[1].session_id,
                    "wu-stress-s5-s1-active-cancel",
                    StressWorkerBehavior.BLOCKING_FINAL,
                )
                run_ids.append(session1_active_cancel_run_id)
                await _wait_run_status(host, session1_active_cancel_run_id, RunStatus.RUNNING)
                await _cancel_run(host, session1_active_cancel_run_id)
                factory.release_run(session1_active_cancel_run_id)
                await wait_all_runs_terminal(
                    host,
                    (session1_active_cancel_run_id,),
                    _SLICE5_WAIT_TIMEOUT_SECONDS,
                )
                session1_failed_run_id = await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[1].session_id,
                    "wu-stress-s5-s1-failed",
                    StressWorkerBehavior.FAILED,
                )
                run_ids.append(session1_failed_run_id)
                session1_final_run_id = await _submit_followup_waiting_for_accept(
                    host,
                    factory,
                    sessions[1].session_id,
                    "wu-stress-s5-s1-final",
                )
                run_ids.append(session1_final_run_id)
                session1_second_failed_run_id = await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[1].session_id,
                    "wu-stress-s5-s1-second-failed",
                    StressWorkerBehavior.FAILED,
                )
                run_ids.append(session1_second_failed_run_id)
                session1_tail_final_run_id = await _submit_followup_waiting_for_accept(
                    host,
                    factory,
                    sessions[1].session_id,
                    "wu-stress-s5-s1-tail-final",
                )
                run_ids.append(session1_tail_final_run_id)
                last_primary_terminal_counts = _record_all_watch_lag_samples(
                    tmp_path,
                    session_ids,
                    primary_observed_events,
                    last_primary_terminal_counts,
                    watch_lag_samples_by_session,
                )

                session2_stream_lost_run_id = await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[2].session_id,
                    "wu-stress-s5-s2-stream-exception",
                    StressWorkerBehavior.STREAM_EXCEPTION,
                )
                run_ids.append(session2_stream_lost_run_id)
                await wait_all_runs_terminal(
                    host,
                    (session2_stream_lost_run_id,),
                    _SLICE5_WAIT_TIMEOUT_SECONDS,
                )
                session2_active_run_id = await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[2].session_id,
                    "wu-stress-s5-s2-active-final",
                    StressWorkerBehavior.BLOCKING_FINAL,
                )
                run_ids.append(session2_active_run_id)
                await _wait_run_status(host, session2_active_run_id, RunStatus.RUNNING)
                session2_queued_cancel_run_id = await _submit_followup(
                    host,
                    sessions[2].session_id,
                    "wu-stress-s5-s2-queued-cancel",
                )
                run_ids.append(session2_queued_cancel_run_id)
                await _cancel_run(host, session2_queued_cancel_run_id)
                factory.release_run(session2_active_run_id)
                await wait_all_runs_terminal(
                    host,
                    (session2_active_run_id, session2_queued_cancel_run_id),
                    _SLICE5_WAIT_TIMEOUT_SECONDS,
                )
                session2_failed_run_id = await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[2].session_id,
                    "wu-stress-s5-s2-failed",
                    StressWorkerBehavior.FAILED,
                )
                run_ids.append(session2_failed_run_id)
                session2_final_run_id = await _submit_followup_waiting_for_accept(
                    host,
                    factory,
                    sessions[2].session_id,
                    "wu-stress-s5-s2-final",
                )
                run_ids.append(session2_final_run_id)
                last_primary_terminal_counts = _record_all_watch_lag_samples(
                    tmp_path,
                    session_ids,
                    primary_observed_events,
                    last_primary_terminal_counts,
                    watch_lag_samples_by_session,
                )

                public_snapshots = await wait_all_runs_terminal(
                    host,
                    tuple(run_ids),
                    _SLICE5_WAIT_TIMEOUT_SECONDS,
                )
                primary_event_groups = tuple(await asyncio.gather(*primary_tasks))
                for index, watcher in enumerate(primary_watchers):
                    await close_host_event_iterator(watcher)
                    primary_watchers_closed[index] = True

                final_watch_lags_by_session = _compute_final_watch_lags_by_session(
                    tmp_path,
                    session_ids,
                    primary_observed_events,
                    last_primary_terminal_counts,
                )
                recovery_count_before_clean_reopen = count_event_type(tmp_path, _EVENT_TYPE_RUN_RECOVERING)
                attempt_lost_before_clean_reopen = count_event_type(tmp_path, _EVENT_TYPE_ATTEMPT_LOST)
            finally:
                if not secondary_first_task.done():
                    secondary_first_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await secondary_first_task
                if not secondary_watcher_closed:
                    with suppress(Exception):
                        await close_host_event_iterator(secondary_watcher)
                for task in primary_tasks:
                    if not task.done():
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                for index, watcher in enumerate(primary_watchers):
                    if not primary_watchers_closed[index]:
                        with suppress(Exception):
                            await close_host_event_iterator(watcher)

        lane_released = await verify_lane_released(options.lane_db_path, options.lane_name)
        reopen_factory = InspectableStressWorkerFactory()
        async with open_host(
            build_stress_open_host_options(
                tmp_path,
                reopen_factory,
                lane_capacity=scenario.lane_capacity,
                lane_timeout_seconds=_SLICE5_LANE_TIMEOUT_SECONDS,
            )
        ) as reopened:
            public_snapshots = await wait_all_runs_terminal(
                reopened,
                tuple(run_ids),
                _SLICE5_WAIT_TIMEOUT_SECONDS,
            )
    except TimeoutError as error:
        summary = _slice5_timeout_summary(len(run_ids))
        summary_json = summary_to_json(summary)
        record_property(_SUMMARY_JSON_PROPERTY, summary_json)
        raise AssertionError(summary_json) from error

    recovery_count = count_event_type(tmp_path, _EVENT_TYPE_RUN_RECOVERING)
    attempt_lost_count = count_event_type(tmp_path, _EVENT_TYPE_ATTEMPT_LOST)
    durable_observations = terminal_events_for_runs(tmp_path, tuple(run_ids))
    host_instances = read_host_instances(tmp_path)
    diagnostics = Slice5MixedHostDiagnostics(
        public_snapshots=public_snapshots,
        primary_events=_flatten_events(primary_event_groups),
        secondary_first_events=secondary_first_events,
        secondary_reconnect_events=secondary_reconnect_events,
        expected_reconnect_run_id=reconnect_run_id,
        durable_observations=durable_observations,
        all_terminal_event_count=terminal_event_count_for_runs(tmp_path, tuple(run_ids)),
        watch_lag_samples_by_session=tuple(tuple(samples) for samples in watch_lag_samples_by_session),
        final_watch_lags_by_session=final_watch_lags_by_session,
        recovery_count=recovery_count,
        attempt_lost_count=attempt_lost_count,
        run_lost_count=run_lost_event_count(tmp_path),
        accepted_handle_count=factory.accepted_handle_count,
        total_close_count=factory.total_close_count,
        total_cancel_count=factory.total_cancel_count,
        lane_released=lane_released,
        stale_instance_count=sum(1 for item in host_instances if item.heartbeat_stale),
        clean_close_recovery_delta=recovery_count - recovery_count_before_clean_reopen,
        clean_close_attempt_lost_delta=attempt_lost_count - attempt_lost_before_clean_reopen,
    )
    summary_watch_lag_samples = _flatten_int_groups(diagnostics.watch_lag_samples_by_session)
    summary = HostStressSummary(
        scenario_name=_SLICE5_SCENARIO_NAME,
        session_count=scenario.session_count,
        run_count=len(run_ids),
        crash_count=scenario.crash_cycles,
        recovery_count=recovery_count,
        watch_lag_max=max(summary_watch_lag_samples),
        watch_lag_samples=summary_watch_lag_samples,
        scheduler_drained=diagnostics.scheduler_drained,
        liveness_stale_detected=diagnostics.liveness_stale_detected,
        terminal_duplicate_count=diagnostics.terminal_duplicate_count,
        terminal_dedupe_ok=diagnostics.terminal_dedupe_ok,
        failure_boundary=diagnostics.failure_boundary,
    )
    summary_json = summary_to_json(summary)
    record_property(_SUMMARY_JSON_PROPERTY, summary_json)
    (tmp_path / "host-stress-summary.json").write_text(summary_json, encoding="utf-8")

    assert summary.session_count == scenario.session_count, summary_json
    assert summary.run_count == _SLICE5_RUN_COUNT, summary_json
    assert summary.crash_count >= 1, summary_json
    assert summary.recovery_count == summary.crash_count, summary_json
    assert summary.watch_lag_max >= 0, summary_json
    assert diagnostics.watch_lag_drained, summary_json
    assert summary.scheduler_drained, summary_json
    assert summary.liveness_stale_detected, summary_json
    assert summary.terminal_duplicate_count == 0, summary_json
    assert summary.terminal_dedupe_ok, summary_json
    assert diagnostics.mixed_statuses_ok, summary_json
    assert diagnostics.reconnect_ok, summary_json
    assert diagnostics.failure_boundary is None, summary_json
    assert_summary_ok(summary)


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_scheduler_liveness_long_run_mixed_flow_stress(
    tmp_path: pathlib.Path,
    record_property: Callable[[str, str], None],
) -> None:
    """验证 queued/active/terminal/cancel/recovery 混合流的 scheduler liveness。

    :param tmp_path: pytest 临时目录。
    :param record_property: pytest 属性记录 fixture。
    :returns: ``None``。
    :raises AssertionError: scheduler drain、liveness、lane release、handle
        cleanup 或 terminal duplicate 断言失败时抛出。
    """

    crashed = start_and_crash_owner_for_stress(
        tmp_path,
        slot_key="wu-stress-s4-crash",
        client_request_id="wu-stress-s4-crash-followup",
        user_prompt="slice4 intentional crash recovery",
    )
    factory = InspectableStressWorkerFactory()
    options = build_stress_open_host_options(
        tmp_path,
        factory,
        lane_capacity=_SLICE4_LANE_CAPACITY,
        lane_timeout_seconds=_SLICE4_LANE_TIMEOUT_SECONDS,
    )
    run_ids: list[str] = [crashed.run_id]
    public_snapshots: tuple[RunSnapshot, ...] = ()
    clean_eof_run_id = ""
    recovery_count_before_clean_reopen = 0
    attempt_lost_before_clean_reopen = 0

    async with open_host(options) as host:
        await wait_all_runs_terminal(
            host,
            (crashed.run_id,),
            _SLICE4_WAIT_TIMEOUT_SECONDS,
        )
        session_list = []
        for index in range(_SLICE4_SESSION_COUNT):
            session_list.append(await host.ensure_session(ensure_request(f"wu-stress-s4-{index}")))
        sessions = tuple(session_list)

        active_success_run_id = await _submit_scripted_followup(
            host,
            factory,
            sessions[0].session_id,
            "wu-stress-s4-active-success",
            StressWorkerBehavior.BLOCKING_FINAL,
        )
        run_ids.append(active_success_run_id)
        await _wait_run_status(host, active_success_run_id, RunStatus.RUNNING)
        queued_cancel_run_id = await _submit_followup(
            host,
            sessions[0].session_id,
            "wu-stress-s4-queued-cancel",
        )
        run_ids.append(queued_cancel_run_id)
        queued_tail_run_id = await _submit_followup(
            host,
            sessions[0].session_id,
            "wu-stress-s4-queued-tail",
        )
        run_ids.append(queued_tail_run_id)
        await _cancel_run(host, queued_cancel_run_id)
        factory.release_run(active_success_run_id)
        await wait_all_runs_terminal(
            host,
            (active_success_run_id, queued_cancel_run_id, queued_tail_run_id),
            _SLICE4_WAIT_TIMEOUT_SECONDS,
        )

        active_cancel_run_id = await _submit_scripted_followup(
            host,
            factory,
            sessions[1].session_id,
            "wu-stress-s4-active-cancel",
            StressWorkerBehavior.BLOCKING_FINAL,
        )
        run_ids.append(active_cancel_run_id)
        await _wait_run_status(host, active_cancel_run_id, RunStatus.RUNNING)
        await _cancel_run(host, active_cancel_run_id)
        factory.release_run(active_cancel_run_id)
        await wait_all_runs_terminal(
            host,
            (active_cancel_run_id,),
            _SLICE4_WAIT_TIMEOUT_SECONDS,
        )

        stream_lost_run_id = await _submit_scripted_followup(
            host,
            factory,
            sessions[2].session_id,
            "wu-stress-s4-stream-exception",
            StressWorkerBehavior.STREAM_EXCEPTION,
        )
        run_ids.append(stream_lost_run_id)
        failed_run_id = await _submit_scripted_followup(
            host,
            factory,
            sessions[3].session_id,
            "wu-stress-s4-failed",
            StressWorkerBehavior.FAILED,
        )
        run_ids.append(failed_run_id)
        clean_eof_run_id = await _submit_scripted_followup(
            host,
            factory,
            sessions[3].session_id,
            "wu-stress-s4-clean-eof",
            StressWorkerBehavior.CLEAN_EOF,
        )
        run_ids.append(clean_eof_run_id)
        public_snapshots = await wait_all_runs_terminal(
            host,
            tuple(run_ids),
            _SLICE4_WAIT_TIMEOUT_SECONDS,
        )
        recovery_count_before_clean_reopen = count_event_type(tmp_path, _EVENT_TYPE_RUN_RECOVERING)
        attempt_lost_before_clean_reopen = count_event_type(tmp_path, _EVENT_TYPE_ATTEMPT_LOST)

    lane_released = await verify_lane_released(options.lane_db_path, options.lane_name)
    reopen_factory = InspectableStressWorkerFactory()
    async with open_host(
        build_stress_open_host_options(
            tmp_path,
            reopen_factory,
            lane_capacity=_SLICE4_LANE_CAPACITY,
            lane_timeout_seconds=_SLICE4_LANE_TIMEOUT_SECONDS,
        )
    ) as reopened:
        public_snapshots = await wait_all_runs_terminal(
            reopened,
            tuple(run_ids),
            _SLICE4_WAIT_TIMEOUT_SECONDS,
        )

    recovery_count = count_event_type(tmp_path, _EVENT_TYPE_RUN_RECOVERING)
    attempt_lost_count = count_event_type(tmp_path, _EVENT_TYPE_ATTEMPT_LOST)
    durable_observations = terminal_events_for_runs(tmp_path, tuple(run_ids))
    host_instances = read_host_instances(tmp_path)
    diagnostics = Slice4SchedulerLivenessDiagnostics(
        public_snapshots=public_snapshots,
        durable_observations=durable_observations,
        all_terminal_event_count=terminal_event_count_for_runs(tmp_path, tuple(run_ids)),
        recovery_count=recovery_count,
        attempt_lost_count=attempt_lost_count,
        run_lost_count=run_lost_event_count(tmp_path),
        accepted_handle_count=factory.accepted_handle_count,
        total_close_count=factory.total_close_count,
        total_cancel_count=factory.total_cancel_count,
        lane_released=lane_released,
        stale_instance_count=sum(1 for item in host_instances if item.heartbeat_stale),
        clean_close_recovery_delta=recovery_count - recovery_count_before_clean_reopen,
        clean_close_attempt_lost_delta=attempt_lost_count - attempt_lost_before_clean_reopen,
        clean_eof_run_id=clean_eof_run_id,
        clean_eof_failed_reason=run_failed_reason_for_run(tmp_path, clean_eof_run_id),
    )
    watch_lag_max, watch_lag_samples = _slice2_watch_lag_placeholder()
    summary = HostStressSummary(
        scenario_name=_SLICE4_SCENARIO_NAME,
        session_count=_SLICE4_SESSION_COUNT + 1,
        run_count=len(run_ids),
        crash_count=_SLICE4_CRASH_COUNT,
        recovery_count=recovery_count,
        watch_lag_max=watch_lag_max,
        watch_lag_samples=watch_lag_samples,
        scheduler_drained=diagnostics.scheduler_drained,
        liveness_stale_detected=diagnostics.liveness_stale_detected,
        terminal_duplicate_count=diagnostics.terminal_duplicate_count,
        terminal_dedupe_ok=diagnostics.terminal_dedupe_ok,
        failure_boundary=diagnostics.failure_boundary,
    )
    summary_json = summary_to_json(summary)
    record_property(_SUMMARY_JSON_PROPERTY, summary_json)

    assert RunStatus.SUCCEEDED in _snapshot_statuses(public_snapshots), summary_json
    assert RunStatus.FAILED in _snapshot_statuses(public_snapshots), summary_json
    assert RunStatus.CANCELLED in _snapshot_statuses(public_snapshots), summary_json
    assert RunStatus.LOST in _snapshot_statuses(public_snapshots), summary_json
    assert diagnostics.clean_eof_failed_closeout_ok, summary_json
    assert diagnostics.failure_boundary is None, summary_json
    assert_summary_ok(summary)


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_repeated_startup_recovery_crash_stress(
    tmp_path: pathlib.Path,
    record_property: Callable[[str, str], None],
) -> None:
    """反复 crash/reopen recovery，并验证 live owner 不被误恢复。

    :param tmp_path: pytest 临时目录。
    :param record_property: pytest 属性记录 fixture。
    :returns: ``None``。
    :raises AssertionError: recovery、attempt、terminal 去重或 live owner
        防误恢复断言失败时抛出。
    """

    live_accepted, live_attempt_lost_delta, live_recovery_delta = _run_live_owner_probe(tmp_path)
    crashed: list[AcceptedAttemptMarker] = []
    crashed_statuses: list[RunStatus] = []
    crashed_terminal_kinds: list[HostEventKind] = []
    recovery_accept_counts: list[int] = []
    recovery_attempt_changed: list[bool] = []

    for cycle_index in range(_CRASH_CYCLE_COUNT):
        accepted = start_and_crash_owner_for_stress(
            tmp_path,
            slot_key=f"wu-stress-s2-crash-{cycle_index}",
            client_request_id=f"wu-stress-s2-crash-followup-{cycle_index}",
            user_prompt=f"recover crash cycle {cycle_index}",
            timeout_seconds=_PROCESS_START_TIMEOUT_SECONDS,
        )
        recovery_factory = AsyncControlledFinalAnswerWorkerFactory(f"stress-recovered-final-{cycle_index}")
        async with open_host(recovery_open_host_options(tmp_path, recovery_factory)) as host:
            watcher = host.watch_session_events(accepted.session_id)
            try:
                await asyncio.wait_for(
                    recovery_factory.accepted_event.wait(),
                    timeout=_PROCESS_START_TIMEOUT_SECONDS,
                )
                terminal_task = asyncio.create_task(next_terminal_for_run(watcher, accepted.run_id))
                recovery_factory.release_event.set()
                terminal = await asyncio.wait_for(
                    terminal_task,
                    timeout=_PROCESS_START_TIMEOUT_SECONDS,
                )
                final_snapshot = await host.get_run(accepted.run_id)
            finally:
                await close_host_event_iterator(watcher)

        crashed.append(accepted)
        crashed_statuses.append(final_snapshot.status)
        crashed_terminal_kinds.append(terminal.kind)
        recovery_accept_counts.append(len(recovery_factory.snapshots))
        recovery_attempt_changed.append(
            len(recovery_factory.snapshots) == 1 and recovery_factory.snapshots[0].attempt_id != accepted.attempt_id
        )

    crashed_run_ids = tuple(marker.run_id for marker in crashed)
    run_ids = crashed_run_ids + (live_accepted.run_id,)
    terminal_observations = terminal_events_for_runs(tmp_path, run_ids)
    recovery_count = count_event_type(tmp_path, _EVENT_TYPE_RUN_RECOVERING)
    attempt_lost_count = count_event_type(tmp_path, _EVENT_TYPE_ATTEMPT_LOST)
    crashed_attempt_counts = tuple(attempt_count_for_run(tmp_path, run_id) for run_id in crashed_run_ids)
    live_attempt_count = attempt_count_for_run(tmp_path, live_accepted.run_id)
    session_count = len(frozenset(marker.session_id for marker in crashed) | {live_accepted.session_id})
    diagnostics = Slice2StressDiagnostics(
        live_owner=Slice2LiveOwnerDiagnostics(
            attempt_lost_delta=live_attempt_lost_delta,
            recovery_delta=live_recovery_delta,
            attempt_count=live_attempt_count,
        ),
        recovery=Slice2RecoveryDiagnostics(
            recovery_count=recovery_count,
            attempt_lost_count=attempt_lost_count,
            recovery_accept_counts=tuple(recovery_accept_counts),
            recovery_attempt_changed=tuple(recovery_attempt_changed),
        ),
        terminal=Slice2TerminalDiagnostics(
            duplicate_count=terminal_duplicate_count(terminal_observations),
            dedupe_ok=terminal_dedupe_ok(terminal_observations),
            observation_count=len(terminal_observations),
            run_count=len(run_ids),
            crashed_statuses=tuple(crashed_statuses),
            crashed_terminal_kinds=tuple(crashed_terminal_kinds),
            terminal_statuses=tuple(observation.terminal_status for observation in terminal_observations),
        ),
        attempts=Slice2AttemptDiagnostics(
            crashed_attempt_counts=crashed_attempt_counts,
        ),
    )
    watch_lag_max, watch_lag_samples = _slice2_watch_lag_placeholder()
    summary = HostStressSummary(
        scenario_name=_SLICE2_SCENARIO_NAME,
        session_count=session_count,
        run_count=len(run_ids),
        crash_count=_CRASH_CYCLE_COUNT,
        recovery_count=recovery_count,
        watch_lag_max=watch_lag_max,
        watch_lag_samples=watch_lag_samples,
        scheduler_drained=diagnostics.scheduler_drained,
        liveness_stale_detected=diagnostics.liveness_stale_detected,
        terminal_duplicate_count=diagnostics.terminal_duplicate_count,
        terminal_dedupe_ok=diagnostics.terminal_dedupe_ok,
        failure_boundary=diagnostics.failure_boundary,
    )
    summary_json = summary_to_json(summary)
    record_property(_SUMMARY_JSON_PROPERTY, summary_json)

    _assert_slice2_diagnostics_ok(diagnostics, summary_json)
    assert_summary_ok(summary)


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_sustained_watch_slow_consumer_reconnect_stress(
    tmp_path: pathlib.Path,
    record_property: Callable[[str, str], None],
) -> None:
    """持续 watch 慢消费、consumer cancel 与 secondary reconnect stress。

    :param tmp_path: pytest 临时目录。
    :param record_property: pytest 属性记录 fixture。
    :returns: ``None``。
    :raises AssertionError: watch、reconnect、consumer cancel、terminal 去重或
        lag drain 断言失败时抛出。
    """

    factory = DeterministicStressWorkerFactory()
    options = build_stress_open_host_options(
        tmp_path,
        factory,
        lane_capacity=_SLICE3_LANE_CAPACITY,
        lane_timeout_seconds=_SLICE3_LANE_TIMEOUT_SECONDS,
    )
    run_ids: list[str] = []
    gap_run_ids: list[str] = []
    watch_lag_samples_by_session: list[list[int]] = [[] for _index in range(_SLICE3_SESSION_COUNT)]
    last_primary_terminal_counts: list[int] = [0 for _index in range(_SLICE3_SESSION_COUNT)]
    session_ids: tuple[str, ...] = ()
    secondary_first_events: tuple[HostEvent, ...] = ()
    secondary_reconnect_events: tuple[HostEvent, ...] = ()
    reconnect_run_id = ""
    public_snapshots: tuple[RunSnapshot, ...] = ()
    primary_event_groups: tuple[tuple[HostEvent, ...], ...] = ()
    final_watch_lags_by_session: tuple[int, ...] = ()
    event_log_count_before_cancel = 0
    event_log_count_after_cancel = 0
    worker_cancel_count_after_consumer_cancel = 0
    outbox_gap_run_count = 0

    async with open_host(options) as host:
        session_list = []
        for index in range(_SLICE3_SESSION_COUNT):
            session_list.append(await host.ensure_session(ensure_request(f"wu-stress-s3-{index}")))
        sessions = tuple(session_list)
        session_ids = tuple(session.session_id for session in sessions)
        primary_watchers = tuple(host.watch_session_events(session.session_id) for session in sessions)
        primary_watchers_closed = [False for _index in range(_SLICE3_SESSION_COUNT)]
        primary_observed_events = tuple(asyncio.Queue[HostEvent]() for _index in range(_SLICE3_SESSION_COUNT))
        primary_tasks = tuple(
            asyncio.create_task(
                consume_terminals(
                    watcher,
                    expected_count=_SLICE3_RUNS_PER_SESSION,
                    delay_seconds=_SLICE3_PRIMARY_DELAY_SECONDS,
                    timeout_seconds=_SLICE3_CONSUME_TIMEOUT_SECONDS,
                    observed_events=primary_observed_events[index],
                )
            )
            for index, watcher in enumerate(primary_watchers)
        )
        secondary_watcher = host.watch_session_events(sessions[0].session_id)
        secondary_first_task = asyncio.create_task(
            consume_terminals(
                secondary_watcher,
                expected_count=_SLICE3_SECONDARY_FIRST_TERMINAL_COUNT,
                delay_seconds=0,
                timeout_seconds=_SLICE3_CONSUME_TIMEOUT_SECONDS,
            )
        )
        cancel_probe_watcher = host.watch_session_events(sessions[0].session_id)
        cancel_probe_consumer = asyncio.create_task(_consume_until_cancelled(cancel_probe_watcher))

        try:
            probe_run_id = await _submit_scripted_followup(
                host,
                factory,
                sessions[0].session_id,
                "wu-stress-s3-s0-probe",
                StressWorkerBehavior.BLOCKING_FINAL,
            )
            run_ids.append(probe_run_id)
            await _wait_run_status(host, probe_run_id, RunStatus.RUNNING)
            event_log_count_before_cancel = read_event_log_count(tmp_path)

            cancel_probe_consumer.cancel()
            with suppress(asyncio.CancelledError):
                await cancel_probe_consumer
            probe_after_consumer_cancel = await host.get_run(probe_run_id)
            event_log_count_after_cancel = read_event_log_count(tmp_path)
            worker_cancel_count_after_consumer_cancel = len(factory.cancel_reasons)
            assert not _is_terminal_status(probe_after_consumer_cancel.status)
            await close_host_event_iterator(cancel_probe_watcher)

            factory.release_run(probe_run_id)
            await _wait_run_status(host, probe_run_id, RunStatus.SUCCEEDED)
            initial_final_run_id = await _submit_followup_waiting_for_accept(
                host,
                factory,
                sessions[0].session_id,
                "wu-stress-s3-s0-initial-final",
            )
            run_ids.append(initial_final_run_id)
            secondary_first_events = await secondary_first_task
            await close_host_event_iterator(secondary_watcher)
            last_primary_terminal_counts = _record_all_watch_lag_samples(
                tmp_path,
                session_ids,
                primary_observed_events,
                last_primary_terminal_counts,
                watch_lag_samples_by_session,
            )

            session1_active_run_id = await _submit_scripted_followup(
                host,
                factory,
                sessions[1].session_id,
                "wu-stress-s3-s1-active",
                StressWorkerBehavior.BLOCKING_FINAL,
            )
            run_ids.append(session1_active_run_id)
            session1_cancelled_run_id = await _submit_followup(
                host,
                sessions[1].session_id,
                "wu-stress-s3-s1-cancelled",
            )
            run_ids.append(session1_cancelled_run_id)
            await _cancel_run(host, session1_cancelled_run_id)
            factory.release_run(session1_active_run_id)
            await _wait_run_status(host, session1_active_run_id, RunStatus.SUCCEEDED)
            session1_failed_run_id = await _submit_scripted_followup(
                host,
                factory,
                sessions[1].session_id,
                "wu-stress-s3-s1-failed",
                StressWorkerBehavior.FAILED,
            )
            run_ids.append(session1_failed_run_id)
            session1_final_run_id = await _submit_followup_waiting_for_accept(
                host,
                factory,
                sessions[1].session_id,
                "wu-stress-s3-s1-final",
            )
            run_ids.append(session1_final_run_id)
            session1_second_failed_run_id = await _submit_scripted_followup(
                host,
                factory,
                sessions[1].session_id,
                "wu-stress-s3-s1-second-failed",
                StressWorkerBehavior.FAILED,
            )
            run_ids.append(session1_second_failed_run_id)
            session1_tail_final_run_id = await _submit_followup_waiting_for_accept(
                host,
                factory,
                sessions[1].session_id,
                "wu-stress-s3-s1-tail-final",
            )
            run_ids.append(session1_tail_final_run_id)
            last_primary_terminal_counts = _record_all_watch_lag_samples(
                tmp_path,
                session_ids,
                primary_observed_events,
                last_primary_terminal_counts,
                watch_lag_samples_by_session,
            )

            session2_final_run_id = await _submit_followup_waiting_for_accept(
                host,
                factory,
                sessions[2].session_id,
                "wu-stress-s3-s2-final",
            )
            run_ids.append(session2_final_run_id)
            session2_failed_run_id = await _submit_scripted_followup(
                host,
                factory,
                sessions[2].session_id,
                "wu-stress-s3-s2-failed",
                StressWorkerBehavior.FAILED,
            )
            run_ids.append(session2_failed_run_id)
            session2_active_run_id = await _submit_scripted_followup(
                host,
                factory,
                sessions[2].session_id,
                "wu-stress-s3-s2-active",
                StressWorkerBehavior.BLOCKING_FINAL,
            )
            run_ids.append(session2_active_run_id)
            session2_cancelled_run_id = await _submit_followup(
                host,
                sessions[2].session_id,
                "wu-stress-s3-s2-cancelled",
            )
            run_ids.append(session2_cancelled_run_id)
            await _cancel_run(host, session2_cancelled_run_id)
            factory.release_run(session2_active_run_id)
            await _wait_run_status(host, session2_active_run_id, RunStatus.SUCCEEDED)
            session2_tail_final_run_id = await _submit_followup_waiting_for_accept(
                host,
                factory,
                sessions[2].session_id,
                "wu-stress-s3-s2-tail-final",
            )
            run_ids.append(session2_tail_final_run_id)
            session2_tail_failed_run_id = await _submit_scripted_followup(
                host,
                factory,
                sessions[2].session_id,
                "wu-stress-s3-s2-tail-failed",
                StressWorkerBehavior.FAILED,
            )
            run_ids.append(session2_tail_failed_run_id)
            assert len(factory.accepted_snapshots) == _SLICE3_DR006_ACCEPTED_COUNT

            gap_run_ids.append(
                await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[0].session_id,
                    "wu-stress-s3-s0-gap-failed",
                    StressWorkerBehavior.FAILED,
                )
            )
            gap_run_ids.append(
                await _submit_followup_waiting_for_accept(
                    host,
                    factory,
                    sessions[0].session_id,
                    "wu-stress-s3-s0-gap-final",
                )
            )
            gap_run_ids.append(
                await _submit_scripted_followup(
                    host,
                    factory,
                    sessions[0].session_id,
                    "wu-stress-s3-s0-gap-second-failed",
                    StressWorkerBehavior.FAILED,
                )
            )
            run_ids.extend(gap_run_ids)
            # reconnect watcher 的 live cursor 必须在 gap terminal 全部 durable
            # commit 后取得；否则测试会把尚在 ingest 的旧 terminal 错当成
            # reconnect 之后的新事件，形成与 watch 契约无关的调度竞态。
            for gap_run_id in gap_run_ids:
                await _wait_run_terminal(host, gap_run_id)
            last_primary_terminal_counts = _record_all_watch_lag_samples(
                tmp_path,
                session_ids,
                primary_observed_events,
                last_primary_terminal_counts,
                watch_lag_samples_by_session,
            )

            secondary_reconnect_watcher = host.watch_session_events(sessions[0].session_id)
            secondary_reconnect_task = asyncio.create_task(
                consume_terminals(
                    secondary_reconnect_watcher,
                    expected_count=_SLICE3_SECONDARY_RECONNECT_TERMINAL_COUNT,
                    delay_seconds=0,
                    timeout_seconds=_SLICE3_CONSUME_TIMEOUT_SECONDS,
                )
            )
            reconnect_run_id = await _submit_followup_waiting_for_accept(
                host,
                factory,
                sessions[0].session_id,
                "wu-stress-s3-s0-reconnect-final",
            )
            run_ids.append(reconnect_run_id)
            secondary_reconnect_events = await secondary_reconnect_task
            assert reconnect_run_id in _run_ids_from_events(secondary_reconnect_events)
            await close_host_event_iterator(secondary_reconnect_watcher)
            last_primary_terminal_counts = _record_all_watch_lag_samples(
                tmp_path,
                session_ids,
                primary_observed_events,
                last_primary_terminal_counts,
                watch_lag_samples_by_session,
            )

            public_snapshot_list: list[RunSnapshot] = []
            for run_id in run_ids:
                public_snapshot_list.append(await _wait_run_terminal(host, run_id))
            public_snapshots = tuple(public_snapshot_list)
            primary_event_groups = tuple(await asyncio.gather(*primary_tasks))
            for index, watcher in enumerate(primary_watchers):
                await close_host_event_iterator(watcher)
                primary_watchers_closed[index] = True

            final_watch_lags_by_session = _compute_final_watch_lags_by_session(
                tmp_path,
                session_ids,
                primary_observed_events,
                last_primary_terminal_counts,
            )
            outbox_gap_run_count = await _read_outbox_gap_run_count(
                host,
                sessions[0].session_id,
                tuple(gap_run_ids),
            )
        finally:
            if not cancel_probe_consumer.done():
                cancel_probe_consumer.cancel()
                with suppress(asyncio.CancelledError):
                    await cancel_probe_consumer
            for task in primary_tasks:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            for index, watcher in enumerate(primary_watchers):
                if not primary_watchers_closed[index]:
                    with suppress(Exception):
                        await close_host_event_iterator(watcher)

    durable_observations = terminal_events_for_runs(tmp_path, tuple(run_ids))
    session_terminal_sequences = tuple(
        read_session_terminal_sequences(tmp_path, session_id) for session_id in session_ids
    )
    primary_events = _flatten_events(primary_event_groups)
    diagnostics = Slice3WatchDiagnostics(
        primary_events=primary_events,
        secondary_first_events=secondary_first_events,
        secondary_reconnect_events=secondary_reconnect_events,
        expected_reconnect_run_id=reconnect_run_id,
        durable_observations=durable_observations,
        public_snapshots=public_snapshots,
        watch_lag_samples_by_session=tuple(tuple(samples) for samples in watch_lag_samples_by_session),
        final_watch_lags_by_session=final_watch_lags_by_session,
        event_log_count_before_consumer_cancel=event_log_count_before_cancel,
        event_log_count_after_consumer_cancel=event_log_count_after_cancel,
        worker_cancel_count_after_consumer_cancel=(worker_cancel_count_after_consumer_cancel),
        gap_run_ids=tuple(gap_run_ids),
        outbox_gap_run_count=outbox_gap_run_count,
    )
    summary_watch_lag_samples = _flatten_int_groups(diagnostics.watch_lag_samples_by_session)
    terminal_statuses = tuple(snapshot.status for snapshot in public_snapshots)
    summary = HostStressSummary(
        scenario_name=_SLICE3_SCENARIO_NAME,
        session_count=_SLICE3_SESSION_COUNT,
        run_count=len(run_ids),
        crash_count=0,
        recovery_count=0,
        watch_lag_max=max(summary_watch_lag_samples),
        watch_lag_samples=summary_watch_lag_samples,
        scheduler_drained=diagnostics.scheduler_drained,
        liveness_stale_detected=False,
        terminal_duplicate_count=diagnostics.terminal_duplicate_count,
        terminal_dedupe_ok=diagnostics.terminal_dedupe_ok,
        failure_boundary=diagnostics.failure_boundary,
    )
    summary_json = summary_to_json(summary)
    record_property(_SUMMARY_JSON_PROPERTY, summary_json)

    assert len(run_ids) == _SLICE3_RUN_COUNT, summary_json
    assert all(len(sequences) == _SLICE3_RUNS_PER_SESSION for sequences in session_terminal_sequences), summary_json
    assert RunStatus.SUCCEEDED in terminal_statuses, summary_json
    assert RunStatus.FAILED in terminal_statuses, summary_json
    assert RunStatus.CANCELLED in terminal_statuses, summary_json
    assert diagnostics.failure_boundary is None, summary_json
    assert_summary_ok(summary)


async def _submit_scripted_followup(
    host: Host,
    factory: DeterministicStressWorkerFactory,
    session_id: str,
    client_request_id: str,
    behavior: StressWorkerBehavior,
) -> str:
    """提交带下一次 accept 脚本行为的 follow-up。

    :param host: public Host handle。
    :param factory: deterministic stress worker factory。
    :param session_id: 目标 Session id。
    :param client_request_id: follow-up 幂等请求 id。
    :param behavior: 下一次 worker accept 使用的行为。
    :returns: Host 接受的 Run id。
    :raises AssertionError: 超时未达到 accepted 数时抛出。
    """

    previous_accept_count = len(factory.accepted_snapshots)
    factory.enqueue_run_behavior(behavior)
    run_id = await _submit_followup(host, session_id, client_request_id)
    await _wait_accepted_count(factory, previous_accept_count + 1)
    return run_id


def _slice5_timeout_summary(run_count: int) -> HostStressSummary:
    """构造 Slice 5 timeout 失败摘要。

    该 helper 只在 mixed stress 的内部 deadline 触发时使用，确保
    AssertionError 仍携带结构化 summary JSON。它不读取 durable store，避免
    在失败清理窗口里引入新的 SQLite 争用或二次异常。

    :param run_count: timeout 发生时已提交或记录的 Run 数量。
    :returns: 带 ``failure_boundary="unknown"`` 的 HostStressSummary。
    :raises Exception: 不主动抛出异常。
    """

    return HostStressSummary(
        scenario_name=_SLICE5_SCENARIO_NAME,
        session_count=_SLICE5_SCENARIO.session_count,
        run_count=run_count,
        crash_count=_SLICE5_SCENARIO.crash_cycles,
        recovery_count=0,
        watch_lag_max=0,
        watch_lag_samples=(0,),
        scheduler_drained=False,
        liveness_stale_detected=False,
        terminal_duplicate_count=0,
        terminal_dedupe_ok=True,
        failure_boundary="unknown",
    )


async def _submit_followup_waiting_for_accept(
    host: Host,
    factory: DeterministicStressWorkerFactory,
    session_id: str,
    client_request_id: str,
) -> str:
    """提交默认脚本 follow-up，并等待其被 worker accept。

    :param host: public Host handle。
    :param factory: deterministic stress worker factory。
    :param session_id: 目标 Session id。
    :param client_request_id: follow-up 幂等请求 id。
    :returns: Host 接受的 Run id。
    :raises AssertionError: 超时未达到下一次 accepted 时抛出。
    """

    previous_accept_count = len(factory.accepted_snapshots)
    run_id = await _submit_followup(host, session_id, client_request_id)
    await _wait_accepted_count(factory, previous_accept_count + 1)
    return run_id


async def _submit_followup(
    host: Host,
    session_id: str,
    client_request_id: str,
) -> str:
    """提交 deterministic queue follow-up。

    :param host: public Host handle。
    :param session_id: 目标 Session id。
    :param client_request_id: follow-up 幂等请求 id。
    :returns: Host 接受的 Run id。
    :raises Exception: Host public API 失败时透传。
    """

    followup = await host.submit_followup(
        session_id,
        followup_request(
            session_id,
            client_request_id,
            f"deterministic stress prompt {client_request_id}",
        ),
    )
    return followup.accepted_run_id


async def _cancel_run(host: Host, run_id: str) -> RunSnapshot:
    """通过 public Host API 取消指定 Run。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :returns: 取消请求后的 Run snapshot。
    :raises Exception: Host public API 失败时透传。
    """

    return await host.cancel_run(
        run_id,
        CancelRunRequest(
            context=host_context(f"cancel-{run_id}"),
            client_request_id=f"cancel-{run_id}",
            reason="wu_stress_slice3_queued_cancel",
            mode=CancelMode.GRACEFUL,
        ),
    )


async def _wait_accepted_count(
    factory: DeterministicStressWorkerFactory,
    expected_count: int,
) -> None:
    """等待 deterministic worker accepted 数达到目标。

    :param factory: deterministic stress worker factory。
    :param expected_count: 期待的累计 accepted 数。
    :returns: ``None``。
    :raises AssertionError: 超时仍未达到期待数量时抛出。
    """

    deadline = asyncio.get_running_loop().time() + _SLICE3_WAIT_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        if len(factory.accepted_snapshots) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"accepted count did not reach {expected_count}: " f"{len(factory.accepted_snapshots)}")


async def _wait_run_status(
    host: Host,
    run_id: str,
    expected_status: RunStatus,
) -> RunSnapshot:
    """等待 Run 到达指定状态。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :param expected_status: 期待状态。
    :returns: 匹配状态的 Run snapshot。
    :raises AssertionError: 超时仍未到达期待状态时抛出。
    """

    deadline = asyncio.get_running_loop().time() + _SLICE3_WAIT_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        snapshot = await host.get_run(run_id)
        if snapshot.status is expected_status:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach {expected_status.value} status")


async def _wait_run_terminal(host: Host, run_id: str) -> RunSnapshot:
    """等待 Run 进入任一终态。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :returns: terminal Run snapshot。
    :raises AssertionError: 超时仍未进入终态时抛出。
    """

    deadline = asyncio.get_running_loop().time() + _SLICE3_WAIT_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        snapshot = await host.get_run(run_id)
        if _is_terminal_status(snapshot.status):
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach terminal status")


async def _consume_until_cancelled(iterator: AsyncIterator[HostEvent]) -> None:
    """持续消费 watcher，直到测试取消 consumer task。

    :param iterator: HostEvent async iterator。
    :returns: ``None``。
    :raises asyncio.CancelledError: 调用方取消任务时抛出。
    """

    async for _event in iterator:
        await asyncio.sleep(0)


def _record_all_watch_lag_samples(
    root_path: pathlib.Path,
    session_ids: Sequence[str],
    observed_events_by_session: Sequence[asyncio.Queue[HostEvent]],
    last_seen_terminal_counts: Sequence[int],
    samples_by_session: Sequence[list[int]],
) -> list[int]:
    """读取所有 primary watcher 的 per-session watch lag 样本。

    :param root_path: pytest 临时根目录。
    :param session_ids: primary watcher 对应的 Session id 序列。
    :param observed_events_by_session: 每个 primary watcher 的已观测事件队列。
    :param last_seen_terminal_counts: 每个 primary watcher 上一次记录的已观测
        terminal 数量。
    :param samples_by_session: 每个 primary watcher 的 watch lag 样本输出列表。
    :returns: 更新后的每个 primary watcher 已观测 terminal 数量。
    :raises ValueError: 序列长度不一致时抛出。
    :raises TypeError: durable 读取字段类型非法时抛出。
    """

    if not (
        len(session_ids) == len(observed_events_by_session) == len(last_seen_terminal_counts) == len(samples_by_session)
    ):
        raise ValueError("per-session watch lag inputs must have equal length")

    updated_counts: list[int] = []
    for index, session_id in enumerate(session_ids):
        updated_last_seen = _drain_observed_event_count(
            observed_events_by_session[index],
            last_seen_terminal_counts[index],
        )
        latest_session_terminal_count = _latest_session_terminal_count(
            root_path,
            session_id,
        )
        samples_by_session[index].append(
            compute_watch_lag(
                latest_session_terminal_count,
                updated_last_seen,
            )
        )
        updated_counts.append(updated_last_seen)
    return updated_counts


def _compute_final_watch_lags_by_session(
    root_path: pathlib.Path,
    session_ids: Sequence[str],
    observed_events_by_session: Sequence[asyncio.Queue[HostEvent]],
    last_seen_terminal_counts: Sequence[int],
) -> tuple[int, ...]:
    """计算所有 primary watcher drain 后的最终 per-session lag。

    :param root_path: pytest 临时根目录。
    :param session_ids: primary watcher 对应的 Session id 序列。
    :param observed_events_by_session: 每个 primary watcher 的已观测事件队列。
    :param last_seen_terminal_counts: 每个 primary watcher 上一次记录的已观测
        terminal 数量。
    :returns: 每个 primary watcher 的最终 lag 元组。
    :raises ValueError: 序列长度不一致时抛出。
    :raises TypeError: durable 读取字段类型非法时抛出。
    """

    if not (len(session_ids) == len(observed_events_by_session) == len(last_seen_terminal_counts)):
        raise ValueError("per-session final lag inputs must have equal length")

    final_lags: list[int] = []
    for index, session_id in enumerate(session_ids):
        final_seen_count = _drain_observed_event_count(
            observed_events_by_session[index],
            last_seen_terminal_counts[index],
        )
        final_lags.append(
            compute_watch_lag(
                _latest_session_terminal_count(root_path, session_id),
                final_seen_count,
            )
        )
    return tuple(final_lags)


def _latest_session_terminal_count(
    root_path: pathlib.Path,
    session_id: str,
) -> int:
    """读取指定 Session 当前 terminal EventLog 数量。

    :param root_path: pytest 临时根目录。
    :param session_id: 目标 Session id。
    :returns: Session 当前 terminal 数量。
    :raises ValueError: ``session_id`` 为空时由底层 helper 抛出。
    :raises TypeError: durable row 字段类型非法时由底层 helper 抛出。
    """

    return len(read_session_terminal_sequences(root_path, session_id))


def _drain_observed_event_count(
    observed_events: asyncio.Queue[HostEvent],
    last_seen_count: int,
) -> int:
    """清空 primary 观测队列并返回已观测 terminal 数量。

    :param observed_events: primary watcher 已观测事件队列。
    :param last_seen_count: 已知已观测 terminal 数量。
    :returns: 更新后的已观测 terminal 数量。
    :raises Exception: 不主动抛出异常。
    """

    updated = last_seen_count
    while True:
        try:
            observed_events.get_nowait()
        except asyncio.QueueEmpty:
            return updated
        updated += 1


async def _read_outbox_gap_run_count(
    host: Host,
    session_id: str,
    gap_run_ids: Sequence[str],
) -> int:
    """通过 public outbox 读取 secondary 断开窗口 Run 覆盖数。

    :param host: public Host handle。
    :param session_id: 目标 Session id。
    :param gap_run_ids: secondary 断开窗口提交的 Run id。
    :returns: outbox terminal items 覆盖的 gap Run 数量。
    :raises Exception: Host public API 失败时透传。
    """

    batch = await host.read_outbox_terminal_items(
        session_id,
        ReadOutboxTerminalItemsRequest(
            after=OutboxTerminalCursor(event_sequence=0),
            seen_terminal_event_ids=(),
            limit=_SLICE3_OUTBOX_LIMIT,
        ),
    )
    outbox_run_ids = frozenset(item.run_id for item in batch.items)
    return len(frozenset(gap_run_ids) & outbox_run_ids)


def _flatten_events(
    event_groups: Sequence[Sequence[HostEvent]],
) -> tuple[HostEvent, ...]:
    """拍平 watcher terminal 事件分组。

    :param event_groups: 多个 watcher 返回的事件序列。
    :returns: 拍平后的 HostEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    events: list[HostEvent] = []
    for group in event_groups:
        events.extend(group)
    return tuple(events)


def _flatten_int_groups(
    value_groups: Sequence[Sequence[int]],
) -> tuple[int, ...]:
    """拍平整数诊断分组。

    :param value_groups: 多组整数诊断值。
    :returns: 拍平后的整数元组。
    :raises Exception: 不主动抛出异常。
    """

    values: list[int] = []
    for group in value_groups:
        values.extend(group)
    return tuple(values)


def _snapshot_statuses(snapshots: Sequence[RunSnapshot]) -> frozenset[RunStatus]:
    """从 Run snapshot 序列提取状态集合。

    :param snapshots: Run snapshot 序列。
    :returns: RunStatus 集合。
    :raises Exception: 不主动抛出异常。
    """

    return frozenset(snapshot.status for snapshot in snapshots)


def _run_ids_from_events(events: Sequence[HostEvent]) -> frozenset[str]:
    """从 HostEvent 序列提取非空 Run id 集合。

    :param events: HostEvent 序列。
    :returns: Run id 集合。
    :raises Exception: 不主动抛出异常。
    """

    return frozenset(event.run_id for event in events if event.run_id is not None)


def _run_ids_from_observations(
    observations: Sequence[StressTerminalObservation],
) -> frozenset[str]:
    """从 durable terminal observation 提取 Run id 集合。

    :param observations: durable terminal observation 序列。
    :returns: Run id 集合。
    :raises Exception: 不主动抛出异常。
    """

    return frozenset(observation.run_id for observation in observations)


def _is_terminal_status(status: RunStatus) -> bool:
    """判断 RunStatus 是否为 Host public Run 终态。

    :param status: Run 状态。
    :returns: succeeded/failed/cancelled/lost 时返回 ``True``；这里刻意使用
        Host-wide public Run terminal 语义，不等同于 HostEventKind /
        HostTerminalStatus 可表达的 terminal observation 集合。
    :raises Exception: 不主动抛出异常。
    """

    return status in {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.LOST,
    }


def _run_live_owner_probe(
    tmp_path: pathlib.Path,
) -> tuple[AcceptedAttemptMarker, int, int]:
    """启动 live owner，并验证第二个 opener 不制造 recovery 事件。

    :param tmp_path: pytest 临时目录。
    :returns: live owner accepted marker、``ATTEMPT_LOST`` 增量、
        ``RUN_RECOVERING`` 增量。
    :raises TimeoutError: owner 未及时写入 accepted marker 时抛出。
    :raises AssertionError: owner/probe 子进程未成功退出或 owner 被 probe
        误杀时抛出。
    """

    accepted_marker = tmp_path / "wu-stress-s2-live-owner-accepted"
    release_marker = tmp_path / "wu-stress-s2-live-owner-release"
    owner_result_marker = tmp_path / "wu-stress-s2-live-owner-result"
    probe_result_marker = tmp_path / "wu-stress-s2-live-probe-result"
    owner_process = Process(
        target=run_blocking_stress_owner_process,
        args=(
            str(tmp_path),
            str(accepted_marker),
            str(release_marker),
            str(owner_result_marker),
            "wu-stress-s2-live-owner",
            "wu-stress-s2-live-followup",
            "keep live owner active",
        ),
    )
    owner_process.start()
    try:
        accepted = wait_for_accepted_marker(
            accepted_marker,
            _PROCESS_START_TIMEOUT_SECONDS,
        )
        before_attempt_lost = count_event_type(tmp_path, _EVENT_TYPE_ATTEMPT_LOST)
        before_recovery = count_event_type(tmp_path, _EVENT_TYPE_RUN_RECOVERING)

        probe_process = Process(
            target=run_open_probe_for_stress,
            args=(str(tmp_path), str(probe_result_marker)),
        )
        probe_process.start()
        assert_process_exited_successfully(probe_process)

        if not owner_process.is_alive():
            raise AssertionError("live owner process was stopped by probe")
        after_attempt_lost = count_event_type(tmp_path, _EVENT_TYPE_ATTEMPT_LOST)
        after_recovery = count_event_type(tmp_path, _EVENT_TYPE_RUN_RECOVERING)
        write_result_marker(release_marker, "release\n")
        owner_process.join(_PROCESS_JOIN_TIMEOUT_SECONDS)
        assert_process_exited_successfully(owner_process)
        return (
            accepted,
            after_attempt_lost - before_attempt_lost,
            after_recovery - before_recovery,
        )
    except BaseException as original_error:
        if owner_process.is_alive():
            try:
                terminate_process(owner_process)
            except BaseException as cleanup_error:
                raise cleanup_error from original_error
        raise


def _slice2_watch_lag_placeholder() -> tuple[int, tuple[int, ...]]:
    """返回 Slice 2 未测量 watch lag 的 summary 占位值。

    Slice 2 只验证 repeated startup/recovery/crash E2E，不测量 Slice 3 的
    watch lag。这里返回固定值仅用于满足 ``HostStressSummary`` 跨 slice
    schema，不表达 watcher replay truth 或 lag 上界。

    :returns: ``watch_lag_max`` 与 ``watch_lag_samples`` 占位值。
    :raises Exception: 不主动抛出异常。
    """

    return _SLICE2_WATCH_LAG_PLACEHOLDER, _SLICE2_WATCH_LAG_SAMPLES_PLACEHOLDER


def _assert_slice2_diagnostics_ok(
    diagnostics: Slice2StressDiagnostics,
    summary_json: str,
) -> None:
    """断言 Slice 2 diagnostics 通过。

    本断言复用 ``Slice2StressDiagnostics.failure_boundary`` 这一唯一
    predicate 真源；summary 的 ``failure_boundary`` 也来自同一个属性，
    避免测试断言和 summary 诊断各自维护一套条件。

    :param diagnostics: Slice 2 诊断集合。
    :param summary_json: 失败时输出的 summary JSON。
    :returns: ``None``。
    :raises AssertionError: 诊断存在失败边界时抛出。
    """

    assert diagnostics.failure_boundary is None, summary_json
