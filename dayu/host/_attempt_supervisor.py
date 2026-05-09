"""Host P8-S3 Attempt Supervisor: lease context、renew heartbeat 与 owner-lost 信号。

本模块实现 :class:`AttemptSupervisor`, 负责把 P8-S1 的 store 层 CAS 能
力包装成可以被 :class:`LocalRunHarness` 直接消费的 attempt 生命周期边
界:

- ``lease_context(...)`` async context manager: 进入时 acquire owner、计
  算 ``lease_expires_at``、启动 renew heartbeat task; 退出时停止 renew
  task; 中间 yield 当前 :class:`AttemptOwnerContext`。
- renew loop: 按 :class:`AttemptLeaseConfig.renew_interval` 周期 renew;
  ``rowcount == 0`` / FENCED / TERMINAL / BUSY 时立刻置位 owner-lost
  signal、记录 masked 日志并退出循环。renew 自身抛异常(SQLite /
  storage 故障等)时记为独立的 ``STORAGE_ERROR`` loss reason, 同样会
  set owner-lost signal, 不再继续延长 lease, 也不会被伪装成 fencing。
- owner-lost signal: 通过 :meth:`wait_owner_lost` 暴露给 harness, 使
  ``LocalRunHarness`` 在等待 Engine event 时可以与 owner-lost race;
  一旦 lease 丢失, harness 会停止后续 EventLog append, 不依赖 store
  层 CAS 兜底。
- diagnostic close: :meth:`close_attempt_with_diagnostic_state` 在同事
  务内对 owner_token_hash + fencing_token 做 CAS; 命中失败说明 owner
  已被 recovery 替换, 直接放弃覆盖未来状态, 不再走 legacy 非 owner-
  aware update。

P8-S3 不实现:

- terminal event append + attempt close 的同事务原子写入(归 P8-S4)。
- recovery scan(归 P8-S6)。
- ToolRuntime / EventLog 事务级 CAS append(归 P8-S5)。
- multiprocessing(归 P8-S7)。

owner secret token 明文不入库、不进入普通日志、不进入 EventLog payload;
本模块所有日志均使用 :meth:`AttemptOwnerToken.masked` / ``owner_id`` /
``fencing_token``。renew / acquire 失败均映射为 typed result 或 typed
error, 禁止把 SQLite 错误透传到上层。
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from collections.abc import AsyncGenerator
from enum import StrEnum

from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptFencingReason,
    AttemptLeaseConfig,
    AttemptLeaseDecision,
    AttemptLeaseResult,
    AttemptOwnerContext,
    AttemptOwnerToken,
    AttemptRecoveryAction,
    AttemptRecoveryDecision,
    AttemptTerminalLink,
    UtcClock,
)
from dayu.host._attempt_state_mapping import (
    attempt_state_from_terminal_event_type,
)
from dayu.host._durable_event_store import DurableRunEventStore
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import (
    AttemptRecord,
    AttemptState,
    GlobalEventPosition,
)
from dayu.host._run_state_store import (
    AttemptIndexCollisionError,
    AttemptLeaseStore,
)
from dayu.host.contracts import (
    TERMINAL_RUN_EVENT_TYPES,
    RunEvent,
    RunEventCursor,
    RunEventDraft,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)
_ERROR_TERMINAL_REQUIRES_TERMINAL_TYPE: str = (
    "append_terminal_and_close requires terminal RunEventType"
)
_ERROR_TERMINAL_DRAFT_TERMINAL_TYPE: str = (
    "AttemptScopedRunEventAppender.append cannot accept terminal "
    "RunEventType; use append_terminal_and_close"
)
_RECOVERY_REASON_RUN_TERMINAL: str = "run_terminal_lost"
"""recovery 原因: run 已 terminal, 旧 attempt 标记为 LOST。"""
_RECOVERY_REASON_ORPHAN_LOST: str = "orphan_created_lost"
"""recovery 原因: ``CREATED`` 孤儿行无 owner, 直接标记为 LOST。"""
_RECOVERY_REASON_UNIQUE_INDEX_COLLISION: str = "unique_index_collision"
"""recovery 原因: 新 recovery attempt INSERT 命中 ``UNIQUE(run_id, attempt_index)`` 冲突, 整事务已回滚。"""
_RECOVERY_OWNER_ID_PREFIX_SUFFIX: str = "recovery"
"""recovery owner_id_prefix 复用 lease_config.owner_id_prefix 并加 suffix。"""


class AttemptOwnerLossReason(StrEnum):
    """owner-lost signal 的强类型原因。

    枚举区分两类不同语义的 owner 失活原因, harness / 诊断 close 据此选
    择收口策略, 禁止把 storage error 伪装成 fencing:

    - ``FENCED``: store 层 CAS 直接拒绝 (FENCED / TERMINAL / BUSY); 当
      前 owner 已被其他 owner 替换, 或 attempt 已被推到终态。
    - ``STORAGE_ERROR``: renew 自身抛出非 ``CancelledError`` 异常 (例
      如 SQLite IO 错误); 不是 fencing, 但同样让当前 owner 不再可写,
      harness 必须按 storage failure 路径收口。
    """

    FENCED = "fenced"
    STORAGE_ERROR = "storage_error"


@dataclass(slots=True)
class _LeaseSession:
    """单次 lease_context 内部状态。

    每个 lease_context 进入时构造一个 session, 用于:

    - 记录当前 owner context (含 lease 到期时刻, renew 后会被替换为
      新副本);
    - 跟踪 renew loop 是否已让 owner 失活 (``loss_reason``) 以及失活
      明细 (``fence_reason``);
    - 暴露 owner-lost signal (``owner_lost_event``), 让 harness 在等
      待 Engine event 时与该 signal race;
    - 让 :meth:`AttemptSupervisor.is_owner_active` 在 supervisor 范围内
      判定该 owner 是否仍可写入 attempt-scoped facts。

    :param owner_context: 当前 owner 句柄, renew 成功后会替换。
    :param loss_reason: owner 失活原因; 为 ``None`` 表示仍 active。
        FENCED / STORAGE_ERROR 后置位, 不可恢复。
    :param fence_reason: store 层 fencing 细分原因; 仅在
        ``loss_reason == FENCED`` 时填充, 用于诊断收口。
    :param owner_lost_event: owner-lost 信号; renew loop 进入失败分支
        前必 set, harness ``wait_owner_lost`` 据此 race。
    :param stopped_event: renew loop 实际退出后 set; 用于 lease_context
        退出路径同步等待 task 终止。
    :param renew_task: renew 后台 task 句柄; 退出时会被取消并 await。
    """

    owner_context: AttemptOwnerContext
    loss_reason: AttemptOwnerLossReason | None = None
    fence_reason: AttemptFencingReason | None = None
    owner_lost_event: asyncio.Event = field(default_factory=asyncio.Event)
    stopped_event: asyncio.Event = field(default_factory=asyncio.Event)
    renew_task: asyncio.Task[None] | None = None


def _default_owner_id(prefix: str) -> str:
    """生成默认 owner 诊断 id。

    ``owner_id`` 仅供诊断/审计, 不参与 fencing 顺序判断, 也不作为授权
    凭据; 使用 ``<prefix>:<pid>:<short uuid>`` 形成进程内唯一摘要。

    :param prefix: owner_id 诊断前缀, 例如 ``host``。
    :returns: 诊断 owner id 字符串。
    :raises Exception: 不主动抛出异常。
    """

    return f"{prefix}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _default_attempt_id(*, run_id: str, attempt_index: int) -> str:
    """生成默认 attempt id。

    保持与 P6/P7 既有 ``attempt-<run_id>-<index>-<uuid>`` 命名一致, 让
    durable harness 集成测试 / smoke 输出可读。

    :param run_id: Run id。
    :param attempt_index: 同一 run 内 attempt 序号。
    :returns: 新建 attempt id 字符串。
    :raises Exception: 不主动抛出异常。
    """

    return f"attempt-{run_id}-{attempt_index}-{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True, slots=True)
class AttemptScopedRunEventAppender:
    """绑定 owner 的 attempt-scoped RunEvent append port。

    本类型是 P8-S5 attempt-scoped append 的强类型入口: 所有由当前
    attempt owner 写入的 canonical fact (Engine-sourced event、context
    overflow / compact facts、``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT``、
    ToolRuntime ``TOOL_RESULT_TRUNCATED`` / ``TOOL_CURSOR_*`` /
    ``TOOL_FETCH_MORE_*``) 都通过本类型在同一个 ``BEGIN IMMEDIATE``
    事务内执行 :meth:`AttemptLeaseStore.verify_owner` + EventLog append,
    任意 owner CAS 命中失败抛 :class:`AttemptFencingError` 整事务回滚,
    EventLog 不残留 stale fact。

    构造约束:

    - 由 :meth:`AttemptSupervisor.scoped_appender` 构造, 调用方不应直接
      持有 ``DurableRunEventStore`` / ``AttemptLeaseStore`` 自行组装事务;
    - ``owner_context`` 是当前 attempt 的 owner 句柄, 不允许跨 attempt /
      跨 run 复用;
    - 所有 append 在内部对 ``draft.run_id`` 与 ``owner_context.run_id``
      做严格相等校验, 不一致时抛
      :class:`AttemptFencingError(reason=OWNER_MISMATCH)`, 防止 ToolRuntime
      在 attempt 边界 race 期间把旧 cursor 的 fact 写到错误 run。

    fencing 真源仍是 :meth:`AttemptLeaseStore.verify_owner` 的事务内 CAS,
    本类型不缓存任何 lease 状态、不旁路 SQL CAS, 也不写诊断 RunEvent;
    fenced late write 直接通过 ``AttemptFencingError`` 透传给上层, 由调
    用方负责 masked 日志 + typed 收口。

    :param storage: 共享 :class:`HostStorage`。
    :param event_store: durable :class:`DurableRunEventStore`; 同事务内
        通过 :meth:`append_with_position_in_transaction` 落库。
    :param lease_store: P8-S1 已落地的 :class:`AttemptLeaseStore`,
        承载 ``verify_owner`` / ``close_terminal`` CAS。
    :param owner_context: 绑定的 owner 句柄。
    """

    storage: HostStorage
    event_store: DurableRunEventStore
    lease_store: AttemptLeaseStore
    owner_context: AttemptOwnerContext

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """在 ``BEGIN IMMEDIATE`` 事务内 append 非 terminal RunEvent。

        步骤:

        1. 校验 ``draft.run_id == owner_context.run_id``, 不一致时抛
           :class:`AttemptFencingError(reason=OWNER_MISMATCH)`;
        2. 校验 ``draft.type`` 不属于 :data:`TERMINAL_RUN_EVENT_TYPES`,
           terminal RunEvent 必须走 :meth:`append_terminal_and_close`,
           否则 attempt close 与 terminal append 失去原子性;
        3. 在同一事务内调用 :meth:`AttemptLeaseStore.verify_owner` +
           :meth:`DurableRunEventStore.append_with_position_in_transaction`,
           任一 CAS 失败抛 :class:`AttemptFencingError`, 整事务回滚。

        非 terminal append 的全局 ``GlobalEventPosition`` 不向调用方暴
        露, 由 ``AppendedRunEvent`` 内部使用; 这与 P6 行为保持一致。

        :param draft: RunEvent 草稿。
        :returns: 已落库的 :class:`RunEvent`。
        :raises ValueError: draft 类型为 terminal 时抛出。
        :raises AttemptFencingError: ``run_id`` 不匹配或 owner CAS 失败。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误透传。
        """

        if draft.type in TERMINAL_RUN_EVENT_TYPES:
            raise ValueError(_ERROR_TERMINAL_DRAFT_TERMINAL_TYPE)
        self._verify_run_id_matches(draft=draft)
        async with self.storage.transaction() as tx:
            self.lease_store.verify_owner(
                tx=tx,
                owner_context=self.owner_context,
            )
            appended = self.event_store.append_with_position_in_transaction(
                tx=tx,
                draft=draft,
            )
        return appended.event

    def append_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        draft: RunEventDraft,
    ) -> RunEvent:
        """在外层事务内同事务 append 非 terminal RunEvent。

        本方法供已经持有 ``HostStorageTransaction`` 的调用方使用 (例如
        ``LocalRunHarness._append_run_input_context_snapshot_fact`` 之
        前已自行开事务的路径), 保证 ``verify_owner`` 与 append 仍在同一
        ``BEGIN IMMEDIATE`` 事务内, 不允许跨事务组合。

        :param tx: 调用方提供的事务上下文。
        :param draft: RunEvent 草稿。
        :returns: 已落库的 :class:`RunEvent`。
        :raises ValueError: draft 类型为 terminal 时抛出。
        :raises AttemptFencingError: ``run_id`` 不匹配或 owner CAS 失败。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误透传。
        """

        if draft.type in TERMINAL_RUN_EVENT_TYPES:
            raise ValueError(_ERROR_TERMINAL_DRAFT_TERMINAL_TYPE)
        self._verify_run_id_matches(draft=draft)
        self.lease_store.verify_owner(
            tx=tx,
            owner_context=self.owner_context,
        )
        appended = self.event_store.append_with_position_in_transaction(
            tx=tx,
            draft=draft,
        )
        return appended.event

    async def append_terminal_and_close(
        self,
        *,
        draft: RunEventDraft,
        failure_summary: str | None = None,
    ) -> AttemptTerminalLink:
        """同事务原子 terminal RunEvent append + attempt 终态 close。

        与 :meth:`AttemptSupervisor.append_terminal_and_close` 语义一致:
        在单一 ``BEGIN IMMEDIATE`` 事务内顺序完成
        :meth:`AttemptLeaseStore.verify_owner` ->
        :meth:`DurableRunEventStore.append_with_position_in_transaction` ->
        :meth:`AttemptLeaseStore.close_terminal`, 任一 CAS 命中失败抛
        :class:`AttemptFencingError` 整事务回滚, EventLog 不残留 stale
        terminal RunEvent。

        :param draft: terminal RunEvent 草稿; 类型必须属于
            :data:`TERMINAL_RUN_EVENT_TYPES`。
        :param failure_summary: 失败摘要; 成功 / 取消 / 暂停诊断为
            ``None``。
        :returns: :class:`AttemptTerminalLink` 含 attempt id、run id、
            terminal state、cursor 与全局 position。
        :raises ValueError: draft 与 owner_context 不一致或 draft 非
            terminal type 时抛出。
        :raises AttemptFencingError: 任一 owner CAS 命中失败时抛出, 整
            事务回滚, EventLog 不残留 terminal RunEvent。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误透传。
        """

        if draft.type not in TERMINAL_RUN_EVENT_TYPES:
            raise ValueError(_ERROR_TERMINAL_REQUIRES_TERMINAL_TYPE)
        self._verify_run_id_matches(draft=draft)
        terminal_state = attempt_state_from_terminal_event_type(draft.type)
        async with self.storage.transaction() as tx:
            self.lease_store.verify_owner(
                tx=tx,
                owner_context=self.owner_context,
            )
            appended = self.event_store.append_with_position_in_transaction(
                tx=tx,
                draft=draft,
            )
            self.lease_store.close_terminal(
                tx=tx,
                owner_context=self.owner_context,
                state=terminal_state,
                terminal_event_position=appended.event_position,
                failure_summary=failure_summary,
            )
        _LOGGER.debug(
            "host.attempt.terminal_close_applied attempt_id=%s "
            "owner_id=%s owner_token=%s fencing_token=%s state=%s "
            "event_position=%s sequence=%s",
            self.owner_context.attempt_id,
            self.owner_context.owner_id,
            self.owner_context.owner_token.masked(),
            self.owner_context.fencing_token.value,
            terminal_state.value,
            appended.event_position.value,
            appended.event.cursor.sequence,
        )
        return AttemptTerminalLink(
            attempt_id=self.owner_context.attempt_id,
            run_id=self.owner_context.run_id,
            terminal_state=terminal_state,
            event=appended.event,
            event_cursor=RunEventCursor(
                sequence=appended.event.cursor.sequence
            ),
            event_position=appended.event_position,
        )

    def _verify_run_id_matches(self, *, draft: RunEventDraft) -> None:
        """校验 draft.run_id 与 owner_context.run_id 严格相等。

        与 store 层 ``verify_owner`` 不同, 本检查是 attempt-scoped append
        的第一道防线: 旧 owner 不应该用绑定它的 appender 写入到其它 run
        的 EventLog, ToolRuntime 在 attempt 边界 race 期间也不应让旧
        cursor 写入新 run。命中失败映射为
        :class:`AttemptFencingError(reason=OWNER_MISMATCH)`, 不写诊断
        RunEvent, 由调用方按 typed refusal 收口。

        :param draft: 待校验的 RunEvent 草稿。
        :returns: 无返回值。
        :raises AttemptFencingError: ``run_id`` 不匹配时抛出。
        """

        if draft.run_id == self.owner_context.run_id:
            return
        _LOGGER.warning(
            "host.attempt.scoped_append_run_id_mismatch "
            "attempt_id=%s owner_run_id=%s draft_run_id=%s "
            "owner_id=%s owner_token=%s fencing_token=%s",
            self.owner_context.attempt_id,
            self.owner_context.run_id,
            draft.run_id,
            self.owner_context.owner_id,
            self.owner_context.owner_token.masked(),
            self.owner_context.fencing_token.value,
        )
        raise AttemptFencingError(
            attempt_id=self.owner_context.attempt_id,
            run_id=self.owner_context.run_id,
            reason=AttemptFencingReason.OWNER_MISMATCH,
            current_state=AttemptState.RUNNING,
            owner_id=self.owner_context.owner_id,
            fencing_token=self.owner_context.fencing_token,
        )


@dataclass(slots=True)
class AttemptSupervisor:
    """Host P8 Attempt 生命周期编排器。

    :param storage: 共享 :class:`HostStorage`; 用于 acquire / renew /
        diagnostic close 的 ``BEGIN IMMEDIATE`` 短事务。
    :param lease_store: P8-S1 已落地的 :class:`AttemptLeaseStore`, 承载
        store 层 CAS。supervisor 不写 SQL, 只通过它访问。
    :param lease_config: 由装配层注入的 :class:`AttemptLeaseConfig`;
        owner secret token / lease TTL / renew interval 全部以该 config
        为真源, 业务调用方与 public ``start_run`` 不暴露 TTL。
    :param clock: 可注入 UTC clock; 用于计算 ``lease_expires_at`` 与
        renew 时间。
    """

    storage: HostStorage
    lease_store: AttemptLeaseStore
    lease_config: AttemptLeaseConfig
    clock: UtcClock
    event_store: DurableRunEventStore
    _sessions: dict[str, _LeaseSession] = field(
        default_factory=dict, init=False
    )

    def is_owner_active(self, owner_context: AttemptOwnerContext) -> bool:
        """判断给定 owner_context 是否仍是该 supervisor 范围内的有效 owner。

        判定条件:

        - supervisor 内有匹配 ``attempt_id`` 的活动 session;
        - session 与传入 owner_context 的 fencing_token 严格相等
          (避免接受同 attempt_id 但 fencing token 不同的旧 owner);
        - session ``loss_reason`` 仍为 ``None``。

        本判定仅用于 supervisor / harness 在 await 之间的内部协调; 真正
        的 fencing 真源仍是 store 层 CAS, 任何 attempt-scoped 写入必须
        在事务内调用 :meth:`AttemptLeaseStore.verify_owner` 或等价 CAS。

        :param owner_context: 待判定的 owner 句柄。
        :returns: 仍 active 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        session = self._sessions.get(owner_context.attempt_id)
        if session is None:
            return False
        if session.loss_reason is not None:
            return False
        return (
            session.owner_context.fencing_token.value
            == owner_context.fencing_token.value
        )

    async def wait_owner_lost(
        self, owner_context: AttemptOwnerContext
    ) -> AttemptOwnerLossReason:
        """等待 owner-lost 信号, 命中后返回 typed loss reason。

        本方法是 P8-S3 给 :class:`LocalRunHarness` 提供的强类型 owner-
        lost 信号入口: harness 在等待 Engine event 时, 必须与本协程做
        race; 一旦 owner-lost 命中, harness 关闭 engine iterator、停止
        后续 EventLog append, 并通过 supervisor diagnostic close 把
        attempt 收口。

        语义约定:

        - ``attempt_id`` 在 ``_sessions`` 缺失时, 视为已失活, 直接返回
          ``FENCED`` (lease_context 已退出, supervisor 已不再为该 owner
          做任何延长承诺)。
        - ``fencing_token`` 不一致时同样按 FENCED 处理, 不阻塞调用方。
        - 已经 set 的 ``owner_lost_event`` 立即返回, 不再 await。

        :param owner_context: harness 持有的 owner 句柄。
        :returns: typed :class:`AttemptOwnerLossReason`。
        :raises Exception: 不主动抛出异常 (内部 await 被取消时透传)。
        """

        session = self._sessions.get(owner_context.attempt_id)
        if session is None:
            return AttemptOwnerLossReason.FENCED
        if (
            session.owner_context.fencing_token.value
            != owner_context.fencing_token.value
        ):
            return AttemptOwnerLossReason.FENCED
        await session.owner_lost_event.wait()
        # owner_lost_event 被 set 时 loss_reason 必为非 None; 若并发场
        # 景下出现 race, 兜底为 FENCED 仍是安全选择 (harness 会停止 append)。
        return session.loss_reason or AttemptOwnerLossReason.FENCED

    @asynccontextmanager
    async def lease_context(
        self,
        *,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None = None,
    ) -> AsyncGenerator[AttemptOwnerContext, None]:
        """async context manager: 在事务内 acquire owner 并启动 renew loop。

        进入流程:

        1. 计算 ``lease_expires_at = clock.now() + lease_config.ttl``;
        2. 在 ``HostStorage.transaction()`` 中调用
           :meth:`AttemptLeaseStore.acquire_new_attempt`, 由 store 同事
           务分配新的全局单调 fencing token 并写入 ``host_attempts``;
        3. 创建 :class:`_LeaseSession` 并启动 renew heartbeat task;
        4. yield 当前 :class:`AttemptOwnerContext`。

        退出流程(包含正常 / 异常):

        - 取消 renew task 并 await 其结束 (无论 task 此前是否已异常退出
          都会读取 ``task.exception()`` 以避免静默丢失);
        - 从 ``_sessions`` 移除当前 session, 防止后续 append 误判 owner
          仍 active;
        - 不在此 slice 内做 terminal event position 写入(归 P8-S4);
          owner-aware diagnostic close 由
          :meth:`close_attempt_with_diagnostic_state` 提供, 调用方按需
          在 lease_context 退出前调用。

        :param run_id: Run id。
        :param attempt_index: 同一 run 内 attempt 序号。
        :param recovered_from_attempt_id: 若为 recovery attempt, 记录被
            恢复的旧 attempt id; 非 recovery 路径为 ``None``。
        :returns: 异步迭代器, 仅产出一个 :class:`AttemptOwnerContext`。
        :raises AttemptFencingError: acquire 命中 BUSY / TERMINAL /
            FENCED 等非 ACQUIRED 决策时抛出, 由调用方决定收口策略。
        """

        owner_token = AttemptOwnerToken.new()
        owner_id = _default_owner_id(self.lease_config.owner_id_prefix)
        attempt_id = _default_attempt_id(
            run_id=run_id, attempt_index=attempt_index
        )
        lease_expires_at = self._compute_lease_expiry()
        result = await self._acquire_in_transaction(
            attempt_id=attempt_id,
            run_id=run_id,
            attempt_index=attempt_index,
            recovered_from_attempt_id=recovered_from_attempt_id,
            owner_id=owner_id,
            owner_token=owner_token,
            lease_expires_at=lease_expires_at,
        )
        owner_context = self._require_acquired(
            result=result,
            attempt_id=attempt_id,
            run_id=run_id,
        )
        session = _LeaseSession(owner_context=owner_context)
        self._sessions[attempt_id] = session
        renew_task = asyncio.create_task(
            self._renew_loop(session=session),
            name=f"attempt-renew:{attempt_id}",
        )
        session.renew_task = renew_task
        _LOGGER.debug(
            "host.attempt.lease_acquired run_id=%s attempt_id=%s "
            "attempt_index=%s owner_id=%s owner_token=%s "
            "fencing_token=%s lease_expires_at=%s",
            run_id,
            attempt_id,
            attempt_index,
            owner_id,
            owner_token.masked(),
            owner_context.fencing_token.value,
            lease_expires_at.isoformat(),
        )
        try:
            yield owner_context
        finally:
            await self._stop_session(session=session, attempt_id=attempt_id)

    async def close_attempt_with_diagnostic_state(
        self,
        *,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        failure_summary: str | None,
        terminal_event_position: GlobalEventPosition | None = None,
    ) -> bool:
        """对 attempt 执行 owner-aware diagnostic close。

        在 ``BEGIN IMMEDIATE`` 短事务内对 ``host_attempts`` 做 CAS 更新,
        条件包含 ``owner_token_hash`` + ``fencing_token``;命中失败时直接
        放弃覆盖, 不回退到 legacy 非 owner-aware update, 也不抛出 (调用
        方仍然可以进入 lease_context 退出路径)。

        本方法适用于 P8-S3 阶段所有非 terminal-event-driven 的 attempt
        收口路径, 例如 ``STALE`` / ``FAILED`` / ``LOST`` 诊断态。
        terminal event append + 终态 close 的真正同事务原子写入仍归
        P8-S4 实现, 不在本方法的承诺内。

        :param owner_context: 当前 owner 句柄; 仅用其 ``attempt_id`` /
            ``owner_token`` / ``fencing_token`` 作 CAS 凭据。
        :param state: 期望写入的 attempt 终态 / 诊断态。
        :param failure_summary: 失败摘要; 成功诊断态可为 ``None``。
        :param terminal_event_position: terminal 事件全局位置; P8-S3 主
            路径调用方应传 ``None``, 终态原子写入归 P8-S4。
        :returns: CAS 命中并写入返回 ``True``; rowcount==0 时返回
            ``False``, 表示 owner 已被 recovery / 其他 owner 替换。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误时透传。
        """

        async with self.storage.transaction() as tx:
            updated = self.lease_store.update_state_owner_aware(
                tx=tx,
                owner_context=owner_context,
                state=state,
                failure_summary=failure_summary,
                terminal_event_position=terminal_event_position,
            )
        if not updated:
            _LOGGER.warning(
                "host.attempt.diagnostic_close_skipped attempt_id=%s "
                "owner_id=%s owner_token=%s fencing_token=%s "
                "target_state=%s",
                owner_context.attempt_id,
                owner_context.owner_id,
                owner_context.owner_token.masked(),
                owner_context.fencing_token.value,
                state.value,
            )
            return False
        _LOGGER.debug(
            "host.attempt.diagnostic_close_applied attempt_id=%s "
            "owner_id=%s owner_token=%s fencing_token=%s state=%s",
            owner_context.attempt_id,
            owner_context.owner_id,
            owner_context.owner_token.masked(),
            owner_context.fencing_token.value,
            state.value,
        )
        return True

    async def append_terminal_and_close(
        self,
        *,
        owner_context: AttemptOwnerContext,
        draft: RunEventDraft,
        failure_summary: str | None = None,
    ) -> AttemptTerminalLink:
        """同事务原子完成: terminal RunEvent append + attempt 终态 close。

        本方法是 P8-S4 的核心入口, 在单一 ``BEGIN IMMEDIATE`` 事务内顺
        序完成:

        1. 校验 ``owner_context.run_id == draft.run_id`` 与 draft type
           为 terminal RunEventType, 防止把非终态事件错误送入终态收口路径;
        2. :meth:`AttemptLeaseStore.verify_owner` 在事务内确认当前 owner
           仍然有效 (state=running、owner_token_hash + fencing_token 命中、
           lease 未过期); 命中失败抛 :class:`AttemptFencingError`,
           ``BEGIN IMMEDIATE`` 事务整体回滚, EventLog 不残留 stale terminal
           RunEvent;
        3. :meth:`DurableRunEventStore.append_with_position_in_transaction`
           在同事务内 append terminal RunEvent, 取得全局位置;
        4. :meth:`AttemptLeaseStore.close_terminal` 用 owner CAS 把
           ``host_attempts`` 推到对应终态, 同时写入
           ``terminal_event_position`` / ``finished_at`` /
           ``failure_summary``。CAS 命中失败同样抛
           :class:`AttemptFencingError` 触发回滚。

        terminal Run state 与 RunResult snapshot 仍由 EventLog
        ``_upsert_run_state`` / ``_write_terminal_result_snapshot`` 在同
        事务内完成, supervisor 不重复 update。

        :param owner_context: 当前 owner 句柄。
        :param draft: 终态 RunEvent 草稿; 必须是 terminal type 且
            ``run_id`` 与 owner_context 一致。
        :param failure_summary: 失败摘要; 成功 / 取消 / 暂停诊断为 ``None``。
        :returns: :class:`AttemptTerminalLink` 包含 attempt id、run id、
            terminal state、cursor 与全局 position。
        :raises ValueError: draft 与 owner_context 不一致或 draft 非
            terminal type 时抛出。
        :raises AttemptFencingError: 任一 owner CAS 命中失败时抛出, 整
            个事务已回滚, EventLog 不残留 terminal RunEvent。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误透传。
        """

        appender = self.scoped_appender(owner_context)
        return await appender.append_terminal_and_close(
            draft=draft,
            failure_summary=failure_summary,
        )

    def scoped_appender(
        self, owner_context: AttemptOwnerContext
    ) -> "AttemptScopedRunEventAppender":
        """构造绑定指定 owner 的 :class:`AttemptScopedRunEventAppender`。

        本工厂是 P8-S5 attempt-scoped append 的唯一公开入口: harness /
        ToolRuntime owner scope / supervisor 自身的 terminal close 都通过
        本方法构造 appender, 不允许调用方直接持有
        :class:`DurableRunEventStore` 或 :class:`AttemptLeaseStore` 自行
        组装事务。

        :param owner_context: 当前 owner 句柄。
        :returns: 绑定 owner 的 attempt-scoped append port。
        :raises Exception: 不主动抛出异常。
        """

        return AttemptScopedRunEventAppender(
            storage=self.storage,
            event_store=self.event_store,
            lease_store=self.lease_store,
            owner_context=owner_context,
        )

    async def recover_stale_attempts(
        self,
        *,
        run_id: str | None = None,
    ) -> tuple[AttemptRecoveryDecision, ...]:
        """对过期 / orphan attempt 执行 recovery scan, 返回 typed 决策序列。

        本方法是 P8-S6 的内部显式入口, 仅供 host 内部测试 / 治理调用,
        不暴露到 public Host API; 也不会自动接入 ``build_durable_harness``
        bootstrap 流程。每个候选 attempt 在独立 ``BEGIN IMMEDIATE`` 短事务
        内处理, 失败原子回滚, 不影响其它候选。

        判定矩阵:

        - run 已 terminal -> ``MARK_LOST`` (旧 attempt 标记 LOST, 不创建
          recovery attempt);
        - ``CREATED`` 孤儿行 (无 owner / 无 fencing token) -> ``MARK_LOST``;
        - ``RUNNING`` 且 ``lease_expires_at <= now`` 且 fencing token 存在
          -> ``MARK_RECOVERING_AND_CREATE_ATTEMPT`` (CAS 旧行为 RECOVERING,
          同事务 INSERT 新 attempt 并分配新 fencing token + 新 owner secret +
          ``recovered_from_attempt_id``);
        - 任一 CAS 命中失败 -> ``NOOP_TERMINAL`` (其它进程已推进, 本轮跳过)。

        本方法严格遵守 P8-S6 scope:

        - 不写 EventLog 诊断 RunEvent;
        - 不推进 projection / outbox checkpoint;
        - 不接管同一 attempt (recovery 必须用新 ``attempt_index`` /
          ``attempt_id`` / fencing token);
        - 不暴露 owner secret 明文; 所有日志使用 masked token。

        :param run_id: 限定 run; ``None`` 表示扫描全库 (诊断用)。
        :returns: 各候选的 typed :class:`AttemptRecoveryDecision` 元组,
            按候选 ``started_at`` 升序; 无候选返回空元组。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误时透传。
        """

        now = self.clock.now()
        async with self.storage.transaction() as scan_tx:
            candidates = self.lease_store.list_recovery_candidates(
                tx=scan_tx,
                run_id=run_id,
                now=now,
            )
        decisions: list[AttemptRecoveryDecision] = []
        for candidate in candidates:
            decision = await self._process_recovery_candidate(candidate)
            decisions.append(decision)
            _LOGGER.info(
                "host.attempt.recovery_decision run_id=%s "
                "source_attempt_id=%s action=%s "
                "recovery_attempt_id=%s reason=%s",
                candidate.run_id,
                candidate.attempt_id,
                decision.action.value,
                decision.recovery_attempt_id,
                decision.reason,
            )
        return tuple(decisions)

    async def _process_recovery_candidate(
        self, candidate: AttemptRecord
    ) -> AttemptRecoveryDecision:
        """在独立短事务内处理单个 recovery 候选。

        本方法把 store 层 typed 决策视为唯一真源, 只在两类情况下不直接
        透传 store decision:

        - run 已 terminal 或 候选为 ``CREATED`` 孤儿: 不进入 ``mark_recovering_and_create_attempt``,
          走 :meth:`AttemptLeaseStore.mark_stale_or_lost`, 由 supervisor
          决定 ``MARK_LOST`` reason 文案 (``run_terminal_lost`` /
          ``orphan_created_lost``);
        - INSERT 命中 ``UNIQUE(run_id, attempt_index)`` 冲突: store 层抛
          :class:`AttemptIndexCollisionError`, 由外层 ``async with
          storage.transaction()`` 回滚整事务 (旧 attempt 的
          ``RECOVERING`` CAS 一并回滚), supervisor 在事务外捕获并返回
          typed ``NOOP_TERMINAL(reason="unique_index_collision")``。

        其它路径下, store 层返回的 :class:`AttemptRecoveryDecision`
        (含 ``MARK_RECOVERING_AND_CREATE_ATTEMPT`` / ``NOOP_TERMINAL``)
        必须原样返回, 包括其 ``reason`` 字段; supervisor 不允许静默改写
        store decision 以保留 store 层 CAS 真源的诊断粒度。

        :param candidate: ``list_recovery_candidates`` 返回的旧 attempt 行。
        :returns: typed :class:`AttemptRecoveryDecision`。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误时透传。
        """

        try:
            async with self.storage.transaction() as tx:
                if self.lease_store.is_run_terminal(
                    tx=tx, run_id=candidate.run_id
                ):
                    return self.lease_store.mark_stale_or_lost(
                        tx=tx,
                        source_attempt_id=candidate.attempt_id,
                        source_fencing_token=(
                            None
                            if candidate.fencing_token is None
                            else candidate.fencing_token.value
                        ),
                        target_state=AttemptState.LOST,
                        reason=_RECOVERY_REASON_RUN_TERMINAL,
                    )
                if (
                    candidate.state is AttemptState.CREATED
                    or candidate.fencing_token is None
                ):
                    return self.lease_store.mark_stale_or_lost(
                        tx=tx,
                        source_attempt_id=candidate.attempt_id,
                        source_fencing_token=None,
                        target_state=AttemptState.LOST,
                        reason=_RECOVERY_REASON_ORPHAN_LOST,
                    )
                recovery_attempt_index = self.lease_store.next_attempt_index(
                    tx=tx, run_id=candidate.run_id
                )
                recovery_attempt_id = _default_attempt_id(
                    run_id=candidate.run_id,
                    attempt_index=recovery_attempt_index,
                )
                owner_token = AttemptOwnerToken.new()
                owner_id = _default_owner_id(
                    f"{self.lease_config.owner_id_prefix}-"
                    f"{_RECOVERY_OWNER_ID_PREFIX_SUFFIX}"
                )
                lease_expires_at = self._compute_lease_expiry()
                decision = (
                    self.lease_store.mark_recovering_and_create_attempt(
                        tx=tx,
                        source_attempt_id=candidate.attempt_id,
                        source_fencing_token=candidate.fencing_token.value,
                        run_id=candidate.run_id,
                        recovery_attempt_id=recovery_attempt_id,
                        recovery_attempt_index=recovery_attempt_index,
                        owner_id=owner_id,
                        owner_token=owner_token,
                        lease_expires_at=lease_expires_at,
                    )
                )
                if (
                    decision.action
                    is AttemptRecoveryAction.MARK_RECOVERING_AND_CREATE_ATTEMPT
                ):
                    _LOGGER.debug(
                        "host.attempt.recovery_started run_id=%s "
                        "source_attempt_id=%s recovery_attempt_id=%s "
                        "recovery_attempt_index=%s owner_id=%s "
                        "owner_token=%s lease_expires_at=%s",
                        candidate.run_id,
                        candidate.attempt_id,
                        recovery_attempt_id,
                        recovery_attempt_index,
                        owner_id,
                        owner_token.masked(),
                        lease_expires_at.isoformat(),
                    )
                    return decision
                # 非 MARK_RECOVERING_AND_CREATE_ATTEMPT 必须由 store 决定
                # action / reason: 当前 store 实现仅返回
                # NOOP_TERMINAL(reason=cas_failed_noop), 但 supervisor
                # 不在此处覆盖, 以保留 store 层 typed decision 的诊断粒度,
                # 也让未来 store 扩展新 action 时不被 supervisor 静默吞掉。
                _LOGGER.debug(
                    "host.attempt.recovery_store_decision "
                    "source_attempt_id=%s action=%s reason=%s",
                    candidate.attempt_id,
                    decision.action.value,
                    decision.reason,
                )
                return decision
        except AttemptIndexCollisionError as exc:
            # 整事务已被外层 ``async with storage.transaction()`` 回滚,
            # 旧 attempt 的 ``RECOVERING`` CAS 与新 recovery attempt
            # INSERT 同时未提交, 不存在半状态。supervisor 必须把 typed
            # 冲突收口为 ``NOOP_TERMINAL(reason="unique_index_collision")``,
            # 避免裸 ``sqlite3.IntegrityError`` 泄漏给上层调用方。
            _LOGGER.warning(
                "host.attempt.recovery_unique_index_collision run_id=%s "
                "source_attempt_id=%s recovery_attempt_index=%s",
                exc.run_id,
                exc.source_attempt_id,
                exc.attempt_index,
            )
            return AttemptRecoveryDecision(
                action=AttemptRecoveryAction.NOOP_TERMINAL,
                source_attempt_id=candidate.attempt_id,
                recovery_attempt_id=None,
                recovery_attempt_index=None,
                reason=_RECOVERY_REASON_UNIQUE_INDEX_COLLISION,
            )

    async def _acquire_in_transaction(
        self,
        *,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None,
        owner_id: str,
        owner_token: AttemptOwnerToken,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        """在 ``BEGIN IMMEDIATE`` 短事务内 acquire 新 owner lease。

        :param attempt_id: 新 attempt id。
        :param run_id: Run id。
        :param attempt_index: attempt 序号。
        :param recovered_from_attempt_id: recovery 来源 attempt id。
        :param owner_id: 新 owner 诊断 id。
        :param owner_token: 新 owner secret token; 明文不入库。
        :param lease_expires_at: 由 supervisor 按 config.ttl 计算的到期
            时刻。
        :returns: store 层 typed :class:`AttemptLeaseResult`。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误时透传。
        """

        async with self.storage.transaction() as tx:
            return self.lease_store.acquire_new_attempt(
                tx=tx,
                attempt_id=attempt_id,
                run_id=run_id,
                attempt_index=attempt_index,
                recovered_from_attempt_id=recovered_from_attempt_id,
                owner_id=owner_id,
                owner_token=owner_token,
                lease_expires_at=lease_expires_at,
            )

    def _require_acquired(
        self,
        *,
        result: AttemptLeaseResult,
        attempt_id: str,
        run_id: str,
    ) -> AttemptOwnerContext:
        """把 acquire 失败映射为 :class:`AttemptFencingError`。

        :param result: store 层返回的 typed lease 结果。
        :param attempt_id: 新 attempt id, 仅用于 error 字段。
        :param run_id: Run id, 仅用于 error 字段。
        :returns: ACQUIRED 时返回非空 :class:`AttemptOwnerContext`。
        :raises AttemptFencingError: 非 ACQUIRED 决策时抛出。
        """

        if (
            result.decision is AttemptLeaseDecision.ACQUIRED
            and result.owner_context is not None
        ):
            return result.owner_context
        reason = (
            result.reason
            if result.reason is not None
            else AttemptFencingReason.STORAGE_CONFLICT
        )
        _LOGGER.warning(
            "host.attempt.lease_acquire_failed run_id=%s attempt_id=%s "
            "decision=%s reason=%s current_owner_id=%s",
            run_id,
            attempt_id,
            result.decision.value,
            reason.value,
            result.current_owner_id,
        )
        raise AttemptFencingError(
            attempt_id=attempt_id,
            run_id=run_id,
            reason=reason,
            current_state=result.current_state,
            owner_id=result.current_owner_id,
            fencing_token=result.current_fencing_token,
        )

    async def _renew_loop(self, *, session: _LeaseSession) -> None:
        """周期 renew 当前 lease, 失败 / fenced / storage error 后立即停止。

        每轮先 sleep ``renew_interval``, 然后在事务内调用
        :meth:`AttemptLeaseStore.renew`。``ACQUIRED`` 替换 session 内的
        owner_context(刷新 lease_expires_at); ``FENCED`` / ``TERMINAL``
        / ``BUSY`` 通过 :meth:`_mark_owner_lost` 标记 session 失活并退出
        循环。renew 自身抛出非 ``CancelledError`` 异常时, 同样调用
        :meth:`_mark_owner_lost` 以独立的 ``STORAGE_ERROR`` loss reason
        收口, 不被伪装成 fencing。

        异常处理:

        - :class:`asyncio.CancelledError`: 由 lease_context 退出路径主
          动取消 task; 不视为 fence。
        - 其它异常: 通过 :meth:`_mark_owner_lost` 置 ``STORAGE_ERROR``
          loss reason, owner-lost signal set; 异常不向上抛, 但通过
          masked ERROR 日志和 session 状态暴露。

        :param session: 当前 lease session。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常 (storage 异常被吞并通过 session
            状态 + ERROR 日志暴露)。
        """

        interval_seconds = (
            self.lease_config.renew_interval.total_seconds()
        )
        try:
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                except asyncio.CancelledError:
                    raise
                if session.loss_reason is not None:
                    return
                new_expiry = self._compute_lease_expiry()
                try:
                    async with self.storage.transaction() as tx:
                        result = self.lease_store.renew(
                            tx=tx,
                            owner_context=session.owner_context,
                            lease_expires_at=new_expiry,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    # storage error: 不是 fencing, 但 owner 不能再继续
                    # 续约。按 STORAGE_ERROR 收口, 不让 task 静默 failed。
                    _LOGGER.error(
                        "host.attempt.lease_renew_storage_error "
                        "attempt_id=%s owner_id=%s owner_token=%s "
                        "fencing_token=%s exc_type=%s",
                        session.owner_context.attempt_id,
                        session.owner_context.owner_id,
                        session.owner_context.owner_token.masked(),
                        session.owner_context.fencing_token.value,
                        type(exc).__name__,
                    )
                    self._mark_owner_lost(
                        session=session,
                        loss_reason=AttemptOwnerLossReason.STORAGE_ERROR,
                        fence_reason=None,
                    )
                    return
                if (
                    result.decision is AttemptLeaseDecision.ACQUIRED
                    and result.owner_context is not None
                ):
                    session.owner_context = result.owner_context
                    _LOGGER.debug(
                        "host.attempt.lease_renewed attempt_id=%s "
                        "owner_id=%s owner_token=%s fencing_token=%s "
                        "lease_expires_at=%s",
                        session.owner_context.attempt_id,
                        session.owner_context.owner_id,
                        session.owner_context.owner_token.masked(),
                        session.owner_context.fencing_token.value,
                        new_expiry.isoformat(),
                    )
                    continue
                reason = (
                    result.reason
                    if result.reason is not None
                    else AttemptFencingReason.STORAGE_CONFLICT
                )
                _LOGGER.warning(
                    "host.attempt.lease_renew_fenced attempt_id=%s "
                    "owner_id=%s owner_token=%s fencing_token=%s "
                    "decision=%s reason=%s",
                    session.owner_context.attempt_id,
                    session.owner_context.owner_id,
                    session.owner_context.owner_token.masked(),
                    session.owner_context.fencing_token.value,
                    result.decision.value,
                    reason.value,
                )
                self._mark_owner_lost(
                    session=session,
                    loss_reason=AttemptOwnerLossReason.FENCED,
                    fence_reason=reason,
                )
                return
        except asyncio.CancelledError:
            return
        finally:
            session.stopped_event.set()

    def _mark_owner_lost(
        self,
        *,
        session: _LeaseSession,
        loss_reason: AttemptOwnerLossReason,
        fence_reason: AttemptFencingReason | None,
    ) -> None:
        """把 owner 置为已失活并 set owner-lost signal。

        二次调用 (例如已经 fenced 后又遇到 storage error) 不会回退已有
        loss_reason; 第一次置位的 reason 即为最终 reason, 这与 store
        层 CAS 真源相符。

        :param session: 当前 lease session。
        :param loss_reason: typed loss reason。
        :param fence_reason: store 层 fencing reason; 仅 FENCED 时填充。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        if session.loss_reason is None:
            session.loss_reason = loss_reason
            session.fence_reason = fence_reason
        if not session.owner_lost_event.is_set():
            session.owner_lost_event.set()

    async def _stop_session(
        self,
        *,
        session: _LeaseSession,
        attempt_id: str,
    ) -> None:
        """取消 renew task 并清理 session 注册。

        无论 renew task 是否已 done, 都会读取其 ``exception()`` 一次,
        防止静默丢失非取消异常。已 done 但 storage error 路径未自我收口
        的极端情况下, 这里仍记录 masked ERROR 日志并 set owner-lost
        signal, 与 :meth:`_renew_loop` 的 storage error 分支一致。

        :param session: 待停止的 lease session。
        :param attempt_id: 当前 attempt id, 用于 ``_sessions`` 去注册。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常; 取消失败仅记录日志。
        """

        renew_task = session.renew_task
        if renew_task is not None:
            if not renew_task.done():
                renew_task.cancel()
                try:
                    await renew_task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error(
                        "host.attempt.lease_renew_task_failed "
                        "attempt_id=%s owner_id=%s owner_token=%s "
                        "fencing_token=%s exc_type=%s",
                        session.owner_context.attempt_id,
                        session.owner_context.owner_id,
                        session.owner_context.owner_token.masked(),
                        session.owner_context.fencing_token.value,
                        type(exc).__name__,
                    )
                    self._mark_owner_lost(
                        session=session,
                        loss_reason=AttemptOwnerLossReason.STORAGE_ERROR,
                        fence_reason=None,
                    )
            else:
                # 已 done 的 task: 仍要读取 exception, 不允许"task
                # exception was never retrieved" 静默吃掉 storage error。
                exc = renew_task.exception()
                if exc is not None and not isinstance(
                    exc, asyncio.CancelledError
                ):
                    _LOGGER.error(
                        "host.attempt.lease_renew_task_failed "
                        "attempt_id=%s owner_id=%s owner_token=%s "
                        "fencing_token=%s exc_type=%s",
                        session.owner_context.attempt_id,
                        session.owner_context.owner_id,
                        session.owner_context.owner_token.masked(),
                        session.owner_context.fencing_token.value,
                        type(exc).__name__,
                    )
                    self._mark_owner_lost(
                        session=session,
                        loss_reason=AttemptOwnerLossReason.STORAGE_ERROR,
                        fence_reason=None,
                    )
        # 等待 renew loop finally 把 stopped_event 置位; renew loop 退
        # 出后 stopped_event 一定 set, 这里只是防御性等待。
        if not session.stopped_event.is_set():
            session.stopped_event.set()
        # lease_context 退出: 任何还未 set 的 owner-lost signal 都视作
        # owner 已不再 active, set 后调用方 wait_owner_lost 立即返回。
        if not session.owner_lost_event.is_set():
            session.owner_lost_event.set()
            if session.loss_reason is None:
                session.loss_reason = AttemptOwnerLossReason.FENCED
        existing = self._sessions.get(attempt_id)
        if existing is session:
            del self._sessions[attempt_id]

    def _compute_lease_expiry(self) -> datetime:
        """按 ``clock.now() + lease_config.ttl`` 计算新的 lease 到期。

        :returns: timezone-aware UTC ``lease_expires_at``。
        :raises Exception: 不主动抛出异常。
        """

        return self.clock.now() + self.lease_config.ttl


__all__ = [
    "AttemptOwnerLossReason",
    "AttemptScopedRunEventAppender",
    "AttemptSupervisor",
]
