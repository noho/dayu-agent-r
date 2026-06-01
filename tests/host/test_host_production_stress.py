"""WU-STRESS-01 Host production stress suite 哨兵测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing import Process

import pytest

from dayu.host import HostEventKind, HostTerminalStatus, RunStatus, open_host
from tests.host.public_smoke_support import next_terminal_for_run
from tests.host.recovery_support import (
    AcceptedAttemptMarker,
    AsyncControlledFinalAnswerWorkerFactory,
    assert_process_exited_successfully,
    close_host_event_iterator,
    recovery_open_host_options,
    terminate_process,
    wait_for_accepted_marker,
    write_result_marker,
)
from tests.host.stress_support import (
    HostStressSummary,
    StressFailureBoundary,
    StressTerminalObservation,
    assert_summary_ok,
    attempt_count_for_run,
    count_event_type,
    run_blocking_stress_owner_process,
    run_open_probe_for_stress,
    start_and_crash_owner_for_stress,
    summary_to_json,
    terminal_dedupe_ok,
    terminal_events_for_runs,
    terminal_duplicate_count,
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

        return (
            self.recovery_count == _CRASH_CYCLE_COUNT
            and self.attempt_lost_count == _CRASH_CYCLE_COUNT
        )

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

        return all(
            status is RunStatus.SUCCEEDED for status in self.crashed_statuses
        ) and all(
            kind is HostEventKind.SUCCEEDED
            for kind in self.crashed_terminal_kinds
        )

    @property
    def terminal_statuses_succeeded(self) -> bool:
        """返回 durable terminal observations 是否均为成功状态。

        :returns: 全部 terminal status 为 ``SUCCEEDED`` 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return all(
            status is HostTerminalStatus.SUCCEEDED
            for status in self.terminal_statuses
        )


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

        return all(
            count == _EXPECTED_CRASH_ATTEMPT_COUNT
            for count in self.crashed_attempt_counts
        )


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

    live_accepted, live_attempt_lost_delta, live_recovery_delta = (
        _run_live_owner_probe(tmp_path)
    )
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
        recovery_factory = AsyncControlledFinalAnswerWorkerFactory(
            f"stress-recovered-final-{cycle_index}"
        )
        async with open_host(
            recovery_open_host_options(tmp_path, recovery_factory)
        ) as host:
            watcher = host.watch_session_events(accepted.session_id)
            try:
                await asyncio.wait_for(
                    recovery_factory.accepted_event.wait(),
                    timeout=_PROCESS_START_TIMEOUT_SECONDS,
                )
                terminal_task = asyncio.create_task(
                    next_terminal_for_run(watcher, accepted.run_id)
                )
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
            len(recovery_factory.snapshots) == 1
            and recovery_factory.snapshots[0].attempt_id != accepted.attempt_id
        )

    crashed_run_ids = tuple(marker.run_id for marker in crashed)
    run_ids = crashed_run_ids + (live_accepted.run_id,)
    terminal_observations = terminal_events_for_runs(tmp_path, run_ids)
    recovery_count = count_event_type(tmp_path, _EVENT_TYPE_RUN_RECOVERING)
    attempt_lost_count = count_event_type(tmp_path, _EVENT_TYPE_ATTEMPT_LOST)
    crashed_attempt_counts = tuple(
        attempt_count_for_run(tmp_path, run_id) for run_id in crashed_run_ids
    )
    live_attempt_count = attempt_count_for_run(tmp_path, live_accepted.run_id)
    session_count = len(
        frozenset(marker.session_id for marker in crashed)
        | {live_accepted.session_id}
    )
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
            terminal_statuses=tuple(
                observation.terminal_status
                for observation in terminal_observations
            ),
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
