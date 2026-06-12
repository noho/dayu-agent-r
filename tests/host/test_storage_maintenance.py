"""Host storage maintenance dry-run public entrypoint 测试。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host import (
    CreateSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostClosedError,
    HostStorageMaintenanceRequest,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    run_storage_maintenance,
)
from dayu.host.api import (
    AttemptDispatchSnapshot,
    HostCommandHandleOptions,
    HostInput,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    StartRunRequest,
)
from dayu.host.command import (
    HostCommandHandle,
    create_host_command_handle,
    create_session as command_create_session,
    start_run,
)
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.durable.payload import write_payload_descriptor_for_artifact
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import default_memory_projection_policy
from dayu.host.open_host import open_host
from dayu.host.read_api import get_run, get_session
from dayu.host.storage_maintenance import report_storage_usage

_OLD_TIMESTAMP_SECONDS = 1_700_000_000


@dataclass(frozen=True, slots=True)
class _NoopWorkerHandle(LocalWorkerHandle):
    """不会产出事件的测试 worker handle。"""

    worker_id: str

    @property
    def local_worker_id(self) -> str:
        """返回测试 worker id。

        :returns: 测试 worker id。
        """

        return self.worker_id

    def events(self) -> AsyncIterator[EngineEvent]:
        """返回空 EngineEvent stream。

        :returns: 空异步迭代器。
        """

        return _empty_engine_events()

    async def close(self) -> None:
        """关闭测试 worker handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """接收取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        return None


@dataclass(frozen=True, slots=True)
class _NoopWorker(LocalEngineWorker):
    """不会启动真实 Engine 的测试 worker。"""

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch snapshot 并返回空 worker handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine run request。
        :returns: 空 worker handle。
        """

        return _NoopWorkerHandle(worker_id=f"noop-{snapshot.attempt_id}")


@dataclass(frozen=True, slots=True)
class _NoopWorkerFactory(LocalEngineWorkerFactory):
    """测试用 no-op worker factory。"""

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 no-op worker。

        :param snapshot: dispatch snapshot。
        :returns: no-op worker。
        """

        return _NoopWorker()


async def _empty_engine_events() -> AsyncIterator[EngineEvent]:
    """返回空 EngineEvent async iterator。

    :returns: 空异步迭代器。
    """

    if False:
        yield _unreachable_engine_event()


def _unreachable_engine_event() -> EngineEvent:
    """类型收窄用不可达 EngineEvent。

    :returns: 不会实际返回的 EngineEvent。
    :raises AssertionError: 若被执行则说明测试 no-op stream 失效。
    """

    raise AssertionError("noop worker must not emit events")


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: HostCommandHandleOptions。
    """

    return HostCommandHandleOptions(
        host_handle_id="storage-maintenance-test",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=3,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.01,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _open_host_options(tmp_path: Path) -> OpenHostOptions:
    """构造测试用 OpenHostOptions。

    :param tmp_path: pytest 临时目录。
    :returns: OpenHostOptions。
    """

    return OpenHostOptions(
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=3,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.01,
        payload_inline_threshold_bytes=4096,
        lane_db_path=tmp_path / "lane.sqlite3",
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.1,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=False,
            ),
            agent_policy=AgentPolicy(
                max_iterations=1,
                continuation_max_attempts=0,
                allow_tool_calls=False,
                tool_execution_timeout_seconds=1.0,
            ),
        ),
        worker_factory=_NoopWorkerFactory(),
        tooling_options=None,
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
    )


def _runner_spec() -> RunnerSpec:
    """构造测试用 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _context(operation_name: str) -> HostCallContext:
    """构造测试用 Host call context。

    :param operation_name: 操作名。
    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=f"{operation_name}-request",
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name=operation_name,
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="storage_maintenance",
            correlation_id=f"corr-{operation_name}",
        ),
    )


def _create_request() -> CreateSessionRequest:
    """构造 create session 请求。

    :returns: CreateSessionRequest。
    """

    return CreateSessionRequest(
        context=_context("create_session"),
        client_request_id="create-session",
        bind_slot=False,
        scope=None,
        slot_key=None,
        metadata=(),
    )


def _start_request(session_id: str) -> StartRunRequest:
    """构造 start run 请求。

    :param session_id: Session id。
    :returns: StartRunRequest。
    """

    return StartRunRequest(
        context=_context("start_run"),
        session_id=session_id,
        client_request_id="start-run",
        input=HostInput(
            display_text="storage maintenance run",
            payload_ref=None,
            payload_digest=None,
        ),
        execution_target="storage-maintenance-target",
        queue_policy="queue",
    )


def test_storage_maintenance_dry_run_reports_candidates_without_deleting(
    tmp_path: Path,
) -> None:
    """dry-run 返回候选和物理 size，但不删除文件或 descriptor row。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session = command_create_session(host, _create_request())
        run = start_run(host, _start_request(session.session_id))
        referenced_path = _write_referenced_artifact(host, options.artifact_root)
        orphan_path = _write_orphan_artifact(options.artifact_root, b"orphan")
        _set_old_mtime(options.artifact_root / referenced_path)
        _set_old_mtime(options.artifact_root / orphan_path)
        _write_non_artifact_files(options.artifact_root)

        before_usage = report_storage_usage(host)
        before_session = get_session(host, session.session_id)
        before_run = get_run(host, run.run_id)

        result = run_storage_maintenance(
            host,
            HostStorageMaintenanceRequest(run_wal_checkpoint=False),
        )

        after_usage = report_storage_usage(host)
        after_session = get_session(host, session.session_id)
        after_run = get_run(host, run.run_id)
    finally:
        host.close()

    assert result.orphan_artifact_candidates == (orphan_path,)
    assert result.reclaimed_artifact_paths == ()
    assert result.file_errors == ()
    assert result.wal_checkpoint is None
    assert result.physical_artifact_bytes == (
        (options.artifact_root / referenced_path).stat().st_size
        + (options.artifact_root / orphan_path).stat().st_size
    )
    assert (options.artifact_root / orphan_path).is_file()
    assert (options.artifact_root / referenced_path).is_file()
    assert after_usage.event_log_rows == before_usage.event_log_rows
    assert after_usage.payload_descriptor_rows == before_usage.payload_descriptor_rows
    assert after_session.status == before_session.status
    assert after_run.status == before_run.status


def test_storage_maintenance_wal_checkpoint_true_returns_result(
    tmp_path: Path,
) -> None:
    """默认 maintenance 用独立 connection 返回 WAL checkpoint 诊断。"""

    host = create_host_command_handle(_command_options(tmp_path))
    try:
        result = run_storage_maintenance(host, HostStorageMaintenanceRequest())
    finally:
        host.close()

    assert result.wal_checkpoint is not None
    assert result.wal_checkpoint.mode.value == "PASSIVE"


def test_storage_maintenance_reclaim_true_fails_fast_without_deleting(
    tmp_path: Path,
) -> None:
    """当前 slice 不支持 destructive reclaim，且 fail fast 不删除文件。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    try:
        orphan_path = _write_orphan_artifact(options.artifact_root, b"blocked")
        _set_old_mtime(options.artifact_root / orphan_path)
        before_usage = report_storage_usage(host)

        with pytest.raises(HostApiError) as exc_info:
            run_storage_maintenance(
                host,
                HostStorageMaintenanceRequest(reclaim_orphan_artifacts=True),
            )

        after_usage = report_storage_usage(host)
    finally:
        host.close()

    assert exc_info.value.code == HostApiErrorCode.UNSUPPORTED_OPERATION
    assert (options.artifact_root / orphan_path).is_file()
    assert after_usage.payload_descriptor_rows == before_usage.payload_descriptor_rows
    assert after_usage.event_log_rows == before_usage.event_log_rows


@pytest.mark.asyncio
async def test_open_host_async_handle_runs_storage_maintenance_dry_run(
    tmp_path: Path,
) -> None:
    """open_host async handle 暴露 storage maintenance dry-run 入口。"""

    async with open_host(_open_host_options(tmp_path)) as host:
        result = await host.run_storage_maintenance(
            HostStorageMaintenanceRequest(run_wal_checkpoint=False)
        )

    assert result.wal_checkpoint is None
    assert result.reclaimed_artifact_paths == ()


@pytest.mark.asyncio
async def test_open_host_run_storage_maintenance_fails_after_close(
    tmp_path: Path,
) -> None:
    """public handle 关闭后 maintenance 使用当前 closed handle 错误语义。"""

    manager = open_host(_open_host_options(tmp_path))
    host = await manager.__aenter__()
    await host.close()

    with pytest.raises(HostClosedError):
        await host.run_storage_maintenance(HostStorageMaintenanceRequest())


def _write_referenced_artifact(host: HostCommandHandle, artifact_root: Path) -> str:
    """写入被 descriptor 引用的 artifact。

    :param host: Host command handle。
    :param artifact_root: artifact root。
    :returns: artifact 相对路径。
    """

    artifact_ref = LocalArtifactStore(artifact_root).write_artifact_bytes(
        b"referenced"
    )

    def write_descriptor(transaction: HostTransaction) -> None:
        """写入 artifact descriptor。

        :param transaction: Host write transaction。
        :returns: ``None``。
        """

        write_payload_descriptor_for_artifact(
            transaction,
            "payload-ref-referenced",
            artifact_ref,
            "application/octet-stream",
            {},
        )

    host._run_write(write_descriptor)
    return artifact_ref.artifact_relative_path


def _write_orphan_artifact(artifact_root: Path, content: bytes) -> str:
    """写入未被 descriptor 引用的已发布 artifact。

    :param artifact_root: artifact root。
    :param content: 文件内容。
    :returns: artifact 相对路径。
    """

    artifact_ref = LocalArtifactStore(artifact_root).write_artifact_bytes(content)
    return artifact_ref.artifact_relative_path


def _write_non_artifact_files(artifact_root: Path) -> None:
    """写入不应被 maintenance 统计为 artifact 的文件。

    :param artifact_root: artifact root。
    :returns: ``None``。
    """

    (artifact_root / ".tmp").mkdir(exist_ok=True)
    (artifact_root / ".tmp" / "temp-file").write_bytes(b"temp")
    (artifact_root / "audit").mkdir(exist_ok=True)
    (artifact_root / "audit" / "audit.jsonl").write_bytes(b"audit")
    (artifact_root / "tool-trace").mkdir(exist_ok=True)
    (artifact_root / "tool-trace" / "trace.jsonl").write_bytes(b"trace")


def _set_old_mtime(path: Path) -> None:
    """把文件 mtime 设置到默认 grace window 之前。

    :param path: 文件路径。
    :returns: ``None``。
    """

    os.utime(path, (_OLD_TIMESTAMP_SECONDS, _OLD_TIMESTAMP_SECONDS))
