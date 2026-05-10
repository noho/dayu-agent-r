"""Host P6/P8 Run / Attempt minimal state stores.

本模块在 ``HostStorage`` 之上提供 Run / Attempt 最小持久状态的查询协议
与实现。写入入口必须经由 :class:`HostStorageTransaction`，写入与
EventLog append 共享同一事务。

P6 不实现 admission、owner lease、fencing、orphan recovery；P8-S1 在
``host_attempts`` 上扩展 owner / lease 字段并新增 :class:`AttemptLeaseStore`
的 CAS acquire / renew / verify 基础，本 slice 不接入
:class:`LocalRunHarness` 主执行路径，也不实现 recovery scan / terminal
event position 原子 close。
"""

from __future__ import annotations

import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from dayu.contracts import JsonValue
from dayu.engine import FinishReason, RunResumeHint
from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptFencingReason,
    AttemptLeaseDecision,
    AttemptLeaseResult,
    AttemptOwnerContext,
    AttemptOwnerToken,
    AttemptRecoveryAction,
    AttemptRecoveryDecision,
    UtcClock,
)
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import (
    AttemptRecord,
    AttemptState,
    ExtendedRunState,
    FencingToken,
    GlobalEventPosition,
    RunRecord,
)
from dayu.host.contracts import (
    RunCancelledResult,
    RunEventCursor,
    RunFailedResult,
    RunResult,
    RunSucceededResult,
    RunSuspendedResult,
)


_ATTEMPT_CAS_TERMINAL_STATES: frozenset[AttemptState] = frozenset(
    {
        AttemptState.SUCCEEDED,
        AttemptState.FAILED,
        AttemptState.CANCELLED,
        AttemptState.SUSPENDED,
        AttemptState.STALE,
        AttemptState.LOST,
    }
)
"""fencing 诊断用终态集合：``_diagnose_fence`` 判断 attempt 是否已 terminal。"""


_ATTEMPT_CLOSE_TERMINAL_VALID_STATES: frozenset[AttemptState] = frozenset(
    {
        AttemptState.SUCCEEDED,
        AttemptState.FAILED,
        AttemptState.CANCELLED,
        AttemptState.SUSPENDED,
        AttemptState.LOST,
    }
)
"""``close_terminal`` 接受的终态集合：不含 ``STALE``（STALE 走 ``mark_stale_or_lost``）。"""


_ATTEMPT_FINISHED_STATES: frozenset[AttemptState] = frozenset(
    {
        AttemptState.SUCCEEDED,
        AttemptState.FAILED,
        AttemptState.CANCELLED,
        AttemptState.SUSPENDED,
        AttemptState.STALE,
        AttemptState.LOST,
    }
)
"""会写入 ``finished_at`` 的状态集合：含正常终态与 owner 收口诊断态。"""


_ATTEMPT_SELECT_COLUMNS: str = (
    "attempt_id, run_id, attempt_index, state, started_at, finished_at, "
    "terminal_event_position, failure_summary, owner_id, owner_token_hash, "
    "fencing_token, lease_expires_at, lease_renewed_at, "
    "recovered_from_attempt_id, stale_marked_at"
)


_FENCING_TOKEN_RESOURCE_TYPE_ATTEMPT: str = "attempt"
"""``host_fencing_tokens.resource_type`` 用于 attempt owner lease。"""


_ATTEMPT_INDEX_UNIQUE_CONSTRAINT_MARKERS: tuple[str, ...] = (
    "host_attempts.run_id, host_attempts.attempt_index",
    "host_attempts.attempt_index, host_attempts.run_id",
)
"""SQLite ``UNIQUE(run_id, attempt_index)`` 冲突的命名 constraint marker。

SQLite 在 ``IntegrityError`` 消息里携带涉及的 constraint 列名 (例如
``UNIQUE constraint failed: host_attempts.run_id, host_attempts.attempt_index``);
acquire 路径只接受 ``(run_id, attempt_index)`` 业务级冲突映射为 BUSY,
其它 ``IntegrityError`` (PRIMARY KEY 碰撞 / 其它 schema 约束) 必须透
传, 避免被伪装成 BUSY 后让上层走错收口路径。这里用集中的 marker 元组
代替散落在业务逻辑里的字面量字符串, 便于审计与测试覆盖。"""


def _is_attempt_index_unique_violation(exc: sqlite3.IntegrityError) -> bool:
    """判断 ``IntegrityError`` 是否由 ``UNIQUE(run_id, attempt_index)`` 触发。

    通过 SQLite 错误消息中的 constraint 列描述匹配。其它
    ``IntegrityError`` (例如 PRIMARY KEY ``attempt_id`` 碰撞) 不属于业务
    级 BUSY 语义, 必须透传给调用方。

    :param exc: SQLite 抛出的 :class:`sqlite3.IntegrityError`。
    :returns: 是 ``(run_id, attempt_index)`` UNIQUE 冲突时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    message = str(exc)
    return any(
        marker in message
        for marker in _ATTEMPT_INDEX_UNIQUE_CONSTRAINT_MARKERS
    )


_RECOVERY_REASON_LEASE_EXPIRED: str = "recovery_lease_expired"
"""recovery 原因: 候选为 ``RUNNING`` 且 lease 已过期; 由 recovery 直接 LOST。"""

_RECOVERY_REASON_CREATED_ORPHAN: str = "recovery_created_orphan"
"""recovery 原因: 候选为 ``CREATED`` 孤儿 (lease 字段为 ``NULL``); LOST 收口。"""

_RECOVERY_REASON_RUN_TERMINAL: str = "recovery_run_terminal"
"""recovery 原因: run 已 terminal, 旧 attempt 标记为 LOST 不再创建 recovery。"""

_RECOVERY_REASON_NOOP_TERMINAL: str = "attempt_already_terminal"
"""recovery 原因: 旧 attempt 已经是 terminal 状态, 无需再处理。"""

_RECOVERY_REASON_CAS_LOST: str = "cas_failed_lost"
"""recovery 原因: CAS 失败, 旧 attempt 由本进程标记为 LOST 收口。"""

_RECOVERY_REASON_CAS_NOOP: str = "cas_failed_noop"
"""recovery 原因: CAS 失败, 当前行已被其他进程推进到 terminal/recovering。"""

_RECOVERY_REASON_MARK_STALE: str = "marked_stale"
"""recovery 原因: 显式 STALE 诊断, 不创建 recovery attempt。"""

_RUN_TERMINAL_STATES: frozenset[str] = frozenset(
    {
        ExtendedRunState.SUCCEEDED.value,
        ExtendedRunState.FAILED.value,
        ExtendedRunState.CANCELLED.value,
        ExtendedRunState.SUSPENDED.value,
        ExtendedRunState.LOST_DIAGNOSTIC.value,
    }
)
"""run 级 terminal 状态字面量集合, 用于 recovery scan 判断 run 是否已收口。"""


@dataclass(slots=True)
class RunStateStore:
    """Run minimal state durable 查询/写入入口。

    :param storage: 共享 :class:`HostStorage`。
    """

    storage: HostStorage

    def get(self, run_id: str) -> RunRecord | None:
        """读取指定 run 的最小状态。

        :param run_id: Run id。
        :returns: :class:`RunRecord`；不存在为 ``None``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT run_id, session_id, state, created_at, updated_at,
                terminal_sequence, terminal_event_position, result_payload
            FROM host_runs WHERE run_id = ?
            """,
            (run_id,),
        )
        if not rows:
            return None
        return _row_to_run_record(rows[0])

    def list_runs(self) -> tuple[RunRecord, ...]:
        """列出全部 run 最小状态，便于诊断。

        :returns: RunRecord 元组。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT run_id, session_id, state, created_at, updated_at,
                terminal_sequence, terminal_event_position, result_payload
            FROM host_runs ORDER BY created_at ASC
            """
        )
        return tuple(_row_to_run_record(row) for row in rows)

    def write_terminal_result(
        self,
        *,
        tx: HostStorageTransaction,
        run_id: str,
        result: RunResult,
    ) -> None:
        """在事务内写入 terminal RunResult snapshot。

        :param tx: 当前事务。
        :param run_id: Run id。
        :param result: 终态 RunResult。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        payload = json.dumps(_encode_run_result(result), ensure_ascii=False)
        tx.execute(
            "UPDATE host_runs SET result_payload = ? WHERE run_id = ?",
            (payload, run_id),
        )

    def get_terminal_result(self, run_id: str) -> RunResult | None:
        """读取 terminal RunResult snapshot。

        :param run_id: Run id。
        :returns: :class:`RunResult`；未写入返回 ``None``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        :raises ValueError: payload 解码失败时抛出。
        """

        rows = self.storage.execute_read(
            "SELECT result_payload FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        if not rows:
            return None
        raw = rows[0][0]
        if raw is None:
            return None
        return _decode_run_result(json.loads(raw))


@dataclass(slots=True)
class AttemptStateStore:
    """Attempt minimal state durable 查询/写入入口。

    本 store 只承载 P6 legacy 非 owner-aware 路径 (``is_durable=False`` 或
    显式的 P6 兼容测试场景), 不参与 P8 fencing CAS。但 ``started_at`` /
    ``finished_at`` 时间戳必须与 fencing 路径共用同一注入时间源, 以保证
    `_FakeClock` 之类的可注入 clock 在 legacy 测试场景下也能稳定断言时间
    字段。clock 的注入是 strict requirement, 不允许通过 ``datetime.now``
    退化成隐式系统墙钟。

    :param storage: 共享 :class:`HostStorage`。
    :param clock: 注入的 UTC clock; 用于生成 ``started_at`` 与诊断/终态
        ``finished_at``。
    """

    storage: HostStorage
    clock: UtcClock

    def create(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
    ) -> AttemptRecord:
        """在事务内创建 attempt 最小记录。

        :param tx: 当前事务。
        :param attempt_id: 新 attempt id。
        :param run_id: Run id。
        :param attempt_index: 同一 run 内 attempt 序号。
        :returns: 新建的 :class:`AttemptRecord`。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        now = self.clock.now()
        tx.execute(
            """
            INSERT INTO host_attempts (
                attempt_id, run_id, attempt_index, state, started_at,
                finished_at, terminal_event_position, failure_summary,
                owner_id, owner_token_hash, fencing_token,
                lease_expires_at, lease_renewed_at,
                recovered_from_attempt_id, stale_marked_at
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL,
                NULL, NULL, NULL, NULL, NULL, NULL, NULL)
            """,
            (
                attempt_id,
                run_id,
                attempt_index,
                AttemptState.CREATED.value,
                now.isoformat(),
            ),
        )
        return AttemptRecord(
            attempt_id=attempt_id,
            run_id=run_id,
            attempt_index=attempt_index,
            state=AttemptState.CREATED,
            started_at=now,
            finished_at=None,
            terminal_event_position=None,
            failure_summary=None,
            owner_id=None,
            owner_token_hash=None,
            fencing_token=None,
            lease_expires_at=None,
            lease_renewed_at=None,
            recovered_from_attempt_id=None,
            stale_marked_at=None,
        )

    def update_state(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        state: AttemptState,
        terminal_event_position: GlobalEventPosition | None = None,
        failure_summary: str | None = None,
    ) -> None:
        """在事务内推进 attempt 状态。

        本方法是 P6/P7 主路径的非 owner-aware 通道；P8-S1 仅扩展状态枚
        举到 ``STALE`` / ``LOST``，但不在此方法上加 owner CAS。owner-
        aware CAS 推进由 :class:`AttemptLeaseStore` 承载，并在后续 slice
        接入 harness 主路径。

        :param tx: 当前事务。
        :param attempt_id: attempt id。
        :param state: 新状态。
        :param terminal_event_position: terminal 事件全局位置；非 terminal 为
            ``None``。
        :param failure_summary: 失败摘要；非失败为 ``None``。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        finished_at_iso = (
            self.clock.now().isoformat()
            if state in _ATTEMPT_FINISHED_STATES
            else None
        )
        tx.execute(
            """
            UPDATE host_attempts SET state = ?, finished_at = ?,
                terminal_event_position = ?, failure_summary = ?
            WHERE attempt_id = ?
            """,
            (
                state.value,
                finished_at_iso,
                None if terminal_event_position is None
                else terminal_event_position.value,
                failure_summary,
                attempt_id,
            ),
        )

    def get(self, attempt_id: str) -> AttemptRecord | None:
        """读取 attempt 最小记录。

        :param attempt_id: attempt id。
        :returns: :class:`AttemptRecord`；不存在为 ``None``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            f"SELECT {_ATTEMPT_SELECT_COLUMNS} FROM host_attempts "
            "WHERE attempt_id = ?",
            (attempt_id,),
        )
        if not rows:
            return None
        return _row_to_attempt_record(rows[0])

    def list_for_run(self, run_id: str) -> tuple[AttemptRecord, ...]:
        """列出某个 run 下全部 attempt。

        :param run_id: Run id。
        :returns: AttemptRecord 元组。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            f"SELECT {_ATTEMPT_SELECT_COLUMNS} FROM host_attempts "
            "WHERE run_id = ? ORDER BY attempt_index ASC",
            (run_id,),
        )
        return tuple(_row_to_attempt_record(row) for row in rows)


@dataclass(slots=True)
class AttemptLeaseStore:
    """Attempt owner lease 的 CAS 写入入口。

    本 store 不持有 :class:`AttemptLeaseConfig`，也不自行计算 TTL；调用
    方（supervisor / 装配层）必须传入已经计算好的 ``lease_expires_at``
    UTC 时刻。``clock`` 仅用于在 WHERE 子句里取 ``now`` 与 fencing 判断
    时间，store 不在此处生成 lease 截止时刻。

    fencing 真源是全局严格单调递增的 :class:`FencingToken`：每次
    :meth:`acquire_new_attempt` 在同一 ``BEGIN IMMEDIATE`` 事务内先向
    ``host_fencing_tokens`` 表插入一行获取新 token，再 INSERT
    ``host_attempts`` 写入 owner 凭据；CAS / fencing 判断只用
    ``fencing_token``，不再使用 per-attempt counter，不复用 owner secret。
    允许 token gap（acquire 冲突回滚），禁止 token 倒退或复用。

    SQL 关键 CAS 条件：

    - acquire 新 attempt：在事务内 INSERT ``host_fencing_tokens`` -> 取新
      ``FencingToken`` -> INSERT ``host_attempts`` ``state='running'``、
      ``fencing_token=<new>``。``UNIQUE(run_id, attempt_index)`` 冲突 ->
      ``BUSY``。
    - renew：``UPDATE ... WHERE attempt_id=? AND state='running' AND
      owner_token_hash=? AND fencing_token=? AND lease_expires_at > now``。
      ``rowcount == 0`` 必须映射成 typed :class:`AttemptLeaseResult` 或
      :class:`AttemptFencingError`，禁止抛裸 SQLite 错误。
    - verify owner：与 renew 相同 WHERE，但不更新；命中失败抛
      :class:`AttemptFencingError`。

    所有时间使用 timezone-aware UTC，由 :class:`UtcClock` 注入；明文
    owner token 不写入数据库，只写 :meth:`AttemptOwnerToken.digest`。

    :param storage: 共享 :class:`HostStorage`。
    :param clock: 可注入 UTC clock，用于 fencing 时间判断。
    """

    storage: HostStorage
    clock: UtcClock

    def acquire_new_attempt(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None,
        owner_id: str,
        owner_token: AttemptOwnerToken,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        """在事务内创建并 acquire 新 attempt 的 owner lease。

        在同一事务内先分配新的全局 :class:`FencingToken`，再 INSERT
        ``host_attempts`` 写入 owner 凭据；``UNIQUE(run_id, attempt_index)``
        冲突时返回 ``AttemptLeaseResult(decision=BUSY)``，调用方不得回退
        到复用旧 attempt（recovery 必须使用新的 ``attempt_index`` /
        ``attempt_id`` 并重新分配 fencing token）。

        其它 :class:`sqlite3.IntegrityError` (例如 PRIMARY KEY
        ``attempt_id`` 碰撞或将来新增的 schema 约束) 不属于 BUSY 业务语
        义, 直接透传给调用方, 避免被伪装成 ``(run_id, attempt_index)``
        冲突导致诊断 payload 描述到错误的 attempt 行。

        :param tx: 当前事务。
        :param attempt_id: 新 attempt id。
        :param run_id: Run id。
        :param attempt_index: 新 attempt 序号；与已有 attempt 冲突时
            BUSY。
        :param recovered_from_attempt_id: 若是 recovery attempt，记录被恢
            复的旧 attempt id；非 recovery 路径为 ``None``。
        :param owner_id: 新 owner 诊断 id。
        :param owner_token: 新 owner secret token；明文不入库。
        :param lease_expires_at: 由调用方按 ``AttemptLeaseConfig`` 计算
            的 lease 到期 UTC 时刻；必须 timezone-aware。
        :returns: ``AttemptLeaseResult``。
        :raises ValueError: ``lease_expires_at`` 非 timezone-aware 时抛出。
        :raises sqlite3.DatabaseError: 非冲突 SQLite 错误时透传。
        """

        _require_aware(lease_expires_at, "lease_expires_at")
        now = self.clock.now()
        owner_hash = owner_token.digest()
        fencing_token = self._allocate_fencing_token(
            tx=tx,
            resource_id=attempt_id,
            owner_id=owner_id,
            now=now,
        )
        try:
            tx.execute(
                """
                INSERT INTO host_attempts (
                    attempt_id, run_id, attempt_index, state, started_at,
                    finished_at, terminal_event_position, failure_summary,
                    owner_id, owner_token_hash, fencing_token,
                    lease_expires_at, lease_renewed_at,
                    recovered_from_attempt_id, stale_marked_at
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL,
                    ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    attempt_id,
                    run_id,
                    attempt_index,
                    AttemptState.RUNNING.value,
                    now.isoformat(),
                    owner_id,
                    owner_hash,
                    fencing_token.value,
                    lease_expires_at.isoformat(),
                    now.isoformat(),
                    recovered_from_attempt_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if not _is_attempt_index_unique_violation(exc):
                # 非预期 IntegrityError (例如 PRIMARY KEY ``attempt_id``
                # 碰撞或新增 schema 约束) 不属于 BUSY 业务语义, 透传给
                # 上层, 避免诊断 payload 描述错误的 attempt 行。
                raise
            # fencing token 已经分配给冲突的 acquire 失败路径；按设计
            # 允许 token gap，不回收、不复用。
            return self._build_busy_result(
                tx=tx, run_id=run_id, attempt_index=attempt_index
            )
        return AttemptLeaseResult(
            decision=AttemptLeaseDecision.ACQUIRED,
            owner_context=AttemptOwnerContext(
                attempt_id=attempt_id,
                run_id=run_id,
                attempt_index=attempt_index,
                owner_id=owner_id,
                owner_token=owner_token,
                fencing_token=fencing_token,
                lease_expires_at=lease_expires_at,
            ),
            current_state=AttemptState.RUNNING,
            current_owner_id=owner_id,
            lease_expires_at=lease_expires_at,
            reason=None,
            current_fencing_token=fencing_token,
        )

    def renew(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult:
        """在事务内 renew 当前 owner 的 lease。

        CAS 条件：``state='running' AND owner_token_hash=? AND
        fencing_token=? AND lease_expires_at > now``。``rowcount == 0``
        时按当前行状态映射成 ``FENCED`` / ``TERMINAL`` 等 typed result；
        ``fencing_token`` 在 renew 路径上不变（renew 只延长 lease，不切
        owner，不分配新 token）。

        :param tx: 当前事务。
        :param owner_context: 当前 owner 句柄。
        :param lease_expires_at: 新 lease 到期 UTC 时刻；必须 timezone-
            aware 且严格大于当前 ``now``。
        :returns: ``AttemptLeaseResult``；ACQUIRED 时复用同一 fencing
            token 返回更新后的 ``owner_context``。
        :raises ValueError: ``lease_expires_at`` 非 timezone-aware 时抛出。
        """

        _require_aware(lease_expires_at, "lease_expires_at")
        now = self.clock.now()
        cursor = tx.execute(
            """
            UPDATE host_attempts SET lease_expires_at = ?, lease_renewed_at = ?
            WHERE attempt_id = ?
              AND state = ?
              AND owner_token_hash = ?
              AND fencing_token = ?
              AND lease_expires_at > ?
            """,
            (
                lease_expires_at.isoformat(),
                now.isoformat(),
                owner_context.attempt_id,
                AttemptState.RUNNING.value,
                owner_context.owner_token.digest(),
                owner_context.fencing_token.value,
                now.isoformat(),
            ),
        )
        if cursor.rowcount == 1:
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.ACQUIRED,
                owner_context=AttemptOwnerContext(
                    attempt_id=owner_context.attempt_id,
                    run_id=owner_context.run_id,
                    attempt_index=owner_context.attempt_index,
                    owner_id=owner_context.owner_id,
                    owner_token=owner_context.owner_token,
                    fencing_token=owner_context.fencing_token,
                    lease_expires_at=lease_expires_at,
                ),
                current_state=AttemptState.RUNNING,
                current_owner_id=owner_context.owner_id,
                lease_expires_at=lease_expires_at,
                reason=None,
                current_fencing_token=owner_context.fencing_token,
            )
        return self._diagnose_fence(
            tx=tx,
            owner_context=owner_context,
            now=now,
        )

    def update_state_owner_aware(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        failure_summary: str | None,
        terminal_event_position: GlobalEventPosition | None,
    ) -> bool:
        """对 attempt 做 owner-aware 的诊断态 / 终态写入。

        本方法只接受 ``host_attempts`` 当前行 ``state='running' AND
        owner_token_hash=? AND fencing_token=?`` 时才更新; 不要求
        ``lease_expires_at > now``, 因为 owner-aware 诊断 close 路径在
        owner 已被 fenced / lease expired 后仍需要把 attempt 从
        ``RUNNING`` 收口为 STALE / FAILED / LOST 等诊断态。owner_token /
        fencing_token 是真源, 防止 recovery 后被旧 owner 覆盖未来状态。

        本方法是 P8-S3 supervisor diagnostic close 的最小依赖; terminal
        event append 与 ``terminal_event_position`` 的同事务原子写入仍
        归 P8-S4 实现。当 ``terminal_event_position`` 为 ``None`` 时本
        方法只更新 state / finished_at / failure_summary, 不动 terminal
        event position 字段。

        :param tx: 当前事务。
        :param owner_context: 当前 owner 句柄。
        :param state: 期望写入的新状态; 应是诊断态 / 终态枚举之一。
        :param failure_summary: 失败摘要; 成功诊断态可为 ``None``。
        :param terminal_event_position: terminal 事件全局位置; P8-S3 调
            用方应传 ``None``, 终态原子写入归 P8-S4。
        :returns: CAS 命中并写入返回 ``True``; rowcount==0 时返回
            ``False`` (owner 已被替换 / 行已不在 RUNNING 状态)。
        :raises ValueError: ``state`` 不是诊断态 / 终态时抛出。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        if state not in _ATTEMPT_FINISHED_STATES:
            raise ValueError(
                "update_state_owner_aware requires finished AttemptState, "
                f"got {state}"
            )
        finished_at_iso = self.clock.now().isoformat()
        position_value = (
            None if terminal_event_position is None
            else terminal_event_position.value
        )
        cursor = tx.execute(
            """
            UPDATE host_attempts SET state = ?, finished_at = ?,
                terminal_event_position = ?, failure_summary = ?
            WHERE attempt_id = ?
              AND state = ?
              AND owner_token_hash = ?
              AND fencing_token = ?
            """,
            (
                state.value,
                finished_at_iso,
                position_value,
                failure_summary,
                owner_context.attempt_id,
                AttemptState.RUNNING.value,
                owner_context.owner_token.digest(),
                owner_context.fencing_token.value,
            ),
        )
        return cursor.rowcount == 1

    def close_terminal(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        state: AttemptState,
        terminal_event_position: GlobalEventPosition,
        failure_summary: str | None,
    ) -> None:
        """在事务内 owner-aware 地把 attempt 收口到正常 terminal 状态。

        与 :meth:`update_state_owner_aware` 的区别：本方法专用于 P8-S4
        terminal append + close 同事务原子写入路径，CAS 条件包含完整
        ``lease_expires_at > now``，``rowcount == 0`` 立即抛
        :class:`AttemptFencingError` 让外层 ``BEGIN IMMEDIATE`` 事务整体
        回滚——这是确保「fencing 失败时 EventLog 不残留 stale terminal
        RunEvent」语义的关键。``terminal_event_position`` 必须由调用方
        在同一事务内由刚 append 的 terminal RunEvent 提供。

        :param tx: 当前事务。
        :param owner_context: 当前 owner 句柄。
        :param state: 终态枚举之一 (SUCCEEDED/FAILED/CANCELLED/SUSPENDED/LOST)。
        :param terminal_event_position: 同事务内刚追加的 terminal RunEvent
            全局位置。
        :param failure_summary: 失败摘要；成功 / 取消 / 暂停可为 ``None``。
        :returns: 无返回值。
        :raises ValueError: ``state`` 不是合法 terminal 状态时抛出。
        :raises AttemptFencingError: CAS miss 时抛出，由外层事务回滚。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        if state not in _ATTEMPT_CLOSE_TERMINAL_VALID_STATES:
            raise ValueError(
                f"close_terminal requires terminal AttemptState, got {state}"
            )
        now = self.clock.now()
        finished_at_iso = now.isoformat()
        cursor = tx.execute(
            """
            UPDATE host_attempts SET state = ?, finished_at = ?,
                terminal_event_position = ?, failure_summary = ?
            WHERE attempt_id = ?
              AND state = ?
              AND owner_token_hash = ?
              AND fencing_token = ?
              AND lease_expires_at > ?
            """,
            (
                state.value,
                finished_at_iso,
                terminal_event_position.value,
                failure_summary,
                owner_context.attempt_id,
                AttemptState.RUNNING.value,
                owner_context.owner_token.digest(),
                owner_context.fencing_token.value,
                now.isoformat(),
            ),
        )
        if cursor.rowcount == 1:
            return
        result = self._diagnose_fence(
            tx=tx,
            owner_context=owner_context,
            now=now,
        )
        raise AttemptFencingError(
            attempt_id=owner_context.attempt_id,
            run_id=owner_context.run_id,
            reason=(
                result.reason
                if result.reason is not None
                else AttemptFencingReason.OWNER_MISSING
            ),
            current_state=result.current_state,
            owner_id=result.current_owner_id,
            fencing_token=result.current_fencing_token,
        )

    def verify_owner(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
    ) -> None:
        """在事务内校验当前 owner 是否仍持有有效 lease。

        与 :meth:`renew` 共享 WHERE 条件，但只读不更新。失败时根据当前
        行状态抛 :class:`AttemptFencingError`，由调用方决定收口策略。

        :param tx: 当前事务。
        :param owner_context: 当前 owner 句柄。
        :returns: 无返回值。
        :raises AttemptFencingError: owner 失效 / 不匹配 / 已 terminal
            等情形时抛出。
        """

        now = self.clock.now()
        rows = tx.execute(
            """
            SELECT 1 FROM host_attempts
            WHERE attempt_id = ?
              AND state = ?
              AND owner_token_hash = ?
              AND fencing_token = ?
              AND lease_expires_at > ?
            """,
            (
                owner_context.attempt_id,
                AttemptState.RUNNING.value,
                owner_context.owner_token.digest(),
                owner_context.fencing_token.value,
                now.isoformat(),
            ),
        ).fetchall()
        if rows:
            return
        result = self._diagnose_fence(
            tx=tx,
            owner_context=owner_context,
            now=now,
        )
        raise AttemptFencingError(
            attempt_id=owner_context.attempt_id,
            run_id=owner_context.run_id,
            reason=(
                result.reason
                if result.reason is not None
                else AttemptFencingReason.OWNER_MISSING
            ),
            current_state=result.current_state,
            owner_id=result.current_owner_id,
            fencing_token=result.current_fencing_token,
        )

    def list_recovery_candidates(
        self,
        *,
        tx: HostStorageTransaction,
        run_id: str | None,
        now: datetime,
    ) -> tuple[AttemptRecord, ...]:
        """列出需要 recovery 处理的候选 attempt。

        覆盖两类候选:

        - ``state = 'running' AND lease_expires_at IS NOT NULL AND
          lease_expires_at <= now``: 旧 owner lease 过期, 需要 LOST 收口。
        - ``state = 'created' AND lease_expires_at IS NULL``: acquire 失败
          或装配异常留下的孤儿行, owner / fencing token 全为 ``NULL``;
          这类行也必须进入 recovery 收口为 LOST, 否则一直滞留 ``CREATED``
          污染状态机 (P8 D3 / 0830-F2)。

        终态行不会出现在结果中, 避免重复处理。结果按
        ``started_at`` 升序返回, 让 recovery scan 顺序稳定可重放。

        本方法仅提供候选列表; 调用方需在每个候选的独立 ``BEGIN IMMEDIATE``
        短事务内调用 :meth:`mark_stale_or_lost` 收口, 不在本方法的事务内做
        后续 CAS。P8 D2 收口语义: recovery 不再创建 recovery attempt; 旧
        attempt 一律 LOST 或 STALE。

        :param tx: 当前事务。
        :param run_id: 限定 run id; ``None`` 表示扫描全库。
        :param now: 用于 ``lease_expires_at <= now`` 比较的 UTC 时间。
        :returns: 候选 :class:`AttemptRecord` 元组, 可能为空。
        :raises ValueError: ``now`` 非 timezone-aware 时抛出。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        _require_aware(now, "now")
        # 两个 OR 子句严格对应 RUNNING-expired 与 CREATED-orphan 两类
        # 候选, 用括号显式分组避免 SQLite 默认运算符优先级把 ``AND``
        # 错配。
        where_clause = (
            "((state = ? AND lease_expires_at IS NOT NULL "
            "AND lease_expires_at <= ?) "
            "OR (state = ? AND lease_expires_at IS NULL))"
        )
        params: tuple[object, ...]
        if run_id is None:
            sql = (
                f"SELECT {_ATTEMPT_SELECT_COLUMNS} FROM host_attempts "
                f"WHERE {where_clause} "
                "ORDER BY started_at ASC, attempt_id ASC"
            )
            params = (
                AttemptState.RUNNING.value,
                now.isoformat(),
                AttemptState.CREATED.value,
            )
        else:
            sql = (
                f"SELECT {_ATTEMPT_SELECT_COLUMNS} FROM host_attempts "
                f"WHERE run_id = ? AND {where_clause} "
                "ORDER BY started_at ASC, attempt_id ASC"
            )
            params = (
                run_id,
                AttemptState.RUNNING.value,
                now.isoformat(),
                AttemptState.CREATED.value,
            )
        rows = tx.execute(sql, params).fetchall()
        return tuple(_row_to_attempt_record(row) for row in rows)

    def is_run_terminal(
        self,
        *,
        tx: HostStorageTransaction,
        run_id: str,
    ) -> bool:
        """在事务内判断 run 是否已 terminal。

        recovery scan 在 mark recovering / 创建新 attempt 前必须先确认 run
        本身仍是非终态; run 已 terminal 时旧 attempt 应该被标记为
        ``LOST``, 而不是再创建新的 recovery attempt。

        :param tx: 当前事务。
        :param run_id: Run id。
        :returns: run 行不存在 (视为不可恢复) 或处于 terminal 状态返回
            ``True``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        row = tx.execute(
            "SELECT state FROM host_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return True
        return row["state"] in _RUN_TERMINAL_STATES

    def next_attempt_index(
        self,
        *,
        tx: HostStorageTransaction,
        run_id: str,
    ) -> int:
        """返回 run 下一个可用 attempt_index。

        基于 ``MAX(attempt_index) + 1``; 没有任何 attempt 时返回 ``0``。

        :param tx: 当前事务。
        :param run_id: Run id。
        :returns: 下一个 attempt index。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        row = tx.execute(
            "SELECT MAX(attempt_index) AS max_idx FROM host_attempts "
            "WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None or row["max_idx"] is None:
            return 0
        return int(row["max_idx"]) + 1

    def mark_stale_or_lost(
        self,
        *,
        tx: HostStorageTransaction,
        source_attempt_id: str,
        source_fencing_token: FencingToken | None,
        target_state: AttemptState,
        reason: str,
    ) -> AttemptRecoveryDecision:
        """在事务内把旧 attempt 收口到 ``STALE`` / ``LOST`` 诊断态。

        P8 D2: recovery 仅做诊断收口, 不创建新 attempt; 本方法只更新旧
        attempt, 用于 lease 过期 LOST、CREATED 孤儿 LOST、run 已 terminal
        收口、显式 STALE 诊断、CAS 失败兜底等场景。

        CAS 条件: ``None`` token 只匹配孤儿行；非 ``None`` token 必须同时
        命中 ``RUNNING``、同一 fencing token，且 ``lease_expires_at <= now``。
        后者避免 recovery scan 读到过期候选后，合法 owner 已成功 renew
        的竞态里仍把 active attempt 错误收口为 ``LOST``。``rowcount == 0``
        表示当前行已被其他进程推进或 lease 已恢复有效，返回
        ``NOOP_TERMINAL``。

        :param tx: 当前事务。
        :param source_attempt_id: 旧 attempt id。
        :param source_fencing_token: 旧 attempt 持有的 fencing token; 仅
            ``CREATED`` 孤儿行可为 ``None``。
        :param target_state: 期望写入的诊断态; 必须是 ``STALE`` 或 ``LOST``。
        :param reason: 摘要原因, 写入 ``failure_summary``。
        :returns: typed :class:`AttemptRecoveryDecision`, action 为
            ``MARK_STALE`` / ``MARK_LOST`` / ``NOOP_TERMINAL`` (CAS miss)。
        :raises ValueError: ``target_state`` 不是 STALE / LOST 时抛出。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        if target_state not in (AttemptState.STALE, AttemptState.LOST):
            raise ValueError(
                "mark_stale_or_lost requires AttemptState.STALE or LOST"
            )
        now = self.clock.now()
        if source_fencing_token is None:
            cursor = tx.execute(
                """
                UPDATE host_attempts SET state = ?, finished_at = ?,
                    stale_marked_at = ?, failure_summary = ?
                WHERE attempt_id = ?
                  AND state IN (?, ?)
                  AND fencing_token IS NULL
                """,
                (
                    target_state.value,
                    now.isoformat(),
                    now.isoformat(),
                    reason,
                    source_attempt_id,
                    AttemptState.RUNNING.value,
                    AttemptState.CREATED.value,
                ),
            )
        else:
            cursor = tx.execute(
                """
                UPDATE host_attempts SET state = ?, finished_at = ?,
                    stale_marked_at = ?, failure_summary = ?
                WHERE attempt_id = ?
                  AND state = ?
                  AND fencing_token = ?
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= ?
                """,
                (
                    target_state.value,
                    now.isoformat(),
                    now.isoformat(),
                    reason,
                    source_attempt_id,
                    AttemptState.RUNNING.value,
                    source_fencing_token.value,
                    now.isoformat(),
                ),
            )
        if cursor.rowcount != 1:
            return AttemptRecoveryDecision(
                action=AttemptRecoveryAction.NOOP_TERMINAL,
                source_attempt_id=source_attempt_id,
                reason=_RECOVERY_REASON_CAS_NOOP,
            )
        action = (
            AttemptRecoveryAction.MARK_STALE
            if target_state is AttemptState.STALE
            else AttemptRecoveryAction.MARK_LOST
        )
        return AttemptRecoveryDecision(
            action=action,
            source_attempt_id=source_attempt_id,
            reason=reason,
        )

    def _allocate_fencing_token(
        self,
        *,
        tx: HostStorageTransaction,
        resource_id: str,
        owner_id: str,
        now: datetime,
    ) -> FencingToken:
        """在事务内向 ``host_fencing_tokens`` 分配下一个全局 fencing token。

        ``fencing_token`` 列是 ``INTEGER PRIMARY KEY AUTOINCREMENT``，
        SQLite 严格保证全局单调递增；事务回滚时已分配的 token 不被回
        收，下一次 acquire 取得严格更大的值，符合"允许 gap，不允许倒
        退或复用"的契约。

        :param tx: 当前事务。
        :param resource_id: 资源标识；attempt 资源使用 ``attempt_id``。
        :param owner_id: owner 诊断 id。
        :param now: 当前 UTC 时间，用于 ``issued_at``。
        :returns: 新分配的 :class:`FencingToken`。
        :raises RuntimeError: SQLite ``lastrowid`` 缺失或非正时, 表示
            ``host_fencing_tokens`` 严格单调递增不变量被破坏, 立即
            fail-fast。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        cursor = tx.execute(
            """
            INSERT INTO host_fencing_tokens (
                resource_type, resource_id, owner_id, issued_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                _FENCING_TOKEN_RESOURCE_TYPE_ATTEMPT,
                resource_id,
                owner_id,
                now.isoformat(),
            ),
        )
        last_rowid = cursor.lastrowid
        if last_rowid is None or last_rowid < 1:
            raise RuntimeError(
                "host_fencing_tokens INSERT did not yield a positive "
                f"lastrowid (got {last_rowid!r}); fencing token monotonic "
                f"invariant violated for resource_id={resource_id!r}"
            )
        return FencingToken(value=int(last_rowid))

    def _diagnose_fence(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        now: datetime,
    ) -> AttemptLeaseResult:
        """根据当前 row 状态把 CAS 失败映射为 typed 结果。

        :param tx: 当前事务。
        :param owner_context: owner 句柄。
        :param now: fencing 判断使用的 UTC 当前时间。
        :returns: ``AttemptLeaseResult``，永不返回 ``ACQUIRED``。
        """

        row = tx.execute(
            "SELECT state, owner_id, owner_token_hash, fencing_token, "
            "lease_expires_at FROM host_attempts WHERE attempt_id = ?",
            (owner_context.attempt_id,),
        ).fetchone()
        if row is None:
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.FENCED,
                owner_context=None,
                current_state=None,
                current_owner_id=None,
                lease_expires_at=None,
                reason=AttemptFencingReason.OWNER_MISSING,
            )
        state = AttemptState(row["state"])
        current_owner_id = row["owner_id"]
        current_hash = row["owner_token_hash"]
        current_token_raw = row["fencing_token"]
        current_token = (
            None
            if current_token_raw is None
            else FencingToken(value=int(current_token_raw))
        )
        lease_expires_raw = row["lease_expires_at"]
        lease_expires = (
            None
            if lease_expires_raw is None
            else datetime.fromisoformat(lease_expires_raw)
        )

        if state in _ATTEMPT_CAS_TERMINAL_STATES:
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.TERMINAL,
                owner_context=None,
                current_state=state,
                current_owner_id=current_owner_id,
                lease_expires_at=lease_expires,
                reason=AttemptFencingReason.ATTEMPT_TERMINAL,
                current_fencing_token=current_token,
            )
        if state is not AttemptState.RUNNING:
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.FENCED,
                owner_context=None,
                current_state=state,
                current_owner_id=current_owner_id,
                lease_expires_at=lease_expires,
                reason=AttemptFencingReason.ATTEMPT_NOT_RUNNING,
                current_fencing_token=current_token,
            )
        expected_hash = owner_context.owner_token.digest()
        if not isinstance(current_hash, str) or not hmac.compare_digest(
            current_hash,
            expected_hash,
        ):
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.FENCED,
                owner_context=None,
                current_state=state,
                current_owner_id=current_owner_id,
                lease_expires_at=lease_expires,
                reason=AttemptFencingReason.OWNER_MISMATCH,
                current_fencing_token=current_token,
            )
        if (
            current_token is None
            or current_token.value != owner_context.fencing_token.value
        ):
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.FENCED,
                owner_context=None,
                current_state=state,
                current_owner_id=current_owner_id,
                lease_expires_at=lease_expires,
                reason=AttemptFencingReason.FENCING_TOKEN_MISMATCH,
                current_fencing_token=current_token,
            )
        if lease_expires is None or lease_expires <= now:
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.FENCED,
                owner_context=None,
                current_state=state,
                current_owner_id=current_owner_id,
                lease_expires_at=lease_expires,
                reason=AttemptFencingReason.LEASE_EXPIRED,
                current_fencing_token=current_token,
            )
        # 所有显式条件均匹配但仍 rowcount==0；这意味着事务边界外发生了
        # 与本 owner 不一致的写入，按 storage conflict 收口。
        return AttemptLeaseResult(
            decision=AttemptLeaseDecision.FENCED,
            owner_context=None,
            current_state=state,
            current_owner_id=current_owner_id,
            lease_expires_at=lease_expires,
            reason=AttemptFencingReason.STORAGE_CONFLICT,
            current_fencing_token=current_token,
        )

    def _build_busy_result(
        self,
        *,
        tx: HostStorageTransaction,
        run_id: str,
        attempt_index: int,
    ) -> AttemptLeaseResult:
        """``UNIQUE(run_id, attempt_index)`` 冲突时构造 BUSY 结果。

        :param tx: 当前事务。
        :param run_id: Run id。
        :param attempt_index: 冲突的 attempt index。
        :returns: ``AttemptLeaseResult(decision=BUSY)``，附带库内当前
            owner 摘要。
        """

        row = tx.execute(
            "SELECT state, owner_id, fencing_token, lease_expires_at "
            "FROM host_attempts "
            "WHERE run_id = ? AND attempt_index = ?",
            (run_id, attempt_index),
        ).fetchone()
        if row is None:
            return AttemptLeaseResult(
                decision=AttemptLeaseDecision.BUSY,
                owner_context=None,
                current_state=None,
                current_owner_id=None,
                lease_expires_at=None,
                reason=AttemptFencingReason.STORAGE_CONFLICT,
            )
        lease_raw = row["lease_expires_at"]
        fencing_token_raw = row["fencing_token"]
        return AttemptLeaseResult(
            decision=AttemptLeaseDecision.BUSY,
            owner_context=None,
            current_state=AttemptState(row["state"]),
            current_owner_id=row["owner_id"],
            lease_expires_at=(
                None if lease_raw is None else datetime.fromisoformat(lease_raw)
            ),
            current_fencing_token=(
                None
                if fencing_token_raw is None
                else FencingToken(value=int(fencing_token_raw))
            ),
            reason=None,
        )


def _require_aware(value: datetime, name: str) -> None:
    """校验 datetime 必须 timezone-aware。

    :param value: 待校验的 datetime。
    :param name: 字段名，用于错误消息。
    :returns: 无返回值。
    :raises ValueError: 缺少 tzinfo 时抛出。
    """

    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC datetime")


def _row_to_run_record(row: sqlite3.Row) -> RunRecord:
    """SQLite 行转换为 :class:`RunRecord`。

    :param row: sqlite3.Row 对象。
    :returns: RunRecord。
    :raises ValueError: state 非法时抛出。
    """

    return RunRecord(
        run_id=row["run_id"],  # type: ignore[index]
        session_id=row["session_id"],  # type: ignore[index]
        state=ExtendedRunState(row["state"]),  # type: ignore[index]
        created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
        updated_at=datetime.fromisoformat(row["updated_at"]),  # type: ignore[index]
        terminal_event_cursor=(
            None if row["terminal_sequence"] is None  # type: ignore[index]
            else RunEventCursor(sequence=int(row["terminal_sequence"]))  # type: ignore[index]
        ),
        terminal_event_position=(
            None if row["terminal_event_position"] is None  # type: ignore[index]
            else GlobalEventPosition(value=int(row["terminal_event_position"]))  # type: ignore[index]
        ),
        result=(
            None if row["result_payload"] is None  # type: ignore[index]
            else _decode_run_result(json.loads(row["result_payload"]))  # type: ignore[index]
        ),
    )


def _row_to_attempt_record(row: sqlite3.Row) -> AttemptRecord:
    """SQLite 行转换为 :class:`AttemptRecord`。

    :param row: sqlite3.Row。
    :returns: AttemptRecord。
    :raises ValueError: state 非法时抛出。
    """

    return AttemptRecord(
        attempt_id=row["attempt_id"],  # type: ignore[index]
        run_id=row["run_id"],  # type: ignore[index]
        attempt_index=int(row["attempt_index"]),  # type: ignore[index]
        state=AttemptState(row["state"]),  # type: ignore[index]
        started_at=datetime.fromisoformat(row["started_at"]),  # type: ignore[index]
        finished_at=(
            None if row["finished_at"] is None  # type: ignore[index]
            else datetime.fromisoformat(row["finished_at"])  # type: ignore[index]
        ),
        terminal_event_position=(
            None if row["terminal_event_position"] is None  # type: ignore[index]
            else GlobalEventPosition(value=int(row["terminal_event_position"]))  # type: ignore[index]
        ),
        failure_summary=row["failure_summary"],  # type: ignore[index]
        owner_id=row["owner_id"],  # type: ignore[index]
        owner_token_hash=row["owner_token_hash"],  # type: ignore[index]
        fencing_token=(
            None if row["fencing_token"] is None  # type: ignore[index]
            else FencingToken(value=int(row["fencing_token"]))  # type: ignore[index]
        ),
        lease_expires_at=(
            None if row["lease_expires_at"] is None  # type: ignore[index]
            else datetime.fromisoformat(row["lease_expires_at"])  # type: ignore[index]
        ),
        lease_renewed_at=(
            None if row["lease_renewed_at"] is None  # type: ignore[index]
            else datetime.fromisoformat(row["lease_renewed_at"])  # type: ignore[index]
        ),
        recovered_from_attempt_id=row["recovered_from_attempt_id"],  # type: ignore[index]
        stale_marked_at=(
            None if row["stale_marked_at"] is None  # type: ignore[index]
            else datetime.fromisoformat(row["stale_marked_at"])  # type: ignore[index]
        ),
    )


_SUCCESS_KIND: str = "succeeded"
_FAILED_KIND: str = "failed"
_CANCELLED_KIND: str = "cancelled"
_SUSPENDED_KIND: str = "suspended"


def _encode_run_result(result: RunResult) -> dict[str, JsonValue]:
    """将 RunResult 编码为 JSON 字典。

    :param result: terminal RunResult。
    :returns: JSON 字典。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(result, RunSucceededResult):
        return {
            "kind": _SUCCESS_KIND,
            "run_id": result.run_id,
            "session_id": result.session_id,
            "content": result.content,
            "filtered": result.filtered,
            "degraded": result.degraded,
            "finish_reason": result.finish_reason.value,
            "terminal_sequence": result.terminal_event_cursor.sequence,
        }
    if isinstance(result, RunFailedResult):
        return {
            "kind": _FAILED_KIND,
            "run_id": result.run_id,
            "session_id": result.session_id,
            "error_code": result.error_code,
            "message": result.message,
            "recoverable": result.recoverable,
            "terminal_sequence": result.terminal_event_cursor.sequence,
        }
    if isinstance(result, RunCancelledResult):
        return {
            "kind": _CANCELLED_KIND,
            "run_id": result.run_id,
            "session_id": result.session_id,
            "reason": result.reason,
            "terminal_sequence": result.terminal_event_cursor.sequence,
        }
    return {
        "kind": _SUSPENDED_KIND,
        "run_id": result.run_id,
        "session_id": result.session_id,
        "reason": result.reason,
        "resume_hint": (
            None if result.resume_hint is None else result.resume_hint.message
        ),
        "terminal_sequence": result.terminal_event_cursor.sequence,
    }


def _decode_run_result(payload: JsonValue) -> RunResult:
    """将 JSON 字典还原为 RunResult。

    :param payload: JSON 字典。
    :returns: RunResult。
    :raises ValueError: 字段非法或 kind 未知时抛出。
    """

    if not isinstance(payload, dict):
        raise ValueError("invalid run_result payload")
    kind = payload.get("kind")
    sequence_raw = payload.get("terminal_sequence")
    if not isinstance(sequence_raw, int) or isinstance(sequence_raw, bool):
        raise ValueError("invalid terminal_sequence")
    cursor = RunEventCursor(sequence=sequence_raw)
    if kind == _SUCCESS_KIND:
        return RunSucceededResult(
            run_id=_must_str(payload.get("run_id")),
            session_id=_must_str(payload.get("session_id")),
            content=_must_str(payload.get("content")),
            filtered=_must_bool(payload.get("filtered")),
            degraded=_must_bool(payload.get("degraded")),
            finish_reason=FinishReason(_must_str(payload.get("finish_reason"))),
            terminal_event_cursor=cursor,
        )
    if kind == _FAILED_KIND:
        return RunFailedResult(
            run_id=_must_str(payload.get("run_id")),
            session_id=_must_str(payload.get("session_id")),
            error_code=_must_str(payload.get("error_code")),
            message=_must_str(payload.get("message")),
            recoverable=_must_bool(payload.get("recoverable")),
            terminal_event_cursor=cursor,
        )
    if kind == _CANCELLED_KIND:
        return RunCancelledResult(
            run_id=_must_str(payload.get("run_id")),
            session_id=_must_str(payload.get("session_id")),
            reason=_must_str(payload.get("reason")),
            terminal_event_cursor=cursor,
        )
    if kind == _SUSPENDED_KIND:
        hint_raw = payload.get("resume_hint")
        return RunSuspendedResult(
            run_id=_must_str(payload.get("run_id")),
            session_id=_must_str(payload.get("session_id")),
            reason=_must_str(payload.get("reason")),
            resume_hint=(
                None if hint_raw is None
                else RunResumeHint(message=_must_str(hint_raw))
            ),
            terminal_event_cursor=cursor,
        )
    raise ValueError(f"unknown run_result kind: {kind}")


def _must_str(value: JsonValue | None) -> str:
    """强制 value 为字符串。

    :param value: 任意值。
    :returns: 字符串。
    :raises ValueError: 类型不符。
    """

    if not isinstance(value, str):
        raise ValueError("expected str")
    return value


def _must_bool(value: JsonValue | None) -> bool:
    """强制 value 为布尔。

    :param value: 任意值。
    :returns: 布尔。
    :raises ValueError: 类型不符。
    """

    if not isinstance(value, bool):
        raise ValueError("expected bool")
    return value


__all__ = [
    "AttemptLeaseStore",
    "AttemptStateStore",
    "RunStateStore",
]
