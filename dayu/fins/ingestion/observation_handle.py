"""Fins awaiting lightweight observation handle 契约。

本模块只定义 tool awaiting 观察长事务 completion 所需的轻量 handle、
状态快照、token 解析和状态到 wait resolution 的中立映射。它不是 CLI
direct event stream，不是 Fins 业务事实真源，也不实现 registry、poller、
wait adapter 或 durable ledger。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Final, Protocol

from dayu.contracts.cancellation import CancellationToken
from dayu.fins.direct_events import (
    FinsErrorKind,
    FinsOperationKind,
    FinsResultSummary,
)

if TYPE_CHECKING:
    from dayu.fins.download_contract import FinsDownloadRequest
    from dayu.fins.ingestion_runtime import (
        FinsPreprocessRequest,
        FinsUploadRequest,
    )

FINS_OBSERVATION_HANDLE_ID_PREFIX: Final[str] = "finsobs_"
"""Fins lightweight observation handle id 的稳定前缀。"""

_HANDLE_ID_MIN_HEX_CHARS: Final[int] = 16
_HANDLE_ID_MAX_CHARS: Final[int] = 96
_MESSAGE_MAX_CHARS: Final[int] = 240
_HANDLE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^{FINS_OBSERVATION_HANDLE_ID_PREFIX}[a-f0-9]{{"
    rf"{_HANDLE_ID_MIN_HEX_CHARS},{_HANDLE_ID_MAX_CHARS}}}$"
)
_DISALLOWED_TOKEN_FRAGMENTS: Final[tuple[str, ...]] = (
    "job",
    "sequence",
    "cursor",
    "resume",
    "token",
    "tool_call",
    "storage",
    ".dayu",
    "/",
    "\\",
)


class FinsObservationStatus(str, Enum):
    """Fins lightweight observation 状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


class FinsObservationPollErrorKind(str, Enum):
    """Fins observation poll 错误分类。"""

    TRANSIENT_UNAVAILABLE = "transient_unavailable"
    PERMANENT_NOT_FOUND = "permanent_not_found"
    PERMANENT_CORRUPT_HANDLE = "permanent_corrupt_handle"


class FinsObservationPollError(Exception):
    """Fins observation poll 的分类异常。

    :param error_kind: 可映射到 Host wait resolution 的 poll 错误分类。
    :param message: 有界、业务可读诊断消息。
    """

    error_kind: FinsObservationPollErrorKind
    message: str

    def __init__(self, error_kind: FinsObservationPollErrorKind, message: str) -> None:
        """初始化 poll 分类异常。

        :param error_kind: poll 错误分类。
        :param message: 诊断消息。
        :returns: ``None``。
        :raises ValueError: 消息为空、过长或包含禁止内容时抛出。
        """

        if not isinstance(error_kind, FinsObservationPollErrorKind):
            raise ValueError("error_kind must be FinsObservationPollErrorKind")
        _validate_message(message)
        super().__init__(message)
        self.error_kind = error_kind
        self.message = message


class FinsObservationResolutionKind(str, Enum):
    """Fins observation 状态映射到 Host wait resolution 的中立分类。"""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


@dataclass(frozen=True, slots=True)
class FinsObservationHandle:
    """Fins awaiting observation 的轻量引用。

    :param handle_id: opaque handle id，只能用于 observation registry 查找。
    :param operation_kind: 当前 Fins 业务操作类型。
    :param created_at: handle 创建时间，必须带时区。
    """

    handle_id: str
    operation_kind: FinsOperationKind
    created_at: datetime

    def __post_init__(self) -> None:
        """校验 handle 字段。

        :returns: ``None``。
        :raises ValueError: handle id 或时间非法时抛出。
        """

        _validate_handle_id(self.handle_id)
        _validate_aware_datetime(self.created_at)


@dataclass(frozen=True, slots=True)
class FinsObservationSnapshot:
    """Fins awaiting observation 的一次 poll 快照。

    :param handle: 被观察的 lightweight handle。
    :param status: 当前 observation 状态。
    :param message: 有界、业务可读诊断消息。
    :param result: terminal 状态的 Fins 业务摘要；非 terminal 状态为空。
    :param error_kind: 可选失败分类。
    :param retry_after_seconds: 建议重试等待秒数；仅 pending/running 可用。
    """

    handle: FinsObservationHandle
    status: FinsObservationStatus
    message: str
    result: FinsResultSummary | None
    error_kind: FinsErrorKind | None
    retry_after_seconds: float | None

    def __post_init__(self) -> None:
        """校验 observation snapshot 字段组合。

        :returns: ``None``。
        :raises ValueError: 字段组合非法时抛出。
        """

        _validate_message(self.message)
        _validate_retry_after(self.status, self.retry_after_seconds)
        if self.status in {
            FinsObservationStatus.SUCCEEDED,
            FinsObservationStatus.FAILED,
            FinsObservationStatus.CANCELLED,
        }:
            if self.result is None:
                raise ValueError("terminal observation snapshot must contain result")
            return
        if self.result is not None:
            raise ValueError("non-terminal observation snapshot must not contain result")


class FinsObservationRuntime(Protocol):
    """Fins awaiting observation runtime 最小协议。

    本协议只描述 tool awaiting 观察面。实现可以使用 process-local registry，
    但不得把该协议实现成 CLI direct job handle、event sidecar 或 durable
    cursor contract。
    """

    def start_observed_download(
        self,
        request: FinsDownloadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动可观察 download operation。

        :param request: Fins download typed request。
        :param cancellation_token: operation-scoped 取消观察 token。
        :returns: lightweight observation handle。
        :raises Exception: 启动失败时由实现抛出。
        """
        ...

    def prepare_observed_download(
        self,
        request: FinsDownloadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记可观察 download operation，但不启动后台执行。

        :param request: Fins download typed request。
        :param cancellation_token: operation-scoped 取消观察 token。
        :returns: lightweight observation handle。
        :raises Exception: prepare 失败时由实现抛出。
        """
        ...

    def start_observed_preprocess(
        self,
        request: FinsPreprocessRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动可观察 preprocess operation。

        :param request: Fins preprocess typed request。
        :param cancellation_token: operation-scoped 取消观察 token。
        :returns: lightweight observation handle。
        :raises Exception: 启动失败时由实现抛出。
        """
        ...

    def prepare_observed_preprocess(
        self,
        request: FinsPreprocessRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记可观察 preprocess operation，但不启动后台执行。

        :param request: Fins preprocess typed request。
        :param cancellation_token: operation-scoped 取消观察 token。
        :returns: lightweight observation handle。
        :raises Exception: prepare 失败时由实现抛出。
        """
        ...

    def start_observed_upload(
        self,
        request: FinsUploadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动可观察 upload operation。

        :param request: Fins upload typed request。
        :param cancellation_token: operation-scoped 取消观察 token。
        :returns: lightweight observation handle。
        :raises Exception: 启动失败时由实现抛出。
        """
        ...

    def prepare_observed_upload(
        self,
        request: FinsUploadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记可观察 upload operation，但不启动后台执行。

        :param request: Fins upload typed request。
        :param cancellation_token: operation-scoped 取消观察 token。
        :returns: lightweight observation handle。
        :raises Exception: prepare 失败时由实现抛出。
        """
        ...

    def activate_observation(self, handle: FinsObservationHandle) -> None:
        """激活已登记的可观察 operation。

        :param handle: lightweight observation handle。
        :returns: ``None``。
        :raises Exception: activation 失败时由实现抛出。
        """
        ...

    async def poll_observation(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot:
        """读取 observation 当前快照。

        :param handle: lightweight observation handle。
        :returns: observation snapshot。
        :raises Exception: 非 poll 分类错误由实现抛出。
        """
        ...

    async def cancel_observation(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot:
        """请求取消 observed operation。

        :param handle: lightweight observation handle。
        :returns: 取消请求后的 observation snapshot。
        :raises Exception: 非 poll 分类错误由实现抛出。
        """
        ...

    async def abandon_observation(self, handle: FinsObservationHandle) -> None:
        """释放不再需要的 observation record。

        :param handle: lightweight observation handle。
        :returns: ``None``。
        :raises Exception: 非 poll 分类错误由实现抛出。
        """
        ...


def observation_handle_id_to_resume_token(handle: FinsObservationHandle) -> str:
    """把 observation handle 投影为 ToolAwaitSpec resume token。

    :param handle: lightweight observation handle。
    :returns: opaque resume token；当前等于 handle id。
    :raises ValueError: handle id 非法时抛出。
    """

    _validate_handle_id(handle.handle_id)
    return handle.handle_id


def parse_observation_handle_id_token(token: str) -> str:
    """从 ToolAwaitSpec resume token 解析 opaque handle id。

    :param token: wait record 中保存的 resume token。
    :returns: handle id。
    :raises ValueError: token 为空、格式非法或包含旧 job/cursor/path 语义时抛出。
    """

    handle_id = token.strip()
    _validate_handle_id(handle_id)
    return handle_id


def observation_status_resolution_kind(
    status: FinsObservationStatus,
) -> FinsObservationResolutionKind:
    """把 observation 状态映射到 Host wait resolution 的中立分类。

    :param status: observation status。
    :returns: wait resolution kind。
    :raises Exception: 不主动抛出异常。
    """

    if status in {FinsObservationStatus.PENDING, FinsObservationStatus.RUNNING}:
        return FinsObservationResolutionKind.PENDING
    if status is FinsObservationStatus.SUCCEEDED:
        return FinsObservationResolutionKind.COMPLETED
    if status is FinsObservationStatus.FAILED:
        return FinsObservationResolutionKind.FAILED
    if status is FinsObservationStatus.CANCELLED:
        return FinsObservationResolutionKind.CANCELLED
    return FinsObservationResolutionKind.LOST


def observation_poll_error_resolution_kind(
    error_kind: FinsObservationPollErrorKind,
) -> FinsObservationResolutionKind:
    """把 observation poll 错误映射到 Host wait resolution 的中立分类。

    :param error_kind: poll 错误分类。
    :returns: transient 错误返回 pending，永久错误返回 lost。
    :raises Exception: 不主动抛出异常。
    """

    if error_kind is FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE:
        return FinsObservationResolutionKind.PENDING
    return FinsObservationResolutionKind.LOST


def _validate_handle_id(handle_id: str) -> None:
    """校验 lightweight observation handle id。

    :param handle_id: 待校验 handle id。
    :returns: ``None``。
    :raises ValueError: handle id 非法时抛出。
    """

    if _HANDLE_ID_PATTERN.fullmatch(handle_id) is None:
        raise ValueError("invalid Fins observation handle id")
    lowered = handle_id.lower()
    for fragment in _DISALLOWED_TOKEN_FRAGMENTS:
        if fragment in lowered:
            raise ValueError("Fins observation handle id contains forbidden text")


def _validate_aware_datetime(value: datetime) -> None:
    """校验 datetime 带有时区。

    :param value: 待校验时间。
    :returns: ``None``。
    :raises ValueError: 时间缺少时区时抛出。
    """

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observation handle created_at must be timezone-aware")


def _validate_message(message: str) -> None:
    """校验 observation snapshot message。

    :param message: 待校验消息。
    :returns: ``None``。
    :raises ValueError: 消息为空、过长或包含禁止内容时抛出。
    """

    if message.strip() == "":
        raise ValueError("observation message must not be empty")
    if len(message) > _MESSAGE_MAX_CHARS:
        raise ValueError("observation message is too long")
    lowered = message.lower()
    for fragment in _DISALLOWED_TOKEN_FRAGMENTS:
        if fragment in lowered:
            raise ValueError("observation message contains forbidden text")


def _validate_retry_after(
    status: FinsObservationStatus,
    retry_after_seconds: float | None,
) -> None:
    """校验 retry-after 字段。

    :param status: snapshot 状态。
    :param retry_after_seconds: 可选重试等待秒数。
    :returns: ``None``。
    :raises ValueError: retry-after 与状态不匹配或数值非法时抛出。
    """

    if retry_after_seconds is None:
        return
    if status not in {FinsObservationStatus.PENDING, FinsObservationStatus.RUNNING}:
        raise ValueError("terminal observation snapshot must not contain retry_after")
    if retry_after_seconds <= 0.0 or not math.isfinite(retry_after_seconds):
        raise ValueError("retry_after_seconds must be a positive finite number")


__all__ = [
    "FINS_OBSERVATION_HANDLE_ID_PREFIX",
    "FinsObservationHandle",
    "FinsObservationPollError",
    "FinsObservationPollErrorKind",
    "FinsObservationResolutionKind",
    "FinsObservationRuntime",
    "FinsObservationSnapshot",
    "FinsObservationStatus",
    "observation_handle_id_to_resume_token",
    "observation_poll_error_resolution_kind",
    "observation_status_resolution_kind",
    "parse_observation_handle_id_token",
]
