"""Host startup recovery scan 编排。

本模块负责启动时读取 durable Run/Attempt/dispatch/liveness truth，调用
只读 orphan proof classifier，并在 positive proof 成立时通过 durable
transition helper 完成旧 Attempt closeout。Slice 3 起，本模块还负责为
可恢复 Run 创建 recovery Attempt、execution 与 pending dispatch record，
并在事务提交后唤醒 scheduler。它不实现 public API、不直接调用 WorkerProxy，
也不读取 projection/read-model。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from dayu.host.admission import AdmissionWakeupPort, PendingDispatchRecord
from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.durable.event_log import EventLogStore
from dayu.host.durable.liveness import HostInstanceRow, read_host_instance
from dayu.host.durable.run_transition import (
    RunTransitionResult,
    StartRecoveryRunInput,
    StartupOrphanCloseInput,
    StartupRecoveringLostInput,
    close_startup_orphan_attempt_in_transaction,
    lose_recovering_run_in_transaction,
    start_recovery_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    RunRow,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_non_terminal_runs,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.recovery_process import (
    DurableOrphanCandidate,
    OrphanClassification,
    OrphanClassificationPolicy,
    OrphanProofInconclusive,
    OwnerStillLive,
    PositiveOrphanProof,
    ProcessEvidence,
    ProcessLivenessProbe,
    StdlibPidLivenessProbe,
    classify_orphan_candidate,
)

_RECOVERY_ACTOR = "host_recovery"
_RECOVERY_SOURCE = "startup_scan"
# heartbeat 周期必须显著小于 stale 阈值，避免破坏 positive orphan proof。
_DEFAULT_STALE_AFTER_SECONDS = 30
_DEFAULT_RECOVERY_DISPATCH_LIMIT = 1
_ATTEMPT_ID_PREFIX = "attempt-recovery"
_EXECUTION_ID_PREFIX = "execution-recovery"
_DISPATCH_RECORD_ID_PREFIX = "dispatch-recovery"
_REASON_STARTUP_ORPHAN_ATTEMPT_LOST = "startup_orphan_attempt_lost"
_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST = "cancel_in_flight_attempt_lost"
_REASON_UNRECOVERABLE_FACTS = "startup_recovery_unrecoverable_facts"
_REASON_RECOVERY_DISPATCH_LIMIT_EXCEEDED = (
    "startup_recovery_dispatch_limit_exceeded"
)
_REASON_RECOVERY_DISPATCH_PENDING_FOLLOW_UP = (
    "startup_recovery_dispatch_pending_follow_up"
)


class StartupRecoveryDecision(StrEnum):
    """startup scan 对单个 Run 的分类决策。"""

    ACCEPTED_WAKE = "accepted_wake"
    QUEUE_PROMOTION_CHECK = "queue_promotion_check"
    WAITING_DIAGNOSTIC_ONLY = "waiting_diagnostic_only"
    OWNER_STILL_LIVE = "owner_still_live"
    ORPHAN_INCONCLUSIVE = "orphan_inconclusive"
    RUN_RECOVERING = "run_recovering"
    RUN_LOST = "run_lost"
    RECOVERING_READY = "recovering_ready"
    RECOVERY_DISPATCHED = "recovery_dispatched"
    CAS_LOST = "cas_lost"
    INVALID_STATE = "invalid_state"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class StartupRecoveryPolicy:
    """startup recovery scan 策略。

    :param now: 分类使用的策略时间。
    :param stale_after: heartbeat 超过该阈值才可进入 orphan proof 判断。
    :param recovery_dispatch_limit: 每个 Run 允许的 startup automatic recovery
        dispatch 上限。
    """

    now: datetime
    stale_after: timedelta
    recovery_dispatch_limit: int = _DEFAULT_RECOVERY_DISPATCH_LIMIT

    @classmethod
    def default(cls) -> "StartupRecoveryPolicy":
        """构造默认 startup recovery 策略。

        :returns: 默认策略；stale 阈值大于 Slice 1 scheduler heartbeat 周期。
        """

        return cls(
            now=datetime.now(UTC),
            stale_after=timedelta(seconds=_DEFAULT_STALE_AFTER_SECONDS),
            recovery_dispatch_limit=_DEFAULT_RECOVERY_DISPATCH_LIMIT,
        )


@dataclass(frozen=True, slots=True)
class StartupRecoveryAction:
    """单个 Run 的 startup recovery scan 结果。

    :param run_id: 目标 Run id。
    :param status: scan 时观察到的 Run 状态。
    :param decision: 分类决策。
    :param reason: 结构化原因。
    """

    run_id: str
    status: RunStatus
    decision: StartupRecoveryDecision
    reason: str


@dataclass(frozen=True, slots=True)
class StartupRecoveryScanResult:
    """startup recovery scan 汇总。

    :param actions: 按扫描顺序记录的每个 Run 分类结果。
    :param pending_dispatches: 本次 scan 事务提交后唤醒的 pending dispatch 摘要。
    """

    actions: tuple[StartupRecoveryAction, ...]
    pending_dispatches: tuple[PendingDispatchRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class StartupRecoveryScanner:
    """startup recovery scanner。

    :param transaction_runner: Host durable transaction runner。
    :param event_log_store: EventLog primitive。
    :param process_probe: 本机进程证据 probe。
    :param dispatch_wakeup_port: commit 后唤醒 dispatch 的端口；未提供时只做
        Slice 2 closeout / classification，不创建 startup recovery dispatch。
    :param recovery_owner_host_instance_id: 当前 opener 的 Host instance id；
        创建 recovery dispatch record 时写入 owner 诊断字段。
    """

    transaction_runner: HostTransactionRunner
    event_log_store: EventLogStore
    process_probe: ProcessLivenessProbe = StdlibPidLivenessProbe()
    dispatch_wakeup_port: AdmissionWakeupPort | None = None
    recovery_owner_host_instance_id: str | None = None

    def scan(
        self, policy: StartupRecoveryPolicy | None = None
    ) -> StartupRecoveryScanResult:
        """执行 startup recovery scan。

        :param policy: 可选 scan 策略；未传时使用默认策略。
        :returns: scan 结果。
        :raises HostDurableError: durable 读取或写入失败时由底层抛出。
        """

        effective_policy = policy if policy is not None else StartupRecoveryPolicy.default()
        _validate_policy(effective_policy)

        def operation(transaction: HostTransaction) -> StartupRecoveryScanResult:
            """在单个 write transaction 内读取并提交必要 closeout。

            :param transaction: Host transaction。
            :returns: scan 结果。
            """

            actions: list[StartupRecoveryAction] = []
            pending_dispatches: list[PendingDispatchRecord] = []
            for run in read_non_terminal_runs(transaction):
                actions.append(
                    self._classify_run(
                        transaction,
                        run,
                        effective_policy,
                        pending_dispatches,
                    )
                )
            return StartupRecoveryScanResult(
                actions=tuple(actions),
                pending_dispatches=tuple(pending_dispatches),
            )

        result = self.transaction_runner.run_write(operation)
        if self.dispatch_wakeup_port is not None:
            for pending_dispatch in result.pending_dispatches:
                self.dispatch_wakeup_port.wake_dispatch(pending_dispatch)
        return result

    def _classify_run(
        self,
        transaction: HostTransaction,
        run: RunRow,
        policy: StartupRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
    ) -> StartupRecoveryAction:
        """分类单个非终态 Run。

        :param transaction: Host transaction。
        :param run: 待分类 Run row。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :returns: 单个 Run 的分类结果。
        """

        if run.status is RunStatus.ACCEPTED:
            return _action(run, StartupRecoveryDecision.ACCEPTED_WAKE, "accepted")
        if run.status is RunStatus.QUEUED:
            return _action(
                run,
                StartupRecoveryDecision.QUEUE_PROMOTION_CHECK,
                "queued",
            )
        if run.status is RunStatus.WAITING:
            return _action(
                run,
                StartupRecoveryDecision.WAITING_DIAGNOSTIC_ONLY,
                "waiting_adapter_observation_unavailable",
            )
        if run.status is RunStatus.RECOVERING:
            return self._classify_recovering(
                transaction, run, policy, pending_dispatches
            )
        if run.status in (RunStatus.RUNNING, RunStatus.CANCELLING):
            return self._classify_active_or_cancelling(
                transaction, run, policy, pending_dispatches
            )
        return _action(run, StartupRecoveryDecision.INVALID_STATE, "unsupported_status")

    def _classify_recovering(
        self,
        transaction: HostTransaction,
        run: RunRow,
        policy: StartupRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
    ) -> StartupRecoveryAction:
        """分类 recovering Run。

        :param transaction: Host transaction。
        :param run: recovering Run row。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :returns: 分类结果。
        """

        count = self.event_log_store.count_recovery_dispatches_for_run(
            transaction, run_id=run.run_id
        )
        if count < policy.recovery_dispatch_limit:
            return self._start_recovery_dispatch_or_ready(
                transaction,
                run,
                policy,
                pending_dispatches,
            )
        if run.current_attempt_id is None:
            return _action(
                run,
                StartupRecoveryDecision.INVALID_STATE,
                "recovering_run_missing_source_attempt",
            )
        result = lose_recovering_run_in_transaction(
            transaction,
            self.event_log_store,
            StartupRecoveringLostInput(
                run_id=run.run_id,
                source_attempt_id=run.current_attempt_id,
                run_lost_event_id=_event_id("run-lost-recovering"),
                occurred_at=policy.now,
                actor=_RECOVERY_ACTOR,
                source=_RECOVERY_SOURCE,
                reason=_REASON_RECOVERY_DISPATCH_LIMIT_EXCEEDED,
                recovery_dispatch_count=count,
                recovery_dispatch_limit=policy.recovery_dispatch_limit,
            ),
        )
        return _action_from_mutation(
            run,
            result.status,
            StartupRecoveryDecision.RUN_LOST,
            _REASON_RECOVERY_DISPATCH_LIMIT_EXCEEDED,
        )

    def _classify_active_or_cancelling(
        self,
        transaction: HostTransaction,
        run: RunRow,
        policy: StartupRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
    ) -> StartupRecoveryAction:
        """分类 running 或 cancelling Run。

        :param transaction: Host transaction。
        :param run: running 或 cancelling Run row。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :returns: 分类结果。
        """

        attempt, dispatch_record = _read_current_attempt_and_dispatch(
            transaction, run
        )
        if attempt is None or dispatch_record is None:
            return _action(
                run,
                StartupRecoveryDecision.ORPHAN_INCONCLUSIVE,
                "missing_current_attempt_or_dispatch",
            )
        classification = self._classify_owner(transaction, dispatch_record, policy)
        if isinstance(classification, OwnerStillLive):
            return _action(
                run,
                StartupRecoveryDecision.OWNER_STILL_LIVE,
                classification.reason,
            )
        if isinstance(classification, OrphanProofInconclusive):
            return _action(
                run,
                StartupRecoveryDecision.ORPHAN_INCONCLUSIVE,
                classification.reason,
            )
        return self._close_positive_orphan(
            transaction,
            run,
            attempt,
            dispatch_record,
            classification,
            policy,
            pending_dispatches,
        )

    def _classify_owner(
        self,
        transaction: HostTransaction,
        dispatch_record: DispatchRecordRow,
        policy: StartupRecoveryPolicy,
    ) -> OrphanClassification:
        """调用 Slice 1 classifier 分类 dispatch owner。

        :param transaction: Host transaction。
        :param dispatch_record: 目标 dispatch record。
        :param policy: scan 策略。
        :returns: orphan classification。
        """

        owner_liveness = (
            read_host_instance(transaction, dispatch_record.owner_host_instance_id)
            if dispatch_record.owner_host_instance_id is not None
            else None
        )
        evidence = _collect_process_evidence(self.process_probe, owner_liveness)
        return classify_orphan_candidate(
            DurableOrphanCandidate(
                owner_host_instance_id=dispatch_record.owner_host_instance_id,
                owner_liveness=owner_liveness,
            ),
            evidence,
            OrphanClassificationPolicy(now=policy.now, stale_after=policy.stale_after),
        )

    def _close_positive_orphan(
        self,
        transaction: HostTransaction,
        run: RunRow,
        attempt: AttemptRow,
        dispatch_record: DispatchRecordRow,
        proof: PositiveOrphanProof,
        policy: StartupRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
    ) -> StartupRecoveryAction:
        """对 positive orphan proof 执行 CAS closeout。

        :param transaction: Host transaction。
        :param run: 目标 Run row。
        :param attempt: 目标 Attempt row。
        :param dispatch_record: 目标 dispatch record row。
        :param proof: positive orphan proof。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :returns: closeout 分类结果。
        """

        recoverable = (
            run.status is RunStatus.RUNNING
            and _run_has_recoverable_facts(run, attempt, dispatch_record)
            and self.event_log_store.count_recovery_dispatches_for_run(
                transaction, run_id=run.run_id
            )
            < policy.recovery_dispatch_limit
        )
        reason = _startup_closeout_reason(run.status, recoverable)
        result = close_startup_orphan_attempt_in_transaction(
            transaction,
            self.event_log_store,
            StartupOrphanCloseInput(
                run_id=run.run_id,
                expected_run_status=run.status,
                attempt_id=attempt.attempt_id,
                expected_attempt_status=attempt.status,
                execution_id=attempt.execution_id,
                dispatch_record_id=dispatch_record.dispatch_record_id,
                expected_dispatch_status=dispatch_record.status,
                owner_host_instance_id=proof.owner_host_instance_id,
                owner_heartbeat_at=proof.heartbeat_at,
                stale_after=policy.stale_after,
                recoverable=recoverable,
                attempt_lost_event_id=_event_id("attempt-lost-startup"),
                run_close_event_id=_event_id(
                    "run-recovering-startup" if recoverable else "run-lost-startup"
                ),
                occurred_at=policy.now,
                actor=_RECOVERY_ACTOR,
                source=_RECOVERY_SOURCE,
                reason=reason,
                orphan_proof_reason=proof.reason,
                observed_process_start_token=proof.observed_start_token,
                observed_boot_id=proof.observed_boot_id,
            ),
        )
        close_action = _action_from_mutation(
            run,
            result.status,
            StartupRecoveryDecision.RUN_RECOVERING
            if recoverable
            else StartupRecoveryDecision.RUN_LOST,
            reason,
        )
        if (
            not recoverable
            or result.status is not StateMutationStatus.UPDATED
            or result.run is None
        ):
            return close_action
        if (
            self.dispatch_wakeup_port is None
            or self.recovery_owner_host_instance_id is None
        ):
            return close_action
        dispatch_action = self._start_recovery_dispatch_or_ready(
            transaction,
            result.run,
            policy,
            pending_dispatches,
        )
        if dispatch_action.decision is StartupRecoveryDecision.INVALID_STATE:
            return _action(
                result.run,
                StartupRecoveryDecision.RECOVERING_READY,
                _REASON_RECOVERY_DISPATCH_PENDING_FOLLOW_UP,
            )
        return dispatch_action

    def _start_recovery_dispatch_or_ready(
        self,
        transaction: HostTransaction,
        run: RunRow,
        policy: StartupRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
    ) -> StartupRecoveryAction:
        """为 RECOVERING Run 创建新 Attempt 与 pending dispatch。

        :param transaction: Host transaction。
        :param run: recovering Run row。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :returns: startup recovery action。
        """

        if (
            self.dispatch_wakeup_port is None
            or self.recovery_owner_host_instance_id is None
        ):
            return _action(
                run,
                StartupRecoveryDecision.RECOVERING_READY,
                "recovery_dispatch_wakeup_unavailable",
            )
        if run.current_attempt_id is None:
            return _action(
                run,
                StartupRecoveryDecision.INVALID_STATE,
                "recovering_run_missing_source_attempt",
            )
        result = start_recovery_run_with_starting_attempt_in_transaction(
            transaction,
            self.event_log_store,
            StartRecoveryRunInput(
                run_id=run.run_id,
                source_attempt_id=run.current_attempt_id,
                run_started_event_id=_event_id("run-started-recovery"),
                attempt_started_event_id=_event_id("attempt-started-recovery"),
                attempt_id=_new_id(_ATTEMPT_ID_PREFIX),
                execution_id=_new_id(_EXECUTION_ID_PREFIX),
                dispatch_record_id=_new_id(_DISPATCH_RECORD_ID_PREFIX),
                occurred_at=policy.now,
                actor=_RECOVERY_ACTOR,
                source=_RECOVERY_SOURCE,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=self.recovery_owner_host_instance_id,
                context_compacted_event_id=None,
                context_compacted_event_sequence=None,
            ),
        )
        if (
            result.status is StateMutationStatus.UPDATED
            and result.run is not None
            and result.attempt is not None
            and result.dispatch_record is not None
        ):
            pending_dispatches.append(_pending_dispatch_from_transition(result))
        return _action_from_mutation(
            run,
            result.status,
            StartupRecoveryDecision.RECOVERY_DISPATCHED,
            RunStartReason.RECOVERY.value,
        )


def _validate_policy(policy: StartupRecoveryPolicy) -> None:
    """校验 startup recovery policy。

    :param policy: 待校验策略。
    :returns: ``None``。
    :raises ValueError: 任一字段非法时抛出。
    """

    if policy.now.tzinfo is None:
        raise ValueError("policy.now must be timezone-aware")
    if policy.stale_after <= timedelta(0):
        raise ValueError("policy.stale_after must be positive")
    if policy.recovery_dispatch_limit <= 0:
        raise ValueError("policy.recovery_dispatch_limit must be positive")


def _collect_process_evidence(
    probe: ProcessLivenessProbe, owner_liveness: HostInstanceRow | None
) -> ProcessEvidence | None:
    """采集 owner 进程证据。

    :param probe: 本机进程证据 probe。
    :param owner_liveness: durable liveness row；缺失时为 ``None``。
    :returns: 进程证据；无法采集时返回 ``None``。
    """

    if owner_liveness is None:
        return None
    try:
        return probe.collect(owner_liveness.pid)
    except ValueError:
        return None


def _read_current_attempt_and_dispatch(
    transaction: HostTransaction, run: RunRow
) -> tuple[AttemptRow | None, DispatchRecordRow | None]:
    """读取 Run 当前 Attempt 与 dispatch record。

    :param transaction: Host transaction。
    :param run: 目标 Run row。
    :returns: Attempt 与 dispatch record；缺失时对应位置为 ``None``。
    """

    if run.current_attempt_id is None:
        return None, None
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, run.current_attempt_id
    )
    return attempt, dispatch_record


def _run_has_recoverable_facts(
    run: RunRow, attempt: AttemptRow, dispatch_record: DispatchRecordRow
) -> bool:
    """判断 startup recovery 所需 durable facts 是否齐全。

    :param run: 目标 Run row。
    :param attempt: 当前 Attempt row。
    :param dispatch_record: 当前 dispatch record row。
    :returns: facts 齐全时返回 ``True``。
    """

    return (
        run.input_event_id.strip() != ""
        and run.accepted_event_id.strip() != ""
        and run.current_attempt_id == attempt.attempt_id
        and attempt.run_id == run.run_id
        and attempt.execution_id == dispatch_record.execution_id
        and dispatch_record.run_id == run.run_id
        and dispatch_record.attempt_id == attempt.attempt_id
    )


def _startup_closeout_reason(status: RunStatus, recoverable: bool) -> str:
    """生成 startup closeout reason。

    :param status: closeout 源 Run 状态。
    :param recoverable: 是否进入 recovering。
    :returns: 结构化 reason。
    """

    if status is RunStatus.CANCELLING:
        return _REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST
    if recoverable:
        return _REASON_STARTUP_ORPHAN_ATTEMPT_LOST
    return _REASON_UNRECOVERABLE_FACTS


def _action(
    run: RunRow, decision: StartupRecoveryDecision, reason: str
) -> StartupRecoveryAction:
    """构造 scan action。

    :param run: 目标 Run row。
    :param decision: scan decision。
    :param reason: 结构化原因。
    :returns: scan action。
    """

    return StartupRecoveryAction(
        run_id=run.run_id,
        status=run.status,
        decision=decision,
        reason=reason,
    )


def _action_from_mutation(
    run: RunRow,
    status: StateMutationStatus,
    success_decision: StartupRecoveryDecision,
    reason: str,
) -> StartupRecoveryAction:
    """根据 durable mutation 结果构造 scan action。

    :param run: 目标 Run row。
    :param status: mutation 状态。
    :param success_decision: mutation 成功时的 decision。
    :param reason: 结构化原因。
    :returns: scan action。
    """

    if status is StateMutationStatus.UPDATED:
        return _action(run, success_decision, reason)
    if status is StateMutationStatus.CAS_LOST:
        return _action(run, StartupRecoveryDecision.CAS_LOST, reason)
    if status is StateMutationStatus.NOT_FOUND:
        return _action(run, StartupRecoveryDecision.NOT_FOUND, reason)
    return _action(run, StartupRecoveryDecision.INVALID_STATE, reason)


def _event_id(prefix: str) -> str:
    """生成 Host recovery 内部事件 id。

    :param prefix: 事件 id 前缀。
    :returns: 全局唯一事件 id。
    """

    return f"event-{prefix}-{uuid4().hex}"


def _new_id(prefix: str) -> str:
    """生成 Host recovery 内部实体 id。

    :param prefix: id 前缀。
    :returns: 全局唯一实体 id。
    """

    return f"{prefix}-{uuid4().hex}"


def _pending_dispatch_from_transition(
    result: RunTransitionResult,
) -> PendingDispatchRecord:
    """从 recovery start transition 结果构造 pending dispatch 摘要。

    :param result: 已校验包含 run、attempt 与 dispatch record 的 transition 结果。
    :returns: pending dispatch 摘要。
    :raises AssertionError: 调用方未先校验 transition row 完整性时抛出。
    """

    if result.run is None or result.attempt is None or result.dispatch_record is None:
        raise AssertionError("transition result rows are required")
    return PendingDispatchRecord(
        dispatch_record_id=result.dispatch_record.dispatch_record_id,
        run_id=result.run.run_id,
        attempt_id=result.attempt.attempt_id,
        execution_id=result.attempt.execution_id,
        execution_target=result.dispatch_record.execution_target,
        worker_kind=result.dispatch_record.worker_kind,
    )
