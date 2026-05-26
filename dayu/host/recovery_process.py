"""Host recovery 进程证据与 orphan proof 分类。

本模块只提供本机进程存活探测与 positive orphan proof 的只读分类基础。
它不扫描 durable store、不写数据库、不推进 Run / Attempt 状态，也不实现
startup recovery closeout。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, TypeAlias

from dayu.host.durable.codec import parse_utc_timestamp
from dayu.host.durable.liveness import HostInstanceRow, HostInstanceStatus

_PROCESS_PROBE_ERROR_PERMISSION_DENIED = "permission_denied"
_PROCESS_PROBE_ERROR_UNEXPECTED_OS_ERROR = "unexpected_os_error"
_ORPHAN_REASON_PID_MISSING = "owner_pid_missing"
_ORPHAN_REASON_START_TOKEN_MISMATCH = "owner_pid_reused_start_token_mismatch"
_ORPHAN_REASON_BOOT_ID_MISMATCH = "owner_pid_reused_boot_id_mismatch"
_ORPHAN_REASON_OWNER_STOPPED = "owner_liveness_stopped"
_LIVE_REASON_HEARTBEAT_RECENT = "owner_heartbeat_recent"
_LIVE_REASON_PROCESS_IDENTITY_MATCHED = "owner_process_identity_matched"
_INCONCLUSIVE_REASON_MISSING_OWNER = "missing_owner_host_instance_id"
_INCONCLUSIVE_REASON_MISSING_LIVENESS = "missing_owner_liveness_row"
_INCONCLUSIVE_REASON_OWNER_NOT_RUNNING = "owner_liveness_not_running"
_INCONCLUSIVE_REASON_PROBE_PID_MISMATCH = "process_evidence_pid_mismatch"
_INCONCLUSIVE_REASON_PROBE_ERROR = "process_probe_error"
_INCONCLUSIVE_REASON_PID_LIVE_WITHOUT_IDENTITY = (
    "owner_pid_live_without_identity_proof"
)
_INCONCLUSIVE_REASON_HEARTBEAT_PARSE_FAILED = "owner_heartbeat_parse_failed"


@dataclass(frozen=True, slots=True)
class ProcessEvidence:
    """本机进程探测证据。

    :param pid: 被探测的进程 pid。
    :param exists: pid 当前是否存在。
    :param observed_start_token: 可选的进程启动指纹；不可观测时为 ``None``。
    :param observed_boot_id: 可选的 boot id；不可观测时为 ``None``。
    :param probe_error_code: 探测失败错误码；无错误时为 ``None``。
    """

    pid: int
    exists: bool
    observed_start_token: str | None
    observed_boot_id: str | None
    probe_error_code: str | None


class ProcessLivenessProbe(Protocol):
    """本机进程存活探测端口。"""

    def collect(self, pid: int) -> ProcessEvidence:
        """采集指定 pid 的进程证据。

        :param pid: 目标进程 pid。
        :returns: 本机进程存活证据。
        :raises ValueError: ``pid`` 非正时抛出。
        """

        ...


@dataclass(frozen=True, slots=True)
class StdlibPidLivenessProbe:
    """基于标准库 ``os.kill(pid, 0)`` 的 pid 存活探测。"""

    def collect(self, pid: int) -> ProcessEvidence:
        """采集指定 pid 是否存在。

        :param pid: 目标进程 pid。
        :returns: 只包含 pid 是否存在的进程证据。
        :raises ValueError: ``pid`` 非正时抛出。
        """

        if pid <= 0:
            raise ValueError("pid must be positive")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return ProcessEvidence(
                pid=pid,
                exists=False,
                observed_start_token=None,
                observed_boot_id=None,
                probe_error_code=None,
            )
        except PermissionError:
            return ProcessEvidence(
                pid=pid,
                exists=True,
                observed_start_token=None,
                observed_boot_id=None,
                probe_error_code=_PROCESS_PROBE_ERROR_PERMISSION_DENIED,
            )
        except OSError:
            return ProcessEvidence(
                pid=pid,
                exists=False,
                observed_start_token=None,
                observed_boot_id=None,
                probe_error_code=_PROCESS_PROBE_ERROR_UNEXPECTED_OS_ERROR,
            )
        return ProcessEvidence(
            pid=pid,
            exists=True,
            observed_start_token=None,
            observed_boot_id=None,
            probe_error_code=None,
        )


@dataclass(frozen=True, slots=True)
class DurableOrphanCandidate:
    """durable owner 候选输入。

    :param owner_host_instance_id: dispatch record 记录的 owner Host instance id。
    :param owner_liveness: owner 对应的 liveness row；缺失时为 ``None``。
    """

    owner_host_instance_id: str | None
    owner_liveness: HostInstanceRow | None


@dataclass(frozen=True, slots=True)
class OrphanClassificationPolicy:
    """orphan proof 分类策略输入。

    :param now: 当前策略时间。
    :param stale_after: heartbeat 超过该时长才视为 stale。
    """

    now: datetime
    stale_after: timedelta


@dataclass(frozen=True, slots=True)
class PositiveOrphanProof:
    """可进入 recovery CAS closeout 的 positive orphan proof。

    :param owner_host_instance_id: 被证明 orphan 的 owner Host instance id。
    :param pid: owner durable row 记录的 pid。
    :param reason: 结构化 proof 原因。
    :param heartbeat_at: durable row 中被分类的 heartbeat timestamp。
    :param observed_start_token: 探测到的启动指纹；不可用时为 ``None``。
    :param observed_boot_id: 探测到的 boot id；不可用时为 ``None``。
    """

    owner_host_instance_id: str
    pid: int
    reason: str
    heartbeat_at: str
    observed_start_token: str | None
    observed_boot_id: str | None


@dataclass(frozen=True, slots=True)
class OwnerStillLive:
    """owner 仍被判断为存活。

    :param owner_host_instance_id: owner Host instance id。
    :param pid: owner durable row 记录的 pid。
    :param reason: 结构化存活原因。
    :param heartbeat_at: durable row 中被分类的 heartbeat timestamp。
    """

    owner_host_instance_id: str
    pid: int
    reason: str
    heartbeat_at: str


@dataclass(frozen=True, slots=True)
class OrphanProofInconclusive:
    """当前证据不足以证明 orphan。

    :param reason: 结构化不确定原因。
    :param owner_host_instance_id: owner Host instance id；缺失时为 ``None``。
    :param pid: durable row 记录或进程证据中的 pid；不可用时为 ``None``。
    :param heartbeat_at: durable row 中被分类的 heartbeat timestamp；不可用时为 ``None``。
    :param probe_error_code: 进程探测错误码；无错误时为 ``None``。
    """

    reason: str
    owner_host_instance_id: str | None
    pid: int | None
    heartbeat_at: str | None
    probe_error_code: str | None


OrphanClassification: TypeAlias = (
    PositiveOrphanProof | OwnerStillLive | OrphanProofInconclusive
)


def classify_orphan_candidate(
    candidate: DurableOrphanCandidate,
    evidence: ProcessEvidence | None,
    policy: OrphanClassificationPolicy,
) -> OrphanClassification:
    """根据 durable owner、进程证据与策略时间分类 orphan proof。

    :param candidate: durable owner 候选输入。
    :param evidence: 本机进程探测证据；探测不可用时可为 ``None``。
    :param policy: stale 阈值与当前策略时间。
    :returns: positive proof、still live 或 inconclusive 的 typed union。
    :raises ValueError: stale 阈值非正或策略时间缺少 timezone 时抛出。
    """

    _validate_policy(policy)
    if candidate.owner_host_instance_id is None:
        return OrphanProofInconclusive(
            reason=_INCONCLUSIVE_REASON_MISSING_OWNER,
            owner_host_instance_id=None,
            pid=None,
            heartbeat_at=None,
            probe_error_code=None,
        )
    if candidate.owner_liveness is None:
        return OrphanProofInconclusive(
            reason=_INCONCLUSIVE_REASON_MISSING_LIVENESS,
            owner_host_instance_id=candidate.owner_host_instance_id,
            pid=None,
            heartbeat_at=None,
            probe_error_code=None,
        )
    row = candidate.owner_liveness
    if row.status is HostInstanceStatus.STOPPED:
        return PositiveOrphanProof(
            owner_host_instance_id=candidate.owner_host_instance_id,
            pid=row.pid,
            reason=_ORPHAN_REASON_OWNER_STOPPED,
            heartbeat_at=row.heartbeat_at,
            observed_start_token=None,
            observed_boot_id=None,
        )
    if row.status not in (HostInstanceStatus.RUNNING, HostInstanceStatus.STOPPING):
        return OrphanProofInconclusive(
            reason=_INCONCLUSIVE_REASON_OWNER_NOT_RUNNING,
            owner_host_instance_id=candidate.owner_host_instance_id,
            pid=row.pid,
            heartbeat_at=row.heartbeat_at,
            probe_error_code=None,
        )
    try:
        heartbeat_at = parse_utc_timestamp(row.heartbeat_at)
    except ValueError:
        return OrphanProofInconclusive(
            reason=_INCONCLUSIVE_REASON_HEARTBEAT_PARSE_FAILED,
            owner_host_instance_id=candidate.owner_host_instance_id,
            pid=row.pid,
            heartbeat_at=row.heartbeat_at,
            probe_error_code=None,
        )
    if policy.now - heartbeat_at <= policy.stale_after:
        return OwnerStillLive(
            owner_host_instance_id=candidate.owner_host_instance_id,
            pid=row.pid,
            reason=_LIVE_REASON_HEARTBEAT_RECENT,
            heartbeat_at=row.heartbeat_at,
        )
    return _classify_stale_owner(candidate.owner_host_instance_id, row, evidence)


def _classify_stale_owner(
    owner_host_instance_id: str,
    row: HostInstanceRow,
    evidence: ProcessEvidence | None,
) -> OrphanClassification:
    """分类 heartbeat 已 stale 的 owner。

    :param owner_host_instance_id: owner Host instance id。
    :param row: owner liveness row。
    :param evidence: 进程探测证据；探测不可用时可为 ``None``。
    :returns: positive proof、still live 或 inconclusive。
    :raises Exception: 不主动抛出异常。
    """

    if evidence is None:
        return OrphanProofInconclusive(
            reason=_INCONCLUSIVE_REASON_PID_LIVE_WITHOUT_IDENTITY,
            owner_host_instance_id=owner_host_instance_id,
            pid=row.pid,
            heartbeat_at=row.heartbeat_at,
            probe_error_code=None,
        )
    if evidence.pid != row.pid:
        return OrphanProofInconclusive(
            reason=_INCONCLUSIVE_REASON_PROBE_PID_MISMATCH,
            owner_host_instance_id=owner_host_instance_id,
            pid=row.pid,
            heartbeat_at=row.heartbeat_at,
            probe_error_code=evidence.probe_error_code,
        )
    if evidence.probe_error_code is not None:
        return OrphanProofInconclusive(
            reason=_INCONCLUSIVE_REASON_PROBE_ERROR,
            owner_host_instance_id=owner_host_instance_id,
            pid=row.pid,
            heartbeat_at=row.heartbeat_at,
            probe_error_code=evidence.probe_error_code,
        )
    if not evidence.exists:
        return _positive_orphan_proof(
            owner_host_instance_id,
            row,
            evidence,
            reason=_ORPHAN_REASON_PID_MISSING,
        )
    if (
        evidence.observed_start_token is not None
        and evidence.observed_start_token != row.process_start_token
    ):
        return _positive_orphan_proof(
            owner_host_instance_id,
            row,
            evidence,
            reason=_ORPHAN_REASON_START_TOKEN_MISMATCH,
        )
    if (
        evidence.observed_boot_id is not None
        and row.boot_id is not None
        and evidence.observed_boot_id != row.boot_id
    ):
        return _positive_orphan_proof(
            owner_host_instance_id,
            row,
            evidence,
            reason=_ORPHAN_REASON_BOOT_ID_MISMATCH,
        )
    if evidence.observed_start_token == row.process_start_token:
        return OwnerStillLive(
            owner_host_instance_id=owner_host_instance_id,
            pid=row.pid,
            reason=_LIVE_REASON_PROCESS_IDENTITY_MATCHED,
            heartbeat_at=row.heartbeat_at,
        )
    return OrphanProofInconclusive(
        reason=_INCONCLUSIVE_REASON_PID_LIVE_WITHOUT_IDENTITY,
        owner_host_instance_id=owner_host_instance_id,
        pid=row.pid,
        heartbeat_at=row.heartbeat_at,
        probe_error_code=None,
    )


def _positive_orphan_proof(
    owner_host_instance_id: str,
    row: HostInstanceRow,
    evidence: ProcessEvidence,
    *,
    reason: str,
) -> PositiveOrphanProof:
    """构造 positive orphan proof。

    :param owner_host_instance_id: owner Host instance id。
    :param row: owner liveness row。
    :param evidence: 进程探测证据。
    :param reason: 结构化 proof 原因。
    :returns: PositiveOrphanProof。
    :raises Exception: 不主动抛出异常。
    """

    return PositiveOrphanProof(
        owner_host_instance_id=owner_host_instance_id,
        pid=row.pid,
        reason=reason,
        heartbeat_at=row.heartbeat_at,
        observed_start_token=evidence.observed_start_token,
        observed_boot_id=evidence.observed_boot_id,
    )


def _validate_policy(policy: OrphanClassificationPolicy) -> None:
    """校验 orphan classification policy。

    :param policy: 分类策略。
    :returns: ``None``。
    :raises ValueError: stale 阈值非正或策略时间缺少 timezone 时抛出。
    """

    if policy.now.tzinfo is None or policy.now.utcoffset() is None:
        raise ValueError("policy now must be timezone-aware")
    if policy.stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")


__all__ = [
    "DurableOrphanCandidate",
    "OrphanClassification",
    "OrphanClassificationPolicy",
    "OrphanProofInconclusive",
    "OwnerStillLive",
    "PositiveOrphanProof",
    "ProcessEvidence",
    "ProcessLivenessProbe",
    "StdlibPidLivenessProbe",
    "classify_orphan_candidate",
]
