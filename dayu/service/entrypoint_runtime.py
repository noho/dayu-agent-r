"""Product entrypoint 共享的 Agent runtime Service 边界。

本模块只编排 runtime assembly 输出与 Host public API / Protocol，不解析 CLI
参数，不读写 stdout / stderr，不安装 signal handler，也不导入 Engine 内部。
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol, cast

from dayu.contracts import JsonValue
from dayu.host.api import (
    CancelRunRequest,
    CancelMode,
    CreateSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostApiError,
    HostActivityCounts,
    HostActivityKind,
    HostActivitySeverity,
    HostActivityStatus,
    HostCallContext,
    HostEvent,
    HostFinalAnswerView,
    HostMetadataEntry,
    HostTerminalStatus,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItem,
    ReadOutboxTerminalItemsRequest,
    RunStatus,
    SessionSnapshot,
)
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig
from dayu.runtime.location import RuntimeLocations, resolve_runtime_locations
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
_WATCHER_FAILURE_DIAGNOSTIC_PREFIX: Final[str] = "watcher drain failed"
_WATCHER_FAILURE_ACTIVITY_DEDUPE_KEY: Final[str] = "entrypoint_watcher_failure"
_WATCHER_FAILURE_ACTIVITY_TITLE: Final[str] = "运行事件流诊断"
_WATCHER_FAILURE_ACTIVITY_SUMMARY_LIMIT: Final[int] = 240
_TERMINAL_RUN_STATUSES: Final[frozenset[RunStatus]] = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.LOST,
    }
)


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
    CONTEXT_COMPACTION = "context_compaction"
    PROVIDER_DIAGNOSTIC = "provider_diagnostic"
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


EntrypointActivityCallback = Callable[[EntrypointActivity], None]
"""entrypoint runtime activity 通知回调类型。"""


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

    :param workspace_root: 当前项目 / workspace 根目录。
    :param package_config_root: 包内默认配置根目录。
    :param explicit_config_dir: 调用方显式指定的配置覆盖目录；``None`` 表示
        使用默认 ``workspace/config`` 探测行为。
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
    :param watcher_failure_message: live watcher drain 失败后的首个诊断消息；
        ``None`` 表示本次观察未发现 watcher drain 失败。
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


class ClosableHostEventIterator(Protocol):
    """支持显式关闭的 HostEvent async iterator 窄协议。"""

    def __aiter__(self) -> AsyncIterator[HostEvent]:
        """返回 HostEvent async iterator。

        :returns: HostEvent async iterator。
        :raises Exception: 具体实现可在不可用时抛出运行时错误。
        """

        ...

    async def __anext__(self) -> HostEvent:
        """读取下一条 HostEvent。

        :returns: 下一条 HostEvent。
        :raises StopAsyncIteration: iterator 结束时抛出。
        """

        ...

    async def aclose(self) -> None:
        """关闭 HostEvent iterator。

        :returns: ``None``。
        :raises Exception: 具体实现可在关闭失败时抛出运行时错误。
        """

        ...


@dataclass(frozen=True, slots=True)
class _WatcherFailure:
    """watcher drain task 捕获到的异常。"""

    error: Exception


@dataclass(slots=True)
class _TerminalObservationState:
    """单次 terminal observation 的本地去重与 outbox 游标状态。"""

    last_observed_event_sequence: int
    seen_event_ids: set[str]
    seen_terminal_event_ids: set[str]
    seen_dedupe_keys: set[str]
    seen_activity_dedupe_keys: set[str]
    outbox_cursor: OutboxTerminalCursor | None
    watcher_failure_message: str | None


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
        project_root=request.workspace_root,
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
    :param poll_interval_seconds: watcher 暂无 terminal 时的 public read 轮询间隔。
    :param sleep: 可注入 sleep coroutine，便于测试。
    :returns: Run terminal 观察结果。
    :raises EntrypointRuntimeError: Host outbox projection 失败或终态投影缺失时抛出。
    :raises HostApiError: Host public API 调用失败时由 Host 抛出。

    本 helper 不持有内部 timeout。调用方必须通过外层 task cancellation、
    ``asyncio.wait_for(...)`` 或显式 cancel 请求控制等待生命周期。
    """

    _require_positive_poll_interval(poll_interval_seconds)
    watcher = _attach_watcher(host, request.session_id)
    queue: asyncio.Queue[HostEvent | _WatcherFailure] = asyncio.Queue()
    drain_task = asyncio.create_task(_drain_host_events(watcher, queue))
    state = _new_terminal_observation_state()
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
        if on_run_accepted is not None:
            on_run_accepted(followup.accepted_run_id)
        return await _wait_for_terminal(
            host,
            session_id=request.session_id,
            run_id=followup.accepted_run_id,
            queue=queue,
            state=state,
            on_activity=on_activity,
            allow_outbox_terminal_fallback=False,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
        )
    finally:
        await _close_watcher(watcher=watcher, drain_task=drain_task)


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
    :param poll_interval_seconds: watcher 暂无 terminal 时的 public read 轮询间隔。
    :param sleep: 可注入 sleep coroutine，便于测试。
    :returns: Run terminal 观察结果。
    :raises EntrypointRuntimeError: Host outbox projection 失败或终态投影缺失时抛出。
    :raises HostApiError: Host public API 调用失败时由 Host 抛出。

    本 helper 不持有内部 timeout。调用方必须通过外层 task cancellation、
    ``asyncio.wait_for(...)`` 或显式 cancel 请求控制等待生命周期。
    """

    _require_positive_poll_interval(poll_interval_seconds)
    run_snapshot = await host.get_run(request.run_id)
    state = _new_terminal_observation_state()
    if _is_terminal_run_status(run_snapshot.status):
        queue: asyncio.Queue[HostEvent | _WatcherFailure] = asyncio.Queue()
        return await _wait_for_terminal(
            host,
            session_id=run_snapshot.session_id,
            run_id=request.run_id,
            queue=queue,
            state=state,
            allow_outbox_terminal_fallback=True,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
        )
    watcher = _attach_watcher(host, run_snapshot.session_id)
    queue: asyncio.Queue[HostEvent | _WatcherFailure] = asyncio.Queue()
    drain_task = asyncio.create_task(_drain_host_events(watcher, queue))
    allow_outbox_terminal_fallback = False
    try:
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
        except HostApiError:
            latest_run_snapshot = await host.get_run(request.run_id)
            if not _is_terminal_run_status(latest_run_snapshot.status):
                raise
            allow_outbox_terminal_fallback = True
        return await _wait_for_terminal(
            host,
            session_id=run_snapshot.session_id,
            run_id=request.run_id,
            queue=queue,
            state=state,
            allow_outbox_terminal_fallback=allow_outbox_terminal_fallback,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
        )
    finally:
        await _close_watcher(watcher=watcher, drain_task=drain_task)


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

    watcher = _attach_watcher(host, request.session_id)
    queue: asyncio.Queue[HostEvent | _WatcherFailure] = asyncio.Queue()
    drain_task = asyncio.create_task(_drain_host_events(watcher, queue))
    state = _new_terminal_observation_state(
        terminal_cursor=request.terminal_cursor,
        seen_terminal_event_ids=request.seen_terminal_event_ids,
    )
    terminal_results: list[EntrypointRunTerminalResult] = []
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
        terminal_results.extend(
            _drain_available_startup_terminal_items(queue=queue, state=state)
        )
        await _observe_startup_active_and_queued_runs(
            host,
            request=request,
            queue=queue,
            state=state,
            terminal_results=terminal_results,
            sleep=sleep,
        )
        return EntrypointStartupReconnectResult(
            terminal_results=tuple(terminal_results),
            next_terminal_cursor=OutboxTerminalCursor(
                event_sequence=state.last_observed_event_sequence
            ),
            seen_terminal_event_ids=frozenset(state.seen_terminal_event_ids),
        )
    finally:
        await _close_watcher(watcher=watcher, drain_task=drain_task)


async def _observe_startup_active_and_queued_runs(
    host: Host,
    *,
    request: EntrypointStartupReconnectRequest,
    queue: asyncio.Queue[HostEvent | _WatcherFailure],
    state: _TerminalObservationState,
    terminal_results: list[EntrypointRunTerminalResult],
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    """观察 startup barrier 中的 active / queued Run 直到 Session idle。

    :param host: Host public Protocol handle。
    :param request: startup reconnect 请求。
    :param queue: watcher drain queue。
    :param state: 本轮本地观察状态。
    :param terminal_results: 已收集 terminal 结果列表。
    :param sleep: 可注入 sleep coroutine。
    :returns: ``None``。
    :raises EntrypointRuntimeError: queued-only promotion 等待耗尽时抛出。
    """

    while True:
        terminal_results.extend(
            _drain_available_startup_terminal_items(queue=queue, state=state)
        )
        snapshot = await host.get_session(request.session_id)
        if snapshot.active_run_id is not None:
            terminal_results.append(
                await _wait_for_terminal(
                    host,
                    session_id=request.session_id,
                    run_id=snapshot.active_run_id,
                    queue=queue,
                    state=state,
                    allow_outbox_terminal_fallback=True,
                    poll_interval_seconds=request.poll_interval_seconds,
                    sleep=sleep,
                )
            )
            continue
        if snapshot.queued_run_ids:
            promoted = await _wait_for_startup_promotion(
                host,
                session_id=request.session_id,
                promotion_max_attempts=request.promotion_max_attempts,
                promotion_poll_interval_seconds=request.promotion_poll_interval_seconds,
                sleep=sleep,
            )
            terminal_results.extend(
                _drain_available_startup_terminal_items(queue=queue, state=state)
            )
            if promoted.active_run_id is None:
                raise EntrypointRuntimeError(
                    "Session 仍有未开始的 queued Run，未进入输入态: "
                    f"session_id={request.session_id}, queued_run_count={len(promoted.queued_run_ids)}"
                )
            terminal_results.append(
                await _wait_for_terminal(
                    host,
                    session_id=request.session_id,
                    run_id=promoted.active_run_id,
                    queue=queue,
                    state=state,
                    allow_outbox_terminal_fallback=True,
                    poll_interval_seconds=request.poll_interval_seconds,
                    sleep=sleep,
                )
            )
            continue
        if await _close_startup_idle_tail(
            host,
            request=request,
            queue=queue,
            state=state,
            terminal_results=terminal_results,
            sleep=sleep,
        ):
            continue
        return


async def _close_startup_idle_tail(
    host: Host,
    *,
    request: EntrypointStartupReconnectRequest,
    queue: asyncio.Queue[HostEvent | _WatcherFailure],
    state: _TerminalObservationState,
    terminal_results: list[EntrypointRunTerminalResult],
    sleep: Callable[[float], Awaitable[None]],
) -> bool:
    """在 idle snapshot 后关闭 startup terminal tail。

    :param host: Host public Protocol handle。
    :param request: startup reconnect 请求。
    :param queue: watcher drain queue。
    :param state: 本轮本地观察状态。
    :param terminal_results: 已收集 terminal 结果列表。
    :param sleep: 可注入 sleep coroutine。
    :returns: 发现 terminal 或首次 watcher failure、需要重新读取 Session snapshot 时返回 ``True``。
    :raises EntrypointRuntimeError: Outbox projection 失败或 LAGGED 重试耗尽时抛出。
    """

    tail_outbox_results = await _read_session_outbox_terminal_backfill(
        host,
        session_id=request.session_id,
        state=state,
        outbox_lagged_max_attempts=request.outbox_lagged_max_attempts,
        poll_interval_seconds=request.poll_interval_seconds,
        sleep=sleep,
    )
    terminal_results.extend(tail_outbox_results)
    watcher_failure_before_drain = state.watcher_failure_message
    tail_live_results = _drain_available_startup_terminal_items(
        queue=queue,
        state=state,
    )
    terminal_results.extend(tail_live_results)
    watcher_failed_during_tail = (
        watcher_failure_before_drain is None
        and state.watcher_failure_message is not None
    )
    return bool(tail_outbox_results or tail_live_results or watcher_failed_during_tail)


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


def _attach_watcher(host: Host, session_id: str) -> ClosableHostEventIterator:
    """在 Host mutating command 前 attach live watcher。

    :param host: Host public Protocol handle。
    :param session_id: 目标 Session id。
    :returns: 可关闭 HostEvent iterator。
    :raises HostApiError: Host watch attach 失败时由 Host 抛出。
    """

    return cast(ClosableHostEventIterator, host.watch_session_events(session_id))


async def _drain_host_events(
    watcher: ClosableHostEventIterator,
    queue: asyncio.Queue[HostEvent | _WatcherFailure],
) -> None:
    """把 watcher 事件转存到本地 queue。

    :param watcher: 已 attach 的 HostEvent iterator。
    :param queue: 本地事件队列。
    :returns: ``None``。
    :raises asyncio.CancelledError: drain task 被取消时透传。
    """

    try:
        async for event in watcher:
            await queue.put(event)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await queue.put(_WatcherFailure(error=exc))


async def _close_watcher(*, watcher: ClosableHostEventIterator, drain_task: asyncio.Task[None]) -> None:
    """关闭 watcher 并回收 drain task。

    :param watcher: 待关闭 watcher。
    :param drain_task: watcher drain task。
    :returns: ``None``。
    :raises asyncio.CancelledError: watcher ``aclose`` 或 drain task 被取消时透传。
    :raises Exception: watcher ``aclose`` 失败时向上抛出。
    """

    try:
        if not drain_task.done():
            drain_task.cancel()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass
    finally:
        # 对 async generator watcher，必须先停止正在执行的 drain task，再调用
        # aclose；否则会触发 "asynchronous generator is already running"。
        await watcher.aclose()


async def _wait_for_terminal(
    host: Host,
    *,
    session_id: str,
    run_id: str,
    queue: asyncio.Queue[HostEvent | _WatcherFailure],
    state: _TerminalObservationState,
    on_activity: EntrypointActivityCallback | None = None,
    allow_outbox_terminal_fallback: bool,
    poll_interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
) -> EntrypointRunTerminalResult:
    """等待指定 Run 的 live 或 outbox terminal。

    :param host: Host public Protocol handle。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :param queue: watcher drain queue。
    :param state: 本轮本地观察状态。
    :param on_activity: 可选 activity 回调。
    :param allow_outbox_terminal_fallback: 是否允许在未观察到 live terminal 时读取
        Outbox terminal。该路径只用于可能错过 terminal 的补读场景；已 attach
        submit 路径不得把 Outbox 当作通用 final answer 读取接口。
    :param poll_interval_seconds: public read 轮询间隔。
    :param sleep: 可注入 sleep coroutine。
    :returns: Run terminal 观察结果。
    :raises EntrypointRuntimeError: outbox projection 失败或终态缺失时抛出。

    本 helper 不持有内部 timeout。调用方必须通过外层 task cancellation、
    ``asyncio.wait_for(...)`` 或显式 cancel 请求控制等待生命周期。
    """

    while True:
        live_terminal = _drain_available_watcher_items(
            queue=queue,
            state=state,
            run_id=run_id,
            on_activity=on_activity,
        )
        if live_terminal is not None:
            return live_terminal
        run_snapshot = await host.get_run(run_id)
        if _is_terminal_run_status(
            run_snapshot.status
        ) and _should_read_outbox_terminal(
            state=state,
            allow_outbox_terminal_fallback=allow_outbox_terminal_fallback,
        ):
            outbox_terminal = await _read_outbox_terminal(
                host,
                session_id=session_id,
                run_id=run_id,
                state=state,
            )
            if outbox_terminal is not None:
                return outbox_terminal
        await sleep(poll_interval_seconds)


def _should_read_outbox_terminal(
    *,
    state: _TerminalObservationState,
    allow_outbox_terminal_fallback: bool,
) -> bool:
    """判断当前等待路径是否允许读取 Outbox terminal。

    :param state: 本轮本地观察状态。
    :param allow_outbox_terminal_fallback: 调用路径是否显式允许 Outbox 补读。
    :returns: 允许读取 Outbox terminal 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return allow_outbox_terminal_fallback or state.watcher_failure_message is not None


def _drain_available_watcher_items(
    *,
    queue: asyncio.Queue[HostEvent | _WatcherFailure],
    state: _TerminalObservationState,
    run_id: str,
    on_activity: EntrypointActivityCallback | None = None,
) -> EntrypointRunTerminalResult | None:
    """消费当前 queue 中已到达的 watcher item。

    :param queue: watcher drain queue。
    :param state: 本轮本地观察状态。
    :param run_id: 目标 Run id。
    :param on_activity: 可选 activity 回调。
    :returns: 命中的 terminal result；没有命中时返回 ``None``。
    :raises Exception: ``on_activity`` callback 抛出的异常会向调用方透传。
    """

    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
        if isinstance(item, _WatcherFailure):
            _record_watcher_failure(state=state, error=item.error)
            _emit_watcher_failure_activity(
                state=state,
                error=item.error,
                on_activity=on_activity,
            )
            continue
        terminal = _terminal_result_from_live_event(
            item,
            run_id=run_id,
            state=state,
        )
        if terminal is not None:
            return terminal
        _emit_entrypoint_activity_from_host_event(
            event=item,
            state=state,
            run_id=run_id,
            on_activity=on_activity,
        )


def _emit_entrypoint_activity_from_host_event(
    *,
    event: HostEvent,
    state: _TerminalObservationState,
    run_id: str,
    on_activity: EntrypointActivityCallback | None,
) -> None:
    """把非终态 Host public activity 投影给 Service activity callback。

    :param event: Host public event。
    :param state: 本轮本地观察状态。
    :param run_id: 当前等待的目标 Run id。
    :param on_activity: 可选 activity 回调。
    :returns: ``None``。
    :raises Exception: callback 抛出的异常会向调用方透传。
    """

    if on_activity is None or event.terminal_status is not None or event.activity is None:
        return
    if event.run_id != run_id:
        return
    if event.dedupe_key in state.seen_activity_dedupe_keys:
        return
    state.seen_activity_dedupe_keys.add(event.dedupe_key)
    on_activity(_entrypoint_activity_from_host_event(event))


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
    if kind is HostActivityKind.CONTEXT_COMPACTION:
        return EntrypointActivityKind.CONTEXT_COMPACTION
    if kind is HostActivityKind.PROVIDER_DIAGNOSTIC:
        return EntrypointActivityKind.PROVIDER_DIAGNOSTIC
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


def _emit_watcher_failure_activity(
    *,
    state: _TerminalObservationState,
    error: Exception,
    on_activity: EntrypointActivityCallback | None,
) -> None:
    """把 watcher failure 转为有界本地诊断 activity。

    :param state: 本轮本地观察状态。
    :param error: watcher drain 捕获的异常。
    :param on_activity: 可选 activity 回调。
    :returns: ``None``。
    :raises Exception: callback 抛出的异常会向调用方透传。
    """

    if on_activity is None:
        return
    if _WATCHER_FAILURE_ACTIVITY_DEDUPE_KEY in state.seen_activity_dedupe_keys:
        return
    state.seen_activity_dedupe_keys.add(_WATCHER_FAILURE_ACTIVITY_DEDUPE_KEY)
    on_activity(
        EntrypointActivity(
            kind=EntrypointActivityKind.WATCHER_DIAGNOSTIC,
            status=EntrypointActivityStatus.INFO,
            run_id=None,
            event_sequence=None,
            dedupe_key=_WATCHER_FAILURE_ACTIVITY_DEDUPE_KEY,
            title=_WATCHER_FAILURE_ACTIVITY_TITLE,
            summary=_bounded_watcher_failure_activity_summary(error),
            severity=EntrypointActivitySeverity.WARNING,
            tool_name=None,
            tool_display_name=None,
            counts=None,
        )
    )


def _bounded_watcher_failure_activity_summary(error: Exception) -> str:
    """生成有界 watcher failure activity 摘要。

    :param error: watcher drain 捕获的异常。
    :returns: 有界诊断摘要。
    :raises Exception: 不主动抛出异常。
    """

    message = str(error)
    error_type = type(error).__name__
    if message:
        summary = f"{error_type}: {message}"
    else:
        summary = error_type
    if len(summary) <= _WATCHER_FAILURE_ACTIVITY_SUMMARY_LIMIT:
        return summary
    return summary[: _WATCHER_FAILURE_ACTIVITY_SUMMARY_LIMIT - 3] + "..."


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
    duplicate = event.event_id in state.seen_event_ids or event.dedupe_key in state.seen_dedupe_keys
    state.seen_event_ids.add(event.event_id)
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
        watcher_failure_message=state.watcher_failure_message,
    )


def _record_watcher_failure(*, state: _TerminalObservationState, error: Exception) -> None:
    """记录 watcher drain 失败的首个可诊断消息。

    :param state: 本轮本地观察状态。
    :param error: watcher drain 捕获的异常。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if state.watcher_failure_message is not None:
        return
    message = str(error)
    error_type = type(error).__name__
    if message:
        state.watcher_failure_message = f"{_WATCHER_FAILURE_DIAGNOSTIC_PREFIX}: {error_type}: {message}"
    else:
        state.watcher_failure_message = f"{_WATCHER_FAILURE_DIAGNOSTIC_PREFIX}: {error_type}"


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
            state.outbox_cursor = OutboxTerminalCursor(
                event_sequence=state.last_observed_event_sequence
            )
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
                _observation_error_message(
                    state=state,
                    message=(
                        "outbox terminal projection failed during startup: "
                        f"{batch.projection_error_code}: "
                        f"{batch.projection_error_message}"
                    ),
                )
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
                _observation_error_message(
                    state=state,
                    message=(
                        "outbox terminal projection lagged during startup: "
                        f"session_id={session_id}, attempts={lagged_attempts}"
                    ),
                )
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
        duplicate = (
            item.terminal_event_id in state.seen_terminal_event_ids
            or item.dedupe_key in state.seen_dedupe_keys
        )
        # Outbox 是 terminal 投递真源；即使与 live dedupe，也要记录其 terminal id。
        state.seen_terminal_event_ids.add(item.terminal_event_id)
        if duplicate:
            continue
        state.seen_dedupe_keys.add(item.dedupe_key)
        results.append(
            _terminal_result_from_outbox_item(
                item,
                watcher_failure_message=state.watcher_failure_message,
            )
        )
    return tuple(results)


def _drain_available_startup_terminal_items(
    *,
    queue: asyncio.Queue[HostEvent | _WatcherFailure],
    state: _TerminalObservationState,
) -> tuple[EntrypointRunTerminalResult, ...]:
    """消费 startup watcher queue 中已到达的 terminal events。

    :param queue: watcher drain queue。
    :param state: 本轮本地观察状态。
    :returns: 未重复的 terminal 结果。
    :raises Exception: 不主动抛出异常。
    """

    results: list[EntrypointRunTerminalResult] = []
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            return tuple(results)
        if isinstance(item, _WatcherFailure):
            _record_watcher_failure(state=state, error=item.error)
            continue
        terminal = _startup_terminal_result_from_live_event(item, state=state)
        if terminal is not None:
            results.append(terminal)


def _startup_terminal_result_from_live_event(
    event: HostEvent,
    *,
    state: _TerminalObservationState,
) -> EntrypointRunTerminalResult | None:
    """把 startup live HostEvent 转为 session-scoped terminal result。

    :param event: Host public event。
    :param state: 本轮本地观察状态。
    :returns: 未重复 terminal result；非 terminal 或重复时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    state.last_observed_event_sequence = max(
        state.last_observed_event_sequence,
        event.event_sequence,
    )
    if event.terminal_status is None or event.run_id is None:
        return None
    duplicate = (
        event.event_id in state.seen_terminal_event_ids
        or event.dedupe_key in state.seen_dedupe_keys
    )
    state.seen_event_ids.add(event.event_id)
    state.seen_terminal_event_ids.add(event.event_id)
    if duplicate:
        return None
    state.seen_dedupe_keys.add(event.dedupe_key)
    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        session_id=event.session_id,
        run_id=event.run_id,
        terminal_event_id=event.event_id,
        event_sequence=event.event_sequence,
        terminal_status=event.terminal_status,
        dedupe_key=event.dedupe_key,
        final_answer=event.final_answer,
        error_message=event.error_message,
        cancel_reason=event.cancel_reason,
        watcher_failure_message=state.watcher_failure_message,
    )


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
                _observation_error_message(
                    state=state,
                    message=(
                        "outbox terminal projection failed: "
                        f"{batch.projection_error_code}: "
                        f"{batch.projection_error_message}"
                    ),
                )
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
                _observation_error_message(
                    state=state,
                    message=(
                        "outbox terminal caught up without matching terminal item: "
                        f"run_id={run_id}, cursor={batch.scanned_watermark.event_sequence}"
                    ),
                )
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
        duplicate = item.dedupe_key in state.seen_dedupe_keys
        state.seen_terminal_event_ids.add(item.terminal_event_id)
        if duplicate:
            continue
        state.seen_dedupe_keys.add(item.dedupe_key)
        if item.run_id == run_id:
            return _terminal_result_from_outbox_item(
                item,
                watcher_failure_message=state.watcher_failure_message,
            )
    return None


def _terminal_result_from_outbox_item(
    item: OutboxTerminalItem,
    *,
    watcher_failure_message: str | None,
) -> EntrypointRunTerminalResult:
    """把 outbox terminal item 转为 entrypoint terminal result。

    :param item: Host public outbox terminal item。
    :param watcher_failure_message: watcher drain 失败诊断消息。
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
        watcher_failure_message=watcher_failure_message,
    )


def _observation_error_message(*, state: _TerminalObservationState, message: str) -> str:
    """把 watcher failure 诊断附加到 terminal observation 错误消息。

    :param state: 本轮本地观察状态。
    :param message: 原始错误消息。
    :returns: 可能包含 watcher failure 诊断的错误消息。
    :raises Exception: 不主动抛出异常。
    """

    if state.watcher_failure_message is None:
        return message
    return f"{message}; {state.watcher_failure_message}"


def _is_terminal_run_status(status: RunStatus) -> bool:
    """判断 RunStatus 是否为终态。

    :param status: Host public RunStatus。
    :returns: 终态返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return status in _TERMINAL_RUN_STATUSES


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
        seen_event_ids=set(),
        seen_terminal_event_ids=set(seen_terminal_event_ids),
        seen_dedupe_keys=set(),
        seen_activity_dedupe_keys=set(),
        outbox_cursor=terminal_cursor,
        watcher_failure_message=None,
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


def _require_positive_poll_interval(value: float) -> None:
    """校验 terminal 轮询间隔为正数。

    :param value: 轮询间隔秒数。
    :returns: ``None``。
    :raises ValueError: 间隔不是正数时抛出。
    """

    if not math.isfinite(value) or value <= 0:
        raise ValueError("poll_interval_seconds must be finite and > 0")
