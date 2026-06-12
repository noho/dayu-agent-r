"""Host storage usage report 只读公共面测试。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
    HostCallContext,
    HostApiError,
    HostApiErrorCode,
    HostClosedError,
    OperationContext,
    OpenHostOptions,
    OrdinaryRunExecutionBaseline,
    report_storage_usage,
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
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_bytes
from dayu.host.durable.payload import (
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
    write_payload_descriptor_for_artifact,
    write_sqlite_payload,
)
from dayu.host.durable.schema import TABLE_SQLITE_PAYLOADS
from dayu.host.durable.storage_lifecycle import (
    HostStorageUsageReport,
    read_storage_usage,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import default_memory_projection_policy
from dayu.host.open_host import open_host

_SQLITE_PAYLOAD_BYTES = b"sqlite-payload"
_ORPHAN_SQLITE_PAYLOAD_BYTES = b"orphan-payload"
_ARTIFACT_BYTES = b"artifact-payload"
_STAT_TARGET_DB = "db"
_STAT_TARGET_WAL = "wal"


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


def _unreachable_engine_event() -> EngineEvent:
    """类型收窄用不可达 EngineEvent。

    :returns: 不会实际返回的 EngineEvent。
    :raises AssertionError: 若被执行则说明测试 no-op stream 失效。
    """

    raise AssertionError("noop worker must not emit events")


async def _empty_engine_events() -> AsyncIterator[EngineEvent]:
    """返回空 EngineEvent async iterator。

    :returns: 空异步迭代器。
    """

    if False:
        yield _unreachable_engine_event()


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: HostCommandHandleOptions。
    """

    return HostCommandHandleOptions(
        host_handle_id="storage-report-test",
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


def _context() -> HostCallContext:
    """构造测试用 Host call context。

    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="storage-report-request",
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name="report_storage_usage",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="storage_usage_report",
            correlation_id="corr-storage-report",
        ),
    )


def _create_request() -> CreateSessionRequest:
    """构造 create session 请求。

    :returns: CreateSessionRequest。
    """

    return CreateSessionRequest(
        context=_context(),
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
        context=_context(),
        session_id=session_id,
        client_request_id="start-run",
        input=HostInput(
            display_text="storage report run",
            payload_ref=None,
            payload_digest=None,
        ),
        execution_target="storage-report-target",
        queue_policy="queue",
    )


def _seed_session_run_and_payloads(host: HostCommandHandle, artifact_root: Path) -> None:
    """写入 report 测试需要的 Session、Run、payload 与 artifact descriptor。

    :param host: Host command handle。
    :param artifact_root: artifact root。
    :returns: ``None``。
    """

    session = command_create_session(host, _create_request())
    start_run(host, _start_request(session.session_id))
    artifact_ref = LocalArtifactStore(artifact_root).write_artifact_bytes(
        _ARTIFACT_BYTES
    )

    def operation(transaction: HostTransaction) -> None:
        """写入 payload rows 与 descriptors。

        :param transaction: Host write transaction。
        :returns: ``None``。
        """

        write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref="payload-sqlite",
                payload_id="sqlite-payload",
                payload_format=SQLitePayloadFormat.BYTES,
                payload_bytes=_SQLITE_PAYLOAD_BYTES,
                media_type="application/octet-stream",
                metadata={},
            ),
        )
        write_payload_descriptor_for_artifact(
            transaction,
            "payload-artifact",
            artifact_ref,
            "application/octet-stream",
            {},
        )
        transaction.execute(
            f"""
            INSERT INTO {TABLE_SQLITE_PAYLOADS} (
              payload_id,
              payload_format,
              payload_json,
              payload_bytes,
              payload_size_bytes,
              payload_digest,
              created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "orphan-sqlite-payload",
                SQLitePayloadFormat.BYTES.value,
                None,
                _ORPHAN_SQLITE_PAYLOAD_BYTES,
                len(_ORPHAN_SQLITE_PAYLOAD_BYTES),
                sha256_digest_bytes(_ORPHAN_SQLITE_PAYLOAD_BYTES),
                format_utc_timestamp(datetime.now(UTC)),
            ),
        )

    host._run_write(operation)


def test_fresh_storage_usage_report_has_zero_counts_and_non_negative_file_sizes(
    tmp_path: Path,
) -> None:
    """fresh durable DB report 的 row count 为零且文件大小非负。"""

    host = create_host_command_handle(_command_options(tmp_path))
    try:
        report = report_storage_usage(host)
        values = report.json_value()
        assert _json_int(values, "event_log_rows") == 0
        assert _json_int(values, "payload_descriptor_rows") == 0
        assert _json_int(values, "sqlite_payload_rows") == 0
        assert report.db_file_bytes >= 0
        assert report.wal_file_bytes >= 0

        missing_wal_report = host._run_read(
            _ReadUsageWithDbPath(db_path=tmp_path / "stat-only.sqlite3")
        )
        assert missing_wal_report.wal_file_bytes == 0
    finally:
        host.close()


def test_storage_usage_report_counts_rows_logical_bytes_and_orphans(
    tmp_path: Path,
) -> None:
    """report 正确统计 Session/Run/payload row、logical bytes 与 orphan payload。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    try:
        _seed_session_run_and_payloads(host, options.artifact_root)

        report = report_storage_usage(host)

        assert report.host_session_rows == 1
        assert report.host_run_rows == 1
        assert report.payload_descriptor_rows == 2
        assert report.sqlite_payload_rows == 2
        assert report.sqlite_payload_logical_bytes == (
            len(_SQLITE_PAYLOAD_BYTES) + len(_ORPHAN_SQLITE_PAYLOAD_BYTES)
        )
        assert report.artifact_descriptor_logical_bytes == len(_ARTIFACT_BYTES)
        assert report.orphan_sqlite_payload_count == 1
        assert report.db_file_bytes >= 0
    finally:
        host.close()


@pytest.mark.parametrize("stat_target", (_STAT_TARGET_DB, _STAT_TARGET_WAL))
def test_report_storage_usage_wraps_file_stat_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stat_target: str,
) -> None:
    """public facade 将 DB/WAL stat 的非缺失 OSError 包装为 HostApiError。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    original_stat = Path.stat
    expected_error = PermissionError("storage usage stat denied")
    wal_path = options.db_path.with_name(f"{options.db_path.name}-wal")
    failed_path = options.db_path if stat_target == _STAT_TARGET_DB else wal_path

    def fail_selected_stat(
        self: Path,
        *,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        """对指定 DB/WAL 路径模拟非缺失类 stat OSError。

        :param self: 正在 stat 的路径。
        :param follow_symlinks: 是否跟随符号链接。
        :returns: 原始 stat 结果。
        :raises PermissionError: 命中目标路径时抛出。
        """

        if self == failed_path:
            raise expected_error
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fail_selected_stat)
    try:
        with pytest.raises(HostApiError) as exc_info:
            report_storage_usage(host)
    finally:
        host.close()

    assert exc_info.value.code == HostApiErrorCode.INTERNAL_ERROR
    assert exc_info.value.retryable is False
    assert exc_info.value.__cause__ is expected_error


@pytest.mark.asyncio
async def test_open_host_async_handle_reports_storage_usage(tmp_path: Path) -> None:
    """open_host async handle 暴露 storage usage report 读取入口。"""

    async with open_host(_open_host_options(tmp_path)) as host:
        report = await host.report_storage_usage()

    assert isinstance(report, HostStorageUsageReport)
    assert report.event_log_rows == 0


@pytest.mark.asyncio
async def test_open_host_report_storage_usage_fails_after_close(
    tmp_path: Path,
) -> None:
    """public handle 关闭后读取 report 使用当前 closed handle 错误语义。"""

    manager = open_host(_open_host_options(tmp_path))
    host = await manager.__aenter__()
    await host.close()

    with pytest.raises(HostClosedError):
        await host.report_storage_usage()


def test_storage_usage_json_value_is_stable_self_explaining_and_non_negative(
    tmp_path: Path,
) -> None:
    """json_value 返回稳定、自解释且非负的 JSON object。"""

    host = create_host_command_handle(_command_options(tmp_path))
    try:
        values = report_storage_usage(host).json_value()
    finally:
        host.close()

    assert isinstance(values, Mapping)
    expected_keys = (
        "event_log_rows",
        "idempotency_record_rows",
        "sqlite_payload_rows",
        "payload_descriptor_rows",
        "host_instance_rows",
        "host_session_rows",
        "host_session_slot_rows",
        "host_run_rows",
        "host_attempt_rows",
        "host_attempt_dispatch_record_rows",
        "host_wait_record_rows",
        "host_projection_checkpoint_rows",
        "host_projection_failure_rows",
        "host_run_result_rows",
        "host_session_timeline_item_rows",
        "host_memory_snapshot_rows",
        "host_memory_item_rows",
        "host_memory_diagnostic_rows",
        "host_audit_sink_marker_rows",
        "host_tool_trace_hot_rows",
        "host_outbox_terminal_item_rows",
        "host_outbox_drain_idempotency_rows",
        "host_purge_tombstone_rows",
        "sqlite_payload_logical_bytes",
        "artifact_descriptor_logical_bytes",
        "orphan_sqlite_payload_count",
        "db_file_bytes",
        "wal_file_bytes",
    )
    assert tuple(values.keys()) == expected_keys
    for key in expected_keys:
        assert _json_int(values, key) >= 0


@dataclass(frozen=True, slots=True)
class _ReadUsageWithDbPath:
    """使用指定 db_path 调用 durable reader 的测试 operation。

    :param db_path: 传给 reader 的 DB 文件路径。
    """

    db_path: Path

    def __call__(self, transaction: HostTransaction) -> HostStorageUsageReport:
        """读取 storage usage report。

        :param transaction: Host read transaction。
        :returns: storage usage report。
        """

        return read_storage_usage(transaction, db_path=self.db_path)


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
