"""Host 等待适配器 registry 与最小 poller 的层内契约。

本模块只定义 Host 内部如何为 ``ToolAwaitingOutcome`` 选择等待适配器
binding，并提供 Phase 7 的最小 poll adapter 轮询编排。它不实现 callback
endpoint 或外部系统协议，也不让 Engine 选择 adapter。
"""

from __future__ import annotations

import logging
import math
import threading
import time
from functools import partial
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, TypeAlias
from uuid import uuid4

from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.host.api import (
    HOST_WAIT_RESUME_TOKEN_MAX_LENGTH,
    HostCallContext,
    ResolveWaitLostOutcome,
    ResolveWaitOutcome,
    ResolveWaitRequest,
    RunSnapshot,
    WaitAdapterKey,
    WaitResolutionSource,
)
from dayu.host._wait_observation import (
    WaitObservationCapacityExceeded,
    WaitObservationClosed,
    WaitObservationDiagnosticsSnapshot,
    WaitObservationFailed,
    WaitObservationPublished,
    WaitObservationRunner,
    WaitObservationTimedOut,
)
from dayu.host.durable.codec import format_utc_timestamp, parse_utc_timestamp
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.state import (
    ExternalJobRef,
    StateMutationStatus,
    WaitPollLastOutcome,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    claim_wait_record_for_poll,
    mark_wait_record_poll_abandoned,
    read_next_wait_record_poll_due_at,
    read_wait_record_by_id,
    release_wait_record_poll_claim,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL
from dayu.host.wait_boundary import (
    WaitBoundaryDecisionKind,
    classify_wait_time_boundary,
)
from dayu.host.waiting import ExpireWaitInput, ExpireWaitResult

if TYPE_CHECKING:
    from dayu.host.waiting import ToolAwaitingAcceptedAck

_LOGGER = logging.getLogger(__name__)
_POLL_ERROR_CODE_ADAPTER_EXCEPTION = "adapter_exception"
_POLL_ERROR_CODE_MISSING_ADAPTER = "missing_adapter"
_POLL_ERROR_CODE_RESOLVE_EXCEPTION = "resolve_exception"
_POLL_ERROR_CODE_ABANDON_EXCEPTION = "abandon_exception"
_POLL_ERROR_CODE_ABANDON_TIMEOUT = "wait_abandon_timeout"
_POLL_ERROR_CODE_OBSERVATION_TIMEOUT = "wait_observation_timeout"
_POLL_ERROR_CODE_OBSERVATION_CAPACITY = "wait_observation_capacity"
_POLL_ERROR_CODE_SHUTDOWN_SKIPPED = "shutdown_skipped"
_POLL_ERROR_CODE_INVALID_TIME_BOUNDARY = "invalid_wait_time_boundary"
_WAIT_POLLER_SELF_CLOSE_MESSAGE = (
    "wait poller supervisor cannot close from its own thread"
)


class _WaitPollerSelfCloseError(RuntimeError):
    """supervisor 线程内自关闭的内部控制流异常。"""


class WaitExternalJobRefSource(StrEnum):
    """外部 job id 的 Host 派生来源。"""

    NONE = "none"
    RESUME_TOKEN = "resume_token"


class WaitExternalJobLifecycleAction(StrEnum):
    """cancelled wait 对外部 job 执行的 lifecycle 动作。"""

    CANCEL = "cancel"
    REVOKE = "revoke"
    ABANDON = "abandon"


@dataclass(frozen=True, slots=True)
class WaitExternalJobLifecycleApplied:
    """adapter 已执行外部 job lifecycle 动作。

    :param action: adapter 实际执行的最强 lifecycle 动作。
    :param message: 可选诊断消息；无补充诊断时为 ``None``。
    """

    action: WaitExternalJobLifecycleAction
    message: str | None = None

    def __post_init__(self) -> None:
        """校验 lifecycle applied result 字段。

        :returns: ``None``。
        :raises ValueError: ``action`` 类型非法或 ``message`` 为空字符串时抛出。
        """

        if not isinstance(self.action, WaitExternalJobLifecycleAction):
            raise ValueError("action must be WaitExternalJobLifecycleAction")
        if self.message is not None and self.message.strip() == "":
            raise ValueError("message must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class WaitExternalJobLifecycleUnsupported:
    """adapter 明确不支持当前 wait 的外部 job lifecycle 动作。

    :param reason: 不支持的稳定诊断原因。
    """

    reason: str

    def __post_init__(self) -> None:
        """校验 unsupported result 字段。

        :returns: ``None``。
        :raises ValueError: ``reason`` 为空时抛出。
        """

        if self.reason.strip() == "":
            raise ValueError("reason must be non-empty")


@dataclass(frozen=True, slots=True)
class WaitExternalJobLifecycleNoop:
    """adapter 判断当前 wait 已无需或无法继续执行外部 lifecycle 动作。

    :param reason: no-op 的稳定诊断原因。
    """

    reason: str

    def __post_init__(self) -> None:
        """校验 no-op result 字段。

        :returns: ``None``。
        :raises ValueError: ``reason`` 为空时抛出。
        """

        if self.reason.strip() == "":
            raise ValueError("reason must be non-empty")


WaitExternalJobLifecycleResult: TypeAlias = (
    WaitExternalJobLifecycleApplied
    | WaitExternalJobLifecycleUnsupported
    | WaitExternalJobLifecycleNoop
)
"""cancelled wait 外部 job lifecycle 结果封闭联合。"""


@dataclass(frozen=True, slots=True)
class WaitPollNotReady:
    """poll adapter 观察到外部 job 尚未完成。"""


@dataclass(frozen=True, slots=True)
class WaitPollReady:
    """poll adapter 观察到外部 job 已产生可恢复结果。

    :param outcome: 交给 ``resolve_wait`` 的 typed 等待结果 envelope。
    """

    outcome: ResolveWaitOutcome


@dataclass(frozen=True, slots=True)
class WaitPollLost:
    """poll adapter 观察到外部 job 状态已不可确认。

    :param outcome: 交给 ``resolve_wait`` 的 lost envelope。
    """

    outcome: ResolveWaitLostOutcome


WaitPollResult: TypeAlias = WaitPollNotReady | WaitPollReady | WaitPollLost
"""poll adapter 单次观察结果封闭联合。"""


class WaitAdapterSnapshotProjectionError(ValueError):
    """Host wait row 投影为 adapter snapshot 失败。"""


@dataclass(frozen=True, slots=True)
class WaitAdapterSnapshot:
    """投影给外部 wait adapter 的最小 Host snapshot。

    :param tool_name: 等待所属工具名。
    :param resume_token: Host durable row 中保存的 opaque resume token。
    :param created_at: Host durable row 创建时间，已解析为 UTC aware datetime。
    """

    tool_name: str
    resume_token: str
    created_at: datetime

    def __post_init__(self) -> None:
        """校验 adapter snapshot 基础字段。

        :returns: ``None``。
        :raises ValueError: 字段为空、类型非法或时间无时区时抛出。
        """

        if self.tool_name.strip() == "":
            raise ValueError("tool_name must be non-empty")
        if self.resume_token.strip() == "":
            raise ValueError("resume_token must be non-empty")
        if len(self.resume_token) > HOST_WAIT_RESUME_TOKEN_MAX_LENGTH:
            raise ValueError("resume_token is too long")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


class WaitPollAdapter(Protocol):
    """外部等待系统 poll adapter 端口。"""

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """在 Host transaction 外观察外部 job 状态。

        :param snapshot: Host 投影给 adapter 的最小快照。
        :returns: poll 结果。
        :raises Exception: adapter 可在外部系统调用失败时抛出普通异常。
        """

        ...

    def abandon_wait(
        self, snapshot: WaitAdapterSnapshot
    ) -> WaitExternalJobLifecycleResult:
        """在 wait 已取消时执行 best-effort 外部 job lifecycle 动作。

        :param snapshot: Host 投影给 adapter 的最小快照。
        :returns: typed lifecycle 结果；applied、unsupported 与 no-op 都是终态诊断。
        :raises Exception: adapter 可在临时外部系统调用失败时抛出普通异常。
        """

        ...


@dataclass(frozen=True, slots=True)
class WaitActivationRequest:
    """已被 Host 接受的等待 activation 请求。

    :param tool_name: 产出等待 outcome 的工具名。
    :param await_spec: 已被 Host 接受的等待规约。
    :param accepted_ack: Host awaiting accept durable ack。
    """

    tool_name: str
    await_spec: ToolAwaitSpec
    accepted_ack: "ToolAwaitingAcceptedAck"

    def __post_init__(self) -> None:
        """校验 activation 请求字段。

        :returns: ``None``。
        :raises ValueError: 工具名为空或等待规约类型非法时抛出。
        """

        if self.tool_name.strip() == "":
            raise ValueError("tool_name must be non-empty")
        if not isinstance(self.await_spec, ToolAwaitSpec):
            raise ValueError("await_spec must be ToolAwaitSpec")


class WaitActivationAdapter(Protocol):
    """Host accepted wait 后触发外部事务 activation 的端口。"""

    def activate_accepted_wait(self, request: WaitActivationRequest) -> None:
        """激活已被 Host durable 接受的等待。

        :param request: accepted wait activation 请求。
        :returns: ``None``。
        :raises Exception: adapter 可在外部 activation 失败时抛出普通异常。
        """

        ...


class WaitResolvePort(Protocol):
    """poller 依赖的 resolve_wait 端口。"""

    def resolve_wait(
        self, wait_id: str, request: ResolveWaitRequest
    ) -> RunSnapshot:
        """接收 poller 观察到的等待结果。

        :param wait_id: wait record id。
        :param request: typed resolve wait 请求。
        :returns: resolve 后 Run snapshot。
        :raises Exception: 具体实现按公共 Host API 抛出结构化错误。
        """

        ...

    def expire_wait(self, request: "ExpireWaitInput") -> "ExpireWaitResult":
        """按 Host durable deadline 收口过期 wait。

        :param request: expiry owner 输入。
        :returns: expiry transition 结果。
        :raises Exception: durable transition 或 wake 失败时透传。
        """

        ...


class WaitPollClock(Protocol):
    """poller 使用的 UTC 时钟端口。"""

    def now(self) -> datetime:
        """返回当前 UTC aware 时间。

        :returns: timezone-aware UTC ``datetime``。
        """

        ...


class WaitPollLifecycleGate(Protocol):
    """wait poller lifecycle close gate。"""

    def is_closed(self) -> bool:
        """返回当前 poller runtime 是否已关闭。

        :returns: 已关闭或正在关闭时返回 ``True``。
        """

        ...


class WaitPollerFactory(Protocol):
    """为 supervisor 创建 wait poller 的端口。"""

    def create_wait_poller(
        self,
        lifecycle_gate: WaitPollLifecycleGate,
        observation_runner: WaitObservationRunner,
    ) -> "WaitPoller":
        """创建绑定当前 lifecycle gate 的 wait poller。

        :param lifecycle_gate: supervisor close gate。
        :param observation_runner: supervisor-owned bounded observation runner。
        :returns: wait poller。
        """

        ...


@dataclass(frozen=True, slots=True)
class WaitPollAdapterRegistration:
    """poll adapter 注册项。

    :param adapter_key: adapter 稳定注册键。
    :param adapter: poll adapter 实例。
    """

    adapter_key: WaitAdapterKey
    adapter: WaitPollAdapter


@dataclass(frozen=True, slots=True)
class WaitActivationAdapterRegistration:
    """activation adapter 注册项。

    :param adapter_key: adapter 稳定注册键。
    :param adapter: activation adapter 实例。
    """

    adapter_key: WaitAdapterKey
    adapter: WaitActivationAdapter


@dataclass(frozen=True, slots=True)
class WaitPollerRuntimePolicy:
    """wait poller runtime policy。

    :param enabled: 是否启用 production wait poller；``False`` 表示 policy
        对象可被校验但 ``open_host`` 不启动 poller。
    :param poll_interval_seconds: background loop idle poll 间隔秒数。
    :param claim_ttl_seconds: 单条 poll claim 有效秒数。
    :param claim_batch_size: 单轮最多 claim 的 wait record 数。
    :param backoff_initial_delay_seconds: retry 初始退避秒数。
    :param backoff_multiplier: retry 指数退避倍率。
    :param backoff_max_delay_seconds: retry 最大退避秒数。
    :param not_ready_observe_interval_seconds: adapter 返回正常运行中
        ``not_ready`` 后的下一次观察间隔秒数。
    :param idle_poll_interval_seconds: 单轮没有 claim 到任何 wait record 时的
        空闲轮询间隔秒数。
    :param adapter_call_timeout_seconds: 单次同步 adapter 调用的最大秒数。
    :param close_drain_timeout_seconds: poller loop 与全部 observation thread
        共享的单次 close 预算秒数。
    :param max_outstanding_adapter_calls: live adapter invocation 正数上限。
    """

    enabled: bool
    poll_interval_seconds: float
    claim_ttl_seconds: float
    claim_batch_size: int
    backoff_initial_delay_seconds: float
    backoff_multiplier: float
    backoff_max_delay_seconds: float
    not_ready_observe_interval_seconds: float
    idle_poll_interval_seconds: float
    adapter_call_timeout_seconds: float
    close_drain_timeout_seconds: float
    max_outstanding_adapter_calls: int

    def __post_init__(self) -> None:
        """校验 runtime policy 字段。

        :returns: ``None``。
        :raises ValueError: 任一 policy 数值不是正数时抛出。
        """

        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")
        _require_positive_float(
            self.poll_interval_seconds, field_name="poll_interval_seconds"
        )
        _require_positive_float(self.claim_ttl_seconds, field_name="claim_ttl_seconds")
        if not isinstance(self.claim_batch_size, int) or isinstance(
            self.claim_batch_size, bool
        ):
            raise TypeError("claim_batch_size must be int")
        if self.claim_batch_size <= 0:
            raise ValueError("claim_batch_size must be positive")
        _require_positive_float(
            self.backoff_initial_delay_seconds,
            field_name="backoff_initial_delay_seconds",
        )
        _require_positive_float(
            self.backoff_multiplier, field_name="backoff_multiplier"
        )
        _require_positive_float(
            self.backoff_max_delay_seconds, field_name="backoff_max_delay_seconds"
        )
        _require_positive_float(
            self.not_ready_observe_interval_seconds,
            field_name="not_ready_observe_interval_seconds",
        )
        _require_positive_float(
            self.idle_poll_interval_seconds,
            field_name="idle_poll_interval_seconds",
        )
        _require_positive_float(
            self.adapter_call_timeout_seconds,
            field_name="adapter_call_timeout_seconds",
        )
        _require_positive_float(
            self.close_drain_timeout_seconds,
            field_name="close_drain_timeout_seconds",
        )
        if not isinstance(self.max_outstanding_adapter_calls, int) or isinstance(
            self.max_outstanding_adapter_calls, bool
        ):
            raise TypeError("max_outstanding_adapter_calls must be int")
        if self.max_outstanding_adapter_calls <= 0:
            raise ValueError("max_outstanding_adapter_calls must be positive")


@dataclass(frozen=True, slots=True)
class WaitPollOnceResult:
    """单轮 poller 执行摘要。

    :param observed: 本轮读取到的 poll wait 数。
    :param not_ready: adapter 返回未就绪的 wait 数。
    :param resolved: 通过 ``resolve_wait`` 接收 completed/failed/cancelled 的数。
    :param lost: 通过 ``resolve_wait`` 接收 lost 的数。
    :param abandoned: 因 wait 已取消而通知 adapter 放弃的数。
    :param adapter_errors: adapter 调用失败的数。
    :param boundary_rejections: Host 在调用 adapter 前拒绝过期或非法边界的数。
    :param claim_conflicts: claim / release / abandon CAS 冲突数。
    :param shutdown_skipped: close gate 触发后跳过 resolve / abandon 的数。
    :param next_poll_delay_seconds: 本轮结束时已知下一次 due wait 的等待秒数；
        没有 active wait 或本轮没有产生可推导 due 时为 ``None``。
    """

    observed: int
    not_ready: int
    resolved: int
    lost: int
    abandoned: int
    adapter_errors: int
    boundary_rejections: int = 0
    claim_conflicts: int = 0
    shutdown_skipped: int = 0
    next_poll_delay_seconds: float | None = None


class WaitPollerLoopStatus(StrEnum):
    """wait poller supervisor loop 状态。"""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    CLOSING = "closing"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WaitPollerDiagnosticsSnapshot:
    """wait poller supervisor runtime diagnostics 快照。

    :param status: loop 当前状态。
    :param poll_rounds: 已完成 poll round 数。
    :param observed: 累计已 claim / observed 数。
    :param not_ready: 累计 not-ready 数。
    :param resolved: 累计 resolved 数。
    :param lost: 累计 lost 数。
    :param abandoned: 累计 abandoned 数。
    :param adapter_errors: 累计 adapter / resolve / abandon 错误数。
    :param boundary_rejections: 累计 Host pre-adapter 边界拒绝数。
    :param claim_conflicts: 累计 claim CAS 冲突数。
    :param shutdown_skipped: 累计 close gate 跳过 resolve / abandon 数。
    :param close_drain_timeouts: close drain 首次超时诊断次数。
    :param round_errors: 可恢复 poll round exception 次数。
    :param fatal_errors: loop-level fatal exception 次数。
    :param last_error_type: 最近一次 loop-level exception 类型。
    :param last_error_message: 最近一次 loop-level exception 消息。
    """

    status: WaitPollerLoopStatus
    poll_rounds: int
    observed: int
    not_ready: int
    resolved: int
    lost: int
    abandoned: int
    adapter_errors: int
    boundary_rejections: int
    claim_conflicts: int
    shutdown_skipped: int
    close_drain_timeouts: int
    round_errors: int
    fatal_errors: int
    last_error_type: str | None
    last_error_message: str | None


@dataclass(frozen=True, slots=True)
class _ClaimedWaitRecord:
    """poller 已取得 claim 的 wait record。

    :param record: claim 后读取到的 wait record。
    :param claim_id: 本次取得的 claim id。
    """

    record: WaitRecordRow
    claim_id: str


@dataclass(frozen=True, slots=True)
class _ReleaseNotReadySummary:
    """释放 not-ready wait claim 的结果摘要。

    :param claim_conflicts: release CAS 冲突计数。
    :param next_poll_delay_seconds: release 成功时的下一次观察等待秒数。
    """

    claim_conflicts: int
    next_poll_delay_seconds: float | None


class _SystemUtcClock:
    """系统 UTC 时钟。"""

    def now(self) -> datetime:
        """返回当前 UTC aware 时间。

        :returns: 当前 UTC 时间。
        """

        return datetime.now(UTC)


class _AlwaysOpenLifecycleGate:
    """默认永不关闭的 lifecycle gate。"""

    def is_closed(self) -> bool:
        """返回关闭状态。

        :returns: 始终返回 ``False``。
        """

        return False


@dataclass(frozen=True, slots=True)
class _ClaimWaitRecordOperation:
    """claim wait record 的 transaction operation。"""

    claim_id: str
    owner_id: str
    now: str
    claim_expires_at: str

    def __call__(
        self, transaction: HostTransaction
    ) -> tuple[StateMutationStatus, WaitRecordRow | None]:
        """执行 claim CAS。

        :param transaction: Host transaction。
        :returns: mutation 状态与成功取得 claim 的 wait record。
        """

        result = claim_wait_record_for_poll(
            transaction,
            claim_id=self.claim_id,
            owner_id=self.owner_id,
            now=self.now,
            claim_expires_at=self.claim_expires_at,
        )
        if result.status is StateMutationStatus.UPDATED:
            if result.row is None:
                raise RuntimeError("poll claim updated without row")
            return result.status, result.row
        return result.status, None


@dataclass(frozen=True, slots=True)
class _ReleaseWaitRecordClaimOperation:
    """release wait record poll claim 的 transaction operation。"""

    wait_id: str
    claim_id: str
    next_observe_at: str
    backoff_attempt: int
    last_outcome: WaitPollLastOutcome
    last_error_code: str | None
    last_error_message: str | None
    updated_at: str

    def __call__(self, transaction: HostTransaction) -> StateMutationStatus:
        """执行 claim release CAS。

        :param transaction: Host transaction。
        :returns: mutation 状态。
        """

        result = release_wait_record_poll_claim(
            transaction,
            wait_id=self.wait_id,
            claim_id=self.claim_id,
            next_observe_at=self.next_observe_at,
            backoff_attempt=self.backoff_attempt,
            last_outcome=self.last_outcome,
            last_error_code=self.last_error_code,
            last_error_message=self.last_error_message,
            updated_at=self.updated_at,
        )
        return result.status


@dataclass(frozen=True, slots=True)
class _MarkWaitRecordAbandonedOperation:
    """mark wait record poll abandoned 的 transaction operation。"""

    wait_id: str
    claim_id: str
    abandoned_at: str
    updated_at: str
    last_outcome: WaitPollLastOutcome

    def __call__(self, transaction: HostTransaction) -> StateMutationStatus:
        """执行 abandon success CAS。

        :param transaction: Host transaction。
        :returns: mutation 状态。
        """

        result = mark_wait_record_poll_abandoned(
            transaction,
            wait_id=self.wait_id,
            claim_id=self.claim_id,
            abandoned_at=self.abandoned_at,
            updated_at=self.updated_at,
            last_outcome=self.last_outcome,
        )
        return result.status


@dataclass(frozen=True, slots=True)
class _ReadWaitRecordOperation:
    """读取单条 wait record 的 transaction operation。"""

    wait_id: str

    def __call__(self, transaction: HostTransaction) -> WaitRecordRow | None:
        """读取 wait record。

        :param transaction: Host transaction。
        :returns: wait record；不存在时为 ``None``。
        """

        return read_wait_record_by_id(transaction, self.wait_id)


@dataclass(frozen=True, slots=True)
class _ReadNextPollDueAtOperation:
    """读取 active poll wait 下一次 due 时间的 transaction operation。"""

    now: str

    def __call__(self, transaction: HostTransaction) -> str | None:
        """读取下一次 due 时间。

        :param transaction: Host transaction。
        :returns: UTC timestamp 文本；没有 active poll wait 时为 ``None``。
        """

        return read_next_wait_record_poll_due_at(transaction, now=self.now)


@dataclass(frozen=True, slots=True)
class WaitAdapterBinding:
    """单个工具等待适配器 binding。

    :param tool_name: 适用工具名。
    :param await_kind: 适用等待类型。
    :param adapter_key: Host registry 中的稳定 adapter key。
    :param resume_policy: 等待恢复策略。
    :param external_job_ref_source: 外部 job id 的派生来源。
    """

    tool_name: str
    await_kind: ToolAwaitKind
    adapter_key: WaitAdapterKey
    resume_policy: WaitResumePolicy
    external_job_ref_source: WaitExternalJobRefSource

    def __post_init__(self) -> None:
        """校验 binding 字段。

        :returns: ``None``。
        :raises ValueError: 工具名为空或 enum 类型非法时抛出。
        """

        if self.tool_name.strip() == "":
            raise ValueError("tool_name must be non-empty")
        if not isinstance(self.await_kind, ToolAwaitKind):
            raise ValueError("await_kind must be ToolAwaitKind")
        if not isinstance(self.adapter_key, WaitAdapterKey):
            raise ValueError("adapter_key must be WaitAdapterKey")
        if not isinstance(self.resume_policy, WaitResumePolicy):
            raise ValueError("resume_policy must be WaitResumePolicy")
        if not isinstance(self.external_job_ref_source, WaitExternalJobRefSource):
            raise ValueError(
                "external_job_ref_source must be WaitExternalJobRefSource"
            )

    def external_job_ref(self, await_spec: ToolAwaitSpec) -> ExternalJobRef | None:
        """根据 Host binding 从等待规约派生外部 job 引用。

        :param await_spec: 工具等待规约。
        :returns: 外部 job 引用；当前 binding 不需要时为 ``None``。
        """

        if self.external_job_ref_source is WaitExternalJobRefSource.NONE:
            return None
        if self.external_job_ref_source is WaitExternalJobRefSource.RESUME_TOKEN:
            return ExternalJobRef(
                adapter_key=self.adapter_key,
                external_job_id=await_spec.resume_token,
            )
        raise ValueError("unsupported external job ref source")


class WaitAdapterRegistry:
    """Host 等待适配器 registry。

    registry 只按 Host 配置过的 tool name 与 await kind 选择 binding，不读取
    Engine event，也不反序列化业务 payload。
    """

    def __init__(self, bindings: tuple[WaitAdapterBinding, ...]) -> None:
        """初始化 registry。

        :param bindings: 可用 binding 列表。
        :returns: ``None``。
        :raises ValueError: 出现重复 binding key 时抛出。
        """

        self._bindings: dict[tuple[str, ToolAwaitKind], WaitAdapterBinding] = {}
        for binding in bindings:
            key = (binding.tool_name, binding.await_kind)
            if key in self._bindings:
                raise ValueError("duplicate wait adapter binding")
            self._bindings[key] = binding

    def resolve_binding(
        self, *, tool_name: str, await_kind: ToolAwaitKind
    ) -> WaitAdapterBinding | None:
        """解析工具等待 binding。

        :param tool_name: 工具名。
        :param await_kind: 等待类型。
        :returns: 匹配 binding；未配置时为 ``None``。
        :raises ValueError: 工具名为空或等待类型非法时抛出。
        """

        if tool_name.strip() == "":
            raise ValueError("tool_name must be non-empty")
        if not isinstance(await_kind, ToolAwaitKind):
            raise ValueError("await_kind must be ToolAwaitKind")
        return self._bindings.get((tool_name, await_kind))


class WaitPollAdapterRegistry:
    """Host poll adapter registry。"""

    def __init__(
        self, registrations: tuple[WaitPollAdapterRegistration, ...]
    ) -> None:
        """初始化 poll adapter registry。

        :param registrations: adapter 注册项。
        :returns: ``None``。
        :raises ValueError: adapter key 重复时抛出。
        """

        self._adapters: dict[WaitAdapterKey, WaitPollAdapter] = {}
        for registration in registrations:
            if registration.adapter_key in self._adapters:
                raise ValueError("duplicate wait poll adapter registration")
            self._adapters[registration.adapter_key] = registration.adapter

    def resolve_adapter(self, adapter_key: WaitAdapterKey) -> WaitPollAdapter | None:
        """按 adapter key 解析 poll adapter。

        :param adapter_key: wait record 上持久化的 adapter key。
        :returns: adapter；未注册时为 ``None``。
        """

        return self._adapters.get(adapter_key)


class WaitActivationRegistry:
    """Host accepted wait activation adapter registry。"""

    def __init__(
        self, registrations: tuple[WaitActivationAdapterRegistration, ...]
    ) -> None:
        """初始化 activation adapter registry。

        :param registrations: adapter 注册项。
        :returns: ``None``。
        :raises ValueError: adapter key 重复时抛出。
        """

        self._adapters: dict[WaitAdapterKey, WaitActivationAdapter] = {}
        for registration in registrations:
            if registration.adapter_key in self._adapters:
                raise ValueError("duplicate wait activation adapter registration")
            self._adapters[registration.adapter_key] = registration.adapter

    def resolve_adapter(
        self, adapter_key: WaitAdapterKey
    ) -> WaitActivationAdapter | None:
        """按 adapter key 解析 activation adapter。

        :param adapter_key: wait binding 使用的 adapter key。
        :returns: adapter；未注册时为 ``None``。
        """

        return self._adapters.get(adapter_key)


class WaitPoller:
    """claim-aware wait poller。

    poller 先通过 Host durable wait row CAS claim 取得处理权；外部 adapter
    调用发生在 Host transaction 外，ready/lost 结果统一交回 ``resolve_wait``。
    """

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        adapter_registry: WaitPollAdapterRegistry,
        resolver: WaitResolvePort,
        context: HostCallContext,
        policy: WaitPollerRuntimePolicy,
        clock: WaitPollClock | None = None,
        lifecycle_gate: WaitPollLifecycleGate | None = None,
        observation_runner: WaitObservationRunner | None = None,
        owner_id: str | None = None,
    ) -> None:
        """初始化 poller。

        :param transaction_runner: Host transaction runner。
        :param adapter_registry: poll adapter registry。
        :param resolver: resolve_wait 端口。
        :param context: poller 调用上下文。
        :param policy: 显式 poller runtime policy。
        :param clock: UTC 时钟；缺省使用系统 UTC 时间。
        :param lifecycle_gate: close gate；缺省为永不关闭。
        :param observation_runner: supervisor-owned bounded observation runner；
            同步 ``poll_once`` 测试未提供时创建当前 poller 私有 runner。
        :param owner_id: poller owner id；缺省为当前实例生成随机 id。
        :returns: ``None``。
        :raises ValueError: owner id 为空时抛出。
        """

        resolved_owner_id = owner_id if owner_id is not None else _new_poller_owner_id()
        if resolved_owner_id.strip() == "":
            raise ValueError("owner_id must be non-empty")
        self._transaction_runner = transaction_runner
        self._adapter_registry = adapter_registry
        self._resolver = resolver
        self._context = context
        self._clock = clock if clock is not None else _SystemUtcClock()
        self._policy = policy
        self._lifecycle_gate = (
            lifecycle_gate if lifecycle_gate is not None else _AlwaysOpenLifecycleGate()
        )
        self._observation_runner = (
            observation_runner
            if observation_runner is not None
            else WaitObservationRunner(
                max_outstanding_adapter_calls=(
                    policy.max_outstanding_adapter_calls
                ),
                thread_name_prefix=f"dayu-wait-observation-{resolved_owner_id}",
            )
        )
        self._owner_id = resolved_owner_id

    def poll_once(self) -> WaitPollOnceResult:
        """执行单轮 poll。

        :returns: 本轮 poll 摘要。
        """

        claimed_records: list[_ClaimedWaitRecord] = []
        claim_conflicts = 0
        for _ in range(self._policy.claim_batch_size):
            claim = self._claim_next_wait_record()
            if claim is None:
                break
            if isinstance(claim, StateMutationStatus):
                claim_conflicts += 1
                continue
            claimed_records.append(claim)
        if claimed_records or claim_conflicts > 0:
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.wait_poller.poll_once.claimed owner_id=%s claimed=%s "
                "claim_conflicts=%s",
                self._owner_id,
                len(claimed_records),
                claim_conflicts,
            )

        not_ready = 0
        resolved = 0
        lost = 0
        abandoned = 0
        adapter_errors = 0
        boundary_rejections = 0
        shutdown_skipped = 0
        next_poll_delay_seconds: float | None = None
        for claimed in claimed_records:
            record = claimed.record
            claim_id = claimed.claim_id
            if self._lifecycle_gate.is_closed():
                shutdown_skipped += 1
                claim_conflicts += self._release_shutdown_skipped(record, claim_id)
                continue
            if record.status is WaitRecordStatus.CANCELLED:
                abandoned_delta, adapter_error_delta, conflict_delta, shutdown_delta = (
                    self._abandon_cancelled_wait(record, claim_id)
                )
                abandoned += abandoned_delta
                adapter_errors += adapter_error_delta
                claim_conflicts += conflict_delta
                shutdown_skipped += shutdown_delta
                continue
            boundary_release = self._handle_time_boundary(
                record, claim_id
            )
            if boundary_release is not None:
                boundary_rejections += 1
                claim_conflicts += boundary_release
                continue
            adapter = self._adapter_registry.resolve_adapter(record.adapter_key)
            if adapter is None:
                _LOGGER.warning(
                    "wait poll adapter not registered; retrying wait_id=%s "
                    "adapter_key=%s",
                    record.wait_id,
                    record.adapter_key.value,
                )
                adapter_errors += 1
                claim_conflicts += self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.MISSING_ADAPTER,
                    error_code=_POLL_ERROR_CODE_MISSING_ADAPTER,
                    error_message=record.adapter_key.value,
                )
                continue
            try:
                adapter_snapshot = _adapter_snapshot_from_wait_record(record)
            except WaitAdapterSnapshotProjectionError as exc:
                adapter_errors += 1
                claim_conflicts += self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.ADAPTER_ERROR,
                    error_code=_POLL_ERROR_CODE_ADAPTER_EXCEPTION,
                    error_message=exc.__class__.__name__,
                )
                continue
            observation = self._observation_runner.observe(
                partial(adapter.poll_wait, adapter_snapshot),
                timeout_seconds=self._policy.adapter_call_timeout_seconds,
            )
            if isinstance(observation, WaitObservationFailed):
                exc = observation.error
                _LOGGER.warning(
                    "wait adapter poll failed; continuing wait_id=%s "
                    "adapter_key=%s error_type=%s",
                    record.wait_id,
                    record.adapter_key.value,
                    exc.__class__.__name__,
                )
                adapter_errors += 1
                claim_conflicts += self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.ADAPTER_ERROR,
                    error_code=_POLL_ERROR_CODE_ADAPTER_EXCEPTION,
                    error_message=exc.__class__.__name__,
                )
                continue
            if isinstance(observation, WaitObservationCapacityExceeded):
                adapter_errors += 1
                claim_conflicts += self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.ADAPTER_ERROR,
                    error_code=_POLL_ERROR_CODE_OBSERVATION_CAPACITY,
                    error_message="adapter observation capacity is exhausted",
                )
                continue
            if isinstance(observation, WaitObservationClosed):
                shutdown_skipped += 1
                claim_conflicts += self._release_shutdown_skipped(record, claim_id)
                continue
            if isinstance(observation, WaitObservationTimedOut):
                if self._lifecycle_gate.is_closed():
                    shutdown_skipped += 1
                    claim_conflicts += self._release_shutdown_skipped(record, claim_id)
                    continue
                adapter_errors += 1
                claim_conflicts += self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.ADAPTER_ERROR,
                    error_code=_POLL_ERROR_CODE_OBSERVATION_TIMEOUT,
                    error_message="wait adapter observation exceeded Host time budget",
                )
                continue
            if not isinstance(observation, WaitObservationPublished):
                raise RuntimeError("wait observation result is invalid")
            poll_result = observation.value
            poll_result_kind = _poll_result_kind(poll_result)
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.wait_poller.observe wait_id=%s adapter_key=%s outcome=%s",
                record.wait_id,
                record.adapter_key.value,
                poll_result_kind,
            )
            if isinstance(poll_result, WaitPollNotReady):
                not_ready += 1
                release_summary = self._release_not_ready(
                    record,
                    claim_id,
                )
                claim_conflicts += release_summary.claim_conflicts
                next_poll_delay_seconds = _min_optional_delay_seconds(
                    next_poll_delay_seconds,
                    release_summary.next_poll_delay_seconds,
                )
                continue
            if self._lifecycle_gate.is_closed():
                shutdown_skipped += 1
                claim_conflicts += self._release_shutdown_skipped(record, claim_id)
                continue
            resolve_status = self._resolve_claimed_wait(record, poll_result)
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.wait_poller.resolve wait_id=%s adapter_key=%s outcome=%s "
                "resolve_status=%s",
                record.wait_id,
                record.adapter_key.value,
                poll_result_kind,
                resolve_status.value,
            )
            if resolve_status is StateMutationStatus.UPDATED:
                if isinstance(poll_result, WaitPollLost):
                    lost += 1
                else:
                    resolved += 1
                continue
            adapter_errors += 1
            if resolve_status is StateMutationStatus.CAS_LOST:
                claim_conflicts += 1
                continue
            claim_conflicts += self._release_with_backoff(
                record,
                claim_id,
                outcome=WaitPollLastOutcome.RESOLVE_ERROR,
                error_code=_POLL_ERROR_CODE_RESOLVE_EXCEPTION,
                error_message=resolve_status.value,
            )
        result = WaitPollOnceResult(
            observed=len(claimed_records),
            not_ready=not_ready,
            resolved=resolved,
            lost=lost,
            abandoned=abandoned,
            adapter_errors=adapter_errors,
            boundary_rejections=boundary_rejections,
            claim_conflicts=claim_conflicts,
            shutdown_skipped=shutdown_skipped,
            next_poll_delay_seconds=self._next_poll_delay_seconds(
                observed=len(claimed_records),
                claim_conflicts=claim_conflicts,
                known_delay_seconds=next_poll_delay_seconds,
            ),
        )
        if _poll_result_has_activity(result):
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.wait_poller.poll_once.done owner_id=%s observed=%s not_ready=%s "
                "resolved=%s lost=%s abandoned=%s adapter_errors=%s "
                "boundary_rejections=%s claim_conflicts=%s shutdown_skipped=%s",
                self._owner_id,
                result.observed,
                result.not_ready,
                result.resolved,
                result.lost,
                result.abandoned,
                result.adapter_errors,
                result.boundary_rejections,
                result.claim_conflicts,
                result.shutdown_skipped,
            )
        return result

    def _claim_next_wait_record(self) -> _ClaimedWaitRecord | StateMutationStatus | None:
        """claim 下一条 eligible wait record。

        :returns: 成功时返回 claimed wait；无候选时返回 ``None``；CAS 冲突时返回状态。
        """

        if self._lifecycle_gate.is_closed():
            return None
        now = self._clock.now()
        claim_id = _new_poll_claim_id()
        status, record = self._transaction_runner.run_write(
            _ClaimWaitRecordOperation(
                claim_id=claim_id,
                owner_id=self._owner_id,
                now=format_utc_timestamp(now),
                claim_expires_at=format_utc_timestamp(
                    now + timedelta(seconds=self._policy.claim_ttl_seconds)
                ),
            )
        )
        if status is StateMutationStatus.UPDATED:
            if record is None:
                raise RuntimeError("poll claim updated without row")
            return _ClaimedWaitRecord(record=record, claim_id=claim_id)
        if status is StateMutationStatus.NOT_FOUND:
            return None
        return status

    def _next_poll_delay_seconds(
        self,
        *,
        observed: int,
        claim_conflicts: int,
        known_delay_seconds: float | None,
    ) -> float | None:
        """计算或读取下一次 active wait due 的等待秒数。

        :param observed: 本轮实际 claim 到的 wait 数。
        :param claim_conflicts: 本轮 claim / release 冲突数。
        :param known_delay_seconds: 本轮已从成功 release 推导出的下一次 due
            等待秒数。
        :returns: 下一次 due 的等待秒数；没有 active wait 或无法推导时为
            ``None``。
        """

        if known_delay_seconds is not None:
            return max(known_delay_seconds, 0.0)
        if observed > 0 or claim_conflicts > 0:
            return None
        now = self._clock.now()
        next_due_at = self._transaction_runner.run_read(
            _ReadNextPollDueAtOperation(format_utc_timestamp(now))
        )
        if next_due_at is None:
            return None
        delay_seconds = (parse_utc_timestamp(next_due_at) - now).total_seconds()
        return max(delay_seconds, 0.0)

    def _abandon_cancelled_wait(
        self, record: WaitRecordRow, claim_id: str
    ) -> tuple[int, int, int, int]:
        """处理已取消 wait 的 best-effort abandon。

        :param record: 已 claim 的 cancelled wait record。
        :param claim_id: 当前 claim id。
        :returns: abandoned、adapter_errors、claim_conflicts、shutdown_skipped 四元组。
        """

        if self._lifecycle_gate.is_closed():
            return 0, 0, self._release_shutdown_skipped(record, claim_id), 1
        adapter = self._adapter_registry.resolve_adapter(record.adapter_key)
        if adapter is None:
            _LOGGER.warning(
                "wait poll adapter not registered; retrying cancelled wait_id=%s "
                "adapter_key=%s",
                record.wait_id,
                record.adapter_key.value,
            )
            return (
                0,
                1,
                self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.MISSING_ADAPTER,
                    error_code=_POLL_ERROR_CODE_MISSING_ADAPTER,
                    error_message=record.adapter_key.value,
                ),
                0,
            )
        try:
            adapter_snapshot = _adapter_snapshot_from_wait_record(record)
        except WaitAdapterSnapshotProjectionError as exc:
            return (
                0,
                1,
                self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.ABANDON_ERROR,
                    error_code=_POLL_ERROR_CODE_ABANDON_EXCEPTION,
                    error_message=exc.__class__.__name__,
                ),
                0,
            )
        observation = self._observation_runner.observe(
            partial(adapter.abandon_wait, adapter_snapshot),
            timeout_seconds=self._policy.adapter_call_timeout_seconds,
        )
        if isinstance(observation, WaitObservationFailed):
            exc = observation.error
            _LOGGER.warning(
                "wait adapter abandon failed; continuing wait_id=%s "
                "adapter_key=%s error_type=%s",
                record.wait_id,
                record.adapter_key.value,
                exc.__class__.__name__,
            )
            return (
                0,
                1,
                self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.ABANDON_ERROR,
                    error_code=_POLL_ERROR_CODE_ABANDON_EXCEPTION,
                    error_message=exc.__class__.__name__,
                ),
                0,
            )
        if isinstance(observation, WaitObservationCapacityExceeded):
            return (
                0,
                1,
                self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.ABANDON_ERROR,
                    error_code=_POLL_ERROR_CODE_OBSERVATION_CAPACITY,
                    error_message="adapter observation capacity is exhausted",
                ),
                0,
            )
        if isinstance(observation, WaitObservationClosed):
            return 0, 0, self._release_shutdown_skipped(record, claim_id), 1
        if isinstance(observation, WaitObservationTimedOut):
            if self._lifecycle_gate.is_closed():
                return 0, 0, self._release_shutdown_skipped(record, claim_id), 1
            return (
                0,
                1,
                self._release_with_backoff(
                    record,
                    claim_id,
                    outcome=WaitPollLastOutcome.ABANDON_ERROR,
                    error_code=_POLL_ERROR_CODE_ABANDON_TIMEOUT,
                    error_message="wait adapter abandon exceeded Host time budget",
                ),
                0,
            )
        if not isinstance(observation, WaitObservationPublished):
            raise RuntimeError("wait abandon observation result is invalid")
        lifecycle_result = observation.value
        last_outcome = _last_outcome_for_lifecycle_result(lifecycle_result)
        now = format_utc_timestamp(self._clock.now())
        status = self._transaction_runner.run_write(
            _MarkWaitRecordAbandonedOperation(
                wait_id=record.wait_id,
                claim_id=claim_id,
                abandoned_at=now,
                updated_at=now,
                last_outcome=last_outcome,
            )
        )
        if status is StateMutationStatus.UPDATED:
            return 1, 0, 0, 0
        return 0, 0, self._release_with_backoff(
            record,
            claim_id,
            outcome=WaitPollLastOutcome.ABANDON_ERROR,
            error_code=_POLL_ERROR_CODE_ABANDON_EXCEPTION,
            error_message=status.value,
        ), 0

    def _handle_time_boundary(
        self, record: WaitRecordRow, claim_id: str
    ) -> int | None:
        """在 provider observation 前处理 expiry 或非法 boundary。

        :param record: 已 claim 的 wait record。
        :param claim_id: 当前 claim id。
        :returns: 处理了边界错误时返回 CAS 冲突计数；边界仍 active 时返回
            ``None``。
        """

        decision = classify_wait_time_boundary(record, observed_at=self._clock.now())
        if decision.kind is WaitBoundaryDecisionKind.ACTIVE:
            return None
        if decision.kind is WaitBoundaryDecisionKind.EXPIRED:
            result = self._resolver.expire_wait(
                ExpireWaitInput(
                    wait_id=record.wait_id,
                    observed_at=self._clock.now(),
                    actor=self._context.actor,
                    source=WaitResolutionSource.POLL,
                )
            )
            return (
                0
                if result.transition.status
                in (StateMutationStatus.UPDATED, StateMutationStatus.CAS_LOST)
                else 1
            )
        error_code = _POLL_ERROR_CODE_INVALID_TIME_BOUNDARY
        error_message = decision.boundary_field
        _LOGGER.warning(
            "wait poll skipped by Host time boundary; wait_id=%s adapter_key=%s "
            "boundary_status=%s boundary_field=%s",
            record.wait_id,
            record.adapter_key.value,
            decision.kind.value,
            decision.boundary_field,
        )
        return self._release_with_backoff(
            record,
            claim_id,
            outcome=WaitPollLastOutcome.BOUNDARY_REJECTED,
            error_code=error_code,
            error_message=error_message,
        )

    def _resolve_claimed_wait(
        self, record: WaitRecordRow, poll_result: WaitPollReady | WaitPollLost
    ) -> StateMutationStatus:
        """把 ready/lost poll 结果交给公共 ``resolve_wait`` pipeline。

        :param record: 已 claim 的 wait record。
        :param poll_result: ready 或 lost poll 结果。
        :returns: ``UPDATED`` 表示 resolve 成功；``CAS_LOST`` 表示异常后已确认终态。
        """

        request = ResolveWaitRequest(
            context=self._context,
            idempotency_key=_poll_idempotency_key(record),
            outcome=poll_result.outcome,
            source=WaitResolutionSource.POLL,
            observed_at=self._clock.now(),
        )
        try:
            self._resolver.resolve_wait(record.wait_id, request)
            return StateMutationStatus.UPDATED
        except Exception as exc:
            _LOGGER.warning(
                "wait poll resolve failed; continuing wait_id=%s "
                "adapter_key=%s error_type=%s",
                record.wait_id,
                record.adapter_key.value,
                exc.__class__.__name__,
            )
            try:
                latest = self._transaction_runner.run_read(
                    _ReadWaitRecordOperation(record.wait_id)
                )
            except Exception as read_exc:
                _LOGGER.warning(
                    "wait poll resolve recovery read failed; continuing wait_id=%s "
                    "adapter_key=%s error_type=%s",
                    record.wait_id,
                    record.adapter_key.value,
                    read_exc.__class__.__name__,
                )
                return StateMutationStatus.INVALID_STATE
            if latest is not None and latest.status in (
                WaitRecordStatus.RESOLVED,
                WaitRecordStatus.FAILED,
                WaitRecordStatus.LOST,
            ):
                return StateMutationStatus.CAS_LOST
            return StateMutationStatus.INVALID_STATE

    def _release_with_backoff(
        self,
        record: WaitRecordRow,
        claim_id: str,
        *,
        outcome: WaitPollLastOutcome,
        error_code: str | None,
        error_message: str | None,
    ) -> int:
        """释放 claim 并写入 durable backoff。

        :param record: 已 claim 的 wait record。
        :param claim_id: 当前 claim id。
        :param outcome: 最近一次 poller outcome。
        :param error_code: 最近一次错误码。
        :param error_message: 最近一次错误消息。
        :returns: CAS 冲突计数。
        """

        now = self._clock.now()
        next_attempt = record.poll_backoff_attempt + 1
        status = self._transaction_runner.run_write(
            _ReleaseWaitRecordClaimOperation(
                wait_id=record.wait_id,
                claim_id=claim_id,
                next_observe_at=format_utc_timestamp(
                    now
                    + timedelta(
                        seconds=_backoff_delay_seconds(next_attempt, self._policy)
                    )
                ),
                backoff_attempt=next_attempt,
                last_outcome=outcome,
                last_error_code=error_code,
                last_error_message=error_message,
                updated_at=format_utc_timestamp(now),
            )
        )
        if status is StateMutationStatus.UPDATED:
            return 0
        return 1

    def _release_not_ready(
        self, record: WaitRecordRow, claim_id: str
    ) -> _ReleaseNotReadySummary:
        """释放正常运行中 wait 的 claim 并安排短间隔复查。

        :param record: 已 claim 的 wait record。
        :param claim_id: 当前 claim id。
        :returns: release 摘要。
        """

        now = self._clock.now()
        delay_seconds = _not_ready_delay_seconds(self._policy)
        status = self._transaction_runner.run_write(
            _ReleaseWaitRecordClaimOperation(
                wait_id=record.wait_id,
                claim_id=claim_id,
                next_observe_at=format_utc_timestamp(
                    now + timedelta(seconds=delay_seconds)
                ),
                backoff_attempt=0,
                last_outcome=WaitPollLastOutcome.NOT_READY,
                last_error_code=None,
                last_error_message=None,
                updated_at=format_utc_timestamp(now),
            )
        )
        if status is StateMutationStatus.UPDATED:
            return _ReleaseNotReadySummary(
                claim_conflicts=0,
                next_poll_delay_seconds=delay_seconds,
            )
        return _ReleaseNotReadySummary(
            claim_conflicts=1,
            next_poll_delay_seconds=None,
        )

    def _release_shutdown_skipped(
        self, record: WaitRecordRow, claim_id: str
    ) -> int:
        """关闭门控触发后释放 claim 并保持 wait 可重试。

        :param record: 已 claim 的 wait record。
        :param claim_id: 当前 claim id。
        :returns: CAS 冲突计数。
        """

        return self._release_with_backoff(
            record,
            claim_id,
            outcome=WaitPollLastOutcome.SHUTDOWN_SKIPPED,
            error_code=_POLL_ERROR_CODE_SHUTDOWN_SKIPPED,
            error_message=None,
        )


class WaitPollerSupervisor:
    """wait poller background lifecycle supervisor。

    supervisor 只负责本地 background loop、close gate、可取消 sleep 和
    runtime diagnostics；它不写 EventLog，也不接入 ``open_host``。
    """

    def __init__(
        self,
        *,
        poller_factory: WaitPollerFactory,
        policy: WaitPollerRuntimePolicy,
        owner_id: str | None = None,
    ) -> None:
        """初始化 supervisor。

        :param poller_factory: 创建 poller 的 factory；后台线程必须由 factory
            提供线程内可用的 durable runner。
        :param policy: 显式 runtime policy。
        :param owner_id: poller owner id；缺省生成随机 id。
        :returns: ``None``。
        :raises ValueError: owner id 为空时抛出。
        """

        resolved_owner_id = owner_id if owner_id is not None else _new_poller_owner_id()
        if resolved_owner_id.strip() == "":
            raise ValueError("owner_id must be non-empty")
        self._policy = policy
        self._owner_id = resolved_owner_id
        self._poller_factory = poller_factory
        self._close_event = threading.Event()
        self._wakeup_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._opened = False
        self._diagnostics = _initial_diagnostics()
        self._observation_runner = WaitObservationRunner(
            max_outstanding_adapter_calls=(
                self._policy.max_outstanding_adapter_calls
            ),
            thread_name_prefix=f"dayu-wait-observation-{self._owner_id}",
            on_drained=self._on_observations_drained,
        )

    def open(self) -> None:
        """启动 background poll loop。

        :returns: ``None``。
        :raises RuntimeError: failed supervisor 或已停止 supervisor 被重新打开时抛出。
        """

        with self._lock:
            if self._diagnostics.status is WaitPollerLoopStatus.RUNNING:
                return
            if self._diagnostics.status is WaitPollerLoopStatus.FAILED:
                raise RuntimeError("failed wait poller supervisor cannot be opened")
            if self._opened:
                raise RuntimeError("stopped wait poller supervisor cannot be reopened")
            self._opened = True
            self._close_event.clear()
            self._diagnostics = _diagnostics_with_status(
                self._diagnostics, WaitPollerLoopStatus.RUNNING
            )
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"dayu-wait-poller-{self._owner_id}",
                daemon=True,
            )
            thread = self._thread
        thread.start()

    def wakeup(self) -> None:
        """唤醒 background poll loop 立即重试。

        :returns: ``None``。
        """

        self._wakeup_event.set()

    def close(self) -> None:
        """按一个 shared deadline 关闭 poll loop 与 observation threads。

        :returns: ``None``。
        """

        with self._lock:
            thread = self._thread
            observations_live = (
                self._observation_runner.diagnostics_snapshot().live_count
            )
            if (
                self._diagnostics.status
                in (WaitPollerLoopStatus.STOPPED, WaitPollerLoopStatus.FAILED)
                and (thread is None or not thread.is_alive())
                and observations_live == 0
            ):
                self._thread = None
                self._close_event.set()
                self._wakeup_event.set()
                return
            if thread is threading.current_thread():
                raise _WaitPollerSelfCloseError(_WAIT_POLLER_SELF_CLOSE_MESSAGE)
            if self._diagnostics.status is not WaitPollerLoopStatus.FAILED:
                self._diagnostics = _diagnostics_with_status(
                    self._diagnostics, WaitPollerLoopStatus.CLOSING
                )
            self._close_event.set()
            self._wakeup_event.set()
        self._observation_runner.begin_close()
        deadline = time.monotonic() + self._policy.close_drain_timeout_seconds
        if thread is not None:
            thread.join(max(0.0, deadline - time.monotonic()))
        observations_drained = self._observation_runner.drain_until(deadline)
        thread_alive = thread is not None and thread.is_alive()
        if thread_alive or not observations_drained:
            _LOGGER.warning(
                "wait poller close drain timeout; detached bounded observations "
                "owner_id=%s poller_alive=%s observations_live=%s",
                self._owner_id,
                thread_alive,
                self._observation_runner.diagnostics_snapshot().live_count,
            )
            with self._lock:
                self._diagnostics = _diagnostics_with_close_timeout(
                    self._diagnostics
                )
        with self._lock:
            if self._thread is thread and not thread_alive:
                self._thread = None
            if (
                self._diagnostics.status is not WaitPollerLoopStatus.FAILED
                and not thread_alive
                and observations_drained
            ):
                self._diagnostics = _diagnostics_with_status(
                    self._diagnostics, WaitPollerLoopStatus.STOPPED
                )
            elif self._diagnostics.status is not WaitPollerLoopStatus.FAILED:
                self._diagnostics = _diagnostics_with_status(
                    self._diagnostics, WaitPollerLoopStatus.CLOSING
                )

    def drain_once_for_test(self) -> WaitPollOnceResult:
        """同步执行单轮 poll 并更新 runtime diagnostics。

        :returns: 单轮 poll 结果。
        """

        result = self._poll_once()
        self._record_poll_result(result)
        return result

    def diagnostics_snapshot(self) -> WaitPollerDiagnosticsSnapshot:
        """读取 runtime diagnostics 快照。

        :returns: diagnostics snapshot。
        """

        with self._lock:
            return self._diagnostics

    def observation_diagnostics_snapshot(
        self,
    ) -> WaitObservationDiagnosticsSnapshot:
        """读取 bounded observation registry diagnostics。

        :returns: observation diagnostics snapshot。
        """

        return self._observation_runner.diagnostics_snapshot()

    def is_closed(self) -> bool:
        """返回 close gate 状态。

        :returns: close 已开始时返回 ``True``。
        """

        return self._close_event.is_set()

    def _run_loop(self) -> None:
        """运行 background poll loop。

        :returns: ``None``。
        """

        while not self._close_event.is_set():
            try:
                result = self._poll_once()
                self._record_poll_result(result)
                if self._close_event.is_set():
                    break
                self._sleep_until_next_poll(result)
            except _WaitPollerSelfCloseError as exc:
                _LOGGER.exception(
                    "wait poller loop failed owner_id=%s error_type=%s",
                    self._owner_id,
                    exc.__class__.__name__,
                )
                with self._lock:
                    self._diagnostics = _diagnostics_with_fatal_error(
                        self._diagnostics, exc
                    )
                self._close_event.set()
                self._wakeup_event.set()
                break
            except Exception as exc:
                _LOGGER.exception(
                    "wait poller round failed; retrying owner_id=%s error_type=%s",
                    self._owner_id,
                    exc.__class__.__name__,
                )
                with self._lock:
                    self._diagnostics = _diagnostics_with_round_error(
                        self._diagnostics, exc
                    )
                if self._close_event.is_set():
                    break
                self._wakeup_event.wait(self._policy.poll_interval_seconds)
                self._wakeup_event.clear()
        with self._lock:
            if (
                self._diagnostics.status is not WaitPollerLoopStatus.FAILED
                and self._observation_runner.diagnostics_snapshot().live_count == 0
            ):
                self._diagnostics = _diagnostics_with_status(
                    self._diagnostics, WaitPollerLoopStatus.STOPPED
                )
            elif self._diagnostics.status is not WaitPollerLoopStatus.FAILED:
                self._diagnostics = _diagnostics_with_status(
                    self._diagnostics, WaitPollerLoopStatus.CLOSING
                )
            if self._thread is threading.current_thread():
                self._thread = None

    def _poll_once(self) -> WaitPollOnceResult:
        """构造 poller 并执行单轮 poll。

        :returns: 单轮 poll 结果。
        """

        poller = self._poller_factory.create_wait_poller(
            self, self._observation_runner
        )
        return poller.poll_once()

    def _on_observations_drained(self) -> None:
        """最后一个 invalidated observation thread 结束后收口状态。

        :returns: ``None``。
        """

        with self._lock:
            thread = self._thread
            if (
                self._close_event.is_set()
                and (thread is None or not thread.is_alive())
                and self._diagnostics.status is not WaitPollerLoopStatus.FAILED
            ):
                self._thread = None
                self._diagnostics = _diagnostics_with_status(
                    self._diagnostics, WaitPollerLoopStatus.STOPPED
                )

    def _sleep_until_next_poll(self, result: WaitPollOnceResult) -> None:
        """按单轮结果等待下一次 poll，支持 wakeup 与 close 立即打断。

        :param result: 刚完成的单轮 poll result。
        :returns: ``None``。
        """

        interval_seconds = _next_loop_interval_seconds(result, self._policy)
        was_woken = self._wakeup_event.wait(interval_seconds)
        if was_woken:
            self._wakeup_event.clear()

    def _record_poll_result(self, result: WaitPollOnceResult) -> None:
        """累加 poll result 到 diagnostics。

        :param result: 单轮 poll 结果。
        :returns: ``None``。
        """

        with self._lock:
            self._diagnostics = _diagnostics_with_poll_result(
                self._diagnostics, result
            )


def _poll_idempotency_key(wait_record: WaitRecordRow) -> str:
    """构造 poll source 的稳定 resolve_wait 幂等键。

    :param wait_record: wait record。
    :returns: 幂等键。
    """

    digest = sha256_digest_json(
        {
            "source": WaitResolutionSource.POLL.value,
            "wait_id": wait_record.wait_id,
        }
    ).removeprefix("sha256:")
    return f"poll-{digest}"


def _poll_result_kind(result: WaitPollResult) -> str:
    """返回日志安全的 poll 结果类别。

    :param result: adapter 返回的 poll 结果。
    :returns: ``not_ready``、``ready`` 或 ``lost``。
    :raises TypeError: 收到未知 poll 结果类型时抛出。
    """

    if isinstance(result, WaitPollNotReady):
        return "not_ready"
    if isinstance(result, WaitPollReady):
        return "ready"
    if isinstance(result, WaitPollLost):
        return "lost"
    raise TypeError("unsupported wait poll result")


def _backoff_delay_seconds(
    backoff_attempt: int, policy: WaitPollerRuntimePolicy
) -> float:
    """计算 poll retry backoff delay。

    :param backoff_attempt: 即将写入的 backoff attempt 计数。
    :param policy: runtime policy。
    :returns: delay 秒数。
    :raises ValueError: ``backoff_attempt`` 非正数时抛出。
    """

    if backoff_attempt <= 0:
        raise ValueError("backoff_attempt must be positive")
    delay = policy.backoff_initial_delay_seconds * (
        policy.backoff_multiplier ** (backoff_attempt - 1)
    )
    return min(delay, policy.backoff_max_delay_seconds)


def _not_ready_delay_seconds(policy: WaitPollerRuntimePolicy) -> float:
    """返回正常 not-ready wait 的下一次观察间隔。

    :param policy: runtime policy。
    :returns: 间隔秒数。
    """

    return policy.not_ready_observe_interval_seconds


def _next_loop_interval_seconds(
    result: WaitPollOnceResult, policy: WaitPollerRuntimePolicy
) -> float:
    """根据单轮结果计算 supervisor 下一次唤醒间隔。

    :param result: 单轮 poll result。
    :param policy: runtime policy。
    :returns: 下一次 loop sleep 秒数。
    """

    if not _poll_result_has_activity(result):
        if result.next_poll_delay_seconds is not None:
            return min(
                max(result.next_poll_delay_seconds, 0.0),
                policy.idle_poll_interval_seconds,
            )
        return policy.idle_poll_interval_seconds
    if result.next_poll_delay_seconds is not None:
        return max(result.next_poll_delay_seconds, 0.0)
    return policy.poll_interval_seconds


def _min_optional_delay_seconds(
    current: float | None, candidate: float | None
) -> float | None:
    """合并可选 delay，返回最短的已知等待秒数。

    :param current: 当前已知 delay；未知时为 ``None``。
    :param candidate: 候选 delay；未知时为 ``None``。
    :returns: 两者中更短的已知 delay；都未知时为 ``None``。
    """

    if candidate is None:
        return current
    if current is None:
        return candidate
    return min(current, candidate)


def _poll_result_has_activity(result: WaitPollOnceResult) -> bool:
    """判断单轮 poll result 是否包含需要逐轮记录的活动。

    :param result: 单轮 poll result。
    :returns: 有 claim、resolve、错误或关闭跳过等活动时返回 ``True``。
    """

    return (
        result.observed > 0
        or result.not_ready > 0
        or result.resolved > 0
        or result.lost > 0
        or result.abandoned > 0
        or result.adapter_errors > 0
        or result.boundary_rejections > 0
        or result.claim_conflicts > 0
        or result.shutdown_skipped > 0
    )


def _last_outcome_for_lifecycle_result(
    lifecycle_result: WaitExternalJobLifecycleResult,
) -> WaitPollLastOutcome:
    """把 typed external lifecycle result 映射为 durable poll outcome。

    :param lifecycle_result: adapter 返回的 cancelled wait lifecycle 结果。
    :returns: durable poll outcome。
    :raises TypeError: lifecycle result 类型不属于封闭联合时抛出。
    """

    if isinstance(lifecycle_result, WaitExternalJobLifecycleApplied):
        return WaitPollLastOutcome.ABANDONED
    if isinstance(lifecycle_result, WaitExternalJobLifecycleUnsupported):
        return WaitPollLastOutcome.ABANDON_UNSUPPORTED
    if isinstance(lifecycle_result, WaitExternalJobLifecycleNoop):
        return WaitPollLastOutcome.ABANDON_NOOP
    raise TypeError("unknown wait external job lifecycle result type")


def _require_positive_float(value: float, *, field_name: str) -> None:
    """校验正浮点数 policy 字段。

    :param value: 待校验数值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 数值类型非法时抛出。
    :raises ValueError: 数值非 finite 或小于等于零时抛出。
    """

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be a finite positive number")
    if not math.isfinite(float(value)) or value <= 0.0:
        raise ValueError(f"{field_name} must be a finite positive number")


def _initial_diagnostics() -> WaitPollerDiagnosticsSnapshot:
    """构造初始 supervisor diagnostics。

    :returns: 初始 diagnostics snapshot。
    """

    return WaitPollerDiagnosticsSnapshot(
        status=WaitPollerLoopStatus.NOT_STARTED,
        poll_rounds=0,
        observed=0,
        not_ready=0,
        resolved=0,
        lost=0,
        abandoned=0,
        adapter_errors=0,
        boundary_rejections=0,
        claim_conflicts=0,
        shutdown_skipped=0,
        close_drain_timeouts=0,
        round_errors=0,
        fatal_errors=0,
        last_error_type=None,
        last_error_message=None,
    )


def _diagnostics_with_status(
    diagnostics: WaitPollerDiagnosticsSnapshot, status: WaitPollerLoopStatus
) -> WaitPollerDiagnosticsSnapshot:
    """复制 diagnostics 并替换状态。

    :param diagnostics: 原 diagnostics。
    :param status: 新状态。
    :returns: 更新后的 diagnostics。
    """

    return WaitPollerDiagnosticsSnapshot(
        status=status,
        poll_rounds=diagnostics.poll_rounds,
        observed=diagnostics.observed,
        not_ready=diagnostics.not_ready,
        resolved=diagnostics.resolved,
        lost=diagnostics.lost,
        abandoned=diagnostics.abandoned,
        adapter_errors=diagnostics.adapter_errors,
        boundary_rejections=diagnostics.boundary_rejections,
        claim_conflicts=diagnostics.claim_conflicts,
        shutdown_skipped=diagnostics.shutdown_skipped,
        close_drain_timeouts=diagnostics.close_drain_timeouts,
        round_errors=diagnostics.round_errors,
        fatal_errors=diagnostics.fatal_errors,
        last_error_type=diagnostics.last_error_type,
        last_error_message=diagnostics.last_error_message,
    )


def _diagnostics_with_poll_result(
    diagnostics: WaitPollerDiagnosticsSnapshot, result: WaitPollOnceResult
) -> WaitPollerDiagnosticsSnapshot:
    """复制 diagnostics 并累加 poll result。

    :param diagnostics: 原 diagnostics。
    :param result: 单轮 poll result。
    :returns: 更新后的 diagnostics。
    """

    return WaitPollerDiagnosticsSnapshot(
        status=diagnostics.status,
        poll_rounds=diagnostics.poll_rounds + 1,
        observed=diagnostics.observed + result.observed,
        not_ready=diagnostics.not_ready + result.not_ready,
        resolved=diagnostics.resolved + result.resolved,
        lost=diagnostics.lost + result.lost,
        abandoned=diagnostics.abandoned + result.abandoned,
        adapter_errors=diagnostics.adapter_errors + result.adapter_errors,
        boundary_rejections=(
            diagnostics.boundary_rejections + result.boundary_rejections
        ),
        claim_conflicts=diagnostics.claim_conflicts + result.claim_conflicts,
        shutdown_skipped=diagnostics.shutdown_skipped + result.shutdown_skipped,
        close_drain_timeouts=diagnostics.close_drain_timeouts,
        round_errors=diagnostics.round_errors,
        fatal_errors=diagnostics.fatal_errors,
        last_error_type=diagnostics.last_error_type,
        last_error_message=diagnostics.last_error_message,
    )


def _diagnostics_with_close_timeout(
    diagnostics: WaitPollerDiagnosticsSnapshot,
) -> WaitPollerDiagnosticsSnapshot:
    """复制 diagnostics 并记录 close drain timeout。

    :param diagnostics: 原 diagnostics。
    :returns: 更新后的 diagnostics。
    """

    return WaitPollerDiagnosticsSnapshot(
        status=diagnostics.status,
        poll_rounds=diagnostics.poll_rounds,
        observed=diagnostics.observed,
        not_ready=diagnostics.not_ready,
        resolved=diagnostics.resolved,
        lost=diagnostics.lost,
        abandoned=diagnostics.abandoned,
        adapter_errors=diagnostics.adapter_errors,
        boundary_rejections=diagnostics.boundary_rejections,
        claim_conflicts=diagnostics.claim_conflicts,
        shutdown_skipped=diagnostics.shutdown_skipped,
        close_drain_timeouts=diagnostics.close_drain_timeouts + 1,
        round_errors=diagnostics.round_errors,
        fatal_errors=diagnostics.fatal_errors,
        last_error_type=diagnostics.last_error_type,
        last_error_message=diagnostics.last_error_message,
    )


def _diagnostics_with_fatal_error(
    diagnostics: WaitPollerDiagnosticsSnapshot, exc: Exception
) -> WaitPollerDiagnosticsSnapshot:
    """复制 diagnostics 并记录 fatal loop exception。

    :param diagnostics: 原 diagnostics。
    :param exc: fatal exception。
    :returns: 更新后的 diagnostics。
    """

    return WaitPollerDiagnosticsSnapshot(
        status=WaitPollerLoopStatus.FAILED,
        poll_rounds=diagnostics.poll_rounds,
        observed=diagnostics.observed,
        not_ready=diagnostics.not_ready,
        resolved=diagnostics.resolved,
        lost=diagnostics.lost,
        abandoned=diagnostics.abandoned,
        adapter_errors=diagnostics.adapter_errors,
        boundary_rejections=diagnostics.boundary_rejections,
        claim_conflicts=diagnostics.claim_conflicts,
        shutdown_skipped=diagnostics.shutdown_skipped,
        close_drain_timeouts=diagnostics.close_drain_timeouts,
        round_errors=diagnostics.round_errors,
        fatal_errors=diagnostics.fatal_errors + 1,
        last_error_type=exc.__class__.__name__,
        last_error_message=str(exc),
    )


def _diagnostics_with_round_error(
    diagnostics: WaitPollerDiagnosticsSnapshot, exc: Exception
) -> WaitPollerDiagnosticsSnapshot:
    """复制 diagnostics 并记录单轮可恢复异常。

    :param diagnostics: 原 diagnostics。
    :param exc: 本轮异常。
    :returns: 保持原 loop 状态并记录异常计数后的 diagnostics。
    """

    return WaitPollerDiagnosticsSnapshot(
        status=diagnostics.status,
        poll_rounds=diagnostics.poll_rounds,
        observed=diagnostics.observed,
        not_ready=diagnostics.not_ready,
        resolved=diagnostics.resolved,
        lost=diagnostics.lost,
        abandoned=diagnostics.abandoned,
        adapter_errors=diagnostics.adapter_errors,
        boundary_rejections=diagnostics.boundary_rejections,
        claim_conflicts=diagnostics.claim_conflicts,
        shutdown_skipped=diagnostics.shutdown_skipped,
        close_drain_timeouts=diagnostics.close_drain_timeouts,
        round_errors=diagnostics.round_errors + 1,
        fatal_errors=diagnostics.fatal_errors,
        last_error_type=exc.__class__.__name__,
        last_error_message=str(exc),
    )


def _new_poll_claim_id() -> str:
    """生成 poll claim id。

    :returns: poll claim id。
    """

    return f"poll-claim-{uuid4()}"


def _adapter_snapshot_from_wait_record(record: WaitRecordRow) -> WaitAdapterSnapshot:
    """把 Host durable wait row 投影为 adapter-facing snapshot。

    :param record: Host durable wait row。
    :returns: adapter-facing 最小 snapshot。
    :raises WaitAdapterSnapshotProjectionError: resume token 或创建时间非法时抛出。
    """

    try:
        _validate_adapter_snapshot_resume_token(record.resume_token)
        created_at = parse_utc_timestamp(record.created_at)
        return WaitAdapterSnapshot(
            tool_name=record.tool_name,
            resume_token=record.resume_token,
            created_at=created_at,
        )
    except (TypeError, ValueError) as exc:
        raise WaitAdapterSnapshotProjectionError(
            "wait record cannot be projected to adapter snapshot"
        ) from exc


def _validate_adapter_snapshot_resume_token(resume_token: str) -> None:
    """校验 Host wait adapter snapshot 的 resume token 边界。

    :param resume_token: durable wait row 中的 resume token。
    :returns: ``None``。
    :raises ValueError: token 为空或超过 Host public 上限时抛出。
    """

    if resume_token.strip() == "":
        raise ValueError("resume_token must be non-empty")
    if len(resume_token) > HOST_WAIT_RESUME_TOKEN_MAX_LENGTH:
        raise ValueError("resume_token is too long")


def _new_poller_owner_id() -> str:
    """生成 poller owner id。

    :returns: poller owner id。
    """

    return f"poller-{uuid4()}"


__all__ = [
    "WaitActivationAdapter",
    "WaitActivationAdapterRegistration",
    "WaitActivationRegistry",
    "WaitActivationRequest",
    "WaitAdapterSnapshot",
    "WaitAdapterSnapshotProjectionError",
    "WaitAdapterBinding",
    "WaitAdapterRegistry",
    "WaitExternalJobLifecycleAction",
    "WaitExternalJobLifecycleApplied",
    "WaitExternalJobLifecycleNoop",
    "WaitExternalJobLifecycleResult",
    "WaitExternalJobLifecycleUnsupported",
    "WaitExternalJobRefSource",
    "WaitPollAdapter",
    "WaitPollAdapterRegistration",
    "WaitPollAdapterRegistry",
    "WaitPollLost",
    "WaitPollNotReady",
    "WaitPollLifecycleGate",
    "WaitPollerDiagnosticsSnapshot",
    "WaitPollerFactory",
    "WaitPollerLoopStatus",
    "WaitPollerRuntimePolicy",
    "WaitPollerSupervisor",
    "WaitPollOnceResult",
    "WaitPollReady",
    "WaitPollResult",
    "WaitPoller",
    "WaitResolvePort",
    "WaitResumePolicy",
]
