"""Host Session attachment target recovery scan 编排。

本模块只读取目标 Session 的 durable Run/Attempt/dispatch/liveness truth，调用
只读 orphan proof classifier，并在 positive proof 成立时通过 durable
transition helper 完成旧 Attempt closeout。Slice 3 起，本模块还负责为
可恢复 Run 创建 recovery Attempt、execution 与 pending dispatch record，
并在事务提交后唤醒 scheduler。它不实现 public API、不直接调用 WorkerProxy，
也不读取 projection/read-model。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final
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
    project_terminal_notice_from_exact_run_event,
    read_cancel_requested_event_from_run_link,
    start_recovery_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    NonTerminalRunKeysetCursor,
    RunRow,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_non_terminal_run_upper_watermark_for_session,
    read_non_terminal_runs_for_session_keyset_page,
    read_session_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.terminal_post_commit import (
    TerminalPostCommitNotice,
    TerminalPostCommitPort,
)
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
_RECOVERY_SOURCE = "session_attachment_recovery"
# heartbeat 周期必须显著小于 stale 阈值，避免破坏 positive orphan proof。
_DEFAULT_STALE_AFTER_SECONDS = 30
_DEFAULT_RECOVERY_DISPATCH_LIMIT = 1
DEFAULT_SESSION_ATTACHMENT_RECOVERY_BATCH_SIZE: Final[int] = 64
"""单个 startup recovery write transaction 最多处理的 Run 数。"""
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
_LOGGER = logging.getLogger(__name__)


class SessionAttachmentRecoveryDecision(StrEnum):
    """startup scan 对单个 Run 的分类决策。"""

    ACCEPTED_WAKE = "accepted_wake"
    QUEUE_PROMOTION_CHECK = "queue_promotion_check"
    WAITING_DIAGNOSTIC_ONLY = "waiting_diagnostic_only"
    OWNER_STILL_LIVE = "owner_still_live"
    ORPHAN_INCONCLUSIVE = "orphan_inconclusive"
    DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG = "deferred_to_active_cancel_watchdog"
    RUN_RECOVERING = "run_recovering"
    RUN_LOST = "run_lost"
    RECOVERING_READY = "recovering_ready"
    RECOVERY_DISPATCHED = "recovery_dispatched"
    CAS_LOST = "cas_lost"
    INVALID_STATE = "invalid_state"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class SessionAttachmentRecoveryPolicy:
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
    def default(cls) -> "SessionAttachmentRecoveryPolicy":
        """构造默认 startup recovery 策略。

        :returns: 默认策略；stale 阈值大于 Slice 1 scheduler heartbeat 周期。
        """

        return cls(
            now=datetime.now(UTC),
            stale_after=timedelta(seconds=_DEFAULT_STALE_AFTER_SECONDS),
            recovery_dispatch_limit=_DEFAULT_RECOVERY_DISPATCH_LIMIT,
        )


@dataclass(frozen=True, slots=True)
class SessionAttachmentRecoveryAction:
    """单个 Run 的 startup recovery scan 结果。

    :param run_id: 目标 Run id。
    :param status: scan 时观察到的 Run 状态。
    :param decision: 分类决策。
    :param reason: 结构化原因。
    """

    run_id: str
    status: RunStatus
    decision: SessionAttachmentRecoveryDecision
    reason: str


@dataclass(frozen=True, slots=True)
class SessionAttachmentRecoveryScanResult:
    """startup recovery scan 汇总。

    :param actions: 按扫描顺序记录的每个 Run 分类结果。
    :param pending_dispatches: 本次 scan 事务提交后唤醒的 pending dispatch 摘要。
    :param queue_promotion_sessions: 本次 scan 事务提交后唤醒 queue
        promotion 的 Session id。
    :param terminal_notices: 本次 transaction 提交的 exact terminal notices。
    """

    actions: tuple[SessionAttachmentRecoveryAction, ...]
    pending_dispatches: tuple[PendingDispatchRecord, ...] = ()
    queue_promotion_sessions: tuple[str, ...] = ()
    terminal_notices: tuple[TerminalPostCommitNotice, ...] = ()


@dataclass(frozen=True, slots=True)
class _SessionAttachmentRecoveryBatchResult:
    """单个已提交 recovery batch 的 immutable 结果。

    :param result: 本批 actions 与 commit 后 wakes。
    :param next_cursor: 本批最后一行 keyset；空页沿用输入 cursor。
    :param page_size: 本批实际读取并分类的 Run row 数。
    """

    result: SessionAttachmentRecoveryScanResult
    next_cursor: NonTerminalRunKeysetCursor | None
    page_size: int


@dataclass(frozen=True, slots=True)
class _SessionAttachmentRecoveryBatchOperation:
    """单个 bounded startup recovery write transaction body。

    :param scanner: 提供既有业务分类的 recovery owner。
    :param upper_watermark: scan 开始时固定的 durable upper watermark。
    :param cursor: 上一批最后提交的 keyset。
    :param batch_size: 本批最大 Run row 数。
    :param policy: 整个 scan 共享的 fixed policy。
    :param policy_now: scan 开始时冻结的 policy time invariant。
    :param seen_queue_promotion_sessions: 先前已提交批次唤醒过的 Session ids。
    """

    scanner: "SessionAttachmentRecoveryScanner"
    upper_watermark: NonTerminalRunKeysetCursor
    cursor: NonTerminalRunKeysetCursor | None
    batch_size: int
    policy: SessionAttachmentRecoveryPolicy
    policy_now: datetime
    seen_queue_promotion_sessions: frozenset[str]

    def __call__(self, transaction: HostTransaction) -> _SessionAttachmentRecoveryBatchResult:
        """读取一个 keyset page 并在同一 write transaction 分类/迁移。

        :param transaction: 当前 bounded Host write transaction。
        :returns: immutable batch result；只可在 commit 成功后消费其中 wake。
        :raises RuntimeError: scan policy time 在批间发生漂移时抛出。
        :raises HostDurableError: durable read/mutation 失败时由底层抛出。
        """

        if self.policy.now != self.policy_now:
            raise RuntimeError("startup recovery policy time changed within scan")
        runs = read_non_terminal_runs_for_session_keyset_page(
            transaction,
            session_id=self.scanner.session_id,
            upper_watermark=self.upper_watermark,
            cursor=self.cursor,
            batch_size=self.batch_size,
        )
        actions: list[SessionAttachmentRecoveryAction] = []
        pending_dispatches: list[PendingDispatchRecord] = []
        queue_promotion_sessions: list[str] = []
        terminal_notices: list[TerminalPostCommitNotice] = []
        seen_queue_promotion_sessions = set(self.seen_queue_promotion_sessions)
        for run in runs:
            actions.append(
                self.scanner._classify_run(
                    transaction,
                    run,
                    self.policy,
                    pending_dispatches,
                    queue_promotion_sessions,
                    seen_queue_promotion_sessions,
                    terminal_notices,
                )
            )
        next_cursor = self.cursor
        if runs:
            next_cursor = _keyset_cursor_from_run(runs[-1])
        return _SessionAttachmentRecoveryBatchResult(
            result=SessionAttachmentRecoveryScanResult(
                actions=tuple(actions),
                pending_dispatches=tuple(pending_dispatches),
                queue_promotion_sessions=tuple(queue_promotion_sessions),
                terminal_notices=tuple(
                    sorted(
                        terminal_notices,
                        key=lambda notice: notice.terminal_event_sequence,
                    )
                ),
            ),
            next_cursor=next_cursor,
            page_size=len(runs),
        )


@dataclass(frozen=True, slots=True)
class SessionAttachmentRecoveryScanner:
    """目标 Session attachment recovery scanner。

    :param session_id: 本次 scan 唯一允许读取与推进的目标 Session id。
    :param transaction_runner: Host durable transaction runner。
    :param event_log_store: EventLog primitive。
    :param process_probe: 本机进程证据 probe。
    :param dispatch_wakeup_port: commit 后唤醒 dispatch 的端口；未提供时只做
        Slice 2 closeout / classification，不创建 startup recovery dispatch。
    :param recovery_owner_host_instance_id: 当前 opener 的 Host instance id；
        创建 recovery dispatch record 时写入 owner 诊断字段。
    :param defer_accepted_cancel_to_watchdog: 为 ``True`` 且已注入 scheduler
        wakeup port 时，带有已接受 active cancel durable facts 的
        ``CANCELLING`` Run 由 active cancel watchdog 收口；未注入 scheduler
        时 recovery 按 orphan proof 执行 fallback closeout。
    :param batch_size: 单个 recovery write transaction 最大处理 Run row 数。
    """

    session_id: str
    transaction_runner: HostTransactionRunner
    event_log_store: EventLogStore
    terminal_post_commit_port: TerminalPostCommitPort
    process_probe: ProcessLivenessProbe = StdlibPidLivenessProbe()
    dispatch_wakeup_port: AdmissionWakeupPort | None = None
    recovery_owner_host_instance_id: str | None = None
    defer_accepted_cancel_to_watchdog: bool = False
    batch_size: int = DEFAULT_SESSION_ATTACHMENT_RECOVERY_BATCH_SIZE

    def scan(
        self, policy: SessionAttachmentRecoveryPolicy | None = None
    ) -> SessionAttachmentRecoveryScanResult:
        """执行 target-session attachment recovery scan。

        :param policy: 可选 scan 策略；未传时使用默认策略。
        :returns: scan 结果。
        :raises HostDurableError: durable 读取或写入失败时由底层抛出。
        """

        if self.session_id.strip() == "":
            raise ValueError("session_id must be non-empty")
        effective_policy = policy if policy is not None else SessionAttachmentRecoveryPolicy.default()
        _validate_policy(effective_policy)
        _validate_batch_size(self.batch_size)
        policy_now = effective_policy.now
        upper_watermark = self.transaction_runner.run_read(
            lambda transaction: read_non_terminal_run_upper_watermark_for_session(
                transaction,
                self.session_id,
            )
        )
        if upper_watermark is None:
            return SessionAttachmentRecoveryScanResult(actions=())

        cursor: NonTerminalRunKeysetCursor | None = None
        actions: list[SessionAttachmentRecoveryAction] = []
        pending_dispatches: list[PendingDispatchRecord] = []
        queue_promotion_sessions: list[str] = []
        terminal_notices: list[TerminalPostCommitNotice] = []
        seen_queue_promotion_sessions: set[str] = set()
        while cursor != upper_watermark:
            batch = self.transaction_runner.run_write(
                _SessionAttachmentRecoveryBatchOperation(
                    scanner=self,
                    upper_watermark=upper_watermark,
                    cursor=cursor,
                    batch_size=self.batch_size,
                    policy=effective_policy,
                    policy_now=policy_now,
                    seen_queue_promotion_sessions=frozenset(
                        seen_queue_promotion_sessions
                    ),
                )
            )
            if batch.page_size == 0:
                break
            self._wake_after_committed_batch(batch.result)
            actions.extend(batch.result.actions)
            pending_dispatches.extend(batch.result.pending_dispatches)
            queue_promotion_sessions.extend(
                batch.result.queue_promotion_sessions
            )
            terminal_notices.extend(batch.result.terminal_notices)
            seen_queue_promotion_sessions.update(
                batch.result.queue_promotion_sessions
            )
            if batch.next_cursor is None or batch.next_cursor == cursor:
                raise RuntimeError("startup recovery keyset cursor did not advance")
            cursor = batch.next_cursor

        return SessionAttachmentRecoveryScanResult(
            actions=tuple(actions),
            pending_dispatches=tuple(pending_dispatches),
            queue_promotion_sessions=tuple(queue_promotion_sessions),
            terminal_notices=tuple(terminal_notices),
        )

    def _wake_after_committed_batch(self, result: SessionAttachmentRecoveryScanResult) -> None:
        """只在当前 batch commit 成功后同步投递其 matching wake。

        :param result: 已提交 batch 返回的 immutable actions/wakes。
        :returns: ``None``。
        :raises Exception: scheduler wake bridge 失败时透传，中止 startup READY。
        """

        for notice in result.terminal_notices:
            self.terminal_post_commit_port.notify_terminal_post_commit(notice)
        if self.dispatch_wakeup_port is not None:
            for pending_dispatch in result.pending_dispatches:
                self.dispatch_wakeup_port.wake_dispatch(pending_dispatch)
            for session_id in result.queue_promotion_sessions:
                self.dispatch_wakeup_port.wake_queue_promotion(session_id)
        elif result.queue_promotion_sessions:
            _LOGGER.error(
                "host.recovery.queue_promotion_wakeup_unavailable "
                "session_count=%s sessions=%s",
                len(result.queue_promotion_sessions),
                ",".join(result.queue_promotion_sessions),
            )

    def _classify_run(
        self,
        transaction: HostTransaction,
        run: RunRow,
        policy: SessionAttachmentRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
        queue_promotion_sessions: list[str],
        seen_queue_promotion_sessions: set[str],
        terminal_notices: list[TerminalPostCommitNotice],
    ) -> SessionAttachmentRecoveryAction:
        """分类单个非终态 Run。

        :param transaction: Host transaction。
        :param run: 待分类 Run row。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :param queue_promotion_sessions: 本次 scan 需要在事务提交后唤醒
            queue promotion 的 Session id 集合。
        :param seen_queue_promotion_sessions: 已加入
            ``queue_promotion_sessions`` 的 Session id 集合。
        :param terminal_notices: 本 batch transaction-local exact notices。
        :returns: 单个 Run 的分类结果。
        """

        if read_session_by_id(transaction, run.session_id) is None:
            return _action(run, SessionAttachmentRecoveryDecision.NOT_FOUND, "session_missing")
        if run.status is RunStatus.ACCEPTED:
            _append_unseen_session_id(
                queue_promotion_sessions,
                seen_queue_promotion_sessions,
                run.session_id,
            )
            return _action(run, SessionAttachmentRecoveryDecision.ACCEPTED_WAKE, "accepted")
        if run.status is RunStatus.QUEUED:
            _append_unseen_session_id(
                queue_promotion_sessions,
                seen_queue_promotion_sessions,
                run.session_id,
            )
            return _action(
                run,
                SessionAttachmentRecoveryDecision.QUEUE_PROMOTION_CHECK,
                "queued",
            )
        if run.status is RunStatus.WAITING:
            return _action(
                run,
                SessionAttachmentRecoveryDecision.WAITING_DIAGNOSTIC_ONLY,
                "waiting_adapter_observation_unavailable",
            )
        if run.status is RunStatus.RECOVERING:
            return self._classify_recovering(
                transaction,
                run,
                policy,
                pending_dispatches,
                terminal_notices,
            )
        if run.status in (RunStatus.RUNNING, RunStatus.CANCELLING):
            if (
                run.status is RunStatus.CANCELLING
                and self.defer_accepted_cancel_to_watchdog
                and self.dispatch_wakeup_port is not None
                and _has_accepted_cancel_fact(
                    transaction,
                    self.event_log_store,
                    run,
                )
            ):
                return _action(
                    run,
                    SessionAttachmentRecoveryDecision.DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG,
                    "accepted_cancel_watchdog_owner",
                )
            return self._classify_active_or_cancelling(
                transaction,
                run,
                policy,
                pending_dispatches,
                terminal_notices,
            )
        return _action(run, SessionAttachmentRecoveryDecision.INVALID_STATE, "unsupported_status")

    def _classify_recovering(
        self,
        transaction: HostTransaction,
        run: RunRow,
        policy: SessionAttachmentRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
        terminal_notices: list[TerminalPostCommitNotice],
    ) -> SessionAttachmentRecoveryAction:
        """分类 recovering Run。

        :param transaction: Host transaction。
        :param run: recovering Run row。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :param terminal_notices: 当前 batch 的 exact terminal notices。
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
                SessionAttachmentRecoveryDecision.INVALID_STATE,
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
        if result.status is StateMutationStatus.UPDATED:
            terminal_notices.append(
                project_terminal_notice_from_exact_run_event(
                    result.run,
                    result.run_event,
                    wake_queue_promotion=True,
                )
            )
        return _action_from_mutation(
            run,
            result.status,
            SessionAttachmentRecoveryDecision.RUN_LOST,
            _REASON_RECOVERY_DISPATCH_LIMIT_EXCEEDED,
        )

    def _classify_active_or_cancelling(
        self,
        transaction: HostTransaction,
        run: RunRow,
        policy: SessionAttachmentRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
        terminal_notices: list[TerminalPostCommitNotice],
    ) -> SessionAttachmentRecoveryAction:
        """分类 running 或 cancelling Run。

        :param transaction: Host transaction。
        :param run: running 或 cancelling Run row。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :param terminal_notices: 当前 batch 的 exact terminal notices。
        :returns: 分类结果。
        """

        attempt, dispatch_record = _read_current_attempt_and_dispatch(
            transaction, run
        )
        if attempt is None or dispatch_record is None:
            return _action(
                run,
                SessionAttachmentRecoveryDecision.ORPHAN_INCONCLUSIVE,
                "missing_current_attempt_or_dispatch",
            )
        classification = self._classify_owner(transaction, dispatch_record, policy)
        if isinstance(classification, OwnerStillLive):
            return _action(
                run,
                SessionAttachmentRecoveryDecision.OWNER_STILL_LIVE,
                classification.reason,
            )
        if isinstance(classification, OrphanProofInconclusive):
            return _action(
                run,
                SessionAttachmentRecoveryDecision.ORPHAN_INCONCLUSIVE,
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
            terminal_notices,
        )

    def _classify_owner(
        self,
        transaction: HostTransaction,
        dispatch_record: DispatchRecordRow,
        policy: SessionAttachmentRecoveryPolicy,
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
        policy: SessionAttachmentRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
        terminal_notices: list[TerminalPostCommitNotice],
    ) -> SessionAttachmentRecoveryAction:
        """对 positive orphan proof 执行 CAS closeout。

        :param transaction: Host transaction。
        :param run: 目标 Run row。
        :param attempt: 目标 Attempt row。
        :param dispatch_record: 目标 dispatch record row。
        :param proof: positive orphan proof。
        :param policy: scan 策略。
        :param pending_dispatches: 本次 scan 已创建的待唤醒 dispatch 摘要集合。
        :param terminal_notices: 当前 batch 的 exact terminal notices。
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
            SessionAttachmentRecoveryDecision.RUN_RECOVERING
            if recoverable
            else SessionAttachmentRecoveryDecision.RUN_LOST,
            reason,
        )
        if not recoverable and result.status is StateMutationStatus.UPDATED:
            terminal_notices.append(
                project_terminal_notice_from_exact_run_event(
                    result.run,
                    result.run_event,
                    wake_queue_promotion=True,
                )
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
        if dispatch_action.decision is SessionAttachmentRecoveryDecision.INVALID_STATE:
            return _action(
                result.run,
                SessionAttachmentRecoveryDecision.RECOVERING_READY,
                _REASON_RECOVERY_DISPATCH_PENDING_FOLLOW_UP,
            )
        return dispatch_action

    def _start_recovery_dispatch_or_ready(
        self,
        transaction: HostTransaction,
        run: RunRow,
        policy: SessionAttachmentRecoveryPolicy,
        pending_dispatches: list[PendingDispatchRecord],
    ) -> SessionAttachmentRecoveryAction:
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
                SessionAttachmentRecoveryDecision.RECOVERING_READY,
                "recovery_dispatch_wakeup_unavailable",
            )
        if run.current_attempt_id is None:
            return _action(
                run,
                SessionAttachmentRecoveryDecision.INVALID_STATE,
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
            SessionAttachmentRecoveryDecision.RECOVERY_DISPATCHED,
            RunStartReason.RECOVERY.value,
        )


def _validate_policy(policy: SessionAttachmentRecoveryPolicy) -> None:
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


def _validate_batch_size(batch_size: int) -> None:
    """校验 startup recovery batch size。

    :param batch_size: 待校验单批最大行数。
    :returns: ``None``。
    :raises TypeError: batch size 不是严格整数时抛出。
    :raises ValueError: batch size 非正时抛出。
    """

    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise TypeError("batch_size must be int")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")


def _keyset_cursor_from_run(run: RunRow) -> NonTerminalRunKeysetCursor:
    """从已校验 Run row 派生 recovery keyset cursor。

    :param run: 当前 batch 最后一条 Run row。
    :returns: 对应 accepted sequence/run id keyset。
    :raises Exception: 不主动抛出异常。
    """

    return NonTerminalRunKeysetCursor(
        accepted_event_sequence=run.accepted_event_sequence,
        run_id=run.run_id,
    )


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


def _has_accepted_cancel_fact(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    run: RunRow,
) -> bool:
    """判断 Run 是否具有完整 accepted active cancel durable facts。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param run: 目标 Run row。
    :returns: Run row typed link 能指向同 Run 的 ``CANCEL_REQUESTED`` 时返回
        ``True``。
    """

    return (
        read_cancel_requested_event_from_run_link(transaction, event_log_store, run)
        is not None
    )


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
    run: RunRow, decision: SessionAttachmentRecoveryDecision, reason: str
) -> SessionAttachmentRecoveryAction:
    """构造 scan action。

    :param run: 目标 Run row。
    :param decision: scan decision。
    :param reason: 结构化原因。
    :returns: scan action。
    """

    return SessionAttachmentRecoveryAction(
        run_id=run.run_id,
        status=run.status,
        decision=decision,
        reason=reason,
    )


def _action_from_mutation(
    run: RunRow,
    status: StateMutationStatus,
    success_decision: SessionAttachmentRecoveryDecision,
    reason: str,
) -> SessionAttachmentRecoveryAction:
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
        return _action(run, SessionAttachmentRecoveryDecision.CAS_LOST, reason)
    if status is StateMutationStatus.NOT_FOUND:
        return _action(run, SessionAttachmentRecoveryDecision.NOT_FOUND, reason)
    return _action(run, SessionAttachmentRecoveryDecision.INVALID_STATE, reason)


def _append_unseen_session_id(
    ordered_session_ids: list[str], seen_session_ids: set[str], session_id: str
) -> None:
    """按扫描顺序追加尚未出现的 Session id。

    :param ordered_session_ids: 按扫描顺序保存的 Session id 列表。
    :param seen_session_ids: 已收集的 Session id 集合。
    :param session_id: 待追加 Session id。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if session_id in seen_session_ids:
        return
    seen_session_ids.add(session_id)
    ordered_session_ids.append(session_id)


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
