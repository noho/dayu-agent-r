"""Host public Session facade 测试。"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from dayu.host import (
    AuthorizationClaim,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostCommandHandle,
    HostCommandHandleOptions,
    HostMetadataEntry,
    OperationContext,
    SessionStatus,
    close_session,
    create_host_command_handle,
    create_session,
    ensure_session,
    get_session,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.state import (
    SessionRow,
    _public_session_status_from_durable,
)
from dayu.host.durable.transaction import HostTransaction


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
    )


def _open_handle(tmp_path: Path) -> HostCommandHandle:
    """创建测试用 Host command handle。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle。
    """

    return create_host_command_handle(_options(tmp_path))


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

    def __call__(
        self, transaction: HostTransaction, session_id: str
    ) -> SessionRow | None:
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
        _public_session_status_from_durable(
            cast(SessionStatus, "future_session_status")
        )


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
        authorization_claims=(
            AuthorizationClaim(name="role", value="research"),
        ),
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

    return EnsureSessionRequest(
        scope="workspace", slot_key=slot_key, metadata=_metadata("ensure")
    )


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

    return CloseSessionRequest(
        context=_context(), client_request_id=client_request_id, reason="done"
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
