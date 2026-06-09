"""Fins ingestion job 到 Host wait-resume contract 的适配器。

本模块只把 Fins 自有 durable job record 投影为 Host 已有等待契约，不改变
Host/Engine public contract，也不把 adapter object 塞进工具发现输出。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultMeta, ToolResultSuccess
from dayu.fins.ingestion_runtime import (
    FinsIngestionJobRecord,
    FinsIngestionJobStatus,
    FinsIngestionRuntime,
)
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
from dayu.host.durable.state import WaitRecordRow, WaitResumePolicy
from dayu.host.wait_adapter import (
    WaitAdapterBinding,
    WaitAdapterRegistry,
    WaitExternalJobRefSource,
    WaitPollLost,
    WaitPollNotReady,
    WaitPollReady,
    WaitPollResult,
)

FINS_INGESTION_WAIT_ADAPTER_KEY: Final[WaitAdapterKey] = WaitAdapterKey(
    "poll:fins-ingestion"
)
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

_ACTIVE_STATUSES: Final[frozenset[FinsIngestionJobStatus]] = frozenset(
    {
        FinsIngestionJobStatus.QUEUED,
        FinsIngestionJobStatus.RUNNING,
        FinsIngestionJobStatus.CANCELLING,
    }
)
_ERROR_FINS_JOB_FAILED: Final[str] = "fins_ingestion_job_failed"
_ERROR_FINS_JOB_LOST: Final[str] = "fins_ingestion_job_lost"
_MESSAGE_FINS_JOB_LOST: Final[str] = "Fins ingestion job evidence is missing or unreadable."


@dataclass(frozen=True, slots=True)
class FinsIngestionWaitPollAdapter:
    """Fins ingestion job 的 Host poll adapter。

    :param runtime: Fins ingestion runtime；adapter 只通过 runtime 读取 job 和
        请求取消，不直接访问 Host durable wait records。
    """

    runtime: FinsIngestionRuntime

    @classmethod
    def from_workspace_root(cls, workspace_root: Path) -> "FinsIngestionWaitPollAdapter":
        """由 Fins workspace root 构造 poll adapter。

        :param workspace_root: 已验证的绝对 Fins workspace root。
        :returns: Fins ingestion poll adapter。
        :raises ValueError: workspace root 非法时由 Fins runtime 构造抛出。
        :raises OSError: Fins runtime 仓储初始化失败时抛出。
        """

        runtime = DefaultFinsRuntime.create(
            workspace_root=workspace_root
        ).get_ingestion_runtime()
        return cls(runtime=runtime)

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """观察 Fins job 状态并映射为 Host wait poll 结果。

        :param wait_record: Host wait record 快照。
        :returns: 未就绪、可 resolve 或 lost 的 poll 结果。
        :raises Exception: 非 job evidence 缺失/损坏类异常会按 Host poller
            约定向外抛出并计入 adapter error。
        """

        job_id = _external_job_id_from_wait_record(wait_record)
        if job_id is None:
            return WaitPollLost(_lost_outcome())
        try:
            record = self.runtime.read_job(job_id)
        except (FileNotFoundError, ValueError):
            return WaitPollLost(_lost_outcome())
        if record.status in _ACTIVE_STATUSES:
            return WaitPollNotReady()
        if record.status is FinsIngestionJobStatus.SUCCEEDED:
            return WaitPollReady(_completed_outcome(wait_record.tool_name, record))
        if record.status is FinsIngestionJobStatus.FAILED:
            return WaitPollReady(_failed_outcome(wait_record.tool_name, record))
        if record.status is FinsIngestionJobStatus.CANCELLED:
            return WaitPollReady(_cancelled_outcome(wait_record.tool_name, record))
        return WaitPollLost(_lost_outcome())

    def abandon_wait(self, wait_record: WaitRecordRow) -> None:
        """Host 取消 wait 后请求 Fins job 合作取消。

        :param wait_record: 已取消的 Host wait record 快照。
        :returns: ``None``。
        :raises Exception: 非 job evidence 缺失/损坏类异常会按 Host poller
            约定向外抛出并计入 adapter error。
        """

        job_id = _external_job_id_from_wait_record(wait_record)
        if job_id is None:
            return
        try:
            self.runtime.request_cancel(job_id)
        except (FileNotFoundError, ValueError):
            return


def build_fins_wait_adapter_registry(
    *, workspace_root: Path, tool_names: Sequence[str]
) -> WaitAdapterRegistry:
    """为启用的 Fins awaiting tools 构造 Host wait adapter registry。

    :param workspace_root: 已验证的绝对 Fins workspace root；binding 本身不把
        workspace 写入 Host durable wait record，但 factory 在装配期 fail fast。
    :param tool_names: 本次 Service assembly 中由启用 provider 声明的 Fins
        awaiting 工具名；重复名称视为配置错误。
    :returns: Host wait adapter registry。
    :raises ValueError: 工具名为空、重复或不属于 Fins awaiting 稳定工具名时
        抛出。
    """

    _require_absolute_workspace_root(workspace_root)
    bindings = tuple(
        _binding_for_tool_name(tool_name) for tool_name in _deterministic_tool_names(tool_names)
    )
    return WaitAdapterRegistry(bindings)


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


def _binding_for_tool_name(tool_name: str) -> WaitAdapterBinding:
    """构造单个 Fins awaiting 工具 binding。

    :param tool_name: 已校验的 Fins awaiting 工具名。
    :returns: Host wait adapter binding。
    :raises ValueError: binding 字段非法时由 Host 契约抛出。
    """

    return WaitAdapterBinding(
        tool_name=tool_name,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY,
        resume_policy=WaitResumePolicy.POLL,
        external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
    )


def _external_job_id_from_wait_record(wait_record: WaitRecordRow) -> str | None:
    """从 Host wait record 读取 Fins external job id。

    :param wait_record: Host wait record 快照。
    :returns: external job id；缺失时为 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if wait_record.external_job_ref is None:
        return None
    return wait_record.external_job_ref.external_job_id


def _completed_outcome(
    tool_name: str, record: FinsIngestionJobRecord
) -> ResolveWaitCompletedOutcome:
    """把 succeeded job record 转成 Host completed resolve outcome。

    :param tool_name: 原等待工具名。
    :param record: Fins succeeded job record。
    :returns: Host completed resolve outcome。
    :raises ValueError: outcome 字段非法时由底层契约抛出。
    """

    return ResolveWaitCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value={
                "job_id": record.job_id,
                "operation": record.operation_kind.value,
                "status": record.status.value,
                "ticker": record.normalized_ticker,
                "result": _copy_json_object(record.result_summary),
            },
            meta=_result_meta(tool_name, record),
        ),
        payload_ref=None,
    )


def _failed_outcome(
    tool_name: str, record: FinsIngestionJobRecord
) -> ResolveWaitFailedOutcome:
    """把 failed job record 转成 Host failed resolve outcome。

    :param tool_name: 原等待工具名。
    :param record: Fins failed job record。
    :returns: Host failed resolve outcome。
    :raises ValueError: outcome 字段非法时由底层契约抛出。
    """

    failure_summary = _copy_json_object(record.failure_summary)
    return ResolveWaitFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=_ERROR_FINS_JOB_FAILED,
            message=_failure_message(failure_summary),
            hint="请检查 Fins ingestion job 摘要，必要时重新发起下载或预处理。",
            meta=_result_meta(tool_name, record),
        ),
        payload_ref=None,
    )


def _cancelled_outcome(
    tool_name: str, record: FinsIngestionJobRecord
) -> ResolveWaitCancelledOutcome:
    """把 cancelled job record 转成 Host cancelled resolve outcome。

    :param tool_name: 原等待工具名。
    :param record: Fins cancelled job record。
    :returns: Host cancelled resolve outcome。
    :raises ValueError: outcome 字段非法时由底层契约抛出。
    """

    return ResolveWaitCancelledOutcome(
        result=ToolCancelledOutcome(
            reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
            message="Fins ingestion job was cancelled before completion.",
            hint="如仍需要该财报资料，请重新发起对应下载或预处理任务。",
            meta=_result_meta(tool_name, record),
        ),
        payload_ref=None,
    )


def _lost_outcome() -> ResolveWaitLostOutcome:
    """构造 Fins job evidence lost outcome。

    :returns: Host lost resolve outcome。
    :raises ValueError: lost 字段非法时由底层契约抛出。
    """

    return ResolveWaitLostOutcome(
        reason_code=_ERROR_FINS_JOB_LOST,
        message=_MESSAGE_FINS_JOB_LOST,
        provider_status_ref=None,
    )


def _result_meta(tool_name: str, record: FinsIngestionJobRecord) -> ToolResultMeta:
    """从 Fins job record 构造工具结果元信息。

    :param tool_name: 原等待工具名。
    :param record: Fins job record。
    :returns: ToolResultMeta。
    :raises ValueError: 时间字段非法时由底层契约抛出。
    """

    started_at = _timestamp_or_now(record.started_at or record.created_at)
    finished_at = _timestamp_or_now(record.finished_at or record.updated_at)
    if finished_at < started_at:
        finished_at = started_at
    return ToolResultMeta(
        tool_name=tool_name,
        started_at=started_at,
        finished_at=finished_at,
    )


def _timestamp_or_now(value: str) -> datetime:
    """把 Fins UTC 字符串转成 aware datetime。

    :param value: Fins job record 时间戳。
    :returns: timezone-aware UTC datetime。
    :raises Exception: 不主动抛出异常；非法输入回退为当前 UTC 时间。
    """

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _copy_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """复制 JSON object，避免把 job record 内部字典直接暴露给 outcome。

    :param value: job record 中的 JSON object。
    :returns: 浅复制后的 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    return dict(value)


def _failure_message(failure_summary: dict[str, JsonValue]) -> str:
    """从失败摘要提取面向模型的失败说明。

    :param failure_summary: Fins job 失败摘要。
    :returns: 非空失败说明。
    :raises Exception: 不主动抛出异常。
    """

    message = failure_summary.get("message")
    if isinstance(message, str) and message.strip() != "":
        return message.strip()
    error = failure_summary.get("error")
    if isinstance(error, str) and error.strip() != "":
        return error.strip()
    return "Fins ingestion job failed."
