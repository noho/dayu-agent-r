"""Host ToolRuntime P6-S5 diagnostic emitter 与 refs 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    DeterministicToolTraceDiagnosticEmitter,
    DuplicateDecisionKind,
    DuplicateGovernancePolicy,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    HostEventRef,
    HostPayloadRef,
    HostToolFactAcceptPort,
    InMemoryToolTraceDiagnosticEmitter,
    NoopToolTraceDiagnosticEmitter,
    ToolAcceptRejectReason,
    ToolAcceptRetryPolicy,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptTimedOut,
    ToolFactAcceptedAck,
    ToolFactKind,
    ToolFactRejectedAck,
    ToolPolicyDecisionKind,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
    ToolTraceDiagnosticRecord,
)
from dayu.host.tool_duplicate_governance import DuplicateGovernanceMessages
from dayu.host.tooling import (
    default_framework_tool_policy_view,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef

_SESSION_ID = "session-diagnostics"
_RUN_ID = "run-diagnostics"
_ATTEMPT_ID = "attempt-diagnostics"
_EXECUTION_ID = "execution-diagnostics"
_ITERATION_ID = "iteration-diagnostics"
_POLICY_DIGEST = "sha256:6666666666666666666666666666666666666666666666666666666666666666"


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


class _CountingTool:
    """返回固定成功结果并记录调用次数的测试工具。"""

    def __init__(self) -> None:
        """初始化测试工具。

        :returns: ``None``。
        """

        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回成功 outcome。

        :param call: 单次工具调用请求。
        :param context: 批式工具上下文。
        :returns: 成功 outcome。
        """

        del call, context
        self.call_count += 1
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"ok": True}, meta=None)
        )


class _ScriptedAcceptPort(HostToolFactAcceptPort):
    """按脚本返回 accept 结果的测试 accept port。"""

    def __init__(self, results: tuple[ToolFactAcceptResult, ...] = ()) -> None:
        """初始化 scripted accept port。

        :param results: 预设 accept 结果。
        :returns: ``None``。
        """

        self._results = results
        self.candidates: list[ToolFactAcceptCandidate] = []
        self.acks: list[ToolFactAcceptedAck] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并返回脚本化结果。

        :param candidate: 工具事实候选。
        :returns: accept 结果。
        """

        self.candidates.append(candidate)
        index = len(self.candidates) - 1
        if index < len(self._results):
            return self._results[index]
        ack = _accepted_ack(candidate)
        self.acks.append(ack)
        return ack


def test_noop_and_in_memory_diagnostic_emitters_return_typed_refs() -> None:
    """no-op 与 in-memory emitter 都返回 typed diagnostic ref。"""

    record = ToolTraceDiagnosticRecord(
        reason_code="duplicate_hint",
        message="duplicate governed",
    )
    noop_ref = NoopToolTraceDiagnosticEmitter().emit(record)
    in_memory = InMemoryToolTraceDiagnosticEmitter()
    memory_ref = in_memory.emit(record)

    assert noop_ref.ref_id == "tool-diagnostic-noop"
    assert memory_ref.ref_id == "tool-diagnostic-memory-1"
    assert in_memory.records == (record,)


def test_deterministic_diagnostic_emitter_rejects_empty_fields() -> None:
    """确定性 diagnostic emitter 拒绝空 reason / message。"""

    emitter = DeterministicToolTraceDiagnosticEmitter()

    with pytest.raises(ValueError, match="reason_code"):
        emitter.emit(ToolTraceDiagnosticRecord(reason_code="", message="message"))
    with pytest.raises(ValueError, match="message"):
        emitter.emit(ToolTraceDiagnosticRecord(reason_code="reason", message=""))


@pytest.mark.asyncio
async def test_candidate_and_ack_carry_duplicate_diagnostic_refs() -> None:
    """duplicate governed candidate 与 accepted ack 携带 diagnostic refs。"""

    configured_action_message = "配置化 hard stop duplicate message"
    configured_diagnostic_message = "配置化 attempt-scope duplicate diagnostic"
    accept_port = _ScriptedAcceptPort()
    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    executor = _executor(
        _CountingTool(),
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.HARD_STOP,
            messages=DuplicateGovernanceMessages(
                hard_stop=configured_action_message,
                attempt_scope_diagnostic=configured_diagnostic_message,
            ),
        ),
        diagnostics,
    )

    result = await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU"}),
            _call("tool-call-2", {"ticker": "DAYU"}),
        )
    )

    governed_candidate = accept_port.candidates[1]
    governed_ack = accept_port.acks[1]
    governed_outcome = result.records[1].outcome
    assert governed_candidate.tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert governed_candidate.policy_decision.message == configured_action_message
    assert isinstance(governed_outcome, ToolFailedOutcome)
    assert governed_outcome.result.message == configured_action_message
    assert governed_candidate.diagnostic_refs
    assert governed_ack.diagnostic_refs == governed_candidate.diagnostic_refs
    assert diagnostics.records[0].reason_code == "duplicate_hard_stop"
    assert diagnostics.records[0].message == configured_diagnostic_message


@pytest.mark.asyncio
async def test_rejected_accept_governed_error_emits_diagnostic_ref() -> None:
    """accept rejected 转成 governed error 时补 diagnostic ref。"""

    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    executor = _executor(
        _CountingTool(),
        _ScriptedAcceptPort(
            (
                ToolFactRejectedAck(
                    reason_code=ToolAcceptRejectReason.EXPLICIT_POLICY_REJECT,
                    message="reject candidate",
                    diagnostic_refs=(),
                    retryable=False,
                ),
            )
        ),
        DuplicateGovernancePolicy(),
        diagnostics,
    )

    outcome = await executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"})))

    assert isinstance(outcome.records[0].outcome, ToolFailedOutcome)
    assert outcome.records[0].outcome.result.error == "tool_accept_rejected"
    assert diagnostics.records[-1].reason_code == "accept_rejected"


@pytest.mark.asyncio
async def test_timeout_governed_error_emits_diagnostic_ref() -> None:
    """accept timeout 转成 governed error 时携带 timeout diagnostic ref。"""

    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    executor = _executor(
        _CountingTool(),
        _ScriptedAcceptPort(
            (
                ToolFactAcceptTimedOut(
                    attempt_count=1,
                    last_error_code="ack_lost",
                    diagnostic_refs=(),
                ),
            )
        ),
        DuplicateGovernancePolicy(),
        diagnostics,
    )

    outcome = await executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"})))

    assert isinstance(outcome.records[0].outcome, ToolFailedOutcome)
    assert outcome.records[0].outcome.result.error == "tool_accept_timeout"
    assert diagnostics.records[-1].reason_code == "accept_timeout"


def _executor(
    tool: _CountingTool,
    accept_port: HostToolFactAcceptPort,
    duplicate_policy: DuplicateGovernancePolicy,
    diagnostic_emitter: InMemoryToolTraceDiagnosticEmitter,
) -> ToolExecutor:
    """构造测试用 ToolRuntime executor。

    :param tool: 测试工具 callable。
    :param accept_port: accept port。
    :param duplicate_policy: duplicate governance 策略。
    :param diagnostic_emitter: 内存诊断 emitter。
    :returns: ToolExecutor protocol 实现。
    """

    return DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(
                    definitions=(_definition("fake_tool", tool),)
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
                allow_tool_calls=True,
            ),
            accept_port=accept_port,
            retry_policy=ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=0.0),
            duplicate_governance_policy=duplicate_policy,
            diagnostic_emitter=diagnostic_emitter,
        )
    ).tool_executor


def _request(*calls: ToolCallRequest) -> BatchToolExecutionRequest:
    """构造批式工具执行请求。

    :param calls: 单次工具调用请求。
    :returns: 批式工具执行请求。
    """

    return BatchToolExecutionRequest(
        calls=calls,
        context=BatchToolExecutionContext(
            run_id=_RUN_ID,
            session_id=_SESSION_ID,
            iteration_id=_ITERATION_ID,
            timeout_seconds=10.0,
            cancellation_token=_OpenCancellationToken(),
            correlation_id="correlation-diagnostics",
        ),
    )


def _call(tool_call_id: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    :param tool_call_id: 工具调用 id。
    :param arguments: 工具参数 JSON object。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name="fake_tool",
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _definition(name: str, tool: _CountingTool) -> ToolDefinition:
    """构造测试工具声明。

    :param name: 工具名。
    :param tool: 测试工具 callable。
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
        callable=tool,
        truncate=None,
        display=None,
        tags=("test",),
    )


def _parameters() -> ToolParametersSchema:
    """构造工具参数 schema。

    :returns: 工具参数 schema。
    """

    properties: dict[str, JsonValue] = {"ticker": {"type": "string"}}
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
        source_id="diagnostics-test",
    )


def _accepted_ack(candidate: ToolFactAcceptCandidate) -> ToolFactAcceptedAck:
    """按 candidate 构造 accepted ack。

    :param candidate: 工具事实候选。
    :returns: accepted ack。
    """

    requested_ref = HostEventRef(
        event_id=f"event-requested-{candidate.tool_call_id}",
        event_sequence=len(candidate.tool_call_id) + 1,
    )
    governed_ref = (
        HostEventRef(
            event_id=f"event-governed-{candidate.tool_call_id}",
            event_sequence=len(candidate.tool_call_id) + 2,
        )
        if candidate.policy_decision.kind is not ToolPolicyDecisionKind.ALLOW
        else None
    )
    result_ref = (
        None
        if candidate.tool_fact_kind is ToolFactKind.REUSE
        else HostEventRef(
            event_id=f"event-result-{candidate.tool_call_id}",
            event_sequence=len(candidate.tool_call_id) + 3,
        )
    )
    accepted_event_refs = tuple(
        ref for ref in (requested_ref, governed_ref, result_ref) if ref is not None
    )
    result_digest = (
        candidate.outcome_digest
        if candidate.outcome_digest is not None
        else candidate.semantic_input_digest
    )
    return ToolFactAcceptedAck(
        accepted_event_refs=accepted_event_refs,
        tool_fact_id=f"tool-fact-{candidate.tool_call_id}",
        tool_call_requested_event_ref=requested_ref,
        tool_call_governed_event_ref=governed_ref,
        tool_result_event_ref=result_ref,
        result_payload_ref=(
            HostPayloadRef("payload-ref", candidate.payload_digest)
            if candidate.payload_digest is not None
            else None
        ),
        result_digest=result_digest,
        reuse_prior_event_refs=candidate.reuse_prior_event_refs,
        diagnostic_refs=candidate.diagnostic_refs,
        idempotency_record_ref=f"idempotency-{candidate.tool_call_id}",
    )
