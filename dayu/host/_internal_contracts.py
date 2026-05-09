"""Host P6 内部契约。

本模块定义 P6 durable EventLog / Run / Attempt minimal state /
projection checkpoint / observer status 所需的强类型 dataclass。它只在
Host internal 使用，不进入 ``dayu.host.__all__``，也不属于
``dayu.runtime``。

P6 不实现 attempt owner lease / fencing / lifecycle admission；这些字段
都按 nullable / 默认值落地，不承载 owner 语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from dayu.host.contracts import RunEventCursor, RunResult, RunState


@dataclass(frozen=True, slots=True)
class GlobalEventPosition:
    """跨 run 的全局事件位置。

    P6 internal-only 全局递增位置；不暴露为 public RunEventCursor，仅
    服务 observer / projection 跨 run 消费。

    :param value: 全局单调递增整数，从 ``0`` 起。
    """

    value: int


@dataclass(frozen=True, slots=True)
class FencingToken:
    """Host P8 fencing token 强类型。

    fencing token 是 Host 跨 attempt / 跨 run 全局唯一且严格单调递增的
    整数，由 :class:`AttemptLeaseStore` 在事务内通过 ``host_fencing_tokens``
    表分配。它是 Host fencing 决策的真源；owner secret token 只证明
    capability，不参与 fencing 顺序判断。

    本类型禁止与 ``int`` 互相隐式转换，禁止用 ``lease_generation`` 等
    per-attempt counter 替代。允许 token gap（acquire 冲突 / 回滚导致），
    禁止 token 倒退或复用同一数值。

    :param value: 全局单调递增整数；首个 token 为 ``1``。
    """

    value: int

    def __post_init__(self) -> None:
        """校验 token 必须为正整数。

        :returns: 无返回值。
        :raises ValueError: ``value`` 不是正整数时抛出。
        """

        if self.value <= 0:
            raise ValueError("fencing token value must be positive")


class AttemptState(StrEnum):
    """Host attempt 最小持久状态。

    P8 在 P6 基础上把 ``STALE_DIAGNOSTIC`` 拆分为 ``STALE`` /
    ``RECOVERING`` / ``LOST`` 三个 owner-aware 终止 / 中间态：

    - ``STALE``：旧 owner lease 过期，attempt 已被关闭执行权但尚未创建
      recovery attempt；结果未知。
    - ``RECOVERING``：旧 attempt 已被 recovery CAS 关闭，并在同事务创
      建了新的 recovery attempt。
    - ``LOST``：结果无法确认且 policy 不创建 recovery attempt。

    合法迁移由 P8 supervisor / lease store 在 CAS 层强制；本枚举只承载
    持久状态字面量。
    """

    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    STALE = "stale"
    RECOVERING = "recovering"
    LOST = "lost"


class ExtendedRunState(StrEnum):
    """Host run 在 P6 持久层使用的扩展状态。

    在 :class:`dayu.host.contracts.RunState` 之外补充
    ``LOST_DIAGNOSTIC``，表示 P6 startup / reconcile 发现 EventLog 与
    Run state 不一致。它不是 P9 public ``LOST`` 治理。
    """

    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    LOST_DIAGNOSTIC = "lost_diagnostic"


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Run 最小持久记录。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param state: 当前 Run 持久状态。
    :param created_at: 创建时间。
    :param updated_at: 最近更新时间。
    :param terminal_event_cursor: 终态事件 cursor；未终态为 ``None``。
    :param terminal_event_position: 终态全局位置；未终态为 ``None``。
    :param result: terminal RunResult snapshot；未终态为 ``None``。
    """

    run_id: str
    session_id: str
    state: ExtendedRunState
    created_at: datetime
    updated_at: datetime
    terminal_event_cursor: RunEventCursor | None
    terminal_event_position: GlobalEventPosition | None
    result: RunResult | None


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Attempt 最小持久记录。

    P8 扩展 owner / lease / recovery 字段：``owner_id`` /
    ``owner_token_hash`` / ``fencing_token`` / ``lease_expires_at`` /
    ``lease_renewed_at`` / ``recovered_from_attempt_id`` /
    ``stale_marked_at``。明文 owner token 永不入库，``owner_token_hash``
    存储 :meth:`AttemptOwnerToken.digest` 结果；``owner_id`` 仅作诊断摘
    要，非授权凭据；``fencing_token`` 来自全局 ``host_fencing_tokens``
    严格单调序列，是 fencing 真源。

    :param attempt_id: attempt id。
    :param run_id: Run id。
    :param attempt_index: 同一 Run 内 attempt 序号。
    :param state: 当前 attempt 状态。
    :param started_at: attempt 开始时间。
    :param finished_at: attempt 完成时间;未完成为 ``None``。
    :param terminal_event_position: terminal 事件全局位置；正常 terminal
        attempt 必须非空；``STALE`` / ``RECOVERING`` / ``LOST`` 这类无
        terminal RunEvent 的诊断终态可为空。
    :param failure_summary: 失败摘要；非失败 / 未失败为 ``None``。
    :param owner_id: 当前 owner 诊断 id；无 owner 为 ``None``。
    :param owner_token_hash: 当前 owner token 的 SHA-256 hex 摘要；无
        owner 为 ``None``。
    :param fencing_token: 当前 owner 在该 attempt 上持有的全局 fencing
        token；从未 acquire 时为 ``None``。
    :param lease_expires_at: 当前 lease 到期 UTC 时刻；从未 acquire 时
        为 ``None``。
    :param lease_renewed_at: 最近一次 acquire / renew UTC 时刻；从未
        acquire 时为 ``None``。
    :param recovered_from_attempt_id: 仅在新 recovery attempt 上写入，
        指向被恢复的旧 attempt id。
    :param stale_marked_at: 旧 attempt 被标记 ``STALE`` / ``RECOVERING`` /
        ``LOST`` 时的 UTC 时刻；其它状态为 ``None``。
    """

    attempt_id: str
    run_id: str
    attempt_index: int
    state: AttemptState
    started_at: datetime
    finished_at: datetime | None
    terminal_event_position: GlobalEventPosition | None
    failure_summary: str | None
    owner_id: str | None
    owner_token_hash: str | None
    fencing_token: FencingToken | None
    lease_expires_at: datetime | None
    lease_renewed_at: datetime | None
    recovered_from_attempt_id: str | None
    stale_marked_at: datetime | None


def extended_state_from_run_state(state: RunState) -> ExtendedRunState:
    """将 public ``RunState`` 映射到持久 ``ExtendedRunState``。

    ``RunState`` 是封闭枚举，``match`` 已穷举全部成员；新增成员时静态类型
    检查会立即报错，无需运行时 wildcard fallback。

    :param state: public RunState。
    :returns: 对应 ExtendedRunState。
    :raises Exception: 不主动抛出异常。
    """

    match state:
        case RunState.CREATED:
            return ExtendedRunState.CREATED
        case RunState.RUNNING:
            return ExtendedRunState.RUNNING
        case RunState.SUCCEEDED:
            return ExtendedRunState.SUCCEEDED
        case RunState.FAILED:
            return ExtendedRunState.FAILED
        case RunState.CANCELLED:
            return ExtendedRunState.CANCELLED
        case RunState.SUSPENDED:
            return ExtendedRunState.SUSPENDED


class ObserverStatus(StrEnum):
    """Observer / projection runner 状态。"""

    IDLE = "idle"
    RUNNING = "running"
    RETRYABLE_FAILED = "retryable_failed"
    BLOCKED_FAILED = "blocked_failed"
    CAUGHT_UP = "caught_up"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ProjectionCheckpoint:
    """Projection checkpoint 持久记录。

    :param observer_id: Observer 稳定 id。
    :param projection_name: projection 名。
    :param schema_version: read model schema 版本。
    :param last_success_position: 最近成功消费的全局位置；尚未消费为
        ``None``。
    :param last_attempted_position: 最近尝试消费的全局位置；尚未尝试为
        ``None``。
    :param status: observer 状态。
    :param retry_count: 当前连续失败次数。
    :param last_error_code: 最近失败错误码；无为 ``None``。
    :param last_error_message: 最近失败可读消息；无为 ``None``。
    :param last_success_at: 最近成功时间；无为 ``None``。
    :param updated_at: 最近更新时间。
    :param lag_events: 落后事件数；可由查询时计算。
    """

    observer_id: str
    projection_name: str
    schema_version: int
    last_success_position: GlobalEventPosition | None
    last_attempted_position: GlobalEventPosition | None
    status: ObserverStatus
    retry_count: int
    last_error_code: str | None
    last_error_message: str | None
    last_success_at: datetime | None
    updated_at: datetime
    lag_events: int


__all__ = [
    "AttemptRecord",
    "AttemptState",
    "ExtendedRunState",
    "FencingToken",
    "GlobalEventPosition",
    "ObserverStatus",
    "ProjectionCheckpoint",
    "RunRecord",
    "extended_state_from_run_state",
]
