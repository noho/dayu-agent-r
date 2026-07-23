"""HostAdmin capability separation 与无 execution side effect 集成测试。"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host import (
    EnsureSessionRequest,
    FollowupBehavior,
    HostApiError,
    HostCallContext,
    OpenHostAdminOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    PurgeSessionRequest,
    SubmitFollowupRequest,
    open_host_admin,
)
from dayu.host.admission import create_host_admission_service
from dayu.host.api import HostCommandHandleOptions, HostLocalExecutionOptions
from dayu.host.command import (
    ensure_session,
    submit_followup,
)
from dayu.host.command import HostCommandHandle
from dayu.host.dispatch import ActiveWorkerRegistry, HostDispatchScheduler
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import project_host_durable_store_options
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.recovery import SessionAttachmentRecoveryScanner
from dayu.host.terminal_post_commit import (
    TerminalPostCommitNotice,
    TerminalPostCommitPort,
)


def _context(request_id: str) -> HostCallContext:
    """构造 admin 集成 seed 使用的 Host context。

    :param request_id: 请求 id。
    :returns: Host call context。
    :raises Exception: contract 校验失败时透传。
    """

    return HostCallContext(
        actor="test",
        source="test_public_host_admin",
        request_id=request_id,
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name="host_admin_test",
            operation_kind="test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="host_admin",
            correlation_id=request_id,
        ),
    )


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造无 scheduler 的 seed command options。

    :param tmp_path: pytest 临时目录。
    :returns: command handle options。
    :raises Exception: 不主动抛出异常。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-admin-seed",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=0.2,
        sqlite_write_busy_retry_count=3,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.01,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _admin_options(tmp_path: Path) -> OpenHostAdminOptions:
    """构造与 seed command 同源的 admin options。

    :param tmp_path: pytest 临时目录。
    :returns: admin opener options。
    :raises Exception: 不主动抛出异常。
    """

    options = _command_options(tmp_path)
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


def _ensure_request(slot_key: str) -> EnsureSessionRequest:
    """构造 seed Session 请求。

    :param slot_key: 稳定 slot key。
    :returns: ensure session 请求。
    :raises Exception: contract 校验失败时透传。
    """

    return EnsureSessionRequest(
        scope="test.host-admin",
        slot_key=slot_key,
        metadata=(),
    )


def _followup_request(session_id: str, request_id: str) -> SubmitFollowupRequest:
    """构造无 execution baseline 的 durable queue seed 请求。

    :param session_id: 目标 Session id。
    :param request_id: client request id。
    :returns: follow-up 请求。
    :raises Exception: contract 校验失败时透传。
    """

    return SubmitFollowupRequest(
        context=_context(request_id),
        session_id=session_id,
        client_request_id=request_id,
        system_prompt=None,
        user_prompt="seed durable run",
        tool_names=frozenset(),
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _ordinary_baseline() -> OrdinaryRunExecutionBaseline:
    """构造只用于冻结 durable execution facts 的 baseline。

    :returns: ordinary Run execution baseline。
    :raises Exception: typed contract 校验失败时透传。
    """

    return OrdinaryRunExecutionBaseline(
        runner_spec=RunnerSpec(
            provider="test",
            model="admin-seed",
            endpoint="https://example.invalid",
            api_key_ref="secret:unused-admin-seed",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            default_timeout_seconds=1.0,
            max_retries=0,
            provider_request=None,
        ),
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
            fallback_prompt="unused admin seed fallback",
            continuation_prompt="unused admin seed continuation",
        ),
    )


class _NoLocalDeliveryTerminalPostCommitPort(TerminalPostCommitPort):
    """测试专用的 no-local-delivery terminal 最终端点。"""

    def notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """消费 exact notice，但不做任何 local delivery 动作。

        :param notice: exact terminal notice。
        :returns: ``None``。
        """

        del notice


def _seed_nonterminal_runs(tmp_path: Path) -> str:
    """seed ACCEPTED、QUEUED、RECOVERING 三类 Run。

    :param tmp_path: pytest 临时目录。
    :returns: 包含 ACCEPTED/QUEUED Run 的 Session id。
    :raises Exception: durable seed 失败时透传。
    """

    options = _command_options(tmp_path)
    durable_store = open_host_durable_store(
        project_host_durable_store_options(options)
    )
    terminal_post_commit_port = _NoLocalDeliveryTerminalPostCommitPort()
    handle = HostCommandHandle(
        host_handle_id="host-admin-seed",
        durable_store=durable_store,
        admission_service=create_host_admission_service(
            durable_store.transaction_runner,
            terminal_post_commit_port=terminal_post_commit_port,
            ordinary_run_baseline=_ordinary_baseline(),
        ),
        active_registry=ActiveWorkerRegistry(),
        terminal_post_commit_port=terminal_post_commit_port,
    )
    try:
        session = ensure_session(handle, _ensure_request("primary"))
        submit_followup(
            handle,
            session.session_id,
            _followup_request(session.session_id, "accepted"),
        )
        submit_followup(
            handle,
            session.session_id,
            _followup_request(session.session_id, "queued"),
        )
        recovering_session = ensure_session(handle, _ensure_request("recovering"))
        recovering = submit_followup(
            handle,
            recovering_session.session_id,
            _followup_request(recovering_session.session_id, "recovering"),
        )
    finally:
        handle.close()
    connection = sqlite3.connect(_command_options(tmp_path).db_path)
    try:
        connection.execute(
            """UPDATE host_runs
               SET status = 'recovering',
                   started_event_id = accepted_event_id,
                   started_event_sequence = accepted_event_sequence
               WHERE run_id = ?""",
            (recovering.accepted_run_id,),
        )
        connection.commit()
    finally:
        connection.close()
    return session.session_id


def _durable_counts(db_path: Path) -> tuple[int, int, int, tuple[tuple[str, int], ...]]:
    """读取 admin 不得改变的 durable count 与 Run status 分布。

    :param db_path: Host SQLite 路径。
    :returns: Run、EventLog、host-instance count 与 status 分布。
    :raises sqlite3.Error: 查询失败时透传。
    """

    connection = sqlite3.connect(db_path)
    try:
        run_count = int(connection.execute("SELECT COUNT(*) FROM host_runs").fetchone()[0])
        event_count = int(connection.execute("SELECT COUNT(*) FROM event_log").fetchone()[0])
        instance_count = int(
            connection.execute("SELECT COUNT(*) FROM host_instances").fetchone()[0]
        )
        statuses = tuple(
            (str(row[0]), int(row[1]))
            for row in connection.execute(
                "SELECT status, COUNT(*) FROM host_runs GROUP BY status ORDER BY status"
            ).fetchall()
        )
        return run_count, event_count, instance_count, statuses
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_admin_list_and_rejected_purge_do_not_start_execution_or_mutate_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """admin graph 不创建 scheduler/recovery，非终态 facts 前后完全不变。"""

    session_id = _seed_nonterminal_runs(tmp_path)
    before = _durable_counts(_command_options(tmp_path).db_path)
    assert dict(before[3]) == {"accepted": 1, "queued": 1, "recovering": 1}

    async def forbidden_scheduler_open(
        *,
        transaction_runner: HostTransactionRunner,
        local_execution: HostLocalExecutionOptions,
        host_handle_id: str,
        active_registry: ActiveWorkerRegistry | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
    ) -> HostDispatchScheduler:
        """禁止 admin opener 创建 scheduler。

        :param transaction_runner: 禁止使用的 transaction runner。
        :param local_execution: 禁止使用的 execution options。
        :param host_handle_id: 禁止使用的 Host id。
        :param active_registry: 禁止使用的 active registry。
        :param projection_catchup_port: 禁止使用的 projection port。
        :returns: 不返回。
        :raises AssertionError: 始终抛出。
        """

        del transaction_runner, local_execution, host_handle_id
        del active_registry, projection_catchup_port
        raise AssertionError("admin opener must not create scheduler")

    def forbidden_recovery_scan(self: SessionAttachmentRecoveryScanner) -> None:
        """禁止 admin opener 执行 recovery。

        :param self: recovery scanner。
        :returns: 不返回。
        :raises AssertionError: 始终抛出。
        """

        raise AssertionError("admin opener must not run recovery")

    monkeypatch.setattr(HostDispatchScheduler, "open", forbidden_scheduler_open)
    monkeypatch.setattr(SessionAttachmentRecoveryScanner, "scan", forbidden_recovery_scan)
    async with open_host_admin(_admin_options(tmp_path)) as admin:
        result = await admin.list_sessions()
        assert len(result.sessions) == 2
        with pytest.raises(HostApiError):
            await admin.purge_session(
                session_id,
                PurgeSessionRequest(
                    context=_context("purge-nonterminal"),
                    client_request_id="purge-nonterminal",
                    reason="must remain unchanged",
                ),
            )
        assert not hasattr(admin, "ensure_session")
        assert not hasattr(admin, "submit_followup")
        assert not hasattr(admin, "cancel_run")
        assert not hasattr(admin, "watch_session_events")
    after = _durable_counts(_command_options(tmp_path).db_path)

    assert after == before


@pytest.mark.asyncio
async def test_admin_close_is_idempotent_and_leaves_no_actor_thread(
    tmp_path: Path,
) -> None:
    """admin close 只回收 actor chain，重复 close 不残留 worker thread。"""

    manager = open_host_admin(_admin_options(tmp_path))
    admin = await manager.__aenter__()
    await admin.list_sessions()
    await admin.close()
    await admin.close()
    await manager.__aexit__(None, None, None)

    assert not any(
        thread.is_alive() and "open-host-admin" in thread.name
        for thread in threading.enumerate()
    )
