"""Host Phase 7 waiting integration tests。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    ToolAwaitingOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.host import AttemptStatus, RunStatus, create_host_command_handle, resolve_wait
from dayu.host.api import EnsureSessionRequest, WaitAdapterKey
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    RunRow,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    read_attempt_by_id,
    read_active_wait_records_for_run,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.tool_runtime import (
    DefaultHostToolFactAcceptPort,
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
)
from dayu.host.tooling import (
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    default_framework_tool_policy_view,
)
from dayu.host.wait_adapter import (
    WaitAdapterBinding,
    WaitAdapterRegistry,
    WaitExternalJobRefSource,
)
from dayu.host.waiting import DefaultHostToolAwaitingAcceptPort
from tests.host.test_resolve_wait_command import (
    _SeededWaitingRun,
    _build_resume_request,
    _completed_request,
    _options,
    _read_wait,
    _seed_active_run,
)

_ITERATION_ID = "iteration-phase7-waiting-integration"
_POLICY_DIGEST = "sha256:7777777777777777777777777777777777777777777777777777777777777777"
_RESUME_TOKEN = "external-job-phase7-integration"
_TOOL_NAME = "awaiting_tool"


class _NeverCancelledToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终为 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        """

        return None


class _AwaitingBusinessTool:
    """返回 awaiting outcome 的本地 fake business tool。"""

    def __init__(self) -> None:
        """初始化 fake tool。

        :returns: ``None``。
        """

        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行本地 awaiting 工具。

        :param call: 工具调用请求。
        :param context: 批式工具上下文。
        :returns: awaiting outcome。
        """

        del call, context
        self.call_count += 1
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token=_RESUME_TOKEN,
            ),
            snapshot=None,
        )


def test_phase7_resolve_wait_public_entry_is_importable() -> None:
    """P7 integration 测试集包含 public resolve_wait 入口。"""

    assert resolve_wait.__name__ == "resolve_wait"


def test_local_awaiting_tool_manual_resolve_resumes_run(
    tmp_path: Path,
) -> None:
    """本地 awaiting 工具进入 WAITING 后可通过 manual resolve 恢复 Run。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_active_integration_run(host._transaction_runner())
        tool = _AwaitingBusinessTool()
        tool_runtime = DefaultToolRuntimeFactory(
            EffectiveToolBundleBuilder()
        ).create_tool_runtime(
            ToolRuntimeBuildRequest(
                effective_bundle_request=EffectiveToolBundleBuildRequest(
                    business_tool_bundle=ToolBundle(
                        definitions=(_definition(tool),)
                    ),
                    source_refs=(_source_ref(),),
                    framework_tool_policy=default_framework_tool_policy_view(),
                    policy_snapshot_digest=_POLICY_DIGEST,
                ),
                execution_scope=ToolRuntimeExecutionScope(
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    allow_tool_calls=True,
                ),
                accept_port=DefaultHostToolFactAcceptPort(
                    transaction_runner=host._transaction_runner()
                ),
                awaiting_accept_port=DefaultHostToolAwaitingAcceptPort(
                    transaction_runner=host._transaction_runner()
                ),
                wait_adapter_registry=_wait_adapter_registry(),
            )
        )

        batch = _awaiting_tool_request(seeded)
        outcome = _execute_tool_runtime(tool_runtime.tool_executor, batch)
        wait = _active_wait(host._transaction_runner(), seeded.run_id)
        wait_record = _read_wait(host._transaction_runner(), wait.wait_id)
        run_before_resolve = _run(host._transaction_runner(), seeded.run_id)
        attempt_before_resolve = _attempt_status(
            host._transaction_runner(), seeded.attempt_id
        )
        snapshot = resolve_wait(
            host,
            wait.wait_id,
            _completed_request("phase7-integration-manual-resolve"),
        )
        resume_request = _build_resume_request(
            host._transaction_runner(),
            seeded.session_id,
            snapshot.current_attempt_id,
        )

        assert isinstance(outcome.records[0].outcome, ToolAwaitingOutcome)
        assert tool.call_count == 1
        assert run_before_resolve.status is RunStatus.WAITING
        assert attempt_before_resolve is AttemptStatus.SUSPENDED
        assert wait_record.status is WaitRecordStatus.WAITING
        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id is not None
        assert snapshot.current_attempt_id != seeded.attempt_id
        assert any(
            isinstance(message.content, str)
            and "Accepted wait result fact:" in message.content
            and wait.wait_id in message.content
            for message in resume_request.messages
        )
    finally:
        host.close()


def _seed_active_integration_run(
    transaction_runner: HostTransactionRunner,
) -> _SeededWaitingRun:
    """创建 active Run。

    :param transaction_runner: Host transaction runner。
    :returns: seeded waiting run refs。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="phase7", metadata=()),
    ).snapshot.session_id
    seeded = _SeededWaitingRun(
        session_id=session_id,
        run_id="run-resolve",
        attempt_id="attempt-resolve",
        execution_id="execution-resolve",
        dispatch_record_id="dispatch-resolve",
        wait_id="",
    )
    _seed_active_run(transaction_runner, seeded)
    return seeded


def _awaiting_tool_request(seeded: _SeededWaitingRun) -> BatchToolExecutionRequest:
    """构造 awaiting tool 执行请求。

    :param seeded: seeded Run refs。
    :returns: 批式工具执行请求。
    """

    return BatchToolExecutionRequest(
        calls=(
            ToolCallRequest(
                tool_call_id="tool-call-phase7-awaiting",
                name=_TOOL_NAME,
                arguments={"ticker": "DAYU"},
                index_in_iteration=0,
                provider_state=None,
            ),
        ),
        context=BatchToolExecutionContext(
            run_id=seeded.run_id,
            session_id=seeded.session_id,
            iteration_id=_ITERATION_ID,
            timeout_seconds=10.0,
            cancellation_token=_NeverCancelledToken(),
            correlation_id="phase7-waiting-integration",
        ),
    )


def _execute_tool_runtime(
    tool_executor: ToolExecutor, request: BatchToolExecutionRequest
) -> BatchToolExecutionOutcome:
    """同步执行 ToolRuntime async executor。

    :param tool_executor: ToolRuntimeHandle 暴露的 executor。
    :param request: 批式工具执行请求。
    :returns: 批式工具执行结果。
    """

    return asyncio.run(tool_executor.execute(request))


def _active_wait(
    transaction_runner: HostTransactionRunner, run_id: str
) -> WaitRecordRow:
    """读取 Run 下唯一 active wait。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: active wait record。
    """

    waits = transaction_runner.run_read(
        lambda transaction: read_active_wait_records_for_run(transaction, run_id)
    )
    assert len(waits) == 1
    return waits[0]


def _run(transaction_runner: HostTransactionRunner, run_id: str) -> RunRow:
    """读取 Run row。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run row。
    """

    run = transaction_runner.run_read(
        lambda transaction: read_run_by_id(transaction, run_id)
    )
    assert run is not None
    return run


def _attempt_status(
    transaction_runner: HostTransactionRunner, attempt_id: str
) -> AttemptStatus:
    """读取 Attempt 状态。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: Attempt id。
    :returns: AttemptStatus。
    """

    attempt = transaction_runner.run_read(
        lambda transaction: read_attempt_by_id(transaction, attempt_id)
    )
    assert attempt is not None
    return attempt.status


def _definition(callable_: _AwaitingBusinessTool) -> ToolDefinition:
    """构造 awaiting fake tool definition。

    :param callable_: fake callable。
    :returns: ToolDefinition。
    """

    return ToolDefinition(
        name=_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=_TOOL_NAME,
                description="fake awaiting business tool",
                parameters=ToolParametersSchema(
                    type="object",
                    properties={"ticker": {"type": "string"}},
                    required=("ticker",),
                    additional_properties=False,
                ),
            ),
        ),
        callable=callable_,
        truncate=None,
        display=None,
        tags=("test",),
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造工具来源引用。

    :returns: ToolBundleSourceRef。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="phase7-waiting-integration",
    )


def _wait_adapter_registry() -> WaitAdapterRegistry:
    """构造等待 adapter registry。

    :returns: WaitAdapterRegistry。
    """

    return WaitAdapterRegistry(
        (
            WaitAdapterBinding(
                tool_name=_TOOL_NAME,
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                adapter_key=WaitAdapterKey("poll:phase7-integration"),
                resume_policy=WaitResumePolicy.POLL,
                external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
            ),
        )
    )
