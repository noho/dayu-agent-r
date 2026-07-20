"""Host public Session facade 测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host import (
    AttemptDispatchSnapshot,
    AuthorizationClaim,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostClosedError,
    HostMetadataEntry,
    LocalEngineWorker,
    OpenHostAdminOptions,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    PurgeSessionRequest,
    SessionStatus,
    close_session,
    create_session,
    ensure_session,
    get_session,
    list_sessions,
    open_host,
    open_host_admin,
    purge_session,
)
from dayu.host.api import HostCommandHandleOptions
from dayu.host.durable.codec import format_utc_timestamp
import dayu.host.command as command_module
from dayu.host.command import HostCommandHandle, create_host_command_handle
from dayu.host.durable.schema import TABLE_HOST_SESSIONS
from dayu.host.durable.errors import HostDurableError, HostRowDecodeError
from dayu.host.durable.state import (
    SessionRow,
    _slot_row_from_session_list_host_row,
    _public_session_status_from_durable,
)
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.memory import default_memory_projection_policy
from dayu.host.projection import ProjectionCatchupPort


def _options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-session-api",
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


def _open_handle(tmp_path: Path) -> HostCommandHandle:
    """创建测试用 Host command handle。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle。
    """

    return create_host_command_handle(_options(tmp_path))


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
        lane_default_timeout_seconds=0.2,
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
        worker_factory=_UnusedWorkerFactory(),
        tooling_options=None,
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
    )


def _open_host_admin_options(tmp_path: Path) -> OpenHostAdminOptions:
    """构造与 execution opener 使用同一 durable policy 的 admin options。

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
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


class _UnusedWorkerFactory:
    """不会被本测试触发的 worker factory。"""

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """满足 ``OpenHostOptions`` 类型契约。

        :param snapshot: dispatch snapshot；本测试不触发 dispatch。
        :returns: 不返回，本方法始终抛出异常。
        :raises RuntimeError: 如果测试意外触发 dispatch 则抛出。
        """

        del snapshot
        raise RuntimeError("list_sessions test must not dispatch worker")


@dataclass(frozen=True, slots=True)
class _SetSessionCreatedAtOperation:
    """测试用 Session created_at 修正事务。"""

    session_id: str
    created_at: str

    def __call__(self, transaction: HostTransaction) -> None:
        """更新指定 Session 的 created_at。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            UPDATE {TABLE_HOST_SESSIONS}
            SET created_at = ?
            WHERE session_id = ?
            """,
            (self.created_at, self.session_id),
        )


@dataclass(frozen=True, slots=True)
class _CorruptSessionCreatedAtOperation:
    """测试用 Session created_at 损坏事务。"""

    session_id: str

    def __call__(self, transaction: HostTransaction) -> None:
        """把指定 Session 的 created_at 更新为非法 timestamp。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            UPDATE {TABLE_HOST_SESSIONS}
            SET created_at = ?
            WHERE session_id = ?
            """,
            ("not-a-fixed-utc-timestamp", self.session_id),
        )


def test_session_lifecycle_commands_trigger_projection_catchup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session lifecycle facade 写入 durable 后必须触发 projection catch-up。"""

    calls = 0

    def record_catchup(port: ProjectionCatchupPort | None) -> None:
        """记录 catch-up 调用。

        :param port: command handle admission service 持有的 catch-up port。
        :returns: ``None``。
        """

        nonlocal calls
        assert port is not None
        calls += 1

    monkeypatch.setattr(
        command_module,
        "catch_up_projection_best_effort",
        record_catchup,
    )
    handle = _open_handle(tmp_path)
    try:
        ensured = ensure_session(handle, _ensure_request())
        created = create_session(handle, _create_request("create-catchup"))
        close_session(handle, created.session_id, _close_request("close-catchup"))
    finally:
        handle.close()

    assert ensured.session_id
    assert calls == 3


def _durable_session_row(status: SessionStatus) -> SessionRow:
    """构造 Session status mapping 测试用 durable Session row。

    :param status: durable Session status。
    :returns: Session row。
    """

    return SessionRow(
        session_id="session-mapping",
        status=status,
        metadata_json="{}",
        created_event_id="event-created",
        created_event_sequence=1,
        closed_event_id=None,
        closed_event_sequence=None,
        created_at="2026-05-16T00:00:00.000000Z",
        closed_at=None,
    )


class _UnknownSessionStatusReader:
    """get_session monkeypatch 用 Session reader。"""

    def __call__(self, transaction: HostTransaction, session_id: str) -> SessionRow | None:
        """返回带未知 status 的 durable Session row。

        :param transaction: Host transaction。
        :param session_id: Session id。
        :returns: Session row。
        """

        return _durable_session_row(cast(SessionStatus, "future_session_status"))


def test_session_status_mapping_covers_current_session_statuses() -> None:
    """durable Session status 到 public SessionStatus 的映射覆盖当前枚举。"""

    for status in SessionStatus:
        assert _public_session_status_from_durable(status) is status


def test_session_status_mapping_rejects_unknown_session_status() -> None:
    """Session status mapping 对未知 durable status fail closed。"""

    with pytest.raises(HostDurableError):
        _public_session_status_from_durable(cast(SessionStatus, "future_session_status"))


def test_get_session_unknown_durable_status_returns_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """public get_session 把 durable status mapping 失败转为 HostApiError。"""

    command_handle = _open_handle(tmp_path)
    try:
        monkeypatch.setattr(
            "dayu.host.read_api.read_session_by_id",
            _UnknownSessionStatusReader(),
        )

        with pytest.raises(HostApiError) as exc_info:
            get_session(command_handle, "session-mapping")

        assert exc_info.value.code == HostApiErrorCode.INTERNAL_ERROR
        assert exc_info.value.retryable is False
    finally:
        command_handle.close()


def _context(actor: str = "analyst", request_id: str = "trace-1") -> HostCallContext:
    """构造测试用 Host call context。

    :param actor: 调用主体。
    :param request_id: trace request id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor=actor,
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="public_session_api",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase4",
            correlation_id="corr-session",
        ),
    )


def _metadata(value: str) -> tuple[HostMetadataEntry, ...]:
    """构造测试 metadata。

    :param value: metadata 值。
    :returns: Host metadata entries。
    """

    return (HostMetadataEntry(key="case", value=value),)


def _ensure_request(slot_key: str = "slot-a") -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :param slot_key: slot key。
    :returns: ensure session 请求。
    """

    return EnsureSessionRequest(scope="workspace", slot_key=slot_key, metadata=_metadata("ensure"))


def _create_request(
    client_request_id: str,
    *,
    bind_slot: bool = False,
    actor: str = "analyst",
) -> CreateSessionRequest:
    """构造 create session 请求。

    :param client_request_id: 幂等请求 id。
    :param bind_slot: 是否绑定 slot。
    :param actor: 调用主体。
    :returns: create session 请求。
    """

    return CreateSessionRequest(
        context=_context(actor=actor),
        client_request_id=client_request_id,
        bind_slot=bind_slot,
        scope="workspace" if bind_slot else None,
        slot_key="slot-a" if bind_slot else None,
        metadata=_metadata("create"),
    )


def _close_request(client_request_id: str) -> CloseSessionRequest:
    """构造 close session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: close session 请求。
    """

    return CloseSessionRequest(context=_context(), client_request_id=client_request_id, reason="done")


def _purge_request(client_request_id: str) -> PurgeSessionRequest:
    """构造 purge session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: purge session 请求。
    """

    return PurgeSessionRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="public_session_api_purge",
    )


def test_ensure_session_repeat_returns_same_snapshot(tmp_path: Path) -> None:
    """重复 ensure_session 返回同一个 SessionSnapshot。"""

    command_handle = _open_handle(tmp_path)
    try:
        first = ensure_session(command_handle, _ensure_request())
        second = ensure_session(command_handle, _ensure_request())

        assert second == first
        assert second.status == SessionStatus.OPEN
        assert second.active_run_id is None
        assert second.queued_run_ids == ()
    finally:
        command_handle.close()


def test_create_session_idempotent_replay_returns_same_session(
    tmp_path: Path,
) -> None:
    """同一 create_session 幂等 key 重放返回同一个 Session。"""

    command_handle = _open_handle(tmp_path)
    try:
        request = _create_request("create-1")
        first = create_session(command_handle, request)
        second = create_session(command_handle, request)

        assert second == first
        assert get_session(command_handle, first.session_id) == first
    finally:
        command_handle.close()


def test_create_session_same_key_different_digest_conflicts(
    tmp_path: Path,
) -> None:
    """同一 create_session 幂等 key 携带不同 semantic digest 时返回冲突。"""

    command_handle = _open_handle(tmp_path)
    try:
        create_session(command_handle, _create_request("create-1"))

        with pytest.raises(HostApiError) as exc_info:
            create_session(
                command_handle,
                _create_request("create-1", actor="different-actor"),
            )
        assert exc_info.value.code == HostApiErrorCode.IDEMPOTENCY_CONFLICT
        assert exc_info.value.retryable is False
    finally:
        command_handle.close()


def test_close_session_is_idempotent_and_does_not_remove_session(
    tmp_path: Path,
) -> None:
    """close_session 可幂等重放，并保留 Session durable truth。"""

    command_handle = _open_handle(tmp_path)
    try:
        created = create_session(command_handle, _create_request("create-1"))
        request = _close_request("close-1")

        first = close_session(command_handle, created.session_id, request)
        second = close_session(command_handle, created.session_id, request)
        fetched = get_session(command_handle, created.session_id)

        assert first == second
        assert fetched == first
        assert fetched.status == SessionStatus.CLOSED
        assert fetched.active_run_id is None
        assert fetched.queued_run_ids == ()
    finally:
        command_handle.close()


def test_get_session_missing_returns_not_found(tmp_path: Path) -> None:
    """get_session 对缺失 Session 返回 NOT_FOUND。"""

    command_handle = _open_handle(tmp_path)
    try:
        with pytest.raises(HostApiError) as exc_info:
            get_session(command_handle, "session-missing")
        assert exc_info.value.code == HostApiErrorCode.NOT_FOUND
        assert exc_info.value.retryable is False
    finally:
        command_handle.close()


def test_get_session_after_purge_returns_not_found(tmp_path: Path) -> None:
    """get_session 在 purge 后不从 tombstone 重建 Session snapshot。"""

    command_handle = _open_handle(tmp_path)
    try:
        created = create_session(command_handle, _create_request("create-1"))
        close_session(command_handle, created.session_id, _close_request("close-1"))
        result = purge_session(
            command_handle,
            created.session_id,
            _purge_request("purge-1"),
        )

        with pytest.raises(HostApiError) as exc_info:
            get_session(command_handle, created.session_id)

        assert result.purged is True
        assert result.purge_tombstone_ref is not None
        assert result.deleted_counts_digest is not None
        assert exc_info.value.code == HostApiErrorCode.NOT_FOUND
        assert exc_info.value.retryable is False
    finally:
        command_handle.close()


def test_list_sessions_returns_durable_rows_with_stable_sort_and_no_purged(
    tmp_path: Path,
) -> None:
    """list_sessions 返回未 purge Session，并按 durable 时间与 id 稳定排序。"""

    command_handle = _open_handle(tmp_path)
    try:
        labeled = ensure_session(command_handle, _ensure_request("slot-labeled"))
        anonymous = create_session(
            command_handle,
            _create_request("create-anonymous"),
        )
        closed = create_session(
            command_handle,
            _create_request("create-closed", bind_slot=True),
        )
        closed = close_session(
            command_handle,
            closed.session_id,
            _close_request("close-listed"),
        )
        purged = create_session(command_handle, _create_request("create-purged"))
        close_session(
            command_handle,
            purged.session_id,
            _close_request("close-purged"),
        )
        purge_session(
            command_handle,
            purged.session_id,
            _purge_request("purge-listed"),
        )

        latest_created_at = format_utc_timestamp(
            datetime(2026, 5, 17, 1, 2, 3, 456789, tzinfo=UTC)
        )
        older_created_at = format_utc_timestamp(
            datetime(2026, 5, 16, 1, 2, 3, 456789, tzinfo=UTC)
        )
        command_handle._run_write(
            _SetSessionCreatedAtOperation(
                session_id=labeled.session_id,
                created_at=latest_created_at,
            )
        )
        command_handle._run_write(
            _SetSessionCreatedAtOperation(
                session_id=anonymous.session_id,
                created_at=latest_created_at,
            )
        )
        command_handle._run_write(
            _SetSessionCreatedAtOperation(
                session_id=closed.session_id,
                created_at=older_created_at,
            )
        )

        result = list_sessions(command_handle)
        items_by_id = {item.session_id: item for item in result.sessions}
        expected_tied_ids = sorted((labeled.session_id, anonymous.session_id))

        assert [item.session_id for item in result.sessions] == [
            *expected_tied_ids,
            closed.session_id,
        ]
        assert purged.session_id not in items_by_id
        assert items_by_id[labeled.session_id].slot is not None
        assert items_by_id[labeled.session_id].slot == labeled.slot
        assert items_by_id[anonymous.session_id].slot is None
        assert items_by_id[closed.session_id].status is SessionStatus.CLOSED
        assert items_by_id[closed.session_id].closed_at is not None
        assert items_by_id[labeled.session_id].active_run_id is None
        assert items_by_id[labeled.session_id].queued_run_ids == ()
        assert items_by_id[labeled.session_id].created_at == datetime(
            2026, 5, 17, 1, 2, 3, 456789, tzinfo=UTC
        )
    finally:
        command_handle.close()


def test_list_sessions_empty_database_returns_empty_result(tmp_path: Path) -> None:
    """list_sessions 在全新 durable store 上返回空 Session 元组。"""

    command_handle = _open_handle(tmp_path)
    try:
        result = list_sessions(command_handle)

        assert result.sessions == ()
    finally:
        command_handle.close()


def test_session_list_slot_row_missing_alias_raises_row_decode_error() -> None:
    """Session list slot join row 缺少预期 alias 时 fail closed。"""

    row = HostRow(
        columns=(
            "slot_slot_key",
            "slot_session_id",
            "slot_bound_event_id",
            "slot_bound_event_sequence",
            "slot_metadata_json",
            "slot_updated_at",
        ),
        values=(None, None, None, None, None, None),
    )

    with pytest.raises(HostRowDecodeError) as exc_info:
        _slot_row_from_session_list_host_row(row)

    assert exc_info.value.field_name == "slot_scope"


def test_list_sessions_malformed_timestamp_returns_public_internal_error(
    tmp_path: Path,
) -> None:
    """list_sessions 对 malformed durable timestamp fail closed。"""

    command_handle = _open_handle(tmp_path)
    try:
        created = create_session(command_handle, _create_request("create-bad-time"))
        command_handle._run_write(
            _CorruptSessionCreatedAtOperation(session_id=created.session_id)
        )

        with pytest.raises(HostApiError) as exc_info:
            list_sessions(command_handle)

        cause = exc_info.value.__cause__
        assert exc_info.value.code == HostApiErrorCode.INTERNAL_ERROR
        assert exc_info.value.retryable is False
        assert isinstance(cause, HostDurableError)
        assert "session row timestamp is invalid" in str(cause)
        assert "not-a-fixed-utc-timestamp" not in str(cause)
    finally:
        command_handle.close()


@pytest.mark.asyncio
async def test_open_host_admin_lists_sessions_and_closed_handle(tmp_path: Path) -> None:
    """HostAdmin 暴露 list_sessions，并在关闭后 fail fast。"""

    async with open_host(_open_host_options(tmp_path)) as execution_host:
        created = await execution_host.create_session(
            _create_request("open-host-list")
        )
    host_manager = open_host_admin(_open_host_admin_options(tmp_path))
    host_admin = await host_manager.__aenter__()
    try:
        result = await host_admin.list_sessions()
        assert [item.session_id for item in result.sessions] == [created.session_id]
    finally:
        await host_manager.__aexit__(None, None, None)

    with pytest.raises(HostClosedError):
        await host_admin.list_sessions()
