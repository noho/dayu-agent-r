"""Host public command handle factory 与 lifecycle 测试。"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path
from typing import cast

import dayu.host as host_package
import pytest

from dayu.host import (
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
    CancelSessionRunsRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostCommandHandle,
    HostCommandHandleOptions,
    HostInput,
    HostLocalExecutionOptions,
    LocalEngineWorkerFactory,
    OperationContext,
    StartRunRequest,
    SubmitFollowupRequest,
    cancel_run,
    cancel_session_runs,
    create_host_command_handle,
    ensure_session,
    start_run,
    submit_followup,
)
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec

_FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "dayu.fins",
    "dayu.service",
    "dayu.ui",
)


class _WorkerFactoryToken:
    """测试用 worker factory token。

    public sync command handle 不消费该结构协议；真实 scheduler 装配由
    HostDispatchScheduler.open 与 pyright 保障。
    """


def _options(tmp_path: Path, host_handle_id: str | None = "host-test") -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :param host_handle_id: 可选 public handle id。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id=host_handle_id,
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


def _local_execution_options(tmp_path: Path) -> HostLocalExecutionOptions:
    """构造测试用 local execution options。

    :param tmp_path: pytest 临时目录。
    :returns: HostLocalExecutionOptions。
    """

    return HostLocalExecutionOptions(
        lane_db_path=tmp_path / "lane.sqlite3",
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.1,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        runner_spec=RunnerSpec(
            provider="test",
            model="test-model",
            endpoint="https://example.invalid",
            api_key_ref="secret:test",
            headers={},
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
        ),
        worker_factory=cast(LocalEngineWorkerFactory, _WorkerFactoryToken()),
    )


def _ensure_request() -> EnsureSessionRequest:
    """构造测试用 ensure session 请求。

    :returns: ensure session 请求。
    """

    return EnsureSessionRequest(scope="workspace", slot_key="slot-a", metadata=())


def _context(request_id: str = "trace-command-handle") -> HostCallContext:
    """构造测试用 Host call context。

    :param request_id: trace request id。
    :returns: Host call context。
    :raises ValueError: context 字段不满足公共类型约束时抛出。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="command_handle_lifecycle",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="closed_handle",
            correlation_id="corr-command-handle",
        ),
    )


def _input(display_text: str) -> HostInput:
    """构造测试用 Host 输入。

    :param display_text: 展示文本。
    :returns: Host input。
    :raises ValueError: 输入展示文本为空时抛出。
    """

    return HostInput(
        display_text=display_text,
        payload_ref=None,
        payload_digest=None,
    )


def _start_request(session_id: str, client_request_id: str) -> StartRunRequest:
    """构造 start_run 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :returns: start run 请求。
    :raises ValueError: 请求字段不满足公共类型约束时抛出。
    """

    return StartRunRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(f"start-{client_request_id}"),
        execution_target="public-target",
        queue_policy="queue",
    )


def _followup_request(
    session_id: str,
    client_request_id: str,
    *,
    behavior: FollowupBehavior = FollowupBehavior.QUEUE,
    target_run_id: str | None = None,
) -> SubmitFollowupRequest:
    """构造 submit_followup 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param behavior: follow-up 行为。
    :param target_run_id: steer 目标 Run id。
    :returns: submit follow-up 请求。
    :raises ValueError: 请求字段或 behavior / target_run_id 组合非法时抛出。
    """

    return SubmitFollowupRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=_input(f"follow-{client_request_id}"),
        behavior=behavior,
        target_run_id=target_run_id,
    )


def _cancel_run_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: cancel run 请求。
    :raises ValueError: 请求字段不满足公共类型约束时抛出。
    """

    return CancelRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_stop",
        mode=CancelMode.GRACEFUL,
    )


def _cancel_session_runs_request(
    client_request_id: str,
) -> CancelSessionRunsRequest:
    """构造 cancel_session_runs 请求。

    :param client_request_id: 幂等请求 id。
    :returns: cancel session runs 请求。
    :raises ValueError: 请求字段不满足公共类型约束时抛出。
    """

    return CancelSessionRunsRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_stop_all",
        mode=CancelMode.GRACEFUL,
    )


def _event_count(db_path: Path) -> int:
    """统计 EventLog row 数。

    :param db_path: SQLite DB 路径。
    :returns: EventLog row 数。
    :raises sqlite3.Error: SQLite 查询失败时抛出。
    :raises AssertionError: COUNT 查询未返回 row 时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM event_log").fetchone()
    assert row is not None
    return int(row[0])


def _idempotency_count(db_path: Path) -> int:
    """统计 idempotency record 数。

    :param db_path: SQLite DB 路径。
    :returns: idempotency record 数。
    :raises sqlite3.Error: SQLite 查询失败时抛出。
    :raises AssertionError: COUNT 查询未返回 row 时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM idempotency_records"
        ).fetchone()
    assert row is not None
    return int(row[0])


def _assert_closed_handle_error(exc: HostApiError) -> None:
    """断言 public facade 返回关闭 handle 的稳定错误。

    :param exc: 捕获到的 Host API 错误。
    :returns: 无返回值。
    :raises AssertionError: 错误契约不匹配时抛出。
    """

    assert exc.code == HostApiErrorCode.INVALID_STATE
    assert exc.retryable is False


def _host_root() -> Path:
    """返回 Host 包源码根目录。

    :returns: ``dayu/host`` 源码目录。
    :raises AssertionError: Host 包缺少 ``__file__`` 时抛出。
    """

    package_file = host_package.__file__
    assert package_file is not None
    return Path(package_file).resolve().parent


def _imported_module_names(source: str) -> list[str]:
    """读取 Python 源码中的绝对 import 模块名。

    :param source: Python 源码。
    :returns: 模块名列表。
    """

    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                names.append(node.module)
    return names


def _matches_forbidden_prefix(module: str) -> bool:
    """判断模块名是否命中 Host 禁止依赖层。

    :param module: 模块名。
    :returns: 命中返回 ``True``。
    """

    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )


def test_factory_opens_fresh_database_and_returns_public_handle(
    tmp_path: Path,
) -> None:
    """factory 能创建 fresh DB，并返回稳定 public handle。"""

    options = _options(tmp_path, host_handle_id="stable-host")
    command_handle = create_host_command_handle(options)
    try:
        assert isinstance(command_handle, HostCommandHandle)
        assert command_handle.host_handle_id == "stable-host"
        assert options.db_path.exists()
        assert ensure_session(command_handle, _ensure_request()).session_id
    finally:
        command_handle.close()


def test_factory_rejects_local_execution_without_hidden_scheduler(
    tmp_path: Path,
) -> None:
    """sync command handle factory 不隐式消费 local execution 配置。"""

    options = _options(tmp_path)
    local_options = _local_execution_options(tmp_path)

    with pytest.raises(ValueError, match="local_execution"):
        create_host_command_handle(
            HostCommandHandleOptions(
                host_handle_id=options.host_handle_id,
                db_path=options.db_path,
                artifact_root=options.artifact_root,
                create_parent_dirs=options.create_parent_dirs,
                sqlite_busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
                sqlite_write_busy_retry_count=(
                    options.sqlite_write_busy_retry_count
                ),
                sqlite_write_retry_initial_delay_seconds=(
                    options.sqlite_write_retry_initial_delay_seconds
                ),
                sqlite_write_retry_backoff_multiplier=(
                    options.sqlite_write_retry_backoff_multiplier
                ),
                sqlite_write_retry_max_delay_seconds=(
                    options.sqlite_write_retry_max_delay_seconds
                ),
                payload_inline_threshold_bytes=(
                    options.payload_inline_threshold_bytes
                ),
                local_execution=local_options,
            )
        )


def test_generated_handle_id_is_stable_for_handle_lifetime(
    tmp_path: Path,
) -> None:
    """未显式提供 handle id 时，factory 生成生命周期内稳定的 public id。"""

    command_handle = create_host_command_handle(
        _options(tmp_path, host_handle_id=None)
    )
    try:
        first_id = command_handle.host_handle_id
        assert first_id.startswith("host-command-")
        assert command_handle.host_handle_id == first_id
    finally:
        command_handle.close()


def test_public_handle_does_not_expose_internal_mutable_dependencies(
    tmp_path: Path,
) -> None:
    """public handle 不暴露 store、transaction runner 或 admission service。"""

    command_handle = create_host_command_handle(_options(tmp_path))
    try:
        public_names = {
            name for name in dir(command_handle) if not name.startswith("_")
        }
        assert "host_handle_id" in public_names
        assert "close" in public_names
        assert "transaction_runner" not in public_names
        assert "durable_store" not in public_names
        assert "admission_service" not in public_names
        assert "store_connection" not in public_names
    finally:
        command_handle.close()


def test_handle_close_is_idempotent_and_facade_fails_after_close(
    tmp_path: Path,
) -> None:
    """handle close 可重复调用；关闭后 public facade 返回稳定错误。"""

    command_handle = create_host_command_handle(_options(tmp_path))
    ensure_session(command_handle, _ensure_request())

    command_handle.close()
    command_handle.close()

    with pytest.raises(HostApiError) as exc_info:
        ensure_session(command_handle, _ensure_request())
    _assert_closed_handle_error(exc_info.value)


def test_admission_backed_facades_fail_closed_before_public_branches(
    tmp_path: Path,
) -> None:
    """关闭后 admission-backed public facade 先返回 lifecycle 错误且不写事实。

    :param tmp_path: pytest 临时目录。
    :returns: 无返回值。
    :raises AssertionError: public 错误契约或 durable 写入断言不满足时抛出。
    """

    options = _options(tmp_path)
    command_handle = create_host_command_handle(options)
    session_id = ensure_session(command_handle, _ensure_request()).session_id
    active = start_run(command_handle, _start_request(session_id, "start-open"))
    before_events = _event_count(options.db_path)
    before_idempotency = _idempotency_count(options.db_path)

    command_handle.close()

    with pytest.raises(HostApiError) as start_exc:
        start_run(command_handle, _start_request(session_id, "start-closed"))
    with pytest.raises(HostApiError) as followup_mismatch_exc:
        submit_followup(
            command_handle,
            "different-session",
            _followup_request(session_id, "follow-mismatch"),
        )
    with pytest.raises(HostApiError) as followup_steer_exc:
        submit_followup(
            command_handle,
            session_id,
            _followup_request(
                session_id,
                "follow-steer",
                behavior=FollowupBehavior.STEER,
                target_run_id=active.run_id,
            ),
        )
    with pytest.raises(HostApiError) as cancel_run_exc:
        cancel_run(
            command_handle,
            active.run_id,
            _cancel_run_request("cancel-closed"),
        )
    with pytest.raises(HostApiError) as cancel_session_runs_exc:
        cancel_session_runs(
            command_handle,
            session_id,
            _cancel_session_runs_request("cancel-session-closed"),
        )

    for exc_info in (
        start_exc,
        followup_mismatch_exc,
        followup_steer_exc,
        cancel_run_exc,
        cancel_session_runs_exc,
    ):
        _assert_closed_handle_error(exc_info.value)
    assert _event_count(options.db_path) == before_events
    assert _idempotency_count(options.db_path) == before_idempotency


def test_host_import_boundary_still_excludes_upper_layers() -> None:
    """Host public command path 不能引入 Engine / Fins / Service / UI 依赖。"""

    violations: list[tuple[str, str]] = []
    for file_path in sorted(_host_root().rglob("*.py")):
        if "__pycache__" in file_path.parts:
            continue
        for module in _imported_module_names(
            file_path.read_text(encoding="utf-8")
        ):
            if _matches_forbidden_prefix(module):
                violations.append((str(file_path), module))
    assert not violations
