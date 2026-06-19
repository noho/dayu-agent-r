"""Host compaction operation async retry tests。"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

import dayu.host.compaction_operation as compaction_operation
import dayu.host.dispatch as dispatch
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
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
    CompactMaterialBlock,
    CompactMaterialBlockKind,
    CompactMaterialSection,
    CompactSegmentTrigger,
    CompactQualityCheckResultVNext,
    CompactQualityIssueVNext,
    CompactionRequest,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
    PromptLocalProvenanceEntry,
)
from dayu.host.compaction_evidence import (
    SelectedEvidenceBlockRef,
    collect_selected_compaction_request_evidence_inputs,
)
from dayu.host.compaction_operation import run_compaction_operation
from dayu.host.compaction_operation import (
    CompactorProposalManifestReference,
    CompactorProposalRunInput,
)
from dayu.host.context_events import build_context_compaction_attempt_rejected_payload
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.schema import (
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
)
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from tests.host.fake_cancellation import StubCancellationToken
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

    def __init__(self, token: StubCancellationToken) -> None:
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
        ),
        tool_schemas=(),
        tool_executor=_RejectingToolExecutor(),
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
    )

    assert result.accepted_candidate is None
    assert result.quality_result is None
    assert len(result.rejected_attempts) == 2
    assert result.rejected_attempts[0].repairable is True
    assert result.rejected_attempts[1].repairable is False
    assert "proposal failed" in result.rejected_attempts[0].diagnostic_refs[0]
    assert result.failure_reason is not None


@pytest.mark.asyncio
async def test_rejected_attempt_diagnostic_captures_invalid_previous_reference(
    tmp_path: Path,
) -> None:
    """previous_compacted_view parse 失败时生成可持久化 diagnostic artifact。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: diagnostic 缺失或 raw material 泄漏到 EventLog payload。
    """

    raw_text = "reference_continuity=previous_fact text=offending raw continuity"
    request = _request_with_previous_reference_continuity(raw_text)
    result = await run_compaction_operation(
        request=request,
        compactor=FakeContextCompactor(),
        max_attempts=1,
        cancellation_token=StubCancellationToken(),
        compaction_operation_id="operation-invalid-reference",
    )

    assert result.accepted_candidate is None
    assert result.failure_reason == "proposal_failed"
    assert len(result.rejected_attempts) == 1
    rejected = result.rejected_attempts[0]
    assert rejected.proposal_manifest_ref is None
    assert rejected.proposal_manifest_digest is None
    diagnostic = rejected.diagnostic
    assert diagnostic is not None
    assert diagnostic.failure_stage == "previous_compacted_view_parse"
    assert diagnostic.parser_or_validator == "previous_reference_continuity"
    assert diagnostic.exception_class == "ValueError"
    assert diagnostic.exception_message == "previous reference continuity text is invalid"
    assert diagnostic.offending_block is not None
    assert diagnostic.offending_block.kind == "reference_continuity"
    assert diagnostic.offending_block.block_label == "P-REF"
    assert diagnostic.offending_block.text_length == len(raw_text)

    reference, artifact_json, metadata_json = _write_and_read_rejected_diagnostic(
        tmp_path,
        diagnostic=diagnostic,
        operation_id="operation-invalid-reference",
        attempt_number=rejected.attempt_number,
    )
    payload = dict(
        build_context_compaction_attempt_rejected_payload(
            operation_id="operation-invalid-reference",
            attempt_number=rejected.attempt_number,
            failure_category=rejected.failure_category.value,
            repairable=rejected.repairable,
            runner_attempt_summary_refs=rejected.runner_attempt_summary_refs,
            diagnostic_refs=rejected.diagnostic_refs,
            next_policy_decision=rejected.next_policy_decision.value,
            budget_after_attempted_compact=rejected.budget_after_attempted_compact,
            proposal_manifest_ref=rejected.proposal_manifest_ref,
            proposal_manifest_digest=rejected.proposal_manifest_digest,
            diagnostic_artifact_ref=reference.payload_ref,
            diagnostic_artifact_digest=reference.payload_digest,
            failure_stage=diagnostic.failure_stage,
            diagnostic_suffix=diagnostic.diagnostic_suffix,
            parser_or_validator=diagnostic.parser_or_validator,
            exception_class=diagnostic.exception_class,
            exception_message=diagnostic.exception_message,
            offending_block_section=diagnostic.offending_block.section,
            offending_block_kind=diagnostic.offending_block.kind,
            offending_block_label=diagnostic.offending_block.block_label,
            offending_block_ordinal=diagnostic.offending_block.block_ordinal,
            offending_block_text_digest=diagnostic.offending_block.text_digest,
            offending_block_text_length=diagnostic.offending_block.text_length,
            material_pack_digest=diagnostic.material_pack_digest,
        )
    )

    assert payload["proposal_manifest_ref"] is None
    assert payload["diagnostic_artifact_ref"] == reference.payload_ref
    assert payload["diagnostic_artifact_digest"] == reference.payload_digest
    assert payload["failure_stage"] == "previous_compacted_view_parse"
    assert payload["offending_block_kind"] == "reference_continuity"
    assert raw_text not in canonical_json_dumps(payload)
    assert metadata_json["descriptor_kind"] == (
        "compaction_rejected_attempt_diagnostic"
    )
    assert metadata_json["event_type"] == "CONTEXT_COMPACTION_ATTEMPT_REJECTED"
    assert metadata_json["compaction_operation_id"] == "operation-invalid-reference"
    assert metadata_json["compaction_attempt_number"] == rejected.attempt_number
    assert metadata_json["failure_stage"] == "previous_compacted_view_parse"
    assert metadata_json["parser_or_validator"] == "previous_reference_continuity"
    assert metadata_json["contains_raw_material"] is True
    assert metadata_json["confidential"] is True
    assert artifact_json["proposal_manifest_ref"] is None
    assert artifact_json["failure_stage"] == "previous_compacted_view_parse"
    assert artifact_json["parser_or_validator"] == "previous_reference_continuity"
    offending = artifact_json["offending_block"]
    assert isinstance(offending, dict)
    assert offending["raw_text"] == raw_text
    assert offending["kind"] == "reference_continuity"
    previous_view = artifact_json["previous_compacted_view"]
    assert isinstance(previous_view, list)
    assert previous_view == [request.material_pack.previous_compacted_view[0].to_json()]


@pytest.mark.asyncio
async def test_run_compaction_operation_stops_before_retry_when_cancelled() -> None:
    """首次失败后 token 被取消时，不发起第二次 compactor 调用。"""

    token = StubCancellationToken()
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
        pass_queue=(request, request),
    )

    assert len(compactor.requests) == 1
    assert result.accepted_candidate is None
    assert result.failure_reason == "max_compaction_attempts_exhausted"


def test_selected_compaction_request_evidence_inputs_read_only_selected_refs(
    tmp_path: Path,
) -> None:
    """selected helper 只读取 selection 指定的证据与 raw 内容。"""

    session_id = "session-evidence-range"
    outside_session_id = "session-outside"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> None:
            """追加测试 EventLog rows。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            inside_event_id = "event-tool-result-inside"
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=inside_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(inside_event_id)
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(inside_event_id),
                    },
                ),
            )
            event_log.append_event(
                transaction,
                _event_request(
                    event_id="event-current-input",
                    session_id=session_id,
                    event_type="USER_INPUT_ACCEPTED",
                    payload={"display_text": "current input"},
                ),
            )
            outside_event_id = "event-tool-result-after-range"
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=outside_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(outside_event_id)
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(outside_event_id),
                    },
                ),
            )
            other_session_event_id = "event-tool-result-other-session"
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=other_session_event_id,
                    session_id=outside_session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(other_session_event_id)
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(other_session_event_id),
                    },
                ),
            )

        store.transaction_runner.run_write(append_rows)

        def read_inputs(
            transaction: HostTransaction,
        ) -> tuple[tuple[str, ...], tuple[tuple[str, str, tuple[str, ...]], ...]]:
            """读取共享 helper 输出的 evidence ids 与 raw context。

            :param transaction: Host transaction。
            :returns: evidence id tuple 与 raw context 摘要。
            """

            inputs = collect_selected_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                selected_evidence_block_refs=(
                    SelectedEvidenceBlockRef(
                        block_id="selected-evidence-inside",
                        tool_result_event_ref="event-tool-result-inside",
                    ),
                ),
            )
            return (
                tuple(material.accepted_evidence_id for material in inputs.evidence_materials),
                tuple(
                    (
                        item.tool_result_event_ref,
                        item.raw_result_text,
                        (item.accepted_evidence_id,),
                    )
                    for item in inputs.evidence_materials
                ),
            )

        assert store.transaction_runner.run_read(read_inputs) == (
            ("evidence:event-tool-result-inside",),
            (
                (
                    "event-tool-result-inside",
                    (
                        '{"kind":"completed","result":{"meta":null,"ok":true,'
                        '"value":{"content":"raw content event-tool-result-inside",'
                        '"event_id":"event-tool-result-inside"}}}'
                    ),
                    ("evidence:event-tool-result-inside",),
                ),
            ),
        )


def test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview(
    tmp_path: Path,
) -> None:
    """Selected evidence reader 从 descriptor 读取 raw payload，不读 envelope preview。"""

    session_id = "session-selected-descriptor"
    event_id = "event-tool-result-descriptor"
    tool_call_event_id = "event-tool-call-descriptor"
    tool_arguments: dict[str, JsonValue] = {
        "company": "MSFT",
        "filing": "10-K",
        "section": "revenue note",
    }
    arguments_digest = _accepted_arguments_digest(tool_arguments)
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_row(transaction: HostTransaction) -> None:
            """写入 descriptor payload 与 selected TOOL_RESULT_ACCEPTED。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _append_tool_call_requested_event(
                transaction,
                event_log,
                event_id=tool_call_event_id,
                session_id=session_id,
                tool_call_id=f"tool-call:{event_id}",
                arguments=tool_arguments,
            )
            payload = {
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_tool_request(
                        event_id,
                        tool_call_requested_event_ref=tool_call_event_id,
                        tool_call_id=f"tool-call:{event_id}",
                        normalized_arguments_digest=arguments_digest,
                        payload_ref="payload-selected-descriptor",
                        payload_digest=None,
                    )
                ),
                "raw_tool_outcome": _raw_tool_outcome(event_id),
            }
            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-selected-descriptor",
                    payload_id="sqlite-payload-selected-descriptor",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json=payload,
                ),
            )
            event_log.append_event(
                transaction,
                _event_request_with_payload_ref(
                    event_id=event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload_ref=descriptor.payload_ref,
                    payload_digest=descriptor.payload_digest,
                ),
            )

        store.transaction_runner.run_write(append_row)

        def read_inputs(transaction: HostTransaction) -> tuple[str, str, tuple[str, ...]]:
            """读取 selected evidence material。

            :param transaction: Host transaction。
            :returns: raw text、query text 与 payload refs。
            """

            inputs = collect_selected_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                selected_evidence_block_refs=(
                    SelectedEvidenceBlockRef(
                        block_id="selected-evidence-1",
                        tool_result_event_ref=event_id,
                    ),
                ),
            )
            material = inputs.evidence_materials[0]
            return (
                material.raw_result_text,
                material.readable_query_text,
                material.payload_refs,
            )

        assert store.transaction_runner.run_read(read_inputs) == (
            (
                '{"kind":"completed","result":{"meta":null,"ok":true,'
                '"value":{"content":"raw content event-tool-result-descriptor",'
                '"event_id":"event-tool-result-descriptor"}}}'
            ),
            (
                '工具参数: {"arguments":{"company":"MSFT","filing":"10-K",'
                '"section":"revenue note"}}'
            ),
            ("payload-selected-descriptor",),
        )


def test_evidence_input_prefers_semantic_query_from_tool_request_atom(
    tmp_path: Path,
) -> None:
    """Selected evidence query_text 优先使用 durable semantic query。"""

    session_id = "session-selected-semantic-query"
    event_id = "event-tool-result-semantic-query"
    tool_call_event_id = "event-tool-call-semantic-query"
    tool_arguments: dict[str, JsonValue] = {"ticker": "MSFT", "period": "FY2025"}
    semantic_query = "读取 MSFT FY2025 年报中的收入分部说明"
    arguments_digest = _accepted_arguments_digest(tool_arguments)
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> None:
            """写入 semantic query request atom 与 selected evidence。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _append_tool_call_requested_event(
                transaction,
                event_log,
                event_id=tool_call_event_id,
                session_id=session_id,
                tool_call_id=f"tool-call:{event_id}",
                arguments=tool_arguments,
                semantic_query_text=semantic_query,
            )
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_tool_request(
                                    event_id,
                                    tool_call_requested_event_ref=tool_call_event_id,
                                    tool_call_id=f"tool-call:{event_id}",
                                    normalized_arguments_digest=arguments_digest,
                                )
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(event_id),
                    },
                ),
            )

        store.transaction_runner.run_write(append_rows)

        assert _collect_selected_query_text(
            store,
            event_log,
            session_id=session_id,
            event_id=event_id,
        ) == semantic_query


def test_evidence_input_semantic_query_text_is_not_truncated(
    tmp_path: Path,
) -> None:
    """Selected evidence query 只规范化，不按旧 1200 字符截断。"""

    session_id = "session-selected-long-semantic-query"
    event_id = "event-tool-result-long-semantic-query"
    tool_call_event_id = "event-tool-call-long-semantic-query"
    tool_arguments: dict[str, JsonValue] = {"ticker": "MSFT", "period": "FY2025"}
    long_query = " ".join(
        ("读取 MSFT FY2025 年报收入分部说明", *("segment" for _ in range(240)))
    )
    arguments_digest = _accepted_arguments_digest(tool_arguments)
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> None:
            """写入超长 semantic query request atom 与 selected evidence。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _append_tool_call_requested_event(
                transaction,
                event_log,
                event_id=tool_call_event_id,
                session_id=session_id,
                tool_call_id=f"tool-call:{event_id}",
                arguments=tool_arguments,
                semantic_query_text=long_query,
            )
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_tool_request(
                                    event_id,
                                    tool_call_requested_event_ref=tool_call_event_id,
                                    tool_call_id=f"tool-call:{event_id}",
                                    normalized_arguments_digest=arguments_digest,
                                )
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(event_id),
                    },
                ),
            )

        store.transaction_runner.run_write(append_rows)

        query_text = _collect_selected_query_text(
            store,
            event_log,
            session_id=session_id,
            event_id=event_id,
        )
        assert query_text == long_query
        assert len(query_text) > 1200
        assert "[truncated_query_text]" not in query_text


def test_evidence_input_missing_tool_request_atom_emits_limited_signal(
    tmp_path: Path,
) -> None:
    """Selected evidence 缺 durable request atom 时 query_text 明确 limited-signal。"""

    session_id = "session-selected-missing-tool-request"
    event_id = "event-tool-result-missing-request"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_row(transaction: HostTransaction) -> None:
            """写入缺少 request ref 的 selected evidence。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            event_log.append_event(
                transaction,
                _event_request(
                    event_id=event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(event_id)
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(event_id),
                    },
                ),
            )

        store.transaction_runner.run_write(append_row)

        query_text = _collect_selected_query_text(
            store,
            event_log,
            session_id=session_id,
            event_id=event_id,
        )
        assert query_text.startswith("状态=limited_signal；")
        assert "已验收工具请求参数材料缺失" in query_text
        assert "tool-call" not in query_text
        assert event_id not in query_text


def test_evidence_block_shares_durable_query_text_without_chunking(
    tmp_path: Path,
) -> None:
    """长 evidence 默认不 chunk，单个 block 使用同一 durable request 的 query_text。"""

    session_id = "session-selected-query-no-chunk"
    event_id = "event-tool-result-query-no-chunk"
    tool_call_event_id = "event-tool-call-query-no-chunk"
    tool_arguments: dict[str, JsonValue] = {"ticker": "MSFT", "chapter": "MD&A"}
    arguments_digest = _accepted_arguments_digest(tool_arguments)
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> None:
            """写入长 selected evidence。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            _append_tool_call_requested_event(
                transaction,
                event_log,
                event_id=tool_call_event_id,
                session_id=session_id,
                tool_call_id=f"tool-call:{event_id}",
                arguments=tool_arguments,
            )
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_tool_request(
                                    event_id,
                                    tool_call_requested_event_ref=tool_call_event_id,
                                    tool_call_id=f"tool-call:{event_id}",
                                    normalized_arguments_digest=arguments_digest,
                                )
                            )
                        ),
                        "raw_tool_outcome": {
                            "kind": "completed",
                            "result": {
                                "ok": True,
                                "value": {"content": "x" * 9000},
                                "meta": None,
                            },
                        },
                    },
                ),
            )

        store.transaction_runner.run_write(append_rows)

        def read_query_texts(transaction: HostTransaction) -> tuple[tuple[str, str], ...]:
            """读取 evidence label 与 query_text。

            :param transaction: Host transaction。
            :returns: ``(label, query_text)`` tuple。
            """

            inputs = collect_selected_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                selected_evidence_block_refs=(
                    SelectedEvidenceBlockRef(
                        block_id="selected-evidence-no-chunk",
                        tool_result_event_ref=event_id,
                    ),
                ),
            )
            pack = build_initial_material_pack(
                current_input_ref="input-query-no-chunk",
                current_input_text="current user text",
                history_materials=(),
                evidence_materials=inputs.evidence_materials,
            )
            return tuple(
                (block.evidence_label, block.readable_query_text)
                for block in pack.evidence_material
            )

        query_texts = store.transaction_runner.run_read(read_query_texts)
        labels = tuple(label for label, _query_text in query_texts)
        assert labels == ("E1",)
        assert not {"E1.1", "E1.2", "E1.3"}.intersection(labels)
        assert all("." not in label for label in labels)
        assert len({query_text for _label, query_text in query_texts}) == 1
        assert query_texts[0][1] == '工具参数: {"arguments":{"chapter":"MD&A","ticker":"MSFT"}}'


def test_missing_or_digest_mismatch_raw_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    """Selected evidence 缺 raw payload 或 envelope digest 不匹配时 fail closed。"""

    session_id = "session-selected-digest-mismatch"
    missing_raw_event_id = "event-tool-result-missing-raw-selected"
    mismatch_event_id = "event-tool-result-digest-mismatch"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> None:
            """写入缺 raw 与 digest mismatch 的 selected events。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            event_log.append_event(
                transaction,
                _event_request(
                    event_id=missing_raw_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(missing_raw_event_id)
                            )
                        )
                    },
                ),
            )
            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-digest-mismatch",
                    payload_id="sqlite-payload-digest-mismatch",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event_with_payload_ref(
                                    mismatch_event_id,
                                    payload_ref="payload-digest-mismatch",
                                    payload_digest=_DIGEST,
                                )
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(mismatch_event_id),
                    },
                ),
            )
            event_log.append_event(
                transaction,
                _event_request_with_payload_ref(
                    event_id=mismatch_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload_ref=descriptor.payload_ref,
                    payload_digest=descriptor.payload_digest,
                ),
            )

        store.transaction_runner.run_write(append_rows)

        with pytest.raises(HostDurableError, match="raw_tool_outcome"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=missing_raw_event_id,
            )
        with pytest.raises(HostDurableError, match="payload digest mismatch"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=mismatch_event_id,
            )


def test_no_result_preview_field_is_read_or_rendered(tmp_path: Path) -> None:
    """旧 result_preview 字段出现时不读取、不渲染、不回退。"""

    session_id = "session-result-preview-rejected"
    event_id = "event-tool-result-preview"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_event(event_id)
                ),
                "raw_tool_outcome": _raw_tool_outcome(event_id),
                "result_preview": "legacy preview must not be used",
            },
        )

        with pytest.raises(HostDurableError, match="result_preview"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=event_id,
            )


def test_selected_compaction_request_evidence_inputs_allow_empty_without_envelope(
    tmp_path: Path,
) -> None:
    """selected TOOL_RESULT_ACCEPTED 无 envelope 时允许显式空 evidence 输入。"""

    session_id = "session-no-evidence"
    event_id = "event-tool-result-without-envelope"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={"tool_name": "legacy-free"},
        )

        assert (
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=event_id,
            )
            == ()
        )


def test_compaction_request_evidence_inputs_reject_malformed_envelope(
    tmp_path: Path,
) -> None:
    """accepted_evidence_envelope 结构损坏时 fail closed。"""

    session_id = "session-malformed-envelope"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-tool-result-malformed-envelope"
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={"accepted_evidence_envelope": {"evidence_id": "evidence:bad"}},
        )

        with pytest.raises(HostDurableError, match="canonical evidence envelope"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=event_id,
            )


def test_compaction_request_evidence_inputs_reject_missing_raw_tool_outcome(
    tmp_path: Path,
) -> None:
    """canonical evidence 对应 raw 工具结果缺失时 fail closed。"""

    session_id = "session-missing-raw-tool-outcome"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-tool-result-missing-raw"
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_event(event_id)
                )
            },
        )

        with pytest.raises(HostDurableError, match="raw_tool_outcome"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=event_id,
            )


def test_compaction_request_evidence_inputs_reject_envelope_producer_mismatch(
    tmp_path: Path,
) -> None:
    """canonical evidence producer_event_ref 必须匹配 EventLog row id。"""

    session_id = "session-envelope-mismatch"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-tool-result-mismatch"
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_event("event-tool-result-other")
                ),
                "raw_tool_outcome": _raw_tool_outcome(event_id),
            },
        )

        with pytest.raises(HostDurableError, match="producer_event_ref mismatch"):
            _collect_selected_evidence_ids(
                store,
                event_log,
                session_id=session_id,
                event_id=event_id,
            )


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (
            {"accepted_candidate": "not-object"},
            "accepted_candidate must be object",
        ),
        (
            {"accepted_candidate": {"evidence_backed_facts": "not-list"}},
            "evidence_backed_facts must be list",
        ),
        (
            {"accepted_candidate": {"evidence_backed_facts": ["not-object"]}},
            "evidence_backed_facts\\[0\\] must be object",
        ),
    ),
)
def test_compaction_request_evidence_inputs_reject_malformed_compacted_payload(
    tmp_path: Path, payload: JsonValue, message: str
) -> None:
    """CONTEXT_COMPACTED fact refs 相关 payload 损坏时 fail closed。

    :param tmp_path: pytest 临时目录。
    :param payload: malformed CONTEXT_COMPACTED payload。
    :param message: 期望错误消息片段。
    """

    session_id = "session-malformed-compacted"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-context-compacted-malformed"
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="CONTEXT_COMPACTED",
            payload=payload,
        )

        with pytest.raises(HostDurableError, match=message):
            _collect_selected_fact_refs(
                store,
                event_log,
                session_id=session_id,
                event_id=event_id,
            )


def test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids(
    tmp_path: Path,
) -> None:
    """evidence material 按 accepted evidence id 去重并保留首个。"""

    session_id = "session-duplicate-evidence"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def append_rows(transaction: HostTransaction) -> int:
            """追加重复 evidence id 的 accepted tool events。

            :param transaction: Host transaction。
            :returns: range 结束 event sequence。
            """

            first_event_id = "event-tool-result-duplicate-first"
            second_event_id = "event-tool-result-duplicate-second"
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=first_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(
                                _accepted_evidence_envelope_for_event(first_event_id)
                            )
                        ),
                        "raw_tool_outcome": _raw_tool_outcome(first_event_id),
                    },
                ),
            )
            duplicate_envelope = AcceptedEvidenceEnvelope(
                evidence_id=f"evidence:{first_event_id}",
                producer_event_ref=second_event_id,
                tool_name="fins.search",
                tool_call_id=f"tool-call:{second_event_id}",
                tool_query=AcceptedEvidenceToolQuery(
                    tool_call_requested_event_ref=None,
                    normalized_arguments_digest=_DIGEST,
                    semantic_input_digest=_DIGEST,
                ),
                result_ref=AcceptedEvidenceResultRef(
                    payload_ref=None,
                    payload_digest=_DIGEST,
                    outcome_digest=_DIGEST,
                    truncation_applied=False,
                ),
                source_refs=(),
                locator_refs=(),
            )
            return event_log.append_event(
                transaction,
                _event_request(
                    event_id=second_event_id,
                    session_id=session_id,
                    event_type="TOOL_RESULT_ACCEPTED",
                    payload={
                        "accepted_evidence_envelope": (accepted_evidence_envelope_to_json_value(duplicate_envelope)),
                        "raw_tool_outcome": _raw_tool_outcome(second_event_id),
                    },
                ),
            ).row.event_sequence

        store.transaction_runner.run_write(append_rows)

        def read_inputs(transaction: HostTransaction) -> tuple[str, ...]:
            """读取 selected helper 输出的去重 evidence ids。

            :param transaction: Host transaction。
            :returns: evidence id tuple。
            """

            inputs = collect_selected_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                selected_evidence_block_refs=(
                    SelectedEvidenceBlockRef(
                        block_id="selected-evidence-first",
                        tool_result_event_ref="event-tool-result-duplicate-first",
                    ),
                    SelectedEvidenceBlockRef(
                        block_id="selected-evidence-second",
                        tool_result_event_ref="event-tool-result-duplicate-second",
                    ),
                ),
            )
            return tuple(material.accepted_evidence_id for material in inputs.evidence_materials)

        assert store.transaction_runner.run_read(read_inputs) == ("evidence:event-tool-result-duplicate-first",)


def test_compaction_request_evidence_inputs_collect_run_succeeded_raw_context(
    tmp_path: Path,
) -> None:
    """RUN_SUCCEEDED assistant conclusion 进入 history material。"""

    session_id = "session-run-succeeded-raw-context"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-run-succeeded-summary"
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="RUN_SUCCEEDED",
            payload={"final_answer": "本轮回答中的稳定结论摘要"},
        )

        def read_history_material(
            transaction: HostTransaction,
        ) -> tuple[tuple[str, CompactMaterialBlockKind, str], ...]:
            """读取共享 helper 输出的 history material 摘要。

            :param transaction: Host transaction。
            :returns: history material 摘要 tuple。
            """

            inputs = collect_selected_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                selected_evidence_block_refs=(),
                selected_history_event_refs=(event_id,),
            )
            return tuple(
                (
                    item.canonical_source_ref,
                    item.kind,
                    item.text,
                )
                for item in inputs.history_materials
            )

        assert store.transaction_runner.run_read(read_history_material) == (
            (
                event_id,
                CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
                "本轮回答中的稳定结论摘要",
            ),
        )


def test_compaction_request_evidence_inputs_collect_terminal_content(
    tmp_path: Path,
) -> None:
    """RUN_SUCCEEDED terminal artifact content 进入 history material。"""

    session_id = "session-run-succeeded-terminal-content"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-run-succeeded-terminal-content"

        def append_event(transaction: HostTransaction) -> None:
            """写入 terminal artifact 与 RUN_SUCCEEDED descriptor。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-terminal-content",
                    payload_id="sqlite-terminal-content",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "content": "terminal artifact final answer",
                        "summary_text": "terminal artifact summary",
                    },
                ),
            )
            event_log.append_event(
                transaction,
                _event_request(
                    event_id=event_id,
                    session_id=session_id,
                    event_type="RUN_SUCCEEDED",
                    payload={
                        "summary_text": "run summary should not be used",
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": descriptor.payload_digest,
                    },
                ),
            )

        store.transaction_runner.run_write(append_event)

        def read_history_material(transaction: HostTransaction) -> tuple[str, ...]:
            """读取共享 helper 输出的 history material 文本。

            :param transaction: Host transaction。
            :returns: history material 文本 tuple。
            """

            inputs = collect_selected_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                selected_evidence_block_refs=(),
                selected_history_event_refs=(event_id,),
            )
            return tuple(item.text for item in inputs.history_materials)

        assert store.transaction_runner.run_read(read_history_material) == (
            "terminal artifact final answer",
        )


def test_compaction_request_evidence_inputs_ignore_summary_only_run_succeeded(
    tmp_path: Path,
) -> None:
    """只有 summary_text 或 nested summary 时不生成 assistant answer material。"""

    session_id = "session-run-succeeded-summary-only"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        event_id = "event-run-succeeded-summary-only"
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=event_id,
            session_id=session_id,
            event_type="RUN_SUCCEEDED",
            payload={
                "summary_text": "run summary should not be used",
                "summary": {"summary_text": "nested summary should not be used"},
            },
        )

        def read_history_material(transaction: HostTransaction) -> tuple[str, ...]:
            """读取共享 helper 输出的 history material 文本。

            :param transaction: Host transaction。
            :returns: history material 文本 tuple。
            """

            inputs = collect_selected_compaction_request_evidence_inputs(
                transaction,
                event_log,
                session_id=session_id,
                selected_evidence_block_refs=(),
                selected_history_event_refs=(event_id,),
            )
            return tuple(item.text for item in inputs.history_materials)

        assert store.transaction_runner.run_read(read_history_material) == ()


def test_compaction_request_evidence_inputs_use_stable_derived_fact_refs(
    tmp_path: Path,
) -> None:
    """CONTEXT_COMPACTED candidate refs 派生为跨 compact event 唯一 memory item refs。"""

    session_id = "session-derived-fact-ref"
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()
        compacted_event_id = "event-context-compacted-derived"
        _append_event_and_return_sequence(
            store,
            event_log,
            event_id=compacted_event_id,
            session_id=session_id,
            event_type="CONTEXT_COMPACTED",
            payload={
                "accepted_candidate": {
                    "evidence_backed_facts": [
                        {"claim_text": "fact one"},
                        {"claim_text": "fact two"},
                    ],
                },
            },
        )

        assert _collect_selected_fact_refs(
            store,
            event_log,
            session_id=session_id,
            event_id=compacted_event_id,
        ) == (
            f"memory-item:evidence_backed_fact:vnext-fact-1:{compacted_event_id}",
            f"memory-item:evidence_backed_fact:vnext-fact-2:{compacted_event_id}",
        )


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


def _request_with_previous_reference_continuity(raw_text: str) -> CompactionRequest:
    """构造包含坏 reference continuity previous view 的 compaction request。

    :param raw_text: previous compacted view 中的 raw block text。
    :returns: compaction request。
    """

    base = _request()
    content_digest = sha256_digest_json({"text": raw_text})
    previous_block = CompactMaterialBlock(
        block_label="P-REF",
        section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
        kind=CompactMaterialBlockKind.REFERENCE_CONTINUITY,
        text=raw_text,
        size_units=len(raw_text),
        source_labels=(),
        canonical_source_refs=("event-previous-reference",),
        content_digest=content_digest,
    )
    provenance_map = {
        **base.material_pack.provenance_map,
        "P-REF": PromptLocalProvenanceEntry(
            label="P-REF",
            section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
            kind=CompactMaterialBlockKind.REFERENCE_CONTINUITY,
            canonical_source_refs=("event-previous-reference",),
            source_event_refs=("event-previous-reference",),
            content_digest=content_digest,
            accepted_evidence_id=None,
            tool_result_event_ref=None,
            tool_call_event_ref=None,
            payload_refs=(),
            artifact_refs=(),
            source_locator_refs=(),
        ),
    }
    material_pack = replace(
        base.material_pack,
        previous_compacted_view=(previous_block,),
        provenance_map=provenance_map,
    )
    return replace(
        base,
        material_pack=material_pack,
        segment_selection=initial_segment_selection(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=base.segment_selection.input_cursor,
            material_pack=material_pack,
        ),
    )


def _write_and_read_rejected_diagnostic(
    tmp_path: Path,
    *,
    diagnostic: compaction_operation.CompactionRejectedAttemptDiagnostic,
    operation_id: str,
    attempt_number: int,
) -> tuple[
    compaction_operation.CompactionRejectedAttemptDiagnosticReference,
    dict[str, JsonValue],
    dict[str, JsonValue],
]:
    """写入并读回 rejected attempt diagnostic artifact 与 descriptor metadata。

    :param tmp_path: pytest 临时目录。
    :param diagnostic: 内存态 diagnostic。
    :param operation_id: compaction operation id。
    :param attempt_number: compaction attempt number。
    :returns: diagnostic reference、artifact JSON、metadata JSON。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:

        def operation(
            transaction: HostTransaction,
        ) -> tuple[
            compaction_operation.CompactionRejectedAttemptDiagnosticReference,
            str,
            str,
        ]:
            """写入 artifact descriptor 并读回 descriptor JSON 文本。

            :param transaction: Host transaction。
            :returns: diagnostic reference、artifact relative path、metadata JSON 文本。
            """

            reference = (
                compaction_operation.write_compaction_rejected_attempt_diagnostic_artifact(
                    transaction=transaction,
                    artifact_store=LocalArtifactStore(
                        options.payload_policy.artifact_root
                    ),
                    payload_store=PayloadStore(),
                    diagnostic=diagnostic,
                    compaction_operation_id=operation_id,
                    compaction_attempt_number=attempt_number,
                )
            )
            descriptor = PayloadStore().read_payload_descriptor(
                transaction,
                reference.payload_ref,
            )
            assert descriptor is not None
            assert descriptor.payload_digest == reference.payload_digest
            assert descriptor.artifact_relative_path == reference.artifact_relative_path
            return reference, reference.artifact_relative_path, descriptor.metadata_json

        reference, relative_path, metadata_text = store.transaction_runner.run_write(
            operation
        )

        artifact_path = options.payload_policy.artifact_root / relative_path
        artifact_json = cast(
            dict[str, JsonValue],
            json.loads(artifact_path.read_text(encoding="utf-8")),
        )
        metadata_json = cast(dict[str, JsonValue], json.loads(metadata_text))
        assert reference.payload_digest == sha256_digest_json(artifact_json)
        return reference, artifact_json, metadata_json

    raise AssertionError("durable store context did not return diagnostic artifact")


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


def _accepted_evidence_envelope() -> AcceptedEvidenceEnvelope:
    """构造测试用 canonical evidence envelope。

    :returns: canonical evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id="evidence:accepted-operation",
        producer_event_ref="event-tool-result-operation",
        tool_name="fins.search",
        tool_call_id="tool-call-operation",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref="event-tool-call-operation",
            normalized_arguments_digest=_DIGEST,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref="payload:operation",
            payload_digest=_DIGEST,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _accepted_evidence_envelope_for_event(
    event_id: str,
) -> AcceptedEvidenceEnvelope:
    """构造绑定指定 TOOL_RESULT_ACCEPTED event 的 canonical evidence envelope。

    :param event_id: TOOL_RESULT_ACCEPTED event id。
    :returns: canonical evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name="fins.search",
        tool_call_id=f"tool-call:{event_id}",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=None,
            normalized_arguments_digest=_DIGEST,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=None,
            payload_digest=_DIGEST,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _accepted_evidence_envelope_for_event_with_payload_ref(
    event_id: str,
    *,
    payload_ref: str,
    payload_digest: str | None,
) -> AcceptedEvidenceEnvelope:
    """构造带 payload descriptor ref 的 canonical evidence envelope。

    :param event_id: TOOL_RESULT_ACCEPTED event id。
    :param payload_ref: payload descriptor ref。
    :param payload_digest: payload digest；未知时为 ``None``。
    :returns: canonical evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name="fins.search",
        tool_call_id=f"tool-call:{event_id}",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=None,
            normalized_arguments_digest=_DIGEST,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _accepted_evidence_envelope_for_tool_request(
    event_id: str,
    *,
    tool_call_requested_event_ref: str,
    tool_call_id: str,
    normalized_arguments_digest: str,
    payload_ref: str | None = None,
    payload_digest: str | None = _DIGEST,
) -> AcceptedEvidenceEnvelope:
    """构造带 TOOL_CALL_REQUESTED ref 的 canonical evidence envelope。

    :param event_id: TOOL_RESULT_ACCEPTED event id。
    :param tool_call_requested_event_ref: 对应 TOOL_CALL_REQUESTED event id。
    :param tool_call_id: 工具调用 id。
    :param normalized_arguments_digest: 工具参数 canonical digest。
    :param payload_ref: result payload descriptor ref。
    :param payload_digest: result payload digest。
    :returns: canonical evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name="fins.search",
        tool_call_id=tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=tool_call_requested_event_ref,
            normalized_arguments_digest=normalized_arguments_digest,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _append_tool_call_requested_event(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    session_id: str,
    tool_call_id: str,
    arguments: dict[str, JsonValue],
    semantic_query_text: str | None = None,
) -> None:
    """追加测试用 TOOL_CALL_REQUESTED durable request atom。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: TOOL_CALL_REQUESTED event id。
    :param session_id: Session id。
    :param tool_call_id: 工具调用 id。
    :param arguments: accepted 工具参数。
    :param semantic_query_text: 可选业务可读 semantic query。
    :returns: ``None``。
    """

    arguments_json = _accepted_arguments_json(arguments)
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_query_storage_kind = TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT
    semantic_query_digest: str | None = None
    if semantic_query_text is not None:
        semantic_query_storage_kind = TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT
        semantic_query_digest = sha256_digest_json(
            {"semantic_query_text": semantic_query_text}
        )
    event_log.append_event(
        transaction,
        _event_request(
            event_id=event_id,
            session_id=session_id,
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": "fins.search",
                "normalized_arguments_digest": arguments_digest,
                "arguments_json_size_bytes": len(
                    canonical_json_dumps(arguments_json).encode("utf-8")
                ),
                "arguments_storage_kind": TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
                "arguments_inline_json": arguments_json,
                "arguments_payload_ref": None,
                "arguments_payload_digest": arguments_digest,
                "semantic_input_digest": _DIGEST,
                "semantic_query_storage_kind": semantic_query_storage_kind,
                "semantic_query_text": semantic_query_text,
                "semantic_query_payload_ref": None,
                "semantic_query_digest": semantic_query_digest,
            },
        ),
    )


def _accepted_arguments_json(arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """构造 accepted arguments canonical JSON preimage。

    :param arguments: accepted 工具参数。
    :returns: 与 ToolRuntime 一致的 arguments digest preimage。
    """

    return {"arguments": dict(arguments)}


def _accepted_arguments_digest(arguments: dict[str, JsonValue]) -> str:
    """计算 accepted arguments digest。

    :param arguments: accepted 工具参数。
    :returns: canonical arguments digest。
    """

    return sha256_digest_json(_accepted_arguments_json(arguments))


def _raw_tool_outcome(event_id: str) -> JsonValue:
    """构造测试用 raw tool outcome。

    :param event_id: 工具结果事件 id。
    :returns: raw tool outcome JSON。
    """

    return {
        "kind": "completed",
        "result": {
            "ok": True,
            "value": {"event_id": event_id, "content": f"raw content {event_id}"},
            "meta": None,
        },
    }


def _append_event_and_return_sequence(
    store: HostDurableStore,
    event_log: EventLogStore,
    *,
    event_id: str,
    session_id: str,
    event_type: str,
    payload: JsonValue,
) -> int:
    """追加单条测试事件并返回 event sequence。

    :param store: Host durable store。
    :param event_log: EventLog store。
    :param event_id: event id。
    :param session_id: Session id。
    :param event_type: event type。
    :param payload: payload JSON。
    :returns: appended event sequence。
    """

    def append_row(transaction: HostTransaction) -> int:
        """在 transaction 内追加事件。

        :param transaction: Host transaction。
        :returns: appended event sequence。
        """

        return event_log.append_event(
            transaction,
            _event_request(
                event_id=event_id,
                session_id=session_id,
                event_type=event_type,
                payload=payload,
            ),
        ).row.event_sequence

    return store.transaction_runner.run_write(append_row)


def _collect_selected_evidence_ids(
    store: HostDurableStore,
    event_log: EventLogStore,
    *,
    session_id: str,
    event_id: str,
) -> tuple[str, ...]:
    """读取 selected helper 输出的 canonical evidence ids。

    :param store: Host durable store。
    :param event_log: EventLog store。
    :param session_id: Session id。
    :param event_id: selected TOOL_RESULT_ACCEPTED event id。
    :returns: evidence id tuple。
    """

    def read_inputs(transaction: HostTransaction) -> tuple[str, ...]:
        """在 transaction 内读取 selected evidence ids。

        :param transaction: Host transaction。
        :returns: evidence id tuple。
        """

        inputs = collect_selected_compaction_request_evidence_inputs(
            transaction,
            event_log,
            session_id=session_id,
            selected_evidence_block_refs=(
                SelectedEvidenceBlockRef(
                    block_id=f"selected:{event_id}",
                    tool_result_event_ref=event_id,
                ),
            ),
        )
        return tuple(material.accepted_evidence_id for material in inputs.evidence_materials)

    return store.transaction_runner.run_read(read_inputs)


def _collect_selected_query_text(
    store: HostDurableStore,
    event_log: EventLogStore,
    *,
    session_id: str,
    event_id: str,
) -> str:
    """读取 selected helper 输出的单条 readable query text。

    :param store: Host durable store。
    :param event_log: EventLog store。
    :param session_id: Session id。
    :param event_id: selected TOOL_RESULT_ACCEPTED event id。
    :returns: readable query text。
    """

    def read_inputs(transaction: HostTransaction) -> str:
        """在 transaction 内读取 query text。

        :param transaction: Host transaction。
        :returns: readable query text。
        """

        inputs = collect_selected_compaction_request_evidence_inputs(
            transaction,
            event_log,
            session_id=session_id,
            selected_evidence_block_refs=(
                SelectedEvidenceBlockRef(
                    block_id=f"selected:{event_id}",
                    tool_result_event_ref=event_id,
                ),
            ),
        )
        return inputs.evidence_materials[0].readable_query_text

    return store.transaction_runner.run_read(read_inputs)


def _collect_selected_fact_refs(
    store: HostDurableStore,
    event_log: EventLogStore,
    *,
    session_id: str,
    event_id: str,
) -> tuple[str, ...]:
    """读取 selected helper 输出的 evidence-backed fact refs。

    :param store: Host durable store。
    :param event_log: EventLog store。
    :param session_id: Session id。
    :param event_id: selected CONTEXT_COMPACTED event id。
    :returns: evidence-backed fact refs。
    """

    def read_inputs(transaction: HostTransaction) -> tuple[str, ...]:
        """在 transaction 内读取 evidence-backed fact refs。

        :param transaction: Host transaction。
        :returns: evidence-backed fact refs。
        """

        inputs = collect_selected_compaction_request_evidence_inputs(
            transaction,
            event_log,
            session_id=session_id,
            selected_evidence_block_refs=(),
            selected_fact_event_refs=(event_id,),
        )
        return inputs.evidence_backed_fact_refs

    return store.transaction_runner.run_read(read_inputs)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _event_request(
    *,
    event_id: str,
    session_id: str,
    event_type: str,
    payload: JsonValue,
) -> EventLogAppendRequest:
    """构造测试用 EventLog append request。

    :param event_id: event id。
    :param session_id: Session id。
    :param event_type: event type。
    :param payload: payload JSON。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=session_id,
        run_id="run-compaction-operation-test",
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=_NOW,
        actor="pytest",
        source="test_compaction_operation",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _event_request_with_payload_ref(
    *,
    event_id: str,
    session_id: str,
    event_type: str,
    payload_ref: str,
    payload_digest: str,
) -> EventLogAppendRequest:
    """构造带 payload descriptor ref 的测试 EventLog append request。

    :param event_id: event id。
    :param session_id: Session id。
    :param event_type: event type。
    :param payload_ref: payload descriptor ref。
    :param payload_digest: payload digest。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=session_id,
        run_id="run-compaction-operation-test",
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=_NOW,
        actor="pytest",
        source="test_compaction_operation",
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={"payload_ref": payload_ref},
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )
