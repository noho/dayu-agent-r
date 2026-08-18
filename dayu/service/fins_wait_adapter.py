"""Service 层 Fins awaiting observation 到 Host wait-resume contract 的适配器。

本模块位于 Service composition boundary，只把 Host 投影出的最小 wait
adapter snapshot 映射到 Fins lightweight observation runtime；不读取 Host
durable row、durable store、state mutator 或 Fins storage。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeVar

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultMeta, ToolResultSuccess
from dayu.fins.direct_events import FinsEventDetail, FinsOperationKind, FinsResultSummary
from dayu.fins.company_metadata_warning import company_metadata_warnings_to_json
from dayu.fins.direct_event_text import (
    wait_cancelled_hint,
    wait_cancelled_message,
    wait_failed_hint,
)
from dayu.fins.ingestion.observation_handle import (
    FinsObservationHandle,
    FinsObservationPollError,
    FinsObservationPollErrorKind,
    FinsObservationRuntime,
    FinsObservationSnapshot,
    FinsObservationStatus,
    parse_observation_handle_id_token,
)
from dayu.fins.ingestion.awaiting_resolution import AwaitingResolutionMode
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME
from dayu.fins.tools.preprocess_tools import PREPROCESS_TOOL_NAME
from dayu.fins.tools.upload_tools import UPLOAD_TOOL_NAME
from dayu.host.api import (
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    WaitAdapterKey,
)
from dayu.host.wait_adapter import (
    WaitActivationAdapterRegistration,
    WaitActivationRegistry,
    WaitActivationRequest,
    WaitAdapterBinding,
    WaitAdapterRegistry,
    WaitAdapterSnapshot,
    WaitExternalJobLifecycleAction,
    WaitExternalJobLifecycleApplied,
    WaitExternalJobLifecycleNoop,
    WaitExternalJobLifecycleResult,
    WaitExternalJobRefSource,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollLost,
    WaitPollNotReady,
    WaitPollReady,
    WaitPollResult,
    WaitResumePolicy,
)

FINS_INGESTION_WAIT_ADAPTER_KEY: Final[WaitAdapterKey] = WaitAdapterKey("poll:fins-ingestion")
"""Fins ingestion poll adapter 的稳定 Host adapter key。"""

FINS_DOWNLOAD_AWAITING_TOOL_NAME: Final[str] = DOWNLOAD_TOOL_NAME
"""Fins download awaiting tool 的稳定名称。"""

FINS_PREPROCESS_AWAITING_TOOL_NAME: Final[str] = PREPROCESS_TOOL_NAME
"""Fins preprocess awaiting tool 的稳定名称。"""

FINS_UPLOAD_AWAITING_TOOL_NAME: Final[str] = UPLOAD_TOOL_NAME
"""Fins upload awaiting tool 的稳定名称。"""

FINS_SUPPORTED_AWAITING_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        FINS_DOWNLOAD_AWAITING_TOOL_NAME,
        FINS_PREPROCESS_AWAITING_TOOL_NAME,
        FINS_UPLOAD_AWAITING_TOOL_NAME,
    }
)
"""Fins awaiting 工具稳定名称集合。"""

_ERROR_FINS_OBSERVATION_FAILED: Final[str] = "fins_observation_failed"
_ERROR_FINS_OBSERVATION_LOST: Final[str] = "fins_observation_lost"
_MESSAGE_FINS_OBSERVATION_LOST: Final[str] = "Fins observation is no longer available."
_ABANDON_REASON_INVALID_OBSERVATION_HANDLE: Final[str] = "invalid_observation_handle"
_ABANDON_REASON_OBSERVATION_MISSING: Final[str] = "observation_missing"
_ABANDON_REASON_OBSERVATION_ERROR_PREFIX: Final[str] = "observation_error"
_ABANDON_APPLIED_MESSAGE: Final[str] = (
    "Fins observation cancellation was requested and local observation tracking was released."
)
_ASYNC_RESULT_T = TypeVar("_ASYNC_RESULT_T")


@dataclass(frozen=True, slots=True)
class FinsIngestionWaitPollAdapter:
    """Fins lightweight observation 的 Host poll adapter。

    :param runtime: Fins observation runtime；adapter 只通过 runtime 观察、
        取消或释放 observation，不读取 durable job record。
    """

    runtime: FinsObservationRuntime

    @classmethod
    def from_workspace_root(cls, workspace_root: Path) -> "FinsIngestionWaitPollAdapter":
        """由 Fins workspace root 构造 poll adapter。

        :param workspace_root: 已验证的绝对 Fins workspace root。
        :returns: Fins ingestion poll adapter。
        :raises ValueError: workspace root 非法时由 Fins runtime 构造抛出。
        :raises OSError: Fins runtime 仓储初始化失败时抛出。
        """

        runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
        return cls(runtime=runtime)

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """观察 Fins lightweight observation 并映射为 Host wait poll 结果。

        :param snapshot: Host 投影出的最小 wait adapter snapshot。
        :returns: 未就绪、可 resolve 或 lost 的 poll 结果。
        :raises Exception: 非 observation 缺失、损坏或 transient 类异常会按
            Host poller 约定向外抛出并计入 adapter error。
        """

        handle = _handle_from_snapshot(snapshot)
        if handle is None:
            return WaitPollLost(_lost_outcome())
        try:
            observation_snapshot = _run_async_observation(self.runtime.poll_observation(handle))
        except FinsObservationPollError as exc:
            return _poll_error_result(exc)
        return _poll_snapshot_result(snapshot.tool_name, observation_snapshot)

    def abandon_wait(
        self,
        snapshot: WaitAdapterSnapshot,
    ) -> WaitExternalJobLifecycleResult:
        """Host 放弃 wait 后 best-effort 取消并释放 Fins observation。

        :param snapshot: Host 投影出的最小 wait adapter snapshot。
        :returns: Host 外部 job lifecycle typed 结果；Fins 当前只在释放本地
            observation handle 后返回 ``ABANDON`` applied，无法继续处理时返回
            no-op。
        :raises FinsObservationPollError: runtime 临时不可用时按原异常抛出，
            交给 Host poller 退避重试。
        """

        handle = _handle_from_snapshot(snapshot)
        if handle is None:
            return WaitExternalJobLifecycleNoop(reason=_ABANDON_REASON_INVALID_OBSERVATION_HANDLE)
        try:
            observation_snapshot = _run_async_observation(self.runtime.cancel_observation(handle))
            if observation_snapshot.status is FinsObservationStatus.LOST:
                return WaitExternalJobLifecycleNoop(reason=_ABANDON_REASON_OBSERVATION_MISSING)
            _run_async_observation(self.runtime.abandon_observation(handle))
            return WaitExternalJobLifecycleApplied(
                action=WaitExternalJobLifecycleAction.ABANDON,
                message=_ABANDON_APPLIED_MESSAGE,
            )
        except FinsObservationPollError as exc:
            if exc.error_kind is FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE:
                raise
            if exc.error_kind is FinsObservationPollErrorKind.PERMANENT_NOT_FOUND:
                return WaitExternalJobLifecycleNoop(reason=_ABANDON_REASON_OBSERVATION_MISSING)
            return WaitExternalJobLifecycleNoop(reason=_observation_error_reason(exc.error_kind))


@dataclass(frozen=True, slots=True)
class FinsIngestionWaitActivationAdapter:
    """Fins lightweight observation 的 Host accepted-wait activation adapter。

    :param runtime: Fins observation runtime；adapter 只解析已有 resume token
        并触发 runtime activation。
    """

    runtime: FinsObservationRuntime

    def activate_accepted_wait(self, request: WaitActivationRequest) -> None:
        """激活 Host 已 durable accepted 的 Fins observation。

        :param request: Host accepted wait activation 请求。
        :returns: ``None``。
        :raises ValueError: resume token 或工具名无法解析时抛出。
        :raises Exception: runtime activation 失败时按原异常抛出。
        """

        handle_id = parse_observation_handle_id_token(request.await_spec.resume_token)
        handle = FinsObservationHandle(
            handle_id=handle_id,
            operation_kind=_operation_kind_from_tool_name(request.tool_name),
            created_at=datetime.now(timezone.utc),
        )
        self.runtime.activate_observation(handle)


def build_fins_wait_adapter_registry(
    *,
    workspace_root: Path,
    tool_modes: Sequence[tuple[str, AwaitingResolutionMode]],
) -> WaitAdapterRegistry:
    """为启用的 Fins awaiting tools 构造 Host wait adapter registry。

    :param workspace_root: 已验证的绝对 Fins workspace root；binding 本身不把
        workspace 写入 Host durable wait record，但 factory 在装配期 fail fast。
    :param tool_modes: 本次 Service assembly 中 active Fins awaiting 工具名与
        owner-parsed typed mode；重复名称视为配置错误。
    :returns: Host wait adapter registry。
    :raises ValueError: 工具名为空、重复或不属于 Fins awaiting 稳定工具名时
        抛出。
    """

    _require_absolute_workspace_root(workspace_root)
    bindings = tuple(
        _binding_for_tool_name(tool_name, mode) for tool_name, mode in _deterministic_tool_modes(tool_modes)
    )
    return WaitAdapterRegistry(bindings)


def build_fins_wait_activation_registry(
    *, runtime: FinsObservationRuntime, tool_names: Sequence[str]
) -> WaitActivationRegistry:
    """为启用的 Fins awaiting tools 构造 Host activation registry。

    activation adapter 必须接收 awaiting tool callable 使用的同一个 runtime；
    该 runtime 保存 process-local prepared observation，不能由 builder 自建。

    :param runtime: Fins awaiting tool callable 使用的共享 observation runtime。
    :param tool_names: 本次 Service assembly 中由启用 provider 声明的 Fins
        awaiting 工具名；重复名称视为配置错误。
    :returns: Host wait activation registry。
    :raises ValueError: 工具名为空、重复或不属于 Fins awaiting 稳定工具名时
        抛出。
    """

    # activation 由单个 adapter key 分发，tool_names 只用于装配期校验。
    _deterministic_tool_names(tool_names)
    adapter = FinsIngestionWaitActivationAdapter(runtime=runtime)
    return WaitActivationRegistry(
        (
            WaitActivationAdapterRegistration(
                adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY,
                adapter=adapter,
            ),
        )
    )


def build_fins_wait_poll_adapter_registry(
    *, runtime: FinsObservationRuntime, tool_names: Sequence[str]
) -> WaitPollAdapterRegistry:
    """为启用的 Fins awaiting tools 构造 Host poll adapter registry。

    :param runtime: Fins awaiting tool callable 使用的共享 observation runtime。
    :param tool_names: 本次 Service assembly 中由启用 provider 声明的 Fins
        awaiting 工具名；重复名称视为配置错误。
    :returns: Host wait poll adapter registry。
    :raises ValueError: 工具名为空、重复或不属于 Fins awaiting 稳定工具名时
        抛出。
    """

    # poll adapter 由单个 adapter key 分发，tool_names 只用于装配期校验。
    _deterministic_tool_names(tool_names)
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)
    return WaitPollAdapterRegistry(
        (
            WaitPollAdapterRegistration(
                adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY,
                adapter=adapter,
            ),
        )
    )


def _require_absolute_workspace_root(workspace_root: Path) -> None:
    """校验 Fins wait adapter workspace root。

    :param workspace_root: Fins workspace root。
    :returns: ``None``。
    :raises ValueError: 路径不是绝对路径时抛出。
    """

    if not workspace_root.is_absolute():
        raise ValueError("Fins wait adapter workspace_root must be absolute")


def _deterministic_tool_names(tool_names: Sequence[str]) -> tuple[str, ...]:
    """校验并稳定排序 Fins awaiting 工具名。

    :param tool_names: 待绑定工具名。
    :returns: 按字典序排序后的工具名元组。
    :raises ValueError: 工具名为空、重复或不受支持时抛出。
    """

    seen: set[str] = set()
    ordered: list[str] = []
    for tool_name in tool_names:
        normalized = tool_name.strip()
        if normalized == "":
            raise ValueError("Fins wait adapter tool_name must be non-empty")
        if normalized not in FINS_SUPPORTED_AWAITING_TOOL_NAMES:
            raise ValueError(f"unsupported Fins wait adapter tool: {normalized}")
        if normalized in seen:
            raise ValueError(f"duplicate Fins wait adapter binding: {normalized}")
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(sorted(ordered))


def _deterministic_tool_modes(
    tool_modes: Sequence[tuple[str, AwaitingResolutionMode]],
) -> tuple[tuple[str, AwaitingResolutionMode], ...]:
    """校验并稳定排序 Fins awaiting 工具与 typed mode。

    :param tool_modes: 待绑定的工具名与 Fins owner-parsed mode。
    :returns: 按工具名字典序排序的 typed pair。
    :raises TypeError: mode 不是 ``AwaitingResolutionMode`` 时抛出。
    :raises ValueError: 工具名为空、重复或不受支持时抛出。
    """

    names = _deterministic_tool_names(tuple(item[0] for item in tool_modes))
    mode_by_name: dict[str, AwaitingResolutionMode] = {}
    for tool_name, mode in tool_modes:
        if not isinstance(mode, AwaitingResolutionMode):
            raise TypeError("Fins wait adapter mode must be AwaitingResolutionMode")
        mode_by_name[tool_name.strip()] = mode
    return tuple((tool_name, mode_by_name[tool_name]) for tool_name in names)


def _binding_for_tool_name(tool_name: str, mode: AwaitingResolutionMode) -> WaitAdapterBinding:
    """构造单个 Fins awaiting 工具 binding。

    :param tool_name: 已校验的 Fins awaiting 工具名。
    :param mode: Fins owner 已解析的恢复模式。
    :returns: Host wait adapter binding。
    :raises ValueError: binding 字段非法时由 Host 契约抛出。
    """

    return WaitAdapterBinding(
        tool_name=tool_name,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY,
        resume_policy=_wait_resume_policy_from_mode(mode),
        external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
    )


def _wait_resume_policy_from_mode(
    mode: AwaitingResolutionMode,
) -> WaitResumePolicy:
    """把 Fins typed 恢复模式映射为 Host binding policy。

    :param mode: Fins owner 已解析的恢复模式。
    :returns: 精确对应的 Host wait resume policy。
    :raises ValueError: 收到未知 enum 成员时抛出。
    """

    if mode is AwaitingResolutionMode.POLL:
        return WaitResumePolicy.POLL
    if mode is AwaitingResolutionMode.CALLBACK:
        return WaitResumePolicy.CALLBACK
    if mode is AwaitingResolutionMode.MANUAL:
        return WaitResumePolicy.MANUAL
    raise ValueError(f"unsupported Fins awaiting resolution mode: {mode}")


def _handle_from_snapshot(snapshot: WaitAdapterSnapshot) -> FinsObservationHandle | None:
    """从 Host adapter snapshot 恢复 typed observation handle。

    :param snapshot: Host 投影出的最小 wait adapter snapshot。
    :returns: observation handle；token 损坏或工具名不支持时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    try:
        handle_id = parse_observation_handle_id_token(snapshot.resume_token)
        operation_kind = _operation_kind_from_tool_name(snapshot.tool_name)
    except ValueError:
        return None
    return FinsObservationHandle(
        handle_id=handle_id,
        operation_kind=operation_kind,
        created_at=snapshot.created_at,
    )


def _operation_kind_from_tool_name(tool_name: str) -> FinsOperationKind:
    """按 awaiting 工具名推导 observation operation kind。

    :param tool_name: Host wait record 中的工具名。
    :returns: Fins operation kind。
    :raises ValueError: 工具名不受支持时抛出。
    """

    if tool_name == FINS_DOWNLOAD_AWAITING_TOOL_NAME:
        return FinsOperationKind.DOWNLOAD
    if tool_name == FINS_PREPROCESS_AWAITING_TOOL_NAME:
        return FinsOperationKind.PREPROCESS
    if tool_name == FINS_UPLOAD_AWAITING_TOOL_NAME:
        return FinsOperationKind.UPLOAD
    raise ValueError(f"unsupported Fins observation wait tool: {tool_name}")


def _poll_error_result(
    exc: FinsObservationPollError,
) -> WaitPollResult:
    """把 observation poll 错误映射为 Host poll result。

    :param exc: observation poll 分类异常。
    :returns: poll result。
    :raises Exception: 不主动抛出异常。
    """

    if exc.error_kind is FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE:
        return WaitPollNotReady()
    return WaitPollLost(_lost_outcome())


def _observation_error_reason(error_kind: FinsObservationPollErrorKind) -> str:
    """把 observation 非临时错误分类映射为稳定 no-op reason。

    :param error_kind: observation 错误分类。
    :returns: Host lifecycle no-op 稳定原因。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_ABANDON_REASON_OBSERVATION_ERROR_PREFIX}:{error_kind.value}"


def _poll_snapshot_result(
    tool_name: str,
    snapshot: FinsObservationSnapshot,
) -> WaitPollResult:
    """把 observation snapshot 映射为 Host poll result。

    :param tool_name: 原等待工具名。
    :param snapshot: observation snapshot。
    :returns: poll result。
    :raises ValueError: terminal snapshot 缺少 result 时由 outcome 构造抛出。
    """

    if snapshot.status in {FinsObservationStatus.PENDING, FinsObservationStatus.RUNNING}:
        return WaitPollNotReady()
    if snapshot.status is FinsObservationStatus.SUCCEEDED:
        return WaitPollReady(_completed_outcome(tool_name, snapshot))
    if snapshot.status is FinsObservationStatus.FAILED:
        return WaitPollReady(_failed_outcome(tool_name, snapshot))
    if snapshot.status is FinsObservationStatus.CANCELLED:
        return WaitPollReady(_cancelled_outcome(tool_name, snapshot))
    return WaitPollLost(_lost_outcome())


def _completed_outcome(tool_name: str, snapshot: FinsObservationSnapshot) -> ResolveWaitCompletedOutcome:
    """把 succeeded observation 转成 Host completed resolve outcome。

    :param tool_name: 原等待工具名。
    :param snapshot: Fins succeeded observation snapshot。
    :returns: Host completed resolve outcome。
    :raises ValueError: outcome 字段非法时由底层契约抛出。
    """

    result = _required_result(snapshot)
    return ResolveWaitCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value=_completed_result_value(snapshot, result),
            meta=_result_meta(tool_name, snapshot),
        ),
        payload_ref=None,
    )


def _failed_outcome(tool_name: str, snapshot: FinsObservationSnapshot) -> ResolveWaitFailedOutcome:
    """把 failed observation 转成 Host failed resolve outcome。

    :param tool_name: 原等待工具名。
    :param snapshot: Fins failed observation snapshot。
    :returns: Host failed resolve outcome。
    :raises ValueError: outcome 字段非法时由底层契约抛出。
    """

    result = _required_result(snapshot)
    return ResolveWaitFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=_ERROR_FINS_OBSERVATION_FAILED,
            message=_failure_message(result),
            hint=(result.failure.retry_hint if result.failure is not None else wait_failed_hint()),
            meta=_result_meta(tool_name, snapshot),
        ),
        payload_ref=None,
    )


def _cancelled_outcome(tool_name: str, snapshot: FinsObservationSnapshot) -> ResolveWaitCancelledOutcome:
    """把 cancelled observation 转成 Host cancelled resolve outcome。

    :param tool_name: 原等待工具名。
    :param snapshot: Fins cancelled observation snapshot。
    :returns: Host cancelled resolve outcome。
    :raises ValueError: outcome 字段非法时由底层契约抛出。
    """

    return ResolveWaitCancelledOutcome(
        result=ToolCancelledOutcome(
            reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
            message=wait_cancelled_message(),
            hint=wait_cancelled_hint(),
            meta=_result_meta(tool_name, snapshot),
        ),
        payload_ref=None,
    )


def _lost_outcome() -> ResolveWaitLostOutcome:
    """构造 Fins observation lost outcome。

    :returns: Host lost resolve outcome。
    :raises ValueError: lost 字段非法时由底层契约抛出。
    """

    return ResolveWaitLostOutcome(
        reason_code=_ERROR_FINS_OBSERVATION_LOST,
        message=_MESSAGE_FINS_OBSERVATION_LOST,
        provider_status_ref=None,
    )


def _required_result(snapshot: FinsObservationSnapshot) -> FinsResultSummary:
    """读取 terminal observation result。

    :param snapshot: observation snapshot。
    :returns: terminal result summary。
    :raises ValueError: snapshot 缺少 result 时抛出。
    """

    if snapshot.result is None:
        raise ValueError("terminal Fins observation must contain result")
    return snapshot.result


def _details_value(details: tuple[FinsEventDetail, ...]) -> list[JsonValue]:
    """把 result details 转成 JSON-compatible 值。

    :param details: Fins event details。
    :returns: JSON-compatible details 列表。
    :raises Exception: 不主动抛出异常。
    """

    return [{"label": detail.label, "value": detail.value} for detail in details]


def _completed_result_value(
    snapshot: FinsObservationSnapshot,
    result: FinsResultSummary,
) -> dict[str, JsonValue]:
    """从 terminal typed object 构造 LLM-facing 成功值。

    :param snapshot: terminal observation snapshot。
    :param result: 同一 observation 的 terminal result。
    :returns: completed value 恒包含 ``warnings`` 数组，非 upload 自然为空 ``[]``；
        download 使用 nested 自解释对象，其它 operation 保持业务 details。
    :raises Exception: 不主动抛出异常。
    """

    value: dict[str, JsonValue] = {
        "operation": snapshot.handle.operation_kind.value,
        "status": result.status.value,
        "title": result.title,
        "warnings": company_metadata_warnings_to_json(result.warnings),
    }
    if result.download is not None:
        value["download"] = result.download.to_json_value()
    else:
        value["details"] = _details_value(result.details)
    return value


def _failure_message(result: FinsResultSummary) -> str:
    """提取模型可读失败说明。

    :param result: terminal result summary。
    :returns: 非空失败说明。
    :raises ValueError: failed result 缺少业务可读失败说明时抛出。
    """

    if result.failure is not None:
        if result.download is None:
            raise ValueError("typed download failure must contain download summary")
        return json.dumps(
            {
                "operation": FinsOperationKind.DOWNLOAD.value,
                "status": result.status.value,
                "title": result.title,
                "download": result.download.to_json_value(),
                "failure": result.failure.to_json_value(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if result.error_message is not None and result.error_message.strip() != "":
        return result.error_message.strip()
    raise ValueError("failed Fins observation result must contain error_message")


def _result_meta(tool_name: str, snapshot: FinsObservationSnapshot) -> ToolResultMeta:
    """从 observation snapshot 构造工具结果元信息。

    :param tool_name: 原等待工具名。
    :param snapshot: Fins observation snapshot。
    :returns: ToolResultMeta。
    :raises ValueError: 时间字段非法时由底层契约抛出。
    """

    started_at = snapshot.handle.created_at
    finished_at = datetime.now(timezone.utc)
    if finished_at < started_at:
        finished_at = started_at
    return ToolResultMeta(
        tool_name=tool_name,
        started_at=started_at,
        finished_at=finished_at,
    )


def _run_async_observation(operation: Coroutine[None, None, _ASYNC_RESULT_T]) -> _ASYNC_RESULT_T:
    """在 sync Host adapter 内执行 observation runtime async 方法。

    :param operation: observation runtime coroutine。
    :returns: coroutine 返回值。
    :raises RuntimeError: 当前线程已有运行中的 event loop 时抛出。
    :raises Exception: coroutine 内部异常按原样抛出。
    """

    return asyncio.run(operation)
