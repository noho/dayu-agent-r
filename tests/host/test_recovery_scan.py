"""Host startup recovery scan 测试。"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import (
    AttemptStatus,
    EnsureSessionRequest,
    HostMetadataEntry,
    RunStatus,
)
from dayu.host.queue_policy import RunQueuePolicy
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventClass, EventLogAppendRequest, EventLogStore
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    CreateAcceptedRunInput,
    CreateQueuedRunInput,
    CreateRunningRunInput,
    create_accepted_run_in_transaction,
    create_queued_run_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_SESSION_SLOTS,
)
from dayu.host.durable.state import (
    DispatchRecordStatus,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
    serialize_run_start_reason,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.recovery import (
    StartupRecoveryDecision,
    StartupRecoveryPolicy,
    StartupRecoveryScanner,
)
from dayu.host.recovery_process import ProcessEvidence

_NOW = datetime(2026, 5, 19, 3, 4, 5, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "recovery-scan-test"})
_INPUT_DIGEST = sha256_digest_json({"input": "hello"})
_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST = "cancel_in_flight_attempt_lost"
_EVENT_TYPE_ATTEMPT_LOST = "ATTEMPT_LOST"
_EVENT_TYPE_CANCEL_REQUESTED = "CANCEL_REQUESTED"
_EVENT_TYPE_RUN_CANCELLING = "RUN_CANCELLING"
_EVENT_TYPE_RUN_LOST = "RUN_LOST"
_EVENT_TYPE_RUN_RECOVERING = "RUN_RECOVERING"
_REASON_OWNER_HEARTBEAT_RECENT = "owner_heartbeat_recent"
_REASON_PROCESS_PROBE_ERROR = "process_probe_error"
_REASON_PID_LIVE_WITHOUT_IDENTITY = "owner_pid_live_without_identity_proof"
_REASON_WAITING_ADAPTER_OBSERVATION_UNAVAILABLE = "waiting_adapter_observation_unavailable"
_REASON_MISSING_CURRENT_ATTEMPT_OR_DISPATCH = "missing_current_attempt_or_dispatch"
_COVERAGE_EXISTING = "existing"
_COVERAGE_NEW = "new"
_COVERAGE_NON_GOAL = "non-goal"


@dataclass(frozen=True, slots=True)
class _RecoveryLifecycleMatrixRow:
    """WU-LIFE recovery lifecycle proof matrix 行。

    :param scenario_id: 场景稳定 id。
    :param run_status: 场景入口 Run status 或非 Run 型治理描述。
    :param owner_proof_or_dispatch_condition: owner proof、dispatch 或治理条件。
    :param expected_decision: 期望 scanner / dispatcher 决策。
    :param expected_durable_mutation: 期望 durable mutation。
    :param expected_reason: 期望结构化 reason。
    :param coverage_classification: 覆盖分类：existing、new 或 non-goal。
    """

    scenario_id: str
    run_status: str
    owner_proof_or_dispatch_condition: str
    expected_decision: str
    expected_durable_mutation: str
    expected_reason: str
    coverage_classification: str


_RECOVERY_LIFECYCLE_PROOF_MATRIX: tuple[_RecoveryLifecycleMatrixRow, ...] = (
    _RecoveryLifecycleMatrixRow(
        scenario_id="accepted-startup-wake",
        run_status=RunStatus.ACCEPTED.value,
        owner_proof_or_dispatch_condition="unstarted run requires queue promotion wake",
        expected_decision=StartupRecoveryDecision.ACCEPTED_WAKE.value,
        expected_durable_mutation="none",
        expected_reason="accepted",
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="queued-startup-promotion-check",
        run_status=RunStatus.QUEUED.value,
        owner_proof_or_dispatch_condition="queued run requires queue promotion check",
        expected_decision=StartupRecoveryDecision.QUEUE_PROMOTION_CHECK.value,
        expected_durable_mutation="none",
        expected_reason="queued",
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="waiting-diagnostic-only-low-level",
        run_status=RunStatus.WAITING.value,
        owner_proof_or_dispatch_condition="wait adapter observation unavailable at startup",
        expected_decision=StartupRecoveryDecision.WAITING_DIAGNOSTIC_ONLY.value,
        expected_durable_mutation="none",
        expected_reason=_REASON_WAITING_ADAPTER_OBSERVATION_UNAVAILABLE,
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="waiting-durable-read-diagnostic-only",
        run_status=RunStatus.WAITING.value,
        owner_proof_or_dispatch_condition="durable read preserves WAITING semantics after startup scan",
        expected_decision=StartupRecoveryDecision.WAITING_DIAGNOSTIC_ONLY.value,
        expected_durable_mutation="none",
        expected_reason=_REASON_WAITING_ADAPTER_OBSERVATION_UNAVAILABLE,
        coverage_classification=_COVERAGE_NEW,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="running-positive-orphan-projection-lag",
        run_status=RunStatus.RUNNING.value,
        owner_proof_or_dispatch_condition="stale owner pid missing with projection lag marker",
        expected_decision=StartupRecoveryDecision.RUN_RECOVERING.value,
        expected_durable_mutation="ATTEMPT_LOST,RUN_RECOVERING",
        expected_reason="startup_orphan_attempt_lost",
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="running-owner-heartbeat-recent",
        run_status=RunStatus.RUNNING.value,
        owner_proof_or_dispatch_condition="owner heartbeat is inside stale threshold",
        expected_decision=StartupRecoveryDecision.OWNER_STILL_LIVE.value,
        expected_durable_mutation="none",
        expected_reason=_REASON_OWNER_HEARTBEAT_RECENT,
        coverage_classification=_COVERAGE_NEW,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="running-process-probe-error",
        run_status=RunStatus.RUNNING.value,
        owner_proof_or_dispatch_condition="process probe returns an error for stale owner",
        expected_decision=StartupRecoveryDecision.ORPHAN_INCONCLUSIVE.value,
        expected_durable_mutation="none",
        expected_reason=_REASON_PROCESS_PROBE_ERROR,
        coverage_classification=_COVERAGE_NEW,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="running-stale-heartbeat-only",
        run_status=RunStatus.RUNNING.value,
        owner_proof_or_dispatch_condition="stale heartbeat without process identity proof",
        expected_decision=StartupRecoveryDecision.ORPHAN_INCONCLUSIVE.value,
        expected_durable_mutation="none",
        expected_reason=_REASON_PID_LIVE_WITHOUT_IDENTITY,
        coverage_classification=_COVERAGE_NEW,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="running-missing-current-attempt-or-dispatch",
        run_status=RunStatus.RUNNING.value,
        owner_proof_or_dispatch_condition="current Attempt or dispatch record is absent",
        expected_decision=StartupRecoveryDecision.ORPHAN_INCONCLUSIVE.value,
        expected_durable_mutation="none",
        expected_reason=_REASON_MISSING_CURRENT_ATTEMPT_OR_DISPATCH,
        coverage_classification=_COVERAGE_NEW,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="cancelling-positive-orphan",
        run_status=RunStatus.CANCELLING.value,
        owner_proof_or_dispatch_condition="stale owner pid missing during cancellation",
        expected_decision=StartupRecoveryDecision.RUN_LOST.value,
        expected_durable_mutation="ATTEMPT_LOST,RUN_LOST",
        expected_reason=_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST,
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="recovering-under-dispatch-limit",
        run_status=RunStatus.RECOVERING.value,
        owner_proof_or_dispatch_condition="canonical recovery dispatch count under limit",
        expected_decision=StartupRecoveryDecision.RECOVERY_DISPATCHED.value,
        expected_durable_mutation="RUN_STARTED,ATTEMPT_STARTED,dispatch record",
        expected_reason=RunStartReason.RECOVERY.value,
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="recovering-over-dispatch-limit-projection-lag",
        run_status=RunStatus.RECOVERING.value,
        owner_proof_or_dispatch_condition="canonical EventLog recovery count reaches limit",
        expected_decision=StartupRecoveryDecision.RUN_LOST.value,
        expected_durable_mutation="RUN_LOST",
        expected_reason="startup_recovery_dispatch_limit_exceeded",
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="old-execution-late-terminal-after-recovery",
        run_status=RunStatus.RECOVERING.value,
        owner_proof_or_dispatch_condition="late terminal event targets old execution",
        expected_decision="late execution rejected",
        expected_durable_mutation="none",
        expected_reason="execution_attempt_mismatch",
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="live-owner-multiprocess",
        run_status=RunStatus.RUNNING.value,
        owner_proof_or_dispatch_condition="separate process owner is live",
        expected_decision=StartupRecoveryDecision.OWNER_STILL_LIVE.value,
        expected_durable_mutation="none",
        expected_reason="multiprocess live owner proof",
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="owner-crash-public-stream-recovery",
        run_status=RunStatus.RUNNING.value,
        owner_proof_or_dispatch_condition="owner process exits before reopen",
        expected_decision=StartupRecoveryDecision.RECOVERY_DISPATCHED.value,
        expected_durable_mutation="ATTEMPT_LOST,RUN_RECOVERING,RUN_STARTED",
        expected_reason="public stream observes recovered final answer",
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="startup-dispatch-failure-reason-mapping",
        run_status="startup/dispatch governance",
        owner_proof_or_dispatch_condition="timeout, dispatch failure, stream failure",
        expected_decision="reason mapping preserved",
        expected_durable_mutation="covered by scheduler tests",
        expected_reason="existing scheduler diagnostics",
        coverage_classification=_COVERAGE_EXISTING,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="stress-repeated-crash-recovery-terminal-dedupe",
        run_status="stress",
        owner_proof_or_dispatch_condition="repeated crash and recovery loop",
        expected_decision="stress evidence only",
        expected_durable_mutation="not in default validation",
        expected_reason="stress coverage outside work unit",
        coverage_classification=_COVERAGE_NON_GOAL,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="rr-dur-01-projection-checkpoint-cas-race",
        run_status="durable governance",
        owner_proof_or_dispatch_condition="true multiprocess projection checkpoint CAS race",
        expected_decision="out of scope",
        expected_durable_mutation="none",
        expected_reason="recovery scanner does not depend on projection checkpoint",
        coverage_classification=_COVERAGE_NON_GOAL,
    ),
    _RecoveryLifecycleMatrixRow(
        scenario_id="rr-dur-04-short-transaction-durable-truth",
        run_status="durable governance",
        owner_proof_or_dispatch_condition=(
            "scanner writes decisions inside run_write using durable Run/Attempt/" "EventLog/dispatch/liveness truth"
        ),
        expected_decision="short transaction durable truth",
        expected_durable_mutation="no production rewrite",
        expected_reason="projection lag covered by existing scanner tests",
        coverage_classification=_COVERAGE_NEW,
    ),
)


@dataclass(frozen=True, slots=True)
class _PidLiveNoIdentityProbe:
    """测试用 pid live without identity probe。"""

    def collect(self, pid: int) -> ProcessEvidence:
        """返回 pid 存活但缺少身份指纹的证据。

        :param pid: 目标 pid。
        :returns: pid 存活证据。
        """

        return ProcessEvidence(
            pid=pid,
            exists=True,
            observed_start_token=None,
            observed_boot_id=None,
            probe_error_code=None,
        )


@dataclass(frozen=True, slots=True)
class _PidProbeErrorProbe:
    """测试用 process probe error probe。"""

    def collect(self, pid: int) -> ProcessEvidence:
        """返回进程探测错误证据。

        :param pid: 目标 pid。
        :returns: 带错误码的进程证据。
        """

        return ProcessEvidence(
            pid=pid,
            exists=True,
            observed_start_token=None,
            observed_boot_id=None,
            probe_error_code="permission_denied",
        )


@dataclass(frozen=True, slots=True)
class _ActiveRunObservation:
    """scanner 前后 active Run durable 观测。

    :param run_status: Run 状态。
    :param run_updated_at: Run updated_at。
    :param current_attempt_id: Run current_attempt_id。
    :param attempt_status: Attempt 状态。
    :param attempt_updated_at: Attempt updated_at。
    :param attempt_terminal_event_id: Attempt terminal event id。
    :param dispatch_status: dispatch record 状态。
    :param dispatch_updated_at: dispatch record updated_at。
    :param dispatch_cancelled_event_id: dispatch cancelled event id。
    :param dispatch_owner_host_instance_id: dispatch owner host instance id。
    :param event_types: canonical EventLog event type 序列。
    """

    run_status: str
    run_updated_at: str
    current_attempt_id: str
    attempt_status: AttemptStatus
    attempt_updated_at: str
    attempt_terminal_event_id: str | None
    dispatch_status: DispatchRecordStatus
    dispatch_updated_at: str
    dispatch_cancelled_event_id: str | None
    dispatch_owner_host_instance_id: str | None
    event_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PidMissingProbe:
    """测试用 pid missing probe。"""

    def collect(self, pid: int) -> ProcessEvidence:
        """返回 pid 不存在证据。

        :param pid: 目标 pid。
        :returns: pid missing 证据。
        """

        return ProcessEvidence(
            pid=pid,
            exists=False,
            observed_start_token=None,
            observed_boot_id=None,
            probe_error_code=None,
        )


class _RecordingWakeup:
    """记录 startup scan commit 后的 scheduler wakeup。"""

    def __init__(self) -> None:
        """初始化 wakeup 记录器。

        :returns: ``None``。
        """

        self.dispatches: list[PendingDispatchRecord] = []
        self.promoted_sessions: list[str] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """记录 dispatch wakeup。

        :param record: pending dispatch 摘要。
        :returns: ``None``。
        """

        self.dispatches.append(record)

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 queue promotion wakeup。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        """

        self.promoted_sessions.append(session_id)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def test_scan_running_positive_orphan_moves_to_recovering_without_projection(
    tmp_path: Path,
) -> None:
    """RUNNING positive orphan 基于 durable truth 进入 RECOVERING，不依赖 projection。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _insert_projection_lag_marker(store.transaction_runner)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RUN_RECOVERING,
        )

        def verify(transaction: HostTransaction) -> str:
            """读取 Run 状态。

            :param transaction: Host transaction。
            :returns: Run 状态。
            """

            run = read_run_by_id(transaction, "run-1")
            assert run is not None
            return run.status.value

        assert store.transaction_runner.run_write(verify) == RunStatus.RECOVERING.value


def test_recovery_lifecycle_proof_matrix_covers_slice_a_rows() -> None:
    """证明 WU-LIFE Slice A recovery lifecycle matrix 覆盖必需场景。

    :returns: ``None``。
    :raises AssertionError: matrix 缺少必需行或覆盖分类非法时由 pytest 抛出。
    """

    scenario_ids = tuple(row.scenario_id for row in _RECOVERY_LIFECYCLE_PROOF_MATRIX)
    rows_by_id = {row.scenario_id: row for row in _RECOVERY_LIFECYCLE_PROOF_MATRIX}
    assert len(scenario_ids) == len(set(scenario_ids))
    assert {
        "waiting-diagnostic-only-low-level",
        "waiting-durable-read-diagnostic-only",
        "running-owner-heartbeat-recent",
        "running-process-probe-error",
        "running-stale-heartbeat-only",
        "running-missing-current-attempt-or-dispatch",
        "rr-dur-04-short-transaction-durable-truth",
    }.issubset(set(scenario_ids))
    assert all(
        row.coverage_classification in (_COVERAGE_EXISTING, _COVERAGE_NEW, _COVERAGE_NON_GOAL)
        for row in _RECOVERY_LIFECYCLE_PROOF_MATRIX
    )
    assert rows_by_id["waiting-diagnostic-only-low-level"].coverage_classification == _COVERAGE_EXISTING
    assert rows_by_id["waiting-durable-read-diagnostic-only"].coverage_classification == _COVERAGE_NEW
    assert rows_by_id["running-missing-current-attempt-or-dispatch"].coverage_classification == _COVERAGE_NEW


def test_scan_running_owner_heartbeat_recent_does_not_mutate_durable_rows(
    tmp_path: Path,
) -> None:
    """RUNNING owner heartbeat recent 时 scanner 不写 recovery 或 terminal facts。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: scanner 误写 durable rows 或 reason 错误时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _mark_owner_heartbeat(
            store.transaction_runner,
            heartbeat_at="2026-05-19T03:04:00.000000Z",
        )
        before = _active_run_observation(store.transaction_runner, "run-1")

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        after = _active_run_observation(store.transaction_runner, "run-1")
        assert tuple(action.decision for action in result.actions) == (StartupRecoveryDecision.OWNER_STILL_LIVE,)
        assert tuple(action.reason for action in result.actions) == (_REASON_OWNER_HEARTBEAT_RECENT,)
        assert after == before
        _assert_no_recovery_or_terminal_facts(store.transaction_runner)


@pytest.mark.parametrize(
    ("process_probe", "expected_reason"),
    (
        (_PidProbeErrorProbe(), _REASON_PROCESS_PROBE_ERROR),
        (_PidLiveNoIdentityProbe(), _REASON_PID_LIVE_WITHOUT_IDENTITY),
    ),
)
def test_scan_running_inconclusive_owner_proof_does_not_mutate_durable_rows(
    tmp_path: Path,
    process_probe: _PidProbeErrorProbe | _PidLiveNoIdentityProbe,
    expected_reason: str,
) -> None:
    """RUNNING inconclusive proof 不得写 terminal 或 recovery facts。

    :param tmp_path: pytest 临时目录。
    :param process_probe: 测试用进程证据 probe。
    :param expected_reason: 期望 scanner action reason。
    :returns: ``None``。
    :raises AssertionError: scanner 误写 durable rows 或 reason 错误时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        before = _active_run_observation(store.transaction_runner, "run-1")

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=process_probe,
        ).scan(_policy())

        after = _active_run_observation(store.transaction_runner, "run-1")
        assert tuple(action.decision for action in result.actions) == (StartupRecoveryDecision.ORPHAN_INCONCLUSIVE,)
        assert tuple(action.reason for action in result.actions) == (expected_reason,)
        assert after == before
        _assert_no_recovery_or_terminal_facts(store.transaction_runner)


def test_scan_waiting_uses_diagnostic_only_fallback(tmp_path: Path) -> None:
    """WAITING startup scan 不创建 Attempt、不推进状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _mark_run_status(store.transaction_runner, "run-1", RunStatus.WAITING)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.WAITING_DIAGNOSTIC_ONLY,
        )
        assert tuple(action.reason for action in result.actions) == (_REASON_WAITING_ADAPTER_OBSERVATION_UNAVAILABLE,)
        assert _count_rows(store.transaction_runner, "host_attempts") == 1
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.WAITING.value
        _assert_no_recovery_or_terminal_facts(store.transaction_runner)


def test_scan_waiting_durable_read_state_remains_diagnostic_only(
    tmp_path: Path,
) -> None:
    """WAITING startup scan 后 durable read 仍保持等待诊断语义。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: scanner 创建 recovery Attempt 或写 terminal fact 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _mark_run_status(store.transaction_runner, "run-1", RunStatus.WAITING)
        attempt_count_before = _count_rows(store.transaction_runner, "host_attempts")

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (StartupRecoveryDecision.WAITING_DIAGNOSTIC_ONLY,)
        assert tuple(action.reason for action in result.actions) == (_REASON_WAITING_ADAPTER_OBSERVATION_UNAVAILABLE,)
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.WAITING.value
        assert _count_rows(store.transaction_runner, "host_attempts") == attempt_count_before
        _assert_no_recovery_or_terminal_facts(store.transaction_runner)


def test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation(
    tmp_path: Path,
) -> None:
    """RUNNING 缺失当前 dispatch row 时 scanner 只给出 inconclusive 诊断。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: scanner 写入 recovery/terminal fact 或 reason 错误时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _delete_dispatch_record_for_attempt(store.transaction_runner, "attempt-run-1")

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.ORPHAN_INCONCLUSIVE,
        )
        assert tuple(action.reason for action in result.actions) == (
            _REASON_MISSING_CURRENT_ATTEMPT_OR_DISPATCH,
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.RUNNING.value
        assert _count_rows(store.transaction_runner, TABLE_HOST_ATTEMPT_DISPATCH_RECORDS) == 0
        _assert_no_recovery_or_terminal_facts(store.transaction_runner)


def test_scan_cancelling_positive_orphan_loses_attempt_then_run(
    tmp_path: Path,
) -> None:
    """CANCELLING positive orphan 写 ATTEMPT_LOST 后写 RUN_LOST，不恢复执行。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _append_accepted_cancel_facts(store.transaction_runner, "run-1")

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RUN_LOST,
        )
        assert tuple(action.reason for action in result.actions) == (
            _REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST,
        )

        def verify(
            transaction: HostTransaction,
        ) -> tuple[str, tuple[str, ...], JsonValue]:
            """读取 closeout 后的状态、事件序列与 RUN_LOST reason。

            :param transaction: Host transaction。
            :returns: Run 状态、event type 序列与 RUN_LOST reason。
            """

            run = read_run_by_id(transaction, "run-1")
            assert run is not None
            run_lost_payload = _event_payload_by_type(
                transaction,
                event_type=_EVENT_TYPE_RUN_LOST,
            )
            return (
                run.status.value,
                _event_types(transaction),
                run_lost_payload["reason"],
            )

        run_status, event_types, run_lost_reason = store.transaction_runner.run_write(
            verify
        )
        assert run_status == RunStatus.LOST.value
        assert event_types[-2:] == (_EVENT_TYPE_ATTEMPT_LOST, _EVENT_TYPE_RUN_LOST)
        assert _EVENT_TYPE_RUN_RECOVERING not in event_types
        assert run_lost_reason == _REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST


def test_scan_defers_accepted_cancel_cancelling_to_watchdog_when_enabled(
    tmp_path: Path,
) -> None:
    """watchdog enabled 且 scheduler 已注入时 accepted-cancel 交给 watchdog。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _append_accepted_cancel_facts(store.transaction_runner, "run-1")
        wakeup = _RecordingWakeup()

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
            defer_accepted_cancel_to_watchdog=True,
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG,
        )
        assert tuple(action.reason for action in result.actions) == (
            "accepted_cancel_watchdog_owner",
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.CANCELLING.value
        assert _event_type_count(store.transaction_runner, _EVENT_TYPE_RUN_LOST) == 0


def test_scan_accepted_cancel_without_scheduler_uses_recovery_fallback(
    tmp_path: Path,
) -> None:
    """watchdog 可能不运行时 recovery 不再永久 defer CANCELLING Run。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _append_accepted_cancel_facts(store.transaction_runner, "run-1")

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            defer_accepted_cancel_to_watchdog=True,
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RUN_LOST,
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.LOST.value
        assert _event_type_count(store.transaction_runner, _EVENT_TYPE_RUN_LOST) == 1


def test_scan_malformed_cancelling_payload_uses_typed_cancel_link(
    tmp_path: Path,
) -> None:
    """malformed RUN_CANCELLING payload 不影响 typed cancel link 判断。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _append_malformed_run_cancelling_payload(store.transaction_runner, "run-1")
        wakeup = _RecordingWakeup()

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
            defer_accepted_cancel_to_watchdog=True,
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG,
        )
        assert tuple(action.reason for action in result.actions) == (
            "accepted_cancel_watchdog_owner",
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.CANCELLING.value
        assert _event_type_count(store.transaction_runner, _EVENT_TYPE_RUN_LOST) == 0


def test_scan_watchdog_disabled_keeps_cancelling_orphan_policy(
    tmp_path: Path,
) -> None:
    """watchdog disabled 时 accepted-cancel CANCELLING 仍按 recovery orphan 策略。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _append_accepted_cancel_facts(store.transaction_runner, "run-1")

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            defer_accepted_cancel_to_watchdog=False,
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RUN_LOST,
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.LOST.value
        assert _event_type_count(store.transaction_runner, _EVENT_TYPE_RUN_LOST) == 1


def test_scan_accepted_does_not_mutate_or_create_attempt(tmp_path: Path) -> None:
    """ACCEPTED startup classification 不写 recovery fact、不改状态、不建 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_unstarted_run(store.transaction_runner, "run-1", RunStatus.ACCEPTED)
        before = _unstarted_scan_observation(store.transaction_runner, "run-1")
        wakeup = _RecordingWakeup()

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
        ).scan(_policy())

        after = _unstarted_scan_observation(store.transaction_runner, "run-1")
        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.ACCEPTED_WAKE,
        )
        assert len(result.queue_promotion_sessions) == 1
        assert wakeup.dispatches == []
        assert wakeup.promoted_sessions == list(result.queue_promotion_sessions)
        assert after == before


def test_scan_accepted_without_wakeup_port_logs_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ACCEPTED 需要 promotion 但无 wakeup port 时必须给出 ERROR 诊断。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_unstarted_run(store.transaction_runner, "run-1", RunStatus.ACCEPTED)
        caplog.set_level(logging.ERROR, logger="dayu.host.recovery")

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.ACCEPTED_WAKE,
        )
        assert len(result.queue_promotion_sessions) == 1
        assert "host.recovery.queue_promotion_wakeup_unavailable" in caplog.text


def test_scan_queued_does_not_mutate_or_create_attempt(tmp_path: Path) -> None:
    """QUEUED startup classification 不写 recovery fact、不改状态、不建 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_unstarted_run(store.transaction_runner, "run-1", RunStatus.QUEUED)
        before = _unstarted_scan_observation(store.transaction_runner, "run-1")
        wakeup = _RecordingWakeup()

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
        ).scan(_policy())

        after = _unstarted_scan_observation(store.transaction_runner, "run-1")
        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.QUEUE_PROMOTION_CHECK,
        )
        assert len(result.queue_promotion_sessions) == 1
        assert wakeup.dispatches == []
        assert wakeup.promoted_sessions == list(result.queue_promotion_sessions)
        assert after == before


def test_scan_recovering_loses_when_eventlog_recovery_limit_reached_despite_projection_lag(
    tmp_path: Path,
) -> None:
    """RECOVERING limit 只看 canonical EventLog，projection lag 不影响 LOST 决策。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _mark_run_status(store.transaction_runner, "run-1", RunStatus.RECOVERING)
        _append_recovery_started_event(store.transaction_runner, "run-1")
        _insert_projection_lag_marker(store.transaction_runner)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RUN_LOST,
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.LOST.value


def test_scan_skips_non_terminal_run_when_session_row_is_missing(
    tmp_path: Path,
) -> None:
    """验证 Session row 缺失时 recovery 不根据残留 Run row 创建恢复事实。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: recovery 写入恢复事实或改变残留 Run 状态时由断言抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
    _delete_session_rows_without_foreign_keys(options.db_path)

    with open_host_durable_store(options) as store:
        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.NOT_FOUND,
        )
        assert tuple(action.reason for action in result.actions) == (
            "session_missing",
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.RUNNING.value
        assert _event_type_count(store.transaction_runner, _EVENT_TYPE_ATTEMPT_LOST) == 0
        assert _event_type_count(store.transaction_runner, _EVENT_TYPE_RUN_RECOVERING) == 0


def _policy() -> StartupRecoveryPolicy:
    """构造测试 recovery policy。

    :returns: startup recovery policy。
    """

    return StartupRecoveryPolicy(
        now=_NOW,
        stale_after=timedelta(seconds=30),
        recovery_dispatch_limit=1,
    )


def _delete_session_rows_without_foreign_keys(db_path: Path) -> None:
    """删除 Session row 以模拟 purge/missing Session 的残留 Run 防御场景。

    :param db_path: Host durable SQLite 路径。
    :returns: ``None``。
    :raises sqlite3.Error: SQLite 打开或执行删除语句失败时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(f"DELETE FROM {TABLE_HOST_SESSION_SLOTS}")
        connection.execute(f"DELETE FROM {TABLE_HOST_SESSIONS}")


def _delete_dispatch_record_for_attempt(
    transaction_runner: HostTransactionRunner, attempt_id: str
) -> None:
    """删除测试 dispatch row 以构造 current Attempt 缺失 dispatch 的 scanner 场景。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: 目标 Attempt id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """删除 dispatch row。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            DELETE FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
            WHERE attempt_id = ?
            """,
            (attempt_id,),
        )

    transaction_runner.run_write(operation)


def _seed_running_dispatching_run(
    transaction_runner: HostTransactionRunner, run_id: str
) -> None:
    """写入 running Run 与 stale owner dispatch record。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: ``None``。
    """

    session_id = _ensure_session_id(transaction_runner)

    def operation(transaction: HostTransaction) -> None:
        """写入测试数据。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        input_event = EventLogStore().append_event(
            transaction,
            _event(
                event_id=f"event-input-{run_id}",
                session_id=session_id,
                run_id=run_id,
                event_type="USER_INPUT_ACCEPTED",
                payload={
                    "input_ref": None,
                    "input_digest": _INPUT_DIGEST,
                    "display_text": "hello",
                    "payload_ref": None,
                    "payload_digest": None,
                    "operation_kind": "start_run",
                    "call_context_digest": _CALL_CONTEXT_DIGEST,
                },
            ),
        ).row
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            _create_running_input(
                session_id=session_id,
                run_id=run_id,
                input_event_sequence=input_event.event_sequence,
            ),
        )
        _insert_stale_host_instance(transaction)
        attempt_id = f"attempt-{run_id}"
        waiting = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-instance-old",
            lane_name="llm",
            waiting_for_lane_at="2026-05-19T03:03:00.000000Z",
        )
        assert waiting.status is StateMutationStatus.UPDATED
        dispatching = mark_dispatching_after_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-instance-old",
            lane_name="llm",
            lane_claim_id="lane-claim-old",
            lane_owner_id="lane-owner-old",
            lane_acquired_at="2026-05-19T03:03:01.000000Z",
            dispatching_at="2026-05-19T03:03:02.000000Z",
        )
        assert dispatching.status is StateMutationStatus.UPDATED

    transaction_runner.run_write(operation)


def _seed_unstarted_run(
    transaction_runner: HostTransactionRunner, run_id: str, status: RunStatus
) -> None:
    """写入 ACCEPTED 或 QUEUED 测试 Run。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :param status: 目标非启动状态。
    :returns: ``None``。
    :raises AssertionError: status 不是 ACCEPTED 或 QUEUED 时抛出。
    """

    session_id = _ensure_session_id(transaction_runner)

    def operation(transaction: HostTransaction) -> None:
        """写入测试数据。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        input_event = EventLogStore().append_event(
            transaction,
            _event(
                event_id=f"event-input-{run_id}",
                session_id=session_id,
                run_id=run_id,
                event_type="USER_INPUT_ACCEPTED",
                payload={
                    "input_ref": None,
                    "input_digest": _INPUT_DIGEST,
                    "display_text": "hello",
                    "payload_ref": None,
                    "payload_digest": None,
                    "operation_kind": "start_run",
                    "call_context_digest": _CALL_CONTEXT_DIGEST,
                },
            ),
        ).row
        if status is RunStatus.ACCEPTED:
            create_accepted_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_accepted_input(
                    session_id=session_id,
                    run_id=run_id,
                    input_event_sequence=input_event.event_sequence,
                ),
            )
            return
        if status is RunStatus.QUEUED:
            create_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_queued_input(
                    session_id=session_id,
                    run_id=run_id,
                    input_event_sequence=input_event.event_sequence,
                ),
            )
            return
        raise AssertionError("status must be ACCEPTED or QUEUED")

    transaction_runner.run_write(operation)


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """创建测试 Session。

    :param transaction_runner: Host transaction runner。
    :returns: Session id。
    """

    result = ensure_session(
        transaction_runner,
        EnsureSessionRequest(
            scope="workspace",
            slot_key="recovery-scan",
            metadata=(HostMetadataEntry(key="case", value="recovery-scan"),),
        ),
    )
    return result.snapshot.session_id


def _create_accepted_input(
    *, session_id: str, run_id: str, input_event_sequence: int
) -> CreateAcceptedRunInput:
    """构造 accepted Run 输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param input_event_sequence: USER_INPUT_ACCEPTED event sequence。
    :returns: CreateAcceptedRunInput。
    """

    return CreateAcceptedRunInput(
        session_id=session_id,
        run_id=run_id,
        client_request_id=f"request-{run_id}",
        input_event_id=f"event-input-{run_id}",
        input_event_sequence=input_event_sequence,
        run_accepted_event_id=f"event-run-accepted-{run_id}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        idempotency_key=f"request-{run_id}",
        execution_target="local-default",
        queue_policy=RunQueuePolicy.QUEUE,
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _create_queued_input(
    *, session_id: str, run_id: str, input_event_sequence: int
) -> CreateQueuedRunInput:
    """构造 queued Run 输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param input_event_sequence: USER_INPUT_ACCEPTED event sequence。
    :returns: CreateQueuedRunInput。
    """

    return CreateQueuedRunInput(
        session_id=session_id,
        run_id=run_id,
        client_request_id=f"request-{run_id}",
        input_event_id=f"event-input-{run_id}",
        input_event_sequence=input_event_sequence,
        run_accepted_event_id=f"event-run-accepted-{run_id}",
        run_queued_event_id=f"event-run-queued-{run_id}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        idempotency_key=f"request-{run_id}",
        execution_target="local-default",
        queue_policy=RunQueuePolicy.QUEUE,
        queue_reason="active_run_exists",
        active_run_id="run-active",
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _create_running_input(
    *, session_id: str, run_id: str, input_event_sequence: int
) -> CreateRunningRunInput:
    """构造 running Run 输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param input_event_sequence: USER_INPUT_ACCEPTED event sequence。
    :returns: CreateRunningRunInput。
    """

    return CreateRunningRunInput(
        session_id=session_id,
        run_id=run_id,
        client_request_id=f"request-{run_id}",
        input_event_id=f"event-input-{run_id}",
        input_event_sequence=input_event_sequence,
        run_accepted_event_id=f"event-run-accepted-{run_id}",
        run_started_event_id=f"event-run-started-{run_id}",
        attempt_started_event_id=f"event-attempt-started-{run_id}",
        attempt_id=f"attempt-{run_id}",
        execution_id=f"execution-{run_id}",
        dispatch_record_id=f"dispatch-{run_id}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        idempotency_key=f"request-{run_id}",
        execution_target="local-default",
        queue_policy=RunQueuePolicy.QUEUE,
        start_reason=RunStartReason.INITIAL,
        worker_kind=WorkerKind.LOCAL,
        owner_host_instance_id=None,
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _event(
    *,
    event_id: str,
    session_id: str,
    run_id: str,
    event_type: str,
    payload: JsonValue,
) -> EventLogAppendRequest:
    """构造测试 EventLog append request。

    :param event_id: event id。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_type: event type。
    :param payload: inline payload。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=session_id,
        run_id=run_id,
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        client_request_id="client-request",
        idempotency_key="client-request",
        policy_decision=None,
        reason=None,
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _insert_stale_host_instance(transaction: HostTransaction) -> None:
    """写入 stale owner host instance。

    :param transaction: Host transaction。
    :returns: ``None``。
    """

    transaction.execute(
        """
        INSERT INTO host_instances (
          host_instance_id,
          pid,
          process_start_token,
          boot_id,
          created_at,
          heartbeat_at,
          status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "host-instance-old",
            999_999,
            "process-start-token-old",
            None,
            "2026-05-19T03:00:00.000000Z",
            "2026-05-19T03:00:00.000000Z",
            "running",
        ),
    )


def _mark_owner_heartbeat(transaction_runner: HostTransactionRunner, *, heartbeat_at: str) -> None:
    """更新测试 owner liveness heartbeat。

    :param transaction_runner: Host transaction runner。
    :param heartbeat_at: 目标 heartbeat timestamp。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """更新 owner heartbeat。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            """
            UPDATE host_instances
            SET heartbeat_at = ?
            WHERE host_instance_id = ?
            """,
            (
                heartbeat_at,
                "host-instance-old",
            ),
        )

    transaction_runner.run_write(operation)


def _insert_projection_lag_marker(transaction_runner: HostTransactionRunner) -> None:
    """写入 projection checkpoint lag 标记。

    :param transaction_runner: Host transaction runner。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """写入 checkpoint。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            """
            INSERT OR REPLACE INTO host_projection_checkpoints (
              consumer_id,
              checkpoint_event_sequence,
              checkpoint_event_id,
              last_success_at,
              updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "lagging-test-projection",
                0,
                None,
                None,
                "2026-05-19T03:00:00.000000Z",
            ),
        )

    transaction_runner.run_write(operation)


def _active_run_observation(transaction_runner: HostTransactionRunner, run_id: str) -> _ActiveRunObservation:
    """读取 active Run scanner 前后必须保持不变的 durable 观测。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: active Run durable 观测。
    :raises AssertionError: 测试数据缺少 Run、Attempt 或 dispatch row 时抛出。
    """

    def operation(transaction: HostTransaction) -> _ActiveRunObservation:
        """在 transaction 中读取 durable 观测。

        :param transaction: Host transaction。
        :returns: active Run durable 观测。
        :raises AssertionError: 测试数据缺少 Run、Attempt 或 dispatch row 时抛出。
        """

        run = read_run_by_id(transaction, run_id)
        assert run is not None
        assert run.current_attempt_id is not None
        attempt = read_attempt_by_id(transaction, run.current_attempt_id)
        assert attempt is not None
        dispatch_record = read_dispatch_record_by_attempt_id(
            transaction,
            run.current_attempt_id,
        )
        assert dispatch_record is not None
        return _ActiveRunObservation(
            run_status=run.status.value,
            run_updated_at=run.updated_at,
            current_attempt_id=run.current_attempt_id,
            attempt_status=attempt.status,
            attempt_updated_at=attempt.updated_at,
            attempt_terminal_event_id=attempt.terminal_event_id,
            dispatch_status=dispatch_record.status,
            dispatch_updated_at=dispatch_record.updated_at,
            dispatch_cancelled_event_id=dispatch_record.cancelled_event_id,
            dispatch_owner_host_instance_id=dispatch_record.owner_host_instance_id,
            event_types=_event_types(transaction),
        )

    return transaction_runner.run_read(operation)


def _assert_no_recovery_or_terminal_facts(
    transaction_runner: HostTransactionRunner,
) -> None:
    """断言 scanner 未写 recovery 或 terminal EventLog facts。

    :param transaction_runner: Host transaction runner。
    :returns: ``None``。
    :raises AssertionError: 任一 forbidden fact 被写入时抛出。
    """

    assert _event_type_count(transaction_runner, _EVENT_TYPE_ATTEMPT_LOST) == 0
    assert _event_type_count(transaction_runner, _EVENT_TYPE_RUN_RECOVERING) == 0
    assert _event_type_count(transaction_runner, _EVENT_TYPE_RUN_LOST) == 0


def _mark_run_status(
    transaction_runner: HostTransactionRunner, run_id: str, status: RunStatus
) -> None:
    """直接设置测试 Run 状态。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :param status: 目标状态。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """更新测试 Run 状态。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            "UPDATE host_runs SET status = ?, updated_at = ? WHERE run_id = ?",
            (status.value, "2026-05-19T03:04:00.000000Z", run_id),
        )

    transaction_runner.run_write(operation)


def _append_recovery_started_event(
    transaction_runner: HostTransactionRunner, run_id: str
) -> None:
    """追加 canonical recovery ``RUN_STARTED`` event。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加 recovery start 事件。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        session_row = transaction.fetchone(
            "SELECT session_id FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        assert session_row is not None
        EventLogStore().append_event(
            transaction,
            _event(
                event_id=f"event-recovery-started-{run_id}",
                session_id=_required_text(session_row, "session_id"),
                run_id=run_id,
                event_type="RUN_STARTED",
                payload={
                    "run_id": run_id,
                    "start_reason": serialize_run_start_reason(
                        RunStartReason.RECOVERY
                    ),
                    "source_attempt_id": f"attempt-{run_id}",
                    "attempt_id": f"attempt-recovery-{run_id}",
                    "dispatch_record_id": f"dispatch-recovery-{run_id}",
                },
            ),
        )

    transaction_runner.run_write(operation)


def _append_accepted_cancel_facts(
    transaction_runner: HostTransactionRunner,
    run_id: str,
) -> None:
    """追加测试用 accepted active cancel facts。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加 ``CANCEL_REQUESTED`` 与 ``RUN_CANCELLING``。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        session_row = transaction.fetchone(
            "SELECT session_id FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        assert session_row is not None
        session_id = _required_text(session_row, "session_id")
        cancel_requested_id = f"event-cancel-requested-{run_id}"
        event_log_store = EventLogStore()
        event_log_store.append_event(
            transaction,
            _event(
                event_id=cancel_requested_id,
                session_id=session_id,
                run_id=run_id,
                event_type=_EVENT_TYPE_CANCEL_REQUESTED,
                payload={
                    "run_id": run_id,
                    "reason": "user_stop",
                    "mode": "graceful",
                },
            ),
        )
        transaction.execute(
            "UPDATE host_runs SET status = ?, cancel_request_event_id = ?, updated_at = ? WHERE run_id = ?",
            (
                RunStatus.CANCELLING.value,
                cancel_requested_id,
                "2026-05-19T03:04:00.000000Z",
                run_id,
            ),
        )
        event_log_store.append_event(
            transaction,
            _event(
                event_id=f"event-run-cancelling-{run_id}",
                session_id=session_id,
                run_id=run_id,
                event_type=_EVENT_TYPE_RUN_CANCELLING,
                payload={
                    "run_id": run_id,
                    "cancel_request_event_id": cancel_requested_id,
                    "reason": "user_stop",
                },
            ),
        )

    transaction_runner.run_write(operation)


def _append_malformed_run_cancelling_payload(
    transaction_runner: HostTransactionRunner,
    run_id: str,
) -> None:
    """追加测试用 malformed ``RUN_CANCELLING`` fact。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加 payload 非 object 的 ``RUN_CANCELLING``。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        session_row = transaction.fetchone(
            "SELECT session_id FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        assert session_row is not None
        session_id = _required_text(session_row, "session_id")
        cancel_requested_id = f"event-cancel-requested-malformed-{run_id}"
        event_log_store = EventLogStore()
        event_log_store.append_event(
            transaction,
            _event(
                event_id=cancel_requested_id,
                session_id=session_id,
                run_id=run_id,
                event_type=_EVENT_TYPE_CANCEL_REQUESTED,
                payload={
                    "run_id": run_id,
                    "reason": "user_stop",
                    "mode": "graceful",
                },
            ),
        )
        event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=f"event-run-cancelling-malformed-{run_id}",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type=_EVENT_TYPE_RUN_CANCELLING,
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                client_request_id="client-request-malformed",
                idempotency_key=f"client-request-malformed-{run_id}",
                policy_decision=None,
                reason=None,
                payload_json="malformed-cancelling-payload",
                payload_ref=None,
                payload_digest=None,
            ),
        )
        transaction.execute(
            "UPDATE host_runs SET status = ?, cancel_request_event_id = ?, updated_at = ? WHERE run_id = ?",
            (
                RunStatus.CANCELLING.value,
                cancel_requested_id,
                "2026-05-19T03:04:00.000000Z",
                run_id,
            ),
        )

    transaction_runner.run_write(operation)


def _run_status(transaction_runner: HostTransactionRunner, run_id: str) -> str:
    """读取 Run status。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run status 文本。
    """

    def operation(transaction: HostTransaction) -> str:
        """读取 Run 状态。

        :param transaction: Host transaction。
        :returns: Run status 文本。
        """

        row = transaction.fetchone("SELECT status FROM host_runs WHERE run_id = ?", (run_id,))
        assert row is not None
        return _required_text(row, "status")

    return transaction_runner.run_write(operation)


def _unstarted_scan_observation(
    transaction_runner: HostTransactionRunner, run_id: str
) -> tuple[str, str, int, tuple[str, ...]]:
    """读取 unstarted Run scan 前后应保持不变的观测值。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run 状态、updated_at、Attempt row 数与 EventLog 序列。
    """

    def operation(transaction: HostTransaction) -> tuple[str, str, int, tuple[str, ...]]:
        """读取测试观测值。

        :param transaction: Host transaction。
        :returns: Run 状态、updated_at、Attempt row 数与 EventLog 序列。
        """

        row = transaction.fetchone(
            "SELECT status, updated_at FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        assert row is not None
        return (
            _required_text(row, "status"),
            _required_text(row, "updated_at"),
            _count_rows_in_transaction(transaction, "host_attempts"),
            _event_types(transaction),
        )

    return transaction_runner.run_write(operation)


def _event_types(transaction: HostTransaction) -> tuple[str, ...]:
    """读取全部 EventLog event type。

    :param transaction: Host transaction。
    :returns: event type 序列。
    """

    rows = transaction.fetchall(
        "SELECT event_type FROM event_log ORDER BY event_sequence ASC"
    )
    return tuple(_required_text(row, "event_type") for row in rows)


def _event_type_count(
    transaction_runner: HostTransactionRunner, event_type: str
) -> int:
    """统计指定 EventLog event type 数量。

    :param transaction_runner: Host transaction runner。
    :param event_type: 目标 event type。
    :returns: 匹配 row 数量。
    :raises AssertionError: count 查询未返回 row 或 row 类型不符合预期时抛出。
    """

    def operation(transaction: HostTransaction) -> int:
        """执行 event type 计数。

        :param transaction: Host transaction。
        :returns: 匹配 row 数量。
        :raises AssertionError: count 查询未返回 row 或 row 类型不符合预期时抛出。
        """

        row = transaction.fetchone(
            f"""
            SELECT COUNT(*) AS count
            FROM {TABLE_EVENT_LOG}
            WHERE event_type = ?
            """,
            (event_type,),
        )
        assert row is not None
        return _required_int(row, "count")

    return transaction_runner.run_read(operation)


def _event_payload_by_type(
    transaction: HostTransaction, *, event_type: str
) -> dict[str, JsonValue]:
    """读取指定类型最后一条 EventLog payload。

    :param transaction: Host transaction。
    :param event_type: event type。
    :returns: payload JSON object。
    """

    row = transaction.fetchone(
        """
        SELECT payload_json
        FROM event_log
        WHERE event_type = ?
        ORDER BY event_sequence DESC
        LIMIT 1
        """,
        (event_type,),
    )
    assert row is not None
    payload = json.loads(_required_text(row, "payload_json"))
    assert isinstance(payload, dict)
    return cast(dict[str, JsonValue], payload)


def _count_rows(transaction_runner: HostTransactionRunner, table_name: str) -> int:
    """统计表行数。

    :param transaction_runner: Host transaction runner。
    :param table_name: 表名。
    :returns: 行数。
    """

    def operation(transaction: HostTransaction) -> int:
        """执行统计。

        :param transaction: Host transaction。
        :returns: 行数。
        """

        return _count_rows_in_transaction(transaction, table_name)

    return transaction_runner.run_write(operation)


def _count_rows_in_transaction(transaction: HostTransaction, table_name: str) -> int:
    """在现有 transaction 内统计表行数。

    :param transaction: Host transaction。
    :param table_name: 表名。
    :returns: 行数。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {table_name}")
    assert row is not None
    return _required_int(row, "total")


def _required_text(row: HostRow, column: str) -> str:
    """读取必填文本列。

    :param row: Host row。
    :param column: 列名。
    :returns: 文本值。
    """

    value = row.get(column)
    assert isinstance(value, str)
    return value


def _required_int(row: HostRow, column: str) -> int:
    """读取必填整数列。

    :param row: Host row。
    :param column: 列名。
    :returns: 整数值。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value
