"""Host ToolRuntimeExecutor P6-S3 测试。"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.host.api import WaitAdapterKey
from dayu.host.durable.state import WaitResumePolicy
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    FetchMoreRequest,
    HostEventRef,
    HostPayloadRef,
    HostToolFactAcceptPort,
    HostToolAwaitingAcceptPort,
    InMemoryToolTraceDiagnosticEmitter,
    ToolAcceptRejectReason,
    ToolAcceptRetryPolicy,
    ToolAcceptCall,
    ToolAcceptDiagnostics,
    ToolAcceptGovernance,
    ToolAcceptIdentity,
    ToolAcceptIdempotency,
    ToolAcceptResult,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptTimedOut,
    ToolFactAcceptedAck,
    ToolFactKind,
    ToolFactRejectedAck,
    ToolAwaitingAcceptRejectReason,
    ToolAwaitingAcceptCandidate,
    ToolAwaitingAcceptResult,
    ToolAwaitingAcceptedAck,
    ToolAwaitingAcceptTimedOut,
    ToolAwaitingEventRef,
    ToolAwaitingRejectedAck,
    ToolPolicyDecision,
    ToolPolicyDecisionKind,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
    ToolRuntimePolicyView,
    ToolRuntimeToolPolicy,
    ToolSideEffectKind,
    TruncationManager,
)
from dayu.host.wait_adapter import (
    WaitAdapterBinding,
    WaitAdapterRegistry,
    WaitExternalJobRefSource,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.errors import HostTransactionRetryExhaustedError
from dayu.host.tool_duplicate_governance import (
    DuplicateDurableMissingReason,
    DuplicateGovernanceRequest,
    InMemoryAttemptDuplicateGovernance,
)
from dayu.host.tooling import (
    default_framework_tool_policy_view,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef

_SESSION_ID = "session-toolruntime"
_RUN_ID = "run-toolruntime"
_ATTEMPT_ID = "attempt-toolruntime"
_EXECUTION_ID = "execution-toolruntime"
_ITERATION_ID = "iteration-toolruntime"
_POLICY_DIGEST = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
_DEFAULT_TOOL_TIMEOUT_SECONDS = 10.0
_FAST_TOOL_TIMEOUT_SECONDS = 0.001
_OVERSIZED_INLINE_TEXT_LENGTH = 70010
_OVERSIZED_TRUNCATED_TEXT_LIMIT = 70000


class _OpenCancellationToken:
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


class _AlreadyCancelledToken:
    """测试用已取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终为 ``True``。
        """

        return True

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 测试取消原因。
        """

        return "test_cancel"

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 本测试不关心请求时间，返回 ``None``。
        """

        return None


class _CountingCallable:
    """返回固定成功结果并记录调用次数的 fake 工具。"""

    def __init__(self, value: JsonValue) -> None:
        """初始化 fake callable。

        :param value: 工具成功载荷。
        :returns: ``None``。
        """

        self._value = value
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回固定成功结果。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 工具成功 outcome。
        """

        del call, context
        self.call_count += 1
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value=self._value, meta=None)
        )


class _BlockingCallable:
    """挂起直到被取消的 fake 工具。"""

    def __init__(self) -> None:
        """初始化 fake callable。

        :returns: ``None``。
        """

        self.call_count = 0
        self.cancelled = False
        self._ready = asyncio.Event()

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """等待一个不会主动完成的事件。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 本测试不会正常返回。
        :raises asyncio.CancelledError: ToolRuntime timeout 取消等待时抛出。
        """

        del call, context
        self.call_count += 1
        try:
            await self._ready.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"unexpected": True}, meta=None)
        )


class _AwaitingCallable:
    """返回 awaiting outcome 的 fake 工具。"""

    def __init__(self) -> None:
        """初始化 fake callable。

        :returns: ``None``。
        """

        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回 P6-S3 不支持的 awaiting outcome。

        :param call: 单次工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: awaiting outcome。
        """

        del call, context
        self.call_count += 1
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token="resume-token",
            ),
            snapshot=None,
        )


class _SequencedAcceptPort(HostToolFactAcceptPort):
    """按序返回 accept 结果的 fake accept port。"""

    def __init__(self, results: tuple[ToolFactAcceptResult, ...]) -> None:
        """初始化 fake accept port。

        :param results: 每次 accept 调用返回的结果序列。
        :returns: ``None``。
        """

        self._results = results
        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并返回脚本化结果。

        :param candidate: 工具事实候选。
        :returns: 脚本化 accept 结果。
        """

        self.candidates.append(candidate)
        index = len(self.candidates) - 1
        if index >= len(self._results):
            return _accepted_ack(candidate)
        return self._results[index]


class _RetryExhaustedAcceptPort(HostToolFactAcceptPort):
    """始终模拟 durable transaction busy retry exhausted 的 accept port。"""

    def __init__(self) -> None:
        """初始化 fake accept port。

        :returns: ``None``。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并抛出 transaction retry exhausted。

        :param candidate: 工具事实候选。
        :returns: 本实现不会正常返回。
        :raises HostTransactionRetryExhaustedError: 始终抛出以模拟 SQLite busy。
        """

        self.candidates.append(candidate)
        raise HostTransactionRetryExhaustedError(
            "busy retry exhausted in fake accept port",
            attempts=len(self.candidates),
        )


class _TimeoutAcceptPort(HostToolFactAcceptPort):
    """始终抛出同步 TimeoutError 的 accept port。"""

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """模拟同步 accept port 抛出 TimeoutError。

        :param candidate: 工具事实候选。
        :returns: 不会正常返回。
        :raises TimeoutError: 始终抛出。
        """

        del candidate
        raise TimeoutError("sync timeout should not be caught")


class _AwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """记录 awaiting candidate 并返回 accepted ack 的 fake port。"""

    def __init__(self) -> None:
        """初始化 fake awaiting accept port。

        :returns: ``None``。
        """

        self.candidates: list[ToolAwaitingAcceptCandidate] = []

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """记录 candidate 并返回 accepted ack。

        :param candidate: awaiting candidate。
        :returns: accepted ack。
        """

        self.candidates.append(candidate)
        return ToolAwaitingAcceptedAck(
            accepted_event_refs=(
                ToolAwaitingEventRef(
                    event_id=f"event-tool-awaiting-{candidate.tool_call_id}",
                    event_sequence=1,
                ),
                ToolAwaitingEventRef(
                    event_id=f"event-run-waiting-{candidate.tool_call_id}",
                    event_sequence=2,
                ),
                ToolAwaitingEventRef(
                    event_id=f"event-attempt-suspended-{candidate.tool_call_id}",
                    event_sequence=3,
                ),
            ),
            wait_id=candidate.wait_id,
            tool_awaiting_event_ref=ToolAwaitingEventRef(
                event_id=f"event-tool-awaiting-{candidate.tool_call_id}",
                event_sequence=1,
            ),
            run_waiting_event_ref=ToolAwaitingEventRef(
                event_id=f"event-run-waiting-{candidate.tool_call_id}",
                event_sequence=2,
            ),
            attempt_suspended_event_ref=ToolAwaitingEventRef(
                event_id=f"event-attempt-suspended-{candidate.tool_call_id}",
                event_sequence=3,
            ),
            result_digest=candidate.semantic_input_digest,
            idempotency_record_ref=f"awaiting:{candidate.wait_id}",
        )


class _SequencedAwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """按序返回 awaiting accept 结果的 fake port。"""

    def __init__(self, results: tuple[ToolAwaitingAcceptResult, ...]) -> None:
        """初始化 fake awaiting accept port。

        :param results: 每次 awaiting accept 调用返回的结果序列。
        :returns: ``None``。
        """

        self._results = results
        self.candidates: list[ToolAwaitingAcceptCandidate] = []

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """记录 candidate 并返回脚本化结果。

        :param candidate: awaiting candidate。
        :returns: 脚本化 awaiting accept 结果。
        """

        self.candidates.append(candidate)
        index = len(self.candidates) - 1
        if index >= len(self._results):
            return _AwaitingAcceptPort().accept_tool_awaiting(candidate)
        return self._results[index]


class _RetryExhaustedAwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """始终模拟 awaiting accept 事务重试耗尽的 fake port。"""

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """抛出 Host 事务重试耗尽异常。

        :param candidate: awaiting candidate。
        :returns: 不会正常返回。
        :raises HostTransactionRetryExhaustedError: 始终抛出。
        """

        del candidate
        raise HostTransactionRetryExhaustedError("busy", attempts=1)


class _TimeoutAwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """始终抛出同步 TimeoutError 的 awaiting accept port。"""

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """模拟同步 awaiting accept port 抛出 TimeoutError。

        :param candidate: awaiting candidate。
        :returns: 不会正常返回。
        :raises TimeoutError: 始终抛出。
        """

        del candidate
        raise TimeoutError("sync awaiting timeout should not be caught")


@pytest.mark.asyncio
async def test_fake_tool_result_returns_only_after_accepted_ack() -> None:
    """fake tool 原始结果只有 accepted ack 后才返回给 Engine。"""

    callable_ = _CountingCallable({"secret": "visible-after-accept"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == {"secret": "visible-after-accept"}


@pytest.mark.asyncio
async def test_oversized_tool_result_returns_completed_outcome_without_default_governance() -> None:
    """无显式截断时超大工具结果原样返回给 Engine。"""

    oversized_value = {"content": "x" * 70000}
    callable_ = _CountingCallable(oversized_value)
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(
        callable_,
        accept_port,
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 1
    candidate = accept_port.candidates[0]
    assert candidate.tool_fact_kind is ToolFactKind.COMPLETED
    assert candidate.governance.policy_decision.kind is ToolPolicyDecisionKind.ALLOW
    assert _required_result(candidate).raw_tool_outcome == {
        "kind": "completed",
        "result": {
            "ok": True,
            "value": oversized_value,
            "meta": None,
        },
    }
    assert isinstance(record.outcome, ToolCompletedOutcome)
    assert record.outcome.result.value == oversized_value


def test_fetch_more_returns_oversized_continuation_without_default_inline_limit() -> None:
    """fetch_more 不再复用 durable payload inline 阈值拒绝 continuation。"""

    spec = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": 1},
        target_field=None,
        field_path=None,
        ttl_seconds=None,
    )
    manager = TruncationManager(
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        truncate_specs_by_name={"fake_tool": spec},
    )
    applied = manager.apply_truncation(
        "fake_tool",
        "tool-call-1",
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value="x" * _OVERSIZED_INLINE_TEXT_LENGTH,
                meta=None,
            )
        ),
        spec,
    )
    assert applied.cursor_hint is not None
    assert isinstance(applied.outcome, ToolCompletedOutcome)
    truncated_value = applied.outcome.result.value
    assert isinstance(truncated_value, dict)
    fetch_more = truncated_value["fetch_more"]
    assert isinstance(fetch_more, dict)
    scope_token = fetch_more["scope_token"]
    assert isinstance(scope_token, str)

    fetched = manager.fetch_more(
        FetchMoreRequest(
            cursor=applied.cursor_hint,
            scope_token=scope_token,
            limit=None,
        ),
        _request(_call("tool-call-1")).context,
    )

    assert isinstance(fetched, ToolCompletedOutcome)
    assert fetched.result.value == "x" * (_OVERSIZED_INLINE_TEXT_LENGTH - 1)


def test_truncation_keeps_cursor_when_visible_result_is_large_by_explicit_spec() -> None:
    """显式截断 spec 的大可见结果不再被默认 inline 阈值二次拒绝。"""

    spec = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": _OVERSIZED_TRUNCATED_TEXT_LIMIT},
        target_field=None,
        field_path=None,
        ttl_seconds=None,
    )
    manager = TruncationManager(
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        truncate_specs_by_name={"fake_tool": spec},
    )

    applied = manager.apply_truncation(
        "fake_tool",
        "tool-call-1",
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value="x" * _OVERSIZED_INLINE_TEXT_LENGTH,
                meta=None,
            )
        ),
        spec,
    )

    assert isinstance(applied.outcome, ToolCompletedOutcome)
    assert applied.cursor_hint is not None
    assert applied.cursor_hint in manager._cursors


@pytest.mark.asyncio
async def test_accept_rejected_does_not_expose_raw_fake_result() -> None:
    """accepted ack 被拒绝时不向 Engine 暴露原始 fake result。"""

    callable_ = _CountingCallable({"secret": "must-not-leak"})
    accept_port = _SequencedAcceptPort(
        (
            ToolFactRejectedAck(
                reason_code=ToolAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                message="reject fake result",
                diagnostic_refs=(),
                retryable=False,
            ),
        )
    )
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_accept_rejected"
    assert "must-not-leak" not in record.outcome.result.message


@pytest.mark.asyncio
async def test_accept_timeout_bounded_retry_returns_governed_error() -> None:
    """accept timeout 只有限重试，耗尽后返回 governed error。"""

    callable_ = _CountingCallable({"secret": "timeout-raw"})
    accept_port = _SequencedAcceptPort(
        (
            ToolFactAcceptTimedOut(
                attempt_count=1,
                last_error_code="ack_lost",
                diagnostic_refs=(),
            ),
            ToolFactAcceptTimedOut(
                attempt_count=2,
                last_error_code="ack_lost",
                diagnostic_refs=(),
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        retry_policy=ToolAcceptRetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 2
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_accept_timeout"
    assert "timeout-raw" not in record.outcome.result.message


@pytest.mark.asyncio
async def test_accept_retry_exhausted_returns_governed_timeout() -> None:
    """durable transaction retry exhausted 被治理成 accept timeout。"""

    callable_ = _CountingCallable({"secret": "retry-exhausted-raw"})
    accept_port = _RetryExhaustedAcceptPort()
    executor = _executor(
        callable_,
        accept_port,
        retry_policy=ToolAcceptRetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert len(accept_port.candidates) == 2
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_accept_timeout"
    assert "retry-exhausted-raw" not in record.outcome.result.message


@pytest.mark.asyncio
async def test_sync_timeout_error_from_accept_port_is_not_caught() -> None:
    """同步 accept port 的 TimeoutError 不应被误分类为 retry timeout。"""

    callable_ = _CountingCallable({"secret": "timeout-error"})
    executor = _executor(callable_, _TimeoutAcceptPort())

    with pytest.raises(TimeoutError, match="sync timeout"):
        await executor.execute(_request(_call("tool-call-1")))


@pytest.mark.asyncio
async def test_duplicate_cleanup_failure_does_not_replace_tool_timeout_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """duplicate cleanup 失败不覆盖工具 timeout 返回结果。"""

    async def _raise_cleanup_failure(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """模拟 duplicate cleanup 失败。

        :param self: duplicate governance 实例。
        :param request: cleanup 请求。
        :param reason: durable missing 原因。
        :returns: ``None``。
        :raises RuntimeError: 始终抛出 cleanup 失败。
        """

        del self, request, reason
        raise RuntimeError("duplicate cleanup failed")

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _raise_cleanup_failure,
    )
    callable_ = _BlockingCallable()
    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    executor = _executor(
        callable_,
        _SequencedAcceptPort(()),
        diagnostic_emitter=diagnostics,
    )

    outcome = await executor.execute(
        _request(_call("tool-call-1"), timeout_seconds=_FAST_TOOL_TIMEOUT_SECONDS)
    )

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_call_governed"
    assert record.outcome.result.hint == "tool_runtime_timeout"
    assert diagnostics.records[-1].reason_code == "duplicate_cleanup_failed"


@pytest.mark.asyncio
async def test_duplicate_cleanup_failure_does_not_replace_original_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """duplicate cleanup 失败不覆盖 try 块原始异常。"""

    async def _raise_cleanup_failure(
        self: InMemoryAttemptDuplicateGovernance,
        request: DuplicateGovernanceRequest,
        reason: DuplicateDurableMissingReason,
    ) -> None:
        """模拟 duplicate cleanup 失败。

        :param self: duplicate governance 实例。
        :param request: cleanup 请求。
        :param reason: durable missing 原因。
        :returns: ``None``。
        :raises RuntimeError: 始终抛出 cleanup 失败。
        """

        del self, request, reason
        raise RuntimeError("duplicate cleanup failed")

    monkeypatch.setattr(
        InMemoryAttemptDuplicateGovernance,
        "record_durable_missing",
        _raise_cleanup_failure,
    )
    callable_ = _CountingCallable({"secret": "timeout-error"})
    executor = _executor(callable_, _TimeoutAcceptPort())

    with pytest.raises(TimeoutError, match="sync timeout"):
        await executor.execute(_request(_call("tool-call-1")))


@pytest.mark.asyncio
async def test_side_effect_tool_missing_idempotency_key_never_calls_callable() -> None:
    """side-effect 工具缺少必需幂等 key 时不得调用 callable。"""

    callable_ = _CountingCallable({"secret": "side-effect"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    policy_view = ToolRuntimePolicyView(
        rules_by_tool_name={
            "fake_tool": ToolRuntimeToolPolicy(
                side_effect_kind=ToolSideEffectKind.SIDE_EFFECT,
                idempotency_key_argument_name="tool_idempotency_key",
            )
        }
    )
    executor = _executor(callable_, accept_port, policy_view=policy_view)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert accept_port.candidates[0].tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_idempotency_key_required"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)


@pytest.mark.asyncio
async def test_tool_runtime_timeout_returns_governed_failure() -> None:
    """业务工具超过批级 timeout 时返回受治理失败且取消底层 task。"""

    callable_ = _BlockingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(
        _request(_call("tool-call-1"), timeout_seconds=_FAST_TOOL_TIMEOUT_SECONDS)
    )

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert callable_.cancelled
    assert len(accept_port.candidates) == 1
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_runtime_timeout"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_call_governed"
    assert record.outcome.result.hint == "tool_runtime_timeout"


@pytest.mark.asyncio
async def test_tool_runtime_pre_cancelled_context_returns_governed_failure() -> None:
    """context token 已取消时不得调用业务工具，并返回受治理失败。"""

    callable_ = _CountingCallable({"secret": "must-not-run"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(
        _request(_call("tool-call-1"), cancellation_token=_AlreadyCancelledToken())
    )

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert len(accept_port.candidates) == 1
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_runtime_cancelled"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_call_governed"
    assert record.outcome.result.hint == "tool_runtime_cancelled"
    assert "must-not-run" not in record.outcome.result.message


@pytest.mark.asyncio
async def test_awaiting_outcome_returns_only_after_awaiting_accepted_ack() -> None:
    """awaiting outcome 只有 Host awaiting accepted ack 后才返回给 Engine。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert accept_port.candidates == []
    assert len(awaiting_accept_port.candidates) == 1
    assert isinstance(record.outcome, ToolAwaitingOutcome)
    assert awaiting_accept_port.candidates[0].external_job_ref is not None
    assert awaiting_accept_port.candidates[0].external_job_ref.external_job_id == (
        "resume-token"
    )


@pytest.mark.asyncio
async def test_awaiting_outcome_without_adapter_binding_is_governed_error() -> None:
    """缺少 Host adapter binding 时 awaiting outcome 不进入普通 accept。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 1
    assert accept_port.candidates == []
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "awaiting_adapter_not_configured"


@pytest.mark.asyncio
async def test_awaiting_accept_rejected_returns_governed_error() -> None:
    """awaiting accept rejected ack 不向 Engine 暴露 awaiting outcome。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _SequencedAwaitingAcceptPort(
        (
            ToolAwaitingRejectedAck(
                reason_code=ToolAwaitingAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                message="awaiting conflict",
                retryable=False,
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_awaiting_accept_rejected"
    assert record.outcome.result.hint == "accept_rejected:idempotency_conflict"


@pytest.mark.asyncio
async def test_awaiting_accept_timeout_returns_governed_error() -> None:
    """awaiting accept timeout 不向 Engine 暴露 awaiting outcome。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _SequencedAwaitingAcceptPort(
        (
            ToolAwaitingAcceptTimedOut(
                attempt_count=1,
                last_error_code="accept_ack_lost",
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_awaiting_accept_timeout"
    assert record.outcome.result.hint is not None
    assert record.outcome.result.hint.startswith("accept_ack_lost;diagnostic_refs=")
    assert "tool-diagnostic-" in record.outcome.result.hint


@pytest.mark.asyncio
async def test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref() -> None:
    """awaiting accept retry 耗尽时最终失败 outcome 携带诊断引用。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _RetryExhaustedAwaitingAcceptPort()
    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry(),
        diagnostic_emitter=diagnostics,
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.error == "tool_awaiting_accept_timeout"
    assert (
        record.outcome.result.hint
        == "accept_ack_lost;diagnostic_refs=tool-diagnostic-memory-1"
    )
    assert len(diagnostics.records) == 1
    assert diagnostics.records[0].reason_code == "accept_timeout"


@pytest.mark.asyncio
async def test_sync_timeout_error_from_awaiting_accept_port_is_not_caught() -> None:
    """同步 awaiting accept port 的 TimeoutError 不应被误分类为 retry timeout。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=_TimeoutAwaitingAcceptPort(),
        wait_adapter_registry=_wait_adapter_registry(),
    )

    with pytest.raises(TimeoutError, match="sync awaiting timeout"):
        await executor.execute(_request(_call("tool-call-1")))


@pytest.mark.asyncio
async def test_poll_awaiting_without_external_job_ref_is_governed_error() -> None:
    """POLL binding 未派生 external_job_ref 时返回受治理错误。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    awaiting_accept_port = _AwaitingAcceptPort()
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=awaiting_accept_port,
        wait_adapter_registry=_wait_adapter_registry_without_external_job_ref(),
    )

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert awaiting_accept_port.candidates == []
    assert isinstance(record.outcome, ToolFailedOutcome)
    assert record.outcome.result.hint == "awaiting_external_job_missing"


@pytest.mark.asyncio
async def test_awaiting_outcome_stops_remaining_batch_calls() -> None:
    """批内首个 awaiting accepted 后不得继续调用后续业务工具。"""

    callable_ = _AwaitingCallable()
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(
        callable_,
        accept_port,
        awaiting_accept_port=_AwaitingAcceptPort(),
        wait_adapter_registry=_wait_adapter_registry(),
    )

    outcome = await executor.execute(
        _request(_call("tool-call-1"), _call("tool-call-2"))
    )

    first, second = (record.outcome for record in outcome.records)
    assert callable_.call_count == 1
    assert isinstance(first, ToolAwaitingOutcome)
    assert isinstance(second, ToolFailedOutcome)
    assert second.result.hint == "run_suspended_by_tool_awaiting"


@pytest.mark.asyncio
async def test_no_tool_scope_rejects_model_tool_call() -> None:
    """replay/no-tool scope 下即使模型发起工具调用也必须拒绝。"""

    callable_ = _CountingCallable({"secret": "no-tool"})
    accept_port = _SequencedAcceptPort((_accepted_ack_for_call("tool-call-1"),))
    executor = _executor(callable_, accept_port, allow_tool_calls=False)

    outcome = await executor.execute(_request(_call("tool-call-1")))

    record = outcome.records[0]
    assert callable_.call_count == 0
    assert accept_port.candidates[0].tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_call_not_allowed_in_scope"
    )
    assert isinstance(record.outcome, ToolFailedOutcome)


@pytest.mark.asyncio
async def test_batch_mixed_accept_outcomes_keep_accepted_visible() -> None:
    """批内 accepted call 可见，rejected / timeout call 只返回 governed error。"""

    callable_ = _CountingCallable({"accepted": True})
    accept_port = _SequencedAcceptPort(
        (
            _accepted_ack_for_call("tool-call-1"),
            ToolFactRejectedAck(
                reason_code=ToolAcceptRejectReason.EXPLICIT_POLICY_REJECT,
                message="reject second",
                diagnostic_refs=(),
                retryable=False,
            ),
            ToolFactAcceptTimedOut(
                attempt_count=1,
                last_error_code="ack_lost",
                diagnostic_refs=(),
            ),
        )
    )
    executor = _executor(
        callable_,
        accept_port,
        retry_policy=ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )

    outcome = await executor.execute(
        _request(
            _call("tool-call-1", ticker="DAYU-1"),
            _call("tool-call-2", ticker="DAYU-2"),
            _call("tool-call-3", ticker="DAYU-3"),
        )
    )

    first, second, third = (record.outcome for record in outcome.records)
    assert callable_.call_count == 3
    assert isinstance(first, ToolCompletedOutcome)
    assert first.result.value == {"accepted": True}
    assert isinstance(second, ToolFailedOutcome)
    assert second.result.error == "tool_accept_rejected"
    assert isinstance(third, ToolFailedOutcome)
    assert third.result.error == "tool_accept_timeout"


def _executor(
    callable_: _CountingCallable | _AwaitingCallable | _BlockingCallable,
    accept_port: HostToolFactAcceptPort,
    *,
    awaiting_accept_port: HostToolAwaitingAcceptPort | None = None,
    wait_adapter_registry: WaitAdapterRegistry | None = None,
    retry_policy: ToolAcceptRetryPolicy | None = None,
    policy_view: ToolRuntimePolicyView | None = None,
    allow_tool_calls: bool = True,
    diagnostic_emitter: InMemoryToolTraceDiagnosticEmitter | None = None,
) -> ToolExecutor:
    """构造测试用 ToolRuntime executor。

    :param callable_: fake 工具 callable。
    :param accept_port: fake accept port。
    :param awaiting_accept_port: fake awaiting accept port。
    :param wait_adapter_registry: wait adapter registry。
    :param retry_policy: accept retry policy。
    :param policy_view: Host 内部工具 policy view。
    :param allow_tool_calls: ToolRuntime scope 是否允许工具调用。
    :param diagnostic_emitter: 可选内存诊断发射器。
    :returns: ToolExecutor protocol 实现。
    """

    handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_definition("fake_tool", callable_),)
                ),
                source_refs=(_source_ref(),),
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest=_POLICY_DIGEST,
            ),
            execution_scope=ToolRuntimeExecutionScope(
                session_id=_SESSION_ID,
                run_id=_RUN_ID,
                attempt_id=_ATTEMPT_ID,
                execution_id=_EXECUTION_ID,
                allow_tool_calls=allow_tool_calls,
            ),
            accept_port=accept_port,
            awaiting_accept_port=awaiting_accept_port,
            wait_adapter_registry=wait_adapter_registry,
            retry_policy=(
                retry_policy
                if retry_policy is not None
                else ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=0.0)
            ),
            policy_view=policy_view if policy_view is not None else ToolRuntimePolicyView(),
            diagnostic_emitter=diagnostic_emitter,
        )
    )
    return handle.tool_executor


def _request(
    *calls: ToolCallRequest,
    timeout_seconds: float | None = _DEFAULT_TOOL_TIMEOUT_SECONDS,
    cancellation_token: CancellationToken | None = None,
) -> BatchToolExecutionRequest:
    """构造批式工具执行请求。

    :param calls: 单次工具调用请求。
    :param timeout_seconds: 批式工具执行 timeout。
    :param cancellation_token: 批式工具执行 cancellation token。
    :returns: 批式工具执行请求。
    """

    return BatchToolExecutionRequest(
        calls=calls,
        context=BatchToolExecutionContext(
            run_id=_RUN_ID,
            session_id=_SESSION_ID,
            iteration_id=_ITERATION_ID,
            timeout_seconds=timeout_seconds,
            cancellation_token=(
                cancellation_token
                if cancellation_token is not None
                else _OpenCancellationToken()
            ),
            correlation_id="correlation-toolruntime",
        ),
    )


def _call(tool_call_id: str, *, ticker: str = "DAYU") -> ToolCallRequest:
    """构造 fake 工具调用。

    :param tool_call_id: 工具调用 id。
    :param ticker: fake ticker 参数。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name="fake_tool",
        arguments={"ticker": ticker},
        index_in_iteration=0,
        provider_state=None,
    )


def _definition(
    name: str, callable_: _CountingCallable | _AwaitingCallable | _BlockingCallable
) -> ToolDefinition:
    """构造工具声明。

    :param name: 工具名。
    :param callable_: 工具 callable。
    :returns: 工具声明。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description="fake tool",
                parameters=_parameters(),
            ),
        ),
        callable=callable_,
        truncate=None,
        display=None,
        tags=("test",),
    )


def _parameters() -> ToolParametersSchema:
    """构造工具参数 schema。

    :returns: 参数 schema。
    """

    properties: dict[str, JsonValue] = {
        "ticker": {"type": "string"},
        "tool_idempotency_key": {"type": "string"},
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造工具来源引用。

    :returns: ToolBundleSourceRef。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="toolruntime-test",
    )


def _wait_adapter_registry() -> WaitAdapterRegistry:
    """构造测试用 wait adapter registry。

    :returns: wait adapter registry。
    """

    return WaitAdapterRegistry(
        (
            WaitAdapterBinding(
                tool_name="fake_tool",
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                adapter_key=WaitAdapterKey("poll:fake-tool"),
                resume_policy=WaitResumePolicy.POLL,
                external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
            ),
        )
    )


def _wait_adapter_registry_without_external_job_ref() -> WaitAdapterRegistry:
    """构造不会派生 external job ref 的 poll registry。

    :returns: wait adapter registry。
    """

    return WaitAdapterRegistry(
        (
            WaitAdapterBinding(
                tool_name="fake_tool",
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                adapter_key=WaitAdapterKey("poll:fake-tool"),
                resume_policy=WaitResumePolicy.POLL,
                external_job_ref_source=WaitExternalJobRefSource.NONE,
            ),
        )
    )


def _accepted_ack_for_call(tool_call_id: str) -> ToolFactAcceptedAck:
    """构造 accepted ack。

    :param tool_call_id: 工具调用 id。
    :returns: accepted ack。
    """

    candidate = ToolFactAcceptCandidate(
        identity=ToolAcceptIdentity(
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            attempt_id=_ATTEMPT_ID,
            execution_id=_EXECUTION_ID,
        ),
        call=ToolAcceptCall(
            iteration_id=_ITERATION_ID,
            tool_call_id=tool_call_id,
            tool_name="fake_tool",
            tool_schema_digest=sha256_digest_json({"schema": tool_call_id}),
            tool_identity_digest=sha256_digest_json({"identity": tool_call_id}),
            normalized_arguments_digest=sha256_digest_json(
                {"arguments": tool_call_id}
            ),
        ),
        tool_fact_kind=ToolFactKind.COMPLETED,
        result=ToolAcceptResult(
            outcome_digest=sha256_digest_json({"outcome": tool_call_id}),
            payload_digest=sha256_digest_json({"payload": tool_call_id}),
            payload_ref=None,
            truncation=None,
            raw_tool_outcome={
                "kind": "completed",
                "result": {
                    "ok": True,
                    "value": {"tool_call_id": tool_call_id},
                    "meta": None,
                },
            },
            tool_timing={
                "schema_version": 1,
                "status": "missing_tool_result_meta",
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
                "duration_source": None,
            },
        ),
        governance=ToolAcceptGovernance(
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.ALLOW,
                reason_code=None,
                message=None,
            ),
            tool_idempotency_key=None,
            duplicate=None,
        ),
        idempotency=ToolAcceptIdempotency(
            accept_idempotency_key=f"accept-{tool_call_id}",
            semantic_input_digest=sha256_digest_json({"semantic": tool_call_id}),
        ),
        diagnostics=ToolAcceptDiagnostics(diagnostic_refs=()),
    )
    return _accepted_ack(candidate)


def _accepted_ack(candidate: ToolFactAcceptCandidate) -> ToolFactAcceptedAck:
    """按 candidate 构造 accepted ack。

    :param candidate: 工具事实候选。
    :returns: accepted ack。
    """

    requested_ref = HostEventRef(
        event_id=f"event-requested-{candidate.call.tool_call_id}",
        event_sequence=1,
    )
    result_ref = HostEventRef(
        event_id=f"event-result-{candidate.call.tool_call_id}",
        event_sequence=2,
    )
    result = candidate.result
    result_digest = (
        result.outcome_digest
        if result is not None
        else candidate.idempotency.semantic_input_digest
    )
    result_payload_ref = (
        HostPayloadRef("payload-ref", result.payload_digest)
        if result is not None and result.payload_digest is not None
        else None
    )
    return ToolFactAcceptedAck(
        accepted_event_refs=(requested_ref, result_ref),
        tool_fact_id=f"tool-fact-{candidate.call.tool_call_id}",
        tool_call_requested_event_ref=requested_ref,
        tool_call_governed_event_ref=None,
        tool_result_event_ref=result_ref,
        result_payload_ref=result_payload_ref,
        result_digest=result_digest,
        reuse_prior_event_refs=(),
        diagnostic_refs=(),
        idempotency_record_ref=f"idempotency-{candidate.call.tool_call_id}",
    )


def _required_result(candidate: ToolFactAcceptCandidate) -> ToolAcceptResult:
    """读取必须存在的 result 子结构。

    :param candidate: 工具事实候选。
    :returns: result 子结构。
    :raises AssertionError: candidate 未携带 result 时抛出。
    """

    assert candidate.result is not None
    return candidate.result
