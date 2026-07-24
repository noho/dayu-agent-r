"""Product entrypoint 共享的 Agent runtime Service 边界。

本模块只编排 runtime assembly 输出与 Host public API / Protocol，不解析 CLI
参数，不读写 stdout / stderr，不安装 signal handler，也不导入 Engine 内部。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Never, Protocol, TypeAlias, assert_never

from dayu.contracts import JsonValue
from dayu.host.api import (
    CancelRunRequest,
    CancelMode,
    CreateSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostActivityCounts,
    HostActivityKind,
    HostActivitySeverity,
    HostActivityStatus,
    HostContextUsageView,
    ContextEstimateMethod,
    ContextPressureLevel,
    HostCallContext,
    HostContentDelta,
    HostEvent,
    HostFinalAnswerView,
    HostMetadataEntry,
    HostReasoningDelta,
    HostSessionEvent,
    HostSessionEventDeliveryDetail,
    HostSessionEventDeliveryReason,
    HostSessionEventIterator,
    HostTerminalStatus,
    HostToolCallDelta,
    HostTransientDelta,
    HostClosedError,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItem,
    ReadOutboxTerminalItemsRequest,
    SessionSnapshot,
    is_terminal_run_status,
)
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig
from dayu.runtime.location import RuntimeLocations, resolve_runtime_locations
from dayu.runtime.numeric import is_positive_finite_number
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    ScenePrepareRequest,
    SceneToolCatalog,
    prepare_scene,
)
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceDiscoveredTools,
    ServiceOpenHostAssemblyRequest,
    ServiceOpenHostAssemblyResult,
    ServiceRunOverrides,
    assemble_effective_tool_provider_configs,
    compose_open_host_options,
    compose_submit_followup_request_with_overrides,
    discover_service_tools,
)

DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS: Final[float] = 0.05
DEFAULT_ENTRYPOINT_STARTUP_PROMOTION_POLL_INTERVAL_SECONDS: Final[float] = 0.05
ENTRYPOINT_STARTUP_OUTBOX_LAGGED_MAX_ATTEMPTS: Final[int] = 3
ENTRYPOINT_STARTUP_PROMOTION_MAX_ATTEMPTS: Final[int] = 20
_OUTBOX_TERMINAL_READ_LIMIT: Final[int] = 50
_WATCHER_CLEANUP_ACTIVITY_DEDUPE_KEY: Final[str] = "entrypoint_watcher_cleanup_failed"
_WATCHER_CLEANUP_ACTIVITY_TITLE: Final[str] = "运行事件流清理失败"
_WATCHER_CLEANUP_ACTIVITY_SUMMARY: Final[str] = "已保留终态结果，但运行事件观察器清理失败。"


class EntrypointRuntimeError(RuntimeError):
    """entrypoint runtime Service helper 观察 Host 终态失败时抛出的错误。"""


RunAcceptedCallback = Callable[[str], None]
"""Host 接受 Run 后通知调用方 accepted_run_id 的回调类型。"""


class EntrypointActivityKind(StrEnum):
    """entrypoint activity 展示语义分类。

    成员表达 Service 传给 UI adapter 的安全展示类型，不等同于 Host
    EventLog ``event_class`` 或 ``event_type``。
    """

    RUN_LIFECYCLE = "run_lifecycle"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_BATCH = "tool_batch"
    TOOL_AWAITING = "tool_awaiting"
    CONTEXT_USAGE = "context_usage"
    CONTEXT_COMPACTION = "context_compaction"
    PROVIDER_DIAGNOSTIC = "provider_diagnostic"
    PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"
    WATCHER_DIAGNOSTIC = "watcher_diagnostic"


class EntrypointActivityStatus(StrEnum):
    """entrypoint activity 展示状态。

    成员只描述单条 activity 对调用方的展示进度，不替代 Host Run
    状态机或 terminal 结果。
    """

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING = "waiting"
    INFO = "info"


class EntrypointActivitySeverity(StrEnum):
    """entrypoint activity 展示严重级别。

    成员用于 UI adapter 选择展示强度，不表达 durable failure truth。
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EntrypointContextEstimateMethod(StrEnum):
    """entrypoint公开的context estimate方法。"""

    USAGE_ANCHORED = "usage_anchored"
    CONSERVATIVE_FALLBACK = "conservative_fallback"


class EntrypointContextPressureLevel(StrEnum):
    """entrypoint公开的context pressure等级。"""

    NORMAL = "normal"
    SOFT_THRESHOLD_EXCEEDED = "soft_threshold_exceeded"
    HARD_THRESHOLD_EXCEEDED = "hard_threshold_exceeded"


@dataclass(frozen=True, slots=True)
class EntrypointActivityCounts:
    """entrypoint activity 的固定计数字段。

    :param total: 总数量，必须是非负整数。
    :param completed: 已完成数量，必须是非负整数。
    :param failed: 失败数量，必须是非负整数。
    :param cancelled: 已取消数量，必须是非负整数。
    """

    total: int
    completed: int
    failed: int
    cancelled: int

    def __post_init__(self) -> None:
        """校验计数字段。

        :returns: ``None``。
        :raises TypeError: 任一字段不是严格整数时抛出。
        :raises ValueError: 任一字段小于零时抛出。
        """

        _require_non_negative_int(self.total, field_name="EntrypointActivityCounts.total")
        _require_non_negative_int(self.completed, field_name="EntrypointActivityCounts.completed")
        _require_non_negative_int(self.failed, field_name="EntrypointActivityCounts.failed")
        _require_non_negative_int(self.cancelled, field_name="EntrypointActivityCounts.cancelled")


@dataclass(frozen=True, slots=True)
class EntrypointContextUsage:
    """Service向UI adapter交付的context usage七字段DTO。

    :param predicted_input_tokens: Host canonical prediction。
    :param context_window_size: Host canonical context window。
    :param utilization_basis_points: Host canonical未clamp利用率基点。
    :param soft_threshold_tokens: Host canonical soft threshold。
    :param hard_threshold_tokens: Host canonical hard threshold。
    :param estimate_method: exhaustive mapped estimate method。
    :param pressure_level: exhaustive mapped pressure level。
    """

    predicted_input_tokens: int
    context_window_size: int
    utilization_basis_points: int
    soft_threshold_tokens: int
    hard_threshold_tokens: int
    estimate_method: EntrypointContextEstimateMethod
    pressure_level: EntrypointContextPressureLevel

    def __post_init__(self) -> None:
        """校验entrypoint context usage字段。

        :returns: ``None``。
        :raises TypeError: 数字或enum类型非法时抛出。
        :raises ValueError: token/window/threshold范围非法时抛出。
        """

        _require_non_negative_int(
            self.predicted_input_tokens,
            field_name="EntrypointContextUsage.predicted_input_tokens",
        )
        _require_positive_int(
            self.context_window_size,
            field_name="EntrypointContextUsage.context_window_size",
        )
        _require_non_negative_int(
            self.utilization_basis_points,
            field_name="EntrypointContextUsage.utilization_basis_points",
        )
        _require_positive_int(
            self.soft_threshold_tokens,
            field_name="EntrypointContextUsage.soft_threshold_tokens",
        )
        _require_positive_int(
            self.hard_threshold_tokens,
            field_name="EntrypointContextUsage.hard_threshold_tokens",
        )
        if self.soft_threshold_tokens >= self.hard_threshold_tokens:
            raise ValueError(
                "EntrypointContextUsage.soft_threshold_tokens must be less than "
                "hard_threshold_tokens"
            )
        if not isinstance(
            self.estimate_method,
            EntrypointContextEstimateMethod,
        ):
            raise TypeError(
                "EntrypointContextUsage.estimate_method must be "
                "EntrypointContextEstimateMethod"
            )
        if not isinstance(
            self.pressure_level,
            EntrypointContextPressureLevel,
        ):
            raise TypeError(
                "EntrypointContextUsage.pressure_level must be "
                "EntrypointContextPressureLevel"
            )


@dataclass(frozen=True, slots=True)
class EntrypointActivity:
    """entrypoint runtime 传给 UI adapter 的安全 activity。

    :param kind: activity 展示语义分类。
    :param status: activity 展示状态。
    :param run_id: 关联 Run id；不绑定 Run 的本地诊断为 ``None``。
    :param event_sequence: Host event sequence；本地诊断为 ``None``。
    :param dedupe_key: activity 去重键。
    :param title: 简短标题，必须非空。
    :param summary: 有界补充摘要；无摘要时为 ``None``。
    :param severity: 展示严重级别。
    :param tool_name: 稳定工具名；非工具 activity 为 ``None``。
    :param tool_display_name: Host-owned 工具展示名；缺失时为 ``None``。
    :param counts: 固定计数视图；无计数时为 ``None``。
    :param context_usage: Host canonical七字段逐项映射；仅context activity非空。
    """

    kind: EntrypointActivityKind
    status: EntrypointActivityStatus
    run_id: str | None
    event_sequence: int | None
    dedupe_key: str
    title: str
    summary: str | None
    severity: EntrypointActivitySeverity
    tool_name: str | None
    tool_display_name: str | None
    counts: EntrypointActivityCounts | None
    context_usage: EntrypointContextUsage | None = None

    def __post_init__(self) -> None:
        """校验 activity 字段。

        :returns: ``None``。
        :raises TypeError: enum、sequence 或 counts 字段类型非法时抛出。
        :raises ValueError: 文本字段为空或 sequence 小于零时抛出。
        """

        if not isinstance(self.kind, EntrypointActivityKind):
            raise TypeError("EntrypointActivity.kind must be EntrypointActivityKind")
        if not isinstance(self.status, EntrypointActivityStatus):
            raise TypeError("EntrypointActivity.status must be EntrypointActivityStatus")
        _require_optional_non_empty(self.run_id, field_name="EntrypointActivity.run_id")
        if self.event_sequence is not None:
            _require_non_negative_int(self.event_sequence, field_name="EntrypointActivity.event_sequence")
        _require_non_empty(self.dedupe_key, field_name="EntrypointActivity.dedupe_key")
        _require_non_empty(self.title, field_name="EntrypointActivity.title")
        _require_optional_non_empty(self.summary, field_name="EntrypointActivity.summary")
        if not isinstance(self.severity, EntrypointActivitySeverity):
            raise TypeError("EntrypointActivity.severity must be EntrypointActivitySeverity")
        _require_optional_non_empty(self.tool_name, field_name="EntrypointActivity.tool_name")
        _require_optional_non_empty(self.tool_display_name, field_name="EntrypointActivity.tool_display_name")
        if self.counts is not None and not isinstance(self.counts, EntrypointActivityCounts):
            raise TypeError("EntrypointActivity.counts must be EntrypointActivityCounts")
        if self.context_usage is not None and not isinstance(
            self.context_usage,
            EntrypointContextUsage,
        ):
            raise TypeError(
                "EntrypointActivity.context_usage must be EntrypointContextUsage"
            )
        if self.kind is EntrypointActivityKind.CONTEXT_USAGE:
            if (
                self.context_usage is None
                or self.tool_name is not None
                or self.tool_display_name is not None
                or self.counts is not None
            ):
                raise ValueError(
                    "entrypoint context usage activity fields are inconsistent"
                )
        elif self.context_usage is not None:
            raise ValueError(
                "non-context entrypoint activity must not include context_usage"
            )


EntrypointActivityCallback = Callable[[EntrypointActivity], None]
"""entrypoint runtime activity 通知回调类型。"""


@dataclass(frozen=True, slots=True)
class EntrypointThinking:
    """entrypoint runtime 传给 UI adapter 的 running thinking 增量。

    :param run_id: 关联 Run id。
    :param runtime_id: 当前 Host runtime 的 opaque identity。
    :param runtime_sequence: 当前 runtime 的瞬态发布序列。
    :param dedupe_key: thinking 增量去重键。
    :param text_delta: 本次 thinking 增量文本。
    """

    run_id: str
    runtime_id: str
    runtime_sequence: int
    dedupe_key: str
    text_delta: str

    def __post_init__(self) -> None:
        """校验 thinking 增量字段。

        :returns: ``None``。
        :raises TypeError: text delta 不是字符串时抛出。
        :raises ValueError: identity 为空或 sequence 非正数时抛出。
        """

        _require_non_empty(self.run_id, field_name="EntrypointThinking.run_id")
        _require_non_empty(
            self.runtime_id,
            field_name="EntrypointThinking.runtime_id",
        )
        _require_positive_int(
            self.runtime_sequence,
            field_name="EntrypointThinking.runtime_sequence",
        )
        _require_non_empty(self.dedupe_key, field_name="EntrypointThinking.dedupe_key")
        if not isinstance(self.text_delta, str):
            raise TypeError("EntrypointThinking.text_delta must be str")


EntrypointThinkingCallback = Callable[[EntrypointThinking], None]
"""entrypoint runtime thinking 通知回调类型。"""


class EntrypointCallbackExecutionPort(Protocol):
    """Service 调用 activity/thinking 同步回调的异步执行端口。

    端口只表达两类精确 invocation。执行域、串行化和线程生命周期由 UI
    adapter 拥有；Service 不持有 executor，也不把 Host event 交给端口。
    """

    async def invoke_activity(
        self,
        callback: EntrypointActivityCallback,
        activity: EntrypointActivity,
    ) -> None:
        """在调用方执行域中调用 activity callback。

        :param callback: 待调用的同步 activity callback。
        :param activity: Service 已投影的 activity DTO。
        :returns: ``None``。
        :raises Exception: callback 或执行域调度失败时透传原异常。
        """

        ...

    async def invoke_thinking(
        self,
        callback: EntrypointThinkingCallback,
        thinking: EntrypointThinking,
    ) -> None:
        """在调用方执行域中调用 thinking callback。

        :param callback: 待调用的同步 thinking callback。
        :param thinking: Service 已投影的 thinking DTO。
        :returns: ``None``。
        :raises Exception: callback 或执行域调度失败时透传原异常。
        """

        ...


class EntrypointTerminalSource(StrEnum):
    """entrypoint runtime 观察到 Run 终态的来源。

    成员：

    - ``LIVE_EVENT``：来自 submit 前已 attach 的 live HostEvent watcher。
    - ``OUTBOX_READ``：来自 Host public outbox terminal read 兜底。
    """

    LIVE_EVENT = "live_event"
    OUTBOX_READ = "outbox_read"


@dataclass(frozen=True, slots=True)
class EntrypointRuntimeRequest:
    """准备 product entrypoint Agent runtime 的请求。

    :param workspace_root: 当前 workspace 根目录。
    :param package_config_root: 包内默认配置根目录。
    :param explicit_config_dir: 调用方显式指定的配置覆盖目录；``None`` 表示
        使用默认 ``<workspace_root>/config`` 探测行为。
    :param scene_id: 本次 entrypoint 使用的 scene id。
    :param context_slot_values: 传给 ScenePrepare 的业务上下文槽位值。
    :param assembly_overrides: Service assembly 显式 override。
    :param env: env / secret 映射。
    """

    workspace_root: Path
    package_config_root: Path
    explicit_config_dir: Path | None
    scene_id: str
    context_slot_values: Mapping[str, JsonValue]
    assembly_overrides: ServiceAssemblyOverrides
    env: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class EntrypointRuntimeResult:
    """product entrypoint Agent runtime 准备结果。

    :param locations: runtime 位置解析结果。
    :param runtime_config: ConfigLoader 输出的 typed runtime config。
    :param scene_inputs: ScenePrepare 输出。
    :param discovered_tools: Service 工具发现结果。
    :param host_assembly: Host opener assembly 结果。
    """

    locations: RuntimeLocations
    runtime_config: RuntimeConfig
    scene_inputs: PreparedSceneInputs
    discovered_tools: ServiceDiscoveredTools
    host_assembly: ServiceOpenHostAssemblyResult


@dataclass(frozen=True, slots=True)
class EntrypointTurnRequest:
    """提交 entrypoint 单轮 Agent 输入的请求。

    :param context: Host 调用上下文。
    :param session_id: 目标 Session id。
    :param client_request_id: 本轮 submit 幂等请求 id。
    :param user_prompt: 本轮用户输入。
    :param tool_names: 本轮工具选择；``None`` 表示全量，空集合表示禁用。
    :param behavior: Host followup 行为。
    :param target_run_id: steer 目标 Run id；queue 时为 ``None``。
    :param run_overrides: 本轮可映射的运行时 override。
    """

    context: HostCallContext
    session_id: str
    client_request_id: str
    user_prompt: str
    tool_names: frozenset[str] | None
    behavior: FollowupBehavior
    target_run_id: str | None
    run_overrides: ServiceRunOverrides


@dataclass(frozen=True, slots=True)
class EntrypointCancelRequest:
    """取消 entrypoint Run 的请求。

    :param context: Host 调用上下文。
    :param run_id: 待取消 Run id。
    :param client_request_id: cancel 幂等请求 id；同一 Run 的重复取消应复用。
    :param reason: 取消原因。
    :param mode: Host public 取消模式。
    """

    context: HostCallContext
    run_id: str
    client_request_id: str
    reason: str
    mode: CancelMode


@dataclass(frozen=True, slots=True)
class EntrypointRunTerminalResult:
    """entrypoint Run 终态观察结果。

    :param source: terminal payload 来源。
    :param session_id: 终态所属 Session id。
    :param run_id: 终态所属 Run id。
    :param terminal_event_id: Host terminal event id。
    :param event_sequence: Host terminal event sequence。
    :param terminal_status: terminal 状态。
    :param dedupe_key: Host public 去重键。
    :param final_answer: 成功终态的最终回答；其它终态为 ``None``。
    :param error_message: 失败终态展示消息。
    :param cancel_reason: 取消终态原因。
    :param watcher_failure_message: 观察器诊断摘要。精确 delivery interruption
        只保留 typed Host error identity，不把异常文本投影到 terminal，因此
        当前固定为 ``None``。
    """

    source: EntrypointTerminalSource
    session_id: str
    run_id: str
    terminal_event_id: str
    event_sequence: int
    terminal_status: HostTerminalStatus
    dedupe_key: str
    final_answer: HostFinalAnswerView | None
    error_message: str | None
    cancel_reason: str | None
    watcher_failure_message: str | None


@dataclass(frozen=True, slots=True)
class EntrypointStartupReconnectRequest:
    """interactive 已有 Session startup reconnect 请求。

    :param context: Host 调用上下文，用于表达本次 startup 的责任链。
    :param session_id: 已选择的 Host Session id。
    :param terminal_cursor: CLI 已成功展示的 terminal 水位。
    :param seen_terminal_event_ids: CLI 已成功展示的 terminal event id 窗口。
    :param poll_interval_seconds: active Run terminal 观察轮询间隔。
    :param outbox_lagged_max_attempts: Outbox projection 落后时的最大重试次数。
    :param promotion_poll_interval_seconds: queued Run promotion 轮询间隔。
    :param promotion_max_attempts: queued-only promotion 最大等待次数。
    """

    context: HostCallContext
    session_id: str
    terminal_cursor: OutboxTerminalCursor
    seen_terminal_event_ids: frozenset[str]
    poll_interval_seconds: float
    outbox_lagged_max_attempts: int
    promotion_poll_interval_seconds: float
    promotion_max_attempts: int

    def __post_init__(self) -> None:
        """校验 startup reconnect 请求。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字符串为空、轮询参数或 seen ids 非法时抛出。
        """

        if not isinstance(self.context, HostCallContext):
            raise TypeError("EntrypointStartupReconnectRequest.context must be HostCallContext")
        _require_non_empty(self.session_id, field_name="EntrypointStartupReconnectRequest.session_id")
        if not isinstance(self.terminal_cursor, OutboxTerminalCursor):
            raise TypeError("EntrypointStartupReconnectRequest.terminal_cursor must be OutboxTerminalCursor")
        if not isinstance(self.seen_terminal_event_ids, frozenset):
            raise TypeError("EntrypointStartupReconnectRequest.seen_terminal_event_ids must be frozenset")
        for terminal_event_id in self.seen_terminal_event_ids:
            _require_non_empty(
                terminal_event_id,
                field_name="EntrypointStartupReconnectRequest.seen_terminal_event_ids",
            )
        _require_positive_poll_interval(self.poll_interval_seconds)
        _require_non_negative_int(
            self.outbox_lagged_max_attempts,
            field_name="EntrypointStartupReconnectRequest.outbox_lagged_max_attempts",
        )
        _require_positive_poll_interval(self.promotion_poll_interval_seconds)
        _require_non_negative_int(
            self.promotion_max_attempts,
            field_name="EntrypointStartupReconnectRequest.promotion_max_attempts",
        )


@dataclass(frozen=True, slots=True)
class EntrypointStartupReconnectResult:
    """interactive startup reconnect 结果。

    :param terminal_results: CLI 进入输入态前必须先展示的 terminal 结果。
    :param next_terminal_cursor: 本次 startup 已观察到的 terminal 水位。
    :param seen_terminal_event_ids: 本次 startup 合并后的 terminal event id 集合。
    """

    terminal_results: tuple[EntrypointRunTerminalResult, ...]
    next_terminal_cursor: OutboxTerminalCursor
    seen_terminal_event_ids: frozenset[str]


class _ObservationPhase(StrEnum):
    """Service watcher runtime 的封闭生命周期阶段。"""

    ATTACHED_UNBOUND = "attached_unbound"
    CONSUMING = "consuming"
    RESULT_READY = "result_ready"
    STOPPING = "stopping"
    CLOSED = "closed"


class _CallbackKind(StrEnum):
    """callback failure 所属的封闭回调类别。"""

    ACTIVITY = "activity"
    THINKING = "thinking"


@dataclass(frozen=True, slots=True)
class _TargetTerminal:
    """sole consumer 观察到目标 Run 终态。"""

    target_generation: int
    result: EntrypointRunTerminalResult


@dataclass(frozen=True, slots=True)
class _DeliveryInterrupted:
    """sole consumer 观察到 typed delivery interruption。"""

    target_generation: int
    error: HostApiError


@dataclass(frozen=True, slots=True)
class _IteratorEnded:
    """sole consumer 在目标终态前观察到 iterator EOF。"""

    target_generation: int


@dataclass(frozen=True, slots=True)
class _CallbackFailed:
    """sole consumer 调用 UI callback 时观察到原始失败。"""

    target_generation: int
    callback_kind: _CallbackKind
    error: Exception


@dataclass(frozen=True, slots=True)
class _IteratorFailed:
    """sole consumer 观察到非 delivery iterator failure。"""

    target_generation: int
    error: Exception


_ServiceObservationResult: TypeAlias = (
    _TargetTerminal | _DeliveryInterrupted | _IteratorEnded | _CallbackFailed | _IteratorFailed
)


class _ServiceObservationState:
    """唯一 generation binding 与 capacity-one observation slot owner。"""

    _phase: _ObservationPhase
    _target_generation: int
    _target_run_id: str | None
    _result: _ServiceObservationResult | None
    _state_changed: asyncio.Event
    _result_ready: asyncio.Event
    _stop_requested: bool

    def __init__(self) -> None:
        """创建已 attach、尚未绑定 target 的状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._phase = _ObservationPhase.ATTACHED_UNBOUND
        self._target_generation = 0
        self._target_run_id = None
        self._result = None
        self._state_changed = asyncio.Event()
        self._result_ready = asyncio.Event()
        self._stop_requested = False

    @property
    def result(self) -> _ServiceObservationResult | None:
        """返回 capacity-one slot 当前成员。

        :returns: 当前 result；slot 为空时返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self._result

    def bind(self, target_run_id: str) -> int:
        """绑定唯一 target 并开始下一 generation。

        :param target_run_id: 当前唯一目标 Run id。
        :returns: 新的单调正整数 generation。
        :raises RuntimeError: 当前状态不可绑定时抛出。
        """

        if self._phase is not _ObservationPhase.ATTACHED_UNBOUND:
            raise RuntimeError("observation target can only bind while unbound")
        if self._stop_requested or self._result is not None:
            raise RuntimeError("observation target cannot bind after stop or result")
        _require_non_empty(target_run_id, field_name="target_run_id")
        self._target_generation += 1
        self._target_run_id = target_run_id
        self._phase = _ObservationPhase.CONSUMING
        self._state_changed.set()
        return self._target_generation

    async def wait_for_binding(self) -> tuple[int, str] | None:
        """等待可消费 target binding 或 stop。

        :returns: ``(generation, run_id)``；stop 已赢得仲裁时返回 ``None``。
        :raises asyncio.CancelledError: consumer task 被取消时透传。
        """

        while True:
            if self._stop_requested:
                return None
            if self._phase is _ObservationPhase.CONSUMING:
                target_run_id = self._target_run_id
                if target_run_id is None:
                    raise RuntimeError("consuming observation missing target_run_id")
                return self._target_generation, target_run_id
            self._state_changed.clear()
            await self._state_changed.wait()

    def try_commit(
        self,
        result: _ServiceObservationResult,
        *,
        target_run_id: str,
    ) -> bool:
        """由 sole consumer 尝试 first-commit 唯一 slot。

        :param result: exact-five observation member。
        :param target_run_id: consumer 读取事件时快照的 target Run id。
        :returns: 本 generation 成功 first-commit 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        if self._stop_requested or self._phase is not _ObservationPhase.CONSUMING:
            return False
        if self._result is not None:
            return False
        if result.target_generation != self._target_generation:
            return False
        if target_run_id != self._target_run_id:
            return False
        self._result = result
        self._phase = _ObservationPhase.RESULT_READY
        self._result_ready.set()
        self._state_changed.set()
        return True

    async def wait_for_result(self) -> _ServiceObservationResult:
        """等待并返回当前 capacity-one slot member。

        :returns: first-committed exact-five member。
        :raises asyncio.CancelledError: caller 被取消时透传。
        :raises RuntimeError: signal 与 slot invariant 不一致时抛出。
        """

        await self._result_ready.wait()
        result = self._result
        if result is None:
            raise RuntimeError("observation result signal set without result")
        return result

    def ack_target_terminal(self, target_generation: int) -> _TargetTerminal:
        """消费并清除同 generation 的 terminal slot 以便 startup 复用。

        :param target_generation: coordinator 已消费的 generation。
        :returns: 已消费的 terminal member。
        :raises RuntimeError: slot 不是目标 generation terminal 时抛出。
        """

        result = self._result
        if not isinstance(result, _TargetTerminal):
            raise RuntimeError("only target terminal can be acknowledged")
        if result.target_generation != target_generation:
            raise RuntimeError("target terminal generation does not match")
        self._result = None
        self._target_run_id = None
        self._phase = _ObservationPhase.ATTACHED_UNBOUND
        self._result_ready.clear()
        self._state_changed.set()
        return result

    async def wait_for_rebind_or_stop(self, target_generation: int) -> None:
        """在 terminal commit 后暂停，直到 ack/rebind 或 stop。

        :param target_generation: 已提交 terminal 的 generation。
        :returns: ``None``。
        :raises asyncio.CancelledError: consumer task 被取消时透传。
        """

        while True:
            if self._stop_requested:
                return
            if self._phase is _ObservationPhase.CONSUMING and self._target_generation > target_generation:
                return
            self._state_changed.clear()
            await self._state_changed.wait()

    def request_stop(self) -> None:
        """让 stop 在空 slot 上赢得仲裁并拒绝后续 late commit。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._phase is _ObservationPhase.CLOSED:
            return
        self._stop_requested = True
        self._phase = _ObservationPhase.STOPPING
        self._state_changed.set()

    def mark_closed(self) -> None:
        """标记 watcher runtime 已完成唯一 cleanup。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._stop_requested = True
        self._phase = _ObservationPhase.CLOSED
        self._state_changed.set()


@dataclass(slots=True)
class _WatchAndWaitRuntime:
    """绑定 public iterator、sole consumer 与唯一 observation slot。"""

    watcher: HostSessionEventIterator
    state: _ServiceObservationState
    consumer_task: asyncio.Task[None]
    closed: bool = False


@dataclass(slots=True)
class _TerminalObservationState:
    """单次 terminal observation 的本地去重与 outbox 游标状态。"""

    last_observed_event_sequence: int
    seen_terminal_event_ids: set[str]
    seen_dedupe_keys: set[str]
    seen_activity_dedupe_keys: set[str]
    seen_thinking_dedupe_keys: set[str]
    outbox_cursor: OutboxTerminalCursor | None


async def prepare_entrypoint_runtime(
    request: EntrypointRuntimeRequest,
) -> EntrypointRuntimeResult:
    """准备 entrypoint 共享 Agent runtime assembly。

    :param request: entrypoint runtime 准备请求。
    :returns: runtime locations、config、scene、tools 与 Host opener assembly。
    :raises Exception: location、config、scene、tool discovery 或 Host assembly
        失败时向上抛出对应结构化错误。
    """

    locations = resolve_runtime_locations(
        workspace_root=request.workspace_root,
        package_config_root=request.package_config_root,
        explicit_config_overlay_dir=request.explicit_config_dir,
    )
    runtime_config = ConfigLoader(package_config_dir=request.package_config_root).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = discover_service_tools(
        assemble_effective_tool_provider_configs(
            tuple(runtime_config.tool_discovery.providers.values()),
            workspace_root=request.workspace_root,
            fins_workspace_root_override=None,
        )
    )
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=request.scene_id,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values=_string_context_slot_values(request.context_slot_values),
            available_tools=SceneToolCatalog.from_tool_bundle(discovered_tools.tool_bundle),
        )
    )
    host_assembly = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=request.workspace_root,
            config=runtime_config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=request.assembly_overrides,
            env=request.env,
        )
    )
    return EntrypointRuntimeResult(
        locations=locations,
        runtime_config=runtime_config,
        scene_inputs=scene_inputs,
        discovered_tools=discovered_tools,
        host_assembly=host_assembly,
    )


def _string_context_slot_values(values: Mapping[str, JsonValue]) -> dict[str, str]:
    """把 entrypoint context slot 值校验并收敛为 ScenePrepare 字符串输入。

    :param values: entrypoint request 提供的 JSON context slot 值。
    :returns: 只包含字符串值的 context slot 映射。
    :raises ValueError: 任一 slot 值不是字符串时抛出。
    """

    result: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(value, str):
            raise ValueError(f"context_slot_values.{key} must be string")
        result[key] = value
    return result


async def ensure_or_create_entrypoint_session(
    host: Host,
    *,
    create_new: bool,
    bind_slot: bool,
    scope: str | None,
    slot_key: str | None,
    metadata: tuple[HostMetadataEntry, ...],
    create_context: HostCallContext | None = None,
    create_client_request_id: str | None = None,
) -> SessionSnapshot:
    """确保或创建 entrypoint 使用的 Host Session。

    :param host: Host public Protocol handle。
    :param create_new: 为 ``True`` 时调用 ``create_session``，否则调用
        ``ensure_session``。
    :param bind_slot: 创建新 Session 时是否绑定 slot。
    :param scope: slot scope；ensure 或 bind_slot 创建时必填。
    :param slot_key: slot key；ensure 或 bind_slot 创建时必填。
    :param metadata: Host 中性 metadata。
    :param create_context: create_session Host 调用上下文。
    :param create_client_request_id: create_session 幂等请求 id。
    :returns: Session snapshot。
    :raises ValueError: 请求字段组合不足以构造 Host public request 时抛出。
    :raises HostApiError: Host public API 调用失败时由 Host 抛出。
    """

    if create_new:
        if create_context is None:
            raise ValueError("create_context is required when create_new is True")
        if create_client_request_id is None:
            raise ValueError("create_client_request_id is required when create_new is True")
        return await host.create_session(
            CreateSessionRequest(
                context=create_context,
                client_request_id=create_client_request_id,
                bind_slot=bind_slot,
                scope=scope,
                slot_key=slot_key,
                metadata=metadata,
            )
        )
    if scope is None or slot_key is None:
        raise ValueError("scope and slot_key are required for ensure_session")
    return await host.ensure_session(EnsureSessionRequest(scope=scope, slot_key=slot_key, metadata=metadata))


async def submit_entrypoint_turn_and_wait(
    host: Host,
    *,
    request: EntrypointTurnRequest,
    scene_inputs: PreparedSceneInputs,
    host_assembly: ServiceOpenHostAssemblyResult,
    on_run_accepted: RunAcceptedCallback | None = None,
    on_activity: EntrypointActivityCallback | None = None,
    on_thinking: EntrypointThinkingCallback | None = None,
    callback_execution_port: EntrypointCallbackExecutionPort | None = None,
    poll_interval_seconds: float = DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> EntrypointRunTerminalResult:
    """提交 entrypoint 单轮输入并等待同一 Run 终态。

    :param host: Host public Protocol handle。
    :param request: 单轮 entrypoint turn 请求。
    :param scene_inputs: ScenePrepare 输出。
    :param host_assembly: Host opener assembly 结果。
    :param on_run_accepted: Host 接受本轮 Run 后的可选通知回调；用于 UI
        adapter 在等待终态期间发起 typed cancel。
    :param on_activity: 可选 activity 回调；只接收 Host public activity 投影和
        Service 本地有界诊断。
    :param on_thinking: 可选 thinking 回调；只接收 Host public thinking 增量。
    :param callback_execution_port: activity/thinking callback 的异步执行端口；
        存在任一 callback 时必填，无 callback 时必须为 ``None``。
    :param poll_interval_seconds: watcher 暂无 terminal 时的 public read 轮询间隔。
    :param sleep: 可注入 sleep coroutine，便于测试。
    :returns: Run terminal 观察结果。
    :raises EntrypointRuntimeError: Host outbox projection 失败或终态投影缺失时抛出。
    :raises HostApiError: Host public API 调用失败时由 Host 抛出。

    本 helper 不持有内部 timeout。调用方必须通过外层 task cancellation、
    ``asyncio.wait_for(...)`` 或显式 cancel 请求控制等待生命周期。
    """

    _require_positive_poll_interval(poll_interval_seconds)
    _validate_callback_execution_port(
        on_activity=on_activity,
        on_thinking=on_thinking,
        callback_execution_port=callback_execution_port,
    )
    state = _new_terminal_observation_state()
    runtime = await _create_watch_and_wait_runtime(
        host,
        request.session_id,
        observation_state=state,
        on_activity=on_activity,
        on_thinking=on_thinking,
        callback_execution_port=callback_execution_port,
    )
    try:
        submit_request = compose_submit_followup_request_with_overrides(
            context=request.context,
            session_id=request.session_id,
            client_request_id=request.client_request_id,
            scene_inputs=scene_inputs,
            user_prompt=request.user_prompt,
            tool_names=request.tool_names,
            behavior=request.behavior,
            target_run_id=request.target_run_id,
            host_assembly=host_assembly,
            run_overrides=request.run_overrides,
        )
        followup = await host.submit_followup(request.session_id, submit_request)
        runtime.state.bind(followup.accepted_run_id)
        if on_run_accepted is not None:
            on_run_accepted(followup.accepted_run_id)
    except BaseException as error:
        cleanup_error = await _close_watch_and_wait_runtime(runtime)
        _raise_primary_with_cleanup(error, cleanup_error)
    return await _wait_for_single_target_result(
        runtime,
        host=host,
        session_id=request.session_id,
        run_id=followup.accepted_run_id,
        state=state,
        on_activity=on_activity,
        callback_execution_port=callback_execution_port,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
    )


async def cancel_entrypoint_run_and_wait(
    host: Host,
    *,
    request: EntrypointCancelRequest,
    poll_interval_seconds: float = DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> EntrypointRunTerminalResult:
    """取消 entrypoint Run 并等待同一 Run 终态。

    :param host: Host public Protocol handle。
    :param request: entrypoint cancel 请求。
    :param poll_interval_seconds: durable recovery 的 public read 轮询间隔。
    :param sleep: 可注入 sleep coroutine，便于测试。
    :returns: Run terminal 观察结果。
    :raises EntrypointRuntimeError: iterator、cleanup、Outbox projection 或终态
        投影失败时抛出。
    :raises HostApiError: Host public API 调用失败时由 Host 抛出。
    :raises HostClosedError: Host public iterator 失败时原样透传。
    """

    _require_positive_poll_interval(poll_interval_seconds)
    run_snapshot = await host.get_run(request.run_id)
    state = _new_terminal_observation_state()
    if is_terminal_run_status(run_snapshot.status):
        return await _wait_for_durable_terminal(
            host,
            session_id=run_snapshot.session_id,
            run_id=request.run_id,
            state=state,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
        )
    runtime = await _create_watch_and_wait_runtime(
        host,
        run_snapshot.session_id,
        observation_state=state,
        on_activity=None,
        on_thinking=None,
        callback_execution_port=None,
    )
    runtime.state.bind(request.run_id)
    try:
        await host.cancel_run(
            request.run_id,
            CancelRunRequest(
                context=request.context,
                client_request_id=request.client_request_id,
                reason=request.reason,
                mode=request.mode,
            ),
        )
    except asyncio.CancelledError as error:
        cleanup_error = await _close_watch_and_wait_runtime(runtime)
        _raise_primary_with_cleanup(error, cleanup_error)
    except HostApiError as error:
        latest_run_snapshot = await host.get_run(request.run_id)
        if not is_terminal_run_status(latest_run_snapshot.status):
            cleanup_error = await _close_watch_and_wait_runtime(runtime)
            _raise_primary_with_cleanup(error, cleanup_error)
        ready_result = runtime.state.result
        if ready_result is not None:
            return await _finish_observation_result(
                ready_result,
                runtime=runtime,
                host=host,
                session_id=run_snapshot.session_id,
                run_id=request.run_id,
                state=state,
                on_activity=None,
                callback_execution_port=None,
                poll_interval_seconds=poll_interval_seconds,
                sleep=sleep,
            )
        cleanup_error = await _close_watch_and_wait_runtime(runtime)
        try:
            recovered = await _wait_for_durable_terminal(
                host,
                session_id=run_snapshot.session_id,
                run_id=request.run_id,
                state=state,
                poll_interval_seconds=poll_interval_seconds,
                sleep=sleep,
            )
        except BaseException as recovery_error:
            _raise_primary_with_cleanup(recovery_error, cleanup_error)
        return recovered
    return await _wait_for_single_target_result(
        runtime,
        host=host,
        session_id=run_snapshot.session_id,
        run_id=request.run_id,
        state=state,
        on_activity=None,
        callback_execution_port=None,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
    )


async def startup_reconnect_entrypoint_session(
    host: Host,
    *,
    request: EntrypointStartupReconnectRequest,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> EntrypointStartupReconnectResult:
    """为 interactive 已有 Session 执行 watcher-first startup reconnect。

    :param host: Host public Protocol handle。
    :param request: startup reconnect 请求。
    :param sleep: 可注入 sleep coroutine，便于测试。
    :returns: startup 阶段需要 CLI 展示的 terminal 结果与新 cursor。
    :raises EntrypointRuntimeError: Outbox projection 失败、LAGGED 重试耗尽或
        queued-only promotion 等待耗尽时抛出。
    :raises HostApiError: Host public API 调用失败时由 Host 抛出。
    """

    state = _new_terminal_observation_state(
        terminal_cursor=request.terminal_cursor,
        seen_terminal_event_ids=request.seen_terminal_event_ids,
    )
    runtime = await _create_watch_and_wait_runtime(
        host,
        request.session_id,
        observation_state=state,
        on_activity=None,
        on_thinking=None,
        callback_execution_port=None,
    )
    terminal_results: list[EntrypointRunTerminalResult] = []
    degraded = False
    cleanup_error: BaseException | None = None
    try:
        terminal_results.extend(
            await _read_session_outbox_terminal_backfill(
                host,
                session_id=request.session_id,
                state=state,
                outbox_lagged_max_attempts=request.outbox_lagged_max_attempts,
                poll_interval_seconds=request.poll_interval_seconds,
                sleep=sleep,
            )
        )
        while True:
            snapshot = await host.get_session(request.session_id)
            if snapshot.active_run_id is not None:
                if degraded:
                    terminal_results.append(
                        await _wait_for_durable_terminal(
                            host,
                            session_id=request.session_id,
                            run_id=snapshot.active_run_id,
                            state=state,
                            poll_interval_seconds=request.poll_interval_seconds,
                            sleep=sleep,
                        )
                    )
                    continue
                generation = runtime.state.bind(snapshot.active_run_id)
                result = await runtime.state.wait_for_result()
                if isinstance(result, _TargetTerminal):
                    terminal_results.append(runtime.state.ack_target_terminal(generation).result)
                    continue
                cleanup_error = await _close_watch_and_wait_runtime(runtime)
                if isinstance(result, _DeliveryInterrupted):
                    degraded = True
                    try:
                        terminal_results.append(
                            await _wait_for_durable_terminal(
                                host,
                                session_id=request.session_id,
                                run_id=snapshot.active_run_id,
                                state=state,
                                poll_interval_seconds=request.poll_interval_seconds,
                                sleep=sleep,
                            )
                        )
                    except BaseException as recovery_error:
                        _raise_delivery_recovery_failure(
                            recovery_error,
                            delivery_error=result.error,
                            cleanup_error=cleanup_error,
                        )
                    continue
                _raise_observation_failure(result, cleanup_error=cleanup_error)
            if snapshot.queued_run_ids:
                promoted = await _wait_for_startup_promotion(
                    host,
                    session_id=request.session_id,
                    promotion_max_attempts=request.promotion_max_attempts,
                    promotion_poll_interval_seconds=(request.promotion_poll_interval_seconds),
                    sleep=sleep,
                )
                if promoted.active_run_id is None:
                    raise EntrypointRuntimeError(
                        "Session 仍有未开始的 queued Run，未进入输入态: "
                        f"session_id={request.session_id}, "
                        f"queued_run_count={len(promoted.queued_run_ids)}"
                    )
                continue
            tail_results = await _read_session_outbox_terminal_backfill(
                host,
                session_id=request.session_id,
                state=state,
                outbox_lagged_max_attempts=request.outbox_lagged_max_attempts,
                poll_interval_seconds=request.poll_interval_seconds,
                sleep=sleep,
            )
            terminal_results.extend(tail_results)
            if tail_results:
                continue
            break
    except BaseException as error:
        if not runtime.closed:
            cleanup_error = await _close_watch_and_wait_runtime(runtime)
        _raise_primary_with_cleanup(error, cleanup_error)
    if not runtime.closed:
        cleanup_error = await _close_watch_and_wait_runtime(runtime)
    if cleanup_error is not None and not terminal_results:
        _raise_cleanup_failure(cleanup_error)
    return EntrypointStartupReconnectResult(
        terminal_results=tuple(terminal_results),
        next_terminal_cursor=OutboxTerminalCursor(event_sequence=state.last_observed_event_sequence),
        seen_terminal_event_ids=frozenset(state.seen_terminal_event_ids),
    )


async def _wait_for_startup_promotion(
    host: Host,
    *,
    session_id: str,
    promotion_max_attempts: int,
    promotion_poll_interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
) -> SessionSnapshot:
    """等待 queued-only Session promotion 出 active Run。

    :param host: Host public Protocol handle。
    :param session_id: 目标 Session id。
    :param promotion_max_attempts: 最大轮询次数。
    :param promotion_poll_interval_seconds: 每次轮询间隔。
    :param sleep: 可注入 sleep coroutine。
    :returns: 最新 Session snapshot。
    :raises EntrypointRuntimeError: 重试耗尽仍没有 active Run 时抛出。
    """

    latest = await host.get_session(session_id)
    for _attempt in range(promotion_max_attempts):
        if latest.active_run_id is not None or not latest.queued_run_ids:
            return latest
        await sleep(promotion_poll_interval_seconds)
        latest = await host.get_session(session_id)
    if latest.active_run_id is not None or not latest.queued_run_ids:
        return latest
    raise EntrypointRuntimeError(
        "Session 仍有未开始的 queued Run，未进入输入态: "
        f"session_id={session_id}, queued_run_count={len(latest.queued_run_ids)}"
    )


def _validate_callback_execution_port(
    *,
    on_activity: EntrypointActivityCallback | None,
    on_thinking: EntrypointThinkingCallback | None,
    callback_execution_port: EntrypointCallbackExecutionPort | None,
) -> None:
    """校验 callback 与 execution port 的精确组合。

    :param on_activity: 可选 activity callback。
    :param on_thinking: 可选 thinking callback。
    :param callback_execution_port: 可选异步执行端口。
    :returns: ``None``。
    :raises ValueError: callback 与执行端口组合不满足 owner contract 时抛出。
    """

    callbacks_present = on_activity is not None or on_thinking is not None
    if callbacks_present and callback_execution_port is None:
        raise ValueError("callback_execution_port is required when callbacks are set")
    if not callbacks_present and callback_execution_port is not None:
        raise ValueError("callback_execution_port requires an activity or thinking callback")


async def _attach_watcher(
    host: Host,
    session_id: str,
) -> HostSessionEventIterator:
    """在 Host mutating command 前 attach public live watcher。

    :param host: Host public Protocol handle。
    :param session_id: 目标 Session id。
    :returns: 可关闭 HostSessionEvent iterator。
    :raises HostApiError: Host watch attach 失败时由 Host 抛出。
    :raises HostClosedError: Host 已关闭时由 Host 抛出。
    """

    return await host.watch_session_events(session_id)


async def _create_watch_and_wait_runtime(
    host: Host,
    session_id: str,
    *,
    observation_state: _TerminalObservationState,
    on_activity: EntrypointActivityCallback | None,
    on_thinking: EntrypointThinkingCallback | None,
    callback_execution_port: EntrypointCallbackExecutionPort | None,
) -> _WatchAndWaitRuntime:
    """attach public iterator 并创建唯一 sole-consumer runtime。

    :param host: Host public Protocol handle。
    :param session_id: 目标 Session 标识。
    :param observation_state: live/outbox 共用的 terminal identity 状态。
    :param on_activity: 可选 activity callback。
    :param on_thinking: 可选 thinking callback。
    :param callback_execution_port: callback 的异步执行端口。
    :returns: public iterator、sole consumer 与 capacity-one slot runtime。
    :raises HostApiError: Host watch attach 失败时由 Host 抛出。
    :raises RuntimeError: sole consumer task 创建失败时透传。
    """

    watcher = await _attach_watcher(host, session_id)
    state = _ServiceObservationState()
    consumer_coroutine = _consume_host_events(
        watcher,
        runtime_state=state,
        observation_state=observation_state,
        on_activity=on_activity,
        on_thinking=on_thinking,
        callback_execution_port=callback_execution_port,
    )
    try:
        consumer_task = asyncio.create_task(consumer_coroutine)
    except BaseException as error:
        consumer_coroutine.close()
        cleanup_error: BaseException | None = None
        try:
            await watcher.aclose()
        except BaseException as close_error:
            cleanup_error = close_error
        _raise_primary_with_cleanup(error, cleanup_error)
    return _WatchAndWaitRuntime(
        watcher=watcher,
        state=state,
        consumer_task=consumer_task,
    )


async def _consume_host_events(
    watcher: HostSessionEventIterator,
    *,
    runtime_state: _ServiceObservationState,
    observation_state: _TerminalObservationState,
    on_activity: EntrypointActivityCallback | None,
    on_thinking: EntrypointThinkingCallback | None,
    callback_execution_port: EntrypointCallbackExecutionPort | None,
) -> None:
    """作为 iterator 唯一 ``anext`` owner 顺序产生 exact-five outcome。

    :param watcher: Host public Session event iterator。
    :param runtime_state: generation binding 与唯一 result slot owner。
    :param observation_state: live/outbox identity 去重状态。
    :param on_activity: 可选 activity callback。
    :param on_thinking: 可选 thinking callback。
    :param callback_execution_port: callback 的异步执行端口。
    :returns: ``None``。
    :raises asyncio.CancelledError: runtime cleanup 取消 consumer 时透传。
    """

    while True:
        binding = await runtime_state.wait_for_binding()
        if binding is None:
            return
        target_generation, target_run_id = binding
        try:
            event = await anext(watcher)
        except asyncio.CancelledError:
            raise
        except StopAsyncIteration:
            runtime_state.try_commit(
                _IteratorEnded(target_generation=target_generation),
                target_run_id=target_run_id,
            )
            return
        except HostApiError as error:
            if (
                error.code is HostApiErrorCode.DELIVERY_INTERRUPTED
                and isinstance(error.detail, HostSessionEventDeliveryDetail)
                and error.detail.reason is HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW
            ):
                runtime_state.try_commit(
                    _DeliveryInterrupted(
                        target_generation=target_generation,
                        error=error,
                    ),
                    target_run_id=target_run_id,
                )
            else:
                runtime_state.try_commit(
                    _IteratorFailed(
                        target_generation=target_generation,
                        error=error,
                    ),
                    target_run_id=target_run_id,
                )
            return
        except Exception as error:
            runtime_state.try_commit(
                _IteratorFailed(
                    target_generation=target_generation,
                    error=error,
                ),
                target_run_id=target_run_id,
            )
            return
        try:
            result = await _observation_result_from_event(
                event,
                target_generation=target_generation,
                target_run_id=target_run_id,
                state=observation_state,
                on_activity=on_activity,
                on_thinking=on_thinking,
                callback_execution_port=callback_execution_port,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            runtime_state.try_commit(
                _IteratorFailed(
                    target_generation=target_generation,
                    error=error,
                ),
                target_run_id=target_run_id,
            )
            return
        if result is None:
            continue
        committed = runtime_state.try_commit(
            result,
            target_run_id=target_run_id,
        )
        if not committed:
            return
        if isinstance(result, _TargetTerminal):
            await runtime_state.wait_for_rebind_or_stop(target_generation)
            continue
        return


async def _observation_result_from_event(
    event: HostSessionEvent,
    *,
    target_generation: int,
    target_run_id: str,
    state: _TerminalObservationState,
    on_activity: EntrypointActivityCallback | None,
    on_thinking: EntrypointThinkingCallback | None,
    callback_execution_port: EntrypointCallbackExecutionPort | None,
) -> _ServiceObservationResult | None:
    """在 consumer 调用栈内投影单个 Host event。

    :param event: 当前唯一 ``anext`` 返回的 public event。
    :param target_generation: 当前 target generation。
    :param target_run_id: 当前 target Run id。
    :param state: terminal/activity/thinking identity 状态。
    :param on_activity: 可选 activity callback。
    :param on_thinking: 可选 thinking callback。
    :param callback_execution_port: callback 的异步执行端口。
    :returns: exact-five member；普通/无关 event 返回 ``None``。
    :raises asyncio.CancelledError: consumer cleanup 取消时透传。
    """

    if isinstance(event, HostEvent):
        terminal = _terminal_result_from_live_event(
            event,
            run_id=target_run_id,
            state=state,
        )
        if terminal is not None:
            return _TargetTerminal(
                target_generation=target_generation,
                result=terminal,
            )
        activity = _activity_from_live_event(
            event=event,
            state=state,
            run_id=target_run_id,
            on_activity=on_activity,
        )
        if activity is None or on_activity is None:
            return None
        if callback_execution_port is None:
            raise RuntimeError("activity callback execution port missing")
        try:
            await _invoke_activity_callback(
                callback_execution_port,
                on_activity,
                activity,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return _CallbackFailed(
                target_generation=target_generation,
                callback_kind=_CallbackKind.ACTIVITY,
                error=error,
            )
        return None
    if isinstance(event, HostTransientDelta):
        thinking = _thinking_from_live_event(
            event=event,
            state=state,
            run_id=target_run_id,
            on_thinking=on_thinking,
        )
        if thinking is None or on_thinking is None:
            return None
        if callback_execution_port is None:
            raise RuntimeError("thinking callback execution port missing")
        try:
            await _invoke_thinking_callback(
                callback_execution_port,
                on_thinking,
                thinking,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return _CallbackFailed(
                target_generation=target_generation,
                callback_kind=_CallbackKind.THINKING,
                error=error,
            )
        return None
    assert_never(event)


def _activity_from_live_event(
    *,
    event: HostEvent,
    state: _TerminalObservationState,
    run_id: str,
    on_activity: EntrypointActivityCallback | None,
) -> EntrypointActivity | None:
    """选择并投影当前 target 的未重复 activity。

    :param event: Host public event。
    :param state: activity identity 状态。
    :param run_id: 当前 target Run id。
    :param on_activity: 可选 activity callback。
    :returns: 待调用 DTO；不应调用 callback 时返回 ``None``。
    :raises ValueError: Host activity payload 不完整时抛出。
    """

    if on_activity is None or event.terminal_status is not None or event.activity is None:
        return None
    if event.run_id != run_id:
        return None
    if event.dedupe_key in state.seen_activity_dedupe_keys:
        return None
    state.seen_activity_dedupe_keys.add(event.dedupe_key)
    return _entrypoint_activity_from_host_event(event)


def _thinking_from_live_event(
    *,
    event: HostTransientDelta,
    state: _TerminalObservationState,
    run_id: str,
    on_thinking: EntrypointThinkingCallback | None,
) -> EntrypointThinking | None:
    """选择并投影当前 target 的未重复 reasoning delta。

    :param event: Host public transient delta。
    :param state: thinking identity 状态。
    :param run_id: 当前 target Run id。
    :param on_thinking: 可选 thinking callback。
    :returns: 待调用 DTO；不应调用 callback 时返回 ``None``。
    :raises AssertionError: Host transient union 出现未知成员时抛出。
    """

    if on_thinking is None or event.run_id != run_id:
        return None
    data = event.data
    if isinstance(data, HostContentDelta | HostToolCallDelta):
        return None
    if not isinstance(data, HostReasoningDelta):
        assert_never(data)
    if event.dedupe_key in state.seen_thinking_dedupe_keys:
        return None
    state.seen_thinking_dedupe_keys.add(event.dedupe_key)
    return _entrypoint_thinking_from_transient_delta(event, data)


async def _invoke_activity_callback(
    execution_port: EntrypointCallbackExecutionPort,
    callback: EntrypointActivityCallback,
    activity: EntrypointActivity,
) -> None:
    """shield 并等待当前 activity callback job 完整收口。

    :param execution_port: UI-owned callback 执行端口。
    :param callback: 同步 activity callback。
    :param activity: Service activity DTO。
    :returns: ``None``。
    :raises asyncio.CancelledError: consumer 被取消且 job 已真实结束后透传。
    :raises Exception: callback 或调度失败时透传原异常。
    """

    job = asyncio.create_task(execution_port.invoke_activity(callback, activity))
    await _await_shielded_callback_job(job)


async def _invoke_thinking_callback(
    execution_port: EntrypointCallbackExecutionPort,
    callback: EntrypointThinkingCallback,
    thinking: EntrypointThinking,
) -> None:
    """shield 并等待当前 thinking callback job 完整收口。

    :param execution_port: UI-owned callback 执行端口。
    :param callback: 同步 thinking callback。
    :param thinking: Service thinking DTO。
    :returns: ``None``。
    :raises asyncio.CancelledError: consumer 被取消且 job 已真实结束后透传。
    :raises Exception: callback 或调度失败时透传原异常。
    """

    job = asyncio.create_task(execution_port.invoke_thinking(callback, thinking))
    await _await_shielded_callback_job(job)


async def _await_shielded_callback_job(job: asyncio.Task[None]) -> None:
    """在 consumer cancellation 下仍等待已创建 callback job。

    :param job: 当前唯一 submitted/in-flight callback job。
    :returns: ``None``。
    :raises asyncio.CancelledError: caller cancellation 在 job 收口后透传。
    :raises Exception: callback job 失败时透传原异常。
    """

    try:
        await asyncio.shield(job)
    except asyncio.CancelledError:
        while not job.done():
            try:
                await asyncio.shield(job)
            except asyncio.CancelledError:
                continue
        try:
            await job
        except Exception:
            pass
        raise


async def _wait_for_single_target_result(
    runtime: _WatchAndWaitRuntime,
    *,
    host: Host,
    session_id: str,
    run_id: str,
    state: _TerminalObservationState,
    on_activity: EntrypointActivityCallback | None,
    callback_execution_port: EntrypointCallbackExecutionPort | None,
    poll_interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
) -> EntrypointRunTerminalResult:
    """等待单目标 slot 并执行唯一 exact-five disposition。

    :param runtime: 当前 watcher runtime。
    :param host: Host public handle。
    :param session_id: 目标 Session id。
    :param run_id: 唯一目标 Run id。
    :param state: durable/live identity 状态。
    :param on_activity: 可选 cleanup diagnostic callback。
    :param callback_execution_port: callback 的异步执行端口。
    :param poll_interval_seconds: durable recovery 轮询间隔。
    :param sleep: 可注入 sleep coroutine。
    :returns: terminal result。
    :raises BaseException: exact disposition 或 caller cancellation 原样传播。
    """

    try:
        result = await runtime.state.wait_for_result()
    except asyncio.CancelledError as error:
        cleanup_error = await _close_watch_and_wait_runtime(runtime)
        _raise_primary_with_cleanup(error, cleanup_error)
    return await _finish_observation_result(
        result,
        runtime=runtime,
        host=host,
        session_id=session_id,
        run_id=run_id,
        state=state,
        on_activity=on_activity,
        callback_execution_port=callback_execution_port,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
    )


async def _finish_observation_result(
    result: _ServiceObservationResult,
    *,
    runtime: _WatchAndWaitRuntime,
    host: Host,
    session_id: str,
    run_id: str,
    state: _TerminalObservationState,
    on_activity: EntrypointActivityCallback | None,
    callback_execution_port: EntrypointCallbackExecutionPort | None,
    poll_interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
) -> EntrypointRunTerminalResult:
    """cleanup watcher 后执行一个 exact-five member 的 caller disposition。

    :param result: first-committed exact-five member。
    :param runtime: 当前 watcher runtime。
    :param host: Host public handle。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :param state: durable/live identity 状态。
    :param on_activity: 可选 cleanup diagnostic callback。
    :param callback_execution_port: callback 的异步执行端口。
    :param poll_interval_seconds: durable recovery 轮询间隔。
    :param sleep: 可注入 sleep coroutine。
    :returns: live terminal 或 delivery recovery terminal。
    :raises BaseException: member 对应的唯一失败 disposition。
    """

    cleanup_error = await _close_watch_and_wait_runtime(runtime)
    if isinstance(result, _TargetTerminal):
        if cleanup_error is not None:
            await _emit_cleanup_diagnostic(
                on_activity=on_activity,
                callback_execution_port=callback_execution_port,
            )
        return result.result
    if isinstance(result, _DeliveryInterrupted):
        try:
            recovered = await _wait_for_durable_terminal(
                host,
                session_id=session_id,
                run_id=run_id,
                state=state,
                poll_interval_seconds=poll_interval_seconds,
                sleep=sleep,
            )
        except BaseException as recovery_error:
            _raise_delivery_recovery_failure(
                recovery_error,
                delivery_error=result.error,
                cleanup_error=cleanup_error,
            )
        if cleanup_error is not None:
            await _emit_cleanup_diagnostic(
                on_activity=on_activity,
                callback_execution_port=callback_execution_port,
            )
        return recovered
    _raise_observation_failure(result, cleanup_error=cleanup_error)


def _raise_observation_failure(
    result: _ServiceObservationResult,
    *,
    cleanup_error: BaseException | None,
) -> Never:
    """按 exact-five 表抛出非成功 member，并保留 cleanup chain。

    :param result: first-committed exact-five member。
    :param cleanup_error: watcher ``aclose`` failure；无失败时为 ``None``。
    :returns: 本函数不返回。
    :raises BaseException: member 对应的唯一 caller failure。
    """

    if isinstance(result, _IteratorEnded):
        _raise_primary_with_cleanup(
            EntrypointRuntimeError("session_event_iterator_ended_before_terminal"),
            cleanup_error,
        )
    if isinstance(result, _CallbackFailed):
        _raise_primary_with_cleanup(result.error, cleanup_error)
    if isinstance(result, _IteratorFailed):
        if isinstance(result.error, HostApiError | HostClosedError):
            _raise_primary_with_cleanup(result.error, cleanup_error)
        _raise_wrapped_iterator_failure(result.error, cleanup_error=cleanup_error)
    if isinstance(result, _DeliveryInterrupted):
        raise RuntimeError("delivery interruption requires durable disposition")
    if isinstance(result, _TargetTerminal):
        raise RuntimeError("target terminal requires success disposition")
    assert_never(result)


def _raise_wrapped_iterator_failure(
    original_error: Exception,
    *,
    cleanup_error: BaseException | None,
) -> Never:
    """抛出 non-public iterator failure 的固定 wrapper/chain。

    :param original_error: iterator 原始异常。
    :param cleanup_error: watcher cleanup 异常；无失败时为 ``None``。
    :returns: 本函数不返回。
    :raises EntrypointRuntimeError: 始终抛出固定 stable reason。
    """

    wrapper = EntrypointRuntimeError("session_event_iterator_failed_before_terminal")
    if cleanup_error is None:
        raise wrapper from original_error
    try:
        raise original_error from cleanup_error
    except Exception as chained_original:
        raise wrapper from chained_original


def _raise_delivery_recovery_failure(
    recovery_error: BaseException,
    *,
    delivery_error: HostApiError,
    cleanup_error: BaseException | None,
) -> Never:
    """抛出 recovery -> delivery -> optional cleanup 固定异常链。

    :param recovery_error: durable recovery 原始失败。
    :param delivery_error: first-committed typed delivery error。
    :param cleanup_error: watcher cleanup 失败；无失败时为 ``None``。
    :returns: 本函数不返回。
    :raises BaseException: recovery error 保持 top-level 原样抛出。
    """

    if cleanup_error is None:
        raise recovery_error from delivery_error
    try:
        raise delivery_error from cleanup_error
    except HostApiError as chained_delivery:
        raise recovery_error from chained_delivery


def _raise_primary_with_cleanup(
    primary_error: BaseException,
    cleanup_error: BaseException | None,
) -> Never:
    """保持 caller primary identity，并把 cleanup error 设为直接 cause。

    :param primary_error: caller-visible primary。
    :param cleanup_error: cleanup failure；无失败时为 ``None``。
    :returns: 本函数不返回。
    :raises BaseException: 原样抛出 ``primary_error``。
    """

    if cleanup_error is None:
        raise primary_error
    raise primary_error from cleanup_error


def _raise_cleanup_failure(cleanup_error: BaseException) -> Never:
    """投影 slot-empty cleanup failure 的唯一 stable disposition。

    :param cleanup_error: watcher ``aclose`` 原始失败。
    :returns: 本函数不返回。
    :raises HostApiError: public Host cleanup error 原样抛出。
    :raises HostClosedError: public Host closed error 原样抛出。
    :raises EntrypointRuntimeError: 非 public cleanup error 使用固定 wrapper。
    """

    if isinstance(cleanup_error, HostApiError | HostClosedError):
        raise cleanup_error
    raise EntrypointRuntimeError("session_event_iterator_cleanup_failed") from cleanup_error


async def _close_watch_and_wait_runtime(
    runtime: _WatchAndWaitRuntime,
) -> BaseException | None:
    """停止并 await sole consumer 后恰好一次关闭 public iterator。

    :param runtime: 待关闭的 watcher runtime。
    :returns: iterator cleanup failure；成功或已经关闭时返回 ``None``。
    :raises Exception: consumer invariant 失败时透传实现错误。
    """

    if runtime.closed:
        return None
    runtime.closed = True
    runtime.state.request_stop()
    if not runtime.consumer_task.done():
        runtime.consumer_task.cancel()
    try:
        await runtime.consumer_task
    except asyncio.CancelledError:
        pass
    cleanup_error: BaseException | None = None
    try:
        await runtime.watcher.aclose()
    except BaseException as error:
        cleanup_error = error
    finally:
        runtime.state.mark_closed()
    return cleanup_error


async def _wait_for_durable_terminal(
    host: Host,
    *,
    session_id: str,
    run_id: str,
    state: _TerminalObservationState,
    poll_interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
) -> EntrypointRunTerminalResult:
    """只用 ``get_run`` / Outbox 等待 durable terminal projection。

    :param host: Host public handle。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :param state: durable/live identity 与 cursor 状态。
    :param poll_interval_seconds: public read 轮询间隔。
    :param sleep: 可注入 sleep coroutine。
    :returns: Outbox terminal result。
    :raises EntrypointRuntimeError: projection 失败或 caught-up 缺 target 时抛出。
    :raises HostApiError: public durable read 失败时原样透传。
    """

    while True:
        run_snapshot = await host.get_run(run_id)
        if is_terminal_run_status(run_snapshot.status):
            terminal = await _read_outbox_terminal(
                host,
                session_id=session_id,
                run_id=run_id,
                state=state,
            )
            if terminal is not None:
                return terminal
        await sleep(poll_interval_seconds)


async def _emit_cleanup_diagnostic(
    *,
    on_activity: EntrypointActivityCallback | None,
    callback_execution_port: EntrypointCallbackExecutionPort | None,
) -> None:
    """best-effort 输出一次固定去敏 watcher cleanup diagnostic。

    :param on_activity: 可选 activity callback。
    :param callback_execution_port: callback 的 UI-owned 执行端口。
    :returns: ``None``。
    :raises asyncio.CancelledError: caller cancellation 透传。
    """

    if on_activity is None or callback_execution_port is None:
        return
    diagnostic = EntrypointActivity(
        kind=EntrypointActivityKind.WATCHER_DIAGNOSTIC,
        status=EntrypointActivityStatus.FAILED,
        run_id=None,
        event_sequence=None,
        dedupe_key=_WATCHER_CLEANUP_ACTIVITY_DEDUPE_KEY,
        title=_WATCHER_CLEANUP_ACTIVITY_TITLE,
        summary=_WATCHER_CLEANUP_ACTIVITY_SUMMARY,
        severity=EntrypointActivitySeverity.WARNING,
        tool_name=None,
        tool_display_name=None,
        counts=None,
    )
    try:
        await _invoke_activity_callback(
            callback_execution_port,
            on_activity,
            diagnostic,
        )
    except Exception:
        return


def _entrypoint_activity_from_host_event(event: HostEvent) -> EntrypointActivity:
    """把 Host public activity view 转为 entrypoint activity。

    :param event: Host public event，必须携带 ``activity``。
    :returns: entrypoint activity。
    :raises ValueError: event 未携带 activity 时抛出。
    """

    activity = event.activity
    if activity is None:
        raise ValueError("HostEvent.activity is required")
    return EntrypointActivity(
        kind=_entrypoint_activity_kind_from_host(activity.kind),
        status=_entrypoint_activity_status_from_host(activity.status),
        run_id=event.run_id,
        event_sequence=event.event_sequence,
        dedupe_key=event.dedupe_key,
        title=activity.title,
        summary=activity.summary,
        severity=_entrypoint_activity_severity_from_host(activity.severity),
        tool_name=activity.tool_name,
        tool_display_name=activity.tool_display_name,
        counts=_entrypoint_activity_counts_from_host(activity.counts),
        context_usage=_entrypoint_context_usage_from_host(
            activity.context_usage
        ),
    )


def _entrypoint_thinking_from_transient_delta(
    event: HostTransientDelta,
    data: HostReasoningDelta,
) -> EntrypointThinking:
    """把 Host public reasoning delta 转为 entrypoint thinking。

    :param event: Host public transient envelope。
    :param data: 已穷举分支出的 reasoning payload。
    :returns: entrypoint thinking DTO。
    :raises ValueError: public DTO identity 校验失败时抛出。
    """

    return EntrypointThinking(
        run_id=event.run_id,
        runtime_id=event.runtime_id,
        runtime_sequence=event.runtime_sequence,
        dedupe_key=event.dedupe_key,
        text_delta=data.text_delta,
    )


def _entrypoint_activity_kind_from_host(kind: HostActivityKind) -> EntrypointActivityKind:
    """把 Host activity kind 映射为 Service activity kind。

    :param kind: Host public activity kind。
    :returns: Service entrypoint activity kind。
    :raises AssertionError: 出现未覆盖的 Host activity kind 时抛出。
    """

    if kind is HostActivityKind.RUN_LIFECYCLE:
        return EntrypointActivityKind.RUN_LIFECYCLE
    if kind is HostActivityKind.TOOL_CALL:
        return EntrypointActivityKind.TOOL_CALL
    if kind is HostActivityKind.TOOL_RESULT:
        return EntrypointActivityKind.TOOL_RESULT
    if kind is HostActivityKind.TOOL_BATCH:
        return EntrypointActivityKind.TOOL_BATCH
    if kind is HostActivityKind.TOOL_AWAITING:
        return EntrypointActivityKind.TOOL_AWAITING
    if kind is HostActivityKind.CONTEXT_USAGE:
        return EntrypointActivityKind.CONTEXT_USAGE
    if kind is HostActivityKind.CONTEXT_COMPACTION:
        return EntrypointActivityKind.CONTEXT_COMPACTION
    if kind is HostActivityKind.PROVIDER_DIAGNOSTIC:
        return EntrypointActivityKind.PROVIDER_DIAGNOSTIC
    if kind is HostActivityKind.PROVIDER_PROTOCOL_ERROR:
        return EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR
    raise AssertionError(f"unexpected HostActivityKind: {kind}")


def _entrypoint_activity_status_from_host(
    status: HostActivityStatus,
) -> EntrypointActivityStatus:
    """把 Host activity status 映射为 Service activity status。

    :param status: Host public activity status。
    :returns: Service entrypoint activity status。
    :raises AssertionError: 出现未覆盖的 Host activity status 时抛出。
    """

    if status is HostActivityStatus.STARTED:
        return EntrypointActivityStatus.STARTED
    if status is HostActivityStatus.IN_PROGRESS:
        return EntrypointActivityStatus.IN_PROGRESS
    if status is HostActivityStatus.COMPLETED:
        return EntrypointActivityStatus.COMPLETED
    if status is HostActivityStatus.FAILED:
        return EntrypointActivityStatus.FAILED
    if status is HostActivityStatus.CANCELLED:
        return EntrypointActivityStatus.CANCELLED
    if status is HostActivityStatus.WAITING:
        return EntrypointActivityStatus.WAITING
    if status is HostActivityStatus.INFO:
        return EntrypointActivityStatus.INFO
    raise AssertionError(f"unexpected HostActivityStatus: {status}")


def _entrypoint_activity_severity_from_host(
    severity: HostActivitySeverity,
) -> EntrypointActivitySeverity:
    """把 Host activity severity 映射为 Service activity severity。

    :param severity: Host public activity severity。
    :returns: Service entrypoint activity severity。
    :raises AssertionError: 出现未覆盖的 Host activity severity 时抛出。
    """

    if severity is HostActivitySeverity.INFO:
        return EntrypointActivitySeverity.INFO
    if severity is HostActivitySeverity.WARNING:
        return EntrypointActivitySeverity.WARNING
    if severity is HostActivitySeverity.ERROR:
        return EntrypointActivitySeverity.ERROR
    raise AssertionError(f"unexpected HostActivitySeverity: {severity}")


def _entrypoint_activity_counts_from_host(
    counts: HostActivityCounts | None,
) -> EntrypointActivityCounts | None:
    """把 Host activity counts 映射为 Service activity counts。

    :param counts: Host public activity counts；无计数时为 ``None``。
    :returns: Service entrypoint activity counts 或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if counts is None:
        return None
    return EntrypointActivityCounts(
        total=counts.total,
        completed=counts.completed,
        failed=counts.failed,
        cancelled=counts.cancelled,
    )


def _entrypoint_context_usage_from_host(
    usage: HostContextUsageView | None,
) -> EntrypointContextUsage | None:
    """逐字段复制Host context usage，不执行算术或decision重算。

    :param usage: Host public context usage；无时为``None``。
    :returns: Service同形typed DTO或``None``。
    :raises AssertionError: Host enum出现未覆盖成员时抛出。
    """

    if usage is None:
        return None
    return EntrypointContextUsage(
        predicted_input_tokens=usage.predicted_input_tokens,
        context_window_size=usage.context_window_size,
        utilization_basis_points=usage.utilization_basis_points,
        soft_threshold_tokens=usage.soft_threshold_tokens,
        hard_threshold_tokens=usage.hard_threshold_tokens,
        estimate_method=_entrypoint_context_estimate_method_from_host(
            usage.estimate_method
        ),
        pressure_level=_entrypoint_context_pressure_from_host(
            usage.pressure_level
        ),
    )


def _entrypoint_context_estimate_method_from_host(
    method: ContextEstimateMethod,
) -> EntrypointContextEstimateMethod:
    """穷举映射Host estimate method。

    :param method: Host typed estimate method。
    :returns: Service对应enum。
    :raises AssertionError: Host出现未覆盖成员时抛出。
    """

    if method is ContextEstimateMethod.USAGE_ANCHORED:
        return EntrypointContextEstimateMethod.USAGE_ANCHORED
    if method is ContextEstimateMethod.CONSERVATIVE_FALLBACK:
        return EntrypointContextEstimateMethod.CONSERVATIVE_FALLBACK
    raise AssertionError(f"unexpected ContextEstimateMethod: {method}")


def _entrypoint_context_pressure_from_host(
    pressure: ContextPressureLevel,
) -> EntrypointContextPressureLevel:
    """穷举映射Host pressure level。

    :param pressure: Host typed pressure。
    :returns: Service对应enum。
    :raises AssertionError: Host出现未覆盖成员时抛出。
    """

    if pressure is ContextPressureLevel.NORMAL:
        return EntrypointContextPressureLevel.NORMAL
    if pressure is ContextPressureLevel.SOFT_THRESHOLD_EXCEEDED:
        return EntrypointContextPressureLevel.SOFT_THRESHOLD_EXCEEDED
    if pressure is ContextPressureLevel.HARD_THRESHOLD_EXCEEDED:
        return EntrypointContextPressureLevel.HARD_THRESHOLD_EXCEEDED
    raise AssertionError(f"unexpected ContextPressureLevel: {pressure}")


def _terminal_result_from_live_event(
    event: HostEvent,
    *,
    run_id: str,
    state: _TerminalObservationState,
) -> EntrypointRunTerminalResult | None:
    """把 live HostEvent 转为目标 Run terminal result。

    :param event: Host public event。
    :param run_id: 目标 Run id。
    :param state: 本轮本地观察状态。
    :returns: 命中的 terminal result；不匹配时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    state.last_observed_event_sequence = max(
        state.last_observed_event_sequence,
        event.event_sequence,
    )
    if event.terminal_status is None:
        return None
    duplicate = event.event_id in state.seen_terminal_event_ids or event.dedupe_key in state.seen_dedupe_keys
    state.seen_terminal_event_ids.add(event.event_id)
    if duplicate:
        return None
    state.seen_dedupe_keys.add(event.dedupe_key)
    if event.run_id != run_id:
        return None
    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        session_id=event.session_id,
        run_id=run_id,
        terminal_event_id=event.event_id,
        event_sequence=event.event_sequence,
        terminal_status=event.terminal_status,
        dedupe_key=event.dedupe_key,
        final_answer=event.final_answer,
        error_message=event.error_message,
        cancel_reason=event.cancel_reason,
        watcher_failure_message=None,
    )


async def _read_session_outbox_terminal_backfill(
    host: Host,
    *,
    session_id: str,
    state: _TerminalObservationState,
    outbox_lagged_max_attempts: int,
    poll_interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
) -> tuple[EntrypointRunTerminalResult, ...]:
    """读取 selected Session 下所有增量 terminal outbox items。

    :param host: Host public Protocol handle。
    :param session_id: 目标 Session id。
    :param state: 本轮本地观察状态。
    :param outbox_lagged_max_attempts: projection ``LAGGED`` 时的最大重试次数。
    :param poll_interval_seconds: LAGGED 重试等待间隔。
    :param sleep: 可注入 sleep coroutine。
    :returns: session-scoped terminal 结果。
    :raises EntrypointRuntimeError: projection failed 或 LAGGED 重试耗尽时抛出。
    """

    lagged_attempts = 0
    results: list[EntrypointRunTerminalResult] = []
    while True:
        if state.outbox_cursor is None:
            state.outbox_cursor = OutboxTerminalCursor(event_sequence=state.last_observed_event_sequence)
        batch = await host.read_outbox_terminal_items(
            session_id,
            ReadOutboxTerminalItemsRequest(
                after=state.outbox_cursor,
                seen_terminal_event_ids=tuple(sorted(state.seen_terminal_event_ids)),
                limit=_OUTBOX_TERMINAL_READ_LIMIT,
            ),
        )
        if batch.projection_status is OutboxProjectionStatus.FAILED:
            raise EntrypointRuntimeError(
                "outbox terminal projection failed during startup: "
                f"{batch.projection_error_code}: "
                f"{batch.projection_error_message}"
            )
        results.extend(
            _scan_session_outbox_terminal_items(
                items=batch.items,
                state=state,
            )
        )
        state.outbox_cursor = batch.next_cursor
        if batch.has_more:
            continue
        if batch.projection_status is OutboxProjectionStatus.CAUGHT_UP:
            return tuple(results)
        if lagged_attempts >= outbox_lagged_max_attempts:
            raise EntrypointRuntimeError(
                "outbox terminal projection lagged during startup: "
                f"session_id={session_id}, attempts={lagged_attempts}"
            )
        lagged_attempts += 1
        await sleep(poll_interval_seconds)


def _scan_session_outbox_terminal_items(
    *,
    items: tuple[OutboxTerminalItem, ...],
    state: _TerminalObservationState,
) -> tuple[EntrypointRunTerminalResult, ...]:
    """扫描 session-scoped outbox terminal items。

    :param items: Host public outbox terminal items。
    :param state: 本轮本地观察状态。
    :returns: 未重复的 terminal 结果。
    :raises Exception: 不主动抛出异常。
    """

    results: list[EntrypointRunTerminalResult] = []
    for item in items:
        state.last_observed_event_sequence = max(
            state.last_observed_event_sequence,
            item.event_sequence,
        )
        duplicate = item.terminal_event_id in state.seen_terminal_event_ids or item.dedupe_key in state.seen_dedupe_keys
        # Outbox 是 terminal 投递真源；即使与 live dedupe，也要记录其 terminal id。
        state.seen_terminal_event_ids.add(item.terminal_event_id)
        if duplicate:
            continue
        state.seen_dedupe_keys.add(item.dedupe_key)
        results.append(_terminal_result_from_outbox_item(item))
    return tuple(results)


async def _read_outbox_terminal(
    host: Host,
    *,
    session_id: str,
    run_id: str,
    state: _TerminalObservationState,
) -> EntrypointRunTerminalResult | None:
    """通过 Host public outbox read 补读目标 Run terminal。

    :param host: Host public Protocol handle。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :param state: 本轮本地观察状态。
    :returns: 命中的 terminal result；projection 落后且未命中时返回 ``None``。
    :raises EntrypointRuntimeError: projection failed 或 caught-up 后仍缺 terminal
        时抛出。
    """

    if state.outbox_cursor is None:
        state.outbox_cursor = OutboxTerminalCursor(event_sequence=state.last_observed_event_sequence)
    while True:
        batch = await host.read_outbox_terminal_items(
            session_id,
            ReadOutboxTerminalItemsRequest(
                after=state.outbox_cursor,
                seen_terminal_event_ids=tuple(sorted(state.seen_terminal_event_ids)),
                limit=_OUTBOX_TERMINAL_READ_LIMIT,
            ),
        )
        if batch.projection_status is OutboxProjectionStatus.FAILED:
            raise EntrypointRuntimeError(
                "outbox terminal projection failed: "
                f"{batch.projection_error_code}: "
                f"{batch.projection_error_message}"
            )
        terminal = _scan_outbox_terminal_items(
            items=batch.items,
            run_id=run_id,
            state=state,
        )
        state.outbox_cursor = batch.next_cursor
        if terminal is not None:
            return terminal
        if batch.has_more:
            continue
        if batch.projection_status is OutboxProjectionStatus.CAUGHT_UP:
            raise EntrypointRuntimeError(
                "outbox terminal caught up without matching terminal item: "
                f"run_id={run_id}, cursor={batch.scanned_watermark.event_sequence}"
            )
        return None


def _scan_outbox_terminal_items(
    *,
    items: tuple[OutboxTerminalItem, ...],
    run_id: str,
    state: _TerminalObservationState,
) -> EntrypointRunTerminalResult | None:
    """扫描 outbox terminal items 并按目标 Run 过滤。

    :param items: Host public outbox terminal items。
    :param run_id: 目标 Run id。
    :param state: 本轮本地观察状态。
    :returns: 命中的 terminal result；没有命中时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for item in items:
        state.last_observed_event_sequence = max(
            state.last_observed_event_sequence,
            item.event_sequence,
        )
        duplicate = item.terminal_event_id in state.seen_terminal_event_ids or item.dedupe_key in state.seen_dedupe_keys
        state.seen_terminal_event_ids.add(item.terminal_event_id)
        if duplicate:
            continue
        state.seen_dedupe_keys.add(item.dedupe_key)
        if item.run_id == run_id:
            return _terminal_result_from_outbox_item(item)
    return None


def _terminal_result_from_outbox_item(
    item: OutboxTerminalItem,
) -> EntrypointRunTerminalResult:
    """把 outbox terminal item 转为 entrypoint terminal result。

    :param item: Host public outbox terminal item。
    :returns: entrypoint terminal result。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.OUTBOX_READ,
        session_id=item.session_id,
        run_id=item.run_id,
        terminal_event_id=item.terminal_event_id,
        event_sequence=item.event_sequence,
        terminal_status=item.terminal_status,
        dedupe_key=item.dedupe_key,
        final_answer=item.final_answer,
        error_message=item.error_message,
        cancel_reason=item.cancel_reason,
        watcher_failure_message=None,
    )


def _new_terminal_observation_state(
    *,
    terminal_cursor: OutboxTerminalCursor | None = None,
    seen_terminal_event_ids: frozenset[str] = frozenset(),
) -> _TerminalObservationState:
    """创建单次 terminal observation 状态。

    :param terminal_cursor: 调用方已成功展示的 terminal 水位；``None`` 表示从
        0 开始观察。
    :param seen_terminal_event_ids: 调用方已成功展示的 terminal event ids。
    :returns: 初始 observation state。
    :raises Exception: 不主动抛出异常。
    """

    initial_sequence = 0 if terminal_cursor is None else terminal_cursor.event_sequence
    return _TerminalObservationState(
        last_observed_event_sequence=initial_sequence,
        seen_terminal_event_ids=set(seen_terminal_event_ids),
        seen_dedupe_keys=set(),
        seen_activity_dedupe_keys=set(),
        seen_thinking_dedupe_keys=set(),
        outbox_cursor=terminal_cursor,
    )


def _require_non_empty(value: str, *, field_name: str) -> None:
    """校验字符串非空。

    :param value: 待校验字符串。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises TypeError: 值不是字符串时抛出。
    :raises ValueError: 值为空字符串时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(value: str | None, *, field_name: str) -> None:
    """校验可选字符串为空或非空字符串。

    :param value: 待校验字符串或 ``None``。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises TypeError: 值不是字符串且不为 ``None`` 时抛出。
    :raises ValueError: 值为空字符串时抛出。
    """

    if value is None:
        return
    _require_non_empty(value, field_name=field_name)


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验值为非负严格整数。

    :param value: 待校验整数。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值小于零时抛出。
    """

    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验值为正的严格整数。

    :param value: 待校验整数。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值不是正数时抛出。
    """

    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_positive_poll_interval(value: float) -> None:
    """校验 terminal 轮询间隔为正数。

    :param value: 轮询间隔秒数。
    :returns: ``None``。
    :raises ValueError: 间隔不是正数时抛出。
    """

    if not is_positive_finite_number(value):
        raise ValueError("poll_interval_seconds must be finite and > 0")
