"""Host S15 日志语义与脱敏测试。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.messages import AgentMessageRole, SystemMessage
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import (
    AuthorizationClaim,
    EnsureSessionRequest,
    HostCallContext,
    OperationContext,
    ensure_session,
)
from dayu.host.api import (
    HostInput,
    AttemptDispatchSnapshot,
    HostCommandHandleOptions,
    StartRunRequest,
)
from dayu.host.command import create_host_command_handle, start_run
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.local_proxy import DefaultLocalEngineWorker
from dayu.host.memory import default_memory_projection_policy
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.run_input import NoToolExecutor
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_SECRET_PROMPT = "SECRET_FULL_PROMPT_DO_NOT_LOG"
_SECRET_AUTH = "SECRET_AUTH_CLAIM_DO_NOT_LOG"


class _NeverCancelledToken(CancellationToken):
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


def test_command_logs_verbose_ids_without_prompt_or_auth_claims(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """public command 只记录 typed ids，不泄漏 prompt 或授权声明。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 日志级别、字段或脱敏不符合预期时抛出。
    """

    host = create_host_command_handle(_command_options(tmp_path))
    try:
        session = ensure_session(
            host,
            EnsureSessionRequest(
                scope="logging-test",
                slot_key="slot-1",
                metadata=(),
            ),
        )
        with caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.command"):
            snapshot = start_run(
                host,
                StartRunRequest(
                    context=_call_context(),
                    session_id=session.session_id,
                    client_request_id="client-log-start",
                    input=HostInput(
                        display_text=_SECRET_PROMPT,
                        payload_ref=None,
                        payload_digest=None,
                    ),
                    execution_target="target-log",
                    queue_policy="queue",
                ),
            )

        messages = tuple(record.getMessage() for record in caplog.records)
        assert snapshot.run_id in caplog.text
        assert session.session_id in caplog.text
        assert any("host.command.accepted" in message for message in messages)
        assert any("host.command.committed" in message for message in messages)
        assert all(record.levelno == VERBOSE_LOG_LEVEL for record in caplog.records)
        assert _SECRET_PROMPT not in caplog.text
        assert _SECRET_AUTH not in caplog.text
    finally:
        host.close()


@pytest.mark.asyncio
async def test_local_proxy_accept_log_uses_counts_not_message_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """LocalProxy accept 日志只记录 ids 与 message_count。

    :param caplog: pytest 日志捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 日志泄漏 message content 或缺少关键字段时抛出。
    """

    worker = DefaultLocalEngineWorker()
    snapshot = _attempt_snapshot()
    request = _agent_run_request(snapshot)

    with caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.local_proxy"):
        handle = await worker.accept(snapshot, request)
        await handle.close()

    assert "host.local_proxy.accept" in caplog.text
    assert "message_count=1" in caplog.text
    assert snapshot.run_id in caplog.text
    assert _SECRET_PROMPT not in caplog.text


def test_memory_catchup_logs_cursors_and_counts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """memory catch-up 日志记录 consumer、cursor 与计数。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 日志缺失 cursor / count 字段时抛出。
    """

    with open_host_durable_store(_durable_options(tmp_path)) as store:
        with caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.memory_repair"):
            result = catch_up_conversation_memory_projection(
                store.transaction_runner,
                policy=default_memory_projection_policy(),
                batch_size=8,
            )
            assert result.failures == 0

    assert "host.memory_repair.catch_up.start" in caplog.text
    assert "host.memory_repair.catch_up.committed" in caplog.text
    assert "consumer_id=host.memory.session.v1" in caplog.text
    assert "events_scanned=0" in caplog.text
    assert "finished_cursor=0" in caplog.text


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造 command handle 测试选项。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-logging-test",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _durable_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 durable store 测试选项。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "memory.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def _call_context() -> HostCallContext:
    """构造包含敏感授权声明的调用上下文。

    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="request-log",
        authorization_claims=(
            AuthorizationClaim(name="secret", value=_SECRET_AUTH),
        ),
        operation_context=OperationContext(
            operation_name="logging_test",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="s15",
            correlation_id="corr-log",
        ),
    )


def _attempt_snapshot() -> AttemptDispatchSnapshot:
    """构造 LocalProxy accept 测试快照。

    :returns: Attempt dispatch snapshot。
    """

    return AttemptDispatchSnapshot(
        session_id="session-log",
        run_id="run-log",
        attempt_id="attempt-log",
        execution_id="execution-log",
        dispatch_record_id="dispatch-log",
        execution_target="target-log",
        policy_snapshot_ref="policy-log",
        cancellation_token=_NeverCancelledToken(),
    )


def _agent_run_request(snapshot: AttemptDispatchSnapshot) -> AgentRunRequest:
    """构造 LocalProxy accept 测试请求。

    :param snapshot: Attempt dispatch snapshot。
    :returns: Agent run request。
    """

    return AgentRunRequest(
        run_id=snapshot.run_id,
        session_id=snapshot.session_id,
        messages=(
            SystemMessage(role=AgentMessageRole.SYSTEM, content=_SECRET_PROMPT),
        ),
        disable_tools=True,
        runner_spec=RunnerSpec(
            provider="pytest",
            model="test-model",
            endpoint="https://example.invalid",
            api_key_ref="api-key-ref",
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
        tool_schemas=(),
        tool_executor=NoToolExecutor(),
        cancellation_token=snapshot.cancellation_token,
    )
