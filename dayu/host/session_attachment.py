"""Host 内部 Session attachment access owner 与生命周期 registry。

本模块拥有单个 Host opener 内的 attachment mode、live record、mutation /
new-work lease 和 close 顺序。跨 opener 的机械互斥委托给层中立
``dayu.runtime.native_mutex``；mutex availability 不表达 Run / Attempt durable
truth。Slice 1 仅建立 internal contract，不接入 public Host Protocol、scheduler
或 recovery production call path。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TypeVar

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
from dayu.runtime.native_mutex import (
    StrictNativeMutexHandle,
    StrictNativeMutexUnavailableError,
    try_acquire_strict_native_mutex,
)

T = TypeVar("T")

_SESSION_MUTEX_DIRECTORY_NAME = ".dayu-session-mutex"
_MUTATION_REQUIRED_MESSAGE = "Session mutation requires an active read-write attachment"
_MUTATION_READ_ONLY_MESSAGE = "Session attachment is read-only"
_MUTATION_CLOSING_MESSAGE = "Session attachment is closing"
_ATTACHMENT_CONFLICT_MESSAGE = "Session already has a live attachment for this Host handle"


class _AttachmentLifecycleState(StrEnum):
    """单个 attachment record 的封闭 lifecycle 状态。"""

    RECOVERING = "recovering"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"


class _SessionLeaseKind(StrEnum):
    """registry 分别 drain 的 Session lease 类别。"""

    MUTATION = "mutation"
    NEW_WORK = "new_work"


class _AttachmentRecord:
    """registry 内单个 Session live attachment 的状态记录。

    :param session_id: 当前 record 的 Session id。
    :param access_mode: attachment 生命周期内冻结的 mode。
    :param state: 初始 lifecycle 状态。
    :param mutex_handle: RW 持有的 native handle；RO 为 ``None``。
    """

    __slots__ = (
        "access_mode",
        "close_completed",
        "close_error",
        "close_task",
        "mutex_handle",
        "mutation_drained",
        "mutation_lease_count",
        "new_work_drained",
        "new_work_lease_count",
        "session_id",
        "state",
    )

    def __init__(
        self,
        *,
        session_id: str,
        access_mode: HostSessionAccessMode,
        state: _AttachmentLifecycleState,
        mutex_handle: StrictNativeMutexHandle | None,
    ) -> None:
        """初始化 attachment record 与零计数 drain events。

        :param session_id: 当前 record 的 Session id。
        :param access_mode: 生命周期内冻结的 mode。
        :param state: 初始 lifecycle 状态。
        :param mutex_handle: RW native handle；RO 为 ``None``。
        :returns: ``None``。
        :raises ValueError: Session id 为空时抛出。
        """

        _require_session_id(session_id)
        self.session_id = session_id
        self.access_mode = access_mode
        self.state = state
        self.mutex_handle = mutex_handle
        self.mutation_lease_count = 0
        self.new_work_lease_count = 0
        self.mutation_drained = asyncio.Event()
        self.mutation_drained.set()
        self.new_work_drained = asyncio.Event()
        self.new_work_drained.set()
        self.close_completed = asyncio.Event()
        self.close_error: StrictNativeMutexUnavailableError | None = None
        self.close_task: asyncio.Task[None] | None = None


class SessionWorkLease:
    """绑定单个 attachment mutation 或 pre-start work 的计数 lease。

    lease 只能由创建它的 registry 释放；``release()`` 幂等。
    ``release_when_done()`` 把资源生命周期绑定到底层 Future/task 的真实完成，
    不绑定 caller awaiter。

    :param registry: 创建并拥有本 lease 的 registry。
    :param record: lease 所属 live attachment record。
    :param kind: mutation 或 new-work 计数类别。
    """

    __slots__ = ("_kind", "_record", "_registry", "_released")

    def __init__(
        self,
        *,
        registry: "HostSessionAttachmentRegistry",
        record: _AttachmentRecord,
        kind: _SessionLeaseKind,
    ) -> None:
        """初始化一次性 Session work lease。

        :param registry: 创建并拥有本 lease 的 registry。
        :param record: lease 所属 live attachment record。
        :param kind: mutation 或 new-work 计数类别。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._registry = registry
        self._record = record
        self._kind = kind
        self._released = False

    def release(self) -> None:
        """幂等释放 registry lease 计数。

        :returns: ``None``。
        :raises RuntimeError: registry 内部计数不变量已损坏时抛出。
        """

        if self._released:
            return
        self._released = True
        self._registry._release_lease(self._record, self._kind)

    def release_when_done(self, future: asyncio.Future[T]) -> None:
        """在底层 Future/task 收口后释放 lease。

        :param future: 已提交的底层 actor Future 或 pre-start task。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        future.add_done_callback(self._release_after_future)

    def _release_after_future(self, future: asyncio.Future[T]) -> None:
        """观察底层 Future 终态并释放 lease。

        :param future: 已完成的底层 Future/task。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if not future.cancelled():
            # 读取 exception 只消除无人 await 时的警告，不改变其他 awaiter。
            future.exception()
        self.release()


class SessionNewWorkAccessPort(Protocol):
    """scheduler 消费 attachment access truth 的窄只读协议。"""

    def try_acquire_new_work_lease(
        self,
        session_id: str,
    ) -> SessionWorkLease | None:
        """尝试为 ACTIVE RW Session 获取 pre-start/new-work lease。

        :param session_id: 目标 Session id。
        :returns: 有资格时返回 lease，否则返回 ``None``。
        :raises ValueError: Session id 为空时抛出。
        """

        ...

    def active_read_write_session_ids(self) -> tuple[str, ...]:
        """返回当前 ACTIVE RW Session id 的稳定排序快照。

        :returns: 排序后的 Session id 元组。
        :raises Exception: 不主动抛出异常。
        """

        ...


class _HostSessionAttachmentImpl:
    """Host public attachment Protocol 的内部资源实现。

    Slice 1 不把本类型加入 public Protocol 或包根导出；它只冻结只读
    ``session_id`` / ``access_mode`` 与 cancellation-safe ``aclose`` 语义。

    :param registry: 拥有 record 的 registry。
    :param record: attachment 对应的唯一 live record。
    """

    __slots__ = ("_record", "_registry")

    def __init__(
        self,
        *,
        registry: "HostSessionAttachmentRegistry",
        record: _AttachmentRecord,
    ) -> None:
        """初始化内部 attachment resource。

        :param registry: 拥有 record 的 registry。
        :param record: attachment 对应的唯一 live record。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._registry = registry
        self._record = record

    @property
    def session_id(self) -> str:
        """返回 attachment 的稳定 Session id。

        :returns: Session id。
        :raises Exception: 不主动抛出异常。
        """

        return self._record.session_id

    @property
    def access_mode(self) -> HostSessionAccessMode:
        """返回 attachment 构造时冻结的访问模式。

        :returns: ``READ_WRITE`` 或 ``READ_ONLY``。
        :raises Exception: 不主动抛出异常。
        """

        return self._record.access_mode

    async def aclose(self) -> None:
        """关闭 attachment；并发/重复调用共享同一 cleanup task。

        caller cancellation 只取消本次等待，后台 cleanup 继续运行并可由后续
        ``aclose`` 或 Host close join。

        :returns: ``None``。
        :raises asyncio.CancelledError: 当前 caller 等待被取消时抛出。
        :raises StrictNativeMutexUnavailableError: native mutex release 失败时抛出。
        """

        await self._registry._close_attachment(self._record)


class _AttachmentAllocation:
    """attach factory 在 successful return 前持有的短生命周期资源 token。

    RW allocation 初始为 RECOVERING，只有 target recovery work 已收口后才可
    ``activate``；RO allocation 初始已是 ACTIVE。失败或 caller cancellation
    路径通过 ``aclose`` 复用同一 drain/cleanup 真源。

    :param registry: 创建 allocation 的 registry。
    :param record: 本次分配已经登记的唯一 live record。
    """

    __slots__ = ("_activated", "_attachment", "_record", "_registry")

    def __init__(
        self,
        *,
        registry: "HostSessionAttachmentRegistry",
        record: _AttachmentRecord,
    ) -> None:
        """初始化 attachment allocation token。

        :param registry: 创建 allocation 的 registry。
        :param record: 已进入 live index 的 record。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._registry = registry
        self._record = record
        self._attachment = _HostSessionAttachmentImpl(
            registry=registry,
            record=record,
        )
        self._activated = False

    @property
    def access_mode(self) -> HostSessionAccessMode:
        """返回本次 allocation 冻结的访问模式。

        :returns: ``READ_WRITE`` 或 ``READ_ONLY``。
        :raises Exception: 不主动抛出异常。
        """

        return self._record.access_mode

    def acquire_recovery_work_lease(self) -> SessionWorkLease:
        """为当前 RECOVERING RW allocation 获取 target recovery work lease。

        :returns: 绑定本次 target recovery/pre-start work 的 lease。
        :raises RuntimeError: allocation 不是当前 live RECOVERING RW record 时抛出。
        """

        return self._registry._acquire_recovery_work_lease(self._record)

    def activate(self) -> _HostSessionAttachmentImpl:
        """完成 allocation 并返回 ACTIVE attachment。

        :returns: 当前 allocation 唯一的内部 attachment 实现。
        :raises RuntimeError: allocation 已 activate、已 closing/closed，或 RW
            recovery work 尚未收口时抛出。
        """

        if self._activated:
            raise RuntimeError("attachment allocation 已经 activate")
        self._registry._activate_allocation(self._record)
        self._activated = True
        return self._attachment

    async def aclose(self) -> None:
        """关闭 allocation 已持有的 record 与 native resource。

        :returns: ``None``。
        :raises asyncio.CancelledError: 当前 caller 等待被取消时抛出。
        :raises StrictNativeMutexUnavailableError: native mutex release 失败时抛出。
        """

        await self._registry._close_attachment(self._record)


class HostSessionAttachmentRegistry:
    """单个 Host opener 的 Session attachment access 唯一 owner。

    registry 只允许在 opener event loop 内使用。构造时接收已经打开且存在的
    SQLite 路径，并在 Host boundary 派生 canonical store identity 与 opaque
    per-Session mutex path；runtime primitive 永远只接收最终 ``Path``。

    :param db_path: 已存在的真实 Host SQLite 文件路径。
    """

    __slots__ = (
        "_canonical_store_identity",
        "_host_close_drained",
        "_host_close_released",
        "_host_closing",
        "_mutex_directory",
        "_records",
        "_resolved_db_path",
    )

    def __init__(self, db_path: Path) -> None:
        """初始化 registry 与 canonical durable-store identity。

        :param db_path: 已存在的 Host SQLite 文件路径。
        :returns: ``None``。
        :raises ValueError: 路径不存在或不是普通文件时抛出。
        """

        resolved_db_path = _resolve_existing_db_path(db_path)
        self._resolved_db_path = resolved_db_path
        self._canonical_store_identity = os.path.normcase(str(resolved_db_path))
        self._mutex_directory = resolved_db_path.parent / _SESSION_MUTEX_DIRECTORY_NAME
        self._records: dict[str, _AttachmentRecord] = {}
        self._host_closing = False
        self._host_close_drained = False
        self._host_close_released = False

    def begin_attachment(self, session_id: str) -> _AttachmentAllocation:
        """原子 preflight 并分配一个 internal attachment record。

        duplicate live record 检查严格先于 mutex path 准备和 native acquire。
        native acquire 成功产生 RECOVERING RW；明确 busy 产生 ACTIVE RO。

        :param session_id: 已由 durable read 验证存在的 Session id。
        :returns: attach factory 短生命周期 allocation token。
        :raises ValueError: Session id 为空时抛出。
        :raises HostApiError: 同 registry/Session 已有 live record 时抛出。
        :raises HostClosedError: registry 已进入 Host close 时抛出。
        :raises StrictNativeMutexUnavailableError: mutex directory 或 native backend
            不可用时抛出。
        """

        _require_session_id(session_id)
        if session_id in self._records:
            raise _attachment_conflict_error(session_id)
        if self._host_closing:
            raise HostClosedError("Host attachment registry is closing")

        self._prepare_mutex_directory()
        mutex_path = _derive_mutex_path_from_identity(
            mutex_directory=self._mutex_directory,
            canonical_store_identity=self._canonical_store_identity,
            session_id=session_id,
        )
        mutex_handle = try_acquire_strict_native_mutex(mutex_path)
        access_mode = HostSessionAccessMode.READ_WRITE if mutex_handle is not None else HostSessionAccessMode.READ_ONLY
        state = (
            _AttachmentLifecycleState.RECOVERING
            if access_mode is HostSessionAccessMode.READ_WRITE
            else _AttachmentLifecycleState.ACTIVE
        )
        try:
            record = _AttachmentRecord(
                session_id=session_id,
                access_mode=access_mode,
                state=state,
                mutex_handle=mutex_handle,
            )
            allocation = _AttachmentAllocation(registry=self, record=record)
            self._records[session_id] = record
            return allocation
        except BaseException as exc:
            if mutex_handle is not None:
                try:
                    mutex_handle.close()
                except StrictNativeMutexUnavailableError as cleanup_error:
                    exc.add_note("attachment allocation cleanup failed: " f"{cleanup_error.__class__.__name__}")
            raise

    def acquire_mutation_lease(self, session_id: str) -> SessionWorkLease:
        """为 ACTIVE RW attachment 获取用户 mutation lease。

        :param session_id: mutation 对应的 Session id。
        :returns: 必须绑定底层 actor Future 或显式释放的 lease。
        :raises ValueError: Session id 为空时抛出。
        :raises HostApiError: attachment 缺失、RO、RECOVERING 或 CLOSING 时抛出。
        """

        _require_session_id(session_id)
        record = self._records.get(session_id)
        if record is None:
            reason = (
                HostSessionMutationRejectionReason.ATTACHMENT_CLOSING
                if self._host_closing
                else HostSessionMutationRejectionReason.ATTACHMENT_REQUIRED
            )
            raise _mutation_access_error(
                session_id=session_id,
                reason=reason,
                actual_mode=None,
            )
        if record.state is _AttachmentLifecycleState.CLOSING:
            raise _mutation_access_error(
                session_id=session_id,
                reason=HostSessionMutationRejectionReason.ATTACHMENT_CLOSING,
                actual_mode=record.access_mode,
            )
        if record.state is not _AttachmentLifecycleState.ACTIVE:
            raise _mutation_access_error(
                session_id=session_id,
                reason=HostSessionMutationRejectionReason.ATTACHMENT_REQUIRED,
                actual_mode=None,
            )
        if record.access_mode is HostSessionAccessMode.READ_ONLY:
            raise _mutation_access_error(
                session_id=session_id,
                reason=HostSessionMutationRejectionReason.READ_ONLY,
                actual_mode=record.access_mode,
            )
        return self._acquire_lease(record, _SessionLeaseKind.MUTATION)

    def try_acquire_new_work_lease(
        self,
        session_id: str,
    ) -> SessionWorkLease | None:
        """尝试为 ACTIVE RW Session 获取 pre-start/new-work lease。

        :param session_id: 目标 Session id。
        :returns: registry access truth 允许时返回 lease，否则返回 ``None``。
        :raises ValueError: Session id 为空时抛出。
        """

        _require_session_id(session_id)
        if self._host_closing:
            return None
        record = self._records.get(session_id)
        if (
            record is None
            or record.state is not _AttachmentLifecycleState.ACTIVE
            or record.access_mode is not HostSessionAccessMode.READ_WRITE
        ):
            return None
        return self._acquire_lease(record, _SessionLeaseKind.NEW_WORK)

    def active_read_write_session_ids(self) -> tuple[str, ...]:
        """返回当前 ACTIVE RW Session id 的稳定排序快照。

        :returns: 排序后的 Session id 元组；Host closing 后为空。
        :raises Exception: 不主动抛出异常。
        """

        if self._host_closing:
            return ()
        return tuple(
            sorted(
                session_id
                for session_id, record in self._records.items()
                if record.state is _AttachmentLifecycleState.ACTIVE
                and record.access_mode is HostSessionAccessMode.READ_WRITE
            )
        )

    def begin_host_close(self) -> None:
        """批量关闭 attach/mutation/new-work gate，但保持全部 mutex 持有。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._host_close_released:
            return
        self._host_closing = True
        for record in self._records.values():
            self._mark_record_closing(record)

    async def drain_host_close(self) -> None:
        """按 mutation 后 new-work 顺序 drain 全部 live attachment lease。

        本方法只建立 scheduler lifecycle barrier 前置条件，不释放 native mutex，
        不删除 record，也不写 durable fact。

        :returns: ``None``。
        :raises RuntimeError: 未先调用 ``begin_host_close`` 时抛出。
        """

        if not self._host_closing:
            raise RuntimeError("Host attachment registry 必须先 begin_host_close")
        records = tuple(self._records.values())
        for record in records:
            await record.mutation_drained.wait()
        for record in records:
            await record.new_work_drained.wait()
        self._host_close_drained = True

    async def release_host_close(self) -> None:
        """在外部 scheduler lifecycle barrier 成功后批量释放 mutex/record。

        :returns: ``None``。
        :raises RuntimeError: Host close 尚未完成 batch drain 时抛出。
        :raises StrictNativeMutexUnavailableError: 任一 native release 失败时抛出；
            其它 record 仍会继续安全 cleanup。
        """

        if self._host_close_released:
            return
        if not self._host_close_drained:
            raise RuntimeError("Host attachment registry 必须在 release 前完成 drain")

        records = tuple(self._records.values())
        first_error: StrictNativeMutexUnavailableError | None = None
        close_tasks: list[asyncio.Task[None]] = []
        for record in records:
            error = self._release_record(record)
            if error is not None and first_error is None:
                first_error = error
            if record.close_task is not None:
                close_tasks.append(record.close_task)

        for close_task in close_tasks:
            await asyncio.shield(close_task)

        if not self._records:
            self._host_close_released = True
        if first_error is not None:
            raise first_error

    def _prepare_mutex_directory(self) -> None:
        """创建 canonical DB 同目录下的私有 mutex 目录。

        :returns: ``None``。
        :raises StrictNativeMutexUnavailableError: 目录创建失败时抛出。
        """

        try:
            self._mutex_directory.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            raise StrictNativeMutexUnavailableError("创建 Session strict-native mutex directory 失败") from exc

    def _activate_allocation(self, record: _AttachmentRecord) -> None:
        """把当前 live allocation 转入 ACTIVE。

        :param record: 待激活的唯一 live record。
        :returns: ``None``。
        :raises RuntimeError: record 已失效、closing，或 recovery work 未 drain 时抛出。
        """

        if self._records.get(record.session_id) is not record:
            raise RuntimeError("attachment allocation 已不再 live")
        if self._host_closing or record.state in (
            _AttachmentLifecycleState.CLOSING,
            _AttachmentLifecycleState.CLOSED,
        ):
            raise RuntimeError("attachment allocation 已进入 closing")
        if record.new_work_lease_count != 0:
            raise RuntimeError("attachment recovery work 尚未收口")
        if record.state is _AttachmentLifecycleState.RECOVERING:
            record.state = _AttachmentLifecycleState.ACTIVE

    def _acquire_recovery_work_lease(
        self,
        record: _AttachmentRecord,
    ) -> SessionWorkLease:
        """为精确 RECOVERING RW allocation 获取 work lease。

        :param record: allocation 持有的 record。
        :returns: target recovery work lease。
        :raises RuntimeError: record 不再是当前 RECOVERING RW owner 时抛出。
        """

        if (
            self._host_closing
            or self._records.get(record.session_id) is not record
            or record.state is not _AttachmentLifecycleState.RECOVERING
            or record.access_mode is not HostSessionAccessMode.READ_WRITE
        ):
            raise RuntimeError("只有 live RECOVERING RW allocation 可取得 recovery lease")
        return self._acquire_lease(record, _SessionLeaseKind.NEW_WORK)

    def _acquire_lease(
        self,
        record: _AttachmentRecord,
        kind: _SessionLeaseKind,
    ) -> SessionWorkLease:
        """增加精确类别计数并返回 lease。

        :param record: lease 所属 live record。
        :param kind: mutation 或 new-work 类别。
        :returns: 新创建的幂等 lease。
        :raises RuntimeError: record 已不在 live index 时抛出。
        """

        if self._records.get(record.session_id) is not record:
            raise RuntimeError("不能为非 live attachment 创建 lease")
        if kind is _SessionLeaseKind.MUTATION:
            record.mutation_lease_count += 1
            record.mutation_drained.clear()
        else:
            record.new_work_lease_count += 1
            record.new_work_drained.clear()
        return SessionWorkLease(registry=self, record=record, kind=kind)

    def _release_lease(
        self,
        record: _AttachmentRecord,
        kind: _SessionLeaseKind,
    ) -> None:
        """减少精确类别 lease 计数并在归零时通知 drain。

        :param record: lease 所属 record。
        :param kind: mutation 或 new-work 类别。
        :returns: ``None``。
        :raises RuntimeError: 对应计数已经为零时抛出。
        """

        if kind is _SessionLeaseKind.MUTATION:
            if record.mutation_lease_count <= 0:
                raise RuntimeError("attachment mutation lease 计数下溢")
            record.mutation_lease_count -= 1
            if record.mutation_lease_count == 0:
                record.mutation_drained.set()
            return

        if record.new_work_lease_count <= 0:
            raise RuntimeError("attachment new-work lease 计数下溢")
        record.new_work_lease_count -= 1
        if record.new_work_lease_count == 0:
            record.new_work_drained.set()

    async def _close_attachment(self, record: _AttachmentRecord) -> None:
        """启动或 join 单 attachment 共享 cleanup task。

        :param record: attachment/allocation 持有的 record。
        :returns: ``None``。
        :raises asyncio.CancelledError: 当前 caller 等待被取消时抛出。
        :raises StrictNativeMutexUnavailableError: native release 失败时抛出。
        """

        if record.state is _AttachmentLifecycleState.CLOSED:
            return
        if record.close_task is None:
            record.close_task = asyncio.create_task(self._run_attachment_close(record))
        await asyncio.shield(record.close_task)
        if record.close_error is not None:
            raise record.close_error

    async def _run_attachment_close(self, record: _AttachmentRecord) -> None:
        """执行单 attachment gate、分段 drain 与条件 release。

        :param record: 待关闭 live record。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常；release 错误写入 record 供 caller 读取。
        """

        self._mark_record_closing(record)
        await record.mutation_drained.wait()
        await record.new_work_drained.wait()
        if self._host_closing:
            await record.close_completed.wait()
            return
        self._release_record(record)

    def _mark_record_closing(self, record: _AttachmentRecord) -> None:
        """把 live RECOVERING/ACTIVE record 原子标为 CLOSING。

        :param record: 待关闭 record。
        :returns: ``None``。
        :raises RuntimeError: record 状态不属于封闭 lifecycle 时抛出。
        """

        if record.state in (
            _AttachmentLifecycleState.RECOVERING,
            _AttachmentLifecycleState.ACTIVE,
        ):
            record.state = _AttachmentLifecycleState.CLOSING
            return
        if record.state in (
            _AttachmentLifecycleState.CLOSING,
            _AttachmentLifecycleState.CLOSED,
        ):
            return
        raise RuntimeError("未知 attachment lifecycle state")

    def _release_record(
        self,
        record: _AttachmentRecord,
    ) -> StrictNativeMutexUnavailableError | None:
        """释放单个 record 的 native handle 并移除 live index。

        :param record: 已完成 lease drain 的 CLOSING record。
        :returns: 成功返回 ``None``；native release 失败返回稳定错误。
        :raises RuntimeError: record 尚未 CLOSING 时抛出。
        """

        if record.state is _AttachmentLifecycleState.CLOSED:
            return record.close_error
        if record.state is not _AttachmentLifecycleState.CLOSING:
            raise RuntimeError("attachment release 前必须进入 CLOSING")
        if record.close_error is not None:
            record.close_completed.set()
            return record.close_error

        if record.mutex_handle is not None:
            try:
                record.mutex_handle.close()
            except StrictNativeMutexUnavailableError as exc:
                record.close_error = exc
                record.close_completed.set()
                return exc
        record.state = _AttachmentLifecycleState.CLOSED
        if self._records.get(record.session_id) is record:
            del self._records[record.session_id]
        record.close_completed.set()
        return None


def _resolve_existing_db_path(db_path: Path) -> Path:
    """解析并校验已经存在的 Host SQLite 真实路径。

    :param db_path: Host durable store 路径。
    :returns: canonical absolute real path。
    :raises ValueError: 路径不存在或不是普通文件时抛出。
    """

    try:
        resolved = db_path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Host durable store path 必须存在") from exc
    if not resolved.is_file():
        raise ValueError("Host durable store path 必须是普通文件")
    return resolved


def _derive_session_mutex_path(db_path: Path, session_id: str) -> Path:
    """从真实 DB identity 与 Session id 派生 opaque mutex path。

    :param db_path: 已存在 Host SQLite 路径。
    :param session_id: 目标 Session id。
    :returns: DB 同目录私有子目录下的 sha256 文件路径。
    :raises ValueError: DB 路径或 Session id 非法时抛出。
    """

    _require_session_id(session_id)
    resolved = _resolve_existing_db_path(db_path)
    return _derive_mutex_path_from_identity(
        mutex_directory=resolved.parent / _SESSION_MUTEX_DIRECTORY_NAME,
        canonical_store_identity=os.path.normcase(str(resolved)),
        session_id=session_id,
    )


def _derive_mutex_path_from_identity(
    *,
    mutex_directory: Path,
    canonical_store_identity: str,
    session_id: str,
) -> Path:
    """用已校验 canonical identity 构造 sha256 mutex 文件名。

    :param mutex_directory: DB 同目录下的私有 mutex 目录。
    :param canonical_store_identity: ``resolve(strict=True)`` 后经 normcase 的路径。
    :param session_id: 目标 Session id。
    :returns: 不暴露 raw Session id 的 mutex path。
    :raises ValueError: Session id 为空时抛出。
    """

    _require_session_id(session_id)
    digest = hashlib.sha256(f"{canonical_store_identity}\0{session_id}".encode("utf-8")).hexdigest()
    return mutex_directory / digest


def _require_session_id(session_id: str) -> None:
    """校验 registry owner key 使用非空 Session id。

    :param session_id: 待校验 Session id。
    :returns: ``None``。
    :raises ValueError: Session id 为空或仅含空白时抛出。
    """

    if session_id.strip() == "":
        raise ValueError("session_id must not be empty")


def _attachment_conflict_error(session_id: str) -> HostApiError:
    """构造 duplicate live attachment 的 typed conflict。

    :param session_id: 已存在 live record 的 Session id。
    :returns: ``CONFLICT`` 且不可重试的 Host API 错误。
    :raises ValueError: Session id 为空时由 detail 校验抛出。
    """

    return HostApiError(
        code=HostApiErrorCode.CONFLICT,
        message=_ATTACHMENT_CONFLICT_MESSAGE,
        retryable=False,
        detail=HostSessionAttachmentConflictDetail(
            kind="session_attachment_conflict",
            session_id=session_id,
            reason=HostSessionAttachmentConflictReason.ALREADY_ATTACHED,
        ),
    )


def _mutation_access_error(
    *,
    session_id: str,
    reason: HostSessionMutationRejectionReason,
    actual_mode: HostSessionAccessMode | None,
) -> HostApiError:
    """构造 registry mutation access typed rejection。

    :param session_id: mutation 对应 Session id。
    :param reason: access owner 产生的稳定拒绝原因。
    :param actual_mode: 当前 live attachment mode；无 ACTIVE mode 时为 ``None``。
    :returns: ``PERMISSION_DENIED`` 且不可重试的 Host API 错误。
    :raises ValueError: detail 字段非法时抛出。
    """

    if reason is HostSessionMutationRejectionReason.READ_ONLY:
        message = _MUTATION_READ_ONLY_MESSAGE
    elif reason is HostSessionMutationRejectionReason.ATTACHMENT_CLOSING:
        message = _MUTATION_CLOSING_MESSAGE
    else:
        message = _MUTATION_REQUIRED_MESSAGE
    return HostApiError(
        code=HostApiErrorCode.PERMISSION_DENIED,
        message=message,
        retryable=False,
        detail=HostSessionMutationErrorDetail(
            kind="session_mutation_access",
            session_id=session_id,
            reason=reason,
            required_mode=HostSessionAccessMode.READ_WRITE,
            actual_mode=actual_mode,
        ),
    )
