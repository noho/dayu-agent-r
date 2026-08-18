"""Service-owned Fins wait adapter 测试。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_await import ToolAwaitKind
from dayu.contracts.tool_await import ToolAwaitSpec
from dayu.host.api import (
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
)
from dayu.host.wait_adapter import (
    WaitAdapterSnapshot,
    WaitExternalJobLifecycleAction,
    WaitExternalJobLifecycleApplied,
    WaitExternalJobLifecycleNoop,
    WaitPollLost,
    WaitPollNotReady,
    WaitPollReady,
    WaitResumePolicy,
)
from dayu.host.wait_adapter import WaitActivationRequest
from dayu.host.waiting import ToolAwaitingAcceptedAck, ToolAwaitingEventRef
from dayu.service.fins_wait_adapter import (
    FINS_INGESTION_WAIT_ADAPTER_KEY,
    FINS_UPLOAD_AWAITING_TOOL_NAME,
    FinsIngestionWaitActivationAdapter,
    FinsIngestionWaitPollAdapter,
    build_fins_wait_activation_registry,
    build_fins_wait_adapter_registry,
    _operation_kind_from_tool_name,
)
from dayu.fins.company_metadata_warning import (
    COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    CompanyMetadataWarning,
    CompanyMetadataWarningKind,
)
from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_FAILURE,
    FINS_RESULT_EXIT_CANCELLED,
    FINS_RESULT_EXIT_SUCCESS,
    FinsErrorKind,
    FinsDownloadPublicDocument,
    FinsDownloadPublicSummary,
    FinsEventDetail,
    FinsOperationKind,
    FinsPublicFailure,
    FinsPublicFailureKind,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.ingestion import (
    FINS_OBSERVATION_HANDLE_ID_PREFIX,
    FinsObservationHandle,
    FinsObservationPollError,
    FinsObservationPollErrorKind,
    FinsObservationRuntime,
    FinsObservationSnapshot,
    FinsObservationStatus,
)
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition,
    FinsDownloadEffectiveFilters,
    FinsDownloadRequest,
    FinsDownloadSource,
    FinsDownloadTerminalDisposition,
    FinsDownloadTransportCategory,
)
from dayu.fins.ingestion_runtime import (
    FinsPreprocessRequest,
    FinsUploadRequest,
)
from dayu.fins.ingestion.awaiting_resolution import AwaitingResolutionMode
from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME
from dayu.fins.tools.preprocess_tools import PREPROCESS_TOOL_NAME
from dayu.fins.tools.upload_tools import UPLOAD_TOOL_NAME

_OBSERVATION_TIME = datetime(2026, 6, 16, tzinfo=timezone.utc)


def test_fins_wait_adapter_registry_binds_supported_tools(tmp_path: Path) -> None:
    """Service adapter registry 应绑定稳定 key 与 poll policy。"""

    registry = build_fins_wait_adapter_registry(
        workspace_root=tmp_path.resolve(strict=False),
        tool_modes=(
            (UPLOAD_TOOL_NAME, AwaitingResolutionMode.MANUAL),
            (DOWNLOAD_TOOL_NAME, AwaitingResolutionMode.POLL),
            (PREPROCESS_TOOL_NAME, AwaitingResolutionMode.CALLBACK),
        ),
    )

    download_binding = registry.resolve_binding(
        tool_name=DOWNLOAD_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    preprocess_binding = registry.resolve_binding(
        tool_name=PREPROCESS_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    upload_binding = registry.resolve_binding(
        tool_name=FINS_UPLOAD_AWAITING_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )

    assert download_binding is not None
    assert preprocess_binding is not None
    assert upload_binding is not None
    assert download_binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY
    assert preprocess_binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY
    assert upload_binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY
    assert download_binding.resume_policy is WaitResumePolicy.POLL
    assert preprocess_binding.resume_policy is WaitResumePolicy.CALLBACK
    assert upload_binding.resume_policy is WaitResumePolicy.MANUAL


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    (
        (DOWNLOAD_TOOL_NAME, FinsOperationKind.DOWNLOAD),
        (PREPROCESS_TOOL_NAME, FinsOperationKind.PREPROCESS),
        (UPLOAD_TOOL_NAME, FinsOperationKind.UPLOAD),
    ),
)
def test_fins_operation_kind_structural_mapping_remains_stable(
    tool_name: str,
    expected: FinsOperationKind,
) -> None:
    """observation handle 的 tool-name 结构映射不得被 mode mapping 替代。

    :param tool_name: Fins awaiting 工具名。
    :param expected: 预期 operation kind。
    :returns: ``None``。
    :raises AssertionError: 结构映射漂移时抛出。
    """

    assert _operation_kind_from_tool_name(tool_name) is expected


def test_fins_wait_adapter_registry_duplicate_binding_fails(tmp_path: Path) -> None:
    """重复 Service wait binding 必须 deterministic fail fast。"""

    workspace_root = tmp_path.resolve(strict=False)

    with pytest.raises(ValueError, match="duplicate Fins wait adapter binding"):
        build_fins_wait_adapter_registry(
            workspace_root=workspace_root,
            tool_modes=(
                (DOWNLOAD_TOOL_NAME, AwaitingResolutionMode.POLL),
                (DOWNLOAD_TOOL_NAME, AwaitingResolutionMode.MANUAL),
            ),
        )


def test_fins_wait_activation_registry_uses_shared_runtime() -> None:
    """activation registry 必须复用 Service discovery 创建的 runtime。"""

    runtime = _FakeObservationRuntime(snapshots={})

    registry = build_fins_wait_activation_registry(
        runtime=runtime,
        tool_names=(DOWNLOAD_TOOL_NAME, PREPROCESS_TOOL_NAME, UPLOAD_TOOL_NAME),
    )

    adapter = registry.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY)

    assert isinstance(adapter, FinsIngestionWaitActivationAdapter)
    assert adapter.runtime is runtime


def test_fins_wait_activation_adapter_activates_existing_resume_token() -> None:
    """activation adapter 应解析 resume token 并调用 runtime activation。"""

    handle = _observation_handle_with_id("1234567890abcdef")
    runtime = _FakeObservationRuntime(snapshots={})
    adapter = FinsIngestionWaitActivationAdapter(runtime=runtime)

    adapter.activate_accepted_wait(
        _activation_request(
            tool_name=DOWNLOAD_TOOL_NAME,
            resume_token=handle.handle_id,
        )
    )

    assert runtime.activated_handles == (handle.handle_id,)


def test_fins_wait_activation_adapter_rejects_corrupt_resume_token() -> None:
    """activation adapter 遇到 corrupt token 不得调用 runtime。"""

    runtime = _FakeObservationRuntime(snapshots={})
    adapter = FinsIngestionWaitActivationAdapter(runtime=runtime)

    with pytest.raises(ValueError):
        adapter.activate_accepted_wait(
            _activation_request(
                tool_name=DOWNLOAD_TOOL_NAME,
                resume_token="finsjob_00000000000000000000000000000007",
            )
        )

    assert runtime.activated_handles == ()


def test_fins_wait_poll_adapter_maps_observation_statuses() -> None:
    """poll adapter 应把 Fins observation 状态映射为 Host outcome。"""

    succeeded = _observation_handle_with_id("bbbbbbbbbbbbbbbb")
    failed = _observation_handle_with_id("cccccccccccccccc")
    cancelled = _observation_handle_with_id("dddddddddddddddd")
    pending = _observation_handle_with_id("eeeeeeeeeeeeeeee")
    running = _observation_handle_with_id("ffffffffffffffff")
    lost = _observation_handle_with_id("1111111111111111")
    runtime = _FakeObservationRuntime(
        snapshots={
            succeeded.handle_id: _observation_snapshot(
                succeeded,
                FinsObservationStatus.SUCCEEDED,
            ),
            failed.handle_id: _observation_snapshot(
                failed,
                FinsObservationStatus.FAILED,
            ),
            cancelled.handle_id: _observation_snapshot(
                cancelled,
                FinsObservationStatus.CANCELLED,
            ),
            pending.handle_id: _observation_snapshot(
                pending,
                FinsObservationStatus.PENDING,
            ),
            running.handle_id: _observation_snapshot(
                running,
                FinsObservationStatus.RUNNING,
            ),
            lost.handle_id: _observation_snapshot(lost, FinsObservationStatus.LOST),
        }
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    succeeded_poll = adapter.poll_wait(_wait_snapshot(succeeded.handle_id, DOWNLOAD_TOOL_NAME))
    failed_poll = adapter.poll_wait(_wait_snapshot(failed.handle_id, DOWNLOAD_TOOL_NAME))
    cancelled_poll = adapter.poll_wait(_wait_snapshot(cancelled.handle_id, PREPROCESS_TOOL_NAME))
    pending_poll = adapter.poll_wait(_wait_snapshot(pending.handle_id, PREPROCESS_TOOL_NAME))
    running_poll = adapter.poll_wait(_wait_snapshot(running.handle_id, DOWNLOAD_TOOL_NAME))
    lost_poll = adapter.poll_wait(_wait_snapshot(lost.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(succeeded_poll, WaitPollReady)
    assert isinstance(succeeded_poll.outcome, ResolveWaitCompletedOutcome)
    assert isinstance(failed_poll, WaitPollReady)
    assert isinstance(failed_poll.outcome, ResolveWaitFailedOutcome)
    assert isinstance(cancelled_poll, WaitPollReady)
    assert isinstance(cancelled_poll.outcome, ResolveWaitCancelledOutcome)
    assert isinstance(pending_poll, WaitPollNotReady)
    assert isinstance(running_poll, WaitPollNotReady)
    assert isinstance(lost_poll, WaitPollLost)
    assert isinstance(lost_poll.outcome, ResolveWaitLostOutcome)
    value = succeeded_poll.outcome.result.value
    assert isinstance(value, Mapping)
    assert value["operation"] == "download"
    assert value["warnings"] == []
    assert "job_id" not in value
    assert "warnings" not in failed_poll.outcome.result.message
    assert "warnings" not in cancelled_poll.outcome.result.message


def test_fins_wait_adapter_projects_completed_warning_exactly() -> None:
    """completed wait value 应机械序列化同一 typed warning。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: completed warning 丢失、重算或 JSON shape 漂移时抛出。
    """

    handle = FinsObservationHandle(
        handle_id=f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}9999999999999999",
        operation_kind=FinsOperationKind.UPLOAD_FILING,
        created_at=_OBSERVATION_TIME,
    )
    warning = CompanyMetadataWarning(
        kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
        message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    )
    result = FinsResultSummary(
        status=FinsResultStatus.SUCCESS,
        exit_code=FINS_RESULT_EXIT_SUCCESS,
        title="上传完成",
        details=(FinsEventDetail(label="stored files", value="1"),),
        error_kind=None,
        error_message=None,
        warnings=(warning,),
    )
    runtime = _FakeObservationRuntime(
        snapshots={
            handle.handle_id: FinsObservationSnapshot(
                handle=handle,
                status=FinsObservationStatus.SUCCEEDED,
                message="succeeded observation",
                result=result,
                error_kind=None,
                retry_after_seconds=None,
            )
        }
    )

    poll = FinsIngestionWaitPollAdapter(runtime=runtime).poll_wait(
        _wait_snapshot(handle.handle_id, UPLOAD_TOOL_NAME)
    )

    assert isinstance(poll, WaitPollReady)
    assert isinstance(poll.outcome, ResolveWaitCompletedOutcome)
    value = poll.outcome.result.value
    assert isinstance(value, Mapping)
    assert value["warnings"] == [warning.to_json()]


def test_fins_wait_adapter_projects_same_typed_download_object() -> None:
    """wait adapter 应直接序列化 runtime typed summary，不从 details 或 storage 反推。

    Returns:
        无。

    Raises:
        AssertionError: nested download 与 typed object 不一致时抛出。
    """

    handle = _observation_handle_with_id("abababababababab")
    download = FinsDownloadPublicSummary(
        source=FinsDownloadSource.SEC,
        canonical_ticker="AAPL",
        effective_filters=FinsDownloadEffectiveFilters(
            form_types=("10-K",),
            start_date="2024-01-01",
            end_date="2024-12-31",
            overwrite_existing=False,
            rebuild_local_artifacts=False,
        ),
        discovered_count=1,
        downloaded_count=1,
        skipped_count=0,
        rejected_count=0,
        failed_count=0,
        document_rows=(
            FinsDownloadPublicDocument(
                document_id="fil-downloaded",
                form_or_period="10-K",
                filing_date="2024-08-01",
                report_date="2024-06-30",
                covered_fiscal_periods=(),
                disposition=FinsDownloadDocumentDisposition.DOWNLOADED,
                reason_category=None,
                reason_message=None,
                artifact_locator="source/AAPL/fil-downloaded",
            ),
        ),
        missing_periods=(),
        omitted_count=0,
        terminal_disposition=FinsDownloadTerminalDisposition.SUCCEEDED,
    )
    result = FinsResultSummary(
        status=FinsResultStatus.SUCCESS,
        exit_code=FINS_RESULT_EXIT_SUCCESS,
        title="下载完成",
        details=(FinsEventDetail(label="ignored", value="must-not-project"),),
        error_kind=None,
        error_message=None,
        download=download,
    )
    runtime = _FakeObservationRuntime(
        snapshots={
            handle.handle_id: FinsObservationSnapshot(
                handle=handle,
                status=FinsObservationStatus.SUCCEEDED,
                message="succeeded observation",
                result=result,
                error_kind=None,
                retry_after_seconds=None,
            )
        }
    )

    poll = FinsIngestionWaitPollAdapter(runtime=runtime).poll_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(poll, WaitPollReady)
    assert isinstance(poll.outcome, ResolveWaitCompletedOutcome)
    value = poll.outcome.result.value
    assert isinstance(value, Mapping)
    assert value["download"] == download.to_json_value()
    download_value = value["download"]
    assert isinstance(download_value, Mapping)
    documents_value = download_value["documents"]
    assert isinstance(documents_value, list)
    assert len(documents_value) == 1
    document_value = documents_value[0]
    assert isinstance(document_value, Mapping)
    coverage_value = document_value["covered_fiscal_periods"]
    assert isinstance(coverage_value, list)
    assert coverage_value == []
    assert "details" not in value
    serialized = str(value)
    assert "must-not-project" not in serialized
    assert "https://" not in serialized
    assert "/Users/" not in serialized


def test_fins_wait_adapter_failure_contains_same_typed_download_and_failure() -> None:
    """失败 wait result 应序列化完整 download/failure，而非仅输出泛化错误。

    Returns:
        无。

    Raises:
        AssertionError: failure message 缺字段或泄漏内部内容时抛出。
    """

    handle = _observation_handle_with_id("acacacacacacacac")
    download = FinsDownloadPublicSummary(
        source=FinsDownloadSource.SEC,
        canonical_ticker="AAPL",
        effective_filters=FinsDownloadEffectiveFilters(
            form_types=("10-K",),
            start_date=None,
            end_date=None,
            overwrite_existing=False,
            rebuild_local_artifacts=False,
        ),
        discovered_count=0,
        downloaded_count=0,
        skipped_count=0,
        rejected_count=0,
        failed_count=0,
        document_rows=(),
        missing_periods=(),
        omitted_count=0,
        terminal_disposition=FinsDownloadTerminalDisposition.FAILED,
    )
    failure = FinsPublicFailure(
        kind=FinsPublicFailureKind.PROVIDER_TRANSPORT,
        source=FinsDownloadSource.SEC,
        transport_category=FinsDownloadTransportCategory.CONNECTION,
        safe_message="无法连接 SEC 来源",
        retry_hint="请稍后重试；若持续失败，请检查来源服务状态。",
    )
    result = FinsResultSummary(
        status=FinsResultStatus.FAILURE,
        exit_code=FINS_RESULT_EXIT_FAILURE,
        title="下载失败",
        details=(),
        error_kind=FinsErrorKind.PROVIDER,
        error_message=failure.safe_message,
        download=download,
        failure=failure,
    )
    runtime = _FakeObservationRuntime(
        snapshots={
            handle.handle_id: FinsObservationSnapshot(
                handle=handle,
                status=FinsObservationStatus.FAILED,
                message="failed observation",
                result=result,
                error_kind=FinsErrorKind.PROVIDER,
                retry_after_seconds=None,
            )
        }
    )

    poll = FinsIngestionWaitPollAdapter(runtime=runtime).poll_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(poll, WaitPollReady)
    assert isinstance(poll.outcome, ResolveWaitFailedOutcome)
    message_value = json.loads(poll.outcome.result.message)
    assert isinstance(message_value, Mapping)
    assert message_value["download"] == download.to_json_value()
    assert message_value["failure"] == failure.to_json_value()
    assert poll.outcome.result.hint == failure.retry_hint
    serialized = str(message_value)
    assert "https://" not in serialized
    assert "/Users/" not in serialized


def test_fins_wait_poll_adapter_rejects_failed_result_without_message() -> None:
    """failed observation 缺少业务错误说明时不得回退内部 message。"""

    failed = _observation_handle_with_id("1212121212121212")
    runtime = _FakeObservationRuntime(
        snapshots={
            failed.handle_id: FinsObservationSnapshot(
                handle=failed,
                status=FinsObservationStatus.FAILED,
                message="Observation activation failed.",
                result=FinsResultSummary(
                    status=FinsResultStatus.FAILURE,
                    exit_code=FINS_RESULT_EXIT_FAILURE,
                    title="Observation result",
                    details=(FinsEventDetail(label="ticker", value="AAPL"),),
                    error_kind=FinsErrorKind.EXECUTION,
                    error_message=None,
                ),
                error_kind=FinsErrorKind.EXECUTION,
                retry_after_seconds=None,
            )
        }
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    with pytest.raises(ValueError, match="must contain error_message"):
        adapter.poll_wait(_wait_snapshot(failed.handle_id, DOWNLOAD_TOOL_NAME))


def test_fins_wait_poll_adapter_corrupt_and_missing_handles_are_lost() -> None:
    """corrupt token 或缺失 handle 必须 resolve LOST。"""

    missing = _observation_handle_with_id("9999999999999999")
    adapter = FinsIngestionWaitPollAdapter(runtime=_FakeObservationRuntime(snapshots={}))

    corrupt_poll = adapter.poll_wait(_wait_snapshot("finsjob_00000000000000000000000000000007", DOWNLOAD_TOOL_NAME))
    missing_poll = adapter.poll_wait(_wait_snapshot(missing.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(corrupt_poll, WaitPollLost)
    assert isinstance(corrupt_poll.outcome, ResolveWaitLostOutcome)
    assert isinstance(missing_poll, WaitPollLost)
    assert isinstance(missing_poll.outcome, ResolveWaitLostOutcome)


def test_fins_wait_poll_adapter_transient_unavailable_is_not_ready() -> None:
    """transient unavailable 只表达 provider observation，Host 边界由 poll owner 判断。"""

    handle = _observation_handle_with_id("abababababababab")
    runtime = _FakeObservationRuntime(
        snapshots={},
        poll_errors={
            handle.handle_id: FinsObservationPollError(
                FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE,
                "Observation temporarily unavailable.",
            )
        },
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    poll = adapter.poll_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(poll, WaitPollNotReady)


def test_fins_wait_poll_adapter_old_snapshot_created_at_does_not_force_lost() -> None:
    """Service adapter 不得从 Host snapshot 创建时间制造终态 timeout。"""

    handle = _observation_handle_with_id("bcbcbcbcbcbcbcbc")
    runtime = _FakeObservationRuntime(
        snapshots={},
        poll_errors={
            handle.handle_id: FinsObservationPollError(
                FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE,
                "Observation temporarily unavailable.",
            )
        },
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    poll = adapter.poll_wait(
        _wait_snapshot(
            handle.handle_id,
            DOWNLOAD_TOOL_NAME,
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
    )

    assert isinstance(poll, WaitPollNotReady)


def test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation() -> None:
    """abandon_wait 应 best-effort cancel 并清理 observation record。"""

    handle = _observation_handle_with_id("cdcdcdcdcdcdcdcd")
    runtime = _FakeObservationRuntime(
        snapshots={handle.handle_id: _observation_snapshot(handle, FinsObservationStatus.RUNNING)}
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    result = adapter.abandon_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))
    poll = adapter.poll_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(result, WaitExternalJobLifecycleApplied)
    assert result.action is WaitExternalJobLifecycleAction.ABANDON
    assert runtime.cancelled_handles == (handle.handle_id,)
    assert runtime.abandoned_handles == (handle.handle_id,)
    assert isinstance(poll, WaitPollLost)


def test_fins_wait_poll_adapter_abandon_corrupt_token_is_noop() -> None:
    """abandon_wait 遇到 corrupt token 时不应调用 observation runtime。"""

    runtime = _FakeObservationRuntime(snapshots={})
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    result = adapter.abandon_wait(_wait_snapshot("finsjob_00000000000000000000000000000009", DOWNLOAD_TOOL_NAME))

    assert isinstance(result, WaitExternalJobLifecycleNoop)
    assert result.reason == "invalid_observation_handle"
    assert runtime.cancelled_handles == ()
    assert runtime.abandoned_handles == ()


def test_fins_wait_poll_adapter_abandon_missing_observation_is_noop() -> None:
    """abandon_wait 遇到缺失 observation 时应返回 missing no-op。"""

    handle = _observation_handle_with_id("1212121212121212")
    runtime = _FakeObservationRuntime(snapshots={})
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    result = adapter.abandon_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(result, WaitExternalJobLifecycleNoop)
    assert result.reason == "observation_missing"
    assert runtime.cancelled_handles == (handle.handle_id,)
    assert runtime.abandoned_handles == ()


def test_fins_wait_poll_adapter_abandon_lost_snapshot_is_noop() -> None:
    """abandon_wait 遇到 LOST snapshot 时应返回 missing no-op。"""

    handle = _observation_handle_with_id("3434343434343434")
    runtime = _FakeObservationRuntime(
        snapshots={handle.handle_id: _observation_snapshot(handle, FinsObservationStatus.LOST)}
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    result = adapter.abandon_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(result, WaitExternalJobLifecycleNoop)
    assert result.reason == "observation_missing"
    assert runtime.cancelled_handles == (handle.handle_id,)
    assert runtime.abandoned_handles == ()


def test_fins_wait_poll_adapter_abandon_non_transient_error_is_noop() -> None:
    """abandon_wait 遇到非临时 observation 错误时应返回 error no-op。"""

    handle = _observation_handle_with_id("5656565656565656")
    runtime = _FakeObservationRuntime(
        snapshots={handle.handle_id: _observation_snapshot(handle, FinsObservationStatus.RUNNING)},
        abandon_errors={
            handle.handle_id: FinsObservationPollError(
                FinsObservationPollErrorKind.PERMANENT_CORRUPT_HANDLE,
                "Observation handle is corrupt.",
            )
        },
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    result = adapter.abandon_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(result, WaitExternalJobLifecycleNoop)
    assert result.reason == "observation_error:permanent_corrupt_handle"
    assert runtime.cancelled_handles == (handle.handle_id,)
    assert runtime.abandoned_handles == (handle.handle_id,)


def test_fins_wait_poll_adapter_abandon_cancel_non_transient_error_is_noop() -> None:
    """abandon_wait 遇到 cancel 非临时 observation 错误时应返回 error no-op。"""

    handle = _observation_handle_with_id("6767676767676767")
    runtime = _FakeObservationRuntime(
        snapshots={handle.handle_id: _observation_snapshot(handle, FinsObservationStatus.RUNNING)},
        cancel_errors={
            handle.handle_id: FinsObservationPollError(
                FinsObservationPollErrorKind.PERMANENT_CORRUPT_HANDLE,
                "Observation handle is corrupt.",
            )
        },
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    result = adapter.abandon_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(result, WaitExternalJobLifecycleNoop)
    assert result.reason == "observation_error:permanent_corrupt_handle"
    assert runtime.cancelled_handles == (handle.handle_id,)
    assert runtime.abandoned_handles == ()


def test_fins_wait_poll_adapter_abandon_transient_unavailable_re_raises() -> None:
    """abandon_wait 遇到 transient unavailable 时应抛出供 Host 重试。"""

    handle = _observation_handle_with_id("7878787878787878")
    runtime = _FakeObservationRuntime(
        snapshots={handle.handle_id: _observation_snapshot(handle, FinsObservationStatus.RUNNING)},
        cancel_errors={
            handle.handle_id: FinsObservationPollError(
                FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE,
                "Observation temporarily unavailable.",
            )
        },
    )
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    with pytest.raises(FinsObservationPollError) as exc_info:
        adapter.abandon_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))

    assert exc_info.value.error_kind is FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE
    assert runtime.cancelled_handles == (handle.handle_id,)
    assert runtime.abandoned_handles == ()


def _wait_snapshot(
    resume_token: str,
    tool_name: str,
    *,
    created_at: datetime = _OBSERVATION_TIME,
) -> WaitAdapterSnapshot:
    """构造 Service adapter 测试用 Host snapshot。

    :param resume_token: Fins observation resume token。
    :param tool_name: 原始 awaiting 工具名。
    :param created_at: Host snapshot 创建时间。
    :returns: Host wait adapter snapshot。
    """

    return WaitAdapterSnapshot(
        tool_name=tool_name,
        resume_token=resume_token,
        created_at=created_at,
    )


def _observation_handle_with_id(hex_suffix: str) -> FinsObservationHandle:
    """构造测试用 observation handle。

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


@dataclass
class _FakeObservationRuntime(FinsObservationRuntime):
    """测试用 process-local observation runtime。

    :param snapshots: handle id 到 snapshot 的映射。
    :param poll_errors: handle id 到 poll 分类异常的映射。
    :param cancel_errors: handle id 到 cancel 分类异常的映射。
    :param abandon_errors: handle id 到 abandon 分类异常的映射。
    :param cancelled_handles: 已请求 cancel 的 handle id。
    :param abandoned_handles: 已请求 abandon 的 handle id。
    :param activated_handles: 已 activation 的 handle id。
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
        :raises FinsObservationPollError: 配置为 abandon 错误时抛出。
        """

        self.abandoned_handles = self.abandoned_handles + (handle.handle_id,)
        if self.abandon_errors is not None and handle.handle_id in self.abandon_errors:
            raise self.abandon_errors[handle.handle_id]
        self.snapshots.pop(handle.handle_id, None)


def _activation_request(tool_name: str, resume_token: str) -> WaitActivationRequest:
    """构造测试用 accepted wait activation request。

    :param tool_name: awaiting 工具名。
    :param resume_token: awaiting resume token。
    :returns: typed activation request。
    :raises ValueError: 字段非法时由 Host 契约抛出。
    """

    return WaitActivationRequest(
        tool_name=tool_name,
        await_spec=ToolAwaitSpec(
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
            deadline=None,
            resume_token=resume_token,
        ),
        accepted_ack=_accepted_ack(),
    )


def _accepted_ack() -> ToolAwaitingAcceptedAck:
    """构造测试用 Host awaiting accepted ack。

    :returns: accepted ack。
    :raises ValueError: ack 字段非法时由 Host 契约抛出。
    """

    tool_ref = ToolAwaitingEventRef(event_id="event-tool-awaiting-1", event_sequence=1)
    run_ref = ToolAwaitingEventRef(event_id="event-run-waiting-1", event_sequence=2)
    attempt_ref = ToolAwaitingEventRef(
        event_id="event-attempt-suspended-1",
        event_sequence=3,
    )
    return ToolAwaitingAcceptedAck(
        accepted_event_refs=(tool_ref, run_ref, attempt_ref),
        wait_id="wait-1",
        tool_awaiting_event_ref=tool_ref,
        run_waiting_event_ref=run_ref,
        attempt_suspended_event_ref=attempt_ref,
        result_digest="digest-1",
        idempotency_record_ref="idempotency-1",
    )
