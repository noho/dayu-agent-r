"""Fins download/preprocess awaiting tools provider 测试。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

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
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools import download_provider, preprocess_provider, provider as read_provider
from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME, FinsDownloadToolCallable
from dayu.fins.tools.preprocess_tools import PREPROCESS_TOOL_NAME, FinsPreprocessToolCallable
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderSpec,
)

_READ_PROVIDER_ID = "financial-tools"
_DOWNLOAD_PROVIDER_ID = "financial-download-tools"
_PREPROCESS_PROVIDER_ID = "financial-preprocess-tools"
_READ_SPEC_ID = "financial-read-tools"
_DOWNLOAD_SPEC_ID = "financial-download-tools"
_PREPROCESS_SPEC_ID = "financial-preprocess-tools"
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
