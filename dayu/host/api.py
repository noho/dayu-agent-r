"""Host 公共 API 类型契约。

本模块定义 Host 后续阶段可依赖的公共 request、snapshot、status、event
stream、error、context 与本地执行装配类型。它不实现 command path、
durable store、EventLog 写入、dispatch scheduler、policy provider 或
Engine 调用路径。`HostLocalExecutionOptions` 为 composition root 本地执行
装配保留构造期 tooling 输入字段，但 tooling 类型仍由 `dayu.host.tooling`
直接导出，不进入 `dayu.host.api.__all__`。
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
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
from dayu.host._public_validation import (
    require_non_empty as _require_non_empty,
)
from dayu.host._public_validation import (
    require_optional_non_empty as _require_optional_non_empty,
)
from dayu.host.tooling import HostToolingOptions as _HostToolingOptions


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
    ``SUCCEEDED``、``FAILED``、``CANCELLED``、``LOST`` 是终态。
    """

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

    def cancel(self, reason: str) -> None:
        """向 worker 发起 best-effort 取消。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises RuntimeError: 具体实现取消失败时可抛出运行时错误。
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
            self.business_object_id,
            field_name="OperationContext.business_object_id",
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
    - ``input``：Host 输入 envelope。
    - ``behavior``：queue 或 steer 行为。
    - ``target_run_id``：steer 目标 Run id；queue 时必须为 ``None``。
    """

    context: HostCallContext
    session_id: str
    client_request_id: str
    input: HostInput
    behavior: FollowupBehavior
    target_run_id: str | None

    def __post_init__(self) -> None:
        """校验 follow-up 请求字段与 target_run_id 前置条件。

        :returns: 无返回值。
        :raises ValueError: id 为空、steer 缺目标、queue 携带目标时抛出。
        """

        _require_non_empty(
            self.session_id, field_name="SubmitFollowupRequest.session_id"
        )
        _require_non_empty(
            self.client_request_id,
            field_name="SubmitFollowupRequest.client_request_id",
        )
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
    - ``current_cursor``：接受后的当前事件游标。
    - ``queued_run_id``：真实处于 queued 状态的 accepted Run id；其它情况为 ``None``。
    - ``target_run_id``：steer 目标 Run id；queue 时为 ``None``。
    """

    accepted_input_ref: str
    behavior: FollowupBehavior
    accepted_run_id: str
    accepted_run_status: RunStatus
    current_cursor: HostStreamCursor
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
            elif self.accepted_run_status == RunStatus.RUNNING:
                if self.queued_run_id is not None:
                    raise ValueError(
                        "FollowupSnapshot.queued_run_id must be None "
                        "for running queue result"
                    )
            else:
                raise ValueError(
                    "FollowupSnapshot.accepted_run_status must be queued "
                    "or running for queue"
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


__all__ = [
    "AttemptDispatchSnapshot",
    "AttemptStatus",
    "AuthorizationClaim",
    "CancelMode",
    "CancelRunRequest",
    "CancelSessionRunsRequest",
    "CloseSessionRequest",
    "CreateSessionRequest",
    "EnsureSessionRequest",
    "FollowupBehavior",
    "FollowupSnapshot",
    "HOST_EVENT_STREAM_DEFAULT_LIMIT",
    "HOST_EVENT_STREAM_MAX_LIMIT",
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
    "HostCommandFacet",
    "HostCommandHandleOptions",
    "HostLocalExecutionOptions",
    "HostEventClass",
    "HostEventStream",
    "HostEventView",
    "HostInput",
    "HostMetadataEntry",
    "HostPayloadRef",
    "HostStreamCursor",
    "LocalEngineWorker",
    "LocalEngineWorkerFactory",
    "LocalWorkerHandle",
    "OperationContext",
    "OutboxSummary",
    "PurgeSessionRequest",
    "PurgeSessionResult",
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
    "StartRunRequest",
    "SteerConflictDetail",
    "SubmitFollowupRequest",
    "TerminalResultSummary",
    "WaitAdapterKey",
    "WaitProviderStatusRef",
    "WaitResolutionSource",
]
