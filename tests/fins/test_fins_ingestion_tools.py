"""Fins download/preprocess/upload awaiting tools provider 测试。"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeGuard

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolAwaitingOutcome,
    ToolCancelledOutcome,
    ToolFailedOutcome,
)
from dayu.fins.download_contract import FinsDownloadRequest
from dayu.fins.ingestion_runtime import (
    FinsIngestionExecutor,
    FinsIngestionRuntime,
    FinsPreprocessRequest,
    FinsUploadRequest,
)
from dayu.fins.ingestion import (
    FINS_OBSERVATION_HANDLE_ID_PREFIX,
    FinsObservationHandle,
    FinsObservationPollError,
    FinsObservationPollErrorKind,
    FinsObservationResolutionKind,
    FinsObservationRuntime,
    FinsObservationSnapshot,
    FinsObservationStatus,
    observation_handle_id_to_resume_token,
    observation_poll_error_resolution_kind,
    observation_status_resolution_kind,
    parse_observation_handle_id_token,
)
from dayu.fins.ingestion.awaiting_resolution import (
    AwaitingResolutionMode,
    parse_awaiting_resolution_mode,
)
from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_CANCELLED,
    FINS_RESULT_EXIT_FAILURE,
    FINS_RESULT_EXIT_SUCCESS,
    FinsErrorKind,
    FinsEventDetail,
    FinsOperationKind,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools import download_provider, preprocess_provider, provider as read_provider
from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME, FinsDownloadToolCallable
from dayu.fins.tools.preprocess_tools import PREPROCESS_TOOL_NAME, FinsPreprocessToolCallable
from dayu.fins.tools import upload_provider
from dayu.fins.tools.upload_tools import UPLOAD_TOOL_NAME, FinsUploadToolCallable
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)

_READ_PROVIDER_ID = "financial-read-tools"
_DOWNLOAD_PROVIDER_ID = "financial-download-tools"
_PREPROCESS_PROVIDER_ID = "financial-preprocess-tools"
_UPLOAD_PROVIDER_ID = "financial-upload-tools"
_READ_SPEC_ID = "financial-read-tools"
_DOWNLOAD_SPEC_ID = "financial-download-tools"
_PREPROCESS_SPEC_ID = "financial-preprocess-tools"
_UPLOAD_SPEC_ID = "financial-upload-tools"
_READ_SAMPLE_TOOL_NAME: Final[str] = "list_documents"
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_PACKAGE_CONFIG_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "dayu" / "config"
_DOWNLOAD_TOOLS_PATH: Final[Path] = _REPO_ROOT / "dayu" / "fins" / "tools" / "download_tools.py"
_PREPROCESS_TOOLS_PATH: Final[Path] = _REPO_ROOT / "dayu" / "fins" / "tools" / "preprocess_tools.py"
_UPLOAD_TOOLS_PATH: Final[Path] = _REPO_ROOT / "dayu" / "fins" / "tools" / "upload_tools.py"
_FORBIDDEN_CANCELLED_MESSAGE_FRAGMENTS: Final[tuple[str, ...]] = ("host", "Host")
_OBSERVATION_TIME: Final[datetime] = datetime(2026, 6, 16, tzinfo=timezone.utc)
_OBSERVATION_HANDLE_ID: Final[str] = f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}aaaaaaaaaaaaaaaa"


@pytest.mark.parametrize(
    ("raw_mode", "expected"),
    (
        ("poll", AwaitingResolutionMode.POLL),
        ("callback", AwaitingResolutionMode.CALLBACK),
        ("manual", AwaitingResolutionMode.MANUAL),
    ),
)
def test_awaiting_resolution_mode_parser_accepts_closed_typed_modes(
    raw_mode: str,
    expected: AwaitingResolutionMode,
) -> None:
    """Fins 唯一 parser 必须精确接受三种 closed mode。

    :param raw_mode: provider config 原始字符串。
    :param expected: 预期 typed enum。
    :returns: ``None``。
    :raises AssertionError: parser 未返回精确 enum 时抛出。
    """

    assert parse_awaiting_resolution_mode({"awaiting_resolution_mode": raw_mode}) is expected


@pytest.mark.parametrize(
    "config",
    (
        {},
        {"awaiting_resolution_mode": None},
        {"awaiting_resolution_mode": 1},
        {"awaiting_resolution_mode": True},
        {"awaiting_resolution_mode": ""},
        {"awaiting_resolution_mode": "POLL"},
        {"awaiting_resolution_mode": " poll"},
        {"awaiting_resolution_mode": "automatic"},
    ),
)
def test_awaiting_resolution_mode_parser_rejects_missing_or_illegal_values(
    config: Mapping[str, JsonValue],
) -> None:
    """Fins 唯一 parser 不得默认、trim 或 loose parse raw mode。

    :param config: 非法 provider config。
    :returns: ``None``。
    :raises AssertionError: 非法值未失败时抛出。
    """

    with pytest.raises(ValueError, match="awaiting_resolution_mode"):
        parse_awaiting_resolution_mode(config)


@pytest.mark.parametrize(
    ("provider", "spec_id", "import_path"),
    (
        (
            download_provider.discover_tools,
            _DOWNLOAD_SPEC_ID,
            "dayu.fins.tools.download_provider:discover_tools",
        ),
        (
            preprocess_provider.discover_tools,
            _PREPROCESS_SPEC_ID,
            "dayu.fins.tools.preprocess_provider:discover_tools",
        ),
        (
            upload_provider.discover_tools,
            _UPLOAD_SPEC_ID,
            "dayu.fins.tools.upload_provider:discover_tools",
        ),
    ),
)
def test_each_fins_awaiting_provider_validates_mode_before_runtime_creation(
    tmp_path: Path,
    provider: Callable[[ToolsDiscoveryProviderSpec], ToolsDiscoveryProviderOutput],
    spec_id: str,
    import_path: str,
) -> None:
    """三个 Fins provider 的直接 discovery 都必须先走同一 parser。

    :param tmp_path: pytest 临时目录。
    :param provider: 本 case 的 provider callable。
    :param spec_id: provider spec id。
    :param import_path: provider import path。
    :returns: ``None``。
    :raises AssertionError: 非法 mode 未在 runtime 创建前失败时抛出。
    """

    with pytest.raises(ValueError, match="awaiting_resolution_mode"):
        provider(
            ToolsDiscoveryProviderSpec(
                spec_id=spec_id,
                location=PythonImportPathProvider(import_path=import_path),
                enabled=True,
                config={
                    "workspace_root": str(tmp_path.resolve(strict=False)),
                    "awaiting_resolution_mode": "POLL",
                },
            )
        )


def test_observation_handle_resume_token_is_opaque_handle_id() -> None:
    """observation resume token 必须只承载 opaque handle id。"""

    handle = _observation_handle()

    token = observation_handle_id_to_resume_token(handle)

    assert token == _OBSERVATION_HANDLE_ID
    assert parse_observation_handle_id_token(token) == _OBSERVATION_HANDLE_ID
    assert "job" not in token
    assert "sequence" not in token
    assert "cursor" not in token
    assert "/" not in token


@pytest.mark.parametrize(
    "token",
    (
        "",
        "finsjob_1234567890abcdef1234567890abcdef",
        f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}gggggggggggggggg",
        f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}jobaaaaaaaaaaaaaaaa",
        f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}cursoraaaaaaaaaaaa",
        f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}aaaaaaaaaaaa/path",
    ),
)
def test_observation_handle_corrupt_token_maps_to_lost(token: str) -> None:
    """corrupt token 必须能被 wait adapter 分类为 LOST。"""

    with pytest.raises(ValueError):
        parse_observation_handle_id_token(token)

    assert (
        observation_poll_error_resolution_kind(FinsObservationPollErrorKind.PERMANENT_CORRUPT_HANDLE)
        is FinsObservationResolutionKind.LOST
    )


def test_process_local_missing_observation_maps_to_lost() -> None:
    """process-local observation source 找不到 handle 时必须分类为 LOST。"""

    assert (
        observation_poll_error_resolution_kind(FinsObservationPollErrorKind.PERMANENT_NOT_FOUND)
        is FinsObservationResolutionKind.LOST
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (FinsObservationStatus.PENDING, FinsObservationResolutionKind.PENDING),
        (FinsObservationStatus.RUNNING, FinsObservationResolutionKind.PENDING),
        (FinsObservationStatus.SUCCEEDED, FinsObservationResolutionKind.COMPLETED),
        (FinsObservationStatus.FAILED, FinsObservationResolutionKind.FAILED),
        (FinsObservationStatus.CANCELLED, FinsObservationResolutionKind.CANCELLED),
        (FinsObservationStatus.LOST, FinsObservationResolutionKind.LOST),
    ),
)
def test_observation_status_resolution_mapping_is_fixed(
    status: FinsObservationStatus,
    expected: FinsObservationResolutionKind,
) -> None:
    """observation status 到 wait resolution 的映射必须固定。"""

    assert observation_status_resolution_kind(status) is expected


def test_observation_snapshot_terminal_and_retry_after_contract() -> None:
    """observation snapshot 必须区分 terminal result 与 retry-after。"""

    terminal = FinsObservationSnapshot(
        handle=_observation_handle(),
        status=FinsObservationStatus.SUCCEEDED,
        message="download completed",
        result=_observation_result(FinsResultStatus.SUCCESS),
        error_kind=None,
        retry_after_seconds=None,
    )
    pending = FinsObservationSnapshot(
        handle=_observation_handle(),
        status=FinsObservationStatus.RUNNING,
        message="download running",
        result=None,
        error_kind=None,
        retry_after_seconds=0.5,
    )

    assert terminal.result is not None
    assert pending.retry_after_seconds == 0.5
    with pytest.raises(ValueError, match="terminal observation snapshot"):
        FinsObservationSnapshot(
            handle=_observation_handle(),
            status=FinsObservationStatus.FAILED,
            message="download failed",
            result=None,
            error_kind=FinsErrorKind.EXECUTION,
            retry_after_seconds=None,
        )
    with pytest.raises(ValueError, match="non-terminal observation snapshot"):
        FinsObservationSnapshot(
            handle=_observation_handle(),
            status=FinsObservationStatus.RUNNING,
            message="download running",
            result=_observation_result(FinsResultStatus.SUCCESS),
            error_kind=None,
            retry_after_seconds=None,
        )


def test_observation_contract_rejects_job_cursor_and_storage_text() -> None:
    """observation contract 不允许暴露 job、sequence、cursor 或 storage path。"""

    with pytest.raises(ValueError):
        FinsObservationHandle(
            handle_id=f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}jobaaaaaaaaaaaaaaaa",
            operation_kind=FinsOperationKind.DOWNLOAD,
            created_at=_OBSERVATION_TIME,
        )
    with pytest.raises(ValueError):
        FinsObservationSnapshot(
            handle=_observation_handle(),
            status=FinsObservationStatus.LOST,
            message="cursor /tmp/fins evidence missing",
            result=None,
            error_kind=FinsErrorKind.UNKNOWN,
            retry_after_seconds=None,
        )


def _observation_handle() -> FinsObservationHandle:
    """构造测试用 lightweight observation handle。

    :returns: Fins observation handle。
    :raises ValueError: 构造字段违反 contract 时抛出。
    """

    return FinsObservationHandle(
        handle_id=_OBSERVATION_HANDLE_ID,
        operation_kind=FinsOperationKind.DOWNLOAD,
        created_at=_OBSERVATION_TIME,
    )


def _observation_handle_with_id(hex_suffix: str) -> FinsObservationHandle:
    """按指定 hex suffix 构造 observation handle。

    :param hex_suffix: handle id 的十六进制 suffix。
    :returns: Fins observation handle。
    :raises ValueError: handle 字段违反 contract 时抛出。
    """

    return FinsObservationHandle(
        handle_id=f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}{hex_suffix}",
        operation_kind=FinsOperationKind.DOWNLOAD,
        created_at=_OBSERVATION_TIME,
    )


def _observation_snapshot(
    handle: FinsObservationHandle,
    status: FinsObservationStatus,
) -> FinsObservationSnapshot:
    """构造测试用 observation snapshot。

    :param handle: observation handle。
    :param status: 目标 observation 状态。
    :returns: Fins observation snapshot。
    :raises ValueError: snapshot 字段非法时抛出。
    """

    terminal_statuses = {
        FinsObservationStatus.SUCCEEDED,
        FinsObservationStatus.FAILED,
        FinsObservationStatus.CANCELLED,
    }
    result_status = _result_status_from_observation_status(status)
    return FinsObservationSnapshot(
        handle=handle,
        status=status,
        message=f"{status.value} observation",
        result=_observation_result(result_status) if status in terminal_statuses else None,
        error_kind=FinsErrorKind.EXECUTION if status is FinsObservationStatus.FAILED else None,
        retry_after_seconds=0.5 if status in {FinsObservationStatus.PENDING, FinsObservationStatus.RUNNING} else None,
    )


def _result_status_from_observation_status(
    status: FinsObservationStatus,
) -> FinsResultStatus:
    """把 observation terminal 状态转成 result status。

    :param status: observation 状态。
    :returns: result status。
    :raises Exception: 不主动抛出异常。
    """

    if status is FinsObservationStatus.CANCELLED:
        return FinsResultStatus.CANCELLED
    if status is FinsObservationStatus.FAILED:
        return FinsResultStatus.FAILURE
    return FinsResultStatus.SUCCESS


def _observation_result(status: FinsResultStatus) -> FinsResultSummary:
    """构造测试用 Fins observation terminal result。

    :param status: result status。
    :returns: Fins result summary。
    :raises ValueError: status 到 exit code 映射非法时抛出。
    """

    if status is FinsResultStatus.SUCCESS:
        exit_code = FINS_RESULT_EXIT_SUCCESS
        error_kind = None
        error_message = None
    elif status is FinsResultStatus.CANCELLED:
        exit_code = FINS_RESULT_EXIT_CANCELLED
        error_kind = FinsErrorKind.CANCELLED
        error_message = "cancelled"
    else:
        exit_code = FINS_RESULT_EXIT_FAILURE
        error_kind = FinsErrorKind.EXECUTION
        error_message = "failed"
    return FinsResultSummary(
        status=status,
        exit_code=exit_code,
        title="Observation result",
        details=(FinsEventDetail(label="ticker", value="AAPL"),),
        error_kind=error_kind,
        error_message=error_message,
    )


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        Returns:
            始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Returns:
            始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Returns:
            始终返回 ``None``。
        """

        return None


class _CancelledCancellationToken:
    """测试用已取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        Returns:
            始终返回 ``True``。
        """

        return True

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Returns:
            测试取消原因。
        """

        return "host-cancelled"

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Returns:
            固定取消请求时间。
        """

        return datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass
class _FakeObservationRuntime(FinsObservationRuntime):
    """测试用 process-local observation runtime。

    :param snapshots: handle id 到 snapshot 的映射。
    :param poll_errors: handle id 到 poll 分类异常的映射。
    """

    snapshots: dict[str, FinsObservationSnapshot]
    poll_errors: dict[str, FinsObservationPollError] | None = None
    cancel_errors: dict[str, FinsObservationPollError] | None = None
    abandon_errors: dict[str, FinsObservationPollError] | None = None
    cancelled_handles: tuple[str, ...] = ()
    abandoned_handles: tuple[str, ...] = ()
    activated_handles: tuple[str, ...] = ()

    def start_observed_download(
        self,
        request: FinsDownloadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动下载 observation。

        :param request: 下载请求。
        :param cancellation_token: operation-scoped 取消 token。
        :returns: observation handle。
        :raises NotImplementedError: 本 fake 不覆盖启动路径。
        """

        del request, cancellation_token
        raise NotImplementedError("fake runtime does not start download observations")

    def prepare_observed_download(
        self,
        request: FinsDownloadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记下载 observation。

        :param request: 下载请求。
        :param cancellation_token: operation-scoped 取消 token。
        :returns: observation handle。
        :raises NotImplementedError: 本 fake 不覆盖 prepare 路径。
        """

        del request, cancellation_token
        raise NotImplementedError("fake runtime does not prepare download observations")

    def start_observed_preprocess(
        self,
        request: FinsPreprocessRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动预处理 observation。

        :param request: 预处理请求。
        :param cancellation_token: operation-scoped 取消 token。
        :returns: observation handle。
        :raises NotImplementedError: 本 fake 不覆盖启动路径。
        """

        del request, cancellation_token
        raise NotImplementedError("fake runtime does not start preprocess observations")

    def prepare_observed_preprocess(
        self,
        request: FinsPreprocessRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记预处理 observation。

        :param request: 预处理请求。
        :param cancellation_token: operation-scoped 取消 token。
        :returns: observation handle。
        :raises NotImplementedError: 本 fake 不覆盖 prepare 路径。
        """

        del request, cancellation_token
        raise NotImplementedError("fake runtime does not prepare preprocess observations")

    def start_observed_upload(
        self,
        request: FinsUploadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """启动上传 observation。

        :param request: 上传请求。
        :param cancellation_token: operation-scoped 取消 token。
        :returns: observation handle。
        :raises NotImplementedError: 本 fake 不覆盖启动路径。
        """

        del request, cancellation_token
        raise NotImplementedError("fake runtime does not start upload observations")

    def prepare_observed_upload(
        self,
        request: FinsUploadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle:
        """登记上传 observation。

        :param request: 上传请求。
        :param cancellation_token: operation-scoped 取消 token。
        :returns: observation handle。
        :raises NotImplementedError: 本 fake 不覆盖 prepare 路径。
        """

        del request, cancellation_token
        raise NotImplementedError("fake runtime does not prepare upload observations")

    def activate_observation(self, handle: FinsObservationHandle) -> None:
        """记录 fake activation。

        :param handle: observation handle。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.activated_handles = self.activated_handles + (handle.handle_id,)

    async def poll_observation(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot:
        """读取 fake observation 快照。

        :param handle: observation handle。
        :returns: snapshot。
        :raises FinsObservationPollError: handle 缺失或配置为错误时抛出。
        """

        if self.poll_errors is not None and handle.handle_id in self.poll_errors:
            raise self.poll_errors[handle.handle_id]
        snapshot = self.snapshots.get(handle.handle_id)
        if snapshot is None:
            raise FinsObservationPollError(
                FinsObservationPollErrorKind.PERMANENT_NOT_FOUND,
                "Observation is no longer available.",
            )
        return snapshot

    async def cancel_observation(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot:
        """记录 fake cancellation。

        :param handle: observation handle。
        :returns: cancellation 后的 snapshot。
        :raises FinsObservationPollError: handle 缺失时抛出。
        """

        self.cancelled_handles = self.cancelled_handles + (handle.handle_id,)
        if self.cancel_errors is not None and handle.handle_id in self.cancel_errors:
            raise self.cancel_errors[handle.handle_id]
        return await self.poll_observation(handle)

    async def abandon_observation(self, handle: FinsObservationHandle) -> None:
        """记录并删除 fake observation。

        :param handle: observation handle。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.abandoned_handles = self.abandoned_handles + (handle.handle_id,)
        if self.abandon_errors is not None and handle.handle_id in self.abandon_errors:
            raise self.abandon_errors[handle.handle_id]
        self.snapshots.pop(handle.handle_id, None)


class _RuntimeErrorExecutor:
    """测试用后台执行器，在提交 job 时模拟非预期异常。"""

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """模拟后台提交失败。

        Args:
            job_id: opaque job id。
            operation: 原始后台任务函数。

        Returns:
            无。

        Raises:
            RuntimeError: 始终抛出，用于覆盖工具非预期启动异常分支。
        """

        del job_id, operation
        raise RuntimeError("executor unavailable")


class _OSErrorExecutor:
    """测试用后台执行器，在提交 observation 时模拟系统错误。"""

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """模拟后台提交系统错误。

        Args:
            job_id: opaque operation id。
            operation: 原始后台任务函数。

        Returns:
            无。

        Raises:
            OSError: 始终抛出，用于覆盖工具 OSError 启动失败分支。
        """

        del job_id, operation
        raise OSError("executor unavailable")


class _NoOpExecutor:
    """测试用后台执行器，只记录提交但不执行后台任务。"""

    submitted_job_ids: tuple[str, ...]

    def __init__(self) -> None:
        """初始化提交记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.submitted_job_ids = ()

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """记录后台任务提交。

        Args:
            job_id: opaque operation id。
            operation: 原始后台任务函数。

        Returns:
            无。

        Raises:
            无。
        """

        del operation
        self.submitted_job_ids = self.submitted_job_ids + (job_id,)


def test_tools_discovery_discovers_read_download_preprocess_and_upload_independently(
    tmp_path: Path,
) -> None:
    """ToolsDiscovery 应能独立发现 read、download、preprocess、upload provider。"""

    workspace_root = _build_workspace(tmp_path)
    result = ToolsDiscovery().discover_from_bindings(
        (
            ToolsDiscoveryProviderBinding(
                spec=_spec(
                    spec_id=_READ_SPEC_ID,
                    import_path="dayu.fins.tools.provider:discover_tools",
                    workspace_root=workspace_root,
                ),
                provider=read_provider.discover_tools,
            ),
            ToolsDiscoveryProviderBinding(
                spec=_spec(
                    spec_id=_DOWNLOAD_SPEC_ID,
                    import_path="dayu.fins.tools.download_provider:discover_tools",
                    workspace_root=workspace_root,
                ),
                provider=download_provider.discover_tools,
            ),
            ToolsDiscoveryProviderBinding(
                spec=_spec(
                    spec_id=_PREPROCESS_SPEC_ID,
                    import_path="dayu.fins.tools.preprocess_provider:discover_tools",
                    workspace_root=workspace_root,
                ),
                provider=preprocess_provider.discover_tools,
            ),
            ToolsDiscoveryProviderBinding(
                spec=_upload_spec(
                    spec_id=_UPLOAD_SPEC_ID,
                    workspace_root=workspace_root,
                ),
                provider=upload_provider.discover_tools,
            ),
        )
    )

    reports_by_provider = {report.provider_id: report for report in result.provider_reports}
    assert tuple(reports_by_provider) == (
        _READ_PROVIDER_ID,
        _DOWNLOAD_PROVIDER_ID,
        _PREPROCESS_PROVIDER_ID,
        _UPLOAD_PROVIDER_ID,
    )
    assert reports_by_provider[_READ_PROVIDER_ID].spec_id == _READ_SPEC_ID
    assert reports_by_provider[_DOWNLOAD_PROVIDER_ID].spec_id == _DOWNLOAD_SPEC_ID
    assert reports_by_provider[_PREPROCESS_PROVIDER_ID].spec_id == _PREPROCESS_SPEC_ID
    assert reports_by_provider[_UPLOAD_PROVIDER_ID].spec_id == _UPLOAD_SPEC_ID
    assert DOWNLOAD_TOOL_NAME in reports_by_provider[_DOWNLOAD_PROVIDER_ID].tool_names
    assert PREPROCESS_TOOL_NAME in reports_by_provider[_PREPROCESS_PROVIDER_ID].tool_names
    assert UPLOAD_TOOL_NAME in reports_by_provider[_UPLOAD_PROVIDER_ID].tool_names
    assert DOWNLOAD_TOOL_NAME not in reports_by_provider[_READ_PROVIDER_ID].tool_names
    assert PREPROCESS_TOOL_NAME not in reports_by_provider[_READ_PROVIDER_ID].tool_names
    assert UPLOAD_TOOL_NAME not in reports_by_provider[_READ_PROVIDER_ID].tool_names
    assert len({report.source_refs[0].source_id for report in result.provider_reports}) == 4


def test_workspace_overlay_enables_split_fins_providers(tmp_path: Path) -> None:
    """workspace overlay 应能分别启用 Fins read、download、preprocess、upload providers。"""

    workspace_root = _build_workspace(tmp_path)
    _write_split_fins_provider_overlay(tmp_path, workspace_root)
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(workspace_config_dir=tmp_path / "config")

    for provider_id in (_READ_SPEC_ID, _DOWNLOAD_SPEC_ID, _PREPROCESS_SPEC_ID, _UPLOAD_SPEC_ID):
        provider_config = config.tool_discovery.providers[provider_id]
        assert provider_config.enabled is True
        assert "include_ingestion_tools" not in provider_config.config

    result = ToolsDiscovery().discover(_provider_specs_from_loaded_config(config))
    reports_by_spec = {report.spec_id: report for report in result.provider_reports}

    assert {
        _READ_SPEC_ID,
        _DOWNLOAD_SPEC_ID,
        _PREPROCESS_SPEC_ID,
        _UPLOAD_SPEC_ID,
    }.issubset(reports_by_spec)
    assert reports_by_spec[_READ_SPEC_ID].provider_id == _READ_PROVIDER_ID
    assert reports_by_spec[_DOWNLOAD_SPEC_ID].provider_id == _DOWNLOAD_PROVIDER_ID
    assert reports_by_spec[_PREPROCESS_SPEC_ID].provider_id == _PREPROCESS_PROVIDER_ID
    assert _READ_SAMPLE_TOOL_NAME in reports_by_spec[_READ_SPEC_ID].tool_names
    assert DOWNLOAD_TOOL_NAME in reports_by_spec[_DOWNLOAD_SPEC_ID].tool_names
    assert PREPROCESS_TOOL_NAME in reports_by_spec[_PREPROCESS_SPEC_ID].tool_names
    assert UPLOAD_TOOL_NAME in reports_by_spec[_UPLOAD_SPEC_ID].tool_names


def test_upload_provider_registers_upload_tool_without_local_file_roots(
    tmp_path: Path,
) -> None:
    """upload provider 启用时不依赖本地文件根目录配置，必须注册上传工具。"""

    workspace_root = _build_workspace(tmp_path)
    result = upload_provider.discover_tools(
        ToolsDiscoveryProviderSpec(
            spec_id=_UPLOAD_SPEC_ID,
            location=PythonImportPathProvider(import_path="dayu.fins.tools.upload_provider:discover_tools"),
            enabled=True,
            config={
                "workspace_root": str(workspace_root),
                "awaiting_resolution_mode": "poll",
            },
        )
    )

    assert result.provider_id == _UPLOAD_PROVIDER_ID
    assert tuple(definition.name for definition in result.definitions) == (UPLOAD_TOOL_NAME,)


def test_upload_provider_rejects_missing_workspace_root() -> None:
    """upload provider 启用时仍必须要求明确的 Fins workspace root。"""

    with pytest.raises(ValueError, match="workspace_root"):
        upload_provider.discover_tools(
            ToolsDiscoveryProviderSpec(
                spec_id=_UPLOAD_SPEC_ID,
                location=PythonImportPathProvider(import_path="dayu.fins.tools.upload_provider:discover_tools"),
                enabled=True,
                config={"awaiting_resolution_mode": "poll"},
            )
        )


def test_download_tool_returns_external_job_awaiting_outcome(tmp_path: Path) -> None:
    """下载工具应返回基于 lightweight observation handle 的 awaiting outcome。"""

    workspace_root = _build_workspace(tmp_path)
    definition = download_provider.discover_tools(
        _spec(
            spec_id=_DOWNLOAD_SPEC_ID,
            import_path="dayu.fins.tools.download_provider:discover_tools",
            workspace_root=workspace_root,
        )
    ).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call(DOWNLOAD_TOOL_NAME, {"ticker": "AAPL", "form_types": ["10-K"]}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)
    assert outcome.await_spec.await_kind is ToolAwaitKind.EXTERNAL_JOB
    _assert_resume_token_is_opaque(outcome.await_spec.resume_token)
    assert outcome.snapshot is not None
    assert "finsjob_" not in outcome.snapshot.snapshot_id


def test_preprocess_tool_returns_external_job_awaiting_outcome(tmp_path: Path) -> None:
    """预处理工具应返回基于 lightweight observation handle 的 awaiting outcome。"""

    workspace_root = _build_workspace(tmp_path)
    definition = preprocess_provider.discover_tools(
        _spec(
            spec_id=_PREPROCESS_SPEC_ID,
            import_path="dayu.fins.tools.preprocess_provider:discover_tools",
            workspace_root=workspace_root,
        )
    ).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call(PREPROCESS_TOOL_NAME, {"ticker": "AAPL", "document_ids": ["aapl-2024-10k"]}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)
    assert outcome.await_spec.await_kind is ToolAwaitKind.EXTERNAL_JOB
    _assert_resume_token_is_opaque(outcome.await_spec.resume_token)
    assert outcome.snapshot is not None
    assert "finsjob_" not in outcome.snapshot.snapshot_id


def test_preprocess_tool_accepts_material_filters_and_rebuild_flag(
    tmp_path: Path,
) -> None:
    """公开工具契约必须接受 material、文档/表单过滤与重建开关。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 有效业务参数未创建 awaiting observation 时抛出。
    """

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    outcome = asyncio.run(
        FinsPreprocessToolCallable(runtime=runtime)(
            _call(
                PREPROCESS_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "source_kind": "material",
                    "document_ids": ["aapl-earnings-call-2024-q4"],
                    "form_types": ["earnings-call"],
                    "rebuild_processed": True,
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)
    assert outcome.await_spec.await_kind is ToolAwaitKind.EXTERNAL_JOB
    _assert_resume_token_is_opaque(outcome.await_spec.resume_token)
    assert outcome.snapshot is not None


@pytest.mark.parametrize(
    ("source_kind", "expected_message"),
    (
        (7, "source_kind must be a string"),
        ("transcript", "source_kind must be one of"),
    ),
)
def test_preprocess_tool_rejects_invalid_source_kind_before_creating_observation(
    tmp_path: Path,
    source_kind: JsonValue,
    expected_message: str,
) -> None:
    """公开工具必须在 observation 创建前拒绝非法源文档类别。

    Args:
        tmp_path: pytest 临时目录。
        source_kind: 非字符串或未知的源文档类别。
        expected_message: 预期的业务可读校验信息。

    Returns:
        无。

    Raises:
        AssertionError: 非法参数未按 invalid_argument 失败时抛出。
    """

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    outcome = asyncio.run(
        FinsPreprocessToolCallable(runtime=runtime)(
            _call(
                PREPROCESS_TOOL_NAME,
                {"ticker": "AAPL", "source_kind": source_kind},
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert expected_message in outcome.result.message
    assert not tuple(_job_store_root(workspace_root).glob("*.json"))


def test_upload_tool_returns_external_job_awaiting_outcome(tmp_path: Path) -> None:
    """上传工具应返回基于 lightweight observation handle 的 awaiting outcome。"""

    workspace_root = _build_workspace(tmp_path)
    definition = upload_provider.discover_tools(
        _upload_spec(
            spec_id=_UPLOAD_SPEC_ID,
            workspace_root=workspace_root,
        )
    ).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "action": "delete",
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)
    assert outcome.await_spec.await_kind is ToolAwaitKind.EXTERNAL_JOB
    _assert_resume_token_is_opaque(outcome.await_spec.resume_token)
    assert outcome.snapshot is not None
    assert "finsjob_" not in outcome.snapshot.snapshot_id


def test_awaiting_tool_callables_prepare_without_executor_submit(tmp_path: Path) -> None:
    """download/preprocess/upload callable 只 prepare observation，不提交 executor。"""

    workspace_root = _build_workspace(tmp_path)
    executor = _NoOpExecutor()
    runtime = _runtime_with_executor(workspace_root=workspace_root, executor=executor)

    download_outcome = asyncio.run(
        FinsDownloadToolCallable(runtime=runtime)(
            _call(DOWNLOAD_TOOL_NAME, {"ticker": "AAPL"}),
            _context(),
        )
    )
    preprocess_outcome = asyncio.run(
        FinsPreprocessToolCallable(runtime=runtime)(
            _call(PREPROCESS_TOOL_NAME, {"ticker": "AAPL"}),
            _context(),
        )
    )
    upload_outcome = asyncio.run(
        FinsUploadToolCallable(runtime=runtime)(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "action": "delete",
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(),
        )
    )

    assert isinstance(download_outcome, ToolAwaitingOutcome)
    assert isinstance(preprocess_outcome, ToolAwaitingOutcome)
    assert isinstance(upload_outcome, ToolAwaitingOutcome)
    assert executor.submitted_job_ids == ()


def test_tool_argument_error_returns_failed_outcome_before_observation_start(tmp_path: Path) -> None:
    """工具参数错误必须返回失败 outcome，且不得启动 observation。"""

    workspace_root = _build_workspace(tmp_path)
    definition = download_provider.discover_tools(
        _spec(
            spec_id=_DOWNLOAD_SPEC_ID,
            import_path="dayu.fins.tools.download_provider:discover_tools",
            workspace_root=workspace_root,
        )
    ).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call(DOWNLOAD_TOOL_NAME, {"ticker": 123}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    job_dir = workspace_root / ".dayu" / "fins_ingestion" / "jobs"
    assert not tuple(job_dir.glob("*.json"))


def test_upload_tool_missing_file_returns_failed_outcome_before_observation_start(tmp_path: Path) -> None:
    """上传缺失文件必须在 observation 启动前返回失败 outcome。"""

    workspace_root = _build_workspace(tmp_path)
    outside_root = tmp_path / "outside"
    missing_file = outside_root / "missing.pdf"
    definition = upload_provider.discover_tools(
        _upload_spec(
            spec_id=_UPLOAD_SPEC_ID,
            workspace_root=workspace_root,
        )
    ).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "files": [str(missing_file)],
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert "existing file" in outcome.result.message
    assert not tuple(_job_store_root(workspace_root).glob("*.json"))


def test_upload_tool_directory_returns_failed_outcome_before_observation_start(tmp_path: Path) -> None:
    """上传目录路径必须在 observation 启动前返回失败 outcome。"""

    workspace_root = _build_workspace(tmp_path)
    directory_path = tmp_path / "outside-directory"
    directory_path.mkdir()
    definition = upload_provider.discover_tools(
        _upload_spec(
            spec_id=_UPLOAD_SPEC_ID,
            workspace_root=workspace_root,
        )
    ).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "files": [str(directory_path)],
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert "existing file" in outcome.result.message
    assert not tuple(_job_store_root(workspace_root).glob("*.json"))


def test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect(
    tmp_path: Path,
) -> None:
    """上传工具接受 workspace 外本地文件，prepare 阶段不提交且不写源侧治理状态。"""

    workspace_root = _build_workspace(tmp_path)
    outside_file = _write_upload_file(tmp_path / "outside-upload-source")
    executor = _NoOpExecutor()
    runtime = _runtime_with_executor(
        workspace_root=workspace_root,
        executor=executor,
    )

    outcome = asyncio.run(
        FinsUploadToolCallable(runtime=runtime)(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "files": [str(outside_file)],
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)
    assert executor.submitted_job_ids == ()
    assert all(str(outside_file.parent) not in job_id for job_id in executor.submitted_job_ids)
    assert not (outside_file.parent / ".dayu").exists()


def test_upload_tool_empty_file_returns_failed_outcome_before_observation_start(tmp_path: Path) -> None:
    """上传空文件必须在 observation 启动前返回失败 outcome。"""

    workspace_root = _build_workspace(tmp_path)
    allowed_root = _build_upload_root(tmp_path)
    empty_file = allowed_root / "empty.pdf"
    empty_file.write_bytes(b"")
    definition = upload_provider.discover_tools(
        _upload_spec(
            spec_id=_UPLOAD_SPEC_ID,
            workspace_root=workspace_root,
        )
    ).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "files": [str(empty_file)],
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert "non-empty file" in outcome.result.message
    assert not tuple(_job_store_root(workspace_root).glob("*.json"))


def test_upload_tool_delete_rejects_unnecessary_files_before_job_creation(tmp_path: Path) -> None:
    """上传 delete 动作带 files 时必须失败，避免误读本地文件。"""

    workspace_root = _build_workspace(tmp_path)
    upload_file = _write_upload_file(_build_upload_root(tmp_path))
    definition = upload_provider.discover_tools(
        _upload_spec(
            spec_id=_UPLOAD_SPEC_ID,
            workspace_root=workspace_root,
        )
    ).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "material",
                    "action": "delete",
                    "files": [str(upload_file)],
                    "form_type": "MATERIAL_OTHER",
                    "material_name": "Deck",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert "files must be omitted" in outcome.result.message
    assert not tuple(_job_store_root(workspace_root).glob("*.json"))


def test_download_tool_cancelled_before_start_returns_cancelled_without_job(tmp_path: Path) -> None:
    """下载工具 start 前收到取消 token 时应取消且不启动 observation。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    outcome = asyncio.run(
        FinsDownloadToolCallable(runtime=runtime)(
            _call(DOWNLOAD_TOOL_NAME, {"ticker": "AAPL"}),
            _context(cancellation_token=_CancelledCancellationToken()),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    _assert_cancelled_outcome_hides_host_term(outcome)
    assert not tuple(_job_store_root(workspace_root).glob("*.json"))


def test_preprocess_tool_cancelled_before_start_returns_cancelled_without_job(tmp_path: Path) -> None:
    """预处理工具 start 前收到取消 token 时应取消且不启动 observation。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    outcome = asyncio.run(
        FinsPreprocessToolCallable(runtime=runtime)(
            _call(PREPROCESS_TOOL_NAME, {"ticker": "AAPL"}),
            _context(cancellation_token=_CancelledCancellationToken()),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    _assert_cancelled_outcome_hides_host_term(outcome)
    assert not tuple(_job_store_root(workspace_root).glob("*.json"))


def test_upload_tool_cancelled_before_start_returns_cancelled_without_job(tmp_path: Path) -> None:
    """上传工具 start 前收到取消 token 时应取消且不启动 observation。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    outcome = asyncio.run(
        FinsUploadToolCallable(runtime=runtime)(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "action": "delete",
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(cancellation_token=_CancelledCancellationToken()),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    _assert_cancelled_outcome_hides_host_term(outcome)
    assert not tuple(_job_store_root(workspace_root).glob("*.json"))


def test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime() -> None:
    """download/preprocess/upload callable 不得丢弃 context，且必须把 token 传给 runtime。"""

    _assert_context_token_bridge(
        source_path=_DOWNLOAD_TOOLS_PATH,
        class_name="FinsDownloadToolCallable",
        start_method="prepare_observed_download",
    )
    _assert_context_token_bridge(
        source_path=_PREPROCESS_TOOLS_PATH,
        class_name="FinsPreprocessToolCallable",
        start_method="prepare_observed_preprocess",
    )
    _assert_context_token_bridge(
        source_path=_UPLOAD_TOOLS_PATH,
        class_name="FinsUploadToolCallable",
        start_method="prepare_observed_upload",
    )


def test_download_tool_os_error_executor_is_not_used_during_prepare(tmp_path: Path) -> None:
    """下载工具 prepare 阶段不得触发 executor OSError。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = _runtime_with_executor(
        workspace_root=workspace_root,
        executor=_OSErrorExecutor(),
    )

    outcome = asyncio.run(
        FinsDownloadToolCallable(runtime=runtime)(
            _call(DOWNLOAD_TOOL_NAME, {"ticker": "AAPL"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)


def test_download_tool_unexpected_executor_error_is_not_used_during_prepare(
    tmp_path: Path,
) -> None:
    """下载工具 prepare 阶段不得触发 executor 非预期异常。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = _runtime_with_executor(
        workspace_root=workspace_root,
        executor=_RuntimeErrorExecutor(),
    )

    outcome = asyncio.run(
        FinsDownloadToolCallable(runtime=runtime)(
            _call(DOWNLOAD_TOOL_NAME, {"ticker": "AAPL"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)


def test_preprocess_tool_os_error_executor_is_not_used_during_prepare(
    tmp_path: Path,
) -> None:
    """预处理工具 prepare 阶段不得触发 executor OSError。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = _runtime_with_executor(
        workspace_root=workspace_root,
        executor=_OSErrorExecutor(),
    )

    outcome = asyncio.run(
        FinsPreprocessToolCallable(runtime=runtime)(
            _call(PREPROCESS_TOOL_NAME, {"ticker": "AAPL"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)


def test_preprocess_tool_unexpected_executor_error_is_not_used_during_prepare(
    tmp_path: Path,
) -> None:
    """预处理工具 prepare 阶段不得触发 executor 非预期异常。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = _runtime_with_executor(
        workspace_root=workspace_root,
        executor=_RuntimeErrorExecutor(),
    )

    outcome = asyncio.run(
        FinsPreprocessToolCallable(runtime=runtime)(
            _call(PREPROCESS_TOOL_NAME, {"ticker": "AAPL"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)


def test_upload_tool_os_error_executor_is_not_used_during_prepare(tmp_path: Path) -> None:
    """上传工具 prepare 阶段不得触发 executor OSError。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = _runtime_with_executor(
        workspace_root=workspace_root,
        executor=_OSErrorExecutor(),
    )

    outcome = asyncio.run(
        FinsUploadToolCallable(runtime=runtime)(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "action": "delete",
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)


def test_upload_tool_unexpected_executor_error_is_not_used_during_prepare(
    tmp_path: Path,
) -> None:
    """上传工具 prepare 阶段不得触发 executor 非预期异常。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = _runtime_with_executor(
        workspace_root=workspace_root,
        executor=_RuntimeErrorExecutor(),
    )

    outcome = asyncio.run(
        FinsUploadToolCallable(runtime=runtime)(
            _call(
                UPLOAD_TOOL_NAME,
                {
                    "ticker": "AAPL",
                    "upload_kind": "filing",
                    "action": "delete",
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolAwaitingOutcome)


def _assert_cancelled_outcome_hides_host_term(outcome: ToolCancelledOutcome) -> None:
    """断言取消 outcome 的模型可见文案不暴露 host 术语。

    Args:
        outcome: 工具取消 outcome。

    Returns:
        无。

    Raises:
        AssertionError: message 或 hint 含 host / Host 时抛出。
    """

    visible_text = f"{outcome.message}\n{outcome.hint}"
    for fragment in _FORBIDDEN_CANCELLED_MESSAGE_FRAGMENTS:
        assert fragment not in visible_text


def _assert_resume_token_is_opaque(resume_token: str) -> None:
    """断言 Fins awaiting resume token 不泄露内部治理或路径语义。

    Args:
        resume_token: ToolAwaitSpec resume token。

    Returns:
        无。

    Raises:
        AssertionError: token 格式非法或包含禁止片段时抛出。
    """

    assert parse_observation_handle_id_token(resume_token)
    assert resume_token.startswith(FINS_OBSERVATION_HANDLE_ID_PREFIX)
    lowered = resume_token.lower()
    for fragment in ("job", "cursor", "sidecar", "storage", ".dayu", "/", "\\"):
        assert fragment not in lowered


def test_ingestion_tool_schemas_hide_host_internal_fields(tmp_path: Path) -> None:
    """下载、预处理和上传工具 schema 不应暴露 Host 内部治理字段。"""

    workspace_root = _build_workspace(tmp_path)
    definitions = (
        download_provider.discover_tools(
            _spec(
                spec_id=_DOWNLOAD_SPEC_ID,
                import_path="dayu.fins.tools.download_provider:discover_tools",
                workspace_root=workspace_root,
            )
        ).definitions
        + preprocess_provider.discover_tools(
            _spec(
                spec_id=_PREPROCESS_SPEC_ID,
                import_path="dayu.fins.tools.preprocess_provider:discover_tools",
                workspace_root=workspace_root,
            )
        ).definitions
        + upload_provider.discover_tools(
            _upload_spec(
                spec_id=_UPLOAD_SPEC_ID,
                workspace_root=workspace_root,
            )
        ).definitions
    )

    for definition in definitions:
        properties = definition.schema.function.parameters.properties
        required = definition.schema.function.parameters.required
        assert "execution_context" not in properties
        assert "cancellation_token" not in properties
        assert "execution_context" not in required
        assert "cancellation_token" not in required

        schema_text = _schema_text(definition)
        assert "tool_call_id" not in schema_text
        assert "wait_id" not in schema_text
        assert "EventLog" not in schema_text
        assert "digest" not in schema_text
        assert "cursor" not in schema_text
        assert "raw job record" not in schema_text
        assert "internal governance" not in schema_text
        assert "Host" not in schema_text
        lowered_schema_text = schema_text.lower()
        assert "external-job" not in lowered_schema_text
        assert "observation handle" not in lowered_schema_text
        assert "runtime" not in lowered_schema_text
        assert "next_step" not in lowered_schema_text
        assert "poll" not in lowered_schema_text
        assert "local file paths to upload" not in lowered_schema_text
        assert "whether the upload" not in lowered_schema_text
        assert "required for filing uploads" not in lowered_schema_text
        assert "optional explicit material" not in lowered_schema_text


def _build_workspace(tmp_path: Path) -> Path:
    """构造空 Fins workspace。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        workspace root。

    Raises:
        OSError: 目录创建失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    return workspace_root


def _job_store_root(workspace_root: Path) -> Path:
    """返回 workspace 派生的 ingestion job store 根目录。

    Args:
        workspace_root: Fins workspace root。

    Returns:
        job store 根目录。

    Raises:
        无。
    """

    return workspace_root / ".dayu" / "fins_ingestion" / "jobs"


def _runtime_with_executor(
    *,
    workspace_root: Path,
    executor: FinsIngestionExecutor,
) -> FinsIngestionRuntime:
    """使用指定后台执行器构造 ingestion runtime。

    Args:
        workspace_root: Fins workspace root。
        executor: 测试注入的后台执行器。

    Returns:
        Fins ingestion 运行时。

    Raises:
        OSError: 默认 Fins runtime 初始化失败时抛出。
    """

    base_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    return FinsIngestionRuntime.create(
        batching_repository=base_runtime.batching_repository,
        source_repository=base_runtime.source_repository,
        blob_repository=base_runtime.blob_repository,
        filing_maintenance_repository=base_runtime.filing_maintenance_repository,
        processed_repository=base_runtime.processed_repository,
        processor_registry=base_runtime.processor_registry,
        job_store=base_runtime.ingestion_job_store,
        executor=executor,
    )


def _write_split_fins_provider_overlay(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    """写入启用 split Fins providers 的 workspace overlay。

    Args:
        tmp_path: pytest 临时目录。
        workspace_root: Fins workspace root。

    Returns:
        无。

    Raises:
        OSError: 配置文件写入失败时抛出。
    """

    payload: JsonValue = {
        "providers": {
            _READ_SPEC_ID: {
                "import_path": "dayu.fins.tools.provider:discover_tools",
                "entry_point": None,
                "source_kind": "explicit_provider",
                "source_id": "dayu.fins.tools.provider",
                "enabled": True,
                "config": {
                    "workspace_root": str(workspace_root),
                    "limits": {},
                },
            },
            _DOWNLOAD_SPEC_ID: {
                "import_path": "dayu.fins.tools.download_provider:discover_tools",
                "entry_point": None,
                "source_kind": "explicit_provider",
                "source_id": "dayu.fins.tools.download_provider",
                "enabled": True,
                "config": {
                    "workspace_root": str(workspace_root),
                    "awaiting_resolution_mode": "poll",
                },
            },
            _PREPROCESS_SPEC_ID: {
                "import_path": "dayu.fins.tools.preprocess_provider:discover_tools",
                "entry_point": None,
                "source_kind": "explicit_provider",
                "source_id": "dayu.fins.tools.preprocess_provider",
                "enabled": True,
                "config": {
                    "workspace_root": str(workspace_root),
                    "awaiting_resolution_mode": "poll",
                },
            },
            _UPLOAD_SPEC_ID: {
                "import_path": "dayu.fins.tools.upload_provider:discover_tools",
                "entry_point": None,
                "source_kind": "explicit_provider",
                "source_id": "dayu.fins.tools.upload_provider",
                "enabled": True,
                "config": {
                    "workspace_root": str(workspace_root),
                    "awaiting_resolution_mode": "poll",
                },
            },
        }
    }
    _write_json(tmp_path / "config" / "tool_discovery.json", payload)


def _provider_specs_from_loaded_config(
    config: RuntimeConfig,
) -> tuple[ToolsDiscoveryProviderSpec, ...]:
    """从已加载配置构造 ToolsDiscovery provider specs。

    Args:
        config: ConfigLoader 加载后的 runtime config。

    Returns:
        provider spec 元组。

    Raises:
        AssertionError: 测试配置缺少 import_path 时抛出。
    """

    specs: list[ToolsDiscoveryProviderSpec] = []
    for provider_config in config.tool_discovery.providers.values():
        assert provider_config.import_path is not None
        specs.append(
            ToolsDiscoveryProviderSpec(
                spec_id=provider_config.provider_id,
                location=PythonImportPathProvider(import_path=provider_config.import_path),
                enabled=provider_config.enabled,
                config=provider_config.config,
            )
        )
    return tuple(specs)


def _write_json(path: Path, value: JsonValue) -> None:
    """写入 JSON 文件。

    Args:
        path: 目标文件路径。
        value: JSON 值。

    Returns:
        无。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _spec(
    *,
    spec_id: str,
    import_path: str,
    workspace_root: Path,
) -> ToolsDiscoveryProviderSpec:
    """构造 provider spec。

    Args:
        spec_id: provider spec id。
        import_path: provider import path。
        workspace_root: Fins workspace root。

    Returns:
        provider spec。

    Raises:
        无。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id=spec_id,
        location=PythonImportPathProvider(import_path=import_path),
        enabled=True,
        config={
            "workspace_root": str(workspace_root),
            "awaiting_resolution_mode": "poll",
        },
    )


def _upload_spec(
    *,
    spec_id: str,
    workspace_root: Path,
) -> ToolsDiscoveryProviderSpec:
    """构造 upload provider spec。

    Args:
        spec_id: provider spec id。
        workspace_root: Fins workspace root。

    Returns:
        provider spec。

    Raises:
        无。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id=spec_id,
        location=PythonImportPathProvider(import_path="dayu.fins.tools.upload_provider:discover_tools"),
        enabled=True,
        config={
            "workspace_root": str(workspace_root),
            "awaiting_resolution_mode": "poll",
        },
    )


def _build_upload_root(tmp_path: Path) -> Path:
    """构造上传文件目录。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        上传文件目录。

    Raises:
        OSError: 目录创建失败时抛出。
    """

    upload_root = tmp_path / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    return upload_root.resolve(strict=False)


def _write_upload_file(upload_root: Path) -> Path:
    """写入测试上传文件。

    Args:
        upload_root: 上传文件根目录。

    Returns:
        测试文件路径。

    Raises:
        OSError: 目录或文件写入失败时抛出。
    """

    upload_root.mkdir(parents=True, exist_ok=True)
    target = upload_root / "sample.pdf"
    target.write_bytes(b"%PDF-1.4\n% test upload\n")
    return target.resolve(strict=False)


def _call(name: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    Args:
        name: 工具名。
        arguments: 工具参数。

    Returns:
        工具调用请求。

    Raises:
        无。
    """

    return ToolCallRequest(
        tool_call_id=f"call-{name}",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _context(cancellation_token: CancellationToken | None = None) -> BatchToolExecutionContext:
    """构造批执行上下文。

    Args:
        cancellation_token: 可选测试取消 token；不传入时使用未取消 token。

    Returns:
        批执行上下文。

    Raises:
        无。
    """

    return BatchToolExecutionContext(
        run_id="run-fins",
        session_id="session-fins",
        iteration_id="iteration-fins",
        timeout_seconds=30.0,
        cancellation_token=cancellation_token or _OpenCancellationToken(),
        correlation_id="correlation-fins",
    )


def _schema_text(definition: ToolDefinition) -> str:
    """提取 schema 文本用于内部字段泄漏断言。

    Args:
        definition: 工具定义。

    Returns:
        schema 的稳定文本表示。

    Raises:
        无。
    """

    return (
        definition.schema.function.description
        + " "
        + " ".join(definition.schema.function.parameters.properties.keys())
        + " "
        + str(definition.schema.function.parameters.properties)
    )


def _assert_context_token_bridge(
    *,
    source_path: Path,
    class_name: str,
    start_method: str,
) -> None:
    """断言 awaiting callable 源码消费 context 并传递 cancellation token。

    Args:
        source_path: 待检查的源码路径。
        class_name: awaiting tool callable 类名。
        start_method: runtime start 方法名。

    Returns:
        无。

    Raises:
        AssertionError: 找不到目标类、目标方法丢弃 context，或调用 runtime start
            时未显式传入 ``cancellation_token``。
    """

    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    class_node = _find_class(tree, class_name)
    call_node = _find_method(class_node, "__call__")
    has_token_bridge = False

    for node in ast.walk(call_node):
        if isinstance(node, ast.Delete):
            assert not any(isinstance(target, ast.Name) and target.id == "context" for target in node.targets)
        if _is_runtime_start_call(node, start_method=start_method):
            has_token_bridge = any(
                keyword.arg == "cancellation_token"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "cancellation_token"
                for keyword in node.keywords
            )

    assert has_token_bridge


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef:
    """在模块 AST 中查找类定义。

    Args:
        tree: 模块 AST。
        class_name: 类名。

    Returns:
        类定义节点。

    Raises:
        AssertionError: 找不到对应类定义。
    """

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"missing class: {class_name}")


def _find_method(class_node: ast.ClassDef, method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """在类 AST 中查找方法定义。

    Args:
        class_node: 类定义节点。
        method_name: 方法名。

    Returns:
        方法定义节点。

    Raises:
        AssertionError: 找不到对应方法定义。
    """

    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
        if isinstance(node, ast.AsyncFunctionDef) and node.name == method_name:
            return node
    raise AssertionError(f"missing method: {class_node.name}.{method_name}")


def _is_runtime_start_call(node: ast.AST, *, start_method: str) -> TypeGuard[ast.Call]:
    """判断 AST 节点是否为 runtime start 调用。

    Args:
        node: 待判断 AST 节点。
        start_method: runtime start 方法名。

    Returns:
        若节点是目标 start 方法调用则返回 ``True``。

    Raises:
        无。
    """

    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == start_method
