"""P15 purge durable tombstone primitive 测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from dataclasses import dataclass, replace
from multiprocessing import Process
from pathlib import Path
from typing import TypeVar, cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host import open_host
from dayu.host import command as host_command_module
from dayu.host.audit import (
    LogAuditSinkOptions,
    PurgeAuditRecordResult,
    PurgeCompletedAuditRecordRequest,
    audit_json_line_marks_purged_source_eventlog_facts,
    default_log_audit_sink_options,
)
from dayu.host.api import (
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostCommandHandleOptions,
    OperationContext,
    PurgeSessionRequest,
    ReplayRunRequest,
    RetryRunRequest,
)
from dayu.host.command import create_host_command_handle, purge_session
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.idempotency import (
    IdempotencyResultRef,
    IdempotencyResultKind,
    IdempotencyScope,
    IdempotencyScopeKind,
    IdempotencyStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.purge import (
    PURGE_IDEMPOTENCY_RESULT_KIND,
    PURGE_IDEMPOTENCY_SCOPE_KIND,
    PurgeDeleteCounts,
    PurgeReplayDecision,
    PurgeReplayDecisionKind,
    PurgeSessionDeleteRequest,
    PurgeSessionDeleteResult,
    PurgeSessionInvalidStateError,
    PurgeSessionNotFoundError,
    PurgeTombstoneRow,
    build_deleted_counts_digest,
    build_purge_attempt_ref,
    build_purge_semantic_digest,
    build_purge_tombstone_digest,
    build_purge_tombstone_id,
    insert_purge_tombstone,
    purge_session_durable,
    read_purge_tombstone_by_id,
    read_purge_tombstone_by_session_id,
    record_or_read_purge_idempotency,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_AUDIT_SINK_MARKERS,
    TABLE_HOST_MEMORY_DIAGNOSTICS,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
    TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
    TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_HOST_RUN_RESULTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_SESSION_SLOTS,
    TABLE_HOST_SESSION_TIMELINE_ITEMS,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_TOOL_TRACE_HOT,
    TABLE_HOST_WAIT_RECORDS,
    TABLE_HOST_PURGE_TOMBSTONES,
    TABLE_IDEMPOTENCY_RECORDS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
)
from dayu.host.durable.transaction import HostTransaction
from tests.host.public_smoke_support import (
    deterministic_runner_spec,
    open_host_options,
)

_SESSION_ID = "session-purged-1"
_CLIENT_REQUEST_ID = "purge-request-1"
_OTHER_CLIENT_REQUEST_ID = "purge-request-2"
_REASON = "user requested durable retention purge"
_PURGED_AT = "2026-05-29T00:00:00.000000Z"
_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_DIGEST_C = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
_AUDIT_RECORD_REF = "audit-jsonl:purge-tombstone:purge-tombstone-1"
_OTHER_SESSION_ID = "session-preserved-1"
_PARENT_RUN_ID = "run-parent-1"
_CHILD_RUN_ID = "run-child-1"
_PARENT_ATTEMPT_ID = "attempt-parent-1"
_CHILD_ATTEMPT_ID = "attempt-child-1"
_PARENT_EXECUTION_ID = "execution-parent-1"
_CHILD_EXECUTION_ID = "execution-child-1"
_TIMESTAMP = "2026-05-29T00:00:00.000000Z"
_UNIQUE_PAYLOAD_REF = "payload-target-unique"
_UNIQUE_PAYLOAD_ID = "sqlite-payload-target-unique"
_SHARED_PAYLOAD_REF = "payload-shared"
_SHARED_PAYLOAD_ID = "sqlite-payload-shared"
_ARTIFACT_PAYLOAD_REF = "payload-target-artifact"
_ARTIFACT_RELATIVE_PATH = "cold/target-artifact.json"
_OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND = "external_projection_ack"
_OUT_OF_SCOPE_IDEMPOTENCY_KEY = "external-ack-key"
_UNSUPPORTED_PROJECTION_CONSUMER_ID = "host.recovery-governance"
_RUN_STATUS_SUCCEEDED = "succeeded"
_RUN_STATUS_ACCEPTED = "accepted"
_RUN_STATUS_QUEUED = "queued"
_RUN_STATUS_RUNNING = "running"
_RUN_STATUS_WAITING = "waiting"
_RUN_STATUS_CANCELLING = "cancelling"
_RUN_STATUS_RECOVERING = "recovering"
_RUN_STATUS_FAILED = "failed"
_RUN_STATUS_CANCELLED = "cancelled"
_RUN_STATUS_LOST = "lost"
_EVENT_TYPE_TEST = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_CANCEL_REQUESTED = "CANCEL_REQUESTED"
_NON_TERMINAL_RUN_STATUSES = (
    _RUN_STATUS_ACCEPTED,
    _RUN_STATUS_QUEUED,
    _RUN_STATUS_RUNNING,
    _RUN_STATUS_WAITING,
    _RUN_STATUS_CANCELLING,
    _RUN_STATUS_RECOVERING,
)
_PROCESS_JOIN_TIMEOUT_SECONDS = 5.0
_AwaitedT = TypeVar("_AwaitedT")


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    durable_options = _options(tmp_path)
    return HostCommandHandleOptions(
        host_handle_id="host-purge-session-test",
        db_path=durable_options.db_path,
        artifact_root=durable_options.payload_policy.artifact_root,
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


def _public_open_durable_options(root_path: Path) -> HostDurableStoreOptions:
    """构造与 public open_host smoke 同路径的 durable store options。

    :param root_path: 测试根目录。
    :returns: Host durable store options。
    :raises ValueError: durable options 字段非法时由 dataclass 校验抛出。
    """

    return HostDurableStoreOptions(
        db_path=root_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=root_path / "artifacts",
            create_artifact_root=True,
        ),
        create_parent_dirs=True,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=1.0,
            write_busy_retry_count=8,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.02,
        ),
    )


def _purge_api_request() -> PurgeSessionRequest:
    """构造 public purge_session 请求。

    :returns: public purge session request。
    :raises ValueError: 请求字段非法时由 dataclass 校验抛出。
    """

    return PurgeSessionRequest(
        context=HostCallContext(
            actor="user-1",
            source="host-api",
            request_id="request-purge-1",
            authorization_claims=(),
            operation_context=OperationContext(
                operation_name="purge_session",
                operation_kind="retention",
                business_domain="host",
                business_object_type="session",
                business_object_id=_SESSION_ID,
                scenario="test",
                correlation_id="correlation-purge-1",
            ),
        ),
        client_request_id=_CLIENT_REQUEST_ID,
        reason=_REASON,
    )


def _retry_api_request(client_request_id: str) -> RetryRunRequest:
    """构造 retry_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: retry run 请求。
    :raises ValueError: 请求字段非法时由 dataclass 校验抛出。
    """

    return RetryRunRequest(
        context=HostCallContext(
            actor="user-1",
            source="host-api",
            request_id=client_request_id,
            authorization_claims=(),
            operation_context=OperationContext(
                operation_name="retry_run",
                operation_kind="recovery",
                business_domain="host",
                business_object_type="run",
                business_object_id=_PARENT_RUN_ID,
                scenario="test",
                correlation_id="correlation-retry-1",
            ),
        ),
        client_request_id=client_request_id,
        reason="purge_multiprocess_read_after_purge",
    )


def _replay_api_request(client_request_id: str) -> ReplayRunRequest:
    """构造 replay_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: replay run 请求。
    :raises ValueError: 请求字段非法时由 dataclass 校验抛出。
    """

    return ReplayRunRequest(
        context=HostCallContext(
            actor="user-1",
            source="host-api",
            request_id=client_request_id,
            authorization_claims=(),
            operation_context=OperationContext(
                operation_name="replay_run",
                operation_kind="repair",
                business_domain="host",
                business_object_type="run",
                business_object_id=_PARENT_RUN_ID,
                scenario="test",
                correlation_id="correlation-replay-1",
            ),
        ),
        client_request_id=client_request_id,
        reason="purge_multiprocess_read_after_purge",
        repair_instruction="verify purge fail closed",
    )


def _json_lines(path: Path) -> list[dict[str, JsonValue]]:
    """读取 JSONL object 行。

    :param path: JSONL 文件路径。
    :returns: 已解析 JSON object 列表。
    :raises AssertionError: 任一行不是 JSON object 时抛出。
    """

    result: list[dict[str, JsonValue]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            parsed = cast(JsonValue, json.loads(raw_line))
            assert isinstance(parsed, dict)
            result.append(cast(dict[str, JsonValue], parsed))
    return result


def _json_object_file(path: Path) -> dict[str, JsonValue]:
    """读取 JSON object 文件。

    :param path: JSON 文件路径。
    :returns: 已解析 JSON object。
    :raises AssertionError: 文件内容不是 JSON object 时抛出。
    :raises OSError: 文件读取失败时抛出。
    :raises json.JSONDecodeError: 文件内容不是合法 JSON 时抛出。
    """

    parsed = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(parsed, dict)
    return cast(dict[str, JsonValue], parsed)


def _counts() -> PurgeDeleteCounts:
    """构造稳定的删除计数样本。

    :returns: purge 删除计数。
    """

    return PurgeDeleteCounts(
        event_log_rows=3,
        idempotency_records=1,
        payload_descriptors=2,
        sqlite_payloads=2,
        host_session_slots=1,
        host_sessions=1,
        host_runs=2,
        host_attempts=2,
        host_attempt_dispatch_records=2,
        host_wait_records=1,
        host_run_results=2,
        host_session_timeline_items=5,
        host_memory_snapshots=1,
        host_memory_items=4,
        host_memory_diagnostics=1,
        host_audit_sink_markers=3,
        host_tool_trace_hot=2,
        host_outbox_terminal_items=1,
        host_outbox_drain_idempotency=1,
        host_projection_checkpoints=1,
        host_projection_failures=1,
    )


def _operation_context_refs() -> dict[str, JsonValue]:
    """构造 operation context refs JSON。

    :returns: operation context refs JSON object。
    """

    return {"request_ref": "purge-context-1", "source": "test"}


def _request_context() -> dict[str, JsonValue]:
    """构造 request context JSON。

    :returns: request context JSON object。
    """

    return {"actor_ref": "user-1", "ui_request_ref": "button-1"}


def _semantic_digest(reason: str = _REASON) -> str:
    """构造测试用 purge semantic digest。

    :param reason: purge 原因。
    :returns: semantic digest。
    """

    return build_purge_semantic_digest(
        session_id=_SESSION_ID,
        reason=reason,
        operation_context_digest=_DIGEST_A,
        operation_context_refs=_operation_context_refs(),
        request_context=_request_context(),
    )


def _tombstone(
    *,
    client_request_id: str = _CLIENT_REQUEST_ID,
    semantic_digest: str | None = None,
) -> PurgeTombstoneRow:
    """构造测试用 tombstone row。

    :param client_request_id: purge 请求幂等 key。
    :param semantic_digest: semantic digest；未提供时使用默认 digest。
    :returns: purge tombstone row。
    """

    counts = _counts()
    effective_semantic_digest = _semantic_digest() if semantic_digest is None else semantic_digest
    return PurgeTombstoneRow(
        tombstone_id="purge-tombstone-1",
        session_id=_SESSION_ID,
        client_request_id=client_request_id,
        semantic_request_digest=effective_semantic_digest,
        actor="user-1",
        source="host-api",
        operation_context_digest=_DIGEST_A,
        operation_context_refs=_operation_context_refs(),
        reason=_REASON,
        purged_at=_PURGED_AT,
        precondition_digest=_DIGEST_B,
        deleted_counts=counts,
        deleted_counts_digest=build_deleted_counts_digest(counts),
        deleted_refs_digest=_DIGEST_C,
        audit_record_ref=_AUDIT_RECORD_REF,
        audit_record_digest=_DIGEST_A,
        request_context=_request_context(),
    )


def _purge_in_independent_process(root_path_text: str, result_marker_text: str) -> None:
    """独立进程 A：打开 public Host handle 并执行 purge。

    :param root_path_text: 测试根目录文本路径。
    :param result_marker_text: 结果 marker 文本路径。
    :returns: ``None``。
    :raises Exception: 子进程内 public Host 打开、purge 或结果写入失败时透传。
    """

    asyncio.run(
        _purge_in_independent_process_async(
            root_path=Path(root_path_text),
            result_marker=Path(result_marker_text),
        )
    )


async def _purge_in_independent_process_async(*, root_path: Path, result_marker: Path) -> None:
    """独立进程 A 的异步 purge 主体。

    :param root_path: 测试根目录。
    :param result_marker: 结果 marker 路径。
    :returns: ``None``。
    :raises Exception: public Host 打开、purge 或结果写入失败时透传。
    """

    options = open_host_options(
        root_path,
        runner_spec=deterministic_runner_spec("p15-s5-purge"),
        worker_factory=None,
        allow_tool_calls=False,
    )
    async with open_host(options) as host:
        result = await host.purge_session(_SESSION_ID, _purge_api_request())
    result_marker.write_text(
        json.dumps(
            {
                "purged": result.purged,
                "tombstone_ref": result.purge_tombstone_ref,
                "deleted_counts_digest": result.deleted_counts_digest,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _read_after_purge_in_independent_process(root_path_text: str, result_marker_text: str) -> None:
    """独立进程 B：打开 public Host handle 并验证 purge 后 fail closed。

    :param root_path_text: 测试根目录文本路径。
    :param result_marker_text: 结果 marker 文本路径。
    :returns: ``None``。
    :raises Exception: 子进程内 public Host 打开、fail-closed 验证或结果写入失败时透传。
    """

    asyncio.run(
        _read_after_purge_in_independent_process_async(
            root_path=Path(root_path_text),
            result_marker=Path(result_marker_text),
        )
    )


async def _read_after_purge_in_independent_process_async(*, root_path: Path, result_marker: Path) -> None:
    """独立进程 B 的异步读后验证主体。

    :param root_path: 测试根目录。
    :param result_marker: 结果 marker 路径。
    :returns: ``None``。
    :raises AssertionError: 任一 public async read path 未按 HostApiError fail closed 时抛出。
    :raises Exception: public Host 打开或结果写入失败时透传。
    """

    options = open_host_options(
        root_path,
        runner_spec=deterministic_runner_spec("p15-s5-read-after-purge"),
        worker_factory=None,
        allow_tool_calls=False,
    )
    observed: dict[str, JsonValue] = {}
    async with open_host(options) as host:
        observed["get_session"] = await _host_api_error_code(host.get_session(_SESSION_ID))
        observed["get_run"] = await _host_api_error_code(host.get_run(_PARENT_RUN_ID))
        observed["retry_run"] = await _host_api_error_code(
            host.retry_run(
                _PARENT_RUN_ID,
                _retry_api_request("retry-after-purge-process"),
            )
        )
        observed["replay_run"] = await _host_api_error_code(
            host.replay_run(
                _PARENT_RUN_ID,
                _replay_api_request("replay-after-purge-process"),
            )
        )
        try:
            host.watch_session_events(_SESSION_ID)
        except HostApiError as exc:
            observed["watch_session_events"] = exc.code.value
        else:
            observed["watch_session_events"] = "unexpected_success"
    result_marker.write_text(json.dumps(observed, sort_keys=True), encoding="utf-8")


async def _host_api_error_code(awaitable: Awaitable[_AwaitedT]) -> str:
    """读取 awaitable 的 HostApiError code。

    :param awaitable: public Host async method 返回的 awaitable。
    :returns: 捕获到的 HostApiError code。
    :raises AssertionError: awaitable 未抛 HostApiError 时抛出。
    """

    try:
        await awaitable
    except HostApiError as exc:
        return exc.code.value
    raise AssertionError("expected HostApiError")


class _InsertAndReadTombstoneOperation:
    """插入并读取 tombstone 的测试 transaction operation。"""

    def __call__(self, transaction: HostTransaction) -> tuple[PurgeTombstoneRow, PurgeTombstoneRow | None]:
        """执行插入并按 Session id 读取。

        :param transaction: Host durable transaction。
        :returns: 插入 row 与按 Session 读取的 row。
        """

        inserted = insert_purge_tombstone(transaction, _tombstone())
        by_session = read_purge_tombstone_by_session_id(
            transaction,
            _SESSION_ID,
        )
        by_id = read_purge_tombstone_by_id(transaction, inserted.tombstone_id)
        assert by_id == inserted
        return inserted, by_session


class _InsertTombstoneOnlyOperation:
    """只插入 tombstone 的测试 transaction operation。"""

    def __init__(
        self,
        *,
        client_request_id: str = _CLIENT_REQUEST_ID,
        semantic_digest: str | None = None,
    ) -> None:
        """初始化 operation。

        :param client_request_id: purge 请求幂等 key。
        :param semantic_digest: semantic digest。
        :returns: ``None``。
        """

        self._client_request_id = client_request_id
        self._semantic_digest = semantic_digest

    def __call__(self, transaction: HostTransaction) -> PurgeTombstoneRow:
        """执行 tombstone 插入。

        :param transaction: Host durable transaction。
        :returns: 插入后的 tombstone row。
        """

        return insert_purge_tombstone(
            transaction,
            _tombstone(
                client_request_id=self._client_request_id,
                semantic_digest=self._semantic_digest,
            ),
        )


class _RecordOrReadOperation:
    """执行 purge idempotency replay helper 的测试 operation。"""

    def __init__(self, *, client_request_id: str, semantic_digest: str) -> None:
        """初始化 operation。

        :param client_request_id: purge 请求幂等 key。
        :param semantic_digest: semantic digest。
        :returns: ``None``。
        """

        self._client_request_id = client_request_id
        self._semantic_digest = semantic_digest

    def __call__(self, transaction: HostTransaction) -> PurgeReplayDecision:
        """执行 replay helper。

        :param transaction: Host durable transaction。
        :returns: purge replay 判定。
        """

        return record_or_read_purge_idempotency(
            transaction,
            session_id=_SESSION_ID,
            client_request_id=self._client_request_id,
            semantic_request_digest=self._semantic_digest,
        )


class _SeedIdempotencyOnlyOperation:
    """只写入 purge idempotency row 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> None:
        """写入 result_ref 指向缺失 tombstone 的幂等 row。

        :param transaction: Host durable transaction。
        :returns: ``None``。
        """

        IdempotencyStore().record_idempotent_result(
            transaction,
            IdempotencyScope(
                scope_kind=PURGE_IDEMPOTENCY_SCOPE_KIND,
                scope_id=_SESSION_ID,
                idempotency_key=_CLIENT_REQUEST_ID,
            ),
            _semantic_digest(),
            IdempotencyResultRef(
                result_kind=PURGE_IDEMPOTENCY_RESULT_KIND,
                result_ref="missing-tombstone",
                created_event_id=None,
                created_event_sequence=None,
            ),
        )


class _SeedTombstoneWithConflictingIdempotencyOperation:
    """写入 tombstone 与同 scope/key 不同 digest 幂等 row 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> None:
        """写入内部不一致的 tombstone / idempotency 组合。

        :param transaction: Host durable transaction。
        :returns: ``None``。
        """

        tombstone = insert_purge_tombstone(transaction, _tombstone())
        IdempotencyStore().record_idempotent_result(
            transaction,
            IdempotencyScope(
                scope_kind=PURGE_IDEMPOTENCY_SCOPE_KIND,
                scope_id=_SESSION_ID,
                idempotency_key=_CLIENT_REQUEST_ID,
            ),
            build_purge_semantic_digest(
                session_id=_SESSION_ID,
                reason="different durable row digest",
                operation_context_digest=_DIGEST_A,
                operation_context_refs=_operation_context_refs(),
                request_context=_request_context(),
            ),
            IdempotencyResultRef(
                result_kind=PURGE_IDEMPOTENCY_RESULT_KIND,
                result_ref=tombstone.tombstone_id,
                created_event_id=None,
                created_event_sequence=None,
            ),
        )


class _InsertMalformedTombstoneOperation:
    """尝试插入 malformed tombstone 的测试 operation。"""

    def __init__(self, tombstone: PurgeTombstoneRow) -> None:
        """初始化 operation。

        :param tombstone: 待插入的 malformed tombstone。
        :returns: ``None``。
        """

        self._tombstone = tombstone

    def __call__(self, transaction: HostTransaction) -> PurgeTombstoneRow:
        """执行 malformed tombstone 插入。

        :param transaction: Host durable transaction。
        :returns: 插入后的 tombstone row。
        :raises HostDurableError: tombstone validation 失败时抛出。
        """

        return insert_purge_tombstone(transaction, self._tombstone)


class _InstallTombstoneInsertFailureTriggerOperation:
    """安装 tombstone insert 失败 trigger 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> None:
        """安装用于模拟 SQLite purge transaction 失败的 trigger。

        :param transaction: Host durable transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            CREATE TRIGGER test_purge_tombstone_insert_failure
            BEFORE INSERT ON {TABLE_HOST_PURGE_TOMBSTONES}
            BEGIN
              SELECT RAISE(ABORT, 'test tombstone insert failed');
            END
            """
        )


class _SeedClosedSessionMatrixOperation:
    """写入覆盖 purge delete matrix 的 closed Session 测试数据。"""

    def __init__(
        self,
        *,
        run_status: str = _RUN_STATUS_SUCCEEDED,
        active_wait: bool = False,
    ) -> None:
        """初始化 seed operation。

        :param run_status: parent/child Run 状态。
        :param active_wait: 是否写入 waiting wait record。
        :returns: ``None``。
        """

        self._run_status = run_status
        self._active_wait = active_wait

    def __call__(self, transaction: HostTransaction) -> None:
        """写入目标 Session、共享 Session 与所有 projection rows。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        _insert_sqlite_payload_descriptor(
            transaction,
            payload_ref=_UNIQUE_PAYLOAD_REF,
            payload_id=_UNIQUE_PAYLOAD_ID,
        )
        _insert_sqlite_payload_descriptor(
            transaction,
            payload_ref=_SHARED_PAYLOAD_REF,
            payload_id=_SHARED_PAYLOAD_ID,
        )
        _insert_artifact_payload_descriptor(transaction)
        target_events = _insert_target_events(transaction)
        _insert_closed_session(transaction, target_events)
        _insert_slot(transaction, target_events.session_created)
        if self._run_status != _RUN_STATUS_SUCCEEDED:
            _insert_run_row(
                transaction,
                run_id=_PARENT_RUN_ID,
                source_run_id=None,
                source_run_relation=None,
                input_event=target_events.parent_input,
                accepted_event=target_events.parent_accepted,
                terminal_event=target_events.parent_terminal,
                status=self._run_status,
                current_attempt_id=_PARENT_ATTEMPT_ID,
            )
            return
        _insert_run_rows(transaction, self._run_status, target_events)
        _insert_attempt_rows(transaction, self._run_status, target_events)
        _insert_dispatch_rows(transaction, target_events)
        _insert_wait_row(transaction, active_wait=self._active_wait, events=target_events)
        _insert_read_model_rows(transaction, target_events)
        _insert_memory_rows(transaction, target_events)
        _insert_audit_marker(transaction, target_events.parent_terminal)
        _insert_tool_trace_row(transaction, target_events.child_attempt_terminal)
        _insert_outbox_rows(transaction, target_events.child_terminal)
        _insert_projection_rows(transaction, target_events)
        _insert_old_idempotency_rows(transaction, target_events)
        _insert_other_session_with_shared_payload(transaction)


class _SeedOpenSessionOperation:
    """写入 open Session 测试数据。"""

    def __call__(self, transaction: HostTransaction) -> None:
        """写入只包含 open Session 的最小数据。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        created = _insert_event(
            transaction,
            event_id="event-open-session-created",
            session_id=_SESSION_ID,
            run_id=None,
            attempt_id=None,
            execution_id=None,
            payload_ref=None,
        )
        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_SESSIONS} (
              session_id,
              status,
              metadata_json,
              created_event_id,
              created_event_sequence,
              closed_event_id,
              closed_event_sequence,
              created_at,
              closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _SESSION_ID,
                "open",
                "{}",
                "event-open-session-created",
                created,
                None,
                None,
                _TIMESTAMP,
                None,
            ),
        )


class _PurgeMatrixOperation:
    """执行 purge_session_durable 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> PurgeSessionDeleteResult:
        """执行 purge delete matrix helper。

        :param transaction: Host transaction。
        :returns: purge delete result。
        """

        return purge_session_durable(
            transaction,
            _delete_request(),
        )


class _PurgeRequestOperation:
    """使用显式请求执行 purge_session_durable 的测试 operation。"""

    def __init__(self, request: PurgeSessionDeleteRequest) -> None:
        """初始化 purge request operation。

        :param request: purge delete request。
        :returns: ``None``。
        """

        self._request = request

    def __call__(self, transaction: HostTransaction) -> PurgeSessionDeleteResult:
        """执行 purge delete helper。

        :param transaction: Host transaction。
        :returns: purge delete result。
        """

        return purge_session_durable(transaction, self._request)


class _ReadTableCountOperation:
    """读取单表 row count 的测试 operation。"""

    def __init__(
        self,
        table_name: str,
        *,
        where_sql: str = "",
        parameters: tuple[str, ...] = (),
    ) -> None:
        """初始化 count operation。

        :param table_name: 目标表名。
        :param where_sql: 可选 WHERE SQL，必须由测试固定常量提供。
        :param parameters: WHERE 参数。
        :returns: ``None``。
        """

        self._table_name = table_name
        self._where_sql = where_sql
        self._parameters = parameters

    def __call__(self, transaction: HostTransaction) -> int:
        """读取 row count。

        :param transaction: Host transaction。
        :returns: row count。
        """

        row = transaction.fetchone(
            f"SELECT COUNT(*) AS count FROM {self._table_name} {self._where_sql}",
            self._parameters,
        )
        assert row is not None
        value = row.get("count")
        assert isinstance(value, int)
        return value


class _ReadPurgeIdempotencyOperation:
    """读取 purge 幂等 row 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> tuple[str, str | None, int | None]:
        """读取 purge 幂等 result_ref 与 EventLog refs。

        :param transaction: Host transaction。
        :returns: ``(result_ref, created_event_id, created_event_sequence)``。
        """

        row = transaction.fetchone(
            f"""
            SELECT result_ref, created_event_id, created_event_sequence
            FROM {TABLE_IDEMPOTENCY_RECORDS}
            WHERE scope_kind = ? AND scope_id = ? AND idempotency_key = ?
            """,
            (PURGE_IDEMPOTENCY_SCOPE_KIND.value, _SESSION_ID, _CLIENT_REQUEST_ID),
        )
        assert row is not None
        result_ref = row.get("result_ref")
        event_id = row.get("created_event_id")
        event_sequence = row.get("created_event_sequence")
        assert isinstance(result_ref, str)
        assert event_id is None or isinstance(event_id, str)
        assert event_sequence is None or isinstance(event_sequence, int)
        return result_ref, event_id, event_sequence


class _ReadOutOfScopeIdempotencyOperation:
    """读取 purge 不应删除的 out-of-scope idempotency row。"""

    def __call__(self, transaction: HostTransaction) -> bool:
        """判断 out-of-scope idempotency row 是否存在。

        :param transaction: Host transaction。
        :returns: 存在时返回 ``True``。
        """

        row = transaction.fetchone(
            f"""
            SELECT 1 AS found
            FROM {TABLE_IDEMPOTENCY_RECORDS}
            WHERE scope_kind = ? AND scope_id = ? AND idempotency_key = ?
            """,
            (
                _OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND,
                _SESSION_ID,
                _OUT_OF_SCOPE_IDEMPOTENCY_KEY,
            ),
        )
        return row is not None


class _ReadTombstoneBySessionOperation:
    """按 Session id 读取 tombstone 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> PurgeTombstoneRow | None:
        """读取 tombstone。

        :param transaction: Host transaction。
        :returns: tombstone row 或 ``None``。
        """

        return read_purge_tombstone_by_session_id(transaction, _SESSION_ID)


class _InsertUnsupportedProjectionCheckpointOperation:
    """写入不可 reset projection consumer checkpoint 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> None:
        """写入引用目标 EventLog 的非白名单 checkpoint。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        event_sequence = _event_sequence_for_id(transaction, "event-child-terminal")
        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
              consumer_id,
              checkpoint_event_sequence,
              checkpoint_event_id,
              last_success_at,
              updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                _UNSUPPORTED_PROJECTION_CONSUMER_ID,
                event_sequence,
                "event-child-terminal",
                _TIMESTAMP,
                _TIMESTAMP,
            ),
        )


class _InsertUnsupportedProjectionFailureOperation:
    """写入不可 reset projection consumer failure 的测试 operation。"""

    def __call__(self, transaction: HostTransaction) -> None:
        """写入引用目标 EventLog 的非白名单 failure。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        event_sequence = _event_sequence_for_id(transaction, "event-child-terminal")
        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_PROJECTION_FAILURES} (
              consumer_id,
              failed_event_sequence,
              failed_event_id,
              failure_count,
              last_error_code,
              last_error_message,
              first_failed_at,
              last_failed_at,
              retry_after
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _UNSUPPORTED_PROJECTION_CONSUMER_ID,
                event_sequence,
                "event-child-terminal",
                1,
                "unsupported",
                "unsupported",
                _TIMESTAMP,
                _TIMESTAMP,
                None,
            ),
        )


@dataclass(frozen=True, slots=True)
class _TargetEvents:
    """目标 Session 测试 EventLog refs。"""

    session_created: tuple[str, int]
    session_closed: tuple[str, int]
    parent_input: tuple[str, int]
    parent_accepted: tuple[str, int]
    parent_terminal: tuple[str, int]
    child_input: tuple[str, int]
    child_accepted: tuple[str, int]
    child_terminal: tuple[str, int]
    parent_attempt_started: tuple[str, int]
    parent_attempt_terminal: tuple[str, int]
    child_attempt_started: tuple[str, int]
    child_attempt_terminal: tuple[str, int]


def _delete_request() -> PurgeSessionDeleteRequest:
    """构造 purge delete matrix 请求。

    :returns: purge delete request。
    """

    return PurgeSessionDeleteRequest(
        session_id=_SESSION_ID,
        client_request_id=_CLIENT_REQUEST_ID,
        semantic_request_digest=_semantic_digest(),
        actor="user-1",
        source="host-api",
        operation_context_digest=_DIGEST_A,
        operation_context_refs=_operation_context_refs(),
        reason=_REASON,
        purged_at=_PURGED_AT,
        started_audit_record_ref=_AUDIT_RECORD_REF,
        started_audit_record_digest=_DIGEST_A,
        request_context=_request_context(),
    )


def _insert_sqlite_payload_descriptor(transaction: HostTransaction, *, payload_ref: str, payload_id: str) -> None:
    """写入 SQLite payload row 与 descriptor。

    :param transaction: Host transaction。
    :param payload_ref: payload descriptor ref。
    :param payload_id: SQLite payload id。
    :returns: ``None``。
    """

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
            payload_id,
            "canonical_json",
            "{}",
            None,
            2,
            _DIGEST_A,
            _TIMESTAMP,
        ),
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_PAYLOAD_DESCRIPTORS} (
          payload_ref,
          payload_kind,
          payload_digest,
          payload_size_bytes,
          media_type,
          sqlite_payload_id,
          artifact_relative_path,
          metadata_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload_ref,
            "sqlite_payload",
            _DIGEST_A,
            2,
            "application/json",
            payload_id,
            None,
            "{}",
            _TIMESTAMP,
        ),
    )


def _insert_artifact_payload_descriptor(transaction: HostTransaction) -> None:
    """写入 artifact payload descriptor。

    :param transaction: Host transaction。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_PAYLOAD_DESCRIPTORS} (
          payload_ref,
          payload_kind,
          payload_digest,
          payload_size_bytes,
          media_type,
          sqlite_payload_id,
          artifact_relative_path,
          metadata_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _ARTIFACT_PAYLOAD_REF,
            "artifact_ref",
            _DIGEST_B,
            64,
            "application/json",
            None,
            _ARTIFACT_RELATIVE_PATH,
            "{}",
            _TIMESTAMP,
        ),
    )


def _insert_event(
    transaction: HostTransaction,
    *,
    event_id: str,
    session_id: str,
    run_id: str | None,
    attempt_id: str | None,
    execution_id: str | None,
    payload_ref: str | None,
    event_type: str = _EVENT_TYPE_TEST,
) -> int:
    """写入 EventLog row 并返回 sequence。

    :param transaction: Host transaction。
    :param event_id: EventLog id。
    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param payload_ref: payload descriptor ref。
    :param event_type: EventLog 事件类型。
    :returns: EventLog sequence。
    :raises AssertionError: SQLite insert 未返回 row id 时抛出。
    """

    result = transaction.execute(
        f"""
        INSERT INTO {TABLE_EVENT_LOG} (
          event_id,
          event_body_digest,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          event_type,
          occurred_at,
          actor,
          source,
          client_request_id,
          idempotency_key,
          policy_decision_json,
          reason_json,
          payload_json,
          payload_ref,
          payload_digest,
          appended_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            _DIGEST_A,
            "canonical_fact",
            session_id,
            run_id,
            attempt_id,
            execution_id,
            event_type,
            _TIMESTAMP,
            "tester",
            "test",
            None,
            None,
            None,
            None,
            "{}",
            payload_ref,
            _DIGEST_A if payload_ref is not None else None,
            _TIMESTAMP,
        ),
    )
    assert result.lastrowid is not None
    return result.lastrowid


def _insert_target_events(transaction: HostTransaction) -> _TargetEvents:
    """写入目标 Session 的 EventLog rows。

    :param transaction: Host transaction。
    :returns: 目标 EventLog refs。
    """

    return _TargetEvents(
        session_created=(
            "event-target-session-created",
            _insert_event(
                transaction,
                event_id="event-target-session-created",
                session_id=_SESSION_ID,
                run_id=None,
                attempt_id=None,
                execution_id=None,
                payload_ref=None,
            ),
        ),
        session_closed=(
            "event-target-session-closed",
            _insert_event(
                transaction,
                event_id="event-target-session-closed",
                session_id=_SESSION_ID,
                run_id=None,
                attempt_id=None,
                execution_id=None,
                payload_ref=None,
            ),
        ),
        parent_input=(
            "event-parent-input",
            _insert_event(
                transaction,
                event_id="event-parent-input",
                session_id=_SESSION_ID,
                run_id=_PARENT_RUN_ID,
                attempt_id=None,
                execution_id=None,
                payload_ref=_UNIQUE_PAYLOAD_REF,
            ),
        ),
        parent_accepted=(
            "event-parent-accepted",
            _insert_event(
                transaction,
                event_id="event-parent-accepted",
                session_id=_SESSION_ID,
                run_id=_PARENT_RUN_ID,
                attempt_id=None,
                execution_id=None,
                payload_ref=None,
            ),
        ),
        parent_terminal=(
            "event-parent-terminal",
            _insert_event(
                transaction,
                event_id="event-parent-terminal",
                session_id=_SESSION_ID,
                run_id=_PARENT_RUN_ID,
                attempt_id=None,
                execution_id=None,
                payload_ref=None,
            ),
        ),
        child_input=(
            "event-child-input",
            _insert_event(
                transaction,
                event_id="event-child-input",
                session_id=_SESSION_ID,
                run_id=_CHILD_RUN_ID,
                attempt_id=None,
                execution_id=None,
                payload_ref=None,
            ),
        ),
        child_accepted=(
            "event-child-accepted",
            _insert_event(
                transaction,
                event_id="event-child-accepted",
                session_id=_SESSION_ID,
                run_id=_CHILD_RUN_ID,
                attempt_id=None,
                execution_id=None,
                payload_ref=None,
            ),
        ),
        child_terminal=(
            "event-child-terminal",
            _insert_event(
                transaction,
                event_id="event-child-terminal",
                session_id=_SESSION_ID,
                run_id=_CHILD_RUN_ID,
                attempt_id=None,
                execution_id=None,
                payload_ref=None,
            ),
        ),
        parent_attempt_started=(
            "event-parent-attempt-started",
            _insert_event(
                transaction,
                event_id="event-parent-attempt-started",
                session_id=_SESSION_ID,
                run_id=_PARENT_RUN_ID,
                attempt_id=_PARENT_ATTEMPT_ID,
                execution_id=_PARENT_EXECUTION_ID,
                payload_ref=None,
            ),
        ),
        parent_attempt_terminal=(
            "event-parent-attempt-terminal",
            _insert_event(
                transaction,
                event_id="event-parent-attempt-terminal",
                session_id=_SESSION_ID,
                run_id=_PARENT_RUN_ID,
                attempt_id=_PARENT_ATTEMPT_ID,
                execution_id=_PARENT_EXECUTION_ID,
                payload_ref=None,
            ),
        ),
        child_attempt_started=(
            "event-child-attempt-started",
            _insert_event(
                transaction,
                event_id="event-child-attempt-started",
                session_id=_SESSION_ID,
                run_id=_CHILD_RUN_ID,
                attempt_id=_CHILD_ATTEMPT_ID,
                execution_id=_CHILD_EXECUTION_ID,
                payload_ref=None,
            ),
        ),
        child_attempt_terminal=(
            "event-child-attempt-terminal",
            _insert_event(
                transaction,
                event_id="event-child-attempt-terminal",
                session_id=_SESSION_ID,
                run_id=_CHILD_RUN_ID,
                attempt_id=_CHILD_ATTEMPT_ID,
                execution_id=_CHILD_EXECUTION_ID,
                payload_ref=_ARTIFACT_PAYLOAD_REF,
            ),
        ),
    )


def test_insert_and_read_purge_tombstone_round_trip(tmp_path: Path) -> None:
    """tombstone 可在无 Session / EventLog row 时插入并按 id/session 读取。"""

    result: tuple[PurgeTombstoneRow, PurgeTombstoneRow | None] | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        result = store.transaction_runner.run_write(_InsertAndReadTombstoneOperation())

    assert result is not None
    inserted, by_session = result
    assert by_session == inserted
    assert inserted.session_id == _SESSION_ID
    assert inserted.deleted_counts.event_log_rows == 3
    assert inserted.deleted_counts_digest == build_deleted_counts_digest(inserted.deleted_counts)


def _insert_closed_session(transaction: HostTransaction, events: _TargetEvents) -> None:
    """写入 closed Session row。

    :param transaction: Host transaction。
    :param events: 目标 EventLog refs。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSIONS} (
          session_id,
          status,
          metadata_json,
          created_event_id,
          created_event_sequence,
          closed_event_id,
          closed_event_sequence,
          created_at,
          closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _SESSION_ID,
            "closed",
            "{}",
            events.session_created[0],
            events.session_created[1],
            events.session_closed[0],
            events.session_closed[1],
            _TIMESTAMP,
            _TIMESTAMP,
        ),
    )


def _insert_slot(transaction: HostTransaction, bound_event: tuple[str, int]) -> None:
    """写入 Session slot binding。

    :param transaction: Host transaction。
    :param bound_event: slot 绑定 EventLog ref。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSION_SLOTS} (
          scope,
          slot_key,
          session_id,
          bound_event_id,
          bound_event_sequence,
          metadata_json,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("default", "slot-1", _SESSION_ID, bound_event[0], bound_event[1], "{}", _TIMESTAMP),
    )


def _insert_run_rows(transaction: HostTransaction, run_status: str, events: _TargetEvents) -> None:
    """写入 parent/child Run rows。

    :param transaction: Host transaction。
    :param run_status: Run 状态。
    :param events: 目标 EventLog refs。
    :returns: ``None``。
    """

    _insert_run_row(
        transaction,
        run_id=_PARENT_RUN_ID,
        source_run_id=None,
        source_run_relation=None,
        input_event=events.parent_input,
        accepted_event=events.parent_accepted,
        terminal_event=events.parent_terminal,
        status=run_status,
        current_attempt_id=_PARENT_ATTEMPT_ID,
    )
    _insert_run_row(
        transaction,
        run_id=_CHILD_RUN_ID,
        source_run_id=_PARENT_RUN_ID,
        source_run_relation="retry",
        input_event=events.child_input,
        accepted_event=events.child_accepted,
        terminal_event=events.child_terminal,
        status=run_status,
        current_attempt_id=_CHILD_ATTEMPT_ID,
    )


def _insert_cancel_request_event_if_needed(
    transaction: HostTransaction, *, run_id: str, status: str
) -> str | None:
    """按 Run 状态写入专用 ``CANCEL_REQUESTED`` 事件。

    参数：
        transaction: Host transaction。
        run_id: Run id。
        status: Run 状态。
    返回值：取消语义状态对应的 EventLog id；其它状态返回 ``None``。
    异常：EventLog 插入未返回 row id 时由 ``_insert_event`` 抛出
        ``AssertionError``。
    """

    if status not in (_RUN_STATUS_CANCELLING, _RUN_STATUS_CANCELLED):
        return None
    event_id = f"event-{run_id}-cancel-requested"
    _insert_event(
        transaction,
        event_id=event_id,
        session_id=_SESSION_ID,
        run_id=run_id,
        attempt_id=None,
        execution_id=None,
        payload_ref=None,
        event_type=_EVENT_TYPE_CANCEL_REQUESTED,
    )
    return event_id


def _insert_run_row(
    transaction: HostTransaction,
    *,
    run_id: str,
    source_run_id: str | None,
    source_run_relation: str | None,
    input_event: tuple[str, int],
    accepted_event: tuple[str, int],
    terminal_event: tuple[str, int],
    status: str,
    current_attempt_id: str,
) -> None:
    """写入单个 Run row。

    :param transaction: Host transaction。
    :param run_id: Run id。
    :param source_run_id: retry/replay source Run id。
    :param source_run_relation: retry/replay source 关系。
    :param input_event: input EventLog ref。
    :param accepted_event: accepted EventLog ref。
    :param terminal_event: terminal EventLog ref。
    :param status: Run 状态。
    :param current_attempt_id: 当前 Attempt id。
    :returns: ``None``。
    """

    is_terminal = status in (
        _RUN_STATUS_SUCCEEDED,
        _RUN_STATUS_FAILED,
        _RUN_STATUS_CANCELLED,
        _RUN_STATUS_LOST,
    )
    queued_event_id = accepted_event[0] if status == _RUN_STATUS_QUEUED else None
    queued_event_sequence = accepted_event[1] if status == _RUN_STATUS_QUEUED else None
    cancel_request_event_id = _insert_cancel_request_event_if_needed(
        transaction, run_id=run_id, status=status
    )
    started_event_id = (
        accepted_event[0] if status not in (_RUN_STATUS_ACCEPTED, _RUN_STATUS_QUEUED) and not is_terminal else None
    )
    started_event_sequence = (
        accepted_event[1] if status not in (_RUN_STATUS_ACCEPTED, _RUN_STATUS_QUEUED) and not is_terminal else None
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_RUNS} (
          run_id,
          session_id,
          status,
          client_request_id,
          input_event_id,
          input_event_sequence,
          accepted_event_id,
          accepted_event_sequence,
          queued_event_id,
          queued_event_sequence,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          cancel_request_event_id,
          current_attempt_id,
          source_run_id,
          source_run_relation,
          execution_target,
          queue_policy,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            _SESSION_ID,
            status,
            f"client-{run_id}",
            input_event[0],
            input_event[1],
            accepted_event[0],
            accepted_event[1],
            queued_event_id,
            queued_event_sequence,
            started_event_id,
            started_event_sequence,
            terminal_event[0] if is_terminal else None,
            terminal_event[1] if is_terminal else None,
            cancel_request_event_id,
            current_attempt_id if status not in (_RUN_STATUS_ACCEPTED, _RUN_STATUS_QUEUED) else None,
            source_run_id,
            source_run_relation,
            "local-default",
            "queue",
            _TIMESTAMP,
            _TIMESTAMP,
            _TIMESTAMP if is_terminal else None,
        ),
    )


def _insert_attempt_rows(transaction: HostTransaction, run_status: str, events: _TargetEvents) -> None:
    """写入 Attempt rows。

    :param transaction: Host transaction。
    :param run_status: Run 状态，用于选择 Attempt 状态。
    :param events: 目标 EventLog refs。
    :returns: ``None``。
    """

    attempt_status = "succeeded" if run_status == _RUN_STATUS_SUCCEEDED else "running"
    terminal_parent = events.parent_attempt_terminal if attempt_status == "succeeded" else None
    terminal_child = events.child_attempt_terminal if attempt_status == "succeeded" else None
    _insert_attempt_row(
        transaction,
        attempt_id=_PARENT_ATTEMPT_ID,
        run_id=_PARENT_RUN_ID,
        execution_id=_PARENT_EXECUTION_ID,
        status=attempt_status,
        started_event=events.parent_attempt_started,
        terminal_event=terminal_parent,
    )
    _insert_attempt_row(
        transaction,
        attempt_id=_CHILD_ATTEMPT_ID,
        run_id=_CHILD_RUN_ID,
        execution_id=_CHILD_EXECUTION_ID,
        status=attempt_status,
        started_event=events.child_attempt_started,
        terminal_event=terminal_child,
    )


def _insert_attempt_row(
    transaction: HostTransaction,
    *,
    attempt_id: str,
    run_id: str,
    execution_id: str,
    status: str,
    started_event: tuple[str, int],
    terminal_event: tuple[str, int] | None,
) -> None:
    """写入单个 Attempt row。

    :param transaction: Host transaction。
    :param attempt_id: Attempt id。
    :param run_id: Run id。
    :param execution_id: execution id。
    :param status: Attempt 状态。
    :param started_event: started EventLog ref。
    :param terminal_event: terminal EventLog ref。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_ATTEMPTS} (
          attempt_id,
          run_id,
          execution_id,
          status,
          started_event_id,
          started_event_sequence,
          terminal_event_id,
          terminal_event_sequence,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt_id,
            run_id,
            execution_id,
            status,
            started_event[0],
            started_event[1],
            None if terminal_event is None else terminal_event[0],
            None if terminal_event is None else terminal_event[1],
            _TIMESTAMP,
            _TIMESTAMP,
            None if terminal_event is None else _TIMESTAMP,
        ),
    )


def test_tombstone_replay_records_purge_idempotency_with_null_event_refs(
    tmp_path: Path,
) -> None:
    """tombstone 存在但幂等 row 缺失时，同 key/digest 从 tombstone replay。"""

    semantic_digest = _semantic_digest()
    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_InsertTombstoneOnlyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_CLIENT_REQUEST_ID,
                semantic_digest=semantic_digest,
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.REPLAY_TOMBSTONE
    assert decision.tombstone is not None
    assert decision.tombstone.tombstone_id == "purge-tombstone-1"
    assert decision.idempotency_record is not None
    assert decision.idempotency_record.result_kind == PURGE_IDEMPOTENCY_RESULT_KIND
    assert decision.idempotency_record.created_event_id is None
    assert decision.idempotency_record.created_event_sequence is None


def test_tombstone_same_key_different_digest_conflicts(tmp_path: Path) -> None:
    """tombstone 存在但同 key digest 不同时返回幂等冲突判定。"""

    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_InsertTombstoneOnlyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_CLIENT_REQUEST_ID,
                semantic_digest=build_purge_semantic_digest(
                    session_id=_SESSION_ID,
                    reason="different purge reason",
                    operation_context_digest=_DIGEST_A,
                    operation_context_refs=_operation_context_refs(),
                    request_context=_request_context(),
                ),
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT
    assert decision.tombstone is not None
    assert decision.idempotency_record is None


def test_tombstone_different_key_returns_already_purged_conflict(
    tmp_path: Path,
) -> None:
    """tombstone 存在但 client_request_id 不同时返回 already-purged conflict。"""

    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_InsertTombstoneOnlyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_OTHER_CLIENT_REQUEST_ID,
                semantic_digest=_semantic_digest(),
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.ALREADY_PURGED_CONFLICT
    assert decision.tombstone is not None
    assert decision.idempotency_record is None


def test_existing_idempotency_same_key_different_digest_conflicts(
    tmp_path: Path,
) -> None:
    """无 tombstone 但同 key 幂等 row digest 不同时返回幂等冲突。"""

    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedIdempotencyOnlyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_CLIENT_REQUEST_ID,
                semantic_digest=build_purge_semantic_digest(
                    session_id=_SESSION_ID,
                    reason="different purge reason",
                    operation_context_digest=_DIGEST_A,
                    operation_context_refs=_operation_context_refs(),
                    request_context=_request_context(),
                ),
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT
    assert decision.tombstone is None
    assert decision.idempotency_record is not None


def test_tombstone_same_key_same_digest_with_conflicting_idempotency_is_inconsistent(
    tmp_path: Path,
) -> None:
    """tombstone 同 key/digest 但幂等表内不同 digest 时返回 durable inconsistency。"""

    decision: PurgeReplayDecision | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedTombstoneWithConflictingIdempotencyOperation())
        decision = store.transaction_runner.run_write(
            _RecordOrReadOperation(
                client_request_id=_CLIENT_REQUEST_ID,
                semantic_digest=_semantic_digest(),
            )
        )

    assert decision is not None
    assert decision.kind is PurgeReplayDecisionKind.DURABLE_INCONSISTENCY
    assert decision.tombstone is not None
    assert decision.idempotency_record is None


def test_deleted_counts_digest_rejects_negative_counts() -> None:
    """deleted counts digest 拒绝负数计数。"""

    with pytest.raises(HostDurableError):
        build_deleted_counts_digest(replace(_counts(), event_log_rows=-1))


def test_insert_tombstone_rejects_mismatched_deleted_counts_digest(
    tmp_path: Path,
) -> None:
    """tombstone validation 拒绝 deleted_counts_digest 与 counts 不匹配。"""

    malformed = replace(_tombstone(), deleted_counts_digest=_DIGEST_A)
    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(_InsertMalformedTombstoneOperation(malformed))


def _insert_dispatch_rows(transaction: HostTransaction, events: _TargetEvents) -> None:
    """写入 dispatch records。

    :param transaction: Host transaction。
    :param events: 目标 EventLog refs。
    :returns: ``None``。
    """

    _insert_dispatch_row(
        transaction,
        dispatch_record_id="dispatch-parent-1",
        run_id=_PARENT_RUN_ID,
        attempt_id=_PARENT_ATTEMPT_ID,
        execution_id=_PARENT_EXECUTION_ID,
        created_event=events.parent_attempt_started,
    )
    _insert_dispatch_row(
        transaction,
        dispatch_record_id="dispatch-child-1",
        run_id=_CHILD_RUN_ID,
        attempt_id=_CHILD_ATTEMPT_ID,
        execution_id=_CHILD_EXECUTION_ID,
        created_event=events.child_attempt_started,
    )


def _insert_dispatch_row(
    transaction: HostTransaction,
    *,
    dispatch_record_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    created_event: tuple[str, int],
) -> None:
    """写入 pending dispatch record。

    :param transaction: Host transaction。
    :param dispatch_record_id: dispatch record id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param created_event: created EventLog ref。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} (
          dispatch_record_id,
          run_id,
          attempt_id,
          execution_id,
          status,
          worker_kind,
          execution_target,
          owner_host_instance_id,
          created_event_id,
          created_event_sequence,
          waiting_for_lane_at,
          lane_name,
          lane_claim_id,
          lane_owner_id,
          lane_acquired_at,
          dispatching_at,
          worker_accepted_at,
          worker_accept_event_id,
          worker_accept_event_sequence,
          cancelled_event_id,
          cancelled_event_sequence,
          created_at,
          updated_at,
          cancelled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dispatch_record_id,
            run_id,
            attempt_id,
            execution_id,
            "pending",
            "local",
            "local-default",
            None,
            created_event[0],
            created_event[1],
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            _TIMESTAMP,
            _TIMESTAMP,
            None,
        ),
    )


def _insert_wait_row(transaction: HostTransaction, *, active_wait: bool, events: _TargetEvents) -> None:
    """写入 wait record。

    :param transaction: Host transaction。
    :param active_wait: 是否为 waiting 状态。
    :param events: 目标 EventLog refs。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_WAIT_RECORDS} (
          wait_id,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          adapter_key,
          await_kind,
          resume_policy,
          resume_token,
          snapshot_ref,
          snapshot_captured_at,
          snapshot_digest,
          external_job_id,
          accept_idempotency_key,
          resolve_idempotency_key,
          resolve_semantic_digest,
          deadline_at,
          expires_at,
          status,
          created_event_id,
          created_event_sequence,
          updated_event_id,
          updated_event_sequence,
          created_at,
          updated_at,
          terminal_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "wait-child-1",
            _SESSION_ID,
            _CHILD_RUN_ID,
            _CHILD_ATTEMPT_ID,
            _CHILD_EXECUTION_ID,
            "tool-call-1",
            "tool_a",
            "adapter-a",
            "external_job",
            "manual",
            "resume-token-1",
            None,
            None,
            None,
            None,
            "accept-wait-1",
            None,
            None,
            None,
            None,
            "waiting" if active_wait else "resolved",
            events.child_attempt_started[0],
            events.child_attempt_started[1],
            events.child_attempt_terminal[0],
            events.child_attempt_terminal[1],
            _TIMESTAMP,
            _TIMESTAMP,
            None if active_wait else _TIMESTAMP,
        ),
    )


def _insert_read_model_rows(transaction: HostTransaction, events: _TargetEvents) -> None:
    """写入 minimal read model rows。

    :param transaction: Host transaction。
    :param events: 目标 EventLog refs。
    :returns: ``None``。
    """

    _insert_run_result(transaction, _PARENT_RUN_ID, events.parent_terminal, None)
    _insert_run_result(
        transaction,
        _CHILD_RUN_ID,
        events.child_terminal,
        _UNIQUE_PAYLOAD_REF,
    )
    _insert_timeline_item(
        transaction,
        timeline_id="timeline-parent-input",
        run_id=_PARENT_RUN_ID,
        event_ref=events.parent_input,
        payload_ref=_SHARED_PAYLOAD_REF,
    )
    _insert_timeline_item(
        transaction,
        timeline_id="timeline-child-terminal",
        run_id=_CHILD_RUN_ID,
        event_ref=events.child_terminal,
        payload_ref=None,
    )


def _insert_run_result(
    transaction: HostTransaction,
    run_id: str,
    terminal_event: tuple[str, int],
    result_ref: str | None,
) -> None:
    """写入 RunResult projection row。

    :param transaction: Host transaction。
    :param run_id: Run id。
    :param terminal_event: terminal EventLog ref。
    :param result_ref: result payload ref。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_RUN_RESULTS} (
          run_id,
          session_id,
          terminal_status,
          terminal_event_id,
          terminal_event_sequence,
          result_ref,
          result_digest,
          summary_ref,
          summary_digest,
          projected_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            _SESSION_ID,
            _RUN_STATUS_SUCCEEDED,
            terminal_event[0],
            terminal_event[1],
            result_ref,
            _DIGEST_A if result_ref is not None else None,
            None,
            None,
            _TIMESTAMP,
            _TIMESTAMP,
        ),
    )


def _insert_timeline_item(
    transaction: HostTransaction,
    *,
    timeline_id: str,
    run_id: str,
    event_ref: tuple[str, int],
    payload_ref: str | None,
) -> None:
    """写入 Session timeline row。

    :param transaction: Host transaction。
    :param timeline_id: timeline item id。
    :param run_id: Run id。
    :param event_ref: source EventLog ref。
    :param payload_ref: payload ref。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSION_TIMELINE_ITEMS} (
          timeline_item_id,
          session_id,
          run_id,
          event_id,
          event_sequence,
          item_kind,
          event_type,
          display_text,
          payload_ref,
          payload_digest,
          projected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timeline_id,
            _SESSION_ID,
            run_id,
            event_ref[0],
            event_ref[1],
            "run_lifecycle",
            "USER_INPUT_ACCEPTED",
            "display",
            payload_ref,
            _DIGEST_A if payload_ref is not None else None,
            _TIMESTAMP,
        ),
    )


def _insert_memory_rows(transaction: HostTransaction, events: _TargetEvents) -> None:
    """写入 memory snapshot/items/diagnostics rows。

    :param transaction: Host transaction。
    :param events: 目标 EventLog refs。
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
            "memory-snapshot-1",
            _SESSION_ID,
            "host.memory.session.v1",
            events.child_attempt_terminal[1],
            events.child_attempt_terminal[0],
            _DIGEST_A,
            _DIGEST_B,
            "{}",
            _TIMESTAMP,
            _TIMESTAMP,
        ),
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_MEMORY_ITEMS} (
          item_id,
          snapshot_id,
          session_id,
          item_kind,
          claim_status,
          event_id,
          event_sequence,
          producer_kind,
          producer_name,
          payload_ref,
          payload_digest,
          item_json,
          included_reason,
          excluded_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "memory-item-1",
            "memory-snapshot-1",
            _SESSION_ID,
            "selected_recent_window",
            "candidate",
            events.parent_input[0],
            events.parent_input[1],
            "user",
            "user",
            _UNIQUE_PAYLOAD_REF,
            _DIGEST_A,
            "{}",
            None,
            None,
        ),
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_MEMORY_DIAGNOSTICS} (
          diagnostic_id,
          session_id,
          snapshot_id,
          reason,
          event_sequence,
          policy_digest,
          diagnostic_json,
          recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "memory-diagnostic-1",
            _SESSION_ID,
            "memory-snapshot-1",
            "snapshot_lag_over_threshold",
            events.child_attempt_terminal[1],
            _DIGEST_A,
            "{}",
            _TIMESTAMP,
        ),
    )


def _insert_audit_marker(transaction: HostTransaction, event_ref: tuple[str, int]) -> None:
    """写入 audit marker row。

    :param transaction: Host transaction。
    :param event_ref: EventLog ref。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_AUDIT_SINK_MARKERS} (
          event_id,
          event_sequence,
          line_digest,
          written_at
        ) VALUES (?, ?, ?, ?)
        """,
        (event_ref[0], event_ref[1], _DIGEST_A, _TIMESTAMP),
    )


def _insert_tool_trace_row(transaction: HostTransaction, event_ref: tuple[str, int]) -> None:
    """写入 tool trace hot row。

    :param transaction: Host transaction。
    :param event_ref: EventLog ref。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_TOOL_TRACE_HOT} (
          trace_id,
          event_id,
          event_sequence,
          event_type,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          tool_call_id,
          tool_name,
          provider_request_id,
          diagnostic_ref,
          normalized_arguments_digest,
          semantic_input_digest,
          result_digest,
          payload_ref,
          payload_digest,
          policy_decision_json,
          trace_summary_json,
          cold_trace_ref,
          cold_trace_digest,
          projected_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "trace-1",
            event_ref[0],
            event_ref[1],
            "TOOL_RESULT_ACCEPTED",
            "canonical_fact",
            _SESSION_ID,
            _CHILD_RUN_ID,
            _CHILD_ATTEMPT_ID,
            _CHILD_EXECUTION_ID,
            "tool-call-1",
            "tool_a",
            None,
            None,
            None,
            None,
            None,
            _ARTIFACT_PAYLOAD_REF,
            _DIGEST_B,
            None,
            "{}",
            None,
            None,
            _TIMESTAMP,
            _TIMESTAMP,
        ),
    )


def _insert_outbox_rows(transaction: HostTransaction, terminal_event: tuple[str, int]) -> None:
    """写入 outbox terminal item 与 drain idempotency rows。

    :param transaction: Host transaction。
    :param terminal_event: terminal EventLog ref。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_OUTBOX_TERMINAL_ITEMS} (
          item_id,
          idempotency_key,
          terminal_event_id,
          event_sequence,
          session_id,
          run_id,
          terminal_status,
          dedupe_key,
          final_answer_json,
          error_message,
          cancel_reason,
          result_ref,
          result_digest,
          terminal_summary_ref,
          terminal_summary_digest,
          item_state,
          projected_at,
          updated_at,
          drained_at,
          last_drain_request_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "outbox-item-1",
            "outbox-key-1",
            terminal_event[0],
            terminal_event[1],
            _SESSION_ID,
            _CHILD_RUN_ID,
            _RUN_STATUS_SUCCEEDED,
            terminal_event[0],
            "{}",
            None,
            None,
            _ARTIFACT_PAYLOAD_REF,
            _DIGEST_B,
            None,
            None,
            "pending",
            _TIMESTAMP,
            _TIMESTAMP,
            None,
            None,
        ),
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY} (
          session_id,
          drain_request_id,
          request_digest,
          batch_item_ids_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (_SESSION_ID, "drain-1", _DIGEST_A, '{"batch_item_ids":["outbox-item-1"]}', _TIMESTAMP),
    )


def _insert_projection_rows(transaction: HostTransaction, events: _TargetEvents) -> None:
    """写入 checkpoint/failure rows。

    :param transaction: Host transaction。
    :param events: 目标 EventLog refs。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
          consumer_id,
          checkpoint_event_sequence,
          checkpoint_event_id,
          last_success_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "host.minimal-read-model",
            events.child_terminal[1],
            events.child_terminal[0],
            _TIMESTAMP,
            _TIMESTAMP,
        ),
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_PROJECTION_FAILURES} (
          consumer_id,
          failed_event_sequence,
          failed_event_id,
          failure_count,
          last_error_code,
          last_error_message,
          first_failed_at,
          last_failed_at,
          retry_after
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "host.tool-trace",
            events.child_accepted[1],
            events.child_accepted[0],
            1,
            "projection_failed",
            "failed",
            _TIMESTAMP,
            _TIMESTAMP,
            None,
        ),
    )


def _insert_old_idempotency_rows(transaction: HostTransaction, events: _TargetEvents) -> None:
    """写入 purge 应删除的旧 command idempotency rows。

    :param transaction: Host transaction。
    :param events: 目标 EventLog refs。
    :returns: ``None``。
    """

    IdempotencyStore().record_idempotent_result(
        transaction,
        IdempotencyScope(
            scope_kind=IdempotencyScopeKind.CLOSE_SESSION,
            scope_id=_SESSION_ID,
            idempotency_key="old-close-key",
        ),
        _DIGEST_A,
        IdempotencyResultRef(
            result_kind=IdempotencyResultKind.SESSION,
            result_ref=_SESSION_ID,
            created_event_id=events.session_closed[0],
            created_event_sequence=events.session_closed[1],
        ),
    )
    IdempotencyStore().record_idempotent_result(
        transaction,
        IdempotencyScope(
            scope_kind=IdempotencyScopeKind.CANCEL_RUN,
            scope_id=_PARENT_RUN_ID,
            idempotency_key="old-cancel-key",
        ),
        _DIGEST_B,
        IdempotencyResultRef(
            result_kind=IdempotencyResultKind.RUN,
            result_ref=_PARENT_RUN_ID,
            created_event_id=events.parent_terminal[0],
            created_event_sequence=events.parent_terminal[1],
        ),
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_IDEMPOTENCY_RECORDS} (
          scope_kind,
          scope_id,
          idempotency_key,
          semantic_input_digest,
          result_kind,
          result_ref,
          created_event_id,
          created_event_sequence,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND,
            _SESSION_ID,
            _OUT_OF_SCOPE_IDEMPOTENCY_KEY,
            _DIGEST_C,
            "external_ack",
            "external-ack-1",
            None,
            None,
            _TIMESTAMP,
        ),
    )


def _insert_other_session_with_shared_payload(transaction: HostTransaction) -> None:
    """写入应被 purge 保留的其它 Session 与共享 payload 引用。

    :param transaction: Host transaction。
    :returns: ``None``。
    """

    created_id = "event-other-session-created"
    created_sequence = _insert_event(
        transaction,
        event_id=created_id,
        session_id=_OTHER_SESSION_ID,
        run_id=None,
        attempt_id=None,
        execution_id=None,
        payload_ref=_SHARED_PAYLOAD_REF,
    )
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_SESSIONS} (
          session_id,
          status,
          metadata_json,
          created_event_id,
          created_event_sequence,
          closed_event_id,
          closed_event_sequence,
          created_at,
          closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _OTHER_SESSION_ID,
            "open",
            "{}",
            created_id,
            created_sequence,
            None,
            None,
            _TIMESTAMP,
            None,
        ),
    )


def _event_sequence_for_id(transaction: HostTransaction, event_id: str) -> int:
    """按 event_id 读取 EventLog sequence。

    :param transaction: Host transaction。
    :param event_id: EventLog id。
    :returns: EventLog sequence。
    """

    row = transaction.fetchone(
        f"""
        SELECT event_sequence
        FROM {TABLE_EVENT_LOG}
        WHERE event_id = ?
        """,
        (event_id,),
    )
    assert row is not None
    sequence = row.get("event_sequence")
    assert isinstance(sequence, int)
    return sequence


def test_insert_tombstone_rejects_invalid_audit_record_ref(
    tmp_path: Path,
) -> None:
    """tombstone validation 拒绝空 audit_record_ref。"""

    malformed = replace(_tombstone(), audit_record_ref="")
    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(_InsertMalformedTombstoneOperation(malformed))


def test_insert_tombstone_rejects_invalid_audit_record_digest(
    tmp_path: Path,
) -> None:
    """tombstone validation 拒绝非 sha256 audit_record_digest。"""

    malformed = replace(_tombstone(), audit_record_digest="not-a-digest")
    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(_InsertMalformedTombstoneOperation(malformed))


def test_purge_session_durable_deletes_matrix_and_preserves_replay(
    tmp_path: Path,
) -> None:
    """purge helper 删除目标矩阵、保留 tombstone，并通过 NULL EventLog 幂等 row replay。"""

    result: PurgeSessionDeleteResult | None = None
    replay: PurgeSessionDeleteResult | None = None
    purge_idempotency: tuple[str, str | None, int | None] | None = None
    out_of_scope_idempotency_exists = False
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())
        result = store.transaction_runner.run_write(_PurgeMatrixOperation())
        replay = store.transaction_runner.run_write(_PurgeMatrixOperation())
        purge_idempotency = store.transaction_runner.run_read(_ReadPurgeIdempotencyOperation())
        out_of_scope_idempotency_exists = store.transaction_runner.run_read(_ReadOutOfScopeIdempotencyOperation())
        assert (
            store.transaction_runner.run_read(
                _ReadTableCountOperation(
                    TABLE_EVENT_LOG,
                    where_sql="WHERE session_id = ?",
                    parameters=(_SESSION_ID,),
                )
            )
            == 0
        )
        assert (
            store.transaction_runner.run_read(
                _ReadTableCountOperation(
                    TABLE_HOST_SESSIONS,
                    where_sql="WHERE session_id = ?",
                    parameters=(_OTHER_SESSION_ID,),
                )
            )
            == 1
        )
        assert (
            store.transaction_runner.run_read(
                _ReadTableCountOperation(
                    TABLE_PAYLOAD_DESCRIPTORS,
                    where_sql="WHERE payload_ref = ?",
                    parameters=(_UNIQUE_PAYLOAD_REF,),
                )
            )
            == 0
        )
        assert (
            store.transaction_runner.run_read(
                _ReadTableCountOperation(
                    TABLE_PAYLOAD_DESCRIPTORS,
                    where_sql="WHERE payload_ref = ?",
                    parameters=(_SHARED_PAYLOAD_REF,),
                )
            )
            == 1
        )
        assert store.transaction_runner.run_read(_ReadTableCountOperation(TABLE_HOST_PROJECTION_CHECKPOINTS)) == 0
        assert store.transaction_runner.run_read(_ReadTableCountOperation(TABLE_HOST_PROJECTION_FAILURES)) == 0

    assert result is not None
    assert replay is not None
    assert purge_idempotency is not None
    assert out_of_scope_idempotency_exists is True
    assert result.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.tombstone == result.tombstone
    assert result.deleted_counts.event_log_rows == 12
    assert result.deleted_counts.host_runs == 2
    assert result.deleted_counts.host_attempts == 2
    assert result.deleted_counts.host_attempt_dispatch_records == 2
    assert result.deleted_counts.host_wait_records == 1
    assert result.deleted_counts.host_sessions == 1
    assert result.deleted_counts.host_session_slots == 1
    assert result.deleted_counts.host_run_results == 2
    assert result.deleted_counts.host_session_timeline_items == 2
    assert result.deleted_counts.host_memory_snapshots == 1
    assert result.deleted_counts.host_memory_items == 1
    assert result.deleted_counts.host_memory_diagnostics == 1
    assert result.deleted_counts.host_audit_sink_markers == 1
    assert result.deleted_counts.host_tool_trace_hot == 1
    assert result.deleted_counts.host_outbox_terminal_items == 1
    assert result.deleted_counts.host_outbox_drain_idempotency == 1
    assert result.deleted_counts.host_projection_checkpoints == 1
    assert result.deleted_counts.host_projection_failures == 1
    assert result.deleted_counts.idempotency_records == 2
    assert result.deleted_counts.payload_descriptors == 2
    assert result.deleted_counts.sqlite_payloads == 1
    assert result.cleanup_refs.artifact_relative_paths == (_ARTIFACT_RELATIVE_PATH,)
    assert result.tombstone.deleted_counts_digest == build_deleted_counts_digest(result.deleted_counts)
    assert result.tombstone.audit_record_ref == _AUDIT_RECORD_REF
    assert result.tombstone.audit_record_digest == _DIGEST_A
    assert result.tombstone.tombstone_id == build_purge_tombstone_id(
        _SESSION_ID,
        _CLIENT_REQUEST_ID,
        _semantic_digest(),
    )
    assert build_purge_attempt_ref(result.tombstone.tombstone_id) == (
        f"purge-attempt:{result.tombstone.tombstone_id}"
    )
    assert build_purge_tombstone_digest(result.tombstone).startswith("sha256:")
    assert purge_idempotency[0] == result.tombstone.tombstone_id
    assert purge_idempotency[1] is None
    assert purge_idempotency[2] is None


def test_purge_session_durable_rejects_invalid_started_audit_ref_before_delete(
    tmp_path: Path,
) -> None:
    """started audit ref 无效时 purge helper 在删除前失败且不写 tombstone。"""

    tombstone: PurgeTombstoneRow | None = None
    event_count = 0
    malformed = replace(_delete_request(), started_audit_record_ref="")
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(_PurgeRequestOperation(malformed))
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())
        event_count = store.transaction_runner.run_read(
            _ReadTableCountOperation(
                TABLE_EVENT_LOG,
                where_sql="WHERE session_id = ?",
                parameters=(_SESSION_ID,),
            )
        )

    assert tombstone is None
    assert event_count == 12


def test_public_purge_session_appends_tombstone_audit_jsonl(
    tmp_path: Path,
) -> None:
    """public purge 成功前追加 tombstone audit line 并把 ref/digest 写入 tombstone。"""

    tombstone: PurgeTombstoneRow | None = None
    durable_options = _options(tmp_path)
    audit_options = default_log_audit_sink_options(
        durable_options.payload_policy.artifact_root,
        create_parent_dirs=True,
    )
    audit_options.audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    existing_line = (
        '{"event_id":"event-existing","line_digest":"sha256:'
        'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}\n'
    )
    audit_options.audit_jsonl_path.write_text(existing_line, encoding="utf-8")

    with open_host_durable_store(durable_options) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())

    handle = create_host_command_handle(_command_options(tmp_path))
    try:
        result = purge_session(handle, _SESSION_ID, _purge_api_request())
    finally:
        handle.close()

    with open_host_durable_store(durable_options) as store:
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())

    lines = _json_lines(audit_options.audit_jsonl_path)
    started_line = lines[1]
    completed_line = lines[2]
    assert result.purged is True
    assert len(lines) == 3
    assert lines[0]["event_id"] == "event-existing"
    assert started_line["line_kind"] == "purge_started"
    assert started_line["source_eventlog_facts_purged"] is False
    assert started_line["purge_tombstone_ref"] is None
    assert audit_json_line_marks_purged_source_eventlog_facts(started_line) is False
    assert completed_line["line_kind"] == "purge_completed"
    assert audit_json_line_marks_purged_source_eventlog_facts(completed_line)
    assert completed_line["session_id"] == _SESSION_ID
    assert completed_line["purge_tombstone_ref"] == result.purge_tombstone_ref
    assert completed_line["deleted_counts_digest"] == result.deleted_counts_digest
    assert completed_line["reason"] == _REASON
    assert completed_line["actor"] == "user-1"
    assert completed_line["source"] == "host-api"
    assert completed_line["source_eventlog_facts_purged"] is True
    assert tombstone is not None
    assert tombstone.audit_record_ref == started_line["audit_record_ref"]
    assert tombstone.audit_record_digest == started_line["line_digest"]
    assert completed_line["started_audit_record_ref"] == started_line["audit_record_ref"]
    assert completed_line["started_audit_record_digest"] == started_line["line_digest"]
    assert completed_line["purge_tombstone_digest"] == build_purge_tombstone_digest(tombstone)


def test_public_purge_session_audit_append_failure_fails_before_success(
    tmp_path: Path,
) -> None:
    """public purge audit append 失败时返回错误且不留下 successful tombstone。"""

    tombstone: PurgeTombstoneRow | None = None
    event_count = 0
    durable_options = _options(tmp_path)
    audit_options = default_log_audit_sink_options(
        durable_options.payload_policy.artifact_root,
        create_parent_dirs=True,
    )
    audit_options.audit_jsonl_path.parent.parent.mkdir(parents=True, exist_ok=True)
    audit_options.audit_jsonl_path.parent.write_text("not a directory", encoding="utf-8")
    with open_host_durable_store(durable_options) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())

    handle = create_host_command_handle(_command_options(tmp_path))
    try:
        with pytest.raises(HostApiError) as exc_info:
            purge_session(handle, _SESSION_ID, _purge_api_request())
    finally:
        handle.close()

    with open_host_durable_store(durable_options) as store:
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())
        event_count = store.transaction_runner.run_read(
            _ReadTableCountOperation(
                TABLE_EVENT_LOG,
                where_sql="WHERE session_id = ?",
                parameters=(_SESSION_ID,),
            )
        )

    assert exc_info.value.code is HostApiErrorCode.INTERNAL_ERROR
    assert exc_info.value.retryable is True
    assert tombstone is None
    assert event_count == 12


def test_public_purge_session_sqlite_failure_writes_started_and_no_completed(
    tmp_path: Path,
) -> None:
    """SQLite purge transaction 失败时 rollback，并只留下 started/failed audit。"""

    tombstone: PurgeTombstoneRow | None = None
    event_count = 0
    durable_options = _options(tmp_path)
    audit_options = default_log_audit_sink_options(
        durable_options.payload_policy.artifact_root,
        create_parent_dirs=True,
    )
    with open_host_durable_store(durable_options) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())
        store.transaction_runner.run_write(_InstallTombstoneInsertFailureTriggerOperation())

    handle = create_host_command_handle(_command_options(tmp_path))
    try:
        with pytest.raises(HostApiError) as exc_info:
            purge_session(handle, _SESSION_ID, _purge_api_request())
    finally:
        handle.close()

    with open_host_durable_store(durable_options) as store:
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())
        event_count = store.transaction_runner.run_read(
            _ReadTableCountOperation(
                TABLE_EVENT_LOG,
                where_sql="WHERE session_id = ?",
                parameters=(_SESSION_ID,),
            )
        )

    lines = _json_lines(audit_options.audit_jsonl_path)
    line_kinds = tuple(line.get("line_kind") for line in lines)
    assert exc_info.value.code is HostApiErrorCode.INTERNAL_ERROR
    assert tombstone is None
    assert event_count == 12
    assert line_kinds == ("purge_started", "purge_failed")
    assert lines[1]["failure_stage"] == "sqlite_purge_transaction"
    assert all(line.get("line_kind") != "purge_completed" for line in lines)
    assert audit_json_line_marks_purged_source_eventlog_facts(lines[0]) is False
    assert audit_json_line_marks_purged_source_eventlog_facts(lines[1]) is False


def test_public_purge_session_completed_append_failure_retries_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """completed append 失败后，同 key retry 通过 tombstone replay 补写 completed。"""

    durable_options = _options(tmp_path)
    audit_options = default_log_audit_sink_options(
        durable_options.payload_policy.artifact_root,
        create_parent_dirs=True,
    )
    with open_host_durable_store(durable_options) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())

    def _fail_completed_append(
        options: LogAuditSinkOptions,
        request: PurgeCompletedAuditRecordRequest,
    ) -> PurgeAuditRecordResult:
        """测试替身：模拟 completed audit append 失败。

        :param options: audit sink options。
        :param request: purge completed audit request。
        :returns: 不返回；始终抛出。
        :raises OSError: 始终抛出。
        """

        raise OSError("completed append failed")

    monkeypatch.setattr(
        host_command_module,
        "append_purge_completed_audit_record",
        _fail_completed_append,
    )
    handle = create_host_command_handle(_command_options(tmp_path))
    try:
        with pytest.raises(HostApiError) as exc_info:
            purge_session(handle, _SESSION_ID, _purge_api_request())
    finally:
        handle.close()
    assert exc_info.value.code is HostApiErrorCode.INTERNAL_ERROR
    assert exc_info.value.retryable is True

    monkeypatch.undo()
    tombstone: PurgeTombstoneRow | None = None
    retry_handle = create_host_command_handle(_command_options(tmp_path))
    try:
        retry_result = purge_session(retry_handle, _SESSION_ID, _purge_api_request())
    finally:
        retry_handle.close()

    with open_host_durable_store(durable_options) as store:
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())
    lines = _json_lines(audit_options.audit_jsonl_path)
    started_lines = tuple(line for line in lines if line.get("line_kind") == "purge_started")
    completed_lines = tuple(line for line in lines if line.get("line_kind") == "purge_completed")
    assert retry_result.purged is True
    assert tombstone is not None
    assert len(started_lines) == 1
    assert len(completed_lines) == 1
    assert completed_lines[0]["purge_tombstone_ref"] == tombstone.tombstone_id
    assert completed_lines[0]["purge_tombstone_digest"] == build_purge_tombstone_digest(tombstone)


def test_public_purge_is_observed_by_independent_process_read_paths(
    tmp_path: Path,
) -> None:
    """验证独立进程 purge 后，另一进程 public read/retry/replay/watch 均 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 任一子进程失败或 fail-closed 结果不符合预期时由断言抛出。
    """

    purge_marker = tmp_path / "purge-process-result.json"
    read_marker = tmp_path / "read-process-result.json"
    with open_host_durable_store(_public_open_durable_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())

    purge_process = Process(
        target=_purge_in_independent_process,
        args=(str(tmp_path), str(purge_marker)),
    )
    purge_process.start()
    purge_process.join(_PROCESS_JOIN_TIMEOUT_SECONDS)
    assert purge_process.exitcode == 0
    assert purge_marker.exists()

    read_process = Process(
        target=_read_after_purge_in_independent_process,
        args=(str(tmp_path), str(read_marker)),
    )
    read_process.start()
    read_process.join(_PROCESS_JOIN_TIMEOUT_SECONDS)
    assert read_process.exitcode == 0

    purge_result = _json_object_file(purge_marker)
    read_result = _json_object_file(read_marker)
    assert purge_result["purged"] is True
    assert isinstance(purge_result["tombstone_ref"], str)
    assert read_result == {
        "get_run": HostApiErrorCode.NOT_FOUND.value,
        "get_session": HostApiErrorCode.NOT_FOUND.value,
        "replay_run": HostApiErrorCode.NOT_FOUND.value,
        "retry_run": HostApiErrorCode.NOT_FOUND.value,
        "watch_session_events": HostApiErrorCode.NOT_FOUND.value,
    }


def test_purge_session_durable_rejects_open_session(tmp_path: Path) -> None:
    """purge helper 拒绝未关闭 Session 且不写 tombstone。"""

    tombstone: PurgeTombstoneRow | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedOpenSessionOperation())
        with pytest.raises(PurgeSessionInvalidStateError):
            store.transaction_runner.run_write(_PurgeMatrixOperation())
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())

    assert tombstone is None


@pytest.mark.parametrize("run_status", _NON_TERMINAL_RUN_STATUSES)
def test_purge_session_durable_rejects_non_terminal_runs(tmp_path: Path, run_status: str) -> None:
    """purge helper 拒绝 active/queued/running/waiting/cancelling/recovering Run。"""

    tombstone: PurgeTombstoneRow | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation(run_status=run_status))
        with pytest.raises(PurgeSessionInvalidStateError):
            store.transaction_runner.run_write(_PurgeMatrixOperation())
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())

    assert tombstone is None


def test_purge_session_durable_rejects_unsupported_projection_checkpoint_and_rolls_back(
    tmp_path: Path,
) -> None:
    """非白名单 projection checkpoint 引用目标 EventLog 时 purge 回滚。"""

    tombstone: PurgeTombstoneRow | None = None
    target_event_count = 0
    unsupported_checkpoint_count = 0
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())
        store.transaction_runner.run_write(_InsertUnsupportedProjectionCheckpointOperation())
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(_PurgeMatrixOperation())
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())
        target_event_count = store.transaction_runner.run_read(
            _ReadTableCountOperation(
                TABLE_EVENT_LOG,
                where_sql="WHERE session_id = ?",
                parameters=(_SESSION_ID,),
            )
        )
        unsupported_checkpoint_count = store.transaction_runner.run_read(
            _ReadTableCountOperation(
                TABLE_HOST_PROJECTION_CHECKPOINTS,
                where_sql="WHERE consumer_id = ?",
                parameters=(_UNSUPPORTED_PROJECTION_CONSUMER_ID,),
            )
        )

    assert tombstone is None
    assert target_event_count == 12
    assert unsupported_checkpoint_count == 1


def test_purge_session_durable_rejects_unsupported_projection_failure_and_rolls_back(
    tmp_path: Path,
) -> None:
    """非白名单 projection failure 引用目标 EventLog 时 purge 回滚。"""

    tombstone: PurgeTombstoneRow | None = None
    target_event_count = 0
    unsupported_failure_count = 0
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation())
        store.transaction_runner.run_write(_InsertUnsupportedProjectionFailureOperation())
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(_PurgeMatrixOperation())
        tombstone = store.transaction_runner.run_read(_ReadTombstoneBySessionOperation())
        target_event_count = store.transaction_runner.run_read(
            _ReadTableCountOperation(
                TABLE_EVENT_LOG,
                where_sql="WHERE session_id = ?",
                parameters=(_SESSION_ID,),
            )
        )
        unsupported_failure_count = store.transaction_runner.run_read(
            _ReadTableCountOperation(
                TABLE_HOST_PROJECTION_FAILURES,
                where_sql="WHERE consumer_id = ?",
                parameters=(_UNSUPPORTED_PROJECTION_CONSUMER_ID,),
            )
        )

    assert tombstone is None
    assert target_event_count == 12
    assert unsupported_failure_count == 1


def test_purge_session_durable_rejects_active_wait(tmp_path: Path) -> None:
    """purge helper 即使 Run 已终态也拒绝 active wait record。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(_SeedClosedSessionMatrixOperation(active_wait=True))
        with pytest.raises(PurgeSessionInvalidStateError):
            store.transaction_runner.run_write(_PurgeMatrixOperation())


def test_purge_session_durable_missing_session_without_tombstone_is_not_found(
    tmp_path: Path,
) -> None:
    """无 Session 且无 tombstone 时 purge helper 返回 not-found durable error。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(PurgeSessionNotFoundError):
            store.transaction_runner.run_write(_PurgeMatrixOperation())
