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
_OUTBOX_TERMINAL_READ_LIMIT: Final[int] = 50
_WATCHER_FAILURE_DIAGNOSTIC_PREFIX: Final[str] = "watcher drain failed"
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
    poll_interval_seconds: float = DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> EntrypointRunTerminalResult:
    """提交 entrypoint 单轮输入并等待同一 Run 终态。

    :param host: Host public Protocol handle。
    :param request: 单轮 entrypoint turn 请求。
    :param scene_inputs: ScenePrepare 输出。
    :param host_assembly: Host opener assembly 结果。
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
        return await _wait_for_terminal(
            host,
            session_id=request.session_id,
            run_id=followup.accepted_run_id,
            queue=queue,
            state=state,
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
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
        )
    watcher = _attach_watcher(host, run_snapshot.session_id)
    queue: asyncio.Queue[HostEvent | _WatcherFailure] = asyncio.Queue()
    drain_task = asyncio.create_task(_drain_host_events(watcher, queue))
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
        return await _wait_for_terminal(
            host,
            session_id=run_snapshot.session_id,
            run_id=request.run_id,
            queue=queue,
            state=state,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
        )
    finally:
        await _close_watcher(watcher=watcher, drain_task=drain_task)


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
    :raises Exception: watcher ``aclose`` 失败时向上抛出。
    """

    await watcher.aclose()
    drain_task.cancel()
    try:
        await drain_task
    except asyncio.CancelledError:
        return


async def _wait_for_terminal(
    host: Host,
    *,
    session_id: str,
    run_id: str,
    queue: asyncio.Queue[HostEvent | _WatcherFailure],
    state: _TerminalObservationState,
    poll_interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
) -> EntrypointRunTerminalResult:
    """等待指定 Run 的 live 或 outbox terminal。

    :param host: Host public Protocol handle。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :param queue: watcher drain queue。
    :param state: 本轮本地观察状态。
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
        )
        if live_terminal is not None:
            return live_terminal
        run_snapshot = await host.get_run(run_id)
        if _is_terminal_run_status(run_snapshot.status):
            outbox_terminal = await _read_outbox_terminal(
                host,
                session_id=session_id,
                run_id=run_id,
                state=state,
            )
            if outbox_terminal is not None:
                return outbox_terminal
        await sleep(poll_interval_seconds)


def _drain_available_watcher_items(
    *,
    queue: asyncio.Queue[HostEvent | _WatcherFailure],
    state: _TerminalObservationState,
    run_id: str,
) -> EntrypointRunTerminalResult | None:
    """消费当前 queue 中已到达的 watcher item。

    :param queue: watcher drain queue。
    :param state: 本轮本地观察状态。
    :param run_id: 目标 Run id。
    :returns: 命中的 terminal result；没有命中时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
        if isinstance(item, _WatcherFailure):
            _record_watcher_failure(state=state, error=item.error)
            continue
        terminal = _terminal_result_from_live_event(
            item,
            run_id=run_id,
            state=state,
        )
        if terminal is not None:
            return terminal


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
    duplicate = event.event_id in state.seen_event_ids or event.dedupe_key in state.seen_dedupe_keys
    state.seen_event_ids.add(event.event_id)
    if event.terminal_status is not None:
        state.seen_terminal_event_ids.add(event.event_id)
    if duplicate:
        return None
    state.seen_dedupe_keys.add(event.dedupe_key)
    if event.run_id != run_id or event.terminal_status is None:
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


def _new_terminal_observation_state() -> _TerminalObservationState:
    """创建单次 terminal observation 状态。

    :returns: 初始 observation state。
    :raises Exception: 不主动抛出异常。
    """

    return _TerminalObservationState(
        last_observed_event_sequence=0,
        seen_event_ids=set(),
        seen_terminal_event_ids=set(),
        seen_dedupe_keys=set(),
        outbox_cursor=None,
        watcher_failure_message=None,
    )


def _require_positive_poll_interval(value: float) -> None:
    """校验 terminal 轮询间隔为正数。

    :param value: 轮询间隔秒数。
    :returns: ``None``。
    :raises ValueError: 间隔不是正数时抛出。
    """

    if not math.isfinite(value) or value <= 0:
        raise ValueError("poll_interval_seconds must be finite and > 0")
