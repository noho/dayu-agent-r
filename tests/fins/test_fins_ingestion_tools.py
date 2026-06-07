"""Fins download/preprocess awaiting tools provider 测试。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import ToolAwaitingOutcome, ToolFailedOutcome
from dayu.fins.ingestion_runtime import (
    FinsIngestionExecutor,
    FinsIngestionJobRecord,
    FinsIngestionJobStatus,
    FinsIngestionOperationKind,
    FinsIngestionRuntime,
    FsFinsIngestionJobStore,
)
from dayu.fins.ingestion import (
    FINS_INGESTION_WAIT_ADAPTER_KEY,
    FinsIngestionWaitPollAdapter,
    build_fins_wait_adapter_registry,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools import download_provider, preprocess_provider, provider as read_provider
from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME, FinsDownloadToolCallable
from dayu.fins.tools.preprocess_tools import PREPROCESS_TOOL_NAME, FinsPreprocessToolCallable
from dayu.host.api import (
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
)
from dayu.host.durable.state import (
    ExternalJobRef,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
)
from dayu.host.wait_adapter import WaitPollLost, WaitPollNotReady, WaitPollReady
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderSpec,
)

_READ_PROVIDER_ID = "financial-read-tools"
_DOWNLOAD_PROVIDER_ID = "financial-download-tools"
_PREPROCESS_PROVIDER_ID = "financial-preprocess-tools"
_READ_SPEC_ID = "financial-read-tools"
_DOWNLOAD_SPEC_ID = "financial-download-tools"
_PREPROCESS_SPEC_ID = "financial-preprocess-tools"
_READ_SAMPLE_TOOL_NAME: Final[str] = "list_documents"
_PACKAGE_CONFIG_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "dayu" / "config"
_DOWNLOAD_START_FAILED_ERROR = "fins_download_start_failed"
_PREPROCESS_START_FAILED_ERROR = "fins_preprocess_start_failed"
_TERMINAL_JOB_STATUSES = frozenset(
    {
        FinsIngestionJobStatus.SUCCEEDED,
        FinsIngestionJobStatus.FAILED,
        FinsIngestionJobStatus.CANCELLED,
    }
)
_JOB_WAIT_TIMEOUT_SECONDS = 5.0
_JOB_WAIT_POLL_SECONDS = 0.02
_WAIT_RECORD_TIME = "2026-01-01T00:00:00Z"


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


class _OSErrorCreateJobStore(FsFinsIngestionJobStore):
    """测试用 job store，在创建 job 时模拟持久化失败。"""

    def create_job(self, record: FinsIngestionJobRecord) -> FinsIngestionJobRecord:
        """模拟 durable job record 创建失败。

        Args:
            record: 待创建的 job record。

        Returns:
            不返回。

        Raises:
            OSError: 始终抛出，用于覆盖工具启动失败分支。
        """

        del record
        raise OSError("job store unavailable")


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


def test_tools_discovery_discovers_read_download_and_preprocess_independently(tmp_path: Path) -> None:
    """ToolsDiscovery 应能独立发现 read、download、preprocess provider。"""

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
        )
    )

    reports_by_provider = {report.provider_id: report for report in result.provider_reports}
    assert tuple(reports_by_provider) == (
        _READ_PROVIDER_ID,
        _DOWNLOAD_PROVIDER_ID,
        _PREPROCESS_PROVIDER_ID,
    )
    assert reports_by_provider[_READ_PROVIDER_ID].spec_id == _READ_SPEC_ID
    assert reports_by_provider[_DOWNLOAD_PROVIDER_ID].spec_id == _DOWNLOAD_SPEC_ID
    assert reports_by_provider[_PREPROCESS_PROVIDER_ID].spec_id == _PREPROCESS_SPEC_ID
    assert DOWNLOAD_TOOL_NAME in reports_by_provider[_DOWNLOAD_PROVIDER_ID].tool_names
    assert PREPROCESS_TOOL_NAME in reports_by_provider[_PREPROCESS_PROVIDER_ID].tool_names
    assert DOWNLOAD_TOOL_NAME not in reports_by_provider[_READ_PROVIDER_ID].tool_names
    assert PREPROCESS_TOOL_NAME not in reports_by_provider[_READ_PROVIDER_ID].tool_names
    assert len({report.source_refs[0].source_id for report in result.provider_reports}) == 3


def test_workspace_overlay_enables_split_fins_providers(tmp_path: Path) -> None:
    """workspace overlay 应能分别启用 Fins read、download、preprocess providers。"""

    workspace_root = _build_workspace(tmp_path)
    _write_split_fins_provider_overlay(tmp_path, workspace_root)
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=tmp_path / "workspace" / "config"
    )

    for provider_id in (_READ_SPEC_ID, _DOWNLOAD_SPEC_ID, _PREPROCESS_SPEC_ID):
        provider_config = config.tool_discovery.providers[provider_id]
        assert provider_config.enabled is True
        assert "include_ingestion_tools" not in provider_config.config

    result = ToolsDiscovery().discover(_provider_specs_from_loaded_config(config))
    reports_by_spec = {report.spec_id: report for report in result.provider_reports}

    assert tuple(reports_by_spec) == (
        _READ_SPEC_ID,
        _DOWNLOAD_SPEC_ID,
        _PREPROCESS_SPEC_ID,
    )
    assert reports_by_spec[_READ_SPEC_ID].provider_id == _READ_PROVIDER_ID
    assert reports_by_spec[_DOWNLOAD_SPEC_ID].provider_id == _DOWNLOAD_PROVIDER_ID
    assert reports_by_spec[_PREPROCESS_SPEC_ID].provider_id == _PREPROCESS_PROVIDER_ID
    assert _READ_SAMPLE_TOOL_NAME in reports_by_spec[_READ_SPEC_ID].tool_names
    assert DOWNLOAD_TOOL_NAME in reports_by_spec[_DOWNLOAD_SPEC_ID].tool_names
    assert PREPROCESS_TOOL_NAME in reports_by_spec[_PREPROCESS_SPEC_ID].tool_names


def test_download_tool_returns_external_job_awaiting_outcome(tmp_path: Path) -> None:
    """下载工具应在 durable job 创建后返回 EXTERNAL_JOB awaiting outcome。"""

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
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    record = runtime.read_job(outcome.await_spec.resume_token)
    assert record.operation_kind is FinsIngestionOperationKind.DOWNLOAD
    assert record.normalized_ticker == "AAPL"
    _wait_ingestion_job_terminal(runtime, outcome.await_spec.resume_token)


def test_preprocess_tool_returns_external_job_awaiting_outcome(tmp_path: Path) -> None:
    """预处理工具应在 durable job 创建后返回 EXTERNAL_JOB awaiting outcome。"""

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
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    record = runtime.read_job(outcome.await_spec.resume_token)
    assert record.operation_kind is FinsIngestionOperationKind.PREPROCESS
    assert record.normalized_ticker == "AAPL"
    _wait_ingestion_job_terminal(runtime, outcome.await_spec.resume_token)


def test_tool_argument_error_returns_failed_outcome_before_job_creation(tmp_path: Path) -> None:
    """工具参数错误必须返回失败 outcome，且不得创建 durable job。"""

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


def test_download_tool_os_error_from_start_returns_start_failed_outcome(tmp_path: Path) -> None:
    """下载工具遇到 start_download OSError 时应返回 start-failed 失败 outcome。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = _runtime_with_job_store(
        workspace_root=workspace_root,
        job_store=_OSErrorCreateJobStore(root_dir=_job_store_root(workspace_root)),
    )

    outcome = asyncio.run(
        FinsDownloadToolCallable(runtime=runtime)(
            _call(DOWNLOAD_TOOL_NAME, {"ticker": "AAPL"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == _DOWNLOAD_START_FAILED_ERROR


def test_download_tool_unexpected_start_exception_returns_start_failed_outcome(tmp_path: Path) -> None:
    """下载工具遇到 start_download 非预期异常时应返回 start-failed 失败 outcome。"""

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

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == _DOWNLOAD_START_FAILED_ERROR


def test_preprocess_tool_os_error_from_start_returns_start_failed_outcome(tmp_path: Path) -> None:
    """预处理工具遇到 start_preprocess OSError 时应返回 start-failed 失败 outcome。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = _runtime_with_job_store(
        workspace_root=workspace_root,
        job_store=_OSErrorCreateJobStore(root_dir=_job_store_root(workspace_root)),
    )

    outcome = asyncio.run(
        FinsPreprocessToolCallable(runtime=runtime)(
            _call(PREPROCESS_TOOL_NAME, {"ticker": "AAPL"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == _PREPROCESS_START_FAILED_ERROR


def test_preprocess_tool_unexpected_start_exception_returns_start_failed_outcome(tmp_path: Path) -> None:
    """预处理工具遇到 start_preprocess 非预期异常时应返回 start-failed 失败 outcome。"""

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

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == _PREPROCESS_START_FAILED_ERROR


def test_ingestion_tool_schemas_hide_host_internal_fields(tmp_path: Path) -> None:
    """下载和预处理工具 schema 不应暴露 Host 内部治理字段。"""

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
    )

    for definition in definitions:
        schema_text = _schema_text(definition)
        assert "tool_call_id" not in schema_text
        assert "digest" not in schema_text
        assert "cursor" not in schema_text
        assert "raw job record" not in schema_text
        assert "Host" not in schema_text


def test_fins_wait_adapter_registry_binds_download_and_preprocess_tools(
    tmp_path: Path,
) -> None:
    """Fins wait adapter registry 应绑定 S4 稳定 awaiting 工具名。"""

    registry = build_fins_wait_adapter_registry(
        workspace_root=tmp_path.resolve(strict=False),
        tool_names=(PREPROCESS_TOOL_NAME, DOWNLOAD_TOOL_NAME),
    )

    download_binding = registry.resolve_binding(
        tool_name=DOWNLOAD_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    preprocess_binding = registry.resolve_binding(
        tool_name=PREPROCESS_TOOL_NAME,
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
    )
    assert download_binding is not None
    assert preprocess_binding is not None
    assert download_binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY
    assert preprocess_binding.adapter_key == FINS_INGESTION_WAIT_ADAPTER_KEY
    assert download_binding.resume_policy is WaitResumePolicy.POLL
    assert preprocess_binding.resume_policy is WaitResumePolicy.POLL


def test_fins_wait_adapter_registry_duplicate_binding_fails(tmp_path: Path) -> None:
    """重复 Fins wait binding 必须 deterministic fail fast。"""

    workspace_root = tmp_path.resolve(strict=False)
    try:
        build_fins_wait_adapter_registry(
            workspace_root=workspace_root,
            tool_names=(DOWNLOAD_TOOL_NAME, DOWNLOAD_TOOL_NAME),
        )
    except ValueError as exc:
        assert "duplicate Fins wait adapter binding" in str(exc)
    else:
        raise AssertionError("重复 Fins wait adapter binding 未失败")


def test_fins_wait_poll_adapter_maps_terminal_and_missing_jobs(
    tmp_path: Path,
) -> None:
    """Fins poll adapter 应把 job 状态映射为 Host wait resolve outcome。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)
    succeeded = _persist_job(runtime, "00000000000000000000000000000001", FinsIngestionJobStatus.SUCCEEDED)
    failed = _persist_job(runtime, "00000000000000000000000000000002", FinsIngestionJobStatus.FAILED)
    cancelled = _persist_job(runtime, "00000000000000000000000000000003", FinsIngestionJobStatus.CANCELLED)
    queued = _persist_job(runtime, "00000000000000000000000000000004", FinsIngestionJobStatus.QUEUED)
    running = _persist_job(runtime, "00000000000000000000000000000005", FinsIngestionJobStatus.RUNNING)
    cancelling = _persist_job(runtime, "00000000000000000000000000000006", FinsIngestionJobStatus.CANCELLING)

    succeeded_poll = adapter.poll_wait(_wait_record(succeeded.job_id, DOWNLOAD_TOOL_NAME))
    failed_poll = adapter.poll_wait(_wait_record(failed.job_id, DOWNLOAD_TOOL_NAME))
    cancelled_poll = adapter.poll_wait(_wait_record(cancelled.job_id, PREPROCESS_TOOL_NAME))
    queued_poll = adapter.poll_wait(_wait_record(queued.job_id, PREPROCESS_TOOL_NAME))
    running_poll = adapter.poll_wait(_wait_record(running.job_id, DOWNLOAD_TOOL_NAME))
    cancelling_poll = adapter.poll_wait(_wait_record(cancelling.job_id, PREPROCESS_TOOL_NAME))
    missing_poll = adapter.poll_wait(
        _wait_record("finsjob_00000000000000000000000000009999", DOWNLOAD_TOOL_NAME)
    )

    assert isinstance(succeeded_poll, WaitPollReady)
    assert isinstance(succeeded_poll.outcome, ResolveWaitCompletedOutcome)
    assert isinstance(failed_poll, WaitPollReady)
    assert isinstance(failed_poll.outcome, ResolveWaitFailedOutcome)
    assert isinstance(cancelled_poll, WaitPollReady)
    assert isinstance(cancelled_poll.outcome, ResolveWaitCancelledOutcome)
    assert isinstance(queued_poll, WaitPollNotReady)
    assert isinstance(running_poll, WaitPollNotReady)
    assert isinstance(cancelling_poll, WaitPollNotReady)
    assert isinstance(missing_poll, WaitPollLost)


def test_fins_wait_poll_adapter_maps_corrupt_job_evidence_to_lost(
    tmp_path: Path,
) -> None:
    """poll_wait 遇到损坏 job evidence 时应返回 lost，而不是抛给 poller。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)
    job_id = "finsjob_00000000000000000000000000000007"
    _write_corrupt_job_evidence(workspace_root, job_id)

    poll = adapter.poll_wait(_wait_record(job_id, DOWNLOAD_TOOL_NAME))

    assert isinstance(poll, WaitPollLost)
    assert isinstance(poll.outcome, ResolveWaitLostOutcome)


def test_fins_wait_poll_adapter_abandon_marks_job_cancellation_requested(
    tmp_path: Path,
) -> None:
    """abandon_wait 应请求取消 Fins job，不删除 job record。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)
    record = _persist_job(
        runtime,
        "00000000000000000000000000000005",
        FinsIngestionJobStatus.RUNNING,
    )

    adapter.abandon_wait(_wait_record(record.job_id, DOWNLOAD_TOOL_NAME))

    updated = runtime.read_job(record.job_id)
    assert updated.cancellation_requested is True
    assert updated.status is FinsIngestionJobStatus.CANCELLING


def test_fins_wait_poll_adapter_abandon_without_external_job_ref_is_noop(
    tmp_path: Path,
) -> None:
    """abandon_wait 缺少 external_job_ref 时不应抛错或修改 Fins job。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)
    record = _persist_job(
        runtime,
        "00000000000000000000000000000008",
        FinsIngestionJobStatus.RUNNING,
    )

    adapter.abandon_wait(
        _wait_record(
            record.job_id,
            DOWNLOAD_TOOL_NAME,
            include_external_job_ref=False,
        )
    )

    unchanged = runtime.read_job(record.job_id)
    assert unchanged.cancellation_requested is False
    assert unchanged.status is FinsIngestionJobStatus.RUNNING


def test_fins_wait_poll_adapter_abandon_missing_job_evidence_is_noop(
    tmp_path: Path,
) -> None:
    """abandon_wait 遇到缺失 job evidence 时不应抛错。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)

    adapter.abandon_wait(
        _wait_record("finsjob_00000000000000000000000000009998", DOWNLOAD_TOOL_NAME)
    )


def test_fins_wait_poll_adapter_abandon_corrupt_job_evidence_is_noop(
    tmp_path: Path,
) -> None:
    """abandon_wait 遇到损坏 job evidence 时不应抛错或删除 evidence 文件。"""

    workspace_root = _build_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    adapter = FinsIngestionWaitPollAdapter(runtime=runtime)
    job_id = "finsjob_00000000000000000000000000000009"
    corrupt_path = _write_corrupt_job_evidence(workspace_root, job_id)

    adapter.abandon_wait(_wait_record(job_id, DOWNLOAD_TOOL_NAME))

    assert corrupt_path.exists()


def _persist_job(
    runtime: FinsIngestionRuntime,
    job_id_suffix: str,
    status: FinsIngestionJobStatus,
) -> FinsIngestionJobRecord:
    """持久化指定状态的测试 job record。

    Args:
        runtime: 测试使用的 Fins ingestion runtime。
        job_id_suffix: 32 位十六进制 job id suffix。
        status: 目标 job 状态。

    Returns:
        已持久化 job record。

    Raises:
        OSError: job store 写入失败时抛出。
        ValueError: record 字段非法时抛出。
    """

    record = _job_record(job_id=f"finsjob_{job_id_suffix}", status=status)
    return runtime.job_store.create_job(record)


def _job_record(
    *,
    job_id: str,
    status: FinsIngestionJobStatus,
) -> FinsIngestionJobRecord:
    """构造测试用 Fins ingestion job record。

    Args:
        job_id: opaque job id。
        status: job 状态。

    Returns:
        Fins ingestion job record。

    Raises:
        无。
    """

    terminal = status in _TERMINAL_JOB_STATUSES
    now = _timestamp()
    return FinsIngestionJobRecord(
        job_id=job_id,
        operation_kind=FinsIngestionOperationKind.DOWNLOAD,
        normalized_ticker="AAPL",
        market="US",
        exchange=None,
        source="auto",
        source_kind=SourceKind.FILING,
        status=status,
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=now if terminal else None,
        request_summary={"ticker": "AAPL"},
        result_summary={"written_document_ids": ["aapl-2024-10k"]}
        if status is FinsIngestionJobStatus.SUCCEEDED
        else {},
        failure_summary={"message": "download failed"}
        if status is FinsIngestionJobStatus.FAILED
        else {},
        cancellation_requested=status
        in {FinsIngestionJobStatus.CANCELLING, FinsIngestionJobStatus.CANCELLED},
    )


def _wait_record(
    job_id: str,
    tool_name: str,
    *,
    include_external_job_ref: bool = True,
) -> WaitRecordRow:
    """构造测试用 Host wait record。

    Args:
        job_id: Fins external job id。
        tool_name: 原始 awaiting 工具名。
        include_external_job_ref: 是否带 external job ref。

    Returns:
        Host wait record row。

    Raises:
        ValueError: 字段非法时由 Host durable 类型抛出。
    """

    external_job_ref = (
        ExternalJobRef(
            adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY,
            external_job_id=job_id,
        )
        if include_external_job_ref
        else None
    )
    return WaitRecordRow(
        wait_id=f"wait-{job_id}",
        session_id="session-fins",
        run_id="run-fins",
        attempt_id="attempt-fins",
        execution_id="execution-fins",
        tool_call_id=f"call-{tool_name}",
        tool_name=tool_name,
        adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY,
        await_kind=ToolAwaitKind.EXTERNAL_JOB.value,
        resume_policy=WaitResumePolicy.POLL,
        resume_token=job_id,
        snapshot_ref=None,
        external_job_ref=external_job_ref,
        accept_idempotency_key=f"accept-{job_id}",
        resolve_idempotency_key=None,
        resolve_semantic_digest=None,
        deadline_at=None,
        expires_at=None,
        status=WaitRecordStatus.WAITING,
        created_event_id=f"event-created-{job_id}",
        created_event_sequence=1,
        updated_event_id=f"event-updated-{job_id}",
        updated_event_sequence=1,
        created_at=_WAIT_RECORD_TIME,
        updated_at=_WAIT_RECORD_TIME,
        terminal_at=None,
    )


def _timestamp() -> str:
    """返回测试用 UTC 时间戳。

    Returns:
        UTC ISO8601 字符串。

    Raises:
        无。
    """

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_corrupt_job_evidence(workspace_root: Path, job_id: str) -> Path:
    """写入损坏的 Fins job evidence 文件。

    Args:
        workspace_root: Fins workspace root。
        job_id: opaque job id。

    Returns:
        损坏 evidence 文件路径。

    Raises:
        OSError: 目录或文件写入失败时抛出。
    """

    path = _job_store_root(workspace_root) / f"{job_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    return path


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


def _runtime_with_job_store(
    *,
    workspace_root: Path,
    job_store: FsFinsIngestionJobStore,
) -> FinsIngestionRuntime:
    """使用指定 job store 构造 ingestion runtime。

    Args:
        workspace_root: Fins workspace root。
        job_store: 测试注入的 job store。

    Returns:
        Fins ingestion runtime。

    Raises:
        OSError: 默认 Fins runtime 初始化失败时抛出。
    """

    base_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    return FinsIngestionRuntime.create(
        source_repository=base_runtime.source_repository,
        blob_repository=base_runtime.blob_repository,
        filing_maintenance_repository=base_runtime.filing_maintenance_repository,
        processed_repository=base_runtime.processed_repository,
        processor_registry=base_runtime.processor_registry,
        job_store=job_store,
    )


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
        Fins ingestion runtime。

    Raises:
        OSError: 默认 Fins runtime 初始化失败时抛出。
    """

    base_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    return FinsIngestionRuntime.create(
        source_repository=base_runtime.source_repository,
        blob_repository=base_runtime.blob_repository,
        filing_maintenance_repository=base_runtime.filing_maintenance_repository,
        processed_repository=base_runtime.processed_repository,
        processor_registry=base_runtime.processor_registry,
        job_store=base_runtime.ingestion_job_store,
        executor=executor,
    )


def _wait_ingestion_job_terminal(
    runtime: FinsIngestionRuntime,
    job_id: str,
) -> FinsIngestionJobRecord:
    """等待 ingestion job 进入终态。

    Args:
        runtime: 与工具共用 workspace 的 ingestion runtime。
        job_id: opaque job id。

    Returns:
        终态 job record。

    Raises:
        AssertionError: 超时未进入终态时抛出。
    """

    deadline = time.monotonic() + _JOB_WAIT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        record = runtime.read_job(job_id)
        if record.status in _TERMINAL_JOB_STATUSES:
            return record
        time.sleep(_JOB_WAIT_POLL_SECONDS)
    raise AssertionError(f"job 未进入终态: {job_id}")


def _write_split_fins_provider_overlay(tmp_path: Path, workspace_root: Path) -> None:
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
                "allow_empty": False,
                "config": {
                    "workspace_root": str(workspace_root),
                    "include_read_tools": True,
                    "limits": {},
                },
            },
            _DOWNLOAD_SPEC_ID: {
                "import_path": "dayu.fins.tools.download_provider:discover_tools",
                "entry_point": None,
                "source_kind": "explicit_provider",
                "source_id": "dayu.fins.tools.download_provider",
                "enabled": True,
                "allow_empty": False,
                "config": {"workspace_root": str(workspace_root)},
            },
            _PREPROCESS_SPEC_ID: {
                "import_path": "dayu.fins.tools.preprocess_provider:discover_tools",
                "entry_point": None,
                "source_kind": "explicit_provider",
                "source_id": "dayu.fins.tools.preprocess_provider",
                "enabled": True,
                "allow_empty": False,
                "config": {"workspace_root": str(workspace_root)},
            },
        }
    }
    _write_json(tmp_path / "workspace" / "config" / "tool_discovery.json", payload)


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
                allow_empty=provider_config.allow_empty,
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
        allow_empty=False,
        config={"workspace_root": str(workspace_root)},
    )


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


def _context() -> BatchToolExecutionContext:
    """构造批执行上下文。

    Args:
        无。

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
        cancellation_token=_OpenCancellationToken(),
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
