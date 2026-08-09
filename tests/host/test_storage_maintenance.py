"""Host storage maintenance public entrypoint 测试。"""

from __future__ import annotations

from dayu.engine.contracts.structured_output import StructuredOutputCapability

import os
from functools import partial
from collections.abc import AsyncIterator, Mapping, Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
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
    OpenHostAdminOptions,
    OpenHostOptions,
    HostSessionEventDeliveryPolicy,
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
    create_session as command_create_session,
    start_run,
)
from dayu.host.durable import storage_lifecycle as storage_lifecycle_module
from dayu.host.durable.artifact import LocalArtifactRef, LocalArtifactStore
from dayu.host.durable.errors import HostArtifactWriteError, HostDurableError
from dayu.host.durable.payload import write_payload_descriptor_for_artifact
from dayu.host.durable.schema import (
    TABLE_HOST_MEMORY_SNAPSHOTS,
    TABLE_PAYLOAD_DESCRIPTORS,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import default_memory_projection_policy
from dayu.host.open_host import open_host_admin
from dayu.host.read_api import get_run, get_session
from dayu.host import storage_maintenance as storage_maintenance_module
from dayu.host.storage_maintenance import report_storage_usage
from tests.host.execution_handle_support import (
    create_execution_command_handle,
    deterministic_ordinary_run_baseline,
)

_OLD_TIMESTAMP_SECONDS = 1_700_000_000
_create_execution_handle = partial(
    create_execution_command_handle,
    ordinary_run_baseline=deterministic_ordinary_run_baseline(
        "storage-maintenance"
    ),
    memory_projection_policy=default_memory_projection_policy(),
    tooling_options=None,
    context_budget_policy=None,
    enable_truncation_manager=False,
)


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
                fallback_prompt="test fallback prompt",
                continuation_prompt="test continuation prompt",
            ),
        ),
        worker_factory=_NoopWorkerFactory(),
        tooling_options=None,
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
        session_event_delivery_policy=HostSessionEventDeliveryPolicy(
            transient_mailbox_max_items=512,
            max_subscriptions_per_session=4,
        ),
    )


def _open_host_admin_options(tmp_path: Path) -> OpenHostAdminOptions:
    """从测试 execution options 投影同源 admin durable options。

    :param tmp_path: pytest 临时目录。
    :returns: HostAdmin opener options。
    :raises Exception: 不主动抛出异常。
    """

    options = _open_host_options(tmp_path)
    return OpenHostAdminOptions(
        db_path=options.db_path,
        artifact_root=options.artifact_root,
        create_parent_dirs=options.create_parent_dirs,
        sqlite_busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
        sqlite_write_busy_retry_count=options.sqlite_write_busy_retry_count,
        sqlite_write_retry_initial_delay_seconds=(
            options.sqlite_write_retry_initial_delay_seconds
        ),
        sqlite_write_retry_backoff_multiplier=(
            options.sqlite_write_retry_backoff_multiplier
        ),
        sqlite_write_retry_max_delay_seconds=(
            options.sqlite_write_retry_max_delay_seconds
        ),
        payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
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
        structured_output_capability=StructuredOutputCapability.NONE,
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
    host = _create_execution_handle(options)
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
    assert result.memory_snapshot_integrity_issues == ()
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

    host = _create_execution_handle(_command_options(tmp_path))
    try:
        result = run_storage_maintenance(host, HostStorageMaintenanceRequest())
    finally:
        host.close()

    assert result.wal_checkpoint is not None
    assert result.wal_checkpoint.mode.value == "PASSIVE"


def test_storage_maintenance_reports_memory_snapshot_integrity_issue(
    tmp_path: Path,
) -> None:
    """maintenance result 暴露 memory snapshot integrity 只读诊断。"""

    host = _create_execution_handle(_command_options(tmp_path))
    try:
        _insert_invalid_memory_snapshot_json(host)

        result = run_storage_maintenance(
            host,
            HostStorageMaintenanceRequest(run_wal_checkpoint=False),
        )
    finally:
        host.close()

    assert len(result.memory_snapshot_integrity_issues) == 1
    issue = result.memory_snapshot_integrity_issues[0]
    assert issue.failure_kind.value == "invalid_json"
    assert issue.snapshot_id == "snapshot-invalid-json"
    assert issue.session_id == "session-invalid-json"
    assert issue.checkpoint_event_sequence == 0


def test_storage_maintenance_reclaim_true_deletes_orphan_without_db_row_changes(
    tmp_path: Path,
) -> None:
    """opt-in reclaim 删除 orphan 物理文件，不删除 SQLite row 或被引用文件。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session = command_create_session(host, _create_request())
        run = start_run(host, _start_request(session.session_id))
        referenced_path = _write_referenced_artifact(host, options.artifact_root)
        orphan_path = _write_orphan_artifact(options.artifact_root, b"reclaim")
        _set_old_mtime(options.artifact_root / referenced_path)
        _set_old_mtime(options.artifact_root / orphan_path)
        before_usage = report_storage_usage(host)
        before_session = get_session(host, session.session_id)
        before_run = get_run(host, run.run_id)

        result = run_storage_maintenance(
            host,
            HostStorageMaintenanceRequest(
                reclaim_orphan_artifacts=True,
                run_wal_checkpoint=False,
            ),
        )

        after_usage = report_storage_usage(host)
        after_session = get_session(host, session.session_id)
        after_run = get_run(host, run.run_id)
    finally:
        host.close()

    assert result.orphan_artifact_candidates == (orphan_path,)
    assert result.reclaimed_artifact_paths == (orphan_path,)
    assert result.file_errors == ()
    assert not (options.artifact_root / orphan_path).exists()
    assert (options.artifact_root / referenced_path).is_file()
    assert after_usage.payload_descriptor_rows == before_usage.payload_descriptor_rows
    assert after_usage.event_log_rows == before_usage.event_log_rows
    assert after_session.status == before_session.status
    assert after_run.status == before_run.status


def test_storage_maintenance_reclaim_keeps_shared_referenced_artifact(
    tmp_path: Path,
) -> None:
    """同一物理 artifact 仍有其它 descriptor 引用时不进入回收候选。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    try:
        artifact_ref = _write_referenced_artifact_with_ref(
            host,
            options.artifact_root,
            b"shared",
            "payload-ref-shared-a",
        )
        _write_artifact_descriptor(host, artifact_ref, "payload-ref-shared-b")
        _delete_payload_descriptor(host, "payload-ref-shared-a")
        _set_old_mtime(options.artifact_root / artifact_ref.artifact_relative_path)

        result = run_storage_maintenance(
            host,
            HostStorageMaintenanceRequest(
                reclaim_orphan_artifacts=True,
                run_wal_checkpoint=False,
            ),
        )
        after_usage = report_storage_usage(host)
    finally:
        host.close()

    assert result.orphan_artifact_candidates == ()
    assert result.reclaimed_artifact_paths == ()
    assert result.file_errors == ()
    assert (options.artifact_root / artifact_ref.artifact_relative_path).is_file()
    assert after_usage.payload_descriptor_rows == 1


def test_storage_maintenance_reclaim_recheck_hit_skips_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """public maintenance recheck 看见 scan 后新增 descriptor 并跳过删除。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    try:
        artifact_ref = _write_orphan_artifact_ref(options.artifact_root, b"recheck")
        _set_old_mtime(options.artifact_root / artifact_ref.artifact_relative_path)
        original_scan = storage_maintenance_module.scan_orphan_artifact_files

        def scan_then_write_descriptor(
            artifact_root: Path,
            referenced: AbstractSet[str],
            *,
            now: datetime,
            grace_seconds: float,
        ) -> tuple[str, ...]:
            """扫描完成后写入 descriptor，模拟 scan/recheck 之间的新引用。

            :param artifact_root: artifact 根目录。
            :param referenced: 扫描时已知的引用路径集合。
            :param now: 扫描使用的当前时间。
            :param grace_seconds: orphan grace window 秒数。
            :returns: 原始扫描候选。
            """

            candidates = original_scan(
                artifact_root,
                referenced,
                now=now,
                grace_seconds=grace_seconds,
            )
            _write_artifact_descriptor(host, artifact_ref, "payload-ref-recheck")
            return candidates

        monkeypatch.setattr(
            storage_maintenance_module,
            "scan_orphan_artifact_files",
            scan_then_write_descriptor,
        )

        result = run_storage_maintenance(
            host,
            HostStorageMaintenanceRequest(
                reclaim_orphan_artifacts=True,
                run_wal_checkpoint=False,
            ),
        )
        after_usage = report_storage_usage(host)
    finally:
        host.close()

    assert result.orphan_artifact_candidates == (
        artifact_ref.artifact_relative_path,
    )
    assert result.reclaimed_artifact_paths == ()
    assert result.file_errors == ()
    assert (options.artifact_root / artifact_ref.artifact_relative_path).is_file()
    assert after_usage.payload_descriptor_rows == 1


def test_storage_maintenance_recheck_durable_error_fails_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """recheck 的 durable 错误经 public facade fail-safe 传播。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    try:
        orphan_path = _write_orphan_artifact(options.artifact_root, b"recheck-error")
        _set_old_mtime(options.artifact_root / orphan_path)

        def fail_recheck(
            transaction: HostTransaction,
            relative_path: str,
        ) -> bool:
            """模拟 recheck read transaction 中 durable 层失败。

            :param transaction: Host read transaction。
            :param relative_path: artifact root 下的 POSIX 相对路径。
            :returns: 不会返回。
            :raises HostDurableError: 始终抛出测试错误。
            """

            raise HostDurableError("forced recheck durable failure")

        monkeypatch.setattr(
            storage_maintenance_module,
            "artifact_relative_path_is_referenced",
            fail_recheck,
        )

        with pytest.raises(HostApiError) as exc_info:
            run_storage_maintenance(
                host,
                HostStorageMaintenanceRequest(
                    reclaim_orphan_artifacts=True,
                    run_wal_checkpoint=False,
                ),
            )
    finally:
        host.close()

    assert exc_info.value.code == HostApiErrorCode.INTERNAL_ERROR
    assert "durable operation failed" in exc_info.value.message
    assert isinstance(exc_info.value.__cause__, HostDurableError)
    assert (options.artifact_root / orphan_path).is_file()


def test_storage_maintenance_reclaim_file_error_keeps_processing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单文件删除失败进入 file_errors，其它候选仍继续回收。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    try:
        failing_path = _write_orphan_artifact(options.artifact_root, b"fail-delete")
        deleted_path = _write_orphan_artifact(options.artifact_root, b"delete-ok")
        _set_old_mtime(options.artifact_root / failing_path)
        _set_old_mtime(options.artifact_root / deleted_path)
        original_delete = storage_lifecycle_module.delete_artifact_file

        def flaky_delete(artifact_root: Path, relative_path: str) -> bool:
            """对指定文件注入删除失败，其它文件走真实删除 helper。"""

            if relative_path == failing_path:
                raise HostArtifactWriteError("forced delete failure")
            return original_delete(artifact_root, relative_path)

        monkeypatch.setattr(
            storage_lifecycle_module,
            "delete_artifact_file",
            flaky_delete,
        )

        result = run_storage_maintenance(
            host,
            HostStorageMaintenanceRequest(
                reclaim_orphan_artifacts=True,
                run_wal_checkpoint=False,
            ),
        )
    finally:
        host.close()

    assert set(result.orphan_artifact_candidates) == {failing_path, deleted_path}
    assert result.reclaimed_artifact_paths == (deleted_path,)
    assert len(result.file_errors) == 1
    assert result.file_errors[0].path == failing_path
    assert result.file_errors[0].operation == "delete_artifact_file"
    assert "forced delete failure" in result.file_errors[0].message
    assert result.file_errors[0].json_value() == {
        "path": failing_path,
        "operation": "delete_artifact_file",
        "message": "forced delete failure",
    }
    assert (options.artifact_root / failing_path).is_file()
    assert not (options.artifact_root / deleted_path).exists()


def test_storage_maintenance_reclaim_is_idempotent(tmp_path: Path) -> None:
    """连续两次 opt-in reclaim 时，第二次无候选且不抛错。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    try:
        orphan_path = _write_orphan_artifact(options.artifact_root, b"idempotent")
        _set_old_mtime(options.artifact_root / orphan_path)
        request = HostStorageMaintenanceRequest(
            reclaim_orphan_artifacts=True,
            run_wal_checkpoint=False,
        )

        first_result = run_storage_maintenance(host, request)
        second_result = run_storage_maintenance(host, request)
    finally:
        host.close()

    assert first_result.orphan_artifact_candidates == (orphan_path,)
    assert first_result.reclaimed_artifact_paths == (orphan_path,)
    assert first_result.file_errors == ()
    assert second_result.orphan_artifact_candidates == ()
    assert second_result.reclaimed_artifact_paths == ()
    assert second_result.file_errors == ()


def test_storage_maintenance_result_json_value_is_stable_self_explaining_and_non_negative(
    tmp_path: Path,
) -> None:
    """maintenance result json_value 返回稳定、自解释且非负的 JSON object。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    try:
        orphan_path = _write_orphan_artifact(options.artifact_root, b"json-value")
        _set_old_mtime(options.artifact_root / orphan_path)
        result = run_storage_maintenance(
            host,
            HostStorageMaintenanceRequest(run_wal_checkpoint=False),
        )
        values = result.json_value()
    finally:
        host.close()

    assert isinstance(values, Mapping)
    expected_keys = (
        "usage",
        "physical_artifact_bytes",
        "orphan_artifact_candidates",
        "reclaimed_artifact_paths",
        "file_errors",
        "memory_snapshot_integrity_issues",
        "wal_checkpoint",
    )
    assert tuple(values.keys()) == expected_keys
    assert isinstance(values["usage"], Mapping)
    assert _json_int(values, "physical_artifact_bytes") >= 0
    assert values["orphan_artifact_candidates"] == [orphan_path]
    assert values["reclaimed_artifact_paths"] == []
    assert values["file_errors"] == []
    assert values["memory_snapshot_integrity_issues"] == []
    assert values["wal_checkpoint"] is None


@pytest.mark.asyncio
async def test_open_host_async_handle_runs_storage_maintenance_dry_run(
    tmp_path: Path,
) -> None:
    """HostAdmin async handle 暴露 storage maintenance dry-run 入口。"""

    async with open_host_admin(_open_host_admin_options(tmp_path)) as host_admin:
        result = await host_admin.run_storage_maintenance(
            HostStorageMaintenanceRequest(run_wal_checkpoint=False)
        )

    assert result.wal_checkpoint is None
    assert result.reclaimed_artifact_paths == ()


@pytest.mark.asyncio
async def test_open_host_run_storage_maintenance_fails_after_close(
    tmp_path: Path,
) -> None:
    """public handle 关闭后 maintenance 使用当前 closed handle 错误语义。"""

    manager = open_host_admin(_open_host_admin_options(tmp_path))
    host_admin = await manager.__aenter__()
    await host_admin.close()

    with pytest.raises(HostClosedError):
        await host_admin.run_storage_maintenance(HostStorageMaintenanceRequest())


def _write_referenced_artifact(host: HostCommandHandle, artifact_root: Path) -> str:
    """写入被 descriptor 引用的 artifact。

    :param host: Host command handle。
    :param artifact_root: artifact root。
    :returns: artifact 相对路径。
    """

    artifact_ref = _write_referenced_artifact_with_ref(
        host,
        artifact_root,
        b"referenced",
        "payload-ref-referenced",
    )
    return artifact_ref.artifact_relative_path


def _write_referenced_artifact_with_ref(
    host: HostCommandHandle,
    artifact_root: Path,
    content: bytes,
    payload_ref: str,
) -> LocalArtifactRef:
    """写入 artifact 并用指定 payload ref 写入 descriptor。

    :param host: Host command handle。
    :param artifact_root: artifact root。
    :param content: artifact 文件内容。
    :param payload_ref: descriptor payload ref。
    :returns: 已发布 artifact ref。
    """

    artifact_ref = _write_orphan_artifact_ref(artifact_root, content)
    _write_artifact_descriptor(host, artifact_ref, payload_ref)
    return artifact_ref


def _write_artifact_descriptor(
    host: HostCommandHandle,
    artifact_ref: LocalArtifactRef,
    payload_ref: str,
) -> None:
    """为已发布 artifact 写入 descriptor。

    :param host: Host command handle。
    :param artifact_ref: 已发布 artifact ref。
    :param payload_ref: descriptor payload ref。
    :returns: ``None``。
    """

    def write_descriptor(transaction: HostTransaction) -> None:
        """写入 artifact descriptor。

        :param transaction: Host write transaction。
        :returns: ``None``。
        """

        write_payload_descriptor_for_artifact(
            transaction,
            payload_ref,
            artifact_ref,
            "application/octet-stream",
            {},
        )

    host._run_write(write_descriptor)


def _write_orphan_artifact(artifact_root: Path, content: bytes) -> str:
    """写入未被 descriptor 引用的已发布 artifact。

    :param artifact_root: artifact root。
    :param content: 文件内容。
    :returns: artifact 相对路径。
    """

    return _write_orphan_artifact_ref(artifact_root, content).artifact_relative_path


def _write_orphan_artifact_ref(
    artifact_root: Path,
    content: bytes,
) -> LocalArtifactRef:
    """写入未被 descriptor 引用的已发布 artifact。

    :param artifact_root: artifact root。
    :param content: 文件内容。
    :returns: artifact ref。
    """

    return LocalArtifactStore(artifact_root).write_artifact_bytes(content)


def _delete_payload_descriptor(host: HostCommandHandle, payload_ref: str) -> None:
    """删除测试构造用 payload descriptor。

    :param host: Host command handle。
    :param payload_ref: 待删除 descriptor payload ref。
    :returns: ``None``。
    """

    def delete_descriptor(transaction: HostTransaction) -> None:
        """删除 payload descriptor row。

        :param transaction: Host write transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"DELETE FROM {TABLE_PAYLOAD_DESCRIPTORS} WHERE payload_ref = ?",
            (payload_ref,),
        )

    host._run_write(delete_descriptor)


def _insert_invalid_memory_snapshot_json(host: HostCommandHandle) -> None:
    """插入 JSON 损坏的 memory snapshot row。

    :param host: Host command handle。
    :returns: ``None``。
    """

    def insert_snapshot(transaction: HostTransaction) -> None:
        """写入损坏 snapshot row。

        :param transaction: Host write transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_MEMORY_SNAPSHOTS} (
              snapshot_id,
              session_id,
              consumer_id,
              checkpoint_event_sequence,
              checkpoint_event_id,
              policy_digest,
              snapshot_digest,
              snapshot_json,
              built_at,
              updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snapshot-invalid-json",
                "session-invalid-json",
                "conversation_memory_v1",
                0,
                None,
                "policy-digest-invalid-json",
                "snapshot-digest-invalid-json",
                "{not-json",
                "2026-06-12T00:00:00.000000Z",
                "2026-06-12T00:00:00.000000Z",
            ),
        )

    host._run_write(insert_snapshot)


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


def _json_int(values: JsonValue, key: str) -> int:
    """从 JSON object 中读取整数字段。

    :param values: JSON value。
    :param key: 字段名。
    :returns: 整数字段值。
    :raises AssertionError: 输入不是 JSON object 或字段不是整数时抛出。
    """

    assert isinstance(values, Mapping)
    value = values[key]
    assert isinstance(value, int)
    return value
