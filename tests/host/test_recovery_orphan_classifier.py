"""Host recovery orphan classifier 测试。"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.liveness import HostInstanceRow, HostInstanceStatus
from dayu.host.recovery_process import (
    DurableOrphanCandidate,
    OrphanClassificationPolicy,
    OrphanProofInconclusive,
    OwnerStillLive,
    PositiveOrphanProof,
    ProcessEvidence,
    StdlibPidLivenessProbe,
    classify_orphan_candidate,
)

_NOW = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
_STALE_AFTER = timedelta(seconds=30)


def _policy() -> OrphanClassificationPolicy:
    """构造测试用 orphan classification policy。

    :returns: OrphanClassificationPolicy。
    :raises Exception: 不主动抛出异常。
    """

    return OrphanClassificationPolicy(now=_NOW, stale_after=_STALE_AFTER)


def _row(
    *,
    heartbeat_age_seconds: int,
    pid: int = 123456,
    status: HostInstanceStatus = HostInstanceStatus.RUNNING,
    process_start_token: str = "token-owner",
    boot_id: str | None = "boot-owner",
) -> HostInstanceRow:
    """构造测试用 HostInstanceRow。

    :param heartbeat_age_seconds: heartbeat 距离 ``_NOW`` 的秒数。
    :param pid: owner pid。
    :param status: liveness status。
    :param process_start_token: owner 启动指纹。
    :param boot_id: owner boot id。
    :returns: HostInstanceRow。
    :raises Exception: 不主动抛出异常。
    """

    heartbeat_at = format_utc_timestamp(
        _NOW - timedelta(seconds=heartbeat_age_seconds)
    )
    return HostInstanceRow(
        host_instance_id="host-owner",
        pid=pid,
        process_start_token=process_start_token,
        boot_id=boot_id,
        created_at=heartbeat_at,
        heartbeat_at=heartbeat_at,
        status=status,
    )


def _candidate(row: HostInstanceRow | None) -> DurableOrphanCandidate:
    """构造测试用 durable orphan candidate。

    :param row: owner liveness row；缺失时为 ``None``。
    :returns: DurableOrphanCandidate。
    :raises Exception: 不主动抛出异常。
    """

    return DurableOrphanCandidate(
        owner_host_instance_id="host-owner",
        owner_liveness=row,
    )


def _evidence(
    *,
    exists: bool,
    pid: int = 123456,
    observed_start_token: str | None = None,
    observed_boot_id: str | None = None,
    probe_error_code: str | None = None,
) -> ProcessEvidence:
    """构造测试用 ProcessEvidence。

    :param exists: pid 是否存在。
    :param pid: 被探测 pid。
    :param observed_start_token: 可选启动指纹。
    :param observed_boot_id: 可选 boot id。
    :param probe_error_code: 可选探测错误码。
    :returns: ProcessEvidence。
    :raises Exception: 不主动抛出异常。
    """

    return ProcessEvidence(
        pid=pid,
        exists=exists,
        observed_start_token=observed_start_token,
        observed_boot_id=observed_boot_id,
        probe_error_code=probe_error_code,
    )


def test_missing_owner_is_inconclusive() -> None:
    """缺 owner_host_instance_id 时不能证明 orphan。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        DurableOrphanCandidate(owner_host_instance_id=None, owner_liveness=None),
        None,
        _policy(),
    )
    assert isinstance(result, OrphanProofInconclusive)
    assert result.reason == "missing_owner_host_instance_id"


def test_missing_liveness_row_is_inconclusive() -> None:
    """缺 owner liveness row 时不能证明 orphan。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(_candidate(None), None, _policy())
    assert isinstance(result, OrphanProofInconclusive)
    assert result.reason == "missing_owner_liveness_row"


def test_recent_heartbeat_owner_is_still_live_without_process_probe() -> None:
    """heartbeat 未 stale 时 owner 仍视为 live，不要求进程证据。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        _candidate(_row(heartbeat_age_seconds=5)),
        None,
        _policy(),
    )
    assert isinstance(result, OwnerStillLive)
    assert result.reason == "owner_heartbeat_recent"


def test_stale_heartbeat_alone_is_not_positive_orphan_proof() -> None:
    """heartbeat stale 但缺进程证据时不能证明 orphan。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        _candidate(_row(heartbeat_age_seconds=60)),
        None,
        _policy(),
    )
    assert isinstance(result, OrphanProofInconclusive)
    assert result.reason == "owner_pid_live_without_identity_proof"


def test_stale_owner_with_missing_pid_is_positive_orphan_proof() -> None:
    """heartbeat stale 且 pid 不存在时产出 positive orphan proof。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        _candidate(_row(heartbeat_age_seconds=60)),
        _evidence(exists=False),
        _policy(),
    )
    assert isinstance(result, PositiveOrphanProof)
    assert result.reason == "owner_pid_missing"


def test_live_pid_without_identity_capability_is_inconclusive() -> None:
    """pid 存在但缺启动指纹能力时不能误判 orphan。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        _candidate(_row(heartbeat_age_seconds=60)),
        _evidence(exists=True),
        _policy(),
    )
    assert isinstance(result, OrphanProofInconclusive)
    assert result.reason == "owner_pid_live_without_identity_proof"


def test_live_pid_with_matching_identity_is_still_live() -> None:
    """pid 存在且启动指纹匹配时 owner 仍视为 live。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        _candidate(_row(heartbeat_age_seconds=60)),
        _evidence(exists=True, observed_start_token="token-owner"),
        _policy(),
    )
    assert isinstance(result, OwnerStillLive)
    assert result.reason == "owner_process_identity_matched"


def test_pid_reused_start_token_mismatch_is_positive_orphan_proof() -> None:
    """pid 复用且启动指纹不匹配时产出 positive orphan proof。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        _candidate(_row(heartbeat_age_seconds=60)),
        _evidence(exists=True, observed_start_token="token-new-owner"),
        _policy(),
    )
    assert isinstance(result, PositiveOrphanProof)
    assert result.reason == "owner_pid_reused_start_token_mismatch"


def test_pid_reused_boot_id_mismatch_is_positive_orphan_proof() -> None:
    """pid 复用且 boot id 不匹配时产出 positive orphan proof。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        _candidate(_row(heartbeat_age_seconds=60)),
        _evidence(exists=True, observed_boot_id="boot-new-owner"),
        _policy(),
    )
    assert isinstance(result, PositiveOrphanProof)
    assert result.reason == "owner_pid_reused_boot_id_mismatch"


def test_probe_error_is_inconclusive() -> None:
    """进程探测错误不能作为 positive orphan proof。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    result = classify_orphan_candidate(
        _candidate(_row(heartbeat_age_seconds=60)),
        _evidence(exists=True, probe_error_code="permission_denied"),
        _policy(),
    )
    assert isinstance(result, OrphanProofInconclusive)
    assert result.reason == "process_probe_error"
    assert result.probe_error_code == "permission_denied"


def test_stdlib_pid_probe_reports_current_process_exists() -> None:
    """stdlib pid probe 能证明当前进程 pid 存在。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    evidence = StdlibPidLivenessProbe().collect(os.getpid())
    assert evidence.pid == os.getpid()
    assert evidence.exists is True
    assert evidence.observed_start_token is None


def test_stdlib_pid_probe_rejects_invalid_pid() -> None:
    """stdlib pid probe 拒绝非正 pid。

    :returns: ``None``。
    :raises AssertionError: 回归断言失败时由 pytest 抛出。
    """

    with pytest.raises(ValueError):
        StdlibPidLivenessProbe().collect(0)
