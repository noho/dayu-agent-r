"""Host ToolRuntime P6-S5 run-local duplicate governance 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
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
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    DuplicateDecisionKind,
    DuplicateGovernancePolicy,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    HostEventRef,
    HostPayloadRef,
    HostToolFactAcceptPort,
    InMemoryRunScopedDuplicateGovernanceRegistry,
    InMemoryToolTraceDiagnosticEmitter,
    ToolAcceptRetryPolicy,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptedAck,
    ToolFactKind,
    ToolPolicyDecision,
    ToolPolicyDecisionKind,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
    ToolRuntimePolicyView,
)
from dayu.host.tooling import (
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    default_framework_tool_policy_view,
)

_SESSION_ID = "session-duplicate"
_RUN_ID = "run-duplicate"
_ATTEMPT_ID = "attempt-duplicate"
_EXECUTION_ID = "execution-duplicate"
_ITERATION_ID = "iteration-duplicate"
_POLICY_DIGEST = "sha256:5555555555555555555555555555555555555555555555555555555555555555"


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


class _CountingTool:
    """返回固定成功结果并记录调用次数的测试工具。"""

    def __init__(self, value: JsonValue) -> None:
        """初始化测试工具。

        :param value: 工具返回值。
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
        :param context: 批式工具上下文。
        :returns: 成功 outcome。
        """

        del call, context
        self.call_count += 1
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value=self._value, meta=None)
        )


class _AcceptingPort(HostToolFactAcceptPort):
    """记录 candidate 并始终 accepted 的测试 accept port。"""

    def __init__(self) -> None:
        """初始化测试 accept port。

        :returns: ``None``。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []
        self.acks: list[ToolFactAcceptedAck] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并返回 accepted ack。

        :param candidate: 工具事实候选。
        :returns: accepted ack。
        """

        self.candidates.append(candidate)
        ack = _accepted_ack(candidate)
        self.acks.append(ack)
        return ack


@pytest.mark.asyncio
async def test_duplicate_key_normalizes_arguments_deterministically() -> None:
    """参数顺序不同但语义相同时命中同一个 duplicate key。"""

    tool = _CountingTool({"accepted": "first"})
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    outcome = await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU", "year": 2026}, index=0),
            _call("tool-call-2", {"year": 2026, "ticker": "DAYU"}, index=1),
        )
    )

    assert tool.call_count == 1
    assert isinstance(outcome.records[1].outcome, ToolCompletedOutcome)
    assert accept_port.candidates[0].normalized_arguments_digest == (
        accept_port.candidates[1].normalized_arguments_digest
    )
    assert accept_port.candidates[0].duplicate_key == (
        accept_port.candidates[1].duplicate_key
    )
    assert accept_port.candidates[1].tool_fact_kind is ToolFactKind.REUSE


@pytest.mark.asyncio
async def test_duplicate_key_excludes_index_in_iteration() -> None:
    """同 iteration 不同 index 的同工具同参数仍进入 duplicate governance。"""

    tool = _CountingTool({"accepted": "first"})
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU"}, index=0),
            _call("tool-call-2", {"ticker": "DAYU"}, index=9),
        )
    )

    assert tool.call_count == 1
    assert accept_port.candidates[1].tool_fact_kind is ToolFactKind.REUSE
    assert accept_port.candidates[1].duplicate_decision is DuplicateDecisionKind.REUSE
    assert accept_port.candidates[1].reuse_prior_event_refs


@pytest.mark.asyncio
async def test_allow_duplicate_decision_executes_and_accepts_each_call() -> None:
    """默认 allow 策略下重复调用仍执行并各自进入 accept path。"""

    tool = _CountingTool({"accepted": True})
    accept_port = _AcceptingPort()
    executor = _executor(tool, accept_port, DuplicateGovernancePolicy())

    await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU"}, index=0),
            _call("tool-call-2", {"ticker": "DAYU"}, index=1),
        )
    )

    assert tool.call_count == 2
    assert [candidate.tool_fact_kind for candidate in accept_port.candidates] == [
        ToolFactKind.COMPLETED,
        ToolFactKind.COMPLETED,
    ]
    assert all(
        candidate.duplicate_decision is DuplicateDecisionKind.ALLOW
        for candidate in accept_port.candidates
    )


@pytest.mark.asyncio
async def test_reuse_references_prior_refs_without_second_result_fact() -> None:
    """reuse 不调用 callable，并只接受 governance event 引用 prior refs。"""

    tool = _CountingTool({"accepted": "prior"})
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    outcome = await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU"}, index=0),
            _call("tool-call-2", {"ticker": "DAYU"}, index=1),
        )
    )

    reuse_candidate = accept_port.candidates[1]
    reuse_ack = accept_port.acks[1]
    assert tool.call_count == 1
    assert isinstance(outcome.records[1].outcome, ToolCompletedOutcome)
    assert outcome.records[1].outcome.result.value == {"accepted": "prior"}
    assert reuse_candidate.tool_fact_kind is ToolFactKind.REUSE
    assert reuse_candidate.reuse_prior_event_refs == (
        accept_port.acks[0].accepted_event_refs
    )
    assert reuse_ack.tool_result_event_ref is None


@pytest.mark.parametrize(
    ("decision", "expected_policy"),
    (
        (DuplicateDecisionKind.HINT, ToolPolicyDecisionKind.HINT),
        (
            DuplicateDecisionKind.REQUIRE_JUSTIFICATION,
            ToolPolicyDecisionKind.REQUIRE_JUSTIFICATION,
        ),
        (DuplicateDecisionKind.HARD_STOP, ToolPolicyDecisionKind.HARD_STOP),
    ),
)
@pytest.mark.asyncio
async def test_duplicate_governed_matrix_produces_diagnostics(
    decision: DuplicateDecisionKind, expected_policy: ToolPolicyDecisionKind
) -> None:
    """hint / require_justification / hard_stop 产生 governed fact 与诊断 refs。"""

    tool = _CountingTool({"accepted": "prior"})
    accept_port = _AcceptingPort()
    diagnostics = InMemoryToolTraceDiagnosticEmitter()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=decision,
            justification_argument_names_by_tool_name={
                "fake_tool": "duplicate_justification"
            },
        ),
        diagnostic_emitter=diagnostics,
    )

    await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU"}, index=0),
            _call("tool-call-2", {"ticker": "DAYU"}, index=1),
        )
    )

    governed_candidate = accept_port.candidates[1]
    assert tool.call_count == 1
    assert governed_candidate.tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert governed_candidate.policy_decision.kind is expected_policy
    assert governed_candidate.diagnostic_refs
    assert governed_candidate.reuse_prior_event_refs
    assert len(diagnostics.records) == 1


@pytest.mark.asyncio
async def test_governed_duplicate_candidate_validation_rejects_missing_prior_refs() -> None:
    """duplicate governed_error candidate 必须携带 prior accepted refs。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HINT
    )

    with pytest.raises(ValueError, match="requires prior event refs"):
        replace(governed_candidate, reuse_prior_event_refs=())


@pytest.mark.asyncio
async def test_governed_duplicate_candidate_validation_rejects_policy_mismatch() -> None:
    """duplicate governed_error candidate 的 policy kind 必须匹配决策类别。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HINT
    )

    with pytest.raises(ValueError, match="policy kind must match decision"):
        replace(
            governed_candidate,
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.HARD_STOP,
                reason_code="duplicate_hint",
                message=(
                    "duplicate tool call should use prior accepted result "
                    "or change evidence scope"
                ),
            ),
        )


@pytest.mark.asyncio
async def test_governed_duplicate_candidate_validation_rejects_reason_mismatch() -> None:
    """duplicate governed_error candidate 的 reason 必须匹配决策类别。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HARD_STOP
    )

    with pytest.raises(ValueError, match="reason must match decision"):
        replace(
            governed_candidate,
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.HARD_STOP,
                reason_code="duplicate_hint",
                message="duplicate tool call hard-stopped by Host governance",
            ),
        )


@pytest.mark.asyncio
async def test_governed_duplicate_candidate_validation_rejects_message_mismatch() -> None:
    """duplicate governed_error candidate 的 message 必须匹配决策类别。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.REQUIRE_JUSTIFICATION
    )

    with pytest.raises(ValueError, match="message must match decision"):
        replace(
            governed_candidate,
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.REQUIRE_JUSTIFICATION,
                reason_code="duplicate_requires_justification",
                message="wrong duplicate governance message",
            ),
        )


@pytest.mark.asyncio
async def test_governed_error_candidate_validation_rejects_allow_policy() -> None:
    """governed_error fact 不允许携带 allow policy。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HINT
    )

    with pytest.raises(ValueError, match="requires governed policy decision"):
        replace(
            governed_candidate,
            duplicate_decision=None,
            reuse_prior_event_refs=(),
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.ALLOW,
                reason_code=None,
                message=None,
            ),
        )


@pytest.mark.asyncio
async def test_require_justification_with_valid_argument_allows_execution() -> None:
    """require_justification 命中且已有结构化说明时允许执行。"""

    tool = _CountingTool({"accepted": True})
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REQUIRE_JUSTIFICATION,
            justification_argument_names_by_tool_name={
                "fake_tool": "duplicate_justification"
            },
        ),
    )
    arguments: dict[str, JsonValue] = {
        "ticker": "DAYU",
        "duplicate_justification": "need a fresh check",
    }

    await executor.execute(
        _request(
            _call("tool-call-1", arguments, index=0),
            _call("tool-call-2", arguments, index=1),
        )
    )

    assert tool.call_count == 2
    assert accept_port.candidates[1].tool_fact_kind is ToolFactKind.COMPLETED
    assert accept_port.candidates[1].duplicate_decision is DuplicateDecisionKind.ALLOW


@pytest.mark.asyncio
async def test_require_justification_without_argument_binding_downgrades_to_hint() -> None:
    """未配置 justification 参数名时 require_justification 降级为 hint。"""

    tool = _CountingTool({"accepted": True})
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REQUIRE_JUSTIFICATION
        ),
    )

    await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU"}, index=0),
            _call("tool-call-2", {"ticker": "DAYU"}, index=1),
        )
    )

    assert tool.call_count == 1
    assert accept_port.candidates[1].tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert accept_port.candidates[1].duplicate_decision is DuplicateDecisionKind.HINT
    assert accept_port.candidates[1].policy_decision.kind is ToolPolicyDecisionKind.HINT


@pytest.mark.asyncio
async def test_governed_duplicate_does_not_overwrite_prior_successful_reuse_source() -> None:
    """governed_error accepted 不得覆盖 duplicate index 中的成功 outcome。"""

    tool = _CountingTool({"accepted": "prior-success"})
    accept_port = _AcceptingPort()
    decisions_by_tool_name: dict[str, DuplicateDecisionKind] = {
        "fake_tool": DuplicateDecisionKind.HINT
    }
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(decisions_by_tool_name=decisions_by_tool_name),
    )

    await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU"}, index=0),
            _call("tool-call-2", {"ticker": "DAYU"}, index=1),
        )
    )
    decisions_by_tool_name["fake_tool"] = DuplicateDecisionKind.REUSE
    outcome = await executor.execute(
        _request(_call("tool-call-3", {"ticker": "DAYU"}, index=2))
    )

    reused = outcome.records[0].outcome
    assert tool.call_count == 1
    assert accept_port.candidates[1].tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert accept_port.candidates[2].tool_fact_kind is ToolFactKind.REUSE
    assert isinstance(reused, ToolCompletedOutcome)
    assert reused.result.value == {"accepted": "prior-success"}


@pytest.mark.asyncio
async def test_plain_policy_rejection_does_not_carry_duplicate_prior_refs() -> None:
    """普通 policy rejection 不携带 unrelated duplicate prior refs。"""

    tool = _CountingTool({"accepted": True})
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.HARD_STOP
        ),
    )

    await executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"}, index=0)))
    await executor.execute(
        _request(
            _call("tool-call-2", {"ticker": "DAYU"}, index=1),
            run_id="run-mismatch",
        )
    )

    assert accept_port.candidates[1].tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert accept_port.candidates[1].policy_decision.reason_code == (
        "tool_call_not_allowed_in_scope"
    )
    assert accept_port.candidates[1].duplicate_decision is DuplicateDecisionKind.HARD_STOP
    assert accept_port.candidates[1].reuse_prior_event_refs == ()


@pytest.mark.asyncio
async def test_same_run_runtime_handles_share_duplicate_index() -> None:
    """同 Run 同进程多个 ToolRuntime handle 共享 duplicate accepted 记忆。"""

    first_tool = _CountingTool({"accepted": "first-runtime"})
    second_tool = _CountingTool({"accepted": "second-runtime"})
    first_accept_port = _AcceptingPort()
    second_accept_port = _AcceptingPort()
    registry = InMemoryRunScopedDuplicateGovernanceRegistry()
    policy = DuplicateGovernancePolicy(
        default_duplicate_decision=DuplicateDecisionKind.REUSE
    )

    await _executor(
        first_tool,
        first_accept_port,
        policy,
        duplicate_governance_registry=registry,
    ).execute(
        _request(_call("tool-call-1", {"ticker": "DAYU"}, index=0))
    )
    outcome = await _executor(
        second_tool,
        second_accept_port,
        policy,
        duplicate_governance_registry=registry,
    ).execute(
        _request(_call("tool-call-2", {"ticker": "DAYU"}, index=0))
    )

    assert first_tool.call_count == 1
    assert second_tool.call_count == 0
    assert isinstance(outcome.records[0].outcome, ToolCompletedOutcome)
    assert outcome.records[0].outcome.result.value == {"accepted": "first-runtime"}
    assert second_accept_port.candidates[0].tool_fact_kind is ToolFactKind.REUSE
    assert second_accept_port.candidates[0].reuse_prior_event_refs == (
        first_accept_port.acks[0].accepted_event_refs
    )


@pytest.mark.asyncio
async def test_different_runs_do_not_share_duplicate_index() -> None:
    """不同 Run 即使共用同一进程 registry 也不共享 duplicate accepted 记忆。"""

    first_tool = _CountingTool({"accepted": "first-run"})
    second_tool = _CountingTool({"accepted": "second-run"})
    registry = InMemoryRunScopedDuplicateGovernanceRegistry()
    policy = DuplicateGovernancePolicy(
        default_duplicate_decision=DuplicateDecisionKind.REUSE
    )

    await _executor(
        first_tool,
        _AcceptingPort(),
        policy,
        duplicate_governance_registry=registry,
    ).execute(
        _request(_call("tool-call-1", {"ticker": "DAYU"}, index=0))
    )
    await _executor(
        second_tool,
        _AcceptingPort(),
        policy,
        run_id="run-other",
        duplicate_governance_registry=registry,
    ).execute(
        _request(
            _call("tool-call-2", {"ticker": "DAYU"}, index=0),
            run_id="run-other",
        )
    )

    assert first_tool.call_count == 1
    assert second_tool.call_count == 1


def _executor(
    tool: _CountingTool,
    accept_port: HostToolFactAcceptPort,
    duplicate_policy: DuplicateGovernancePolicy,
    *,
    diagnostic_emitter: InMemoryToolTraceDiagnosticEmitter | None = None,
    policy_view: ToolRuntimePolicyView | None = None,
    run_id: str = _RUN_ID,
    duplicate_governance_registry: (
        InMemoryRunScopedDuplicateGovernanceRegistry | None
    ) = None,
) -> ToolExecutor:
    """构造测试用 ToolRuntime executor。

    :param tool: 测试工具。
    :param accept_port: accept port。
    :param duplicate_policy: duplicate governance 策略。
    :param diagnostic_emitter: 可选内存诊断 emitter。
    :param policy_view: 可选工具 policy view。
    :param run_id: ToolRuntime execution scope 的 Run id。
    :param duplicate_governance_registry: 可选 Run-scoped duplicate registry。
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
                run_id=run_id,
                attempt_id=_ATTEMPT_ID,
                execution_id=_EXECUTION_ID,
                allow_tool_calls=True,
            ),
            accept_port=accept_port,
            retry_policy=ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=0.0),
            policy_view=(
                policy_view if policy_view is not None else ToolRuntimePolicyView()
            ),
            duplicate_governance_policy=duplicate_policy,
            duplicate_governance_registry=duplicate_governance_registry,
            diagnostic_emitter=diagnostic_emitter,
        )
    ).tool_executor


async def _governed_duplicate_candidate(
    decision: DuplicateDecisionKind,
) -> ToolFactAcceptCandidate:
    """执行重复调用并返回 duplicate governed candidate。

    :param decision: duplicate governance 决策。
    :returns: 第二次重复调用产生的 governed candidate。
    """

    tool = _CountingTool({"accepted": "prior"})
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=decision,
            justification_argument_names_by_tool_name=(
                {"fake_tool": "duplicate_justification"}
                if decision is DuplicateDecisionKind.REQUIRE_JUSTIFICATION
                else {}
            ),
        ),
    )

    await executor.execute(
        _request(
            _call("tool-call-1", {"ticker": "DAYU"}, index=0),
            _call("tool-call-2", {"ticker": "DAYU"}, index=1),
        )
    )

    candidate = accept_port.candidates[1]
    assert candidate.tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    return candidate


def _request(
    *calls: ToolCallRequest, run_id: str = _RUN_ID
) -> BatchToolExecutionRequest:
    """构造批式工具执行请求。

    :param calls: 单次工具调用请求。
    :param run_id: 请求上下文 run id。
    :returns: 批式工具执行请求。
    """

    return BatchToolExecutionRequest(
        calls=calls,
        context=BatchToolExecutionContext(
            run_id=run_id,
            session_id=_SESSION_ID,
            iteration_id=_ITERATION_ID,
            timeout_seconds=10.0,
            cancellation_token=_NeverCancelledToken(),
            correlation_id="correlation-duplicate",
        ),
    )


def _call(
    tool_call_id: str, arguments: Mapping[str, JsonValue], *, index: int
) -> ToolCallRequest:
    """构造工具调用请求。

    :param tool_call_id: 工具调用 id。
    :param arguments: 工具参数。
    :param index: iteration 内结构性序号。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name="fake_tool",
        arguments=arguments,
        index_in_iteration=index,
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

    properties: dict[str, JsonValue] = {
        "ticker": {"type": "string"},
        "year": {"type": "integer"},
        "duplicate_justification": {"type": "string"},
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
        source_id="duplicate-test",
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
        if candidate.tool_fact_kind is ToolFactKind.REUSE
        or candidate.policy_decision.kind is not ToolPolicyDecisionKind.ALLOW
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
