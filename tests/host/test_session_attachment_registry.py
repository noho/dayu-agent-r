"""Host Session attachment registry 的 owner-contract 测试。

本模块只验证 Slice 1 internal contract：canonical key、唯一 live record、
不可变 mode、RECOVERING / ACTIVE / CLOSING / CLOSED 生命周期、mutation /
new-work lease、caller cancellation 下的共享 close cleanup，以及 Host close 的
batch mark / drain / release 顺序；不接入 public Host Protocol 或 scheduler。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Literal, cast

import pytest

import dayu.host as host_package
import dayu.host.session_attachment as session_attachment_module
from dayu.host.api import (
    HostApiError,
    HostApiErrorCode,
    HostClosedError,
    HostSessionAccessMode,
    HostSessionAttachmentConflictDetail,
    HostSessionAttachmentConflictReason,
    HostSessionMutationErrorDetail,
    HostSessionMutationRejectionReason,
)
from dayu.host.session_attachment import (
    HostSessionAttachmentRegistry,
    SessionNewWorkAccessPort,
    SessionWorkLease,
)
from dayu.runtime.native_mutex import StrictNativeMutexUnavailableError


def _create_db(tmp_path: Path, *, name: str = "host.sqlite3") -> Path:
    """创建 registry 所需的已存在 durable store 文件。

    :param tmp_path: pytest 临时目录。
    :param name: SQLite 文件名。
    :returns: 已创建文件路径。
    :raises OSError: 文件创建失败时抛出。
    """

    db_path = tmp_path / name
    db_path.touch()
    return db_path


def _activate_attachment(
    registry: HostSessionAttachmentRegistry,
    session_id: str,
) -> session_attachment_module._HostSessionAttachmentImpl:
    """分配并激活一个无需 target recovery 的测试 attachment。

    :param registry: attachment registry。
    :param session_id: 目标 Session id。
    :returns: 已 ACTIVE 的内部 attachment 实现。
    :raises HostApiError: 同 registry 已有 live record 时抛出。
    :raises StrictNativeMutexUnavailableError: native mutex 不可用时抛出。
    """

    allocation = registry.begin_attachment(session_id)
    return allocation.activate()


async def _probe_mode(db_path: Path, session_id: str) -> HostSessionAccessMode:
    """用独立 registry fresh attach 一次并立即关闭。

    :param db_path: 已存在 SQLite 路径。
    :param session_id: 目标 Session id。
    :returns: fresh attach 得到的 mode。
    :raises HostApiError: registry contract 冲突时抛出。
    :raises StrictNativeMutexUnavailableError: native mutex 不可用时抛出。
    """

    registry = HostSessionAttachmentRegistry(db_path)
    attachment = _activate_attachment(registry, session_id)
    mode = attachment.access_mode
    await attachment.aclose()
    return mode


def _assert_conflict(error: HostApiError, session_id: str) -> None:
    """断言 duplicate attachment 使用精确 typed conflict。

    :param error: 捕获到的 Host API 错误。
    :param session_id: 预期 Session id。
    :returns: ``None``。
    :raises AssertionError: 错误 code、retryable 或 detail 不匹配时抛出。
    """

    assert error.code is HostApiErrorCode.CONFLICT
    assert error.retryable is False
    assert error.detail == HostSessionAttachmentConflictDetail(
        kind="session_attachment_conflict",
        session_id=session_id,
        reason=HostSessionAttachmentConflictReason.ALREADY_ATTACHED,
    )


def _assert_mutation_rejection(
    error: HostApiError,
    *,
    session_id: str,
    reason: HostSessionMutationRejectionReason,
    actual_mode: HostSessionAccessMode | None,
) -> None:
    """断言 mutation gate 使用精确 permission detail。

    :param error: 捕获到的 Host API 错误。
    :param session_id: 预期 Session id。
    :param reason: 预期拒绝原因。
    :param actual_mode: 预期 attachment mode；无 active mode 时为 ``None``。
    :returns: ``None``。
    :raises AssertionError: 错误 contract 不匹配时抛出。
    """

    assert error.code is HostApiErrorCode.PERMISSION_DENIED
    assert error.retryable is False
    assert error.detail == HostSessionMutationErrorDetail(
        kind="session_mutation_access",
        session_id=session_id,
        reason=reason,
        required_mode=HostSessionAccessMode.READ_WRITE,
        actual_mode=actual_mode,
    )


def _raise_native_unavailable(path: Path) -> None:
    """模拟 native mutex backend unavailable。

    :param path: 已派生的 mutex path。
    :returns: 不会正常返回。
    :raises StrictNativeMutexUnavailableError: 始终抛出。
    """

    del path
    raise StrictNativeMutexUnavailableError("native unavailable")


async def _wait_for_event(event: asyncio.Event) -> None:
    """等待测试事件，用作底层 work task。

    :param event: 控制 task 完成的事件。
    :returns: ``None``。
    :raises asyncio.CancelledError: task 被取消时抛出。
    """

    await event.wait()


def test_canonical_mutex_path_uses_resolved_store_and_hashed_session(
    tmp_path: Path,
) -> None:
    """Host 必须从 canonical DB identity 与 Session id 派生 opaque key。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: path 未 canonicalize 或泄漏 raw Session id 时抛出。
    """

    db_path = _create_db(tmp_path)
    session_id = "session/raw-sensitive-id"
    resolved = db_path.resolve(strict=True)
    identity = os.path.normcase(str(resolved))
    expected_name = hashlib.sha256(f"{identity}\0{session_id}".encode("utf-8")).hexdigest()

    mutex_path = session_attachment_module._derive_session_mutex_path(
        db_path,
        session_id,
    )

    assert mutex_path.parent.parent == resolved.parent
    assert mutex_path.name == expected_name
    assert session_id not in str(mutex_path)


def test_registry_rejects_missing_db_and_empty_session(tmp_path: Path) -> None:
    """canonical owner 必须拒绝不存在 DB 与空 Session id。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 非法 owner key 被接受时抛出。
    """

    with pytest.raises(ValueError, match="必须存在"):
        HostSessionAttachmentRegistry(tmp_path / "missing.sqlite3")

    registry = HostSessionAttachmentRegistry(_create_db(tmp_path))
    with pytest.raises(ValueError, match="session_id"):
        registry.begin_attachment(" ")


@pytest.mark.asyncio
async def test_duplicate_rw_attachment_conflicts_before_native_acquire(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RW live record 的 duplicate attach 必须在 native probe 前冲突。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: duplicate attach 触发 native acquire 时抛出。
    """

    registry = HostSessionAttachmentRegistry(_create_db(tmp_path))
    attachment = _activate_attachment(registry, "session-1")
    assert attachment.access_mode is HostSessionAccessMode.READ_WRITE
    monkeypatch.setattr(
        session_attachment_module,
        "try_acquire_strict_native_mutex",
        _raise_native_unavailable,
    )

    with pytest.raises(HostApiError) as exc_info:
        registry.begin_attachment("session-1")
    _assert_conflict(exc_info.value, "session-1")
    await attachment.aclose()


@pytest.mark.asyncio
async def test_duplicate_ro_attachment_conflicts_before_native_acquire(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RO live record 的 duplicate attach 也必须在 native probe 前冲突。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: duplicate RO 创建第二个 record 时抛出。
    """

    db_path = _create_db(tmp_path)
    owner_registry = HostSessionAttachmentRegistry(db_path)
    owner = _activate_attachment(owner_registry, "session-1")
    observer_registry = HostSessionAttachmentRegistry(db_path)
    observer = _activate_attachment(observer_registry, "session-1")
    assert observer.access_mode is HostSessionAccessMode.READ_ONLY
    monkeypatch.setattr(
        session_attachment_module,
        "try_acquire_strict_native_mutex",
        _raise_native_unavailable,
    )

    with pytest.raises(HostApiError) as exc_info:
        observer_registry.begin_attachment("session-1")
    _assert_conflict(exc_info.value, "session-1")
    await observer.aclose()
    await owner.aclose()


@pytest.mark.asyncio
async def test_different_sessions_are_independent_and_ro_never_upgrades(
    tmp_path: Path,
) -> None:
    """不同 Session 可同时 RW，既有 RO 在 owner release 后保持不变。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: key 隔离或 immutable mode 不成立时抛出。
    """

    db_path = _create_db(tmp_path)
    owner_registry = HostSessionAttachmentRegistry(db_path)
    session_one_owner = _activate_attachment(owner_registry, "session-1")
    session_two_owner = _activate_attachment(owner_registry, "session-2")
    assert session_one_owner.access_mode is HostSessionAccessMode.READ_WRITE
    assert session_two_owner.access_mode is HostSessionAccessMode.READ_WRITE

    observer_registry = HostSessionAttachmentRegistry(db_path)
    observer = _activate_attachment(observer_registry, "session-1")
    assert observer.access_mode is HostSessionAccessMode.READ_ONLY
    await session_one_owner.aclose()
    assert observer.access_mode is HostSessionAccessMode.READ_ONLY

    await observer.aclose()
    fresh = _activate_attachment(observer_registry, "session-1")
    assert fresh.access_mode is HostSessionAccessMode.READ_WRITE
    await fresh.aclose()
    await session_two_owner.aclose()


@pytest.mark.asyncio
async def test_recovering_record_only_allows_allocation_recovery_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RECOVERING RW 只在 root recovery lease 存续时允许嵌套 work。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: RECOVERING gate 被绕过时抛出。
    """

    registry = HostSessionAttachmentRegistry(_create_db(tmp_path))
    allocation = registry.begin_attachment("session-1")
    assert allocation.access_mode is HostSessionAccessMode.READ_WRITE
    assert registry.try_acquire_new_work_lease("session-1") is None
    monkeypatch.setattr(
        session_attachment_module,
        "try_acquire_strict_native_mutex",
        _raise_native_unavailable,
    )
    with pytest.raises(HostApiError) as conflict_error:
        registry.begin_attachment("session-1")
    _assert_conflict(conflict_error.value, "session-1")
    with pytest.raises(HostApiError) as exc_info:
        registry.acquire_mutation_lease("session-1")
    _assert_mutation_rejection(
        exc_info.value,
        session_id="session-1",
        reason=HostSessionMutationRejectionReason.ATTACHMENT_REQUIRED,
        actual_mode=None,
    )

    recovery_lease = allocation.acquire_recovery_work_lease()
    assert isinstance(recovery_lease, SessionWorkLease)
    nested_lease = registry.try_acquire_new_work_lease("session-1")
    assert isinstance(nested_lease, SessionWorkLease)
    nested_lease.release()
    with pytest.raises(RuntimeError, match="recovery work"):
        allocation.activate()
    recovery_lease.release()
    assert registry.try_acquire_new_work_lease("session-1") is None
    attachment = allocation.activate()
    assert attachment.access_mode is HostSessionAccessMode.READ_WRITE
    await attachment.aclose()


@pytest.mark.asyncio
async def test_mutation_and_work_leases_bind_underlying_future_and_task(
    tmp_path: Path,
) -> None:
    """close 必须等待绑定底层 Future/task 的 mutation 与 work lease。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 任一 lease 未阻止 mutex 提前释放时抛出。
    """

    db_path = _create_db(tmp_path)
    registry = HostSessionAttachmentRegistry(db_path)
    attachment = _activate_attachment(registry, "session-1")
    mutation_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    work_event = asyncio.Event()
    work_task = asyncio.create_task(_wait_for_event(work_event))

    mutation_lease = registry.acquire_mutation_lease("session-1")
    mutation_lease.release_when_done(mutation_future)
    work_lease = registry.try_acquire_new_work_lease("session-1")
    assert isinstance(work_lease, SessionWorkLease)
    work_lease.release_when_done(work_task)

    close_task = asyncio.create_task(attachment.aclose())
    await asyncio.sleep(0)
    assert close_task.done() is False
    assert await _probe_mode(db_path, "session-1") is HostSessionAccessMode.READ_ONLY

    mutation_future.set_result(None)
    await asyncio.sleep(0)
    assert close_task.done() is False
    assert await _probe_mode(db_path, "session-1") is HostSessionAccessMode.READ_ONLY

    work_event.set()
    await close_task
    assert await _probe_mode(db_path, "session-1") is HostSessionAccessMode.READ_WRITE


@pytest.mark.asyncio
async def test_cancelled_recovering_allocation_close_does_not_cancel_cleanup(
    tmp_path: Path,
) -> None:
    """attach caller 取消 RECOVERING cleanup 等待后，底层 cleanup 必须继续。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: caller cancellation 泄漏或提前释放 mutex 时抛出。
    """

    db_path = _create_db(tmp_path)
    registry = HostSessionAttachmentRegistry(db_path)
    allocation = registry.begin_attachment("session-1")
    future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    lease = allocation.acquire_recovery_work_lease()
    lease.release_when_done(future)

    cancelled_waiter = asyncio.create_task(allocation.aclose())
    await asyncio.sleep(0)
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter
    assert await _probe_mode(db_path, "session-1") is HostSessionAccessMode.READ_ONLY

    future.set_result(None)
    await allocation.aclose()
    assert await _probe_mode(db_path, "session-1") is HostSessionAccessMode.READ_WRITE


@pytest.mark.asyncio
async def test_concurrent_and_repeated_close_share_one_cleanup(
    tmp_path: Path,
) -> None:
    """attachment/allocation 的并发与重复 close 必须幂等共享 cleanup。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: close race 泄漏 record 或 mutex 时抛出。
    """

    db_path = _create_db(tmp_path)
    registry = HostSessionAttachmentRegistry(db_path)
    allocation = registry.begin_attachment("session-1")
    attachment = allocation.activate()

    await asyncio.gather(
        attachment.aclose(),
        attachment.aclose(),
        allocation.aclose(),
    )
    await attachment.aclose()
    fresh = _activate_attachment(registry, "session-1")
    assert fresh.access_mode is HostSessionAccessMode.READ_WRITE
    await fresh.aclose()


@pytest.mark.asyncio
async def test_closing_and_missing_mutation_rejections_are_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """missing、RO 与 CLOSING mutation gate 必须提供精确 typed reason。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: mutation rejection detail 不精确时抛出。
    """

    db_path = _create_db(tmp_path)
    registry = HostSessionAttachmentRegistry(db_path)
    with pytest.raises(HostApiError) as missing_error:
        registry.acquire_mutation_lease("missing-session")
    _assert_mutation_rejection(
        missing_error.value,
        session_id="missing-session",
        reason=HostSessionMutationRejectionReason.ATTACHMENT_REQUIRED,
        actual_mode=None,
    )

    owner_registry = HostSessionAttachmentRegistry(db_path)
    owner = _activate_attachment(owner_registry, "read-only-session")
    read_only = _activate_attachment(registry, "read-only-session")
    with pytest.raises(HostApiError) as read_only_error:
        registry.acquire_mutation_lease("read-only-session")
    _assert_mutation_rejection(
        read_only_error.value,
        session_id="read-only-session",
        reason=HostSessionMutationRejectionReason.READ_ONLY,
        actual_mode=HostSessionAccessMode.READ_ONLY,
    )

    writable = _activate_attachment(registry, "closing-session")
    lease = registry.acquire_mutation_lease("closing-session")
    close_task = asyncio.create_task(writable.aclose())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    monkeypatch.setattr(
        session_attachment_module,
        "try_acquire_strict_native_mutex",
        _raise_native_unavailable,
    )
    with pytest.raises(HostApiError) as conflict_error:
        registry.begin_attachment("closing-session")
    _assert_conflict(conflict_error.value, "closing-session")
    with pytest.raises(HostApiError) as closing_error:
        registry.acquire_mutation_lease("closing-session")
    _assert_mutation_rejection(
        closing_error.value,
        session_id="closing-session",
        reason=HostSessionMutationRejectionReason.ATTACHMENT_CLOSING,
        actual_mode=HostSessionAccessMode.READ_WRITE,
    )

    lease.release()
    await close_task
    await read_only.aclose()
    await owner.aclose()


@pytest.mark.asyncio
async def test_host_close_batch_drains_before_explicit_release(
    tmp_path: Path,
) -> None:
    """Host close 必须 batch mark/drain，并在显式 barrier 后才 release mutex。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Host close 顺序或多 Session batch 不变量失效时抛出。
    """

    db_path = _create_db(tmp_path)
    registry = HostSessionAttachmentRegistry(db_path)
    first = _activate_attachment(registry, "session-1")
    second = _activate_attachment(registry, "session-2")
    mutation_lease = registry.acquire_mutation_lease("session-1")
    work_lease = registry.try_acquire_new_work_lease("session-2")
    assert isinstance(work_lease, SessionWorkLease)

    registry.begin_host_close()
    with pytest.raises(HostClosedError):
        registry.begin_attachment("session-3")
    with pytest.raises(RuntimeError, match="drain"):
        await registry.release_host_close()

    drain_task = asyncio.create_task(registry.drain_host_close())
    await asyncio.sleep(0)
    assert drain_task.done() is False
    assert await _probe_mode(db_path, "session-1") is HostSessionAccessMode.READ_ONLY
    assert await _probe_mode(db_path, "session-2") is HostSessionAccessMode.READ_ONLY

    mutation_lease.release()
    work_lease.release()
    await drain_task
    assert await _probe_mode(db_path, "session-1") is HostSessionAccessMode.READ_ONLY
    assert await _probe_mode(db_path, "session-2") is HostSessionAccessMode.READ_ONLY

    await registry.release_host_close()
    await registry.release_host_close()
    assert await _probe_mode(db_path, "session-1") is HostSessionAccessMode.READ_WRITE
    assert await _probe_mode(db_path, "session-2") is HostSessionAccessMode.READ_WRITE
    await first.aclose()
    await second.aclose()


@pytest.mark.asyncio
async def test_registry_satisfies_narrow_new_work_access_port(tmp_path: Path) -> None:
    """registry 必须结构化满足 scheduler 所需窄只读 access port。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: ACTIVE RW snapshot 或 lease contract 不成立时抛出。
    """

    registry = HostSessionAttachmentRegistry(_create_db(tmp_path))
    port: SessionNewWorkAccessPort = registry
    allocation = registry.begin_attachment("session-1")
    assert port.active_read_write_session_ids() == ()
    attachment = allocation.activate()
    assert port.active_read_write_session_ids() == ("session-1",)
    lease = port.try_acquire_new_work_lease("session-1")
    assert isinstance(lease, SessionWorkLease)
    lease.release()
    assert attachment.access_mode is HostSessionAccessMode.READ_WRITE
    await attachment.aclose()


@pytest.mark.asyncio
async def test_native_acquire_failure_does_not_leave_live_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """native acquire unavailable 时 registry 不得留下 pending record。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: failure 后 fresh attach 被伪 conflict 阻断时抛出。
    """

    registry = HostSessionAttachmentRegistry(_create_db(tmp_path))
    monkeypatch.setattr(
        session_attachment_module,
        "try_acquire_strict_native_mutex",
        _raise_native_unavailable,
    )
    with pytest.raises(StrictNativeMutexUnavailableError):
        registry.begin_attachment("session-1")
    monkeypatch.undo()
    allocation = registry.begin_attachment("session-1")
    assert allocation.access_mode is HostSessionAccessMode.READ_WRITE
    await allocation.aclose()


def test_new_api_value_types_validate_closed_contracts() -> None:
    """新增 mode/error value types 必须校验 kind、枚举与必填字段。

    :returns: ``None``。
    :raises AssertionError: value type 接受非法 contract 时抛出。
    """

    mutation = HostSessionMutationErrorDetail(
        kind="session_mutation_access",
        session_id="session-1",
        reason=HostSessionMutationRejectionReason.READ_ONLY,
        required_mode=HostSessionAccessMode.READ_WRITE,
        actual_mode=HostSessionAccessMode.READ_ONLY,
    )
    conflict = HostSessionAttachmentConflictDetail(
        kind="session_attachment_conflict",
        session_id="session-1",
        reason=HostSessionAttachmentConflictReason.ALREADY_ATTACHED,
    )
    assert mutation.actual_mode is HostSessionAccessMode.READ_ONLY
    assert conflict.reason is HostSessionAttachmentConflictReason.ALREADY_ATTACHED

    with pytest.raises(ValueError, match="kind"):
        HostSessionMutationErrorDetail(
            kind=cast(Literal["session_mutation_access"], "wrong"),
            session_id="session-1",
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            required_mode=HostSessionAccessMode.READ_WRITE,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )
    with pytest.raises(ValueError, match="session_id"):
        HostSessionMutationErrorDetail(
            kind="session_mutation_access",
            session_id=" ",
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            required_mode=HostSessionAccessMode.READ_WRITE,
            actual_mode=HostSessionAccessMode.READ_ONLY,
        )
    with pytest.raises(ValueError, match="kind"):
        HostSessionAttachmentConflictDetail(
            kind=cast(Literal["session_attachment_conflict"], "wrong"),
            session_id="session-1",
            reason=HostSessionAttachmentConflictReason.ALREADY_ATTACHED,
        )
    with pytest.raises(ValueError, match="session_id"):
        HostSessionAttachmentConflictDetail(
            kind="session_attachment_conflict",
            session_id=" ",
            reason=HostSessionAttachmentConflictReason.ALREADY_ATTACHED,
        )
    with pytest.raises(TypeError, match="reason"):
        HostSessionAttachmentConflictDetail(
            kind="session_attachment_conflict",
            session_id="session-1",
            reason=cast(HostSessionAttachmentConflictReason, "wrong"),
        )
    with pytest.raises(TypeError, match="reason"):
        HostSessionMutationErrorDetail(
            kind="session_mutation_access",
            session_id="session-1",
            reason=cast(HostSessionMutationRejectionReason, "wrong"),
            required_mode=HostSessionAccessMode.READ_WRITE,
            actual_mode=None,
        )
    with pytest.raises(TypeError, match="required_mode"):
        HostSessionMutationErrorDetail(
            kind="session_mutation_access",
            session_id="session-1",
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            required_mode=cast(HostSessionAccessMode, "wrong"),
            actual_mode=None,
        )
    with pytest.raises(TypeError, match="actual_mode"):
        HostSessionMutationErrorDetail(
            kind="session_mutation_access",
            session_id="session-1",
            reason=HostSessionMutationRejectionReason.READ_ONLY,
            required_mode=HostSessionAccessMode.READ_WRITE,
            actual_mode=cast(HostSessionAccessMode, "wrong"),
        )


def test_slice_two_exports_only_public_attachment_contract_from_package_root() -> None:
    """Slice 2 从 ``dayu.host`` 包根公开 attachment value contract。

    :returns: ``None``。
    :raises AssertionError: public value type 缺失或 internal owner 被导出时抛出。
    """

    public_contract = {
        "HostSessionAccessMode",
        "HostSessionAttachment",
        "HostSessionAttachmentConflictDetail",
        "HostSessionAttachmentConflictReason",
        "HostSessionMutationErrorDetail",
        "HostSessionMutationRejectionReason",
    }
    internal_contract = {
        "HostSessionAttachmentRegistry",
        "SessionNewWorkAccessPort",
        "SessionWorkLease",
    }
    assert public_contract.issubset(host_package.__all__)
    assert public_contract.issubset(vars(host_package))
    assert internal_contract.isdisjoint(host_package.__all__)
    assert internal_contract.isdisjoint(vars(host_package))
