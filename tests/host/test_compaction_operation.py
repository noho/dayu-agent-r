"""Host compaction operation async retry tests。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime

import pytest

import dayu.host.compaction_operation as compaction_operation
import dayu.host.dispatch as dispatch
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import runner_role_sequence_digest
from dayu.engine.contracts.messages import AgentMessageRole, SystemMessage, UserMessage
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactCandidateDiagnosticVNext,
    CompactSegmentTrigger,
    CompactQualityCheckResultVNext,
    CompactQualityIssueVNext,
    CompactionRequest,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
)
from dayu.host.compaction_operation import run_compaction_operation
from dayu.host.compaction_operation import (
    CompactorProposalManifestReference,
    CompactorProposalRunInput,
)
from dayu.host.context_events import build_context_compaction_attempt_rejected_payload
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import sha256_digest_json
from tests.host.fake_cancellation import ControllableCancellationToken
from tests.host.fake_compaction import FakeContextCompactor

_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_NOW = datetime(2026, 5, 22, 1, 2, 3, tzinfo=UTC)
_DEFAULT_SENSITIVE_EXCEPTION_MESSAGE = (
    "provider failed Bearer bearer-secret "
    "api_key=plain-secret token=token-secret secret=raw-secret "
    "password=password-secret api key api-key-space-secret "
    "apikey=apikey-secret api-key:api-key-colon-secret "
    "api-key: api-key-colon-space-secret"
)


class _FailOnceCompactor(FakeContextCompactor):
    """首次 proposal 失败，第二次返回 fake candidate。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """执行可重试 proposal。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        :raises RuntimeError: 首次调用时模拟 proposal failure。
        """

        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("proposal failed once")
        return await self._fake.compact(request, cancellation_token)


class _AlwaysFailingCompactor(FakeContextCompactor):
    """始终 proposal 失败的 compactor。"""

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """模拟 proposal failure。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出 proposal failure。
        """

        del request
        del cancellation_token
        raise RuntimeError("proposal failed")


class _SensitiveFailingCompactor(FakeContextCompactor):
    """始终抛出带敏感字段的 proposal 异常。"""

    def __init__(self, exception_message: str = _DEFAULT_SENSITIVE_EXCEPTION_MESSAGE) -> None:
        """初始化异常消息。

        :param exception_message: compactor 抛出的 provider 错误消息。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._exception_message = exception_message

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """模拟 provider 错误消息携带 secret。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出带敏感字段的 proposal failure。
        """

        del request
        del cancellation_token
        raise RuntimeError(self._exception_message)


class _EmptyMessageFailingCompactor(FakeContextCompactor):
    """始终抛出空消息 proposal 异常。"""

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """模拟 provider 抛出空消息异常。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出空消息 proposal failure。
        """

        del request
        del cancellation_token
        raise RuntimeError()


class _CancelAfterFailureCompactor(FakeContextCompactor):
    """首次失败后请求取消的 compactor。"""

    def __init__(self, token: ControllableCancellationToken) -> None:
        """初始化可控 token 与调用计数。

        :param token: 测试用可控 cancellation token。
        :returns: ``None``。
        """

        self.calls = 0
        self._token = token

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """首次 proposal 失败并在重试前请求取消。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不会返回。
        :raises RuntimeError: 首次调用时模拟 proposal failure。
        """

        del request
        del cancellation_token
        self.calls += 1
        self._token.request_cancel("test_cancelled")
        raise RuntimeError("proposal failed before cancellation")


class _QualityRejectOnceCompactor(FakeContextCompactor):
    """首次返回 quality reject candidate，第二次返回 accepted candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """返回可修复 quality rejection 后的成功 candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request, cancellation_token)
        if self.calls == 1:
            assert candidate.session_summary is not None
            return replace(
                candidate,
                session_summary=replace(
                    candidate.session_summary,
                    source_labels=("C1",),
                ),
            )
        return candidate


class _HardThresholdOnceCompactor(FakeContextCompactor):
    """首次 compact 后仍越过 hard threshold，第二次返回 accepted candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """返回 hard-threshold rejection 后的成功 candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request, cancellation_token)
        if self.calls == 1:
            assert candidate.session_summary is not None
            return replace(
                candidate,
                session_summary=replace(
                    candidate.session_summary,
                    summary_text="x" * 2000,
                ),
            )
        return candidate


class _DiagnosticsOnlyLargeCompactor(FakeContextCompactor):
    """返回业务文本很小但 diagnostic 很大的 candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor。

        :returns: ``None``。
        """

        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """返回只在 diagnostics 中携带大文本的 candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        candidate = await self._fake.compact(request, cancellation_token)
        return replace(
            candidate,
            diagnostics=(
                CompactCandidateDiagnosticVNext(
                    code="large_diagnostic",
                    text="diagnostic text " * 200,
                ),
            ),
        )


class _RecordingCompactor(FakeContextCompactor):
    """记录 multi-pass request 并返回 fake candidate。"""

    def __init__(self) -> None:
        """初始化 recorder。

        :returns: ``None``。
        """

        self.requests: list[CompactionRequest] = []
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """记录 request 并返回 fake candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        """

        self.requests.append(request)
        return await self._fake.compact(request, cancellation_token)


class _DistinctFactPassCompactor(FakeContextCompactor):
    """每个 pass 返回不同 evidence fact tuple 的 deterministic compactor。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """返回带 pass 差异的 accepted vNext fact tuple。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request, cancellation_token)
        assert len(candidate.evidence_backed_facts) > 0
        first_fact = candidate.evidence_backed_facts[0]
        return replace(
            candidate,
            evidence_backed_facts=(
                replace(
                    first_fact,
                    claim_text=f"whole vNext fact tuple from pass {self.calls}",
                ),
            ),
        )


class _SecondPassFailingCompactor(FakeContextCompactor):
    """第一 pass 成功，第二 pass proposal 失败。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """第二次调用抛出 proposal failure。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        :raises RuntimeError: 第二次调用时抛出。
        """

        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("second pass failed")
        return await self._fake.compact(request, cancellation_token)


class _DistinctPassCompactor(FakeContextCompactor):
    """每个 pass 返回不同 summary / patch 的 deterministic compactor。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """返回带 pass 差异的 accepted candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request, cancellation_token)
        assert candidate.session_summary is not None
        return replace(
            candidate,
            session_summary=replace(
                candidate.session_summary,
                summary_text=f"whole vNext candidate from pass {self.calls}",
            ),
        )


class _RejectingToolExecutor(ToolExecutor):
    """测试用禁用工具 executor。"""

    async def execute(
        self,
        request: BatchToolExecutionRequest,
    ) -> BatchToolExecutionOutcome:
        """返回空工具执行结果。

        :param request: Engine 工具执行请求。
        :returns: 空 outcome。
        """

        del request
        return BatchToolExecutionOutcome(records=())


class _RecordingProposalManifestRecorder:
    """记录 proposal manifest recorder 调用。"""

    def __init__(self, events: list[str]) -> None:
        """初始化调用记录。

        :param events: 共享顺序记录列表。
        :returns: ``None``。
        """

        self.events = events
        self.references: list[CompactorProposalManifestReference] = []

    def record_compactor_proposal_manifest(
        self,
        *,
        request: CompactionRequest,
        prepared_input: CompactorProposalRunInput,
        compaction_operation_id: str,
        compaction_attempt_number: int,
    ) -> CompactorProposalManifestReference:
        """记录 proposal manifest 并返回 deterministic ref。

        :param request: Host compaction request。
        :param prepared_input: prepared proposal input。
        :param compaction_operation_id: operation id。
        :param compaction_attempt_number: attempt 序号。
        :returns: fake manifest reference。
        """

        self.events.append("record")
        reference = CompactorProposalManifestReference(
            manifest_event_id=f"event-manifest-{compaction_attempt_number}",
            manifest_payload_ref=(
                f"runner-call-manifest:{compaction_operation_id}:"
                f"{compaction_attempt_number}"
            ),
            manifest_digest=prepared_input.role_sequence_digest,
            compactor_input_projection_ref=(
                f"compactor-input-projection:{request.run_id}:"
                f"{compaction_attempt_number}"
            ),
            compactor_input_projection_digest=(
                prepared_input.compactor_input_projection_digest
            ),
        )
        self.references.append(reference)
        return reference


class _PreparedManifestCompactor(FakeContextCompactor):
    """支持 prepared proposal manifest 的测试 compactor。"""

    def __init__(self, events: list[str], *, fail_run: bool = False) -> None:
        """初始化 fake compactor。

        :param events: 共享顺序记录列表。
        :param fail_run: run 阶段是否抛出 proposal failure。
        :returns: ``None``。
        """

        self.events = events
        self.fail_run = fail_run
        self._fake = FakeContextCompactor()

    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
    ) -> CompactorProposalRunInput:
        """构造测试用 prepared proposal input。

        :param request: Host compaction request。
        :param cancellation_token: Host cancellation token。
        :param compaction_operation_id: operation id。
        :param compaction_attempt_number: attempt 序号。
        :returns: prepared proposal input。
        """

        del cancellation_token
        self.events.append("prepare")
        compact_input = compaction_operation.conversation_compact_input_vnext_from_material_pack(
            request.material_pack
        )
        agent_request = _proposal_agent_request(
            request,
            compaction_operation_id=compaction_operation_id,
            compaction_attempt_number=compaction_attempt_number,
        )
        roles = tuple(message.role.value for message in agent_request.messages)
        projection = {
            "projection_kind": "compactor_input_projection",
            "compaction_request_digest": request.digest(),
        }
        return CompactorProposalRunInput(
            compact_input=compact_input,
            agent_request=agent_request,
            compaction_request_digest=request.digest(),
            compactor_engine_run_id=agent_request.run_id,
            message_count=len(agent_request.messages),
            role_sequence_digest=runner_role_sequence_digest(roles),
            system_prompt_asset_digest=_DIGEST,
            user_prompt_template_digest=_DIGEST,
            user_prompt_digest=sha256_digest_json({"user_prompt": "user"}),
            compactor_input_projection=projection,
            compactor_input_projection_digest=sha256_digest_json(projection),
        )

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> ConversationCompactOutputVNext:
        """执行 prepared proposal。

        :param prepared_input: prepared proposal input。
        :returns: fake candidate。
        :raises RuntimeError: ``fail_run`` 为真时抛出。
        """

        self.events.append("run")
        if self.fail_run:
            raise RuntimeError("prepared proposal failed")
        return await self._fake.compact(
            _request(),
            prepared_input.agent_request.cancellation_token,
        )


class _PreparedCancelledCompactor(_PreparedManifestCompactor):
    """prepared proposal run 阶段请求取消并抛出 CancelledError。"""

    def __init__(self, events: list[str], token: ControllableCancellationToken) -> None:
        """初始化 compactor。

        :param events: 共享顺序记录列表。
        :param token: 测试用 cancellation token。
        :returns: ``None``。
        """

        super().__init__(events)
        self._token = token

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> ConversationCompactOutputVNext:
        """模拟 Host cancellation 已生效后的 proposal 取消。

        :param prepared_input: prepared proposal input。
        :returns: 不会返回。
        :raises asyncio.CancelledError: 始终抛出。
        """

        del prepared_input
        self.events.append("run")
        self._token.request_cancel("host_cancelled_during_proposal")
        raise asyncio.CancelledError()


def _proposal_agent_request(
    request: CompactionRequest,
    *,
    compaction_operation_id: str | None,
    compaction_attempt_number: int,
) -> AgentRunRequest:
    """构造测试用 compactor AgentRunRequest。

    :param request: compaction request。
    :param compaction_operation_id: operation id。
    :param compaction_attempt_number: attempt 序号。
    :returns: AgentRunRequest。
    """

    return AgentRunRequest(
        run_id=(
            f"compactor-run:{request.run_id}:"
            f"{compaction_operation_id}:{compaction_attempt_number}"
        ),
        session_id="context-compactor:test",
        attempt_id=None,
        execution_id=None,
        messages=(
            SystemMessage(role=AgentMessageRole.SYSTEM, content="system"),
            UserMessage(role=AgentMessageRole.USER, content="user"),
        ),
        disable_tools=True,
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
        tool_schemas=(),
        tool_executor=_RejectingToolExecutor(),
        cancellation_token=ControllableCancellationToken(),
    )


def _runner_spec() -> RunnerSpec:
    """构造测试 RunnerSpec。

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


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_async_proposal_failure() -> None:
    """operation await async compactor，并保留 proposal failure 后 retry 行为。"""

    compactor = _FailOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert result.quality_result is not None
    assert result.quality_result.accepted is True
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].repairable is True
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_records_prepared_proposal_manifest_before_call() -> None:
    """prepared compactor 在 proposal call 前记录 manifest 并传出 accepted ref。"""

    events: list[str] = []
    recorder = _RecordingProposalManifestRecorder(events)

    result = await run_compaction_operation(
        request=_request(),
        compactor=_PreparedManifestCompactor(events),
        max_attempts=1,
        cancellation_token=ControllableCancellationToken(),
        compaction_operation_id="operation-prepared-accepted",
        proposal_manifest_recorder=recorder,
    )

    assert events == ["prepare", "record", "run"]
    assert result.accepted_candidate is not None
    assert result.accepted_proposal_manifest_ref == (
        "runner-call-manifest:operation-prepared-accepted:1"
    )
    assert result.accepted_proposal_manifest_digest == (
        recorder.references[0].manifest_digest
    )
    assert len(result.rejected_attempts) == 0


def test_compactor_proposal_manifest_uses_initial_trigger_for_first_attempt() -> None:
    """首次 compactor proposal manifest 使用专用 initial trigger reason。"""

    request = _request()
    compactor = _PreparedManifestCompactor([])
    prepared_input = compactor.prepare_compactor_proposal_run_input(
        request,
        ControllableCancellationToken(),
        compaction_operation_id="operation-trigger",
        compaction_attempt_number=1,
    )

    first_manifest = compaction_operation._compactor_runner_call_manifest_body(
        request=request,
        prepared_input=prepared_input,
        event_id="event-trigger-first",
        compaction_operation_id="operation-trigger",
        compaction_attempt_number=1,
        compactor_input_projection_ref="payload-ref-trigger-first",
    )
    retry_manifest = compaction_operation._compactor_runner_call_manifest_body(
        request=request,
        prepared_input=prepared_input,
        event_id="event-trigger-retry",
        compaction_operation_id="operation-trigger",
        compaction_attempt_number=2,
        compactor_input_projection_ref="payload-ref-trigger-retry",
    )

    assert first_manifest["runner_call_kind"] == "compactor_proposal"
    assert first_manifest["runner_call_trigger_reason"] == (
        "context_compaction_initial_proposal"
    )
    assert retry_manifest["runner_call_trigger_reason"] == (
        "context_compaction_retry_attempt"
    )


@pytest.mark.asyncio
async def test_run_compaction_operation_rejected_attempt_keeps_proposal_manifest_ref() -> None:
    """proposal failure attempt 通过 rejected summary 暴露 proposal manifest。"""

    events: list[str] = []
    recorder = _RecordingProposalManifestRecorder(events)

    result = await run_compaction_operation(
        request=_request(),
        compactor=_PreparedManifestCompactor(events, fail_run=True),
        max_attempts=1,
        cancellation_token=ControllableCancellationToken(),
        compaction_operation_id="operation-prepared-failed",
        proposal_manifest_recorder=recorder,
    )

    assert events == ["prepare", "record", "run"]
    assert result.accepted_candidate is None
    assert len(result.rejected_attempts) == 1
    rejected = result.rejected_attempts[0]
    assert rejected.proposal_manifest_ref == (
        "runner-call-manifest:operation-prepared-failed:1"
    )
    assert rejected.proposal_manifest_digest == recorder.references[0].manifest_digest


@pytest.mark.asyncio
async def test_run_compaction_operation_cancelled_proposal_keeps_manifest_ref() -> None:
    """proposal 已写 manifest 后被 Host 取消时仍返回 rejected attempt。"""

    events: list[str] = []
    token = ControllableCancellationToken()
    recorder = _RecordingProposalManifestRecorder(events)

    result = await run_compaction_operation(
        request=_request(),
        compactor=_PreparedCancelledCompactor(events, token),
        max_attempts=1,
        cancellation_token=token,
        compaction_operation_id="operation-prepared-cancelled",
        proposal_manifest_recorder=recorder,
    )

    assert events == ["prepare", "record", "run"]
    assert result.accepted_candidate is None
    assert result.failure_reason == "cancellation_requested"
    assert len(result.rejected_attempts) == 1
    rejected = result.rejected_attempts[0]
    assert rejected.failure_category == (
        compaction_operation.CompactionFailureCategory.CANCELLATION_REQUESTED
    )
    assert rejected.repairable is False
    assert rejected.proposal_manifest_ref == (
        "runner-call-manifest:operation-prepared-cancelled:1"
    )
    assert rejected.proposal_manifest_digest == recorder.references[0].manifest_digest
    assert "host_cancelled_during_proposal" in rejected.diagnostic_refs[0]


def test_accepted_compaction_missing_proposal_manifest_guard_fails_closed() -> None:
    """accepted compaction 缺 proposal manifest ref/digest 时 fail-closed。"""

    missing_ref = compaction_operation.CompactionOperationResult(
        accepted_candidate=None,
        quality_result=None,
        rejected_attempts=(),
        failure_reason=None,
        budget_after_attempted_compact=10,
        accepted_proposal_manifest_ref=None,
        accepted_proposal_manifest_digest=_DIGEST,
    )
    missing_digest = compaction_operation.CompactionOperationResult(
        accepted_candidate=None,
        quality_result=None,
        rejected_attempts=(),
        failure_reason=None,
        budget_after_attempted_compact=10,
        accepted_proposal_manifest_ref="runner-call-manifest:test",
        accepted_proposal_manifest_digest=None,
    )

    with pytest.raises(
        RuntimeError,
        match="accepted compaction is missing proposal manifest ref",
    ):
        dispatch._required_compactor_manifest_ref(missing_ref)
    with pytest.raises(
        RuntimeError,
        match="accepted compaction is missing proposal manifest digest",
    ):
        dispatch._required_compactor_manifest_digest(missing_digest)


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_quality_rejection() -> None:
    """quality_check_rejected 后 retry，并接受第二次 candidate。"""

    compactor = _QualityRejectOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert len(result.rejected_attempts) == 1
    rejected = result.rejected_attempts[0]
    assert isinstance(
        rejected.failure_category,
        compaction_operation.CompactionFailureCategory,
    )
    assert isinstance(
        rejected.next_policy_decision,
        compaction_operation.CompactionNextPolicyDecision,
    )
    assert (
        rejected.failure_category
        is compaction_operation.CompactionFailureCategory.QUALITY_CHECK_REJECTED
    )
    assert (
        rejected.next_policy_decision
        is compaction_operation.CompactionNextPolicyDecision.RETRY_SEMANTIC_REPAIR
    )
    assert rejected.repairable is True
    payload = build_context_compaction_attempt_rejected_payload(
        operation_id="operation-quality-rejected",
        attempt_number=rejected.attempt_number,
        failure_category=rejected.failure_category.value,
        repairable=rejected.repairable,
        runner_attempt_summary_refs=rejected.runner_attempt_summary_refs,
        diagnostic_refs=rejected.diagnostic_refs,
        next_policy_decision=rejected.next_policy_decision.value,
        budget_after_attempted_compact=rejected.budget_after_attempted_compact,
    )
    assert payload["failure_category"] == "quality_check_rejected"
    assert payload["next_policy_decision"] == "retry_semantic_repair"
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_retries_hard_threshold_after_compact() -> None:
    """proactive hard_threshold_after_compact 后 retry，并接受第二次 candidate。"""

    compactor = _HardThresholdOnceCompactor()
    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is not None
    assert len(result.rejected_attempts) == 1
    assert isinstance(
        result.rejected_attempts[0].failure_category,
        compaction_operation.CompactionFailureCategory,
    )
    assert (
        result.rejected_attempts[0].failure_category
        is compaction_operation.CompactionFailureCategory.HARD_THRESHOLD_AFTER_COMPACT
    )
    assert result.rejected_attempts[0].repairable is True
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_accepts_reactive_budget_estimate_overflow() -> None:
    """reactive compact 不用 compact 后估算值阻断 recovery dispatch。

    :returns: ``None``。
    :raises AssertionError: reactive path 仍按估算 hard threshold reject 时抛出。
    """

    compactor = _HardThresholdOnceCompactor()
    result = await run_compaction_operation(
        request=_request(trigger_source=ContextCompactionTriggerSource.REACTIVE),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
    )

    assert compactor.calls == 1
    assert result.accepted_candidate is not None
    assert result.quality_result is not None
    assert len(result.rejected_attempts) == 0
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_fails_after_async_attempt_budget() -> None:
    """operation await async compactor，并在 proposal attempts 耗尽后失败。"""

    result = await run_compaction_operation(
        request=_request(),
        compactor=_AlwaysFailingCompactor(),
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
    )

    assert result.accepted_candidate is None
    assert result.quality_result is None
    assert len(result.rejected_attempts) == 2
    assert result.rejected_attempts[0].repairable is True
    assert result.rejected_attempts[1].repairable is False
    assert "proposal failed" in result.rejected_attempts[0].diagnostic_refs[0]
    assert result.failure_reason is not None


@pytest.mark.asyncio
async def test_run_compaction_operation_logs_terminal_reject_as_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """terminal attempt reject 只记录为 warning，最终 fallback 决策负责 error 语义。

    :param caplog: pytest 日志捕获夹具。
    :returns: ``None``。
    :raises AssertionError: terminal reject 被记录为 error 时抛出。
    """

    logger_name = "dayu.host.compaction_operation"
    with caplog.at_level(logging.WARNING, logger=logger_name):
        result = await run_compaction_operation(
            request=_request(),
            compactor=_AlwaysFailingCompactor(),
            max_attempts=1,
            cancellation_token=ControllableCancellationToken(),
        )

    assert result.failure_reason is not None
    records = tuple(
        record
        for record in caplog.records
        if record.name == logger_name
        and "host.compaction_operation.attempt_rejected" in record.getMessage()
    )
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_run_compaction_operation_budget_excludes_candidate_diagnostics() -> None:
    """compact 后预算只统计 accepted business texts，不统计 diagnostics。

    :returns: ``None``。
    :raises AssertionError: diagnostics 被误计入 budget 或 candidate 未被接受时抛出。
    """

    request = _request()
    result = await run_compaction_operation(
        request=request,
        compactor=_DiagnosticsOnlyLargeCompactor(),
        max_attempts=1,
        cancellation_token=ControllableCancellationToken(),
        compaction_operation_id="operation-diagnostics-budget",
    )

    assert result.accepted_candidate is not None
    assert len(result.accepted_candidate.diagnostics) == 1
    assert result.budget_after_attempted_compact is not None
    assert result.budget_after_attempted_compact < request.budget_before_compact.hard_threshold_tokens
    assert result.rejected_attempts == ()
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_run_compaction_operation_stops_before_retry_when_cancelled() -> None:
    """首次失败后 token 被取消时，不发起第二次 compactor 调用。"""

    token = ControllableCancellationToken()
    compactor = _CancelAfterFailureCompactor(token)

    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        max_attempts=2,
        cancellation_token=token,
    )

    assert compactor.calls == 1
    assert result.accepted_candidate is None
    assert result.quality_result is None
    assert result.failure_reason == "cancellation_requested"
    assert len(result.rejected_attempts) == 2
    assert result.rejected_attempts[1].attempt_number == 2
    assert isinstance(
        result.rejected_attempts[1].failure_category,
        compaction_operation.CompactionFailureCategory,
    )
    assert (
        result.rejected_attempts[1].failure_category
        is compaction_operation.CompactionFailureCategory.CANCELLATION_REQUESTED
    )
    assert result.rejected_attempts[1].repairable is False
    assert "test_cancelled" in result.rejected_attempts[1].diagnostic_refs[0]


@pytest.mark.asyncio
async def test_run_compaction_operation_redacts_exception_diagnostic_refs() -> None:
    """proposal 异常诊断 ref 不能持久化 value-bearing secret 原文。

    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    result = await run_compaction_operation(
        request=_request(),
        compactor=_SensitiveFailingCompactor(),
        max_attempts=1,
        cancellation_token=ControllableCancellationToken(),
    )

    diagnostic_ref = result.rejected_attempts[0].diagnostic_refs[0]
    secret_values = (
        "bearer-secret",
        "plain-secret",
        "token-secret",
        "raw-secret",
        "password-secret",
        "api-key-space-secret",
        "apikey-secret",
        "api-key-colon-secret",
        "api-key-colon-space-secret",
    )
    for secret_value in secret_values:
        assert secret_value not in diagnostic_ref
    assert "<redacted>" in diagnostic_ref


@pytest.mark.parametrize(
    ("message", "secret_value", "redacted_fragment"),
    [
        ("provider failed Bearer bearer-secret", "bearer-secret", "Bearer <redacted>"),
        ("provider failed api_key=plain-secret", "plain-secret", "api_key=<redacted>"),
        ("provider failed token=token-secret", "token-secret", "token=<redacted>"),
        ("provider failed secret=raw-secret", "raw-secret", "secret=<redacted>"),
        ("provider failed password=password-secret", "password-secret", "password=<redacted>"),
        ("provider failed api key api-key-space-secret", "api-key-space-secret", "api key <redacted>"),
        ("provider failed apikey=apikey-secret", "apikey-secret", "apikey=<redacted>"),
        ("provider failed api-key:api-key-colon-secret", "api-key-colon-secret", "api-key:<redacted>"),
        (
            "provider failed api-key: api-key-colon-space-secret",
            "api-key-colon-space-secret",
            "api-key: <redacted>",
        ),
    ],
)
@pytest.mark.asyncio
async def test_run_compaction_operation_redacts_each_value_bearing_secret_pattern(
    message: str,
    secret_value: str,
    redacted_fragment: str,
) -> None:
    """Host proposal 异常诊断必须局部脱敏每类 value-bearing secret。

    :param message: 带单个敏感值的 proposal 异常消息。
    :param secret_value: 不应出现在 diagnostic ref 中的原始 secret value。
    :param redacted_fragment: 应保留字段上下文的脱敏片段。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    result = await run_compaction_operation(
        request=_request(),
        compactor=_SensitiveFailingCompactor(message),
        max_attempts=1,
        cancellation_token=ControllableCancellationToken(),
    )

    diagnostic_ref = result.rejected_attempts[0].diagnostic_refs[0]
    assert secret_value not in diagnostic_ref
    assert redacted_fragment in diagnostic_ref
    assert "<redacted>" in diagnostic_ref


@pytest.mark.asyncio
async def test_run_compaction_operation_keeps_plain_token_expired_context() -> None:
    """普通 token 诊断句不应被整体删除或误脱敏。

    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    result = await run_compaction_operation(
        request=_request(),
        compactor=_SensitiveFailingCompactor("provider failed: JWT token has expired"),
        max_attempts=1,
        cancellation_token=ControllableCancellationToken(),
    )

    diagnostic_ref = result.rejected_attempts[0].diagnostic_refs[0]
    assert "JWT token has expired" in diagnostic_ref
    assert "<redacted>" not in diagnostic_ref


@pytest.mark.asyncio
async def test_exception_diagnostic_suffix_uses_exception_type_for_empty_message() -> None:
    """异常消息为空时 diagnostic suffix 只保留异常类名。

    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    result = await run_compaction_operation(
        request=_request(),
        compactor=_EmptyMessageFailingCompactor(),
        max_attempts=1,
        cancellation_token=ControllableCancellationToken(),
    )

    diagnostic_ref = result.rejected_attempts[0].diagnostic_refs[0]
    assert diagnostic_ref.endswith(":RuntimeError")
    assert ":RuntimeError:" not in diagnostic_ref


@pytest.mark.asyncio
async def test_reactive_multi_pass_commits_single_merged_context_compacted() -> None:
    """reactive multi-pass 全部成功后只返回一个完整 vNext candidate。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _RecordingCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
        pass_queue=(request, request),
    )

    assert len(compactor.requests) == 2
    assert result.accepted_candidate is not None
    assert result.accepted_candidate.schema_version == "conversation_compact_output_v1"
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_reactive_multi_pass_uses_last_whole_vnext_fact_tuple() -> None:
    """reactive multi-pass 接受最后一次完整 vNext fact tuple。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _DistinctFactPassCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
        pass_queue=(request, request),
    )

    assert result.accepted_candidate is not None
    assert len(result.accepted_candidate.evidence_backed_facts) == 1
    assert result.accepted_candidate.evidence_backed_facts[0].claim_text == (
        "whole vNext fact tuple from pass 2"
    )
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_reactive_multi_pass_uses_last_whole_vnext_candidate() -> None:
    """reactive multi-pass 不合并旧字段，只接受最后一个 whole candidate。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _DistinctPassCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
        pass_queue=(request, request),
    )

    assert result.accepted_candidate is not None
    assert result.accepted_candidate.session_summary is not None
    assert result.accepted_candidate.session_summary.summary_text == (
        "whole vNext candidate from pass 2"
    )


@pytest.mark.asyncio
async def test_vnext_quality_reject_records_rejected_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """vNext quality reject 必须写入 rejected_attempts 供诊断。"""

    checks = 0

    def fake_check_vnext(
        request: ConversationCompactInputVNext,
        candidate: ConversationCompactOutputVNext,
    ) -> CompactQualityCheckResultVNext:
        """首次拒绝，第二次放行。

        :param request: vNext compaction input。
        :param candidate: vNext compaction output。
        :returns: vNext quality check fake result。
        """

        nonlocal checks
        del request, candidate
        checks += 1
        if checks == 1:
            return CompactQualityCheckResultVNext(
                accepted=False,
                rejection_reasons=(CompactQualityIssueVNext.UNKNOWN_SOURCE_LABEL,),
            )
        return CompactQualityCheckResultVNext(
                accepted=True,
                rejection_reasons=(),
        )

    monkeypatch.setattr(
        compaction_operation,
        "check_conversation_compact_output_vnext",
        fake_check_vnext,
    )
    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)

    result = await run_compaction_operation(
        request=request,
        compactor=_RecordingCompactor(),
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
    )

    assert result.accepted_candidate is not None
    assert result.failure_reason is None
    assert len(result.rejected_attempts) == 1
    assert isinstance(
        result.rejected_attempts[0].failure_category,
        compaction_operation.CompactionFailureCategory,
    )
    assert (
        result.rejected_attempts[0].failure_category
        is compaction_operation.CompactionFailureCategory.QUALITY_CHECK_REJECTED
    )
    assert result.rejected_attempts[0].repairable is True


@pytest.mark.asyncio
async def test_reactive_multi_pass_intermediate_failure_commits_single_failed_event() -> None:
    """reactive multi-pass 中间 pass 失败时 operation 整体失败且无 partial candidate。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _SecondPassFailingCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=2,
        cancellation_token=ControllableCancellationToken(),
        pass_queue=(request, request),
    )

    assert compactor.calls == 2
    assert result.accepted_candidate is None
    assert result.failure_reason == "proposal_failed"
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].attempt_number == 2


@pytest.mark.asyncio
async def test_reactive_passes_share_operation_attempt_budget() -> None:
    """operation attempt budget 是所有 reactive passes 共享的总 proposal 上限。"""

    request = _request(trigger_source=ContextCompactionTriggerSource.REACTIVE)
    compactor = _RecordingCompactor()

    result = await run_compaction_operation(
        request=request,
        compactor=compactor,
        max_attempts=1,
        cancellation_token=ControllableCancellationToken(),
        pass_queue=(request, request),
    )

    assert len(compactor.requests) == 1
    assert result.accepted_candidate is None
    assert result.failure_reason == "max_compaction_attempts_exhausted"


def _request(
    *,
    trigger_source: ContextCompactionTriggerSource = (ContextCompactionTriggerSource.PROACTIVE),
) -> CompactionRequest:
    """构造标准 compaction request。

    :param trigger_source: compaction 触发来源。
    :returns: compaction request。
    """

    is_reactive = trigger_source is ContextCompactionTriggerSource.REACTIVE
    return CompactionRequest(
        trigger_source=trigger_source,
        session_id="session-operation",
        run_id="run-operation",
        attempt_id="attempt-operation" if is_reactive else None,
        execution_id="execution-operation" if is_reactive else None,
        memory_snapshot_cursor=7,
        material_pack=_material_pack(),
        segment_selection=initial_segment_selection(
            trigger_source=(CompactSegmentTrigger.REACTIVE if is_reactive else CompactSegmentTrigger.PROACTIVE),
            input_cursor=2,
            material_pack=_material_pack(),
        ),
        evidence_backed_fact_refs=("fact-existing-1",),
        recent_raw_turn_refs=("input-1",),
        older_raw_turn_refs=("input-2",),
        existing_episode_summary_refs=("summary-1",),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=100,
            input_budget_tokens=200,
            soft_threshold_tokens=120,
            hard_threshold_tokens=400,
            safety_margin_tokens=20,
            estimator_digest=_DIGEST,
            overage_reason=None,
        ),
    )


def _material_pack():
    """构造 compaction operation 测试 material pack。

    :returns: material pack。
    """

    return build_initial_material_pack(
        current_input_ref="input-1",
        current_input_text="current user text",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="input-2",
                text="previous assistant turn",
                kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted-operation",
                accepted_evidence_id="evidence:accepted-operation",
                tool_result_event_ref="event-tool-result-operation",
                tool_call_event_ref="event-tool-call-operation",
                readable_tool_name="fins.search",
                readable_query_text="accepted tool query",
                raw_result_text="operation canonical evidence raw content",
                readable_source_text="accepted tool evidence",
                payload_refs=("payload:operation",),
            ),
        ),
    )
