"""Host P8 Attempt Lease / Fencing 内部契约。

本模块承载 P8 attempt owner lease、fencing 与 recovery 决策所需的强类
型契约。它只在 Host internal 使用，不进入 ``dayu.host.__all__``，也不
属于 ``dayu.runtime``。

核心要点：

- ``AttemptOwnerToken`` 持有 owner secret 明文；明文绝不入库、不进普通
  日志、不进 EventLog payload，库内仅存 ``digest()`` 摘要，日志只允许
  ``masked()`` 形式。owner secret 只用于证明 capability，不参与 fencing
  顺序判断。
- ``AttemptOwnerContext`` 是 owner 的强类型句柄，绑定 attempt / run /
  fencing_token / lease 到期时刻；所有 attempt-scoped 写入必须以它为
  owner 授权来源。
- ``FencingToken`` 是 Host 跨 attempt 全局严格单调递增的整数（由
  ``host_fencing_tokens`` 表分配），是 fencing 真源；禁止用 owner secret
  或 per-attempt counter 替代。
- ``AttemptLeaseDecision`` / ``AttemptLeaseResult`` / ``AttemptFencingReason``
  / ``AttemptFencingError`` / ``AttemptRecoveryAction`` /
  ``AttemptRecoveryDecision`` / ``AttemptTerminalLink`` 给 store / supervisor
  层提供 typed CAS / recovery 结果，``rowcount == 0`` 必须映射成这些类
  型，禁止抛裸 SQLite 错误或返回 ``Any`` / ``object``。
- ``UtcClock`` Protocol 用于注入 timezone-aware UTC 时间，测试可使用 fake
  clock 推进 lease 过期，禁止依赖真实 ``time.sleep``。
- 常量集中在本模块，禁止在调用方散落 lease TTL / token 长度等魔法数字。

P8-S1 仅落地契约本身与 store CAS 基础；supervisor 主路径由 P8-S3 起承
载，本模块不实现 supervisor / renew loop / recovery scan。
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from dayu.host._internal_contracts import (
    AttemptState,
    FencingToken,
    GlobalEventPosition,
)
from dayu.host.contracts import RunEvent, RunEventCursor

ATTEMPT_OWNER_TOKEN_BYTES: int = 32
"""Attempt owner secret token 字节数；用于 :func:`secrets.token_hex`。"""

_DEFAULT_LEASE_TTL_SECONDS: int = 30
"""默认 lease TTL（秒），仅用于构造 :data:`DEFAULT_ATTEMPT_LEASE_CONFIG`。"""

_DEFAULT_LEASE_RENEW_INTERVAL_SECONDS: int = 10
"""默认 renew heartbeat 间隔（秒），仅用于构造默认配置。"""

ATTEMPT_OWNER_ID_PREFIX: str = "host"
"""默认 owner id 诊断前缀；owner_id 仅作摘要诊断，不作授权凭据。"""

_OWNER_TOKEN_MASK_TAIL: int = 4
"""``masked()`` 末位保留字符数；其余位以 ``*`` 屏蔽。"""


@dataclass(frozen=True, slots=True)
class AttemptLeaseConfig:
    """Attempt lease 治理配置。

    本配置由 Host durable harness / Host bootstrap 装配层注入到
    supervisor，store 层不持有它，也不自行决定 TTL；store 层方法直接接
    收已经计算好的 ``lease_expires_at`` UTC 时刻。

    禁止把 TTL / renew interval 暴露到 public ``start_run`` 或业务调用
    方；它是 Host internal 治理常量，由装配层一次性注入。

    :param ttl: lease 生存时间，必须为正。
    :param renew_interval: renew heartbeat 间隔；必须为正且小于 ``ttl``。
    :param owner_id_prefix: owner_id 诊断前缀，例如 ``host``。
    """

    ttl: timedelta
    renew_interval: timedelta
    owner_id_prefix: str

    def __post_init__(self) -> None:
        """校验配置合法性。

        :returns: 无返回值。
        :raises ValueError: ttl / renew_interval / owner_id_prefix 非法。
        """

        if self.ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        if self.renew_interval <= timedelta(0):
            raise ValueError("renew_interval must be positive")
        if self.renew_interval >= self.ttl:
            raise ValueError("renew_interval must be smaller than ttl")
        if not self.owner_id_prefix:
            raise ValueError("owner_id_prefix must not be empty")


DEFAULT_ATTEMPT_LEASE_CONFIG: AttemptLeaseConfig = AttemptLeaseConfig(
    ttl=timedelta(seconds=_DEFAULT_LEASE_TTL_SECONDS),
    renew_interval=timedelta(seconds=_DEFAULT_LEASE_RENEW_INTERVAL_SECONDS),
    owner_id_prefix=ATTEMPT_OWNER_ID_PREFIX,
)
"""默认 lease 配置；只是默认值，不是不可替换治理真源。"""


@dataclass(frozen=True, slots=True)
class AttemptOwnerToken:
    """Attempt owner secret token。

    明文 ``value`` 仅在 Host internal 执行上下文流动；持久化只能写入
    :meth:`digest` 返回值；日志、异常、result 只允许 :meth:`masked`。

    :param value: owner secret 明文，长度由 :data:`ATTEMPT_OWNER_TOKEN_BYTES`
        间接决定（hex 编码 -> 2 倍字符）。
    """

    value: str

    @classmethod
    def new(
        cls, *, token_bytes: int = ATTEMPT_OWNER_TOKEN_BYTES
    ) -> "AttemptOwnerToken":
        """生成新的 owner secret token。

        :param token_bytes: secret 字节数；必须为正整数。
        :returns: 新的 :class:`AttemptOwnerToken`。
        :raises ValueError: ``token_bytes`` 非正时抛出。
        """

        if token_bytes <= 0:
            raise ValueError("token_bytes must be positive")
        return cls(value=secrets.token_hex(token_bytes))

    def digest(self) -> str:
        """返回 owner token 的 SHA-256 hex 摘要。

        摘要写入 ``host_attempts.owner_token_hash``，与明文等价但不可还
        原；CAS 校验时与库内 hash 比较。

        :returns: 64 位 hex 字符串。
        :raises Exception: 不主动抛出异常。
        """

        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()

    def masked(self) -> str:
        """返回安全的 masked 表达，仅供日志 / 诊断使用。

        :returns: 形如 ``***abcd`` 的字符串，仅暴露末尾若干位。
        :raises Exception: 不主动抛出异常。
        """

        if len(self.value) <= _OWNER_TOKEN_MASK_TAIL:
            return "***"
        return "***" + self.value[-_OWNER_TOKEN_MASK_TAIL:]


@dataclass(frozen=True, slots=True)
class AttemptOwnerContext:
    """Attempt 当前 owner 的强类型句柄。

    所有 attempt-scoped 写入（EventLog append / lease renew / terminal
    close / ToolRuntime canonical fact 等）必须携带本句柄；store 与
    supervisor 必须用 ``owner_token.digest()`` + ``fencing_token`` +
    ``lease_expires_at > now`` 做 CAS 校验。``fencing_token`` 是全局严
    格单调递增的 :class:`FencingToken`，为 fencing 真源；owner secret 只
    证明 capability，不参与 fencing 顺序。

    :param attempt_id: 当前 attempt id。
    :param run_id: Run id。
    :param attempt_index: 同 run 内 attempt 序号。
    :param owner_id: owner 诊断 id（例如 ``host:<pid>:<boot_id>``）。
    :param owner_token: owner secret 明文 token。
    :param fencing_token: 当前 owner 在该 attempt 上持有的全局 fencing
        token。
    :param lease_expires_at: 当前 lease 到期 UTC 时刻。
    """

    attempt_id: str
    run_id: str
    attempt_index: int
    owner_id: str
    owner_token: AttemptOwnerToken
    fencing_token: FencingToken
    lease_expires_at: datetime


class AttemptLeaseDecision(StrEnum):
    """``AttemptLeaseStore`` acquire / renew CAS 的离散结果。"""

    ACQUIRED = "acquired"
    BUSY = "busy"
    TERMINAL = "terminal"
    FENCED = "fenced"


class AttemptFencingReason(StrEnum):
    """fencing / CAS 失败的细分原因。"""

    OWNER_MISSING = "owner_missing"
    OWNER_MISMATCH = "owner_mismatch"
    RUN_ID_MISMATCH = "run_id_mismatch"
    LEASE_EXPIRED = "lease_expired"
    FENCING_TOKEN_MISMATCH = "fencing_token_mismatch"
    ATTEMPT_NOT_RUNNING = "attempt_not_running"
    ATTEMPT_TERMINAL = "attempt_terminal"
    RUN_TERMINAL = "run_terminal"
    STORAGE_CONFLICT = "storage_conflict"


class AttemptLeaseBusyReason(StrEnum):
    """acquire 返回 ``BUSY`` 的业务级冲突原因。"""

    ATTEMPT_INDEX_CONFLICT = "attempt_index_conflict"


@dataclass(frozen=True, slots=True)
class AttemptLeaseResult:
    """``AttemptLeaseStore`` acquire / renew 的 typed 结果。

    :param decision: 离散决策枚举。
    :param owner_context: 仅在 ``ACQUIRED`` 时非空；表示新的 owner 句柄。
    :param current_state: 库内当前 attempt 状态；当无对应行时可为 ``None``。
    :param current_owner_id: 库内当前 owner id；无 owner 时为 ``None``。
    :param lease_expires_at: 库内当前 lease 到期；无 lease 时为 ``None``。
    :param reason: fencing / terminal 失败的细分原因；``ACQUIRED`` 与
        ``BUSY`` 时为 ``None``。
    :param busy_reason: ``BUSY`` 的业务级冲突原因；非 ``BUSY`` 时为
        ``None``。
    :param current_fencing_token: 库内当前 owner 持有的 fencing token；
        无 owner / 无对应行时为 ``None``。仅作诊断用，CAS 真源仍是
        ``owner_context.fencing_token``。
    """

    decision: AttemptLeaseDecision
    owner_context: AttemptOwnerContext | None
    current_state: AttemptState | None
    current_owner_id: str | None
    lease_expires_at: datetime | None
    reason: AttemptFencingReason | None
    busy_reason: AttemptLeaseBusyReason | None = None
    current_fencing_token: FencingToken | None = None


class AttemptFencingError(Exception):
    """非 owner / 过期 owner / 不一致 owner 试图写入时抛出的强类型异常。

    本异常不进入 EventLog payload；调用方捕获后只能记录 masked 日志或
    转换为 typed result，禁止把 owner 明文 token 暴露到普通日志或公开
    流。
    """

    def __init__(
        self,
        *,
        attempt_id: str,
        run_id: str,
        reason: AttemptFencingReason,
        current_state: AttemptState | None,
        owner_id: str | None,
        fencing_token: FencingToken | None,
    ) -> None:
        """构造 fencing 错误。

        :param attempt_id: 触发 fencing 的 attempt id。
        :param run_id: Run id。
        :param reason: 细分原因。
        :param current_state: 库内当前 attempt 状态；查不到为 ``None``。
        :param owner_id: 库内当前 owner id；无 owner 为 ``None``。
        :param fencing_token: 库内当前 fencing token；无 owner 为 ``None``。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(
            f"attempt fenced: attempt_id={attempt_id} run_id={run_id} "
            f"reason={reason.value} state="
            f"{current_state.value if current_state is not None else 'none'} "
            f"owner_id={owner_id or 'none'} "
            f"fencing_token="
            f"{fencing_token.value if fencing_token is not None else 'none'}"
        )
        self.attempt_id: str = attempt_id
        self.run_id: str = run_id
        self.reason: AttemptFencingReason = reason
        self.current_state: AttemptState | None = current_state
        self.owner_id: str | None = owner_id
        self.fencing_token: FencingToken | None = fencing_token


class AttemptRecoveryAction(StrEnum):
    """recovery scan 对单个 attempt 的离散收口动作。

    P8 D2: recovery 仅做诊断收口, 不再创建新 attempt; 上游 retry / resume
    必须由 Service 层显式发起新 ``StartRunRequest``。
    """

    NOOP_TERMINAL = "noop_terminal"
    MARK_STALE = "mark_stale"
    MARK_LOST = "mark_lost"


@dataclass(frozen=True, slots=True)
class AttemptRecoveryDecision:
    """recovery scan 对单个 attempt 收口后的 typed 决策。

    P8 D2: recovery 仅做诊断收口, 决策不携带任何"新 attempt"字段。

    :param action: 离散动作。
    :param source_attempt_id: 被处理的旧 attempt id。
    :param reason: 摘要原因，例如 ``recovery_lease_expired`` /
        ``recovery_created_orphan`` / ``recovery_run_terminal``。
    """

    action: AttemptRecoveryAction
    source_attempt_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class AttemptTerminalLink:
    """``append_terminal_and_close`` 的强类型返回。

    本类型同时承载事务内 append 出的 terminal :class:`RunEvent` 实例,
    供调用方在事务提交后无需再次访问 ``EventLog`` 即可拿到完整事件;
    避免事务提交后再做一次 ``list_events`` 查询带来的额外 SQLite
    round-trip 与 "append 后立即可查" 的隐含不变量假设。

    :param attempt_id: 关闭的 attempt id。
    :param run_id: Run id。
    :param terminal_state: terminal 状态。
    :param event: 已落库的 terminal :class:`RunEvent`; 在原子 append +
        close 事务内构造, 与 ``event_cursor`` / ``event_position`` 同源。
    :param event_cursor: terminal RunEvent 的 per-run cursor。
    :param event_position: terminal RunEvent 的全局 position。
    """

    attempt_id: str
    run_id: str
    terminal_state: AttemptState
    event: RunEvent
    event_cursor: RunEventCursor
    event_position: GlobalEventPosition


class UtcClock(Protocol):
    """可注入的 UTC clock 协议。

    所有 lease / fencing 时间判断必须经由本协议返回的 timezone-aware UTC
    ``datetime``，禁止直接调用 ``datetime.now()`` / ``time.time()`` 散落
    在 store / supervisor 之中。测试需要 fake clock 推进 lease 过期。
    """

    def now(self) -> datetime:
        """返回 timezone-aware UTC 当前时间。

        :returns: timezone-aware UTC datetime。
        :raises Exception: 不主动抛出异常。
        """
        ...


__all__ = [
    "ATTEMPT_OWNER_ID_PREFIX",
    "ATTEMPT_OWNER_TOKEN_BYTES",
    "DEFAULT_ATTEMPT_LEASE_CONFIG",
    "AttemptFencingError",
    "AttemptFencingReason",
    "AttemptLeaseBusyReason",
    "AttemptLeaseConfig",
    "AttemptLeaseDecision",
    "AttemptLeaseResult",
    "AttemptOwnerContext",
    "AttemptOwnerToken",
    "AttemptRecoveryAction",
    "AttemptRecoveryDecision",
    "AttemptTerminalLink",
    "FencingToken",
    "UtcClock",
]
