"""Host API 类型契约。

本模块定义 Host 后续阶段可依赖的 request、snapshot、status、typed
HostEvent、error、context、public opener options 与低层本地执行装配类型。
它不实现 command path、durable store、EventLog 写入、dispatch scheduler、
policy provider 或 Engine 调用路径。普通 Service-facing 包根导出由
``dayu.host.__all__`` 收口；低层测试如需 legacy command / stream 类型，应
显式导入内部模块路径。
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, TypeAlias

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import ToolCancelledOutcome
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO,
    context_budget_policy_from_threshold_tokens,
)
from dayu.host.compaction import ContextCompactor
from dayu.host._public_validation import (
    require_non_empty as _require_non_empty,
)
from dayu.host._public_validation import (
    require_optional_non_empty as _require_optional_non_empty,
)
from dayu.host.memory import (
    MemoryProjectionPolicy,
    default_memory_projection_policy,
)
from dayu.host.tooling import HostToolingOptions as _HostToolingOptions

_DEFAULT_COMMAND_MINIMUM_PROTECTION_TOKENS = 256


HOST_EVENT_STREAM_DEFAULT_LIMIT = 100
HOST_EVENT_STREAM_MAX_LIMIT = 1000
HOST_WAIT_ID_MAX_LENGTH = 128
HOST_WAIT_ADAPTER_KEY_MAX_LENGTH = 128
HOST_WAIT_TOOL_CALL_ID_MAX_LENGTH = 256
HOST_WAIT_TOOL_NAME_MAX_LENGTH = 128
HOST_WAIT_RESUME_TOKEN_MAX_LENGTH = 2048
HOST_WAIT_SNAPSHOT_ID_MAX_LENGTH = 256
HOST_WAIT_EXTERNAL_JOB_ID_MAX_LENGTH = 512
HOST_WAIT_PROVIDER_STATUS_REF_MAX_LENGTH = 512
HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH = 256
HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT = 500
HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT = 1000

_WAIT_ADAPTER_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
_SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _require_non_negative(value: int, *, field_name: str) -> None:
    """校验整数游标或序列号不为负数。

    :param value: 待校验的整数值。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises ValueError: ``value`` 小于零时抛出。
    """

    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验整数配置值不为负数且不是布尔值。

    :param value: 待校验的整数值。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises TypeError: ``value`` 不是严格整数时抛出。
    :raises ValueError: ``value`` 小于零时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验整数配置值大于零。

    :param value: 待校验的整数值。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises TypeError: ``value`` 不是严格整数时抛出。
    :raises ValueError: ``value`` 小于或等于零时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_positive_float(value: float, *, field_name: str) -> None:
    """校验浮点配置值大于零。

    :param value: 待校验的浮点值。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises TypeError: ``value`` 不是严格数值时抛出。
    :raises ValueError: ``value`` 小于或等于零时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be float")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_path(value: pathlib.Path, *, field_name: str) -> None:
    """校验路径配置字段使用 ``pathlib.Path`` 实例。

    :param value: 待校验的路径值。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises TypeError: ``value`` 不是 ``pathlib.Path`` 实例时抛出。
    """

    if not isinstance(value, pathlib.Path):
        raise TypeError(f"{field_name} must be pathlib.Path")


def _require_bool(value: bool, *, field_name: str) -> None:
    """校验布尔配置字段使用 ``bool`` 值。

    :param value: 待校验的布尔值。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises TypeError: ``value`` 不是 ``bool`` 时抛出。
    """

    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool")


def _require_max_length(value: str, *, field_name: str, max_length: int) -> None:
    """校验必填字符串非空且不超过长度上限。

    :param value: 待校验字符串。
    :param field_name: 错误消息中使用的字段名。
    :param max_length: 允许的最大字符数。
    :returns: 无返回值。
    :raises ValueError: 字符串为空或超过长度上限时抛出。
    """

    _require_non_empty(value, field_name=field_name)
    if len(value) > max_length:
        raise ValueError(f"{field_name} length must be <= {max_length}")


def _require_optional_max_length(
    value: str | None, *, field_name: str, max_length: int
) -> None:
    """校验可选字符串存在时非空且不超过长度上限。

    :param value: 待校验字符串或 ``None``。
    :param field_name: 错误消息中使用的字段名。
    :param max_length: 允许的最大字符数。
    :returns: 无返回值。
    :raises ValueError: 字符串存在但为空或超过长度上限时抛出。
    """

    if value is not None:
        _require_max_length(value, field_name=field_name, max_length=max_length)


def _require_sha256_digest(value: str, *, field_name: str) -> None:
    """校验字符串为 Host 标准 sha256 digest。

    :param value: 待校验 digest。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises ValueError: digest 格式无效时抛出。
    """

    if _SHA256_DIGEST_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_optional_sha256_digest(
    value: str | None, *, field_name: str
) -> None:
    """校验可选字符串存在时为 Host 标准 sha256 digest。

    :param value: 待校验 digest 或 ``None``。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises ValueError: digest 格式无效时抛出。
    """

    if value is not None:
        _require_sha256_digest(value, field_name=field_name)


def _require_utc_datetime(value: datetime, *, field_name: str) -> None:
    """校验时间为 timezone-aware UTC ``datetime``。

    :param value: 待校验时间。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises TypeError: ``value`` 不是 ``datetime`` 时抛出。
    :raises ValueError: ``value`` 是 naive 或非 UTC 时间时抛出。
    """

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"{field_name} must be timezone.utc aware")


def _require_metadata_entries(
    entries: tuple["HostMetadataEntry", ...], *, field_name: str
) -> None:
    """校验 metadata 元组中的 key 非空。

    :param entries: Host metadata 条目元组。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises ValueError: 任一 metadata key 为空时抛出。
    """

    for entry in entries:
        _require_non_empty(entry.key, field_name=f"{field_name}.key")


def _require_graceful_cancel(mode: "CancelMode", *, field_name: str) -> None:
    """校验取消模式仍处于第一版允许集合。

    :param mode: 请求传入的取消模式。
    :param field_name: 错误消息中使用的字段名。
    :returns: 无返回值。
    :raises ValueError: 取消模式不是 :attr:`CancelMode.GRACEFUL` 时抛出。
    """

    if mode != CancelMode.GRACEFUL:
        raise ValueError(f"{field_name} must be graceful")


class SessionStatus(StrEnum):
    """Session 生命周期状态。

    成员：

    - ``OPEN``：Session 可继续接收新 Run 或 follow-up。
    - ``CLOSED``：Session 已关闭，不再接收新 Run。
    """

    OPEN = "open"
    CLOSED = "closed"


class RunStatus(StrEnum):
    """Run 生命周期状态。

    成员覆盖 Host 对用户可见目标的排队、执行、等待、取消、恢复与终态。
    ``RECOVERING`` 由 Phase 11 recovery owner 接入；当前 P9 生产转换代码
    尚不写入。``SUCCEEDED``、``FAILED``、``CANCELLED``、``LOST`` 是终态。
    """

    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    CANCELLING = "cancelling"
    RECOVERING = "recovering"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


class AttemptStatus(StrEnum):
    """Attempt 生命周期状态。

    成员描述 Host 派发给本地或远端 EngineWorker 的一次执行尝试状态。
    Attempt 终态不自动等同于 Run 终态。
    """

    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    STEERED = "steered"
    LOST = "lost"


class FollowupBehavior(StrEnum):
    """follow-up admission 行为。

    - ``QUEUE``：作为同一 Session 后续输入排队或启动新 Run。
    - ``STEER``：作用于指定 active Run，并通过新 Attempt 继续。
    """

    QUEUE = "queue"
    STEER = "steer"


class CancelMode(StrEnum):
    """取消模式枚举。

    Phase 1 只定义优雅取消；不承诺 force 或 immediate 语义。
    """

    GRACEFUL = "graceful"


class WaitResolutionSource(StrEnum):
    """等待结果来源枚举。

    成员表示 ``resolve_wait`` 接收结果的外部来源，不表示长阻塞等待机制。
    """

    POLL = "poll"
    CALLBACK = "callback"
    MANUAL = "manual"


class HostEventClass(StrEnum):
    """Host public event stream 事件分类。

    成员与 durable EventLog row 的事件分类一一对应，但作为 public API
    类型暴露，避免调用方依赖 durable 内部模块。
    """

    CANONICAL_FACT = "canonical_fact"
    PREVIEW = "preview"
    DIAGNOSTIC = "diagnostic"
    PROJECTION_SIGNAL = "projection_signal"


@dataclass(frozen=True, slots=True)
class WaitAdapterKey:
    """Host 等待适配器稳定注册键。

    :param value: 适配器注册键，只允许 ASCII 字母、数字、下划线、点、冒号与连字符。
    """

    value: str

    def __post_init__(self) -> None:
        """校验适配器键格式与长度。

        :returns: 无返回值。
        :raises ValueError: ``value`` 为空、超长或含非法字符时抛出。
        """

        _require_max_length(
            self.value,
            field_name="WaitAdapterKey.value",
            max_length=HOST_WAIT_ADAPTER_KEY_MAX_LENGTH,
        )
        if _WAIT_ADAPTER_KEY_PATTERN.fullmatch(self.value) is None:
            raise ValueError("WaitAdapterKey.value contains invalid characters")


@dataclass(frozen=True, slots=True)
class HostPayloadRef:
    """Host payload descriptor 引用。

    :param payload_ref: payload descriptor 标识。
    :param payload_digest: payload 内容 digest。
    """

    payload_ref: str
    payload_digest: str

    def __post_init__(self) -> None:
        """校验 payload 引用字段。

        :returns: 无返回值。
        :raises ValueError: 引用为空或 digest 非法时抛出。
        """

        _require_non_empty(self.payload_ref, field_name="HostPayloadRef.payload_ref")
        _require_sha256_digest(
            self.payload_digest, field_name="HostPayloadRef.payload_digest"
        )


@dataclass(frozen=True, slots=True)
class WaitProviderStatusRef:
    """等待适配器可重读 provider 状态引用。

    :param adapter_key: 产生该状态引用的 Host 等待适配器键。
    :param status_ref: provider 状态引用，不承载 provider payload。
    :param status_digest: provider 状态摘要；无摘要时为 ``None``。
    """

    adapter_key: WaitAdapterKey
    status_ref: str
    status_digest: str | None

    def __post_init__(self) -> None:
        """校验 provider 状态引用。

        :returns: 无返回值。
        :raises TypeError: ``adapter_key`` 类型非法时抛出。
        :raises ValueError: ``status_ref`` 为空、超长或 digest 非法时抛出。
        """

        if not isinstance(self.adapter_key, WaitAdapterKey):
            raise TypeError("WaitProviderStatusRef.adapter_key must be WaitAdapterKey")
        _require_max_length(
            self.status_ref,
            field_name="WaitProviderStatusRef.status_ref",
            max_length=HOST_WAIT_PROVIDER_STATUS_REF_MAX_LENGTH,
        )
        _require_optional_sha256_digest(
            self.status_digest, field_name="WaitProviderStatusRef.status_digest"
        )


@dataclass(frozen=True, slots=True)
class ResolveWaitCompletedOutcome:
    """等待完成后返回工具成功结果的 envelope。

    :param result: 工具成功结果。
    :param payload_ref: 可选 Host payload descriptor 引用。
    """

    result: ToolResultSuccess
    payload_ref: HostPayloadRef | None

    def __post_init__(self) -> None:
        """校验成功结果 envelope。

        :returns: 无返回值。
        :raises TypeError: ``result`` 或 ``payload_ref`` 类型非法时抛出。
        """

        if not isinstance(self.result, ToolResultSuccess):
            raise TypeError("ResolveWaitCompletedOutcome.result must be ToolResultSuccess")
        if self.payload_ref is not None and not isinstance(
            self.payload_ref, HostPayloadRef
        ):
            raise TypeError(
                "ResolveWaitCompletedOutcome.payload_ref must be HostPayloadRef"
            )


@dataclass(frozen=True, slots=True)
class ResolveWaitFailedOutcome:
    """等待完成后返回工具失败结果的 envelope。

    :param result: 工具失败结果。
    :param payload_ref: 可选 Host payload descriptor 引用。
    """

    result: ToolResultFailure
    payload_ref: HostPayloadRef | None

    def __post_init__(self) -> None:
        """校验失败结果 envelope。

        :returns: 无返回值。
        :raises TypeError: ``result`` 或 ``payload_ref`` 类型非法时抛出。
        """

        if not isinstance(self.result, ToolResultFailure):
            raise TypeError("ResolveWaitFailedOutcome.result must be ToolResultFailure")
        if self.payload_ref is not None and not isinstance(
            self.payload_ref, HostPayloadRef
        ):
            raise TypeError("ResolveWaitFailedOutcome.payload_ref must be HostPayloadRef")


@dataclass(frozen=True, slots=True)
class ResolveWaitCancelledOutcome:
    """等待完成后返回工具级取消结果的 envelope。

    :param result: 工具级取消结果。
    :param payload_ref: 可选 Host payload descriptor 引用。
    """

    result: ToolCancelledOutcome
    payload_ref: HostPayloadRef | None

    def __post_init__(self) -> None:
        """校验工具级取消 envelope。

        :returns: 无返回值。
        :raises TypeError: ``result`` 或 ``payload_ref`` 类型非法时抛出。
        """

        if not isinstance(self.result, ToolCancelledOutcome):
            raise TypeError(
                "ResolveWaitCancelledOutcome.result must be ToolCancelledOutcome"
            )
        if self.payload_ref is not None and not isinstance(
            self.payload_ref, HostPayloadRef
        ):
            raise TypeError(
                "ResolveWaitCancelledOutcome.payload_ref must be HostPayloadRef"
            )


@dataclass(frozen=True, slots=True)
class ResolveWaitLostOutcome:
    """等待适配器报告无法确认外部 job 状态的 envelope。

    :param reason_code: 机器可读 lost 原因码。
    :param message: 人类可读说明。
    :param provider_status_ref: 可选 provider 状态引用。
    """

    reason_code: str
    message: str
    provider_status_ref: WaitProviderStatusRef | None

    def __post_init__(self) -> None:
        """校验 lost outcome 字段。

        :returns: 无返回值。
        :raises TypeError: ``provider_status_ref`` 类型非法时抛出。
        :raises ValueError: 原因或说明为空时抛出。
        """

        _require_non_empty(
            self.reason_code, field_name="ResolveWaitLostOutcome.reason_code"
        )
        _require_non_empty(self.message, field_name="ResolveWaitLostOutcome.message")
        if self.provider_status_ref is not None and not isinstance(
            self.provider_status_ref, WaitProviderStatusRef
        ):
            raise TypeError(
                "ResolveWaitLostOutcome.provider_status_ref must be "
                "WaitProviderStatusRef"
            )


ResolveWaitOutcome: TypeAlias = (
    ResolveWaitCompletedOutcome
    | ResolveWaitFailedOutcome
    | ResolveWaitCancelledOutcome
    | ResolveWaitLostOutcome
)
"""``resolve_wait`` 接收的等待结果封闭联合。"""


class SourceRunRelation(StrEnum):
    """当前 Run 与源 Run 的关系。

    - ``RETRY``：重试源 Run 的失败或可恢复失败。
    - ``REPLAY``：复用源 Run 事实做 no-tool 结构修复。
    """

    RETRY = "retry"
    REPLAY = "replay"


@dataclass(frozen=True, slots=True)
class AttemptDispatchSnapshot:
    """一次 Attempt dispatch 的强类型输入快照。

    本快照只承载 durable identity refs、dispatch refs、policy snapshot ref
    与取消观察 token。Runner 规约、Runner 调用参数、AgentPolicy、工具
    schema 与 ToolExecutor 必须由 RunInputBuilder 的 typed providers 在
    build 时注入，不能重复塞入本快照。

    :param session_id: Attempt 所属 Session id。
    :param run_id: Attempt 所属 Run id。
    :param attempt_id: Attempt id。
    :param execution_id: Attempt execution id。
    :param dispatch_record_id: Attempt dispatch record id。
    :param execution_target: 已解析执行目标。
    :param policy_snapshot_ref: Host policy snapshot ref。
    :param cancellation_token: Host 注入的取消观察 token。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    execution_target: str
    policy_snapshot_ref: str
    cancellation_token: CancellationToken

    def __post_init__(self) -> None:
        """校验快照必填字段。

        :returns: ``None``。
        :raises TypeError: 取消 token 不是 ``CancellationToken`` 时抛出。
        :raises ValueError: 任一必填文本为空时抛出。
        """

        _require_non_empty(self.session_id, field_name="session_id")
        _require_non_empty(self.run_id, field_name="run_id")
        _require_non_empty(self.attempt_id, field_name="attempt_id")
        _require_non_empty(self.execution_id, field_name="execution_id")
        _require_non_empty(
            self.dispatch_record_id, field_name="dispatch_record_id"
        )
        _require_non_empty(self.execution_target, field_name="execution_target")
        _require_non_empty(
            self.policy_snapshot_ref, field_name="policy_snapshot_ref"
        )
        if not isinstance(self.cancellation_token, CancellationToken):
            raise TypeError("cancellation_token must implement CancellationToken")


class LocalWorkerHandle(Protocol):
    """本地 Engine worker accept 后的运行期 handle 协议。"""

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker 诊断 id。

        :returns: 本地 worker id。
        :raises RuntimeError: 具体实现不可用时可抛出运行时错误。
        """

        ...

    def events(self) -> AsyncIterator[EngineEvent]:
        """返回本次 Engine run 的事件流。

        :returns: EngineEvent 异步迭代器。
        :raises RuntimeError: 具体 worker 事件流不可用时可抛出运行时错误。
        """

        ...

    async def close(self) -> None:
        """关闭 worker handle。

        :returns: ``None``。
        :raises RuntimeError: 具体实现关闭失败时可抛出运行时错误。
        """

        ...

    def on_cancel(self, reason: str) -> None:
        """在 Host 已发出取消信号后通知 worker handle。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises RuntimeError: 具体实现处理取消通知失败时可抛出运行时错误。
        """

        ...


class LocalEngineWorker(Protocol):
    """本地 Engine worker accept 协议。"""

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受一次本地 Engine run。

        :param snapshot: durable dispatch 快照。
        :param request: RunInputBuilder 构造的 Engine 请求。
        :returns: worker handle。
        :raises RuntimeError: worker 无法接受本次运行时可抛出运行时错误。
        """

        ...


class LocalEngineWorkerFactory(Protocol):
    """本地 Engine worker factory 协议。"""

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建处理指定 dispatch snapshot 的 worker。

        :param snapshot: durable dispatch 快照。
        :returns: 本地 Engine worker。
        :raises RuntimeError: worker 无法创建时可抛出运行时错误。
        """

        ...


@dataclass(frozen=True, slots=True)
class HostLocalExecutionOptions:
    """Host 本地执行调度配置。

    :param lane_db_path: runtime lane SQLite 数据库路径。
    :param lane_name: 本地执行 lane 名称。
    :param lane_capacity: 本地执行 lane 容量。
    :param lane_default_timeout_seconds: lane acquire 默认 timeout；``None`` 表示无限等待。
    :param lane_claim_ttl_seconds: lane claim TTL 秒数。
    :param lane_heartbeat_interval_seconds: lane heartbeat 秒数。
    :param worker_startup_timeout_seconds: worker accept timeout 秒数。
    :param dispatch_poll_interval_seconds: dispatch 后台循环空闲轮询秒数。
    :param runner_spec: Engine Runner 规约。
    :param runner_options: Engine Runner 调用参数。
    :param agent_policy: Engine Agent policy。
    :param worker_factory: 本地 worker factory。
    :param context_budget_policy: Host Context Governance 的 typed 预算策略；
        ``None`` 表示 pre-start governance 直接放行，不触发 proactive compact。
    :param context_compactor: Host Context Governance 使用的 compactor typed port；
        仅在预算触发 compact 时需要，生产不得隐式使用 fake compactor。
    :param compactor_runner_spec: compactor 独立 Runner 规约；无 LLM
        compactor 时为 ``None``。
    :param compactor_runner_options: compactor 独立 Runner 调用参数；无 LLM
        compactor 时为 ``None``。
    :param compactor_policy_ref: compactor policy 的稳定引用；无独立 policy
        时为 ``None``。
    :param compact_artifact_root: compact artifact 写入根目录；未配置且触发
        compact 时 fail closed。
    :param compact_artifact_create_parent_dirs: compact artifact 根目录缺失时是否创建。
    :param memory_projection_policy: 本地 dispatch 注入 RunInputBuilder 的
        durable conversation memory policy。
    :param memory_projection_catchup_batch_size: worker 启动前追平 memory
        projection 时单批最大扫描 EventLog row 数。
    :param tooling_options: Host construction 阶段传入的业务工具选项；无则
        本地 dispatch 仍按 no-tool 模式构造 Engine request。
    :param enable_truncation_manager: tool-enabled 本地 dispatch 是否为当前
        Attempt 创建 run-scoped truncation manager。
    """

    lane_db_path: pathlib.Path
    lane_name: str
    lane_capacity: int
    lane_default_timeout_seconds: float | None
    lane_claim_ttl_seconds: float
    lane_heartbeat_interval_seconds: float
    worker_startup_timeout_seconds: float
    dispatch_poll_interval_seconds: float
    runner_spec: RunnerSpec
    runner_options: RunnerCallOptions
    agent_policy: AgentPolicy
    worker_factory: LocalEngineWorkerFactory
    context_budget_policy: ContextBudgetPolicy | None = None
    context_compactor: ContextCompactor | None = None
    compactor_runner_spec: RunnerSpec | None = None
    compactor_runner_options: RunnerCallOptions | None = None
    compactor_policy_ref: str | None = None
    compact_artifact_root: pathlib.Path | None = None
    compact_artifact_create_parent_dirs: bool = True
    memory_projection_policy: MemoryProjectionPolicy = field(
        default_factory=default_memory_projection_policy
    )
    memory_projection_catchup_batch_size: int = 128
    tooling_options: _HostToolingOptions | None = None
    enable_truncation_manager: bool = True

    def __post_init__(self) -> None:
        """校验本地执行配置。

        :returns: ``None``。
        :raises TypeError: 路径或整数配置类型非法时抛出。
        :raises ValueError: 文本为空、容量非法或 timeout 非法时抛出。
        """

        _require_path(
            self.lane_db_path,
            field_name="HostLocalExecutionOptions.lane_db_path",
        )
        _require_non_empty(
            self.lane_name, field_name="HostLocalExecutionOptions.lane_name"
        )
        _require_positive_int(
            self.lane_capacity,
            field_name="HostLocalExecutionOptions.lane_capacity",
        )
        if self.lane_default_timeout_seconds is not None:
            if (
                isinstance(self.lane_default_timeout_seconds, bool)
                or not isinstance(self.lane_default_timeout_seconds, int | float)
            ):
                raise TypeError(
                    "HostLocalExecutionOptions.lane_default_timeout_seconds "
                    "must be float"
                )
            if self.lane_default_timeout_seconds < 0:
                raise ValueError(
                    "HostLocalExecutionOptions.lane_default_timeout_seconds "
                    "must be non-negative"
                )
        _require_positive_float(
            self.lane_claim_ttl_seconds,
            field_name="HostLocalExecutionOptions.lane_claim_ttl_seconds",
        )
        _require_positive_float(
            self.lane_heartbeat_interval_seconds,
            field_name=(
                "HostLocalExecutionOptions.lane_heartbeat_interval_seconds"
            ),
        )
        _require_positive_float(
            self.worker_startup_timeout_seconds,
            field_name=(
                "HostLocalExecutionOptions.worker_startup_timeout_seconds"
            ),
        )
        _require_positive_float(
            self.dispatch_poll_interval_seconds,
            field_name=(
                "HostLocalExecutionOptions.dispatch_poll_interval_seconds"
            ),
        )
        if not isinstance(self.runner_spec, RunnerSpec):
            raise TypeError("HostLocalExecutionOptions.runner_spec must be RunnerSpec")
        if not isinstance(self.runner_options, RunnerCallOptions):
            raise TypeError(
                "HostLocalExecutionOptions.runner_options must be RunnerCallOptions"
            )
        if not isinstance(self.agent_policy, AgentPolicy):
            raise TypeError("HostLocalExecutionOptions.agent_policy must be AgentPolicy")
        if self.worker_factory is None:
            raise TypeError(
                "HostLocalExecutionOptions.worker_factory must be non-None"
            )
        if self.context_budget_policy is not None and not isinstance(
            self.context_budget_policy, ContextBudgetPolicy
        ):
            raise TypeError(
                "HostLocalExecutionOptions.context_budget_policy must be "
                "ContextBudgetPolicy"
            )
        if self.compactor_runner_spec is not None and not isinstance(
            self.compactor_runner_spec, RunnerSpec
        ):
            raise TypeError(
                "HostLocalExecutionOptions.compactor_runner_spec must be "
                "RunnerSpec"
            )
        if self.compactor_runner_options is not None and not isinstance(
            self.compactor_runner_options, RunnerCallOptions
        ):
            raise TypeError(
                "HostLocalExecutionOptions.compactor_runner_options must be "
                "RunnerCallOptions"
            )
        _require_optional_non_empty(
            self.compactor_policy_ref,
            field_name="HostLocalExecutionOptions.compactor_policy_ref",
        )
        if self.compact_artifact_root is not None:
            _require_path(
                self.compact_artifact_root,
                field_name="HostLocalExecutionOptions.compact_artifact_root",
            )
        _require_bool(
            self.compact_artifact_create_parent_dirs,
            field_name=(
                "HostLocalExecutionOptions.compact_artifact_create_parent_dirs"
            ),
        )
        if not isinstance(self.memory_projection_policy, MemoryProjectionPolicy):
            raise TypeError(
                "HostLocalExecutionOptions.memory_projection_policy must be "
                "MemoryProjectionPolicy"
            )
        _require_positive_int(
            self.memory_projection_catchup_batch_size,
            field_name=(
                "HostLocalExecutionOptions.memory_projection_catchup_batch_size"
            ),
        )
        if self.tooling_options is not None and not isinstance(
            self.tooling_options, _HostToolingOptions
        ):
            raise TypeError(
                "HostLocalExecutionOptions.tooling_options must be HostToolingOptions"
            )
        if not isinstance(self.enable_truncation_manager, bool):
            raise TypeError(
                "HostLocalExecutionOptions.enable_truncation_manager must be bool"
            )


@dataclass(frozen=True, slots=True)
class OrdinaryRunExecutionBaseline:
    """普通 Run 的构造期执行基线。

    :param runner_spec: 普通 Run 默认使用的 Engine Runner 规约。
    :param runner_options: 普通 Run 默认使用的 Runner 调用参数。
    :param agent_policy: 普通 Run 默认使用的 Agent 策略。
    """

    runner_spec: RunnerSpec
    runner_options: RunnerCallOptions
    agent_policy: AgentPolicy

    def __post_init__(self) -> None:
        """校验普通 Run 执行基线。

        :returns: ``None``。
        :raises TypeError: 任一字段不是对应 typed contract 时抛出。
        """

        if not isinstance(self.runner_spec, RunnerSpec):
            raise TypeError(
                "OrdinaryRunExecutionBaseline.runner_spec must be RunnerSpec"
            )
        if not isinstance(self.runner_options, RunnerCallOptions):
            raise TypeError(
                "OrdinaryRunExecutionBaseline.runner_options must be "
                "RunnerCallOptions"
            )
        if not isinstance(self.agent_policy, AgentPolicy):
            raise TypeError(
                "OrdinaryRunExecutionBaseline.agent_policy must be AgentPolicy"
            )


@dataclass(frozen=True, slots=True)
class CompactorRunnerBaseline:
    """Host-owned LLM compactor 的构造期运行配置。

    :param compactor_runner_spec: compactor 独立 Runner 规约。
    :param compactor_runner_options: compactor 独立 Runner 调用参数。
    :param compactor_agent_policy: compactor 独立 Agent policy。
    :param compactor_system_prompt: Service 从 compactor scene 装配的
        system prompt。
    :param compactor_user_prompt_template: Service 从 compactor baseline 指定
        prompt asset 装配的 user prompt template。
    :param compact_artifact_root: compact artifact 写入根目录。
    :param compact_artifact_create_parent_dirs: artifact 根目录缺失时是否创建。
    """

    compactor_runner_spec: RunnerSpec
    compactor_runner_options: RunnerCallOptions
    compactor_agent_policy: AgentPolicy
    compactor_system_prompt: str
    compactor_user_prompt_template: str
    compact_artifact_root: pathlib.Path
    compact_artifact_create_parent_dirs: bool = True

    def __post_init__(self) -> None:
        """校验 compactor runner 基线。

        :returns: ``None``。
        :raises TypeError: 路径、布尔或 Runner typed 字段类型非法时抛出。
        """

        if not isinstance(self.compactor_runner_spec, RunnerSpec):
            raise TypeError(
                "CompactorRunnerBaseline.compactor_runner_spec must be "
                "RunnerSpec"
            )
        if not isinstance(self.compactor_runner_options, RunnerCallOptions):
            raise TypeError(
                "CompactorRunnerBaseline.compactor_runner_options must be "
                "RunnerCallOptions"
            )
        if not isinstance(self.compactor_agent_policy, AgentPolicy):
            raise TypeError(
                "CompactorRunnerBaseline.compactor_agent_policy must be "
                "AgentPolicy"
            )
        _require_non_empty(
            self.compactor_system_prompt,
            field_name="CompactorRunnerBaseline.compactor_system_prompt",
        )
        _require_non_empty(
            self.compactor_user_prompt_template,
            field_name="CompactorRunnerBaseline.compactor_user_prompt_template",
        )
        _require_path(
            self.compact_artifact_root,
            field_name="CompactorRunnerBaseline.compact_artifact_root",
        )
        _require_bool(
            self.compact_artifact_create_parent_dirs,
            field_name=(
                "CompactorRunnerBaseline."
                "compact_artifact_create_parent_dirs"
            ),
        )


@dataclass(frozen=True, slots=True)
class OpenHostOptions:
    """``open_host`` 的普通本地多轮构造期选项。

    :param db_path: Host durable SQLite 数据库路径。
    :param artifact_root: Host artifact 根目录。
    :param create_parent_dirs: 打开 store / artifact 前是否创建父目录。
    :param sqlite_busy_timeout_seconds: durable SQLite busy timeout 秒数。
    :param sqlite_write_busy_retry_count: 写事务 busy 重试次数。
    :param sqlite_write_retry_initial_delay_seconds: 首次写重试等待秒数。
    :param sqlite_write_retry_backoff_multiplier: 写重试退避倍率。
    :param sqlite_write_retry_max_delay_seconds: 写重试最大等待秒数。
    :param payload_inline_threshold_bytes: payload 内联存储阈值字节数。
    :param lane_db_path: runtime lane SQLite 数据库路径。
    :param lane_name: 本地执行 lane 名称。
    :param lane_capacity: 本地执行 lane 容量。
    :param lane_default_timeout_seconds: lane acquire 默认 timeout；``None``
        表示无限等待。
    :param lane_claim_ttl_seconds: lane claim TTL 秒数。
    :param lane_heartbeat_interval_seconds: lane heartbeat 秒数。
    :param worker_startup_timeout_seconds: worker accept timeout 秒数。
    :param dispatch_poll_interval_seconds: dispatch 后台循环空闲轮询秒数。
    :param ordinary_run_baseline: 普通 Run 执行基线。
    :param worker_factory: 本地 worker factory typed port。
    :param tooling_options: construction-time 工具治理选项；无工具时为
        ``None``。
    :param context_budget_policy: Host Context Governance 预算策略；不启用
        proactive compact 时为 ``None``。
    :param compactor_runner_baseline: Host-owned LLM compactor 运行配置；未装配
        compact 能力时为 ``None``。
    :param memory_projection_policy: dispatch 前 memory projection catch-up
        使用的 policy。
    :param memory_projection_catchup_batch_size: memory catch-up 单批最大 row 数。
    :param enable_truncation_manager: tool-enabled dispatch 是否启用截断治理。
    """

    db_path: pathlib.Path
    artifact_root: pathlib.Path
    create_parent_dirs: bool
    sqlite_busy_timeout_seconds: float
    sqlite_write_busy_retry_count: int
    sqlite_write_retry_initial_delay_seconds: float
    sqlite_write_retry_backoff_multiplier: float
    sqlite_write_retry_max_delay_seconds: float
    payload_inline_threshold_bytes: int
    lane_db_path: pathlib.Path
    lane_name: str
    lane_capacity: int
    lane_default_timeout_seconds: float | None
    lane_claim_ttl_seconds: float
    lane_heartbeat_interval_seconds: float
    worker_startup_timeout_seconds: float
    dispatch_poll_interval_seconds: float
    ordinary_run_baseline: OrdinaryRunExecutionBaseline
    worker_factory: LocalEngineWorkerFactory
    tooling_options: _HostToolingOptions | None
    context_budget_policy: ContextBudgetPolicy | None
    compactor_runner_baseline: CompactorRunnerBaseline | None
    memory_projection_policy: MemoryProjectionPolicy
    memory_projection_catchup_batch_size: int
    enable_truncation_manager: bool

    def __post_init__(self) -> None:
        """校验 ``open_host`` 构造期选项。

        :returns: ``None``。
        :raises TypeError: 路径、布尔、整数或 typed contract 字段类型非法时抛出。
        :raises ValueError: 文本为空、容量非法、timeout 非法或 lane TTL
            不大于 heartbeat 时抛出。
        """

        _require_path(self.db_path, field_name="OpenHostOptions.db_path")
        _require_path(
            self.artifact_root, field_name="OpenHostOptions.artifact_root"
        )
        _require_bool(
            self.create_parent_dirs,
            field_name="OpenHostOptions.create_parent_dirs",
        )
        _require_positive_float(
            self.sqlite_busy_timeout_seconds,
            field_name="OpenHostOptions.sqlite_busy_timeout_seconds",
        )
        _require_non_negative_int(
            self.sqlite_write_busy_retry_count,
            field_name="OpenHostOptions.sqlite_write_busy_retry_count",
        )
        _require_positive_float(
            self.sqlite_write_retry_initial_delay_seconds,
            field_name=(
                "OpenHostOptions.sqlite_write_retry_initial_delay_seconds"
            ),
        )
        _require_positive_float(
            self.sqlite_write_retry_backoff_multiplier,
            field_name="OpenHostOptions.sqlite_write_retry_backoff_multiplier",
        )
        _require_positive_float(
            self.sqlite_write_retry_max_delay_seconds,
            field_name="OpenHostOptions.sqlite_write_retry_max_delay_seconds",
        )
        _require_positive_int(
            self.payload_inline_threshold_bytes,
            field_name="OpenHostOptions.payload_inline_threshold_bytes",
        )
        _require_path(
            self.lane_db_path, field_name="OpenHostOptions.lane_db_path"
        )
        _require_non_empty(self.lane_name, field_name="OpenHostOptions.lane_name")
        _require_positive_int(
            self.lane_capacity, field_name="OpenHostOptions.lane_capacity"
        )
        if self.lane_default_timeout_seconds is not None:
            if (
                isinstance(self.lane_default_timeout_seconds, bool)
                or not isinstance(self.lane_default_timeout_seconds, int | float)
            ):
                raise TypeError(
                    "OpenHostOptions.lane_default_timeout_seconds must be float"
                )
            if self.lane_default_timeout_seconds < 0:
                raise ValueError(
                    "OpenHostOptions.lane_default_timeout_seconds must be "
                    "non-negative"
                )
        _require_positive_float(
            self.lane_claim_ttl_seconds,
            field_name="OpenHostOptions.lane_claim_ttl_seconds",
        )
        _require_positive_float(
            self.lane_heartbeat_interval_seconds,
            field_name="OpenHostOptions.lane_heartbeat_interval_seconds",
        )
        if self.lane_claim_ttl_seconds <= self.lane_heartbeat_interval_seconds:
            raise ValueError(
                "OpenHostOptions.lane_claim_ttl_seconds must be greater than "
                "lane_heartbeat_interval_seconds"
            )
        _require_positive_float(
            self.worker_startup_timeout_seconds,
            field_name="OpenHostOptions.worker_startup_timeout_seconds",
        )
        _require_positive_float(
            self.dispatch_poll_interval_seconds,
            field_name="OpenHostOptions.dispatch_poll_interval_seconds",
        )
        if not isinstance(
            self.ordinary_run_baseline, OrdinaryRunExecutionBaseline
        ):
            raise TypeError(
                "OpenHostOptions.ordinary_run_baseline must be "
                "OrdinaryRunExecutionBaseline"
            )
        if self.worker_factory is None:
            raise TypeError("OpenHostOptions.worker_factory must be non-None")
        if self.tooling_options is not None and not isinstance(
            self.tooling_options, _HostToolingOptions
        ):
            raise TypeError(
                "OpenHostOptions.tooling_options must be HostToolingOptions"
            )
        if self.context_budget_policy is not None and not isinstance(
            self.context_budget_policy, ContextBudgetPolicy
        ):
            raise TypeError(
                "OpenHostOptions.context_budget_policy must be "
                "ContextBudgetPolicy"
            )
        if self.compactor_runner_baseline is not None and not isinstance(
            self.compactor_runner_baseline, CompactorRunnerBaseline
        ):
            raise TypeError(
                "OpenHostOptions.compactor_runner_baseline must be "
                "CompactorRunnerBaseline"
            )
        if not isinstance(self.memory_projection_policy, MemoryProjectionPolicy):
            raise TypeError(
                "OpenHostOptions.memory_projection_policy must be "
                "MemoryProjectionPolicy"
            )
        _require_positive_int(
            self.memory_projection_catchup_batch_size,
            field_name="OpenHostOptions.memory_projection_catchup_batch_size",
        )
        _require_bool(
            self.enable_truncation_manager,
            field_name="OpenHostOptions.enable_truncation_manager",
        )


class HostApiErrorCode(StrEnum):
    """Host API 结构化错误码。

    当前只冻结公共错误码集合，不实现 command path 抛错路径。
    """

    NOT_FOUND = "not_found"
    INVALID_STATE = "invalid_state"
    CONFLICT = "conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    PERMISSION_DENIED = "permission_denied"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class SteerConflictDetail:
    """steer 前置条件冲突的结构化错误详情。

    字段语义：

    - ``target_run_id``：调用方请求 steer 的目标 Run id。
    - ``target_run_status``：目标 Run 当前状态；目标不存在或无法读取时为 ``None``。
    - ``current_active_run_id``：Session 当前 active Run id；无 active Run 时为 ``None``。
    - ``current_active_run_status``：当前 active Run 状态；无 active Run 时为 ``None``。
    """

    target_run_id: str
    target_run_status: RunStatus | None
    current_active_run_id: str | None
    current_active_run_status: RunStatus | None

    def __post_init__(self) -> None:
        """校验 steer 冲突详情中的 Run id 字段。

        :returns: 无返回值。
        :raises ValueError: ``target_run_id`` 为空，或可选 active Run id 存在但为空时抛出。
        """

        _require_non_empty(
            self.target_run_id, field_name="SteerConflictDetail.target_run_id"
        )
        _require_optional_non_empty(
            self.current_active_run_id,
            field_name="SteerConflictDetail.current_active_run_id",
        )


HostApiErrorDetail: TypeAlias = SteerConflictDetail


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Host 调用的业务 / 操作上下文。

    字段语义：

    - ``operation_name``：操作名称，用于审计、trace 与诊断。
    - ``operation_kind``：操作类别，例如交互、批处理或后台任务。
    - ``business_domain``：业务域名称。
    - ``business_object_type``：业务对象类型；无绑定对象时为 ``None``。
    - ``business_object_id``：业务对象 id；无绑定对象时为 ``None``。
    - ``scenario``：场景名称；无场景时为 ``None``。
    - ``correlation_id``：跨系统关联 id；无关联时为 ``None``。
    """

    operation_name: str
    operation_kind: str
    business_domain: str
    business_object_type: str | None
    business_object_id: str | None
    scenario: str | None
    correlation_id: str | None

    def __post_init__(self) -> None:
        """校验操作上下文字段的基础完整性。

        :returns: 无返回值。
        :raises ValueError: 必填字符串为空，或可选 id 字段存在但为空时抛出。
        """

        _require_non_empty(
            self.operation_name, field_name="OperationContext.operation_name"
        )
        _require_non_empty(
            self.operation_kind, field_name="OperationContext.operation_kind"
        )
        _require_non_empty(
            self.business_domain, field_name="OperationContext.business_domain"
        )
        _require_optional_non_empty(
            self.business_object_type,
            field_name="OperationContext.business_object_type",
        )
        _require_optional_non_empty(
            self.business_object_id,
            field_name="OperationContext.business_object_id",
        )
        _require_optional_non_empty(
            self.scenario, field_name="OperationContext.scenario"
        )
        _require_optional_non_empty(
            self.correlation_id, field_name="OperationContext.correlation_id"
        )


@dataclass(frozen=True, slots=True)
class AuthorizationClaim:
    """调用方授权声明。

    字段语义：

    - ``name``：声明名称。
    - ``value``：声明值。
    """

    name: str
    value: str

    def __post_init__(self) -> None:
        """校验授权声明非空。

        :returns: 无返回值。
        :raises ValueError: ``name`` 或 ``value`` 为空时抛出。
        """

        _require_non_empty(self.name, field_name="AuthorizationClaim.name")
        _require_non_empty(self.value, field_name="AuthorizationClaim.value")


@dataclass(frozen=True, slots=True)
class HostCallContext:
    """Host API 调用上下文。

    字段语义：

    - ``actor``：发起调用的主体。
    - ``source``：调用来源，例如 CLI、Service 或 UI adapter。
    - ``request_id``：本次调用的追踪 id，不是统一幂等键。
    - ``authorization_claims``：调用方授权声明集合。
    - ``operation_context``：业务 / 操作上下文。
    """

    actor: str
    source: str
    request_id: str
    authorization_claims: tuple[AuthorizationClaim, ...]
    operation_context: OperationContext

    def __post_init__(self) -> None:
        """校验调用上下文基础字段非空。

        :returns: 无返回值。
        :raises ValueError: ``actor``、``source`` 或 ``request_id`` 为空时抛出。
        """

        _require_non_empty(self.actor, field_name="HostCallContext.actor")
        _require_non_empty(self.source, field_name="HostCallContext.source")
        _require_non_empty(
            self.request_id, field_name="HostCallContext.request_id"
        )


@dataclass(frozen=True, slots=True)
class HostMetadataEntry:
    """Host 中性附加说明条目。

    字段语义：

    - ``key``：metadata key，仅用于非状态机、非幂等、非恢复、非审计主链说明。
    - ``value``：严格 JSON 值；显式 request 字段禁止塞入 metadata。
    """

    key: str
    value: JsonValue

    def __post_init__(self) -> None:
        """校验 metadata key 非空。

        :returns: 无返回值。
        :raises ValueError: ``key`` 为空或仅包含空白字符时抛出。
        """

        _require_non_empty(self.key, field_name="HostMetadataEntry.key")


@dataclass(frozen=True, slots=True)
class HostInput:
    """Host 输入 envelope。

    字段语义：

    - ``display_text``：面向会话的输入展示文本。
    - ``payload_ref``：大 payload 的外部引用；Phase 1 不实现 payload store。
    - ``payload_digest``：外部 payload 的摘要；无 payload 时为 ``None``。
    """

    display_text: str
    payload_ref: str | None
    payload_digest: str | None

    def __post_init__(self) -> None:
        """校验输入 envelope 的可选引用字段。

        :returns: 无返回值。
        :raises ValueError: 可选引用或摘要存在但为空时抛出。
        """

        _require_optional_non_empty(
            self.payload_ref, field_name="HostInput.payload_ref"
        )
        _require_optional_non_empty(
            self.payload_digest, field_name="HostInput.payload_digest"
        )


@dataclass(frozen=True, slots=True)
class SessionSlotRef:
    """Session slot 引用。

    字段语义：

    - ``scope``：slot 命名空间。
    - ``slot_key``：slot 在 scope 内的稳定键。
    """

    scope: str
    slot_key: str

    def __post_init__(self) -> None:
        """校验 slot 引用字段非空。

        :returns: 无返回值。
        :raises ValueError: ``scope`` 或 ``slot_key`` 为空时抛出。
        """

        _require_non_empty(self.scope, field_name="SessionSlotRef.scope")
        _require_non_empty(self.slot_key, field_name="SessionSlotRef.slot_key")


@dataclass(frozen=True, slots=True)
class HostStreamCursor:
    """Host event stream 游标。

    字段语义：

    - ``event_sequence``：Host durable store 分配的全局单调事件序列。
    """

    event_sequence: int

    def __post_init__(self) -> None:
        """校验事件序列号非负。

        :returns: 无返回值。
        :raises ValueError: ``event_sequence`` 为负数时抛出。
        """

        _require_non_negative(
            self.event_sequence, field_name="HostStreamCursor.event_sequence"
        )


class HostCommandFacet(Protocol):
    """未来函数式 Host command API 的 opaque command handle 协议。

    该协议只暴露稳定 handle id，不持有 store、policy、tool runtime 或其它
    Host 具体实现细节，避免退化为 god bag。
    """

    @property
    def host_handle_id(self) -> str:
        """返回 Host command handle 的稳定诊断 id。

        :returns: command handle id。
        :raises RuntimeError: 具体实现可在自身不可用时抛出运行时错误。
        """

        ...


@dataclass(frozen=True, slots=True)
class HostCommandHandleOptions:
    """Host command handle 的公共构造选项。

    字段语义：

    - ``host_handle_id``：可选稳定诊断 id；不传时由后续 factory 决定。
    - ``db_path``：Host durable SQLite 数据库路径。
    - ``artifact_root``：Host 本地 artifact 根目录。
    - ``create_parent_dirs``：factory 打开存储前是否创建父目录。
    - ``sqlite_busy_timeout_seconds``：SQLite busy timeout 秒数。
    - ``sqlite_write_busy_retry_count``：写事务 busy 重试次数。
    - ``sqlite_write_retry_initial_delay_seconds``：首次写重试等待秒数。
    - ``sqlite_write_retry_backoff_multiplier``：写重试退避倍率。
    - ``sqlite_write_retry_max_delay_seconds``：写重试最大等待秒数。
    - ``payload_inline_threshold_bytes``：payload 内联存储阈值字节数。
    - ``context_window_size``：Host Context Governance 输入窗口 token 数。
    - ``reserved_output_tokens``：Host Context Governance 输出预留 token 数。
    - ``context_budget_hard_threshold_tokens``：可选 hard threshold；``None`` 时按 policy 默认计算。
    - ``context_budget_minimum_protection_tokens``：可选最小保护 token；``None`` 时按 policy 默认计算。
    - ``local_execution``：本地执行配置；``None`` 保持 no-op dispatch wakeup。
    """

    host_handle_id: str | None
    db_path: pathlib.Path
    artifact_root: pathlib.Path
    create_parent_dirs: bool
    sqlite_busy_timeout_seconds: float
    sqlite_write_busy_retry_count: int
    sqlite_write_retry_initial_delay_seconds: float
    sqlite_write_retry_backoff_multiplier: float
    sqlite_write_retry_max_delay_seconds: float
    payload_inline_threshold_bytes: int
    context_window_size: int
    reserved_output_tokens: int
    context_budget_hard_threshold_tokens: int | None = None
    context_budget_minimum_protection_tokens: int | None = None
    local_execution: HostLocalExecutionOptions | None = None

    def __post_init__(self) -> None:
        """校验 Host command handle 构造选项。

        :returns: 无返回值。
        :raises ValueError: 可选 handle id 为空、数值配置不满足正数或非负约束时抛出。
        :raises TypeError: 路径字段不是 ``pathlib.Path`` 或布尔字段不是 ``bool`` 时抛出。
        """

        _require_optional_non_empty(
            self.host_handle_id,
            field_name="HostCommandHandleOptions.host_handle_id",
        )
        _require_path(
            self.db_path, field_name="HostCommandHandleOptions.db_path"
        )
        _require_path(
            self.artifact_root,
            field_name="HostCommandHandleOptions.artifact_root",
        )
        _require_bool(
            self.create_parent_dirs,
            field_name="HostCommandHandleOptions.create_parent_dirs",
        )
        _require_positive_float(
            self.sqlite_busy_timeout_seconds,
            field_name=(
                "HostCommandHandleOptions.sqlite_busy_timeout_seconds"
            ),
        )
        _require_non_negative_int(
            self.sqlite_write_busy_retry_count,
            field_name=(
                "HostCommandHandleOptions.sqlite_write_busy_retry_count"
            ),
        )
        _require_positive_float(
            self.sqlite_write_retry_initial_delay_seconds,
            field_name=(
                "HostCommandHandleOptions."
                "sqlite_write_retry_initial_delay_seconds"
            ),
        )
        _require_positive_float(
            self.sqlite_write_retry_backoff_multiplier,
            field_name=(
                "HostCommandHandleOptions."
                "sqlite_write_retry_backoff_multiplier"
            ),
        )
        _require_positive_float(
            self.sqlite_write_retry_max_delay_seconds,
            field_name=(
                "HostCommandHandleOptions."
                "sqlite_write_retry_max_delay_seconds"
            ),
        )
        _require_positive_int(
            self.payload_inline_threshold_bytes,
            field_name=(
                "HostCommandHandleOptions.payload_inline_threshold_bytes"
            ),
        )
        _validate_command_context_budget_fields(self)


def _validate_command_context_budget_fields(
    options: HostCommandHandleOptions,
) -> None:
    """校验 command handle 上的 context budget typed 输入。

    :param options: Host command handle options。
    :returns: ``None``。
    :raises TypeError: 整数字段类型非法时抛出。
    :raises ValueError: 预算字段非法时抛出。
    """

    _context_budget_policy_from_command_options(options)


def _context_budget_policy_from_command_options(
    options: HostCommandHandleOptions,
) -> ContextBudgetPolicy:
    """把既有 command options 映射为 ratio-first context budget policy。

    :param options: Host command handle options。
    :returns: ratio-first context budget policy。
    :raises TypeError: 整数字段类型非法时抛出。
    :raises ValueError: 预算字段非法时抛出。
    """

    _require_positive_int(
        options.context_window_size,
        field_name="HostCommandHandleOptions.context_window_size",
    )
    _require_positive_int(
        options.reserved_output_tokens,
        field_name="HostCommandHandleOptions.reserved_output_tokens",
    )
    if options.reserved_output_tokens >= options.context_window_size:
        raise ValueError(
            "HostCommandHandleOptions.reserved_output_tokens must be smaller "
            "than context_window_size"
        )
    input_budget_tokens = options.context_window_size - options.reserved_output_tokens
    soft_threshold_tokens = max(
        1, int(input_budget_tokens * DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO)
    )
    hard_threshold_tokens = _command_hard_threshold_tokens(
        options=options,
        input_budget_tokens=input_budget_tokens,
    )
    return context_budget_policy_from_threshold_tokens(
        context_window_size=options.context_window_size,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
    )


def _command_hard_threshold_tokens(
    *,
    options: HostCommandHandleOptions,
    input_budget_tokens: int,
) -> int:
    """返回 command options 派生的 hard threshold token 数。

    :param options: Host command handle options。
    :param input_budget_tokens: 输出预留后的输入预算 token 数。
    :returns: hard threshold token 数。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字段值非法时抛出。
    """

    if options.context_budget_hard_threshold_tokens is not None:
        _require_positive_int(
            options.context_budget_hard_threshold_tokens,
            field_name=(
                "HostCommandHandleOptions."
                "context_budget_hard_threshold_tokens"
            ),
        )
        if options.context_budget_hard_threshold_tokens > input_budget_tokens:
            raise ValueError(
                "HostCommandHandleOptions.context_budget_hard_threshold_tokens "
                "must not exceed input budget"
            )
        return options.context_budget_hard_threshold_tokens
    minimum_protection_tokens = (
        options.context_budget_minimum_protection_tokens
        if options.context_budget_minimum_protection_tokens is not None
        else _DEFAULT_COMMAND_MINIMUM_PROTECTION_TOKENS
    )
    _require_non_negative_int(
        minimum_protection_tokens,
        field_name=(
            "HostCommandHandleOptions."
            "context_budget_minimum_protection_tokens"
        ),
    )
    if minimum_protection_tokens >= input_budget_tokens:
        raise ValueError(
            "HostCommandHandleOptions.context_budget_minimum_protection_tokens "
            "must be smaller than input budget"
        )
    return input_budget_tokens - minimum_protection_tokens


@dataclass(frozen=True, slots=True)
class EnsureSessionRequest:
    """确保 Session 存在并绑定到 slot 的请求。

    字段语义：

    - ``scope``：slot 命名空间。
    - ``slot_key``：slot 稳定键。
    - ``metadata``：中性附加说明，不承载显式请求字段。
    """

    scope: str
    slot_key: str
    metadata: tuple[HostMetadataEntry, ...]

    def __post_init__(self) -> None:
        """校验 ensure session 请求字段。

        :returns: 无返回值。
        :raises ValueError: slot 字段或 metadata key 为空时抛出。
        """

        _require_non_empty(self.scope, field_name="EnsureSessionRequest.scope")
        _require_non_empty(
            self.slot_key, field_name="EnsureSessionRequest.slot_key"
        )
        _require_metadata_entries(
            self.metadata, field_name="EnsureSessionRequest.metadata"
        )


@dataclass(frozen=True, slots=True)
class CreateSessionRequest:
    """显式创建 Session 的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``client_request_id``：客户端操作幂等 id。
    - ``bind_slot``：是否把新 Session 绑定到 slot。
    - ``scope``：绑定 slot 时的命名空间；不绑定时可为 ``None``。
    - ``slot_key``：绑定 slot 时的稳定键；不绑定时可为 ``None``。
    - ``metadata``：中性附加说明，不承载显式请求字段。
    """

    context: HostCallContext
    client_request_id: str
    bind_slot: bool
    scope: str | None
    slot_key: str | None
    metadata: tuple[HostMetadataEntry, ...]

    def __post_init__(self) -> None:
        """校验 create session 请求字段与 slot 绑定前置条件。

        :returns: 无返回值。
        :raises ValueError: 幂等 id 为空、metadata key 为空，或绑定 slot
            时缺少 ``scope`` / ``slot_key`` 时抛出。
        """

        _require_non_empty(
            self.client_request_id,
            field_name="CreateSessionRequest.client_request_id",
        )
        if self.bind_slot:
            _require_optional_non_empty(
                self.scope, field_name="CreateSessionRequest.scope"
            )
            _require_optional_non_empty(
                self.slot_key, field_name="CreateSessionRequest.slot_key"
            )
            if self.scope is None or self.slot_key is None:
                raise ValueError(
                    "CreateSessionRequest scope and slot_key are required"
                )
        else:
            _require_optional_non_empty(
                self.scope, field_name="CreateSessionRequest.scope"
            )
            _require_optional_non_empty(
                self.slot_key, field_name="CreateSessionRequest.slot_key"
            )
        _require_metadata_entries(
            self.metadata, field_name="CreateSessionRequest.metadata"
        )


@dataclass(frozen=True, slots=True)
class CloseSessionRequest:
    """关闭 Session 的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``client_request_id``：客户端操作幂等 id。
    - ``reason``：关闭原因机器码或短说明。
    """

    context: HostCallContext
    client_request_id: str
    reason: str

    def __post_init__(self) -> None:
        """校验 close session 请求字段。

        :returns: 无返回值。
        :raises ValueError: 幂等 id 或 reason 为空时抛出。
        """

        _require_non_empty(
            self.client_request_id,
            field_name="CloseSessionRequest.client_request_id",
        )
        _require_non_empty(
            self.reason, field_name="CloseSessionRequest.reason"
        )


@dataclass(frozen=True, slots=True)
class PurgeSessionRequest:
    """清理已关闭 Session 本地可恢复事实的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``client_request_id``：客户端操作幂等 id。
    - ``reason``：清理原因机器码或短说明。
    """

    context: HostCallContext
    client_request_id: str
    reason: str

    def __post_init__(self) -> None:
        """校验 purge session 请求字段。

        :returns: 无返回值。
        :raises ValueError: 幂等 id 或 reason 为空时抛出。
        """

        _require_non_empty(
            self.client_request_id,
            field_name="PurgeSessionRequest.client_request_id",
        )
        _require_non_empty(
            self.reason, field_name="PurgeSessionRequest.reason"
        )


@dataclass(frozen=True, slots=True)
class StartRunRequest:
    """显式启动独立 Run 的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``session_id``：目标 Session id。
    - ``client_request_id``：客户端操作幂等 id。
    - ``input``：Host 输入 envelope。
    - ``execution_target``：执行目标标识。
    - ``queue_policy``：排队策略标识。
    """

    context: HostCallContext
    session_id: str
    client_request_id: str
    input: HostInput
    execution_target: str
    queue_policy: str

    def __post_init__(self) -> None:
        """校验 start run 请求字段。

        :returns: 无返回值。
        :raises ValueError: id 或必填字符串为空时抛出。
        """

        _require_non_empty(
            self.session_id, field_name="StartRunRequest.session_id"
        )
        _require_non_empty(
            self.client_request_id,
            field_name="StartRunRequest.client_request_id",
        )
        _require_non_empty(
            self.execution_target,
            field_name="StartRunRequest.execution_target",
        )
        _require_non_empty(
            self.queue_policy, field_name="StartRunRequest.queue_policy"
        )


@dataclass(frozen=True, slots=True)
class CancelRunRequest:
    """取消单个 Run 的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``client_request_id``：客户端操作幂等 id。
    - ``reason``：取消原因机器码或短说明。
    - ``mode``：取消模式；Phase 1 只允许 graceful。
    """

    context: HostCallContext
    client_request_id: str
    reason: str
    mode: CancelMode

    def __post_init__(self) -> None:
        """校验 cancel run 请求字段。

        :returns: 无返回值。
        :raises ValueError: 幂等 id、reason 为空或取消模式非法时抛出。
        """

        _require_non_empty(
            self.client_request_id,
            field_name="CancelRunRequest.client_request_id",
        )
        _require_non_empty(self.reason, field_name="CancelRunRequest.reason")
        _require_graceful_cancel(self.mode, field_name="CancelRunRequest.mode")


@dataclass(frozen=True, slots=True)
class CancelSessionRunsRequest:
    """取消 Session 下全部未终态 Run 的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``client_request_id``：客户端操作幂等 id。
    - ``reason``：取消原因机器码或短说明。
    - ``mode``：取消模式；Phase 1 只允许 graceful。
    """

    context: HostCallContext
    client_request_id: str
    reason: str
    mode: CancelMode

    def __post_init__(self) -> None:
        """校验 cancel session runs 请求字段。

        :returns: 无返回值。
        :raises ValueError: 幂等 id、reason 为空或取消模式非法时抛出。
        """

        _require_non_empty(
            self.client_request_id,
            field_name="CancelSessionRunsRequest.client_request_id",
        )
        _require_non_empty(
            self.reason, field_name="CancelSessionRunsRequest.reason"
        )
        _require_graceful_cancel(
            self.mode, field_name="CancelSessionRunsRequest.mode"
        )


@dataclass(frozen=True, slots=True)
class SubmitFollowupRequest:
    """向同一 Session 提交后续输入的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``session_id``：目标 Session id。
    - ``client_request_id``：客户端操作幂等 id。
    - ``system_prompt``：本次 Run 的显式系统提示；无则为 ``None``。
    - ``user_prompt``：本次 Run 的用户提示。
    - ``tool_names``：本次 Run 的业务工具选择器；``None`` 表示全量业务工具，
      空集合表示禁用业务工具，非空集合表示只启用指定子集。
    - ``runner_spec``：本次 Run 的完整 Runner 规约 override；无则使用 opener
      baseline。
    - ``runner_options``：本次 Run 的完整 Runner 调用参数 override；无则使用
      opener baseline。
    - ``agent_policy``：本次 Run 的完整 Agent policy override；无则使用
      opener baseline。
    - ``behavior``：queue 或 steer 行为。
    - ``target_run_id``：steer 目标 Run id；queue 时必须为 ``None``。
    """

    context: HostCallContext
    session_id: str
    client_request_id: str
    system_prompt: str | None
    user_prompt: str
    tool_names: frozenset[str] | None
    runner_spec: RunnerSpec | None
    runner_options: RunnerCallOptions | None
    agent_policy: AgentPolicy | None
    behavior: FollowupBehavior
    target_run_id: str | None

    def __post_init__(self) -> None:
        """校验 follow-up 请求字段与 target_run_id 前置条件。

        :returns: 无返回值。
        :raises TypeError: typed override 或工具选择器类型非法时抛出。
        :raises ValueError: id / prompt 为空、steer 缺目标、queue 携带目标时抛出。
        """

        _require_non_empty(
            self.session_id, field_name="SubmitFollowupRequest.session_id"
        )
        _require_non_empty(
            self.client_request_id,
            field_name="SubmitFollowupRequest.client_request_id",
        )
        _require_optional_non_empty(
            self.system_prompt,
            field_name="SubmitFollowupRequest.system_prompt",
        )
        _require_non_empty(
            self.user_prompt, field_name="SubmitFollowupRequest.user_prompt"
        )
        _validate_submit_followup_tool_names(self.tool_names)
        if self.runner_spec is not None and not isinstance(
            self.runner_spec, RunnerSpec
        ):
            raise TypeError("SubmitFollowupRequest.runner_spec must be RunnerSpec")
        if self.runner_options is not None and not isinstance(
            self.runner_options, RunnerCallOptions
        ):
            raise TypeError(
                "SubmitFollowupRequest.runner_options must be RunnerCallOptions"
            )
        if self.agent_policy is not None and not isinstance(
            self.agent_policy, AgentPolicy
        ):
            raise TypeError("SubmitFollowupRequest.agent_policy must be AgentPolicy")
        _require_optional_non_empty(
            self.target_run_id,
            field_name="SubmitFollowupRequest.target_run_id",
        )
        if (
            self.behavior == FollowupBehavior.STEER
            and self.target_run_id is None
        ):
            raise ValueError(
                "SubmitFollowupRequest.target_run_id is required for steer"
            )
        if (
            self.behavior == FollowupBehavior.QUEUE
            and self.target_run_id is not None
        ):
            raise ValueError(
                "SubmitFollowupRequest.target_run_id must be None for queue"
            )


def _validate_submit_followup_tool_names(
    tool_names: frozenset[str] | None,
) -> None:
    """校验 follow-up 业务工具选择器。

    :param tool_names: 请求传入的工具名集合或 ``None``。
    :returns: ``None``。
    :raises TypeError: ``tool_names`` 不是 ``frozenset[str] | None`` 时抛出。
    :raises ValueError: 任一工具名为空时抛出。
    """

    if tool_names is None:
        return
    if not isinstance(tool_names, frozenset):
        raise TypeError("SubmitFollowupRequest.tool_names must be frozenset[str]")
    for tool_name in tool_names:
        if not isinstance(tool_name, str):
            raise TypeError("SubmitFollowupRequest.tool_names entries must be str")
        _require_non_empty(
            tool_name, field_name="SubmitFollowupRequest.tool_names"
        )


@dataclass(frozen=True, slots=True)
class RetryRunRequest:
    """重试源 Run 的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``client_request_id``：客户端操作幂等 id。
    - ``reason``：重试原因机器码或短说明。
    """

    context: HostCallContext
    client_request_id: str
    reason: str

    def __post_init__(self) -> None:
        """校验 retry run 请求字段。

        :returns: 无返回值。
        :raises ValueError: 幂等 id 或 reason 为空时抛出。
        """

        _require_non_empty(
            self.client_request_id,
            field_name="RetryRunRequest.client_request_id",
        )
        _require_non_empty(self.reason, field_name="RetryRunRequest.reason")


@dataclass(frozen=True, slots=True)
class ReplayRunRequest:
    """对源 Run 做 no-tool 结构修复的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``client_request_id``：客户端操作幂等 id。
    - ``reason``：replay 原因机器码或短说明。
    - ``repair_instruction``：结构修复指令。
    """

    context: HostCallContext
    client_request_id: str
    reason: str
    repair_instruction: str

    def __post_init__(self) -> None:
        """校验 replay run 请求字段。

        :returns: 无返回值。
        :raises ValueError: 幂等 id、reason 或修复指令为空时抛出。
        """

        _require_non_empty(
            self.client_request_id,
            field_name="ReplayRunRequest.client_request_id",
        )
        _require_non_empty(self.reason, field_name="ReplayRunRequest.reason")
        _require_non_empty(
            self.repair_instruction,
            field_name="ReplayRunRequest.repair_instruction",
        )


@dataclass(frozen=True, slots=True)
class ResolveWaitRequest:
    """接收外部等待结果并交给 Host 治理的请求。

    字段语义：

    - ``context``：调用上下文。
    - ``idempotency_key``：等待结果接收幂等键。
    - ``outcome``：强类型等待结果 envelope。
    - ``source``：等待结果来源。
    - ``observed_at``：UTC aware 结果观测时间。
    """

    context: HostCallContext
    idempotency_key: str
    outcome: ResolveWaitOutcome
    source: WaitResolutionSource
    observed_at: datetime

    def __post_init__(self) -> None:
        """校验 resolve wait 请求字段。

        :returns: 无返回值。
        :raises TypeError: ``outcome`` 或 ``observed_at`` 类型非法时抛出。
        :raises ValueError: 幂等键为空、超长或观测时间不是 UTC 时抛出。
        """

        _require_max_length(
            self.idempotency_key,
            field_name="ResolveWaitRequest.idempotency_key",
            max_length=HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
        )
        if not isinstance(
            self.outcome,
            (
                ResolveWaitCompletedOutcome,
                ResolveWaitFailedOutcome,
                ResolveWaitCancelledOutcome,
                ResolveWaitLostOutcome,
            ),
        ):
            raise TypeError("ResolveWaitRequest.outcome must be ResolveWaitOutcome")
        if not isinstance(self.source, WaitResolutionSource):
            raise TypeError("ResolveWaitRequest.source must be WaitResolutionSource")
        _require_utc_datetime(
            self.observed_at, field_name="ResolveWaitRequest.observed_at"
        )


@dataclass(frozen=True, slots=True)
class TerminalResultSummary:
    """Run 终态结果摘要。

    字段语义：

    - ``status``：Run 终态状态。
    - ``summary_ref``：终态摘要引用；无摘要时为 ``None``。
    - ``summary_digest``：终态摘要内容摘要；无摘要时为 ``None``。
    """

    status: RunStatus
    summary_ref: str | None
    summary_digest: str | None

    def __post_init__(self) -> None:
        """校验终态结果摘要引用字段。

        :returns: 无返回值。
        :raises ValueError: 可选引用或摘要存在但为空时抛出。
        """

        _require_optional_non_empty(
            self.summary_ref, field_name="TerminalResultSummary.summary_ref"
        )
        _require_optional_non_empty(
            self.summary_digest,
            field_name="TerminalResultSummary.summary_digest",
        )


@dataclass(frozen=True, slots=True)
class OutboxSummary:
    """终态 outbox 投递摘要。

    字段语义：

    - ``terminal_event_id``：终态事件 id。
    - ``event_sequence``：终态事件序列号。
    - ``delivery_state``：投递状态标识。
    """

    terminal_event_id: str
    event_sequence: int
    delivery_state: str

    def __post_init__(self) -> None:
        """校验 outbox 摘要字段。

        :returns: 无返回值。
        :raises ValueError: 事件 id、投递状态为空或序列号为负时抛出。
        """

        _require_non_empty(
            self.terminal_event_id, field_name="OutboxSummary.terminal_event_id"
        )
        _require_non_negative(
            self.event_sequence, field_name="OutboxSummary.event_sequence"
        )
        _require_non_empty(
            self.delivery_state, field_name="OutboxSummary.delivery_state"
        )


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Session read model 快照。

    字段语义：

    - ``session_id``：Session id。
    - ``status``：Session 当前状态。
    - ``slot``：绑定 slot；未绑定时为 ``None``。
    - ``active_run_id``：当前 active Run id；无 active Run 时为 ``None``。
    - ``queued_run_ids``：已持久化但未启动的 queued Run id。
    - ``timeline_cursor``：Session timeline 当前游标。
    """

    session_id: str
    status: SessionStatus
    slot: SessionSlotRef | None
    active_run_id: str | None
    queued_run_ids: tuple[str, ...]
    timeline_cursor: HostStreamCursor

    def __post_init__(self) -> None:
        """校验 Session 快照 id 字段。

        :returns: 无返回值。
        :raises ValueError: Session id、active run id 或 queued run id 为空时抛出。
        """

        _require_non_empty(
            self.session_id, field_name="SessionSnapshot.session_id"
        )
        _require_optional_non_empty(
            self.active_run_id, field_name="SessionSnapshot.active_run_id"
        )
        for run_id in self.queued_run_ids:
            _require_non_empty(
                run_id, field_name="SessionSnapshot.queued_run_ids"
            )


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """Run read model 快照。

    字段语义：

    - ``run_id``：Run id。
    - ``session_id``：所属 Session id。
    - ``status``：Run 当前状态。
    - ``current_attempt_id``：当前 Attempt id；无当前 Attempt 时为 ``None``。
    - ``terminal_result_summary``：终态结果摘要；非终态或无摘要时为 ``None``。
    - ``event_cursor``：Run 当前事件游标。
    - ``source_run_id``：retry / replay 源 Run id；无源 Run 时为 ``None``。
    - ``source_run_relation``：与源 Run 的关系；无源 Run 时为 ``None``。
    - ``outbox_summary``：终态 outbox 摘要；无投递摘要时为 ``None``。
    """

    run_id: str
    session_id: str
    status: RunStatus
    current_attempt_id: str | None
    terminal_result_summary: TerminalResultSummary | None
    event_cursor: HostStreamCursor
    source_run_id: str | None
    source_run_relation: SourceRunRelation | None
    outbox_summary: OutboxSummary | None

    def __post_init__(self) -> None:
        """校验 Run 快照 id 字段。

        :returns: 无返回值。
        :raises ValueError: id 字段为空，或 source relation 与 source id 不一致时抛出。
        """

        _require_non_empty(self.run_id, field_name="RunSnapshot.run_id")
        _require_non_empty(
            self.session_id, field_name="RunSnapshot.session_id"
        )
        _require_optional_non_empty(
            self.current_attempt_id,
            field_name="RunSnapshot.current_attempt_id",
        )
        _require_optional_non_empty(
            self.source_run_id, field_name="RunSnapshot.source_run_id"
        )
        if self.source_run_id is None and self.source_run_relation is not None:
            raise ValueError(
                "RunSnapshot.source_run_relation requires source_run_id"
            )
        if self.source_run_id is not None and self.source_run_relation is None:
            raise ValueError(
                "RunSnapshot.source_run_id requires source_run_relation"
            )


@dataclass(frozen=True, slots=True)
class FollowupSnapshot:
    """follow-up 接受结果快照。

    字段语义：

    - ``accepted_input_ref``：已接受输入的引用。
    - ``behavior``：Host 采用的 follow-up 行为。
    - ``accepted_run_id``：本次 follow-up 接受后关联的 Run id。
    - ``accepted_run_status``：本次 follow-up 接受后关联 Run 的当前状态。
    - ``command_watermark``：本次 command commit 后的 durable read watermark；
      它不是 ``watch_session_events`` 的 watch cursor。
    - ``queued_run_id``：真实处于 queued 状态的 accepted Run id；其它情况为 ``None``。
    - ``target_run_id``：steer 目标 Run id；queue 时为 ``None``。
    """

    accepted_input_ref: str
    behavior: FollowupBehavior
    accepted_run_id: str
    accepted_run_status: RunStatus
    command_watermark: HostStreamCursor
    queued_run_id: str | None
    target_run_id: str | None

    def __post_init__(self) -> None:
        """校验 follow-up 快照字段与行为一致性。

        :returns: 无返回值。
        :raises ValueError: 引用 / id 为空，或 queue / steer 字段组合非法时抛出。
        """

        _require_non_empty(
            self.accepted_input_ref,
            field_name="FollowupSnapshot.accepted_input_ref",
        )
        _require_non_empty(
            self.accepted_run_id,
            field_name="FollowupSnapshot.accepted_run_id",
        )
        _require_optional_non_empty(
            self.target_run_id, field_name="FollowupSnapshot.target_run_id"
        )
        _require_optional_non_empty(
            self.queued_run_id, field_name="FollowupSnapshot.queued_run_id"
        )
        if self.behavior == FollowupBehavior.QUEUE:
            if self.target_run_id is not None:
                raise ValueError(
                    "FollowupSnapshot.target_run_id must be None for queue"
                )
            if self.accepted_run_status == RunStatus.QUEUED:
                if self.queued_run_id != self.accepted_run_id:
                    raise ValueError(
                        "FollowupSnapshot.queued_run_id must equal "
                        "accepted_run_id for queued queue result"
                    )
            if self.accepted_run_status != RunStatus.QUEUED:
                if self.queued_run_id is not None:
                    raise ValueError(
                        "FollowupSnapshot.queued_run_id must be None "
                        "unless accepted Run is queued"
                    )
            if self.accepted_run_status == RunStatus.RECOVERING:
                raise ValueError(
                    "FollowupSnapshot.accepted_run_status must not be recovering"
                )


@dataclass(frozen=True, slots=True)
class PurgeSessionResult:
    """Session 清理结果。

    字段语义：

    - ``session_id``：被清理的 Session id。
    - ``purged``：是否完成清理。
    - ``purge_tombstone_ref``：清理 tombstone 引用；未清理时为 ``None``。
    - ``deleted_counts_digest``：删除计数摘要；未清理时为 ``None``。
    """

    session_id: str
    purged: bool
    purge_tombstone_ref: str | None
    deleted_counts_digest: str | None

    def __post_init__(self) -> None:
        """校验清理结果字段。

        :returns: 无返回值。
        :raises ValueError: Session id 为空，或可选引用存在但为空时抛出。
        """

        _require_non_empty(
            self.session_id, field_name="PurgeSessionResult.session_id"
        )
        _require_optional_non_empty(
            self.purge_tombstone_ref,
            field_name="PurgeSessionResult.purge_tombstone_ref",
        )
        _require_optional_non_empty(
            self.deleted_counts_digest,
            field_name="PurgeSessionResult.deleted_counts_digest",
        )


@dataclass(frozen=True, slots=True)
class HostEventView:
    """Host event stream 的事件视图。

    字段语义：

    - ``event_sequence``：全局单调事件序列。
    - ``event_id``：canonical event id。
    - ``event_class``：事件分类，用于区分 canonical fact、preview、
      diagnostic 与 projection signal。
    - ``event_type``：事件类型标识。
    - ``session_id``：关联 Session id。
    - ``run_id``：关联 Run id；事件不绑定 Run 时为 ``None``。
    - ``payload_ref``：事件 payload 引用；无 payload 时为 ``None``。
    - ``payload_digest``：事件 payload 摘要；无 payload 时为 ``None``。
    """

    event_sequence: int
    event_id: str
    event_class: HostEventClass
    event_type: str
    session_id: str
    run_id: str | None
    payload_ref: str | None
    payload_digest: str | None

    def __post_init__(self) -> None:
        """校验 Host event view 字段。

        :returns: 无返回值。
        :raises ValueError: 序列号为负、id 为空或可选引用存在但为空时抛出。
        """

        _require_non_negative(
            self.event_sequence, field_name="HostEventView.event_sequence"
        )
        _require_non_empty(self.event_id, field_name="HostEventView.event_id")
        if not isinstance(self.event_class, HostEventClass):
            raise ValueError("HostEventView.event_class must be HostEventClass")
        _require_non_empty(
            self.event_type, field_name="HostEventView.event_type"
        )
        _require_non_empty(
            self.session_id, field_name="HostEventView.session_id"
        )
        _require_optional_non_empty(
            self.run_id, field_name="HostEventView.run_id"
        )
        _require_optional_non_empty(
            self.payload_ref, field_name="HostEventView.payload_ref"
        )
        _require_optional_non_empty(
            self.payload_digest, field_name="HostEventView.payload_digest"
        )


@dataclass(frozen=True, slots=True)
class HostEventStream:
    """Host event stream 补读结果。

    字段语义：

    - ``events``：按 ``event_sequence`` 排列的事件视图。
    - ``next_cursor``：下一次补读使用的游标。
    """

    events: tuple[HostEventView, ...]
    next_cursor: HostStreamCursor


class HostEventKind(StrEnum):
    """Service-facing Host event 类型。

    成员：

    - ``PROGRESS``：非终态进度事件。
    - ``SUCCEEDED``：Run 成功终态事件。
    - ``FAILED``：Run 失败终态事件。
    - ``CANCELLED``：Run 取消终态事件。
    """

    PROGRESS = "progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HostTerminalStatus(StrEnum):
    """Service-facing terminal Host event 状态。

    成员：

    - ``SUCCEEDED``：Run 成功完成。
    - ``FAILED``：Run 失败完成。
    - ``CANCELLED``：Run 被用户治理取消。
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutboxTerminalItemState(StrEnum):
    """Outbox terminal item 队列状态。

    成员只表达 Host outbox projection 内部 drain 状态，不表达任何 Service /
    UI / channel 投递成功事实。
    """

    PENDING = "pending"
    DRAINED = "drained"


class OutboxProjectionStatus(StrEnum):
    """Outbox projection 对调用方可见的追平状态。

    成员：

    - ``CAUGHT_UP``：Outbox projection checkpoint 已追到当前 EventLog 水位。
    - ``LAGGED``：projection checkpoint 落后，调用方不能把空结果视为完整。
    - ``FAILED``：最近一次 projection catch-up 失败或存在 failure row。
    """

    CAUGHT_UP = "caught_up"
    LAGGED = "lagged"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class HostFinalAnswerView:
    """terminal Host event 中内联的最终回答视图。

    :param content: 最终回答文本。
    :param filtered: 最终回答是否经过安全或展示过滤。
    :param degraded: 最终回答是否为降级结果。
    :param finish_reason: provider / runner 归一化 finish reason；未知时为
        ``None``。
    :param terminal_status: 对应 terminal Host event 状态。
    """

    content: str
    filtered: bool
    degraded: bool
    finish_reason: str | None
    terminal_status: HostTerminalStatus

    def __post_init__(self) -> None:
        """校验最终回答视图字段。

        :returns: ``None``。
        :raises TypeError: 布尔字段类型非法时抛出。
        :raises ValueError: 可选 finish reason 为空，或 terminal 状态不是
            ``SUCCEEDED`` 时抛出。
        """

        if not isinstance(self.content, str):
            raise TypeError("HostFinalAnswerView.content must be str")
        _require_bool(
            self.filtered, field_name="HostFinalAnswerView.filtered"
        )
        _require_bool(
            self.degraded, field_name="HostFinalAnswerView.degraded"
        )
        _require_optional_non_empty(
            self.finish_reason,
            field_name="HostFinalAnswerView.finish_reason",
        )
        if self.terminal_status != HostTerminalStatus.SUCCEEDED:
            raise ValueError(
                "HostFinalAnswerView.terminal_status must be succeeded"
            )


@dataclass(frozen=True, slots=True)
class OutboxTerminalCursor:
    """Outbox terminal 补读游标。

    :param event_sequence: 调用方已经处理的 terminal EventLog sequence 水位。
    """

    event_sequence: int

    def __post_init__(self) -> None:
        """校验 Outbox terminal 游标。

        :returns: ``None``。
        :raises TypeError: ``event_sequence`` 不是严格整数时抛出。
        :raises ValueError: ``event_sequence`` 为负数时抛出。
        """

        _require_non_negative_int(
            self.event_sequence,
            field_name="OutboxTerminalCursor.event_sequence",
        )


@dataclass(frozen=True, slots=True)
class OutboxTerminalItem:
    """Outbox terminal delivery queue 的 public item。

    :param item_id: Outbox item 稳定 id。
    :param idempotency_key: projection 内部幂等键，调用方不应依赖它去重。
    :param terminal_event_id: source terminal EventLog id。
    :param event_sequence: source terminal EventLog sequence。
    :param session_id: source Session id。
    :param run_id: source Run id。
    :param terminal_status: terminal 状态。
    :param dedupe_key: 与 live ``HostEvent.dedupe_key`` 对齐的去重键。
    :param final_answer: 成功终态的最终回答视图；其它终态为 ``None``。
    :param error_message: 失败终态展示消息。
    :param cancel_reason: 取消终态原因。
    :param result_ref: 可选结果 payload 引用。
    :param result_digest: 可选结果 payload digest。
    :param terminal_summary_ref: 可选 terminal summary 引用。
    :param terminal_summary_digest: 可选 terminal summary digest。
    :param projected_at: item 首次投影时间，必须为 UTC-aware datetime。
    :param item_state: outbox queue item 状态。
    """

    item_id: str
    idempotency_key: str
    terminal_event_id: str
    event_sequence: int
    session_id: str
    run_id: str
    terminal_status: HostTerminalStatus
    dedupe_key: str
    final_answer: HostFinalAnswerView | None
    error_message: str | None
    cancel_reason: str | None
    result_ref: str | None
    result_digest: str | None
    terminal_summary_ref: str | None
    terminal_summary_digest: str | None
    projected_at: datetime
    item_state: OutboxTerminalItemState

    def __post_init__(self) -> None:
        """校验 public Outbox terminal item 字段。

        :returns: ``None``。
        :raises TypeError: enum、datetime 或 final answer 字段类型非法时抛出。
        :raises ValueError: 必填文本为空、sequence 非法或 terminal payload 组合非法时抛出。
        """

        _require_non_empty(self.item_id, field_name="OutboxTerminalItem.item_id")
        _require_non_empty(
            self.idempotency_key,
            field_name="OutboxTerminalItem.idempotency_key",
        )
        _require_non_empty(
            self.terminal_event_id,
            field_name="OutboxTerminalItem.terminal_event_id",
        )
        _require_non_negative_int(
            self.event_sequence,
            field_name="OutboxTerminalItem.event_sequence",
        )
        _require_non_empty(
            self.session_id, field_name="OutboxTerminalItem.session_id"
        )
        _require_non_empty(self.run_id, field_name="OutboxTerminalItem.run_id")
        if not isinstance(self.terminal_status, HostTerminalStatus):
            raise TypeError(
                "OutboxTerminalItem.terminal_status must be HostTerminalStatus"
            )
        _require_non_empty(
            self.dedupe_key, field_name="OutboxTerminalItem.dedupe_key"
        )
        if self.dedupe_key != self.terminal_event_id:
            raise ValueError(
                "OutboxTerminalItem.dedupe_key must equal terminal_event_id"
            )
        if self.final_answer is not None and not isinstance(
            self.final_answer, HostFinalAnswerView
        ):
            raise TypeError(
                "OutboxTerminalItem.final_answer must be HostFinalAnswerView"
            )
        _require_optional_non_empty(
            self.error_message, field_name="OutboxTerminalItem.error_message"
        )
        _require_optional_non_empty(
            self.cancel_reason, field_name="OutboxTerminalItem.cancel_reason"
        )
        _require_optional_non_empty(
            self.result_ref, field_name="OutboxTerminalItem.result_ref"
        )
        _require_optional_sha256_digest(
            self.result_digest, field_name="OutboxTerminalItem.result_digest"
        )
        _require_optional_non_empty(
            self.terminal_summary_ref,
            field_name="OutboxTerminalItem.terminal_summary_ref",
        )
        _require_optional_sha256_digest(
            self.terminal_summary_digest,
            field_name="OutboxTerminalItem.terminal_summary_digest",
        )
        if (self.result_ref is None) != (self.result_digest is None):
            raise ValueError("OutboxTerminalItem result ref and digest must pair")
        if (self.terminal_summary_ref is None) != (
            self.terminal_summary_digest is None
        ):
            raise ValueError("OutboxTerminalItem summary ref and digest must pair")
        _require_utc_datetime(
            self.projected_at, field_name="OutboxTerminalItem.projected_at"
        )
        if not isinstance(self.item_state, OutboxTerminalItemState):
            raise TypeError(
                "OutboxTerminalItem.item_state must be OutboxTerminalItemState"
            )
        _validate_outbox_terminal_payload(self)


@dataclass(frozen=True, slots=True)
class ReadOutboxTerminalItemsRequest:
    """读取 Outbox terminal items 的 public 请求。

    :param after: 严格返回该 terminal cursor 之后的 item。
    :param seen_terminal_event_ids: 调用方已通过 live watch 或本地记录展示过的 terminal ids。
    :param limit: 本次返回 item 上限。
    """

    after: OutboxTerminalCursor
    seen_terminal_event_ids: tuple[str, ...]
    limit: int

    def __post_init__(self) -> None:
        """校验 Outbox read 请求。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: limit 越界、seen id 为空或重复时抛出。
        """

        _validate_outbox_read_page_fields(
            self.after,
            self.seen_terminal_event_ids,
            self.limit,
            request_name="ReadOutboxTerminalItemsRequest",
        )


@dataclass(frozen=True, slots=True)
class DrainOutboxTerminalItemsRequest:
    """幂等 drain Outbox terminal items 的 public 请求。

    :param context: Host 调用上下文，只表达调用责任链，不表达 channel 投递目标。
    :param after: 严格 drain 该 terminal cursor 之后的 item。
    :param seen_terminal_event_ids: 调用方已展示过的 terminal ids。
    :param limit: 本次返回 item 上限。
    :param drain_request_id: drain 幂等请求 id。
    """

    context: HostCallContext
    after: OutboxTerminalCursor
    seen_terminal_event_ids: tuple[str, ...]
    limit: int
    drain_request_id: str

    def __post_init__(self) -> None:
        """校验 Outbox drain 请求。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: limit 越界、seen id 为空或重复、幂等 id 为空时抛出。
        """

        if not isinstance(self.context, HostCallContext):
            raise TypeError(
                "DrainOutboxTerminalItemsRequest.context must be HostCallContext"
            )
        _validate_outbox_read_page_fields(
            self.after,
            self.seen_terminal_event_ids,
            self.limit,
            request_name="DrainOutboxTerminalItemsRequest",
        )
        _require_non_empty(
            self.drain_request_id,
            field_name="DrainOutboxTerminalItemsRequest.drain_request_id",
        )


@dataclass(frozen=True, slots=True)
class OutboxTerminalItemsBatch:
    """Outbox terminal read / drain 返回批次。

    :param items: 当前批次返回的 terminal items。
    :param next_cursor: 调用方可保存的推荐 terminal watermark。
    :param scanned_watermark: 本次查询实际扫描到的最高 terminal sequence。
    :param projection_checkpoint: Outbox projection 当前 checkpoint。
    :param projection_status: Outbox projection catch-up 状态。
    :param projection_error_code: projection 失败码；无失败时为 ``None``。
    :param projection_error_message: projection 失败消息；无失败时为 ``None``。
    :param has_more: 当前 cursor 后是否还有同 Session item。
    """

    items: tuple[OutboxTerminalItem, ...]
    next_cursor: OutboxTerminalCursor
    scanned_watermark: OutboxTerminalCursor
    projection_checkpoint: OutboxTerminalCursor
    projection_status: OutboxProjectionStatus
    projection_error_code: str | None
    projection_error_message: str | None
    has_more: bool

    def __post_init__(self) -> None:
        """校验 Outbox terminal batch 字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 错误字段或 item 元组非法时抛出。
        """

        if not isinstance(self.items, tuple):
            raise TypeError("OutboxTerminalItemsBatch.items must be tuple")
        for item in self.items:
            if not isinstance(item, OutboxTerminalItem):
                raise TypeError(
                    "OutboxTerminalItemsBatch.items must contain OutboxTerminalItem"
                )
        if not isinstance(self.next_cursor, OutboxTerminalCursor):
            raise TypeError(
                "OutboxTerminalItemsBatch.next_cursor must be OutboxTerminalCursor"
            )
        if not isinstance(self.scanned_watermark, OutboxTerminalCursor):
            raise TypeError(
                "OutboxTerminalItemsBatch.scanned_watermark must be "
                "OutboxTerminalCursor"
            )
        if not isinstance(self.projection_checkpoint, OutboxTerminalCursor):
            raise TypeError(
                "OutboxTerminalItemsBatch.projection_checkpoint must be "
                "OutboxTerminalCursor"
            )
        if not isinstance(self.projection_status, OutboxProjectionStatus):
            raise TypeError(
                "OutboxTerminalItemsBatch.projection_status must be "
                "OutboxProjectionStatus"
            )
        _require_optional_non_empty(
            self.projection_error_code,
            field_name="OutboxTerminalItemsBatch.projection_error_code",
        )
        _require_optional_non_empty(
            self.projection_error_message,
            field_name="OutboxTerminalItemsBatch.projection_error_message",
        )
        if not isinstance(self.has_more, bool):
            raise TypeError("OutboxTerminalItemsBatch.has_more must be bool")


@dataclass(frozen=True, slots=True)
class HostEvent:
    """Service-facing Host-owned typed event。

    :param event_id: Host event 稳定 id。
    :param event_sequence: Host durable store 分配的全局单调事件序列。
    :param session_id: 关联 Session id。
    :param run_id: 关联 Run id；事件不绑定 Run 时为 ``None``。
    :param kind: Service-facing event 类型。
    :param dedupe_key: 调用方去重使用的稳定键。
    :param terminal_status: terminal event 状态；非终态事件为 ``None``。
    :param final_answer: 成功终态事件内联的最终回答视图；非成功终态为
        ``None``。
    :param error_message: 失败终态的 typed 展示消息；无展示消息时为
        ``None``。
    :param cancel_reason: 取消终态的 typed 原因；无展示原因时为 ``None``。
    """

    event_id: str
    event_sequence: int
    session_id: str
    run_id: str | None
    kind: HostEventKind
    dedupe_key: str
    terminal_status: HostTerminalStatus | None
    final_answer: HostFinalAnswerView | None
    error_message: str | None
    cancel_reason: str | None

    def __post_init__(self) -> None:
        """校验 Service-facing Host event 字段。

        :returns: ``None``。
        :raises ValueError: id 为空、序列号非法、kind/status 组合非法或
            terminal payload 组合非法时抛出。
        """

        _require_non_empty(self.event_id, field_name="HostEvent.event_id")
        _require_non_negative(
            self.event_sequence, field_name="HostEvent.event_sequence"
        )
        _require_non_empty(self.session_id, field_name="HostEvent.session_id")
        _require_optional_non_empty(self.run_id, field_name="HostEvent.run_id")
        if not isinstance(self.kind, HostEventKind):
            raise ValueError("HostEvent.kind must be HostEventKind")
        _require_non_empty(self.dedupe_key, field_name="HostEvent.dedupe_key")
        _require_optional_non_empty(
            self.error_message, field_name="HostEvent.error_message"
        )
        _require_optional_non_empty(
            self.cancel_reason, field_name="HostEvent.cancel_reason"
        )
        _validate_host_event_terminal_payload(self)


def _validate_host_event_terminal_payload(event: HostEvent) -> None:
    """校验 public Host event 的 terminal payload 组合。

    :param event: 待校验 Host event。
    :returns: ``None``。
    :raises ValueError: kind、terminal status 与 payload 组合不一致时抛出。
    """

    if event.kind == HostEventKind.PROGRESS:
        if event.terminal_status is not None or event.final_answer is not None:
            raise ValueError(
                "HostEvent progress kind must not include terminal payload"
            )
        return

    expected_status = _terminal_status_for_event_kind(event.kind)
    if event.terminal_status != expected_status:
        raise ValueError("HostEvent.terminal_status does not match kind")
    if event.kind == HostEventKind.SUCCEEDED:
        if event.final_answer is None:
            raise ValueError("HostEvent succeeded kind requires final_answer")
        return
    if event.final_answer is not None:
        raise ValueError(
            "HostEvent failed or cancelled kind must not include final_answer"
        )


def _terminal_status_for_event_kind(kind: HostEventKind) -> HostTerminalStatus:
    """返回 terminal event kind 对应的 terminal status。

    :param kind: terminal Host event kind。
    :returns: 对应 terminal status。
    :raises ValueError: ``kind`` 不是 terminal kind 时抛出。
    """

    if kind == HostEventKind.SUCCEEDED:
        return HostTerminalStatus.SUCCEEDED
    if kind == HostEventKind.FAILED:
        return HostTerminalStatus.FAILED
    if kind == HostEventKind.CANCELLED:
        return HostTerminalStatus.CANCELLED
    raise ValueError("HostEventKind.PROGRESS has no terminal status")


def _validate_outbox_terminal_payload(item: OutboxTerminalItem) -> None:
    """校验 Outbox terminal item 的 terminal payload 组合。

    :param item: 待校验 Outbox terminal item。
    :returns: ``None``。
    :raises ValueError: terminal 状态与 final answer / error / cancel 字段组合不一致时抛出。
    """

    if item.terminal_status is HostTerminalStatus.SUCCEEDED:
        if item.error_message is not None or item.cancel_reason is not None:
            raise ValueError(
                "OutboxTerminalItem succeeded item cannot carry error or cancel"
            )
        return
    if item.final_answer is not None:
        raise ValueError(
            "OutboxTerminalItem failed or cancelled item must not carry final_answer"
        )


def _validate_outbox_read_page_fields(
    after: OutboxTerminalCursor,
    seen_terminal_event_ids: tuple[str, ...],
    limit: int,
    *,
    request_name: str,
) -> None:
    """校验 Outbox read / drain 共享分页字段。

    :param after: 请求游标。
    :param seen_terminal_event_ids: seen terminal event id 元组。
    :param limit: 返回数量上限。
    :param request_name: 错误消息中的请求类型名。
    :returns: ``None``。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: limit 越界、seen id 为空或重复时抛出。
    """

    if not isinstance(after, OutboxTerminalCursor):
        raise TypeError(f"{request_name}.after must be OutboxTerminalCursor")
    if not isinstance(seen_terminal_event_ids, tuple):
        raise TypeError(f"{request_name}.seen_terminal_event_ids must be tuple")
    _require_positive_int(limit, field_name=f"{request_name}.limit")
    if limit > HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT:
        raise ValueError(
            f"{request_name}.limit must be <= "
            f"{HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT}"
        )
    if len(seen_terminal_event_ids) > HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT:
        raise ValueError(
            f"{request_name}.seen_terminal_event_ids length must be <= "
            f"{HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT}"
        )
    seen: set[str] = set()
    for terminal_event_id in seen_terminal_event_ids:
        _require_non_empty(
            terminal_event_id,
            field_name=f"{request_name}.seen_terminal_event_ids",
        )
        if terminal_event_id in seen:
            raise ValueError(f"{request_name}.seen_terminal_event_ids duplicated")
        seen.add(terminal_event_id)


class HostApiError(Exception):
    """Host API 结构化异常。

    字段语义：

    - ``code``：结构化错误码。
    - ``message``：人类可读错误描述。
    - ``retryable``：调用方是否可以重试同一操作。
    - ``detail``：受限 typed 错误详情；无详情时为 ``None``。
    """

    code: HostApiErrorCode
    message: str
    retryable: bool
    detail: HostApiErrorDetail | None

    def __init__(
        self,
        *,
        code: HostApiErrorCode,
        message: str,
        retryable: bool,
        detail: HostApiErrorDetail | None = None,
    ) -> None:
        """构造 Host API 异常。

        :param code: 结构化错误码。
        :param message: 人类可读错误描述。
        :param retryable: 调用方是否可以重试同一操作。
        :param detail: 受限 typed 错误详情；无详情时为 ``None``。
        :returns: 无返回值。
        :raises ValueError: ``message`` 为空或仅包含空白字符时抛出。
        """

        _require_non_empty(message, field_name="HostApiError.message")
        self.code = code
        self.message = message
        self.retryable = retryable
        self.detail = detail
        super().__init__(message)


class HostClosedError(Exception):
    """Host handle 生命周期已关闭异常。

    :param message: 人类可读错误描述。
    """

    def __init__(self, message: str = "Host handle is closed") -> None:
        """构造 Host handle 关闭异常。

        :param message: 人类可读错误描述。
        :returns: 无返回值。
        :raises ValueError: ``message`` 为空时抛出。
        """

        _require_non_empty(message, field_name="HostClosedError.message")
        super().__init__(message)


class Host(Protocol):
    """普通 Service 使用的异步 Host handle 协议。

    该协议只描述 public async command / read / watch 方法，不暴露 durable
    store、scheduler、registry、dispatch row、wakeup port 或 ToolRuntime 内部对象。
    """

    async def ensure_session(
        self, request: EnsureSessionRequest
    ) -> SessionSnapshot:
        """确保 slot 绑定到 Session。

        :param request: ensure session 请求。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Host durable command 失败时抛出。
        """

        ...

    async def create_session(
        self, request: CreateSessionRequest
    ) -> SessionSnapshot:
        """显式创建 Session。

        :param request: create session 请求。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Host durable command 失败时抛出。
        """

        ...

    async def get_session(self, session_id: str) -> SessionSnapshot:
        """读取 Session snapshot。

        :param session_id: 目标 Session id。
        :returns: Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Session 不存在或读取失败时抛出。
        """

        ...

    async def get_run(self, run_id: str) -> RunSnapshot:
        """读取 Run snapshot。

        :param run_id: 目标 Run id。
        :returns: Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Run 不存在或读取失败时抛出。
        """

        ...

    async def read_outbox_terminal_items(
        self,
        session_id: str,
        request: ReadOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """读取 Session 的 Outbox terminal items。

        :param session_id: 目标 Session id。
        :param request: Outbox terminal read 请求。
        :returns: Outbox terminal item 批次与 projection 状态。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Session 不存在或 durable 读取失败时抛出。
        """

        ...

    async def drain_outbox_terminal_items(
        self,
        session_id: str,
        request: DrainOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """幂等 drain Session 的 Outbox terminal items。

        :param session_id: 目标 Session id。
        :param request: Outbox terminal drain 请求。
        :returns: 本次 drain 的 Outbox terminal item 批次与 projection 状态。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Session 不存在、幂等冲突或 durable 写入失败时抛出。
        """

        ...

    async def submit_followup(
        self, session_id: str, request: SubmitFollowupRequest
    ) -> FollowupSnapshot:
        """提交普通 queue / steer follow-up。

        :param session_id: 目标 Session id。
        :param request: follow-up 请求。
        :returns: follow-up 接受结果 snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: 请求未被 Host 接受时抛出。
        """

        ...

    async def retry_run(
        self, run_id: str, request: RetryRunRequest
    ) -> RunSnapshot:
        """重试源 Run。

        :param run_id: 源 Run id。
        :param request: retry 请求。
        :returns: 新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: retry 前置条件不满足时抛出。
        """

        ...

    async def replay_run(
        self, run_id: str, request: ReplayRunRequest
    ) -> RunSnapshot:
        """基于源 Run 创建结构化 replay Run。

        :param run_id: 源 Run id。
        :param request: replay 请求。
        :returns: 新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: replay 前置条件不满足时抛出。
        """

        ...

    async def resolve_wait(
        self, wait_id: str, request: ResolveWaitRequest
    ) -> RunSnapshot:
        """接收已取得的 wait result 并恢复治理路径。

        :param wait_id: 待 resolve 的 wait id。
        :param request: resolve wait 请求。
        :returns: 最新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: wait 不存在、状态非法或幂等冲突时抛出。
        """

        ...

    async def cancel_run(
        self, run_id: str, request: CancelRunRequest
    ) -> RunSnapshot:
        """取消单个 Run。

        :param run_id: 目标 Run id。
        :param request: cancel run 请求。
        :returns: 最新 Run snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: cancel 前置条件不满足时抛出。
        """

        ...

    async def cancel_session_runs(
        self, session_id: str, request: CancelSessionRunsRequest
    ) -> SessionSnapshot:
        """取消 Session 下全部未终态 Run。

        :param session_id: 目标 Session id。
        :param request: cancel session runs 请求。
        :returns: 最新 Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: cancel 前置条件不满足时抛出。
        """

        ...

    async def close_session(
        self, session_id: str, request: CloseSessionRequest
    ) -> SessionSnapshot:
        """关闭 Session 的新输入入口。

        :param session_id: 目标 Session id。
        :param request: close session 请求。
        :returns: 最新 Session snapshot。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: close 前置条件不满足时抛出。
        """

        ...

    def watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]:
        """创建 Session live HostEvent 订阅。

        :param session_id: 目标 Session id。
        :returns: Host-owned typed event async iterator。
        :raises HostClosedError: Host handle 已关闭时抛出。
        :raises HostApiError: Session 不存在或不可 watch 时抛出。
        """

        ...

    async def close(self) -> None:
        """关闭当前 Host handle lifecycle。

        :returns: ``None``。
        :raises HostClosedError: 实现选择对重复关闭 fail fast 时可抛出。
        """

        ...


__all__ = [
    "AttemptDispatchSnapshot",
    "AttemptStatus",
    "AuthorizationClaim",
    "CancelMode",
    "CancelRunRequest",
    "CancelSessionRunsRequest",
    "CloseSessionRequest",
    "CreateSessionRequest",
    "DrainOutboxTerminalItemsRequest",
    "EnsureSessionRequest",
    "FollowupBehavior",
    "FollowupSnapshot",
    "HOST_EVENT_STREAM_DEFAULT_LIMIT",
    "HOST_EVENT_STREAM_MAX_LIMIT",
    "HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT",
    "HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT",
    "HOST_WAIT_ADAPTER_KEY_MAX_LENGTH",
    "HOST_WAIT_EXTERNAL_JOB_ID_MAX_LENGTH",
    "HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH",
    "HOST_WAIT_ID_MAX_LENGTH",
    "HOST_WAIT_PROVIDER_STATUS_REF_MAX_LENGTH",
    "HOST_WAIT_RESUME_TOKEN_MAX_LENGTH",
    "HOST_WAIT_SNAPSHOT_ID_MAX_LENGTH",
    "HOST_WAIT_TOOL_CALL_ID_MAX_LENGTH",
    "HOST_WAIT_TOOL_NAME_MAX_LENGTH",
    "HostApiError",
    "HostApiErrorCode",
    "HostApiErrorDetail",
    "HostCallContext",
    "Host",
    "HostClosedError",
    "HostEvent",
    "HostEventClass",
    "HostEventKind",
    "HostFinalAnswerView",
    "HostMetadataEntry",
    "HostPayloadRef",
    "HostStreamCursor",
    "HostTerminalStatus",
    "LocalEngineWorker",
    "LocalEngineWorkerFactory",
    "LocalWorkerHandle",
    "OperationContext",
    "OpenHostOptions",
    "OrdinaryRunExecutionBaseline",
    "OutboxProjectionStatus",
    "OutboxSummary",
    "OutboxTerminalCursor",
    "OutboxTerminalItem",
    "OutboxTerminalItemsBatch",
    "OutboxTerminalItemState",
    "PurgeSessionRequest",
    "PurgeSessionResult",
    "CompactorRunnerBaseline",
    "ReadOutboxTerminalItemsRequest",
    "ReplayRunRequest",
    "ResolveWaitCancelledOutcome",
    "ResolveWaitCompletedOutcome",
    "ResolveWaitFailedOutcome",
    "ResolveWaitLostOutcome",
    "ResolveWaitOutcome",
    "ResolveWaitRequest",
    "RetryRunRequest",
    "RunSnapshot",
    "RunStatus",
    "SessionSlotRef",
    "SessionSnapshot",
    "SessionStatus",
    "SourceRunRelation",
    "SteerConflictDetail",
    "SubmitFollowupRequest",
    "TerminalResultSummary",
    "WaitAdapterKey",
    "WaitProviderStatusRef",
    "WaitResolutionSource",
]
