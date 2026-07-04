"""Host ToolRuntime attempt-scoped duplicate governance 测试。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolCallable, ToolDefinition
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
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
)
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    HostEventRef,
    HostPayloadRef,
    HostToolFactAcceptPort,
    InMemoryToolTraceDiagnosticEmitter,
    ToolAcceptDuplicateGovernance,
    ToolAcceptRejectReason,
    ToolAcceptRetryPolicy,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptTimedOut,
    ToolFactAcceptedAck,
    ToolFactRejectedAck,
    ToolFactKind,
    ToolPolicyDecision,
    ToolPolicyDecisionKind,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
    ToolRuntimePolicyView,
)
from dayu.host.tooling import (
    default_framework_tool_policy_view,
)
from dayu.host.tool_duplicate_governance import (
    DuplicateAwaitingAcceptedEntry,
    DuplicateDecisionKind,
    DuplicateDurableMissingReason,
    DuplicateGovernanceScope,
    DuplicateGovernanceMessages,
    DuplicateGovernancePolicy,
    DuplicateGovernanceRequest,
    InMemoryAttemptDuplicateGovernance,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef

_SESSION_ID = "session-duplicate"
_RUN_ID = "run-duplicate"
_ATTEMPT_ID = "attempt-duplicate"
_EXECUTION_ID = "execution-duplicate"
_ITERATION_ID = "iteration-duplicate"
_POLICY_DIGEST = "sha256:5555555555555555555555555555555555555555555555555555555555555555"
_GOVERNED_BEFORE_ACCEPT_TIMEOUT_SECONDS = 0.1
_GOVERNED_BEFORE_ACCEPT_WAIT_SECONDS = 1.0


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


class _ControllableCancellationToken:
    """测试用可控取消 token。"""

    def __init__(self) -> None:
        """初始化未取消 token。

        :returns: ``None``。
        """

        self._cancelled = False
        self._reason: str | None = None
        self._requested_at: datetime | None = None

    def cancel(self, reason: str) -> None:
        """请求取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self._cancelled = True
        self._reason = reason
        self._requested_at = datetime.now()

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已请求取消时返回 ``True``。
        """

        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 取消原因；未取消时为 ``None``。
        """

        return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 取消请求时间；未取消时为 ``None``。
        """

        return self._requested_at


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


class _BlockingCountingTool:
    """等待测试事件释放后返回固定成功结果的测试工具。"""

    def __init__(
        self,
        value: JsonValue,
        *,
        entered: asyncio.Event,
        release: asyncio.Event,
    ) -> None:
        """初始化阻塞测试工具。

        :param value: 工具返回值。
        :param entered: 工具开始执行时置位的事件。
        :param release: 允许工具返回的事件。
        :returns: ``None``。
        """

        self._value = value
        self._entered = entered
        self._release = release
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """等待 release 事件后返回固定成功结果。

        :param call: 单次工具调用请求。
        :param context: 批式工具上下文。
        :returns: 成功 outcome。
        """

        del call, context
        self.call_count += 1
        self._entered.set()
        await self._release.wait()
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value=self._value, meta=None)
        )


class _SequencedBlockingCountingTool:
    """按调用序号使用独立事件阻塞并返回对应结果的测试工具。"""

    def __init__(
        self,
        values: tuple[JsonValue, ...],
        *,
        entered_events: tuple[asyncio.Event, ...],
        release_events: tuple[asyncio.Event, ...],
    ) -> None:
        """初始化序列阻塞测试工具。

        :param values: 每次调用返回的结果值。
        :param entered_events: 每次调用开始执行时置位的事件。
        :param release_events: 每次调用允许返回的事件。
        :returns: ``None``。
        :raises ValueError: 三个序列长度不一致时抛出。
        """

        if len(values) != len(entered_events) or len(values) != len(release_events):
            raise ValueError("sequenced blocking tool requires aligned sequences")
        self._values = values
        self._entered_events = entered_events
        self._release_events = release_events
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """等待当前调用对应 release 事件后返回固定成功结果。

        :param call: 单次工具调用请求。
        :param context: 批式工具上下文。
        :returns: 成功 outcome。
        :raises RuntimeError: 调用次数超过已配置序列长度时抛出。
        """

        del call, context
        call_index = self.call_count
        self.call_count += 1
        if call_index >= len(self._values):
            raise RuntimeError("unexpected sequenced blocking tool call")
        self._entered_events[call_index].set()
        await self._release_events[call_index].wait()
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=self._values[call_index],
                meta=None,
            )
        )


class _FailingTool:
    """抛出业务异常的测试工具。"""

    def __init__(self) -> None:
        """初始化失败工具。

        :returns: ``None``。
        """

        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """抛出业务异常。

        :param call: 单次工具调用请求。
        :param context: 批式工具上下文。
        :returns: 不返回；始终抛出异常。
        :raises RuntimeError: 始终抛出。
        """

        del call, context
        self.call_count += 1
        raise RuntimeError("boom")


class _BlockingFailingTool:
    """等待测试事件释放后抛出业务异常的测试工具。"""

    def __init__(self, *, entered: asyncio.Event, release: asyncio.Event) -> None:
        """初始化阻塞失败工具。

        :param entered: 工具开始执行时置位的事件。
        :param release: 允许工具抛出异常的事件。
        :returns: ``None``。
        """

        self._entered = entered
        self._release = release
        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """等待 release 事件后抛出业务异常。

        :param call: 单次工具调用请求。
        :param context: 批式工具上下文。
        :returns: 不返回；始终抛出异常。
        :raises RuntimeError: 始终抛出。
        """

        del call, context
        self.call_count += 1
        self._entered.set()
        await self._release.wait()
        raise RuntimeError("boom")


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


class _RejectingPort(HostToolFactAcceptPort):
    """记录 candidate 并始终 rejected 的测试 accept port。"""

    def __init__(self) -> None:
        """初始化测试 accept port。

        :returns: ``None``。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并返回 rejected ack。

        :param candidate: 工具事实候选。
        :returns: rejected ack。
        """

        self.candidates.append(candidate)
        return ToolFactRejectedAck(
            reason_code=ToolAcceptRejectReason.EXPLICIT_POLICY_REJECT,
            message="reject for duplicate governance test",
            diagnostic_refs=(),
            retryable=False,
        )


class _TimedOutPort(HostToolFactAcceptPort):
    """记录 candidate 并始终返回 timed out 的测试 accept port。"""

    def __init__(self) -> None:
        """初始化测试 accept port。

        :returns: ``None``。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并返回 timed out。

        :param candidate: 工具事实候选。
        :returns: timed out 结果。
        """

        self.candidates.append(candidate)
        return ToolFactAcceptTimedOut(
            attempt_count=1,
            last_error_code="forced-timeout",
            diagnostic_refs=(),
        )


class _RejectOnceThenAcceptingPort(HostToolFactAcceptPort):
    """第一次 rejected、后续 accepted 的测试 accept port。"""

    def __init__(self) -> None:
        """初始化测试 accept port。

        :returns: ``None``。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []
        self.acks: list[ToolFactAcceptedAck] = []

    def accept_tool_fact(
        self, candidate: ToolFactAcceptCandidate
    ) -> ToolFactAcceptResult:
        """记录 candidate 并按调用序号返回 rejected 或 accepted。

        :param candidate: 工具事实候选。
        :returns: 第一次为 rejected ack，后续为 accepted ack。
        """

        self.candidates.append(candidate)
        if len(self.candidates) == 1:
            return ToolFactRejectedAck(
                reason_code=ToolAcceptRejectReason.EXPLICIT_POLICY_REJECT,
                message="reject first candidate for duplicate handoff test",
                diagnostic_refs=(),
                retryable=False,
            )
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
    assert accept_port.candidates[0].call.normalized_arguments_digest == (
        accept_port.candidates[1].call.normalized_arguments_digest
    )
    assert _candidate_duplicate(accept_port.candidates[0]).duplicate_key == (
        _candidate_duplicate(accept_port.candidates[1]).duplicate_key
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
    assert _candidate_duplicate_decision(
        accept_port.candidates[1]
    ) is DuplicateDecisionKind.REUSE
    assert _candidate_reuse_prior_event_refs(accept_port.candidates[1])


@pytest.mark.asyncio
async def test_allow_duplicate_decision_executes_and_accepts_each_call() -> None:
    """显式 allow 策略下重复调用仍执行并各自进入 accept path。"""

    tool = _CountingTool({"accepted": True})
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.ALLOW
        ),
    )

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
        _candidate_duplicate_decision(candidate) is DuplicateDecisionKind.ALLOW
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
    assert _candidate_reuse_prior_event_refs(reuse_candidate) == (
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
    duplicate_scope = _candidate_duplicate_scope(governed_candidate)
    assert tool.call_count == 1
    assert governed_candidate.tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert governed_candidate.governance.policy_decision.kind is expected_policy
    assert duplicate_scope.kind == "attempt"
    assert duplicate_scope.attempt_id == _ATTEMPT_ID
    assert governed_candidate.diagnostics.diagnostic_refs
    assert _candidate_reuse_prior_event_refs(governed_candidate)
    assert len(diagnostics.records) == 1


@pytest.mark.asyncio
async def test_governed_duplicate_candidate_validation_rejects_missing_prior_refs() -> None:
    """duplicate governed_error candidate 必须携带 prior accepted refs。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HINT
    )

    with pytest.raises(ValueError, match="requires prior event refs"):
        duplicate = replace(
            _candidate_duplicate(governed_candidate), reuse_prior_event_refs=()
        )
        governance = replace(governed_candidate.governance, duplicate=duplicate)
        replace(governed_candidate, governance=governance)


@pytest.mark.asyncio
async def test_governed_duplicate_candidate_validation_rejects_policy_mismatch() -> None:
    """duplicate governed_error candidate 的 policy kind 必须匹配决策类别。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HINT
    )

    with pytest.raises(ValueError, match="policy kind must match decision"):
        governance = replace(
            governed_candidate.governance,
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.HARD_STOP,
                reason_code="duplicate_hint",
                message=(
                    "请优先使用上一次工具结果继续推理；只有当需要不同主体、"
                    "期间、指标或证据范围时，才重新调用工具并修改参数。"
                ),
            ),
        )
        replace(
            governed_candidate,
            governance=governance,
        )


@pytest.mark.asyncio
async def test_governed_duplicate_candidate_validation_rejects_reason_mismatch() -> None:
    """duplicate governed_error candidate 的 reason 必须匹配决策类别。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HARD_STOP
    )

    with pytest.raises(ValueError, match="reason must match decision"):
        governance = replace(
            governed_candidate.governance,
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.HARD_STOP,
                reason_code="duplicate_hint",
                message=(
                    "本次重复工具调用已被拒绝。请使用上一次工具结果继续推理；"
                    "如果信息不足，请说明不确定性，不要编造。"
                ),
            ),
        )
        replace(
            governed_candidate,
            governance=governance,
        )


@pytest.mark.asyncio
async def test_governed_duplicate_candidate_validation_rejects_message_mismatch() -> None:
    """duplicate governed_error candidate 的 message 必须匹配决策类别。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.REQUIRE_JUSTIFICATION
    )

    with pytest.raises(ValueError, match="message must match decision"):
        governance = replace(
            governed_candidate.governance,
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.REQUIRE_JUSTIFICATION,
                reason_code="duplicate_requires_justification",
                message="wrong duplicate governance message",
            ),
        )
        replace(
            governed_candidate,
            governance=governance,
        )


@pytest.mark.asyncio
async def test_governed_error_candidate_validation_rejects_allow_policy() -> None:
    """governed_error fact 不允许携带 allow policy。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HINT
    )

    with pytest.raises(ValueError, match="requires governed policy decision"):
        governance = replace(
            governed_candidate.governance,
            duplicate=None,
            policy_decision=ToolPolicyDecision(
                kind=ToolPolicyDecisionKind.ALLOW,
                reason_code=None,
                message=None,
            ),
        )
        replace(
            governed_candidate,
            governance=governance,
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
    assert _candidate_duplicate_decision(
        accept_port.candidates[1]
    ) is DuplicateDecisionKind.ALLOW


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
    assert _candidate_duplicate_decision(
        accept_port.candidates[1]
    ) is DuplicateDecisionKind.HINT
    assert (
        accept_port.candidates[1].governance.policy_decision.kind
        is ToolPolicyDecisionKind.HINT
    )


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
    assert accept_port.candidates[1].governance.policy_decision.reason_code == (
        "tool_call_not_allowed_in_scope"
    )
    assert _candidate_duplicate_decision(
        accept_port.candidates[1]
    ) is DuplicateDecisionKind.HARD_STOP
    assert _candidate_reuse_prior_event_refs(accept_port.candidates[1]) == ()


@pytest.mark.asyncio
async def test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs() -> None:
    """相同 run_id 不同 Attempt 的同工具同参数按 fresh request 执行。"""

    first_tool = _CountingTool({"accepted": "first-attempt"})
    second_tool = _CountingTool({"accepted": "second-attempt"})
    first_accept_port = _AcceptingPort()
    second_accept_port = _AcceptingPort()
    policy = DuplicateGovernancePolicy(
        default_duplicate_decision=DuplicateDecisionKind.REUSE
    )

    await _executor(first_tool, first_accept_port, policy).execute(
        _request(_call("tool-call-1", {"ticker": "DAYU"}, index=0))
    )
    await _executor(
        second_tool,
        second_accept_port,
        policy,
        attempt_id="attempt-other",
    ).execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=0)))

    assert first_tool.call_count == 1
    assert second_tool.call_count == 1
    assert first_accept_port.candidates[0].tool_fact_kind is ToolFactKind.COMPLETED
    assert second_accept_port.candidates[0].tool_fact_kind is ToolFactKind.COMPLETED
    assert _candidate_duplicate_decision(first_accept_port.candidates[0]) is (
        DuplicateDecisionKind.ALLOW
    )
    assert _candidate_duplicate_decision(second_accept_port.candidates[0]) is (
        DuplicateDecisionKind.ALLOW
    )
    assert _candidate_reuse_prior_event_refs(first_accept_port.candidates[0]) == ()
    assert _candidate_reuse_prior_event_refs(second_accept_port.candidates[0]) == ()
    assert _candidate_duplicate(first_accept_port.candidates[0]).duplicate_key != (
        _candidate_duplicate(second_accept_port.candidates[0]).duplicate_key
    )
    assert _candidate_duplicate_scope(
        first_accept_port.candidates[0]
    ).attempt_id == _ATTEMPT_ID
    assert _candidate_duplicate_scope(second_accept_port.candidates[0]).attempt_id == (
        "attempt-other"
    )


@pytest.mark.asyncio
async def test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_restart_behavior() -> None:
    """新 ToolRuntime handle 不继承内存 duplicate index；该行为不是 correctness 前提。"""

    first_tool = _CountingTool({"accepted": "before-restart"})
    restarted_tool = _CountingTool({"accepted": "after-restart"})
    first_accept_port = _AcceptingPort()
    restarted_accept_port = _AcceptingPort()
    policy = DuplicateGovernancePolicy(
        default_duplicate_decision=DuplicateDecisionKind.REUSE
    )

    await _executor(first_tool, first_accept_port, policy).execute(
        _request(_call("tool-call-before-restart", {"ticker": "DAYU"}, index=0))
    )
    await _executor(restarted_tool, restarted_accept_port, policy).execute(
        _request(_call("tool-call-after-restart", {"ticker": "DAYU"}, index=0))
    )

    assert first_tool.call_count == 1
    assert restarted_tool.call_count == 1
    assert _candidate_duplicate_scope(
        first_accept_port.candidates[0]
    ).attempt_id == _ATTEMPT_ID
    assert _candidate_duplicate_scope(restarted_accept_port.candidates[0]).attempt_id == (
        _ATTEMPT_ID
    )
    assert _candidate_duplicate(first_accept_port.candidates[0]).duplicate_key == (
        _candidate_duplicate(restarted_accept_port.candidates[0]).duplicate_key
    )
    assert restarted_accept_port.candidates[0].tool_fact_kind is ToolFactKind.COMPLETED
    assert _candidate_duplicate_decision(restarted_accept_port.candidates[0]) is (
        DuplicateDecisionKind.ALLOW
    )
    assert _candidate_reuse_prior_event_refs(restarted_accept_port.candidates[0]) == ()


@pytest.mark.asyncio
async def test_same_attempt_concurrent_reuse_waits_for_owner_accept() -> None:
    """同 Attempt 并发重复调用等待 owner accepted 后复用结果。"""

    entered = asyncio.Event()
    release = asyncio.Event()
    tool = _BlockingCountingTool(
        {"accepted": "owner"}, entered=entered, release=release
    )
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    owner = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"}, index=0)))
    )
    await entered.wait()
    waiter = asyncio.create_task(
        executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))
    )
    await asyncio.sleep(0)
    assert tool.call_count == 1
    assert not waiter.done()

    release.set()
    owner_outcome, waiter_outcome = await asyncio.gather(owner, waiter)

    assert tool.call_count == 1
    assert isinstance(owner_outcome.records[0].outcome, ToolCompletedOutcome)
    assert isinstance(waiter_outcome.records[0].outcome, ToolCompletedOutcome)
    assert waiter_outcome.records[0].outcome.result.value == {"accepted": "owner"}
    assert accept_port.candidates[1].tool_fact_kind is ToolFactKind.REUSE
    assert _candidate_reuse_prior_event_refs(accept_port.candidates[1]) == (
        accept_port.acks[0].accepted_event_refs
    )


@pytest.mark.asyncio
async def test_same_attempt_concurrent_rejected_accept_hands_off_to_waiter() -> None:
    """owner accept rejected 时 waiter 接棒成为新 owner 并真实执行。"""

    owner_entered = asyncio.Event()
    replacement_entered = asyncio.Event()
    owner_release = asyncio.Event()
    replacement_release = asyncio.Event()
    tool = _SequencedBlockingCountingTool(
        ({"accepted": "owner"}, {"accepted": "replacement"}),
        entered_events=(owner_entered, replacement_entered),
        release_events=(owner_release, replacement_release),
    )
    accept_port = _RejectOnceThenAcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    owner = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"}, index=0)))
    )
    await owner_entered.wait()
    waiter = asyncio.create_task(
        executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))
    )
    await asyncio.sleep(0)
    owner_release.set()
    await replacement_entered.wait()
    replacement_release.set()
    owner_outcome, waiter_outcome = await asyncio.gather(owner, waiter)

    assert tool.call_count == 2
    assert isinstance(owner_outcome.records[0].outcome, ToolFailedOutcome)
    assert isinstance(waiter_outcome.records[0].outcome, ToolCompletedOutcome)
    assert waiter_outcome.records[0].outcome.result.value == {
        "accepted": "replacement"
    }
    assert [candidate.tool_fact_kind for candidate in accept_port.candidates] == [
        ToolFactKind.COMPLETED,
        ToolFactKind.COMPLETED,
    ]

    later = await executor.execute(
        _request(_call("tool-call-3", {"ticker": "DAYU"}, index=2))
    )
    assert tool.call_count == 2
    assert isinstance(later.records[0].outcome, ToolCompletedOutcome)
    assert later.records[0].outcome.result.value == {"accepted": "replacement"}
    assert accept_port.candidates[2].tool_fact_kind is ToolFactKind.REUSE
    assert _candidate_reuse_prior_event_refs(accept_port.candidates[2]) == (
        accept_port.acks[0].accepted_event_refs
    )


@pytest.mark.asyncio
async def test_durable_missing_only_one_waiter_replaces_owner_and_others_reuse() -> None:
    """owner durable-missing 后只有一个 waiter 接棒，其它 waiter 继续等待复用。"""

    owner_entered = asyncio.Event()
    replacement_entered = asyncio.Event()
    owner_release = asyncio.Event()
    replacement_release = asyncio.Event()
    tool = _SequencedBlockingCountingTool(
        ({"accepted": "owner"}, {"accepted": "replacement"}),
        entered_events=(owner_entered, replacement_entered),
        release_events=(owner_release, replacement_release),
    )
    accept_port = _RejectOnceThenAcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    owner = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"}, index=0)))
    )
    await owner_entered.wait()
    waiter_one = asyncio.create_task(
        executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))
    )
    waiter_two = asyncio.create_task(
        executor.execute(_request(_call("tool-call-3", {"ticker": "DAYU"}, index=2)))
    )
    await asyncio.sleep(0)
    assert tool.call_count == 1

    owner_release.set()
    await replacement_entered.wait()
    await asyncio.sleep(0)
    assert tool.call_count == 2
    assert not waiter_one.done() or not waiter_two.done()

    replacement_release.set()
    owner_outcome, waiter_one_outcome, waiter_two_outcome = await asyncio.gather(
        owner,
        waiter_one,
        waiter_two,
    )

    waiter_outcomes = (
        waiter_one_outcome.records[0].outcome,
        waiter_two_outcome.records[0].outcome,
    )
    assert tool.call_count == 2
    assert isinstance(owner_outcome.records[0].outcome, ToolFailedOutcome)
    assert all(isinstance(outcome, ToolCompletedOutcome) for outcome in waiter_outcomes)
    assert all(
        outcome.result.value == {"accepted": "replacement"}
        for outcome in waiter_outcomes
        if isinstance(outcome, ToolCompletedOutcome)
    )
    assert [candidate.tool_fact_kind for candidate in accept_port.candidates] == [
        ToolFactKind.COMPLETED,
        ToolFactKind.COMPLETED,
        ToolFactKind.REUSE,
    ]
    assert accept_port.candidates[2].call.tool_call_id in {
        "tool-call-2",
        "tool-call-3",
    }
    assert _candidate_reuse_prior_event_refs(accept_port.candidates[2]) == (
        accept_port.acks[0].accepted_event_refs
    )


@pytest.mark.asyncio
async def test_governed_before_accept_hands_off_to_waiter() -> None:
    """owner 工具超时并在 accept 前受治理时，waiter 接棒执行。"""

    owner_entered = asyncio.Event()
    replacement_entered = asyncio.Event()
    owner_release = asyncio.Event()
    replacement_release = asyncio.Event()
    tool = _SequencedBlockingCountingTool(
        ({"accepted": "owner"}, {"accepted": "replacement"}),
        entered_events=(owner_entered, replacement_entered),
        release_events=(owner_release, replacement_release),
    )
    accept_port = _AcceptingPort()
    executor = _executor(
        tool,
        accept_port,
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    owner = asyncio.create_task(
        executor.execute(
            _request(
                _call("tool-call-1", {"ticker": "DAYU"}, index=0),
                timeout_seconds=_GOVERNED_BEFORE_ACCEPT_TIMEOUT_SECONDS,
            )
        )
    )
    await owner_entered.wait()
    waiter = asyncio.create_task(
        executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))
    )
    await asyncio.sleep(0)
    assert tool.call_count == 1
    assert not waiter.done()

    await asyncio.wait_for(
        replacement_entered.wait(),
        timeout=_GOVERNED_BEFORE_ACCEPT_WAIT_SECONDS,
    )
    replacement_release.set()
    owner_outcome, waiter_outcome = await asyncio.gather(owner, waiter)

    assert tool.call_count == 2
    assert isinstance(owner_outcome.records[0].outcome, ToolFailedOutcome)
    assert isinstance(waiter_outcome.records[0].outcome, ToolCompletedOutcome)
    assert waiter_outcome.records[0].outcome.result.value == {
        "accepted": "replacement"
    }
    assert [candidate.tool_fact_kind for candidate in accept_port.candidates] == [
        ToolFactKind.GOVERNED_ERROR,
        ToolFactKind.COMPLETED,
    ]

    later = await executor.execute(
        _request(_call("tool-call-3", {"ticker": "DAYU"}, index=2))
    )
    assert tool.call_count == 2
    assert isinstance(later.records[0].outcome, ToolCompletedOutcome)
    assert later.records[0].outcome.result.value == {"accepted": "replacement"}
    assert accept_port.candidates[2].tool_fact_kind is ToolFactKind.REUSE
    assert _candidate_reuse_prior_event_refs(accept_port.candidates[2]) == (
        accept_port.acks[1].accepted_event_refs
    )


@pytest.mark.asyncio
async def test_same_attempt_concurrent_timed_out_accept_hands_off_to_waiter() -> None:
    """owner accept timeout 时 waiter 接棒成为新 owner 并真实执行。"""

    entered = asyncio.Event()
    release = asyncio.Event()
    tool = _BlockingCountingTool(
        {"accepted": "owner"}, entered=entered, release=release
    )
    executor = _executor(
        tool,
        _TimedOutPort(),
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    owner = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"}, index=0)))
    )
    await entered.wait()
    waiter = asyncio.create_task(
        executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))
    )
    await asyncio.sleep(0)
    release.set()
    owner_outcome, waiter_outcome = await asyncio.gather(owner, waiter)

    assert tool.call_count == 2
    assert isinstance(owner_outcome.records[0].outcome, ToolFailedOutcome)
    assert isinstance(waiter_outcome.records[0].outcome, ToolFailedOutcome)
    assert waiter_outcome.records[0].outcome.result.hint != (
        "duplicate_prior_accept_missing"
    )

    later = await executor.execute(
        _request(_call("tool-call-3", {"ticker": "DAYU"}, index=2))
    )
    assert tool.call_count == 3
    assert isinstance(later.records[0].outcome, ToolFailedOutcome)


@pytest.mark.asyncio
async def test_same_attempt_concurrent_tool_exception_hands_off_to_waiter() -> None:
    """owner 工具异常时 waiter 接棒成为新 owner 并真实执行。"""

    entered = asyncio.Event()
    release = asyncio.Event()
    tool = _BlockingFailingTool(entered=entered, release=release)
    executor = _executor(
        tool,
        _AcceptingPort(),
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    owner = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"}, index=0)))
    )
    await entered.wait()
    waiter = asyncio.create_task(
        executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))
    )
    await asyncio.sleep(0)
    release.set()
    owner_outcome, waiter_outcome = await asyncio.gather(owner, waiter)

    assert tool.call_count == 2
    assert isinstance(owner_outcome.records[0].outcome, ToolFailedOutcome)
    assert isinstance(waiter_outcome.records[0].outcome, ToolFailedOutcome)
    assert waiter_outcome.records[0].outcome.result.hint != (
        "duplicate_prior_accept_missing"
    )

    later = await executor.execute(
        _request(_call("tool-call-3", {"ticker": "DAYU"}, index=2))
    )
    assert tool.call_count == 3
    assert isinstance(later.records[0].outcome, ToolFailedOutcome)


@pytest.mark.asyncio
async def test_same_attempt_concurrent_owner_cancellation_hands_off_to_waiter() -> None:
    """owner 取消时 waiter 接棒成为新 owner 并真实执行。"""

    owner_entered = asyncio.Event()
    replacement_entered = asyncio.Event()
    owner_release = asyncio.Event()
    replacement_release = asyncio.Event()
    token = _ControllableCancellationToken()
    tool = _SequencedBlockingCountingTool(
        ({"accepted": "owner"}, {"accepted": "replacement"}),
        entered_events=(owner_entered, replacement_entered),
        release_events=(owner_release, replacement_release),
    )
    executor = _executor(
        tool,
        _AcceptingPort(),
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        ),
    )

    owner = asyncio.create_task(
        executor.execute(
            _request(
                _call("tool-call-1", {"ticker": "DAYU"}, index=0),
                cancellation_token=token,
            )
        )
    )
    await owner_entered.wait()
    waiter = asyncio.create_task(
        executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))
    )
    await asyncio.sleep(0)
    token.cancel("owner cancelled by test")
    await replacement_entered.wait()
    replacement_release.set()
    owner_outcome, waiter_outcome = await asyncio.wait_for(
        asyncio.gather(owner, waiter),
        timeout=1.0,
    )

    assert tool.call_count == 2
    assert isinstance(owner_outcome.records[0].outcome, ToolFailedOutcome)
    assert owner_outcome.records[0].outcome.result.hint == "tool_runtime_cancelled"
    assert isinstance(waiter_outcome.records[0].outcome, ToolCompletedOutcome)
    assert waiter_outcome.records[0].outcome.result.value == {
        "accepted": "replacement"
    }

    later = await executor.execute(
        _request(_call("tool-call-3", {"ticker": "DAYU"}, index=2))
    )
    assert tool.call_count == 2
    assert isinstance(later.records[0].outcome, ToolCompletedOutcome)


@pytest.mark.asyncio
async def test_allow_policy_concurrent_waits_for_owner_before_second_execution() -> None:
    """allow policy 的并发 duplicate 也必须等 owner terminal 后才二次执行。"""

    entered = asyncio.Event()
    release = asyncio.Event()
    tool = _BlockingCountingTool(
        {"accepted": "owner"}, entered=entered, release=release
    )
    executor = _executor(
        tool,
        _AcceptingPort(),
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.ALLOW
        ),
    )

    owner = asyncio.create_task(
        executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"}, index=0)))
    )
    await entered.wait()
    waiter = asyncio.create_task(
        executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))
    )
    await asyncio.sleep(0)
    assert tool.call_count == 1

    release.set()
    await asyncio.gather(owner, waiter)

    assert tool.call_count == 2


@pytest.mark.asyncio
async def test_allow_policy_post_owner_completion_executes_again() -> None:
    """allow policy 在 owner 完成后的重复调用会再次真实执行。"""

    tool = _CountingTool({"accepted": True})
    executor = _executor(
        tool,
        _AcceptingPort(),
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.ALLOW
        ),
    )

    await executor.execute(_request(_call("tool-call-1", {"ticker": "DAYU"}, index=0)))
    await executor.execute(_request(_call("tool-call-2", {"ticker": "DAYU"}, index=1)))

    assert tool.call_count == 2


@pytest.mark.asyncio
async def test_record_awaiting_accepted_marks_terminal_without_ordinary_reuse() -> None:
    """awaiting accepted marker 不污染普通 accepted index。"""

    governance = InMemoryAttemptDuplicateGovernance(
        DuplicateGovernancePolicy(
            default_duplicate_decision=DuplicateDecisionKind.REUSE
        )
    )
    request = _duplicate_request()
    owner = await governance.decide_duplicate(request)
    awaiting_outcome = _awaiting_outcome()
    refs = (HostEventRef(event_id="event-awaiting-owner", event_sequence=1),)

    await governance.record_awaiting_accepted(
        request,
        DuplicateAwaitingAcceptedEntry(
            accepted_event_refs=refs,
            wait_id="wait-owner",
            awaiting_outcome=awaiting_outcome,
            result_digest=sha256_digest_json({"awaiting": "owner"}),
        ),
    )
    decision = await governance.decide_duplicate(request)

    assert owner.kind is DuplicateDecisionKind.ALLOW
    assert decision.kind is DuplicateDecisionKind.AWAITING_FANOUT
    assert decision.prior_event_refs == refs
    assert decision.prior_outcome is None
    assert decision.prior_awaiting_outcome is awaiting_outcome
    assert decision.prior_wait_id == "wait-owner"


@pytest.mark.asyncio
async def test_record_awaiting_accepted_fans_out_multiple_waiters() -> None:
    """awaiting accepted marker 下多个 waiter 均共享同一 owner wait。"""

    governance = InMemoryAttemptDuplicateGovernance()
    request = _duplicate_request()
    await governance.decide_duplicate(request)
    awaiting_outcome = _awaiting_outcome()

    await governance.record_awaiting_accepted(
        request,
        DuplicateAwaitingAcceptedEntry(
            accepted_event_refs=(
                HostEventRef(event_id="event-awaiting-owner", event_sequence=1),
            ),
            wait_id="wait-owner",
            awaiting_outcome=awaiting_outcome,
            result_digest=sha256_digest_json({"awaiting": "owner"}),
        ),
    )

    first = await governance.decide_duplicate(request)
    second = await governance.decide_duplicate(request)

    assert first.kind is DuplicateDecisionKind.AWAITING_FANOUT
    assert second.kind is DuplicateDecisionKind.AWAITING_FANOUT
    assert first.prior_wait_id == "wait-owner"
    assert second.prior_wait_id == "wait-owner"
    assert first.prior_awaiting_outcome is awaiting_outcome
    assert second.prior_awaiting_outcome is awaiting_outcome


@pytest.mark.asyncio
async def test_durable_missing_preserves_awaiting_accepted_marker() -> None:
    """AWAITING_ACCEPTED guard 保留 owner wait，不重新竞争 owner。"""

    governance = InMemoryAttemptDuplicateGovernance()
    request = _duplicate_request()
    owner = await governance.decide_duplicate(request)
    awaiting_outcome = _awaiting_outcome()
    refs = (HostEventRef(event_id="event-awaiting-owner", event_sequence=1),)

    await governance.record_awaiting_accepted(
        request,
        DuplicateAwaitingAcceptedEntry(
            accepted_event_refs=refs,
            wait_id="wait-owner",
            awaiting_outcome=awaiting_outcome,
            result_digest=sha256_digest_json({"awaiting": "owner"}),
        ),
    )
    await governance.record_durable_missing(
        request,
        DuplicateDurableMissingReason.GOVERNED_BEFORE_ACCEPT,
    )
    decision = await governance.decide_duplicate(request)

    assert owner.kind is DuplicateDecisionKind.ALLOW
    assert decision.kind is DuplicateDecisionKind.AWAITING_FANOUT
    assert decision.prior_event_refs == refs
    assert decision.prior_wait_id == "wait-owner"
    assert decision.prior_awaiting_outcome is awaiting_outcome
    assert decision.prior_outcome is None


@pytest.mark.asyncio
async def test_durable_missing_still_reopens_owner_competition() -> None:
    """durable-missing 仍释放 waiter 重新竞争 owner。"""

    governance = InMemoryAttemptDuplicateGovernance()
    request = _duplicate_request()
    owner = await governance.decide_duplicate(request)

    await governance.record_durable_missing(
        request,
        DuplicateDurableMissingReason.HOST_ACCEPT_TIMEOUT,
    )
    replacement = await governance.decide_duplicate(request)

    assert owner.kind is DuplicateDecisionKind.ALLOW
    assert replacement.kind is DuplicateDecisionKind.ALLOW
    assert replacement.prior_event_refs == ()
    assert replacement.prior_outcome is None
    assert replacement.prior_awaiting_outcome is None
    assert replacement.prior_wait_id is None


def test_duplicate_governance_messages_reject_empty_text() -> None:
    """duplicate governance messages 拒绝空白消息配置。"""

    with pytest.raises(ValueError, match="reuse must be non-empty"):
        DuplicateGovernanceMessages(reuse=" ")


@pytest.mark.asyncio
async def test_duplicate_candidate_validation_rejects_missing_duplicate_message() -> None:
    """duplicate candidate 缺少配置消息时 fail fast。"""

    governed_candidate = await _governed_duplicate_candidate(
        DuplicateDecisionKind.HINT
    )

    with pytest.raises(ValueError, match="requires duplicate_decision_message"):
        duplicate = replace(
            _candidate_duplicate(governed_candidate),
            duplicate_decision_message=None,
        )
        governance = replace(governed_candidate.governance, duplicate=duplicate)
        replace(governed_candidate, governance=governance)


def _executor(
    tool: ToolCallable,
    accept_port: HostToolFactAcceptPort,
    duplicate_policy: DuplicateGovernancePolicy,
    *,
    diagnostic_emitter: InMemoryToolTraceDiagnosticEmitter | None = None,
    policy_view: ToolRuntimePolicyView | None = None,
    run_id: str = _RUN_ID,
    attempt_id: str = _ATTEMPT_ID,
) -> ToolExecutor:
    """构造测试用 ToolRuntime executor。

    :param tool: 测试工具。
    :param accept_port: accept port。
    :param duplicate_policy: duplicate governance 策略。
    :param diagnostic_emitter: 可选内存诊断 emitter。
    :param policy_view: 可选工具 policy view。
    :param run_id: ToolRuntime execution scope 的 Run id。
    :param attempt_id: ToolRuntime execution scope 的 Attempt id。
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
                attempt_id=attempt_id,
                execution_id=_EXECUTION_ID,
                allow_tool_calls=True,
            ),
            accept_port=accept_port,
            retry_policy=ToolAcceptRetryPolicy(max_attempts=1, backoff_seconds=0.0),
            policy_view=(
                policy_view if policy_view is not None else ToolRuntimePolicyView()
            ),
            duplicate_governance_policy=duplicate_policy,
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
    duplicate_scope = _candidate_duplicate_scope(candidate)
    assert candidate.tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    assert duplicate_scope.kind == "attempt"
    assert duplicate_scope.attempt_id == _ATTEMPT_ID
    return candidate


def _request(
    *calls: ToolCallRequest,
    run_id: str = _RUN_ID,
    timeout_seconds: float | None = 10.0,
    cancellation_token: _OpenCancellationToken | _ControllableCancellationToken | None = None,
) -> BatchToolExecutionRequest:
    """构造批式工具执行请求。

    :param calls: 单次工具调用请求。
    :param run_id: 请求上下文 run id。
    :param timeout_seconds: 批级 timeout 秒数；无 timeout 时为 ``None``。
    :param cancellation_token: 可选取消 token；无则使用未取消 token。
    :returns: 批式工具执行请求。
    """

    token = cancellation_token if cancellation_token is not None else _OpenCancellationToken()
    return BatchToolExecutionRequest(
        calls=calls,
        context=BatchToolExecutionContext(
            run_id=run_id,
            session_id=_SESSION_ID,
            iteration_id=_ITERATION_ID,
            timeout_seconds=timeout_seconds,
            cancellation_token=token,
            correlation_id="correlation-duplicate",
        ),
    )


def _duplicate_request() -> DuplicateGovernanceRequest:
    """构造 direct duplicate governance 测试请求。

    :returns: duplicate governance 查询输入。
    """

    return DuplicateGovernanceRequest(
        scope=DuplicateGovernanceScope(kind="attempt", attempt_id=_ATTEMPT_ID),
        tool_name="fake_tool",
        tool_identity_digest=sha256_digest_json({"identity": "fake_tool"}),
        normalized_arguments_digest=sha256_digest_json({"ticker": "DAYU"}),
        arguments={"ticker": "DAYU"},
        semantic_duplicate_key=None,
    )


def _awaiting_outcome() -> ToolAwaitingOutcome:
    """构造 direct duplicate governance 测试 awaiting outcome。

    :returns: awaiting outcome。
    """

    return ToolAwaitingOutcome(
        await_spec=ToolAwaitSpec(
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
            deadline=None,
            resume_token="resume-token",
        ),
        snapshot=None,
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


def _definition(name: str, tool: ToolCallable) -> ToolDefinition:
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
        execution=AsyncDirectToolExecutionCapability(),
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

    tool_call_id = candidate.call.tool_call_id
    policy_decision = candidate.governance.policy_decision
    result = candidate.result
    requested_ref = HostEventRef(
        event_id=f"event-requested-{tool_call_id}",
        event_sequence=len(tool_call_id) + 1,
    )
    governed_ref = (
        HostEventRef(
            event_id=f"event-governed-{tool_call_id}",
            event_sequence=len(tool_call_id) + 2,
        )
        if candidate.tool_fact_kind is ToolFactKind.REUSE
        or policy_decision.kind is not ToolPolicyDecisionKind.ALLOW
        else None
    )
    result_ref = (
        None
        if candidate.tool_fact_kind is ToolFactKind.REUSE
        else HostEventRef(
            event_id=f"event-result-{tool_call_id}",
            event_sequence=len(tool_call_id) + 3,
        )
    )
    accepted_event_refs = tuple(
        ref for ref in (requested_ref, governed_ref, result_ref) if ref is not None
    )
    result_digest = (
        result.outcome_digest
        if result is not None
        else candidate.idempotency.semantic_input_digest
    )
    return ToolFactAcceptedAck(
        accepted_event_refs=accepted_event_refs,
        tool_fact_id=f"tool-fact-{tool_call_id}",
        tool_call_requested_event_ref=requested_ref,
        tool_call_governed_event_ref=governed_ref,
        tool_result_event_ref=result_ref,
        result_payload_ref=(
            HostPayloadRef("payload-ref", result.payload_digest)
            if result is not None and result.payload_digest is not None
            else None
        ),
        result_digest=result_digest,
        reuse_prior_event_refs=_candidate_reuse_prior_event_refs(candidate),
        diagnostic_refs=candidate.diagnostics.diagnostic_refs,
        idempotency_record_ref=f"idempotency-{tool_call_id}",
    )


def _candidate_duplicate(
    candidate: ToolFactAcceptCandidate,
) -> ToolAcceptDuplicateGovernance:
    """返回 candidate 的 duplicate governance 子结构。

    :param candidate: 工具事实候选。
    :returns: 非空 duplicate governance 子结构。
    """

    duplicate = candidate.governance.duplicate
    assert duplicate is not None
    return duplicate


def _candidate_duplicate_decision(
    candidate: ToolFactAcceptCandidate,
) -> DuplicateDecisionKind:
    """返回 candidate 的 duplicate governance 决策。

    :param candidate: 工具事实候选。
    :returns: duplicate governance 决策类别。
    """

    return _candidate_duplicate(candidate).duplicate_decision


def _candidate_duplicate_scope(
    candidate: ToolFactAcceptCandidate,
) -> DuplicateGovernanceScope:
    """返回 candidate 的 duplicate governance 作用域。

    :param candidate: 工具事实候选。
    :returns: 非空 duplicate governance 作用域。
    """

    duplicate_scope = _candidate_duplicate(candidate).duplicate_scope
    assert duplicate_scope is not None
    return duplicate_scope


def _candidate_reuse_prior_event_refs(
    candidate: ToolFactAcceptCandidate,
) -> tuple[HostEventRef, ...]:
    """返回 candidate 的 duplicate prior refs。

    :param candidate: 工具事实候选。
    :returns: candidate 携带的 prior accepted event refs。
    """

    return _candidate_duplicate(candidate).reuse_prior_event_refs
